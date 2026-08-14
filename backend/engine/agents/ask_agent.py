"""Ask-the-data agent: answers stakeholder questions grounded in the run's facts."""
from __future__ import annotations

import json
from typing import Any

from engine.llm.base import LLMProvider

_SYSTEM = (
    "You are a data analyst assistant embedded in an analytics platform for decision "
    "makers with no ML background. You are given the computed facts of an analysis run: "
    "the dataset profile, findings, drivers/segments/outlook, model metrics, and the "
    "executive brief. Answer the user's question plainly and concretely.\n"
    "Rules: cite only numbers present in the provided context — never invent or estimate "
    "figures. If the question cannot be answered from the context, say so and state what "
    "additional analysis or data would answer it. Keep answers short (2-6 sentences) "
    "unless the question genuinely needs more."
)


def _context(run_data: dict[str, Any]) -> str:
    """Assemble a compact, factual context block from the run."""
    parts: dict[str, Any] = {}
    profile = run_data.get("profile") or {}
    parts["dataset"] = {
        "filename": run_data.get("filename"),
        "rows": profile.get("n_rows"),
        "columns": [
            {
                "name": c["name"],
                "label": c.get("display_name"),
                "meaning": c.get("meaning"),
                "role": c["role"],
                "stats": c.get("stats"),
                "top_values": c.get("top_values"),
                "missing_pct": c.get("missing_pct"),
            }
            for c in profile.get("columns", [])
        ],
        "correlations": profile.get("correlations"),
        "health": profile.get("health"),
    }
    parts["question_asked"] = run_data.get("question")
    if run_data.get("eda"):
        parts["eda_summary"] = run_data["eda"].get("summary")
    if run_data.get("config"):
        parts["model"] = {k: run_data["config"].get(k) for k in ("model_name", "use_case", "hyperparams", "target")}
    if run_data.get("result"):
        parts["metrics"] = run_data["result"].get("metrics")
    if run_data.get("insights"):
        ins = run_data["insights"]
        parts["insights"] = {
            "outcome_summary": ins.get("outcome_summary"),
            "findings": ins.get("findings"),
            "drivers": ins.get("drivers"),
            "segments": ins.get("segments"),
            "outlook": ins.get("outlook"),
            "evidence": ins.get("evidence"),
            "brief": ins.get("brief"),
        }
    if run_data.get("comparison"):
        comp = run_data["comparison"]
        parts["model_comparison"] = [
            {"model": r["model_name"], "metrics": r["metrics"], "error": r["error"]}
            for r in comp.get("results", [])
        ]
    return json.dumps(parts, default=str)


def run_ask_agent(
    provider: LLMProvider | None,
    run_data: dict[str, Any],
    question: str,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    if provider is None:
        return {
            "answer": (
                "Interactive Q&A needs Claude connected (add ANTHROPIC_API_KEY to backend/.env). "
                "Meanwhile, the decision brief above and the technical appendix contain all "
                "computed findings for this analysis."
            ),
            "generated_by": "heuristic",
        }
    try:
        convo = ""
        for h in (history or [])[-3:]:
            convo += f"\nEarlier Q: {h.get('q', '')}\nEarlier A: {h.get('a', '')}\n"
        prompt = (
            "Analysis context (JSON):\n" + _context(run_data)
            + ("\n\nConversation so far:" + convo if convo else "")
            + f"\n\nThe decision maker now asks: {question}"
        )
        answer = provider.complete_text(_SYSTEM, prompt, max_tokens=1024)
        return {"answer": answer, "generated_by": "claude"}
    except Exception as exc:
        return {"answer": f"Could not answer right now ({exc}).", "generated_by": "error"}
