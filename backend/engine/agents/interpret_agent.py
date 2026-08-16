"""Interpretation agent: explains model results in plain language."""
from __future__ import annotations

import json
from typing import Any

from engine.llm.base import LLMProvider

_SYSTEM = (
    "You are the results-interpretation agent in an ML workbench. You are given "
    "the model that was run, its hyperparameters, evaluation metrics, and "
    "chart artifacts. Explain what the results mean in plain language for a "
    "mixed audience, assess whether the model performed well, and suggest "
    "concrete next steps. Never invent numbers; only reference values present "
    "in the input. Style rule: use plain hyphens (-) only; never use em dashes "
    "or en dashes in your output."
)

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "2-4 sentence plain-language interpretation of the results."},
        "assessment": {
            "type": "string",
            "enum": ["strong", "moderate", "weak", "inconclusive"],
            "description": "Overall quality judgment of the model's performance.",
        },
        "highlights": {"type": "array", "items": {"type": "string"}, "description": "3-5 concrete observations citing metric values."},
        "next_steps": {"type": "array", "items": {"type": "string"}, "description": "2-4 actionable suggestions."},
    },
    "required": ["summary", "assessment", "highlights", "next_steps"],
    "additionalProperties": False,
}


def _fallback(model_name: str, use_case: str, metrics: dict[str, Any]) -> dict[str, Any]:
    highlights = [f"{k.replace('_', ' ')}: {v}" for k, v in metrics.items() if v is not None][:5]

    assessment = "inconclusive"
    if use_case == "classification" and isinstance(metrics.get("accuracy"), (int, float)):
        acc = metrics["accuracy"]
        assessment = "strong" if acc >= 0.85 else "moderate" if acc >= 0.7 else "weak"
    elif use_case == "regression" and isinstance(metrics.get("r2"), (int, float)):
        r2 = metrics["r2"]
        assessment = "strong" if r2 >= 0.7 else "moderate" if r2 >= 0.4 else "weak"
    elif use_case == "clustering" and isinstance(metrics.get("silhouette"), (int, float)):
        sil = metrics["silhouette"]
        assessment = "strong" if sil >= 0.5 else "moderate" if sil >= 0.25 else "weak"
    elif use_case == "forecasting" and isinstance(metrics.get("mape_pct"), (int, float)):
        mape = metrics["mape_pct"]
        assessment = "strong" if mape <= 10 else "moderate" if mape <= 25 else "weak"

    return {
        "summary": f"{model_name} completed. Review the metrics and charts below; assessment: {assessment}.",
        "assessment": assessment,
        "highlights": highlights,
        "next_steps": [
            "Try an alternative model from the same use case and compare metrics.",
            "Adjust hyperparameters and re-run to see the effect.",
        ],
        "generated_by": "heuristic",
    }


def run_interpret_agent(
    provider: LLMProvider | None,
    model_name: str,
    use_case: str,
    hyperparams: dict[str, Any],
    metrics: dict[str, Any],
    artifacts: dict[str, Any],
    question: str,
) -> dict[str, Any]:
    if provider is None:
        return _fallback(model_name, use_case, metrics)
    try:
        # Artifacts can be big (scatter points); trim for the prompt.
        slim_artifacts = {}
        for k, v in artifacts.items():
            if k == "scatter":
                slim_artifacts[k] = {"axes": v.get("axes"), "n_points": len(v.get("points", []))}
            elif k == "series":
                slim_artifacts[k] = {"n_points": len(v), "first": v[:3], "last": v[-3:]}
            else:
                slim_artifacts[k] = v
        prompt = (
            f"Model: {model_name} (use case: {use_case})\n"
            f"User's original question: {question or '(none)'}\n"
            f"Hyperparameters: {json.dumps(hyperparams)}\n"
            f"Metrics: {json.dumps(metrics)}\n"
            f"Artifacts (trimmed): {json.dumps(slim_artifacts, default=str)}"
        )
        result = provider.complete_json(_SYSTEM, prompt, _SCHEMA)
        result["generated_by"] = "claude"
        return result
    except Exception:
        return _fallback(model_name, use_case, metrics)
