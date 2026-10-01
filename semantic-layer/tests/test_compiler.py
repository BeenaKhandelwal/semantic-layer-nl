from datetime import date
import pytest
from src.semantic.intent import QueryIntent, Filter, TimeWindow
from src.semantic.loader import load_semantic_model
from src.semantic.compiler import compile_sql
from src.semantic.executor import run
from src import build_warehouse

@pytest.fixture(scope="module")
def model():
    build_warehouse.build()
    return load_semantic_model()

JULY = TimeWindow(start=date(2026, 7, 1), end=date(2026, 7, 31), label="July 2026")
JUNE = TimeWindow(start=date(2026, 6, 1), end=date(2026, 6, 30), label="June 2026")

def _otd(window=JULY, dims=None, region="IN", **over):
    kw = dict(
        metric="on_time_delivery_pct", dimensions=dims or [],
        filters=[Filter(column="region", operator="=", value=region)],
        grain="order", time_window=window, intent_type="descriptive",
    )
    kw.update(over)
    return QueryIntent(**kw)

# ---------- the canonical answers ----------

def test_q1_otd_india_july_is_87_27_percent(model):
    rows = run(compile_sql(_otd(), model))
    assert len(rows) == 1
    r = rows[0]
    assert r["numerator"] == 48
    assert r["denominator"] == 55
    assert r["value"] == pytest.approx(87.2727, abs=0.0001)

def test_otd_india_june_is_96_15_percent(model):
    r = run(compile_sql(_otd(window=JUNE), model))[0]
    assert (r["numerator"], r["denominator"]) == (25, 26)
    assert r["value"] == pytest.approx(96.1538, abs=0.0001)

def test_the_drop_is_8_88_pp(model):
    jul = run(compile_sql(_otd(), model))[0]["value"]
    jun = run(compile_sql(_otd(window=JUNE), model))[0]["value"]
    assert jun - jul == pytest.approx(8.8811, abs=0.001)

def test_q2_attribution_breakdown(model):
    rows = run(compile_sql(
        _otd(dims=["delay_attribution_phase"], intent_type="diagnostic"), model))
    attributed = {r["delay_attribution_phase"]: r["late_count"]
                  for r in rows if r["delay_attribution_phase"]}
    assert attributed == {
        "quality_inspection": 4, "transportation": 2, "production_execution": 1
    }

# ---------- the wrong answers, proven wrong (spec 5.4) ----------

def test_naive_delivery_grain_overstates_to_88_52(model):
    """The whole point: the wrong number is close AND flattering."""
    import duckdb
    from src.semantic.constants import DB_PATH
    con = duckdb.connect(str(DB_PATH), read_only=True)
    num, den = con.execute("""
        SELECT sum(CASE WHEN d.delivery_date <> ''
                         AND CAST(d.delivery_date AS DATE) <= o.promised_delivery_date
                        THEN 1 ELSE 0 END),
               count(*)
        FROM fact_order_delivery o
        JOIN read_csv_auto('data/deliveries_raw.csv', header=true, all_varchar=true) d
          ON d.order_id = o.order_id
        WHERE o.region='IN' AND o.is_eligible
          AND o.promised_delivery_date BETWEEN DATE '2026-07-01' AND DATE '2026-07-31'
    """).fetchone()
    con.close()
    assert (num, den) == (54, 61)
    naive = 100.0 * num / den
    assert naive == pytest.approx(88.5246, abs=0.0001)
    assert naive > 87.2727, "the grain error must OVERSTATE -- that is why it survives review"
    assert abs(naive - 87.2727) < 2.0, "and it must be close enough to look plausible"

def test_fpy_correct_and_naive(model):
    """94.44% correct vs 94.55% counting rework re-inspections."""
    rows = run(compile_sql(QueryIntent(
        metric="first_pass_yield_pct",
        filters=[Filter(column="region", operator="=", value="IN")],
        grain="production_order", time_window=JULY, intent_type="descriptive",
    ), model))
    r = rows[0]
    assert (r["numerator"], r["denominator"]) == (51, 54)
    assert r["value"] == pytest.approx(94.4444, abs=0.0001)
    naive = 100.0 * 52 / 55
    assert naive == pytest.approx(94.5455, abs=0.0001)
    assert naive > r["value"], "counting rework also overstates"

