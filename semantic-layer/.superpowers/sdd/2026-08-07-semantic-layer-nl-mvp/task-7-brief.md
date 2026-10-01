# Task 7 brief — the deterministic SQL compiler

Repo: your assigned git worktree. Branch: work on the branch you are checked out on.

Read `docs/superpowers/plans/2026-08-07-semantic-layer-nl-mvp.md` **Task 7** (heading
"## Task 7: Deterministic SQL compiler") plus the **Global Constraints** section near the
top. Follow its steps in order; the plan contains the verbatim test file.

Then read, do not assume:
- `metadata/05_semantic_model.yml` and `src/semantic/loader.py` — what you compile from.
- `src/semantic/intent.py` — the `QueryIntent` / `Filter` shapes you consume.
- `.superpowers/sdd/2026-08-07-semantic-layer-nl-mvp/preflight-findings.md` — measured
  numbers and the traps below, all verified against the built warehouse.

Build the warehouse first (`python -m src.build_warehouse`) and verify every column you
reference with `PRAGMA table_info(...)`. Several documents in this repo have named columns
that do not exist; one of them cost a critical defect.

## Files
- Create `src/semantic/compiler.py`
- Create `tests/test_compiler.py`

Do not modify anything else. If the semantic model is missing something you need, **stop
and report it** rather than editing the model to suit the compiler.

## What this task is for

The LLM chooses *which* governed metric and filters. This module writes the arithmetic.
That split is the entire trust argument: if the compiler is deterministic and reads its
expression from approved metadata, then a wrong answer is a metadata bug with an owner,
not a model that hallucinated a formula. Do not accept a metric expression from the
intent; look it up by name.

## Traps, all measured — do not rediscover these the hard way

**1. Production metrics reach `region` and `promised_delivery_date` only through a join.**
`fact_production_order` has 15 columns and **neither**. Verified:

| Windowing choice | FPY | Adherence |
|---|---|---|
| `promised_delivery_date` via join to `fact_order_delivery` | **51/54** ✅ | **50/54** ✅ |
| `scheduled_finish_date` on the fact itself | 42/45 ❌ | 42/45 ❌ |

The join is `many_to_one` and verified non-fan-out (131 production orders over 131
distinct `order_id`s). Emit it **only when the query actually needs a column from the
other entity** — an unconditional join is a different bug. The plan asks you to assert
`denominator != 45`; keep that assertion.

**2. FPY numerator is `first_usage_decision = 'ACCEPT'`, giving 51/54.**
`decision_count = 1` gives **53/54** — plausible and wrong. Domain of
`first_usage_decision`: `ACCEPT` 124, `REJECT` 2, `REWORK` 1, NULL 4.

**3. The naive FPY figure 52/55 has no fact-table path.** It is decision-grain over
`data/inspection_lots_raw.csv` (52 `ACCEPT` of 55 decision rows in the cohort; by
quantity 5200/5500, the same 94.5455%). Compute it from the raw CSV the way the existing
naive 54/61 test does. Do not expect `fact_production_order` to produce it.

**4. `SUM()` over an empty result set returns `NULL`, not `0`.** The August window
matches zero rows — all 4 IN/August orders fall to the `not_yet_due` exclusion. Raw, that
returns `(None, None, 0)`. `test_not_yet_due_returns_no_eligible_orders_not_zero` asserts
`denominator == 0`, so a *fully correct* compiler without `coalesce(..., 0)` on **both**
aggregates fails. Coalescing is also what makes the `CASE WHEN denominator = 0 THEN NULL`
branch reachable.

**5. The cancelled exclusion is load-bearing on the denominator.** Without it the IN/July
production cohort is 55, not 54. Note `fact_production_order.status` carries the *sales*
order status (DLVD 123 / IN_TRANSIT 4 / CANC 4) and `is_on_schedule` is FALSE — not NULL —
for the 4 confirm-less CANC rows, so an unexcluded adherence query returns a
plausible-looking **123/131 = 93.89%**.

## Non-negotiable constraints

- **`compiler.py` must not import `anthropic`.** It is a pure function from validated
  intent + metadata to SQL. There is a test asserting this by source inspection.
- **`AS_OF_DATE` must not appear as a literal** in any file you write. `constants.py` is
  the only place that value lives; SQL and YAML carry the `__AS_OF_DATE__` token. A test
  now greps `metadata/` and `sql/` for the literal — do not add a new home for it.
- **Every exclusion in the metric's `exclusions` list must be applied**, and the compiler
  must be able to report *which* it applied, because the `exclusions_applied` gate and the
  provenance block both cite them.
- **Never weaken an assertion to make it pass.** If a test looks wrong, stop and say so.
  Two earlier tasks shipped code that passed all of its tests and was still wrong.

## Definition of done

- `python -m pytest tests/test_compiler.py -v` → all pass (21 tests per the plan).
- `python -m pytest -q` → all pre-existing tests still pass plus yours. Baseline is
  **98 passed**. You broke nothing.
- One commit, message from the plan's final step.

## Report back

Write `.superpowers/sdd/2026-08-07-semantic-layer-nl-mvp/task-7-report.md` and return it
as your final message: the commit SHA, exact test counts from real output, the SQL your
compiler emits for Q1 and for FPY (paste it), how you verified the join is emitted only
when needed, and any deviation from the plan and why.

Report honestly and precisely. Do not overstate: an earlier implementer's report claimed
file sizes ~20x too large and claimed a grep was clean when it was not. Give real numbers
you actually ran, and quote command output where it matters.
