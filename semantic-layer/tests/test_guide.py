"""The guide is the deliverable, so it is under test like the code.

Prose rots differently from code: nothing breaks when a number in a sentence stops
matching the number the pipeline prints, so the drift is invisible until a reader
tries to reproduce it and cannot. These tests pin the guide to the artifacts and
the measured figures.
"""
import re
import pytest
from src.semantic.constants import REPO_ROOT

def _readme():
    return (REPO_ROOT / "README.md").read_text(encoding="utf-8")

def test_readme_exists_and_is_substantial():
    assert len(_readme()) > 8000

def test_no_placeholders_in_guide():
    text = _readme()
    for bad in ("TBD", "TODO", "FIXME", "XXX", "Lorem ipsum", "<placeholder>"):
        assert bad not in text, f"guide contains {bad}"

@pytest.mark.parametrize("phase", [
    "Phase 0", "Phase 1", "Phase 2", "Phase 3",
    "Phase 4", "Phase 5", "Phase 6", "Phase 7",
])
def test_every_phase_has_a_section(phase):
    assert phase in _readme()

@pytest.mark.parametrize("artifact", [
    "00_kpi_contract.md", "01_technical_metadata.json", "02_standardized_metadata.json",
    "03_glossary.yml", "03_column_bindings.yml", "04_process_model.yml",
    "05_semantic_model.yml", "06_dq_rules.yml", "07_catalog_asset.json",
])
def test_every_artifact_is_named_in_the_guide(artifact):
    assert artifact in _readme()

def test_every_phase_names_the_nl_failure_it_closes():
    """Acceptance criterion 10."""
    text = _readme().lower()
    assert text.count("nl failure closed") >= 8

def test_guide_quotes_the_canonical_numbers():
    text = _readme()
    for n in ("87.3", "96.2", "8.9", "88.5", "94.4", "92.6"):
        assert n in text, f"guide omits canonical figure {n}"
    # 48 and 55 must appear as the ratio, not as incidental digits anywhere.
    assert re.search(r"48\s*(/|of|out of)\s*55", text, re.I), \
        "guide must show the 48/55 arithmetic behind 87.3%"

def test_guide_shows_the_wrong_answer_first():
    text = _readme()
    assert "88.5" in text
    assert re.search(r"overstat|flatter|too high", text, re.I)

def test_guide_covers_manufacturing_phases():
    text = _readme()
    for phase in ("production", "quality inspection", "goods receipt", "material"):
        assert phase.lower() in text.lower()
    for module in ("SAP PP", "SAP QM", "SAP MM"):
        assert module in text

def test_guide_states_governance_limits_in_body_not_appendix():
    """Acceptance criterion 11: "appears in the guide body, not buried in an appendix."

    This first asserted the statement fell within the first 90% of the file by
    character count. That proxy was brittle rather than wrong: the statement opens
    section 6, which is body, but adding any section above it moved the ratio and
    failed a guide that had not got worse. It tripped at 0.905 after the metadata
    sourcing figure went in above it.

    Encoded structurally now -- before the appendix heading, and reachable from the
    Contents list, which is what "not buried" means to someone skimming.
    """
    text = _readme()
    idx = text.lower().find("does not enforce")
    if idx == -1:
        idx = text.lower().find("not a substitute")
    assert idx != -1, "guide never states the governance limit"

    appendix = text.find("## 7. Appendix")
    assert appendix != -1, "the appendix heading moved; this test needs rewriting"
    assert idx < appendix, "the governance limit is stated inside the appendix"

    contents, body = text.find("## Contents"), text.find("## 1.")
    assert contents != -1 and contents < idx, "no Contents list above the statement"
    assert "what this does not do" in text[contents:body].lower(), (
        "the limits section is not listed in Contents, so it is only discoverable "
        "by reading to the end -- which is what criterion 11 rules out"
    )

def test_guide_documents_offline_operation():
    text = _readme()
    assert "--offline" in text
    assert "ANTHROPIC_API_KEY" in text

def test_guide_documents_deferred_scope():
    """Spec 10.2: be honest about what the MVP does not include."""
    text = _readme().lower()
    assert "production_cycle_time_days" in text or "deferred" in text

def test_portability_appendix_covers_target_tools():
    text = (REPO_ROOT / "appendix" / "portability.md").read_text(encoding="utf-8")
    for tool in ("MetricFlow", "Cube", "Unity Catalog", "Datasphere"):
        assert tool in text

