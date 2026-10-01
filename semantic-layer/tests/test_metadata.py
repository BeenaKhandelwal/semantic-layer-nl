import json, yaml, pytest
from src.semantic.constants import METADATA_DIR

def _yaml(name):
    with open(METADATA_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)

def _json(name):
    with open(METADATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)

ARTIFACTS = [
    "00_kpi_contract.md", "01_technical_metadata.json", "02_standardized_metadata.json",
    "03_glossary.yml", "03_column_bindings.yml", "04_process_model.yml",
]

@pytest.mark.parametrize("name", ARTIFACTS)
def test_artifact_exists_and_is_nonempty(name):
    p = METADATA_DIR / name
    assert p.exists(), f"missing {name}"
    assert len(p.read_text(encoding="utf-8").strip()) > 200

@pytest.mark.parametrize("name", ARTIFACTS)
def test_no_placeholders(name):
    text = (METADATA_DIR / name).read_text(encoding="utf-8")
    for bad in ("TBD", "TODO", "FIXME", "XXX", "<placeholder>"):
        assert bad not in text, f"{name} contains {bad}"

def test_process_model_has_12_phases():
    phases = _yaml("04_process_model.yml")["phases"]
    assert len(phases) == 12
    assert [p["phase_seq"] for p in phases] == list(range(1, 13))

def test_process_model_durations_match_the_warehouse():
    """The YAML and dim_process_phase must not drift apart.

    Phases 1-11 sum to 12, which is exactly what available_slack_days subtracts.
    All 12 phases sum to 13: billing follows delivery, so it cannot consume slack
    against the promised delivery date.
    """
    phases = _yaml("04_process_model.yml")["phases"]
    to_delivery = sum(
        p["standard_duration_days"] for p in phases if p["phase_seq"] <= 11
    )
    assert to_delivery == 12
    assert sum(p["standard_duration_days"] for p in phases) == 13

def test_process_model_agrees_with_dim_process_phase():
    """Same durations, same phase_keys, same order as the built warehouse."""
    import duckdb
    from src import build_warehouse
    from src.semantic.constants import DB_PATH
    build_warehouse.build()
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        rows = con.execute("""
            SELECT phase_seq, phase_key, standard_duration_days
            FROM dim_process_phase ORDER BY phase_seq
        """).fetchall()
    finally:
        con.close()
    phases = sorted(_yaml("04_process_model.yml")["phases"], key=lambda p: p["phase_seq"])
    assert [(p["phase_seq"], p["phase_key"], p["standard_duration_days"])
            for p in phases] == rows

def test_process_model_covers_manufacturing_modules():
    phases = _yaml("04_process_model.yml")["phases"]
    modules = {p["sap_module"] for p in phases}
    for required in ("SAP PP", "SAP QM", "SAP MM"):
        assert any(required in m for m in modules), f"no phase from {required}"

def test_glossary_has_synonyms_for_nl_resolution():
    """Without synonyms the resolver cannot map user vocabulary to columns."""
    terms = {t["term"]: t for t in _yaml("03_glossary.yml")["terms"]}
    assert "On-Time Delivery %" in terms
    otd = terms["On-Time Delivery %"]
    assert {"otd", "on time delivery", "delivery performance"} <= {
        s.lower() for s in otd["synonyms"]
    }
    region = terms["Region"]
    assert "india" in {v.lower() for v in region["allowed_values"]} or \
           "IN" in region["allowed_values"]

def test_every_glossary_term_has_owner_and_steward():
    for t in _yaml("03_glossary.yml")["terms"]:
        assert t.get("owner"), f"{t['term']} has no owner"
        assert t.get("steward"), f"{t['term']} has no steward"

def test_bindings_reference_real_fact_columns():
    import duckdb
    from src import build_warehouse
    from src.semantic.constants import DB_PATH
    build_warehouse.build()
    con = duckdb.connect(str(DB_PATH), read_only=True)
    for b in _yaml("03_column_bindings.yml")["bindings"]:
        cols = {r[1] for r in con.execute(f"PRAGMA table_info('{b['table']}')").fetchall()}
        assert b["column"] in cols, f"{b['table']}.{b['column']} does not exist"
    con.close()

def test_technical_metadata_has_sap_field_names():
    tech = _json("01_technical_metadata.json")
    blob = json.dumps(tech)
    for field in ("VBELN", "KUNNR", "WADAT_IST", "AUFNR"):
        assert field in blob, f"{field} missing from technical metadata"


