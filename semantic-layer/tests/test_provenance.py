import json
from datetime import date
import pytest
from src import build_warehouse
from src.semantic.intent import QueryIntent, Filter, TimeWindow
from src.semantic.loader import load_semantic_model
from src.semantic.compiler import compile_sql
from src.semantic.executor import run
from src.semantic.dq import run_rules
from src.semantic.provenance import build_answer
from src.semantic.constants import METADATA_DIR

JULY = TimeWindow(start=date(2026, 7, 1), end=date(2026, 7, 31), label="July 2026")

@pytest.fixture(scope="module")
def model():
    build_warehouse.build()
    return load_semantic_model()

def _answer(model, dims=None, intent_type="descriptive"):
    qi = QueryIntent(
        metric="on_time_delivery_pct", dimensions=dims or [],
        filters=[Filter(column="region", operator="=", value="IN")],
        grain="order", time_window=JULY, intent_type=intent_type,
    )
    cq = compile_sql(qi, model)
    return build_answer(qi, cq, run(cq), model, run_rules("on_time_delivery_pct"))

def test_catalog_asset_is_valid_json_with_governance_fields():
    asset = json.loads((METADATA_DIR / "07_catalog_asset.json").read_text(encoding="utf-8"))
    for field in ("owner", "steward", "personal_data_category", "processing_purpose",
                  "legal_basis", "access_group", "retention_period",
                  "masking_policy", "certification_state", "lineage"):
        assert field in asset, f"missing governance field {field}"

def test_catalog_asset_states_enforcement_limits():
    """Spec: catalog metadata supports discovery, it does not enforce policy."""
    asset = json.loads((METADATA_DIR / "07_catalog_asset.json").read_text(encoding="utf-8"))
    note = json.dumps(asset).lower()
    assert "does not enforce" in note or "not a substitute" in note

def test_answer_carries_the_number_and_its_arithmetic(model):
    a = _answer(model)
    assert a.value == pytest.approx(87.2727, abs=0.0001)
    assert (a.numerator, a.denominator) == (48, 55)
    assert "87.3" in a.headline

def test_answer_carries_lineage(model):
    a = _answer(model)
    assert len(a.lineage) >= 3
    assert any("SAP" in s for s in a.lineage)

def test_answer_carries_exclusions_and_grain(model):
    a = _answer(model)
    assert set(a.exclusions_applied) >= {"cancelled_orders", "not_yet_due"}
    assert a.grain == "order"

def test_answer_carries_trust_badge(model):
    assert _answer(model).trust_badge == "TRUSTED"

def test_rendered_output_is_defensible_in_review(model):
    """Everything needed to defend the number must be in the rendered block."""
    text = _answer(model).render()
    for required in ("87.3", "48", "55", "order", "cancelled_orders",
                     "SAP", "TRUSTED", "on_time_delivery_pct"):
        assert required in text, f"rendered answer omits {required}"

def test_diagnostic_answer_includes_breakdown(model):
    a = _answer(model, dims=["delay_attribution_phase"], intent_type="diagnostic")
    phases = {r["delay_attribution_phase"] for r in a.breakdown}
    assert "quality_inspection" in phases
    assert "quality inspection" in a.render().lower()


# --- Added beyond the plan --------------------------------------------------
# The plan's 8 tests never check that the grouped headline agrees with the ungrouped
# one, never exercise the zero-denominator display, and never verify that the label
# comes from the dimension rather than from a string replace. Each of those is a way
# to produce a wrong-but-plausible answer block.

def test_grouped_and_ungrouped_answers_agree(model):
    """Summing then dividing, not averaging the per-group rates.

    Averaging the 4 group percentages gives a different number from the real ratio --
    Simpson's paradox -- and it would silently disagree with the same question asked
    without a breakdown. The diagnostic and descriptive answers to one question must
    not differ.
    """
    plain = _answer(model)
    grouped = _answer(model, dims=["delay_attribution_phase"], intent_type="diagnostic")
    assert (grouped.numerator, grouped.denominator) == (plain.numerator, plain.denominator)
    assert grouped.value == pytest.approx(plain.value, abs=1e-9)


def test_zero_denominator_renders_as_a_refusal_not_zero_percent(model):
    """August: 4 orders, none due. 0% would report catastrophic performance."""
    qi = QueryIntent(
        metric="on_time_delivery_pct",
        filters=[Filter(column="region", operator="=", value="IN")],
        grain="order", intent_type="descriptive",
        time_window=TimeWindow(start=date(2026, 8, 1), end=date(2026, 8, 31),
                               label="August 2026"),
    )
    cq = compile_sql(qi, model)
    a = build_answer(qi, cq, run(cq), model, run_rules("on_time_delivery_pct"))
    assert a.value is None
    assert a.denominator == 0
    assert "0.0%" not in a.headline and "0%" not in a.headline
    assert "no eligible orders" in a.headline.lower()
    assert a.display_value == "no eligible orders"
    # The block must still be defensible: exclusions and lineage do not vanish.
    text = a.render()
    assert "not_yet_due" in text and "SAP" in text


def test_phase_label_comes_from_the_dimension_not_a_string_replace():
    """`goods_receipt` renders as "Goods receipt to stock" -- underscores-to-spaces cannot.

    A blind replace passes the plan's assertion for `quality_inspection` while silently
    inventing display names for 8 of the 9 phases, so the label would drift from the
    declared model with nothing failing.
    """
    from src.semantic.provenance import phase_labels
    labels = phase_labels()
    assert labels["goods_receipt"] == "Goods receipt to stock"
    assert labels["quality_inspection"] == "Quality inspection"
    assert labels["mrp_planning"] == "Requirements planning"
    naive = {k: k.replace("_", " ") for k in labels}
    differing = {k for k in labels if labels[k].lower() != naive[k].lower()}
    assert len(differing) >= 5, (
        "if a string replace reproduced most labels, this test would not be evidence "
        "that the dimension is being read"
    )


def test_catalog_asset_does_not_hardcode_the_as_of_date():
    """It carries the token; provenance expands it at read time."""
    from src.semantic.constants import AS_OF_DATE
    from src.semantic.provenance import load_catalog_asset
    raw = (METADATA_DIR / "07_catalog_asset.json").read_text(encoding="utf-8")
    assert AS_OF_DATE.isoformat() not in raw
    assert "__AS_OF_DATE__" in raw
    assert load_catalog_asset()["certified_on"] == AS_OF_DATE.isoformat()


def test_provenance_does_not_import_anthropic():
    import src.semantic.provenance as p, inspect
    assert "anthropic" not in inspect.getsource(p)
