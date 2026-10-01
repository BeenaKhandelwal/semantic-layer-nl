# Pre-flight findings for Tasks 5–14 (verified against the built warehouse)

Measured, not remembered. Every number here came from a real query on
`warehouse.duckdb` built by `python -m src.build_warehouse` at commit 32e78bf.

## Fixed in the plan (commit 32e78bf)

**BLOCKING — production metrics had no route to region/promised date.**
`fact_production_order` has 15 columns and **neither `region` nor
`promised_delivery_date`**. Task 7 filters both production metrics on `region` and windows
them on the promised date, expecting 51/54 (FPY) and 50/54 (adherence).

| Windowing choice | FPY | Adherence |
|---|---|---|
| `promised_delivery_date` via join to `fact_order_delivery` | **51/54** ✅ | **50/54** ✅ |
| `scheduled_finish_date` on the fact itself | 42/45 ❌ | 42/45 ❌ |

Join verified non-fan-out: 131 production orders over 131 distinct `order_id`s, zero
orders with >1 production order. So `many_to_one` is correct and the `no_fanout` gate must
**permit** it. Fixed in T5 (declare entity + join), T6 (reachability in gates 2/3/5, +5
tests), T7 (emit join, assert denominator ≠ 45, +7 tests).

`cancelled_production_orders` is load-bearing on the denominator: without it the IN/July
cohort is 55, not 54.

## Warned to the Task 8 agent (live)

**design.md §6.1 timeliness threshold contradicts `test_clean_warehouse_is_trusted`.**
`max(invoice_date)` = 2026-08-04, `AS_OF_DATE` = 2026-08-07 → lag is exactly **72 hours**.
The spec says "within 26 hours", which fails, making the badge `DEGRADED` while the test
demands `TRUSTED`. Resolution directed: threshold 96h with the reason documented in the
YAML (frozen snapshot cannot express a live 26h SLA), `severity: degrading`, rule still
proven capable of failing. Not to be resolved by weakening the test.

Also measured for T8, so rules can be written against reality:
- nulls in `final_delivery_date` among the 124 eligible orders: **0**
- consistency violations (`release_date <= gr_date <= goods_issue_date <= final_delivery_date`): **0**
- `plant` domain: exactly `{1010, 1710}`; `order_status`: `{DLVD, IN_TRANSIT, CANC}`
- design §6.1 names `delivery_timestamp`, which **does not exist** — the column is
  `final_delivery_date`.

## Pending trap for Task 9 (provenance)

`test_diagnostic_answer_includes_breakdown` asserts:

```python
assert "quality inspection" in a.render().lower()      # SPACE
```

but the column value is `quality_inspection` (**underscore**), and
`"quality inspection" in "quality_inspection"` is `False`. So `render()` **must humanize
phase keys** — it cannot just print the raw value. `dim_process_phase.phase_name` already
holds the display forms (`Quality inspection`, `Transportation`, `Production execution`);
prefer joining/mapping to those over a blind `replace("_", " ")`, since the dimension is
the declared source of the label. Note the test lowercases, so casing is free.

## Fixed in the plan — Task 7, empty-window aggregate (commit 53d46c8)

The August window matches **zero rows**: all 4 IN/August orders fall to the `not_yet_due`
exclusion, so the WHERE clause eliminates every row. SQL `SUM()` over an empty set returns
`NULL`, not `0`:

```
August raw: (None, None, 0)      -- num, den, rows_matched
with coalesce: (0, 0)
```

`test_not_yet_due_returns_no_eligible_orders_not_zero` asserts `denominator == 0`, so a
*fully correct* compiler without `coalesce` returns `None` and fails. Both aggregates need
`coalesce(..., 0)`; that is also what makes the `CASE WHEN denominator = 0 THEN NULL`
branch reachable.

## Verified good — do not re-litigate

- Naive delivery-grain OTD: **54/61 = 88.5246%** ✅ (the relative `data/deliveries_raw.csv`
  path in the test resolves because pytest runs from the repo root; `pytest.ini` sets
  `pythonpath = .`).
