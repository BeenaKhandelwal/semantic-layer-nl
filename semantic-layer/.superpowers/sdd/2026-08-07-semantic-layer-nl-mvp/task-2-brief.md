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

