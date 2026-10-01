"""QueryIntent -> SQL. Deterministic, parameterized, no LLM.

This module is the reason the semantic layer is trustworthy: the model chooses WHICH
metric and filters, this code decides HOW the number is computed. The arithmetic lives in
`05_semantic_model.yml` and nowhere else -- `compile_sql` looks the expression up by
metric name and never accepts one from the intent. So a wrong number is a metadata bug
with a named owner, not a model that invented a formula.

Three decisions here are load-bearing and each was measured against the built warehouse:

**The join is emitted only when the intent needs a column from another entity.**
`fact_production_order` has 15 columns and carries neither `region` nor
`promised_delivery_date`, so both production metrics are unfilterable and unwindowable
without joining to `fact_order_delivery`. Windowing on the fact's own
`scheduled_finish_date` instead returns 42/45 for both -- a plausible, precisely wrong
cohort. But an *unconditional* join is a different bug, so the order-grain path stays
single-table.

**Both aggregates are wrapped in `coalesce(..., 0)`.** The August window matches zero
rows: all 4 IN/August orders fall to the `not_yet_due` exclusion, and SQL `SUM()` over an
empty set returns NULL, not 0. Without the coalesce a fully correct compiler reports
"denominator: None". With it, "no eligible orders" reads as an explicit zero denominator
and a NULL value -- a refusal to divide rather than a 0% that looks like terrible
performance.

**Every column is alias-qualified.** The two fact tables share 10 column names, including
`plant`, `order_id`, and `release_date`. An unqualified reference in a joined query is
either an ambiguity error or, worse, silently the wrong table's column.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.semantic.constants import AS_OF_DATE
from src.semantic.intent import Filter, QueryIntent
from src.semantic.loader import SemanticModel

# The `__AS_OF_DATE__` token is how YAML and SQL artifacts refer to the as-of date without
# hard-coding it. `constants.AS_OF_DATE` is the single source of that value; substituting
# here is the one place the token is expanded for exclusion predicates.
AS_OF_TOKEN = "__AS_OF_DATE__"

# Stable, readable aliases keyed by entity name. Derived from the entity, not the metric,
# so the same table always gets the same alias and the emitted SQL is diffable.
_ALIASES = {
    "fact_order_delivery": "o",
    "fact_production_order": "p",
}


class CompilerError(Exception):
    """The intent cannot be compiled into governed SQL.

    Every raise site is defence in depth: the validator gates should have refused the
    intent first. Reaching one of these means either the validator was bypassed or the
    semantic model is internally inconsistent -- both of which must be loud.
    """


@dataclass(frozen=True)
class CompiledQuery:
    """SQL plus everything needed to defend the number it returns."""

    sql: str
    params: list[Any] = field(default_factory=list)
    applied_exclusions: list[str] = field(default_factory=list)
    grain: str = ""
    metric: str = ""
    # entity name -> alias, so provenance can name the tables actually read
    tables: dict[str, str] = field(default_factory=dict)


# --------------------------------------------------------------------------------------
# Metadata resolution
# --------------------------------------------------------------------------------------


def _require_metric(qi: QueryIntent, model: SemanticModel) -> dict:
    metric = model.get_metric(qi.metric)
    if metric is None:
        raise CompilerError(
            f"Metric {qi.metric!r} is not defined in the semantic model; "
            f"there is no approved expression to compile."
        )
    if metric.get("approval_state") != "approved":
        raise CompilerError(
            f"Metric {qi.metric!r} has approval_state "
            f"{metric.get('approval_state')!r}, not 'approved'; refusing to compile it."
        )
    return metric


def _require_table(model: SemanticModel, entity_name: str) -> str:
    """The physical table for an entity, or a named error.

    `raw_deliveries` is declared `materialized: false` -- it is a logical entity that
    exists so the fan-out hazard can be declared and rejected. Emitting `FROM
    raw_deliveries` would fail in DuckDB as "table does not exist", which reads like a
    broken warehouse rather than what it is: a query nobody should have been allowed to
    ask.
    """
    try:
        entity = model.get_entity(entity_name)
    except KeyError as exc:
        raise CompilerError(
            f"Entity {entity_name!r} is not declared in the semantic model."
        ) from exc
    if entity.get("materialized") is False or not entity.get("table"):
        raise CompilerError(
            f"Entity {entity_name!r} is not materialized in the warehouse "
            f"(materialized: {entity.get('materialized')!r}), so it cannot appear in a "
            f"FROM clause. It is declared to make its join cardinality reviewable."
        )
    return entity["table"]


def _alias(entity_name: str) -> str:
    return _ALIASES.get(entity_name, entity_name)


def _dimension(model: SemanticModel, metric_name: str, name: str) -> dict:
    dim = model.get_dimension(metric_name, name)
    if dim is None:
        raise CompilerError(
            f"{name!r} is not a declared dimension, so it has no governed column binding."
        )
    return dim


def _qualified(model: SemanticModel, metric_name: str, name: str) -> tuple[str, str]:
    """(alias-qualified column reference, owning entity name) for a dimension."""
    dim = _dimension(model, metric_name, name)
    entity = dim.get("entity")
    column = dim.get("column") or name
    return f"{_alias(entity)}.{column}", entity


def _find_join(model: SemanticModel, from_entity: str, to_entity: str) -> dict:
    """The declared join from one entity to another, cardinality-checked.

    Read from the entity's own `joins:` rather than hard-coded, so correcting the join in
    the model reaches the compiler on load. A `one_to_many` edge is refused: traversing it
    duplicates rows before aggregation, which is the 88.52% error.
    """
    for join in model.get_entity(from_entity).get("joins") or []:
        if join.get("to") != to_entity:
            continue
        cardinality = join.get("cardinality")
        if cardinality == "one_to_many":
            raise CompilerError(
                f"The declared join {from_entity} -> {to_entity} is {cardinality!r}, "
                f"which duplicates rows before aggregation and would overstate the "
                f"metric. Refusing to emit it."
            )
        if not join.get("join_key"):
            raise CompilerError(
                f"The join {from_entity} -> {to_entity} declares no join_key."
            )
        return join
    raise CompilerError(
        f"{from_entity!r} declares no join to {to_entity!r}, so columns on "
        f"{to_entity!r} are unreachable from this metric."
    )


# --------------------------------------------------------------------------------------
# Predicate rendering
# --------------------------------------------------------------------------------------


def _qualify_predicate(predicate: str, alias: str, columns: set[str]) -> str:
    """Prefix bare column names in a metadata predicate with the owning table's alias.

    Metric expressions and exclusion predicates are written unqualified in the YAML --
    `order_status <> 'CANC'` -- because the metric author should not have to know what
    alias a compiler will pick. Since the two fact tables share 10 column names, the
    qualification has to happen here.

    Token-boundary matching only, so `status` inside `order_status` is not rewritten
    twice; longest names first for the same reason.
    """
    import re

    out = predicate
    for column in sorted(columns, key=len, reverse=True):
        out = re.sub(
            rf"(?<![\w.]){re.escape(column)}(?![\w])",
            f"{alias}.{column}",
            out,
        )
    return out


def _render_filter(
    model: SemanticModel, qi: QueryIntent, f: Filter
) -> tuple[str, list[Any], str]:
    """(SQL fragment, params, owning entity) for one filter. Always parameterized.

    Values never reach the SQL string. Beyond the injection argument, this is what makes
    the emitted SQL stable across different questions about the same metric -- the text is
    the *shape* of the query, and the shape is what a reviewer checks.
    """
    ref, entity = _qualified(model, qi.metric, f.column)
    values = list(f.value) if isinstance(f.value, list) else [f.value]

    if f.operator == "in":
        if not values:
            raise CompilerError(f"filter on {f.column!r} uses 'in' with no values")
        placeholders = ", ".join("?" for _ in values)
        return f"{ref} IN ({placeholders})", values, entity
    if f.operator == "between":
        if len(values) != 2:
            raise CompilerError(
                f"filter on {f.column!r} uses 'between' with {len(values)} values, needs 2"
            )
        return f"{ref} BETWEEN ? AND ?", values, entity
    if f.operator in {"=", ">=", "<="}:
        if isinstance(f.value, list):
            raise CompilerError(
                f"filter on {f.column!r} uses {f.operator!r} with a list value"
            )
        return f"{ref} {f.operator} ?", [f.value], entity
    raise CompilerError(f"unsupported operator {f.operator!r} on {f.column!r}")


# --------------------------------------------------------------------------------------
# compile_sql
# --------------------------------------------------------------------------------------


def compile_sql(qi: QueryIntent, model: SemanticModel) -> CompiledQuery:
    """Turn a validated intent into governed, parameterized SQL.

    Deterministic: dimensions, filters and exclusions are iterated in declared order,
    never over a set, so the same intent always produces byte-identical SQL. That is what
    lets `test_compiler_output_is_stable` be meaningful and what makes a diff of emitted
    SQL a reviewable artifact.
    """
    metric = _require_metric(qi, model)
    base_entity = metric["entity"]
    base_table = _require_table(model, base_entity)
    base_alias = _alias(base_entity)

    expression = metric.get("expression") or {}
    numerator = expression.get("numerator")
    denominator = expression.get("denominator")
    if not numerator or not denominator:
        raise CompilerError(
            f"Metric {qi.metric!r} declares no numerator/denominator expression."
        )

    base_columns = _entity_columns(model, base_entity)

    # --- WHERE: exclusions first (always, in declared order), then intent filters ------
    where: list[str] = []
    params: list[Any] = []
    applied_exclusions: list[str] = []
    needed_entities: list[str] = []

    for exclusion in metric.get("exclusions") or []:
        key = exclusion.get("key")
        predicate = exclusion.get("predicate")
        if not key or not predicate:
            raise CompilerError(
                f"Metric {qi.metric!r} has an exclusion missing a key or predicate: "
                f"{exclusion!r}"
            )
        # An exclusion predicate is written against the metric's own entity. The one that
        # is not -- `not_yet_due` on promised_delivery_date for the production metrics --
        # is handled by resolving the column through the dimension registry below.
        owner, column_set = _predicate_owner(model, qi.metric, predicate, base_entity)
        if owner != base_entity:
            _note(needed_entities, owner)
        where.append(
            _qualify_predicate(
                predicate.replace(AS_OF_TOKEN, AS_OF_DATE.isoformat()),
                _alias(owner),
                column_set,
            )
        )
        applied_exclusions.append(key)

    for f in qi.filters:
        fragment, fparams, entity = _render_filter(model, qi, f)
        if entity != base_entity:
            _note(needed_entities, entity)
        where.append(fragment)
        params.extend(fparams)

    # --- time window on the metric's declared time dimension --------------------------
    if qi.time_window is not None:
        time_dim = metric.get("time_dimension")
        if not time_dim:
            raise CompilerError(
                f"Metric {qi.metric!r} declares no time_dimension, so a reporting "
                f"window cannot be applied."
            )
        ref, entity = _qualified(model, qi.metric, time_dim)
        if entity != base_entity:
            _note(needed_entities, entity)
        where.append(f"{ref} BETWEEN ? AND ?")
        params.extend([qi.time_window.start, qi.time_window.end])

    # --- SELECT: dimensions, then the governed arithmetic -----------------------------
    select: list[str] = []
    group_by: list[str] = []
    for name in qi.dimensions:
        ref, entity = _qualified(model, qi.metric, name)
        if entity != base_entity:
            _note(needed_entities, entity)
        select.append(f"{ref} AS {name}")
        group_by.append(ref)

    num_sql = _qualify_predicate(numerator, base_alias, base_columns)
    den_sql = _qualify_predicate(denominator, base_alias, base_columns)
    select.append(f"coalesce({num_sql}, 0) AS numerator")
    select.append(f"coalesce({den_sql}, 0) AS denominator")
    select.append(
        "CASE WHEN coalesce(%s, 0) = 0 THEN NULL "
        "ELSE 100.0 * coalesce(%s, 0) / coalesce(%s, 0) END AS value"
        % (den_sql, num_sql, den_sql)
    )

    # A grouped answer needs the count being explained, not just the rate. Derived from
    # the metric's own numerator/denominator so it stays correct for every metric rather
    # than hard-coding on_time_delivery_pct's columns.
    if group_by:
        select.append(
            f"coalesce({den_sql}, 0) - coalesce({num_sql}, 0) AS late_count"
        )

    # --- FROM / JOIN: only the entities the intent actually reached into ---------------
    from_sql = f"{base_table} {base_alias}"
    tables = {base_entity: base_alias}
    for entity in needed_entities:
        join = _find_join(model, base_entity, entity)
        table = _require_table(model, entity)
        alias = _alias(entity)
        key = join["join_key"]
        # LEFT JOIN: make-to-stock orders have no production order (SO-1015), and an
        # INNER JOIN would silently drop eligible orders and inflate the metric.
        from_sql += (
            f"\nLEFT JOIN {table} {alias} ON {base_alias}.{key} = {alias}.{key}"
        )
        tables[entity] = alias

    sql = "SELECT\n  " + ",\n  ".join(select) + f"\nFROM {from_sql}"
    if where:
        sql += "\nWHERE " + "\n  AND ".join(where)
    if group_by:
        sql += "\nGROUP BY " + ", ".join(group_by)
        sql += "\nORDER BY " + ", ".join(group_by)

    return CompiledQuery(
        sql=sql,
        params=params,
        applied_exclusions=applied_exclusions,
        grain=metric.get("grain", ""),
        metric=qi.metric,
        tables=tables,
    )


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------


def _note(entities: list[str], entity: str) -> None:
    """Record a needed entity once, preserving first-seen order (determinism)."""
    if entity not in entities:
        entities.append(entity)


def _entity_columns(model: SemanticModel, entity_name: str) -> set[str]:
    """Column names attributable to an entity, for predicate qualification.

    Sourced from the declared dimensions plus the columns named in the entity's own
    expressions and predicates. This is deliberately *not* a warehouse introspection:
    the compiler must be a pure function of the metadata so it can be tested without a
    database, and a column that is not declared anywhere in the model is not a column the
    compiler should be qualifying.
    """
    columns: set[str] = set()
    for dim in model._data.get("dimensions", []):
        if dim.get("entity") == entity_name:
            columns.add(dim.get("column") or dim["name"])
    entity = model.get_entity(entity_name)
    if entity.get("primary_key"):
        columns.add(entity["primary_key"])
    for metric in model._data.get("metrics", []):
        if metric.get("entity") != entity_name:
            continue
        expression = metric.get("expression") or {}
        for text in (expression.get("numerator"), expression.get("denominator")):
            columns |= _identifiers(text or "")
        for exclusion in metric.get("exclusions") or []:
            columns |= _identifiers(exclusion.get("predicate") or "")
    return columns - _SQL_KEYWORDS


def _identifiers(sql_fragment: str) -> set[str]:
    """Bare identifiers in a fragment, excluding string literals and SQL keywords."""
    import re

    without_literals = re.sub(r"'[^']*'", " ", sql_fragment)
    words = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", without_literals))
    return words - _SQL_KEYWORDS


_SQL_KEYWORDS = {
    "sum", "count", "avg", "min", "max", "case", "when", "then", "else", "end",
    "and", "or", "not", "null", "is", "date", "cast", "as", "coalesce", "distinct",
    "SUM", "COUNT", "AVG", "CASE", "WHEN", "THEN", "ELSE", "END", "AND", "OR",
    "NOT", "NULL", "IS", "DATE", "CAST", "AS",
}


def _predicate_owner(
    model: SemanticModel, metric_name: str, predicate: str, base_entity: str
) -> tuple[str, set[str]]:
    """Which entity an exclusion predicate is written against, plus that entity's columns.

    `not_yet_due` filters `promised_delivery_date`, which for the two production metrics
    lives on the *joined* entity, not the metric's own. Resolving the owner through the
    declared dimensions -- rather than assuming the metric's entity -- is what lets one
    exclusion be reused across metrics on different tables.
    """
    names = _identifiers(predicate)
    for name in sorted(names):
        dim = model.get_dimension(metric_name, name)
        if dim and dim.get("entity"):
            entity = dim["entity"]
            return entity, _entity_columns(model, entity) | names
    return base_entity, _entity_columns(model, base_entity) | names
