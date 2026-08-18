"""Query planner agent: natural-language question -> structured QueryPlan.

The LLM NEVER writes code (CLAUDE.md rule 11): it fills the typed plan
schema. Its output is validated by Pydantic and the column-resolution
layer; one retry with the error appended, then honest failure. Ambiguity
returns up to two candidate plans; unmappable terms return a clarifying
question, never a fabricated plan.
"""
from __future__ import annotations

import json
from typing import Any

from engine.llm.base import LLMProvider
from engine.query.fallback_planner import fallback_plan
from engine.query.plan import QueryPlan
from engine.query.resolve import resolve_plan

_SYSTEM = (
    "You translate a plain-language question about a dataset into a structured "
    "query plan. You NEVER write code - you fill the plan schema exactly.\n"
    "Steps use a COMPACT notation (only these ops, only these fields):\n"
    "- filter: {op:'filter', column, operator in [==,!=,>,>=,<,<=,in,not_in,"
    "contains,is_null,not_null], value}\n"
    "- time_window: {op:'time_window', column, n} for the last n periods, or "
    "{op:'time_window', column, left:start, right:end} for an absolute range\n"
    "- derive (the ONLY way to compute): {op:'derive', name, fn in [ratio,"
    "difference,percent_of], left, right} - e.g. share = left as percent of right\n"
    "- group_by: {op:'group_by', columns:[...]}\n"
    "- aggregate: {op:'aggregate', column, fn in [sum,mean,median,min,max,count,"
    "nunique], name: alias}\n"
    "- sort: {op:'sort', column, dir in [asc,desc]}\n"
    "- top_n: {op:'top_n', n}\n"
    "- pivot: {op:'pivot', left: row column, right: column-per column, column: values} "
    "- e.g. 'one row per District, one column per Month showing Total' = "
    "{op:'pivot', left:'District', right:'Month', column:'Total'}\n"
    "- delta_vs_period: {op:'delta_vs_period', column, right: period column, n: lag}\n"
    "Filter values are ALWAYS strings: numbers as '40', multiple values for "
    "in/not_in joined with ' | ' (e.g. 'Pune | Nashik').\n"
    "Rules: use ONLY column names from the provided schema; never invent "
    "columns. When a question term matches a GLOSSARY entry that defines a "
    "computation (e.g. 'rate = X divided by Y'), BUILD it with a derive step "
    "from the named columns - that is a confident plan, not a reason to "
    "clarify. A time_window must always carry n or a start/end range. "
    "When a question term could mean two different columns, return mode="
    "'ambiguous' with two candidate plans and a one-line difference note each. "
    "Return mode='clarify' ONLY when a core term matches no column AND no "
    "glossary entry - if you can construct a reasonable plan, return it with "
    "a note and lower confidence instead of clarifying. Questions usually "
    "need several steps composed: derive first, then filter/group/aggregate, "
    "then sort/top_n - build the full chain.\n"
    "Example - 'districts with completion rate below 60%' where the glossary "
    "says completion rate = Completed divided by Enrolled:\n"
    "plans=[{steps:[{op:'derive',name:'completion_rate',fn:'percent_of',"
    "left:'Completed',right:'Enrolled'},{op:'filter',column:'completion_rate',"
    "operator:'<',value:'60'}],note:'rate built from Completed and Enrolled'}]\n"
    "Percentages: if the data holds counts, derive percent_of; if it already "
    "holds a rate column, use it directly. Style rule: plain hyphens only, "
    "never em dashes."
)

# COMPACT step schema: few optional properties on purpose. Constrained
# decoding compiles a grammar from this schema, and grammar size explodes
# with the number of optional keys in an additionalProperties:false object
# (17 keys reliably timed out; ~11 compiles in seconds). Generic fields are
# expanded to the full plan notation by _expand_compact_steps.
_STEP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "op": {"type": "string"},
        "column": {"type": "string"},
        "operator": {"type": "string"},
        # Always a string (grammar stays simple); coerced deterministically.
        "value": {"type": "string"},
        "fn": {"type": "string"},
        "name": {"type": "string"},
        "left": {"type": "string"},
        "right": {"type": "string"},
        "n": {"type": "integer"},
        "dir": {"type": "string"},
        "columns": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["op"],
    "additionalProperties": False,
}


