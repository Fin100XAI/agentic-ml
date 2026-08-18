"""Deterministic QueryPlan interpreter.

Pure function: (plan, frame) -> QueryResult dict. No web imports, no
LLM, no eval - every step is a typed operation from plan.py. Row counts
are recorded after every step, null rows excluded by aggregates are
counted honestly, and hard limits fail with plain-language errors.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

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

MAX_ROWS_IN = 500_000
MAX_ROWS_OUT = 10_000


class QueryExecutionError(ValueError):
    """Plain-language execution failure the UI can show verbatim."""


def _clean(v: Any) -> Any:
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        f = float(v)
        return None if (np.isnan(f) or np.isinf(f)) else round(f, 6)
    if isinstance(v, (pd.Timestamp, datetime)):
        return str(v)[:19]
    if isinstance(v, np.bool_):
        return bool(v)
    return v


def _as_datetime(s: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(s):
        return s
    return pd.to_datetime(s.astype(str), errors="coerce", format="mixed")


def _apply_filter(frame: pd.DataFrame, s: FilterStep) -> pd.DataFrame:
    col = frame[s.column]
    op = s.operator
    if op == "is_null":
        return frame[col.isna()]
    if op == "not_null":
        return frame[col.notna()]
    if op == "contains":
        return frame[col.astype(str).str.contains(str(s.value), case=False, na=False)]
    if op in ("in", "not_in"):
        values = s.value if isinstance(s.value, (list, tuple)) else [s.value]
        # Compare case-insensitively on strings so 'pune' matches 'Pune'.
        if col.dtype == object:
            lowered = col.astype(str).str.strip().str.lower()
            targets = {str(v).strip().lower() for v in values}
            mask = lowered.isin(targets)
        else:
            mask = col.isin(list(values))
        return frame[mask if op == "in" else ~mask]
    # Comparison operators: numeric coercion on the column side.
    value = s.value
    if op in (">", ">=", "<", "<="):
        num = pd.to_numeric(col, errors="coerce")
        try:
            v = float(value)
        except (TypeError, ValueError) as exc:
            raise QueryExecutionError(
                f"'{s.column}' comparison needs a number, got '{value}'."
            ) from exc
        if op == ">":
            mask = num > v
        elif op == ">=":
            mask = num >= v
        elif op == "<":
            mask = num < v
        else:
            mask = num <= v
        return frame[mask.fillna(False)]
    # == / != (case-insensitive on text)
    if col.dtype == object:
        mask = col.astype(str).str.strip().str.lower() == str(value).strip().lower()
    else:
        mask = (col == value).fillna(False)
    return frame[mask] if op == "==" else frame[~mask]


def _apply_time_window(frame: pd.DataFrame, s: TimeWindowStep, notes: list[str]) -> pd.DataFrame:
    if s.last_n is not None:
        # Last N DISTINCT period values (works for dates and period strings).
        ts = _as_datetime(frame[s.column])
        order_key = ts if ts.notna().mean() > 0.8 else frame[s.column]
        periods = pd.Series(order_key.values).dropna().drop_duplicates().sort_values()
        keep = set(periods.tail(s.last_n))
        notes.append(
            f"Time window: last {s.last_n} of {len(periods)} periods in '{s.column}'."
        )
        key = ts if ts.notna().mean() > 0.8 else frame[s.column]
        return frame[pd.Series(key.values, index=frame.index).isin(keep)]
    ts = _as_datetime(frame[s.column])
    mask = pd.Series(True, index=frame.index)
    if s.start:
        mask &= ts >= pd.to_datetime(s.start)
    if s.end:
        mask &= ts <= pd.to_datetime(s.end)
    return frame[mask.fillna(False)]


def _apply_derive(frame: pd.DataFrame, s: DeriveStep) -> pd.DataFrame:
    left = pd.to_numeric(frame[s.left], errors="coerce")
    right = pd.to_numeric(frame[s.right], errors="coerce")
    out = frame.copy()
    if s.kind == "difference":
        out[s.name] = left - right
    else:
        denom = right.replace(0, np.nan)
        out[s.name] = (left / denom) * (100.0 if s.kind == "percent_of" else 1.0)
    return out


def _apply_delta(frame: pd.DataFrame, s: DeltaVsPeriodStep, notes: list[str]) -> pd.DataFrame:
    key_cols = [c for c in frame.columns
                if c not in (s.column, s.period_column)
                and not pd.api.types.is_numeric_dtype(frame[c])]
    ts = _as_datetime(frame[s.period_column])
    work = frame.assign(__order=ts if ts.notna().mean() > 0.8 else frame[s.period_column])
    work = work.sort_values("__order")
    delta_name = f"{s.column}__delta"
    if key_cols:
        work[delta_name] = work.groupby(key_cols, dropna=False)[s.column].diff(s.lag)
        missing = int(work.groupby(key_cols, dropna=False)[delta_name].apply(lambda g: g.isna().all()).sum())
        if missing:
            notes.append(f"{missing} group(s) had no prior period to compare against.")
    else:
        work[delta_name] = pd.to_numeric(work[s.column], errors="coerce").diff(s.lag)
    return work.drop(columns=["__order"])


def execute_plan(plan: QueryPlan, frame: pd.DataFrame) -> dict[str, Any]:
    """Execute a RESOLVED plan. Returns the JSON-safe QueryResult."""
    if len(frame) > MAX_ROWS_IN:
        raise QueryExecutionError(
            f"This dataset has {len(frame):,} rows - above the {MAX_ROWS_IN:,} "
            "row limit for direct questions. Filter it down first."
        )
    work = frame.copy()
    row_counts: list[dict[str, Any]] = [{"step": "input", "rows": int(len(work))}]
    excluded_null_rows: dict[str, int] = {}
    coverage_notes: list[str] = []
    group_cols: list[str] = []
    pending_aggs: list[AggregateStep] = []

    def flush_aggregates() -> None:
        nonlocal work, group_cols, pending_aggs
        if not pending_aggs:
            return
        spec: dict[str, tuple[str, str]] = {}
        for a in pending_aggs:
            alias = a.alias or (f"{a.fn}_{a.column}" if a.fn != "count" else "count")
            nulls = int(work[a.column].isna().sum()) if a.column in work.columns else 0
            if a.fn not in ("count",) and nulls:
                excluded_null_rows[alias] = nulls
            spec[alias] = (a.column, a.fn)
        if group_cols:
            gb = work.groupby(group_cols, dropna=False)
            pieces = {}
            for alias, (col, fn) in spec.items():
                if fn == "count":
                    pieces[alias] = gb[col].size() if col not in work.columns else gb[col].count()
                else:
                    pieces[alias] = getattr(gb[col], fn)()
            work = pd.DataFrame(pieces).reset_index()
        else:
            row = {}
            for alias, (col, fn) in spec.items():
                series = work[col]
                row[alias] = int(series.count()) if fn == "count" else getattr(
                    pd.to_numeric(series, errors="coerce") if fn != "nunique" else series, fn)()
            work = pd.DataFrame([row])
        group_cols = []
        pending_aggs = []

    for i, step in enumerate(plan.steps):
        label = f"{i + 1}. {step.op}"
        if isinstance(step, AggregateStep):
            pending_aggs.append(step)
            # aggregation applies when the next step is not another aggregate
            nxt = plan.steps[i + 1] if i + 1 < len(plan.steps) else None
            if not isinstance(nxt, AggregateStep):
                flush_aggregates()
                row_counts.append({"step": label, "rows": int(len(work))})
            continue
        if isinstance(step, GroupByStep):
            missing = [c for c in step.columns if c not in work.columns]
            if missing:
                raise QueryExecutionError(f"Column '{missing[0]}' is not available at this step.")
            group_cols = list(step.columns)
            row_counts.append({"step": label, "rows": int(len(work))})
            continue
        flush_aggregates()
        if isinstance(step, FilterStep):
            if step.column not in work.columns:
                raise QueryExecutionError(f"Column '{step.column}' is not available at this step.")
            work = _apply_filter(work, step)
        elif isinstance(step, TimeWindowStep):
            work = _apply_time_window(work, step, coverage_notes)
        elif isinstance(step, DeriveStep):
            work = _apply_derive(work, step)
        elif isinstance(step, SortStep):
            if step.column not in work.columns:
                raise QueryExecutionError(f"Cannot sort by '{step.column}' - not in the result.")
            work = work.sort_values(step.column, ascending=step.dir == "asc", na_position="last")
        elif isinstance(step, TopNStep):
            work = work.head(step.n)
        elif isinstance(step, PivotStep):
            work = pd.pivot_table(
                work, index=step.index, columns=step.columns, values=step.values,
                aggfunc="mean",
            ).reset_index()
            work.columns = [str(c) for c in work.columns]
        elif isinstance(step, DeltaVsPeriodStep):
            work = _apply_delta(work, step, coverage_notes)
        row_counts.append({"step": label, "rows": int(len(work))})

    flush_aggregates()
    if row_counts[-1]["step"] == "input" or row_counts[-1]["rows"] != len(work):
        row_counts.append({"step": "output", "rows": int(len(work))})

    if len(work) > MAX_ROWS_OUT:
        raise QueryExecutionError(
            f"This answer would have {len(work):,} rows - above the {MAX_ROWS_OUT:,} "
            "row limit. Add a filter, grouping or top-N to narrow it."
        )

    table = [
        {str(k): _clean(v) for k, v in rec.items()}
        for rec in work.to_dict("records")
    ]
    return {
        "table": table,
        "columns": [str(c) for c in work.columns],
        "dtypes": {str(c): str(work[c].dtype) for c in work.columns},
        "row_counts": row_counts,
        "excluded_null_rows": excluded_null_rows,
        "coverage_notes": coverage_notes,
        "plan_echo": plan.model_dump(),
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }
