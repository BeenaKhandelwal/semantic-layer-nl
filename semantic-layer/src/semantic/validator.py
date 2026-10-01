"""The 7 gates. Pure functions over the semantic model YAML -- no DB, no network, no LLM.

This module is the trust boundary. The resolver upstream is a language model and will
sometimes be confidently wrong; these gates are what turn a wrong number into a
structured refusal that names the gate that refused. A gate that cannot reject is
decoration, so each one is written to fail on a specific, demonstrated failure mode:

  metric_approved      an invented or unapproved metric
  dimensions_declared  a group-by on a column nobody governs
  filters_bound        a filter on an unknown column, or a value outside the allowed set
  grain_matches        the 88.52% error: right metric, wrong grain
  no_fanout            a join that duplicates rows before aggregation
  time_window_bounded  an unbounded or backwards reporting window
  exclusions_applied   a metric whose certified exclusions cannot be applied

Design rules that are not negotiable:

* All 7 gates always run and all 7 always appear in `gate_results`. No short-circuit on
  the first failure -- a user deserves every reason at once.
* `validate` never raises. A hallucinated metric name is a normal, expected input.
* A gate reports True only when it actually verified its property. When the metric
  cannot be resolved, the gates that depend on the metric definition report False with
  a message saying so, rather than passing vacuously. "I did not check" must never be
  recorded as "I checked and it was fine".

Reachability (gates 2, 3 and 5)
-------------------------------
`fact_production_order` carries no `region` column and no `promised_delivery_date`
column -- verified against the built warehouse with `PRAGMA table_info`, 15 columns,
neither present. Both production metrics must still filter on `region` and window on
`promised_delivery_date`, which they reach through the `many_to_one` join their entity
declares to `fact_order_delivery`. So a dimension is legal when it sits on the metric's
entity *or* on an entity that entity declares a join to -- never "must live on this
entity", which would reject every legal production-metric query.

`no_fanout` therefore has to reject one direction and permit the other. It rejects only
a path that traverses a join declared `one_to_many` (`delivery_id` via `raw_deliveries`,
the hop that turns 87.27% into 88.52%). A `many_to_one` hop cannot duplicate rows and
must pass. A gate that blocks every join passes all twelve of the original gate tests
while silently breaking two of the three metrics; that is why both directions are
asserted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from src.semantic.intent import Filter, QueryIntent
from src.semantic.loader import SemanticModel

# Exact gate names. Downstream code and the guide refer to these strings; the order is
# the order they are reported in.
GATE_NAMES: tuple[str, ...] = (
    "metric_approved",
    "dimensions_declared",
    "filters_bound",
    "grain_matches",
    "no_fanout",
    "time_window_bounded",
    "exclusions_applied",
)

# How far reachability searches. The declared graph has 3 entities, so 4 is generous;
# the bound exists only so a cyclic join declaration cannot hang the validator.
_MAX_HOPS = 4

# Operators whose value must be a list, and the required length where fixed.
_LIST_OPERATORS: dict[str, int | None] = {"in": None, "between": 2}


@dataclass(frozen=True)
class GateFailure:
    """One gate's refusal. `message` always names the offending value, not just the gate."""

    gate: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    """The outcome of all 7 gates.

    `ok` is derived rather than stored so it cannot disagree with `gate_results`, and it
    demands that all 7 gates are present -- a truncated run is not a pass.
    """

    gate_results: dict[str, bool] = field(default_factory=dict)
    failures: list[GateFailure] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (
            len(self.gate_results) == len(GATE_NAMES)
            and all(self.gate_results.values())
            and not self.failures
        )


# --------------------------------------------------------------------------------------
# Reachability over the declared join graph
# --------------------------------------------------------------------------------------

Reach = Literal["direct", "joined", "unreachable"]


def _joins(model: SemanticModel, entity_name: str) -> list[dict[str, Any]]:
    """Declared joins leaving `entity_name`. Empty if the entity is not declared."""
    try:
        entity = model.get_entity(entity_name)
    except KeyError:
        return []
    joins = entity.get("joins") or []
    return [j for j in joins if isinstance(j, dict) and j.get("to")]


