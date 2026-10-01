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
import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DATA_DIR.parent))

from src.semantic.constants import AS_OF_DATE

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

def load_seed():
    """Load seed_core.csv and parse it into order dictionaries."""
    with open(DATA_DIR / "seed_core.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def date_from_str(s):
    """Parse YYYY-MM-DD string to date, or None if empty."""
    if not s:
        return None
    return date.fromisoformat(s)

def date_to_str(d):
    """Convert date to YYYY-MM-DD string, or empty string if None."""
    if d is None:
        return ""
    return d.isoformat()

def generate_filler_order(order_id, region, promised_date, late=False, cancelled=False, not_yet_due=False):
    """Generate a single filler order with derived timestamps."""
    # Standard lead time: mrp(1) + release(1) + issue(1) + confirm(3) + qm(1) + gr(1) + picking(1) + goods_issue(0) + shipment_lead(1) + delivery(3) = 13 days
    # To be on time, order_date should be at least 13 days before promised_date
    order_date = promised_date - timedelta(days=14)  # 14 days to have margin

    plant = "1010" if region == "IN" else "1710"
    warehouse = f"WH-{region}-01"
    carrier = RNG.choice(["BLUEDART", "FEDEX"])
    customer_id = f"C-{region}-{RNG.randint(100, 999):03d}"

    order_status = "CANC" if cancelled else "IN_TRANSIT" if not_yet_due else "DLVD"

    # Generate production and delivery timeline
    prod_order_id = order_id.replace("SO-", "PO-")
    inspection_lot_id = order_id.replace("SO-", "QL-")

    # Start from order_date and walk through phases
    mrp_date = order_date + timedelta(days=STD["mrp"])
    release_date = mrp_date + timedelta(days=STD["release"])
    material_issue_date = release_date + timedelta(days=STD["issue"])
    confirm_date = material_issue_date + timedelta(days=STD["confirm"])
    qm_decision_date = confirm_date + timedelta(days=STD["qm"])
    gr_date = qm_decision_date + timedelta(days=STD["gr"])
    picking_date = gr_date + timedelta(days=STD["picking"])
    goods_issue_date = picking_date + timedelta(days=STD["goods_issue"])
    shipment_date = goods_issue_date + timedelta(days=1)

    if late:
        # Make it late by adding 4 days to delivery
        delivery_date = shipment_date + timedelta(days=STD["shipment"] + 4)
    else:
        delivery_date = shipment_date + timedelta(days=STD["shipment"])

    # For not-yet-due, delivery_date is empty
    if not_yet_due:
        delivery_date = None

    # For cancelled, most dates are empty
    if cancelled:
        return {
            "order_id": order_id,
            "region": region,
            "plant": plant,
            "warehouse": warehouse,
            "carrier": carrier,
            "customer_id": customer_id,
            "order_date": date_to_str(order_date),
            "promised_delivery_date": date_to_str(promised_date),
            "promised_date_original": "",
            "order_status": order_status,
            "production_order_id": prod_order_id,
            "inspection_lot_id": "",
            "rework": "N",
            "split_delivery": "none",
            "mrp_date": date_to_str(mrp_date),
            "prod_release_date": date_to_str(release_date),
            "material_issue_date": "",
            "prod_confirm_date": "",
            "qm_decision_date": "",
            "gr_date": "",
            "picking_date": "",
            "goods_issue_date": "",
            "shipment_date": "",
            "final_delivery_date": "",
            "invoice_date": "",
            "expected_attribution_phase": "",
        }

    invoice_date = delivery_date + timedelta(days=STD["invoice"]) if delivery_date else None

    return {
        "order_id": order_id,
        "region": region,
        "plant": plant,
        "warehouse": warehouse,
        "carrier": carrier,
        "customer_id": customer_id,
        "order_date": date_to_str(order_date),
        "promised_delivery_date": date_to_str(promised_date),
        "promised_date_original": "",
        "order_status": order_status,
        "production_order_id": prod_order_id,
        "inspection_lot_id": inspection_lot_id,
        "rework": "N",
        "split_delivery": "none",
        "mrp_date": date_to_str(mrp_date),
        "prod_release_date": date_to_str(release_date),
        "material_issue_date": date_to_str(material_issue_date),
        "prod_confirm_date": date_to_str(confirm_date),
        "qm_decision_date": date_to_str(qm_decision_date),
        "gr_date": date_to_str(gr_date),
        "picking_date": date_to_str(picking_date),
        "goods_issue_date": date_to_str(goods_issue_date),
        "shipment_date": date_to_str(shipment_date),
        "final_delivery_date": date_to_str(delivery_date),
        "invoice_date": date_to_str(invoice_date),
        "expected_attribution_phase": "",
    }

def generate_orders():
    """Generate all 132 orders: 20 seed + 112 filler."""
    seed = load_seed()
    orders = list(seed)  # Start with seed orders

    next_order_id = 2001

    # IN Jul: need 39 filler (all on time)
    for _ in range(39):
        promised = date(2026, 7, RNG.randint(1, 31))
        order = generate_filler_order(f"SO-{next_order_id}", "IN", promised, late=False, cancelled=False)
        orders.append(order)
        next_order_id += 1

    # IN Jun: need 26 filler (25 on time + 1 cancelled)
    for i in range(26):
        promised = date(2026, 6, RNG.randint(1, 30))
        cancelled = (i == 0)  # First one is cancelled
        order = generate_filler_order(f"SO-{next_order_id}", "IN", promised, late=False, cancelled=cancelled)
        orders.append(order)
        next_order_id += 1

    # IN Aug: need 3 filler (all not-yet-due, promised after AS_OF_DATE)
    for _ in range(3):
        # Strictly after AS_OF_DATE, so these are not yet due and must be
        # excluded from the OTD denominator rather than counted as late.
        promised = date(
            AS_OF_DATE.year, AS_OF_DATE.month, RNG.randint(AS_OF_DATE.day + 1, 31)
        )
        order = generate_filler_order(f"SO-{next_order_id}", "IN", promised, late=False, cancelled=False, not_yet_due=True)
        orders.append(order)
        next_order_id += 1

    # US Jul: need 29 filler (25 on time + 2 late + 2 cancelled)
    for i in range(29):
        promised = date(2026, 7, RNG.randint(1, 31))
        if i < 2:
            cancelled = True
            late = False
        elif i < 4:
            cancelled = False
            late = True
        else:
            cancelled = False
            late = False
        order = generate_filler_order(f"SO-{next_order_id}", "US", promised, late=late, cancelled=cancelled)
        orders.append(order)
        next_order_id += 1

    # US Jun: need 15 filler (14 on time + 1 late)
    for i in range(15):
        promised = date(2026, 6, RNG.randint(1, 30))
        late = (i == 0)  # First one is late
        order = generate_filler_order(f"SO-{next_order_id}", "US", promised, late=late, cancelled=False)
        orders.append(order)
        next_order_id += 1

    return orders

def create_sales_orders(orders):
    """Create sales_orders_raw.csv from order list."""
    fieldnames = [
        "order_id", "region", "plant", "warehouse", "carrier", "customer_id",
        "order_date", "promised_delivery_date", "promised_date_original", "order_status"
    ]
    rows = []
    for o in orders:
        rows.append({
            "order_id": o["order_id"],
            "region": o["region"],
            "plant": o["plant"],
            "warehouse": o["warehouse"],
            "carrier": o["carrier"],
            "customer_id": o["customer_id"],
            "order_date": o["order_date"],
            "promised_delivery_date": o["promised_delivery_date"],
            "promised_date_original": o["promised_date_original"],
            "order_status": o["order_status"],
        })
    write_csv("sales_orders_raw.csv", fieldnames, rows)

def create_production_orders(orders):
    """Create production_orders_raw.csv."""
    fieldnames = [
        "production_order_id", "order_id", "plant", "mrp_date", "release_date",
        "scheduled_finish_date", "material_issue_date", "confirm_date", "gr_date", "status"
    ]
    rows = []

    # Identify IN July production orders for schedule adherence calculation
    in_july_prod_orders = []
    for o in orders:
        if (o["region"] == "IN" and
            o["promised_delivery_date"].startswith("2026-07") and
            o["production_order_id"] and
            o["order_status"] != "CANC"):
            in_july_prod_orders.append(o)

    # Need 50 out of 54 to meet schedule (4 late)
    # PO-3005 is already late (production_execution), mark 3 more as late
    late_indices = [5, 15, 25]  # Fixed indices for determinism

    for o in orders:
        if not o["production_order_id"]:
            continue  # SO-1015 has no production order

        # Calculate scheduled_finish_date
        if o["prod_confirm_date"]:
            confirm_date = date_from_str(o["prod_confirm_date"])
            # For schedule adherence: set scheduled_finish_date
            # On-time means: confirm_date <= scheduled_finish_date
            if o in in_july_prod_orders:
                idx = in_july_prod_orders.index(o)
                if o["production_order_id"] == "PO-3005" or idx in late_indices:
                    # Make it late: scheduled before actual confirm
                    scheduled_finish = confirm_date - timedelta(days=1)
                else:
                    # On time: scheduled at or after confirm
                    scheduled_finish = confirm_date + timedelta(days=1)
            else:
                # Default: slightly after confirm (on time)
                scheduled_finish = confirm_date + timedelta(days=1)
        else:
            scheduled_finish = None

        rows.append({
            "production_order_id": o["production_order_id"],
            "order_id": o["order_id"],
            "plant": o["plant"],
            "mrp_date": o["mrp_date"],
            "release_date": o["prod_release_date"],
            "scheduled_finish_date": date_to_str(scheduled_finish),
            "material_issue_date": o["material_issue_date"],
            "confirm_date": o["prod_confirm_date"],
            "gr_date": o["gr_date"],
            "status": o["order_status"],
        })

    write_csv("production_orders_raw.csv", fieldnames, rows)

def create_inspection_lots(orders):
    """Create inspection_lots_raw.csv with rework handling."""
    fieldnames = [
        "inspection_lot_id", "production_order_id", "decision_seq",
        "decision_date", "usage_decision", "qty_inspected", "qty_accepted"
    ]
    rows = []

    # Identify IN July lots for first-pass yield calculation
    in_july_lots = []
    for o in orders:
        if (o["region"] == "IN" and
            o["promised_delivery_date"].startswith("2026-07") and
            o["inspection_lot_id"] and
            o["order_status"] != "CANC"):
            in_july_lots.append(o)

    # Need 51 out of 54 to accept on first pass (3 reject/rework)
    # QL-4004 is already rework, mark 2 more as reject
    reject_indices = [10, 20]  # Fixed indices for determinism

    for o in orders:
        if not o["inspection_lot_id"]:
            continue  # SO-1015 and cancelled orders have no inspection lot

        # Handle QL-4004 rework case
        if o["inspection_lot_id"] == "QL-4004":
            rows.append({
                "inspection_lot_id": "QL-4004",
                "production_order_id": o["production_order_id"],
                "decision_seq": "1",
                "decision_date": "2026-07-11",
                "usage_decision": "REWORK",
                "qty_inspected": "100",
                "qty_accepted": "0",
            })
            rows.append({
                "inspection_lot_id": "QL-4004",
                "production_order_id": o["production_order_id"],
                "decision_seq": "2",
                "decision_date": "2026-07-14",
                "usage_decision": "ACCEPT",
                "qty_inspected": "100",
                "qty_accepted": "100",
            })
        else:
            # Determine usage decision
            if o in in_july_lots:
                idx = in_july_lots.index(o)
                if idx in reject_indices:
                    usage_decision = "REJECT"
                    qty_accepted = "0"
                else:
                    usage_decision = "ACCEPT"
                    qty_accepted = "100"
            else:
                usage_decision = "ACCEPT"
                qty_accepted = "100"

            rows.append({
                "inspection_lot_id": o["inspection_lot_id"],
                "production_order_id": o["production_order_id"],
                "decision_seq": "1",
                "decision_date": o["qm_decision_date"],
                "usage_decision": usage_decision,
                "qty_inspected": "100",
                "qty_accepted": qty_accepted,
            })

    write_csv("inspection_lots_raw.csv", fieldnames, rows)

def create_goods_movements(orders):
    """Create goods_movements_raw.csv."""
    fieldnames = ["movement_id", "production_order_id", "movement_type", "posting_date"]
    rows = []

    movement_counter = 5001
    for o in orders:
        if not o["production_order_id"] or not o["material_issue_date"]:
            continue  # No production or cancelled

        rows.append({
            "movement_id": f"GM-{movement_counter}",
            "production_order_id": o["production_order_id"],
            "movement_type": "261",  # Goods issue
            "posting_date": o["material_issue_date"],
        })
        movement_counter += 1

        if o["gr_date"]:
            rows.append({
                "movement_id": f"GM-{movement_counter}",
                "production_order_id": o["production_order_id"],
                "movement_type": "101",  # Goods receipt
                "posting_date": o["gr_date"],
            })
            movement_counter += 1

    write_csv("goods_movements_raw.csv", fieldnames, rows)

def create_deliveries(orders):
    """Create deliveries_raw.csv with split delivery handling."""
    fieldnames = [
        "delivery_id", "order_id", "delivery_leg", "picking_date",
        "goods_issue_date", "delivery_date", "delivery_status"
    ]
    rows = []

    for o in orders:
        if o["order_status"] == "CANC":
            continue  # Cancelled orders have no delivery

        # Handle split deliveries
        if o["split_delivery"] in ["on_time", "mixed"]:
            # Two legs
            delivery_id_a = o["order_id"].replace("SO-", "DL-") + "A"
            delivery_id_b = o["order_id"].replace("SO-", "DL-") + "B"

            if o["order_id"] == "SO-1009":
                # Mixed case: leg A on time (2026-07-16), leg B late (2026-07-20)
                rows.append({
                    "delivery_id": delivery_id_a,
                    "order_id": o["order_id"],
                    "delivery_leg": "1",
                    "picking_date": o["picking_date"],
                    "goods_issue_date": o["goods_issue_date"],
                    "delivery_date": "2026-07-16",
                    "delivery_status": "DLVD",
                })
                rows.append({
                    "delivery_id": delivery_id_b,
                    "order_id": o["order_id"],
                    "delivery_leg": "2",
                    "picking_date": o["picking_date"],
                    "goods_issue_date": o["goods_issue_date"],
                    "delivery_date": "2026-07-20",
                    "delivery_status": "DLVD",
                })
            else:
                # Both legs on time
                rows.append({
                    "delivery_id": delivery_id_a,
                    "order_id": o["order_id"],
                    "delivery_leg": "1",
                    "picking_date": o["picking_date"],
                    "goods_issue_date": o["goods_issue_date"],
                    "delivery_date": o["final_delivery_date"],
                    "delivery_status": o["order_status"],
                })
                rows.append({
                    "delivery_id": delivery_id_b,
                    "order_id": o["order_id"],
                    "delivery_leg": "2",
                    "picking_date": o["picking_date"],
                    "goods_issue_date": o["goods_issue_date"],
                    "delivery_date": o["final_delivery_date"],
                    "delivery_status": o["order_status"],
                })
        else:
            # Single delivery
            delivery_id = o["order_id"].replace("SO-", "DL-")
            rows.append({
                "delivery_id": delivery_id,
                "order_id": o["order_id"],
                "delivery_leg": "1",
                "picking_date": o["picking_date"],
                "goods_issue_date": o["goods_issue_date"],
                "delivery_date": o["final_delivery_date"],
                "delivery_status": o["order_status"],
            })

    write_csv("deliveries_raw.csv", fieldnames, rows)

def create_shipments(orders):
    """Create shipments_raw.csv."""
    fieldnames = [
        "shipment_id", "delivery_id", "carrier", "dispatch_date",
        "delivery_date", "delivery_status"
    ]
    rows = []

    for o in orders:
        if o["order_status"] == "CANC":
            continue

        # Handle split deliveries
        if o["split_delivery"] in ["on_time", "mixed"]:
            delivery_id_a = o["order_id"].replace("SO-", "DL-") + "A"
            delivery_id_b = o["order_id"].replace("SO-", "DL-") + "B"
            shipment_id_a = o["order_id"].replace("SO-", "SH-") + "A"
            shipment_id_b = o["order_id"].replace("SO-", "SH-") + "B"

            if o["order_id"] == "SO-1009":
                rows.append({
                    "shipment_id": shipment_id_a,
                    "delivery_id": delivery_id_a,
                    "carrier": o["carrier"],
                    "dispatch_date": o["shipment_date"],
                    "delivery_date": "2026-07-16",
                    "delivery_status": "DLVD",
                })
                rows.append({
                    "shipment_id": shipment_id_b,
                    "delivery_id": delivery_id_b,
                    "carrier": o["carrier"],
                    "dispatch_date": o["shipment_date"],
                    "delivery_date": "2026-07-20",
                    "delivery_status": "DLVD",
                })
            else:
                rows.append({
                    "shipment_id": shipment_id_a,
                    "delivery_id": delivery_id_a,
                    "carrier": o["carrier"],
                    "dispatch_date": o["shipment_date"],
                    "delivery_date": o["final_delivery_date"],
                    "delivery_status": o["order_status"],
                })
                rows.append({
                    "shipment_id": shipment_id_b,
                    "delivery_id": delivery_id_b,
                    "carrier": o["carrier"],
                    "dispatch_date": o["shipment_date"],
                    "delivery_date": o["final_delivery_date"],
                    "delivery_status": o["order_status"],
                })
        else:
            delivery_id = o["order_id"].replace("SO-", "DL-")
            shipment_id = o["order_id"].replace("SO-", "SH-")
            rows.append({
                "shipment_id": shipment_id,
                "delivery_id": delivery_id,
                "carrier": o["carrier"],
                "dispatch_date": o["shipment_date"],
                "delivery_date": o["final_delivery_date"],
                "delivery_status": o["order_status"],
            })

    write_csv("shipments_raw.csv", fieldnames, rows)

def main():
    """Generate all raw CSV files."""
    print("Generating orders...")
    orders = generate_orders()

    # Verify composition before writing
    print("Verifying window composition...")

    # IN Jul
    in_jul = [o for o in orders if o["region"] == "IN" and o["promised_delivery_date"].startswith("2026-07")]
    in_jul_canc = [o for o in in_jul if o["order_status"] == "CANC"]
    in_jul_eligible = [o for o in in_jul if o["order_status"] != "CANC"]
    in_jul_on_time = [o for o in in_jul_eligible if o["final_delivery_date"] and o["final_delivery_date"] <= o["promised_delivery_date"]]

    assert len(in_jul) == 56, f"IN Jul total: expected 56, got {len(in_jul)}"
    assert len(in_jul_canc) == 1, f"IN Jul cancelled: expected 1, got {len(in_jul_canc)}"
    assert len(in_jul_eligible) == 55, f"IN Jul eligible: expected 55, got {len(in_jul_eligible)}"
    assert len(in_jul_on_time) == 48, f"IN Jul on time: expected 48, got {len(in_jul_on_time)}"

    # IN Jun
    in_jun = [o for o in orders if o["region"] == "IN" and o["promised_delivery_date"].startswith("2026-06")]
    in_jun_canc = [o for o in in_jun if o["order_status"] == "CANC"]

    assert len(in_jun) == 27, f"IN Jun total: expected 27, got {len(in_jun)}"
    assert len(in_jun_canc) == 1, f"IN Jun cancelled: expected 1, got {len(in_jun_canc)}"

    # IN Aug
    in_aug = [o for o in orders if o["region"] == "IN" and o["promised_delivery_date"].startswith("2026-08")]

    assert len(in_aug) == 4, f"IN Aug total: expected 4, got {len(in_aug)}"
    for o in in_aug:
        assert o["promised_delivery_date"] > AS_OF_DATE.isoformat(), f"IN Aug order {o['order_id']} not after AS_OF_DATE"

    # US Jul
    us_jul = [o for o in orders if o["region"] == "US" and o["promised_delivery_date"].startswith("2026-07")]
    us_jul_canc = [o for o in us_jul if o["order_status"] == "CANC"]

    assert len(us_jul) == 30, f"US Jul total: expected 30, got {len(us_jul)}"
    assert len(us_jul_canc) == 2, f"US Jul cancelled: expected 2, got {len(us_jul_canc)}"

    # US Jun
    us_jun = [o for o in orders if o["region"] == "US" and o["promised_delivery_date"].startswith("2026-06")]

    assert len(us_jun) == 15, f"US Jun total: expected 15, got {len(us_jun)}"

    # Total
    assert len(orders) == 132, f"Total orders: expected 132, got {len(orders)}"

    print("Creating CSVs...")
    create_sales_orders(orders)
    create_production_orders(orders)
    create_inspection_lots(orders)
    create_goods_movements(orders)
    create_deliveries(orders)
    create_shipments(orders)

    print("Done. 6 raw CSV files generated.")

if __name__ == "__main__":
    main()
