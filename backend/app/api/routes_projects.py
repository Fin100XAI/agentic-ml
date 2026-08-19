"""Project endpoints: the top-level container for datasets, runs and activity."""
from __future__ import annotations

import io

import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.store import store

router = APIRouter()


class ProjectRequest(BaseModel):
    name: str
    description: str = ""


class ProjectPatch(BaseModel):
    name: str | None = None
    description: str | None = None


class GlossaryRequest(BaseModel):
    entries: list[dict] = Field(default_factory=list)  # [{term, definition}]


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


@router.get("/projects/{project_id}/glossary")
def get_glossary(project_id: str) -> dict:
    _require_project(project_id)
    return {"entries": store.list_glossary(project_id)}


@router.post("/projects/{project_id}/glossary")
def add_glossary(project_id: str, req: GlossaryRequest) -> dict:
    _require_project(project_id)
    added = store.add_glossary_entries(project_id, req.entries)
    store.log_event("user", "approval", project_id=project_id,
                    payload={"gate": "glossary", "added": added})
    return {"added": added, "entries": store.list_glossary(project_id)}


@router.post("/projects/{project_id}/glossary/upload")
async def upload_glossary(project_id: str, file: UploadFile) -> dict:
    """Parse a codebook file: CSV/Excel (term, definition columns) or plain
    text with 'term: definition' / 'term - definition' lines."""
    _require_project(project_id)
    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(413, "Codebook files are capped at 5 MB.")
    name = (file.filename or "").lower()
    entries: list[dict] = []
    try:
        if name.endswith((".csv", ".xlsx", ".xls")):
            frame = (pd.read_excel(io.BytesIO(raw)) if name.endswith((".xlsx", ".xls"))
                     else pd.read_csv(io.BytesIO(raw)))
            if frame.shape[1] < 2:
                raise HTTPException(400, "The codebook needs at least two columns: term and definition.")
            for _, row in frame.iterrows():
                entries.append({"term": str(row.iloc[0]), "definition": str(row.iloc[1])})
        else:
            for line in raw.decode("utf-8", errors="replace").splitlines():
                for sep in (":", " - ", "\t"):
                    if sep in line:
                        term, _, definition = line.partition(sep)
                        if term.strip() and definition.strip():
                            entries.append({"term": term.strip(), "definition": definition.strip()})
                        break
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"Could not parse the codebook: {exc}") from exc
    added = store.add_glossary_entries(project_id, entries)
    store.log_event("user", "file_upload", project_id=project_id,
                    payload={"filename": file.filename, "glossary_terms": added})
    return {"added": added, "entries": store.list_glossary(project_id)}


@router.delete("/projects/{project_id}/glossary/{term}")
def delete_glossary(project_id: str, term: str) -> dict:
    _require_project(project_id)
    store.delete_glossary_entry(project_id, term)
    return {"entries": store.list_glossary(project_id)}


def _require_project(project_id: str) -> None:
    if project_id not in store.projects:
        raise HTTPException(404, f"Unknown project: {project_id}")


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
