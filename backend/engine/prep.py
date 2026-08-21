"""Data Prep Studio engine: pure helpers that turn a pile of sheets into one
analysis-ready table. Deterministic throughout - the LLM only reads the
inventory (names, dtypes, shapes; never row values) and phrases guidance.

PREP-STUDIO prototype: additive module, nothing existing imports it.
"""
from __future__ import annotations

import datetime as _dt
import re
from typing import Any

import pandas as pd

_YEAR_RE = re.compile(r"(19|20)\d{2}")
_TOTAL_RE = re.compile(r"^\s*(grand\s+)?(total|all|overall|india|sum)\b", re.I)
# Summary rows label themselves mid-string too: 'IGST on Import - All India',
# 'Gross Revenue', 'Sub Total' - searched anywhere in the row label.
_SUMMARY_RE = re.compile(
    r"grand\s+total|all\s+india|sub\s*total|gross\s+revenue|aggregate|net\s+total",
    re.I)


def normalize_col(name: str) -> str:
    """'Dist. Name' and 'dist_name' should meet in the middle."""
    return re.sub(r"[^a-z0-9]+", "", str(name).lower())


def year_guess(label: str) -> int | None:
    m = _YEAR_RE.search(str(label))
    if not m:
        return None
    y = int(m.group(0))
    return y if 1900 <= y <= 2100 else None


def _fmt_label(v: Any) -> str:
    """Month columns in government workbooks are often real datetimes next
    to strings like 'Apr-18' - format them as compact period labels."""
    if isinstance(v, (pd.Timestamp, _dt.datetime, _dt.date)):
        return v.strftime("%b-%Y")
    return str(v).strip()


def _labels_single(raw: pd.DataFrame, h: int) -> list:
    return [None if pd.isna(v) or str(v).strip() == "" else _fmt_label(v)
            for v in raw.iloc[h]]


def _labels_pair(raw: pd.DataFrame, h: int) -> list:
    """Two-tier merged header: the top row carries block labels merged across
    several columns (forward-filled), the bottom row the per-column names -
    'Apr-18' + 'CGST' becomes 'Apr-18 CGST'."""
    # Manual forward-fill of the merged block labels (object dtype safe).
    top = []
    last = None
    for v in raw.iloc[h]:
        if pd.notna(v) and str(v).strip() != "":
            last = v
        top.append(last)
    bot = raw.iloc[h + 1]
    out = []
    for t, b in zip(top, bot):
        tl = None if pd.isna(t) or str(t).strip() == "" else _fmt_label(t)
        bl = None if pd.isna(b) or str(b).strip() == "" else _fmt_label(b)
        if tl and bl and tl != bl:
            out.append(f"{tl} {bl}")
        else:
            out.append(bl or tl)
    return out


def _label_score(labels: list) -> float:
    """How usable a candidate set of column names is: filled, unique, text."""
    vals = [l for l in labels if l]
    if len(vals) < 2:
        return 0.0
    uniq = len(set(vals)) / len(vals)
    nonnum = sum(
        1 for l in vals
        if not l.replace(",", "").replace(".", "", 1).lstrip("-").isdigit()
    ) / len(vals)
    fill = len(vals) / max(1, len(labels))
    return 0.35 * uniq + 0.3 * nonnum + 0.35 * fill


def _header_score(row: pd.Series) -> float:
    """How header-like a raw row is: filled, unique, mostly non-numeric text."""
    vals = [v for v in row if pd.notna(v) and str(v).strip() != ""]
    if len(vals) < 2:
        return 0.0
    strs = [str(v).strip() for v in vals]
    uniq = len(set(strs)) / len(strs)
    nonnum = sum(
        1 for s in strs
        if not s.replace(",", "").replace(".", "", 1).lstrip("-").isdigit()
    ) / len(strs)
    fill = len(vals) / max(1, len(row))
    return 0.35 * uniq + 0.3 * nonnum + 0.35 * fill


def detect_header(raw: pd.DataFrame, scan: int = 10,
                  force_row: int | None = None) -> dict:
    """Find the row(s) that actually name the columns. Handles the two
    hardest common shapes: a title banner above the header, and a TWO-TIER
    merged header (block labels forward-filled over per-column names).
    Returns a dict with 'row' and 'tiers' (1 or 2); row 0 / 1 tier means a
    normal file."""
    n = min(scan, len(raw))
    if n == 0:
        return {"row": 0, "tiers": 1}
    if force_row is not None:
        h = max(0, min(force_row, len(raw) - 1))
        s1 = _label_score(_labels_single(raw, h))
        s2 = _label_score(_labels_pair(raw, h)) if h + 1 < len(raw) else 0.0
        return {"row": h, "tiers": 2 if s2 > s1 + 0.1 else 1}
    base = _label_score(_labels_single(raw, 0))
    best = {"row": 0, "tiers": 1, "score": base}
    for h in range(n):
        s1 = _label_score(_labels_single(raw, h))
        if h > 0 and s1 > best["score"] and s1 >= 0.75 and base < 0.55:
            best = {"row": h, "tiers": 1, "score": s1}
        # A merged header band spans SEVERAL columns. One filled cell is a
        # note ('(Rs. In Crore)'), not a tier - treating it as one steals
        # the header row and mangles every column name below it.
        if h + 1 < len(raw) and int(raw.iloc[h].notna().sum()) >= 2:
            s2 = _label_score(_labels_pair(raw, h))
            s1_next = _label_score(_labels_single(raw, h + 1))
            # The pair must beat BOTH single readings clearly - a banner over
            # a normal header, or row 0 over the first data row, must never
            # masquerade as a merged two-tier header.
            if (s2 > best["score"] + 0.1 and s2 >= 0.75
                    and s2 > s1 + 0.1 and s2 > s1_next + 0.05):
                best = {"row": h, "tiers": 2, "score": s2}
    return {"row": best["row"], "tiers": best["tiers"]}


