"""Check every acceptance criterion mechanically and exit non-zero on any failure.

`pytest` proves the components behave. This script asks the different question the
spec's acceptance list asks: does the deliverable, as committed, do what it claims?
Some of those claims are not unit-testable -- that the warehouse builds from a deleted
database with no network, that the suite is green with credentials stripped from the
environment, that the guide states its own governance limit. Each runs here in a
subprocess against the real files.

The one rule this script exists to enforce on itself: an untested criterion is never
printed as PASS. Criterion 12 of the spec needs a live API key, there is none in this
environment, and reporting it as anything but SKIP would make the whole report
worthless -- a green list nobody can trust is worse than a red one.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if __package__ in (None, ""):
    _root = str(Path(__file__).resolve().parent)
    if _root not in sys.path:
        sys.path.insert(0, _root)

from src.semantic.constants import AS_OF_DATE, DB_PATH, METADATA_DIR, REPO_ROOT

PY = sys.executable
_WIDTH = 74

# Every criterion's outcome, in declaration order.
_results: list[tuple[str, str, str]] = []


def record(num: str, state: str, title: str, detail: str = "") -> None:
    """Print one criterion's verdict as it is decided, so a hang is locatable."""
    if state not in ("PASS", "FAIL"):
        raise ValueError(
            f"record() decides measured outcomes only, got {state!r}. An outcome that "
            f"was not measured must go through record_unverifiable()."
        )
    _results.append((num, state, title))
    _print_verdict(num, state, title, detail)


def record_unverifiable(num: str, title: str, detail: str) -> None:
    """Report a criterion that CANNOT be checked here. Always SKIP -- there is no
    argument to get wrong.

    Separate from `record` on purpose. Falsifying this script found that changing one
    `"SKIP"` to `"PASS"` at the call site produced "13 passed, 0 failed, 0 skipped" and
    nothing anywhere objected -- the single worst outcome available, since the report's
    only value is that its PASSes were measured. With the state no longer a parameter
    there is no code path from an unverifiable criterion to a pass, so that edit is not
    a one-token slip any more; it is a visible rewrite that `test_guide.py` also asserts
    against.
    """
    _results.append((num, "SKIP", title))
    _print_verdict(num, "SKIP", title, detail)


def _print_verdict(num: str, state: str, title: str, detail: str) -> None:
    line = f"{state:<5} {num:>2}. {title}"
    print(line[:_WIDTH] if len(line) <= _WIDTH else line)
    if detail:
        for chunk in detail.strip().splitlines():
            print(f"          {chunk}")


