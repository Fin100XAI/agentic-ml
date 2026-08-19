"""Keyword fallback planner: simple question shapes without any LLM.

Deterministic pattern matching for the common shapes (top/bottom N,
count, average/total by group, threshold filters, last N periods).
Returns a plan dict or None when the question is beyond it - never a
guess dressed up as an answer.
"""
from __future__ import annotations

import re
from typing import Any

from ..librarian import _normalize

_AGG_WORDS = {
    "average": "mean", "mean": "mean", "total": "sum", "sum": "sum",
    "median": "median", "highest": "max", "largest": "max", "maximum": "max",
    "lowest": "min", "smallest": "min", "minimum": "min",
}

_THRESHOLD_WORDS = [
    (r"(?:at least|>=)", ">="), (r"(?:at most|<=)", "<="),
    (r"(?:above|over|more than|greater than|exceeding|>)", ">"),
    (r"(?:below|under|less than|fewer than|<)", "<"),
]


def _mentioned_columns(question: str, columns: list[str]) -> list[str]:
    """Columns whose normalized name appears in the normalized question,
    longest matches first so 'female participants' beats 'participants'."""
    qn = " " + re.sub(r"[^a-z0-9]+", " ", question.lower()).strip() + " "
    hits = []
    for col in columns:
        token = " " + _normalize(str(col)).replace("_", " ") + " "
        if token.strip() and token in qn:
            hits.append(str(col))
    return sorted(hits, key=lambda c: len(_normalize(c)), reverse=True)


def _time_column(columns: list[str], dtypes: dict[str, str] | None) -> str | None:
    for col in columns:
        n = _normalize(str(col))
        if any(k in n for k in ("date", "month", "week", "quarter", "year", "period", "time")):
            return str(col)
    if dtypes:
        for col, dt in dtypes.items():
            if "datetime" in str(dt):
                return str(col)
    return None


def fallback_plan(
    question: str,
    columns: list[str],
    dtypes: dict[str, str] | None = None,
    numeric_columns: list[str] | None = None,
) -> dict[str, Any] | None:
    q = question.lower()
    mentioned = _mentioned_columns(question, columns)
    numeric = set(numeric_columns or [])
    steps: list[dict[str, Any]] = []

    # last N periods
    m = re.search(r"last\s+(\d+)\s+(day|week|month|quarter|year|period)s?", q)
    if m:
        tcol = _time_column(columns, dtypes)
        if tcol:
            steps.append({"op": "time_window", "column": tcol, "last_n": int(m.group(1))})

    # threshold filter: "<col> below 40" (needs a mentioned column)
    for pattern, op in _THRESHOLD_WORDS:
        tm = re.search(pattern + r"\s+(\d+(?:\.\d+)?)\s*%?", q)
        if tm:
            target = next((c for c in mentioned if not numeric or c in numeric), None)
            if target:
                steps.append({"op": "filter", "column": target,
                              "operator": op, "value": float(tm.group(1))})
            break

    # top/bottom N ... by <metric>
    tb = re.search(r"\b(top|bottom|lowest|highest)\s+(\d+)\b", q)
    agg_m = re.search(r"\b(average|mean|total|sum|median)\b(?:\s+of)?\s+", q)
    by_m = re.search(r"\b(?:by|per|for each)\b", q)

    metric = next((c for c in mentioned if c in numeric), None) if numeric else (
        mentioned[0] if mentioned else None)
    group = next((c for c in mentioned if c != metric and (not numeric or c not in numeric)), None)

    if tb:
        n = int(tb.group(2))
        ascending = tb.group(1) in ("bottom", "lowest")
        if metric and group:
            steps += [
                {"op": "group_by", "columns": [group]},
                {"op": "aggregate", "column": metric, "fn": "sum", "alias": metric},
            ]
        if metric:
            steps.append({"op": "sort", "column": metric, "dir": "asc" if ascending else "desc"})
        steps.append({"op": "top_n", "n": n})
        return {"source": "", "steps": steps} if metric else None

    # how many / count (by group)
    if re.search(r"\bhow many\b|\bcount\b|\bnumber of\b", q):
        if group:
            steps += [
                {"op": "group_by", "columns": [group]},
                {"op": "aggregate", "column": group, "fn": "count", "alias": "count"},
                {"op": "sort", "column": "count", "dir": "desc"},
            ]
        elif columns:
            steps.append({"op": "aggregate", "column": str(columns[0]), "fn": "count", "alias": "count"})
        else:
            return None  # nothing left to count in a zero-column dataset
        return {"source": "", "steps": steps}

    # average/total of <metric> (by <group>)
    if agg_m and metric:
        fn = _AGG_WORDS[agg_m.group(1)]
        if by_m and group:
            steps += [
                {"op": "group_by", "columns": [group]},
                {"op": "aggregate", "column": metric, "fn": fn, "alias": f"{fn}_{_normalize(metric)}"},
                {"op": "sort", "column": f"{fn}_{_normalize(metric)}", "dir": "desc"},
            ]
        else:
            steps.append({"op": "aggregate", "column": metric, "fn": fn})
        return {"source": "", "steps": steps}

    # bare threshold/time filters are a valid answer (list the rows)
    if steps:
        return {"source": "", "steps": steps}
    return None
