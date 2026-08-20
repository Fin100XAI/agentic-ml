"""PII screening: detect personal data per column BEFORE anything reaches an LLM.

Pure regex + heuristics (no model calls - this runs precisely so that raw
values never leave the machine). Each finding carries a confidence, the share
of matching values, and a proposed action the human approves or overrides:

- mask: replace with a redacted form that keeps analytical shape (last 4 digits,
  email domain, name initial)
- drop: remove the column entirely
- keep: leave as-is (an explicit human decision, logged as declined masking)

Indian formats are first-class: 10-digit mobiles (+91/0 prefixes), Aadhaar-like
12-digit numbers, PAN codes, 6-digit PIN codes.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

SAMPLE = 300  # values inspected per column

_EMAIL = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.]{2,}$")
_PHONE_IN = re.compile(r"^(?:\+?91[\-\s]?|0)?[6-9]\d{9}$")
_AADHAAR = re.compile(r"^\d{4}[\s-]?\d{4}[\s-]?\d{4}$")
_PAN = re.compile(r"^[A-Z]{5}\d{4}[A-Z]$")
_PIN = re.compile(r"^[1-9]\d{5}$")
_ACCOUNT = re.compile(r"^\d{9,18}$")
_STREET_WORDS = (
    "road", "street", "st.", "nagar", "colony", "lane", "sector", "block",
    "apartment", "apt", "house", "floor", "cross", "main", "layout", "phase",
)
_NAME_HINTS = ("name", "customer", "person", "holder", "applicant", "beneficiary", "father", "spouse")
_ACCOUNT_HINTS = ("account", "acct", "acc_no", "iban", "card")
_PIN_HINTS = ("pin", "zip", "postal")


def _match_share(values: pd.Series, pattern: re.Pattern) -> float:
    s = values.astype(str).str.strip()
    # A numeric column with even one blank becomes float64, so phone and ID
    # numbers stringify as '9876543210.0' and dodge the patterns - strip the
    # float tail before matching or such columns slip past the screen.
    s = s.str.replace(r"\.0$", "", regex=True)
    if len(s) == 0:
        return 0.0
    return float(s.str.fullmatch(pattern).mean())


def _looks_like_names(values: pd.Series, col_name: str) -> float:
    s = values.astype(str).str.strip()
    if len(s) == 0 or s.nunique() / len(s) < 0.3:
        return 0.0
    words = s.str.split()
    word_counts = words.str.len()
    capitalized = words.apply(
        lambda ws: all(w[:1].isalpha() and w[:1] == w[:1].upper() for w in ws) if ws else False
    )
    shape_score = float(((word_counts.between(2, 4)) & capitalized).mean())
    hint = any(h in col_name.lower() for h in _NAME_HINTS)
    if shape_score > 0.7 and hint:
        return 0.9
    if shape_score > 0.8:
        return 0.6
    return 0.0


def _looks_like_address(values: pd.Series) -> float:
    s = values.astype(str).str.strip()
    if len(s) == 0:
        return 0.0
    long_enough = s.str.len() > 25
    has_digit = s.str.contains(r"\d", regex=True)
    has_street = s.str.lower().str.contains("|".join(re.escape(w) for w in _STREET_WORDS))
    return float((long_enough & has_digit & has_street).mean())


def detect_pii(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Return per-column PII findings with proposed actions."""
    findings: list[dict[str, Any]] = []
    for col in df.columns:
        values = df[col].dropna().head(SAMPLE)
        if len(values) < 5:
            continue
        name = str(col)
        lower = name.lower()

        checks: list[tuple[str, float, str]] = []  # (kind, share, action)
        share = _match_share(values, _EMAIL)
        if share > 0.5:
            checks.append(("email", share, "mask"))
        share = _match_share(values, _PHONE_IN)
        if share > 0.5:
            checks.append(("phone", share, "mask"))
        share = _match_share(values, _PAN)
        if share > 0.5:
            checks.append(("pan", share, "mask"))
        share = _match_share(values, _AADHAAR)
        if share > 0.5 and not any(k == "phone" for k, _, _ in checks):
            checks.append(("aadhaar", share, "mask"))
        share = _match_share(values, _PIN)
        if share > 0.6 and any(h in lower for h in _PIN_HINTS):
            checks.append(("pincode", share, "keep"))
        share = _match_share(values, _ACCOUNT)
        if share > 0.5 and any(h in lower for h in _ACCOUNT_HINTS) and not checks:
            checks.append(("account_number", share, "mask"))
        if not checks and values.dtype == object:
            score = _looks_like_names(values, name)
            if score > 0:
                checks.append(("person_name", score, "mask"))
            elif (score := _looks_like_address(values)) > 0.5:
                checks.append(("address", score, "drop"))

        if not checks:
            continue
        kind, confidence, action = max(checks, key=lambda c: c[1])
        findings.append({
            "column": name,
            "kind": kind,
            "confidence": round(min(confidence, 0.99), 2),
            "match_pct": round(confidence * 100, 1),
            "proposed_action": action,
            "example_masked": _mask_value(str(values.iloc[0]), kind),
            "note": _NOTES[kind],
        })
    return findings


_NOTES = {
    "email": "Email addresses identify individuals directly.",
    "phone": "Looks like Indian mobile numbers (10 digits, 6-9 start).",
    "aadhaar": "12-digit numbers in Aadhaar format - treat as sensitive ID.",
    "pan": "Matches the PAN card pattern (AAAAA9999A).",
    "pincode": "6-digit PIN codes are area-level, usually safe to keep for analysis.",
    "account_number": "Long digit strings in an account-like column.",
    "person_name": "Capitalized multi-word values that read like personal names.",
    "address": "Long free text with numbers and street words - likely home addresses.",
}


def _mask_value(v: str, kind: str) -> str:
    v = v.strip()
    if kind == "email":
        local, _, domain = v.partition("@")
        return (local[:1] + "***@" + domain) if domain else "***"
    if kind in ("phone", "aadhaar", "account_number"):
        digits = re.sub(r"\D", "", v)
        return "XXXX-" + digits[-4:] if len(digits) >= 4 else "XXXX"
    if kind == "pan":
        return "XXXXX" + v[-5:] if len(v) >= 5 else "XXXXX"
    if kind == "person_name":
        parts = v.split()
        return " ".join(p[:1] + "." for p in parts if p)
    if kind == "address":
        return "(address withheld)"
    return v  # keep kinds (pincode) pass through


def apply_pii_actions(
    df: pd.DataFrame, findings: list[dict[str, Any]], actions: dict[str, str]
) -> pd.DataFrame:
    """Build the masked frame from approved per-column actions. Never mutates df."""
    work = df.copy()
    kinds = {f["column"]: f["kind"] for f in findings}
    for col, action in actions.items():
        if col not in work.columns:
            continue
        if action == "drop":
            work = work.drop(columns=[col])
        elif action == "mask":
            kind = kinds.get(col, "account_number")
            work[col] = work[col].map(
                lambda v: _mask_value(str(v), kind) if pd.notna(v) else v
            )
    return work
