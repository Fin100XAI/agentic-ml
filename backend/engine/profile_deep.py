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

# Month names as they actually appear: English long and short, and the
# Marathi and Hindi names a Maharashtra department may well use.
_MONTHS: dict[str, int] = {}
for _i, _names in enumerate([
    ("jan", "january", "जानेवारी", "जनवरी"),
    ("feb", "february", "फेब्रुवारी", "फरवरी", "फ़रवरी"),
    ("mar", "march", "मार्च"),
    ("apr", "april", "एप्रिल", "अप्रैल"),
    ("may", "मे", "मई"),
    ("jun", "june", "जून"),
    ("jul", "july", "जुलै", "जुलाई"),
    ("aug", "august", "ऑगस्ट", "अगस्त"),
    ("sep", "sept", "september", "सप्टेंबर", "सितंबर"),
    ("oct", "october", "ऑक्टोबर", "अक्टूबर"),
    ("nov", "november", "नोव्हेंबर", "नवंबर"),
    ("dec", "december", "डिसेंबर", "दिसंबर"),
], start=1):
    for _n in _names:
        _MONTHS[_n] = _i

_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))
_SEP = r"[\s\-/.,'’_]+"
# Optional separator: _SEP already ends in +, so a bare '?' would make
# it lazy rather than optional.
_SEPQ = rf"(?:{_SEP})?"
# Fiscal year: FY2025-26, 2025-26, F.Y. 2025/2026. The second part must be
# the year AFTER the first - without that check '2025-06' (June) is read as
# a fiscal year, which is how a monthly column became a year column.
_FY = re.compile(rf"^(?:f\.?\s*y\.?{_SEPQ})?((?:19|20)\d{{2}}){_SEP}((?:19|20)?\d{{1,2}})$", re.I)
_FY_SHORT = re.compile(rf"^f\.?\s*y\.?{_SEPQ}((?:19|20)?\d{{2}})$", re.I)
_MONTH_YEAR = re.compile(rf"^({_MONTH_ALT})[a-z]*{_SEPQ}((?:19|20)?\d{{2}})$", re.I)
_YEAR_MONTH = re.compile(rf"^((?:19|20)\d{{2}}){_SEP}({_MONTH_ALT})[a-z]*$", re.I)
_NUM_MONTH_YEAR = re.compile(rf"^(0?[1-9]|1[0-2]){_SEP}((?:19|20)\d{{2}})$")
_YEAR_NUM_MONTH = re.compile(rf"^((?:19|20)\d{{2}}){_SEP}(0?[1-9]|1[0-2])$")
_QUARTER = re.compile(
    rf"^(?:q|quarter{_SEPQ})([1-4])(?:{_SEPQ}(?:f\.?y\.?)?{_SEPQ}((?:19|20)?\d{{2}}))?$", re.I)
_QUARTER_ORD = re.compile(
    rf"^([1-4])(?:st|nd|rd|th){_SEP}quarter{_SEP}(?:f\.?y\.?)?{_SEPQ}((?:19|20)?\d{{2}})$", re.I)
_QUARTER_TAIL = re.compile(rf"^((?:19|20)\d{{2}}){_SEPQ}q([1-4])$", re.I)
_HALF = re.compile(rf"^h([12]){_SEPQ}(?:f\.?y\.?)?{_SEPQ}((?:19|20)?\d{{2}})$", re.I)
_WEEK = re.compile(rf"^(?:w|wk|week){_SEPQ}(\d{{1,2}}){_SEP}((?:19|20)\d{{2}})$", re.I)
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


# Abbreviations a government column header actually uses. Kept deliberately
# short and unambiguous - a wrong expansion is worse than none.
_HEADER_ABBREV = {
    "hh": "households", "hhs": "households", "pop": "population",
    "popn": "population", "lit": "literacy", "amt": "amount",
    "qty": "quantity", "avg": "average", "tot": "total", "no": "number",
    "nos": "number", "cnt": "count", "yr": "year", "mth": "month",
    "dept": "department", "dist": "district", "distt": "district",
    "blk": "block", "vill": "village", "sc": "scheduled caste",
    "st": "scheduled tribe", "obc": "other backward classes",
    "bpl": "below poverty line", "cgst": "CGST", "sgst": "SGST",
    "igst": "IGST", "cess": "cess", "gst": "GST", "fy": "financial year",
    "ry": "revenue year", "m": "male", "f": "female", "t": "total",
    "pct": "percent", "perc": "percent", "rs": "rupees", "cr": "crore",
    "lac": "lakh", "lakhs": "lakh", "reg": "registered", "benef": "beneficiary",
    "benfy": "beneficiary", "wrk": "worker", "emp": "employment",
}
_NOISE_WORDS = {"col", "column", "field", "value", "data", "unnamed"}


