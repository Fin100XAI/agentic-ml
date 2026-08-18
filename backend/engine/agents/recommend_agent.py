"""Recommendation agent: picks use case, ranks models, proposes configuration.

Given the EDA profile + the user's question, it recommends one of the three use
cases (classification / clustering / forecasting), ranks the catalog models for
it, and proposes target/feature/hyperparameter configuration. Heuristic fallback
keeps the pipeline working without an API key.
"""
from __future__ import annotations

import json
from typing import Any

from engine.catalog import models_for_use_case
from engine.llm.base import LLMProvider
from engine.query.routing import classify_route  # QUERY-PATH EXTENSION

USE_CASES = ("classification", "regression", "clustering", "forecasting")

_SYSTEM = (
    "You are the model-selection agent in an ML workbench with a fixed model "
    "catalog. Based on the dataset profile and the user's goal, choose the most "
    "appropriate use case and rank the available models for it. Use "
    "classification when predicting a category, REGRESSION when predicting a "
    "continuous numeric amount (price, yield, cost, score), clustering to find "
    "groups, forecasting only when projecting a time-ordered series forward. "
    "Only use model "
    "keys and column names that actually appear in the input. Explain your "
    "reasoning concretely, referencing the data's characteristics. The profile "
    "includes a 'health' section listing data-quality issues (imbalance, small "
    "sample, missing data) - factor these into your choice and mention how they "
    "affect it (e.g. prefer robust models on imbalanced data). Also judge "
    "the route: model_needed for prediction/forecast/pattern questions, "
    "direct_query for questions answerable by filtering/grouping/counting the "
    "data as it stands (which/top/how many/compare), both when mixed, "
    "unanswerable when the data cannot answer it at all. Also judge "
    "alignment: can the user's question actually be answered with the columns in "
    "this dataset? If the question refers to information the data does not "
    "contain (different domain, missing measures), set alignment.aligned=false "
    "and write a short, kind note saying what is missing and what this data CAN "
    "answer instead - but still recommend the closest sensible use case. Style "
    "rule: use plain hyphens (-) only; never use em dashes or en dashes in your output."
)


def _schema(catalog_keys: list[str], column_names: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "use_case": {"type": "string", "enum": list(USE_CASES)},
            "reasoning": {"type": "string", "description": "Why this use case fits the data and the user's goal."},
            "ranked_models": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "enum": catalog_keys},
                        "rationale": {"type": "string"},
                    },
                    "required": ["key", "rationale"],
                    "additionalProperties": False,
                },
            },
            "target": {
                "type": ["string", "null"],
                "description": "Target column for classification/forecasting; null for clustering.",
            },
            "time_column": {
                "type": ["string", "null"],
                "description": "Datetime column for forecasting; null otherwise.",
            },
            "alignment": {
                "type": "object",
                "properties": {
                    "aligned": {
                        "type": "boolean",
                        "description": "True if the user's question can genuinely be answered with this dataset's columns.",
                    },
                    "note": {
                        "type": "string",
                        "description": "If not aligned: one or two plain sentences on why, and what this data CAN answer. Empty string when aligned.",
                    },
                    # QUERY-PATH EXTENSION: route classification (rule 10 touch point a)
                    "route": {
                        "type": "string",
                        "enum": ["model_needed", "direct_query", "both", "unanswerable"],
                        "description": "model_needed: prediction/pattern question requiring training. "
                                       "direct_query: answerable by filtering/grouping the data as-is. "
                                       "both: mixes the two. unanswerable: the data cannot answer it.",
                    },
                    "route_reasoning": {
                        "type": "string",
                        "description": "One sentence on why this route.",
                    },
                },
                "required": ["aligned", "note", "route", "route_reasoning"],
                "additionalProperties": False,
            },
        },
        "required": ["use_case", "reasoning", "ranked_models", "target", "time_column", "alignment"],
        "additionalProperties": False,
    }


_AMOUNT_TOKENS = ("price", "cost", "amount", "revenue", "value", "yield", "total", "spend", "income", "salary")


def _pick_numeric_target(numeric: list[str], q: str) -> str | None:
    """Prefer the column the question names, then amount-like names, then the first."""
    if not numeric:
        return None
    for col in numeric:
        if col.lower().replace("_", " ") in q or col.lower() in q.replace(" ", "_"):
            return col
    for col in numeric:
        if any(tok in col.lower() for tok in _AMOUNT_TOKENS):
            return col
    return numeric[0]


