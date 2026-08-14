"""Run endpoints: the approval-gated agent pipeline."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas import ApproveConfigRequest, ApproveEdaRequest, StartRunRequest
from app.store import store
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
    return run.to_dict()


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    return _get_run(run_id).to_dict()


@router.post("/runs/{run_id}/approve-eda")
def approve_eda(run_id: str, req: ApproveEdaRequest) -> dict:
    run = _get_run(run_id)
    if run.stage != "eda":
        raise HTTPException(409, f"Run is at stage '{run.stage}', expected 'eda'.")
    _orchestrator().approve_eda(run, req.comment)
    return run.to_dict()


@router.post("/runs/{run_id}/approve-config")
def approve_config(run_id: str, req: ApproveConfigRequest) -> dict:
    run = _get_run(run_id)
    if run.stage not in ("recommend", "configure", "execute", "interpret"):
        raise HTTPException(409, f"Run is at stage '{run.stage}', expected 'recommend' or later.")
    try:
        _orchestrator().approve_config(
            run, req.model_key, req.hyperparams, req.target, req.features, req.time_column
        )
    except KeyError as exc:
        raise HTTPException(400, str(exc)) from exc
    return run.to_dict()


@router.post("/runs/{run_id}/execute")
def execute(run_id: str) -> dict:
    run = _get_run(run_id)
    if not run.config:
        raise HTTPException(409, "Approve a model configuration before executing.")
    _orchestrator().execute(run)
    return run.to_dict()
