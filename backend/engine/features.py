"""Feature engineering: deterministic candidates the agent curates, human approves.

``propose_features`` scans the data for transformations with a defensible
rationale (skewed columns, related numeric pairs, long text). The feature
agent then keeps/drops and rewrites rationales in plain language, and the
human ticks the ones to apply. ``apply_features`` builds the new columns.

New column names use the ``__`` convention so display labels resolve
automatically (col__log, a__per__b, a__x__b, col__length).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

MAX_CANDIDATES = 8


def parents_of(spec: dict[str, Any]) -> set[str]:
    """The raw source columns an engineered feature is derived from.

    Explicit lineage metadata: the leakage guard uses this to make sure an
    excluded column cannot sneak back in under a new engineered name.
    """
    return set(spec.get("parent_columns") or spec.get("columns") or [])


def propose_features(
    df: pd.DataFrame, target: str | None = None, use_case: str | None = None
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    numeric = [
        c for c in df.columns
        if c != target and pd.api.types.is_numeric_dtype(df[c]) and df[c].nunique(dropna=True) > 10
    ]

    # 1. Log transform for heavily right-skewed non-negative columns.
    for col in numeric:
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(s) < 20 or (s < 0).any():
            continue
        skew = float(s.skew())
        if skew > 2:
            out.append({
                "id": f"log:{col}",
                "kind": "log",
                "columns": [col], "parent_columns": [col],
                "name": f"{col}__log",
                "rationale": f"'{col}' is heavily skewed (skew {skew:.1f}) - a log scale lets the model treat "
                             "a jump from 10 to 100 like a jump from 100 to 1000 instead of ignoring the small end.",
                "recommended": True,
            })

    # 2. Ratio + interaction between the numeric pair most tied to the outcome.
    ranked = _rank_numeric(df, numeric, target)
    if len(ranked) >= 2:
        a, b = ranked[0], ranked[1]
        b_vals = pd.to_numeric(df[b], errors="coerce")
        if (b_vals != 0).mean() > 0.95:
            out.append({
                "id": f"ratio:{a}:{b}",
                "kind": "ratio",
                "columns": [a, b], "parent_columns": [a, b],
                "name": f"{a}__per__{b}",
                "rationale": f"'{a}' relative to '{b}' - the two strongest numeric signals; their ratio often "
                             "captures intensity (per-unit behaviour) that neither column shows alone.",
                "recommended": use_case == "classification",
            })
        out.append({
            "id": f"interact:{a}:{b}",
            "kind": "interaction",
            "columns": [a, b], "parent_columns": [a, b],
            "name": f"{a}__x__{b}",
            "rationale": f"'{a}' combined with '{b}' - lets the model see cases where both are high (or both low) "
                         "as different from cases where only one is.",
            "recommended": False,
        })

    # 3. Length of long free-text columns.
    for col in df.columns:
        if col == target or df[col].dtype != object:
            continue
        sample = df[col].dropna().astype(str).head(200)
        if len(sample) < 20:
            continue
        if pd.to_datetime(sample.head(50), errors="coerce", format="mixed").notna().mean() > 0.9:
            continue  # dates are expanded elsewhere
        if float(sample.str.len().mean()) > 15 and sample.nunique() > 10:
            out.append({
                "id": f"length:{col}",
                "kind": "length",
                "columns": [col], "parent_columns": [col],
                "name": f"{col}__length",
                "rationale": f"'{col}' is free text the model would otherwise drop - its length alone "
                             "(short note vs long note) is often a usable signal.",
                "recommended": False,
            })

    return out[:MAX_CANDIDATES]


def _rank_numeric(df: pd.DataFrame, numeric: list[str], target: str | None) -> list[str]:
    """Order numeric columns by |correlation with the outcome|, else variance."""
    if target and target in df.columns:
        y = pd.to_numeric(df[target], errors="coerce")
        if y.notna().mean() < 0.5:
            y = pd.Series(pd.factorize(df[target])[0], index=df.index).replace(-1, np.nan)
        corrs = {}
        for c in numeric:
            v = pd.to_numeric(df[c], errors="coerce")
            corr = v.corr(y)
            if pd.notna(corr):
                corrs[c] = abs(float(corr))
        if corrs:
            return sorted(corrs, key=corrs.get, reverse=True)
    cvs = {}
    for c in numeric:
        v = pd.to_numeric(df[c], errors="coerce").dropna()
        if len(v) and v.mean():
            cvs[c] = abs(float(v.std() / v.mean()))
    return sorted(cvs, key=cvs.get, reverse=True)


def apply_features(df: pd.DataFrame, specs: list[dict[str, Any]]) -> pd.DataFrame:
    if not specs:
        return df
    work = df.copy()
    for s in specs:
        try:
            cols = s["columns"]
            if s["kind"] == "log":
                v = pd.to_numeric(work[cols[0]], errors="coerce").clip(lower=0)
                work[s["name"]] = np.log1p(v)
            elif s["kind"] == "ratio":
                denom = pd.to_numeric(work[cols[1]], errors="coerce").replace(0, np.nan)
                work[s["name"]] = pd.to_numeric(work[cols[0]], errors="coerce") / denom
            elif s["kind"] == "interaction":
                work[s["name"]] = (
                    pd.to_numeric(work[cols[0]], errors="coerce")
                    * pd.to_numeric(work[cols[1]], errors="coerce")
                )
            elif s["kind"] == "length":
                col = work[cols[0]]
                work[s["name"]] = col.astype(str).str.len().where(col.notna())
        except Exception:
            continue  # a single bad spec must not sink the run
    return work
