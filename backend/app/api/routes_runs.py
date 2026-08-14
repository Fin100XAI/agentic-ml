"""Run endpoints: the approval-gated agent pipeline."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, Response

from app.pdf_report import build_report_pdf
from app.report import build_report
from app.schemas import (
    ApproveConfigRequest,
    ApproveEdaRequest,
    AskRequest,
    CompareRequest,
    StartRunRequest,
)
from app.store import store
from engine.agents import run_ask_agent
from engine.llm import get_provider
from engine.orchestrator import Orchestrator, Run

router = APIRouter()


def _orchestrator() -> Orchestrator:
    return Orchestrator(get_provider())


def _get_run(run_id: str) -> Run:
    try:
        return store.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


# Sync endpoints on purpose: FastAPI runs them in a threadpool, so model
# training and LLM calls don't block the event loop.

@router.post("/runs")
def start_run(req: StartRunRequest) -> dict:
    try:
        ds = store.get_dataset(req.dataset_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    run = Run(dataset_id=ds.id, df=ds.df, filename=ds.filename)
    store.add_run(run)
    _orchestrator().start(run, req.question)
    store.save_run(run)
    return run.to_dict()


@router.get("/runs")
def list_runs() -> dict:
    return {
        "runs": [
            {
                "id": r.id,
                "filename": r.filename,
                "question": r.question,
                "stage": r.stage,
                "created_at": r.created_at,
            }
            for r in sorted(store.runs.values(), key=lambda r: r.created_at, reverse=True)
        ]
    }


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    return _get_run(run_id).to_dict()


@router.get("/runs/{run_id}/report", response_class=PlainTextResponse)
def get_report(run_id: str) -> str:
    return build_report(_get_run(run_id))


@router.get("/runs/{run_id}/report.pdf")
def get_report_pdf(run_id: str) -> Response:
    run = _get_run(run_id)
    return Response(
        content=build_report_pdf(run),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="decision_brief_{run.id}.pdf"'},
    )


@router.post("/runs/{run_id}/eda")
def run_eda(run_id: str) -> dict:
    run = _get_run(run_id)
    if run.stage != "profiled":
        raise HTTPException(409, f"Run is at stage '{run.stage}', expected 'profiled'.")
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


@router.post("/runs/{run_id}/ask")
def ask(run_id: str, req: AskRequest) -> dict:
    run = _get_run(run_id)
    if not req.question.strip():
        raise HTTPException(400, "Please enter a question.")
    return run_ask_agent(get_provider(), run.to_dict(), req.question, req.history)


@router.post("/runs/{run_id}/approve-config")
def approve_config(run_id: str, req: ApproveConfigRequest) -> dict:
    run = _get_run(run_id)
    if run.stage not in ("recommend", "configure", "execute", "interpret", "compare"):
        raise HTTPException(409, f"Run is at stage '{run.stage}', expected 'recommend' or later.")
    try:
        _orchestrator().approve_config(
            run, req.model_key, req.hyperparams, req.target, req.features,
            req.time_column, req.feature_ids,
        )
    except KeyError as exc:
        raise HTTPException(400, str(exc)) from exc
    store.save_run(run)
    return run.to_dict()


@router.post("/runs/{run_id}/execute")
def execute(run_id: str) -> dict:
    run = _get_run(run_id)
    if not run.config:
        raise HTTPException(409, "Approve a model configuration before executing.")
    _orchestrator().execute(run)
    store.save_run(run)
    return run.to_dict()
