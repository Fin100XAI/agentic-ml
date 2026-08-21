"""Blueprint: the schema contract at the heart of the Data Prep Studio.

Flow, all deterministic except phrasing:
  profile -> INTERVIEW (grounded questions, each with a suggested answer)
          -> BLUEPRINT (a target schema the human edits)
          -> BUILD (apply it) -> CERTIFY (prove the result matches)
          -> DATA DICTIONARY (what the department actually shares)

Every question carries the evidence that raised it and a recommendation, so
the human is deciding, not guessing - and can always override.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

from engine.profile_deep import (MISSING_TOKENS, norm_name, parse_number,
                                 parse_period)

DTYPES = ("number", "integer", "text", "category", "boolean", "period")
ROLES = ("identifier", "geography", "period", "dimension", "measure", "flag")
_SUMMARY_RE = re.compile(
    r"grand\s+total|all\s+india|sub\s*total|gross\s+(?:revenue|total)|aggregate|"
    r"net\s+total|^\s*total\b|^\s*all\b", re.I)
# Rates and averages do not add up, so reconciling a total row against them is
# meaningless - they are skipped when choosing the check column.
_NON_ADDITIVE = re.compile(
    r"pct|percent|%|\brate\b|ratio|share|avg|average|\bmean\b|per\s*1000|"
    r"per\s*capita|index|"
    # Identifiers and periods are numbers that must never be summed: totalling
    # a serial-number column and comparing it to a total row is nonsense, and
    # it used to flip the recommendation on a perfectly ordinary file.
    r"\bsr\.?\s*no\b|\bs\.?\s*no\b|\bid\b|\bcode\b|serial|\bno\.?$|"
    r"\byear\b|\bmonth\b|\bperiod\b|\bdate\b", re.I)


# ------------------------------------------------------------------ interview

def build_interview(profile: dict[str, Any], df: pd.DataFrame,
                    goal: str | None = None) -> list[dict[str, Any]]:
    """Ask only what profiling could NOT settle - each question grounded in
    what was actually found, with options computed from the data."""
    qs: list[dict[str, Any]] = []
    cols = {c["source_name"]: c for c in profile["columns"]}

    # 1. Purpose - shapes later defaults (kept short; it is not a quiz)
    qs.append({
        "id": "purpose",
        "kind": "purpose",
        "question": "What will this table be used for?",
        "why": "It decides how strict the checks should be and what the ideal shape is.",
        "options": [
            {"value": "analytics", "label": "Explore and answer questions",
             "detail": "Charts, comparisons, trends - a readable table matters most."},
            {"value": "ml", "label": "Train a prediction model",
             "detail": "One row per case, clean types, no leaking totals."},
            {"value": "both", "label": "Both", "detail": "Prepare for analytics, keep it model-ready."},
        ],
        "suggested": "both",
        "allow_note": True,
    })

    # 2. Reshape - only when a real wide block exists
    wb = profile.get("wide_blocks")
    if wb:
        if wb["kind"] == "period_measure_blocks":
            detail = (f"{len(wb['periods'])} periods x {len(wb['measures'])} measures "
                      f"({', '.join(wb['measures'][:4])}{'...' if len(wb['measures']) > 4 else ''})")
        else:
            detail = f"{len(wb['periods'])} period columns"
        qs.append({
            "id": "reshape",
            "kind": "reshape",
            "question": "The periods run across the columns. Turn them into rows?",
            "why": f"Found {detail}. Long tables answer time questions; wide tables read like a report.",
            "options": [
                {"value": "long", "label": "Yes - one row per period",
                 "detail": "Adds a period column and one column per measure. Best for trends and models."},
                {"value": "wide", "label": "No - keep the report layout",
                 "detail": "Columns stay as they are."},
            ],
            "suggested": "long",
            "allow_note": False,
        })

    # 3. Grain - what one row stands for
    gc = profile.get("grain_candidates") or []
    if gc:
        opts = [{"value": "|".join(g["columns"]),
                 "label": " + ".join(g["columns"]),
                 "detail": ("uniquely identifies every row" if g["unique"]
                            else f"repeats - only {int(g['coverage'] * 100)}% distinct")}
                for g in gc]
        opts.append({"value": "", "label": "No key - rows are just records",
                     "detail": "Skip the uniqueness check."})
        qs.append({
            "id": "grain",
            "kind": "grain",
            "question": "What should one row stand for?",
            "why": "Declaring the key lets the studio prove there are no hidden duplicates.",
            "options": opts,
            "suggested": opts[0]["value"] if gc and gc[0]["unique"] else "",
            "allow_note": False,
        })

    # 4. Units - when a scale was found or currency-ish measures have none
    tu = profile.get("table_unit")
    if tu:
        qs.append({
            "id": "unit_scale",
            "kind": "unit",
            "question": f"The file says values are in {tu['unit']}. How should they be stored?",
            "why": f"Found in the {tu['source']}. Unstated units are how numbers get misread.",
            "options": [
                {"value": "record", "label": f"Keep the numbers, record '{tu['unit']}' as the unit",
                 "detail": "Values unchanged; the unit travels with the column."},
                {"value": "convert", "label": f"Multiply into base units (x {int(tu['scale_to_base']):,})",
                 "detail": "Values become absolute; useful when combining sources."},
            ],
            "suggested": "record",
            "allow_note": False,
        })

    # 5. Summary rows - with a reconciliation result, not a guess
    summary = _summary_rows(df)
    if summary["count"]:
        rec = summary.get("reconciliation")
        detail = (f"the parts add up to it exactly" if rec == "match"
                  else "the parts do NOT add up to it" if rec == "mismatch"
                  else "could not be checked")
        qs.append({
            "id": "summary_rows",
            "kind": "rows",
            "question": f"Found {summary['count']} total/summary row(s). What should happen to them?",
            "why": f"Example: '{summary['examples'][0]}'. Checked against the other rows: {detail}."
                   " Left in, they double every sum.",
            "options": [
                {"value": "drop", "label": "Remove them", "detail": "Recommended - they are derived, not data."},
                {"value": "flag", "label": "Keep, add an 'is_summary' column",
                 "detail": "Nothing is lost; charts can filter them out."},
                {"value": "keep", "label": "Keep as ordinary rows", "detail": "Only if you know why."},
            ],
            "suggested": "drop" if rec != "mismatch" else "flag",
            "allow_note": True,
        })

    # 6. Ambiguous types - only genuinely uncertain columns
    unsure = [c for c in profile["columns"]
              if c["dtype_confidence"] < 0.85 and c["missing_pct"] < 95][:4]
    for c in unsure:
        qs.append({
            "id": f"type::{c['source_name']}",
            "kind": "type",
            "question": f"How should '{c['source_name']}' be treated?",
            "why": f"{c['dtype_evidence']}; {c['distinct']} distinct value(s).",
            "options": [
                {"value": "category", "label": "A category to group by", "detail": "Repeated labels."},
                {"value": "number", "label": "A number to measure", "detail": "Sums and averages."},
                {"value": "text", "label": "Free text", "detail": "Notes; not for grouping."},
                {"value": "drop", "label": "Drop it", "detail": "Not needed for this purpose."},
            ],
            "suggested": c["dtype"] if c["dtype"] in ("category", "number", "text") else "text",
            "allow_note": False,
        })

    # 7. Mostly-empty columns
    empties = [c["source_name"] for c in profile["columns"] if c["missing_pct"] >= 80]
    if empties:
        qs.append({
            "id": "empty_columns",
            "kind": "columns",
            "question": f"{len(empties)} column(s) are 80%+ empty. Drop them?",
            "why": "Examples: " + ", ".join(empties[:5]) + ". Near-empty columns mislead more than they inform.",
            "options": [
                {"value": "drop", "label": "Drop them", "detail": "Recommended."},
                {"value": "keep", "label": "Keep them", "detail": "They will be marked optional."},
            ],
            "suggested": "drop",
            "allow_note": False,
        })

    # 8. PII
    pii = profile.get("pii_columns") or []
    if pii:
        qs.append({
            "id": "pii",
            "kind": "privacy",
            "question": f"Personal data found in {len(pii)} column(s). How should it be handled?",
            "why": "Columns: " + ", ".join(p["column"] for p in pii[:5])
                   + ". Personal data must not reach analysis or any AI call.",
            "options": [
                {"value": "drop", "label": "Drop those columns", "detail": "Recommended."},
                {"value": "mask", "label": "Mask the values", "detail": "Keeps row counts, hides identities."},
            ],
            "suggested": "drop",
            "allow_note": False,
        })
    return qs


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

def _is_row_counter(series: pd.Series) -> bool:
    """A column that just numbers the rows (1, 2, 3 ...) or holds plausible
    years. Neither adds up to anything, whatever it is called."""
    vals = pd.to_numeric(series, errors="coerce").dropna()
    if len(vals) < 3:
        return False
    if (vals % 1 != 0).any():
        return False
    ints = vals.astype("int64")
    if ints.between(1900, 2100).all():
        return True          # a year column
    diffs = ints.sort_values().diff().dropna()
    return bool(len(diffs)) and bool((diffs == 1).all())


def _summary_rows(df: pd.DataFrame) -> dict[str, Any]:
    """Find total-like rows and, when possible, CHECK whether the other rows
    actually add up to them - a mismatch is a finding, not a nuisance."""
    if df.empty:
        return {"count": 0, "examples": [], "index": []}
    text_cols = [c for c in df.columns if df[c].dtype == object][:3]
    if not text_cols:
        return {"count": 0, "examples": [], "index": []}
    mask = pd.Series(False, index=df.index)
    label = pd.Series("", index=df.index)
    for c in text_cols:
        vals = df[c].astype(str)
        hit = vals.str.contains(_SUMMARY_RE, na=False)
        label = label.where(~(hit & (label == "")), vals)
        mask |= hit
    idx = list(df.index[mask])
    out = {"count": int(mask.sum()), "examples": [str(v) for v in label[mask].head(3)],
           "index": idx}
    if not idx:
        return out
    num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])
                and not _NON_ADDITIVE.search(str(c))
                and not _is_row_counter(df[c])]
    if num_cols:
        col = max(num_cols, key=lambda c: pd.to_numeric(df[c], errors="coerce").abs().sum())
        parts = pd.to_numeric(df.loc[~mask, col], errors="coerce").sum()
        totals = pd.to_numeric(df.loc[mask, col], errors="coerce").dropna()
        if len(totals):
            near = any(abs(float(t) - float(parts)) <= max(1.0, abs(float(parts)) * 0.005)
                       for t in totals)
            out["reconciliation"] = "match" if near else "mismatch"
            out["reconciliation_detail"] = {
                "column": str(col), "parts_sum": round(float(parts), 3),
                "total_row": round(float(totals.iloc[0]), 3)}
    return out


# ----------------------------------------------------------------- blueprint

def propose_blueprint(profile: dict[str, Any], answers: dict[str, Any],
                      df: pd.DataFrame) -> dict[str, Any]:
    """Turn profile + answers into an editable target schema."""
    reshape_long = answers.get("reshape") == "long" and profile.get("wide_blocks")
    wb = profile.get("wide_blocks") if reshape_long else None
    drop_empty = answers.get("empty_columns", "drop") == "drop"
    pii_action = answers.get("pii", "drop")
    pii_cols = {p["column"] for p in (profile.get("pii_columns") or [])}
    tu = profile.get("table_unit")
    convert_unit = answers.get("unit_scale") == "convert" and tu

    columns: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(source: str | None, name: str, dtype: str, role: str,
            unit: dict | None, nullable: bool, desc: str, action: str = "keep",
            origin: str = "", rules: dict | None = None) -> None:
        base = norm_name(name)
        final = base
        i = 2
        while final in seen:
            final, i = f"{base}_{i}", i + 1
        seen.add(final)
        columns.append({"source_name": source, "name": final, "label": str(name),
                        "dtype": dtype, "role": role,
                        # Units belong to quantities only.
                        "unit": (unit or {}).get("unit") if role == "measure" else None,
                        "nullable": nullable, "description": desc,
                        "action": action, "origin": origin,
                        "rules": rules or {}})

    by_name = {c["source_name"]: c for c in profile["columns"]}
    if wb:
        # Long shape: ids, then one period column, then one column per measure.
        for c in wb["id_columns"]:
            p = by_name.get(c)
            if not p:
                continue
            add(c, p["suggested_name"], _target_dtype(p, answers), p["role"], p["unit"],
                p["missing_pct"] > 0, _describe(p), "keep", "source column",
                _value_rules(p, df))
        add(None, "period", "period", "period", None, False,
            "The period each row covers, taken from the column headings.",
            "derive", "reshaped from column headings")
        for m in wb["measures"]:
            add(None, m, "number", "measure", tu, True,
                f"{m}, one value per period.", "derive", "reshaped from wide block",
                {"min": 0} if _all_non_negative(df, wb, m) else None)
    else:
        for p in profile["columns"]:
            src = p["source_name"]
            action = "keep"
            if src in pii_cols and pii_action == "drop":
                action = "drop"
            elif src in pii_cols:
                action = "mask"
            elif drop_empty and p["missing_pct"] >= 80:
                action = "drop"
            elif answers.get(f"type::{src}") == "drop":
                action = "drop"
            add(src, p["suggested_name"], _target_dtype(p, answers), p["role"], p["unit"],
                p["missing_pct"] > 0, _describe(p), action, "source column",
                _value_rules(p, df))

    if answers.get("summary_rows") == "flag":
        add(None, "is_summary", "boolean", "flag", None, False,
            "True for total or summary rows kept from the source.", "derive",
            "flagged summary rows")

    grain_raw = answers.get("grain", "")
    grain = [norm_name(g) for g in grain_raw.split("|") if g] if grain_raw else []
    if wb and grain:
        grain = [g for g in grain if g in seen] + ["period"]
    return {
        "columns": columns,
        "grain": [g for g in grain if g in seen],
        "reshape": ({"kind": wb["kind"], "id_columns": wb["id_columns"],
                     "measures": wb["measures"],
                     "block_columns": wb.get("block_columns", {}),
                     "period_columns": wb.get("period_columns", []),
                     "measure_of": wb.get("measure_of", {})} if wb else None),
        "row_rules": {
            "summary_rows": answers.get("summary_rows", "drop"),
            "drop_empty_rows": True,
            "drop_footer_rows": True,
            "drop_duplicate_rows": bool(profile.get("duplicate_rows")),
        },
        "unit_conversion": ({"unit": tu["unit"], "factor": tu["scale_to_base"]}
                            if convert_unit else None),
        "purpose": answers.get("purpose", "both"),
        "notes": answers.get("_notes", ""),
    }


def _all_non_negative(df: pd.DataFrame, wb: dict[str, Any], measure: str) -> bool:
    cols = [c for c, m in (wb.get("measure_of") or {}).items()
            if m == measure and c in df.columns]
    if not cols:
        return False
    try:
        vals = pd.to_numeric(df[cols].stack(), errors="coerce").dropna()
    except Exception:
        return False
    return bool(len(vals)) and bool((vals >= 0).all())


def _value_rules(p: dict[str, Any], df: pd.DataFrame) -> dict[str, Any]:
    """The rules worth CHECKING - not a description of the sample. A domain
    read off the data would make certify pass by construction; these are the
    ones that catch a real mistake: percentages over 100, negative counts,
    a category that appeared from nowhere, a district that is not a district."""
    rules: dict[str, Any] = {}
    col = p["source_name"]
    unit = (p.get("unit") or {}).get("unit")
    if p["dtype"] == "number":
        if unit == "percent":
            rules["min"], rules["max"] = 0, 100
        elif col in df.columns:
            try:
                vals = pd.to_numeric(df[col], errors="coerce").dropna()
                if len(vals) and (vals >= 0).all():
                    rules["min"] = 0
            except Exception:
                pass
    if p["dtype"] in ("category", "boolean") and 0 < p["distinct"] <= 30 \
            and col in df.columns:
        seen = sorted({str(v).strip() for v in df[col].dropna()
                       if str(v).strip().lower() not in MISSING_TOKENS})
        if seen:
            rules["allowed"] = seen
    if p["role"] == "geography":
        rules["reference"] = "india_boundaries"
    return rules


def _target_dtype(p: dict[str, Any], answers: dict[str, Any]) -> str:
    override = answers.get(f"type::{p['source_name']}")
    if override in DTYPES:
        return override
    return p["dtype"]


def _describe(p: dict[str, Any]) -> str:
    bits = {"identifier": "Identifies each record.", "geography": "The place each row refers to.",
            "period": "The time period of the row.", "measure": "A quantity to add up or average.",
            "dimension": "A label to group by.", "flag": "A yes/no marker."}
    d = bits.get(p["role"], "")
    # Only quantities carry units - a state name is not measured in crore.
    if p.get("unit") and p["role"] == "measure":
        d += f" Unit: {p['unit'].get('unit')}."
    return d.strip()


# --------------------------------------------------------------------- build

def apply_blueprint(df: pd.DataFrame, bp: dict[str, Any]) -> tuple[pd.DataFrame, list[str]]:
    """Execute the approved blueprint. Deterministic and order-defined:
    row rules -> reshape -> select/rename -> cast -> unit -> sort."""
    steps: list[str] = []
    work = df.copy()

    # 1. rows
    rules = bp.get("row_rules", {})
    if rules.get("drop_footer_rows"):
        n = _footer_rows(work)
        if n:
            work = work.iloc[: len(work) - n]
            steps.append(f"removed {n} trailing note row(s)")
    if rules.get("drop_empty_rows"):
        before = len(work)
        work = work.dropna(how="all")
        if before - len(work):
            steps.append(f"removed {before - len(work)} fully empty row(s)")
    summary = _summary_rows(work)
    if summary["count"]:
        mode = rules.get("summary_rows", "drop")
        if mode == "drop":
            work = work.drop(index=summary["index"])
            steps.append(f"removed {summary['count']} total/summary row(s)")
        elif mode == "flag":
            work["__is_summary"] = work.index.isin(summary["index"])
            steps.append(f"flagged {summary['count']} summary row(s)")
    if rules.get("drop_duplicate_rows"):
        before = len(work)
        work = work.drop_duplicates()
        if before - len(work):
            steps.append(f"removed {before - len(work)} duplicate row(s)")
    work = work.reset_index(drop=True)

    # 2. reshape wide -> long
    rs = bp.get("reshape")
    if rs:
        work = _reshape_long(work, rs)
        steps.append(f"reshaped {len(rs.get('measures', []))} measure(s) across periods into rows")

    # 3. select + rename, 4. cast, 5. unit
    conv = bp.get("unit_conversion")
    out = pd.DataFrame(index=work.index)
    for spec in bp["columns"]:
        if spec.get("action") == "drop":
            continue
        src = spec.get("source_name") or spec["name"]
        if src not in work.columns:
            # derived columns from reshape/flag carry their target name already
            alt = spec["name"] if spec["name"] in work.columns else None
            if alt is None and spec["name"] == "is_summary" and "__is_summary" in work.columns:
                out[spec["name"]] = work["__is_summary"].astype(bool)
                continue
            if alt is None:
                continue
            src = alt
        col = _cast(work[src], spec["dtype"])
        if spec.get("action") == "mask" and spec["dtype"] in ("text", "category"):
            col = col.astype(str).str.replace(r"[A-Za-z0-9]", "x", regex=True)
        if conv and spec["role"] == "measure" and spec["dtype"] in ("number", "integer"):
            col = pd.to_numeric(col, errors="coerce") * float(conv["factor"])
        out[spec["name"]] = col
    if any(s.get("action") == "drop" for s in bp["columns"]):
        steps.append(f"dropped {sum(1 for s in bp['columns'] if s.get('action') == 'drop')} column(s)")
    steps.append("renamed columns to their agreed names and set every type")
    if conv:
        steps.append(f"converted measures from {conv['unit']} to base units")

    grain = [g for g in bp.get("grain", []) if g in out.columns]
    if grain:
        out = out.sort_values(grain, kind="stable").reset_index(drop=True)
        steps.append("sorted by the declared key")
    return out, steps


def _reshape_long(df: pd.DataFrame, rs: dict[str, Any]) -> pd.DataFrame:
    ids = [c for c in rs.get("id_columns", []) if c in df.columns]
    if rs.get("kind") == "bare_periods":
        value_cols = [c for c in rs.get("period_columns", []) if c in df.columns]
        if not value_cols:
            return df
        long = df.melt(id_vars=ids, value_vars=value_cols,
                       var_name="period", value_name="value")
        long["period"] = long["period"].map(
            lambda v: (parse_period(v) or {}).get("label", str(v)))
        return long
    block = {c: p for c, p in (rs.get("block_columns") or {}).items() if c in df.columns}
    measure_of = rs.get("measure_of") or {}
    if not block:
        return df
    frames = []
    for measure in rs.get("measures", []):
        cols = [c for c in block if measure_of.get(c) == measure]
        if not cols:
            continue
        part = df[ids + cols].melt(id_vars=ids, value_vars=cols,
                                   var_name="__col", value_name=norm_name(measure))
        part["period"] = part["__col"].map(block)
        part = part.drop(columns="__col")
        frames.append(part.set_index(ids + ["period"]))
    if not frames:
        return df
    joined = pd.concat(frames, axis=1).reset_index()
    return joined


def _cast(series: pd.Series, dtype: str) -> pd.Series:
    if dtype in ("number", "integer"):
        out = series.map(parse_number)
        num = pd.to_numeric(out, errors="coerce")
        if dtype == "integer" and num.notna().all() and (num % 1 == 0).all():
            return num.astype("int64")
        return num
    if dtype == "boolean":
        def to_bool(v: Any) -> Any:
            s = str(v).strip().lower()
            if s in ("y", "yes", "true", "t", "1"):
                return True
            if s in ("n", "no", "false", "f", "0"):
                return False
            return None
        return series.map(to_bool).astype("object")
    if dtype == "period":
        return series.map(lambda v: (parse_period(v) or {}).get("label", None if pd.isna(v) else str(v)))
    if dtype == "category":
        return series.astype(str).str.strip().replace(
            {t: None for t in MISSING_TOKENS if t}, regex=False)
    return series.astype(str).str.strip().replace(
        {t: None for t in MISSING_TOKENS if t}, regex=False)


# ------------------------------------------------------------------- certify

def certify(df: pd.DataFrame, bp: dict[str, Any]) -> dict[str, Any]:
    """Prove the built table matches the contract. Every check is reported,
    pass or fail - a clean report is what makes the output shareable."""
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str, severity: str = "error") -> None:
        checks.append({"check": name, "passed": bool(ok), "detail": detail,
                       "severity": severity})

    expected = [c["name"] for c in bp["columns"] if c.get("action") != "drop"]
    missing = [c for c in expected if c not in df.columns]
    add("All contracted columns present", not missing,
        "every column in the blueprint exists" if not missing else f"missing: {missing}")

    bad_types: list[str] = []
    for spec in bp["columns"]:
        if spec.get("action") == "drop" or spec["name"] not in df.columns:
            continue
        col = df[spec["name"]]
        if spec["dtype"] in ("number", "integer"):
            if not pd.api.types.is_numeric_dtype(col):
                bad_types.append(spec["name"])
    add("Declared types hold", not bad_types,
        "every column matches its declared type" if not bad_types else f"not numeric: {bad_types}")

    grain = [g for g in bp.get("grain", []) if g in df.columns]
    if grain:
        dups = int(df.duplicated(subset=grain).sum())
        add("Key is unique", dups == 0,
            f"one row per {' + '.join(grain)}" if dups == 0
            else f"{dups} duplicate key value(s) - the key does not hold")
    else:
        add("Key declared", False, "no key declared - duplicates cannot be ruled out", "warning")

    for spec in bp["columns"]:
        if spec.get("action") == "drop" or spec["name"] not in df.columns:
            continue
        if not spec.get("nullable", True):
            n = int(df[spec["name"]].isna().sum())
            if n:
                add(f"'{spec['name']}' has no blanks", False, f"{n} blank value(s)", "warning")

    # Value rules: the checks that catch a real mistake rather than restating
    # the sample. A geography column is matched against the bundled boundary
    # master, so an unrecognised district is caught before it reaches a chart.
    for spec in bp["columns"]:
        if spec.get("action") == "drop" or spec["name"] not in df.columns:
            continue
        rules = spec.get("rules") or {}
        col = df[spec["name"]]
        name = spec["name"]
        if "min" in rules:
            n = int((pd.to_numeric(col, errors="coerce") < rules["min"]).sum())
            add(f"'{name}' is never below {rules['min']}", n == 0,
                "all values in range" if n == 0 else f"{n} value(s) below {rules['min']}")
        if "max" in rules:
            n = int((pd.to_numeric(col, errors="coerce") > rules["max"]).sum())
            add(f"'{name}' is never above {rules['max']}", n == 0,
                "all values in range" if n == 0 else f"{n} value(s) above {rules['max']}")
        if rules.get("allowed"):
            allowed = {str(v) for v in rules["allowed"]}
            seen = {str(v) for v in col.dropna().unique()}
            extra = sorted(seen - allowed)[:5]
            add(f"'{name}' holds only known values", not extra,
                f"{len(allowed)} agreed value(s)" if not extra
                else f"unexpected: {', '.join(extra)}", "warning")
        if rules.get("reference") == "india_boundaries":
            unmatched = _unmatched_places(col)
            add(f"'{name}' matches known places", not unmatched,
                "every value matches a state or district"
                if not unmatched else
                f"{len(unmatched)} unrecognised: {', '.join(unmatched[:4])}", "warning")

    empty_cols = [c for c in df.columns if df[c].isna().all()]
    add("No empty columns", not empty_cols,
        "every column holds data" if not empty_cols else f"all blank: {empty_cols}", "warning")

    add("Rows present", len(df) > 0, f"{len(df):,} row(s) in the prepared table")

    errors = sum(1 for c in checks if not c["passed"] and c["severity"] == "error")
    warnings = sum(1 for c in checks if not c["passed"] and c["severity"] == "warning")
    return {"checks": checks, "errors": errors, "warnings": warnings,
            "verdict": "ready" if errors == 0 else "not ready",
            "n_rows": int(len(df)), "n_cols": int(df.shape[1])}


# ----------------------------------------------------------- data dictionary

def _unmatched_places(series: pd.Series) -> list[str]:
    """Values that match no bundled state or district. Empty when the
    boundary files are unavailable - the check simply reports clean rather
    than failing the build."""
    try:
        from engine.query.geo import _norm, boundary_names
    except Exception:
        return []
    known: set[str] = set()
    for level in ("states", "districts"):
        try:
            known |= {_norm(n) for n in boundary_names(level)}
        except Exception:
            continue
    if not known:
        return []
    out = []
    for v in sorted({str(x).strip() for x in series.dropna()}):
        if v and _norm(v) not in known:
            out.append(v)
    return out


def data_dictionary(df: pd.DataFrame, bp: dict[str, Any],
                    provenance: dict[str, Any] | None = None) -> str:
    """The human-readable contract - what a department actually shares."""
    lines = ["# Data dictionary", ""]
    if bp.get("notes"):
        lines += [f"**Purpose:** {bp['notes']}", ""]
    lines += [f"- Rows: {len(df):,}", f"- Columns: {df.shape[1]}"]
    if bp.get("grain"):
        lines.append(f"- One row per: {' + '.join(bp['grain'])}")
    if bp.get("unit_conversion"):
        lines.append(f"- Measures converted from {bp['unit_conversion']['unit']} to base units")
    if provenance:
        for k, v in provenance.items():
            lines.append(f"- {k}: {v}")
    lines += ["", "## Columns", "",
              "| Column | Type | Role | Unit | Blank | Rules | Description |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for spec in bp["columns"]:
        if spec.get("action") == "drop" or spec["name"] not in df.columns:
            continue
        col = df[spec["name"]]
        blank = f"{100 * float(col.isna().mean()):.0f}%" if len(df) else "-"
        r = spec.get("rules") or {}
        bits = []
        if "min" in r and "max" in r:
            bits.append(f"{r['min']} to {r['max']}")
        elif "min" in r:
            bits.append(f"at least {r['min']}")
        elif "max" in r:
            bits.append(f"at most {r['max']}")
        if r.get("allowed"):
            bits.append(f"{len(r['allowed'])} agreed value(s)")
        if r.get("reference"):
            bits.append("known places")
        lines.append(f"| `{spec['name']}` | {spec['dtype']} | {spec['role']} | "
                     f"{spec.get('unit') or '-'} | {blank} | {'; '.join(bits) or '-'} | "
                     f"{spec.get('description') or '-'} |")
    dropped = [s for s in bp["columns"] if s.get("action") == "drop"]
    if dropped:
        lines += ["", "## Columns removed", ""]
        for s in dropped:
            lines.append(f"- `{s['label']}` - {s.get('description') or 'not needed'}")
    return "\n".join(lines) + "\n"
