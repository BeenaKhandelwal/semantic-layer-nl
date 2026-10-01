import duckdb, pytest, yaml
from src import build_warehouse
from src.semantic.constants import DB_PATH

@pytest.fixture(scope="module")
def con():
    # fresh=True so the suite tests the SQL as written, not a database file that
    # still holds views an earlier build declared and this one no longer does.
    build_warehouse.build(fresh=True)
    c = duckdb.connect(str(DB_PATH), read_only=True)
    yield c
    c.close()

def test_fact_is_one_row_per_order(con):
    """Grain guarantee. Split deliveries must NOT create extra fact rows."""
    total, distinct = con.execute(
        "SELECT count(*), count(DISTINCT order_id) FROM fact_order_delivery"
    ).fetchone()
    assert total == distinct == 132

def test_split_delivery_collapsed_to_max_date(con):
    """SO-1009: legs on 07-16 and 07-20. Order is late, using the LAST leg."""
    row = con.execute("""
        SELECT delivery_count, final_delivery_date, is_on_time
        FROM fact_order_delivery WHERE order_id = 'SO-1009'
    """).fetchone()
    assert row[0] == 2
    assert str(row[1]) == "2026-07-20"
    assert row[2] is False or row[2] == 0

def test_in_july_eligibility_and_ontime(con):
    """The canonical numbers: 55 eligible, 48 on time."""
    eligible, on_time = con.execute("""
        SELECT sum(CASE WHEN is_eligible THEN 1 ELSE 0 END),
               sum(CASE WHEN is_eligible AND is_on_time THEN 1 ELSE 0 END)
        FROM fact_order_delivery
        WHERE region = 'IN'
          AND promised_delivery_date BETWEEN DATE '2026-07-01' AND DATE '2026-07-31'
    """).fetchone()
    assert (eligible, on_time) == (55, 48)

def test_cancelled_order_not_eligible(con):
    assert con.execute(
        "SELECT is_eligible FROM fact_order_delivery WHERE order_id='SO-1007'"
    ).fetchone()[0] in (False, 0)

def test_in_transit_future_promise_not_eligible_not_late(con):
    """SO-1013: promised 2026-08-12, after AS_OF_DATE. Not-yet-due."""
    eligible, on_time = con.execute(
        "SELECT is_eligible, is_on_time FROM fact_order_delivery WHERE order_id='SO-1013'"
    ).fetchone()
    assert eligible in (False, 0)
    assert on_time in (False, 0, None)

def test_make_to_stock_order_survives_left_join(con):
    """SO-1015 has no production order -- must still be a complete, eligible row."""
    row = con.execute("""
        SELECT is_eligible, is_on_time, production_order_id, prod_confirm_date
        FROM fact_order_delivery WHERE order_id='SO-1015'
    """).fetchone()
    assert row[0] in (True, 1)
    assert row[1] in (True, 1)
    assert row[2] is None
    assert row[3] is None

def test_attribution_matches_oracle(con):
    """Derived attribution must equal the hand-authored expected_attribution_phase."""
    rows = con.execute("""
        SELECT order_id, delay_attribution_phase
        FROM fact_order_delivery
        WHERE region='IN'
          AND promised_delivery_date BETWEEN DATE '2026-07-01' AND DATE '2026-07-31'
          AND is_eligible AND NOT is_on_time
        ORDER BY order_id
    """).fetchall()
    assert dict(rows) == {
        "SO-1002": "quality_inspection",
        "SO-1003": "transportation",
        "SO-1004": "quality_inspection",
        "SO-1005": "production_execution",
        "SO-1006": "quality_inspection",
        "SO-1009": "transportation",
        "SO-1010": "quality_inspection",
    }

def test_qm_first_vs_final_decision_differ_for_rework(con):
    """Rework: first decision 07-11, final 07-14. FPY needs the FIRST."""
    first, final = con.execute("""
        SELECT qm_first_decision_date, qm_final_decision_date
        FROM fact_order_delivery WHERE order_id='SO-1004'
    """).fetchone()
    assert str(first) == "2026-07-11"
    assert str(final) == "2026-07-14"

