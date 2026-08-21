"""Deep column profiling for the Data Prep Studio.

General-purpose and deterministic: given any table (and any banner text
found above its header), work out for every column what it IS - type,
semantic role, unit and scale, missing-value sentinels, value domain - and
for the table as a whole what one row STANDS FOR (grain) and whether the
columns hide a wide period block that should be reshaped.

Nothing here is tuned to one file: every detector is driven by evidence in
the values plus name hints, and every finding carries a confidence so the
interview can ask about the uncertain ones instead of guessing.
"""
from __future__ import annotations

import datetime as _dt
import re
from typing import Any

import pandas as pd

# ---------------------------------------------------------------- constants

MISSING_TOKENS = {
    "", "-", "--", "---", "na", "n/a", "n.a.", "nil", "none", "null", "nan",
    "not available", "not applicable", "no data", "*", "**", "#", "?", ".",
    "unknown", "unspecified", "-na-",
}

_CURRENCY = re.compile(r"[₹$€£]|\b(rs|inr|usd)\.?\s*", re.I)
_FOOTNOTE = re.compile(r"[*#†‡]+\s*$")
_PAREN_NEG = re.compile(r"^\((.*)\)$")
# 1,23,456 (Indian lakh-crore grouping) vs 123,456 (western thousands)
_INDIAN_GROUP = re.compile(r"^\d{1,2}(,\d{2})+,\d{3}$")
_WESTERN_GROUP = re.compile(r"^\d{1,3}(,\d{3})+$")

_FY = re.compile(r"^(f\.?y\.?\s*)?((19|20)\d{2})\s*[-/]\s*((19|20)?\d{2})$", re.I)
_MONTH_YEAR = re.compile(
    r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
    r"[\s\-/,]*((19|20)?\d{2})$", re.I)
_QUARTER = re.compile(r"^(q[1-4])[\s\-/]*((19|20)?\d{2})$|^((19|20)\d{2})[\s\-]?(q[1-4])$", re.I)
_BARE_YEAR = re.compile(r"^(19|20)\d{2}$")

_TRUE = {"y", "yes", "true", "t", "1", "haan", "हाँ"}
_FALSE = {"n", "no", "false", "f", "0", "nahi", "नहीं"}

_GEO_HINTS = ("state", "district", "city", "town", "village", "region", "zone",
              "block", "taluk", "tehsil", "ward", "circle", "division",
              "country", "province", "mandal", "panchayat", "constituency")
_ID_HINTS = ("id", "code", "no", "number", "sr", "srno", "serial", "ref",
             "uid", "key", "cd")
_PERIOD_HINTS = ("date", "month", "year", "period", "quarter", "week", "day",
                 "time", "fy", "session")
_PCT_HINTS = ("pct", "percent", "percentage", "rate", "ratio", "share", "%")
_UNIT_PATTERNS = [
    (re.compile(r"\bin\s+crores?\b|\bcrores?\b|\bcr\.?\b", re.I), "crore", 1e7),
    (re.compile(r"\bin\s+lakhs?\b|\blakhs?\b|\blacs?\b", re.I), "lakh", 1e5),
    (re.compile(r"\bin\s+millions?\b|\bmillions?\b|\bmn\b", re.I), "million", 1e6),
    (re.compile(r"\bin\s+billions?\b|\bbillions?\b|\bbn\b", re.I), "billion", 1e9),
    (re.compile(r"\bin\s+thousands?\b|\bthousands?\b|\b000s\b", re.I), "thousand", 1e3),
    (re.compile(r"\bper\s+1000\b|\bper\s+thousand\b", re.I), "per 1000", 1.0),
    (re.compile(r"\bper\s+lakh\b|\bper\s+100000\b", re.I), "per lakh", 1.0),
]
_CURRENCY_HINT = re.compile(r"₹|\brs\.?\b|\binr\b|rupees?|\bamount\b|\bvalue\b"
                            r"|collection|revenue|expenditure|cost|budget", re.I)


# ------------------------------------------------------------------ helpers

def norm_name(name: str) -> str:
    """Machine-safe canonical column name: snake_case, ascii-ish, no dupes of
    separators. Display labels are kept separately - this is the join key."""
    s = str(name).strip().lower()
    s = re.sub(r"[%]", "pct", s)
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "column"


