"""Data Prep Studio (PREP-STUDIO prototype, additive): an intent-first,
agent-guided path that turns messy multi-sheet/multi-year uploads into ONE
analysis-ready table.

Rules honored: the guide agent sees only metadata (goal, sheet names, column
names, dtypes, shapes) - never row values; every combine/clean step is
proposed and human-approved; every action lands in the activity log; the
finished table registers through the normal dataset machinery. Sessions are
in-memory (prototype) - a server restart clears unfinished prep work.
"""
from __future__ import annotations

import io
import json
import uuid
from typing import Any

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.store import store
from app.telemetry import current_agent, instrumented_provider
from engine import prep
from engine.pii import detect_pii
from engine.query.places import detect_place_variants
from engine.query.readiness import readiness_audit
from engine.query.textnum import apply_text_number_fix, detect_text_numbers

router = APIRouter()

_SESSIONS: dict[str, dict[str, Any]] = {}
_MAX_UPLOAD = 50 * 1024 * 1024


def _session(sid: str) -> dict[str, Any]:
    s = _SESSIONS.get(sid)
    if s is None:
        raise HTTPException(404, "Prep session not found (sessions reset on restart).")
    return s


def _log(s: dict[str, Any], actor: str, event: str, payload: dict) -> None:
    store.log_event(actor, event, mode=payload.pop("mode", "fallback"),
                    payload={"prep_session": s["id"], **payload})


class SessionRequest(BaseModel):
    goal: str


class CombineRequest(BaseModel):
    spec: dict[str, Any]


class CleanRequest(BaseModel):
    fix_number_columns: list[str] = []
    place_maps: dict[str, dict[str, str]] = {}
    drop_columns: list[str] = []
    drop_empty_rows: bool = False
    drop_total_rows: bool = False


class FinishRequest(BaseModel):
    name: str
    project_id: str | None = None


@router.post("/prep/session")
def create_session(req: SessionRequest) -> dict:
    goal = req.goal.strip()
    if not goal:
        raise HTTPException(400, "Tell the agents what you expect from this data first.")
    sid = uuid.uuid4().hex[:12]
    _SESSIONS[sid] = {"id": sid, "goal": goal, "frames": {}, "combined": None,
                      "report": None}
    agent = _goal_guidance(goal)
    _log(_SESSIONS[sid], "Prep guide", "query_plan",
         {"context": "prep_goal", "goal": goal[:200], "mode": agent["mode"]})
    return {"id": sid, "agent": agent}


def _goal_guidance(goal: str) -> dict[str, Any]:
    """The intent-first step: before any data arrives, the guide reflects the
    goal back and asks what it needs to know. LLM phrases; fallback templated."""
    fallback = {
        "message": ("Understood - the goal is: " + goal + ". Now add the data: "
                    "you can drop in several files or a multi-sheet workbook; "
                    "sheets from different years are welcome."),
        "questions": [
            "What should one row stand for when the data is ready (a district, a beneficiary, a month)?",
            "Is this for quick analytics, or for training a model?",
            "If there are several sheets or files, do they cover different years or different facts?",
        ],
        "mode": "fallback",
    }
    provider = instrumented_provider()
    if provider is None:
        return fallback
    current_agent.set("Prep guide")
    try:
        raw = provider.complete_json(
            "You are a data-preparation guide for a government analyst. Given "
            "their goal, write 'message': 2-3 short sentences on what data to "
            "add and what the finished table should look like for that goal, "
            "and 'questions': up to 3 short clarifying questions ONLY where "
            "the goal leaves real ambiguity. Plain language, plain hyphens; "
            "put a colon before any number.",
            f"Goal: {goal}",
            schema={"type": "object", "properties": {
                "message": {"type": "string"},
                "questions": {"type": "array", "items": {"type": "string"}}},
                "required": ["message", "questions"]},
            max_tokens=500,
        )
        return {"message": str(raw.get("message", ""))[:800] or fallback["message"],
                "questions": [str(q)[:200] for q in raw.get("questions", [])][:3],
                "mode": "llm"}
    except Exception:
        return fallback


@router.post("/prep/{sid}/files")
async def add_file(sid: str, file: UploadFile = File(...)) -> dict:
    s = _session(sid)
    raw = await file.read()
    if len(raw) > _MAX_UPLOAD:
        raise HTTPException(413, "File larger than 50MB - split it first.")
    fname = file.filename or "upload"
    try:
        # Parse every sheet header-less first, then find the REAL header row -
        # government exports open with title banners more often than not.
        if fname.lower().endswith((".xlsx", ".xls", ".xlsm")):
            book = pd.read_excel(io.BytesIO(raw), sheet_name=None, header=None)
            added = []
            for sheet, rawdf in book.items():
                if rawdf.dropna(how="all").empty:
                    continue
                key = f"{fname} :: {sheet}" if len(book) > 1 else fname
                _install_sheet(s, key, rawdf)
                added.append(key)
            if not added:
                raise HTTPException(400, "The workbook has no non-empty sheets.")
        else:
            rawdf = pd.read_csv(io.BytesIO(raw), header=None, skip_blank_lines=False)
            _install_sheet(s, fname, rawdf)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"Could not parse '{fname}': {exc}") from exc
    s["combined"] = None  # new data invalidates any previous combine
    _log(s, "You", "file_upload", {"context": "prep", "filename": fname})
    return {"inventory": _inventory(s)}


