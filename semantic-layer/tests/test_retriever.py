import pytest
from src.semantic.loader import load_semantic_model
from src.semantic.retriever import build_context, load_golden_intents, golden_intent
from src.semantic.intent import QueryIntent

@pytest.fixture(scope="module")
def model():
    return load_semantic_model()

def test_context_includes_metric_names_and_grains(model):
    ctx = build_context("on-time delivery for India warehouses last month", model)
    assert "on_time_delivery_pct" in ctx
    assert "order" in ctx

def test_context_includes_synonyms_so_model_can_map_vocabulary(model):
    ctx = build_context("what was OTD last month", model)
    assert "otd" in ctx.lower()

def test_context_includes_allowed_values_for_filters(model):
    ctx = build_context("india numbers", model)
    assert "IN" in ctx

def test_context_includes_as_of_date_for_relative_dates(model):
    """'last month' is unresolvable without a stated as-of date."""
    ctx = build_context("last month", model)
    assert "2026-08-07" in ctx

def test_context_includes_process_phases_for_diagnostic_queries(model):
    ctx = build_context("why did on-time delivery drop", model)
    assert "quality_inspection" in ctx

def test_golden_intents_cover_q1_and_q2():
    g = load_golden_intents()
    assert set(g) >= {"Q1", "Q2"}

def test_q1_golden_intent_parses_and_is_descriptive():
    qi = golden_intent("Q1")
    assert isinstance(qi, QueryIntent)
    assert qi.metric == "on_time_delivery_pct"
    assert qi.grain == "order"
    assert qi.intent_type == "descriptive"
    assert qi.time_window.start.isoformat() == "2026-07-01"
    assert qi.time_window.end.isoformat() == "2026-07-31"
    assert any(f.column == "region" and f.value == "IN" for f in qi.filters)

def test_q2_golden_intent_is_diagnostic_with_attribution():
    qi = golden_intent("Q2")
    assert qi.intent_type == "diagnostic"
    assert "delay_attribution_phase" in qi.dimensions
    assert qi.comparison is not None
    assert qi.comparison.start.isoformat() == "2026-06-01"

def test_golden_intents_pass_the_validator():
    from src.semantic.validator import validate
    model = load_semantic_model()
    for qid in ("Q1", "Q2"):
        r = validate(golden_intent(qid), model)
        assert r.ok, f"{qid} fails gates: {r.failures}"


# --- Added beyond the plan --------------------------------------------------
# The plan's 9 tests check that things are PRESENT in the context. None checks what
# must be ABSENT, and the absent cases are the governance ones: an unapproved metric
# or an un-emittable attribution value in the context is a way for the resolver to be
# confidently wrong.

def test_context_never_offers_an_unapproved_metric(model):
    """Handing the resolver a draft metric is handing it an uncertified number.

    Falsified by flipping a metric to draft in a copy of the model: the metric must
    disappear from the context, not merely be labelled.
    """
    ctx = build_context("anything", model)
    approved = set(model.approved_metric_names())
    for name in model.metric_names():
        if name not in approved:
            assert name not in ctx, f"unapproved metric {name} offered to the resolver"
    # And the guard is real, not vacuous: prove it removes a metric when one is draft.
    import copy
    from src.semantic.loader import SemanticModel
    drafted = copy.deepcopy(model._data)
    for m in drafted["metrics"]:
        if m["name"] == "first_pass_yield_pct":
            m["approval_state"] = "draft"
    ctx2 = build_context("anything", SemanticModel(_data=drafted))
    assert "first_pass_yield_pct" not in ctx2
    assert "on_time_delivery_pct" in ctx2


def test_context_marks_the_un_emittable_phases_as_not_attributable(model):
    """All 12 phases are shown so the process is legible, but only 9 are attributable.

    Presenting `demand_capture` as a valid attribution value would let the resolver
    emit a filter that passes every gate and returns zero rows -- an answer-shaped
    non-answer. The phases are still listed because a reader (and the model) needs the
    full chain to reason about 'why'; they are listed with their status.
    """
    ctx = build_context("why did it drop", model)
    # Parse the phase chain into {phase_key: attributable?} from the rendered lines,
    # so the test reads the context the way the resolver would rather than trusting the
    # YAML it was built from.
    status: dict[str, bool] = {}
    for line in ctx.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("- ") and "std " in stripped):
            continue
        key = stripped.split()[2]
        status[key] = "not attributable" not in stripped

    assert len(status) == 12, f"all 12 phases must be legible, got {sorted(status)}"
    for key in ("demand_capture", "delivery_confirmation", "billing"):
        assert key in status, f"{key} should appear in the phase chain"
        assert status[key] is False, (
            f"{key} is not an emittable attribution value and must be marked so"
        )
    for key in ("quality_inspection", "transportation", "production_execution"):
        assert status[key] is True, f"{key} must be offered as attributable"
    assert sum(status.values()) == 9, (
        f"exactly 9 phases are attributable, context offers {sum(status.values())}"
    )


