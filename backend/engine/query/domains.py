"""Domain scout: group a wide dataset's columns into topics ("literacy",
"workers", "amenities") so the user can choose WHERE to dig and the agents
can suggest where more analysis looks worthwhile.

Grouping column names into topics is a judgment call - exactly the LLM's
role (rule 3). This module is the deterministic fallback and the validator:
a token-stem heuristic that always works offline, plus helpers the route
uses to sanity-check whatever the LLM proposes (only real columns survive).
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

# Qualifier tokens that describe HOW a thing is measured, not WHAT it is.
_QUALIFIERS = {
    "male", "males", "female", "females", "persons", "person", "total",
    "rate", "ratio", "number", "of", "per", "percentage", "pct", "to",
    "population", "and", "the", "in", "with", "without", "years", "year",
    "name", "level", "x0", "x5", "x15", "x60", "above", "below", "incl",
    "1", "2", "3", "0", "4", "5", "14", "15", "59", "6", "60",
}

MIN_GROUP = 2
MAX_DOMAINS = 8


def _tokens(col: str) -> list[str]:
    return [t for t in re.split(r"[^a-zA-Z0-9]+", str(col).lower()) if t]


def heuristic_domains(columns: list[str]) -> list[dict[str, Any]]:
    """Group columns by shared salient tokens. Two passes: count how often
    each topic word appears across ALL columns, then assign each column to
    its most widely shared word - so 'Main.workers' joins 'Total.workers'
    under workers instead of founding a 'main' group. Deterministic."""
    def salient_tokens(col: str) -> list[str]:
        return [t for t in _tokens(col) if t not in _QUALIFIERS and len(t) >= 4]

    freq: dict[str, int] = {}
    for col in columns:
        for t in set(salient_tokens(col)):
            freq[t] = freq.get(t, 0) + 1

    groups_by_token: dict[str, list[str]] = {}
    for col in columns:
        toks = salient_tokens(col)
        if not toks:
            continue
        best = max(toks, key=lambda t: (freq[t], -toks.index(t)))
        groups_by_token.setdefault(best, []).append(col)

    groups = [
        {"name": token.capitalize(), "columns": cols,
         "why": f"{len(cols)} columns share the '{token}' theme."}
        for token, cols in groups_by_token.items() if len(cols) >= MIN_GROUP
    ]
    groups.sort(key=lambda g: len(g["columns"]), reverse=True)
    return groups[:MAX_DOMAINS]


def validate_domains(raw: list[dict[str, Any]], columns: list[str]) -> list[dict[str, Any]]:
    """Keep only real column names in each proposed domain; drop empties."""
    colset = {str(c) for c in columns}
    out = []
    for d in raw[:MAX_DOMAINS]:
        cols = [c for c in d.get("columns", []) if c in colset]
        if len(cols) >= MIN_GROUP and d.get("name"):
            out.append({"name": str(d["name"])[:40], "columns": cols,
                        "why": str(d.get("why", ""))[:200]})
    return out


def suggest_domain(domains: list[dict[str, Any]], df: pd.DataFrame) -> str | None:
    """Deterministic default suggestion: the domain whose numeric columns
    vary the most relative to their means - where differences (and therefore
    questions) are likely to live."""
    best, best_score = None, -1.0
    for d in domains:
        score = 0.0
        n = 0
        for c in d["columns"]:
            if c in df.columns and pd.api.types.is_numeric_dtype(df[c]):
                s = df[c].dropna()
                if len(s) > 3 and abs(float(s.mean())) > 1e-9:
                    score += float(s.std()) / abs(float(s.mean()))
                    n += 1
        if n:
            score /= n
            if score > best_score:
                best, best_score = d["name"], score
    return best