def _cells(series: pd.Series, limit: int = 400) -> list[str]:
    """Non-missing values as trimmed strings, sampled for speed."""
    vals = series.dropna()
    if len(vals) > limit:
        vals = vals.sample(limit, random_state=42)
    out = []
    for v in vals:
        s = str(v).strip()
        if s.lower() not in MISSING_TOKENS:
            out.append(s)
    return out


def parse_number(raw: Any) -> float | None:
    """Parse a number written the way people actually write them: Indian or
    western digit grouping, currency symbols, percent signs, footnote marks,
    accounting parentheses for negatives."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    s = str(raw).strip()
    if s.lower() in MISSING_TOKENS:
        return None
    neg = False
    m = _PAREN_NEG.match(s)
    if m:
        neg, s = True, m.group(1).strip()
    s = _CURRENCY.sub("", s)
    s = _FOOTNOTE.sub("", s).strip()
    pct = s.endswith("%")
    if pct:
        s = s[:-1].strip()
    s = s.replace(",", "").replace(" ", "")
    if s in ("", "-", "."):
        return None
    try:
        val = float(s)
    except ValueError:
        return None
    return -val if neg else val


def detect_missing_sentinels(series: pd.Series) -> list[str]:
    """Which placeholder strings this column actually uses for 'no value'."""
    found: set[str] = set()
    for v in series.dropna().head(600):
        s = str(v).strip()
        if s.lower() in MISSING_TOKENS and s != "":
            found.add(s)
    return sorted(found)


def detect_number_format(series: pd.Series) -> dict[str, Any]:
    """How numeric this column is once written-number conventions are honored,
    and which conventions appear."""
    cells = _cells(series)
    if not cells:
        return {"parseable_pct": 0.0, "indian_grouping": False,
                "currency": False, "footnotes": False, "percent": False,
                "accounting_negatives": False}
    ok = sum(1 for c in cells if parse_number(c) is not None)
    return {
        "parseable_pct": round(100 * ok / len(cells), 1),
        "indian_grouping": any(_INDIAN_GROUP.match(c) for c in cells),
        "western_grouping": any(_WESTERN_GROUP.match(c) for c in cells),
        "currency": any(_CURRENCY.search(c) for c in cells),
        "footnotes": any(_FOOTNOTE.search(c) for c in cells),
        "percent": any(c.rstrip().endswith("%") for c in cells),
        "accounting_negatives": any(_PAREN_NEG.match(c) for c in cells),
    }


def parse_period(raw: Any) -> dict[str, Any] | None:
    """Recognize the period notations real reports use: full dates, month-year,
    fiscal years, quarters, bare years. Returns kind + a sortable key."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    if isinstance(raw, (pd.Timestamp, _dt.datetime, _dt.date)):
        return {"kind": "date", "key": pd.Timestamp(raw).strftime("%Y-%m-%d"),
                "label": pd.Timestamp(raw).strftime("%b-%Y")}
    s = str(raw).strip()
    if not s or s.lower() in MISSING_TOKENS:
        return None
    m = _FY.match(s)
    if m:
        start = int(m.group(2))
        return {"kind": "fiscal_year", "key": f"{start}", "label": f"FY{start}-{str(start + 1)[-2:]}"}
    m = _MONTH_YEAR.match(s)
    if m:
        # Build from the parts so 'Apr-18' and 'April 2018' land on one label.
        mon = m.group(1)[:3].title()
        yr = int(m.group(2))
        yr = yr + 2000 if yr < 100 else yr
        try:
            ts = pd.Timestamp(f"{yr}-{mon}-01")
            return {"kind": "month", "key": ts.strftime("%Y-%m"), "label": ts.strftime("%b-%Y")}
        except Exception:
            return {"kind": "month", "key": f"{yr}-{mon}", "label": f"{mon}-{yr}"}
    m = _QUARTER.match(s)
    if m:
        return {"kind": "quarter", "key": s.upper(), "label": s.upper()}
    if _BARE_YEAR.match(s):
        y = int(s)
        if 1900 <= y <= 2100:
            return {"kind": "year", "key": s, "label": s}
    try:
        ts = pd.to_datetime(s, errors="raise", format="mixed", dayfirst=True)
        if pd.notna(ts) and 1900 <= ts.year <= 2100:
            return {"kind": "date", "key": ts.strftime("%Y-%m-%d"), "label": ts.strftime("%d-%b-%Y")}
    except Exception:
        pass
    return None


