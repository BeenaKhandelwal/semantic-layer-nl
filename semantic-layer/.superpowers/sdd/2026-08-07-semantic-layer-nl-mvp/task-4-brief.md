# Task 4 brief — Metadata artifacts, phases 0 through 4

Repo: `C:\Users\legion\semantic-layer-nl`  Branch: `feat/semantic-layer-mvp`

Read `docs/superpowers/plans/2026-08-07-semantic-layer-nl-mvp.md` **Task 4** (heading
"## Task 4: Metadata artifacts — phases 0 through 4") and the **Global Constraints** section
near the top. Follow its five steps in order. The plan contains the verbatim test file and
the content requirements for each artifact.

Also read `docs/design.md` §3.3 (the 12-phase table, ~line 83) and §3.2 (the two exemplar
NL questions). Those are the source of truth for phase content and the KPI contract.

## Files
- Create `metadata/00_kpi_contract.md`
- Create `metadata/01_technical_metadata.json`
- Create `metadata/02_standardized_metadata.json`
- Create `metadata/03_glossary.yml`
- Create `metadata/03_column_bindings.yml`
- Create `metadata/04_process_model.yml`
- Create `tests/test_metadata.py`

Do not modify anything else. Specifically: do not touch `sql/`, `data/`, `src/`, or the
existing test files.

## What this task is for

These six artifacts are the demo's whole argument. Each one closes a specific way natural
language querying goes wrong, and the guide written in a later task walks through them in
order. So the content has to be genuinely useful, not decorative:

- **Phase 0 (KPI contract)** — without an agreed metric definition, two people asking the
  same question get two different numbers and neither is wrong.
- **Phase 1 (technical metadata)** — raw SAP field names are unguessable (`LIKP-WADAT_IST`
  is the actual goods-issue date). An LLM cannot resolve "when did it ship" without this.
- **Phase 2 (standardized metadata)** — declares the **grain** of each table. This is what
  prevents the split-delivery fan-out that makes on-time delivery read 88.5% instead of
  87.3%.
- **Phase 3 (glossary + bindings)** — maps human vocabulary to columns. This is the layer
  that lets "OTD in India last month" resolve at all.
- **Phase 4 (process model)** — the 12 manufacturing phases and the variance rule. This is
  what turns "why did OTD drop" from unanswerable into attributable.

Write them as artifacts a data team would actually keep, with real owners and real
definitions. Prose in `00_kpi_contract.md` should be explanatory; the machine-readable files
should be complete and consistent.

## Non-negotiable constraints

- **Durations in `04_process_model.yml` must match `dim_process_phase` in
  `sql/02_staging_model.sql` exactly** — same `phase_seq`, `phase_key`, and
  `standard_duration_days` for all 12 rows. A test compares them row by row. Read the SQL;
  do not retype the numbers from memory. Phases 1–11 sum to 12 (what `available_slack_days`
  subtracts); all 12 sum to 13, because billing follows delivery and cannot consume
  delivery slack.
- **`03_column_bindings.yml` must bind only to columns that actually exist.** Build the
  warehouse (`python -m src.build_warehouse`) and check against the real schema — there are
  40 columns on `fact_order_delivery`. Note `var_goods_issue` exists, and the QM columns are
  `qm_first_decision_date` / `qm_final_decision_date`, not `qm_decision_date`.
- **No placeholders.** A test greps every artifact for `TBD`, `TODO`, `FIXME`, `XXX`,
  `<placeholder>`. Every field needs a real value. If you genuinely cannot determine an
  owner, use a plausible role name (e.g. "Supply Chain Analytics Lead") rather than a stub.
- **Synonyms are load-bearing, not filler.** `Region` must map "India"/"india"/"IN";
  `On-Time Delivery %` must map "OTD"/"on time delivery"/"delivery performance". A later
  task's retriever matches user phrasing against exactly these lists.
- **`AS_OF_DATE` (2026-08-07) must not appear as a literal in any metadata file.** It lives
  only in `src/semantic/constants.py`. If an artifact needs to reference the demo's "today",
  describe it as `AS_OF_DATE` by name.
- **Never weaken an assertion to make it pass.** If a test looks wrong, stop and say so in
  your report rather than editing it.

## Definition of done

- `python -m pytest tests/test_metadata.py -v` → all pass.
- `python -m pytest -q` → 34 existing tests still pass plus the new ones. You broke nothing.
- `grep -rn "2026-08-07" metadata/` → no matches.
- One commit, message from the plan's Step 5.

## Report back

Write `.superpowers/sdd/2026-08-07-semantic-layer-nl-mvp/task-4-report.md` and return it as
your final message: what each artifact contains, the commit SHA, test counts, how you
verified the durations and bindings against the warehouse rather than from memory, any
deviation from the plan and why, and anything that looked wrong in the plan, the SQL, or the
design doc. Report honestly — if something does not pass, say so plainly.
