# Semantic Layer NL Querying MVP — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable semantic layer over a synthetic SAP Plan-to-Deliver warehouse that answers two natural-language questions — one descriptive, one diagnostic — through governed metric definitions rather than free-hand SQL, with every published number under test.

**Architecture:** Raw CSVs → DuckDB staging → order-grain fact table. A tool-neutral YAML semantic model declares entities, joins with cardinality, and 3 metrics with grain/exclusions. Natural language is resolved to a **validated `QueryIntent` JSON object** (Claude API, json_schema-constrained), passed through a 7-gate validator, then compiled to SQL by a **deterministic, LLM-free compiler**. The model chooses *which* governed metric and filters apply; it never writes arithmetic. Offline golden intents make everything except the resolver runnable with no API key.

**Tech Stack:** Python 3.12, DuckDB 1.5.2, PyYAML, pytest, `anthropic` 0.100.0 (resolver only), Pydantic (intent schema).

## Global Constraints

- **Repo root:** `C:\Users\legion\semantic-layer-nl\`. Spec at `docs/design.md` — the authority; if this plan and the spec disagree, stop and flag it.
- **No API key required.** `pytest` must pass and both demo queries must work with `ANTHROPIC_API_KEY` unset. Only `resolver.py` may need credentials.
- **No network access** in build, compile, or test paths.
- **No wall-clock, no unseeded randomness.** The as-of date is the constant `AS_OF_DATE = date(2026, 8, 7)`, defined once in `src/semantic/constants.py` and imported everywhere. Never call `date.today()`. The generator uses `random.Random(20260807)` exclusively.
- **`AS_OF_DATE` appears as a literal in exactly one place: `constants.py`.** SQL files and YAML carry the token `__AS_OF_DATE__`; the loading code substitutes it. A reviewer finding `2026-08-07` hard-coded in a `.sql` or `.yml` file should flag it. Tests may use date literals freely — a test that computes its own expected value proves nothing.
- **Determinism:** re-running `python data/generate.py` must leave CSVs byte-identical. Write CSVs with `newline=""` and `lineterminator="\n"`.
- **The LLM never writes SQL or arithmetic.** `compiler.py` and `validator.py` must not import `anthropic`.
- **Claude API (resolver only, per spec §4.3):** model `claude-opus-5`; `thinking={"type": "adaptive"}`; `output_config={"effort": "medium"}`; `max_tokens=16000`; structured output via `client.messages.parse(output_format=QueryIntent)`; check `response.stop_reason == "refusal"` **before** reading `.content`. **Never** pass `temperature`, `top_p`, `top_k`, or `budget_tokens` — they return HTTP 400 on Opus 5. Construct with zero-arg `anthropic.Anthropic()` so it picks up any configured auth.
- **Money numbers are canon.** These come from spec §5.1 and §5.4 and are verified arithmetic. Every one is asserted by a test. Do not "fix" a test to match code — fix the code.

| Quantity | Value |
|---|---|
| OTD, IN July 2026 | 48/55 = 87.2727% |
| OTD, IN June 2026 | 25/26 = 96.1538% |
| Drop | 8.88pp |
| Late attribution, IN July | quality_inspection 4, transportation 2, production_execution 1 |
| Naive delivery-grain OTD (wrong) | 54/61 = 88.5246% |
| First-pass yield, IN July | 51/54 = 94.4444% |
| Naive FPY counting rework (wrong) | 52/55 = 94.5455% |
| Schedule adherence, IN July | 50/54 = 92.5926% |
| Total orders | 132 (20 in `seed_core.csv`, 112 generated) |

---

## File Structure

| File | Responsibility |
|---|---|
| `data/seed_core.csv` | 20 hand-authored orders: all 8 defects, all 11 late orders. The rows the guide prints. |
| `data/generate.py` | Deterministic filler → 112 well-behaved orders; writes all 6 raw CSVs. |
| `data/*_raw.csv` | Committed SAP-shaped extracts (generator output). |
| `metadata/00_kpi_contract.md` … `07_catalog_asset.json` | The 8 phase artifacts — the deliverable's substance. |
| `sql/02_staging_model.sql` | Staging views + `fact_order_delivery` (order grain) + `fact_production_order`. |
| `src/semantic/constants.py` | `AS_OF_DATE`, paths, `DB_PATH`. Zero dependencies. |
| `src/semantic/loader.py` | Parse + structurally validate `05_semantic_model.yml`; typed accessors. |
| `src/semantic/intent.py` | Pydantic `QueryIntent`. Imported by resolver, validator, compiler. |
| `src/semantic/validator.py` | The 7 gates. Pure. No DB, no LLM. |
| `src/semantic/compiler.py` | `QueryIntent` + model → SQL string. Pure. No LLM. |
| `src/semantic/executor.py` | Run SQL on DuckDB, return rows. |
| `src/semantic/dq.py` | Execute `06_dq_rules.yml`, return per-rule results + trust badge. |
| `src/semantic/provenance.py` | Assemble answer + lineage + badge + definition into a printable block. |
| `src/semantic/retriever.py` | Select the metadata slice for a question (resolver's context). |
| `src/semantic/resolver.py` | Claude API: NL → `QueryIntent`. **Only** file importing `anthropic`. |
| `src/build_warehouse.py` | CSVs → DuckDB. Idempotent. |
| `src/ask.py` | CLI. `--offline Q1` uses golden intents; bare question calls resolver. |
| `tests/golden_intents.json` | Hand-authored intents for Q1, Q2. |
| `tests/test_data.py` | Spec §5.1 denominators vs. committed CSVs. |
| `tests/test_compiler.py` | Grain-correct vs. naive figures; SQL shape. |
| `tests/test_validator.py` | Each gate rejects what it must. |
| `tests/test_dq.py` | Each of the 8 defects trips its intended rule. |
| `tests/test_end_to_end.py` | Q1/Q2 through the full offline pipeline. |
| `README.md` | The guide: P0–P7, artifact per phase, NL failure closed. |

**Task order rationale:** data first (Tasks 1–2) because every later assertion depends on it; then warehouse (3); then the metadata artifacts the compiler reads (4–5); then the pure logic (6–8); then DQ/provenance (9–10); then CLI + e2e (11); resolver last (12) since it's the only unverifiable-here piece; guide last (13) so it documents what exists.

---

## Task 1: Hand-authored seed data

**Files:**
- Create: `data/seed_core.csv`
- Create: `src/semantic/constants.py`
- Test: `tests/test_data.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `constants.AS_OF_DATE: date`, `constants.REPO_ROOT: Path`, `constants.DATA_DIR: Path`, `constants.METADATA_DIR: Path`, `constants.SQL_DIR: Path`, `constants.DB_PATH: Path`. `data/seed_core.csv` with the exact columns listed in Step 3.

- [ ] **Step 1: Write the failing test**

Create `tests/test_data.py`:

```python
import csv
from datetime import date
from src.semantic.constants import DATA_DIR

def _seed_rows():
    with open(DATA_DIR / "seed_core.csv", newline="") as f:
        return list(csv.DictReader(f))

def test_seed_has_20_orders():
    rows = _seed_rows()
    assert len(rows) == 20
    assert len({r["order_id"] for r in rows}) == 20

def test_seed_late_orders_are_exactly_the_documented_ones():
    """The 7 late IN/July orders from spec section 5.1."""
    rows = {r["order_id"]: r for r in _seed_rows()}
    expected_late = {
        "SO-1002", "SO-1003", "SO-1004", "SO-1005",
        "SO-1006", "SO-1009", "SO-1010",
    }
    actual_late = set()
    for oid, r in rows.items():
        if r["region"] != "IN" or not r["promised_delivery_date"].startswith("2026-07"):
            continue
        if r["order_status"] == "CANC":
            continue
        if r["final_delivery_date"] and r["final_delivery_date"] > r["promised_delivery_date"]:
            actual_late.add(oid)
    assert actual_late == expected_late

def test_seed_attribution_counts():
    """Spec section 5.1: quality_inspection 4, transportation 2, production_execution 1."""
    from collections import Counter
    rows = _seed_rows()
    counts = Counter(
        r["expected_attribution_phase"]
        for r in rows
        if r["expected_attribution_phase"]
    )
    assert counts == {
        "quality_inspection": 4,
        "transportation": 2,
        "production_execution": 1,
    }

def test_seed_defects_present():
    rows = {r["order_id"]: r for r in _seed_rows()}
    assert rows["SO-1007"]["order_status"] == "CANC"           # defect 1
    assert rows["SO-1013"]["final_delivery_date"] == ""         # defect 2 (in transit)
    assert rows["SO-1013"]["promised_delivery_date"] > "2026-08-07"
    assert rows["SO-1004"]["rework"] == "Y"                     # defect 3
    assert rows["SO-1009"]["split_delivery"] == "mixed"         # defect 4
    assert rows["SO-1011"]["promised_date_original"] == "2026-07-18"  # defect 5
    assert rows["SO-1015"]["production_order_id"] == ""         # defect 6

def test_split_delivery_orders():
    """5 fully-on-time splits + SO-1009 mixed = 6 split orders (spec 5.4)."""
    rows = _seed_rows()
    on_time_splits = {r["order_id"] for r in rows if r["split_delivery"] == "on_time"}
    mixed = {r["order_id"] for r in rows if r["split_delivery"] == "mixed"}
    assert on_time_splits == {"SO-1012", "SO-1014", "SO-1016", "SO-1017", "SO-1018"}
    assert mixed == {"SO-1009"}

def test_as_of_date_is_frozen():
    from src.semantic.constants import AS_OF_DATE
    assert AS_OF_DATE == date(2026, 8, 7)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/Users/legion/semantic-layer-nl && python -m pytest tests/test_data.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src'` (collection error).

- [ ] **Step 3: Create constants and seed data**

Create `src/__init__.py` (empty), `src/semantic/__init__.py` (empty), `tests/__init__.py` (empty), and `pytest.ini`:

```ini
[pytest]
testpaths = tests
pythonpath = .
```

Create `src/semantic/constants.py`:

```python
"""Frozen constants. No wall-clock, no randomness anywhere in this project."""
from datetime import date
from pathlib import Path

# The demo's "today". Every relative date ("last month") resolves against this.
# Never call date.today() -- it would make results drift and tests flaky.
AS_OF_DATE = date(2026, 8, 7)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
METADATA_DIR = REPO_ROOT / "metadata"
SQL_DIR = REPO_ROOT / "sql"
DB_PATH = REPO_ROOT / "warehouse.duckdb"
```

Create `data/seed_core.csv` with exactly these 20 rows. Columns:
`order_id,region,plant,warehouse,carrier,customer_id,order_date,promised_delivery_date,promised_date_original,order_status,production_order_id,inspection_lot_id,rework,split_delivery,mrp_date,prod_release_date,material_issue_date,prod_confirm_date,qm_decision_date,gr_date,picking_date,goods_issue_date,shipment_date,final_delivery_date,invoice_date,expected_attribution_phase`

```csv
order_id,region,plant,warehouse,carrier,customer_id,order_date,promised_delivery_date,promised_date_original,order_status,production_order_id,inspection_lot_id,rework,split_delivery,mrp_date,prod_release_date,material_issue_date,prod_confirm_date,qm_decision_date,gr_date,picking_date,goods_issue_date,shipment_date,final_delivery_date,invoice_date,expected_attribution_phase
SO-1001,IN,1010,WH-IN-01,BLUEDART,C-IN-001,2026-07-01,2026-07-13,,DLVD,PO-3001,QL-4001,N,none,2026-07-02,2026-07-03,2026-07-04,2026-07-07,2026-07-08,2026-07-09,2026-07-10,2026-07-10,2026-07-11,2026-07-12,2026-07-14,
SO-1002,IN,1010,WH-IN-01,BLUEDART,C-IN-002,2026-07-01,2026-07-13,,DLVD,PO-3002,QL-4002,N,none,2026-07-02,2026-07-03,2026-07-04,2026-07-07,2026-07-12,2026-07-13,2026-07-14,2026-07-14,2026-07-15,2026-07-16,2026-07-18,quality_inspection
SO-1003,IN,1010,WH-IN-01,FEDEX,C-IN-003,2026-07-02,2026-07-14,,DLVD,PO-3003,QL-4003,N,none,2026-07-03,2026-07-04,2026-07-05,2026-07-08,2026-07-09,2026-07-10,2026-07-11,2026-07-11,2026-07-12,2026-07-19,2026-07-21,transportation
SO-1004,IN,1010,WH-IN-01,BLUEDART,C-IN-004,2026-07-02,2026-07-14,,DLVD,PO-3004,QL-4004,Y,none,2026-07-03,2026-07-04,2026-07-05,2026-07-08,2026-07-14,2026-07-15,2026-07-16,2026-07-16,2026-07-17,2026-07-18,2026-07-20,quality_inspection
SO-1005,IN,1010,WH-IN-01,BLUEDART,C-IN-005,2026-07-03,2026-07-15,,DLVD,PO-3005,QL-4005,N,none,2026-07-04,2026-07-05,2026-07-06,2026-07-13,2026-07-14,2026-07-15,2026-07-16,2026-07-16,2026-07-17,2026-07-18,2026-07-20,production_execution
SO-1006,IN,1010,WH-IN-01,FEDEX,C-IN-006,2026-07-03,2026-07-15,,DLVD,PO-3006,QL-4006,N,none,2026-07-04,2026-07-05,2026-07-06,2026-07-09,2026-07-15,2026-07-16,2026-07-17,2026-07-17,2026-07-18,2026-07-19,2026-07-21,quality_inspection
SO-1007,IN,1010,WH-IN-01,BLUEDART,C-IN-007,2026-07-04,2026-07-16,,CANC,PO-3007,,N,none,2026-07-05,2026-07-06,,,,,,,,,,
SO-1008,IN,1010,WH-IN-01,BLUEDART,C-IN-008,2026-07-04,2026-07-16,,DLVD,PO-3008,QL-4008,N,none,2026-07-05,2026-07-06,2026-07-07,2026-07-10,2026-07-11,2026-07-12,2026-07-13,2026-07-13,2026-07-14,2026-07-15,2026-07-17,
SO-1009,IN,1010,WH-IN-01,FEDEX,C-IN-009,2026-07-05,2026-07-17,,DLVD,PO-3009,QL-4009,N,mixed,2026-07-06,2026-07-07,2026-07-08,2026-07-11,2026-07-12,2026-07-13,2026-07-14,2026-07-14,2026-07-15,2026-07-20,2026-07-22,transportation
SO-1010,IN,1010,WH-IN-01,BLUEDART,C-IN-010,2026-07-06,2026-07-18,,DLVD,PO-3010,QL-4010,N,none,2026-07-07,2026-07-08,2026-07-09,2026-07-12,2026-07-18,2026-07-19,2026-07-20,2026-07-20,2026-07-21,2026-07-22,2026-07-24,quality_inspection
SO-1011,IN,1010,WH-IN-01,BLUEDART,C-IN-011,2026-07-06,2026-07-24,2026-07-18,DLVD,PO-3011,QL-4011,N,none,2026-07-07,2026-07-08,2026-07-09,2026-07-12,2026-07-13,2026-07-14,2026-07-15,2026-07-15,2026-07-16,2026-07-21,2026-07-23,
SO-1012,IN,1010,WH-IN-01,FEDEX,C-IN-012,2026-07-07,2026-07-19,,DLVD,PO-3012,QL-4012,N,on_time,2026-07-08,2026-07-09,2026-07-10,2026-07-13,2026-07-14,2026-07-15,2026-07-16,2026-07-16,2026-07-17,2026-07-18,2026-07-20,
SO-1013,IN,1010,WH-IN-01,BLUEDART,C-IN-013,2026-07-28,2026-08-12,,IN_TRANSIT,PO-3013,QL-4013,N,none,2026-07-29,2026-07-30,2026-07-31,2026-08-03,2026-08-04,2026-08-05,2026-08-06,2026-08-06,2026-08-07,,,
SO-1014,IN,1010,WH-IN-01,BLUEDART,C-IN-014,2026-07-08,2026-07-20,,DLVD,PO-3014,QL-4014,N,on_time,2026-07-09,2026-07-10,2026-07-11,2026-07-14,2026-07-15,2026-07-16,2026-07-17,2026-07-17,2026-07-18,2026-07-19,2026-07-21,
SO-1015,IN,1010,WH-IN-01,BLUEDART,C-IN-015,2026-07-09,2026-07-21,,DLVD,,,N,none,,,,,,,2026-07-17,2026-07-17,2026-07-18,2026-07-19,2026-07-21,
SO-1016,IN,1010,WH-IN-01,FEDEX,C-IN-016,2026-07-10,2026-07-22,,DLVD,PO-3016,QL-4016,N,on_time,2026-07-11,2026-07-12,2026-07-13,2026-07-16,2026-07-17,2026-07-18,2026-07-19,2026-07-19,2026-07-20,2026-07-21,2026-07-23,
SO-1017,IN,1010,WH-IN-01,BLUEDART,C-IN-017,2026-07-11,2026-07-23,,DLVD,PO-3017,QL-4017,N,on_time,2026-07-12,2026-07-13,2026-07-14,2026-07-17,2026-07-18,2026-07-19,2026-07-20,2026-07-20,2026-07-21,2026-07-22,2026-07-24,
SO-1018,IN,1010,WH-IN-01,BLUEDART,C-IN-018,2026-07-12,2026-07-24,,DLVD,PO-3018,QL-4018,N,on_time,2026-07-13,2026-07-14,2026-07-15,2026-07-18,2026-07-19,2026-07-20,2026-07-21,2026-07-21,2026-07-22,2026-07-23,2026-07-25,
SO-1019,IN,1010,WH-IN-01,BLUEDART,C-IN-019,2026-06-01,2026-06-13,,DLVD,PO-3019,QL-4019,N,none,2026-06-02,2026-06-03,2026-06-04,2026-06-07,2026-06-08,2026-06-09,2026-06-10,2026-06-10,2026-06-11,2026-06-18,2026-06-20,
SO-1020,US,1710,WH-US-01,FEDEX,C-US-001,2026-07-01,2026-07-13,,DLVD,PO-3020,QL-4020,N,none,2026-07-02,2026-07-03,2026-07-04,2026-07-07,2026-07-08,2026-07-09,2026-07-10,2026-07-10,2026-07-11,2026-07-12,2026-07-14,
```

Notes for the implementer:
- `expected_attribution_phase` is a **test oracle column** — it records the answer the pipeline must independently derive from timestamps. The compiler must never read it. `tests/test_end_to_end.py` compares the derived attribution against it.
- `SO-1013` is promised 2026-08-12 (after `AS_OF_DATE`), so it is not-yet-due and falls outside the July window — it must not count as late anywhere.
- `SO-1019` is the single late June IN order (June: 27 in window, 1 cancelled, 25 on time of 26 eligible). Its `expected_attribution_phase` is **empty**: the oracle column is populated for IN-July orders only, since that is the window Q2 interrogates, and `test_seed_attribution_counts` counts the column unfiltered.
- `SO-1011` shows defect 5: `promised_date_original` 2026-07-18 was re-promised to 2026-07-24. Delivered 07-21 → on time against the current promise, late against the original. The metric measures the **current** promise; the semantic model states this explicitly.
- Blank means NULL. Keep the trailing commas exactly as written.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_data.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add pytest.ini src/__init__.py src/semantic/__init__.py src/semantic/constants.py data/seed_core.csv tests/__init__.py tests/test_data.py
git commit -m "feat: add frozen constants and 20-row hand-authored seed dataset"
```

---

## Task 2: Deterministic data generator

**Files:**
- Create: `data/generate.py`
- Create (generated, committed): `data/sales_orders_raw.csv`, `data/production_orders_raw.csv`, `data/inspection_lots_raw.csv`, `data/goods_movements_raw.csv`, `data/deliveries_raw.csv`, `data/shipments_raw.csv`
- Modify: `tests/test_data.py` (append)

**Interfaces:**
- Consumes: `constants.DATA_DIR`, `data/seed_core.csv`.
- Produces: 6 raw CSVs. `sales_orders_raw.csv` columns: `order_id,region,plant,warehouse,carrier,customer_id,order_date,promised_delivery_date,promised_date_original,order_status`. `deliveries_raw.csv`: `delivery_id,order_id,delivery_leg,picking_date,goods_issue_date,delivery_date,delivery_status`. `production_orders_raw.csv`: `production_order_id,order_id,plant,mrp_date,release_date,scheduled_finish_date,material_issue_date,confirm_date,gr_date,status`. `inspection_lots_raw.csv`: `inspection_lot_id,production_order_id,decision_seq,decision_date,usage_decision,qty_inspected,qty_accepted`. `goods_movements_raw.csv`: `movement_id,production_order_id,movement_type,posting_date`. `shipments_raw.csv`: `shipment_id,delivery_id,carrier,dispatch_date,delivery_date,delivery_status`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_data.py`:

```python
import subprocess, sys, hashlib
from src.semantic.constants import DATA_DIR, REPO_ROOT

RAW_FILES = [
    "sales_orders_raw.csv", "production_orders_raw.csv", "inspection_lots_raw.csv",
    "goods_movements_raw.csv", "deliveries_raw.csv", "shipments_raw.csv",
]

def _orders():
    with open(DATA_DIR / "sales_orders_raw.csv", newline="") as f:
        return list(csv.DictReader(f))

def test_all_raw_files_exist():
    for name in RAW_FILES:
        assert (DATA_DIR / name).exists(), f"missing {name}"

def test_total_order_count():
    assert len(_orders()) == 132

def test_in_july_window_composition():
    """Spec 5.1: 56 in window, 1 cancelled, 55 eligible, 48 on time, 7 late."""
    rows = [r for r in _orders()
            if r["region"] == "IN" and r["promised_delivery_date"].startswith("2026-07")]
    assert len(rows) == 56
    cancelled = [r for r in rows if r["order_status"] == "CANC"]
    assert len(cancelled) == 1
    assert len(rows) - len(cancelled) == 55

def test_in_june_window_composition():
    rows = [r for r in _orders()
            if r["region"] == "IN" and r["promised_delivery_date"].startswith("2026-06")]
    assert len(rows) == 27
    assert len([r for r in rows if r["order_status"] == "CANC"]) == 1

def test_us_july_window_composition():
    rows = [r for r in _orders()
            if r["region"] == "US" and r["promised_delivery_date"].startswith("2026-07")]
    assert len(rows) == 30
    assert len([r for r in rows if r["order_status"] == "CANC"]) == 2

def test_us_june_window_composition():
    rows = [r for r in _orders()
            if r["region"] == "US" and r["promised_delivery_date"].startswith("2026-06")]
    assert len(rows) == 15

def test_august_not_yet_due_window():
    """4 orders promised after AS_OF_DATE -- the not-yet-due exclusion."""
    rows = [r for r in _orders()
            if r["region"] == "IN" and r["promised_delivery_date"].startswith("2026-08")]
    assert len(rows) == 4
    for r in rows:
        assert r["promised_delivery_date"] > "2026-08-07"

def test_seed_orders_all_present_in_raw():
    seed_ids = {r["order_id"] for r in _seed_rows()}
    raw_ids = {r["order_id"] for r in _orders()}
    assert seed_ids <= raw_ids

def test_split_deliveries_produce_extra_rows():
    """6 split orders -> 6 extra delivery legs."""
    with open(DATA_DIR / "deliveries_raw.csv", newline="") as f:
        deliveries = list(csv.DictReader(f))
    from collections import Counter
    per_order = Counter(d["order_id"] for d in deliveries)
    assert len([o for o, n in per_order.items() if n == 2]) == 6

def test_rework_lot_has_two_decisions():
    with open(DATA_DIR / "inspection_lots_raw.csv", newline="") as f:
        lots = list(csv.DictReader(f))
    ql4004 = [l for l in lots if l["inspection_lot_id"] == "QL-4004"]
    assert len(ql4004) == 2
    assert {l["decision_seq"] for l in ql4004} == {"1", "2"}
    first = next(l for l in ql4004 if l["decision_seq"] == "1")
    assert first["usage_decision"] == "REWORK"

def test_generator_is_deterministic():
    """Re-running must leave files byte-identical."""
    before = {n: hashlib.sha256((DATA_DIR / n).read_bytes()).hexdigest() for n in RAW_FILES}
    subprocess.run([sys.executable, str(DATA_DIR / "generate.py")], cwd=REPO_ROOT, check=True)
    after = {n: hashlib.sha256((DATA_DIR / n).read_bytes()).hexdigest() for n in RAW_FILES}
    assert before == after
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_data.py -v`
Expected: the 7 Task-1 tests PASS; the new ones FAIL on missing `sales_orders_raw.csv`.

- [ ] **Step 3: Write the generator**

Create `data/generate.py`. Requirements it must satisfy — derive the filler counts from these, do not hardcode blindly:

```python
"""Deterministic sample-data generator. Fixed seed, no wall-clock, no network.

Emits 6 SAP-shaped raw CSVs from data/seed_core.csv plus generated filler.
Re-running produces byte-identical output.

Target composition (spec section 5.1):
  IN Jul 2026: 56 in window, 1 cancelled, 55 eligible, 48 on time, 7 late
  IN Jun 2026: 27 in window, 1 cancelled, 26 eligible, 25 on time, 1 late
  IN Aug 2026:  4 in window, all not-yet-due
  US Jul 2026: 30 in window, 2 cancelled, 28 eligible, 26 on time, 2 late
  US Jun 2026: 15 in window, 0 cancelled, 15 eligible, 14 on time, 1 late
  Total: 132 orders
"""
import csv, random
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
RNG = random.Random(20260807)   # fixed seed -- never change

# Standard phase durations (days), from metadata/04_process_model.yml
STD = {
    "mrp": 1, "release": 1, "issue": 1, "confirm": 3,
    "qm": 1, "gr": 1, "picking": 1, "goods_issue": 0,
    "shipment": 3, "delivery": 0, "invoice": 1,
}

def write_csv(name, fieldnames, rows):
    """Deterministic CSV writing: LF endings, no platform variance."""
    with open(DATA_DIR / name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
```

Implementation requirements:

1. **Read `seed_core.csv` first.** Seed rows pass through verbatim — never regenerate or perturb them. Count what they already contribute per window, then generate only the difference. Seed contributions: IN-Jul 17 orders (1 cancelled, 7 late, 9 on time), IN-Jun 1 (SO-1019, late), IN-Aug 1 (SO-1013), US-Jul 1 (SO-1020, on time).
2. **Filler is on time and not cancelled by default**, deviating only where a window needs a late or cancelled count the seed doesn't supply. Required filler per window:

| Window | Seed gives | Filler count | Filler composition | Resulting window total |
|---|---|---|---|---|
| IN Jul | 17 (1 canc, 7 late, 9 on time) | 39 | 39 on time | 56 in window, 55 eligible, 48 on time |
| IN Jun | 1 (SO-1019, late) | 26 | 25 on time + 1 cancelled | 27 in window, 26 eligible, 25 on time |
| IN Aug | 1 (SO-1013) | 3 | 3 not-yet-due | 4 in window, 0 eligible |
| US Jul | 1 (SO-1020, on time) | 29 | 25 on time + 2 late + 2 cancelled | 30 in window, 28 eligible, 26 on time |
| US Jun | 0 | 15 | 14 on time + 1 late | 15 in window, 15 eligible, 14 on time |
| **Total** | **20** | **112** | | **132** |
3. **Assert the composition before writing.** End `main()` with explicit asserts on each window's counts so a wrong generator fails loudly at generation time, not later in the test suite.
4. **Order IDs:** seed uses `SO-1001`–`SO-1020`. Filler uses `SO-2001` upward, assigned in a fixed loop order so IDs are stable across runs.
5. **Derive timestamps by walking the phase chain** from `order_date` using `STD`, so on-time orders land on or before `promised_delivery_date`. For the seed rows, use the dates given in the CSV as-is.
6. **Split deliveries:** the 6 orders flagged `on_time`/`mixed` in `split_delivery` get two rows in `deliveries_raw.csv` (`delivery_leg` 1 and 2) with IDs suffixed `A`/`B`. For `SO-1009`, leg A `delivery_date` = 2026-07-16 (on time), leg B = 2026-07-20 (late); the order-grain `final_delivery_date` is the **max** = 2026-07-20. All other orders get one delivery row.
7. **Rework (`QL-4004`):** two rows in `inspection_lots_raw.csv` — `decision_seq` 1 with `usage_decision=REWORK` on 2026-07-11, `decision_seq` 2 with `ACCEPT` on 2026-07-14. Every other lot gets a single `decision_seq=1` row.
8. **`SO-1015`** (make-to-stock) contributes no row to `production_orders_raw.csv`, `inspection_lots_raw.csv`, or `goods_movements_raw.csv`.
9. **`SO-1007`** (cancelled) gets a production order with `status=CANC` but no delivery, no shipment, no inspection lot.
10. **`SO-1013`** (in transit) gets a delivery row with `delivery_date` empty and `delivery_status=IN_TRANSIT`.
11. **Schedule adherence:** set `scheduled_finish_date` on production orders so exactly **50 of the 54** IN/July production orders confirm on or before it (92.5926%). The 4 that miss are `PO-3005` (production_execution delay) and 3 filler orders chosen by fixed index.
12. **First-pass yield:** exactly **3 of the 54** IN/July lots have a first decision that is not `ACCEPT` (51/54 = 94.4444%). `QL-4004` is one (REWORK); the other 2 are filler lots at fixed indices with `usage_decision=REJECT`.

- [ ] **Step 4: Generate and run tests**

Run:
```bash
python data/generate.py && python -m pytest tests/test_data.py -v
```
Expected: all tests PASS. If a composition assert fires inside the generator, fix the filler counts — do not relax the test.

- [ ] **Step 5: Commit**

```bash
git add data/generate.py data/*_raw.csv tests/test_data.py
git commit -m "feat: add deterministic data generator producing 132-order dataset"
```

---

## Task 3: DuckDB warehouse with order-grain fact table

**Files:**
- Create: `sql/02_staging_model.sql`
- Create: `src/build_warehouse.py`
- Create: `tests/test_warehouse.py`

**Interfaces:**
- Consumes: the 6 raw CSVs; `constants.DB_PATH`, `constants.SQL_DIR`, `constants.DATA_DIR`.
- Produces: `build_warehouse.build(db_path=None) -> None`, idempotent. Tables: `stg_sales_orders`, `stg_deliveries`, `stg_production_orders`, `stg_inspection_lots`, `stg_shipments`, `stg_goods_movements`, `fact_order_delivery` (**one row per order_id**), `fact_production_order` (one row per production_order_id), `dim_process_phase`.
- `fact_order_delivery` columns: `order_id, region, plant, warehouse, carrier, customer_id, order_date, promised_delivery_date, promised_date_original, order_status, production_order_id, delivery_count, final_delivery_date, is_delivered, is_eligible, is_on_time, delay_days, mrp_date, prod_release_date, scheduled_finish_date, material_issue_date, prod_confirm_date, qm_first_decision_date, qm_final_decision_date, gr_date, picking_date, goods_issue_date, shipment_date, invoice_date, var_mrp, var_release, var_issue, var_confirm, var_qm, var_gr, var_picking, var_goods_issue, var_shipment, delay_attribution_phase, available_slack_days`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_warehouse.py`:

```python
import duckdb, pytest
from src import build_warehouse
from src.semantic.constants import DB_PATH

@pytest.fixture(scope="module")
def con():
    build_warehouse.build()
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_warehouse.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.build_warehouse'`.

- [ ] **Step 3: Write the SQL and builder**

Create `sql/02_staging_model.sql`. Key requirements:

```sql
-- Phase 2 artifact: standardize raw SAP extracts and model to declared grain.
-- Grain declarations (enforced by tests, referenced by 05_semantic_model.yml):
--   fact_order_delivery   : one row per order_id
--   fact_production_order : one row per production_order_id

CREATE OR REPLACE VIEW stg_sales_orders AS
SELECT order_id, region, plant, warehouse, carrier, customer_id,
       CAST(order_date AS DATE)               AS order_date,
       CAST(promised_delivery_date AS DATE)    AS promised_delivery_date,
       CAST(NULLIF(promised_date_original,'') AS DATE) AS promised_date_original,
       order_status
FROM read_csv_auto('__DATA_DIR__/sales_orders_raw.csv', header=true, all_varchar=true);

-- Collapse deliveries to ORDER grain. This CTE is the whole ballgame:
-- max(delivery_date) because an order is delivered when its LAST leg lands.
CREATE OR REPLACE VIEW delivery_by_order AS
SELECT order_id,
       count(*)                                        AS delivery_count,
       max(CAST(NULLIF(delivery_date,'') AS DATE))      AS final_delivery_date,
       count(CASE WHEN delivery_date <> '' THEN 1 END)  AS delivered_legs
FROM read_csv_auto('__DATA_DIR__/deliveries_raw.csv', header=true, all_varchar=true)
GROUP BY order_id;

-- Inspection lots: FIRST vs FINAL usage decision.
-- first_pass_yield_pct uses decision_seq = 1 only (rework re-inspections excluded).
CREATE OR REPLACE VIEW inspection_by_prod_order AS
SELECT production_order_id,
       min(CASE WHEN decision_seq='1' THEN CAST(decision_date AS DATE) END) AS qm_first_decision_date,
       max(CAST(decision_date AS DATE))                                     AS qm_final_decision_date,
       max(CASE WHEN decision_seq='1' THEN usage_decision END)              AS first_usage_decision,
       count(*)                                                             AS decision_count
FROM read_csv_auto('__DATA_DIR__/inspection_lots_raw.csv', header=true, all_varchar=true)
GROUP BY production_order_id;
```

Then `fact_order_delivery` must implement, in order:

- **LEFT JOIN** orders → `delivery_by_order` → `stg_production_orders` → `inspection_by_prod_order`. Left joins throughout, so `SO-1015` (no production order) keeps a complete row.
- `is_delivered` = `final_delivery_date IS NOT NULL AND delivered_legs = delivery_count`
- `is_eligible` = `order_status <> 'CANC' AND promised_delivery_date <= DATE '__AS_OF_DATE__'`
  The token is replaced by `build_warehouse.py` from `constants.AS_OF_DATE`. Write the token,
  **not** the date — the literal lives in `constants.py` only.
- `is_on_time` = `is_eligible AND is_delivered AND final_delivery_date <= promised_delivery_date`
- `delay_days` = `date_diff('day', promised_delivery_date, final_delivery_date)`, NULL when not delivered
- Per-phase `var_*` columns: actual gap between consecutive phase dates minus the standard duration from `dim_process_phase`
- `available_slack_days` = `date_diff('day', order_date, promised_delivery_date) - 12`
  where 12 = Σ `standard_duration_days` for phases **1 through 11 only**. Billing (phase 12,
  1 day) is excluded because it happens after delivery confirmation and so cannot consume
  slack against the promised *delivery* date. All 12 phases sum to 13 — if you compute the
  constant from `dim_process_phase`, filter `phase_seq <= 11` and say so in a comment,
  otherwise the next reader will "correct" 12 to 13 and break every OTD number.
- `delay_attribution_phase`: a `CASE`/`greatest()` expression picking the phase name with the largest positive variance, evaluated only when `is_eligible AND NOT is_on_time AND is_delivered`; otherwise NULL. Ties break in phase order (earliest phase wins) — state this in a comment.

Also create `dim_process_phase` as a literal `VALUES` table with all 12 phases: `phase_seq, phase_key, phase_name, sap_module, business_event, timestamp_field, standard_duration_days`.

Create `src/build_warehouse.py`:

```python
"""Build the DuckDB warehouse from committed CSVs. Idempotent, offline."""
import duckdb
from src.semantic.constants import AS_OF_DATE, DATA_DIR, DB_PATH, SQL_DIR

def build(db_path=None):
    db_path = db_path or DB_PATH
    sql = (SQL_DIR / "02_staging_model.sql").read_text(encoding="utf-8")
    sql = sql.replace("__DATA_DIR__", DATA_DIR.as_posix())
    sql = sql.replace("__AS_OF_DATE__", AS_OF_DATE.isoformat())
    con = duckdb.connect(str(db_path))
    try:
        con.execute(sql)
    finally:
        con.close()

if __name__ == "__main__":
    build()
    print(f"Built warehouse at {DB_PATH}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_warehouse.py -v`
Expected: PASS (9 tests). `test_in_july_eligibility_and_ontime` returning anything but `(55, 48)` means the fact table is wrong — fix the SQL, never the assertion.

- [ ] **Step 5: Commit**

```bash
git add sql/02_staging_model.sql src/build_warehouse.py tests/test_warehouse.py
git commit -m "feat: build order-grain DuckDB warehouse with phase variance attribution"
```

---

## Task 4: Metadata artifacts — phases 0 through 4

**Files:**
- Create: `metadata/00_kpi_contract.md`, `metadata/01_technical_metadata.json`, `metadata/02_standardized_metadata.json`, `metadata/03_glossary.yml`, `metadata/03_column_bindings.yml`, `metadata/04_process_model.yml`
- Create: `tests/test_metadata.py`

**Interfaces:**
- Consumes: `constants.METADATA_DIR`.
- Produces: `03_glossary.yml` with top-level `terms:` — each entry has `term, definition, synonyms[], owner, steward, allowed_values (optional)`. `03_column_bindings.yml` with top-level `bindings:` — each has `term, table, column`. `04_process_model.yml` with `phases:` — 12 entries with `phase_seq, phase_key, phase_name, sap_module, business_event, timestamp_field, standard_duration_days`, plus `attribution:` describing the variance rule.

- [ ] **Step 1: Write the failing test**

Create `tests/test_metadata.py`:

```python
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
    build_warehouse.build(fresh=True)
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
    build_warehouse.build(fresh=True)
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_metadata.py -v`
Expected: FAIL on missing files.

- [ ] **Step 3: Write the artifacts**

Content requirements (spec §3.3, §6):

`00_kpi_contract.md` — the 12 NL questions the layer must answer (Q1 and Q2 first, verbatim from spec §3.2), metric owners, the business decision each KPI supports, and the acceptance test for "done".

`01_technical_metadata.json` — SAP DDIC-shaped extract. Must include real field names: `VBAK-VBELN`, `VBAK-KUNNR`, `VBAK-ERDAT`, `LIKP-WADAT_IST`, `AFKO-AUFNR`, `AFKO-GSTRP`, `AFKO-GLTRP`, `AFRU-BUDAT`, `QALS-VDATUM`, `MKPF-BUDAT`, `MSEG-BUDAT`, `VTTK-DPTBG`, `VBRK-FKDAT`. Per field: `table, field, data_element, domain, data_type, length, is_key, is_nullable, source_system, description`.

`02_standardized_metadata.json` — canonical name per source field, target table/column, declared grain per table, conformed dimensions.

`03_glossary.yml` — at minimum: `On-Time Delivery %`, `Manufacturing Schedule Adherence %`, `First Pass Yield %`, `Sales Order`, `Production Order`, `Inspection Lot`, `Region`, `Plant`, `Warehouse`, `Carrier`, `Promised Delivery Date`, `Delivery Date`, `Quality Inspection`. Every term needs `synonyms` (this is what makes NL resolution work — `Region` must map "India"/"india"/"IN", `On-Time Delivery %` must map "OTD"/"on time delivery"/"delivery performance"), `owner`, `steward`, and `allowed_values` for the dimensions.

`03_column_bindings.yml` — term → `fact_order_delivery` / `fact_production_order` column.

`04_process_model.yml` — the 12 phases from spec §3.3. Durations must match `dim_process_phase` in `sql/02_staging_model.sql` exactly (a test compares them row by row); phases 1–11 sum to 12, all 12 sum to 13: demand_capture 0, mrp_planning 1, production_release 1, material_staging 1, production_execution 3, quality_inspection 1, goods_receipt 1, picking_packing 1, goods_issue 0, transportation 3, delivery_confirmation 0, billing 1. Plus an `attribution:` block stating: variance = actual − standard; attributed phase = largest positive variance across phases 1–11; ties break to the earliest phase; evaluated only for late delivered eligible orders.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_metadata.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add metadata/ tests/test_metadata.py
git commit -m "feat: add metadata artifacts for phases 0-4 incl. 12-phase process model"
```

---

## Task 5: Semantic model with 3 governed metrics

**Files:**
- Create: `metadata/05_semantic_model.yml`
- Create: `src/semantic/loader.py`
- Create: `tests/test_loader.py`

**Interfaces:**
- Consumes: `constants.METADATA_DIR`.
- Produces:
  - `loader.load_semantic_model(path=None) -> SemanticModel`
  - `SemanticModel.get_metric(name: str) -> dict | None`
  - `SemanticModel.metric_names() -> list[str]`
  - `SemanticModel.approved_metric_names() -> list[str]`
  - `SemanticModel.get_dimension(metric_name: str, dim_name: str) -> dict | None`
  - `SemanticModel.dimensions_for(metric_name: str) -> list[str]`
  - `SemanticModel.get_entity(name: str) -> dict`
  - `loader.SemanticModelError` (raised on structural violations)
- YAML shape: top-level `entities:`, `dimensions:`, `metrics:`. Each metric: `name, label, description, entity, grain, expression{numerator, denominator, type}, exclusions[], business_rules[], time_dimension, owner, steward, approval_state, lineage[]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_loader.py`:

```python
import pytest
from src.semantic.loader import load_semantic_model, SemanticModelError

@pytest.fixture(scope="module")
def model():
    return load_semantic_model()

def test_three_metrics_defined(model):
    assert set(model.metric_names()) == {
        "on_time_delivery_pct", "mfg_schedule_adherence_pct", "first_pass_yield_pct"
    }

def test_all_mvp_metrics_approved(model):
    assert set(model.approved_metric_names()) == set(model.metric_names())

def test_otd_declares_grain_and_exclusions(model):
    m = model.get_metric("on_time_delivery_pct")
    assert m["grain"] == "order"
    assert m["entity"] == "fact_order_delivery"
    keys = {e["key"] for e in m["exclusions"]}
    assert {"cancelled_orders", "not_yet_due"} <= keys

def test_fpy_excludes_rework_reinspections(model):
    """The exclusion that prevents the 94.55% wrong answer."""
    m = model.get_metric("first_pass_yield_pct")
    assert m["grain"] == "production_order"
    keys = {e["key"] for e in m["exclusions"]}
    assert "rework_reinspections" in keys

def test_metrics_have_distinct_grains(model):
    grains = {model.get_metric(n)["grain"] for n in model.metric_names()}
    assert len(grains) >= 2, "a single-grain model cannot demonstrate fan-out"

def test_every_metric_has_owner_and_lineage(model):
    for name in model.metric_names():
        m = model.get_metric(name)
        assert m["owner"] and m["steward"]
        assert len(m["lineage"]) >= 3

def test_otd_dimensions_include_attribution(model):
    dims = model.dimensions_for("on_time_delivery_pct")
    for d in ("region", "plant", "warehouse", "carrier", "delay_attribution_phase"):
        assert d in dims

def test_joins_declare_cardinality(model):
    """Without declared cardinality the validator cannot detect fan-out."""
    ent = model.get_entity("fact_order_delivery")
    for join in ent.get("joins", []):
        assert join["cardinality"] in ("one_to_one", "one_to_many", "many_to_one")

def test_rejects_metric_with_unknown_entity(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        "entities:\n"
        "  - name: fact_a\n    grain: a\n"
        "dimensions: []\n"
        "metrics:\n"
        "  - name: m\n    entity: does_not_exist\n    grain: a\n"
        "    approval_state: approved\n",
        encoding="utf-8",
    )
    with pytest.raises(SemanticModelError, match="does_not_exist"):
        load_semantic_model(bad)

def test_rejects_metric_grain_not_matching_entity(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        "entities:\n"
        "  - name: fact_a\n    grain: order\n"
        "dimensions: []\n"
        "metrics:\n"
        "  - name: m\n    entity: fact_a\n    grain: delivery\n"
        "    approval_state: approved\n",
        encoding="utf-8",
    )
    with pytest.raises(SemanticModelError, match="grain"):
        load_semantic_model(bad)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_loader.py -v`
Expected: FAIL — no module `src.semantic.loader`.

- [ ] **Step 3: Write the semantic model and loader**

`metadata/05_semantic_model.yml` — the three metrics:

```yaml
# Phase 5 artifact: the governed semantic model.
# Tool-neutral. Portable to dbt MetricFlow, Cube, Unity Catalog, SAP Datasphere.
# This file is the single definition of every metric. BI and NL querying both read it,
# so the number cannot drift between a dashboard and a chat answer.

entities:
  - name: fact_order_delivery
    label: Order Delivery Fact
    grain: order
    primary_key: order_id
    description: One row per customer sales order, all delivery legs collapsed.
    joins:
      - to: fact_production_order
        cardinality: many_to_one
        on: production_order_id
        note: >
          Orders may have no production order (make-to-stock, e.g. SO-1015).
          LEFT JOIN required; an INNER JOIN silently drops eligible orders
          and inflates OTD.
      - to: raw_deliveries
        cardinality: one_to_many
        on: order_id
        note: >
          FAN-OUT HAZARD. 6 orders ship in two legs. Joining here without
          re-aggregating to order grain yields 88.52% instead of 87.27%.
          Never join this path for an order-grain metric.

metrics:
  - name: on_time_delivery_pct
    label: On-Time Delivery %
    description: >
      Share of eligible customer orders delivered on or before the promised
      delivery date. An order counts as delivered only when its final leg
      arrives.
    entity: fact_order_delivery
    grain: order
    time_dimension: promised_delivery_date
    expression:
      type: ratio_percent
      numerator: "sum(CASE WHEN is_on_time THEN 1 ELSE 0 END)"
      denominator: "sum(CASE WHEN is_eligible THEN 1 ELSE 0 END)"
    exclusions:
      - key: cancelled_orders
        predicate: "order_status <> 'CANC'"
        rationale: A cancelled order was never due; including it inflates the denominator.
      - key: not_yet_due
        predicate: "promised_delivery_date <= DATE '__AS_OF_DATE__'"
        rationale: >
          An order promised after the as-of date is not late, it is pending.
          Counting it as a miss understates performance.
    business_rules:
      - Measured against the CURRENT promised date, not the original. Re-promised
        orders (SO-1011) are judged on the commitment in force at delivery.
      - Order-grain only. Delivery-grain aggregation double-counts split shipments.
    owner: VP Supply Chain
    steward: Supply Chain Data Steward
    approval_state: approved
    lineage: ["SAP SD", "SAP EWM", "SAP TM", "fact_order_delivery"]
```

Also declare the second entity, `fact_production_order`:

```yaml
  - name: fact_production_order
    label: Production Order Fact
    grain: production_order
    primary_key: production_order_id
    description: One row per production order. Make-to-stock orders have none.
    joins:
      - to: fact_order_delivery
        cardinality: many_to_one
        on: order_id
        note: >
          REQUIRED, not optional. fact_production_order carries NO region and NO
          promised_delivery_date column, so both production metrics are unfilterable
          and unwindowable without this join. Verified non-fan-out against the built
          warehouse: 131 production orders over 131 distinct order_ids, zero orders
          with more than one production order. many_to_one, so the no_fanout gate
          must PERMIT it -- it is the counter-example to raw_deliveries.
```

Add `mfg_schedule_adherence_pct` and `first_pass_yield_pct`, both `entity: fact_production_order`, `grain: production_order`:

- `mfg_schedule_adherence_pct` — numerator `sum(CASE WHEN is_on_schedule THEN 1 ELSE 0 END)` (confirmed on or before `scheduled_finish_date`); exclusion `cancelled_production_orders` → `status <> 'CANC'`.
- `first_pass_yield_pct` — numerator `sum(CASE WHEN first_usage_decision = 'ACCEPT' THEN 1 ELSE 0 END)`; same cancelled exclusion plus `rework_reinspections`, documented as what prevents the 94.55% error. The rework collapse is already materialized as `first_usage_decision` / `decision_count` in the fact table, so this exclusion is satisfied by reading the first-decision column rather than by a WHERE predicate — say so in its `rationale`, and still give it a `predicate` (`decision_count >= 1`, i.e. the row is a production order not a decision row) so the `exclusions_applied` gate has something to record. Never resolve it to `qm_final_decision_date`.

**Both production metrics must declare `time_dimension: promised_delivery_date`, resolved through the join above — NOT `scheduled_finish_date`.** Verified against the built warehouse:

| Window column for IN / July | FPY | Adherence | |
|---|---|---|---|
| `promised_delivery_date` via the join (**correct**) | 51/54 | 50/54 | matches Task 7 and the canonical table |
| `scheduled_finish_date` on the fact itself | 42/45 | 42/45 | wrong denominator, fails Task 7 |

`scheduled_finish_date` is the intuitive choice and it is wrong: it asks "orders *scheduled* to finish in July", a different cohort from "orders *promised* to the customer in July". The `cancelled_production_orders` exclusion is load-bearing on the denominator too — without it the cohort is 55, not 54.

Declare `dimensions:` — `region`, `plant`, `warehouse`, `carrier`, `delay_attribution_phase`, `order_status`, plus `promised_delivery_date` as the time dimension — each with `column`, `entity`, and `allowed_values` where bounded. `region` and `promised_delivery_date` carry `entity: fact_order_delivery`, so for the two production metrics they resolve **through** the declared `many_to_one` join; the compiler emits that JOIN and the `no_fanout` gate permits it.

Also declare `delivery_id` as a dimension with `entity: raw_deliveries` and `reachable_via: raw_deliveries` (the `one_to_many` join). It exists **so the `no_fanout` gate has something to reject**: it is a legitimately declared dimension that an order-grain metric must refuse, which is what `test_gate_no_fanout_rejects_one_to_many_dimension` asserts. Without it, that gate is untestable and the fan-out protection is theatre. Mark it `queryable_at_grain: delivery` so the gate can distinguish "undeclared" from "declared but wrong grain".

`src/semantic/loader.py` — parse, then structurally validate:
1. Every metric's `entity` exists in `entities`.
2. Every metric's `grain` equals its entity's declared `grain`.
3. Every metric has non-empty `owner`, `steward`, `approval_state`, `lineage`.
4. `approval_state` ∈ {`approved`, `draft`, `deprecated`}.
5. Every dimension's `entity` exists.
6. Every join declares a valid `cardinality`.
Raise `SemanticModelError` with the offending name in the message. Return a `SemanticModel` dataclass exposing the accessors listed under Interfaces.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_loader.py -v`
Expected: PASS (10 tests).

- [ ] **Step 5: Commit**

```bash
git add metadata/05_semantic_model.yml src/semantic/loader.py tests/test_loader.py
git commit -m "feat: add semantic model with 3 governed metrics and loader validation"
```

---

## Task 6: QueryIntent schema and the 7-gate validator

**Files:**
- Create: `src/semantic/intent.py`
- Create: `src/semantic/validator.py`
- Create: `tests/test_validator.py`

**Interfaces:**
- Consumes: `loader.SemanticModel`, `constants.AS_OF_DATE`.
- Produces:
  - `intent.QueryIntent` (Pydantic BaseModel): `metric: str`, `dimensions: list[str] = []`, `filters: list[Filter] = []`, `grain: str`, `time_window: TimeWindow | None`, `intent_type: Literal["descriptive","diagnostic"]`, `comparison: TimeWindow | None`
  - `intent.Filter`: `column: str`, `operator: Literal["=","in","between",">=","<="]`, `value: str | list[str]`
  - `intent.TimeWindow`: `start: date`, `end: date`, `label: str`
  - `validator.validate(qi: QueryIntent, model: SemanticModel) -> ValidationResult`
  - `validator.ValidationResult`: `.ok: bool`, `.failures: list[GateFailure]`, `.gate_results: dict[str, bool]`
  - `validator.GateFailure`: `.gate: str`, `.message: str`
  - Gate names exactly: `metric_approved`, `dimensions_declared`, `filters_bound`, `grain_matches`, `no_fanout`, `time_window_bounded`, `exclusions_applied`

- [ ] **Step 1: Write the failing test**

Create `tests/test_validator.py`:

```python
from datetime import date
import pytest
from src.semantic.intent import QueryIntent, Filter, TimeWindow
from src.semantic.loader import load_semantic_model
from src.semantic.validator import validate

@pytest.fixture(scope="module")
def model():
    return load_semantic_model()

def _valid_intent(**over):
    base = dict(
        metric="on_time_delivery_pct",
        dimensions=[],
        filters=[Filter(column="region", operator="=", value="IN")],
        grain="order",
        time_window=TimeWindow(start=date(2026, 7, 1), end=date(2026, 7, 31),
                               label="July 2026"),
        intent_type="descriptive",
    )
    base.update(over)
    return QueryIntent(**base)

def test_valid_intent_passes_all_seven_gates(model):
    r = validate(_valid_intent(), model)
    assert r.ok, r.failures
    assert len(r.gate_results) == 7
    assert all(r.gate_results.values())

def test_gate_metric_approved_rejects_unknown_metric(model):
    r = validate(_valid_intent(metric="revenue_per_unicorn"), model)
    assert not r.ok
    assert "metric_approved" in {f.gate for f in r.failures}

def test_gate_dimensions_declared_rejects_undeclared(model):
    r = validate(_valid_intent(dimensions=["salesperson_shoe_size"]), model)
    assert not r.ok
    assert "dimensions_declared" in {f.gate for f in r.failures}

def test_gate_filters_bound_rejects_unknown_column(model):
    r = validate(_valid_intent(
        filters=[Filter(column="not_a_column", operator="=", value="X")]), model)
    assert not r.ok
    assert "filters_bound" in {f.gate for f in r.failures}

def test_gate_filters_bound_rejects_value_outside_allowed_set(model):
    """'MARS' is not a region. Catching this is why allowed_values exist."""
    r = validate(_valid_intent(
        filters=[Filter(column="region", operator="=", value="MARS")]), model)
    assert not r.ok
    assert "filters_bound" in {f.gate for f in r.failures}

def test_gate_grain_matches_rejects_wrong_grain(model):
    """The gate that prevents the 88.52% answer."""
    r = validate(_valid_intent(grain="delivery"), model)
    assert not r.ok
    assert "grain_matches" in {f.gate for f in r.failures}

def test_gate_no_fanout_rejects_one_to_many_dimension(model):
    """delivery_id is declared, but only reachable through a one_to_many join.
    It must fail no_fanout specifically -- not merely 'some gate failed'."""
    r = validate(_valid_intent(dimensions=["delivery_id"]), model)
    assert not r.ok
    assert "no_fanout" in {f.gate for f in r.failures}

def test_gate_time_window_bounded_rejects_missing_window(model):
    r = validate(_valid_intent(time_window=None), model)
    assert not r.ok
    assert "time_window_bounded" in {f.gate for f in r.failures}

def test_gate_time_window_bounded_rejects_inverted_range(model):
    r = validate(_valid_intent(time_window=TimeWindow(
        start=date(2026, 7, 31), end=date(2026, 7, 1), label="backwards")), model)
    assert not r.ok
    assert "time_window_bounded" in {f.gate for f in r.failures}

def test_failure_message_names_the_gate_and_the_problem(model):
    r = validate(_valid_intent(metric="nope"), model)
    f = next(f for f in r.failures if f.gate == "metric_approved")
    assert "nope" in f.message

def test_diagnostic_intent_with_attribution_dimension_passes(model):
    r = validate(_valid_intent(
        dimensions=["delay_attribution_phase"],
        intent_type="diagnostic",
        comparison=TimeWindow(start=date(2026, 6, 1), end=date(2026, 6, 30),
                              label="June 2026"),
    ), model)
    assert r.ok, r.failures

def test_validator_does_not_import_anthropic():
    """Structural guarantee: the gates never call an LLM."""
    import src.semantic.validator as v, inspect
    assert "anthropic" not in inspect.getsource(v)

# --- the many_to_one hop must be PERMITTED, not merely "some gate failed" ------
# fact_production_order carries no region and no promised_delivery_date, so both
# production metrics reach them through a declared many_to_one join. A no_fanout
# gate that blocks every join passes every test above while breaking 2 of 3 metrics.

def _prod_intent(metric, **over):
    base = dict(
        metric=metric, dimensions=[],
        filters=[Filter(column="region", operator="=", value="IN")],
        grain="production_order",
        time_window=TimeWindow(start=date(2026, 7, 1), end=date(2026, 7, 31),
                               label="July 2026"),
        intent_type="descriptive",
    )
    base.update(over)
    return QueryIntent(**base)

@pytest.mark.parametrize("metric",
                         ["first_pass_yield_pct", "mfg_schedule_adherence_pct"])
def test_production_metric_reaches_region_through_many_to_one(model, metric):
    """region lives on fact_order_delivery; the metric's entity is fact_production_order."""
    r = validate(_prod_intent(metric), model)
    assert r.ok, r.failures
    assert r.gate_results["no_fanout"] is True
    assert r.gate_results["filters_bound"] is True

@pytest.mark.parametrize("metric",
                         ["first_pass_yield_pct", "mfg_schedule_adherence_pct"])
def test_production_metric_can_group_by_a_joined_dimension(model, metric):
    r = validate(_prod_intent(metric, dimensions=["plant"]), model)
    assert r.ok, r.failures

def test_no_fanout_still_rejects_the_one_to_many_hop_for_production_metrics(model):
    """Permitting many_to_one must not have opened the one_to_many door."""
    r = validate(_prod_intent("first_pass_yield_pct",
                              dimensions=["delivery_id"]), model)
    assert not r.ok
    assert "no_fanout" in {f.gate for f in r.failures}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_validator.py -v`
Expected: FAIL — no module `src.semantic.intent`.

- [ ] **Step 3: Implement intent and validator**

`src/semantic/intent.py` — Pydantic models exactly as specified under Interfaces. Set `model_config = ConfigDict(extra="forbid")` so a hallucinated extra field is a parse error rather than silently ignored.

`src/semantic/validator.py` — implement each gate as a small named function returning `GateFailure | None`, then run all 7 and collect. Never raise on invalid input; always return a `ValidationResult`. Gate specifics:

1. `metric_approved` — metric exists **and** `approval_state == "approved"`. Report which of the two failed.
2. `dimensions_declared` — every requested dimension is declared **and reachable** from the metric's entity: either it sits on that entity directly, or it sits on an entity the metric's entity declares a join `to`. Reachability is mandatory, not a nicety — `region` is declared on `fact_order_delivery`, so the two production metrics (entity `fact_production_order`) reach it only through their declared `many_to_one` join. A gate that demands the dimension live on the metric's own entity rejects every legal production-metric query.
3. `filters_bound` — column resolves to a real declared dimension **by the same reachability rule as gate 2**, and if that dimension has `allowed_values`, the value is in it (case-insensitive). Applies to every element of a list value.
4. `grain_matches` — `qi.grain == metric["grain"]`.
5. `no_fanout` — reject a requested dimension only when reaching it traverses a join declared `one_to_many` (`delivery_id` via `raw_deliveries`). A `many_to_one` hop does **not** fan out and must PASS — that is how the production metrics reach `region`. Assert both directions; a gate that blocks every join is indistinguishable from one that blocks the dangerous join and silently breaks two of the three metrics.
6. `time_window_bounded` — window present, both dates concrete, `start <= end`.
7. `exclusions_applied` — every exclusion in the metric definition is non-empty and carries a `predicate`, so the compiler can apply it. (The compiler applies them unconditionally; this gate guarantees they exist to apply.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_validator.py -v`
Expected: PASS (17 tests — 12 gate tests plus the 5 many_to_one reachability cases).

- [ ] **Step 5: Commit**

```bash
git add src/semantic/intent.py src/semantic/validator.py tests/test_validator.py
git commit -m "feat: add QueryIntent schema and 7-gate validator"
```

---

## Task 7: Deterministic SQL compiler

**Files:**
- Create: `src/semantic/compiler.py`
- Create: `src/semantic/executor.py`
- Create: `tests/test_compiler.py`

**Interfaces:**
- Consumes: `QueryIntent`, `SemanticModel`.
- Produces:
  - `compiler.compile_sql(qi: QueryIntent, model: SemanticModel) -> CompiledQuery`
  - `compiler.CompiledQuery`: `.sql: str`, `.params: list`, `.applied_exclusions: list[str]`, `.grain: str`
  - `compiler.CompilerError`
  - `executor.run(cq: CompiledQuery, db_path=None) -> list[dict]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_compiler.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_compiler.py -v`
Expected: FAIL — no module `src.semantic.compiler`.

- [ ] **Step 3: Implement compiler and executor**

`src/semantic/compiler.py`:

```python
"""QueryIntent -> SQL. Deterministic, parameterized, no LLM.

This module is the reason the semantic layer is trustworthy: the model chooses
WHICH metric and filters, this code decides HOW the number is computed. The
arithmetic lives in 05_semantic_model.yml and nowhere else.
"""
```

Requirements:
- Raise `CompilerError` if the metric is absent or not `approved` (defence in depth — the validator should have caught it).
- Build `SELECT`, in order: the requested dimension columns, then `numerator`, `denominator`, and `value`.
- `value` must be `CASE WHEN denominator = 0 THEN NULL ELSE 100.0 * numerator / denominator END` — never a bare division. This is what makes the August window return NULL rather than crash.
- **Wrap both aggregates in `coalesce(..., 0)`.** Verified: the August window matches **zero rows** (all 4 IN/August orders are excluded by `not_yet_due`), and SQL `SUM()` over an empty set returns `NULL`, not `0`. `test_not_yet_due_returns_no_eligible_orders_not_zero` asserts `denominator == 0`, so without `coalesce` a fully correct compiler returns `None` and fails. Note this makes the `denominator = 0` branch above reachable — the two fixes are one behaviour: *no eligible orders* must read as an explicit zero denominator with a NULL value, which is a refusal to divide, not a 0%.
- Apply **every** exclusion predicate from the metric definition unconditionally; record their keys in `applied_exclusions`.
- Apply the time window on the metric's declared `time_dimension` via `BETWEEN ? AND ?`.
- **Emit the join when a filter, dimension, or the time dimension lives on another entity.** For the two production metrics that is `FROM fact_production_order p JOIN fact_order_delivery o ON p.order_id = o.order_id`, because `region` and `promised_delivery_date` exist only on `fact_order_delivery`. Qualify every column with its entity's alias, and derive the join from the entity's declared `joins:` — never hard-code it. Only emit joins actually needed by the intent, so the order-grain path stays single-table. Refuse (`CompilerError`) rather than emit a `one_to_many` join: the validator should have caught it, this is defence in depth.
- Every filter value goes into `params` as `?` — never string-interpolated. `in` renders `IN (?, ?, ...)`.
- When `dimensions` is non-empty, add `GROUP BY` and `ORDER BY` on those columns, plus a `late_count` column (`sum(CASE WHEN is_eligible AND NOT is_on_time THEN 1 ELSE 0 END)`) so the diagnostic breakdown works.
- Emit stable output: iterate dimensions and exclusions in declared order, never over a set.

`src/semantic/executor.py` — open DuckDB read-only, `con.execute(cq.sql, cq.params)`, return `list[dict]` zipping cursor description to values. Close in a `finally`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_compiler.py -v`
Expected: PASS (21 tests — 14 original plus the 7 production-metric windowing/join cases). Any canonical number mismatching means the compiler or fact table is wrong, not the assertion.

- [ ] **Step 5: Commit**

```bash
git add src/semantic/compiler.py src/semantic/executor.py tests/test_compiler.py
git commit -m "feat: add deterministic SQL compiler proving grain-correct vs naive answers"
```

---

## Task 8: Data-quality contract and trust badge

**Files:**
- Create: `metadata/06_dq_rules.yml`
- Create: `src/semantic/dq.py`
- Create: `tests/test_dq.py`

**Interfaces:**
- Consumes: DuckDB warehouse, `constants.METADATA_DIR`.
- Produces:
  - `dq.load_rules(path=None) -> list[dict]`
  - `dq.run_rules(metric_name: str | None = None, db_path=None) -> DQReport`
  - `dq.DQReport`: `.results: list[DQResult]`, `.badge: str` ∈ {`TRUSTED`,`DEGRADED`,`BLOCKED`}, `.failing_rules: list[str]`
  - `dq.DQResult`: `.rule_id`, `.dimension`, `.passed: bool`, `.observed: float`, `.threshold: float`, `.severity`, `.bound_to: list[str]`
- YAML: `rules:` — each with `rule_id, dimension, description, sql, threshold, comparison, severity (blocking|degrading), bound_to[], defect_demonstrated`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_dq.py`:

```python
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
```

Note: `run_rules` needs an optional `rules_path` parameter — add it to the signature: `run_rules(metric_name=None, db_path=None, rules_path=None)`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dq.py -v`
Expected: FAIL — no module `src.semantic.dq`.

- [ ] **Step 3: Write the rules and runner**

`metadata/06_dq_rules.yml` — six rules per spec §6.1. Each `sql` returns a single column `observed`; `comparison` is `lte` or `gte` against `threshold`. Requirements:
- **completeness** — null `final_delivery_date` rate among orders that are `is_eligible` and past due; threshold `lte 2.0`. Must be scoped so `SO-1013` doesn't trip it.
- **validity** — share of rows with `delivery_status` outside the allowed set or `plant` outside {1010, 1710}; threshold `lte 0.0`.
- **uniqueness** — count of `order_id` values with more than one fact row; threshold `lte 0.0`; `severity: blocking`.
- **timeliness** — hours since the warehouse's max `invoice_date` relative to `AS_OF_DATE`; threshold documented; this rule may legitimately be `degrading`.
- **consistency** — count of orders violating `prod_release_date <= gr_date <= goods_issue_date <= final_delivery_date` (ignoring NULLs); threshold `lte 0.0`.
- **accuracy** — recomputed IN/July OTD vs. the certified `87.2727`; absolute difference; threshold `lte 0.1`.

`defect_demonstrated` across the six rules must collectively name all 8 defect keys from the parametrized test.

`src/semantic/dq.py` — load rules, execute each `sql`, compare, build `DQReport`. Badge logic: any failing `blocking` rule → `BLOCKED`; else any failing `degrading` rule → `DEGRADED`; else `TRUSTED`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dq.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add metadata/06_dq_rules.yml src/semantic/dq.py tests/test_dq.py
git commit -m "feat: add data-quality contract with metric-bound rules and trust badge"
```

---

## Task 9: Catalog asset and provenance output

**Files:**
- Create: `metadata/07_catalog_asset.json`
- Create: `src/semantic/provenance.py`
- Create: `tests/test_provenance.py`

**Interfaces:**
- Consumes: `CompiledQuery`, executor rows, `DQReport`, `SemanticModel`, `metadata/07_catalog_asset.json`.
- Produces:
  - `provenance.build_answer(qi, cq, rows, model, dq_report) -> Answer`
  - `provenance.Answer`: `.headline: str`, `.value: float | None`, `.numerator: int`, `.denominator: int`, `.breakdown: list[dict]`, `.metric_definition: str`, `.lineage: list[str]`, `.exclusions_applied: list[str]`, `.trust_badge: str`, `.grain: str`
  - `Answer.render() -> str` (the printable block)

- [ ] **Step 1: Write the failing test**

Create `tests/test_provenance.py`:

```python
import json
from datetime import date
import pytest
from src import build_warehouse
from src.semantic.intent import QueryIntent, Filter, TimeWindow
from src.semantic.loader import load_semantic_model
from src.semantic.compiler import compile_sql
from src.semantic.executor import run
from src.semantic.dq import run_rules
from src.semantic.provenance import build_answer
from src.semantic.constants import METADATA_DIR

JULY = TimeWindow(start=date(2026, 7, 1), end=date(2026, 7, 31), label="July 2026")

@pytest.fixture(scope="module")
def model():
    build_warehouse.build()
    return load_semantic_model()

def _answer(model, dims=None, intent_type="descriptive"):
    qi = QueryIntent(
        metric="on_time_delivery_pct", dimensions=dims or [],
        filters=[Filter(column="region", operator="=", value="IN")],
        grain="order", time_window=JULY, intent_type=intent_type,
    )
    cq = compile_sql(qi, model)
    return build_answer(qi, cq, run(cq), model, run_rules("on_time_delivery_pct"))

def test_catalog_asset_is_valid_json_with_governance_fields():
    asset = json.loads((METADATA_DIR / "07_catalog_asset.json").read_text(encoding="utf-8"))
    for field in ("owner", "steward", "personal_data_category", "processing_purpose",
                  "legal_basis", "access_group", "retention_period",
                  "masking_policy", "certification_state", "lineage"):
        assert field in asset, f"missing governance field {field}"

def test_catalog_asset_states_enforcement_limits():
    """Spec: catalog metadata supports discovery, it does not enforce policy."""
    asset = json.loads((METADATA_DIR / "07_catalog_asset.json").read_text(encoding="utf-8"))
    note = json.dumps(asset).lower()
    assert "does not enforce" in note or "not a substitute" in note

def test_answer_carries_the_number_and_its_arithmetic(model):
    a = _answer(model)
    assert a.value == pytest.approx(87.2727, abs=0.0001)
    assert (a.numerator, a.denominator) == (48, 55)
    assert "87.3" in a.headline

def test_answer_carries_lineage(model):
    a = _answer(model)
    assert len(a.lineage) >= 3
    assert any("SAP" in s for s in a.lineage)

def test_answer_carries_exclusions_and_grain(model):
    a = _answer(model)
    assert set(a.exclusions_applied) >= {"cancelled_orders", "not_yet_due"}
    assert a.grain == "order"

def test_answer_carries_trust_badge(model):
    assert _answer(model).trust_badge == "TRUSTED"

def test_rendered_output_is_defensible_in_review(model):
    """Everything needed to defend the number must be in the rendered block."""
    text = _answer(model).render()
    for required in ("87.3", "48", "55", "order", "cancelled_orders",
                     "SAP", "TRUSTED", "on_time_delivery_pct"):
        assert required in text, f"rendered answer omits {required}"

def test_diagnostic_answer_includes_breakdown(model):
    a = _answer(model, dims=["delay_attribution_phase"], intent_type="diagnostic")
    phases = {r["delay_attribution_phase"] for r in a.breakdown}
    assert "quality_inspection" in phases
    assert "quality inspection" in a.render().lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_provenance.py -v`
Expected: FAIL — no module `src.semantic.provenance`.

- [ ] **Step 3: Write the artifact and provenance module**

`metadata/07_catalog_asset.json` — catalog/marketplace entry for `on_time_delivery_pct` and `fact_order_delivery`: all governance fields from the test, the full lineage chain `SAP SD → SAP PP → SAP QM → SAP MM/EWM → SAP TM → data lake → fact_order_delivery → semantic layer → dashboard`, related metrics, and a `governance_note` stating plainly that these fields support discovery and DPDP readiness work but **do not enforce** anything — enforcement lives in access control, consent management, retention automation, and masking.

`src/semantic/provenance.py` — assemble the `Answer`. `render()` must produce a block containing: the headline number, `numerator/denominator`, the metric name and its one-line definition, the declared grain, the applied exclusions, the lineage chain, and the trust badge. For diagnostic answers, add the per-phase breakdown sorted by late count descending, and name the top phase in prose. Round display values to one decimal; keep `.value` unrounded.

**`render()` must humanize phase keys.** The fact column holds `quality_inspection` (underscore) but the test asserts `"quality inspection" in a.render().lower()` (space) — and `"quality inspection" in "quality_inspection"` is `False`, so printing the raw value fails. Resolve the display label from `dim_process_phase.phase_name`, which already holds `Quality inspection` / `Transportation` / `Production execution`, rather than a blind `str.replace("_", " ")`: the dimension is the declared source of the label, and reading it keeps the display name from drifting from the model. The test lowercases, so casing is free. Keep the machine-readable key in `.breakdown` — only the rendered prose is humanized.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_provenance.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add metadata/07_catalog_asset.json src/semantic/provenance.py tests/test_provenance.py
git commit -m "feat: add catalog asset and provenance-carrying answer output"
```

---

## Task 10: Retriever and golden intents

**Files:**
- Create: `src/semantic/retriever.py`
- Create: `tests/golden_intents.json`
- Create: `tests/test_retriever.py`

**Interfaces:**
- Consumes: `SemanticModel`, `03_glossary.yml`, `04_process_model.yml`.
- Produces:
  - `retriever.build_context(question: str, model: SemanticModel) -> str` — the metadata slice for the resolver prompt
  - `retriever.load_golden_intents(path=None) -> dict[str, dict]` — keyed `Q1`, `Q2`; each has `question`, `intent`, `expected_value`
  - `retriever.golden_intent(qid: str) -> QueryIntent`

- [ ] **Step 1: Write the failing test**

Create `tests/test_retriever.py`:

```python
import pytest
from src.semantic.loader import load_semantic_model
from src.semantic.retriever import build_context, load_golden_intents, golden_intent
from src.semantic.intent import QueryIntent

@pytest.fixture(scope="module")
def model():
    return load_semantic_model()

def test_context_includes_metric_names_and_grains(model):
    ctx = build_context("on-time delivery for India warehouses last month", model)
    assert "on_time_delivery_pct" in ctx
    assert "order" in ctx

def test_context_includes_synonyms_so_model_can_map_vocabulary(model):
    ctx = build_context("what was OTD last month", model)
    assert "otd" in ctx.lower()

def test_context_includes_allowed_values_for_filters(model):
    ctx = build_context("india numbers", model)
    assert "IN" in ctx

def test_context_includes_as_of_date_for_relative_dates(model):
    """'last month' is unresolvable without a stated as-of date."""
    ctx = build_context("last month", model)
    assert "2026-08-07" in ctx

def test_context_includes_process_phases_for_diagnostic_queries(model):
    ctx = build_context("why did on-time delivery drop", model)
    assert "quality_inspection" in ctx

def test_golden_intents_cover_q1_and_q2():
    g = load_golden_intents()
    assert set(g) >= {"Q1", "Q2"}

def test_q1_golden_intent_parses_and_is_descriptive():
    qi = golden_intent("Q1")
    assert isinstance(qi, QueryIntent)
    assert qi.metric == "on_time_delivery_pct"
    assert qi.grain == "order"
    assert qi.intent_type == "descriptive"
    assert qi.time_window.start.isoformat() == "2026-07-01"
    assert qi.time_window.end.isoformat() == "2026-07-31"
    assert any(f.column == "region" and f.value == "IN" for f in qi.filters)

def test_q2_golden_intent_is_diagnostic_with_attribution():
    qi = golden_intent("Q2")
    assert qi.intent_type == "diagnostic"
    assert "delay_attribution_phase" in qi.dimensions
    assert qi.comparison is not None
    assert qi.comparison.start.isoformat() == "2026-06-01"

def test_golden_intents_pass_the_validator():
    from src.semantic.validator import validate
    model = load_semantic_model()
    for qid in ("Q1", "Q2"):
        r = validate(golden_intent(qid), model)
        assert r.ok, f"{qid} fails gates: {r.failures}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_retriever.py -v`
Expected: FAIL — no module `src.semantic.retriever`.

- [ ] **Step 3: Implement retriever and author golden intents**

`tests/golden_intents.json`:

```json
{
  "Q1": {
    "question": "On-time delivery for India warehouses last month",
    "expected_value": 87.2727,
    "intent": {
      "metric": "on_time_delivery_pct",
      "dimensions": [],
      "filters": [{"column": "region", "operator": "=", "value": "IN"}],
      "grain": "order",
      "time_window": {"start": "2026-07-01", "end": "2026-07-31", "label": "July 2026"},
      "intent_type": "descriptive",
      "comparison": null
    }
  },
  "Q2": {
    "question": "Why did on-time delivery drop for India warehouses last month?",
    "expected_value": 87.2727,
    "intent": {
      "metric": "on_time_delivery_pct",
      "dimensions": ["delay_attribution_phase"],
      "filters": [{"column": "region", "operator": "=", "value": "IN"}],
      "grain": "order",
      "time_window": {"start": "2026-07-01", "end": "2026-07-31", "label": "July 2026"},
      "intent_type": "diagnostic",
      "comparison": {"start": "2026-06-01", "end": "2026-06-30", "label": "June 2026"}
    }
  }
}
```

`src/semantic/retriever.py` — `build_context` renders a compact text block from the metadata: available approved metrics with grain, time dimension and one-line definition; declared dimensions with allowed values; glossary terms with synonyms; the 12 process phases (keys only, for attribution); and the literal `AS_OF_DATE` so relative dates resolve. Keep it stable and ordered — this string is the cacheable prompt prefix. `load_golden_intents` reads the JSON; `golden_intent` returns a parsed `QueryIntent`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_retriever.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add src/semantic/retriever.py tests/golden_intents.json tests/test_retriever.py
git commit -m "feat: add metadata retriever and golden intents for offline operation"
```

---

## Task 11: CLI and end-to-end verification

**Files:**
- Create: `src/ask.py`
- Create: `tests/test_end_to_end.py`
- Create: `requirements.txt`

**Interfaces:**
- Consumes: everything from Tasks 3–10.
- Produces: `ask.answer_offline(qid: str) -> Answer`; `ask.main(argv=None) -> int`. CLI: `python src/ask.py --offline Q1`, `python src/ask.py "question"`, `python src/ask.py --list`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_end_to_end.py`:

```python
import subprocess, sys, os, csv, re
import pytest
from src import build_warehouse
from src.semantic.constants import REPO_ROOT, DATA_DIR

@pytest.fixture(scope="module", autouse=True)
def warehouse():
    build_warehouse.build()

def _run_cli(*args):
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)          # prove no key is needed
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    env["PYTHONPATH"] = str(REPO_ROOT)
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "src" / "ask.py"), *args],
        capture_output=True, text=True, cwd=REPO_ROOT, env=env,
    )

def test_q1_via_cli_without_api_key():
    """Acceptance criterion 2."""
    p = _run_cli("--offline", "Q1")
    assert p.returncode == 0, p.stderr
    out = p.stdout
    assert "87.3" in out
    assert "48" in out and "55" in out
    assert "TRUSTED" in out
    assert "SAP" in out

def test_q2_via_cli_without_api_key():
    """Acceptance criterion 3: attribution and the 8.9pp drop."""
    p = _run_cli("--offline", "Q2")
    assert p.returncode == 0, p.stderr
    out = p.stdout
    assert "87.3" in out
    assert "96.2" in out
    assert "8.9" in out
    # The attribution breakdown, with counts tied to their phases.
    assert re.search(r"quality[_ ]inspection\D{0,20}4", out, re.I), out
    assert re.search(r"transportation\D{0,20}2", out, re.I), out
    assert re.search(r"production[_ ]execution\D{0,20}1", out, re.I), out

def test_cli_lists_available_questions():
    p = _run_cli("--list")
    assert p.returncode == 0
    assert "Q1" in p.stdout and "Q2" in p.stdout

def test_cli_fails_gracefully_on_unknown_id():
    p = _run_cli("--offline", "Q99")
    assert p.returncode != 0
    assert "Q99" in (p.stdout + p.stderr)

def test_derived_attribution_matches_hand_authored_oracle():
    """The pipeline's answer must match the CSV's expected_attribution_phase
    column, which it never reads."""
    from src.semantic.loader import load_semantic_model
    from src.semantic.compiler import compile_sql
    from src.semantic.executor import run
    from src.semantic.retriever import golden_intent
    rows = run(compile_sql(golden_intent("Q2"), load_semantic_model()))
    derived = {r["delay_attribution_phase"]: r["late_count"]
               for r in rows if r["delay_attribution_phase"]}
    with open(DATA_DIR / "seed_core.csv", newline="") as f:
        from collections import Counter
        # The oracle column is populated for IN-July orders only -- that is the
        # window Q2 asks about. Rows outside it carry an empty value and are
        # skipped by the truthiness filter.
        oracle = Counter(r["expected_attribution_phase"] for r in csv.DictReader(f)
                         if r["expected_attribution_phase"])
    assert derived == dict(oracle)
    assert dict(oracle) == {"quality_inspection": 4, "transportation": 2,
                            "production_execution": 1}

def test_full_suite_passes_without_api_key():
    """Acceptance criterion 4."""
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    env["PYTHONPATH"] = str(REPO_ROOT)
    p = subprocess.run(
        [sys.executable, "-m", "pytest", "-q",
         "--ignore=tests/test_end_to_end.py"],   # avoid recursion
        capture_output=True, text=True, cwd=REPO_ROOT, env=env,
    )
    assert p.returncode == 0, p.stdout[-4000:]

def test_no_module_outside_resolver_imports_anthropic():
    """Structural guarantee that the pipeline is LLM-free."""
    import pathlib
    sem = REPO_ROOT / "src" / "semantic"
    for path in list(sem.glob("*.py")) + [REPO_ROOT / "src" / "build_warehouse.py"]:
        if path.name == "resolver.py":
            continue
        assert "anthropic" not in path.read_text(encoding="utf-8"), \
            f"{path.name} imports anthropic"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_end_to_end.py -v`
Expected: FAIL — `src/ask.py` does not exist.

- [ ] **Step 3: Write the CLI**

Create `requirements.txt`:

```
duckdb>=1.5.2
pyyaml>=6.0
pydantic>=2.0
pytest>=8.0
anthropic>=0.100.0
```

Create `src/ask.py`:

```python
"""CLI entry point.

  python src/ask.py --offline Q1     # no API key needed
  python src/ask.py --list
  python src/ask.py "on-time delivery for India warehouses last month"
"""
```

Requirements:
- `--offline QID`: load the golden intent → validate → compile → execute → run DQ → build answer → print `render()`. For `intent_type == "diagnostic"` with a `comparison` window, also compile and execute the comparison window and include both values plus the delta in the output.
- Bare question string: import `resolver` **lazily inside the function** so a missing/failing `anthropic` import never breaks offline mode. On any auth failure, print a clear message pointing at `ant auth status` and `--offline`, and return non-zero.
- `--list`: print each golden intent's ID and question.
- If validation fails, print the failed gate names and the reason, and return non-zero. Never print a number that failed a gate.
- If the DQ badge is `BLOCKED`, print a refusal with the failing rule instead of the number.
- Build the warehouse automatically if `DB_PATH` is missing.

- [ ] **Step 4: Run tests and both demo commands**

Run:
```bash
python src/build_warehouse.py
python src/ask.py --offline Q1
python src/ask.py --offline Q2
python -m pytest -q
```
Expected: Q1 prints 87.3% (48/55) with lineage and `TRUSTED`; Q2 prints 87.3% vs 96.2%, −8.9pp, quality inspection 4; full suite green.

- [ ] **Step 5: Commit**

```bash
git add src/ask.py requirements.txt tests/test_end_to_end.py
git commit -m "feat: add CLI answering Q1 and Q2 offline with full provenance"
```

---

## Task 12: Claude API resolver

**Files:**
- Create: `src/semantic/resolver.py`
- Create: `tests/test_resolver_live.py`

**Interfaces:**
- Consumes: `retriever.build_context`, `intent.QueryIntent`.
- Produces: `resolver.resolve(question: str, model: SemanticModel) -> QueryIntent`; `resolver.ResolverError`; `resolver.SYSTEM_PROMPT: str`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_resolver_live.py`:

```python
import os, inspect
import pytest

def _has_creds():
    return bool(os.environ.get("ANTHROPIC_API_KEY") or
                os.environ.get("ANTHROPIC_AUTH_TOKEN"))

live = pytest.mark.skipif(not _has_creds(),
                          reason="no Anthropic credentials configured")

# ---- these run WITHOUT credentials: they inspect the code, not the API ----

def test_resolver_module_imports_without_credentials():
    import src.semantic.resolver as r
    assert hasattr(r, "resolve")

def test_resolver_uses_correct_model_id():
    import src.semantic.resolver as r
    src = inspect.getsource(r)
    assert "claude-opus-5" in src

def test_resolver_uses_adaptive_thinking():
    import src.semantic.resolver as r
    src = inspect.getsource(r)
    assert '"adaptive"' in src or "'adaptive'" in src

def test_resolver_never_sends_forbidden_params():
    """temperature/top_p/top_k/budget_tokens all return HTTP 400 on Opus 5."""
    import src.semantic.resolver as r
    src = inspect.getsource(r)
    for forbidden in ("temperature", "top_p", "top_k", "budget_tokens"):
        assert forbidden not in src, f"resolver passes forbidden param {forbidden}"

def test_resolver_checks_refusal_stop_reason():
    import src.semantic.resolver as r
    assert "refusal" in inspect.getsource(r)

def test_resolver_uses_zero_arg_constructor():
    """Lets the SDK pick up whatever auth is configured."""
    import src.semantic.resolver as r
    assert "Anthropic()" in inspect.getsource(r)

def test_system_prompt_forbids_sql_generation():
    from src.semantic.resolver import SYSTEM_PROMPT
    low = SYSTEM_PROMPT.lower()
    assert "sql" in low
    assert "do not" in low or "never" in low

# ---- these need credentials ----

@live
def test_resolves_q1_to_the_golden_intent():
    from src.semantic.loader import load_semantic_model
    from src.semantic.resolver import resolve
    from src.semantic.retriever import golden_intent
    got = resolve("On-time delivery for India warehouses last month", load_semantic_model())
    want = golden_intent("Q1")
    assert got.metric == want.metric
    assert got.grain == want.grain
    assert got.time_window.start == want.time_window.start
    assert got.time_window.end == want.time_window.end
    assert {(f.column, str(f.value)) for f in got.filters} == \
           {(f.column, str(f.value)) for f in want.filters}

@live
def test_resolves_q2_as_diagnostic():
    from src.semantic.loader import load_semantic_model
    from src.semantic.resolver import resolve
    got = resolve("Why did on-time delivery drop for India warehouses last month?",
                  load_semantic_model())
    assert got.intent_type == "diagnostic"
    assert "delay_attribution_phase" in got.dimensions

@live
def test_resolved_intent_passes_the_validator():
    from src.semantic.loader import load_semantic_model
    from src.semantic.resolver import resolve
    from src.semantic.validator import validate
    model = load_semantic_model()
    r = validate(resolve("what was OTD in India in July 2026", model), model)
    assert r.ok, r.failures
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_resolver_live.py -v`
Expected: FAIL — no module `src.semantic.resolver`. (The `@live` tests will SKIP.)

- [ ] **Step 3: Write the resolver**

Create `src/semantic/resolver.py`:

```python
"""NL question -> validated QueryIntent via the Claude API.

The ONLY module in this project that talks to an LLM, and the only one that
needs credentials. It chooses WHICH governed metric and filters a question
means. It never writes SQL and never computes a number -- compiler.py does
that deterministically from 05_semantic_model.yml.
"""
import anthropic
from src.semantic.constants import AS_OF_DATE
from src.semantic.intent import QueryIntent
from src.semantic.retriever import build_context

MODEL = "claude-opus-5"

SYSTEM_PROMPT = """\
You map natural-language analytics questions onto a governed semantic model.

You do NOT write SQL. You do NOT compute numbers. You do NOT invent metrics,
dimensions, or arithmetic. Your only job is to select which of the governed
metrics, dimensions, and filters below the question refers to, and to resolve
relative dates against the stated as-of date.

Rules:
- Use only metric names, dimension names, and filter values listed in the
  semantic metadata provided. If the question cannot be answered with them,
  still return your closest attempt -- a downstream validator will reject it
  and explain why. Never substitute a metric you were not given.
- grain must be the declared grain of the metric you select.
- Resolve relative dates ("last month", "Q2") against the as-of date given.
- intent_type is "diagnostic" when the question asks why something changed,
  or asks for a cause or breakdown; otherwise "descriptive".
- For diagnostic questions about lateness, include "delay_attribution_phase"
  in dimensions, and set comparison to the preceding period.
"""
```

Implementation requirements:
- `client = anthropic.Anthropic()` — zero-arg, so it picks up `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, or an `ant auth login` profile.
- Call `client.messages.parse(model=MODEL, max_tokens=16000, thinking={"type": "adaptive"}, output_config={"effort": "medium"}, system=[...], messages=[...], output_format=QueryIntent)`.
- Put the retriever context in the **system** block with `cache_control: {"type": "ephemeral"}` on the last system block; keep the volatile question in the user turn. Render order is `tools` → `system` → `messages`.
- Check `response.stop_reason == "refusal"` **before** touching `.content`; raise `ResolverError` if so.
- Never pass `temperature`, `top_p`, `top_k`, or `budget_tokens`.
- Catch exceptions most-specific-first (`anthropic.BadRequestError`, `anthropic.AuthenticationError`, `anthropic.RateLimitError`, `anthropic.APIStatusError`, `anthropic.APIConnectionError`) and re-raise as `ResolverError` with an actionable message.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_resolver_live.py -v`
Expected: 7 code-inspection tests PASS; 3 `@live` tests SKIP with "no Anthropic credentials configured".

- [ ] **Step 5: Commit**

```bash
git add src/semantic/resolver.py tests/test_resolver_live.py
git commit -m "feat: add Claude API resolver mapping NL to validated QueryIntent"
```

---

## Task 12.5: Metadata → NL dataflow swimlane diagram

**Files:**
- Create: `docs/diagrams/render_dataflow.py`
- Create: `docs/diagrams/nl_dataflow.svg` (committed output)
- Create: `docs/diagrams/nl_dataflow.png` (committed output)
- Create: `tests/test_diagram.py`

**Interfaces:**
- Consumes: the real modules in `src/semantic/`, the 8 artifacts in `metadata/`.
- Produces: `render_dataflow.py --check` (verify committed output is current, exit non-zero on drift) and `--write` (regenerate).

**Why this task exists:** the reader's question is "how do the metadata phases actually get used to answer a natural-language question?". The phase table answers *what each artifact is*; nothing yet answers *which artifact each pipeline stage reads*. This is the diagram the guide's §5 needs.

**Renderer choice:** matplotlib (confirmed present, 3.10.9). `graphviz` the Python package is **not** installed and the `dot` binary is **not on PATH** — do not use either, and do not add a dependency to make a picture. Pure matplotlib patches + annotations, no seaborn, no styles, no network.

- [ ] **Step 1: Write the failing test**

Create `tests/test_diagram.py`:

```python
"""The diagram is documentation, so it can drift from the code. These tests
make the drift fail loudly rather than mislead a reader.

The load-bearing test is test_every_declared_edge_is_real: it reads the edge list
out of the renderer and greps the actual module source for the artifact filename,
so an edge the code does not have cannot survive in the picture.
"""
import subprocess, sys
import pytest
from src.semantic.constants import REPO_ROOT

DIAGRAM_DIR = REPO_ROOT / "docs" / "diagrams"

def test_committed_output_exists_and_is_nonempty():
    for name in ("nl_dataflow.svg", "nl_dataflow.png"):
        p = DIAGRAM_DIR / name
        assert p.exists(), f"missing {name}"
        assert p.stat().st_size > 5000, f"{name} looks truncated"

def test_renderer_check_mode_says_committed_output_is_current():
    """--check must fail if someone edits the renderer and forgets to regenerate."""
    p = subprocess.run(
        [sys.executable, str(DIAGRAM_DIR / "render_dataflow.py"), "--check"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert p.returncode == 0, f"committed diagram is stale, run --write:\n{p.stdout}{p.stderr}"

def test_all_six_pipeline_stages_are_lanes():
    from docs.diagrams.render_dataflow import STAGES
    keys = [s["key"] for s in STAGES]
    assert keys == ["retriever", "resolver", "validator",
                    "compiler", "executor", "provenance"]

def test_all_nine_artifacts_appear():
    """All 8 phases P0-P7, which is 9 files (phase 3 emits two)."""
    from docs.diagrams.render_dataflow import ARTIFACTS
    assert {a["file"] for a in ARTIFACTS} == {
        "00_kpi_contract.md", "01_technical_metadata.json",
        "02_standardized_metadata.json", "03_glossary.yml",
        "03_column_bindings.yml", "04_process_model.yml",
        "05_semantic_model.yml", "06_dq_rules.yml", "07_catalog_asset.json",
    }

def test_every_artifact_file_actually_exists():
    from docs.diagrams.render_dataflow import ARTIFACTS
    from src.semantic.constants import METADATA_DIR
    for a in ARTIFACTS:
        assert (METADATA_DIR / a["file"]).exists(), f"{a['file']} does not exist"

def test_every_declared_edge_is_real():
    """An arrow from artifact X to stage Y must correspond to Y's code reading X.

    This is what stops the diagram becoming a pretty lie. Build-time artifacts are
    exempt: they feed sql/ and the generator, not a query-time module.
    """
    from docs.diagrams.render_dataflow import EDGES, STAGE_MODULE
    for e in EDGES:
        if e.get("phase") == "build":
            continue
        module = STAGE_MODULE[e["stage"]]
        src = (REPO_ROOT / module).read_text(encoding="utf-8")
        stem = e["file"].split(".")[0]
        assert stem in src or e["file"] in src, (
            f"diagram claims {module} reads {e['file']}, but its source never "
            f"names it. Either the edge is wrong or the module changed."
        )

def test_no_edge_claims_the_compiler_reads_the_glossary():
    """Architectural invariant: vocabulary resolution happens BEFORE the gates.

    If the compiler read the glossary, synonym choice would influence arithmetic,
    which is exactly the coupling this architecture exists to prevent.
    """
    from docs.diagrams.render_dataflow import EDGES
    bad = [e for e in EDGES
           if e["stage"] == "compiler" and e["file"].startswith("03_")]
    assert bad == [], f"compiler must not depend on vocabulary: {bad}"

def test_resolver_is_the_only_llm_lane():
    from docs.diagrams.render_dataflow import STAGES
    llm = [s["key"] for s in STAGES if s.get("llm")]
    assert llm == ["resolver"]

def test_diagram_is_deterministic(tmp_path):
    """Same input, same bytes -- so the committed SVG diffs cleanly."""
    from docs.diagrams.render_dataflow import render_svg
    a = render_svg()
    b = render_svg()
    assert a == b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_diagram.py -v`
Expected: FAIL — no module `docs.diagrams.render_dataflow`.

Note: `docs/diagrams/` needs an `__init__.py` (and `docs/__init__.py`) for the import to resolve, since `pythonpath = .` is already set in `pytest.ini`.

- [ ] **Step 3: Write the renderer**

`docs/diagrams/render_dataflow.py` — declare the graph as data first, then draw it:

- `STAGES` — the 6 query-time lanes in order, each `{key, label, num, llm: bool}`. Only `resolver` has `llm: True`.
- `STAGE_MODULE` — `{stage_key: "src/semantic/<module>.py"}`, used by the drift test.
- `ARTIFACTS` — the 9 metadata files with their phase number and one-line role.
- `EDGES` — `{file, stage, label, phase}`. `label` is *what* is consumed, which is the whole point of the diagram. The accurate set, per the plan's own task definitions:

| Artifact | Stage | What it supplies |
|---|---|---|
| `03_glossary.yml` | retriever | synonyms → vocabulary match ("OTD", "India") |
| `04_process_model.yml` | retriever | phase keys, so diagnostic questions can name a cause |
| `05_semantic_model.yml` | retriever | approved metric names, grain, time dimension |
| `05_semantic_model.yml` | validator | `approval_state`, declared dims, join cardinality → gates 1,2,4,5 |
| `03_glossary.yml` | validator | `allowed_values` → gate 3 (rejects "MARS") |
| `05_semantic_model.yml` | compiler | numerator/denominator, exclusion predicates, the join |
| `06_dq_rules.yml` | provenance | rule results → trust badge |
| `07_catalog_asset.json` | provenance | owner, lineage chain, governance fields |
| `00_kpi_contract.md` | — | `phase: "contract"`, the acceptance oracle; draw as a framing band, not an arrow into a stage |
| `01_technical_metadata.json` | — | `phase: "build"`, feeds `sql/02_staging_model.sql` |
| `02_standardized_metadata.json` | — | `phase: "build"`, grain declaration → the warehouse |
| `03_column_bindings.yml` | retriever | term → physical column |

- Layout: artifacts as a left column grouped by phase, the 6 stages as a horizontal pipeline band, arrows from artifact to the stage that reads it. Put the build-time artifacts in a visually separate band feeding the warehouse box, so a reader sees that P1/P2 are consumed *before* query time — that distinction is the thing most such diagrams get wrong.
- Annotate the architectural rule on the figure itself: *the resolver picks which metric; the compiler owns all arithmetic.* Mark the resolver lane as the only LLM step, and mark the validator→refusal path.
- `render_svg() -> str` and `render_png() -> bytes`. **Determinism:** set `matplotlib.use("Agg")`, `mpl.rcParams["svg.hashsalt"] = "semantic-layer-nl"`, and `metadata={"Date": None}` on `savefig` — without these the SVG embeds a timestamp and random element ids, so the committed file would differ on every run and `--check` would always fail.
- `--check` compares freshly rendered bytes to the committed files and exits 1 with a diff summary; `--write` regenerates both.
- No wall-clock, no network, no `Date.now`-equivalent. Consistent with the project's determinism rule.

- [ ] **Step 4: Run test and regenerate**

```bash
python docs/diagrams/render_dataflow.py --write
python -m pytest tests/test_diagram.py -v
python docs/diagrams/render_dataflow.py --check
```
Expected: PASS (9 tests); `--check` exits 0.

Then **look at the PNG** and confirm it is readable: no overlapping labels, no clipped text, arrows visibly land on their target lane. A diagram that passes its tests and is illegible has failed. Report what you saw.

- [ ] **Step 5: Commit**

```bash
git add docs/__init__.py docs/diagrams/ tests/test_diagram.py
git commit -m "docs: add verified metadata-to-NL dataflow swimlane diagram"
```

---

## Task 13: The guide

**Files:**
- Create: `README.md`
- Create: `appendix/portability.md`
- Create: `tests/test_guide.py`

**Interfaces:**
- Consumes: every artifact and module built above.
- Produces: the reader-facing guide.

- [ ] **Step 1: Write the failing test**

Create `tests/test_guide.py`:

```python
import re
import pytest
from src.semantic.constants import REPO_ROOT

def _readme():
    return (REPO_ROOT / "README.md").read_text(encoding="utf-8")

def test_readme_exists_and_is_substantial():
    assert len(_readme()) > 8000

def test_no_placeholders_in_guide():
    text = _readme()
    for bad in ("TBD", "TODO", "FIXME", "XXX", "Lorem ipsum", "<placeholder>"):
        assert bad not in text, f"guide contains {bad}"

@pytest.mark.parametrize("phase", [
    "Phase 0", "Phase 1", "Phase 2", "Phase 3",
    "Phase 4", "Phase 5", "Phase 6", "Phase 7",
])
def test_every_phase_has_a_section(phase):
    assert phase in _readme()

@pytest.mark.parametrize("artifact", [
    "00_kpi_contract.md", "01_technical_metadata.json", "02_standardized_metadata.json",
    "03_glossary.yml", "03_column_bindings.yml", "04_process_model.yml",
    "05_semantic_model.yml", "06_dq_rules.yml", "07_catalog_asset.json",
])
def test_every_artifact_is_named_in_the_guide(artifact):
    assert artifact in _readme()

def test_every_phase_names_the_nl_failure_it_closes():
    """Acceptance criterion 10."""
    text = _readme().lower()
    assert text.count("nl failure closed") >= 8

def test_guide_quotes_the_canonical_numbers():
    text = _readme()
    for n in ("87.3", "96.2", "8.9", "88.5", "94.4", "92.6"):
        assert n in text, f"guide omits canonical figure {n}"
    # 48 and 55 must appear as the ratio, not as incidental digits anywhere.
    assert re.search(r"48\s*(/|of|out of)\s*55", text, re.I), \
        "guide must show the 48/55 arithmetic behind 87.3%"

def test_guide_shows_the_wrong_answer_first():
    text = _readme()
    assert "88.5" in text
    assert re.search(r"overstat|flatter|too high", text, re.I)

def test_guide_covers_manufacturing_phases():
    text = _readme()
    for phase in ("production", "quality inspection", "goods receipt", "material"):
        assert phase.lower() in text.lower()
    for module in ("SAP PP", "SAP QM", "SAP MM"):
        assert module in text

def test_guide_states_governance_limits_in_body_not_appendix():
    """Acceptance criterion 11."""
    text = _readme()
    idx = text.lower().find("does not enforce")
    if idx == -1:
        idx = text.lower().find("not a substitute")
    assert idx != -1, "guide never states the governance limit"
    assert idx < len(text) * 0.9, "governance limit is buried at the very end"

def test_guide_documents_offline_operation():
    text = _readme()
    assert "--offline" in text
    assert "ANTHROPIC_API_KEY" in text

def test_guide_documents_deferred_scope():
    """Spec 10.2: be honest about what the MVP does not include."""
    text = _readme().lower()
    assert "production_cycle_time_days" in text or "deferred" in text

def test_portability_appendix_covers_target_tools():
    text = (REPO_ROOT / "appendix" / "portability.md").read_text(encoding="utf-8")
    for tool in ("MetricFlow", "Cube", "Unity Catalog", "Datasphere"):
        assert tool in text

def test_guide_embeds_the_dataflow_diagram():
    """The 'how does metadata answer a question' picture must be in the guide,
    not only in docs/diagrams/."""
    text = _readme()
    assert "nl_dataflow" in text, "guide does not embed the dataflow diagram"
    assert "![" in text, "diagram must be embedded as an image, not just linked"

def test_guide_explains_which_stage_reads_which_artifact():
    """The diagram needs prose beside it naming at least the load-bearing edges."""
    text = _readme()
    for pair in ("03_glossary.yml", "05_semantic_model.yml", "06_dq_rules.yml"):
        assert pair in text
    assert re.search(r"retriev\w+", text, re.I)
    assert re.search(r"valid\w+", text, re.I)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_guide.py -v`
Expected: FAIL — no `README.md`.

- [ ] **Step 3: Write the guide**

`README.md` structure (spec §7.1):

1. **The problem** — open with the two NL questions and the wrong answers. Show 88.52% and explain that it is *higher* than the truth and only 1.25pp off, so it survives review. This is the hook: grain errors flatter, they don't scream.
2. **Quickstart** — `pip install -r requirements.txt`, `python src/build_warehouse.py`, `python src/ask.py --offline Q1`, `--offline Q2`, `pytest`. State plainly that no API key is needed.
3. **The domain** — SAP Plan-to-Deliver, the 12 process phases table with SAP modules and standard durations, and why manufacturing phases are what make "why" answerable.
4. **Phases 0–7**, one section each: INPUT → WORK → OUTPUT (the real artifact, excerpted) → GATE → **NL FAILURE CLOSED** (that exact heading, 8 times — the test counts them).
5. **The NL resolution path** — retriever → resolver → 7 gates → compiler → executor → provenance, with the architectural rule stated once and prominently: *the model picks which metric; it never writes arithmetic.* **Embed the Task 12.5 swimlane here** (`![Metadata to NL dataflow](docs/diagrams/nl_dataflow.svg)`) and walk the reader through it edge by edge: which artifact each stage reads and what it supplies. State explicitly that P1/P2 are consumed at *build* time and P3–P7 at *query* time — that is the distinction the picture exists to make. Also state which gate each artifact backs, so a reader can trace a refusal to the file that caused it.
6. **What this does not do** — governance metadata supports discovery and DPDP readiness but **does not enforce** anything; single fact table; synthetic data; deferred items from spec §10.2 including `production_cycle_time_days`.
7. **Appendix pointer.**

`appendix/portability.md` — table mapping each `05_semantic_model.yml` concept (entity, dimension, metric, grain, exclusion, join cardinality) to dbt MetricFlow, Cube, Databricks Unity Catalog, Atlan, Collibra, and SAP Datasphere equivalents.

- [ ] **Step 4: Run the full suite**

Run:
```bash
python -m pytest -v
python src/ask.py --offline Q1
python src/ask.py --offline Q2
```
Expected: all tests PASS (live resolver tests SKIP); both commands print their documented answers.

- [ ] **Step 5: Commit**

```bash
git add README.md appendix/portability.md tests/test_guide.py
git commit -m "docs: add the implementation guide covering phases 0-7"
```

---

## Task 14: Acceptance verification

**Files:**
- Create: `verify_acceptance.py`

**Interfaces:**
- Consumes: everything.
- Produces: `verify_acceptance.py` printing PASS/FAIL for spec §8 criteria 1–11 and exiting non-zero on any failure.

- [ ] **Step 1: Write the verification script**

Create `verify_acceptance.py` — check each criterion mechanically, printing one line per criterion:

1. `build_warehouse.build()` succeeds from a deleted DB with no network.
2. `ask.py --offline Q1` → 87.3%, 48/55, provenance, `TRUSTED`.
3. `ask.py --offline Q2` → 87.3%, −8.9pp vs 96.2%, attribution `quality_inspection 4, transportation 2, production_execution 1`.
4. `pytest` green with `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` stripped from the environment; live tests skipped.
5. Compiler asserts 87.27% / 88.52% / 94.44% / 94.55%.
6. Each of the 8 defects is named by a DQ rule, and each rule fails on its own
   corruption while staying quiet on the others. Delegate to
   `test_each_rule_fails_on_its_own_corruption_and_stays_quiet_otherwise` rather than
   re-deriving it: that test mutates a scratch copy inside a rolled-back transaction
   and asserts the whole verdict set. Note "only its intended rule" is **not** the
   right criterion — a duplicated order row genuinely changes the published OTD
   number, so `dq_accuracy_otd_certification` failing alongside
   `dq_uniqueness_order_grain` is the certification working as a backstop, not
   leakage. Measured: that is the one and only expected cross-fire.
7. Section 5.1 denominators match the committed CSVs.
8. `python data/generate.py` twice → byte-identical CSVs (compare SHA-256).
9. All 9 metadata artifacts exist, parse, and contain no placeholder tokens.
10. `README.md` contains "NL FAILURE CLOSED" at least 8 times.
11. Governance-limits statement present in `README.md` body.
12. The dataflow diagram is committed, current, and embedded: `docs/diagrams/nl_dataflow.svg` and `.png` exist, `python docs/diagrams/render_dataflow.py --check` exits 0, and `README.md` embeds the SVG. (Task 12.5. Spec §8 lists 11 criteria; this one is additive, so label it 12 and note it as an addition rather than renumbering the spec's list.)

- [ ] **Step 2: Run it**

Run: `python verify_acceptance.py`
Expected: 12 lines, all PASS, exit 0. Any FAIL is a real defect — fix the code, not the check.

Note criterion 12 of **spec §8** (live resolver with a real API key) is a different thing from check 12 above and is **not verifiable in this environment** — no credentials. The script must print it as `SKIP (no credentials)`, never as `PASS`. Claiming an untested criterion passed is the one failure mode this script exists to prevent.

- [ ] **Step 3: Commit**

```bash
git add verify_acceptance.py
git commit -m "test: add acceptance verification for spec criteria 1-11"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Covered by |
|---|---|
| §3.1 anchor KPI | Task 5 |
| §3.2 Q1 and Q2 | Tasks 10, 11 |
| §3.3 twelve process phases | Task 4 (`04_process_model.yml`), Task 3 (`dim_process_phase`) |
| §3.4 variance attribution | Task 3 (`delay_attribution_phase`), Task 4 (`attribution:` block) |
| §3.5 metrics | Task 5 (3 of 4; `production_cycle_time_days` deferred per §10.2) |
| §4 architecture | Tasks 6, 7, 12 |
| §4.2 seven gates | Task 6 |
| §4.3 Claude API contract | Task 12 |
| §4.4 offline mode | Tasks 10, 11 |
| §5.1 scale | Task 2 |
| §5.2 seed vs generated | Tasks 1, 2 |
| §5.3 eight defects | Task 1 (data), Task 8 (rules) |
| §5.4 wrong answer worked | Task 7, Task 13 |
| §6 phases P0–P7 | Tasks 4, 5, 8, 9 |
| §6.1 DQ rules | Task 8 |
| §6.2 governance + limits | Task 9, Task 13 |
| §7 file structure | all |
| §8 acceptance 1–11 | Task 14 |
| §10 MVP scope | all; deferrals documented in Task 13 |

No gaps.

**Placeholder scan:** every code step carries runnable code or an explicit, checkable requirement list. Artifact-content steps (Tasks 4, 5, 8, 9, 13) specify required keys, required values, and the tests that enforce them rather than full file bodies — the tests are the contract, and they are written out in full.

**Type consistency:** `QueryIntent`/`Filter`/`TimeWindow` (Task 6) are used identically in Tasks 7, 10, 11, 12. `CompiledQuery.sql`/`.params`/`.applied_exclusions`/`.grain` consistent across Tasks 7, 9. `DQReport.badge`/`.results`/`.failing_rules` consistent across Tasks 8, 9, 11. `Answer` fields consistent across Tasks 9, 11. `run_rules(metric_name, db_path, rules_path)` — the `rules_path` parameter needed by `test_blocking_failure_yields_blocked_badge` is declared in Task 8's interface block. Gate names are fixed strings, identical in Task 6's implementation and its tests. `SemanticModel` accessors declared in Task 5 and used in Tasks 6, 7, 10, 12.

**Verified before writing:** every canonical figure in Global Constraints was computed and cross-checked (48/55 = 87.2727%, 25/26 = 96.1538%, delta 8.88pp, naive 54/61 = 88.5246%, FPY 51/54 = 94.4444% vs naive 52/55 = 94.5455%, adherence 50/54 = 92.5926%, window totals summing to 132). Two errors in an earlier draft of the spec were corrected as a result: the naive delivery-grain figure was wrong in both magnitude and direction, and the not-yet-due accounting didn't balance. The spec at `docs/design.md` now matches these numbers.
