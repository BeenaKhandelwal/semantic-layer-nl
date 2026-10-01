# Task 10 brief — retriever and golden intents

Repo: your assigned git worktree. Branch: work on the branch you are checked out on.

Read `docs/superpowers/plans/2026-08-07-semantic-layer-nl-mvp.md` **Task 10** (heading
"## Task 10: Retriever and golden intents") plus the **Global Constraints** section near
the top. Follow its steps in order; the plan contains the verbatim test file.

Then read, do not assume:
- `metadata/05_semantic_model.yml`, `metadata/03_glossary.yml`,
  `metadata/04_process_model.yml` — what you assemble context from.
- `src/semantic/intent.py` — the `QueryIntent` shape `golden_intent()` must return.
- `.superpowers/sdd/2026-08-07-semantic-layer-nl-mvp/preflight-findings.md`.

## Files
- Create `src/semantic/retriever.py`
- Create `tests/golden_intents.json`
- Create `tests/test_retriever.py`

Do not modify anything else. In particular do not edit the metadata artifacts; if the
context you need is missing from them, **stop and report it**.

## What this task is for

The resolver is the only LLM in the pipeline, and it can only choose among things it was
shown. What you put in the context window *is* the model's universe of possible answers.
Omit a filter column and the resolver cannot use it; include a metric that is not
approved and you have handed it a way to be confidently wrong. The golden intents are the
offline path: they are what lets the whole pipeline be tested and demoed with no API key.

## Verified facts — build on these, do not rediscover them

- **`OTD` lives in the glossary, not the semantic model.** No metric in
  `05_semantic_model.yml` has a `synonyms` key (verified: all three are `None`).
  `03_glossary.yml`'s *On-Time Delivery %* term carries
  `['OTD', 'on time delivery', 'on-time delivery', 'delivery performance',
  'delivery reliability', 'promise adherence', 'OTIF', 'on time in full']`. So
  `test_context_includes_synonyms_so_model_can_map_vocabulary` passes only if you pull
  synonyms from the **glossary**. Join the two sources by term/metric name.
- **Point the retriever at `03_column_bindings.yml`, not
  `02_standardized_metadata.json`'s `field_mappings`.** Measured: `field_mappings` covers
  14 of 41 `fact_order_delivery` columns and omits **every Q1 filter column** — `region`,
  `plant`, `warehouse`, `carrier`, `order_status`. The bindings cover them. A retriever
  built on `field_mappings` cannot resolve "India warehouses" at all.
- `05_semantic_model.yml`'s `dimensions` carry `allowed_values`: `region` is
  `['IN','US','EU','APAC']`, so `"IN" in ctx` is satisfiable from there.
- `delay_attribution_phase` has exactly **9** allowed values (phase_seq 2–10).
  `demand_capture` and `delivery_confirmation` are **not emittable** — the attribution SQL
  structurally cannot produce them. Do not re-add them to anything, and if you surface the
  domain in the context, surface the 9.
- `04_process_model.yml` phase 3's `timestamp_field` is `release_date` (it briefly said
  `prod_release_date`, which is not a column). If you read `timestamp_field`, verify each
  against `PRAGMA table_info('fact_order_delivery')` rather than trusting the file.

## The AS_OF_DATE subtlety

`test_context_includes_as_of_date_for_relative_dates` asserts `"2026-08-07" in ctx`. That
is correct and not a violation: the context is built **at runtime** from
`constants.AS_OF_DATE`, and "last month" is unresolvable without a stated as-of date. What
is forbidden is writing the literal into a **file**. So:

- Import `AS_OF_DATE` from `src.semantic.constants` and format it into the context string.
- **Do not** write `2026-08-07` into `tests/golden_intents.json` or `retriever.py`.
  `test_no_metadata_artifact_hardcodes_the_as_of_date` scans `metadata/` and `sql/`; your
  files are outside that scan, but the Global Constraint applies to the whole repo and a
  reviewer will flag it. If `golden_intents.json` needs the July window, write the July
  dates (`2026-07-01` / `2026-07-31`) — those are the *question's* window, not the as-of
  date, and they are legitimately literal.

## Golden intents must match the real cohort

`Q1` → `on_time_delivery_pct`, grain `order`, filter `region = 'IN'`, July 2026,
`intent_type: descriptive`, expected **87.2727** (48/55).
`Q2` → same metric and filters, plus dimension `delay_attribution_phase`,
`intent_type: diagnostic`, expected breakdown `quality_inspection` 4, `transportation` 2,
`production_execution` 1 — reconciling to 7 late of 55 eligible.

If your intents produce anything else when compiled, the intent is wrong. Do not adjust
the expected values.

## Non-negotiable constraints

- **`retriever.py` must not import `anthropic`.** It assembles text from YAML; it does not
  call a model. The resolver (Task 12) is the only module that may.
- **The context must not include unapproved metrics.** Filter on
  `approval_state == "approved"`. Handing the resolver an unapproved metric is handing it a
  way to produce a governed-looking number nobody signed off on.
- **Never weaken an assertion to make it pass.** If a test looks wrong, stop and report
  it. Two earlier tasks shipped code that passed all of its own tests and was still wrong.

## Definition of done

- `python -m pytest tests/test_retriever.py -v` → all pass (the plan's full test list).
- `python -m pytest -q` → all pre-existing tests still pass plus yours. You broke nothing.
- One commit, message from the plan's final step.

## Report back

Write `.superpowers/sdd/2026-08-07-semantic-layer-nl-mvp/task-10-report.md` and return it
as your final message: the commit SHA, exact test counts from real output, **the full
context string `build_context` produces for Q1, pasted verbatim** (this is the single most
reviewable artifact of the task — it is literally what the model will see), which files
you drew each part of it from, and any deviation from the plan and why.

Report honestly and precisely. Do not overstate: an earlier implementer's report claimed
file sizes ~20x too large and claimed a grep was clean when it was not. Give real numbers
you actually ran, and quote command output where it matters.