def _reach(model: SemanticModel, from_entity: str, to_entity: str) -> Reach:
    """One-hop reachability, which is the rule gates 2 and 3 apply.

    "direct" -- the dimension sits on the metric's own entity.
    "joined" -- it sits on an entity the metric's entity declares a join to. This is the
                case that carries `region` and `promised_delivery_date` to the two
                production metrics.
    Cardinality is deliberately not consulted here: whether a legal dimension is *safe*
    to reach is `no_fanout`'s question, and keeping the two separate is what lets a
    fan-out hazard be reported as `no_fanout` rather than as "undeclared".
    """
    if from_entity == to_entity:
        return "direct"
    if any(j["to"] == to_entity for j in _joins(model, from_entity)):
        return "joined"
    return "unreachable"


def _path_hazards(model: SemanticModel, from_entity: str, to_entity: str) -> set[bool]:
    """For every declared join path from `from_entity` to `to_entity`, whether it fans out.

    Returns a set of flags: True for "this path traverses a one_to_many join", False for
    "this path cannot duplicate rows". An empty set means no declared path at all.

    Edges are followed only in the direction they are declared, because `cardinality`
    describes that direction: traversing a `many_to_one` backwards would be a
    `one_to_many`, so treating the graph as undirected would invert the hazard.

    The search is multi-hop on purpose. `first_pass_yield_pct` sits on
    `fact_production_order`, which reaches `raw_deliveries` only as
    fact_production_order --many_to_one--> fact_order_delivery --one_to_many--> raw_deliveries.
    A one-hop check would miss that the fan-out hop is still on the path.
    """
    hazards: set[bool] = set()
    queue: list[tuple[str, bool, frozenset[str]]] = [
        (from_entity, False, frozenset({from_entity}))
    ]
    while queue:
        node, fans_out, seen = queue.pop(0)
        if node == to_entity:
            hazards.add(fans_out)
            continue  # reaching it is what matters; do not tunnel through it
        if len(seen) > _MAX_HOPS:
            continue
        for join in _joins(model, node):
            nxt = join["to"]
            if nxt in seen:
                continue
            queue.append(
                (
                    nxt,
                    fans_out or join.get("cardinality") == "one_to_many",
                    seen | {nxt},
                )
            )
    return hazards


def _dimension(model: SemanticModel, metric_name: str, dim_name: str) -> dict | None:
    """Look up a declared dimension by name, or None."""
    try:
        return model.get_dimension(metric_name, dim_name)
    except Exception:
        return None


# --------------------------------------------------------------------------------------
# Gate 1: metric_approved
# --------------------------------------------------------------------------------------


def gate_metric_approved(qi: QueryIntent, model: SemanticModel) -> GateFailure | None:
    """The metric must exist in the model *and* be approved. Reports which of the two failed.

    Both halves matter and for different reasons: an unknown name is a hallucination,
    while a known-but-draft metric is a governance failure -- a number somebody has not
    signed off on being served as if they had.
    """
    metric = model.get_metric(qi.metric)
    if metric is None:
        known = ", ".join(sorted(model.metric_names())) or "<none>"
        return GateFailure(
            "metric_approved",
            f"Metric {qi.metric!r} is not defined in the semantic model. "
            f"Defined metrics: {known}.",
        )
    state = metric.get("approval_state")
    if state != "approved":
        return GateFailure(
            "metric_approved",
            f"Metric {qi.metric!r} exists but its approval_state is {state!r}, "
            f"not 'approved'; it must not be served.",
        )
    return None


# --------------------------------------------------------------------------------------
# Gate 2: dimensions_declared
# --------------------------------------------------------------------------------------