def detect_period_column(series: pd.Series, name: str) -> dict[str, Any] | None:
    cells = _cells(series, 200)
    if len(cells) < 3:
        return None
    parsed = [parse_period(c) for c in cells]
    hits = [p for p in parsed if p]
    share = len(hits) / len(cells)
    if share < 0.8:
        return None
    kinds = {p["kind"] for p in hits}
    hinted = any(h in norm_name(name) for h in _PERIOD_HINTS)
    # A bare-year column of pure integers is ambiguous with a measure - require
    # a name hint before calling it a period.
    if kinds == {"year"} and not hinted:
        return None
    return {"kind": sorted(kinds)[0], "coverage_pct": round(100 * share, 1),
            "distinct": int(series.nunique(dropna=True))}


def detect_boolean(series: pd.Series) -> dict[str, Any] | None:
    cells = [c.lower() for c in _cells(series, 200)]
    if len(cells) < 3:
        return None
    vocab = set(cells)
    if not vocab or len(vocab) > 4:
        return None
    if vocab <= (_TRUE | _FALSE) and (vocab & _TRUE) and (vocab & _FALSE):
        return {"true_values": sorted(vocab & _TRUE), "false_values": sorted(vocab & _FALSE)}
    return None


def detect_unit(name: str, banner_hints: str = "") -> dict[str, Any] | None:
    """Units live in column names AND in the banner text above the header
    ('(Rs. In Crore)'). Name wins when both are present."""
    for text, source in ((str(name), "column name"), (banner_hints or "", "sheet banner")):
        for pattern, unit, scale in _UNIT_PATTERNS:
            if pattern.search(text):
                return {"unit": unit, "scale_to_base": scale, "source": source}
    return None


def _geo_hit_rate(series: pd.Series) -> float:
    """Share of values matching a bundled boundary name (states or districts).
    Zero when the boundary files are unavailable - never raises."""
    try:
        from engine.query.geo import _norm, boundary_names
    except Exception:
        return 0.0
    cells = _cells(series, 120)
    if not cells:
        return 0.0
    known: set[str] = set()
    for level in ("states", "districts"):
        try:
            known |= {_norm(n) for n in boundary_names(level)}
        except Exception:
            continue
    if not known:
        return 0.0
    hits = sum(1 for c in cells if _norm(c) in known)
    return hits / len(cells)


# ------------------------------------------------------------ column profile