def _install_sheet(s: dict[str, Any], key: str, rawdf: pd.DataFrame) -> None:
    """Keep the raw header-less frame (for manual re-headering) and install
    the parsed frame using the detected header row."""
    header_row = prep.detect_header_row(rawdf)
    s.setdefault("raw", {})[key] = rawdf
    s.setdefault("header_rows", {})[key] = header_row
    s["frames"][key] = prep.reheader(rawdf, header_row)


def _inventory(s: dict[str, Any]) -> list[dict[str, Any]]:
    inv = prep.sheet_inventory(s["frames"])
    for item in inv:
        hr = s.get("header_rows", {}).get(item["name"], 0)
        item["header_row"] = hr
        if hr > 0:
            item["note"] = (f"Header found on row {hr + 1} - the {hr} row(s) "
                            "above looked like a title banner and were skipped.")
    return inv


class HeaderRequest(BaseModel):
    header_row: int


@router.post("/prep/{sid}/files/{name}/header")
def set_header(sid: str, name: str, req: HeaderRequest) -> dict:
    """Manual override when the detector guessed wrong."""
    s = _session(sid)
    rawdf = s.get("raw", {}).get(name)
    if rawdf is None:
        raise HTTPException(404, "No such sheet in this session.")
    if not 0 <= req.header_row < min(len(rawdf), 20):
        raise HTTPException(400, "Header row must be within the first 20 rows.")
    s["header_rows"][name] = req.header_row
    s["frames"][name] = prep.reheader(rawdf, req.header_row)
    s["combined"] = None
    _log(s, "You", "approval", {"context": "prep_header", "sheet": name,
                                "header_row": req.header_row})
    return {"inventory": _inventory(s)}


@router.delete("/prep/{sid}/files/{name}")
def remove_sheet(sid: str, name: str) -> dict:
    s = _session(sid)
    if name not in s["frames"]:
        raise HTTPException(404, "No such sheet in this session.")
    del s["frames"][name]
    s.get("raw", {}).pop(name, None)
    s.get("header_rows", {}).pop(name, None)
    s["combined"] = None
    return {"inventory": _inventory(s)}


@router.post("/prep/{sid}/advise")
def advise(sid: str) -> dict:
    s = _session(sid)
    if not s["frames"]:
        raise HTTPException(400, "Add at least one file first.")
    proposal = prep.propose_combine(s["frames"])
    agent = _combine_guidance(s["goal"], prep.sheet_inventory(s["frames"]), proposal)
    _log(s, "Prep guide", "query_plan",
         {"context": "prep_advise", "strategy": proposal["strategy"],
          "sheets": len(s["frames"]), "mode": agent["mode"]})
    return {"proposal": proposal, "agent": agent}


def _combine_guidance(goal: str, inventory: list[dict], proposal: dict) -> dict:
    strategy = proposal["strategy"]
    fb = {
        "stack": "The sheets share the same shape - stacking them into one table "
                 "(with a column saying which sheet each row came from) fits the goal.",
        "join": "The sheets describe the same entities - joining them on the shared "
                "key column puts every fact on one row.",
        "single": "One sheet - it goes straight to cleaning.",
        "review": "These sheets do not obviously belong together - pick one, or "
                  "add files that share columns or a key.",
    }
    fallback = {"message": fb.get(strategy, ""), "mode": "fallback"}
    provider = instrumented_provider()
    if provider is None:
        return fallback
    current_agent.set("Prep guide")
    try:
        meta = [{"sheet": i["name"], "rows": i["rows"],
                 "columns": [c["name"] for c in i["columns"]][:25],
                 "year": i["year_guess"]} for i in inventory]
        raw = provider.complete_json(
            "You are a data-preparation guide. Given the user's goal, the sheet "
            "inventory (names, shapes, column names only - you never see values) "
            "and the deterministic combine proposal, explain in 2-3 plain "
            "sentences WHY this combine strategy fits the goal, or warn if it "
            "does not. Never propose a different computation - the proposal is "
            "what will run. Plain hyphens; colon before numbers.",
            f"Goal: {goal}\nInventory: {json.dumps(meta)}\n"
            f"Proposal: {json.dumps({k: v for k, v in proposal.items() if k != 'mappings'})}",
            schema={"type": "object", "properties": {"message": {"type": "string"}},
                    "required": ["message"]},
            max_tokens=400,
        )
        return {"message": str(raw.get("message", ""))[:700] or fallback["message"],
                "mode": "llm"}
    except Exception:
        return fallback


