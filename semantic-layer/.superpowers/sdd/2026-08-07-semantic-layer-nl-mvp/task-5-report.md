# Task 5 Report: Semantic Model with 3 Governed Metrics + Loader

## Summary

Successfully implemented Task 5 following the TDD workflow. All 10 new tests pass, all 61 existing tests still pass (71 total), and the semantic model correctly declares the three metrics with proper grain separation and join relationships.

## Commit

**SHA:** 3be3254947414355f32ce6980af6790061e08891

**Message:** feat: add semantic model with 3 governed metrics and loader validation

## Files Created

1. **metadata/05_semantic_model.yml** (216 lines)
2. **src/semantic/loader.py** (189 lines)
3. **tests/test_loader.py** (77 lines)
**Total:** 482 lines added

## What Was Declared

### Entities
- fact_order_delivery (grain: order) with joins to fact_production_order and raw_deliveries
- fact_production_order (grain: production_order) with join to fact_order_delivery
- raw_deliveries (grain: delivery)

### Metrics
1. on_time_delivery_pct (order grain, time_dimension: promised_delivery_date)
2. first_pass_yield_pct (production_order grain, time_dimension: promised_delivery_date via join)
3. mfg_schedule_adherence_pct (production_order grain, time_dimension: promised_delivery_date via join)

## Verification Against Built Warehouse

### Column Verification
Ran PRAGMA table_info() to verify all columns exist in warehouse tables.

fact_production_order: Confirmed NO region or promised_delivery_date columns (as expected).
fact_order_delivery: All 40 columns verified.

### Join Cardinality
Query result: 131 production orders, 131 distinct order_ids, max 1 order per production order.
Confirms many_to_one relationship.

### Production Metrics Windowing
**Correct approach (promised_delivery_date via join):**
- FPY: 51/54 = 94.4444%
- Adherence: 50/54 = 92.5926%
- Matches certified numbers from plan

**Wrong approach (scheduled_finish_date):**
- FPY: 42/45 = 93.3333%
- Adherence: 42/45 = 93.3333%
- Matches the 42/45 error cited in brief

## Test Results

python -m pytest tests/test_loader.py -v
Result: 10 passed

python -m pytest -q
Result: 71 passed in 1.72s (61 existing + 10 new)

grep -rn "2026-08-07" metadata/
Result: No output (confirmed no date literals)

## Adherence to Plan

Followed all 5 TDD steps exactly:
1. Wrote failing test
2. Verified failure
3. Implemented YAML and loader
4. Verified tests pass
5. Committed with plan message

No deviations from plan. No issues found in plan or SQL.

## File Sizes (verified with wc -l)
  216 metadata/05_semantic_model.yml
  189 src/semantic/loader.py
   77 tests/test_loader.py
  482 total

## Conclusion

Task 5 complete. Semantic model correctly declares 3 governed metrics with distinct grains, proper many_to_one joins, production metrics reaching region/promised_delivery_date through the join, all exclusions using __AS_OF_DATE__ token, and all column names verified against warehouse.