def profile_column(df: pd.DataFrame, col: Any, banner_hints: str = "") -> dict[str, Any]:
    series = df[col]
    name = str(col)
    nname = norm_name(name)
    n = len(series)
    sentinels = detect_missing_sentinels(series)
    blank_mask = series.isna() | series.astype(str).str.strip().str.lower().isin(MISSING_TOKENS)
    missing_pct = round(100 * float(blank_mask.mean()), 1) if n else 100.0
    distinct = int(series[~blank_mask].nunique(dropna=True))
    fmt = detect_number_format(series)
    period = detect_period_column(series, name)
    boolean = detect_boolean(series)
    unit = detect_unit(name, banner_hints)
    geo_rate = 0.0

    # ---- type decision, with the evidence that drove it
    if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
        dtype, conf, why = "number", 0.99, "already numeric in the file"
    elif boolean:
        dtype, conf, why = "boolean", 0.9, "only yes/no style values"
    elif period:
        dtype, conf, why = "period", 0.9, f"{period['coverage_pct']}% parse as {period['kind']}"
    elif fmt["parseable_pct"] >= 80:
        dtype, conf = "number", 0.85
        extras = [k for k in ("indian_grouping", "currency", "footnotes", "percent",
                              "accounting_negatives") if fmt.get(k)]
        why = (f"{fmt['parseable_pct']}% parse as numbers"
               + (f" once {', '.join(e.replace('_', ' ') for e in extras)} are handled" if extras else ""))
    elif distinct <= max(2, min(60, int(0.2 * max(n, 1)))):
        dtype, conf, why = "category", 0.8, f"{distinct} repeated values"
    else:
        dtype, conf, why = "text", 0.7, "free text"

    # ---- role decision
    unique_rate = distinct / max(1, int((~blank_mask).sum()))
    if dtype == "period":
        role = "period"
    elif dtype == "boolean":
        role = "flag"
    else:
        geo_rate = _geo_hit_rate(series) if dtype in ("category", "text") else 0.0
        if geo_rate >= 0.6 or (any(h in nname for h in _GEO_HINTS) and dtype != "number"):
            role = "geography"
        elif unique_rate > 0.95 and (dtype in ("text", "category")
                                     or any(nname == h or nname.endswith("_" + h)
                                            for h in _ID_HINTS)):
            role = "identifier"
        elif dtype == "number":
            role = "identifier" if (unique_rate > 0.98 and any(
                nname == h or nname.endswith("_" + h) for h in _ID_HINTS)) else "measure"
        else:
            role = "dimension"

    is_pct = any(h in nname for h in _PCT_HINTS) or fmt.get("percent")
    if unit is None and is_pct:
        unit = {"unit": "percent", "scale_to_base": 1.0, "source": "column name"}
    if unit is None and dtype == "number" and _CURRENCY_HINT.search(name):
        unit = {"unit": "currency", "scale_to_base": 1.0, "source": "column name"}

    prof: dict[str, Any] = {
        "source_name": name,
        "suggested_name": nname,
        "dtype": dtype,
        "dtype_confidence": conf,
        "dtype_evidence": why,
        "role": role,
        "unit": unit,
        "missing_pct": missing_pct,
        "missing_sentinels": sentinels,
        "distinct": distinct,
        "unique_rate": round(unique_rate, 3),
        "number_format": fmt if dtype in ("number", "text", "category") else None,
        "period": period,
        "boolean": boolean,
        "quality": [],
    }

    # ---- quality flags (things a human should look at)
    q = prof["quality"]
    if missing_pct >= 50:
        q.append({"kind": "mostly_empty", "detail": f"{missing_pct}% of rows have no value"})
    if distinct <= 1 and n:
        q.append({"kind": "constant", "detail": "every row holds the same value"})
    if fmt.get("footnotes"):
        q.append({"kind": "footnote_marks", "detail": "some values carry * or # marks"})
    if fmt.get("indian_grouping"):
        q.append({"kind": "indian_grouping", "detail": "digits grouped Indian style (1,23,456)"})
    if sentinels:
        q.append({"kind": "missing_sentinels",
                  "detail": "blanks written as " + ", ".join(f"'{s}'" for s in sentinels[:4])})
    if dtype == "number" and pd.api.types.is_numeric_dtype(series):
        num = pd.to_numeric(series, errors="coerce")
        if role == "measure" and (num < 0).any() and not _CURRENCY_HINT.search(name):
            q.append({"kind": "negatives", "detail": f"{int((num < 0).sum())} negative value(s)"})
        if is_pct and (num > 100).any():
            q.append({"kind": "pct_over_100", "detail": "percentage values above 100"})
    return prof


# ------------------------------------------------------------- table profile

def grain_candidates(df: pd.DataFrame, profiles: list[dict[str, Any]],
                     max_combo: int = 2) -> list[dict[str, Any]]:
    """Which column (or pair) uniquely identifies a row - what one row STANDS
    FOR. Single columns first, then pairs of key-ish columns."""
    n = len(df)
    if n == 0:
        return []
    keyish = [p for p in profiles
              if p["role"] in ("identifier", "geography", "dimension", "period")
              and p["distinct"] > 1]
    out: list[dict[str, Any]] = []
    for p in keyish:
        col = p["source_name"]
        if df[col].nunique(dropna=False) == n:
            out.append({"columns": [col], "unique": True, "coverage": 1.0})
    if not out and max_combo >= 2:
        for i, a in enumerate(keyish):
            for b in keyish[i + 1:]:
                try:
                    u = df[[a["source_name"], b["source_name"]]].drop_duplicates().shape[0]
                except Exception:
                    continue
                if u == n:
                    out.append({"columns": [a["source_name"], b["source_name"]],
                                "unique": True, "coverage": 1.0})
                if len(out) >= 3:
                    break
            if len(out) >= 3:
                break
    # Near-misses are worth showing: they usually mean duplicates exist.
    if not out and keyish:
        best = max(keyish, key=lambda p: p["distinct"])
        out.append({"columns": [best["source_name"]], "unique": False,
                    "coverage": round(best["distinct"] / n, 3)})
    return out[:4]