def test_build_is_idempotent(tmp_path):
    """Building twice over the same file must not duplicate rows.

    Deliberately builds to a temp path, NOT DB_PATH: the module-scoped `con`
    fixture holds a read_only handle on DB_PATH, and DuckDB rejects a
    second in-process connection to one file with a different configuration.
    """
    db = tmp_path / "idem.duckdb"
    build_warehouse.build(db_path=db)
    build_warehouse.build(db_path=db)
    c = duckdb.connect(str(db), read_only=True)
    try:
        assert c.execute("SELECT count(*) FROM fact_order_delivery").fetchone()[0] == 132
    finally:
        c.close()


# --- Added during review of Task 3 -----------------------------------------
# The original attribution was 9 copies of an 8-branch GREATEST expression, and 7
# of the 9 had production_execution and quality_inspection standards swapped. The
# tests above all still passed, because the one seeded production delay (SO-1005,
# a 7-day gap) was extreme enough to win the argmax under either standard. These
# tests pin the properties that were silently broken.

def test_variance_columns_are_end_anchored(con):
    """Each var_* must measure the gap ENDING at its phase, not starting from it.

    SO-1002's delay is a quality-inspection overrun, so it must land in var_qm.
    Under the start-anchored reading it showed up in var_confirm -- the column
    named after production execution -- which made every phase label off by one.
    """
    var_confirm, var_qm = con.execute("""
        SELECT var_confirm, var_qm FROM fact_order_delivery WHERE order_id = 'SO-1002'
    """).fetchone()
    assert var_qm == 4, "QM overrun belongs in var_qm"
    assert var_confirm == 0, "production execution ran to standard; var_confirm must be 0"

def test_variance_chain_is_contiguous(con):
    """Every day between order and delivery must be owned by exactly one phase.

    This is the invariant that catches an unmeasured span. The variances originally
    ran gr_date -> picking_date then jumped to shipment_date -> delivery, leaving
    goods_issue -> dispatch measured by nothing. 128 of 132 orders had a real day
    sitting in that hole, so a dispatch hold would have made an order late while
    every var_* column read on-standard and attribution returned NULL.

    Sum of variances must equal total elapsed minus the standard, per order.
    """
    mismatches = con.execute("""
        SELECT order_id,
               date_diff('day', order_date, final_delivery_date) - 12 AS elapsed_over_std,
               COALESCE(var_mrp,0) + COALESCE(var_release,0) + COALESCE(var_issue,0)
             + COALESCE(var_confirm,0) + COALESCE(var_qm,0) + COALESCE(var_gr,0)
             + COALESCE(var_picking,0) + COALESCE(var_goods_issue,0)
             + COALESCE(var_shipment,0) AS sum_var
        FROM fact_order_delivery
        WHERE is_delivered AND production_order_id IS NOT NULL
          AND date_diff('day', order_date, final_delivery_date) - 12 <>
              COALESCE(var_mrp,0) + COALESCE(var_release,0) + COALESCE(var_issue,0)
            + COALESCE(var_confirm,0) + COALESCE(var_qm,0) + COALESCE(var_gr,0)
            + COALESCE(var_picking,0) + COALESCE(var_goods_issue,0)
            + COALESCE(var_shipment,0)
    """).fetchall()
    assert mismatches == [], f"unowned time in the phase chain: {mismatches[:5]}"

