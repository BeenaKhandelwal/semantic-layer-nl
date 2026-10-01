import pytest
from src.semantic.loader import load_semantic_model, SemanticModelError

@pytest.fixture(scope="module")
def model():
    return load_semantic_model()

def test_three_metrics_defined(model):
    assert set(model.metric_names()) == {
        "on_time_delivery_pct", "mfg_schedule_adherence_pct", "first_pass_yield_pct"
    }

def test_all_mvp_metrics_approved(model):
    assert set(model.approved_metric_names()) == set(model.metric_names())

def test_otd_declares_grain_and_exclusions(model):
    m = model.get_metric("on_time_delivery_pct")
    assert m["grain"] == "order"
    assert m["entity"] == "fact_order_delivery"
    keys = {e["key"] for e in m["exclusions"]}
    assert {"cancelled_orders", "not_yet_due"} <= keys

def test_fpy_excludes_rework_reinspections(model):
    """The exclusion that prevents the 94.55% wrong answer."""
    m = model.get_metric("first_pass_yield_pct")
    assert m["grain"] == "production_order"
    keys = {e["key"] for e in m["exclusions"]}
    assert "rework_reinspections" in keys

def test_metrics_have_distinct_grains(model):
    grains = {model.get_metric(n)["grain"] for n in model.metric_names()}
    assert len(grains) >= 2, "a single-grain model cannot demonstrate fan-out"

def test_every_metric_has_owner_and_lineage(model):
    for name in model.metric_names():
        m = model.get_metric(name)
        assert m["owner"] and m["steward"]
        assert len(m["lineage"]) >= 3

def test_otd_dimensions_include_attribution(model):
    dims = model.dimensions_for("on_time_delivery_pct")
    for d in ("region", "plant", "warehouse", "carrier", "delay_attribution_phase"):
        assert d in dims

def test_joins_declare_cardinality(model):
    """Without declared cardinality the validator cannot detect fan-out."""
    ent = model.get_entity("fact_order_delivery")
    for join in ent.get("joins", []):
        assert join["cardinality"] in ("one_to_one", "one_to_many", "many_to_one")

def test_rejects_metric_with_unknown_entity(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        "entities:\n"
        "  - name: fact_a\n    grain: a\n"
        "dimensions: []\n"
        "metrics:\n"
        "  - name: m\n    entity: does_not_exist\n    grain: a\n"
        "    approval_state: approved\n",
        encoding="utf-8",
    )
    with pytest.raises(SemanticModelError, match="does_not_exist"):
        load_semantic_model(bad)

def test_rejects_metric_grain_not_matching_entity(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        "entities:\n"
        "  - name: fact_a\n    grain: order\n"
        "dimensions: []\n"
        "metrics:\n"
        "  - name: m\n    entity: fact_a\n    grain: delivery\n"
        "    approval_state: approved\n",
        encoding="utf-8",
    )
    with pytest.raises(SemanticModelError, match="grain"):
        load_semantic_model(bad)


def test_no_yaml_key_parsed_as_a_boolean():
    """The Norway problem: bare `on:` is boolean True in YAML 1.1, not "on".

    Every join declared `on: order_id`, so PyYAML stored the key as True and
    `join["on"]` raised KeyError -- the compiler could not read the join key it was
    required to emit. `_validate_structure` never looked at the key name, so the
    model loaded clean and all 10 loader tests passed. Renamed to `join_key`.

    Also catches y/n/yes/no/off, which YAML 1.1 coerces the same way, anywhere in
    the model. A key that is not a string is always a bug here.
    """
    import yaml
    from src.semantic.constants import METADATA_DIR

    def walk(node, path="root"):
        bad = []
        if isinstance(node, dict):
            for k, v in node.items():
                if not isinstance(k, str):
                    bad.append(f"{path}: key {k!r} ({type(k).__name__}) is not a string")
                bad += walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                bad += walk(v, f"{path}[{i}]")
        return bad

    for name in ("05_semantic_model.yml", "06_dq_rules.yml", "03_glossary.yml",
                 "04_process_model.yml", "03_column_bindings.yml"):
        with open(METADATA_DIR / name, encoding="utf-8") as f:
            doc = yaml.safe_load(f)
        offenders = walk(doc, name)
        assert offenders == [], f"YAML 1.1 coerced a key in {name}: {offenders}"


def test_categorical_allowed_values_are_strings_everywhere():
    """Plant codes are VARCHAR in the warehouse; unquoted `1010` is an int in YAML.

    The glossary declared allowed_values [1010, 1710] as ints while
    05_semantic_model.yml declared ['1010', '1710'] as strings, so a gate comparing a
    resolved filter value against the glossary domain would never match -- and the
    value_labels lookup for a plant returned nothing. Same class as the Norway problem,
    on the value side rather than the key side.
    """
    import yaml
    from src.semantic.constants import METADATA_DIR

    offenders = []
    for name in ("05_semantic_model.yml", "03_glossary.yml"):
        with open(METADATA_DIR / name, encoding="utf-8") as f:
            doc = yaml.safe_load(f)
        for section in ("dimensions", "terms"):
            for item in doc.get(section) or []:
                for v in item.get("allowed_values") or []:
                    if not isinstance(v, str):
                        offenders.append(
                            f"{name}:{item.get('name') or item.get('term')} "
                            f"allowed_value {v!r} is {type(v).__name__}, not str")
    assert offenders == [], offenders


def test_every_join_declares_a_readable_key_and_cardinality():
    """A join the compiler cannot read is a join it cannot emit."""
    model = load_semantic_model()
    seen = 0
    for entity in model._data["entities"]:
        for join in entity.get("joins") or []:
            seen += 1
            assert isinstance(join.get("join_key"), str) and join["join_key"], (
                f"{entity['name']} -> {join.get('to')} has no readable join_key")
            assert join["cardinality"] in ("one_to_one", "one_to_many", "many_to_one")
            assert join.get("note"), (
                f"{entity['name']} -> {join['to']} has no note; a join's hazard or "
                "necessity must be written down where the next reader will look")
    assert seen == 3, f"expected 3 declared joins, found {seen}"
