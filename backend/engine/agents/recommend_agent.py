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

USE_CASES = ("classification", "clustering", "forecasting")

_SYSTEM = (
    "You are the model-selection agent in an ML workbench with a fixed model "
    "catalog. Based on the dataset profile and the user's goal, choose the most "
    "appropriate use case and rank the available models for it. Only use model "
    "keys and column names that actually appear in the input. Explain your "
    "reasoning concretely, referencing the data's characteristics."
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
        },
        "required": ["use_case", "reasoning", "ranked_models", "target", "time_column"],
        "additionalProperties": False,
    }


def _heuristic(profile: dict[str, Any], question: str) -> dict[str, Any]:
    q = (question or "").lower()
    suggested = profile.get("suggested_use_cases", [])
    cols = profile["columns"]

    # Question keywords override profile suggestion.
    if any(w in q for w in ("forecast", "predict future", "next month", "trend", "time series")):
        use_case = "forecasting"
    elif any(w in q for w in ("segment", "cluster", "group", "anomal", "outlier")):
        use_case = "clustering"
    elif any(w in q for w in ("classify", "predict", "churn", "fraud", "default", "label")):
        use_case = "classification"
    else:
        use_case = suggested[0] if suggested else "clustering"

    target = None
    time_column = None
    if use_case in ("classification", "forecasting"):
        candidates = profile.get("candidate_targets", [])
        if use_case == "forecasting":
            numeric = [c["name"] for c in candidates if c["role"] == "numeric"]
            target = numeric[0] if numeric else next((c["name"] for c in cols if c["role"] == "numeric"), None)
            time_column = next((c["name"] for c in cols if c["role"] == "datetime"), None)
        else:
            preferred = [c["name"] for c in candidates if c["role"] in ("boolean", "categorical")]
            target = preferred[0] if preferred else (candidates[0]["name"] if candidates else None)

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
            + "\n\nUser's goal/question: " + (question or "(none provided — infer from the data)")
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
        result["generated_by"] = "claude"
        return result
    except Exception:
        return _heuristic(profile, question)
