"""Feature agent: curates deterministic feature candidates in plain language."""
from __future__ import annotations

import json
from typing import Any

from engine.llm.base import LLMProvider

_SYSTEM = (
    "You are the feature-engineering agent in an ML workbench for non-experts. "
    "You are given candidate engineered features computed from the data, plus "
    "the user's goal. For each candidate decide keep (worth offering to the "
    "human) or drop (unlikely to help this goal), and rewrite the rationale as "
    "one short plain-language sentence a policy maker understands - say what "
    "the new signal captures, not how it is computed. Do not invent new "
    "features; only judge the listed ones. Style rule: use plain hyphens (-) "
    "only; never use em dashes or en dashes in your output."
)

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "features": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "The candidate's id, unchanged."},
                    "keep": {"type": "boolean"},
                    "recommended": {"type": "boolean", "description": "Tick by default for the human?"},
                    "rationale": {"type": "string", "description": "One plain-language sentence."},
                },
                "required": ["id", "keep", "recommended", "rationale"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["features"],
    "additionalProperties": False,
}


def run_feature_agent(
    provider: LLMProvider | None,
    candidates: list[dict[str, Any]],
    question: str,
    use_case: str,
    column_labels: dict[str, str],
) -> list[dict[str, Any]]:
    """Return the curated candidate list (kept ones only), labeled."""
    curated = candidates
    generated_by = "heuristic"
    if provider is not None and candidates:
        try:
            prompt = (
                f"User's goal: {question or '(none)'}\n"
                f"Analysis type: {use_case}\n"
                f"Candidates: {json.dumps(candidates)}"
            )
            result = provider.complete_json(_SYSTEM, prompt, _SCHEMA)
            by_id = {f["id"]: f for f in result.get("features", [])}
            curated = []
            for c in candidates:
                verdict = by_id.get(c["id"])
                if verdict is None or verdict.get("keep", True):
                    item = dict(c)
                    if verdict:
                        item["rationale"] = verdict.get("rationale") or c["rationale"]
                        item["recommended"] = bool(verdict.get("recommended", c["recommended"]))
                    curated.append(item)
            generated_by = "claude"
        except Exception:
            curated = candidates

    out = []
    for c in curated:
        item = dict(c)
        item["label"] = _label(c, column_labels)
        item["generated_by"] = generated_by
        out.append(item)
    return out


def _label(spec: dict[str, Any], labels: dict[str, str]) -> str:
    cols = [labels.get(c, c) for c in spec["columns"]]
    kind = spec["kind"]
    if kind == "log":
        return f"{cols[0]} (log scale)"
    if kind == "ratio":
        return f"{cols[0]} per {cols[1]}"
    if kind == "interaction":
        return f"{cols[0]} x {cols[1]}"
    if kind == "length":
        return f"{cols[0]} (text length)"
    return spec["name"]