def test_schedule_adherence(model):
    r = run(compile_sql(QueryIntent(
        metric="mfg_schedule_adherence_pct",
        filters=[Filter(column="region", operator="=", value="IN")],
        grain="production_order", time_window=JULY, intent_type="descriptive",
    ), model))[0]
    assert (r["numerator"], r["denominator"]) == (50, 54)
    assert r["value"] == pytest.approx(92.5926, abs=0.0001)

# ---------- the production metrics window on the PROMISED date, via the join ----
# fact_production_order has no region and no promised_delivery_date column. The
# intuitive scheduled_finish_date gives 42/45 for both metrics -- a plausible wrong
# cohort. These pin the denominator so that substitution cannot pass.

@pytest.mark.parametrize("metric,expected", [
    ("first_pass_yield_pct", (51, 54)),
    ("mfg_schedule_adherence_pct", (50, 54)),
])
def test_production_metrics_window_on_the_promised_date(model, metric, expected):
    cq = compile_sql(QueryIntent(
        metric=metric, filters=[Filter(column="region", operator="=", value="IN")],
        grain="production_order", time_window=JULY, intent_type="descriptive",
    ), model)
    assert "scheduled_finish_date" not in cq.sql, (
        "windowing on scheduled_finish_date asks 'scheduled to finish in July', "
        "a different cohort: it returns 42/45, not the certified denominator"
    )
    assert "promised_delivery_date" in cq.sql
    assert "join" in cq.sql.lower(), "region/promised date require the declared join"
    r = run(cq)[0]
    assert (r["numerator"], r["denominator"]) == expected
    assert r["denominator"] != 45, "45 is the scheduled_finish_date cohort"

def test_cancelled_production_orders_are_excluded(model):
    """Without this exclusion the cohort is 55, not 54 -- verified in the warehouse."""
    cq = compile_sql(QueryIntent(
        metric="first_pass_yield_pct",
        filters=[Filter(column="region", operator="=", value="IN")],
        grain="production_order", time_window=JULY, intent_type="descriptive",
    ), model)
    assert "cancelled_production_orders" in cq.applied_exclusions
    assert run(cq)[0]["denominator"] == 54

def test_fpy_reads_the_first_decision_not_the_final(model):
    """The rework collapse is materialized as first_usage_decision.

    Resolving it to qm_final_decision_date would count SO-1004's eventually-accepted
    rework as a first-pass success -- the 94.55% error, in the flattering direction.
    """
    cq = compile_sql(QueryIntent(
        metric="first_pass_yield_pct",
        filters=[Filter(column="region", operator="=", value="IN")],
        grain="production_order", time_window=JULY, intent_type="descriptive",
    ), model)
    assert "first_usage_decision" in cq.sql
    assert "qm_final_decision_date" not in cq.sql

def test_order_grain_metric_emits_no_join(model):
    """Only pay for the join when the intent actually needs it."""
    assert "join" not in compile_sql(_otd(), model).sql.lower()

# ---------- compiler contract ----------

def test_exclusions_always_applied(model):
    cq = compile_sql(_otd(), model)
    assert set(cq.applied_exclusions) >= {"cancelled_orders", "not_yet_due"}
    assert "CANC" in cq.sql

def test_not_yet_due_returns_no_eligible_orders_not_zero(model):
    """August window: 4 orders, all pending. Must not divide by zero."""
    aug = TimeWindow(start=date(2026, 8, 1), end=date(2026, 8, 31), label="August 2026")
    r = run(compile_sql(_otd(window=aug), model))[0]
    assert r["denominator"] == 0
    assert r["value"] is None

def test_compiler_is_parameterized_not_interpolated(model):
    cq = compile_sql(_otd(region="IN"), model)
    assert "'IN'" not in cq.sql
    assert "?" in cq.sql
    assert "IN" in [str(p) for p in cq.params]

def test_compiler_rejects_unapproved_metric_defensively(model):
    from src.semantic.compiler import CompilerError
    with pytest.raises(CompilerError):
        compile_sql(_otd(metric="does_not_exist"), model)

def test_compiler_does_not_import_anthropic():
    import src.semantic.compiler as c, inspect
    assert "anthropic" not in inspect.getsource(c)

