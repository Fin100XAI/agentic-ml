"""Numbers stored as text: the most common defect in real government files
('197886' quoted, '-' for missing, '1,23,456' with separators, 'Rs. 500').
Such columns are invisible as measures - no ranking, trend, map or
relationship can use them - so a third of a typical census sheet cannot be
explored at all.

Detection and cleaning are fully deterministic. Nothing applies without
approval, and the fix lands as a derived artifact (the original never
changes, lineage kept) - the same contract as every other repair.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

PLACEHOLDERS = {"", "-", "--", "na", "n/a", "nan", "none", "nil", "null"}
PARSE_THRESHOLD = 0.6
_CODE_NAME = re.compile(r"(^|[^a-z])(id|code|cd)([^a-z]|$)", re.IGNORECASE)


def _cleaned_text(s: pd.Series) -> pd.Series:
    """Strip formatting that hides numbers: separators, currency, percent."""
    return (s.astype(str).str.strip()
            .str.replace(",", "", regex=False)
            .str.replace("₹", "", regex=False)
            .str.replace(r"(?i)^rs\.?\s*", "", regex=True)
            .str.replace("%", "", regex=False)
            .str.strip())


def clean_series(s: pd.Series) -> pd.Series:
    """Text column -> numeric column; placeholders become missing."""
    text = _cleaned_text(s)
    text = text.mask(text.str.lower().isin(PLACEHOLDERS))
    out = pd.to_numeric(text, errors="coerce")
    return out.where(s.notna(), other=pd.NA).astype(float)


def detect_text_numbers(df: pd.DataFrame) -> list[dict[str, Any]]:
    """-> proposals [{column, parse_pct, n_blank, samples}] for columns that
    are numbers wearing a text costume. Name-coded identifiers are skipped -
    converting a district code to a measure would invite nonsense totals."""
    proposals: list[dict[str, Any]] = []
    for col in df.columns:
        s = df[col]
        if s.dtype != object or _CODE_NAME.search(str(col)):
            continue
        non_null = s.dropna()
        if len(non_null) < 5:
            continue
        text = _cleaned_text(non_null)
        is_placeholder = text.str.lower().isin(PLACEHOLDERS)
        candidates = text[~is_placeholder]
        if len(candidates) < 5:
            continue
        parsed = pd.to_numeric(candidates, errors="coerce")
        parse_pct = float(parsed.notna().mean())
        if parse_pct < PARSE_THRESHOLD:
            continue
        raw_samples = non_null[~is_placeholder.values][:50]
        samples = []
        for v in raw_samples.unique()[:3]:
            cleaned = pd.to_numeric(_cleaned_text(pd.Series([v])), errors="coerce").iloc[0]
            if pd.notna(cleaned):
                samples.append({"from": str(v),
                                "to": round(float(cleaned), 2)})
        proposals.append({
            "column": str(col),
            "parse_pct": round(parse_pct * 100, 1),
            "n_blank": int(is_placeholder.sum() + s.isna().sum()),
            "samples": samples,
        })
    return proposals


def apply_text_number_fix(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col in out.columns and out[col].dtype == object:
            out[col] = clean_series(out[col])
    return out
