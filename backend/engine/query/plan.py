"""QueryPlan: the typed contract between the planner and the executor.

Every operation the query path can perform is a Pydantic model here.
There are NO free-form expressions - derive supports exactly ratio,
difference and percent-of between two columns. If an operation is not
in this schema, the platform cannot do it, by design (CLAUDE.md rule 11).
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field

FilterOperator = Literal[
    "==", "!=", ">", ">=", "<", "<=", "in", "not_in", "contains", "is_null", "not_null"
]

AggFn = Literal["sum", "mean", "median", "min", "max", "count", "nunique"]


class FilterStep(BaseModel):
    op: Literal["filter"] = "filter"
    column: str
    operator: FilterOperator
    value: Any = None  # unused for is_null / not_null


class TimeWindowStep(BaseModel):
    op: Literal["time_window"] = "time_window"
    column: str
    # Either a rolling window of the last N distinct periods...
    last_n: int | None = Field(None, ge=1)
    # ...or an absolute range (ISO dates or period strings, inclusive).
    start: str | None = None
    end: str | None = None


class DeriveStep(BaseModel):
    """Typed formulas only: ratio = left/right, difference = left-right,
    percent_of = 100*left/right. Never free-form expressions."""
    op: Literal["derive"] = "derive"
    name: str
    kind: Literal["ratio", "difference", "percent_of"]
    left: str
    right: str


class GroupByStep(BaseModel):
    op: Literal["group_by"] = "group_by"
    columns: list[str] = Field(min_length=1)


class AggregateStep(BaseModel):
    op: Literal["aggregate"] = "aggregate"
    column: str
    fn: AggFn
    alias: str | None = None


class SortStep(BaseModel):
    op: Literal["sort"] = "sort"
    column: str
    dir: Literal["asc", "desc"] = "desc"


class TopNStep(BaseModel):
    op: Literal["top_n"] = "top_n"
    n: int = Field(ge=1, le=1000)


class PivotStep(BaseModel):
    op: Literal["pivot"] = "pivot"
    index: str
    columns: str
    values: str


class DeltaVsPeriodStep(BaseModel):
    """Change of `column` vs `lag` periods earlier, per remaining key columns."""
    op: Literal["delta_vs_period"] = "delta_vs_period"
    column: str
    period_column: str
    lag: int = Field(1, ge=1)


QueryStep = Annotated[
    Union[
        FilterStep, TimeWindowStep, DeriveStep, GroupByStep, AggregateStep,
        SortStep, TopNStep, PivotStep, DeltaVsPeriodStep,
    ],
    Field(discriminator="op"),
]

# Introspection list used by the describe/vizmap completeness tests.
ALL_STEP_TYPES = [
    FilterStep, TimeWindowStep, DeriveStep, GroupByStep, AggregateStep,
    SortStep, TopNStep, PivotStep, DeltaVsPeriodStep,
]


class OutputHints(BaseModel):
    chart: str | None = None  # preference only; vizmap decides deterministically
    labels: dict[str, str] = Field(default_factory=dict)  # derived column -> friendly label


class QueryPlan(BaseModel):
    source: str  # artifact_id
    steps: list[QueryStep] = Field(default_factory=list)
    output_hints: OutputHints = Field(default_factory=OutputHints)


def plan_columns(plan: QueryPlan) -> list[str]:
    """Every column name a plan references (before resolution), in order."""
    cols: list[str] = []
    for s in plan.steps:
        if isinstance(s, (FilterStep, TimeWindowStep, AggregateStep, SortStep)):
            cols.append(s.column)
        elif isinstance(s, DeriveStep):
            cols.extend([s.left, s.right])
        elif isinstance(s, GroupByStep):
            cols.extend(s.columns)
        elif isinstance(s, PivotStep):
            cols.extend([s.index, s.columns, s.values])
        elif isinstance(s, DeltaVsPeriodStep):
            cols.extend([s.column, s.period_column])
    return cols