- OTD IN July **48/55 = 87.2727%**, June **25/26 = 96.1538%**, drop **8.8811 → displays
  8.9pp**; headline roundings give **87.3** and **96.2** as the guide claims.
- Task 11's nested-pytest test does not recurse: `--ignore=tests/test_end_to_end.py`
  verified, rc 0, 61 passed.
- Task 11's Q2 regexes (`quality[_ ]inspection\D{0,20}4` etc.) match any sane rendering,
  underscored or humanized, colon- or space-separated.
- Baseline suite at commit 53d46c8: **61 passed in 1.64s**.

Diagnostic breakdown at order grain, IN/July, exclusions applied:

```
production_execution  1
quality_inspection    4
transportation        2
NULL                 48 on-time
```
Reconciles: 4+2+1 = 7 late, 48/55 eligible. Matches the canonical table and the
`seed_core.csv` oracle.

---

# Whole-branch review of Tasks 1–8 (all findings verified against the warehouse)

Eight artifact defects survived 27 metadata tests. Fixed in `51b6c67` and `66422ff`,
each with a test falsified against the pre-fix artifact. Canonical numbers unchanged
after rebuild: OTD IN/July 48/55, attribution 4/2/1, FPY 51/54, adherence 50/54.

| # | Defect | Fix |
|---|---|---|
| 1 | **CRITICAL** `prod_release_date` declared in `dim_process_phase` seq 3, `04_process_model.yml` `timestamp_field`, and 2 span endpoints. Fact column is `release_date`. | renamed in both artifacts + the seed row; 2 new tests check every `timestamp_field` and every span endpoint against `PRAGMA table_info` |
| 2 | `delay_attribution_phase` declared 11 `allowed_values`; SQL ranks 9 spans, so `demand_capture` / `delivery_confirmation` unreachable | 9 values in both artifacts; test compares declared to emittable |
| 3 | "phases 1–11" in 3 artifacts | restated as "the 9 variance spans (phase_seq 2–10)" |
| 4 | Q2 headline claimed 4.1 / 3.1 / 4.0 days. Measured `avg(var_qm)` = **4.75**, `available_slack_days` = **0** for all 4 | sentence corrected in contract + design; test asserts (4, 4.75, 0.0) |
| 5 | `design.md` defect-8 row named `SO-1012` (on time, `delay_days` −1, attribution NULL) | → `SO-1003`, `SO-1009` |
| 6 | `quality inspection` was a synonym of *Inspection Lot* and also the term *Quality Inspection* | removed from the lot; test intersects synonyms against term names |
| 7 | `06_dq_rules.yml:70` printed `AS_OF_DATE = 2026-08-07` | rewritten; test greps all `metadata/` + `sql/` for the literal |
| 8 | `02_standardized_metadata.json` cited `test_production_order_grain`, which never existed | test written (131/131), citation repointed |

Plus four more in `66422ff`: Delivery Date unbound from `LIKP-WADAT` (planned goods
issue, not delivery); `design.md`'s "binds to concrete SAP fields" claim restated;
FPY grain corrected from `inspection_lot` to `production_order`; re-promise behaviour
pinned (47 vs 48 — falsified by flipping the column).

## The measurement that mattered most

**Only 3 of 9 variance columns are ever positive** — `var_confirm` (1 order),
`var_qm` (4), `var_shipment` (110). The other six are positive in zero orders. So six
of the nine phase labels in the attribution CTE are **unexercised by any data-driven
test**. Proof: swapping the `goods_receipt` and `picking_packing` labels left all 95
tests green, including a reconciliation over all 132 orders — because that
reconciliation walks the same pairing the table was built from. Only
`test_attribution_sql_pairs_each_phase_with_the_declared_variance_column`, which diffs
the SQL text against `04_process_model.yml`, fails on it.

Generalization for the remaining tasks: **when data cannot exercise a branch, assert
the declaration statically.** A reconciliation invariant is strong only over the paths
the data walks.