def test_compiler_output_is_stable(model):
    a = compile_sql(_otd(), model).sql
    b = compile_sql(_otd(), model).sql
    assert a == b


# --- Added beyond the plan --------------------------------------------------
# The plan's 21 tests never exercise the unmaterialized entity or the one_to_many
# refusal, because the validator rejects those intents first. Defence in depth that
# is never tested is defence nobody has checked.

def test_compiler_refuses_a_delivery_grain_dimension_naming_the_cardinality(model):
    """`raw_deliveries` is declared so the fan-out hazard is reviewable; it is not a table.

    Two guards can stop this intent -- the join cardinality and the entity not being
    materialized -- and the cardinality check fires first. That ordering is deliberate:
    "this join duplicates rows" is the reason a reviewer needs, while "no such table" is
    an implementation detail of how the model chose to declare the hazard.
    """
    from src.semantic.compiler import CompilerError
    with pytest.raises(CompilerError, match="one_to_many"):
        compile_sql(_otd(dims=["delivery_id"]), model)


def test_unmaterialized_entities_never_reach_a_from_clause(model):
    """The second guard, reached directly since the cardinality check shadows it.

    A logical entity with no table must fail by name. Without this check the compiler
    emits `FROM raw_deliveries` and DuckDB reports "table does not exist" -- which reads
    like a broken warehouse rather than a query that was never legal to ask. If the model
    ever declared an unmaterialized entity behind a many_to_one edge, this is the only
    thing standing between it and an unresolvable table name.
    """
    from src.semantic.compiler import CompilerError, _require_table
    with pytest.raises(CompilerError, match="not materialized"):
        _require_table(model, "raw_deliveries")
    # And the materialized ones resolve, so the guard is not simply rejecting everything.
    assert _require_table(model, "fact_order_delivery") == "fact_order_delivery"
    assert _require_table(model, "fact_production_order") == "fact_production_order"


def test_compiler_refuses_to_traverse_a_one_to_many_join(model):
    """The gate that stops 88.52% from being computable at all.

    `_find_join` is reached only for a column on another entity; asserting the refusal
    names the cardinality proves the compiler is reading the declared edge rather than
    failing for some incidental reason.
    """
    from src.semantic.compiler import CompilerError, _find_join
    with pytest.raises(CompilerError, match="one_to_many"):
        _find_join(model, "fact_order_delivery", "raw_deliveries")


def test_every_column_in_a_joined_query_is_alias_qualified(model):
    """The two fact tables share 10 column names, `plant` and `order_id` among them.

    An unqualified reference is either an ambiguity error or silently the wrong table's
    column -- and the silent case is the dangerous one, since `p.plant` and `o.plant`
    agree in this dataset and would diverge the moment a plant were corrected on one side.
    """
    import re
    cq = compile_sql(QueryIntent(
        metric="first_pass_yield_pct", dimensions=["plant"],
        filters=[Filter(column="region", operator="=", value="IN")],
        grain="production_order", time_window=JULY, intent_type="descriptive",
    ), model)
    shared = {"plant", "order_id", "release_date", "gr_date", "scheduled_finish_date",
              "material_issue_date", "mrp_date", "production_order_id",
              "qm_first_decision_date", "qm_final_decision_date"}
    # Strip the trailing `AS <alias>` labels, which are intentionally bare.
    body = re.sub(r"\bAS\s+\w+", " ", cq.sql)
    unqualified = sorted(
        c for c in shared
        if re.search(rf"(?<![\w.]){c}(?![\w])", body)
    )
    assert unqualified == [], (
        f"shared columns appear unqualified in a joined query: {unqualified}\n{cq.sql}"
    )


def test_the_join_is_a_left_join_so_make_to_stock_orders_survive(model):
    """SO-1015 is make-to-stock: no production order at all.

    An INNER JOIN drops it from the denominator, which *raises* OTD -- the same
    flattering direction as every other defect in this dataset.
    """
    cq = compile_sql(QueryIntent(
        metric="first_pass_yield_pct",
        filters=[Filter(column="region", operator="=", value="IN")],
        grain="production_order", time_window=JULY, intent_type="descriptive",
    ), model)
    assert "LEFT JOIN" in cq.sql
    assert "INNER JOIN" not in cq.sql