# --- Added during review of Task 4 -----------------------------------------
# The artifacts passed every original test while carrying three defects that would
# have surfaced as confidently wrong NL answers rather than as errors.

def test_no_synonym_is_ambiguous():
    """One phrase must not resolve to two different terms.

    'PO' was a synonym of both Sales Order and Production Order, and 'location' of
    both Region and Plant. A resolver matching user vocabulary against these lists
    would silently pick one -- answering a production question with sales data and
    reporting it as grounded.
    """
    from collections import defaultdict
    owners = defaultdict(set)
    for t in _yaml("03_glossary.yml")["terms"]:
        for s in t.get("synonyms") or []:
            owners[s.lower().strip()].add(t["term"])
    clashes = {s: sorted(v) for s, v in owners.items() if len(v) > 1}
    assert clashes == {}, f"ambiguous synonyms: {clashes}"

def test_no_synonym_names_a_different_sap_document():
    """A synonym must not rename the business object.

    'purchase order' and 'PO' were listed under Sales Order. In SAP a purchase order
    is a procurement document (EKKO/EKPO); a sales order is VBAK. Treating them as
    synonyms invites a procurement question to be answered from sales data.
    """
    for t in _yaml("03_glossary.yml")["terms"]:
        syns = {s.lower() for s in (t.get("synonyms") or [])}
        if t["term"] == "Sales Order":
            assert "purchase order" not in syns
            assert "po" not in syns

def test_every_business_binding_has_a_glossary_term():
    """Bindings are the resolver's map from vocabulary to columns.

    A business-scoped binding whose term no glossary entry defines is unreachable:
    nothing tells the resolver what words lead to it. Internal bindings are exempt
    by design -- they are columns the compiler reads, not things users name.
    """
    terms = {t["term"] for t in _yaml("03_glossary.yml")["terms"]}
    bindings = _yaml("03_column_bindings.yml")["bindings"]
    assert bindings, "no bindings found"
    unscoped = [b["term"] for b in bindings if not b.get("scope")]
    assert unscoped == [], f"bindings missing a scope: {unscoped}"
    assert {b["scope"] for b in bindings} <= {"business", "internal"}
    orphans = sorted(
        b["term"] for b in bindings
        if b["scope"] == "business" and b["term"] not in terms
    )
    assert orphans == [], f"business bindings with no glossary term: {orphans}"

def test_metric_terms_are_defined_even_though_unbound():
    """Metrics are computed, so they have no single column -- but must still be defined.

    Guards the opposite failure from the test above: a metric dropping out of the
    glossary because it has no binding to anchor it.
    """
    terms = {t["term"] for t in _yaml("03_glossary.yml")["terms"]}
    for metric in ("On-Time Delivery %", "Manufacturing Schedule Adherence %",
                   "First Pass Yield %", "Eligible Orders"):
        assert metric in terms, f"{metric} missing from the glossary"

def test_variance_block_matches_the_warehouse_columns():
    """The documented variance spans must be the ones the SQL actually computes.

    04_process_model.yml is where a reader (and the guide) learns the variance model,
    so it drifting from the SQL is the same class of failure as a metric definition
    drifting from its implementation. Checks the column names against the fact table
    and the standards against dim_process_phase.
    """
    import duckdb
    from src import build_warehouse
    from src.semantic.constants import DB_PATH
    build_warehouse.build(fresh=True)
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        fact_cols = {r[1] for r in con.execute(
            "PRAGMA table_info('fact_order_delivery')").fetchall()}
        dim = dict(con.execute(
            "SELECT phase_key, standard_duration_days FROM dim_process_phase").fetchall())
        slack_total = con.execute("SELECT std_to_delivery FROM phase_standard").fetchone()[0]
    finally:
        con.close()

    variances = _yaml("04_process_model.yml")["variances"]
    assert len(variances) == 9, f"expected 9 variance columns, got {len(variances)}"
    for v in variances:
        assert v["column"] in fact_cols, f"{v['column']} is not a fact column"
        assert v["phase_key"] in dim, f"{v['phase_key']} is not a declared phase"
        assert "->" in v["span"], f"{v['column']} span must name both endpoints"

    # Contiguity: each span starts where the previous ended.
    for prev, cur in zip(variances, variances[1:]):
        prev_end = prev["span"].split("->")[1].strip()
        cur_start = cur["span"].split("->")[0].strip()
        assert prev_end == cur_start, (
            f"unowned time: {prev['column']} ends at {prev_end} but "
            f"{cur['column']} starts at {cur_start}"
        )

    # The documented standards must add up to the slack the warehouse subtracts.
    assert sum(v["standard_duration_days"] for v in variances) == slack_total == 12