@router.post("/prep/{sid}/combine")
def combine(sid: str, req: CombineRequest) -> dict:
    s = _session(sid)
    if not s["frames"]:
        raise HTTPException(400, "Add at least one file first.")
    try:
        df, report = prep.apply_combine(s["frames"], req.spec)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    s["combined"] = df
    s["report"] = report
    _log(s, "You", "approval", {"context": "prep_combine", **report})
    return {"report": report, "preview": _preview(df), "checks": _checks(df)}


def _preview(df: pd.DataFrame) -> dict:
    head = df.head(50)
    return {"columns": [str(c) for c in df.columns],
            "rows": json.loads(head.to_json(orient="records", date_format="iso")),
            "n_rows": int(len(df)), "n_cols": int(df.shape[1])}


def _checks(df: pd.DataFrame) -> dict:
    pii = detect_pii(df)
    # Place spellings: scan the text columns that look like places (small
    # vocabularies), same per-column contract the main board uses.
    places: list[dict[str, Any]] = []
    for c in df.columns:
        s = df[c]
        if s.dtype == object and 2 <= s.nunique(dropna=True) <= 120:
            props = detect_place_variants(s)
            if props:
                places.append({"column": str(c), "proposals": props})
    return {
        "text_numbers": detect_text_numbers(df),
        "place_variants": places,
        "junk": prep.junk_scan(df),
        "pii_columns": [{"column": f["column"], "kind": f["kind"]} for f in pii],
        "readiness": readiness_audit(df)["findings"],
    }


@router.get("/prep/{sid}/state")
def state(sid: str) -> dict:
    s = _session(sid)
    out: dict[str, Any] = {"goal": s["goal"],
                           "inventory": _inventory(s)}
    if s["combined"] is not None:
        out["report"] = s["report"]
        out["preview"] = _preview(s["combined"])
        out["checks"] = _checks(s["combined"])
    return out


@router.post("/prep/{sid}/clean")
def clean(sid: str, req: CleanRequest) -> dict:
    s = _session(sid)
    df = s["combined"]
    if df is None:
        raise HTTPException(400, "Combine the sheets first.")
    applied: list[str] = []
    if req.drop_columns:
        missing = [c for c in req.drop_columns if c not in df.columns]
        if missing:
            raise HTTPException(400, f"No such column(s): {missing}")
        df = df.drop(columns=req.drop_columns)
        applied.append(f"dropped {len(req.drop_columns)} column(s)")
    if req.fix_number_columns:
        df = apply_text_number_fix(df, req.fix_number_columns)
        applied.append(f"converted {len(req.fix_number_columns)} text column(s) to numbers")
    for col, mapping in req.place_maps.items():
        if col in df.columns and mapping:
            df[col] = df[col].astype(str).replace(mapping)
            applied.append(f"merged {len(mapping)} spelling(s) in '{col}'")
    if req.drop_empty_rows or req.drop_total_rows:
        df, n = prep.drop_junk(df, req.drop_empty_rows, req.drop_total_rows)
        if n:
            applied.append(f"removed {n} junk row(s)")
    s["combined"] = df
    _log(s, "You", "approval", {"context": "prep_clean", "applied": applied})
    return {"applied": applied, "preview": _preview(df), "checks": _checks(df)}


@router.get("/prep/{sid}/export")
def export_csv(sid: str) -> StreamingResponse:
    s = _session(sid)
    if s["combined"] is None:
        raise HTTPException(400, "Combine the sheets first.")
    buf = io.StringIO()
    s["combined"].to_csv(buf, index=False)
    buf.seek(0)
    _log(s, "You", "export", {"context": "prep_csv", "rows": int(len(s["combined"]))})
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=prepared.csv"})


@router.post("/prep/{sid}/finish")
def finish(sid: str, req: FinishRequest) -> dict:
    s = _session(sid)
    df = s["combined"]
    if df is None:
        raise HTTPException(400, "Combine the sheets first.")
    if df.empty or df.shape[1] == 0:
        raise HTTPException(400, "The prepared table is empty - nothing to register.")
    pii = detect_pii(df)
    if pii:
        cols = sorted({f["column"] for f in pii})
        raise HTTPException(400, "Personal data is still present in: "
                            + ", ".join(cols) + ". Drop those columns in the "
                            "clean step before registering.")
    name = (req.name.strip() or "prepared-data") + ".csv"
    ds = store.add_dataset(df, filename=name,
                           pii={"status": "clean", "findings": []},
                           project_id=req.project_id)
    _log(s, "You", "approval", {"context": "prep_finish", "dataset_id": ds.id,
                                "rows": int(len(df)), "name": name})
    return {"dataset_id": ds.id, "filename": name,
            "project_id": ds.project_id, "rows": int(len(df))}
