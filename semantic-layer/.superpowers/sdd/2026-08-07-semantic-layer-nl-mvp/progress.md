# SDD ledger — plan: docs/superpowers/plans/2026-08-07-semantic-layer-nl-mvp.md

Branch: feat/semantic-layer-mvp
Merge base: 7d2f054 (master)
Spec: docs/design.md

## Progress

Pre-flight: fixed 4 plan defects (AS_OF_DATE duplicated into YAML; test_gate_no_fanout
set-intersection assert; test_q2 bare "4" assert; test_guide bare "48"/"55" assert) — commit 92c9d15.

Task 1: complete (commits 92c9d15..5303eca, review clean — spec ✅, quality Approved, 0 Critical/Important)
Task 1: minor (deferred): test_data.py string-compares ISO dates rather than parsing them
Task 1: minor (deferred): _seed_rows() re-reads CSV per test instead of using a fixture
Task 1: note — implementer added .gitattributes (*.csv text eol=lf); reviewer judged justified, it enforces the LF constraint on Windows
Task 1: plan fix — SO-1019 oracle column reconciled (plan CSV contradicted its own test); commit 72b693b

Task 2: complete (commits 72b693b..a9c39a0, review — spec ✅ all 12 reqs, quality Approved,
0 Critical, 2 Important both fixed in a9c39a0)
Task 2: fixed — AS_OF_DATE literal restated at generate.py:182 and :565; now derived from the
constant. CSVs verified byte-identical before/after via md5sum (randint range is unchanged).
Task 2: fixed — no .gitignore existed, 5 __pycache__ .pyc files were tracked; untracked and
ignored, plus warehouse.duckdb ahead of Task 3.
Task 2: fixed (found while verifying) — .gitattributes only covered *.csv, but core.autocrlf=true
is set globally, so a fresh checkout would write CRLF .py/.yaml and change Task 9's metadata
hashes. Extended to py/yaml/yml/sql/md/json.
Task 2: verified independently — all 5 window compositions exact; naive delivery-grain
54/61 = 88.5246%; adherence 50/54 = 92.5926%; FPY 51/54 = 94.4444%; QL-4004 REWORK→ACCEPT;
SO-1015 absent from production orders; 17 tests pass.

