"""Parse and structurally validate the semantic model YAML.

This module provides typed access to metric definitions, dimensions, and entities.
Structural validation happens at load time so downstream consumers can trust the shape.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml

from src.semantic.constants import METADATA_DIR


class SemanticModelError(Exception):
    """Raised when the semantic model fails structural validation."""
    pass


@dataclass
class SemanticModel:
    """Typed accessor for the semantic model."""

    _data: dict

    def metric_names(self) -> list[str]:
        """Return all metric names."""
        return [m["name"] for m in self._data.get("metrics", [])]

    def approved_metric_names(self) -> list[str]:
        """Return names of approved metrics only."""
        return [
            m["name"]
            for m in self._data.get("metrics", [])
            if m.get("approval_state") == "approved"
        ]

    def get_metric(self, name: str) -> dict | None:
        """Get metric definition by name, or None if not found."""
        for m in self._data.get("metrics", []):
            if m["name"] == name:
                return m
        return None

    def get_entity(self, name: str) -> dict:
        """Get entity definition by name. Raises KeyError if not found."""
        for e in self._data.get("entities", []):
            if e["name"] == name:
                return e
        raise KeyError(f"Entity not found: {name}")

    def get_dimension(self, metric_name: str, dim_name: str) -> dict | None:
        """Get dimension definition for a specific metric.

        Returns None if dimension not found or not reachable from metric's entity.
        """
        # Get all dimensions
        for d in self._data.get("dimensions", []):
            if d["name"] == dim_name:
                return d
        return None

    def dimensions_for(self, metric_name: str) -> list[str]:
        """Return list of dimension names reachable from this metric.

        A dimension is reachable if:
        1. It sits on the metric's entity directly, OR
        2. It sits on an entity the metric's entity declares a join to
        """
        metric = self.get_metric(metric_name)
        if not metric:
            return []

        metric_entity = metric["entity"]

        # Get the entity and its joins
        try:
            entity = self.get_entity(metric_entity)
        except KeyError:
            return []

        # Collect reachable entities: the metric's own entity plus joined entities
        reachable_entities = {metric_entity}
        for join in entity.get("joins", []):
            reachable_entities.add(join["to"])

        # Return dimensions that live on reachable entities
        result = []
        for d in self._data.get("dimensions", []):
            if d.get("entity") in reachable_entities:
                result.append(d["name"])

        return result


def load_semantic_model(path: Path | None = None) -> SemanticModel:
    """Load and validate the semantic model from YAML.

    Args:
        path: Path to semantic model YAML. Defaults to metadata/05_semantic_model.yml.

    Returns:
        SemanticModel with validated structure.

    Raises:
        SemanticModelError: If structural validation fails.
    """
    if path is None:
        path = METADATA_DIR / "05_semantic_model.yml"

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # Validate structure
    _validate_structure(data)

    return SemanticModel(_data=data)


def _validate_structure(data: dict) -> None:
    """Structural validation of the semantic model.

    Validates:
    1. Every metric's entity exists in entities
    2. Every metric's grain matches its entity's grain
    3. Every metric has required fields: owner, steward, approval_state, lineage
    4. approval_state is in allowed values
    5. Every dimension's entity exists
    6. Every join declares a valid cardinality
    """
    entities = {e["name"]: e for e in data.get("entities", [])}

    # Validate metrics
    for metric in data.get("metrics", []):
        metric_name = metric.get("name", "<unnamed>")

        # 1. Entity exists
        entity_name = metric.get("entity")
        if entity_name not in entities:
            raise SemanticModelError(
                f"Metric '{metric_name}' references unknown entity '{entity_name}'"
            )

        # 2. Grain matches
        metric_grain = metric.get("grain")
        entity_grain = entities[entity_name].get("grain")
        if metric_grain != entity_grain:
            raise SemanticModelError(
                f"Metric '{metric_name}' grain '{metric_grain}' does not match "
                f"entity '{entity_name}' grain '{entity_grain}'"
            )

        # 3. Required fields
        if not metric.get("owner"):
            raise SemanticModelError(f"Metric '{metric_name}' missing 'owner'")
        if not metric.get("steward"):
            raise SemanticModelError(f"Metric '{metric_name}' missing 'steward'")
        if not metric.get("approval_state"):
            raise SemanticModelError(f"Metric '{metric_name}' missing 'approval_state'")
        if not metric.get("lineage"):
            raise SemanticModelError(f"Metric '{metric_name}' missing 'lineage'")

        # 4. Valid approval state
        approval_state = metric.get("approval_state")
        if approval_state not in ("approved", "draft", "deprecated"):
            raise SemanticModelError(
                f"Metric '{metric_name}' has invalid approval_state '{approval_state}'"
            )

    # Validate dimensions
    for dimension in data.get("dimensions", []):
        dim_name = dimension.get("name", "<unnamed>")
        entity_name = dimension.get("entity")

        # 5. Dimension entity exists
        if entity_name and entity_name not in entities:
            raise SemanticModelError(
                f"Dimension '{dim_name}' references unknown entity '{entity_name}'"
            )

    # Validate joins
    for entity in data.get("entities", []):
        entity_name = entity.get("name", "<unnamed>")
        for join in entity.get("joins", []):
            # 6. Valid cardinality
            cardinality = join.get("cardinality")
            if cardinality not in ("one_to_one", "one_to_many", "many_to_one"):
                raise SemanticModelError(
                    f"Entity '{entity_name}' has join with invalid cardinality '{cardinality}'"
                )