def humanize_header(name: str) -> str:
    """A cryptic header read as a person would say it.

    'financial_year_2018_19_total' -> 'Total, FY2018-19'
    'HH_pop_2011'                  -> 'Households population, 2011'
    'apr_18_cgst'                  -> 'CGST, Apr-2018'
    Any period buried in the name is lifted out and put at the end, because
    that is where a person naturally says it.
    """
    raw = str(name).strip()
    if not raw:
        return "Column"
    tokens = [t for t in re.split(r"[\s_\-/.]+", raw) if t]
    # Pull out a period spanning up to three adjacent tokens, LONGEST first:
    # 'fy 2024 25' is FY2024-25, not 'fy 2024' (FY2023-24) with a stray 25.
    period, rest, i = None, [], 0
    while i < len(tokens):
        if period is None:
            hit = None
            for span in (3, 2, 1):
                if i + span > len(tokens):
                    continue
                cand = parse_period(" ".join(tokens[i:i + span]))
                if cand:
                    hit = (cand, span)
                    break
            if hit:
                period, i = hit[0], i + hit[1]
                continue
        rest.append(tokens[i])
        i += 1
    # Once the period is lifted out, the words that merely NAME a period
    # ('financial', 'year') are redundant - the period itself says it.
    redundant = {"financial", "fiscal", "year", "yr", "fy", "month", "mth",
                 "quarter", "qtr", "week", "period", "as", "on", "of", "for"}
    words: list[str] = []
    for t in rest:
        low = t.lower()
        if low in _NOISE_WORDS:
            continue
        if period and low in redundant:
            continue
        words.append(_HEADER_ABBREV.get(low, t))
    if not words or all(w.isdigit() for w in words):
        # nothing but noise or a bare position ('unnamed_3') - say so honestly
        digits = [w for w in words if w.isdigit()]
        if digits:
            return f"Column {digits[0]}"
        return period["label"] if period else "Column"
    label = " ".join(words).strip()
    # keep deliberate casing (CGST), sentence-case anything else
    if label and label[0].islower():
        label = label[0].upper() + label[1:]
    if period:
        label = f"{label}, {period['label']}"
    return re.sub(r"\s+", " ", label).strip(" ,")


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


def _yr(v: str | int) -> int:
    """Two-digit years belong to this century unless that is absurd."""
    y = int(v)
    if y < 100:
        y = 2000 + y if y < 70 else 1900 + y
    return y


def _month_label(year: int, month: int) -> dict[str, Any]:
    ts = pd.Timestamp(year=year, month=month, day=1)
    return {"kind": "month", "key": ts.strftime("%Y-%m"), "label": ts.strftime("%b-%Y")}


def parse_period(raw: Any) -> dict[str, Any] | None:
    """Recognize a period however it is written.

    Handles month-year in either order and in any separator ('Jun-2025',
    'July 2026', '2026 July', 'july/2026', "Jun'25", '06/2025', '2025-06'),
    Indian fiscal years ('2025-26', 'FY2025-26', 'FY25'), quarters ('Q1
    2025', '1st Quarter 2025', 'Q1 FY25', '2025Q1'), halves, weeks, bare
    years, and full dates - plus Marathi and Hindi month names.
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    if isinstance(raw, (pd.Timestamp, _dt.datetime, _dt.date)):
        ts = pd.Timestamp(raw)
        return {"kind": "date", "key": ts.strftime("%Y-%m-%d"),
                "label": ts.strftime("%b-%Y")}
    s = str(raw).strip()
    if not s or s.lower() in MISSING_TOKENS:
        return None

    # Fiscal year - only when the second part really is the following year.
    m = _FY.match(s)
    if m:
        start = int(m.group(1))
        nxt = _yr(m.group(2)) if len(m.group(2)) == 4 else None
        two = int(m.group(2)) % 100
        if (nxt == start + 1) or (nxt is None and two == (start + 1) % 100):
            return {"kind": "fiscal_year", "key": str(start),
                    "label": f"FY{start}-{str(start + 1)[-2:]}"}
    m = _FY_SHORT.match(s)
    if m:
        y = _yr(m.group(1))
        return {"kind": "fiscal_year", "key": str(y - 1),
                "label": f"FY{y - 1}-{str(y)[-2:]}"}

    # Month and year, in either order, named or numeric.
    for pat, mi, yi in ((_MONTH_YEAR, 1, 2), (_YEAR_MONTH, 2, 1)):
        m = pat.match(s)
        if m:
            month = _MONTHS.get(m.group(mi).lower()[:12]) or \
                _MONTHS.get(m.group(mi).lower()[:3])
            if month:
                return _month_label(_yr(m.group(yi)), month)
    for pat, mi, yi in ((_NUM_MONTH_YEAR, 1, 2), (_YEAR_NUM_MONTH, 2, 1)):
        m = pat.match(s)
        if m:
            return _month_label(int(m.group(yi)), int(m.group(mi)))

    # Quarters, halves, weeks.
    for pat, qi, yi in ((_QUARTER, 1, 2), (_QUARTER_ORD, 1, 2), (_QUARTER_TAIL, 2, 1)):
        m = pat.match(s)
        if m:
            q = int(m.group(qi))
            yr = m.group(yi)
            if not yr:
                return {"kind": "quarter", "key": f"Q{q}", "label": f"Q{q}"}
            y = _yr(yr)
            return {"kind": "quarter", "key": f"{y}-Q{q}", "label": f"Q{q} {y}"}
    m = _HALF.match(s)
    if m:
        y = _yr(m.group(2))
        return {"kind": "half", "key": f"{y}-H{m.group(1)}", "label": f"H{m.group(1)} {y}"}
    m = _WEEK.match(s)
    if m:
        y, w = int(m.group(2)), int(m.group(1))
        if 1 <= w <= 53:
            return {"kind": "week", "key": f"{y}-W{w:02d}", "label": f"Week {w} {y}"}

    if _BARE_YEAR.match(s):
        y = int(s)
        if 1900 <= y <= 2100:
            return {"kind": "year", "key": s, "label": s}

    # Anything else that is genuinely a date.
    try:
        ts = pd.to_datetime(s, errors="raise", format="mixed", dayfirst=True)
        if pd.notna(ts) and 1900 <= ts.year <= 2100:
            return {"kind": "date", "key": ts.strftime("%Y-%m-%d"),
                    "label": ts.strftime("%d-%b-%Y")}
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
        "label": humanize_header(name),
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
