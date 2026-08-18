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
from engine.query.plan import AggregateStep, GroupByStep, QueryPlan, plan_columns
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
    # Attach the dataset context so every LLM call in this request logs its
    # token counts AGAINST THIS PROJECT - without this, analytics-path agent
    # calls were orphaned and invisible in the project activity log.
    from app.telemetry import current_dataset_id
    current_dataset_id.set(ds.id)
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
    caveats += _small_group_caveats(ds.df, resolved)
    chart_spec = choose_chart(result, resolved)
    _attach_map(chart_spec, result, caveats)

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
        "chart": chart_spec,
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


def _attach_map(chart: dict[str, Any], result: dict[str, Any],
                caveats: list[str]) -> None:
    """Offer a map view when the keys match a bundled boundary set (rule 14:
    deterministic offer, chart stays the default). Unmatched names are
    counted honestly in the caveats."""
    if chart.get("kind") not in ("hbar", "bar", "table") or not chart.get("x") \
            or not chart.get("y"):
        return
    from engine.query.geo import match_level
    keys = [str(r.get(chart["x"])) for r in result["table"]]
    m = match_level(keys)
    if not m:
        return
    # Coloring mode, decided deterministically from the result:
    # - mixed signs (a change metric) -> diverging around zero
    # - a below-threshold selection -> judgment (flagged areas in amber)
    # - otherwise -> sequential intensity with quantile classes
    y = (chart.get("y") or [None])[0]
    vals = [r.get(y) for r in result["table"]
            if isinstance(r.get(y), (int, float)) and not isinstance(r.get(y), bool)]
    if vals and min(vals) < 0 < max(vals):
        mode = "diverging"
    elif chart.get("threshold") is not None and chart.get("threshold_dir") == "below":
        mode = "judgment"
    else:
        mode = "sequential"
    chart["map"] = {"level": m["level"], "match_pct": m["match_pct"],
                    "matches": m["matches"], "unmatched": m["unmatched"],
                    "mode": mode}
    if m["unmatched"]:
        names = ", ".join(m["unmatched"][:3])
        caveats.append(f"{len(m['unmatched'])} area(s) could not be matched to "
                       f"the map ({names}) - they appear in the chart and table "
                       f"but not on the map.")


def _small_group_caveats(df, resolved: QueryPlan) -> list[str]:
    """Averages over tiny groups mislead - say so (small-sample honesty)."""
    group_cols = next((s.columns for s in resolved.steps
                       if isinstance(s, GroupByStep)), None)
    has_avg = any(isinstance(s, AggregateStep) and s.fn in ("mean", "median")
                  for s in resolved.steps)
    if not group_cols or not has_avg:
        return []
    cols = [c for c in group_cols if c in df.columns]
    if not cols:
        return []
    sizes = df.groupby(cols, dropna=False).size()
    tiny = sizes[sizes < 5]
    if tiny.empty:
        return []
    names = ", ".join(str(k) for k in list(tiny.index)[:4])
    return [f"{len(tiny)} group(s) have fewer than 5 records ({names}) - "
            f"their averages can swing on a single row, compare with care."]


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


@router.get("/datasets/{dataset_id}/domains")
def dataset_domains(dataset_id: str) -> dict:
    """Domain scout: group a wide file's columns into topics the user can
    choose between ("literacy", "workers", "amenities"). The LLM judges the
    grouping (its proper role); the token heuristic is the fallback; either
    way only real column names survive validation, and the suggested focus
    is computed deterministically from variability."""
    from engine.query.domains import (heuristic_domains, suggest_domain,
                                      validate_domains)

    ds = _gated_dataset(dataset_id)
    columns = [str(c) for c in ds.df.columns]
    domains = heuristic_domains(columns)
    generated_by = "heuristic"
    provider = instrumented_provider()
    if provider is not None and len(columns) >= 8:
        try:
            import json as _json

            raw = provider.complete_json(
                "Group these dataset columns into 3-8 topical domains a "
                "government analyst would recognize (e.g. literacy, workers, "
                "amenities, demographics). Use ONLY the exact column names "
                "given. Short plain names; one sentence why per domain. "
                "Leave out identifier/name columns.",
                f"Columns: {_json.dumps(columns)}",
                {"type": "object", "properties": {"domains": {
                    "type": "array", "items": {"type": "object", "properties": {
                        "name": {"type": "string"},
                        "columns": {"type": "array", "items": {"type": "string"}},
                        "why": {"type": "string"}},
                        "required": ["name", "columns", "why"],
                        "additionalProperties": False}}},
                 "required": ["domains"], "additionalProperties": False},
                max_tokens=2500,
            )
            validated = validate_domains(raw.get("domains", []), columns)
            if validated:
                domains = validated
                generated_by = "claude"
        except Exception:
            pass
    suggested = suggest_domain(domains, ds.df)
    store.log_event("Domain scout", "profile", dataset_id=ds.id,
                    mode="llm" if generated_by == "claude" else "fallback",
                    payload={"context": "domains", "n_domains": len(domains),
                             "suggested": suggested})
    return {"domains": domains, "suggested": suggested,
            "generated_by": generated_by}


