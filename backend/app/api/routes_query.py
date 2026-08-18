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
from engine.query.executor import QueryExecutionError, execute_plan
from engine.query.plan import QueryPlan, plan_columns
from engine.query.readiness import caveats_for_columns, readiness_audit
from engine.query.resolve import ColumnResolutionError, resolve_plan
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
            findings_raw.append({
                "question": cand["question"],
                "plan": resolved.model_dump(),
                "sentences": describe_plan(resolved, dataset_name=f"'{ds.filename}'")["sentences"],
                "result": result,
                "chart": choose_chart(result, resolved),
                "caveats": caveats,
            })
            store.log_event(
                "Explorer agents", "query_plan", dataset_id=ds.id, mode="fallback",
                payload={"question": cand["question"], "auto": True,
                         "rows_out": result["row_counts"][-1]["rows"]},
            )
    except QueryExecutionError as exc:
        raise HTTPException(400, str(exc)) from exc

    headlines, generated_by = _batch_headlines(findings_raw)
    for f, h in zip(findings_raw, headlines):
        f["headline"] = h
    store.log_event(
        "Explorer agents", "query_execute", dataset_id=ds.id,
        mode="llm" if generated_by == "claude" else "fallback",
        payload={"auto_explore": True, "n_findings": len(findings_raw)},
    )
    return {"findings": findings_raw, "generated_by": generated_by,
            "filename": ds.filename, "artifact_id": ds.artifact_id}


def _batch_headlines(findings: list[dict[str, Any]]) -> tuple[list[str], str]:
    """ONE phrasing call for the whole board - never one per finding."""
    fallbacks = [_template_headline(f["result"]["table"], f["result"]["columns"])
                 for f in findings]
    provider = instrumented_provider()
    if provider is None or not findings:
        return fallbacks, "heuristic"
    try:
        import json as _json

        compact = [{"i": i, "question": f["question"],
                    "table": f["result"]["table"][:8]}
                   for i, f in enumerate(findings)]
        raw = provider.complete_json(
            "You phrase data findings for a government officer. For each item, "
            "write ONE plain sentence using ONLY the numbers in its table - "
            "never compute or invent. Style: plain hyphens only.",
            f"Items: {_json.dumps(compact)}",
            {"type": "object", "properties": {"headlines": {
                "type": "array", "items": {"type": "object", "properties": {
                    "i": {"type": "integer"}, "text": {"type": "string"}},
                    "required": ["i", "text"], "additionalProperties": False}}},
             "required": ["headlines"], "additionalProperties": False},
            max_tokens=1500,
        )
        by_i = {h["i"]: h["text"] for h in raw.get("headlines", [])}
        return [by_i.get(i) or fb for i, fb in enumerate(fallbacks)], "claude"
    except Exception:
        return fallbacks, "heuristic"


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
    items: list[dict[str, Any]]  # {question, headline, sentences, table}


@router.post("/datasets/{dataset_id}/explore/export")
def export_board(dataset_id: str, req: BoardExportRequest):
    """Download the findings board as markdown; export logged."""
    from fastapi.responses import Response

    ds = _gated_dataset(dataset_id)
    lines = [f"# Initial findings - {ds.filename}", ""]
    for item in req.items[:12]:
        lines.append(f"## {str(item.get('question', ''))[:200]}")
        if item.get("headline"):
            lines.append(f"**{str(item['headline'])[:400]}**")
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