def test_guide_embeds_the_dataflow_diagram():
    """The 'how does metadata answer a question' picture must be in the guide,
    not only in docs/diagrams/."""
    text = _readme()
    assert "nl_dataflow" in text, "guide does not embed the dataflow diagram"
    assert "![" in text, "diagram must be embedded as an image, not just linked"

def test_guide_explains_which_stage_reads_which_artifact():
    """The diagram needs prose beside it naming at least the load-bearing edges."""
    text = _readme()
    for pair in ("03_glossary.yml", "05_semantic_model.yml", "06_dq_rules.yml"):
        assert pair in text
    assert re.search(r"retriev\w+", text, re.I)
    assert re.search(r"valid\w+", text, re.I)

def test_guide_embeds_the_metadata_sourcing_diagram():
    """The companion picture: where each artifact came from, and when it is read.

    The dataflow figure answers "which stage reads what". It cannot answer "can't we
    just harvest this from SAP", which is the question that decides whether this work
    gets funded. Embedded, not merely committed, for the same reason as the other one.
    """
    text = _readme()
    assert "metadata_sources" in text, "guide does not embed the sourcing diagram"
    assert "![" in text.split("metadata_sources")[0][-400:], \
        "the sourcing diagram must be embedded as an image, not just linked"

def test_guide_states_how_much_metadata_is_actually_harvestable():
    """The sourcing figure's whole argument, required in the prose beside it.

    A reader who takes away only "there is a diagram about sources" has missed it.
    The number -- one of nine -- is what changes how the work gets planned, and the
    reason has to be there too: a crawler cannot produce grain.
    """
    text = _readme()
    assert re.search(r"\bone of the nine\b|\b1 of 9\b|only ONE", text, re.I), \
        "the guide never states how many artifacts are machine-harvestable"
    lowered = text.lower()
    for kind in ("derived", "authored", "harvest"):
        assert kind in lowered, f"the guide never mentions {kind} provenance"
    assert "cannot get you" in lowered or "cannot get" in lowered, \
        "the guide does not say what harvesting cannot give you"


# --- Added beyond the plan ----------------------------------------------------
# The plan's tests check the guide is COMPLETE -- every phase, every artifact,
# every canonical figure present. They cannot tell whether what it says is TRUE.
# A guide that names 05_semantic_model.yml while describing a metric the file
# does not define passes every test above. These check the claims against the
# artifacts and the running code, because a reproduction guide whose commands
# and numbers have drifted is worse than no guide: it spends the reader's trust
# before it spends their time.

def _fenced_commands():
    """Every line in a bash/console fence that looks like a project command."""
    out = []
    for block in re.findall(r"```(?:bash|sh|console)\n(.*?)```", _readme(), re.S):
        for raw in block.splitlines():
            line = raw.strip().lstrip("$").strip()
            if line.startswith(("python ", "pytest", "pip install")):
                out.append(line)
    return out


def test_every_documented_command_names_a_file_that_exists():
    """A quickstart that references a moved script is the first thing a reader hits.

    Checks the path only -- running each command here would rebuild the warehouse
    inside the test suite. Existence is the failure mode that actually happens,
    because renaming a module does not touch the prose.
    """
    commands = _fenced_commands()
    assert commands, "no runnable commands found in the guide"
    for cmd in commands:
        for token in cmd.split():
            if token.endswith(".py"):
                assert (REPO_ROOT / token).exists(), \
                    f"guide documents `{cmd}` but {token} does not exist"