def test_context_is_byte_stable_across_calls(model):
    """It is the cacheable prompt prefix; an unstable prefix defeats caching entirely."""
    a = build_context("on-time delivery for India last month", model)
    b = build_context("on-time delivery for India last month", model)
    assert a == b
    # Only the trailing question should differ between two questions.
    c = build_context("why did it drop", model)
    assert a.split("## QUESTION")[0] == c.split("## QUESTION")[0]


def test_context_covers_every_q1_filter_column(model):
    """Measured: 02_standardized_metadata's field_mappings omit ALL of these.

    A retriever built on that artifact cannot resolve "India warehouses" at all, so this
    pins the source the context is drawn from.
    """
    ctx = build_context("india warehouses bluedart plant 1010", model)
    for column in ("region", "plant", "warehouse", "carrier", "order_status"):
        assert column in ctx, f"{column} is unreachable by the resolver"
    for value in ("IN", "1010", "BLUEDART", "CANC"):
        assert value in ctx, f"allowed value {value} missing from the context"


def test_golden_intents_do_not_hardcode_the_as_of_date():
    """July dates are the question's window and legitimately literal; the as-of date is not.

    A golden intent carrying 2026-08-07 would be a second home for a value that lives in
    constants.py, and it would keep parsing long after the date stopped being current.
    """
    from pathlib import Path
    from src.semantic.constants import AS_OF_DATE, REPO_ROOT
    raw = (REPO_ROOT / "tests" / "golden_intents.json").read_text(encoding="utf-8")
    assert AS_OF_DATE.isoformat() not in raw


def test_golden_intents_compile_to_the_expected_numbers():
    """The offline path must actually produce the documented answer.

    An intent that parses and passes the gates can still describe the wrong cohort. This
    is the only test that closes the loop from stored JSON to executed number.
    """
    from src import build_warehouse
    from src.semantic.compiler import compile_sql
    from src.semantic.executor import run
    build_warehouse.build()
    model = load_semantic_model()
    intents = load_golden_intents()
    for qid in ("Q1", "Q2"):
        spec = intents[qid]
        rows = run(compile_sql(golden_intent(qid), model))
        numerator = sum(int(r["numerator"] or 0) for r in rows)
        denominator = sum(int(r["denominator"] or 0) for r in rows)
        assert (numerator, denominator) == (
            spec["expected_numerator"], spec["expected_denominator"]
        ), qid
        assert 100.0 * numerator / denominator == pytest.approx(
            spec["expected_value"], abs=0.0001
        ), qid
        if "expected_breakdown" in spec:
            got = {r["delay_attribution_phase"]: r["late_count"]
                   for r in rows if r["delay_attribution_phase"]}
            assert got == spec["expected_breakdown"], qid


def test_retriever_does_not_import_anthropic():
    """It assembles text from YAML. The resolver is the only module that calls a model."""
    import src.semantic.retriever as r, inspect
    assert "anthropic" not in inspect.getsource(r)


# --- Found by reading the emitted context, not by a failing test -------------
# Both defects below passed all 16 tests above. Reviewing the actual string the model
# would see is what surfaced them, which is why the guide prints it in full.

def test_context_never_offers_a_dimension_the_gates_always_refuse(model):
    """`delivery_id` is reachable but only through the one_to_many edge.

    `dimensions_for` listed it under every metric's groupable_by, so the resolver could
    pick it, pass schema validation, and be refused by no_fanout -- turning an answerable
    question into "I can't answer that". Offering a dimension guaranteed to fail is worse
    than omitting it: the refusal looks like a limitation of the data.
    """
    from src.semantic.retriever import queryable_dimensions
    ctx = build_context("break it down by delivery leg", model)
    assert "delivery_id" not in ctx
    for metric_name in model.approved_metric_names():
        assert "delivery_id" not in queryable_dimensions(model, metric_name)
    # Not vacuous: the reachable, safe dimensions are still offered.
    for name in ("region", "plant", "delay_attribution_phase"):
        assert name in queryable_dimensions(model, "on_time_delivery_pct")
    # And the raw reachability set does still contain it, so the filter is doing work.
    assert "delivery_id" in model.dimensions_for("on_time_delivery_pct")


def test_value_labels_never_name_a_value_outside_the_allowed_set(model):
    """The glossary labels DE, CN, BR and plant 2020; this dataset has none of them.

    Showing `DE = Germany` beside `allowed_values: IN, US` invites `region = 'DE'`. The
    gates would refuse it -- but the refusal is avoidable, and if a label were ever added
    without a matching allowed value the query would return zero rows and be presented as
    an answer.
    """
    ctx = build_context("germany numbers", model)
    for absent in ("Germany", "China", "Brazil", "2020", "3030"):
        assert absent not in ctx, f"context leaks the unavailable value {absent!r}"
    # The labels that ARE in the allowed set must survive -- this is how "India" -> IN.
    assert "IN = India" in ctx
    assert "1010 = India Plant" in ctx
