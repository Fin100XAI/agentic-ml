"""Query path endpoints: plan a question, show the interpretation, run it.

Rule 12: plans are returned WITH their plain-language interpretation and
nothing executes until the user runs the shown plan. Rule 13: every
answer carries caveats from the same health/readiness machinery as the
ML path. All events land in the unified activity log (additive types
query_plan / query_execute).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.store import store
from app.telemetry import instrumented_provider
from engine.agents.query_planner import run_query_planner
from engine.query.describe import describe_plan
from engine.query.diff import diff_plans
from engine.query.executor import QueryExecutionError, execute_plan
from engine.query.routing import classify_route
from engine.query.plan import QueryPlan, plan_columns
from engine.query.readiness import caveats_for_columns, readiness_audit
from engine.query.resolve import ColumnResolutionError, resolve_plan
from engine.query.signals import finding_signals, plain_meaning, plain_synthesis
from engine.query.starter import starter_questions
from engine.query.vizmap import choose_chart

router = APIRouter()


class PlanRequest(BaseModel):
    question: str
    prior_plan: dict[str, Any] | None = None


class RunRequest(BaseModel):
    plan: dict[str, Any]
    question: str = ""


class RouteChoiceRequest(BaseModel):
    choice: str  # "direct_query" | "model"


def _gated_dataset(dataset_id: str):
    try:
        ds = store.get_dataset(dataset_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    if ds.pii and ds.pii.get("status") == "pending":
        raise HTTPException(409, "PII review pending on this dataset - approve its privacy screen first.")
    return ds


def _context_for(ds) -> dict[str, Any]:
    from datetime import date

    cols = []
    for c in ds.df.columns:
        s = ds.df[c]
        samples: list[Any] = []
        if s.dtype == object:
            samples = [str(v) for v in s.dropna().unique()[:4]]
        cols.append({"name": str(c), "label": str(c), "dtype": str(s.dtype), "samples": samples})
    glossary = store.glossary_for_columns(ds.project_id, [str(c) for c in ds.df.columns])
    return {
        "artifact_id": ds.artifact_id or ds.id,
        "dataset_name": ds.filename,
        "today": date.today().isoformat(),
        "columns": cols,
        "glossary": glossary,
    }


@router.post("/datasets/{dataset_id}/query/plan")
def plan_question(dataset_id: str, req: PlanRequest) -> dict:
    ds = _gated_dataset(dataset_id)
    provider = instrumented_provider()
    result = run_query_planner(provider, req.question, _context_for(ds), req.prior_plan)
    # Rule 12: every candidate ships with its exact interpretation.
    for cand in result["plans"]:
        plan = QueryPlan.model_validate(cand["plan"])
        desc = describe_plan(plan, dataset_name=f"'{ds.filename}'")
        cand["sentences"] = desc["sentences"]
        cand["term_glossary"] = desc["glossary"]
        # Follow-up: what changed vs the prior plan, computed deterministically.
        # Silent drops (a lost filter) are the main wrong-answer risk.
        if req.prior_plan:
            cand["changes"] = diff_plans(req.prior_plan, cand["plan"])
    # A follow-up that is really a prediction question gets the honest
    # route suggestion - phrased as good news, not an error. Only a POSITIVE
    # prediction signal counts here: a terse phrase like "only scheme A"
    # matching nothing must not read as "needs a model".
    route_info = classify_route(req.question)
    if route_info["route"] == "model_needed" and not route_info.get("model_signal"):
        route_info = {"route": "direct_query", "route_reasoning": ""}
    result["route"] = route_info["route"]
    result["route_reasoning"] = route_info["route_reasoning"]
    store.log_event(
        "Query planner", "query_plan", dataset_id=ds.id,
        mode="llm" if result["generated_by"] == "claude" else "fallback",
        payload={"question": req.question[:300], "mode": result["mode"],
                 "n_plans": len(result["plans"]),
                 "unresolved": result.get("unresolved_terms", [])[:5]},
    )
    return result


@router.post("/datasets/{dataset_id}/query/run")
def run_question(dataset_id: str, req: RunRequest) -> dict:
    ds = _gated_dataset(dataset_id)
    try:
        plan = QueryPlan.model_validate(req.plan)
        resolved = resolve_plan(plan, [str(c) for c in ds.df.columns])
    except ColumnResolutionError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"That plan is not valid: {exc}") from exc

    # Running the shown plan IS the approval (rule 12).
    store.log_event("user", "approval", dataset_id=ds.id,
                    payload={"gate": "query_run", "question": req.question[:300]})
    try:
        result = execute_plan(resolved, ds.df)
    except QueryExecutionError as exc:
        raise HTTPException(400, str(exc)) from exc

    used = plan_columns(resolved)
    caveats: list[str] = list(result["coverage_notes"])
    for alias, n in result["excluded_null_rows"].items():
        caveats.append(f"{n} empty row(s) were left out of '{alias}'.")
    # Readiness caveats (rule 13): unfixed findings touching used columns.
    try:
        findings = readiness_audit(ds.df)["findings"]
        caveats += caveats_for_columns(findings, used)
    except Exception:
        pass
    # Missingness on used columns, same thresholds as the health screen.
    for col in dict.fromkeys(used):
        if col in ds.df.columns:
            pct = float(ds.df[col].isna().mean() * 100)
            if pct > 5:
                caveats.append(f"'{col}' is {pct:.0f}% empty - answers using it cover only the filled rows.")

    headline, generated_by = _headline(req.question, resolved, result)
    store.log_event(
        "Query engine", "query_execute", dataset_id=ds.id,
        mode="llm" if generated_by == "claude" else "fallback",
        payload={"rows_in": result["row_counts"][0]["rows"],
                 "rows_out": result["row_counts"][-1]["rows"],
                 "steps": len(resolved.steps)},
    )
    sentences = describe_plan(resolved, dataset_name=f"'{ds.filename}'")["sentences"]
    return {
        "result": result,
        "headline": headline,
        "generated_by": generated_by,
        "caveats": caveats,
        "sentences": sentences,
        # Chart chosen deterministically from the result shape (rule 14).
        "chart": choose_chart(result, resolved),
        "plan": resolved.model_dump(),
        "artifact_id": ds.artifact_id,
        "filename": ds.filename,
    }


def _headline(question: str, plan: QueryPlan, result: dict[str, Any]) -> tuple[str, str]:
    """One phrasing call; templated fallback. Never invents a number."""
    table = result["table"]
    fallback = _template_headline(table, result["columns"])
    provider = instrumented_provider()
    if provider is None or not table:
        return fallback, "heuristic"
    try:
        import json as _json

        text = provider.complete_text(
            "You phrase a data query answer in 1-2 plain sentences for a "
            "government officer. Use ONLY the numbers in the table - never "
            "compute or invent new ones. Style: plain hyphens only.",
            f"Question: {question}\nAnswer table (first rows): "
            f"{_json.dumps(table[:12])}\nRow count: {len(table)}",
            max_tokens=200,
        )
        return text.strip(), "claude"
    except Exception:
        return fallback, "heuristic"


def _template_headline(table: list[dict], columns: list[str]) -> str:
    if not table:
        return "No rows match."
    if len(table) == 1 and len(columns) == 1:
        k = columns[0]
        return f"{k}: {table[0][k]}"
    first = table[0]
    summary = ", ".join(f"{k}: {v}" for k, v in list(first.items())[:3])
    return f"{len(table)} row(s). First: {summary}."


@router.get("/datasets/{dataset_id}/overview")
def dataset_overview(dataset_id: str) -> dict:
    """Data description for the analytics path: the same profiler the ML
    path uses (roles, missingness, distributions, top values) - computed
    in Python, no AI involved."""
    from engine.profiler import profile_dataframe

    ds = _gated_dataset(dataset_id)
    prof = profile_dataframe(ds.df)
    store.log_event("Profiler", "profile", dataset_id=ds.id, mode="fallback",
                    payload={"context": "analytics_overview"})
    return {"profile": prof, "filename": ds.filename}


@router.post("/datasets/{dataset_id}/explore")
def auto_explore(dataset_id: str) -> dict:
    """The exploring agents: starter questions asked AND answered before the
    user types anything. Plans are generated deterministically from the
    schema and run through the same executor as user questions; ONE batched
    LLM call phrases the findings (templated fallback). Every finding is
    individually logged."""
    ds = _gated_dataset(dataset_id)
    try:
        findings_raw = []
        readiness = readiness_audit(ds.df)["findings"]
        for cand in starter_questions(ds.df, ds.artifact_id or ds.id):
            try:
                plan = QueryPlan.model_validate(cand["plan"])
                resolved = resolve_plan(plan, [str(c) for c in ds.df.columns])
                result = execute_plan(resolved, ds.df)
            except Exception:
                continue  # one broken starter must not sink the board
            used = plan_columns(resolved)
            caveats = list(result["coverage_notes"])
            caveats += caveats_for_columns(readiness, used)
            chart = choose_chart(result, resolved)
            findings_raw.append({
                "question": cand["question"],
                "plan": resolved.model_dump(),
                "sentences": describe_plan(resolved, dataset_name=f"'{ds.filename}'")["sentences"],
                "result": result,
                "chart": chart,
                "caveats": caveats,
                # Facts for the analyst agent - computed here, never by the LLM.
                "signals": finding_signals(result, chart),
            })
            store.log_event(
                "Explorer agents", "query_plan", dataset_id=ds.id, mode="fallback",
                payload={"question": cand["question"], "auto": True,
                         "rows_out": result["row_counts"][-1]["rows"]},
            )
    except QueryExecutionError as exc:
        raise HTTPException(400, str(exc)) from exc

    narrative = _batch_narrative(findings_raw)
    for f, h, m in zip(findings_raw, narrative["headlines"], narrative["meanings"]):
        f["headline"] = h
        f["meaning"] = m
    generated_by = narrative["generated_by"]
    store.log_event(
        "Explorer agents", "query_execute", dataset_id=ds.id,
        mode="llm" if generated_by == "claude" else "fallback",
        payload={"auto_explore": True, "n_findings": len(findings_raw)},
    )
    return {"findings": findings_raw, "generated_by": generated_by,
            "synthesis": narrative["synthesis"],
            "filename": ds.filename, "artifact_id": ds.artifact_id}


def _batch_narrative(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """The analyst agent: ONE call for the whole board covering headlines,
    per-finding meanings, and the overall takeaway. Every number it may use
    is precomputed (tables + signals); templated fallbacks use the same."""
    fb_headlines = [_template_headline(f["result"]["table"], f["result"]["columns"])
                    for f in findings]
    fb_meanings = [plain_meaning(f.get("signals", {})) for f in findings]
    fb_synthesis = plain_synthesis(findings)
    fallback = {"headlines": fb_headlines, "meanings": fb_meanings,
                "synthesis": fb_synthesis, "generated_by": "heuristic"}
    provider = instrumented_provider()
    if provider is None or not findings:
        return fallback
    try:
        import json as _json

        compact = [{"i": i, "question": f["question"],
                    "table": f["result"]["table"][:8],
                    "signals": f.get("signals", {})}
                   for i, f in enumerate(findings)]
        raw = provider.complete_json(
            "You are a data analyst explaining findings to a government "
            "officer with no statistics background. For each item: 'text' is "
            "ONE plain sentence stating the finding, and 'meaning' is 1-2 "
            "sentences on what to infer or check next. Use ONLY numbers "
            "present in the item's table or signals - NEVER compute new ones. "
            "Note honest limits (a gap is not proof of cause). 'synthesis' is "
            "2-3 sentences: the overall story across all items plus ONE "
            "suggested next question. Style: plain hyphens only, no jargon.",
            f"Items: {_json.dumps(compact)}",
            {"type": "object", "properties": {
                "headlines": {"type": "array", "items": {
                    "type": "object", "properties": {
                        "i": {"type": "integer"}, "text": {"type": "string"},
                        "meaning": {"type": "string"}},
                    "required": ["i", "text", "meaning"],
                    "additionalProperties": False}},
                "synthesis": {"type": "string"}},
             "required": ["headlines", "synthesis"],
             "additionalProperties": False},
            max_tokens=3000,
        )
        by_i = {h["i"]: h for h in raw.get("headlines", [])}
        return {
            "headlines": [by_i.get(i, {}).get("text") or fb
                          for i, fb in enumerate(fb_headlines)],
            "meanings": [by_i.get(i, {}).get("meaning") or fb
                         for i, fb in enumerate(fb_meanings)],
            "synthesis": raw.get("synthesis") or fb_synthesis,
            "generated_by": "claude",
        }
    except Exception:
        return fallback


@router.post("/datasets/{dataset_id}/query/export")
def export_answer(dataset_id: str, req: RunRequest):
    """Download an answer as CSV: the plan re-executes (deterministic, same
    numbers) and the export is logged like every other export."""
    from fastapi.responses import Response

    ds = _gated_dataset(dataset_id)
    try:
        plan = QueryPlan.model_validate(req.plan)
        resolved = resolve_plan(plan, [str(c) for c in ds.df.columns])
        result = execute_plan(resolved, ds.df)
    except (ColumnResolutionError, QueryExecutionError) as exc:
        raise HTTPException(400, str(exc)) from exc
    import pandas as pd

    csv_bytes = pd.DataFrame(result["table"]).to_csv(index=False).encode("utf-8-sig")
    store.log_event("user", "export", dataset_id=ds.id,
                    payload={"format": "csv", "kind": "query_answer",
                             "question": req.question[:200],
                             "rows": len(result["table"])})
    return Response(
        content=csv_bytes, media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="answer.csv"'},
    )


class BoardExportRequest(BaseModel):
    items: list[dict[str, Any]]  # {question, headline, meaning, sentences, table}
    synthesis: str = ""


@router.post("/datasets/{dataset_id}/explore/export")
def export_board(dataset_id: str, req: BoardExportRequest):
    """Download the findings board as markdown; export logged."""
    from fastapi.responses import Response

    ds = _gated_dataset(dataset_id)
    lines = [f"# Initial findings - {ds.filename}", ""]
    if req.synthesis:
        lines += ["## What to take away", str(req.synthesis)[:800], ""]
    for item in req.items[:12]:
        lines.append(f"## {str(item.get('question', ''))[:200]}")
        if item.get("headline"):
            lines.append(f"**{str(item['headline'])[:400]}**")
        if item.get("meaning"):
            lines.append(f"_{str(item['meaning'])[:500]}_")
        lines.append("")
        for s in (item.get("sentences") or [])[:12]:
            lines.append(f"- {str(s)[:200]}")
        table = item.get("table") or []
        if table:
            cols = list(table[0].keys())
            lines.append("")
            lines.append("| " + " | ".join(cols) + " |")
            lines.append("|" + "---|" * len(cols))
            for row in table[:50]:
                lines.append("| " + " | ".join(str(row.get(c, "")) for c in cols) + " |")
        lines.append("")
    lines.append("_Every number computed deterministically from the data; "
                 "plans and row counts are in the activity log._")
    store.log_event("user", "export", dataset_id=ds.id,
                    payload={"format": "markdown", "kind": "explore_board",
                             "n_items": len(req.items)})
    return Response(
        content="\n".join(lines).encode("utf-8"),
        media_type="text/markdown",
        headers={"Content-Disposition": 'attachment; filename="initial-findings.md"'},
    )


@router.post("/datasets/{dataset_id}/path-choice")
def path_choice(dataset_id: str, req: RouteChoiceRequest) -> dict:
    """The post-upload fork decision is a logged approval."""
    ds = _gated_dataset(dataset_id)
    store.log_event("user", "approval", dataset_id=ds.id,
                    payload={"gate": "path", "choice": req.choice})
    return {"ok": True}


@router.post("/runs/{run_id}/route-choice")
def route_choice(run_id: str, req: RouteChoiceRequest) -> dict:
    """The direction-stage routing decision is a logged approval."""
    try:
        run = store.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    store.log_event(
        "user", "approval", run_id=run.id, dataset_id=run.dataset_id,
        payload={"gate": "route", "choice": req.choice},
    )
    return {"ok": True}
