"""Remediation agent: phrases and prioritizes deterministic fix proposals."""
from __future__ import annotations

import json
from typing import Any

from engine.llm.base import LLMProvider

_SYSTEM = (
    "You are the data-remediation agent in an ML workbench for non-experts. "
    "You receive deterministic fix proposals computed from data-health findings "
    "plus the user's goal. For each proposal: keep its id, decide whether it "
    "should be ticked by default for THIS goal (recommended), and rewrite the "
    "description and reasoning as short plain-language sentences. Order the "
    "list most-important-first. Never invent new fixes and never change the "
    "numbers. Style rule: use plain hyphens (-) only; never use em dashes or "
    "en dashes in your output."
)

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "proposals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "recommended": {"type": "boolean"},
                    "description": {"type": "string"},
                    "reasoning": {"type": "string"},
                },
                "required": ["id", "recommended", "description", "reasoning"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["proposals"],
    "additionalProperties": False,
}


def run_remediation_agent(
    provider: LLMProvider | None,
    proposals: list[dict[str, Any]],
    question: str,
) -> tuple[list[dict[str, Any]], str]:
    """Return (curated proposals, generated_by)."""
    if provider is None or not proposals:
        return proposals, "heuristic"
    try:
        prompt = (
            f"User's goal: {question or '(none)'}\n"
            f"Deterministic fix proposals: {json.dumps(proposals)}"
        )
        result = provider.complete_json(_SYSTEM, prompt, _SCHEMA)
        by_id = {p["id"]: p for p in result.get("proposals", [])}
        ordered_ids = [p["id"] for p in result.get("proposals", []) if p["id"] in {x["id"] for x in proposals}]
        base = {p["id"]: p for p in proposals}
        curated = []
        for pid in ordered_ids + [p["id"] for p in proposals if p["id"] not in ordered_ids]:
            item = dict(base[pid])
            verdict = by_id.get(pid)
            if verdict:
                item["recommended"] = bool(verdict["recommended"])
                item["description"] = verdict.get("description") or item["description"]
                item["reasoning"] = verdict.get("reasoning") or item["reasoning"]
            curated.append(item)
        return curated, "claude"
    except Exception:
        return proposals, "heuristic"
