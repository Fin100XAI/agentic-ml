"""Dataset endpoints: upload CSV, list models."""
from __future__ import annotations

import io

import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile

from app.store import store
from engine.catalog import all_models

router = APIRouter()

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


@router.post("/datasets")
async def upload_dataset(file: UploadFile) -> dict:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Please upload a .csv file.")
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File exceeds the 50 MB POC limit.")
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:
        raise HTTPException(400, f"Could not parse CSV: {exc}") from exc
    if df.empty or df.shape[1] == 0:
        raise HTTPException(400, "The CSV appears to be empty.")

    ds = store.add_dataset(df, file.filename)
    return {
        "dataset_id": ds.id,
        "filename": ds.filename,
        "n_rows": int(df.shape[0]),
        "n_cols": int(df.shape[1]),
        "columns": [str(c) for c in df.columns],
    }


@router.get("/models")
def list_models() -> dict:
    return {"models": [m.to_dict() for m in all_models()]}
