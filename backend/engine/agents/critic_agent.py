"""Critic agent: one review pass over the draft brief before anyone reads it.

Verifies every quantitative claim maps to a computed number, rewrites
overclaims down to the trust tier, and adds driver-vs-cause caveats to any
recommendation implying causality. Fallback: numbers are deterministic anyway,
so the pass is skipped and a template causal caveat is appended instead.
"""
from __future__ import annotations

import json
from typing import Any

from engine.llm.base import LLMProvider

_SYSTEM = (
    "You are the critic agent - the last reviewer before a decision brief "
    "reaches a policy maker. You receive the DRAFT brief, the machine-computed "
    "insights and metrics it must be grounded in, the stability verdict, and "
    "the trust tier (strong / moderate / weak). Your job: "
    "(a) check every number and quantitative claim in the draft against the "
    "computed values - list any claim you cannot match; "
    "(b) rewrite overclaims so the language matches the trust tier - a weak "
    "tier speaks in hypotheses to verify, never firm recommendations; "
    "(c) any recommendation that implies causation (do X to change Y) must "
    "carry a driver-vs-cause caveat or be rephrased as a pilot/test; "
    "(d) return the revised brief in the SAME structure plus a change list "
    "describing each edit in one short sentence. Keep the author's voice; "
    "change only what the rules require. Style rule: use plain hyphens (-) "
    "only; never use em dashes or en dashes in your output."
)

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "executive_summary": {"type": "string"},
        "recommended_actions": {"type": "array", "items": {"type": "string"}},
        "watch_outs": {"type": "array", "items": {"type": "string"}},
        "changes": {
            "type": "array", "items": {"type": "string"},
            "description": "One short sentence per edit made. Empty if nothing needed changing.",
        },
        "unmatched_claims": {
            "type": "array", "items": {"type": "string"},
            "description": "Quantitative claims in the draft that map to no computed number.",
        },
    },
    "required": ["executive_summary", "recommended_actions", "watch_outs", "changes", "unmatched_claims"],
    "additionalProperties": False,
}

_CAUSAL_CAVEAT = (
    "Drivers shown here are correlations - before acting on one as a cause, "
    "verify it with a small controlled pilot."
)


def run_critic_agent(
    provider: LLMProvider | None,
    brief: dict[str, Any],
    insights: dict[str, Any],
    metrics: dict[str, Any],
    validation: dict[str, Any] | None,
    tier: str,
) -> dict[str, Any]:
    if provider is not None:
        try:
            slim = {k: v for k, v in insights.items() if k not in ("brief", "brief_draft", "critic")}
            prompt = (
                f"Trust tier: {tier}\n"
                f"Stability verdict: {json.dumps(validation or {})}\n"
                f"Computed metrics: {json.dumps(metrics, default=str)}\n"
                f"Computed insights: {json.dumps(slim, default=str)}\n\n"
                f"DRAFT brief to review: {json.dumps({k: brief.get(k) for k in ('executive_summary', 'recommended_actions', 'watch_outs')})}"
            )
            result = provider.complete_json(_SYSTEM, prompt, _SCHEMA)
            revised = {
                "executive_summary": result["executive_summary"],
                "recommended_actions": result["recommended_actions"],
                "watch_outs": result["watch_outs"],
                "generated_by": brief.get("generated_by", "claude"),
            }
            return {
                "brief": revised,
                "changes": result.get("changes", []),
                "unmatched_claims": result.get("unmatched_claims", []),
                "generated_by": "claude",
            }
        except Exception:
            pass

    # Fallback: deterministic numbers cannot be hallucinated, so skip the
    # verification pass - but the causal caveat still applies.
    revised = dict(brief)
    watch_outs = list(brief.get("watch_outs", []))
    if not any("correlation" in w.lower() or "cause" in w.lower() for w in watch_outs):
        watch_outs.append(_CAUSAL_CAVEAT)
    revised["watch_outs"] = watch_outs
    return {
        "brief": revised,
        "changes": ["Heuristic mode: review pass skipped (all numbers are computed); standard causal caveat ensured."],
        "unmatched_claims": [],
        "generated_by": "heuristic",
    }