def test_every_documented_script_is_importable_the_way_the_guide_invokes_it():
    """Existence is not enough: `python src/build_warehouse.py` failed on a clean clone.

    Found by cloning the branch into a temp directory and running the README's first
    command, which raised ModuleNotFoundError: running a script inside src/ puts src/
    on sys.path, not the repo root, so `from src.semantic...` cannot resolve. Nothing
    caught it because no caller used the documented form -- the tests get the repo root
    from pytest's `pythonpath = .`, and verify_acceptance.py imports the module as
    `src.build_warehouse`. The one invocation a reader actually types was the one
    invocation nothing ran.

    So this imports each documented script in a subprocess whose sys.path holds the
    script's own directory and NOT the repo root -- which is what `python <path>` gives
    you. Getting that wrong makes the test useless: the first version passed `-c` with
    `cwd=REPO_ROOT`, and `python -c` prepends the working directory, so the repo root was
    on sys.path after all and the reintroduced defect went undetected. `-P` (suppress
    cwd) plus an explicit filter is what actually reproduces the reader's shell.

    Run with `run_name='__not_main__'` so module bodies execute but no main() does;
    nothing is built.
    """
    import subprocess, sys
    scripts = sorted({
        token for cmd in _fenced_commands() for token in cmd.split()
        if token.endswith(".py")
    })
    assert scripts, "the guide documents no scripts"
    env = {k: v for k, v in __import__("os").environ.items() if k != "PYTHONPATH"}
    failures = []
    for script in scripts:
        path = REPO_ROOT / script
        code = (
            "import runpy, sys\n"
            # Belt and braces with -P: drop cwd and any repo-root entry, then add the
            # script's directory exactly as the interpreter would.
            f"_root = {str(REPO_ROOT)!r}\n"
            "sys.path = [p for p in sys.path if p not in ('', '.', _root)]\n"
            f"sys.path.insert(0, {str(path.parent)!r})\n"
            "sys.argv = [sys.argv[0], '--help']\n"
            f"runpy.run_path({str(path)!r}, run_name='__not_main__')\n"
        )
        proc = subprocess.run([sys.executable, "-P", "-c", code], cwd=REPO_ROOT,
                              capture_output=True, text=True, env=env, timeout=120)
        if "ModuleNotFoundError" in proc.stderr or "ImportError" in proc.stderr:
            last = proc.stderr.strip().splitlines()[-1]
            failures.append(f"`python {script}` -> {last}")
    assert not failures, (
        "documented commands fail when run the way the guide shows:\n  "
        + "\n  ".join(failures)
        + "\n(add the run-as-script sys.path bootstrap, as src/ask.py has)"
    )


def test_documented_cli_flags_are_flags_the_cli_actually_accepts():
    """`--offline` is in the plan's test; the others are not, and they rot silently."""
    text = _readme()
    parser_src = (REPO_ROOT / "src" / "ask.py").read_text(encoding="utf-8")
    for flag in set(re.findall(r"--[a-z][a-z-]+", text)):
        if flag in ("--check", "--write"):  # the diagram renderer's flags
            assert flag in (REPO_ROOT / "docs" / "diagrams" / "render_dataflow.py")\
                .read_text(encoding="utf-8"), f"{flag} is documented but not implemented"
            continue
        assert f'"{flag}"' in parser_src, \
            f"guide documents {flag}, but src/ask.py declares no such flag"


def test_every_metric_the_guide_names_is_defined_in_the_semantic_model():
    """Except the deferred one, which the guide must mark as deferred.

    The guide is what a reader trusts about what they can ask. Naming a metric
    that does not exist promises an answer the validator will refuse.
    """
    import yaml
    text = _readme()
    model = yaml.safe_load(
        (REPO_ROOT / "metadata" / "05_semantic_model.yml").read_text(encoding="utf-8")
    )
    defined = {m["name"] for m in model["metrics"]}
    # Every implemented metric ends in `_pct`. The one deferred metric is named
    # explicitly rather than by pattern, because `_days` also matches real column
    # names the guide legitimately discusses (standard_duration_days,
    # available_slack_days) and flagging those would make this test noise.
    named = set(re.findall(r"\b[a-z_]+_pct\b", text)) | (
        {"production_cycle_time_days"} if "production_cycle_time_days" in text else set()
    )
    for metric in named:
        if metric in defined:
            continue
        # An undefined metric may only appear near the word "deferred". Scanned in a
        # character window rather than per line: prose wraps, and "is\n**deferred**"
        # is the same claim as "is **deferred**".
        for match in re.finditer(re.escape(metric), text):
            window = text[max(0, match.start() - 200):match.end() + 200].lower()
            if "defer" in window:
                break
        else:
            assert False, (
                f"guide names {metric}, which 05_semantic_model.yml does not define, "
                f"and never marks it deferred"
            )


def test_the_seed_rows_the_guide_walks_through_are_real_rows():
    """The guide prints order IDs and asserts what they demonstrate. If a seed row
    were renumbered, the walkthrough would describe a row nobody can look up."""
    import csv
    text = _readme()
    with open(REPO_ROOT / "data" / "seed_core.csv", newline="", encoding="utf-8") as f:
        seeded = {r["order_id"] for r in csv.DictReader(f)}
    cited = set(re.findall(r"\bSO-\d{4}\b", text))
    assert cited, "the guide walks through no concrete order"
    missing = sorted(cited - seeded)
    assert not missing, f"guide cites orders that are not in seed_core.csv: {missing}"


