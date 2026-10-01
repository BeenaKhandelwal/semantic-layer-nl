# Task 3 brief — DuckDB warehouse with order-grain fact table

Repo: `C:\Users\legion\semantic-layer-nl`  Branch: `feat/semantic-layer-mvp`

Read `docs/superpowers/plans/2026-08-07-semantic-layer-nl-mvp.md` **Task 3** (starts at the
heading "## Task 3: DuckDB warehouse with order-grain fact table") and the **Global
Constraints** section near the top. Follow Task 3's five steps in order — it contains the
verbatim test file, the SQL skeleton, and `build_warehouse.py` in full.

## Files
- Create `sql/02_staging_model.sql`
- Create `src/build_warehouse.py`
- Create `tests/test_warehouse.py`

Do not modify anything else. In particular: never edit `data/*.csv`, `data/generate.py`,
`src/semantic/constants.py`, or `tests/test_data.py`.

## What this task is for

This is the layer the whole demo rests on. A natural-language question like "why did on-time
delivery drop last month" gets answered by a deterministic SQL compiler reading this fact
table. Two properties matter more than anything else:

1. **`fact_order_delivery` is exactly one row per `order_id`.** Six IN/July orders have two
   delivery legs. If those fan out into extra rows, on-time delivery computes as 54/61 =
   88.5% instead of the correct 48/55 = 87.3% — a wrong answer that looks plausible enough
   to ship. Collapse deliveries to order grain with `max(delivery_date)` *before* joining.
2. **Left joins throughout.** `SO-1015` is make-to-stock with no production order. It must
   survive as a complete, eligible, on-time row with NULL manufacturing columns.

## Non-negotiable constraints

- **`AS_OF_DATE` (2026-08-07) appears as a literal in exactly one place in this repo:
  `src/semantic/constants.py`.** In SQL, write the `__AS_OF_DATE__` token;
  `build_warehouse.py` substitutes it. Do not type the date anywhere in `sql/` or `src/`.
  (Test files may use date literals freely — `tests/test_warehouse.py` does.)
- **No wall-clock, no randomness.** Never `date.today()`.
- **Never weaken an assertion to make it pass.** The numbers in the tests are verified
  arithmetic that ten later tasks depend on. If `test_in_july_eligibility_and_ontime`
  returns anything but `(55, 48)`, your SQL is wrong — fix the SQL. Same for the
  `test_attribution_matches_oracle` dict, which I have separately confirmed matches
  `data/seed_core.csv`. If you become convinced a test itself is wrong, **stop and say so
  in your report** rather than editing it.
- `is_eligible` excludes cancelled orders AND orders promised after `AS_OF_DATE`
  (not-yet-due ≠ late). `SO-1007` (cancelled) and `SO-1013` (promised 2026-08-12) are both
  ineligible.
- `qm_first_decision_date` uses `decision_seq = 1` only; `qm_final_decision_date` uses the
  max. `SO-1004`/lot `QL-4004` has REWORK then ACCEPT — first 2026-07-11, final 2026-07-14.
  First-pass yield later depends on this distinction.
- `available_slack_days` subtracts **12** = Σ standard duration for `phase_seq <= 11`.
  Billing (phase 12) is excluded: it happens after delivery and cannot consume delivery
  slack. All 12 phases sum to 13 — 12 is deliberate, comment it so nobody "corrects" it.
- `delay_attribution_phase` = phase with the largest positive variance, computed **only**
  when `is_eligible AND NOT is_on_time AND is_delivered`, else NULL. Ties break to the
  earliest phase; state that in a comment.
- `dim_process_phase` is a literal `VALUES` table of all 12 phases. Take
  `phase_seq, phase_name, sap_module, business_event, timestamp_field,
  standard_duration_days` from the 12-row table in `docs/design.md` §3.3 (around line 83).
  Add a snake_case `phase_key` (e.g. `quality_inspection`, `transportation`,
  `production_execution`) — these must match the `delay_attribution_phase` values the
  oracle test expects.

## Definition of done

- `python -m pytest tests/test_warehouse.py -v` → 10 passed.
- `python -m pytest -q` → all 27 pass (17 existing + 10 new). You broke nothing.
- `grep -rn "2026-08-07" sql/ src/` → no matches.
- `warehouse.duckdb` is git-ignored already; do not commit it. Do not add it to
  `.gitignore` again.
- One commit, message from the plan's Step 5.

## Report back

Write `.superpowers/sdd/2026-08-07-semantic-layer-nl-mvp/task-3-report.md` and also return it
as your final message: what you built, the commit SHA, test counts, the actual
`(eligible, on_time)` tuple you observed, any place you deviated from the plan and why, and
anything that looked wrong in the plan or the data. Report honestly — if something does not
pass, say so plainly rather than describing it as passing.