def _heuristic(profile: dict[str, Any], question: str) -> dict[str, Any]:
    q = (question or "").lower()
    suggested = profile.get("suggested_use_cases", [])
    cols = profile["columns"]

    # Question keywords override profile suggestion.
    if any(w in q for w in ("forecast", "predict future", "next month", "trend", "time series")):
        use_case = "forecasting"
    elif any(w in q for w in ("segment", "cluster", "group", "anomal", "outlier")):
        use_case = "clustering"
    elif any(w in q for w in ("how much", "estimate", "price", "value", "amount", "yield", "cost", "revenue", "score")):
        use_case = "regression"
    elif any(w in q for w in ("classify", "predict", "churn", "fraud", "default", "label")):
        use_case = "classification"
    else:
        use_case = suggested[0] if suggested else "clustering"

    target = None
    time_column = None
    if use_case in ("classification", "regression", "forecasting"):
        candidates = profile.get("candidate_targets", [])
        if use_case == "forecasting":
            numeric = [c["name"] for c in candidates if c["role"] == "numeric"]
            target = numeric[0] if numeric else next((c["name"] for c in cols if c["role"] == "numeric"), None)
            time_column = next((c["name"] for c in cols if c["role"] == "datetime"), None)
        elif use_case == "regression":
            numeric = [c["name"] for c in candidates if c["role"] == "numeric"]
            if not numeric:
                numeric = [c["name"] for c in cols if c["role"] == "numeric"]
            target = _pick_numeric_target(numeric, q)
        else:
            preferred = [c["name"] for c in candidates if c["role"] in ("boolean", "categorical")]
            target = preferred[0] if preferred else (candidates[0]["name"] if candidates else None)
            # A "predict" question with only continuous targets is regression.
            if target is None and "predict" in q:
                numeric = [c["name"] for c in candidates if c["role"] == "numeric"]
                if numeric:
                    use_case, target = "regression", numeric[0]

    models = models_for_use_case(use_case)
    ranked = [{"key": m.key, "rationale": m.strengths} for m in models]

    return {
        "use_case": use_case,
        "reasoning": (
            f"Chosen heuristically from the dataset profile (suggested: {', '.join(suggested) or 'n/a'}) "
            f"and your question. Configure Claude for richer reasoning."
        ),
        "ranked_models": ranked,
        "target": target,
        "time_column": time_column,
        # QUERY-PATH EXTENSION: heuristic route classification
        "alignment": {"aligned": True, "note": "", **classify_route(question)},
        "generated_by": "heuristic",
    }


def run_recommend_agent(
    provider: LLMProvider | None, profile: dict[str, Any], question: str
) -> dict[str, Any]:
    # Build catalog context for the prompt.
    catalog = [
        {"key": m.key, "name": m.name, "use_case": m.use_case,
         "description": m.description, "strengths": m.strengths}
        for uc in USE_CASES
        for m in models_for_use_case(uc)
    ]
    column_names = [c["name"] for c in profile["columns"]]

    if provider is None:
        return _heuristic(profile, question)
    try:
        slim = {k: v for k, v in profile.items() if k != "preview"}
        slim["columns"] = [
            {k: v for k, v in c.items() if k != "histogram"} for c in slim.get("columns", [])
        ]
        prompt = (
            "Dataset profile (JSON):\n" + json.dumps(slim, default=str)
            + "\n\nModel catalog (JSON):\n" + json.dumps(catalog)
            + "\n\nUser's goal/question: " + (question or "(none provided - infer from the data)")
        )
        result = provider.complete_json(_SYSTEM, prompt, _schema([m["key"] for m in catalog], column_names))

        # Guard: ranked models must match the chosen use case; fill if empty.
        valid = {m.key for m in models_for_use_case(result["use_case"])}
        result["ranked_models"] = [r for r in result.get("ranked_models", []) if r["key"] in valid]
        if not result["ranked_models"]:
            result["ranked_models"] = [
                {"key": m.key, "rationale": m.strengths} for m in models_for_use_case(result["use_case"])
            ]
        if result.get("target") not in column_names:
            result["target"] = None if result.get("target") else result.get("target")
        # QUERY-PATH EXTENSION: guarantee route fields (heuristic default)
        result.setdefault("alignment", {"aligned": True, "note": ""})
        if not result["alignment"].get("route"):
            result["alignment"].update(classify_route(question))
        result["generated_by"] = "claude"
        return result
    except Exception:
        return _heuristic(profile, question)