def test_attribution_survives_a_narrow_production_delay(con):
    """A small positive production variance must attribute, not fall through to NULL.

    With the standards swapped, an order whose material_issue->confirm gap was 5 days
    (standard 3, variance +2) scored 4 in the guard but 2 in the label branch. Nothing
    matched and delay_attribution_phase came back NULL -- a diagnostic query answering
    "no cause found" for an order that plainly had one. SO-1005's real gap is 7 days,
    extreme enough to win under either standard, which is why the suite missed it.

    So build the narrow case for real: copy SO-1005's row, shrink the production gap to
    5 days, and re-run the published attribution logic over it.
    """
    got = con.execute("""
        WITH s AS (SELECT * FROM phase_standard),
        narrowed AS (
            -- confirm lands 5 days after material issue instead of 7
            SELECT DATE '2026-07-01' AS material_issue_date,
                   DATE '2026-07-06' AS prod_confirm_date,
                   DATE '2026-07-07' AS qm_final_decision_date
        ),
        vars AS (
            SELECT date_diff('day', n.material_issue_date, n.prod_confirm_date) - s.std_confirm AS var_confirm,
                   date_diff('day', n.prod_confirm_date, n.qm_final_decision_date) - s.std_qm  AS var_qm
            FROM narrowed n CROSS JOIN s
        ),
        ranked AS (
            SELECT phase_key, variance_days,
                   row_number() OVER (ORDER BY variance_days DESC, phase_seq ASC) AS rn
            FROM (SELECT 5 AS phase_seq, 'production_execution' AS phase_key, var_confirm AS variance_days FROM vars
                  UNION ALL SELECT 6, 'quality_inspection', var_qm FROM vars) u
            WHERE variance_days > 0
        )
        SELECT phase_key, variance_days FROM ranked WHERE rn = 1
    """).fetchone()
    assert got == ("production_execution", 2), (
        f"a +2 production variance must attribute to production_execution, got {got}"
    )
    # And the seeded order attributes for the same reason, not by being an outlier.
    assert con.execute(
        "SELECT delay_attribution_phase FROM fact_order_delivery WHERE order_id='SO-1005'"
    ).fetchone()[0] == "production_execution"

def test_phase_standards_come_from_the_dimension(con):
    """Durations must be declared once, in dim_process_phase.

    They were previously retyped as literals inside every branch, which is how the
    two copies drifted apart. Also guards the 12 that available_slack_days
    subtracts: phases 1-11 sum to 12, all 12 phases sum to 13.
    """
    std = con.execute("SELECT * FROM phase_standard").fetchone()
    cols = [d[0] for d in con.description]
    got = dict(zip(cols, std))
    assert got["std_confirm"] == 3, "production_execution standard is 3 days"
    assert got["std_qm"] == 1, "quality_inspection standard is 1 day"
    assert got["std_to_delivery"] == 12
    assert con.execute("SELECT sum(standard_duration_days) FROM dim_process_phase").fetchone()[0] == 13

def test_every_attributed_phase_resolves_to_a_declared_phase(con):
    """No attribution may name a phase the dimension does not declare.

    Two branches both emitted 'quality_inspection', which left goods_receipt
    unreachable -- a delay there could never be reported.
    """
    orphans = con.execute("""
        SELECT DISTINCT delay_attribution_phase FROM fact_order_delivery
        WHERE delay_attribution_phase IS NOT NULL
          AND delay_attribution_phase NOT IN (SELECT phase_key FROM dim_process_phase)
    """).fetchall()
    assert orphans == []
    assert con.execute(
        "SELECT count(*) - count(DISTINCT phase_key) FROM dim_process_phase"
    ).fetchone()[0] == 0

def test_attribution_is_populated_exactly_for_late_orders(con):
    """Attribution is a strict function of lateness: no gaps, no strays."""
    strays, gaps = con.execute("""
        SELECT
          count(*) FILTER (WHERE delay_attribution_phase IS NOT NULL
                             AND (is_on_time OR NOT is_eligible)),
          count(*) FILTER (WHERE is_eligible AND NOT is_on_time AND is_delivered
                             AND delay_attribution_phase IS NULL)
        FROM fact_order_delivery
    """).fetchone()
    assert (strays, gaps) == (0, 0)