def test_the_attribution_walkthrough_matches_the_computed_attribution():
    """The Q2 answer is the guide's punchline; it must match what the pipeline says.

    Reads the warehouse rather than the prose's own arithmetic, so the guide cannot
    agree with itself while disagreeing with the data.

    EVERY pairing must be right, not merely one of them. The first version of this test
    searched the whole document for each phase/count pair and passed if it found one --
    which let a mutation change the breakdown block to "Quality inspection 5" and still
    pass, because the sentence below it ("4 of 7 late orders") kept matching. Since the
    breakdown block is the part a reader copies, that is precisely the drift that
    matters, so each occurrence of a phase label followed by a number is now checked.
    """
    import duckdb
    from src.semantic.constants import DB_PATH
    if not DB_PATH.exists():
        pytest.skip("warehouse not built; run python src/build_warehouse.py")
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT delay_attribution_phase, count(*)
            FROM fact_order_delivery
            WHERE region = 'IN'
              AND promised_delivery_date BETWEEN DATE '2026-07-01' AND DATE '2026-07-31'
              AND is_eligible AND NOT is_on_time
            GROUP BY 1
            """
        ).fetchall()
    finally:
        con.close()
    counts = {phase: n for phase, n in rows if phase}
    assert counts, "no attributed late orders; the walkthrough has nothing to check"
    text = _readme()
    for phase, n in counts.items():
        label = phase.replace("_", " ")
        # Every place the guide pairs this phase label with a bare count must state the
        # measured count. `\d+` is deliberately narrow: it matches the breakdown block
        # ("Quality inspection    4") and the summary sentence ("4 of 7 late orders"),
        # but not the process table, where the trailing number is a standard duration.
        pairings = re.findall(rf"{label}[ \t]+\(?(\d+)\b", text, re.I)
        assert pairings, (
            f"the warehouse attributes {n} late orders to {phase}, and the guide "
            f"never states that pairing"
        )
        wrong = [p for p in pairings if int(p) != n]
        assert not wrong, (
            f"guide pairs '{label}' with {wrong} somewhere, but the warehouse "
            f"attributes {n} late orders to it"
        )


def test_the_guide_shows_a_real_refusal_not_only_a_successful_answer():
    """Half the argument is what the layer will not answer.

    A guide that only shows the happy path teaches the reader nothing about the
    gates -- and the gates are the reason to believe the happy path.
    """
    text = _readme()
    assert re.search(r"REFUSED", text), "the guide never shows a refusal"
    from src.semantic.validator import GATE_NAMES
    shown = [g for g in GATE_NAMES if g in text]
    assert len(shown) == len(GATE_NAMES), (
        f"guide names only {len(shown)} of {len(GATE_NAMES)} gates: "
        f"missing {sorted(set(GATE_NAMES) - set(shown))}"
    )


def test_the_dq_rules_the_guide_lists_are_the_rules_that_exist():
    """Rule IDs appear in the trust badge a reader sees, so they must be the real ones."""
    import yaml
    rules = yaml.safe_load(
        (REPO_ROOT / "metadata" / "06_dq_rules.yml").read_text(encoding="utf-8")
    )["rules"]
    real = {r["rule_id"] for r in rules}
    text = _readme()
    cited = set(re.findall(r"\bdq_[a-z_]+\b", text))
    assert cited, "the guide names no DQ rule"
    assert not (cited - real), f"guide cites rules that do not exist: {sorted(cited - real)}"
    assert real <= cited, f"guide omits real rules: {sorted(real - cited)}"


def test_the_guide_states_the_architectural_rule_before_the_phase_walkthrough():
    """"The model never writes SQL" is the one sentence that has to land.

    Buried after eight phase sections it reads as a footnote to an implementation;
    stated up front it is the premise everything else follows from.
    """
    text = _readme()
    rule = re.search(r"never writes? (?:the )?(?:SQL|arithmetic)", text, re.I)
    assert rule, "the guide never states that the model does not write SQL"
    first_phase = text.find("Phase 0")
    assert first_phase != -1
    assert rule.start() < first_phase, \
        "the architectural rule is stated after the phase walkthrough begins"


def test_every_quoted_artifact_excerpt_is_faithful_to_the_real_file():
    """The guide shows YAML/JSON excerpts and calls them the artifact.

    They are abridged -- that is fine and necessary, a full 05_semantic_model.yml would
    bury the point. What is not fine is a quoted key or value that does not appear in
    any real artifact, because a reader who opens the file and cannot find what the
    guide showed them has to distrust every other excerpt too.

    Elisions are marked with `...` and exempted; anything else must be verbatim
    somewhere in metadata/.
    """
    from pathlib import Path
    readme = _readme()
    corpus = "\n".join(
        p.read_text(encoding="utf-8")
        for p in sorted((REPO_ROOT / "metadata").iterdir())
        if p.is_file()
    )
    blocks = re.findall(r"```(?:json|yaml)\n(.*?)```", readme, re.S)
    assert blocks, "the guide quotes no artifact excerpts at all"

    def present(token: str) -> bool:
        """Word-boundary match, not substring.

        Substring matching let a mutation quote `qm_decision_date` -- a column that does
        not exist -- and pass, because it sits inside `qm_final_decision_date`. Since
        confusing those two is the exact defect Phase 4 warns about, a check that cannot
        tell them apart is checking nothing here.
        """
        return re.search(rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])",
                         corpus) is not None

    problems = []
    for block in blocks:
        for key, value in re.findall(
            r'"?([a-z_]+)"?:\s*"?([A-Za-z_][A-Za-z0-9_ .%\-/]*)"?', block
        ):
            value = value.strip().rstrip('",')
            if len(value) < 4 or value in ("true", "false") or "..." in value:
                continue
            if not present(key):
                problems.append(f"key {key!r} appears in no artifact")
            elif not present(value):
                problems.append(f"{key}: {value!r} appears in no artifact")
    assert not problems, "guide excerpts have drifted from the artifacts:\n" + \
        "\n".join(problems)


def test_every_column_name_the_guide_quotes_is_a_real_warehouse_column():
    """Sharper than the excerpt check, and needed because that one cannot do this.

    A mutation quoting `timestamp_field: qm_decision_date` survived the excerpt test for
    a legitimate reason: that string genuinely appears in `01_technical_metadata.json` --
    inside a note explaining that no such column exists. Presence in metadata therefore
    cannot separate a real column from one a document warns you about, and `_date`
    columns are exactly where Phase 4's first/final-decision trap lives. So the check
    for column names goes to the warehouse instead, which either has the column or
    does not.
    """
    import duckdb
    from src.semantic.constants import DB_PATH
    if not DB_PATH.exists():
        pytest.skip("warehouse not built; run python src/build_warehouse.py")
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        tables = [r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()]
        columns = {
            row[1] for t in tables
            for row in con.execute(f"PRAGMA table_info('{t}')").fetchall()
        }
    finally:
        con.close()
    # Date-ish and variance columns only: the guide also names CSV headers and SAP
    # fields, which are legitimately not warehouse columns.
    quoted = set(re.findall(r"\b((?:var|std)_[a-z_]+|[a-z_]+_date)\b", _readme()))
    # DQ rule IDs end in a column name (`dq_completeness_delivery_date`) and are not
    # columns themselves; the guide legitimately names them, and a separate test already
    # checks them against 06_dq_rules.yml.
    quoted = {q for q in quoted if not q.startswith("dq_")}
    unknown = sorted(quoted - columns)
    assert not unknown, (
        f"the guide names {unknown} as columns, but the built warehouse has no such "
        f"column -- check for a first/final decision mix-up"
    )


def test_the_acceptance_script_cannot_report_an_unverified_criterion_as_passed():
    """Its one indispensable property, so it gets a test rather than a docstring.

    Found by falsifying the script: flipping one `"SKIP"` to `"PASS"` at the call site
    printed "13 passed, 0 failed, 0 skipped" and nothing objected. A verification report
    whose PASSes might not have been measured is worse than no report -- it spends trust
    it did not earn. So the unverifiable path no longer takes a state argument, and this
    asserts that stays true.
    """
    import verify_acceptance as va
    with pytest.raises(ValueError):
        va.record("X", "PASS_MAYBE", "not a real state")
    with pytest.raises(ValueError):
        va.record("X", "SKIP", "an unmeasured criterion must not use record()")
    # And the live-resolver criterion must reach the report through the safe path.
    # Sliced to the function body only -- running to end-of-file swept in main()'s
    # `r[1] == "PASS"` tally, which is the code doing the counting, not a verdict.
    src = (REPO_ROOT / "verify_acceptance.py").read_text(encoding="utf-8")
    start = src.index("def check_spec_12_live_resolver")
    live = src[start:src.index("\nCHECKS = (", start)]
    assert "record_unverifiable(" in live
    assert '"PASS"' not in live, \
        "the live-resolver check names PASS; it cannot be verified in this environment"


# --- docs/design.md ------------------------------------------------------------
# The design doc had drifted in three places at once -- it claimed 12 golden intents
# when 2 shipped, 8 metadata artifacts when 9 exist, and listed 5 of 13 test files --
# and every one was found by reading it, not by a failing test. README.md is pinned
# above; this pins the parts of design.md that are mechanically checkable, since a
# spec nobody can trust is read once and then ignored.

def _design():
    return (REPO_ROOT / "docs" / "design.md").read_text(encoding="utf-8")


def _layout_block():
    """The fenced repo-layout tree in Section 7."""
    blocks = re.findall(r"```\n(semantic-layer-nl/.*?)```", _design(), re.S)
    assert blocks, "design.md has no repo layout block"
    return blocks[0]


def test_every_test_file_on_disk_is_listed_in_the_design_layout():
    """The omission that actually happened: 8 of 13 test files were missing.

    A layout block readers use as a map has to be the whole map, or the modules it
    omits look like they do not exist.
    """
    listed = set(re.findall(r"\b(test_[a-z_]+\.py)\b", _layout_block()))
    on_disk = {p.name for p in (REPO_ROOT / "tests").glob("test_*.py")}
    missing = sorted(on_disk - listed)
    assert not missing, f"design.md's layout block omits {missing}"
    phantom = sorted(listed - on_disk)
    assert not phantom, f"design.md's layout block names nonexistent {phantom}"


def test_every_path_the_design_layout_names_exists():
    """Guards the reverse direction for non-test files: a renamed module leaves the
    tree describing a repo that is no longer this one.

    The filename pattern allows hyphens and interior dots. Without hyphens it matched only
    the tail of a hyphenated name -- `semantic-layer-complete.md` came through as
    `complete.md`; without interior dots a double extension split the same way, and
    `medium-post.template.md` came through as `template.md`. Both times the test reported a
    missing file that was sitting right there.
    """
    problems = []
    for name in re.findall(r"([a-z0-9_.-]+(?:\.py|\.yml|\.json|\.sql|\.csv|\.md))\b",
                           _layout_block()):
        if not list(REPO_ROOT.rglob(name)):
            problems.append(name)
    assert not problems, f"design.md's layout block names paths that do not exist: {problems}"


def test_the_test_count_in_the_design_doc_is_the_real_count():
    """Stated counts rot the moment a test is added, and this doc had three wrong ones.

    Collected via a subprocess rather than by counting `def test_` -- parametrized
    tests make those two numbers legitimately different, and the collected count is
    the one a reader would compare against their own terminal.
    """
    import subprocess, sys
    claimed = re.search(r"tests/\s+(\d+) tests", _design())
    assert claimed, "design.md no longer states a test count; it should"
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=180,
    ).stdout
    actual = re.search(r"(\d+) tests collected", out)
    assert actual, f"could not read a collected count from pytest:\n{out[-500:]}"
    assert int(claimed.group(1)) == int(actual.group(1)), (
        f"design.md claims {claimed.group(1)} tests; pytest collects "
        f"{actual.group(1)}"
    )


def test_the_design_doc_records_no_unresolved_open_item():
    """Section 9 was an open question addressed to the user, settled long ago.

    A spec still asking a question it has answered makes a reader wonder what else
    in it is stale -- which, at the time this was written, was the correct instinct.
    """
    text = _design()
    assert "Open item for the user" not in text, \
        "design.md still poses Section 9 as an open item; it was settled as option (c)"


def test_build_time_and_query_time_artifacts_are_distinguished():
    """The distinction the diagram exists to make must survive into the prose.

    Believing P1/P2 are read at query time is the most common misreading of a
    layer like this: it makes the SAP dictionary look like a live dependency of
    every question, which is both wrong and much scarier than the truth.
    """
    text = _readme().lower()
    assert "build time" in text or "build-time" in text
    assert "query time" in text or "query-time" in text
