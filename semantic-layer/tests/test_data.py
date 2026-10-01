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