def gate_dimensions_declared(
    qi: QueryIntent, model: SemanticModel
) -> GateFailure | None:
    """Every requested dimension must be declared and reachable from the metric's entity.

    Reachable means: on that entity, or on an entity it declares a join to. Demanding
    that the dimension live on the metric's own entity would reject `region` for both
    production metrics, whose entity has no region column at all.
    """
    metric = model.get_metric(qi.metric)
    if metric is None:
        return GateFailure(
            "dimensions_declared",
            f"Cannot check dimensions: metric {qi.metric!r} is not in the semantic model, "
            f"so there is no entity to resolve {list(qi.dimensions)!r} against.",
        )
    entity = metric.get("entity")
    problems: list[str] = []
    for dim_name in qi.dimensions:
        dim = _dimension(model, qi.metric, dim_name)
        if dim is None:
            problems.append(f"{dim_name!r} is not a declared dimension")
            continue
        dim_entity = dim.get("entity")
        if _reach(model, entity, dim_entity) == "unreachable":
            problems.append(
                f"{dim_name!r} is declared on entity {dim_entity!r}, which "
                f"{entity!r} declares no join to"
            )
    if problems:
        return GateFailure(
            "dimensions_declared",
            f"Metric {qi.metric!r} (entity {entity!r}) cannot group by: "
            + "; ".join(problems)
            + ".",
        )
    return None


# --------------------------------------------------------------------------------------
# Gate 3: filters_bound
# --------------------------------------------------------------------------------------


def _filter_values(f: Filter) -> list[str]:
    return list(f.value) if isinstance(f.value, list) else [f.value]


def _check_filter(
    model: SemanticModel, qi: QueryIntent, entity: str, f: Filter
) -> list[str]:
    """Problems with one filter. Empty list means bound."""
    problems: list[str] = []
    dim = _dimension(model, qi.metric, f.column)
    if dim is None:
        return [f"{f.column!r} is not a declared dimension"]

    dim_entity = dim.get("entity")
    if _reach(model, entity, dim_entity) == "unreachable":
        problems.append(
            f"{f.column!r} is declared on entity {dim_entity!r}, which "
            f"{entity!r} declares no join to"
        )

    # Operator/value arity. A 'between' carrying a single scalar, or an 'in' carrying a
    # bare string, compiles to something that is not the question that was asked.
    if f.operator in _LIST_OPERATORS:
        required = _LIST_OPERATORS[f.operator]
        if not isinstance(f.value, list):
            problems.append(
                f"operator {f.operator!r} on {f.column!r} needs a list of values, "
                f"got {f.value!r}"
            )
        elif required is not None and len(f.value) != required:
            problems.append(
                f"operator {f.operator!r} on {f.column!r} needs exactly {required} "
                f"values, got {f.value!r}"
            )
    elif isinstance(f.value, list):
        problems.append(
            f"operator {f.operator!r} on {f.column!r} needs a single value, "
            f"got the list {f.value!r}"
        )

    # Allowed values, case-insensitively, for every element of a list value. This is the
    # gate that catches region = 'MARS': a filter that binds to a real column but
    # selects nothing, which would otherwise be reported as a valid answer of 0 rows.
    allowed = dim.get("allowed_values")
    if allowed:
        folded = {str(a).casefold() for a in allowed}
        for value in _filter_values(f):
            if str(value).casefold() not in folded:
                problems.append(
                    f"{f.column!r} = {value!r} is outside its allowed values "
                    f"({', '.join(str(a) for a in allowed)})"
                )
    return problems


def gate_filters_bound(qi: QueryIntent, model: SemanticModel) -> GateFailure | None:
    """Every filter column must resolve to a reachable declared dimension, and every
    value must be inside that dimension's `allowed_values` when it declares any.

    `allowed_values` is read from the artifact, never hard-coded here, so a correction to
    the model reaches this gate on load rather than needing a code change.
    """
    metric = model.get_metric(qi.metric)
    if metric is None:
        columns = [f.column for f in qi.filters]
        return GateFailure(
            "filters_bound",
            f"Cannot bind filters: metric {qi.metric!r} is not in the semantic model, "
            f"so {columns!r} cannot be resolved.",
        )
    entity = metric.get("entity")
    problems: list[str] = []
    for f in qi.filters:
        problems.extend(_check_filter(model, qi, entity, f))
    if problems:
        return GateFailure(
            "filters_bound",
            f"Metric {qi.metric!r} (entity {entity!r}) has unbound filters: "
            + "; ".join(problems)
            + ".",
        )
    return None


# --------------------------------------------------------------------------------------
# Gate 4: grain_matches
# --------------------------------------------------------------------------------------