Pre-flight T3: fixed 3 plan defects (is_eligible bullet printed the AS_OF_DATE literal it
forbade; test_build_is_idempotent would deadlock on DuckDB's read_only fixture handle;
available_slack_days' "-12" was miscommented as the sum of all 12 phases, which is 13) — 25e52c8.

Task 3: complete (commits 25e52c8..d7da9b0, 34 tests pass, all canonical numbers hold:
132 rows, IN Jul 55/48, IN Jun 26/25, attribution QM 4 / transport 2 / production 1)
Task 3: implementer's commit 02c57d6 passed all 9 of its tests but was correct only by luck.
Attribution was 9 copies of an 8-branch GREATEST with durations retyped as literals in each;
7 of 9 had production_execution and quality_inspection standards swapped, so the guard scored
an order differently from the branch that named the phase. A 5-day production gap would have
returned NULL ("no cause found"); the seeded case had a 7-day gap and won either way.
Root cause: end-anchored var_* names given start-anchored definitions. Rewrote as one unpivot
+ row_number() argmax reading dim_process_phase (443→297 lines, 0 GREATEST) — 20899af.
Task 3: second defect found by reviewing my own rewrite — the chain had an unowned span
(goods issue → dispatch), so 123 delivered orders failed "sum(var) = elapsed − standard" and a
dispatch hold would attribute to nothing. Added var_goods_issue, redefined var_shipment to
start at goods issue, std_shipment now absorbs the 0-day POD phase — d7da9b0.
Task 3: also fixed — invoice_date was a fabricated TIMESTAMP (delivery+1) contradicting the
seed's own values (delivery+2); no raw extract has a billing document, so it is now explicitly
modeled from dim_process_phase and commented as modeled, not measured.
Task 3: also fixed — build() could not drop objects the SQL stopped declaring (DuckDB persists
to a file), and a stale phase_standard view made 3 tests pass that should have failed. Added
build(fresh=True), used by the fixture.
Task 3: practice that worked — every new regression test was falsified against the prior SQL
on a clean DB before committing (4 of 7 failed; contiguity test reported 123 failing orders).
Task 3: reviewer finding NOT accepted — phase_standard CROSS JOIN called a Critical grain risk.
An aggregate with no GROUP BY returns exactly 1 row even over empty input; verified.
Task 3: lesson for later tasks — "all tests pass" proved nothing here twice. Reconciliation
invariants (sum of parts = whole) caught what per-case assertions could not. Prefer them.

Pre-flight T4: fixed plan defect — test_process_model_standard_durations_sum_to_12 asserted 12
over all 12 phases while Step 3 listed durations summing to 13, so the test would have failed
against the artifact the same task specifies. Split into 1-11=12 and all-12=13, and added a
row-by-row comparison against dim_process_phase — 10de584.

Task 4: complete (commits 10de584..b0beea9, 61 tests pass)
Task 4: implementer's 684d46a passed all 20 of its tests; content review found 6 defects.
Task 4: fixed — 'PO' was a synonym of BOTH Sales Order and Production Order, and 'location' of
both Region and Plant, so the resolver would silently pick one. Also 'purchase order'/'PO' were
listed under Sales Order: in SAP that is a procurement doc (EKKO), not VBAK — 8cffc41.
Task 4: fixed — 34 of 46 bindings referenced terms absent from the glossary, unreachable by NL.
Added scope: business|internal rather than inventing 34 business terms (which would widen the
resolver's guess space without answering any real question) — 8cffc41.
Task 4: fixed — both exemplar questions said "last month" without pinning the date column.
order_date gives 33/40 = 82.50% vs the governed 48/55 = 87.27%: wrong by 4.8pp with nothing in
the number to reveal it. Contract now tabulates all three readings — b0beea9.
Task 4: fixed — 01_technical_metadata.json mapped QALS-VDATUM to qm_decision_date, a column
that does not exist; the model splits it by decision_seq into first/final — b0beea9.
Task 4: fixed — 04_process_model.yml documented the attribution rule but not how durations are
measured. Added a variances block (9 columns, spans, END-ANCHORED convention) with a test that
checks it against the fact table, asserts span contiguity, and requires the standards to sum
to the warehouse's 12 — b0beea9.
Task 4: fixed — Production Cycle Time listed beside 3 queryable metrics with no marker; it is
deferred per design §10.2, so a reader would expect an answer the validator refuses — b0beea9.
Task 4: reviewer confirmed SAP DDIC facts are accurate (VBAK-VBELN CHAR 10, LIKP-WADAT_IST as
actual vs planned WADAT, AFKO-GSTRP/GLTRP, AFRU/MKPF/MSEG-BUDAT by context, VTTK-DPTBG,
VBRK-FKDAT) and that glossary definitions match the SQL predicates.
Task 4: note — implementer's report overstated file sizes ~20x (00_kpi_contract.md is 150
lines, reported 2,958) and claimed the AS_OF_DATE grep was clean when a literal was present
inside a quoted grep command. Verify report claims; do not take them at face value.

## Tasks 5-14 — reconstructed 2026-08-11 from git history

Per-task entries below were not written contemporaneously (the live ledger stopped at Task 4
while the build continued). They are reconstructed from commit history, not from the task
reports, so they record what landed rather than what each review found. The task-N-report.md
files in this directory remain the primary source for Tasks 1-5.

Task 5: semantic model, 3 governed metrics + loader validation (3be3254, merged ab6ae86)
Task 6: QueryIntent schema and the 7 validation gates (f69bb9f)
Task 7: deterministic SQL compiler, proves grain-correct vs naive answers (4286f2b);
  fix — SUM over the empty August window returns NULL, not 0 (53d46c8)
Task 8: data-quality contract, metric-bound rules + trust badge (1f7d100, merged 1967b28);
  8fbda27 proves each DQ rule fails on its own corruption and stays quiet on the others
Task 9: catalog asset and provenance-carrying answer output (0da40f9)
Task 10: metadata retriever and golden intents for offline operation (f6fde45)
Task 11: CLI wiring the pipeline end to end (c4159de)
Task 12: Claude API resolver — the only module that calls a model (dd8c7d8)
Task 12.5: metadata-to-NL dataflow swimlane, verified against the code (5bb7c6c) — task added
  mid-build alongside a blocking cross-task plan defect (32e78bf)
Task 13: the implementation guide, pinned to the artifacts by test (a37e795)
Task 14: acceptance verification for spec criteria 1-11 (9925924)

Cross-task review sweeps: 51b6c67 (eight defects found reviewing Tasks 1-8, each with a
falsified test first), 66422ff (four more, incl. a mutation the whole suite missed),
c3f054b (05_semantic_model.yml declared delivery_confirmation, which is un-emittable),
b5deddb (YAML 1.1 coerced every join key to boolean True and plant codes to int),
34ae808 + ecf81d9 (design.md had drifted from what shipped; now tested so it cannot again).

Closeout: full suite 274 passed / 3 skipped; verify_acceptance.py 12 passed / 0 failed /
1 skipped (S12 needs live API credentials — documented, never asserted as tested).
c1e4bb6 fixed `python src/build_warehouse.py` failing on a clean clone.
feat/semantic-layer-mvp fast-forward merged to master and deleted; tree clean.
Re-verified green on master 2026-08-11 before committing this scaffolding.
