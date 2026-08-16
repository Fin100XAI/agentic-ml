"""Model registry endpoints: versioned trained models per project."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.store import store

router = APIRouter()


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


@router.post("/models/{model_id}/{version}/archive")
def archive_model_version(model_id: str, version: int) -> dict:
    try:
        store.archive_model(model_id, version)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    store.log_event("user", "approval",
                    payload={"gate": "registry_archive", "model_id": model_id, "version": version})
    return {"archived": f"{model_id} v{version}"}
