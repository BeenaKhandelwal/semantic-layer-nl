"""Data quality rule execution and trust badge generation.

Each rule measures one DQ dimension against a threshold. Rules are bound to specific
metric inputs, so a failing rule degrades a specific answer rather than producing a
dashboard-wide red light.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import yaml

from src.semantic.constants import AS_OF_DATE, DB_PATH, METADATA_DIR


@dataclass
class DQResult:
    """Result of running one DQ rule."""
    rule_id: str
    dimension: str
    passed: bool
    observed: float
    threshold: float
    severity: str
    bound_to: list[str]


@dataclass
class DQReport:
    """Aggregated DQ report with trust badge."""
    results: list[DQResult]
    badge: str  # TRUSTED | DEGRADED | BLOCKED
    failing_rules: list[str]


def load_rules(path: Path | None = None) -> list[dict[str, Any]]:
    """Load DQ rules from YAML.

    Args:
        path: Path to rules file, defaults to METADATA_DIR / "06_dq_rules.yml"

    Returns:
        List of rule dictionaries
    """
    path = path or (METADATA_DIR / "06_dq_rules.yml")
    with open(path, encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    return doc["rules"]


def run_rules(
    metric_name: str | None = None,
    db_path: Path | None = None,
    rules_path: Path | None = None,
) -> DQReport:
    """Execute all DQ rules and generate trust badge.

    Args:
        metric_name: If provided, only run rules bound to this metric
        db_path: Path to DuckDB warehouse, defaults to DB_PATH
        rules_path: Path to rules YAML, defaults to METADATA_DIR / "06_dq_rules.yml"

    Returns:
        DQReport with results and badge
    """
    rules = load_rules(rules_path)
    db_path = Path(db_path) if db_path else DB_PATH

    # Filter rules by metric if specified
    if metric_name:
        rules = [r for r in rules if metric_name in r["bound_to"]]

    con = duckdb.connect(str(db_path), read_only=True)
    results = []

    try:
        for rule in rules:
            # Substitute AS_OF_DATE token
            sql = rule["sql"].replace("__AS_OF_DATE__", AS_OF_DATE.isoformat())

            # Execute rule SQL
            row = con.execute(sql).fetchone()
            observed = float(row[0]) if row and row[0] is not None else 0.0
            threshold = float(rule["threshold"])
            comparison = rule["comparison"]

            # Evaluate pass/fail
            if comparison == "lte":
                passed = observed <= threshold
            elif comparison == "gte":
                passed = observed >= threshold
            else:
                raise ValueError(f"Unknown comparison: {comparison}")

            results.append(DQResult(
                rule_id=rule["rule_id"],
                dimension=rule["dimension"],
                passed=passed,
                observed=observed,
                threshold=threshold,
                severity=rule["severity"],
                bound_to=rule["bound_to"],
            ))
    finally:
        con.close()

    # Generate badge
    failing_blocking = [r.rule_id for r in results
                        if not r.passed and r.severity == "blocking"]
    failing_degrading = [r.rule_id for r in results
                         if not r.passed and r.severity == "degrading"]

    if failing_blocking:
        badge = "BLOCKED"
        failing_rules = failing_blocking
    elif failing_degrading:
        badge = "DEGRADED"
        failing_rules = failing_degrading
    else:
        badge = "TRUSTED"
        failing_rules = []

    return DQReport(
        results=results,
        badge=badge,
        failing_rules=failing_rules,
    )