def test_deferred_metric_is_marked_deferred():
    """Production Cycle Time is contracted but not implemented (design 10.2).

    Listing it beside three queryable metrics with no marker invites a reader to
    expect an answer the validator will refuse.
    """
    text = (METADATA_DIR / "00_kpi_contract.md").read_text(encoding="utf-8")
    idx = text.index("Production Cycle Time")
    assert "deferred" in text[idx:idx + 300].lower()

def test_kpi_contract_pins_the_meaning_of_last_month():
    """"Last month" must resolve to promised_delivery_date, and say so.

    Filtering IN/July on order_date instead returns 33/40 = 82.5% -- plausible,
    precise, and wrong by 4.8pp, with nothing in the number to reveal the swap.
    """
    text = (METADATA_DIR / "00_kpi_contract.md").read_text(encoding="utf-8")
    assert "promised_delivery_date" in text
    assert "82.5" in text, "the contract should show what the wrong reading returns"


# --- Added during review of the whole branch (Tasks 1-8) -------------------
# Seven defects survived 27 metadata tests. Each test below was falsified against
# the pre-fix artifacts: every one of them failed. A test that passes either way
# would document nothing.

def _fact_columns():
    import duckdb
    from src import build_warehouse
    from src.semantic.constants import DB_PATH
    build_warehouse.build()
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        return {c[1] for c in con.execute(
            "PRAGMA table_info('fact_order_delivery')").fetchall()}
    finally:
        con.close()


def test_every_phase_timestamp_field_is_a_real_column():
    """`prod_release_date` was declared for phase 3; the column is `release_date`.

    `test_variance_chain_is_contiguous` checked the variance `column` and `phase_key`
    against the warehouse but asserted only `"->" in span`, so a nonexistent span
    endpoint passed. Any code that reads `timestamp_field` to build SQL -- the
    provenance renderer and the diagram both do -- emits an invalid query.
    """
    cols = _fact_columns()
    bad = [(p["phase_seq"], p["timestamp_field"])
           for p in _yaml("04_process_model.yml")["phases"]
           if p["timestamp_field"] not in cols]
    assert bad == [], f"phases whose timestamp_field is not a fact column: {bad}"


def test_variance_span_endpoints_are_real_columns():
    """The same hole, on the other side of the artifact."""
    cols = _fact_columns()
    bad = []
    for v in _yaml("04_process_model.yml")["variances"]:
        start, end = (s.strip() for s in v["span"].split("->"))
        bad += [(v["column"], e) for e in (start, end) if e not in cols]
    assert bad == [], f"span endpoints that are not fact columns: {bad}"


def test_attribution_allowed_values_are_all_emittable():
    """11 values were declared; the SQL ranks 9 spans, so 2 can never be produced.

    A filter gate validating against `allowed_values` accepts
    `delay_attribution_phase = 'demand_capture'` and the pipeline returns zero rows
    dressed as a valid answer -- the exact failure the gates exist to stop.
    """
    import duckdb
    from src.semantic.constants import DB_PATH
    _fact_columns()
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        emittable = {r[0] for r in con.execute(
            "SELECT DISTINCT phase_key FROM dim_process_phase d "
            "WHERE d.phase_seq BETWEEN 2 AND 10").fetchall()}
    finally:
        con.close()

    declared_json = set(next(
        d["allowed_values"]
        for d in _json("02_standardized_metadata.json")["conformed_dimensions"]
        if d["dimension"] == "delay_attribution_phase"))
    declared_yaml = set(next(
        t["allowed_values"] for t in _yaml("03_glossary.yml")["terms"]
        if t.get("data_type") == "categorical" and "allowed_values" in t
        and "quality_inspection" in (t.get("allowed_values") or [])))

    assert declared_json == emittable, (
        f"02_standardized_metadata declares un-emittable values: "
        f"{sorted(declared_json - emittable)}")
    assert declared_yaml == emittable, (
        f"03_glossary declares un-emittable values: "
        f"{sorted(declared_yaml - emittable)}")

    # The semantic model carries its own copy, and it is the one the filter gate reads.
    declared_model = set(next(
        d["allowed_values"] for d in _yaml("05_semantic_model.yml")["dimensions"]
        if d["name"] == "delay_attribution_phase"))
    assert declared_model == emittable, (
        f"05_semantic_model declares un-emittable values: "
        f"{sorted(declared_model - emittable)}")


