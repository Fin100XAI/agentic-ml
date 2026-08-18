"""Deterministic result-shape -> chart mapping (rule 14).

The LLM never chooses a chart. This module inspects the executed result
and the plan and emits a ChartSpec the shared frontend chart component
renders under the binding grammar (zero-based bars, no dual axes,
colorblind-safe palette, red/amber reserved for judgment states).

This is the working subset that answers need today (kpi, bar, ordered
horizontal bar, line, table fallback + threshold reference lines); the
full grammar - stacked bars, scatter, diverging deltas, small multiples
- lands with the dedicated visualization task.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from .plan import DeltaVsPeriodStep, FilterStep, PivotStep, QueryPlan, SortStep, TopNStep

MAX_BAR_CATEGORIES = 30
# Thin diverging bars stay readable much further than labeled category bars.
MAX_DELTA_BARS = 120


def _is_timeish(values: list[Any]) -> bool:
    s = pd.Series([v for v in values if v is not None]).astype(str)
    if len(s) < 3:
        return False
    return pd.to_datetime(s, errors="coerce", format="mixed").notna().mean() > 0.8


def choose_chart(result: dict[str, Any], plan: QueryPlan) -> dict[str, Any]:
    """-> ChartSpec {kind, x, y, threshold, note}. kind=table means no chart."""
    table = result.get("table") or []
    columns: list[str] = result.get("columns") or []
    dtypes: dict[str, str] = result.get("dtypes") or {}
    numeric_cols = [c for c in columns
                    if any(t in str(dtypes.get(c, "")) for t in ("int", "float"))]
    non_numeric = [c for c in columns if c not in numeric_cols]

    # Threshold reference line: a filter in the plan on a column that ends up
    # as the metric encoding.
    threshold = None
    for s in plan.steps:
        if isinstance(s, FilterStep) and s.operator in (">", ">=", "<", "<="):
            try:
                threshold = {"column": s.column, "value": float(s.value)}
            except (TypeError, ValueError):
                pass

    # Single row of aggregates -> KPI card(s).
    if len(table) == 1 and numeric_cols and len(non_numeric) == 0:
        return {"kind": "kpi", "x": None, "y": numeric_cols,
                "threshold": None, "note": None}

    if not table or not numeric_cols or not non_numeric:
        return {"kind": "table", "x": None, "y": [], "threshold": None, "note": None}

    x = non_numeric[0]
    y = numeric_cols[0]

    # delta_vs_period -> diverging bars around zero on the change column.
    if any(isinstance(s, DeltaVsPeriodStep) for s in plan.steps):
        delta_cols = [c for c in numeric_cols if c.endswith("__delta")]
        if delta_cols and len(table) <= MAX_DELTA_BARS:
            return {"kind": "dbar", "x": x, "y": [delta_cols[0]],
                    "threshold": None, "note": None}
        if delta_cols:
            return {"kind": "table", "x": None, "y": [], "threshold": None,
                    "note": f"{len(table)} periods - too many to chart the changes honestly."}
    thr = threshold["value"] if threshold and threshold["column"] in (y, x) else None

    timeish = _is_timeish([r.get(x) for r in table[:50]])

    # Grouped time series -> small multiples, never spaghetti lines.
    if timeish and len(non_numeric) >= 2:
        groups = {r.get(non_numeric[1]) for r in table}
        if 2 <= len(groups) <= 9:
            return {"kind": "multiples", "x": x, "y": [y],
                    "facet": non_numeric[1], "threshold": thr, "note": None}
        return {"kind": "table", "x": None, "y": [], "threshold": None,
                "note": f"{len(groups)} series - too many to chart honestly."}

    # Pivot output with a few metric columns -> stacked bar (<= 6 slices,
    # NEVER pie); more slices fall through to the table.
    if any(isinstance(s, PivotStep) for s in plan.steps) and not timeish:
        if 2 <= len(numeric_cols) <= 6 and len(table) <= MAX_BAR_CATEGORIES:
            return {"kind": "sbar", "x": x, "y": numeric_cols,
                    "threshold": None, "note": None}

    # Two metrics per key -> scatter (each point one key).
    if (len(numeric_cols) >= 2 and not timeish and len(table) >= 5
            and not any(isinstance(s, PivotStep) for s in plan.steps)):
        return {"kind": "scatter", "x": None, "y": numeric_cols[:2],
                "label": x, "threshold": None, "note": None}

    # Time on the key axis -> line.
    if timeish:
        return {"kind": "line", "x": x, "y": [y], "threshold": thr, "note": None}

    if len(table) > MAX_BAR_CATEGORIES:
        return {"kind": "table", "x": None, "y": [], "threshold": None,
                "note": f"{len(table)} rows - too many categories to chart honestly."}

    # top_n / explicit ranking -> ordered horizontal bars.
    has_topn = any(isinstance(s, TopNStep) for s in plan.steps)
    has_sort = any(isinstance(s, SortStep) for s in plan.steps)
    if has_topn or (has_sort and len(table) <= 15):
        return {"kind": "hbar", "x": x, "y": [y], "threshold": thr, "note": None}

    return {"kind": "bar", "x": x, "y": [y], "threshold": thr, "note": None}
