import pytest
from src import build_warehouse
from src.semantic.dq import load_rules, run_rules

@pytest.fixture(scope="module", autouse=True)
def warehouse():
    build_warehouse.build()

def test_all_six_dq_dimensions_covered():
    dims = {r["dimension"] for r in load_rules()}
    assert dims == {"completeness", "validity", "uniqueness",
                    "timeliness", "consistency", "accuracy"}

def test_every_rule_is_bound_to_a_metric():
    """An unbound rule can only produce a dashboard-wide red light."""
    for r in load_rules():
        assert r["bound_to"], f"{r['rule_id']} is not bound to any metric"

def test_uniqueness_rule_guarantees_order_grain():
    """Defect 4: this is the rule that would catch a fan-out regression."""
    report = run_rules()
    uniq = next(r for r in report.results if r.dimension == "uniqueness")
    assert uniq.passed, "fact_order_delivery is not one row per order"

def test_completeness_rule_is_scoped_not_blanket():
    """Defect 2: SO-1013 is legitimately null (in transit, not yet due).
    A blanket NOT NULL check would wrongly fail."""
    report = run_rules()
    comp = next(r for r in report.results if r.dimension == "completeness")
    assert comp.passed
    rule = next(r for r in load_rules() if r["dimension"] == "completeness")
    sql = rule["sql"].lower()
    assert "promised_delivery_date" in sql and (
        "canc" in sql or "is_eligible" in sql
    ), "completeness rule must be scoped to eligible, due orders"

def test_consistency_rule_checks_phase_ordering():
    report = run_rules()
    cons = next(r for r in report.results if r.dimension == "consistency")
    assert cons.passed

def test_clean_warehouse_is_trusted():
    assert run_rules().badge == "TRUSTED"

def test_rules_can_be_filtered_by_metric():
    report = run_rules(metric_name="on_time_delivery_pct")
    assert report.results
    for r in report.results:
        assert "on_time_delivery_pct" in r.bound_to

def test_blocking_failure_yields_blocked_badge(tmp_path):
    """A blocking rule must produce BLOCKED, which suppresses the answer."""
    import yaml
    from src.semantic.constants import METADATA_DIR
    rules = yaml.safe_load((METADATA_DIR / "06_dq_rules.yml").read_text(encoding="utf-8"))
    rules["rules"] = [{
        "rule_id": "forced_fail", "dimension": "completeness",
        "description": "forced failure for testing",
        "sql": "SELECT 100.0 AS observed",
        "threshold": 0.0, "comparison": "lte", "severity": "blocking",
        "bound_to": ["on_time_delivery_pct"], "defect_demonstrated": "none",
    }]
    p = tmp_path / "forced.yml"
    p.write_text(yaml.safe_dump(rules), encoding="utf-8")
    report = run_rules(rules_path=p)
    assert report.badge == "BLOCKED"
    assert "forced_fail" in report.failing_rules

@pytest.mark.parametrize("defect", [
    "cancelled_order", "in_transit_null", "rework_loop", "split_delivery",
    "repromised_date", "make_to_stock_no_prod_order", "qm_dominated_delay",
    "non_qm_delay",
])
def test_all_eight_defects_are_documented_in_rules(defect):
    """Every seeded defect must be named by at least one rule."""
    blob = " ".join(r["defect_demonstrated"] for r in load_rules())
    assert defect in blob, f"no rule documents defect {defect}"


# --- Added during review: acceptance criterion 6 -----------------------------

# Each mutation is the plausible corruption its rule claims to detect. Applied to a
# scratch COPY of the warehouse inside a transaction that is always rolled back --
# never the shared warehouse, and never the committed CSVs.
_MUTATIONS = {
    "completeness": "UPDATE fact_order_delivery SET final_delivery_date = NULL "
                    "WHERE is_eligible AND promised_delivery_date <= DATE '__AS_OF_DATE__'",
    "validity": "UPDATE fact_order_delivery SET order_status = 'SHIPPED' "
                "WHERE order_id = (SELECT min(order_id) FROM fact_order_delivery)",
    "uniqueness": "INSERT INTO fact_order_delivery "
                  "SELECT * FROM fact_order_delivery LIMIT 1",
    "timeliness": "UPDATE fact_order_delivery SET invoice_date = DATE '2026-01-01' "
                  "WHERE invoice_date IS NOT NULL",
    "consistency": "UPDATE fact_order_delivery SET gr_date = release_date - INTERVAL 5 DAY "
                   "WHERE release_date IS NOT NULL AND gr_date IS NOT NULL",
    "accuracy": "UPDATE fact_order_delivery SET is_on_time = FALSE WHERE region = 'IN' "
                "AND promised_delivery_date BETWEEN DATE '2026-07-01' AND DATE '2026-07-31'",
}

# Which rules a mutation is EXPECTED to fail. Mostly itself -- but a duplicated order
# row genuinely changes the OTD number, so the accuracy certification failing too is
# correct, not leakage. That is the rule acting as a backstop, which is the point of
# certifying the published figure.
_EXPECTED_FAILURES = {dim: {dim} for dim in _MUTATIONS}
_EXPECTED_FAILURES["uniqueness"] = {"uniqueness", "accuracy"}


@pytest.fixture(scope="module")
def scratch_db(tmp_path_factory):
    """A throwaway copy, so a mutation can never reach the shared warehouse."""
    import shutil
    from src.semantic.constants import DB_PATH
    dest = tmp_path_factory.mktemp("dq") / "scratch.duckdb"
    shutil.copy(DB_PATH, dest)
    return dest


def _verdicts(db_path, mutation_sql=None):
    """Evaluate every rule, optionally under a rolled-back mutation."""
    import duckdb
    from src.semantic.constants import AS_OF_DATE
    con = duckdb.connect(str(db_path))
    try:
        if mutation_sql:
            con.execute("BEGIN")
            con.execute(mutation_sql.replace("__AS_OF_DATE__", AS_OF_DATE.isoformat()))
        out = {}
        for r in load_rules():
            sql = r["sql"].replace("__AS_OF_DATE__", AS_OF_DATE.isoformat())
            row = con.execute(sql).fetchone()
            observed = float(row[0]) if row and row[0] is not None else 0.0
            threshold = float(r["threshold"])
            out[r["dimension"]] = (observed <= threshold if r["comparison"] == "lte"
                                   else observed >= threshold)
        if mutation_sql:
            con.execute("ROLLBACK")
        return out
    finally:
        con.close()


def test_every_rule_passes_on_the_clean_warehouse(scratch_db):
    failing = [d for d, ok in _verdicts(scratch_db).items() if not ok]
    assert failing == [], f"rules failing on clean data: {failing}"


@pytest.mark.parametrize("dimension", sorted(_MUTATIONS))
def test_each_rule_fails_on_its_own_corruption_and_stays_quiet_otherwise(
        dimension, scratch_db):
    """Acceptance criterion 6, mechanically.

    A rule that cannot fail is decoration; a rule that fails on everything is a
    dashboard-wide red light, which is the failure mode `bound_to` exists to prevent.
    Both halves have to hold, so assert the whole verdict set rather than just the
    one rule -- otherwise a rule that fires on every mutation still passes.
    """
    verdicts = _verdicts(scratch_db, _MUTATIONS[dimension])
    actually_failed = {d for d, ok in verdicts.items() if not ok}
    assert actually_failed == _EXPECTED_FAILURES[dimension], (
        f"{dimension} mutation failed {sorted(actually_failed)}, "
        f"expected {sorted(_EXPECTED_FAILURES[dimension])}")