def test_attribution_rule_states_the_right_span_count():
    """Three artifacts said "phases 1-11"; the rule ranks 9 spans, seq 2-10."""
    for name in ("02_standardized_metadata.json", "00_kpi_contract.md"):
        text = (METADATA_DIR / name).read_text(encoding="utf-8")
        assert "phases 1-11" not in text and "phases 1–11" not in text, (
            f"{name} still describes attribution as spanning phases 1-11; "
            "the emittable domain is the 9 variance spans")


def test_q2_narrative_numbers_match_the_data():
    """The contract's Q2 sentence claimed 4.1 days avg against 4.0 days of slack.

    Measured on the 4 QM-attributed IN-July orders: avg(var_qm) = 4.75 and
    available_slack_days = 0 for all four. Task 12 renders this sentence as
    provenance, so a wrong number here becomes a wrong answer with a citation.
    """
    import duckdb
    from src.semantic.constants import DB_PATH
    _fact_columns()
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        avg_var, avg_slack, n = con.execute("""
            SELECT avg(var_qm), avg(available_slack_days), count(*)
            FROM fact_order_delivery
            WHERE region = 'IN'
              AND promised_delivery_date BETWEEN DATE '2026-07-01' AND DATE '2026-07-31'
              AND delay_attribution_phase = 'quality_inspection'
        """).fetchone()
    finally:
        con.close()
    assert (n, float(avg_var), float(avg_slack)) == (4, 4.75, 0.0)

    text = (METADATA_DIR / "00_kpi_contract.md").read_text(encoding="utf-8")
    assert "4.75" in text, "contract must quote the measured average variance"
    for stale in ("4.1 days", "3.1 days", "4.0 days"):
        assert stale not in text, f"contract still quotes the wrong figure {stale}"


def test_no_metadata_artifact_hardcodes_the_as_of_date():
    """AS_OF_DATE lives in constants.py only; YAML/SQL carry `__AS_OF_DATE__`.

    A literal date in an artifact is a silent expiry: the file keeps parsing and
    keeps returning a number after the date stops being the as-of date.
    """
    from src.semantic.constants import AS_OF_DATE, METADATA_DIR as MD, SQL_DIR
    literal = AS_OF_DATE.isoformat()
    offenders = []
    for d in (MD, SQL_DIR):
        for p in sorted(d.rglob("*")):
            if p.is_file() and p.suffix in {".yml", ".yaml", ".json", ".sql", ".md"}:
                for i, line in enumerate(
                        p.read_text(encoding="utf-8").splitlines(), start=1):
                    if literal in line:
                        offenders.append(f"{p.name}:{i}")
    assert offenders == [], (
        f"{literal} is hard-coded in {offenders}; use the __AS_OF_DATE__ token")


def test_no_synonym_collides_with_a_term_name():
    """'quality inspection' was a synonym of Inspection Lot and also a term.

    `test_no_synonym_is_ambiguous` compares synonyms to synonyms only, so this
    class of collision -- the same class as the fixed 'PO' defect -- passed it.
    """
    terms = _yaml("03_glossary.yml")["terms"]
    names = {t["term"].lower().strip(): t["term"] for t in terms}
    clashes = {}
    for t in terms:
        for s in t.get("synonyms") or []:
            owner = names.get(s.lower().strip())
            if owner and owner != t["term"]:
                clashes[s] = sorted({owner, t["term"]})
    assert clashes == {}, f"synonyms that collide with term names: {clashes}"


def test_production_order_grain_claim_is_enforced():
    """02_standardized_metadata cited `test_production_order_grain`, which did not
    exist. Both manufacturing metrics sit on this grain; an unenforced claim is a
    claim that stops being true without anything failing."""
    import duckdb
    from src.semantic.constants import DB_PATH
    _fact_columns()
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        rows, distinct = con.execute(
            "SELECT count(*), count(DISTINCT production_order_id) "
            "FROM fact_production_order").fetchone()
    finally:
        con.close()
    assert rows == distinct == 131, (rows, distinct)