def gate_grain_matches(qi: QueryIntent, model: SemanticModel) -> GateFailure | None:
    """The intent's grain must be the metric's certified grain.

    This is the gate that prevents the 88.52% answer: on-time delivery is defined per
    order, and evaluating it per delivery leg double-counts the six split shipments into
    a higher, more flattering number that survives review because it looks plausible.
    """
    metric = model.get_metric(qi.metric)
    if metric is None:
        return GateFailure(
            "grain_matches",
            f"Cannot check grain: metric {qi.metric!r} is not in the semantic model, "
            f"so there is no certified grain to compare {qi.grain!r} against.",
        )
    expected = metric.get("grain")
    if qi.grain != expected:
        return GateFailure(
            "grain_matches",
            f"Metric {qi.metric!r} is certified at grain {expected!r}; the intent asks "
            f"for grain {qi.grain!r}. Aggregating at the wrong grain changes the number.",
        )
    return None


# --------------------------------------------------------------------------------------
# Gate 5: no_fanout
# --------------------------------------------------------------------------------------


def gate_no_fanout(qi: QueryIntent, model: SemanticModel) -> GateFailure | None:
    """Reject a column only when reaching it must traverse a `one_to_many` join.

    A `many_to_one` hop cannot duplicate rows and must PASS -- that is precisely how both
    production metrics reach `region` and `promised_delivery_date`, neither of which
    exists on `fact_production_order`. Only the `one_to_many` hop to `raw_deliveries` is
    a hazard, because it multiplies an order into one row per delivery leg before the
    metric aggregates.

    Columns that are not reachable at all are not this gate's business; `dimensions_declared`
    and `filters_bound` report those. Filter columns are checked alongside group-by
    columns because a filter on `delivery_id` would force the same hazardous join.
    """
    metric = model.get_metric(qi.metric)
    if metric is None:
        return GateFailure(
            "no_fanout",
            f"Cannot check join safety: metric {qi.metric!r} is not in the semantic "
            f"model, so no join path can be traced.",
        )
    entity = metric.get("entity")
    requested = [(d, "dimension") for d in qi.dimensions]
    requested += [(f.column, "filter") for f in qi.filters]

    problems: list[str] = []
    for name, kind in requested:
        dim = _dimension(model, qi.metric, name)
        if dim is None:
            continue  # undeclared: reported by gates 2 and 3, not a fan-out question
        dim_entity = dim.get("entity")
        hazards = _path_hazards(model, entity, dim_entity)
        if not hazards:
            continue  # unreachable: also gates 2 and 3
        if False not in hazards:
            problems.append(
                f"{kind} {name!r} lives on {dim_entity!r}, reachable from {entity!r} "
                f"only through a one_to_many join, which duplicates rows before "
                f"aggregation"
            )
    if problems:
        return GateFailure(
            "no_fanout",
            f"Metric {qi.metric!r} at grain {metric.get('grain')!r} would fan out: "
            + "; ".join(problems)
            + ".",
        )
    return None


# --------------------------------------------------------------------------------------
# Gate 6: time_window_bounded
# --------------------------------------------------------------------------------------


def gate_time_window_bounded(
    qi: QueryIntent, model: SemanticModel
) -> GateFailure | None:
    """The reporting window must be present and be a closed, forward range.

    Deliberately *not* checked here: whether the window ends on or before the as-of date.
    A window reaching into the future is a legitimate question -- August 2026 has four
    orders, all still pending -- and the metric's own `not_yet_due` exclusion is what
    keeps them out of the denominator. Rejecting the window instead would refuse a
    question the model can answer correctly.

    The comparison window a diagnostic intent carries is held to the same standard; an
    inverted comparison range would otherwise reach the compiler unchallenged.
    """
    problems: list[str] = []
    if qi.time_window is None:
        problems.append(
            "no time_window: an unbounded window aggregates the whole table, which is "
            "not the question anybody asked"
        )
    for window, what in ((qi.time_window, "time_window"), (qi.comparison, "comparison")):
        if window is None:
            continue
        # Both bounds must be concrete. `date` typing already enforces this on any
        # window built through the schema, but a half-open window assembled another way
        # must be named as such rather than surfacing as a TypeError from the comparison
        # below -- "I could not check" is not "I checked and it was fine".
        missing = [n for n, v in (("start", window.start), ("end", window.end)) if v is None]
        if missing:
            problems.append(
                f"{what} {window.label!r} has no concrete "
                f"{' and no concrete '.join(missing)}, so the window is open-ended"
            )
        elif window.start > window.end:
            problems.append(
                f"{what} {window.label!r} runs backwards: start "
                f"{window.start.isoformat()} is after end {window.end.isoformat()}"
            )
    if problems:
        return GateFailure(
            "time_window_bounded",
            f"Metric {qi.metric!r} has an unusable reporting window: "
            + "; ".join(problems)
            + ".",
        )
    return None


