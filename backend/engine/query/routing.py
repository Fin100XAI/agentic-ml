"""Route classification: does this question need a trained model, or can
it be answered directly from the data? Deterministic keyword heuristic -
used as the fallback and as a sanity default when the LLM omits a route.
"""
from __future__ import annotations

import re

_MODEL_PATTERNS = [
    r"\bpredict", r"\bforecast", r"\bwill\b", r"\blikely\b", r"\brisk\b",
    r"\bnext (month|quarter|year|week)\b", r"\bfuture\b", r"\bexpected\b",
    r"\bproject(ed|ion)?\b", r"\bclassif", r"\bsegment", r"\bcluster",
    r"\bdrives?\b", r"\bdriver", r"\bwhat if\b", r"\bestimate\b",
]

# Strong signals stand on their own; weak ones ('which', 'show') also appear
# inside prediction phrasings ('predict which customers...') and only count
# when no model verb is present.
_QUERY_STRONG = [
    r"\btop\b", r"\bbottom\b", r"\bhow many\b", r"\bcount\b",
    r"\baverage\b", r"\btotal\b", r"\bsum\b", r"\bmedian\b",
    r"\bcompare\b", r"\bhighest\b", r"\blowest\b",
    r"\blast (month|quarter|year)\b", r"\bbelow\b", r"\babove\b",
]
_QUERY_WEAK = [
    r"\bwhich\b", r"\blist\b", r"\bshow\b", r"\bshare\b",
    r"\bper district\b", r"\bby district\b",
]


def classify_route(question: str) -> dict[str, str]:
    """-> {route: model_needed | direct_query | both, route_reasoning}."""
    q = (question or "").lower()
    model_hit = any(re.search(p, q) for p in _MODEL_PATTERNS)
    strong_hit = any(re.search(p, q) for p in _QUERY_STRONG)
    weak_hit = any(re.search(p, q) for p in _QUERY_WEAK)
    query_hit = strong_hit or (weak_hit and not model_hit)
    if model_hit and strong_hit:
        return {
            "route": "both",
            "route_reasoning": "The question mixes a lookup you can answer directly from "
                         "the data with a prediction that needs a trained model.",
        }
    if query_hit and not model_hit:
        return {
            "route": "direct_query",
            "route_reasoning": "This asks about what the data already contains - it can be "
                         "answered directly, no model training needed.",
        }
    return {
        "route": "model_needed",
        "route_reasoning": "This asks about outcomes or patterns beyond a direct lookup - "
                     "a trained model is the right tool.",
    }
