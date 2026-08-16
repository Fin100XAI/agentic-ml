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
from engine.pii import apply_pii_actions, detect_pii

router = APIRouter()

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
EXCEL_EXT = (".xlsx", ".xls")


@router.post("/datasets")
async def upload_dataset(
    file: UploadFile,
    sheet: str | None = Form(None),
    join: str | None = Form(None),
) -> dict:
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

    # Immutable ledger: the raw file is stored read-only; the analyzed table
    # is a derived artifact pointing back at it. The original never changes.
    ext = Path(name).suffix or ".bin"
    original = store.add_original_artifact(raw, ext)
    table = store.add_derived_artifact(df, [original.id], transform_type, table_params)

    # PII screening runs HERE, before any run (and thus any LLM) can see rows.
    findings = detect_pii(df)
    pii = {"status": "pending" if findings else "clean", "findings": findings, "actions": {}}
    ds = store.add_dataset(df, display_name, artifact_id=table.id, pii=pii)
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
            masked, [ds.artifact_id] if ds.artifact_id else [], "pii_mask", effective
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
