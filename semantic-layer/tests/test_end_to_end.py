import subprocess, sys, os, csv, re
import pytest
from src import build_warehouse
from src.semantic.constants import REPO_ROOT, DATA_DIR

@pytest.fixture(scope="module", autouse=True)
def warehouse():
    build_warehouse.build()

def _run_cli(*args):
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)          # prove no key is needed
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    env["PYTHONPATH"] = str(REPO_ROOT)
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "src" / "ask.py"), *args],
        capture_output=True, text=True, cwd=REPO_ROOT, env=env,
    )

def test_q1_via_cli_without_api_key():
    """Acceptance criterion 2."""
    p = _run_cli("--offline", "Q1")
    assert p.returncode == 0, p.stderr
    out = p.stdout
    assert "87.3" in out
    assert "48" in out and "55" in out
    assert "TRUSTED" in out
    assert "SAP" in out

def test_q2_via_cli_without_api_key():
    """Acceptance criterion 3: attribution and the 8.9pp drop."""
    p = _run_cli("--offline", "Q2")
    assert p.returncode == 0, p.stderr
    out = p.stdout
    assert "87.3" in out
    assert "96.2" in out
    assert "8.9" in out
    # The attribution breakdown, with counts tied to their phases.
    assert re.search(r"quality[_ ]inspection\D{0,20}4", out, re.I), out
    assert re.search(r"transportation\D{0,20}2", out, re.I), out
    assert re.search(r"production[_ ]execution\D{0,20}1", out, re.I), out

def test_cli_lists_available_questions():
    p = _run_cli("--list")
    assert p.returncode == 0
    assert "Q1" in p.stdout and "Q2" in p.stdout

def test_cli_fails_gracefully_on_unknown_id():
    p = _run_cli("--offline", "Q99")
    assert p.returncode != 0
    assert "Q99" in (p.stdout + p.stderr)

def test_derived_attribution_matches_hand_authored_oracle():
    """The pipeline's answer must match the CSV's expected_attribution_phase
    column, which it never reads."""
    from src.semantic.loader import load_semantic_model
    from src.semantic.compiler import compile_sql
    from src.semantic.executor import run
    from src.semantic.retriever import golden_intent
    rows = run(compile_sql(golden_intent("Q2"), load_semantic_model()))
    derived = {r["delay_attribution_phase"]: r["late_count"]
               for r in rows if r["delay_attribution_phase"]}
    with open(DATA_DIR / "seed_core.csv", newline="") as f:
        from collections import Counter
        # The oracle column is populated for IN-July orders only -- that is the
        # window Q2 asks about. Rows outside it carry an empty value and are
        # skipped by the truthiness filter.
        oracle = Counter(r["expected_attribution_phase"] for r in csv.DictReader(f)
                         if r["expected_attribution_phase"])
    assert derived == dict(oracle)
    assert dict(oracle) == {"quality_inspection": 4, "transportation": 2,
                            "production_execution": 1}

def test_full_suite_passes_without_api_key():
    """Acceptance criterion 4."""
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    env["PYTHONPATH"] = str(REPO_ROOT)
    p = subprocess.run(
        [sys.executable, "-m", "pytest", "-q",
         "--ignore=tests/test_end_to_end.py"],   # avoid recursion
        capture_output=True, text=True, cwd=REPO_ROOT, env=env,
    )
    assert p.returncode == 0, p.stdout[-4000:]

def test_no_module_outside_resolver_imports_anthropic():
    """Structural guarantee that the pipeline is LLM-free."""
    import pathlib
    sem = REPO_ROOT / "src" / "semantic"
    for path in list(sem.glob("*.py")) + [REPO_ROOT / "src" / "build_warehouse.py"]:
        if path.name == "resolver.py":
            continue
        assert "anthropic" not in path.read_text(encoding="utf-8"), \
            f"{path.name} imports anthropic"


# --- Added beyond the plan ---------------------------------------------------
# The plan's tests check that the happy path prints the right numbers. None checks
# the refusal paths, and the refusal paths are the ones that matter: a layer that
# serves a number when a gate fails is worse than no layer, because the number
# arrives wearing the same provenance block as a trustworthy one.

