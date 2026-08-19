"""Run endpoints: the approval-gated agent pipeline."""
from __future__ import annotations

import threading

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, Response

from app.pdf_report import build_report_pdf
from app.report import build_report
from app.schemas import (
    ApproveConfigRequest,
    ApproveEdaRequest,
    AskRequest,
    CompareRequest,
    RemediateRequest,
    StartRunRequest,
)
from app.store import store
from app.telemetry import (
    instrumented_orchestrator,
    instrumented_provider,
    set_run_context,
)
from engine.agents import run_ask_agent
from engine.orchestrator import Orchestrator, Run

router = APIRouter()


def _orchestrator() -> Orchestrator:
    return instrumented_orchestrator()


def _get_run(run_id: str) -> Run:
    try:
        run = store.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    set_run_context(run)
    return run


# Sync endpoints on purpose: FastAPI runs them in a threadpool, so model
# training and LLM calls don't block the event loop.

@router.post("/runs")
def start_run(req: StartRunRequest) -> dict:
    try:
        ds = store.get_dataset(req.dataset_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    # Hard gate: no analysis (and therefore no LLM call) before PII review.
    if ds.pii and ds.pii.get("status") == "pending":
        raise HTTPException(409, "PII review pending: approve the privacy screen for this dataset first.")
    run = Run(dataset_id=ds.id, df=ds.df, filename=ds.filename)
    run.artifact_id = ds.artifact_id  # lineage starts at the dataset's table artifact
    store.add_run(run)
    set_run_context(run)
    _orchestrator().start(run, req.question)
    _attach_glossary(run, ds.project_id)
    store.save_run(run)
    return run.to_dict()


def _attach_glossary(run: Run, project_id: str | None) -> None:
    """The project's own data dictionary overrides guessed column meanings and
    rides into every agent prompt built from the profile."""
    if not run.profile:
        return
    matched = store.glossary_for_columns(project_id, [c["name"] for c in run.profile["columns"]])
    if not matched:
        return
    run.profile["glossary"] = matched
    for col in run.profile["columns"]:
        if col["name"] in matched:
            col["meaning"] = matched[col["name"]]
            col["glossary"] = True


@router.get("/runs")
def list_runs(project_id: str | None = None) -> dict:
    runs = store.runs_for_project(project_id) if project_id else list(store.runs.values())
    return {
        "runs": [
            {
                "id": r.id,
                "filename": r.filename,
                "question": r.question,
                "stage": r.stage,
                "created_at": r.created_at,
            }
            for r in sorted(runs, key=lambda r: r.created_at, reverse=True)
        ]
    }


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    return _get_run(run_id).to_dict()


@router.get("/runs/{run_id}/report", response_class=PlainTextResponse)
def get_report(run_id: str) -> str:
    run = _get_run(run_id)
    report = build_report(run)
    store.log_event("user", "export", run_id=run.id, dataset_id=run.dataset_id,
                    payload={"format": "markdown", "bytes": len(report)})
    return report


@router.get("/runs/{run_id}/report.pdf")
def get_report_pdf(run_id: str) -> Response:
    run = _get_run(run_id)
    pdf = build_report_pdf(run)
    store.log_event("user", "export", run_id=run.id, dataset_id=run.dataset_id,
                    payload={"format": "pdf", "bytes": len(pdf)})
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="decision_brief_{run.id}.pdf"'},
    )


@router.post("/runs/{run_id}/remediate")
def remediate(run_id: str, req: RemediateRequest) -> dict:
    run = _get_run(run_id)
    try:
        _orchestrator().apply_remediation(run, req.accepted_ids, req.skip)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    store.save_run(run)
    return run.to_dict()


@router.post("/runs/{run_id}/eda")
def run_eda(run_id: str) -> dict:
    run = _get_run(run_id)
    if run.stage != "profiled":
        raise HTTPException(409, f"Run is at stage '{run.stage}', expected 'profiled'.")
    if (run.remediation or {}).get("status") == "pending":
        raise HTTPException(409, "Resolve the data-fix proposals first (apply or skip).")
    _orchestrator().run_eda(run)
    store.save_run(run)
    return run.to_dict()


@router.post("/runs/{run_id}/approve-eda")
def approve_eda(run_id: str, req: ApproveEdaRequest) -> dict:
    run = _get_run(run_id)
    # Allowed from any post-EDA stage too, so the human can change direction
    # later and get a fresh recommendation.
    if run.stage in ("upload", "profiled"):
        raise HTTPException(409, f"Run is at stage '{run.stage}', expected 'eda' or later.")
    _orchestrator().approve_eda(run, req.comment)
    store.save_run(run)
    return run.to_dict()