def _run(args: list[str], env: dict[str, str] | None = None, cwd: Path = REPO_ROOT):
    return subprocess.run(
        [PY, *args], capture_output=True, text=True, cwd=str(cwd),
        env={**os.environ, **(env or {})},
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _readme() -> str:
    return (REPO_ROOT / "README.md").read_text(encoding="utf-8")


# --------------------------------------------------------------------------------------
# 1. The warehouse builds from nothing, offline
# --------------------------------------------------------------------------------------
def check_1_warehouse_builds_from_scratch() -> None:
    """Built into a temp path rather than by deleting the real one.

    Deleting warehouse.duckdb would work, but a failure partway through would leave the
    reader's working copy broken by the script that was supposed to reassure them.
    """
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "acceptance.duckdb"
        proc = _run(["-c", f"import src.build_warehouse as b; b.build(db_path=r'{target}')"])
        if proc.returncode != 0:
            record("1", "FAIL", "warehouse builds from committed CSVs",
                   proc.stderr[-700:])
            return
        if not target.exists() or target.stat().st_size < 10_000:
            record("1", "FAIL", "warehouse builds from committed CSVs",
                   "build reported success but produced no usable database")
            return
        import duckdb
        con = duckdb.connect(str(target), read_only=True)
        try:
            rows, keys = con.execute(
                "SELECT count(*), count(DISTINCT order_id) FROM fact_order_delivery"
            ).fetchone()
        finally:
            con.close()
        if (rows, keys) != (132, 132):
            record("1", "FAIL", "warehouse builds from committed CSVs",
                   f"expected 132 orders at order grain, got {rows} rows / {keys} keys")
            return
    record("1", "PASS", "warehouse builds from committed CSVs, no network, 132/132")


# --------------------------------------------------------------------------------------
# 2 & 3. The two documented answers
# --------------------------------------------------------------------------------------
def check_2_q1_answer() -> None:
    proc = _run(["src/ask.py", "--offline", "Q1"])
    out = proc.stdout
    missing = [
        want for want in ("87.3%", "48 of 55", "TRUSTED", "7/7 passed",
                          "48 / 55 = 87.2727%", "region = IN",
                          "cancelled_orders, not_yet_due")
        if want not in out
    ]
    if proc.returncode != 0 or missing:
        record("2", "FAIL", "ask.py --offline Q1 -> 87.3% (48/55), TRUSTED",
               f"exit {proc.returncode}; missing: {missing}")
        return
    record("2", "PASS", "ask.py --offline Q1 -> 87.3% (48/55), TRUSTED, 7/7 gates")


def check_3_q2_answer() -> None:
    proc = _run(["src/ask.py", "--offline", "Q2"])
    out = proc.stdout
    problems = []
    for want in ("87.3%", "96.2% (25 / 26)", "down 8.9pp"):
        if want not in out:
            problems.append(f"missing {want!r}")
    # Attribution counts must be paired with their phases, not merely present.
    for label, n in (("Quality inspection", 4), ("Transportation", 2),
                     ("Production execution", 1)):
        if not re.search(rf"{label}\s+{n}\b", out):
            problems.append(f"{label} not reported as {n}")
    if proc.returncode != 0 or problems:
        record("3", "FAIL", "ask.py --offline Q2 -> -8.9pp with QM 4 / transport 2 / prod 1",
               f"exit {proc.returncode}; " + "; ".join(problems))
        return
    record("3", "PASS", "ask.py --offline Q2 -> -8.9pp vs 96.2%, QM 4 / transport 2 / prod 1")


# --------------------------------------------------------------------------------------
# 4. Green with credentials stripped
# --------------------------------------------------------------------------------------
def check_4_suite_green_without_credentials() -> None:
    """The claim is 'works without a key', so the check must remove any key present.

    Emptying the variables is not enough -- the SDK treats an empty string as
    configured -- so they are deleted from the child's environment outright.
    """
    env = {k: v for k, v in os.environ.items()
           if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
                        "ANTHROPIC_BEDROCK_BASE_URL", "CLAUDE_CODE_USE_BEDROCK")}
    proc = subprocess.run(
        [PY, "-m", "pytest", "-q", "--no-header"],
        capture_output=True, text=True, cwd=str(REPO_ROOT), env=env,
    )
    tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    if proc.returncode != 0:
        record("4", "FAIL", "pytest green with no credentials in the environment",
               tail or proc.stderr[-500:])
        return
    if "skipped" not in tail:
        record("4", "FAIL", "pytest green with no credentials; live tests skip",
               f"nothing skipped, so the live tests did not skip cleanly: {tail}")
        return
    record("4", "PASS", f"pytest green with no credentials -- {tail}")


