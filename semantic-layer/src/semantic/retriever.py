"""Assemble the metadata slice the resolver is allowed to choose from.

The resolver is the only language model in the pipeline, and it can only pick among
things it was shown. What goes into this string *is* the model's universe of possible
answers, which makes this module a governance surface rather than a formatting one:

* Omit a filter column and the resolver cannot use it -- "India warehouses" becomes
  unanswerable no matter how capable the model is.
* Include an unapproved metric and you have handed it a way to be confidently wrong,
  serving a number nobody signed off on with the same confidence as a certified one.
  `build_context` filters on `approval_state == "approved"` for exactly this reason.
* Synonyms come from `03_glossary.yml`, not the semantic model: no metric in
  `05_semantic_model.yml` carries a `synonyms` key, so "OTD" is unmappable without the
  glossary. The two artifacts are joined on the metric's `label`.
* Column bindings come from `03_column_bindings.yml`, not
  `02_standardized_metadata.json`'s `field_mappings` -- measured, the latter covers 14 of
  41 fact columns and omits *every* Q1 filter column (region, plant, warehouse, carrier,
  order_status).

This module calls no language model. It assembles text from YAML; the resolver is the
only module that talks to the API. Keeping the two apart is what lets the context be
tested, diffed, and reviewed without a key -- and there is a source-inspection test
asserting the separation, which is why the vendor SDK's name appears nowhere below.

The output is stable and ordered because it is the cacheable prompt prefix: an unstable
context defeats prompt caching and makes two runs of the same question incomparable.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from src.semantic.constants import AS_OF_DATE, METADATA_DIR, REPO_ROOT
from src.semantic.intent import QueryIntent
from src.semantic.loader import SemanticModel
from src.semantic.validator import _path_hazards

GOLDEN_INTENTS_PATH = REPO_ROOT / "tests" / "golden_intents.json"

# The boundary between the governed prefix and the volatile question. `build_context`
# renders both so the whole artifact is reviewable in one string, but the resolver must
# split here: everything above is the cacheable, governed part, and everything below is
# user text. Named once so the two sides cannot drift.
QUESTION_HEADER = "## QUESTION"


def split_context(context: str) -> tuple[str, str]:
    """(governed prefix, question) -- the cache breakpoint and the volatile tail.

    Splitting matters twice over. The prefix is byte-identical for every question, so it
    caches; and the question stays out of the block the model reads as governed
    instruction, which is otherwise a path from user text straight into the approved
    metric list.
    """
    prefix, _, tail = context.partition(QUESTION_HEADER)
    return prefix.rstrip(), tail.strip()


def queryable_dimensions(model: SemanticModel, metric_name: str) -> list[str]:
    """Dimensions a metric can actually be grouped by without tripping a gate.

    `SemanticModel.dimensions_for` answers "is this reachable", which includes
    `delivery_id` -- reachable through the declared `one_to_many` edge and therefore
    *always* rejected by `no_fanout`. Offering it to the resolver is offering a refusal:
    the model picks it, the gate rejects it, and the user gets "I can't answer that" for a
    question the layer could have answered another way.

    So the context advertises only what will survive validation. The fan-out judgement is
    imported from the validator rather than reimplemented, because two copies of that rule
    would eventually disagree and the disagreement would show up as an unexplainable
    refusal.
    """
    metric = model.get_metric(metric_name)
    if metric is None:
        return []
    entity = metric.get("entity")
    out: list[str] = []
    for name in model.dimensions_for(metric_name):
        dim = model.get_dimension(metric_name, name)
        hazards = _path_hazards(model, entity, (dim or {}).get("entity"))
        if hazards and False not in hazards:
            continue  # every path fans out; no_fanout would refuse it
        out.append(name)
    return out


def _load_yaml(name: str) -> dict[str, Any]:
    with open(METADATA_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _one_line(text: str | None) -> str:
    return " ".join((text or "").split())


# --------------------------------------------------------------------------------------
# build_context
# --------------------------------------------------------------------------------------


def build_context(question: str, model: SemanticModel) -> str:
    """Render the governed metadata slice for one question.

    The whole model is included rather than a similarity-filtered subset. With three
    metrics and eight dimensions the entire context is small enough to cache, and
    retrieving a subset would introduce a second failure mode -- the right metric being
    filtered out before the resolver ever sees it -- for no benefit at this scale. The
    `question` argument is accepted and echoed so the interface does not change when a
    larger model needs real retrieval; where that boundary sits is documented in the
    guide.
    """
    glossary = _load_yaml("03_glossary.yml")
    bindings = _load_yaml("03_column_bindings.yml")
    process = _load_yaml("04_process_model.yml")
    terms_by_name = {t["term"]: t for t in glossary["terms"]}

    out: list[str] = []
    out.append("# GOVERNED SEMANTIC METADATA")
    out.append("")
    out.append(
        "You may only choose from the metrics, dimensions and values below. If the "
        "question cannot be answered from them, say so -- do not substitute a near "
        "approximation."
    )
    out.append("")
    out.append(f"AS_OF_DATE: {AS_OF_DATE.isoformat()}")
    out.append(
        "  Relative dates resolve against this date. "
        f"'last month' = {AS_OF_DATE.year}-{AS_OF_DATE.month - 1:02d}, "
        "'this month' = the month containing AS_OF_DATE."
    )
    out.append("")

    # --- metrics: approved only, with the vocabulary that maps to them -----------------
    out.append("## APPROVED METRICS")
    out.append("")
    for name in model.approved_metric_names():
        metric = model.get_metric(name)
        term = terms_by_name.get(metric.get("label", ""), {})
        synonyms = term.get("synonyms") or []
        out.append(f"- metric: {name}")
        out.append(f"  label: {metric.get('label')}")
        out.append(f"  grain: {metric.get('grain')}   (one row per {metric.get('grain')})")
        out.append(f"  time_dimension: {metric.get('time_dimension')}")
        out.append(f"  definition: {_one_line(metric.get('description'))}")
        if synonyms:
            out.append(f"  also called: {', '.join(synonyms)}")
        exclusions = [e.get("key") for e in metric.get("exclusions") or []]
        if exclusions:
            out.append(
                f"  always excluded: {', '.join(exclusions)} (applied automatically -- "
                f"do not add filters for these)"
            )
        out.append(f"  groupable_by: {', '.join(queryable_dimensions(model, name))}")
        out.append("")

    # --- dimensions: the filter and group-by vocabulary, with legal values -------------
    # Only dimensions that survive the gates for at least one approved metric. A
    # dimension the validator always refuses is not vocabulary, it is a trapdoor.
    queryable = {
        name
        for metric_name in model.approved_metric_names()
        for name in queryable_dimensions(model, metric_name)
    }
    out.append("## DIMENSIONS")
    out.append("")
    for dim in model._data.get("dimensions", []):
        if dim["name"] not in queryable:
            continue
        term = terms_by_name.get(dim.get("label", ""), {})
        synonyms = term.get("synonyms") or []
        line = f"- {dim['name']} ({dim.get('data_type', 'string')})"
        out.append(line)
        if dim.get("label"):
            out.append(f"    label: {dim['label']}")
        if synonyms:
            out.append(f"    also called: {', '.join(synonyms)}")
        allowed = dim.get("allowed_values")
        if allowed:
            out.append(f"    allowed_values: {', '.join(str(a) for a in allowed)}")
        # Value labels are the bridge from "India" to `IN`, but the glossary carries
        # labels for codes this dataset does not contain (DE, CN, BR, plant 2020). Showing
        # them invites `region = 'DE'`: a filter the gates then refuse, or worse -- if a
        # label were ever added without the value -- a query returning zero rows dressed
        # as an answer. Intersect with the declared allowed values.
        labels = term.get("value_labels") or {}
        if labels:
            permitted = {str(a) for a in (allowed or [])}
            shown = {
                k: v for k, v in labels.items()
                if not permitted or str(k) in permitted
            }
            if shown:
                rendered = ", ".join(f"{k} = {v}" for k, v in shown.items())
                out.append(f"    value_labels: {rendered}")
        out.append(f"    {_one_line(dim.get('description'))}")
        out.append("")

    # --- business vocabulary that is not a metric or dimension -------------------------
    out.append("## BUSINESS TERM BINDINGS  (word -> physical column)")
    out.append("")
    for binding in bindings["bindings"]:
        if binding.get("scope") != "business":
            continue
        term = terms_by_name.get(binding["term"], {})
        synonyms = term.get("synonyms") or []
        also = f"  [also: {', '.join(synonyms)}]" if synonyms else ""
        out.append(
            f"- {binding['term']} -> {binding['table']}.{binding['column']}{also}"
        )
    out.append("")

    # --- process phases: the attribution domain for diagnostic questions ---------------
    out.append("## PROCESS PHASES  (plan-to-deliver; the 'why' chain)")
    out.append("")
    attribution = model.get_dimension("on_time_delivery_pct", "delay_attribution_phase")
    emittable = set(attribution.get("allowed_values") or []) if attribution else set()
    for phase in sorted(process["phases"], key=lambda p: p["phase_seq"]):
        key = phase["phase_key"]
        mark = "attributable" if key in emittable else "not attributable"
        out.append(
            f"- {phase['phase_seq']:>2}. {key:<22} {phase['phase_name']}"
            f"  [{phase['sap_module']}, std {phase['standard_duration_days']}d, {mark}]"
        )
    out.append("")
    out.append(
        "  delay_attribution_phase is only one of the values marked attributable. "
        "A late order is attributed to the phase with the largest positive variance "
        "against its standard duration."
    )
    out.append("")

    out.append(QUESTION_HEADER)
    out.append("")
    out.append(question)
    return "\n".join(out)


# --------------------------------------------------------------------------------------
# golden intents -- the offline path
# --------------------------------------------------------------------------------------


def load_golden_intents(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Read the hand-authored intents that make the pipeline runnable with no API key.

    These are not test fixtures in the incidental sense: they are the offline mode. Every
    stage except the resolver is exercised by them, which is what lets a reader without a
    key run the whole system and lets CI assert the canonical numbers.
    """
    with open(path or GOLDEN_INTENTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def golden_intent(qid: str, path: Path | None = None) -> QueryIntent:
    """Parse one golden intent into a validated `QueryIntent`.

    Parsed through the same Pydantic model the resolver's output goes through, so a
    golden intent that would fail schema validation fails here rather than looking
    authoritative. `extra="forbid"` means a typo'd key in the JSON is an error, not a
    silently ignored field.
    """
    intents = load_golden_intents(path)
    if qid not in intents:
        raise KeyError(
            f"no golden intent {qid!r}; available: {', '.join(sorted(intents))}"
        )
    return QueryIntent.model_validate(intents[qid]["intent"])