@router.post("/datasets/{dataset_id}/explore")
def auto_explore(dataset_id: str, lang: str = "en", focus: str = "") -> dict:
    """The exploring agents: starter questions asked AND answered before the
    user types anything. Plans are generated deterministically from the
    schema and run through the same executor as user questions; ONE batched
    LLM call phrases the findings (templated fallback). Every finding is
    individually logged."""
    from engine.query.shape import classify_shape

    ds = _gated_dataset(dataset_id)
    focus_columns = [c for c in focus.split("|") if c] if focus else None
    # Shape Scout first: WHAT KIND of dataset is this? The classification is
    # deterministic, shown on the board, and steers which questions lead.
    shape = classify_shape(ds.df)
    source = ds.artifact_id or ds.id
    # Question Scout (general mode): the LLM chooses WHICH columns are worth
    # asking about from a fixed template menu - diversity across topics is
    # its brief, and the validator enforces it regardless. Plans are built
    # deterministically; the fallback is the hand-written starter list.
    questions_by = "heuristic"
    candidates = None
    if not focus_columns:
        candidates = _question_scout(ds, shape, source)
        if candidates:
            questions_by = "claude"
    if not candidates:
        candidates = starter_questions(ds.df, source,
                                       focus_columns=focus_columns, shape=shape)
    try:
        findings_raw = []
        readiness = readiness_audit(ds.df)["findings"]
        for cand in candidates:
            try:
                plan = QueryPlan.model_validate(cand["plan"])
                resolved = resolve_plan(plan, [str(c) for c in ds.df.columns])
                result = execute_plan(resolved, ds.df)
            except Exception:
                continue  # one broken starter must not sink the board
            used = plan_columns(resolved)
            caveats = list(result["coverage_notes"])
            caveats += caveats_for_columns(readiness, used)
            caveats += _small_group_caveats(ds.df, resolved)
            chart = choose_chart(result, resolved)
            _attach_map(chart, result, caveats)
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

    narrative = _batch_narrative(findings_raw, lang)
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
            "questions_by": questions_by,
            "shape": {"shape": shape["shape"], "label": shape["label"],
                      "reasoning": shape["reasoning"]},
            "filename": ds.filename, "artifact_id": ds.artifact_id}


