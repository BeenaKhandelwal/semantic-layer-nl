"""The single-file demo published in the Medium post must run, and must agree.

Two distinct risks, and they need different tests:

1. It stops running. Published code that crashes on paste is worse than no published
   code, so `test_the_standalone_runs_clean_with_no_api_key` executes it as a subprocess
   with the environment stripped.

2. It keeps running but drifts. The demo embeds its own copy of the data and its own copy
   of the metadata, so nothing forces it to agree with the project it was extracted from.
   The cross-check tests recompute each headline figure from the REAL warehouse and the
   REAL semantic model and compare, so a change to either side that isn't mirrored fails
   here rather than in a reader's terminal.

Deliberately NOT asserted: that the standalone's output is byte-identical to `src/ask.py`.
It is a different program with a narrower job, and pinning its formatting to the CLI's
would make every cosmetic change to either one a two-file edit for no gain.
"""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
STANDALONE = REPO_ROOT / "standalone" / "semantic_layer_demo.py"


def _load_standalone():
    """Import the demo without putting `standalone/` on `sys.path` permanently.

    The `sys.modules` registration is required, not tidiness: the demo uses
    `from __future__ import annotations`, so `@dataclass` resolves its field annotations
    by looking the defining module up in `sys.modules`, and an unregistered module makes
    that lookup return None.
    """
    spec = importlib.util.spec_from_file_location("_sl_demo", STANDALONE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def demo():
    return _load_standalone()


@pytest.fixture(scope="module")
def output() -> str:
    """The demo's real stdout, with no API key and no repo on the path.

    `-E` ignores PYTHON* environment variables and the cleared env removes the key, so a
    pass here means a reader with neither credentials nor this repository gets the same
    output. Run from a temp-ish cwd would be stricter still, but the script reads no files
    at all -- which `test_the_standalone_reads_no_files_and_imports_nothing_local` pins.
    """
    env = {k: v for k, v in os.environ.items()
           if k in ("SYSTEMROOT", "PATH", "TEMP", "TMP", "COMSPEC", "WINDIR")}
    proc = subprocess.run([sys.executable, "-E", str(STANDALONE)],
                          capture_output=True, text=True, env=env, timeout=180)
    assert proc.returncode == 0, (
        f"the published demo exited {proc.returncode}\n"
        f"--- stdout ---\n{proc.stdout[-3000:]}\n--- stderr ---\n{proc.stderr[-3000:]}"
    )
    return proc.stdout


# ======================================================================================
# 1. It runs
# ======================================================================================


def test_the_standalone_runs_clean_with_no_api_key(output: str) -> None:
    """Exit 0 is asserted in the fixture; here we check it did not exit 0 having quietly
    skipped its own demonstrations. `main` counts them and says so."""
    assert "OK -- every demonstration behaved as documented." in output
    assert "FAILED" not in output


def test_the_standalone_reads_no_files_and_imports_nothing_local(demo) -> None:
    """Self-contained is the entire promise of the artifact.

    An `import src.semantic...` or an `open(...)` would still pass every other test in
    this file, because the repository is present when the tests run. It would fail for
    the reader, which is the only place it matters.
    """
    source = STANDALONE.read_text(encoding="utf-8")
    code = re.sub(r'"""(?:.|\n)*?"""', "", source)          # drop docstrings

    for forbidden in ("from src", "import src", "read_text(", "open(",
                      "Path(__file__)", "read_csv"):
        assert forbidden not in code, (
            f"the standalone must not use {forbidden!r}: a reader who pasted this file "
            f"into an empty directory has no repository and no data files"
        )

    third_party = {n for n in re.findall(r"^\s*import (\w+)", code, re.M)
                   if n not in sys.stdlib_module_names}
    assert third_party <= {"duckdb", "yaml", "anthropic"}, (
        f"the post tells the reader to `pip install duckdb pyyaml`; this file also "
        f"imports {sorted(third_party - {'duckdb', 'yaml', 'anthropic'})}"
    )


def test_the_only_model_call_is_in_the_resolver(demo) -> None:
    """The architectural claim, checked against the code rather than the prose.

    If `anthropic` were reachable from the compiler or the validator, the claim "the model
    never writes SQL and never does arithmetic" would be a comment, not a property.
    """
    source = STANDALONE.read_text(encoding="utf-8")
    body = source[source.index("def resolve_with_claude"):]
    outside = source[:source.index("def resolve_with_claude")]
    assert "anthropic" in body
    assert "import anthropic" not in outside, (
        "anthropic is imported outside resolve_with_claude, so some other stage can "
        "reach a model"
    )


# ======================================================================================
# 2. It agrees with the project it was extracted from
# ======================================================================================


def test_the_headline_figure_matches_the_real_pipeline(output: str) -> None:
    """87.3% and 48/55 recomputed from the committed warehouse, not from a constant."""
    import duckdb

    from src.semantic.constants import DB_PATH

    con = duckdb.connect(str(DB_PATH), read_only=True)
    num, den = con.execute("""
        SELECT sum(CASE WHEN is_on_time THEN 1 ELSE 0 END),
               sum(CASE WHEN is_eligible THEN 1 ELSE 0 END)
        FROM fact_order_delivery
        WHERE is_eligible AND region = 'IN'
          AND promised_delivery_date BETWEEN DATE '2026-07-01' AND DATE '2026-07-31'
    """).fetchone()
    con.close()

    assert f"{num} / {den} = {100 * num / den:.4f}%" in output
    assert f"is {100 * num / den:.1f}% -- {num} of {den} eligible orders" in output


def test_the_counter_demo_matches_the_real_delivery_grain_number(output: str) -> None:
    """88.5% is the whole reason the project exists; it has to be the real 88.5%."""
    import duckdb

    from src.semantic.constants import DB_PATH

    con = duckdb.connect(str(DB_PATH), read_only=True)
    num, den = con.execute("""
        SELECT sum(CASE WHEN d.delivery_date <= o.promised_delivery_date THEN 1 ELSE 0 END),
               count(*)
        FROM fact_order_delivery o JOIN stg_deliveries d USING (order_id)
        WHERE o.is_eligible AND o.region = 'IN'
          AND o.promised_delivery_date BETWEEN DATE '2026-07-01' AND DATE '2026-07-31'
    """).fetchone()
    con.close()

    assert f"{num} / {den} = {100 * num / den:.4f}%" in output


def test_the_prior_window_comparison_matches_the_real_june_number(output: str) -> None:
    import duckdb

    from src.semantic.constants import DB_PATH

    con = duckdb.connect(str(DB_PATH), read_only=True)
    num, den = con.execute("""
        SELECT sum(CASE WHEN is_on_time THEN 1 ELSE 0 END),
               sum(CASE WHEN is_eligible THEN 1 ELSE 0 END)
        FROM fact_order_delivery
        WHERE is_eligible AND region = 'IN'
          AND promised_delivery_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-30'
    """).fetchone()
    con.close()

    assert f"{100 * num / den:.1f}% ({num} / {den})" in output


def test_the_embedded_metric_definition_matches_the_governed_one(demo) -> None:
    """The fields that decide correctness, compared field by field with P5.

    A demo that declares `grain: delivery` while the project declares `grain: order`
    teaches the reader the exact mistake the project is about.
    """
    from src.semantic.loader import load_semantic_model

    real = load_semantic_model().get_metric("on_time_delivery_pct")
    mine = demo.get_metric(demo.load_model(), "on_time_delivery_pct")

    for field in ("grain", "entity", "time_dimension", "approval_state"):
        assert mine[field] == real[field], (
            f"{field}: demo says {mine[field]!r}, P5 says {real[field]!r}"
        )
    for half in ("numerator", "denominator"):
        assert mine["expression"][half] == real["expression"][half]
    assert [e["key"] for e in mine["exclusions"]] == [e["key"] for e in real["exclusions"]]
    assert list(mine["lineage"]) == list(real["lineage"])


def test_the_embedded_allowed_values_match_the_governed_ones(demo) -> None:
    """Caught a real drift: the demo shipped `plant: [1010, 1020, 2010]` against P5's
    `[1010, 1710]`.

    Allowed values are what `filters_bound` enforces, so a demo with its own list teaches
    the reader that a question the real system refuses is answerable, or vice versa.
    """
    from src.semantic.loader import load_semantic_model

    real = load_semantic_model()
    mine = demo.load_model()["_dims_by_name"]
    for name in ("region", "plant", "carrier"):
        governed = real.get_dimension("on_time_delivery_pct", name)["allowed_values"]
        assert set(mine[name]["allowed_values"]) == set(governed), (
            f"{name}: demo has {sorted(mine[name]['allowed_values'])}, "
            f"P5 has {sorted(governed)}"
        )


def test_the_embedded_synonyms_match_the_governed_glossary(demo) -> None:
    """A synonym the project sanctions but the demo omits is a question the reader's copy
    refuses and the real system answers."""
    import yaml

    from src.semantic.constants import METADATA_DIR

    real = yaml.safe_load((METADATA_DIR / "03_glossary.yml").read_text(encoding="utf-8"))
    entry = next(t for t in real["terms"] if t["term"] == "On-Time Delivery %")
    mine = next(t for t in demo.load_model()["glossary"]
                if t["metric"] == "on_time_delivery_pct")
    assert sorted(mine["synonyms"]) == sorted(entry["synonyms"])
    # The definition is what states the grain in prose the model reads, so it has to be
    # the same prose -- not a paraphrase that drops "one row per order_id".
    assert " ".join(mine["definition"].split()) == " ".join(entry["definition"].split())


def test_the_demo_runs_every_gate_the_project_declares(demo) -> None:
    from src.semantic.validator import GATE_NAMES

    assert set(demo.GATE_NAMES) == set(GATE_NAMES)


def test_every_declared_gate_is_actually_evaluated_not_just_named(demo) -> None:
    """`GATE_NAMES` is a tuple of strings; a gate can be listed and never run.

    The project's rule is that all seven gates run on every intent and an unevaluable gate
    fails closed. A demo that names seven and evaluates five would print `5/5 passed` and
    look completely convincing.
    """
    model = demo.load_model()
    result = demo.validate(
        demo.QueryIntent(intent_type="descriptive", metric="on_time_delivery_pct",
                         grain="order", time_window=("2026-07-01", "2026-07-31")),
        model,
    )
    assert set(result.passed) == set(demo.GATE_NAMES), (
        f"gates declared but never evaluated: "
        f"{sorted(set(demo.GATE_NAMES) - set(result.passed))}"
    )
    assert result.ok


@pytest.mark.parametrize(
    "gate,mutate",
    [
        ("grain_matches", {"grain": "delivery"}),
        ("metric_approved", {"metric": "production_cycle_time_days"}),
        ("time_window_bounded", {"time_window": ("2026-07-31", "2026-07-01")}),
        ("dimensions_declared", {"dimensions": ("moon_phase",)}),
        ("no_fanout", {"dimensions": ("delivery_id",)}),
    ],
)
def test_each_gate_refuses_the_thing_it_exists_to_refuse(demo, gate, mutate) -> None:
    """One case per gate, because a gate that never fires is indistinguishable from one
    that always passes."""
    base = dict(intent_type="descriptive", metric="on_time_delivery_pct", grain="order",
                time_window=("2026-07-01", "2026-07-31"))
    result = demo.validate(demo.QueryIntent(**{**base, **mutate}), demo.load_model())
    assert not result.ok
    assert gate in [name for name, _ in result.failures], (
        f"expected {gate} to refuse {mutate}; got "
        f"{[n for n, _ in result.failures] or 'no failures at all'}"
    )


def test_a_filter_value_outside_allowed_values_is_refused_not_silently_empty(demo) -> None:
    """The zero-rows failure mode: `region = 'MARS'` is legal SQL returning nothing, and
    nothing gets read as an answer."""
    model = demo.load_model()
    result = demo.validate(
        demo.QueryIntent(intent_type="descriptive", metric="on_time_delivery_pct",
                         grain="order", time_window=("2026-07-01", "2026-07-31"),
                         filters=(demo.Filter("region", "=", "MARS"),)),
        model,
    )
    assert "filters_bound" in [n for n, _ in result.failures]


def test_validation_happens_before_compilation(demo) -> None:
    """A refused intent must never reach the compiler.

    Checked by making compilation observably fatal: if `answer` compiles first and
    validates second, this raises instead of returning a refusal.
    """
    model = demo.load_model()
    con = demo.build_warehouse()
    original = demo.compile_sql
    calls: list[str] = []

    def spy(qi, m, window=None):
        calls.append(qi.metric)
        return original(qi, m, window)

    demo.compile_sql = spy
    try:
        rc, out = demo.answer(
            con,
            demo.QueryIntent(intent_type="descriptive", metric="on_time_delivery_pct",
                             grain="delivery",
                             time_window=("2026-07-01", "2026-07-31")),
            model,
        )
    finally:
        demo.compile_sql = original

    assert rc == 1 and out.startswith("REFUSED")
    assert calls == [], "a refused intent was compiled to SQL anyway"


def test_the_refusal_names_the_gate_and_shows_no_number(output: str) -> None:
    # Anchored on the refusal itself, not on the word: the section heading above it also
    # contains "REFUSED", and a test that matched the heading would pass on a run where
    # the refusal never printed.
    block = output[output.index("REFUSED  on_time_delivery_pct"):]
    block = block[:block.index("=" * 20)]
    flat = " ".join(block.split())        # the reason is wrapped across three lines
    assert "gates failed  grain_matches" in block
    assert "is certified at grain 'order'; the intent asks for grain 'delivery'" in flat
    assert not re.search(r"\d+\.\d+%", block), (
        f"a refusal must not carry a number:\n{block}"
    )


def test_the_attribution_breakdown_matches_the_real_process_model(output: str) -> None:
    """The per-phase tally, recomputed from `fact_order_delivery`'s variance columns."""
    import duckdb

    from src.semantic.constants import DB_PATH

    con = duckdb.connect(str(DB_PATH), read_only=True)
    rows = con.execute("""
        SELECT delay_attribution_phase, count(*)
        FROM fact_order_delivery
        WHERE is_eligible AND NOT is_on_time AND region = 'IN'
          AND promised_delivery_date BETWEEN DATE '2026-07-01' AND DATE '2026-07-31'
        GROUP BY 1
    """).fetchall()
    con.close()

    labels = {"quality_inspection": "Quality inspection",
              "transportation": "Transportation",
              "production_execution": "Production execution"}
    assert rows, "no late orders in the window; this test would assert nothing"
    for phase, count in rows:
        label = labels[phase]
        assert re.search(rf"^\s+{re.escape(label)}\s+{count}$", output, re.M), (
            f"the demo's breakdown does not report {label} = {count}"
        )
    assert re.search(r"^\s+unattributed\s+\d+$", output, re.M), (
        "unattributed must be printed even when zero, or the tally cannot be audited"
    )


def test_the_counter_intuitive_finding_is_measured_not_asserted(output: str) -> None:
    """"Transportation ran under standard on 5 of 7" is the article's strongest claim."""
    import duckdb

    from src.semantic.constants import DB_PATH

    con = duckdb.connect(str(DB_PATH), read_only=True)
    under, late = con.execute("""
        SELECT sum(CASE WHEN var_shipment < 0 THEN 1 ELSE 0 END), count(*)
        FROM fact_order_delivery
        WHERE is_eligible AND NOT is_on_time AND region = 'IN'
          AND promised_delivery_date BETWEEN DATE '2026-07-01' AND DATE '2026-07-31'
    """).fetchone()
    con.close()

    assert f"UNDER its standard on {under} of {late} late orders" in output


def test_the_attribution_population_check_actually_fires(demo) -> None:
    """The demo embeds its variance rows but DERIVES lateness, so the two can diverge.

    It guards that with an assertion. An assertion nobody has seen fail is a comment, so
    this one is made to fail: substitute an order id that is not late and confirm the
    breakdown refuses to be printed rather than describing the wrong population.
    """
    demo.PHASE_VARIANCE_CSV = demo.PHASE_VARIANCE_CSV.replace("SO-1002,", "SO-9999,")
    try:
        con = demo.build_warehouse()
        model = demo.load_model()
        qi = demo.resolve_offline("Why did OTD drop for India last month?", model)
        with pytest.raises(AssertionError, match="attribution population mismatch"):
            demo.answer(con, qi, model)
    finally:
        demo.PHASE_VARIANCE_CSV = demo.PHASE_VARIANCE_CSV.replace("SO-9999,", "SO-1002,")


# ======================================================================================
# 3. The resolver, which is the only stage a model touches
# ======================================================================================


def test_the_resolver_takes_the_grain_from_metadata_not_from_the_question(demo) -> None:
    """The question says "deliveries"; the answer must still be at order grain."""
    model = demo.load_model()
    qi = demo.resolve_offline("how many deliveries were on time delivery last month",
                              model)
    assert qi.grain == demo.get_metric(model, "on_time_delivery_pct")["grain"] == "order"


def test_every_sanctioned_synonym_resolves_to_the_metric(demo) -> None:
    model = demo.load_model()
    entry = next(t for t in model["glossary"] if t["metric"] == "on_time_delivery_pct")
    for synonym in entry["synonyms"]:
        qi = demo.resolve_offline(f"what was {synonym} last month", model)
        assert qi.metric == "on_time_delivery_pct", f"{synonym!r} resolved to {qi.metric}"


def test_a_question_with_no_governed_metric_is_refused_not_guessed(demo) -> None:
    with pytest.raises(ValueError, match="No governed metric"):
        demo.resolve_offline("what was revenue by salesperson last quarter",
                             demo.load_model())


@pytest.mark.parametrize(
    "question,expected",
    [
        ("What was OTD for India warehouses last month?", {("region", "IN")}),
        # "IN" is a substring of "inspection" and also an English preposition. Both once
        # produced a phantom region filter that every gate passed, because a filter on a
        # declared dimension with a declared value is perfectly legal.
        ("What was quality inspection driven OTD last month?", set()),
        ("What was delivery reliability for FEDEX in APAC?",
         {("region", "APAC"), ("carrier", "FEDEX")}),
        ("on-time delivery for plant 1010 in EU", {("region", "EU"), ("plant", "1010")}),
    ],
)
def test_the_resolver_does_not_invent_filters(demo, question, expected) -> None:
    qi = demo.resolve_offline(question, demo.load_model())
    assert {(f.column, f.value) for f in qi.filters} == expected


def test_the_offline_and_live_resolvers_are_interchangeable(demo) -> None:
    """Same signature, same return type. If the downstream stages could tell which
    resolver produced an intent, the boundary would be leaking."""
    import inspect

    offline = inspect.signature(demo.resolve_offline)
    live = inspect.signature(demo.resolve_with_claude)
    assert list(offline.parameters) == list(live.parameters)
    assert offline.return_annotation == live.return_annotation == "QueryIntent"


def test_the_live_resolver_only_offers_approved_metrics(demo) -> None:
    """The retriever's job, stated as a property of the source.

    `production_cycle_time_days` exists in the embedded model with `approval_state:
    draft`. The enum handed to the tool must not contain it -- an unapproved metric should
    be unaskable because it was never offered, not merely because a gate would catch it.
    """
    source = STANDALONE.read_text(encoding="utf-8")
    body = source[source.index("def resolve_with_claude"):]
    body = body[:body.index("# " + "=" * 20)]
    assert 'approval_state"] == "approved"' in body
    assert '"enum": [m["name"] for m in approved]' in body


# ======================================================================================
# 4. The compiler
# ======================================================================================


def test_the_compiler_is_deterministic(demo) -> None:
    model = demo.load_model()
    qi = demo.QueryIntent(intent_type="descriptive", metric="on_time_delivery_pct",
                          grain="order", time_window=("2026-07-01", "2026-07-31"),
                          filters=(demo.Filter("region", "=", "IN"),))
    assert demo.compile_sql(qi, model) == demo.compile_sql(qi, model)


def test_the_compiler_always_applies_every_declared_exclusion(demo) -> None:
    """Exclusions are not optional and not conditional on the question.

    An intent that mentions neither cancellations nor due dates must still exclude both,
    or the denominator is wrong in a way no gate can see.
    """
    model = demo.load_model()
    sql = demo.compile_sql(
        demo.QueryIntent(intent_type="descriptive", metric="on_time_delivery_pct",
                         grain="order", time_window=("2026-07-01", "2026-07-31")),
        model,
    )
    for exclusion in demo.get_metric(model, "on_time_delivery_pct")["exclusions"]:
        assert exclusion["predicate"] in sql, f"{exclusion['key']} was not applied"


def test_the_compiler_sums_numerators_and_denominators_rather_than_averaging(demo) -> None:
    """Grouped ratios are the Simpson's-paradox trap.

    `avg(rate)` across groups of unequal size is a different number from
    `sum(num)/sum(den)`, and it looks entirely reasonable. Checked structurally: the
    grouped SQL must divide two sums, never average a rate.
    """
    model = demo.load_model()
    sql = demo.compile_sql(
        demo.QueryIntent(intent_type="descriptive", metric="on_time_delivery_pct",
                         grain="order", time_window=("2026-07-01", "2026-07-31"),
                         dimensions=("carrier",)),
        model,
    )
    assert "GROUP BY carrier" in sql
    assert re.search(r"sum\(.+?\)\s*/\s*nullif\(sum\(", sql), sql
    assert "avg(" not in sql.lower().replace("average", "")


def test_grouped_and_ungrouped_totals_reconcile(demo) -> None:
    """The property the previous test protects, measured on the real numbers: the
    per-carrier numerators and denominators must sum to the total."""
    model = demo.load_model()
    con = demo.build_warehouse()
    base = dict(intent_type="descriptive", metric="on_time_delivery_pct", grain="order",
                time_window=("2026-07-01", "2026-07-31"))

    total = demo.execute(con, demo.QueryIntent(**base), model)
    grouped = con.execute(
        demo.compile_sql(demo.QueryIntent(**base, dimensions=("carrier",)), model)
    ).fetchall()

    # Grouped rows are (carrier, value, numerator, denominator) -- the group column shifts
    # the measures right by one, which is exactly the kind of off-by-one that makes a
    # reconciliation test pass against the wrong pair of columns.
    assert len(grouped) > 1, "one group reconciles trivially; this proves nothing"
    assert sum(r[-1] for r in grouped) == total.denominator
    assert sum(r[-2] for r in grouped) == total.numerator