@router.post("/runs/{run_id}/compare")
def compare(run_id: str, req: CompareRequest) -> dict:
    run = _get_run(run_id)
    if not run.recommendation:
        raise HTTPException(409, "Approve the EDA first so a use case is chosen.")
    try:
        _orchestrator().compare(run, req.target, req.time_column)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    store.save_run(run)
    return run.to_dict()


@router.post("/runs/{run_id}/autotune")
def autotune(run_id: str, req: CompareRequest) -> dict:
    run = _get_run(run_id)
    if not run.recommendation:
        raise HTTPException(409, "Approve the EDA first so a use case is chosen.")
    try:
        _orchestrator().run_autotune(run, req.target, req.time_column, req.n_candidates)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    store.save_run(run)
    return run.to_dict()


@router.post("/runs/diff")
def diff_two_runs(req: dict) -> dict:
    """Compare two completed runs of the same use case."""
    from engine.rundiff import diff_runs, narrative_template, to_markdown

    try:
        run_a = store.get_run(str(req.get("run_a", "")))
        run_b = store.get_run(str(req.get("run_b", "")))
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    for r in (run_a, run_b):
        if not r.result or not r.insights:
            raise HTTPException(409, f"Run {r.id} has no completed results to compare.")
    if (run_a.config or {}).get("use_case") != (run_b.config or {}).get("use_case"):
        raise HTTPException(409, "These analyses answer different kinds of questions "
                                 f"({(run_a.config or {}).get('use_case')} vs "
                                 f"{(run_b.config or {}).get('use_case')}) - pick two of the same kind.")

    diff = diff_runs(run_a, run_b)
    narrative = narrative_template(diff)
    generated_by = "heuristic"
    provider = instrumented_provider()
    if provider is not None:
        try:
            narrative = provider.complete_text(
                "You explain the difference between two analyses to a policy maker in "
                "3-5 plain sentences: what changed in the data, the approach, the "
                "results, and what that means for decisions. Never invent numbers - "
                "only use the facts given. Style rule: use plain hyphens (-) only in prose - but put a colon, never a hyphen, before a number (a hyphen reads as minus); "
                "never use em dashes or en dashes.",
                f"Computed deltas: {diff}\nDeterministic summary: {narrative}",
                max_tokens=400,
            )
            generated_by = "claude"
        except Exception:
            pass
    store.log_event(
        "user", "export", run_id=run_b.id, dataset_id=run_b.dataset_id,
        payload={"format": "run_diff", "against": run_a.id},
    )
    return {
        "diff": diff,
        "narrative": narrative,
        "generated_by": generated_by,
        "markdown": to_markdown(diff, narrative),
    }


@router.post("/runs/{run_id}/ask")
def ask(run_id: str, req: AskRequest) -> dict:
    run = _get_run(run_id)
    if not req.question.strip():
        raise HTTPException(400, "Please enter a question.")
    answer = run_ask_agent(instrumented_provider(), run.to_dict(), req.question, req.history)
    store.log_event(
        "Ask-the-data agent", "agent_call", run_id=run.id, dataset_id=run.dataset_id,
        mode="llm" if answer.get("generated_by") == "claude" else "fallback",
        payload={"question": req.question[:300]},
    )
    return answer


@router.post("/runs/{run_id}/approve-config")
def approve_config(run_id: str, req: ApproveConfigRequest) -> dict:
    run = _get_run(run_id)
    if run.stage not in ("recommend", "configure", "execute", "interpret", "compare"):
        raise HTTPException(409, f"Run is at stage '{run.stage}', expected 'recommend' or later.")
    try:
        _orchestrator().approve_config(
            run, req.model_key, req.hyperparams, req.target, req.features,
            req.time_column, req.feature_ids, req.excluded_columns,
            req.group_column, req.group_agg,
        )
    except (KeyError, ValueError) as exc:
        # ValueError carries the purpose-written messages (e.g. an approved
        # feature colliding with a leakage-excluded column) - surface them,
        # never a 500.
        raise HTTPException(400, str(exc)) from exc
    store.save_run(run)
    return run.to_dict()


# Double-click guard: one training per run at a time, ever.
_executing: set[str] = set()
_executing_lock = threading.Lock()


@router.post("/runs/{run_id}/execute")
def execute(run_id: str) -> dict:
    run = _get_run(run_id)
    if not run.config:
        raise HTTPException(409, "Approve a model configuration before executing.")
    if run.stage in ("interpret", "compare"):
        raise HTTPException(409, "This run has already been trained - retrain "
                                 "from the registry to produce a new version.")
    with _executing_lock:
        if run.id in _executing:
            raise HTTPException(409, "This run is already training.")
        _executing.add(run.id)
    try:
        _orchestrator().execute(run)
        store.save_run(run)
    finally:
        with _executing_lock:
            _executing.discard(run.id)
    return run.to_dict()
