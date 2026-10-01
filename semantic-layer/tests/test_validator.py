from datetime import date
import pytest
from src.semantic.intent import QueryIntent, Filter, TimeWindow
from src.semantic.loader import load_semantic_model
from src.semantic.validator import validate

@pytest.fixture(scope="module")
def model():
    return load_semantic_model()

def _valid_intent(**over):
    base = dict(
        metric="on_time_delivery_pct",
        dimensions=[],
        filters=[Filter(column="region", operator="=", value="IN")],
        grain="order",
        time_window=TimeWindow(start=date(2026, 7, 1), end=date(2026, 7, 31),
                               label="July 2026"),
        intent_type="descriptive",
    )
    base.update(over)
    return QueryIntent(**base)

def test_valid_intent_passes_all_seven_gates(model):
    r = validate(_valid_intent(), model)
    assert r.ok, r.failures
    assert len(r.gate_results) == 7
    assert all(r.gate_results.values())

def test_gate_metric_approved_rejects_unknown_metric(model):
    r = validate(_valid_intent(metric="revenue_per_unicorn"), model)
    assert not r.ok
    assert "metric_approved" in {f.gate for f in r.failures}

def test_gate_dimensions_declared_rejects_undeclared(model):
    r = validate(_valid_intent(dimensions=["salesperson_shoe_size"]), model)
    assert not r.ok
    assert "dimensions_declared" in {f.gate for f in r.failures}

def test_gate_filters_bound_rejects_unknown_column(model):
    r = validate(_valid_intent(
        filters=[Filter(column="not_a_column", operator="=", value="X")]), model)
    assert not r.ok
    assert "filters_bound" in {f.gate for f in r.failures}

def test_gate_filters_bound_rejects_value_outside_allowed_set(model):
    """'MARS' is not a region. Catching this is why allowed_values exist."""
    r = validate(_valid_intent(
        filters=[Filter(column="region", operator="=", value="MARS")]), model)
    assert not r.ok
    assert "filters_bound" in {f.gate for f in r.failures}

def test_gate_grain_matches_rejects_wrong_grain(model):
    """The gate that prevents the 88.52% answer."""
    r = validate(_valid_intent(grain="delivery"), model)
    assert not r.ok
    assert "grain_matches" in {f.gate for f in r.failures}

def test_gate_no_fanout_rejects_one_to_many_dimension(model):
    """delivery_id is declared, but only reachable through a one_to_many join.
    It must fail no_fanout specifically -- not merely 'some gate failed'."""
    r = validate(_valid_intent(dimensions=["delivery_id"]), model)
    assert not r.ok
    assert "no_fanout" in {f.gate for f in r.failures}

def test_gate_time_window_bounded_rejects_missing_window(model):
    r = validate(_valid_intent(time_window=None), model)
    assert not r.ok
    assert "time_window_bounded" in {f.gate for f in r.failures}

def test_gate_time_window_bounded_rejects_inverted_range(model):
    r = validate(_valid_intent(time_window=TimeWindow(
        start=date(2026, 7, 31), end=date(2026, 7, 1), label="backwards")), model)
    assert not r.ok
    assert "time_window_bounded" in {f.gate for f in r.failures}

def test_failure_message_names_the_gate_and_the_problem(model):
    r = validate(_valid_intent(metric="nope"), model)
    f = next(f for f in r.failures if f.gate == "metric_approved")
    assert "nope" in f.message

def test_diagnostic_intent_with_attribution_dimension_passes(model):
    r = validate(_valid_intent(
        dimensions=["delay_attribution_phase"],
        intent_type="diagnostic",
        comparison=TimeWindow(start=date(2026, 6, 1), end=date(2026, 6, 30),
                              label="June 2026"),
    ), model)
    assert r.ok, r.failures

def test_validator_does_not_import_anthropic():
    """Structural guarantee: the gates never call an LLM."""
    import src.semantic.validator as v, inspect
    assert "anthropic" not in inspect.getsource(v)

# --- the many_to_one hop must be PERMITTED, not merely "some gate failed" ------
# fact_production_order carries no region and no promised_delivery_date, so both
# production metrics reach them through a declared many_to_one join. A no_fanout
# gate that blocks every join passes every test above while breaking 2 of 3 metrics.

def _prod_intent(metric, **over):
    base = dict(
        metric=metric, dimensions=[],
        filters=[Filter(column="region", operator="=", value="IN")],
        grain="production_order",
        time_window=TimeWindow(start=date(2026, 7, 1), end=date(2026, 7, 31),
                               label="July 2026"),
        intent_type="descriptive",
    )
    base.update(over)
    return QueryIntent(**base)

@pytest.mark.parametrize("metric",
                         ["first_pass_yield_pct", "mfg_schedule_adherence_pct"])
def test_production_metric_reaches_region_through_many_to_one(model, metric):
    """region lives on fact_order_delivery; the metric's entity is fact_production_order."""
    r = validate(_prod_intent(metric), model)
    assert r.ok, r.failures
    assert r.gate_results["no_fanout"] is True
    assert r.gate_results["filters_bound"] is True