def test_a_gate_failure_prints_no_number_at_all():
    """Acceptance criterion 6, from the CLI's side.

    A failed gate must produce a refusal naming the gate -- never a value with a
    caveat attached. Constructed here rather than through a golden intent, since
    every golden intent passes by design.
    """
    from src.semantic.intent import QueryIntent
    from src.semantic.loader import load_semantic_model
    from src import ask
    bad = QueryIntent.model_validate({
        "metric": "on_time_delivery_pct",
        "dimensions": ["delivery_id"],          # reachable, but only via one_to_many
        "filters": [],
        "grain": "order",
        "time_window": {"start": "2026-07-01", "end": "2026-07-31",
                        "label": "July 2026"},
        "intent_type": "descriptive",
        "comparison": None,
    })
    rc, text = ask.answer_intent(bad, load_semantic_model())
    assert rc != 0
    assert "no_fanout" in text
    assert "REFUSED" in text
    # No percentage anywhere in a refusal.
    assert not re.search(r"\d+\.\d+\s*%", text), text
    assert "87.3" not in text


def test_offline_mode_never_imports_the_vendor_sdk():
    """The lazy import is load-bearing, not stylistic.

    If `anthropic` were imported at module scope, a broken or absent SDK install
    would take offline mode down with it -- and offline mode is the path a reader
    without a key uses to run the whole system.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    probe = (
        "import sys, src.ask as a;"
        "a.main(['--offline','Q1']);"
        "print('ANTHROPIC_LOADED=' + str('anthropic' in sys.modules))"
    )
    p = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                       text=True, cwd=REPO_ROOT, env=env)
    assert p.returncode == 0, p.stderr
    assert "ANTHROPIC_LOADED=False" in p.stdout, p.stdout


def test_comparison_delta_is_computed_from_summed_totals_not_averaged_rates():
    """The 8.9pp drop must be (48/55) - (25/26), not a difference of group means.

    Q2's current window is grouped by attribution phase; the comparison window is
    not. Deriving the headline from per-group rates would make the two windows
    incomparable and the delta arithmetically meaningless.
    """
    from src import ask
    result = ask.answer_offline("Q2")
    cur, prior = result.answer, result.comparison
    assert prior is not None
    assert (cur.numerator, cur.denominator) == (48, 55)
    assert round(cur.value - prior.value, 1) == round(
        100.0 * cur.numerator / cur.denominator
        - 100.0 * prior.numerator / prior.denominator, 1
    )
    assert result.delta is not None and result.delta < 0


def test_every_gate_name_stays_separated_from_its_own_message():
    """Found by reading a refusal, not from a failing assertion.

    `time_window_bounded` is 19 characters; a hardcoded 14-wide label column ran it
    straight into its message ("time_window_boundedMetric 'on_time...'), so the
    longest and most detailed refusal was the least readable one. The width is now
    derived from GATE_NAMES, and this test fails if a gate is added that outgrows it.
    """
    from src.semantic.intent import QueryIntent
    from src.semantic.loader import load_semantic_model
    from src.semantic.validator import GATE_NAMES
    from src import ask
    model = load_semantic_model()
    base = {"metric": "on_time_delivery_pct", "dimensions": [], "filters": [],
            "grain": "order",
            "time_window": {"start": "2026-07-01", "end": "2026-07-31",
                            "label": "July 2026"},
            "intent_type": "descriptive", "comparison": None}
    # One intent per refusal shape, chosen to exercise the longest gate names.
    breakages = [
        {"dimensions": ["delivery_id"]},          # no_fanout
        {"time_window": None},                    # time_window_bounded  (19 chars)
        {"grain": "delivery"},                    # grain_matches
        {"filters": [{"column": "sales_rep", "operator": "=", "value": "X"}]},
    ]
    seen = set()
    for update in breakages:
        qi = QueryIntent.model_validate({**base, **update})
        rc, text = ask.answer_intent(qi, model)
        assert rc != 0
        for line in text.splitlines():
            for gate in GATE_NAMES:
                if line.strip().startswith(gate):
                    seen.add(gate)
                    rest = line.strip()[len(gate):]
                    assert rest.startswith("  "), (
                        f"{gate} is not separated from its message: {line!r}"
                    )
    assert "time_window_bounded" in seen, "the longest gate name was never exercised"


def test_cli_reports_the_trust_badge_it_actually_measured():
    """The badge is read from a DQ run, not asserted by the CLI.

    A hardcoded TRUSTED string would render the whole quality contract
    decorative. Proven by checking the CLI's badge equals a freshly measured one.
    """
    from src.semantic.dq import run_rules
    from src import ask
    measured = run_rules("on_time_delivery_pct")
    result = ask.answer_offline("Q1")
    assert result.answer.trust_badge == measured.badge
    assert result.answer.failing_rules == list(measured.failing_rules)
