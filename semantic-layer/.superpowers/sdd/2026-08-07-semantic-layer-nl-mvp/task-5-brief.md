# Task 5 brief — Semantic model with 3 governed metrics + loader

Repo: your assigned git worktree. Branch: work on the branch you are checked out on.

Read `docs/superpowers/plans/2026-08-07-semantic-layer-nl-mvp.md` **Task 5** (heading
"## Task 5: Semantic model with 3 governed metrics") plus the **Global Constraints**
section near the top. Follow its five steps in order. The plan contains the verbatim test
file and the required YAML shape.

## Files
- Create `metadata/05_semantic_model.yml`
- Create `src/semantic/loader.py`
- Create `tests/test_loader.py`

Do not modify anything else. Specifically: do not touch `sql/`, `data/`, other
`metadata/` files, or existing test files. Another agent is working on
`metadata/06_dq_rules.yml`, `src/semantic/dq.py`, `tests/test_dq.py` concurrently — stay
out of those.

## What this task is for

This file is the single definition of every metric. BI and NL querying both read it, so a
number cannot drift between a dashboard and a chat answer. Everything downstream — the 7
validator gates, the SQL compiler, the provenance block — is driven by what you declare
here. If a metric's grain, exclusions, or time dimension are wrong here, the whole
pipeline is confidently wrong.

## The defect that was just fixed in the plan — read this carefully

`fact_production_order` has **no `region` column and no `promised_delivery_date` column.**
Verify this yourself: `PRAGMA table_info('fact_production_order')`.

Both production metrics (`first_pass_yield_pct`, `mfg_schedule_adherence_pct`) must still
be filterable by `region` and windowed on `promised_delivery_date`, because that is what
produces the certified numbers. That only works through a declared `many_to_one` join to
`fact_order_delivery`. So:

- Declare the `fact_production_order` entity **with** that join. The plan gives you the
  exact YAML.
- Set `time_dimension: promised_delivery_date` on **both** production metrics.
- **Do not** use `scheduled_finish_date` as the time dimension. It is the intuitive choice
  given the columns present, and it is wrong — it returns 42/45 instead of 51/54 and
  50/54. I verified both numbers against the built warehouse.

## Non-negotiable constraints

- **`AS_OF_DATE` (2026-08-07) must not appear as a literal in any YAML.** The
  `not_yet_due` exclusion carries the token `__AS_OF_DATE__`; the loader/compiler
  substitutes it. It lives as a literal only in `src/semantic/constants.py`.
- **Verify every column you reference exists.** Build the warehouse
  (`python -m src.build_warehouse`) and check against the real schema. 40 columns on
  `fact_order_delivery`, 15 on `fact_production_order`. Note the QM columns are
  `qm_first_decision_date` / `qm_final_decision_date` — there is no `qm_decision_date`.
  FPY reads `first_usage_decision`, which is already materialized.
- **`delivery_id` must be declared** as a dimension on entity `raw_deliveries` (the
  `one_to_many` join) with `queryable_at_grain: delivery`. It exists so the `no_fanout`
  gate has a legitimate thing to reject. Without it that gate is untestable and the
  fan-out protection is theatre.
- **No placeholders.** No `TBD`, `TODO`, `FIXME`, `XXX`. Real owners and stewards.
- **Never weaken an assertion to make it pass.** If a test looks wrong, stop and say so
  in your report rather than editing it. Two earlier tasks in this project shipped code
  that passed every test and was still wrong; assertions are the only defence.

## Definition of done

- `python -m pytest tests/test_loader.py -v` → all pass (10 tests).
- `python -m pytest -q` → the 61 existing tests still pass plus yours. You broke nothing.
- `grep -rn "2026-08-07" metadata/` → no matches.
- One commit, message from the plan's Step 5.

## Report back

Write `.superpowers/sdd/2026-08-07-semantic-layer-nl-mvp/task-5-report.md` and return it
as your final message: what you declared, the commit SHA, exact test counts, how you
verified column names and the join cardinality against the built warehouse rather than
from memory, any deviation from the plan and why, and anything that looked wrong in the
plan or the SQL.

Report honestly and precisely. Do not overstate: a previous implementer's report claimed
file sizes ~20x too large and claimed a grep was clean when it was not. Give real numbers
you actually ran, and quote the command output where it matters.
