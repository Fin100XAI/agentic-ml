"""Data Prep Studio engine: pure helpers that turn a pile of sheets into one
analysis-ready table. Deterministic throughout - the LLM only reads the
inventory (names, dtypes, shapes; never row values) and phrases guidance.

PREP-STUDIO prototype: additive module, nothing existing imports it.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

_YEAR_RE = re.compile(r"(19|20)\d{2}")
_TOTAL_RE = re.compile(r"^\s*(grand\s+)?(total|all|overall|india|sum)\b", re.I)


def normalize_col(name: str) -> str:
    """'Dist. Name' and 'dist_name' should meet in the middle."""
    return re.sub(r"[^a-z0-9]+", "", str(name).lower())


def year_guess(label: str) -> int | None:
    m = _YEAR_RE.search(str(label))
    if not m:
        return None
    y = int(m.group(0))
    return y if 1900 <= y <= 2100 else None


def sheet_inventory(frames: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    """What the user (and the guide agent) sees about each sheet - metadata
    only, no row values."""
    out: list[dict[str, Any]] = []
    for name, df in frames.items():
        unnamed = sum(1 for c in df.columns if str(c).lower().startswith("unnamed"))
        out.append({
            "name": name,
            "rows": int(len(df)),
            "cols": int(df.shape[1]),
            "columns": [{"name": str(c), "dtype": str(df[c].dtype)} for c in df.columns],
            "year_guess": year_guess(name),
            "unnamed_columns": unnamed,
        })
    return out


def _schema_similarity(a: list[str], b: list[str]) -> float:
    sa = {normalize_col(c) for c in a}
    sb = {normalize_col(c) for c in b}
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _canonical_mapping(frames: dict[str, pd.DataFrame]) -> dict[str, dict[str, str]]:
    """Per-sheet rename map onto canonical names. The first sheet's spelling
    wins; later sheets map onto it by normalized name."""
    canon: dict[str, str] = {}
    mappings: dict[str, dict[str, str]] = {}
    for name, df in frames.items():
        m: dict[str, str] = {}
        for c in df.columns:
            key = normalize_col(c)
            if key not in canon:
                canon[key] = str(c)
            if str(c) != canon[key]:
                m[str(c)] = canon[key]
        mappings[name] = m
    return mappings


def _join_key_candidates(frames: dict[str, pd.DataFrame]) -> list[str]:
    """Normalized column names present in EVERY sheet with high uniqueness -
    plausible join keys."""
    sheets = list(frames.values())
    if len(sheets) < 2:
        return []
    common = set.intersection(*({normalize_col(c) for c in df.columns} for df in sheets))
    out: list[str] = []
    for key in common:
        ok = True
        label = None
        for df in sheets:
            col = next((c for c in df.columns if normalize_col(c) == key), None)
            if col is None:
                ok = False
                break
            label = label or str(col)
            n = len(df)
            if n == 0 or df[col].nunique(dropna=True) / n < 0.8:
                ok = False
                break
        if ok and label:
            out.append(label)
    return sorted(out)


def propose_combine(frames: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Deterministic combine proposal. The agent phrases it; code decides."""
    names = list(frames.keys())
    if len(names) == 1:
        return {"strategy": "single", "sheets": names, "notes": [], "mappings": {},
                "join_key": None, "add_source_column": False, "add_year_column": False}
    sims = []
    base = list(frames[names[0]].columns)
    for n in names[1:]:
        sims.append(_schema_similarity(base, list(frames[n].columns)))
    min_sim = min(sims) if sims else 1.0
    years = [year_guess(n) for n in names]
    have_years = sum(1 for y in years if y is not None) >= max(2, len(names) - 1)
    notes: list[str] = []
    if min_sim >= 0.6:
        mappings = _canonical_mapping(frames)
        renamed = sum(len(m) for m in mappings.values())
        if renamed:
            notes.append(f"{renamed} column name(s) spelled differently across sheets "
                         "will be harmonized to one spelling.")
        if have_years:
            notes.append("Sheet names carry years - a 'year' column will be added "
                         "so time questions work after stacking.")
        return {"strategy": "stack", "sheets": names, "mappings": mappings,
                "join_key": None, "add_source_column": True,
                "add_year_column": have_years, "notes": notes}
    keys = _join_key_candidates(frames)
    if keys:
        notes.append(f"The sheets share the high-uniqueness column '{keys[0]}' - "
                     "they look like different facts about the same entities.")
        return {"strategy": "join", "sheets": names, "mappings": {},
                "join_key": keys[0], "join_candidates": keys,
                "add_source_column": False, "add_year_column": False, "notes": notes}
    notes.append("The sheets share too few columns to stack and no common key to "
                 "join - pick one sheet to continue with, or upload files that "
                 "belong together.")
    return {"strategy": "review", "sheets": names, "mappings": {}, "join_key": None,
            "add_source_column": False, "add_year_column": False, "notes": notes}