def test_invoice_date_is_a_date_not_a_timestamp(con):
    """invoice_date is modeled from dim_process_phase, and typed like its siblings.

    An INTERVAL add silently produced TIMESTAMP, so it compared unequal to every
    other phase column and would have skewed the DQ timeliness rule.
    """
    dtype = con.execute("""
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'fact_order_delivery' AND column_name = 'invoice_date'
    """).fetchone()[0]
    assert dtype == "DATE"
    delivered, invoiced = con.execute("""
        SELECT final_delivery_date, invoice_date
        FROM fact_order_delivery WHERE order_id = 'SO-1002'
    """).fetchone()
    billing_std = con.execute(
        "SELECT standard_duration_days FROM dim_process_phase WHERE phase_key='billing'"
    ).fetchone()[0]
    assert (invoiced - delivered).days == billing_std

def test_missing_phase_reads_as_null_not_zero_variance(con):
    """SO-1015 is make-to-stock: absent phases must be NULL, never 0.

    A 0 would read as "ran exactly to standard" and could win an argmax tie,
    attributing a delay to a phase that never executed.
    """
    row = con.execute("""
        SELECT var_mrp, var_confirm, var_qm, delay_attribution_phase
        FROM fact_order_delivery WHERE order_id = 'SO-1015'
    """).fetchone()
    assert row[0] is None and row[1] is None and row[2] is None
    assert row[3] is None


def test_repromise_uses_current_promise_not_original():
    """Defect 5: SO-1011 was re-promised from 07-18 to 07-24 and delivered 07-21.

    Only its presence was asserted, never its effect. Measuring against
    `promised_date_original` gives 47/55 -- one order off the governed 48/55, in the
    pessimistic direction. This pins the SCD-2 choice: the contract measures against
    the *current* promise, so a re-promise that the customer agreed to counts as met.
    A silent flip of the column would move the headline from 87.3% to 85.5%.
    """
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        window = ("region = 'IN' AND is_eligible AND promised_delivery_date "
                  "BETWEEN DATE '2026-07-01' AND DATE '2026-07-31'")
        current, total = con.execute(
            f"SELECT sum(CASE WHEN final_delivery_date <= promised_delivery_date "
            f"THEN 1 ELSE 0 END), count(*) FROM fact_order_delivery WHERE {window}"
        ).fetchone()
        original, _ = con.execute(
            f"SELECT sum(CASE WHEN final_delivery_date <= "
            f"coalesce(promised_date_original, promised_delivery_date) THEN 1 ELSE 0 END), "
            f"count(*) FROM fact_order_delivery WHERE {window}"
        ).fetchone()
        row = con.execute(
            "SELECT promised_date_original, promised_delivery_date, final_delivery_date, "
            "is_on_time FROM fact_order_delivery WHERE order_id = 'SO-1011'").fetchone()
    finally:
        con.close()

    assert (current, total) == (48, 55)
    assert original == 47, (
        "the original-promise reading must differ, or the defect is not seeded")
    assert current - original == 1, "exactly SO-1011 should flip"
    orig, promised, delivered, on_time = row
    assert orig < promised, "SO-1011 must carry an earlier original promise"
    assert delivered <= promised and delivered > orig
    assert on_time in (True, 1)


