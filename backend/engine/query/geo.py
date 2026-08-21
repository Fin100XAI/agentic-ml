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

# Standard two-letter state/UT codes (census files often carry ONLY the
# code) - calibrated to the bundled boundary names.
STATE_CODES = {
    "an": "Andaman & Nicobar Island", "ap": "Andhra Pradesh",
    "ar": "Arunanchal Pradesh", "as": "Assam", "br": "Bihar",
    "ch": "Chandigarh", "cg": "Chhattisgarh", "ct": "Chhattisgarh",
    "dn": "Dadara & Nagar Havelli", "dd": "Daman & Diu",
    "dl": "NCT of Delhi", "ga": "Goa", "gj": "Gujarat", "hr": "Haryana",
    "hp": "Himachal Pradesh", "jk": "Jammu & Kashmir", "jh": "Jharkhand",
    "ka": "Karnataka", "kl": "Kerala", "ld": "Lakshadweep",
    "mp": "Madhya Pradesh", "mh": "Maharashtra", "mn": "Manipur",
    "ml": "Meghalaya", "mz": "Mizoram", "nl": "Nagaland",
    "or": "Odisha", "od": "Odisha", "pb": "Punjab", "py": "Puducherry",
    "rj": "Rajasthan", "sk": "Sikkim", "tn": "Tamil Nadu",
    "tg": "Telangana", "ts": "Telangana", "tr": "Tripura",
    "up": "Uttar Pradesh", "ut": "Uttarakhand", "uk": "Uttarakhand",
    "wb": "West Bengal",
}


# Common misspellings and abbreviations seen in real files, keyed by their
# fully normalized (alphanumeric-only) form. Note the boundary file itself
# spells "Arunanchal Pradesh" - the fix maps the CORRECT spelling onto it.
GEO_NAME_FIXES = {
    "andhra": "Andhra Pradesh", "orrisa": "Odisha", "delhi": "NCT of Delhi",
    "newdelhi": "NCT of Delhi", "uttranchal": "Uttarakhand",
    "meghalya": "Meghalaya", "arunachalpradesh": "Arunanchal Pradesh",
    "dnh": "Dadara & Nagar Havelli", "dd": "Daman & Diu",
    "lakshdweep": "Lakshadweep", "jandk": "Jammu & Kashmir",
    "chattisgarh": "Chhattisgarh", "hariyana": "Haryana",
}


def _norm(name: str) -> str:
    low = str(name).strip().lower()
    low = STATE_CODES.get(low, low).lower()
    low = _V2C.get(low, low).lower()
    # The boundary files write '&' where departmental files write 'and'
    # ('Daman & Diu' vs 'Daman and Diu'), and stripping punctuation alone
    # leaves the two apart. Drop the connector as a WHOLE WORD only - the
    # district of Anand must survive.
    low = re.sub(r"\band\b", " ", low)
    slug = re.sub(r"[^a-z0-9]", "", low)
    fixed = GEO_NAME_FIXES.get(slug)
    if fixed:
        return re.sub(r"[^a-z0-9]", "", fixed.lower())
    return slug


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
