"""Map layer (P2.2): match result keys to bundled India boundaries.

Boundary files are bundled in backend/geo_data (Datameet community maps,
CC-BY 4.0, simplified) - loaded locally, never fetched from a network.
Matching is deterministic: normalized names + the official-rename alias
dictionary. A map is only OFFERED when >= 70% of a result's keys match a
boundary set; unmatched names are returned and counted honestly.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .places import INDIA_ALIASES

GEO_DIR = Path(__file__).resolve().parents[2] / "geo_data"
LEVELS = ("states", "districts")
MATCH_THRESHOLD = 0.7

_V2C = {v.lower(): c for c, variants in INDIA_ALIASES.items() for v in variants}


def _norm(name: str) -> str:
    low = str(name).strip().lower()
    low = _V2C.get(low, low).lower()
    return re.sub(r"[^a-z0-9]", "", low)


@lru_cache(maxsize=None)
def boundary_names(level: str) -> dict[str, str]:
    """normalized name -> canonical boundary name for a bundled level."""
    path = GEO_DIR / f"india_{level}.geojson"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {_norm(f["properties"]["name"]): f["properties"]["name"]
            for f in data["features"]}


def match_level(keys: list[str]) -> dict[str, Any] | None:
    """Best boundary level for these keys, or None below the threshold."""
    keys = [k for k in dict.fromkeys(str(k).strip() for k in keys) if k]
    if len(keys) < 2:
        return None
    best: dict[str, Any] | None = None
    for level in LEVELS:
        names = boundary_names(level)
        if not names:
            continue
        matched = {k: names[_norm(k)] for k in keys if _norm(k) in names}
        pct = len(matched) / len(keys)
        if pct >= MATCH_THRESHOLD and (best is None or pct > best["match_pct"]):
            best = {
                "level": level,
                "match_pct": round(pct, 2),
                "matches": matched,
                "unmatched": [k for k in keys if k not in matched],
            }
    return best


def geojson_path(level: str) -> Path | None:
    if level not in LEVELS:
        return None
    path = GEO_DIR / f"india_{level}.geojson"
    return path if path.exists() else None
