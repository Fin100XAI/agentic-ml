"""Dataset profiling / EDA engine.

Industry-agnostic: infers structure from the data itself. Produces a structured
summary consumed both by the agents (as context) and by the UI (for display).
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


# Semantic column roles inferred from the data.
NUMERIC = "numeric"
CATEGORICAL = "categorical"
DATETIME = "datetime"
BOOLEAN = "boolean"
TEXT = "text"
IDENTIFIER = "identifier"


def _clean(value: Any) -> Any:
    """Make a value JSON-safe (no NaN/inf, numpy scalars -> python)."""
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return round(value, 4)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def _infer_role(series: pd.Series, n_rows: int) -> str:
    name = str(series.name).lower()
    non_null = series.dropna()
    if non_null.empty:
        return TEXT

    if pd.api.types.is_bool_dtype(series):
        return BOOLEAN
    if pd.api.types.is_datetime64_any_dtype(series):
        return DATETIME

    if pd.api.types.is_numeric_dtype(series):
        unique = non_null.nunique()
        # Integer-like id column: unique per row and named like an id.
        if unique >= 0.95 * n_rows and ("id" in name or name.endswith("_no")):
            return IDENTIFIER
        # Small integer set reads as categorical (e.g. a 0/1/2 class label).
        if unique <= 2:
            return BOOLEAN if unique == 2 else NUMERIC
        return NUMERIC

    # Object / string columns.
    unique = non_null.nunique()
    # Try datetime parse on a sample.
    sample = non_null.astype(str).head(50)
    parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
    if parsed.notna().mean() > 0.9:
        return DATETIME
    if unique >= 0.95 * n_rows:
        return IDENTIFIER if "id" in name else TEXT
    if unique <= max(20, 0.5 * n_rows):
        return CATEGORICAL
    return TEXT


def _column_summary(series: pd.Series, role: str) -> dict[str, Any]:
    n = len(series)
    missing = int(series.isna().sum())
    summary: dict[str, Any] = {
        "name": str(series.name),
        "role": role,
        "dtype": str(series.dtype),
        "missing_count": missing,
        "missing_pct": _clean(missing / n * 100 if n else 0),
        "unique_count": int(series.nunique(dropna=True)),
        "sample_values": [_clean(v) for v in series.dropna().unique()[:5]],
    }

    non_null = series.dropna()
    if role == NUMERIC and not non_null.empty:
        summary["stats"] = {
            "min": _clean(non_null.min()),
            "max": _clean(non_null.max()),
            "mean": _clean(non_null.mean()),
            "std": _clean(non_null.std()),
            "median": _clean(non_null.median()),
        }
        # A small histogram for the UI.
        counts, edges = np.histogram(non_null.astype(float), bins=min(10, max(1, summary["unique_count"])))
        summary["histogram"] = {
            "counts": [int(c) for c in counts],
            "edges": [_clean(e) for e in edges],
        }
    elif role in (CATEGORICAL, BOOLEAN) and not non_null.empty:
        vc = non_null.value_counts().head(8)
        summary["top_values"] = [
            {"value": _clean(k), "count": int(v)} for k, v in vc.items()
        ]
    return summary


def _correlations(df: pd.DataFrame, numeric_cols: list[str]) -> list[dict[str, Any]]:
    if len(numeric_cols) < 2:
        return []
    corr = df[numeric_cols].corr(numeric_only=True)
    pairs: list[dict[str, Any]] = []
    for i, a in enumerate(numeric_cols):
        for b in numeric_cols[i + 1 :]:
            val = corr.loc[a, b]
            if pd.notna(val):
                pairs.append({"a": a, "b": b, "corr": _clean(val)})
    pairs.sort(key=lambda p: abs(p["corr"] or 0), reverse=True)
    return pairs[:10]


def _candidate_targets(columns: list[dict[str, Any]], n_rows: int) -> list[dict[str, Any]]:
    """Heuristically rank columns that could be a prediction target."""
    candidates = []
    keywords = ("target", "label", "class", "outcome", "y", "price", "amount",
                "churn", "default", "fraud", "score", "value", "sales", "revenue")
    for col in columns:
        if col["role"] in (IDENTIFIER, TEXT):
            continue
        score = 0.0
        name = col["name"].lower()
        if any(k in name for k in keywords):
            score += 2.0
        if col["role"] == BOOLEAN:
            score += 1.5  # classic classification target
        if col["role"] == CATEGORICAL and col["unique_count"] <= 10:
            score += 1.0
        if col["role"] == NUMERIC:
            score += 0.5
        if col["missing_pct"] and col["missing_pct"] > 20:
            score -= 1.0
        if score > 0:
            candidates.append({"name": col["name"], "role": col["role"], "score": _clean(score)})
    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[:5]


def _suggested_use_cases(columns: list[dict[str, Any]]) -> list[str]:
    roles = [c["role"] for c in columns]
    out: list[str] = []
    if any(r in (BOOLEAN, CATEGORICAL) for r in roles):
        out.append("classification")
    if sum(r == NUMERIC for r in roles) >= 2:
        out.append("clustering")
    if any(r == DATETIME for r in roles) and any(r == NUMERIC for r in roles):
        out.append("forecasting")
    return out or ["clustering"]


def profile_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    """Produce a full structured EDA profile of a dataframe."""
    n_rows, n_cols = df.shape
    columns: list[dict[str, Any]] = []
    for name in df.columns:
        role = _infer_role(df[name], n_rows)
        columns.append(_column_summary(df[name], role))

    numeric_cols = [c["name"] for c in columns if c["role"] == NUMERIC]
    total_missing = int(df.isna().sum().sum())

    preview = [
        {k: _clean(v) for k, v in row.items()}
        for row in df.head(10).to_dict(orient="records")
    ]

    return {
        "n_rows": int(n_rows),
        "n_cols": int(n_cols),
        "columns": columns,
        "preview": preview,
        "missingness": {
            "total_missing_cells": total_missing,
            "pct_missing": _clean(total_missing / (n_rows * n_cols) * 100 if n_rows and n_cols else 0),
            "columns_with_missing": [c["name"] for c in columns if c["missing_count"] > 0],
        },
        "correlations": _correlations(df, numeric_cols),
        "candidate_targets": _candidate_targets(columns, n_rows),
        "suggested_use_cases": _suggested_use_cases(columns),
    }
