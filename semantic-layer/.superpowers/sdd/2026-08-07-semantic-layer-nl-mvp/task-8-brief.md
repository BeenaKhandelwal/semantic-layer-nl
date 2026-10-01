# Task 8 brief — Data-quality contract and trust badge

Repo: your assigned git worktree. Branch: work on the branch you are checked out on.

Read `docs/superpowers/plans/2026-08-07-semantic-layer-nl-mvp.md` **Task 8** (heading
"## Task 8: Data-quality contract and trust badge") plus the **Global Constraints**
section near the top, and `docs/design.md` §6.1 (the six DQ rules table) and §5.3 (the
eight deliberate defects). Follow the plan's five steps in order. It contains the verbatim
test file.

## Files
- Create `metadata/06_dq_rules.yml`
- Create `src/semantic/dq.py`
- Create `tests/test_dq.py`

Do not modify anything else. Another agent is concurrently creating
`metadata/05_semantic_model.yml`, `src/semantic/loader.py`, `tests/test_loader.py` — stay
out of those three files entirely. **Do not import `loader` or `05_semantic_model.yml`**;
your module depends only on the warehouse and your own YAML. That independence is why
these two tasks can run in parallel, so preserve it.

## What this task is for

Every answer the system gives carries a trust badge. The point is that a failing rule
degrades **a specific metric's answer**, not a dashboard-wide red light — so each rule is
bound to the metric inputs it protects. A `BLOCKED` input must return a refusal, never a
number.

## Non-negotiable constraints

- **`AS_OF_DATE` (2026-08-07) must not appear as a literal in your YAML.** The timeliness
  rule needs the demo's "today": use the token `__AS_OF_DATE__` in the SQL and have
  `dq.py` substitute `AS_OF_DATE` from `src/semantic/constants.py`, exactly as
  `src/build_warehouse.py` already does for `sql/02_staging_model.sql`. Read that file and
  copy the pattern.
- **The completeness rule must be scoped, not blanket.** `SO-1013` is legitimately null:
  in transit, promised after the as-of date. A blanket NOT NULL check wrongly fails it.
  Scope to eligible, past-due orders. There is a test for this.
- **Every rule's `sql` returns a single column named `observed`**; `comparison` is `lte`
  or `gte` against `threshold`.
- **All 6 dimensions, exactly:** completeness, validity, uniqueness, timeliness,
  consistency, accuracy.
- **`defect_demonstrated` across the six rules must collectively name all 8 defect keys**
  the parametrized test lists: `cancelled_order`, `in_transit_null`, `rework_loop`,
  `split_delivery`, `repromised_date`, `make_to_stock_no_prod_order`,
  `qm_dominated_delay`, `non_qm_delay`.
- **`run_rules` signature is `run_rules(metric_name=None, db_path=None, rules_path=None)`.**
  The `rules_path` parameter is required by the forced-failure test.
- **Verify column names against the built warehouse** (`python -m src.build_warehouse`),
  do not retype from the design doc. The design doc's §6.1 says `delivery_timestamp` and
  `release_date <= gr_date <= goods_issue_date <= delivery_date`; the actual columns are
  `final_delivery_date`, `release_date`, `gr_date`, `goods_issue_date`. Use the real ones
  and note the discrepancy in your report.
- **Never weaken an assertion to make it pass.** If a test looks wrong, stop and say so in
  your report rather than editing it.

## A caution specific to this task

The rules must **pass on the clean warehouse** (`test_clean_warehouse_is_trusted` asserts
badge `TRUSTED`), while still being strict enough to catch a real regression. A rule
written as `SELECT 0.0 AS observed` passes every test and protects nothing. Each rule's
SQL must genuinely measure the thing its dimension names, against real columns. After
writing each rule, prove it can fail: run its SQL against deliberately corrupted input (a
temp DuckDB view, or a modified copy — do not mutate the committed CSVs or the shared
warehouse) and confirm the observed value crosses the threshold. Report what you did to
prove each rule bites.

## Definition of done

- `python -m pytest tests/test_dq.py -v` → all pass.
- `python -m pytest -q` → the 61 existing tests still pass plus yours. You broke nothing.
- `grep -rn "2026-08-07" metadata/` → no matches.
- One commit, message from the plan's Step 5.

## Report back

Write `.superpowers/sdd/2026-08-07-semantic-layer-nl-mvp/task-8-report.md` and return it
as your final message: each rule and what it measures, the commit SHA, exact test counts,
**how you proved each rule can actually fail**, how you verified column names against the
built warehouse, any deviation from the plan and why, and anything that looked wrong in the
plan, the SQL, or the design doc.

Report honestly and precisely. Do not overstate: a previous implementer's report claimed
file sizes ~20x too large and claimed a grep was clean when it was not. Give real numbers
you actually ran, and quote command output where it matters.