def apply_combine(frames: dict[str, pd.DataFrame], spec: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Execute the approved combine spec. Deterministic; returns the frame
    plus an honest report of what happened."""
    strategy = spec.get("strategy")
    names = [n for n in spec.get("sheets", list(frames.keys())) if n in frames]
    if not names:
        raise ValueError("No sheets selected.")
    if strategy == "single" or len(names) == 1:
        pick = spec.get("pick") or names[0]
        if pick not in frames:
            raise ValueError(f"Unknown sheet '{pick}'.")
        df = frames[pick].copy()
        return df, {"strategy": "single", "sheets": [pick], "rows": int(len(df))}
    if strategy == "stack":
        mappings = spec.get("mappings") or {}
        parts: list[pd.DataFrame] = []
        for n in names:
            part = frames[n].rename(columns=mappings.get(n, {}))
            if spec.get("add_source_column"):
                part = part.assign(source_sheet=n)
            if spec.get("add_year_column"):
                part = part.assign(year=year_guess(n))
            parts.append(part)
        df = pd.concat(parts, ignore_index=True, sort=False)
        return df, {"strategy": "stack", "sheets": names, "rows": int(len(df)),
                    "renamed": sum(len(mappings.get(n, {})) for n in names)}
    if strategy == "join":
        key_label = spec.get("join_key")
        if not key_label:
            raise ValueError("A join needs a key column.")
        key_norm = normalize_col(key_label)
        df = None
        for n in names:
            part = frames[n]
            col = next((c for c in part.columns if normalize_col(c) == key_norm), None)
            if col is None:
                raise ValueError(f"Sheet '{n}' has no column matching '{key_label}'.")
            part = part.rename(columns={col: key_label})
            df = part if df is None else df.merge(
                part, on=key_label, how="outer", suffixes=("", f"__{n[:12]}"))
        return df, {"strategy": "join", "sheets": names, "key": key_label,
                    "rows": int(len(df))}
    raise ValueError(f"Unknown combine strategy '{strategy}'.")


def junk_scan(df: pd.DataFrame) -> dict[str, Any]:
    """Rows that poison analysis: fully-empty rows and total/summary rows
    (an 'All India' row silently doubles every sum)."""
    empty = int(df.isna().all(axis=1).sum())
    totals = 0
    text_cols = [c for c in df.columns if df[c].dtype == object][:2]
    if text_cols and len(df):
        mask = pd.Series(False, index=df.index)
        for c in text_cols:
            mask |= df[c].astype(str).str.match(_TOTAL_RE).fillna(False)
        totals = int(mask.sum())
    return {"empty_rows": empty, "total_like_rows": totals}


def drop_junk(df: pd.DataFrame, drop_empty: bool, drop_totals: bool) -> tuple[pd.DataFrame, int]:
    before = len(df)
    if drop_empty:
        df = df.dropna(how="all")
    if drop_totals:
        text_cols = [c for c in df.columns if df[c].dtype == object][:2]
        if text_cols:
            mask = pd.Series(False, index=df.index)
            for c in text_cols:
                mask |= df[c].astype(str).str.match(_TOTAL_RE).fillna(False)
            df = df[~mask]
    return df.reset_index(drop=True), before - len(df)
