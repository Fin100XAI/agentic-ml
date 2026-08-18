"""Starter questions: what the exploring agents ask on the user's behalf.

Deterministic generation from the schema - each candidate is a natural
question WITH its ready-made QueryPlan, so execution never depends on an
LLM. The LLM's only later role is choosing which findings are worth
leading with and phrasing them (judge and phrase, rule 11).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from .readiness import _find_entity_key, _find_period_column

MAX_STARTERS = 9
# Grouping columns may have up to 60 levels (India has 35+ states; charts
# guard their own category caps and top-N keeps rankings honest).
MAX_CAT_LEVELS = 60


def _is_numberish_text(s: pd.Series) -> bool:
    """Numbers stored as text ('4,076', '-', '959') must not be treated as
    categories - grouping by them is meaningless. The health screen already
    proposes fixing such columns properly."""
    non_null = s.dropna().astype(str).str.strip()
    non_null = non_null[~non_null.isin(["", "-", "NA", "N/A", "nan"])]
    if len(non_null) < 5:
        return False
    coerced = pd.to_numeric(non_null.str.replace(",", "", regex=False),
                            errors="coerce")
    return bool(coerced.notna().mean() > 0.6)


def _plausible_period(s: pd.Series) -> bool:
    """A time column must parse as PLAUSIBLE dates - '959' technically
    parses as the year 959 AD, which is how a sex-ratio column once became
    the timeline. Years must sit in 1900-2100."""
    sample = s.dropna().astype(str).head(60)
    if len(sample) < 3:
        return False
    parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
    ok = parsed.notna()
    if ok.mean() < 0.6:
        return False
    years = parsed.dropna().dt.year
    return bool(years.between(1900, 2100).mean() > 0.9)


def _is_monthly(series: pd.Series) -> bool:
    """True when the distinct periods parse as dates spaced ~one month."""
    vals = series.dropna().astype(str).unique()
    parsed = pd.to_datetime(pd.Series(sorted(vals)), errors="coerce", format="mixed")
    parsed = parsed.dropna().sort_values()
    if len(parsed) < 13:
        return False
    diffs = parsed.diff().dropna().dt.days
    return bool(diffs.between(28, 31).mean() > 0.8)


def _pick_columns(df: pd.DataFrame) -> dict[str, Any]:
    period = _find_period_column(df)
    if period is not None and not _plausible_period(df[period]):
        period = None
    key = _find_entity_key(df, period)
    numerics = [
        str(c) for c in df.columns
        if pd.api.types.is_numeric_dtype(df[c]) and df[c].nunique(dropna=True) > 2
        and str(c) != period
    ]
    cats = [
        str(c) for c in df.columns
        if not pd.api.types.is_numeric_dtype(df[c]) and str(c) != period
        and 2 <= df[c].nunique(dropna=True) <= MAX_CAT_LEVELS
        # all-unique text is an identifier, not a category worth counting
        and df[c].nunique(dropna=True) < len(df)
        # numbers-stored-as-text are broken measures, not categories
        and not _is_numberish_text(df[c])
    ]
    # Prefer the entity key as the main categorical; highest-spread numeric first.
    if key and key in cats:
        cats = [key] + [c for c in cats if c != key]
    numerics.sort(key=lambda c: float(df[c].std() or 0) / (abs(float(df[c].mean() or 0)) + 1e-9),
                  reverse=True)
    return {"period": period, "cats": cats, "numerics": numerics}


def starter_questions(df: pd.DataFrame, source: str = "",
                      focus_columns: list[str] | None = None) -> list[dict[str, Any]]:
    """Up to MAX_STARTERS {question, plan} candidates, most interesting first.
    focus_columns (a chosen domain) restricts the measures explored; the
    grouping columns stay open so every domain can still be sliced."""
    picks = _pick_columns(df)
    period, cats, numerics = picks["period"], picks["cats"], picks["numerics"]
    if focus_columns:
        focus = {str(c) for c in focus_columns}
        focused = [n for n in numerics if n in focus]
        if focused:
            numerics = focused
    out: list[dict[str, Any]] = []

    if cats and numerics:
        cat, num = cats[0], numerics[0]
        n = min(10, int(df[cat].nunique(dropna=True)))
        out.append({
            "question": f"Which {cat} values have the highest total {num}?",
            "plan": {"source": source, "steps": [
                {"op": "group_by", "columns": [cat]},
                {"op": "aggregate", "column": num, "fn": "sum", "alias": f"total_{num}"},
                {"op": "sort", "column": f"total_{num}", "dir": "desc"},
                {"op": "top_n", "n": n},
            ]},
        })
        # The lagging end matters as much as the leaders for policy work.
        if int(df[cat].nunique(dropna=True)) > 3:
            out.append({
                "question": f"Which {cat} values have the lowest total {num}?",
                "plan": {"source": source, "steps": [
                    {"op": "group_by", "columns": [cat]},
                    {"op": "aggregate", "column": num, "fn": "sum", "alias": f"total_{num}"},
                    {"op": "sort", "column": f"total_{num}", "dir": "asc"},
                    {"op": "top_n", "n": min(5, n)},
                ]},
            })
        # Relationships first: how two measures move together across groups.
        if len(numerics) > 1:
            num2 = numerics[1]
            out.append({
                "question": f"How do {num} and {num2} move together across {cat}?",
                "plan": {"source": source, "steps": [
                    {"op": "group_by", "columns": [cat]},
                    {"op": "aggregate", "column": num, "fn": "sum", "alias": f"total_{num}"},
                    {"op": "aggregate", "column": num2, "fn": "sum", "alias": f"total_{num2}"},
                ]},
            })
        # Diversity: the average view uses the SECOND grouping column when
        # one exists, so the board is not one category's story on repeat.
        avg_cat = cats[1] if len(cats) > 1 else cats[0]
        avg_num = numerics[2] if len(numerics) > 2 else num
        out.append({
            "question": f"What is the average {avg_num} per {avg_cat}?",
            "plan": {"source": source, "steps": [
                {"op": "group_by", "columns": [avg_cat]},
                {"op": "aggregate", "column": avg_num, "fn": "mean", "alias": f"avg_{avg_num}"},
                {"op": "sort", "column": f"avg_{avg_num}", "dir": "desc"},
            ]},
        })

    if period and numerics:
        num = numerics[0]
        out.append({
            "question": f"How does total {num} move across {period}?",
            "plan": {"source": source, "steps": [
                {"op": "group_by", "columns": [period]},
                {"op": "aggregate", "column": num, "fn": "sum", "alias": f"total_{num}"},
                {"op": "sort", "column": period, "dir": "asc"},
            ]},
        })
        # The comparison view: period-over-period change (diverging bars).
        if int(df[period].nunique(dropna=True)) >= 3:
            out.append({
                "question": f"How did total {num} change from one {period} to the next?",
                "plan": {"source": source, "steps": [
                    {"op": "group_by", "columns": [period]},
                    {"op": "aggregate", "column": num, "fn": "sum", "alias": f"total_{num}"},
                    {"op": "sort", "column": period, "dir": "asc"},
                    {"op": "delta_vs_period", "column": f"total_{num}",
                     "period_column": period, "lag": 1},
                ]},
            })
        # Seasonal honesty: monthly data spanning a year+ compares each month
        # with the SAME month a year earlier, not just the month before.
        if _is_monthly(df[period]) and int(df[period].nunique(dropna=True)) >= 13:
            out.append({
                "question": f"How does each {period} compare with the same {period} a year earlier?",
                "plan": {"source": source, "steps": [
                    {"op": "group_by", "columns": [period]},
                    {"op": "aggregate", "column": num, "fn": "sum", "alias": f"total_{num}"},
                    {"op": "sort", "column": period, "dir": "asc"},
                    {"op": "delta_vs_period", "column": f"total_{num}",
                     "period_column": period, "lag": 12},
                ]},
            })

    # A second lens: how the metric splits across the OTHER grouping column.
    if len(cats) > 1 and numerics:
        cat2, num = cats[1], numerics[0]
        out.append({
            "question": f"How does total {num} split across {cat2}?",
            "plan": {"source": source, "steps": [
                {"op": "group_by", "columns": [cat2]},
                {"op": "aggregate", "column": num, "fn": "sum", "alias": f"total_{num}"},
                {"op": "sort", "column": f"total_{num}", "dir": "desc"},
            ]},
        })

    # A second measure, when the data carries one.
    if cats and len(numerics) > 1:
        cat, num2 = cats[0], numerics[1]
        out.append({
            "question": f"Which {cat} values have the highest total {num2}?",
            "plan": {"source": source, "steps": [
                {"op": "group_by", "columns": [cat]},
                {"op": "aggregate", "column": num2, "fn": "sum", "alias": f"total_{num2}"},
                {"op": "sort", "column": f"total_{num2}", "dir": "desc"},
                {"op": "top_n", "n": min(10, int(df[cat].nunique(dropna=True)))},
            ]},
        })

    if cats:
        cat = cats[1] if len(cats) > 1 else cats[0]
        out.append({
            "question": f"How many rows fall under each {cat}?",
            "plan": {"source": source, "steps": [
                {"op": "group_by", "columns": [cat]},
                {"op": "aggregate", "column": cat, "fn": "count", "alias": "count"},
                {"op": "sort", "column": "count", "dir": "desc"},
            ]},
        })

    if numerics:
        num = numerics[0]
        out.append({
            "question": f"What are the overall total and average of {num}?",
            "plan": {"source": source, "steps": [
                {"op": "aggregate", "column": num, "fn": "sum", "alias": f"total_{num}"},
                {"op": "aggregate", "column": num, "fn": "mean", "alias": f"avg_{num}"},
            ]},
        })

    return out[:MAX_STARTERS]
