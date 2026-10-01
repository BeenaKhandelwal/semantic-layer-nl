# Task 9 brief — catalog asset and provenance output

Repo: your assigned git worktree. Branch: work on the branch you are checked out on.

Read `docs/superpowers/plans/2026-08-07-semantic-layer-nl-mvp.md` **Task 9** (heading
"## Task 9: Catalog asset and provenance output") plus the **Global Constraints** section
near the top. Follow its five steps in order; the plan contains the verbatim test file.

Then read, do not assume:
- `metadata/05_semantic_model.yml` — where `lineage`, `exclusions[].key`, and the metric
  definition you render come from.
- `src/semantic/compiler.py`, `src/semantic/executor.py`, `src/semantic/dq.py` — the
  `CompiledQuery`, row shape, and `DQReport` you consume.
- `.superpowers/sdd/2026-08-07-semantic-layer-nl-mvp/preflight-findings.md`.

Build the warehouse first (`python -m src.build_warehouse`) and verify every column with
`PRAGMA table_info(...)`. Documents in this repo have named columns that do not exist.

## Files
- Create `metadata/07_catalog_asset.json`
- Create `src/semantic/provenance.py`
- Create `tests/test_provenance.py`

Do not modify anything else.

## What this task is for

An answer nobody can defend in a review is not an answer. Everything needed to challenge
the number — its arithmetic, grain, exclusions, lineage, and trust badge — must travel
with it. This module is what makes "87.3%" auditable rather than merely plausible.

## The trap that will bite you — `render()` must humanize phase keys

`test_diagnostic_answer_includes_breakdown` asserts:

```python
assert "quality inspection" in a.render().lower()      # SPACE
```

The fact column holds `quality_inspection` (**underscore**), and
`"quality inspection" in "quality_inspection"` is `False`. So printing the raw value
fails the test. **Resolve the label from `dim_process_phase.phase_name`**, which already
holds `Quality inspection` / `Transportation` / `Production execution` — verified. Do not
use a blind `str.replace("_", " ")`: the dimension is the declared source of the display
name, and reading it is what keeps the label from drifting from the model. The test
lowercases, so casing is free.

Keep the machine-readable key in `.breakdown` — only the rendered prose is humanized.
`test_diagnostic_answer_includes_breakdown` also asserts `"quality_inspection" in phases`
where `phases` comes from `.breakdown`, so both forms must coexist.

## Verified prerequisites — these are already true, build on them

- `on_time_delivery_pct` exclusion keys are exactly `cancelled_orders` and `not_yet_due`,
  which is what the test asserts as a subset.
- Its `lineage` is `["SAP SD", "SAP EWM", "SAP TM", "fact_order_delivery"]` — length 4
  with `SAP` present, satisfying `len(a.lineage) >= 3`.
- The diagnostic breakdown for IN/July, exclusions applied, is `quality_inspection` 4,
  `transportation` 2, `production_execution` 1, reconciling to 7 late of 55 eligible with
  48 on time. If you get anything else, stop — do not adjust the test.

## Non-negotiable constraints

- **`provenance.py` must not import `anthropic`.** It formats governed output; it does not
  ask a model anything.
- **`AS_OF_DATE` must not appear as a literal** in `07_catalog_asset.json` or anywhere
  else you write. `constants.py` is its only home; artifacts carry the `__AS_OF_DATE__`
  token. `test_no_metadata_artifact_hardcodes_the_as_of_date` greps all of `metadata/` and
  `sql/` for it and **will fail your commit**. An earlier task shipped exactly this
  violation.
- **`.value` stays unrounded; only the display is rounded** to one decimal. The test
  asserts `a.value == approx(87.2727, abs=0.0001)` and `"87.3" in a.headline`.
- **The catalog asset must state plainly that it does not enforce anything.**
  `test_catalog_asset_states_enforcement_limits` requires the phrase `does not enforce` or
  `not a substitute`. This is substance, not box-ticking: catalog metadata supports
  discovery and DPDP-readiness work, while enforcement lives in access control, consent
  management, retention automation, and masking. Say so.
- **Never weaken an assertion to make it pass.** If a test looks wrong, stop and report
  it. Two earlier tasks shipped code that passed all of its own tests and was still wrong.

## Definition of done

- `python -m pytest tests/test_provenance.py -v` → all pass (8 tests).
- `python -m pytest -q` → all pre-existing tests still pass plus yours. You broke nothing.
- One commit, message from the plan's Step 5.

## Report back

Write `.superpowers/sdd/2026-08-07-semantic-layer-nl-mvp/task-9-report.md` and return it
as your final message: the commit SHA, exact test counts from real output, **the full
rendered output block for Q1 and for the diagnostic Q2, pasted verbatim**, how you
resolved the display labels, and any deviation from the plan and why.

Report honestly and precisely. Do not overstate: an earlier implementer's report claimed
file sizes ~20x too large and claimed a grep was clean when it was not. Give real numbers
you actually ran, and quote command output where it matters.