# --------------------------------------------------------------------------------------
# 5. The wrong-answer narrative is under test
# --------------------------------------------------------------------------------------
def check_5_compiler_asserts_the_canonical_figures() -> None:
    """Delegated to test_compiler.py rather than recomputed here.

    Recomputing would prove the numbers are reproducible but not that they are
    *asserted* -- and the criterion is that the narrative cannot drift without a test
    going red.
    """
    src = (REPO_ROOT / "tests" / "test_compiler.py").read_text(encoding="utf-8")
    missing = [n for n in ("87.2727", "88.5246", "94.4444", "94.5455", "92.5926")
               if n not in src]
    if missing:
        record("5", "FAIL", "test_compiler.py asserts the grain-error figures",
               f"not asserted anywhere: {missing}")
        return
    proc = subprocess.run(
        [PY, "-m", "pytest", "tests/test_compiler.py", "-q", "--no-header"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if proc.returncode != 0:
        record("5", "FAIL", "test_compiler.py asserts the grain-error figures",
               proc.stdout[-500:])
        return
    record("5", "PASS", "87.27 / 88.52 / 94.44 / 94.55 / 92.59 all asserted and passing")


# --------------------------------------------------------------------------------------
# 6. Each defect trips its own rule
# --------------------------------------------------------------------------------------
def check_6_each_defect_trips_its_own_rule() -> None:
    """Delegated deliberately (see the plan's note on this criterion).

    The test mutates a scratch copy inside a rolled-back transaction and asserts the
    whole verdict set. Re-deriving it here would mean a second implementation of the
    corruption harness, and the two would eventually disagree about what "quiet on the
    others" means. Note the criterion is NOT "only its intended rule": a duplicated
    order row genuinely changes the published OTD number, so the accuracy certification
    firing alongside the uniqueness rule is a backstop working, not leakage.
    """
    name = "test_each_rule_fails_on_its_own_corruption_and_stays_quiet_otherwise"
    proc = subprocess.run(
        [PY, "-m", "pytest", f"tests/test_dq.py::{name}", "-q", "--no-header"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if proc.returncode != 0:
        record("6", "FAIL", "each seeded defect trips its intended DQ rule",
               proc.stdout[-700:])
        return
    record("6", "PASS", "each seeded defect trips its intended rule (1 expected cross-fire)")


# --------------------------------------------------------------------------------------
# 7. Denominators match the committed CSVs
# --------------------------------------------------------------------------------------
def check_7_denominators_match_the_data() -> None:
    proc = subprocess.run(
        [PY, "-m", "pytest", "tests/test_data.py", "-q", "--no-header"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if proc.returncode != 0:
        record("7", "FAIL", "design 5.1 denominators match the committed CSVs",
               proc.stdout[-700:])
        return
    record("7", "PASS", "design 5.1 denominators match the committed CSVs")


# --------------------------------------------------------------------------------------
# 8. The generator is deterministic
# --------------------------------------------------------------------------------------
def check_8_generator_is_deterministic() -> None:
    """Re-runs the real generator, so the committed CSVs are the ones under test.

    Hashed before and after and restored from the pre-images on any difference: a
    non-deterministic generator would otherwise leave the repo dirty as a side effect
    of checking whether it was deterministic.
    """
    csvs = sorted((REPO_ROOT / "data").glob("*_raw.csv"))
    if not csvs:
        record("8", "FAIL", "data/generate.py is deterministic", "no generated CSVs found")
        return
    before = {p: _sha(p) for p in csvs}
    backup = {p: p.read_bytes() for p in csvs}
    proc = _run(["data/generate.py"])
    if proc.returncode != 0:
        record("8", "FAIL", "data/generate.py is deterministic", proc.stderr[-500:])
        return
    changed = [p.name for p in csvs if _sha(p) != before[p]]
    if changed:
        for p in csvs:  # leave the working copy as we found it
            p.write_bytes(backup[p])
        record("8", "FAIL", "data/generate.py is deterministic",
               f"re-running changed {changed} (restored)")
        return
    record("8", "PASS", f"data/generate.py re-run leaves {len(csvs)} CSVs byte-identical")


# --------------------------------------------------------------------------------------
# 9. All nine artifacts real, parseable, placeholder-free
# --------------------------------------------------------------------------------------
def check_9_artifacts_are_real() -> None:
    import json

    import yaml

    expected = [
        "00_kpi_contract.md", "01_technical_metadata.json",
        "02_standardized_metadata.json", "03_glossary.yml", "03_column_bindings.yml",
        "04_process_model.yml", "05_semantic_model.yml", "06_dq_rules.yml",
        "07_catalog_asset.json",
    ]
    problems = []
    for name in expected:
        path = METADATA_DIR / name
        if not path.exists():
            problems.append(f"{name} missing")
            continue
        text = path.read_text(encoding="utf-8")
        for bad in ("TBD", "TODO", "FIXME", "Lorem ipsum", "<placeholder>"):
            if bad in text:
                problems.append(f"{name} contains {bad}")
        # The as-of date token is legitimate -- it is resolved at load time from
        # constants.py, which is exactly how the date stays in one place. Anything
        # else in __TOKEN__ shape is an unfilled blank.
        #
        # At least one uppercase letter is required: `[A-Z_]+` alone matches the
        # signature rules in the KPI contract (`_________________ Date: _______`),
        # which are a deliberate part of a document meant to be signed, not blanks
        # someone forgot to fill in.
        for token in set(re.findall(r"__[A-Z][A-Z_]*__", text)) - {"__AS_OF_DATE__"}:
            problems.append(f"{name} has unresolved token {token}")
        try:
            if name.endswith(".json"):
                json.loads(text)
            elif name.endswith(".yml"):
                yaml.safe_load(text)
        except Exception as exc:
            problems.append(f"{name} does not parse: {exc}")
    if problems:
        record("9", "FAIL", "all 9 metadata artifacts exist, parse, no placeholders",
               "\n".join(problems))
        return
    record("9", "PASS", "all 9 metadata artifacts exist, parse, and carry no placeholders")


# --------------------------------------------------------------------------------------
# 10 & 11. The guide's own obligations
# --------------------------------------------------------------------------------------
def check_10_guide_names_every_nl_failure() -> None:
    count = _readme().lower().count("nl failure closed")
    if count < 8:
        record("10", "FAIL", "README names the NL failure each phase closes",
               f"found {count} 'NL FAILURE CLOSED' sections, need 8")
        return
    record("10", "PASS", f"README names the NL failure closed by all {count} phases")


def check_11_governance_limit_in_the_body() -> None:
    """Measured at the EARLIEST statement, not the first phrasing that matches.

    The first version of this check searched only for "does not enforce" and found the
    section 6 restatement at 89.9% -- one rounding step from a false failure -- while
    the actual statement sits in the Phase 7 section at 71%. Pinning the criterion to
    one exact wording measures the phrasing rather than the placement, which is not
    what the criterion is about.
    """
    text = _readme()
    lower = text.lower()
    positions = [i for i in (lower.find(p) for p in
                             ("does not enforce", "do not enforce", "not a substitute"))
                 if i != -1]
    if not positions:
        record("11", "FAIL", "governance-limits statement is in the README body",
               "no governance-limits statement found in any expected phrasing")
        return
    position = min(positions) / len(text)
    if position > 0.9:
        record("11", "FAIL", "governance-limits statement is in the README body",
               f"stated at {position:.0%} through the document -- effectively an appendix")
        return
    record("11", "PASS",
           f"governance limit stated at {position:.0%} through the README body")


# --------------------------------------------------------------------------------------
# 12 (additive). The diagram is committed, current, and embedded
# --------------------------------------------------------------------------------------
def check_12_diagram_is_current_and_embedded() -> None:
    """Additive to spec section 8's list of 11, not a renumbering of it (Task 12.5)."""
    problems = []
    for name in ("nl_dataflow.svg", "nl_dataflow.png"):
        path = REPO_ROOT / "docs" / "diagrams" / name
        if not path.exists() or path.stat().st_size < 5000:
            problems.append(f"{name} missing or truncated")
    proc = _run(["docs/diagrams/render_dataflow.py", "--check"])
    if proc.returncode != 0:
        problems.append("renderer --check reports the committed diagram is stale")
    if "![" not in _readme() or "nl_dataflow" not in _readme():
        problems.append("README does not embed the diagram as an image")
    if problems:
        record("12", "FAIL", "dataflow diagram committed, current, and embedded",
               "\n".join(problems))
        return
    record("12", "PASS", "dataflow diagram committed, --check current, embedded in README")


# --------------------------------------------------------------------------------------
# 13 (additive). The metadata sourcing map is committed, current, embedded, and TRUE
# --------------------------------------------------------------------------------------
def check_13_sourcing_diagram_claims_are_supported_by_the_artifacts() -> None:
    """Additive, like 12. The extra clause over criterion 12 is the last one.

    A dataflow diagram that lies gets caught by the module sources. A *provenance*
    diagram that lies has nothing to catch it -- "01_technical_metadata.json came from
    SAP DDIC" is unfalsifiable prose unless something checks the file. So every edge
    declares a `probe` string that must occur in the artifact it points at, and this
    criterion is that all of them do. An unsupported arrow is a governance claim
    nobody can audit, which is the failure this whole project argues against.
    """
    problems = []
    for name in ("metadata_sources.svg", "metadata_sources.png"):
        path = REPO_ROOT / "docs" / "diagrams" / name
        if not path.exists() or path.stat().st_size < 5000:
            problems.append(f"{name} missing or truncated")
    proc = _run(["docs/diagrams/render_sources.py", "--check"])
    if proc.returncode != 0:
        problems.append("renderer --check reports the committed diagram is stale")
    readme = _readme()
    if "![" not in readme or "metadata_sources" not in readme:
        problems.append("README does not embed the sourcing diagram as an image")

    from docs.diagrams.render_sources import ARTIFACTS, EDGES

    for edge in EDGES:
        path = METADATA_DIR / edge["file"]
        if not path.exists():
            problems.append(f"edge points at a missing artifact: {edge['file']}")
        elif edge["probe"] not in path.read_text(encoding="utf-8"):
            problems.append(
                f"{edge['file']} is drawn as coming from '{edge['src']}' on the "
                f"evidence of {edge['probe']!r}, which is not in the file"
            )
    harvested = [a["file"] for a in ARTIFACTS if a["kind"] == "harvested"]
    if harvested != ["01_technical_metadata.json"]:
        problems.append(
            f"the figure's central claim -- one harvestable artifact -- no longer "
            f"holds: {harvested}"
        )

    if problems:
        record("13", "FAIL", "sourcing diagram current, embedded, and artifact-backed",
               "\n".join(problems))
        return
    record("13", "PASS",
           f"sourcing diagram embedded and current; all {len(EDGES)} provenance "
           f"claims found in their artifacts")


# --------------------------------------------------------------------------------------
# Spec criterion 12: the live resolver. Not verifiable here.
# --------------------------------------------------------------------------------------
def check_spec_12_live_resolver() -> None:
    """SKIP, never PASS. This is the one claim the script exists to refuse to make.

    If credentials ever are present this still reports SKIP rather than running a
    billable call from a verification script -- `pytest -m live` is where that belongs.
    The distinction reported here is only whether it *could* be run.
    """
    has = bool(os.environ.get("ANTHROPIC_API_KEY") or
               os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    detail = (
        "credentials are present; run `python -m pytest tests/test_resolver_live.py` "
        "to exercise it"
        if has else
        "no credentials in this environment; documented, never asserted as tested"
    )
    record_unverifiable(
        "S12", "spec criterion 12: live resolver maps Q1 to the golden intent", detail
    )


CHECKS = (
    check_1_warehouse_builds_from_scratch,
    check_2_q1_answer,
    check_3_q2_answer,
    check_4_suite_green_without_credentials,
    check_5_compiler_asserts_the_canonical_figures,
    check_6_each_defect_trips_its_own_rule,
    check_7_denominators_match_the_data,
    check_8_generator_is_deterministic,
    check_9_artifacts_are_real,
    check_10_guide_names_every_nl_failure,
    check_11_governance_limit_in_the_body,
    check_12_diagram_is_current_and_embedded,
    check_13_sourcing_diagram_claims_are_supported_by_the_artifacts,
    check_spec_12_live_resolver,
)


def main(argv: list[str] | None = None) -> int:
    print(f"Acceptance verification -- as of {AS_OF_DATE.isoformat()}")
    print(f"repo: {REPO_ROOT}")
    print("-" * _WIDTH)
    for check in CHECKS:
        try:
            check()
        except Exception as exc:  # a crashed check is a failed check, never a silent skip
            record("?", "FAIL", f"{check.__name__} raised", f"{type(exc).__name__}: {exc}")
    print("-" * _WIDTH)
    failed = [r for r in _results if r[1] == "FAIL"]
    passed = [r for r in _results if r[1] == "PASS"]
    skipped = [r for r in _results if r[1] == "SKIP"]
    print(f"{len(passed)} passed, {len(failed)} failed, {len(skipped)} skipped")
    if failed:
        print()
        print("A failure here is a real defect in the deliverable. Fix the code or the")
        print("guide -- not this script.")
        for num, _, title in failed:
            print(f"  {num}. {title}")
        return 1
    if not DB_PATH.exists():
        print("(note: warehouse.duckdb is not committed; ask.py builds it on demand)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
