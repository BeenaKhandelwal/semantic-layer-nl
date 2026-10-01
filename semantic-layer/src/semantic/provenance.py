"""Assemble the answer, plus everything needed to challenge it.

An answer nobody can defend in a review is not an answer. "87.3%" on its own invites
exactly one useful question -- *says who?* -- and a pipeline that cannot answer it has
moved the trust problem rather than solved it. So the arithmetic, the grain, the
exclusions applied, the lineage chain, and the data-quality badge all travel with the
number and all appear in the rendered block.

This module formats governed output. It does not ask a model anything, and it does not
compute the metric: the numbers arrive from the executor and are only ever displayed.
`.value` therefore stays unrounded while the display rounds to one decimal -- a rounded
stored value would quietly become the input to somebody's next calculation.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb

from src.semantic.compiler import AS_OF_TOKEN, CompiledQuery
from src.semantic.constants import AS_OF_DATE, DB_PATH, METADATA_DIR
from src.semantic.dq import DQReport
from src.semantic.intent import QueryIntent
from src.semantic.loader import SemanticModel

CATALOG_PATH = METADATA_DIR / "07_catalog_asset.json"


def load_catalog_asset(path: Path | None = None) -> dict[str, Any]:
    """Read the catalog entry, expanding the `__AS_OF_DATE__` token.

    The artifact carries the token rather than a literal so it cannot silently expire;
    expansion happens here, at read time, from the one place the date lives.
    """
    raw = (path or CATALOG_PATH).read_text(encoding="utf-8")
    return json.loads(raw.replace(AS_OF_TOKEN, AS_OF_DATE.isoformat()))


def phase_labels(db_path: Path | None = None) -> dict[str, str]:
    """phase_key -> display name, read from `dim_process_phase`.

    Deliberately not `key.replace("_", " ")`. The dimension is the declared source of the
    display name, so reading it is what keeps the label from drifting from the model:
    `goods_receipt` renders as "Goods receipt to stock", which a naive replace would never
    produce. If the warehouse is absent the keys are returned unchanged -- a missing label
    should degrade the prose, never fail the answer.
    """
    path = db_path or DB_PATH
    if not Path(path).exists():
        return {}
    con = duckdb.connect(str(path), read_only=True)
    try:
        return {
            key: name
            for key, name in con.execute(
                "SELECT phase_key, phase_name FROM dim_process_phase"
            ).fetchall()
        }
    finally:
        con.close()


@dataclass
class Answer:
    """A number and its defence."""

    metric: str
    headline: str
    value: float | None
    numerator: int
    denominator: int
    grain: str
    metric_definition: str
    lineage: list[str] = field(default_factory=list)
    exclusions_applied: list[str] = field(default_factory=list)
    trust_badge: str = "TRUSTED"
    failing_rules: list[str] = field(default_factory=list)
    breakdown: list[dict[str, Any]] = field(default_factory=list)
    filters: list[str] = field(default_factory=list)
    window: str = ""
    sql: str = ""
    gate_results: dict[str, bool] = field(default_factory=dict)

    # ---- display helpers -------------------------------------------------------------

    @property
    def display_value(self) -> str:
        """One decimal, or an explicit refusal to divide.

        A zero denominator is not 0% -- it is "nothing was due yet". Rendering it as 0%
        would report the August window as catastrophic delivery performance.
        """
        if self.value is None:
            return "no eligible orders"
        return f"{self.value:.1f}%"

    def render(self, labels: dict[str, str] | None = None) -> str:
        """The printable block. Everything a reviewer needs, in one place."""
        labels = labels if labels is not None else phase_labels()
        lines = [
            f"ANSWER   {self.headline}",
            "",
            f"  metric        {self.metric} -- {self.metric_definition}",
            f"  arithmetic    {self.numerator} / {self.denominator}"
            + (f" = {self.value:.4f}%" if self.value is not None else " (no eligible rows)"),
            f"  grain         {self.grain} (one row per {self.grain})",
        ]
        if self.window:
            lines.append(f"  window        {self.window}")
        if self.filters:
            lines.append(f"  filters       {', '.join(self.filters)}")
        lines.append(
            f"  exclusions    {', '.join(self.exclusions_applied) or 'none declared'}"
        )
        lines.append(f"  lineage       {' -> '.join(self.lineage)}")

        badge = self.trust_badge
        if self.failing_rules:
            badge += f" (failing: {', '.join(self.failing_rules)})"
        lines.append(f"  trust         {badge}")

        if self.gate_results:
            passed = sum(1 for v in self.gate_results.values() if v)
            lines.append(
                f"  gates         {passed}/{len(self.gate_results)} passed: "
                + ", ".join(sorted(self.gate_results))
            )

        if self.breakdown:
            lines += ["", "  BREAKDOWN"]
            for row in self.breakdown:
                key = row.get("key")
                label = labels.get(key, key) if key else "unattributed"
                lines.append(f"    {label:<28} {row.get('late_count', 0)}")
            top = self.breakdown[0]
            top_key = top.get("key")
            if top_key:
                top_label = labels.get(top_key, top_key)
                lines += [
                    "",
                    f"  Largest contributor: {top_label} "
                    f"({top.get('late_count', 0)} of "
                    f"{sum(r.get('late_count', 0) for r in self.breakdown)} late orders).",
                ]
        return "\n".join(lines)


# --------------------------------------------------------------------------------------
# build_answer
# --------------------------------------------------------------------------------------


def _one_line(text: str) -> str:
    """Collapse a YAML folded-block description to a single line."""
    return " ".join((text or "").split())


def _describe_filter(f: Any) -> str:
    value = f.value
    if isinstance(value, list):
        rendered = ", ".join(str(v) for v in value)
        return f"{f.column} {f.operator} ({rendered})"
    return f"{f.column} {f.operator} {value}"


def build_answer(
    qi: QueryIntent,
    cq: CompiledQuery,
    rows: list[dict[str, Any]],
    model: SemanticModel,
    dq_report: DQReport | None = None,
    gate_results: dict[str, bool] | None = None,
) -> Answer:
    """Assemble a defensible answer from a compiled query and its result rows.

    A grouped result carries one row per dimension value, so the headline totals are
    summed back up here rather than re-queried. Summing the numerator and denominator and
    dividing once is not the same as averaging the per-group percentages -- the latter is
    Simpson's paradox waiting to happen, and it would disagree with the ungrouped answer
    for the same question.
    """
    metric = model.get_metric(qi.metric)
    if metric is None:  # pragma: no cover -- compile_sql refuses first
        raise ValueError(f"metric {qi.metric!r} is not in the semantic model")

    numerator = sum(int(r.get("numerator") or 0) for r in rows)
    denominator = sum(int(r.get("denominator") or 0) for r in rows)
    value = None if denominator == 0 else 100.0 * numerator / denominator

    breakdown: list[dict[str, Any]] = []
    if qi.dimensions:
        key_dim = qi.dimensions[0]
        for r in rows:
            entry = {
                "key": r.get(key_dim),
                "late_count": int(r.get("late_count") or 0),
                "numerator": int(r.get("numerator") or 0),
                "denominator": int(r.get("denominator") or 0),
                "value": r.get("value"),
            }
            # Keep the machine-readable dimension name too, so a consumer can address the
            # breakdown by the column it grouped on rather than by position.
            entry[key_dim] = r.get(key_dim)
            breakdown.append(entry)
        # Attributed phases first, largest contributor first; the unattributed bucket
        # (on-time orders) sorts last because it explains nothing.
        breakdown.sort(key=lambda e: (e["key"] is None, -e["late_count"], str(e["key"])))

    window = ""
    if qi.time_window is not None:
        window = (
            f"{qi.time_window.label} "
            f"({qi.time_window.start.isoformat()} to {qi.time_window.end.isoformat()}) "
            f"on {metric.get('time_dimension')}"
        )

    label = metric.get("label", qi.metric)
    if value is None:
        headline = (
            f"{label}: no eligible orders in {qi.time_window.label if qi.time_window else 'the window'}"
            f" -- {denominator} of the orders in range were due by {AS_OF_DATE.isoformat()}"
        )
    else:
        headline = (
            f"{label} is {value:.1f}% -- {numerator} of {denominator} eligible orders "
            f"delivered on or before the promised date"
        )

    return Answer(
        metric=qi.metric,
        headline=headline,
        value=value,
        numerator=numerator,
        denominator=denominator,
        grain=cq.grain or metric.get("grain", ""),
        metric_definition=_one_line(metric.get("description", "")),
        lineage=list(metric.get("lineage") or []),
        exclusions_applied=list(cq.applied_exclusions),
        trust_badge=dq_report.badge if dq_report else "UNKNOWN",
        failing_rules=list(dq_report.failing_rules) if dq_report else [],
        breakdown=breakdown,
        filters=[_describe_filter(f) for f in qi.filters],
        window=window,
        sql=cq.sql,
        gate_results=dict(gate_results or {}),
    )
