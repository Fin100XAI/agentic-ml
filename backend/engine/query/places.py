"""Place Harmonizer: the practical fix for place names written differently
across documents ("Poona"/"Pune", "Bangalore"/"Bengaluru").

Three deterministic layers propose merges; an optional LLM judge phrases and
filters ambiguous ones elsewhere. NOTHING is applied without approval, and
approved mappings become project aliases so next month's file harmonizes
automatically. The same fix serves maps AND group-bys - a split spelling
silently splits totals.
"""
from __future__ import annotations

import difflib
from typing import Any

import pandas as pd

# Official renames and very common variants (canonical -> variants).
# Curated, offline, additive - extend freely.
INDIA_ALIASES: dict[str, list[str]] = {
    "Bengaluru": ["Bangalore"],
    "Mumbai": ["Bombay"],
    "Chennai": ["Madras"],
    "Kolkata": ["Calcutta"],
    "Pune": ["Poona"],
    "Prayagraj": ["Allahabad"],
    "Varanasi": ["Benares", "Banaras"],
    "Gurugram": ["Gurgaon"],
    "Vadodara": ["Baroda"],
    "Thiruvananthapuram": ["Trivandrum"],
    "Kochi": ["Cochin"],
    "Kozhikode": ["Calicut"],
    "Puducherry": ["Pondicherry"],
    "Vishakhapatnam": ["Visakhapatnam", "Vizag"],
    "Shimla": ["Simla"],
    "Kanpur": ["Cawnpore"],
    "Guwahati": ["Gauhati"],
    "Odisha": ["Orissa"],
    "Uttarakhand": ["Uttaranchal"],
    "Belagavi": ["Belgaum"],
    "Mysuru": ["Mysore"],
    "Mangaluru": ["Mangalore"],
    "Hubballi": ["Hubli"],
    "Tumakuru": ["Tumkur"],
    "Shivamogga": ["Shimoga"],
}
_VARIANT_TO_CANONICAL = {
    v.lower(): canon for canon, variants in INDIA_ALIASES.items() for v in variants
}

FUZZY_THRESHOLD = 0.86
MAX_LEVELS = 80


def detect_place_variants(
    series: pd.Series,
    project_aliases: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """-> proposals [{canonical, variants, source, counts}] for ONE column.
    project_aliases maps variant(lower) -> canonical from earlier approvals."""
    counts = series.dropna().astype(str).str.strip().value_counts()
    values = [v for v in counts.index if v]
    if not 2 <= len(values) <= MAX_LEVELS:
        return []
    proposals: list[dict[str, Any]] = []
    consumed: set[str] = set()

    def _propose(canonical: str, variants: list[str], source: str) -> None:
        variants = [v for v in variants if v not in consumed and v != canonical]
        if not variants:
            return
        consumed.update(variants + [canonical])
        proposals.append({
            "canonical": canonical,
            "variants": variants,
            "source": source,
            "counts": {v: int(counts.get(v, 0)) for v in variants + [canonical]},
        })

    lower_map: dict[str, list[str]] = {}
    for v in values:
        lower_map.setdefault(v.lower(), []).append(v)

    # Layer 0: project aliases learned from earlier approvals.
    for low, originals in lower_map.items():
        canon = (project_aliases or {}).get(low)
        if canon and any(o != canon for o in originals):
            _propose(canon, originals, "project alias")

    # Layer 1: case/spacing variants of the same name ("PUNE" vs "Pune").
    for low, originals in lower_map.items():
        if len(originals) > 1 and low not in consumed:
            canonical = max(originals, key=lambda o: counts.get(o, 0))
            _propose(canonical, originals, "case/spacing")

    # Layer 2: the official-rename dictionary.
    for low, originals in lower_map.items():
        canon = _VARIANT_TO_CANONICAL.get(low)
        if canon and originals and originals[0] not in consumed:
            # Propose the official name whether or not it already appears.
            _propose(canon, originals, "official rename")

    # Layer 3: fuzzy spelling within the column ("Bhramati" ~ "Baramati").
    remaining = [v for v in values if v not in consumed]
    for i, a in enumerate(remaining):
        if a in consumed:
            continue
        close = [b for b in remaining[i + 1:]
                 if b not in consumed
                 and difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() > FUZZY_THRESHOLD]
        if close:
            group = [a] + close
            canonical = max(group, key=lambda o: counts.get(o, 0))
            _propose(canonical, group, "spelling")

    return proposals


def apply_place_mapping(df: pd.DataFrame, column: str,
                        mapping: dict[str, str]) -> pd.DataFrame:
    out = df.copy()
    out[column] = out[column].astype(str).str.strip().replace(mapping).where(
        df[column].notna(), df[column])
    return out
