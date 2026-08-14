"""EDA agent: turns the structured profile into human-readable findings.

With Claude configured it writes a narrative summary and key findings; without a
key it falls back to deterministic text derived from the profile, so the
pipeline always completes.
"""
from __future__ import annotations

import json
from typing import Any

from engine.llm.base import LLMProvider

_SYSTEM = (
    "You are a senior data analyst inside an ML workbench. You are given a "
    "structured statistical profile of a dataset the user just uploaded. "
    "Explain what the dataset appears to contain in plain language for a mixed "
    "technical/non-technical audience. Be concrete, cite column names and "
    "numbers from the profile, and never invent facts not present in it. Style rule: use plain hyphens (-) only; never use em dashes or en dashes in your output."
)

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "2-4 sentence plain-language description of the dataset."},
        "key_findings": {
            "type": "array",
            "items": {"type": "string"},
            "description": "3-6 short, concrete findings (data quality, distributions, correlations, anomalies).",
        },
        "suggested_questions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "2-4 questions the user might want to ask of this data.",
        },
        "problem_statements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "statement": {
                        "type": "string",
                        "description": "A concrete business/policy problem this data could answer, in one plain sentence. Use everyday words and the friendly column labels - never raw column headers.",
                    },
                    "use_case": {
                        "type": "string",
                        "enum": ["classification", "clustering", "forecasting"],
                    },
                },
                "required": ["statement", "use_case"],
                "additionalProperties": False,
            },
            "description": "2-4 problem statements a decision maker would recognize, each mapped to the analysis type that answers it.",
        },
        "column_labels": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The raw column name exactly as in the profile."},
                    "label": {"type": "string", "description": "A short, human-friendly label a non-expert instantly understands (2-4 words, no jargon)."},
                    "meaning": {"type": "string", "description": "One plain sentence on what this column likely represents."},
                },
                "required": ["name", "label", "meaning"],
                "additionalProperties": False,
            },
            "description": "A friendly label + meaning for every column in the profile.",
        },
    },
    "required": ["summary", "key_findings", "suggested_questions", "problem_statements", "column_labels"],
    "additionalProperties": False,
}


def _heuristic_problems(profile: dict[str, Any]) -> list[dict[str, str]]:
    """Plain-language problem statements built from the profile (no raw headers)."""
    out: list[dict[str, str]] = []
    cols = profile["columns"]
    label = {c["name"]: c.get("display_name", c["name"]) for c in cols}

    if "classification" in profile.get("suggested_use_cases", []):
        cands = [c for c in profile.get("candidate_targets", []) if c["role"] in ("boolean", "categorical")]
        if cands:
            out.append({
                "statement": f"Understand what makes '{label.get(cands[0]['name'], cands[0]['name']).lower()}' differ between records, and who is most at risk.",
                "use_case": "classification",
            })
    if "clustering" in profile.get("suggested_use_cases", []):
        out.append({
            "statement": "Find the natural groups hiding in these records so each group can be treated differently.",
            "use_case": "clustering",
        })
    if "forecasting" in profile.get("suggested_use_cases", []):
        num = next((c for c in cols if c["role"] == "numeric"), None)
        if num:
            out.append({
                "statement": f"See where '{num.get('display_name', num['name']).lower()}' is heading over the coming periods.",
                "use_case": "forecasting",
            })
    return out


def _fallback(profile: dict[str, Any]) -> dict[str, Any]:
    cols = profile["columns"]
    roles: dict[str, int] = {}
    for c in cols:
        roles[c["role"]] = roles.get(c["role"], 0) + 1
    role_txt = ", ".join(f"{v} {k}" for k, v in roles.items())

    findings = [
        f"Dataset has {profile['n_rows']:,} rows and {profile['n_cols']} columns ({role_txt})."
    ]
    miss = profile["missingness"]
    if miss["total_missing_cells"]:
        findings.append(
            f"{miss['pct_missing']}% of cells are missing, concentrated in: "
            + ", ".join(miss["columns_with_missing"][:5])
        )
    else:
        findings.append("No missing values detected.")
    if profile["correlations"]:
        top = profile["correlations"][0]
        findings.append(f"Strongest correlation: {top['a']} vs {top['b']} (r={top['corr']}).")
    if profile["candidate_targets"]:
        names = ", ".join(c["name"] for c in profile["candidate_targets"][:3])
        findings.append(f"Likely prediction target candidates: {names}.")

    return {
        "summary": (
            f"The dataset contains {profile['n_rows']:,} records across {profile['n_cols']} columns. "
            f"Detected column types: {role_txt}. Suggested analysis directions: "
            + ", ".join(profile["suggested_use_cases"]) + "."
        ),
        "key_findings": findings,
        "suggested_questions": [
            "Which columns most influence the likely target?",
            "Are there natural groups or segments in this data?",
        ],
        "problem_statements": _heuristic_problems(profile),
        "generated_by": "heuristic",
    }


def run_eda_agent(provider: LLMProvider | None, profile: dict[str, Any]) -> dict[str, Any]:
    if provider is None:
        return _fallback(profile)
    try:
        # Keep the prompt compact: strip previews/histograms the model doesn't need.
        slim = {k: v for k, v in profile.items() if k != "preview"}
        slim["columns"] = [
            {k: v for k, v in c.items() if k != "histogram"} for c in slim.get("columns", [])
        ]
        result = provider.complete_json(
            _SYSTEM,
            "Dataset profile (JSON):\n" + json.dumps(slim, default=str),
            _SCHEMA,
        )
        # Merge Claude's friendlier labels/meanings back into the profile columns.
        labels = {cl["name"]: cl for cl in result.pop("column_labels", [])}
        for col in profile.get("columns", []):
            cl = labels.get(col["name"])
            if cl:
                col["display_name"] = cl["label"]
                col["meaning"] = cl["meaning"]
        if not result.get("problem_statements"):
            result["problem_statements"] = _heuristic_problems(profile)
        result["generated_by"] = "claude"
        return result
    except Exception:
        return _fallback(profile)