def _split_tokens(name: str) -> list[str]:
    return [t for t in re.split(r"[\s_\-/.]+", str(name).strip()) if t]


def detect_wide_blocks(columns: list[str]) -> dict[str, Any] | None:
    """Find columns that repeat a set of measures across periods - the classic
    wide report ('Apr-2018 CGST', 'May-2018 CGST', ... or '2019_pop',
    '2020_pop'). Returns the pieces needed to offer a long reshape."""
    period_of: dict[str, str] = {}
    measure_of: dict[str, str] = {}
    for c in columns:
        toks = _split_tokens(c)
        if len(toks) < 2:
            continue
        # A period may span one token ('2019', 'Apr-18' when unsplit) or two
        # ('Apr' + '2021') - remember how many it ate so the remaining tokens
        # are the measure name, not a stray year.
        pidx, span, p = None, 0, None
        for i, t in enumerate(toks):
            two = parse_period(" ".join(toks[i:i + 2])) if i + 1 < len(toks) else None
            one = parse_period(t)
            if two:
                pidx, span, p = i, 2, two
                break
            if one:
                pidx, span, p = i, 1, one
                break
        if pidx is None or not p:
            continue
        rest = [t for i, t in enumerate(toks) if i < pidx or i >= pidx + span]
        if not rest:
            continue
        period_of[c] = p["label"]
        measure_of[c] = " ".join(rest)
    if len(period_of) < 4:
        # Bare-period columns ('2019', '2020', 'Apr-18') with one implied measure
        bare = {c: parse_period(c)["label"] for c in columns if parse_period(c)}
        if len(bare) >= 3:
            return {"kind": "bare_periods", "period_columns": list(bare),
                    "periods": sorted(set(bare.values())),
                    "measures": ["value"],
                    "id_columns": [c for c in columns if c not in bare]}
        return None
    # Keep only measures that recur across periods. Real reports mix a regular
    # monthly grid with one-off blocks (an annual total, a 'previous year'
    # column); those appear under a single period and would otherwise dilute
    # the grid until it stops looking like a block at all.
    all_periods = sorted(set(period_of.values()))
    per_measure: dict[str, set[str]] = {}
    for c, m in measure_of.items():
        per_measure.setdefault(m, set()).add(period_of[c])
    min_periods = max(2, int(0.5 * len(all_periods)))
    measures = sorted(m for m, ps in per_measure.items() if len(ps) >= min_periods)
    if not measures:
        return None
    block_cols = {c: p for c, p in period_of.items() if measure_of[c] in measures}
    periods = sorted(set(block_cols.values()))
    if len(periods) < 2 or len(block_cols) < 4:
        return None
    coverage = len(block_cols) / max(1, len(periods) * len(measures))
    if coverage < 0.6:
        return None
    period_of, measure_of = block_cols, {c: measure_of[c] for c in block_cols}
    return {
        "kind": "period_measure_blocks",
        "periods": periods,
        "measures": measures,
        "block_columns": period_of,
        "measure_of": measure_of,
        "id_columns": [c for c in columns if c not in period_of],
        "coverage": round(coverage, 2),
    }


def profile_table(df: pd.DataFrame, banner_hints: str = "") -> dict[str, Any]:
    """The full understanding of one table: every column, the grain, wide
    blocks, duplicates, and any table-level unit hint."""
    profiles = [profile_column(df, c, banner_hints) for c in df.columns]
    cols = [str(c) for c in df.columns]
    dup_rows = int(df.duplicated().sum()) if len(df) else 0
    table_unit = detect_unit("", banner_hints)
    return {
        "n_rows": int(len(df)),
        "n_cols": int(df.shape[1]),
        "columns": profiles,
        "grain_candidates": grain_candidates(df, profiles),
        "wide_blocks": detect_wide_blocks(cols),
        "duplicate_rows": dup_rows,
        "table_unit": table_unit,
        "banner_text": (banner_hints or "").strip()[:400] or None,
        "role_counts": {
            r: sum(1 for p in profiles if p["role"] == r)
            for r in ("identifier", "geography", "period", "dimension", "measure", "flag")
        },
    }