def _question_scout(ds, shape: dict[str, Any], source: str) -> list[dict[str, Any]] | None:
    """ONE LLM call choosing template+column selections; validated and built
    deterministically. Returns None when unavailable or too thin (the
    deterministic starters then take over). Wide datasets benefit most."""
    from engine.query.domains import heuristic_domains
    from engine.query.starter import SCOUT_TEMPLATES, starters_from_selections

    provider = instrumented_provider()
    if provider is None or ds.df.shape[1] < 6:
        return None
    try:
        import json as _json

        cols_ctx = []
        for c in ds.df.columns:
            s = ds.df[c]
            samples = ([str(v) for v in s.dropna().unique()[:3]]
                       if s.dtype == object else [])
            cols_ctx.append({"name": str(c), "dtype": str(s.dtype),
                             "samples": samples})
        domains = heuristic_domains([str(c) for c in ds.df.columns])
        raw = provider.complete_json(
            "You choose the OPENING questions for a government data board by "
            "filling a fixed template menu - you never write queries. "
            f"Templates: {', '.join(SCOUT_TEMPLATES)}. Each selection names a "
            "template plus real column names: metric (numeric), group "
            "(categorical), second_metric (relationship only). Pick 8-9 "
            "selections that SPREAD across the dataset's different topics - "
            "at most 2 selections per metric, at least 4 distinct metrics "
            "from DIFFERENT topics when available. Prefer headline measures "
            "an administrator cares about over obscure ones. Use exact "
            "column names in the column fields; in 'question' write the "
            "question as a government officer would naturally ask it - plain "
            "words, no raw column names, must mean exactly what the template "
            "computes.",
            f"Dataset shape: {shape['label']}\n"
            f"Topic groups: {_json.dumps([{d['name']: d['columns'][:6]} for d in domains])}\n"
            f"Columns: {_json.dumps(cols_ctx)}",
            {"type": "object", "properties": {"selections": {
                "type": "array", "items": {"type": "object", "properties": {
                    "template": {"type": "string"},
                    "metric": {"type": "string"},
                    "group": {"type": "string"},
                    "second_metric": {"type": "string"},
                    "question": {"type": "string"}},
                    "required": ["template", "metric", "group",
                                 "second_metric", "question"],
                    "additionalProperties": False}}},
             "required": ["selections"], "additionalProperties": False},
            max_tokens=2500,
        )
        built = starters_from_selections(raw.get("selections", []), ds.df, source)
        # Too thin a result means the scout misfired - fall back honestly.
        return built if len(built) >= 4 else None
    except Exception:
        return None


_LANGS = {"hi": "Hindi (Devanagari script)", "mr": "Marathi (Devanagari script)"}


