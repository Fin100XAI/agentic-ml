"""Query readiness: is this data fit for direct questioning?

Deterministic checks for the failure modes that silently poison query
answers: period gaps, entities missing from some periods, duplicated
entity-period rows, order-of-magnitude unit jumps mid-series, and
near-duplicate category spellings ('Nashik'/'Nasik'). Findings surface
on the health screen; unfixed ones become caveats on every answer that
touches the affected columns.
"""
from __future__ import annotations

import difflib
from typing import Any

import numpy as np
import pandas as pd

from ..librarian import _normalize

MAX_UNIQUE_FOR_KEYS = 200
SCALE_JUMP = 8.0  # median shifting by this factor between periods = unit jump


def _find_period_column(df: pd.DataFrame) -> str | None:
    for col in df.columns:
        n = _normalize(str(col))
        if any(k in n for k in ("date", "month", "week", "quarter", "year", "period", "time")):
            if df[col].nunique(dropna=True) > 1:
                return str(col)
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]) and df[col].nunique(dropna=True) > 1:
            return str(col)
    return None


def _find_entity_key(df: pd.DataFrame, period_col: str | None) -> str | None:
    best = None
    for col in df.columns:
        if str(col) == period_col or pd.api.types.is_numeric_dtype(df[col]):
            continue
        nunique = df[col].nunique(dropna=True)
        if 2 <= nunique <= MAX_UNIQUE_FOR_KEYS and nunique < 0.8 * len(df):
            if best is None or nunique > best[1]:
                best = (str(col), nunique)
    return best[0] if best else None


def _parse_periods(s: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(s):
        return s
    return pd.to_datetime(s.astype(str), errors="coerce", format="mixed")


def readiness_audit(df: pd.DataFrame) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    period_col = _find_period_column(df)
    key_col = _find_entity_key(df, period_col)

    # 1. Period continuity
    if period_col:
        ts = _parse_periods(df[period_col]).dropna()
        periods = pd.Series(sorted(ts.unique()))
        if len(periods) >= 3:
            diffs = periods.diff().dropna()
            # The smallest spacing is the true frequency - gaps only ever
            # make spacings LARGER, so min is robust where median is not.
            base = diffs.min()
            gaps = int((diffs > base * 1.8).sum())
            if gaps:
                findings.append({
                    "id": f"gap:{period_col}",
                    "kind": "period_gap",
                    "title": f"Gaps in '{period_col}' coverage",
                    "detail": f"{gaps} gap(s) in the time coverage - some periods have no rows at all. "
                              "Questions like 'last quarter' will silently cover less than they say.",
                    "columns": [period_col],
                    "fixable": False,
                })

    # 2 + 3. Key completeness and duplicate entity-period rows
    if period_col and key_col:
        counts = df.groupby([key_col, period_col], dropna=False).size()
        dupes = counts[counts > 1]
        if len(dupes):
            examples = ", ".join(str(i[0]) for i in dupes.index[:3])
            findings.append({
                "id": f"dupkey:{key_col}",
                "kind": "duplicate_keys",
                "title": f"More than one row per {key_col} and {period_col}",
                "detail": f"{len(dupes)} entity-period pair(s) appear multiple times (e.g. {examples}). "
                          "Totals and averages will double-count them.",
                "columns": [key_col, period_col],
                "fixable": False,
            })
        n_periods = df[period_col].nunique(dropna=True)
        per_entity = df.groupby(key_col, dropna=False)[period_col].nunique()
        incomplete = per_entity[per_entity < n_periods]
        if len(incomplete) and n_periods > 1:
            examples = ", ".join(str(i) for i in incomplete.index[:3])
            findings.append({
                "id": f"incomplete:{key_col}",
                "kind": "key_incomplete",
                "title": f"Some {key_col} values are missing from some periods",
                "detail": f"{len(incomplete)} of {len(per_entity)} entities lack rows in at "
                          f"least one period (e.g. {examples}). Comparisons across periods "
                          "will silently drop or misrepresent them.",
                "columns": [key_col, period_col],
                "fixable": False,
            })

    # 4. Unit/scale jumps mid-series
    if period_col:
        ts = _parse_periods(df[period_col])
        order = df.assign(__p=ts).dropna(subset=["__p"])
        for col in df.columns:
            if not pd.api.types.is_numeric_dtype(df[col]) or str(col) == period_col:
                continue
            med = order.groupby("__p")[col].median().dropna()
            med = med[med.abs() > 0]
            if len(med) >= 3:
                ratio = (med / med.shift(1)).abs().dropna()
                jumps = ratio[(ratio > SCALE_JUMP) | (ratio < 1 / SCALE_JUMP)]
                if len(jumps):
                    findings.append({
                        "id": f"scale:{col}",
                        "kind": "scale_jump",
                        "title": f"'{col}' changes scale mid-series",
                        "detail": f"The typical value of '{col}' shifts by {SCALE_JUMP:.0f}x or more "
                                  "between periods - often a unit change (lakhs vs rupees, counts vs "
                                  "percentages). Trends across the jump are not comparable.",
                        "columns": [str(col), period_col],
                        "fixable": False,
                    })

    # 5. Categorical near-duplicate spellings
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]) or str(col) == period_col:
            continue
        uniques = [str(v) for v in df[col].dropna().unique()[:50]]
        if not 2 <= len(uniques) <= 50:
            continue
        norm = {u: _normalize(u) for u in uniques}
        pairs = []
        seen: set[frozenset] = set()
        for i, a in enumerate(uniques):
            for b in uniques[i + 1:]:
                if a == b or frozenset((a, b)) in seen:
                    continue
                seen.add(frozenset((a, b)))
                if norm[a] == norm[b] or (
                    norm[a][:1] == norm[b][:1]
                    and difflib.SequenceMatcher(None, norm[a], norm[b]).ratio() > 0.86
                ):
                    pairs.append((a, b))
        if pairs:
            # Canonical spelling = the more frequent variant.
            vc = df[col].astype(str).value_counts()
            mapping = {}
            for a, b in pairs[:5]:
                canonical = a if vc.get(a, 0) >= vc.get(b, 0) else b
                variant = b if canonical == a else a
                mapping[variant] = canonical
            findings.append({
                "id": f"spelling:{col}",
                "kind": "near_duplicates",
                "title": f"'{col}' has near-duplicate spellings",
                "detail": "These look like the same thing spelled differently: "
                          + "; ".join(f"'{v}' vs '{c}'" for v, c in mapping.items())
                          + ". Grouped answers will split them into separate rows.",
                "columns": [str(col)],
                "fixable": True,
                "fix": {"kind": "harmonize_values", "column": str(col), "mapping": mapping},
            })

    return {
        "period_column": period_col,
        "key_column": key_col,
        "findings": findings,
    }


def caveats_for_columns(findings: list[dict[str, Any]], used_columns: list[str]) -> list[str]:
    """The caveat lines a query answer must carry when it touches columns
    with unfixed readiness findings (audit declined != audit forgotten)."""
    used_norm = {_normalize(str(c)) for c in used_columns}
    out = []
    for f in findings:
        if any(_normalize(str(c)) in used_norm for c in f.get("columns", [])):
            out.append(f"{f['title']}: {f['detail']}")
    return out
