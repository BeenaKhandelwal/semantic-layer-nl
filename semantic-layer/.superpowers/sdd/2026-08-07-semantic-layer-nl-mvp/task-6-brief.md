# Task 6 brief — QueryIntent schema and the 7-gate validator

Repo: your assigned git worktree. Branch: work on the branch you are checked out on.

Read `docs/superpowers/plans/2026-08-07-semantic-layer-nl-mvp.md` **Task 6** (heading
"## Task 6: QueryIntent schema and the 7-gate validator") plus the **Global Constraints**
section near the top. Follow its five steps in order. The plan contains the verbatim test
file and the exact gate semantics.

Also read `metadata/05_semantic_model.yml` and `src/semantic/loader.py` — they were just
built by Task 5 and are what your gates read. Read them; do not assume their shape.

## Files
- Create `src/semantic/intent.py`
- Create `src/semantic/validator.py`
- Create `tests/test_validator.py`

Do not modify anything else. In particular do not edit `metadata/05_semantic_model.yml` or
`src/semantic/loader.py`. If a gate cannot be implemented because the semantic model is
missing a declaration, **stop and report it** rather than editing the model to suit your
gate.

## What this task is for

These 7 gates are the whole trust story. The resolver is an LLM and will sometimes be
wrong; the gates are what turn "confidently wrong number" into "structured refusal naming
the failed gate". A gate that cannot reject is decoration.

## The subtlety that matters most — reachability

`fact_production_order` carries **no `region` column and no `promised_delivery_date`
column** (verify: `PRAGMA table_info('fact_production_order')`). Both production metrics
must still filter on `region` and window on `promised_delivery_date`, which they reach via
a declared `many_to_one` join to `fact_order_delivery`.

So gates 2, 3 and 5 resolve dimensions by **reachability**, not by "lives on this entity":

- A dimension is valid if it sits on the metric's entity **or** on an entity the metric's
  entity declares a join `to`.
- `no_fanout` rejects **only** the `one_to_many` hop (`delivery_id` via `raw_deliveries`).
  A `many_to_one` hop does not fan out and **must pass**.

**This is the trap:** a `no_fanout` gate that blocks every join passes all 12 of the
original tests while silently breaking 2 of the 3 metrics. That is why the plan adds 5
cases asserting `many_to_one` PASSES and `one_to_many` still fails. Both directions are
required. Do not implement the gate as "any join → reject".

## Non-negotiable constraints

- **`validator.py` must not import `anthropic`.** There is a test asserting this by source
  inspection. The gates are pure functions over YAML.
- **Never raise on invalid input.** Always return a `ValidationResult`. A hallucinated
  metric name is a normal, expected input to this function.
- **`extra="forbid"` on the Pydantic models**, so a hallucinated extra field is a parse
  error rather than silently ignored.
- **Gate names exactly:** `metric_approved`, `dimensions_declared`, `filters_bound`,
  `grain_matches`, `no_fanout`, `time_window_bounded`, `exclusions_applied`. Downstream
  code and the guide refer to these strings.
- **All 7 gates always run and all 7 appear in `gate_results`** — `len(r.gate_results) == 7`
  is asserted. Do not short-circuit on first failure; a user deserves every reason at once.
- **Failure messages must name the offending value**, not just the gate. There is a test
  that the string `"nope"` appears in the message for metric `"nope"`.
- **Never weaken an assertion to make it pass.** If a test looks wrong, stop and say so in
  your report. Two earlier tasks in this project shipped code that passed every one of its
  tests and was still wrong.

## Definition of done

- `python -m pytest tests/test_validator.py -v` → all pass (17 tests: 12 gate tests plus
  the 5 reachability cases).
- `python -m pytest -q` → every pre-existing test still passes plus yours. You broke nothing.
- One commit, message from the plan's Step 5.

## Report back

Write `.superpowers/sdd/2026-08-07-semantic-layer-nl-mvp/task-6-report.md` and return it
as your final message: each gate and how it decides, the commit SHA, exact test counts,
**how you verified the many_to_one hop passes while the one_to_many hop fails** (show the
actual test output), any deviation from the plan and why, and anything that looked wrong in
the plan or in Task 5's semantic model.

Report honestly and precisely. Do not overstate: a previous implementer's report claimed
file sizes ~20x too large and claimed a grep was clean when it was not. Give real numbers
you actually ran, and quote command output where it matters.

---

## Addendum — findings from the Tasks 1–4 review (all measured, not guessed)

**`delay_attribution_phase` declares 11 allowed values but the warehouse can only emit 9.**
`02_standardized_metadata.json` and `03_glossary.yml` both list `demand_capture` …
`delivery_confirmation` (11 values). The attribution SQL ranks only 9 spans, `phase_seq`
2–10, so `demand_capture` and `delivery_confirmation` are **unreachable**. Verified:

```
SELECT delay_attribution_phase, count(*) FROM fact_order_delivery GROUP BY 1
-> NULL 121, transportation 6, quality_inspection 4, production_execution 1
```

Consequence for you: if gate 3 (`filters_bound`) validates a filter *value* against
`allowed_values`, it will accept `delay_attribution_phase = 'demand_capture'` and the
pipeline will return **0 rows presented as a valid answer** — exactly the failure mode the
gates exist to prevent. I am fixing the two metadata files to 9 values on the main branch
in parallel with your task. **Do not edit those files.** Just make sure your gate reads
`allowed_values` from the artifact rather than hard-coding a list, so the fix reaches you
on merge.

If `05_semantic_model.yml` carries its own copy of the attribution values, report the
discrepancy — do not reconcile it yourself.
