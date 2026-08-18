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

MAX_STARTERS = 5
MAX_CAT_LEVELS = 30


def _pick_columns(df: pd.DataFrame) -> dict[str, Any]:
    period = _find_period_column(df)
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
    ]
    # Prefer the entity key as the main categorical; highest-spread numeric first.
    if key and key in cats:
        cats = [key] + [c for c in cats if c != key]
    numerics.sort(key=lambda c: float(df[c].std() or 0) / (abs(float(df[c].mean() or 0)) + 1e-9),
                  reverse=True)
    return {"period": period, "cats": cats, "numerics": numerics}


def starter_questions(df: pd.DataFrame, source: str = "") -> list[dict[str, Any]]:
    """Up to MAX_STARTERS {question, plan} candidates, most interesting first."""
    picks = _pick_columns(df)
    period, cats, numerics = picks["period"], picks["cats"], picks["numerics"]
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
        out.append({
            "question": f"What is the average {num} per {cat}?",
            "plan": {"source": source, "steps": [
                {"op": "group_by", "columns": [cat]},
                {"op": "aggregate", "column": num, "fn": "mean", "alias": f"avg_{num}"},
                {"op": "sort", "column": f"avg_{num}", "dir": "desc"},
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