def _batch_narrative(findings: list[dict[str, Any]], lang: str = "en") -> dict[str, Any]:
    """The analyst agent: ONE call for the whole board covering headlines,
    per-finding meanings, and the overall takeaway. Every number it may use
    is precomputed (tables + signals); templated fallbacks use the same.
    lang: hi/mr writes the phrasing in that language (AI only - the
    templated fallback stays English, honestly badged as heuristic)."""
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
        lang_note = (f" Write ALL text in {_LANGS[lang]} - keep column names "
                     f"and numbers as they are." if lang in _LANGS else "")
        raw = provider.complete_json(
            "You are a data analyst explaining findings to a government "
            "officer with no statistics background. For each item: 'text' is "
            "ONE plain sentence stating the finding, and 'meaning' is 1-2 "
            "sentences on what to infer or check next. Use ONLY numbers "
            "present in the item's table or signals - NEVER compute new ones. "
            "Note honest limits (a gap is not proof of cause). 'synthesis' is "
            "2-3 sentences: the overall story across all items plus ONE "
            "suggested next question. Style: plain hyphens only, no jargon."
            + lang_note,
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


class BriefRequest(BaseModel):
    items: list[dict[str, Any]]  # {question, plan, headline?, meaning?}
    takeaway: str = ""
    title: str = ""


@router.post("/datasets/{dataset_id}/query/brief")
def create_query_brief(dataset_id: str, req: BriefRequest) -> dict:
    """Build a Query Decision Brief (P2.4): re-execute every included plan,
    verify every phrased claim with the deterministic critic, attach the
    data-trust panel, store, and log. No stability tier - nothing was modeled."""
    import uuid
    from datetime import datetime, timezone

    from engine.query.brief import brief_markdown, verify_claim

    ds = _gated_dataset(dataset_id)
    readiness = readiness_audit(ds.df)["findings"]
    items_out: list[dict[str, Any]] = []
    flagged = 0
    used_all: list[str] = []
    for raw in req.items[:12]:
        try:
            plan = QueryPlan.model_validate(raw["plan"])
            resolved = resolve_plan(plan, [str(c) for c in ds.df.columns])
            result = execute_plan(resolved, ds.df)
        except (KeyError, ColumnResolutionError, QueryExecutionError) as exc:
            raise HTTPException(400, f"A brief item failed to recompute: {exc}") from exc
        chart = choose_chart(result, resolved)
        signals = finding_signals(result, chart)
        used = plan_columns(resolved)
        used_all += used
        caveats = list(result["coverage_notes"]) + caveats_for_columns(readiness, used)
        headline = str(raw.get("headline") or "")
        review = verify_claim(headline, result["table"], signals,
                              result["row_counts"]) if headline else {"verified": False,
                                                                      "unmatched_numbers": []}
        if not headline or not review["verified"]:
            # The critic wins: unverifiable phrasing is replaced by a
            # computed restatement.
            headline = _template_headline(result["table"], result["columns"])
            if raw.get("headline"):
                flagged += 1
        meaning = str(raw.get("meaning") or "")
        if meaning and not verify_claim(meaning, result["table"], signals,
                                        result["row_counts"])["verified"]:
            meaning = plain_meaning(signals)
        items_out.append({
            "question": str(raw.get("question", ""))[:300],
            "plan": resolved.model_dump(),
            "headline": headline,
            "meaning": meaning or plain_meaning(signals),
            "sentences": describe_plan(resolved, dataset_name=f"'{ds.filename}'")["sentences"],
            "table": result["table"][:50],
            "columns": result["columns"],
            "chart": chart,
            "caveats": caveats,
            "signals": signals,
            "review": review,
            "row_counts": result["row_counts"],
        })

    trust_lines = [
        f"Source rows: {len(ds.df):,} in {ds.filename}.",
    ]
    for col in dict.fromkeys(used_all):
        if col in ds.df.columns:
            pct = float(ds.df[col].isna().mean() * 100)
            if pct > 0:
                trust_lines.append(f"'{col}' is {pct:.0f}% empty - answers using it "
                                   f"cover only the filled rows.")
    for f in readiness[:5]:
        trust_lines.append(f.get("message") or str(f.get("kind")))
    if len(trust_lines) == 1:
        trust_lines.append("No missing-data or readiness issues touch the columns used.")

    takeaway = str(req.takeaway or "")
    brief_id = uuid.uuid4().hex[:12]
    brief = {
        "id": brief_id,
        "title": (req.title or f"Data findings - {ds.filename}")[:120],
        "dataset_id": ds.id,
        "filename": ds.filename,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "takeaway": takeaway,
        "items": items_out,
        "trust": {
            "lines": trust_lines,
            "scope_note": "This panel covers data quality only. No model was "
                          "trained for these answers, so no stability or "
                          "model-trust tier applies - and none is implied.",
        },
        "provenance": {
            "dataset_id": ds.id,
            "artifact_id": ds.artifact_id,
            "generated_by": "claude" if instrumented_provider() is not None else "heuristic",
        },
        "critic": {"flagged_claims": flagged, "checked": len(items_out)},
    }
    store.save_query_brief(brief_id, ds.id, ds.project_id, brief["created_at"], brief)
    store.log_event("Critic", "query_execute", dataset_id=ds.id, mode="fallback",
                    payload={"query_brief": brief_id, "claims_checked": len(items_out),
                             "claims_flagged": flagged})
    store.log_event("user", "export", dataset_id=ds.id,
                    payload={"format": "brief", "kind": "query_brief",
                             "brief_id": brief_id, "n_items": len(items_out)})
    return {"brief_id": brief_id, "brief": brief,
            "markdown": brief_markdown(brief)}


@router.get("/query-briefs/{brief_id}")
def get_query_brief(brief_id: str) -> dict:
    try:
        return store.get_query_brief(brief_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/query-briefs/{brief_id}/markdown")
def get_query_brief_markdown(brief_id: str):
    from fastapi.responses import Response

    from engine.query.brief import brief_markdown
    try:
        brief = store.get_query_brief(brief_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    return Response(content=brief_markdown(brief).encode("utf-8"),
                    media_type="text/markdown",
                    headers={"Content-Disposition": 'attachment; filename="query-brief.md"'})


@router.get("/query-briefs/{brief_id}/pdf")
def get_query_brief_pdf(brief_id: str):
    from fastapi.responses import Response

    from app.pdf_report import markdown_to_pdf
    from engine.query.brief import brief_markdown
    try:
        brief = store.get_query_brief(brief_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    store.log_event("user", "export", dataset_id=brief.get("dataset_id"),
                    payload={"format": "pdf", "kind": "query_brief",
                             "brief_id": brief_id})
    return Response(content=markdown_to_pdf(brief_markdown(brief)),
                    media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="query-brief.pdf"'})


@router.get("/geo/{level}")
def get_boundaries(level: str):
    """Serve the bundled boundary file (Datameet community maps, CC-BY 4.0,
    simplified). Local file - the air-gap rule holds."""
    from fastapi.responses import FileResponse

    from engine.query.geo import geojson_path
    path = geojson_path(level)
    if path is None:
        raise HTTPException(404, f"No bundled boundary set called '{level}'.")
    return FileResponse(path, media_type="application/geo+json",
                        headers={"Cache-Control": "max-age=86400"})


@router.get("/datasets/{dataset_id}/number-check")
def number_check(dataset_id: str) -> dict:
    """Scan for numbers stored as text - proposals only, nothing applies
    without approval."""
    from engine.query.textnum import detect_text_numbers

    ds = _gated_dataset(dataset_id)
    proposals = detect_text_numbers(ds.df)
    if proposals:
        store.log_event("Number repair", "profile", dataset_id=ds.id,
                        mode="fallback",
                        payload={"context": "number_check",
                                 "n_columns": len(proposals)})
    return {"columns": proposals}


class FixNumbersRequest(BaseModel):
    columns: list[str]


@router.post("/datasets/{dataset_id}/fix-numbers")
def fix_numbers(dataset_id: str, req: FixNumbersRequest) -> dict:
    """Apply an APPROVED text-to-number conversion as a derived artifact.
    The original file never changes; every previously invisible measure
    becomes explorable."""
    import pandas as pd

    from engine.query.textnum import apply_text_number_fix

    ds = _gated_dataset(dataset_id)
    columns = [c for c in req.columns if c in ds.df.columns
               and ds.df[c].dtype == object]
    if not columns:
        raise HTTPException(400, "Nothing to convert - no matching text columns.")
    fixed = apply_text_number_fix(ds.df, columns)
    art = store.add_derived_artifact(
        fixed, [ds.artifact_id] if ds.artifact_id else [],
        "fix_text_numbers", {"columns": columns},
        project_id=ds.project_id,
    )
    ds.df = fixed
    ds.artifact_id = art.id
    store.update_dataset(ds)
    store.log_event("user", "approval", dataset_id=ds.id,
                    payload={"gate": "fix_text_numbers", "n_columns": len(columns)})
    store.log_event("user", "transform", dataset_id=ds.id, artifact_id=art.id,
                    payload={"action": "fix_text_numbers", "columns": columns})
    n_numeric = sum(1 for c in ds.df.columns
                    if pd.api.types.is_numeric_dtype(ds.df[c]))
    return {"ok": True, "artifact_id": art.id, "converted": len(columns),
            "numeric_columns_now": n_numeric}


@router.get("/datasets/{dataset_id}/place-check")
def place_check(dataset_id: str) -> dict:
    """The Place Harmonizer's scan: layered deterministic detection of place
    names written differently (case, official renames, close spellings,
    learned project aliases). Proposals only - nothing applies without
    approval."""
    from engine.query.places import MAX_LEVELS, detect_place_variants

    ds = _gated_dataset(dataset_id)
    project_aliases = store.get_place_aliases(ds.project_id)
    columns_out = []
    for col in ds.df.columns:
        s = ds.df[col]
        if s.dtype != object:
            continue
        n_unique = s.nunique(dropna=True)
        if not 2 <= n_unique <= MAX_LEVELS:
            continue
        proposals = detect_place_variants(s, project_aliases)
        if proposals:
            columns_out.append({"column": str(col), "proposals": proposals})
    if columns_out:
        store.log_event(
            "Place harmonizer", "profile", dataset_id=ds.id, mode="fallback",
            payload={"context": "place_check",
                     "n_proposals": sum(len(c["proposals"]) for c in columns_out)},
        )
    return {"columns": columns_out}


class HarmonizeRequest(BaseModel):
    column: str
    mapping: dict[str, str]  # variant -> canonical


@router.post("/datasets/{dataset_id}/harmonize")
def harmonize_places(dataset_id: str, req: HarmonizeRequest) -> dict:
    """Apply an APPROVED place-name mapping as a derived artifact (the
    original never changes) and remember the aliases for future files."""
    from engine.query.places import apply_place_mapping

    ds = _gated_dataset(dataset_id)
    if req.column not in ds.df.columns:
        raise HTTPException(400, f"No column called '{req.column}'.")
    mapping = {str(k): str(v).strip() for k, v in req.mapping.items()
               if str(v).strip() and str(k) != str(v).strip()}
    if not mapping:
        raise HTTPException(400, "Nothing to merge - the mapping is empty.")
    harmonized = apply_place_mapping(ds.df, req.column, mapping)
    art = store.add_derived_artifact(
        harmonized, [ds.artifact_id] if ds.artifact_id else [],
        "harmonize_places", {"column": req.column, "mapping": mapping},
        project_id=ds.project_id,
    )
    ds.df = harmonized
    ds.artifact_id = art.id
    store.update_dataset(ds)
    store.save_place_aliases(ds.project_id, mapping)
    store.log_event("user", "approval", dataset_id=ds.id,
                    payload={"gate": "harmonize_places", "column": req.column,
                             "n_merged": len(mapping)})
    store.log_event("user", "transform", dataset_id=ds.id, artifact_id=art.id,
                    payload={"action": "harmonize_places", "column": req.column,
                             "mapping": mapping})
    return {"ok": True, "artifact_id": art.id,
            "distinct_after": int(ds.df[req.column].nunique(dropna=True))}


@router.post("/datasets/{dataset_id}/path-choice")
def path_choice(dataset_id: str, req: RouteChoiceRequest) -> dict:
    """The post-upload fork decision is a logged approval."""
    ds = _gated_dataset(dataset_id)
    store.log_event("user", "approval", dataset_id=ds.id,
                    payload={"gate": "path", "choice": req.choice})
    return {"ok": True}


class SaveQueryRequest(BaseModel):
    name: str
    plan: dict[str, Any]
    question: str = ""


def _fingerprint(cols: list[str]) -> str:
    from engine.librarian import _normalize
    return "|".join(sorted({_normalize(c) for c in cols}))


def _indicator_result(result: dict[str, Any], chart: dict[str, Any]) -> dict[str, Any]:
    return {
        "headline": _template_headline(result["table"], result["columns"]),
        "table": result["table"][:5],
        "columns": result["columns"],
        "chart_kind": chart["kind"],
        "rows_out": result["row_counts"][-1]["rows"],
    }


@router.post("/datasets/{dataset_id}/saved-queries")
def save_indicator(dataset_id: str, req: SaveQueryRequest) -> dict:
    """Save an answer as a named indicator (P2.5). The plan is stored with a
    normalized schema fingerprint, so next month's file with the same shape
    can refresh the same number."""
    import uuid
    from datetime import datetime, timezone

    ds = _gated_dataset(dataset_id)
    try:
        plan = QueryPlan.model_validate(req.plan)
        resolved = resolve_plan(plan, [str(c) for c in ds.df.columns])
        result = execute_plan(resolved, ds.df)
    except (ColumnResolutionError, QueryExecutionError) as exc:
        raise HTTPException(400, str(exc)) from exc
    name = req.name.strip()[:80]
    if not name:
        raise HTTPException(400, "Give the indicator a name.")
    if any(sq["name"].lower() == name.lower()
           for sq in store.list_saved_queries(ds.project_id)):
        raise HTTPException(409, f"An indicator called '{name}' already exists - "
                                 f"pick another name or delete the old one.")
    chart = choose_chart(result, resolved)
    now = datetime.now(timezone.utc).isoformat()
    rec = {
        "id": uuid.uuid4().hex[:12],
        "project_id": ds.project_id,
        "dataset_id": ds.id,
        "name": name,
        "question": req.question[:300],
        "plan": resolved.model_dump(),
        "fingerprint": _fingerprint(plan_columns(resolved)),
        "chart_kind": chart["kind"],
        "created_at": now,
        "last_result": _indicator_result(result, chart),
        "last_run_at": now,
    }
    store.save_saved_query(rec)
    store.log_event("user", "approval", dataset_id=ds.id,
                    payload={"gate": "save_indicator", "name": name,
                             "saved_query_id": rec["id"]})
    return rec


@router.get("/projects/{project_id}/saved-queries")
def list_indicators(project_id: str) -> dict:
    return {"saved_queries": store.list_saved_queries(project_id)}


@router.post("/saved-queries/{sq_id}/run")
def run_indicator(sq_id: str, req: dict | None = None) -> dict:
    """Re-run an indicator - against its origin dataset or any compatible
    one (same schema fingerprint via column normalization)."""
    from datetime import datetime, timezone

    try:
        rec = store.get_saved_query(sq_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    target_id = (req or {}).get("dataset_id") or rec["dataset_id"]
    ds = _gated_dataset(target_id)
    try:
        plan = QueryPlan.model_validate(rec["plan"])
        resolved = resolve_plan(plan, [str(c) for c in ds.df.columns])
        result = execute_plan(resolved, ds.df)
    except ColumnResolutionError as exc:
        # Plain-language incompatibility, not a stack trace.
        raise HTTPException(400, f"'{ds.filename}' does not fit this indicator: {exc}") from exc
    except QueryExecutionError as exc:
        raise HTTPException(400, str(exc)) from exc
    chart = choose_chart(result, resolved)
    rec["last_result"] = _indicator_result(result, chart)
    rec["last_run_at"] = datetime.now(timezone.utc).isoformat()
    rec["dataset_id"] = ds.id
    store.save_saved_query(rec)
    store.log_event("Query engine", "query_execute", dataset_id=ds.id, mode="fallback",
                    payload={"saved_query_id": sq_id, "indicator": rec["name"],
                             "rows_out": result["row_counts"][-1]["rows"]})
    return {"saved_query": rec, "result": result, "chart": chart}


@router.post("/projects/{project_id}/indicators/refresh")
def refresh_all_indicators(project_id: str) -> dict:
    """One click after a new file arrives: re-run every indicator against
    the NEWEST compatible dataset in the project (fingerprint compatibility
    = the plan resolves against its columns). Nothing moves without this
    click; every refresh is logged."""
    from datetime import datetime, timezone

    sqs = store.list_saved_queries(project_id)
    # Insertion order = upload order; newest last.
    candidates = [d for d in store.datasets.values()
                  if d.project_id == project_id
                  and not (d.pii and d.pii.get("status") == "pending")]
    candidates.reverse()
    refreshed, skipped = [], []
    for rec in sqs:
        done = False
        for ds in candidates:
            try:
                plan = QueryPlan.model_validate(rec["plan"])
                resolved = resolve_plan(plan, [str(c) for c in ds.df.columns])
                result = execute_plan(resolved, ds.df)
            except (ColumnResolutionError, QueryExecutionError):
                continue
            chart = choose_chart(result, resolved)
            rec["last_result"] = _indicator_result(result, chart)
            rec["last_run_at"] = datetime.now(timezone.utc).isoformat()
            rec["dataset_id"] = ds.id
            store.save_saved_query(rec)
            store.log_event("Query engine", "query_execute", dataset_id=ds.id,
                            mode="fallback",
                            payload={"saved_query_id": rec["id"],
                                     "indicator": rec["name"], "refresh_all": True,
                                     "rows_out": result["row_counts"][-1]["rows"]})
            refreshed.append({"name": rec["name"], "filename": ds.filename})
            done = True
            break
        if not done:
            skipped.append(rec["name"])
    store.log_event("user", "approval", project_id=project_id,
                    payload={"gate": "refresh_indicators",
                             "refreshed": len(refreshed), "skipped": len(skipped)})
    return {"refreshed": refreshed, "skipped": skipped}


@router.delete("/saved-queries/{sq_id}")
def delete_indicator(sq_id: str) -> dict:
    try:
        rec = store.get_saved_query(sq_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    store.delete_saved_query(sq_id)
    store.log_event("user", "decline", dataset_id=rec.get("dataset_id"),
                    payload={"deleted_indicator": rec["name"], "saved_query_id": sq_id})
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