@pytest.mark.parametrize("metric",
                         ["first_pass_yield_pct", "mfg_schedule_adherence_pct"])
def test_production_metric_can_group_by_a_joined_dimension(model, metric):
    r = validate(_prod_intent(metric, dimensions=["plant"]), model)
    assert r.ok, r.failures

def test_no_fanout_still_rejects_the_one_to_many_hop_for_production_metrics(model):
    """Permitting many_to_one must not have opened the one_to_many door."""
    r = validate(_prod_intent("first_pass_yield_pct",
                              dimensions=["delivery_id"]), model)
    assert not r.ok
    assert "no_fanout" in {f.gate for f in r.failures}


# --- exclusions_applied: the one gate with no rejection test -------------------
# Six of the seven gates above are proven to refuse something. This one was only
# ever exercised on the passing path, so nothing established that it refuses at
# all -- and it is the gate standing between a question and the naive 94.55% FPY,
# which needs exactly this failure: exclusions declared but not applied.
#
# The model is mutated in memory via a deep copy. Editing metadata/05_semantic_model.yml
# would make these tests damage the artifact the rest of the suite validates.

def _model_with_metric_patched(model, metric_name, **changes):
    """A deep copy of the model with one metric's keys changed or deleted.

    A key set to None is removed, which is how a dropped `exclusions:` block is
    simulated -- the realistic regression, since an exclusion list is far more
    likely to be deleted or emptied than to be set to a wrong type.
    """
    import copy
    from src.semantic.loader import SemanticModel
    data = copy.deepcopy(model._data)
    target = next(m for m in data["metrics"] if m["name"] == metric_name)
    for key, value in changes.items():
        if value is None:
            target.pop(key, None)
        else:
            target[key] = value
    return SemanticModel(data)


def test_gate_exclusions_applied_rejects_a_metric_whose_exclusions_were_dropped(model):
    """The gate that prevents the naive 94.55% first-pass yield.

    first_pass_yield_pct excludes rework loops and cancelled orders. Remove the block
    and the metric still computes -- it returns 52/55 instead of 51/54, which looks
    like a healthier plant rather than like a bug. The gate has to refuse rather than
    let a plausible wrong number through.
    """
    patched = _model_with_metric_patched(model, "first_pass_yield_pct", exclusions=None)
    r = validate(_prod_intent("first_pass_yield_pct"), patched)
    assert not r.ok
    assert "exclusions_applied" in {f.gate for f in r.failures}
    assert r.gate_results["exclusions_applied"] is False


def test_gate_exclusions_applied_rejects_an_empty_exclusion_list(model):
    """`exclusions: []` is the same defect as a missing block, and reads as deliberate."""
    patched = _model_with_metric_patched(model, "on_time_delivery_pct", exclusions=[])
    r = validate(_valid_intent(), patched)
    assert not r.ok
    assert "exclusions_applied" in {f.gate for f in r.failures}


def test_gate_exclusions_applied_rejects_an_exclusion_with_no_predicate(model):
    """An exclusion the compiler cannot emit SQL for.

    This is the worst shape of the three: provenance still reports
    'exclusions: cancelled_orders', so the answer arrives looking governed while the
    row it names is in the denominator.
    """
    keyed_but_toothless = [{"key": "cancelled_orders", "description": "no predicate"}]
    patched = _model_with_metric_patched(
        model, "on_time_delivery_pct", exclusions=keyed_but_toothless)
    r = validate(_valid_intent(), patched)
    assert not r.ok
    failure = next(f for f in r.failures if f.gate == "exclusions_applied")
    assert "cancelled_orders" in failure.message
    assert "predicate" in failure.message


def test_gate_exclusions_applied_rejects_an_exclusion_with_no_key(model):
    """Without a key, provenance cannot report which exclusion was applied."""
    patched = _model_with_metric_patched(
        model, "on_time_delivery_pct",
        exclusions=[{"predicate": "status <> 'CANCELLED'"}])
    r = validate(_valid_intent(), patched)
    assert not r.ok
    assert "exclusions_applied" in {f.gate for f in r.failures}


def test_every_gate_has_a_test_that_proves_it_refuses_something():
    """A gate that has never been seen to refuse is a gate nobody has tested.

    Written after finding exclusions_applied in exactly that state: implemented,
    wired into the registry, asserted True on the happy path, and never once
    observed saying no. This fails if a gate is added without a rejection test,
    which is the moment the omission is cheap to fix.
    """
    import pathlib
    from src.semantic.validator import GATE_NAMES
    src = pathlib.Path(__file__).read_text(encoding="utf-8")
    # A rejection test asserts the gate's name is among r.failures. Counting that
    # phrasing rather than the bare name avoids crediting a positive-path assertion
    # (`r.gate_results["no_fanout"] is True`) as proof of refusal.
    for gate in GATE_NAMES:
        proven = (
            f'"{gate}" in {{f.gate for f in r.failures}}' in src
            or f'f.gate == "{gate}"' in src
        )
        assert proven, (
            f"no test asserts that the {gate} gate refuses anything; it is only "
            f"exercised on the passing path"
        )
