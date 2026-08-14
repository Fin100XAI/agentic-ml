"""Brief agent: composes a decision-ready executive brief from computed insights.

The insight numbers are computed deterministically in ``engine/insights.py``;
this agent writes the narrative around them — executive summary, recommended
actions, and what to watch out for. Falls back to a template without an API key.
"""
from __future__ import annotations

import json
from typing import Any

from engine.llm.base import LLMProvider

_SYSTEM = (
    "You write executive briefs for policy makers and business decision makers with no ML "
    "background. You are given machine-computed findings from a dataset analysis. Compose a "
    "brief that helps them decide what to do: a crisp executive summary, concrete recommended "
    "actions grounded in the findings, and honest caveats. Never invent numbers — only use "
    "figures present in the input. Write plainly; no jargon."
)

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "executive_summary": {
            "type": "string",
            "description": "3-5 sentences a decision maker could read aloud in a meeting.",
        },
        "recommended_actions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "3-5 concrete, prioritized actions tied to specific findings.",
        },
        "watch_outs": {
            "type": "array",
            "items": {"type": "string"},
            "description": "1-3 risks or caveats a careful decision maker should keep in mind.",
        },
    },
    "required": ["executive_summary", "recommended_actions", "watch_outs"],
    "additionalProperties": False,
}


def _heuristic(insights: dict[str, Any], question: str) -> dict[str, Any]:
    use_case = insights.get("use_case", "")
    findings = insights.get("findings", [])
    evidence = insights.get("evidence", {})

    summary_bits = [insights.get("outcome_summary", "").rstrip(".")]
    summary_bits += [f["headline"].rstrip(".") for f in findings[1:3]]
    executive_summary = (
        ". ".join(b for b in summary_bits if b) + f". Evidence strength: {evidence.get('level', 'unknown')} — "
        + evidence.get("reason", "")
    )

    actions: list[str] = []
    if use_case == "classification":
        for d in insights.get("drivers", [])[:2]:
            actions.append(
                f"Target interventions at the '{d['feature']}' groups with the highest rates — "
                f"the data shows up to {d['lift']}× difference across groups." if d.get("lift")
                else f"Prioritize the '{d['feature']}' groups with the highest outcome rates."
            )
        actions.append("Pilot an intervention on the highest-rate group and measure the change against the baseline.")
    elif use_case == "clustering":
        segs = [s for s in insights.get("segments", []) if s["cluster"] != -1]
        if segs:
            biggest = max(segs, key=lambda s: s["share_pct"])
            actions.append(
                f"Design differentiated policies per segment — start with {biggest['name']} "
                f"({biggest['share_pct']}% of records)."
            )
        if any(s["cluster"] == -1 for s in insights.get("segments", [])):
            actions.append("Review the outlier records individually — they don't fit any pattern.")
        actions.append("Validate the segment profiles with domain experts before acting on them.")
    elif use_case == "forecasting":
        o = insights.get("outlook", {})
        if o:
            actions.append(
                f"Plan capacity/budget for a projected total of {o.get('projected_total'):,} over the "
                f"next {o.get('horizon')} periods."
            )
            if o.get("uncertainty_pct") is not None:
                actions.append(
                    f"Build plans that stay viable across the ±{o['uncertainty_pct']}% range, not just the central number."
                )
        actions.append("Re-run the forecast as new data arrives to keep the outlook current.")

    return {
        "executive_summary": executive_summary,
        "recommended_actions": actions or ["Review the findings with domain experts to define next steps."],
        "watch_outs": evidence.get("caveats", []),
        "generated_by": "heuristic",
    }


def run_brief_agent(
    provider: LLMProvider | None, insights: dict[str, Any], question: str
) -> dict[str, Any]:
    if provider is None:
        return _heuristic(insights, question)
    try:
        prompt = (
            f"The decision maker's question: {question or '(none given — infer the decision context)'}\n\n"
            "Machine-computed findings (JSON):\n" + json.dumps(insights, default=str)
        )
        result = provider.complete_json(_SYSTEM, prompt, _SCHEMA)
        result["generated_by"] = "claude"
        return result
    except Exception:
        return _heuristic(insights, question)