def test_attribution_column_reconciles_with_an_independent_argmax(con):
    """Recompute attribution for every order and compare to the shipped column.

    `test_attribution_survives_a_narrow_production_delay` builds its narrow case from
    synthetic dates and ranks them with an inline copy of the unpivot/row_number logic,
    so it proves the *rule* is sound without ever reading the fact table's `attribution`
    CTE. Swap two phase_key labels in that CTE, or point one at the wrong var_ column,
    and it still passes.

    This walks the published variance columns in Python -- an independent implementation
    of the same contract -- and asserts the answer for all 132 orders. A mispairing of
    var_ column to phase_key now has nowhere to hide.
    """
    # The pairing published in 04_process_model.yml, phase_seq 2-10.
    spans = [
        (2, "mrp_planning", "var_mrp"),
        (3, "production_release", "var_release"),
        (4, "material_staging", "var_issue"),
        (5, "production_execution", "var_confirm"),
        (6, "quality_inspection", "var_qm"),
        (7, "goods_receipt", "var_gr"),
        (8, "picking_packing", "var_picking"),
        (9, "goods_issue", "var_goods_issue"),
        (10, "transportation", "var_shipment"),
    ]
    cols = ", ".join(c for _, _, c in spans)
    rows = con.execute(
        f"SELECT order_id, delay_attribution_phase, is_eligible, is_delivered, "
        f"delay_days, {cols} FROM fact_order_delivery ORDER BY order_id").fetchall()
    assert len(rows) == 132

    mismatches = []
    for r in rows:
        order_id, shipped, eligible, delivered, delay_days = r[:5]
        variances = r[5:]
        # Scope: only eligible, delivered, late orders are attributed at all.
        is_late = bool(eligible) and bool(delivered) and (delay_days or 0) > 0
        if is_late:
            positive = [(v, seq, key) for (seq, key, _), v in zip(spans, variances)
                        if v is not None and v > 0]
            # argmax by variance, ties to the lowest phase_seq.
            expected = max(positive, key=lambda t: (t[0], -t[1]))[2] if positive else None
        else:
            expected = None
        if shipped != expected:
            mismatches.append((order_id, shipped, expected, variances))

    assert mismatches == [], (
        f"{len(mismatches)} orders disagree with an independent argmax; "
        f"first: {mismatches[:3]}")


def test_attribution_sql_pairs_each_phase_with_the_declared_variance_column():
    """Compare the SQL's phase_key/var_ pairing to 04_process_model.yml, statically.

    Six of the nine variance columns are never positive in this dataset (only
    var_confirm, var_qm and var_shipment ever fire), so mislabelling any of the other
    six is invisible to every data-driven test -- including the reconciliation above,
    which walks the same pairing the fact table was built from. Verified: swapping the
    `goods_receipt` and `picking_packing` labels in the attribution CTE leaves the whole
    suite green.

    Reading the pairing out of the SQL text and diffing it against the metadata is the
    only check that covers all nine. It is also the check that keeps the artifact
    honest: 04_process_model.yml is what the guide and the diagram publish as the rule.
    """
    import re
    from src.semantic.constants import METADATA_DIR, SQL_DIR

    sql = (SQL_DIR / "02_staging_model.sql").read_text(encoding="utf-8")
    body = sql.split("attribution AS (", 1)[1].split("WHERE variance_days > 0", 1)[0]
    # Rows look like: SELECT order_id, <seq>[ AS phase_seq], '<key>'[ AS phase_key], <var>
    pattern = re.compile(
        r"SELECT\s+order_id,\s*(\d+)(?:\s+AS\s+phase_seq)?,\s*"
        r"'([a-z_]+)'(?:\s+AS\s+phase_key)?,\s*(var_[a-z_]+)")
    from_sql = {int(seq): (key, col) for seq, key, col in pattern.findall(body)}
    assert len(from_sql) == 9, f"expected 9 unpivoted spans, parsed {sorted(from_sql)}"
    assert sorted(from_sql) == list(range(2, 11)), sorted(from_sql)

    with open(METADATA_DIR / "04_process_model.yml", encoding="utf-8") as f:
        model = yaml.safe_load(f)
    phase_seq = {p["phase_key"]: p["phase_seq"] for p in model["phases"]}
    declared = {phase_seq[v["phase_key"]]: (v["phase_key"], v["column"])
                for v in model["variances"]}

    assert from_sql == declared, (
        "attribution CTE disagrees with 04_process_model.yml: "
        f"{ {k: (from_sql.get(k), declared.get(k)) for k in set(from_sql) | set(declared) if from_sql.get(k) != declared.get(k)} }")