def detect_header_row(raw: pd.DataFrame, scan: int = 10) -> int:
    """Back-compat single-row view of detect_header."""
    return int(detect_header(raw, scan)["row"])


def reheader(raw: pd.DataFrame, header_row: int, tiers: int = 1) -> pd.DataFrame:
    """Rebuild the frame with the detected header row(s) as column names,
    restoring numeric dtypes that header=None parsing turned into objects."""
    labels = (_labels_pair(raw, header_row)
              if tiers == 2 and header_row + 1 < len(raw)
              else _labels_single(raw, header_row))
    names = []
    seen = {}
    for i, l in enumerate(labels):
        name = l or f"column_{i + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1
        names.append(name)
    df = raw.iloc[header_row + tiers:].reset_index(drop=True)
    df.columns = names
    df = df.dropna(axis=1, how="all").dropna(how="all")
    for c in df.columns:
        if df[c].dtype == object:
            num = pd.to_numeric(df[c], errors="coerce")
            if len(df) and num.notna().mean() > 0.9:
                df[c] = num
    return df


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


def join_quality(frames: dict[str, pd.DataFrame], key_label: str,
                 sheets: list[str] | None = None) -> dict[str, Any]:
    """How well a join key actually lines up across sheets. Silent data loss
    hides here: a key that matches 60% of rows drops 40% of the data without
    saying so, and the officer should see that BEFORE approving."""
    names = [n for n in (sheets or list(frames)) if n in frames]
    if len(names) < 2 or not key_label:
        return {"key": key_label, "checked": False}
    key_norm = normalize_col(key_label)
    sets: dict[str, set[str]] = {}
    for n in names:
        col = next((c for c in frames[n].columns
                    if normalize_col(c) == key_norm), None)
        if col is None:
            return {"key": key_label, "checked": False,
                    "note": f"'{key_label}' is missing from sheet '{n}'."}
        sets[n] = {str(v).strip() for v in frames[n][col].dropna()}
    shared = set.intersection(*sets.values())
    per_sheet = []
    for n in names:
        total = len(sets[n])
        matched = len(sets[n] & shared)
        missing = sorted(sets[n] - shared)[:5]
        per_sheet.append({
            "sheet": n, "keys": total, "matched": matched,
            "match_pct": round(100 * matched / total, 1) if total else 0.0,
            "unmatched_examples": missing,
        })
    worst = min((p["match_pct"] for p in per_sheet), default=0.0)
    return {"key": key_label, "checked": True, "shared_keys": len(shared),
            "per_sheet": per_sheet, "worst_match_pct": worst,
            "verdict": "clean" if worst >= 99 else "lossy" if worst >= 60 else "poor"}


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
            vals = df[c].astype(str)
            mask |= vals.str.match(_TOTAL_RE).fillna(False)
            mask |= vals.str.contains(_SUMMARY_RE, na=False)
        totals = int(mask.sum())
    return {"empty_rows": empty, "total_like_rows": totals,
            "footer_rows": _footer_rows(df)}


def _footer_rows(df: pd.DataFrame) -> int:
    """Trailing note rows ('Note :', 'Source: ...'). Sparsity is judged
    RELATIVE to the body: a fixed fraction of the column count marks every row
    on a narrow table and nothing on a wide one."""
    if df.empty:
        return 0
    filled = df.notna().sum(axis=1)
    body = float(filled.median() or 0)
    thresh = max(1, int(0.25 * body))
    n = 0
    for i in range(len(df) - 1, -1, -1):
        if int(filled.iloc[i]) <= thresh:
            n += 1
        else:
            break
    return n if n < len(df) else 0

def drop_junk(df: pd.DataFrame, drop_empty: bool, drop_totals: bool,
              drop_footer: bool = False) -> tuple[pd.DataFrame, int]:
    before = len(df)
    if drop_footer:
        n = _footer_rows(df)
        if n:
            df = df.iloc[: len(df) - n]
    if drop_empty:
        df = df.dropna(how="all")
    if drop_totals:
        text_cols = [c for c in df.columns if df[c].dtype == object][:2]
        if text_cols:
            mask = pd.Series(False, index=df.index)
            for c in text_cols:
                vals = df[c].astype(str)
                mask |= vals.str.match(_TOTAL_RE).fillna(False)
                mask |= vals.str.contains(_SUMMARY_RE, na=False)
            df = df[~mask]
    return df.reset_index(drop=True), before - len(df)
