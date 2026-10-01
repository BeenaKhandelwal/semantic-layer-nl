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
SO-1019,IN,1010,WH-IN-01,BLUEDART,C-IN-019,2026-06-01,2026-06-13,,DLVD,PO-3019,QL-4019,N,none,2026-06-02,2026-06-03,2026-06-04,2026-06-07,2026-06-08,2026-06-09,2026-06-10,2026-06-10,2026-06-11,2026-06-18,2026-06-20,transportation
SO-1020,US,1710,WH-US-01,FEDEX,C-US-001,2026-07-01,2026-07-13,,DLVD,PO-3020,QL-4020,N,none,2026-07-02,2026-07-03,2026-07-04,2026-07-07,2026-07-08,2026-07-09,2026-07-10,2026-07-10,2026-07-11,2026-07-12,2026-07-14,
```

Notes for the implementer:
- `expected_attribution_phase` is a **test oracle column** — it records the answer the pipeline must independently derive from timestamps. The compiler must never read it. `tests/test_end_to_end.py` compares the derived attribution against it.
- `SO-1013` is promised 2026-08-12 (after `AS_OF_DATE`), so it is not-yet-due and falls outside the July window — it must not count as late anywhere.
- `SO-1019` is the single late June IN order (June: 27 in window, 1 cancelled, 25 on time of 26 eligible).
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