def _infer_derive_kind(step: dict[str, Any], all_steps: list[dict[str, Any]]) -> str:
    """The model habitually omits the derive kind. Infer it deterministically:
    a later filter on the derived name with a value above 1.5 means the user
    thinks in percents; name hints break the remaining ties; ratio otherwise."""
    name = str(step.get("name") or "").lower()
    if any(h in name for h in ("percent", "pct")):
        return "percent_of"
    if any(h in name for h in ("diff", "change", "gap", "delta")):
        return "difference"
    for later in all_steps:
        if later.get("op") == "filter" and str(later.get("column")) == step.get("name"):
            try:
                if abs(float(later.get("value"))) > 1.5:
                    return "percent_of"
            except (TypeError, ValueError):
                pass
    return "ratio"


def _expand_compact_steps(
    steps: list[dict[str, Any]], numeric_columns: list[str] | None = None
) -> list[dict[str, Any]]:
    """Deterministic translation from the compact LLM notation to the full
    QueryPlan step fields, with inference for habitually-omitted fields."""
    out = []
    for s in steps:
        s = {k: v for k, v in dict(s).items() if v is not None}
        op = s.get("op")
        # Tolerant of BOTH notations: the LLM writes compact fields, the
        # fallback planner writes full ones - neither must be clobbered.
        if op == "time_window":
            e: dict[str, Any] = {"op": op, "column": s.get("column")}
            if s.get("last_n") is not None or s.get("n") is not None:
                e["last_n"] = s.get("last_n") if s.get("last_n") is not None else s.get("n")
            if s.get("start") or s.get("left"):
                e["start"] = s.get("start") or s.get("left")
            if s.get("end") or s.get("right"):
                e["end"] = s.get("end") or s.get("right")
            out.append(e)
        elif op == "derive":
            out.append({"op": op, "name": s.get("name"),
                        "kind": s.get("kind") or s.get("fn") or _infer_derive_kind(s, steps),
                        "left": s.get("left"), "right": s.get("right")})
        elif op == "aggregate":
            out.append({"op": op, "column": s.get("column"), "fn": s.get("fn"),
                        "alias": s.get("alias") or s.get("name")})
        elif op == "pivot":
            values = s.get("values") or s.get("column")
            if not values and numeric_columns:
                used = {s.get("index") or s.get("left"), s.get("columns") or s.get("right")}
                values = next((c for c in numeric_columns if c not in used), None)
            out.append({"op": op, "index": s.get("index") or s.get("left"),
                        "columns": s.get("columns") or s.get("right"), "values": values})
        elif op == "delta_vs_period":
            out.append({"op": op, "column": s.get("column"),
                        "period_column": s.get("period_column") or s.get("right"),
                        "lag": s.get("lag") or s.get("n") or 1})
        else:  # filter, group_by, sort, top_n pass through
            out.append(s)
    return out

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "mode": {"type": "string", "enum": ["plan", "ambiguous", "clarify"]},
        "plans": {
            "type": "array",
            "description": "One plan normally; exactly two for mode=ambiguous.",
            "items": {
                "type": "object",
                "properties": {
                    "steps": {"type": "array", "items": _STEP_SCHEMA},
                    "note": {"type": "string",
                             "description": "One line: what this interpretation assumes."},
                },
                "required": ["steps", "note"],
                "additionalProperties": False,
            },
        },
        "clarify_question": {"type": "string"},
        "confidence": {"type": "number"},
        "unresolved_terms": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["mode", "plans", "confidence", "unresolved_terms"],
    "additionalProperties": False,
}