## Open risks for Tasks 7, 9–14 (not defects — things to get right)

- **Task 7, FPY numerator.** `first_usage_decision = 'ACCEPT'` gives **51/54** ✅.
  `decision_count = 1` gives **53/54** ❌ — plausible-looking and wrong. Domain:
  `ACCEPT` 124, `REJECT` 2, `REWORK` 1, NULL 4.
- **Task 7, naive FPY 52/55.** Has **no fact-table path**: it is decision-grain over
  `inspection_lots_raw.csv` (52 ACCEPT of 55 decision rows; by qty 5200/5500 — same
  figure). Compute it from the raw CSV, as the naive 54/61 test already does, or add a
  staging view. Do not expect it from `fact_production_order`.
- **Task 7, adherence exclusion.** `fact_production_order.status` carries the *sales*
  order status (DLVD 123 / IN_TRANSIT 4 / CANC 4), not an SAP PO status.
  `is_on_schedule` is FALSE (not NULL) for the 4 confirm-less CANC rows, so an
  unexcluded query returns a plausible **123/131 = 93.89%**. The exclusion is
  load-bearing on the denominator: 55 → 54.
- **`is_eligible` is baked in at build time** against `AS_OF_DATE`, so no query can ask
  "as of another date". Acceptable for the MVP; worth one sentence in the guide as a
  known limitation rather than leaving it implicit.
- **Retriever indexing (Tasks 10/13).** `02_standardized_metadata.json`'s
  `field_mappings` covers 14 of 41 fact columns and omits **every Q1 filter column**
  (`region`, `plant`, `warehouse`, `carrier`, `order_status`).
  `03_column_bindings.yml` covers them. **Point the retriever at the bindings.**
- **`01_technical_metadata.json` has 6 `target_column`s with no warehouse column**
  (`delivery_type`, `scheduled_start_date`, `usage_decision`, `order_reason`,
  `sales_org`, `shipping_point`). Defensible for a DDIC harvest, but a retriever
  binding via `target_column` would offer nonexistent columns.
- **Build-fixture ordering.** `test_metadata.py` calls `build()` twice and
  `build(fresh=True)` once while `test_warehouse.py` holds a module-scoped read_only
  handle; `IO Error: file is already open` is reproducible if the order changes. Works
  today by file ordering. Brittle, not broken.
- **Weak assertions left in place** (`in (True, 1)`, substring greps like
  `"82.5" in text`). Deliberate: they are documented tolerances, not holes worth
  churning now.

## Ninth defect — `05_semantic_model.yml` carried the same un-emittable value

Task 5's model declares its own `delay_attribution_phase.allowed_values`, and it listed
`delivery_confirmation`. This is **the copy the `filters_bound` gate actually reads**, so
fixing the other two artifacts would not have closed the hole. Now 9 values; the emittable
test was extended to cover all three copies.

### The distinction worth teaching (Task 13)

Cross-checking every declared domain against the data turned up two *different* things:

| Dimension | Declared | In data | Verdict |
|---|---|---|---|
| `delay_attribution_phase` | 9 (was 10) | 3 | **was a defect** — the SQL structurally cannot emit the missing ones |
| `region` | IN, US, EU, APAC | IN, US | **correct as-is** — a reference domain a future load can populate |
| `carrier` | BLUEDART, FEDEX, DHL | BLUEDART, FEDEX | **correct as-is** — same |

The difference is *structural impossibility* vs *currently-empty*. Only the first belongs
out of `allowed_values`. The second is handled architecturally instead: the compiler's
`CASE WHEN denominator = 0 THEN NULL` branch means "OTD for EU" returns no number rather
than a fabricated one — which is exactly what
`test_not_yet_due_returns_no_eligible_orders_not_zero` pins for the August window. Worth
one paragraph in the guide: a declared value that cannot be produced is a lie in the
metadata; a declared value that has no rows yet is a query that must answer "none".
