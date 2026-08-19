"""Column resolution: plan names -> the artifact's actual schema.

Uses the same keyword normalization as the librarian and glossary, so
"Monthly Charge", "monthly_charge" and "MONTHLY-CHARGE" all resolve.
Unknown columns fail BEFORE execution with did-you-mean suggestions -
a plan that cannot be fully resolved never runs.
"""
from __future__ import annotations

import difflib

from ..librarian import _normalize
from .plan import (
    AggregateStep,
    DeltaVsPeriodStep,
    DeriveStep,
    FilterStep,
    GroupByStep,
    PivotStep,
    QueryPlan,
    SortStep,
    TimeWindowStep,
)


class ColumnResolutionError(ValueError):
    def __init__(self, column: str, suggestions: list[str]) -> None:
        hint = (" Did you mean " + " or ".join(f"'{s}'" for s in suggestions) + "?"
                if suggestions else "")
        super().__init__(f"No column called '{column}' in this dataset.{hint}")
        self.column = column
        self.suggestions = suggestions


def _build_index(actual_columns: list[str]) -> dict[str, str]:
    # First occurrence wins on a normalization collision ("Total Amount" vs
    # "total_amount") so resolution is stable, not last-write-wins.
    index: dict[str, str] = {}
    for c in actual_columns:
        index.setdefault(_normalize(str(c)), str(c))
    return index


def _resolve_one(name: str, index: dict[str, str], derived: dict[str, str]) -> str:
    norm = _normalize(name)
    if name in derived.values() or norm in derived:
        # A column this plan derives earlier - matched by normalization too,
        # so 'participation rate' finds a derived 'participation_rate'.
        return derived.get(norm, name)
    if norm in index:
        return index[norm]
    close = difflib.get_close_matches(norm, list(index) + list(derived), n=2, cutoff=0.6)
    resolved_close = [index.get(c) or derived.get(c) for c in close]
    raise ColumnResolutionError(name, [c for c in resolved_close if c])


def resolve_plan(plan: QueryPlan, actual_columns: list[str]) -> QueryPlan:
    """Return a copy of the plan with every column rewritten to the actual
    schema name. Raises ColumnResolutionError on the first unknown column."""
    index = _build_index(actual_columns)
    derived: dict[str, str] = {}  # normalized -> as-derived name
    resolved = plan.model_copy(deep=True)
    for s in resolved.steps:
        if isinstance(s, (FilterStep, TimeWindowStep, SortStep)):
            s.column = _resolve_one(s.column, index, derived)
        elif isinstance(s, AggregateStep):
            s.column = _resolve_one(s.column, index, derived)
            if s.alias:
                derived[_normalize(s.alias)] = s.alias
        elif isinstance(s, DeriveStep):
            s.left = _resolve_one(s.left, index, derived)
            s.right = _resolve_one(s.right, index, derived)
            derived[_normalize(s.name)] = s.name
        elif isinstance(s, GroupByStep):
            s.columns = [_resolve_one(c, index, derived) for c in s.columns]
        elif isinstance(s, PivotStep):
            s.index = _resolve_one(s.index, index, derived)
            s.columns = _resolve_one(s.columns, index, derived)
            s.values = _resolve_one(s.values, index, derived)
        elif isinstance(s, DeltaVsPeriodStep):
            s.column = _resolve_one(s.column, index, derived)
            s.period_column = _resolve_one(s.period_column, index, derived)
            derived[_normalize(f"{s.column}__delta")] = f"{s.column}__delta"
    return resolved
