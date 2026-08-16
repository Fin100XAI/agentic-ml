"""Project endpoints: the top-level container for datasets, runs and activity."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.store import store

router = APIRouter()


class ProjectRequest(BaseModel):
    name: str
    description: str = ""


class ProjectPatch(BaseModel):
    name: str | None = None
    description: str | None = None


@router.get("/projects")
def list_projects() -> dict:
    out = []
    for proj in sorted(store.projects.values(), key=lambda p: p.created_at):
        out.append({**proj.to_dict(), **store.project_summary(proj.id)})
    return {"projects": out}


@router.post("/projects")
def create_project(req: ProjectRequest) -> dict:
    if not req.name.strip():
        raise HTTPException(400, "Give the project a name.")
    proj = store.add_project(req.name, req.description)
    store.log_event("user", "approval", project_id=proj.id,
                    payload={"gate": "project_created", "name": proj.name})
    return proj.to_dict()


@router.get("/projects/{project_id}")
def get_project(project_id: str) -> dict:
    try:
        proj = store.get_project(project_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    datasets = [
        {
            "id": ds.id, "filename": ds.filename,
            "n_rows": int(ds.df.shape[0]), "n_cols": int(ds.df.shape[1]),
            "pii_status": (ds.pii or {}).get("status", "clean"),
        }
        for ds in store.datasets.values() if ds.project_id == project_id
    ]
    runs = [
        {
            "id": r.id, "filename": r.filename, "question": r.question,
            "stage": r.stage, "created_at": r.created_at,
        }
        for r in sorted(store.runs_for_project(project_id), key=lambda r: r.created_at, reverse=True)
    ]
    return {
        **proj.to_dict(),
        **store.project_summary(project_id),
        "datasets": datasets,
        "runs": runs,
        "recent_activity": store.list_activity(project_id=project_id, limit=20),
    }


@router.patch("/projects/{project_id}")
def update_project(project_id: str, req: ProjectPatch) -> dict:
    try:
        return store.update_project(project_id, req.name, req.description).to_dict()
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete("/projects/{project_id}")
def delete_project(project_id: str) -> dict:
    try:
        store.delete_project(project_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"deleted": project_id}
