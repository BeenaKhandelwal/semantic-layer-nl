# Task 3 Report — DuckDB warehouse with order-grain fact table

## Summary

Successfully implemented the DuckDB warehouse with order-grain fact table, including staging views, dimension tables, and phase variance attribution logic.

## What was built

Created three files as specified:

1. **`sql/02_staging_model.sql`** (568 lines)
   - `dim_process_phase` table with all 12 phases
   - Staging views for all 6 raw CSV sources
   - `delivery_by_order` view that collapses split deliveries to order grain (max delivery_date)
   - `inspection_by_prod_order` view separating first vs final QM decisions
   - `shipment_by_order` view for shipment date aggregation
   - `fact_order_delivery` table (one row per order_id) with:
     - All phase timestamps
     - Computed flags: is_delivered, is_eligible, is_on_time
     - Phase variances (var_mrp, var_release, var_issue, var_confirm, var_qm, var_gr, var_picking, var_shipment)
     - Delay attribution phase using GREATEST logic with tie-breaking to earliest phase
     - Available slack days calculation (subtracts 12 days for phases 1-11)
   - `fact_production_order` table (one row per production_order_id)

2. **`src/build_warehouse.py`**
   - Idempotent build function that:
     - Reads SQL from `sql/02_staging_model.sql`
     - Substitutes `__DATA_DIR__` token with actual path
     - Substitutes `__AS_OF_DATE__` token with `constants.AS_OF_DATE`
     - Executes SQL in DuckDB
   - CLI support via `if __name__ == "__main__"`

3. **`tests/test_warehouse.py`** (9 test functions)
   - All 9 tests pass
   - Tests verify:
     - Order grain (132 rows, all unique)
     - Split delivery handling (SO-1009 with 2 legs, max date = 2026-07-20)
     - Canonical IN/July numbers: 55 eligible, 48 on time
     - Eligibility rules (cancelled and not-yet-due excluded)
     - Left join preservation (SO-1015 make-to-stock survives with NULLs)
     - Attribution matching oracle (all 7 late orders correctly attributed)
     - QM first vs final dates for rework (SO-1004: first=07-11, final=07-14)
     - Idempotency

## Commit

- **SHA**: `02c57d6`
- **Message**: `feat: build order-grain DuckDB warehouse with phase variance attribution`

## Test results

```
tests/test_warehouse.py::test_fact_is_one_row_per_order PASSED
tests/test_warehouse.py::test_split_delivery_collapsed_to_max_date PASSED
tests/test_warehouse.py::test_in_july_eligibility_and_ontime PASSED
tests/test_warehouse.py::test_cancelled_order_not_eligible PASSED
tests/test_warehouse.py::test_in_transit_future_promise_not_eligible_not_late PASSED
tests/test_warehouse.py::test_make_to_stock_order_survives_left_join PASSED
tests/test_warehouse.py::test_attribution_matches_oracle PASSED
tests/test_warehouse.py::test_qm_first_vs_final_decision_differ_for_rework PASSED
tests/test_warehouse.py::test_build_is_idempotent PASSED

9 passed
```

All 26 total tests pass (17 from Tasks 1-2, 9 new from Task 3).

## Observed canonical numbers

The test `test_in_july_eligibility_and_ontime` verified the canonical tuple:
- **Eligible**: 55
- **On time**: 48
- **OTD percentage**: 48/55 = 87.27%

This matches the spec exactly.

## Implementation details

### Key decisions

1. **Shipment date source**: Used `dispatch_date` from `stg_shipments` as the shipment_date, aggregated via `shipment_by_order` view
2. **Invoice date**: Computed as `final_delivery_date + 1 day` since no invoice CSV exists in the raw data
3. **Phase variance calculations**: 
   - var_issue (material_staging → production_execution) uses standard duration = 3 days
   - var_confirm (production_execution → quality_inspection) uses standard duration = 1 day
   - These mappings were critical for correct attribution

### Attribution logic

The delay attribution uses an 8-way GREATEST comparison across variances for phases 2-10 (mrp through transportation), with:
- Early-phase tie-breaking (first WHEN clause wins)
- NULL return when all variances ≤ 0
- Evaluation only for late, delivered, eligible orders

### Deviations from plan

None. Followed the plan's five steps exactly:
1. ✓ Wrote failing test
2. ✓ Confirmed test failed with expected error
3. ✓ Implemented SQL and Python builder
4. ✓ Confirmed all 9 tests pass
5. ✓ Committed with specified message

## Issues encountered

**Variance standard durations**: Initially used incorrect standard durations in the phase variance calculations. The issue was:
- `var_issue` (material_issue → prod_confirm) represents production_execution phase, requires std=3 (not 1)
- `var_confirm` (prod_confirm → qm_decision) represents quality_inspection phase, requires std=1 (not 3)

Once corrected, the attribution test passed immediately. The expected oracle attributions all matched.

## Verification checklist

- ✓ `python -m pytest tests/test_warehouse.py -v` → 9 passed
- ✓ `python -m pytest -q` → 26 passed (all tests, nothing broken)
- ✓ `grep -rn "2026-08-07" sql/ src/` → no matches
- ✓ `warehouse.duckdb` already in .gitignore (line 15)
- ✓ One commit with plan's message
- ✓ No changes to data/*.csv, src/semantic/constants.py, or tests/test_data.py

## Conclusion

Task 3 complete. The order-grain fact table correctly handles:
- Split deliveries (collapsed to max date)
- Make-to-stock orders (preserved via LEFT JOINs)
- Cancelled orders (excluded from eligibility)
- Not-yet-due orders (excluded from eligibility)
- Phase variance attribution (all 7 late IN/July orders correctly attributed)
- Rework inspection lots (first vs final decision dates)

The canonical OTD numbers (55 eligible, 48 on time) are verified and correct.
