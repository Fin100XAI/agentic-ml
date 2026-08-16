"""Dataset endpoints: upload CSV/Excel, list models, artifact lineage."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Form, HTTPException, UploadFile

from app.schemas import PiiReviewRequest
from app.store import store
from engine.catalog import all_models
from engine.joins import perform_join, propose_join
from engine.librarian import classify_file, perform_stack
from engine.pii import apply_pii_actions, detect_pii

router = APIRouter()

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
EXCEL_EXT = (".xlsx", ".xls")


@router.post("/datasets")
async def upload_dataset(
    file: UploadFile,
    sheet: str | None = Form(None),
    join: str | None = Form(None),
    project_id: str | None = Form(None),
    assembly: str | None = Form(None),  # librarian decision: JSON or "standalone"
) -> dict:
    if project_id is not None and project_id not in store.projects:
        raise HTTPException(404, f"Unknown project: {project_id}")
    name = (file.filename or "").lower()
    if not name.endswith((".csv", *EXCEL_EXT)):
        raise HTTPException(400, "Please upload a .csv or .xlsx file.")
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File exceeds the 50 MB POC limit.")

    table_params: dict = {}
    transform_type = "upload"

    if name.endswith(EXCEL_EXT):
        try:
            book = pd.read_excel(io.BytesIO(raw), sheet_name=None)
        except Exception as exc:
            raise HTTPException(400, f"Could not parse Excel file: {exc}") from exc
        book = {k: v for k, v in book.items() if not v.empty and v.shape[1] > 0}
        if not book:
            raise HTTPException(400, "The workbook has no non-empty sheets.")
        if join is not None:
            # Human approved the join scout's proposal (or supplied their own).
            try:
                spec = json.loads(join)
                df = perform_join(
                    book, spec["left"], spec["right"],
                    spec["on_left"], spec["on_right"], spec.get("how", "left"),
                )
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            except (KeyError, json.JSONDecodeError) as exc:
                raise HTTPException(400, f"Invalid join spec: {exc}") from exc
            display_name = f"{file.filename} [{spec['left']}+{spec['right']}]"
            transform_type, table_params = "join", spec
        elif sheet is None and len(book) > 1:
            # Multiple sheets: ask the human, with the join scout's proposal if any.
            try:
                suggestion = propose_join(book)
            except Exception:
                suggestion = None
            return {
                "needs_sheet_selection": True,
                "filename": file.filename,
                "sheets": [
                    {"name": k, "n_rows": int(v.shape[0]), "n_cols": int(v.shape[1])}
                    for k, v in book.items()
                ],
                "join_suggestion": suggestion,
            }
        else:
            chosen = sheet if sheet is not None else next(iter(book))
            if chosen not in book:
                raise HTTPException(400, f"Sheet '{chosen}' not found in the workbook.")
            df = book[chosen]
            display_name = f"{file.filename} [{chosen}]" if len(book) > 1 else (file.filename or chosen)
            if len(book) > 1:
                table_params = {"sheet": chosen}
    else:
        try:
            df = pd.read_csv(io.BytesIO(raw))
        except Exception as exc:
            raise HTTPException(400, f"Could not parse CSV: {exc}") from exc
        display_name = file.filename or "upload.csv"

    if df.empty or df.shape[1] == 0:
        raise HTTPException(400, "The file appears to be empty.")

    pid = project_id or store.default_project_id()

    # Librarian: when the project already holds data, ask how this file fits -
    # unless the human already decided (assembly param present).
    project_datasets = [
        {"id": d.id, "filename": d.filename, "df": d.df}
        for d in store.datasets.values() if d.project_id == pid
    ]
    if assembly is None and project_datasets:
        try:
            proposals = classify_file(df, display_name, project_datasets)
        except Exception:
            proposals = []
        if proposals:
            store.log_event(
                "Librarian", "agent_call", project_id=pid, mode="fallback",
                payload={"action": "Classified an incoming file",
                         "proposals": [{k: v for k, v in p.items() if k != "df"} for p in proposals]},
            )
            return {
                "needs_assembly_decision": True,
                "filename": display_name,
                "n_rows": int(df.shape[0]),
                "n_cols": int(df.shape[1]),
                "assembly_proposals": proposals,
            }

    assembly_note: dict | None = None
    if assembly and assembly != "standalone":
        try:
            spec = json.loads(assembly)
            target = store.get_dataset(spec["target_dataset_id"])
        except (KeyError, json.JSONDecodeError) as exc:
            raise HTTPException(400, f"Invalid assembly decision: {exc}") from exc
        try:
            if spec["kind"] == "stack":
                df = perform_stack(df, target.df, display_name, target.filename)
                display_name = f"{target.filename} + {display_name}"
            elif spec["kind"] == "join":
                df = perform_join(
                    {"new": df, "existing": target.df}, "new", "existing",
                    spec["on_left"], spec["on_right"],
                )
                display_name = f"{display_name} [+{target.filename}]"
            else:
                raise HTTPException(400, f"Unknown assembly kind: {spec.get('kind')}")
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        assembly_note = {"kind": spec["kind"], "target": target.id,
                         "params": {k: v for k, v in spec.items() if k != "kind"}}

    if assembly == "standalone" and project_datasets:
        store.log_event("user", "decline", project_id=pid,
                        payload={"gate": "librarian", "note": "treated the file as standalone"})
    elif assembly_note:
        store.log_event("user", "approval", project_id=pid,
                        payload={"gate": "librarian", **assembly_note})

    # Immutable ledger: the raw file is stored read-only; the analyzed table
    # is a derived artifact pointing back at it. The original never changes.
    ext = Path(name).suffix or ".bin"
    original = store.add_original_artifact(raw, ext, project_id=pid)
    parents = [original.id]
    if assembly_note:
        t = store.datasets.get(assembly_note["target"])
        if t and t.artifact_id:
            parents.append(t.artifact_id)
        transform_type = assembly_note["kind"]
        table_params = assembly_note["params"]
    table = store.add_derived_artifact(df, parents, transform_type, table_params, project_id=pid)

    # PII screening runs HERE, before any run (and thus any LLM) can see rows.
    findings = detect_pii(df)
    pii = {"status": "pending" if findings else "clean", "findings": findings, "actions": {}}
    ds = store.add_dataset(df, display_name, artifact_id=table.id, pii=pii, project_id=pid)
    store.log_event(
        "user", "file_upload", dataset_id=ds.id, artifact_id=original.id,
        payload={
            "filename": display_name, "rows": int(df.shape[0]), "cols": int(df.shape[1]),
            "sha256": original.sha256,
            **({"sheet": sheet} if sheet else {}),
            **({"join": json.loads(join)} if join else {}),
        },
    )
    if findings:
        store.log_event(
            "PII screen", "pii_review", dataset_id=ds.id,
            payload={"status": "pending", "findings": findings},
        )
    return {
        "dataset_id": ds.id,
        "filename": ds.filename,
        "n_rows": int(df.shape[0]),
        "n_cols": int(df.shape[1]),
        "columns": [str(c) for c in df.columns],
        "pii_status": pii["status"],
        "pii_findings": findings,
    }


@router.post("/datasets/{dataset_id}/pii-review")
def review_pii(dataset_id: str, req: PiiReviewRequest) -> dict:
    try:
        ds = store.get_dataset(dataset_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    if not ds.pii or ds.pii.get("status") != "pending":
        raise HTTPException(409, "This dataset has no pending PII review.")

    findings = ds.pii["findings"]
    valid_cols = {f["column"] for f in findings}
    actions = {c: a for c, a in req.actions.items() if c in valid_cols and a in ("mask", "drop", "keep")}
    for f in findings:  # anything the request omits falls back to the proposal
        actions.setdefault(f["column"], f["proposed_action"])

    effective = {c: a for c, a in actions.items() if a != "keep"}
    if effective:
        masked = apply_pii_actions(ds.df, findings, effective)
        art = store.add_derived_artifact(
            masked, [ds.artifact_id] if ds.artifact_id else [], "pii_mask", effective,
            project_id=ds.project_id,
        )
        ds.df = masked
        ds.artifact_id = art.id

    ds.pii = {"status": "reviewed", "findings": findings, "actions": actions}
    store.update_dataset(ds)

    declined = [c for c, a in actions.items() if a == "keep"]
    store.log_event(
        "user", "pii_review", dataset_id=ds.id, artifact_id=ds.artifact_id,
        payload={"status": "approved", "actions": actions},
    )
    for col in declined:
        store.log_event(
            "user", "decline", dataset_id=ds.id,
            payload={"gate": "pii_mask", "column": col, "note": "kept as-is by explicit choice"},
        )
    return {
        "dataset_id": ds.id,
        "pii_status": "reviewed",
        "masked": bool(effective),
        "n_rows": int(ds.df.shape[0]),
        "n_cols": int(ds.df.shape[1]),
        "columns": [str(c) for c in ds.df.columns],
    }


@router.get("/models")
def list_models() -> dict:
    return {"models": [m.to_dict() for m in all_models()]}


@router.get("/artifacts/{artifact_id}/lineage")
def get_lineage(artifact_id: str) -> dict:
    try:
        chain = store.lineage(artifact_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    if not chain:
        raise HTTPException(404, f"Unknown artifact: {artifact_id}")
    return {"lineage": [a.to_dict() for a in chain]}
