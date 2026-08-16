"""Model registry endpoints: versioned trained models per project."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.store import store
from app.telemetry import instrumented_orchestrator, set_run_context
from engine.orchestrator import Run

router = APIRouter()


class RetrainRequest(BaseModel):
    dataset_id: str


@router.get("/projects/{project_id}/models")
def list_project_models(project_id: str) -> dict:
    if project_id not in store.projects:
        raise HTTPException(404, f"Unknown project: {project_id}")
    return {"models": store.list_registry(project_id=project_id)}


@router.get("/models/{model_id}")
def list_model_versions(model_id: str) -> dict:
    versions = store.list_registry(model_id=model_id)
    if not versions:
        raise HTTPException(404, f"Unknown model: {model_id}")
    return {"versions": versions}


@router.get("/models/{model_id}/{version}")
def get_model_version(model_id: str, version: int) -> dict:
    try:
        return store.get_registry_entry(model_id, version)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/models/{model_id}/{version}/retrain")
def retrain(model_id: str, version: int, req: RetrainRequest) -> dict:
    """Start a run pre-filled from a registry entry against a chosen dataset.

    The pipeline advances to the configure gate; the human still approves the
    actual training - retraining never skips the approval.
    """
    try:
        entry = store.get_registry_entry(model_id, version)
        ds = store.get_dataset(req.dataset_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    if ds.pii and ds.pii.get("status") == "pending":
        raise HTTPException(409, "PII review pending on that dataset - approve its privacy screen first.")
    orch = instrumented_orchestrator()
    run = Run(dataset_id=ds.id, df=ds.df, filename=ds.filename)
    run.artifact_id = ds.artifact_id
    store.add_run(run)
    set_run_context(run)
    purpose = entry.get("purpose_statement") or f"retrain {entry['model_name']}"
    orch.start(run, purpose)
    if run.remediation and run.remediation.get("status") == "pending":
        orch.apply_remediation(run, [], skip=True)  # retrains keep the data as-is
    orch.run_eda(run)
    orch.approve_eda(run, purpose)
    store.save_run(run)
    store.log_event(
        "user", "approval", run_id=run.id, dataset_id=ds.id, project_id=ds.project_id,
        payload={"gate": "retrain_started", "model_id": model_id, "from_version": version},
    )
    return {
        "run": run.to_dict(),
        "prefill": {
            "model_key": entry["model_key"],
            "hyperparams": entry.get("hyperparams") or {},
            "target": _entry_target(entry),
        },
    }


def _entry_target(entry: dict) -> str | None:
    """The target column the entry was trained on, recovered from its run."""
    run = store.runs.get(entry.get("run_id") or "")
    if run and run.config:
        return run.config.get("target")
    return None


@router.post("/models/{model_id}/{version}/archive")
def archive_model_version(model_id: str, version: int) -> dict:
    try:
        store.archive_model(model_id, version)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    store.log_event("user", "approval",
                    payload={"gate": "registry_archive", "model_id": model_id, "version": version})
    return {"archived": f"{model_id} v{version}"}