# --------------------------------------------------------------------------------------
# Gate 7: exclusions_applied
# --------------------------------------------------------------------------------------


def gate_exclusions_applied(
    qi: QueryIntent, model: SemanticModel
) -> GateFailure | None:
    """The metric's exclusions must exist and be applicable.

    The compiler applies exclusions unconditionally; this gate guarantees there is
    something to apply. Each exclusion needs a non-empty `predicate` (the compiler emits
    it) and a non-empty `key` (provenance reports which exclusions were applied by
    name). A metric whose exclusions silently vanished would still return a number --
    the wrong one, with cancelled and not-yet-due orders back in the denominator.
    """
    metric = model.get_metric(qi.metric)
    if metric is None:
        return GateFailure(
            "exclusions_applied",
            f"Cannot check exclusions: metric {qi.metric!r} is not in the semantic model.",
        )
    exclusions = metric.get("exclusions")
    if not exclusions:
        return GateFailure(
            "exclusions_applied",
            f"Metric {qi.metric!r} declares no exclusions, so the compiler has nothing "
            f"to apply and cancelled or not-yet-due rows would enter the denominator.",
        )
    problems: list[str] = []
    for i, exclusion in enumerate(exclusions):
        if not isinstance(exclusion, dict):
            problems.append(f"exclusion #{i} is {exclusion!r}, not a mapping")
            continue
        key = exclusion.get("key")
        if not key:
            problems.append(f"exclusion #{i} has no 'key' to report it by")
        if not exclusion.get("predicate"):
            problems.append(
                f"exclusion {key or f'#{i}'!r} has no 'predicate', so it cannot be applied"
            )
    if problems:
        return GateFailure(
            "exclusions_applied",
            f"Metric {qi.metric!r} has unusable exclusions: " + "; ".join(problems) + ".",
        )
    return None


# --------------------------------------------------------------------------------------
# The runner
# --------------------------------------------------------------------------------------

_GATES = {
    "metric_approved": gate_metric_approved,
    "dimensions_declared": gate_dimensions_declared,
    "filters_bound": gate_filters_bound,
    "grain_matches": gate_grain_matches,
    "no_fanout": gate_no_fanout,
    "time_window_bounded": gate_time_window_bounded,
    "exclusions_applied": gate_exclusions_applied,
}
assert tuple(_GATES) == GATE_NAMES, "gate registry must match the declared gate names"


def validate(qi: QueryIntent, model: SemanticModel) -> ValidationResult:
    """Run all 7 gates and return every reason the intent was refused.

    Never raises. An invented metric name is a normal input to this function -- refusing
    it is the whole job -- and so is a semantic model that turns out to be malformed: an
    unexpected exception inside a gate is recorded as that gate failing, never as it
    passing, so a bug can never be mistaken for approval.
    """
    gate_results: dict[str, bool] = {}
    failures: list[GateFailure] = []
    for name in GATE_NAMES:
        try:
            failure = _GATES[name](qi, model)
        except Exception as exc:  # a gate must fail closed, never crash the caller
            failure = GateFailure(
                name, f"Gate {name!r} could not be evaluated: {exc!r}. Failing closed."
            )
        gate_results[name] = failure is None
        if failure is not None:
            failures.append(failure)
    return ValidationResult(gate_results=gate_results, failures=failures)
