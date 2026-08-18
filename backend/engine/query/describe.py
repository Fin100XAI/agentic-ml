"""Plain-language rendering of a QueryPlan - the user's contract.

Deterministic templates, NO LLM: the sentences are exactly what the
executor will do, not a paraphrase (CLAUDE.md rule 12). Every op type
must have a template; the completeness test enforces it.
"""
from __future__ import annotations

from typing import Any, Callable

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
    TopNStep,
)

_OP_PHRASE = {
    "==": "is", "!=": "is not", ">": "is above", ">=": "is at least",
    "<": "is below", "<=": "is at most", "in": "is one of", "not_in": "is not one of",
    "contains": "contains", "is_null": "is empty", "not_null": "is filled in",
}

_FN_PHRASE = {
    "sum": "total", "mean": "average", "median": "median (middle value)",
    "min": "smallest", "max": "largest", "count": "number of filled-in rows",
    "nunique": "number of distinct values",
}

GLOSSARY = {
    "median": "The middle value: half the rows are above it, half below. Not pulled around by extremes.",
    "average": "The sum divided by the number of rows. A few extreme values can pull it.",
    "distinct": "Counted once no matter how many times it repeats.",
    "percent of": "The first value divided by the second, times 100.",
}


def _fmt_value(v: Any) -> str:
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v)
    return str(v)


def _label(col: str, labels: dict[str, str]) -> str:
    return labels.get(col, col)


def _t_filter(s: FilterStep, labels: dict[str, str]) -> str:
    phrase = _OP_PHRASE[s.operator]
    if s.operator in ("is_null", "not_null"):
        return f"Keep rows where {_label(s.column, labels)} {phrase}."
    return f"Keep rows where {_label(s.column, labels)} {phrase} {_fmt_value(s.value)}."


def _t_time_window(s: TimeWindowStep, labels: dict[str, str]) -> str:
    col = _label(s.column, labels)
    if s.last_n is not None:
        unit = "period" if s.last_n == 1 else "periods"
        return f"Keep only the last {s.last_n} {unit} of {col}."
    if s.start and s.end:
        return f"Keep rows where {col} is between {s.start} and {s.end}."
    if s.start:
        return f"Keep rows where {col} is on or after {s.start}."
    return f"Keep rows where {col} is on or before {s.end}."


def _t_derive(s: DeriveStep, labels: dict[str, str]) -> str:
    name = _label(s.name, labels)
    left, right = _label(s.left, labels), _label(s.right, labels)
    if s.kind == "ratio":
        return f"For each row, compute {name} = {left} ÷ {right}."
    if s.kind == "percent_of":
        return f"For each row, compute {name} = {left} as a percent of {right}."
    return f"For each row, compute {name} = {left} minus {right}."


def _t_group_by(s: GroupByStep, labels: dict[str, str]) -> str:
    cols = " and ".join(_label(c, labels) for c in s.columns)
    return f"For each {cols}:"


def _t_aggregate(s: AggregateStep, labels: dict[str, str]) -> str:
    fn = _FN_PHRASE[s.fn]
    col = _label(s.column, labels)
    alias = f" (called {_label(s.alias, labels)})" if s.alias else ""
    if s.fn == "count":
        return f"Compute the {fn} in {col}{alias}."
    return f"Compute the {fn} of {col}{alias}."


def _t_sort(s: SortStep, labels: dict[str, str]) -> str:
    order = "lowest first" if s.dir == "asc" else "highest first"
    return f"Sort by {_label(s.column, labels)}, {order}."


def _t_top_n(s: TopNStep, labels: dict[str, str]) -> str:
    return f"Keep the first {s.n} rows."


def _t_pivot(s: PivotStep, labels: dict[str, str]) -> str:
    return (f"Arrange as a table: one row per {_label(s.index, labels)}, one column per "
            f"{_label(s.columns, labels)}, showing {_label(s.values, labels)}.")


def _t_delta(s: DeltaVsPeriodStep, labels: dict[str, str]) -> str:
    lag = "previous period" if s.lag == 1 else f"{s.lag} periods earlier"
    return (f"Compute the change in {_label(s.column, labels)} versus the {lag} "
            f"of {_label(s.period_column, labels)}.")


# op literal -> template. The completeness test asserts this covers every
# step type in plan.ALL_STEP_TYPES.
OP_TEMPLATES: dict[str, Callable[..., str]] = {
    "filter": _t_filter,
    "time_window": _t_time_window,
    "derive": _t_derive,
    "group_by": _t_group_by,
    "aggregate": _t_aggregate,
    "sort": _t_sort,
    "top_n": _t_top_n,
    "pivot": _t_pivot,
    "delta_vs_period": _t_delta,
}


def describe_plan(
    plan: QueryPlan,
    dataset_name: str = "your data",
    labels: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Ordered sentences + a glossary map for tooltip rendering."""
    labels = {**(labels or {}), **plan.output_hints.labels}
    sentences = [f"Take {dataset_name}."]
    used_terms: dict[str, str] = {}
    for step in plan.steps:
        template = OP_TEMPLATES[step.op]
        sentences.append(template(step, labels))
        if isinstance(step, AggregateStep):
            if step.fn == "median":
                used_terms["median"] = GLOSSARY["median"]
            elif step.fn == "mean":
                used_terms["average"] = GLOSSARY["average"]
            elif step.fn == "nunique":
                used_terms["distinct"] = GLOSSARY["distinct"]
        if isinstance(step, DeriveStep) and step.kind == "percent_of":
            used_terms["percent of"] = GLOSSARY["percent of"]
    return {"sentences": sentences, "glossary": used_terms}