def _coerce_step_values(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic value coercion: the LLM emits string values (keeps the
    output grammar simple); numbers and lists are restored here."""
    out = []
    for s in steps:
        s = dict(s)
        if s.get("op") == "filter" and isinstance(s.get("value"), str):
            v = s["value"].strip()
            if s.get("operator") in ("in", "not_in"):
                parts = [p.strip() for p in (v.split("|") if "|" in v else v.split(","))]
                s["value"] = [p for p in parts if p]
            else:
                try:
                    s["value"] = float(v)
                except ValueError:
                    pass  # text comparison stays text
        out.append(s)
    return out


def _translate_error(msg: str) -> str:
    """Validation errors reference the FULL plan notation; the model writes
    the COMPACT one. Translate so the retry can actually fix the problem."""
    for full, compact in [
        ("derive.kind", "derive fn (must be ratio, difference or percent_of)"),
        ("pivot.values", "pivot column (the values to show)"),
        ("pivot.index", "pivot left (the row column)"),
        ("pivot.columns", "pivot right (the column-per column)"),
        ("aggregate.alias", "aggregate name"),
        ("period_column", "delta_vs_period right (the period column)"),
        ("last_n", "n"),
    ]:
        msg = msg.replace(full, compact)
    return msg


def _validate_plans(
    raw_plans: list[dict[str, Any]], artifact_id: str, columns: list[str],
    numeric_columns: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Pydantic + column resolution for every candidate. Raises on failure."""
    out = []
    for cand in raw_plans:
        steps = _coerce_step_values(
            _expand_compact_steps(cand.get("steps", []), numeric_columns))
        plan = QueryPlan.model_validate({"source": artifact_id, "steps": steps})
        resolved = resolve_plan(plan, columns)
        out.append({"plan": resolved.model_dump(), "note": cand.get("note", "")})
    return out


def _context_prompt(question: str, context: dict[str, Any], prior_plan: dict | None) -> str:
    cols = [
        {"name": c["name"], "label": c.get("label"), "dtype": c.get("dtype"),
         "samples": c.get("samples", [])[:4]}
        for c in context.get("columns", [])
    ]
    parts = [
        f"Question: {question}",
        f"Today's date: {context.get('today', '')}",
        f"Dataset: {context.get('dataset_name', '')}",
        f"Columns: {json.dumps(cols)}",
    ]
    if context.get("glossary"):
        parts.append(f"Glossary (the user's own definitions): {json.dumps(context['glossary'])}")
    if prior_plan:
        parts.append(
            "This is a FOLLOW-UP. Prior plan (modify it rather than starting over "
            f"when the question refers back): {json.dumps(prior_plan)}"
        )
    return "\n".join(parts)


def run_query_planner(
    provider: LLMProvider | None,
    question: str,
    context: dict[str, Any],
    prior_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Returns {mode, plans:[{plan, note}], clarify_question, confidence,
    unresolved_terms, generated_by}. mode='failed' only when even the
    fallback cannot help - with an honest message, never a guess."""
    artifact_id = context.get("artifact_id", "")
    columns = [c["name"] for c in context.get("columns", [])]
    numeric = [c["name"] for c in context.get("columns", [])
               if "int" in str(c.get("dtype", "")) or "float" in str(c.get("dtype", ""))]
    last_error: str | None = None

    if provider is not None:
        prompt = _context_prompt(question, context, prior_plan)
        for attempt in range(2):  # one retry with the validation error appended
            try:
                raw = provider.complete_json(_SYSTEM, prompt, _SCHEMA)
                mode = raw.get("mode", "plan")
                if mode == "clarify":
                    return {
                        "mode": "clarify",
                        "plans": [],
                        "clarify_question": raw.get("clarify_question")
                        or "Which column do you mean?",
                        "confidence": float(raw.get("confidence", 0.0)),
                        "unresolved_terms": raw.get("unresolved_terms", []),
                        "generated_by": "claude",
                    }
                plans = _validate_plans(raw.get("plans", []), artifact_id, columns, numeric)
                if not plans:
                    raise ValueError("planner returned no plans")
                return {
                    "mode": "ambiguous" if (mode == "ambiguous" and len(plans) > 1) else "plan",
                    "plans": plans if mode == "ambiguous" else plans[:1],
                    "clarify_question": None,
                    "confidence": float(raw.get("confidence", 0.0)),
                    "unresolved_terms": raw.get("unresolved_terms", []),
                    "generated_by": "claude",
                }
            except Exception as exc:
                friendly = _translate_error(str(exc)[:400])
                last_error = f"{type(exc).__name__}: {friendly[:300]}"
                if attempt == 0:
                    prompt += (
                        f"\n\nYour previous answer failed validation: {friendly}. "
                        "Correct it: every derive step needs fn (ratio/difference/"
                        "percent_of), every pivot needs left, right AND column, and "
                        "use ONLY the listed column names and compact field names."
                    )
                # fall through to fallback after the retry fails

    # Heuristic fallback (also the no-provider path)
    dtypes = {c["name"]: c.get("dtype", "") for c in context.get("columns", [])}
    raw_plan = fallback_plan(question, columns, dtypes, numeric)
    if raw_plan is not None:
        try:
            raw_plan["source"] = artifact_id
            plans = _validate_plans([{"steps": raw_plan["steps"], "note": ""}],
                                    artifact_id, columns, numeric)
            return {"mode": "plan", "plans": plans, "clarify_question": None,
                    "confidence": 0.5, "unresolved_terms": [], "generated_by": "heuristic"}
        except Exception:
            pass
    return {
        "mode": "clarify",
        "plans": [],
        "clarify_question": (
            "I could not turn that into a data question. Try naming a column and "
            "what to compute - for example 'average <column> by <group>' or "
            "'top 10 <group> by <column>'."
        ),
        "confidence": 0.0,
        "unresolved_terms": [question],
        "generated_by": "heuristic",
        "last_error": last_error,  # diagnostics: why the LLM path gave up
    }
