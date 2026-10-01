"""The `QueryIntent` schema: the only thing a language model is allowed to produce.

The resolver emits one of these, the validator gates it, the compiler turns it into
SQL. Note what is *not* here: no SQL, no arithmetic, no column expressions. The model
chooses *which* governed metric, dimensions, filters and window apply; every number
is computed downstream from the certified metric definition.

`extra="forbid"` is load-bearing. A resolver that hallucinates a field -- say
`aggregation: "avg"` -- must fail to parse rather than have the key silently dropped,
because a silently dropped key looks exactly like a correct answer.
"""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TimeWindow(BaseModel):
    """A closed, concrete reporting window. Both bounds inclusive.

    `label` is the human phrase the window came from ("July 2026"), carried through
    to the answer so the reader can check that "last month" was resolved as intended.
    """

    model_config = ConfigDict(extra="forbid")

    start: date
    end: date
    label: str


class Filter(BaseModel):
    """A predicate on one declared dimension.

    `column` names a dimension in the semantic model, not a physical column chosen by
    the model. The validator's `filters_bound` gate resolves it and checks the value
    against the dimension's `allowed_values`.
    """

    model_config = ConfigDict(extra="forbid")

    column: str
    operator: Literal["=", "in", "between", ">=", "<="]
    value: str | list[str]


class QueryIntent(BaseModel):
    """A resolved natural-language question, structured and checkable.

    `grain` is stated explicitly rather than inferred so that the `grain_matches` gate
    has something to reject: it is the field that catches "on-time delivery at delivery
    grain", the plausible-looking 88.52% instead of the certified 87.27%.
    """

    model_config = ConfigDict(extra="forbid")

    metric: str
    dimensions: list[str] = Field(default_factory=list)
    filters: list[Filter] = Field(default_factory=list)
    grain: str
    time_window: TimeWindow | None = None
    intent_type: Literal["descriptive", "diagnostic"]
    comparison: TimeWindow | None = None
