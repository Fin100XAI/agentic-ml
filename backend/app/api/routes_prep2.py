"""Data Prep Studio v2 (PREP-STUDIO prototype, additive): the inverted,
understand-first flow.

  upload -> PROFILE (deep, deterministic) -> INTERVIEW (grounded questions,
  each with a suggested answer) -> BLUEPRINT (an editable schema contract)
  -> BUILD -> CERTIFY -> bundle (data + dictionary + schema + recipe)

Human in the loop everywhere: the agent proposes, the human decides, and
every answer can be overridden. The narrator agent only PHRASES what the
deterministic profile found - it sees column names, dtypes and counts, never
row values.
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
from engine.blueprint import (apply_blueprint, build_interview, certify,
                              data_dictionary, propose_blueprint)
from engine.pii import detect_pii
from engine.profile_deep import profile_table

router = APIRouter()

_S: dict[str, dict[str, Any]] = {}
_MAX_UPLOAD = 50 * 1024 * 1024


def _sess(sid: str) -> dict[str, Any]:
    s = _S.get(sid)
    if s is None:
        raise HTTPException(404, "Prep session not found (sessions reset when the server restarts).")
    return s


def _log(s: dict, actor: str, event: str, payload: dict) -> None:
    store.log_event(actor, event, mode=payload.pop("mode", "fallback"),
                    payload={"prep2_session": s["id"], **payload})


class AnswersRequest(BaseModel):
    answers: dict[str, Any] = {}


class BlueprintRequest(BaseModel):
    blueprint: dict[str, Any]


class FinishRequest(BaseModel):
    name: str
    project_id: str | None = None


# ---------------------------------------------------------------- 1. upload

@router.post("/prep2/session")
def new_session() -> dict:
    sid = uuid.uuid4().hex[:12]
    _S[sid] = {"id": sid, "sheets": {}, "raw": {}, "headers": {}, "banners": {},
               "combined": None, "profile": None, "interview": None,
               "answers": {}, "blueprint": None, "built": None, "cert": None,
               "steps": []}
    return {"id": sid}


@router.post("/prep2/{sid}/files")
async def add_file(sid: str, file: UploadFile = File(...)) -> dict:
    s = _sess(sid)
    raw = await file.read()
    if len(raw) > _MAX_UPLOAD:
        raise HTTPException(413, "File larger than 50MB - split it first.")
    fname = file.filename or "upload"
    try:
        if fname.lower().endswith((".xlsx", ".xls", ".xlsm")):
            book = pd.read_excel(io.BytesIO(raw), sheet_name=None, header=None)
            added = 0
            for sheet, rawdf in book.items():
                if rawdf.dropna(how="all").empty:
                    continue
                _install(s, f"{fname} :: {sheet}" if len(book) > 1 else fname, rawdf)
                added += 1
            if not added:
                raise HTTPException(400, "The workbook has no non-empty sheets.")
        else:
            _install(s, fname, pd.read_csv(io.BytesIO(raw), header=None,
                                           skip_blank_lines=False))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"Could not read '{fname}': {exc}") from exc
    _reset_downstream(s)
    _log(s, "You", "file_upload", {"context": "prep2", "filename": fname})
    return {"sheets": _sheets(s)}


def _install(s: dict, key: str, rawdf: pd.DataFrame) -> None:
    hdr = prep.detect_header(rawdf)
    s["raw"][key] = rawdf
    s["headers"][key] = hdr
    s["banners"][key] = " ".join(
        str(v) for v in rawdf.iloc[:hdr["row"]].values.flatten() if pd.notna(v))[:400]
    s["sheets"][key] = prep.reheader(rawdf, hdr["row"], hdr["tiers"])


def _reset_downstream(s: dict) -> None:
    s.update({"combined": None, "profile": None, "interview": None,
              "blueprint": None, "built": None, "cert": None, "steps": []})


def _sheets(s: dict) -> list[dict]:
    out = []
    for name, df in s["sheets"].items():
        hdr = s["headers"].get(name, {"row": 0, "tiers": 1})
        note = []
        if hdr["row"] > 0:
            note.append(f"skipped {hdr['row']} banner row(s)")
        if hdr["tiers"] == 2:
            note.append("combined a two-row merged header")
        out.append({"name": name, "rows": int(len(df)), "cols": int(df.shape[1]),
                    "header_row": hdr["row"], "header_tiers": hdr["tiers"],
                    "note": "; ".join(note) or None,
                    "columns": [str(c) for c in df.columns][:40]})
    return out


@router.delete("/prep2/{sid}/files/{name}")
def drop_sheet(sid: str, name: str) -> dict:
    s = _sess(sid)
    if name not in s["sheets"]:
        raise HTTPException(404, "No such sheet.")
    for k in ("sheets", "raw", "headers", "banners"):
        s[k].pop(name, None)
    _reset_downstream(s)
    return {"sheets": _sheets(s)}


class HeaderRequest(BaseModel):
    header_row: int


@router.post("/prep2/{sid}/files/{name}/header")
def set_header(sid: str, name: str, req: HeaderRequest) -> dict:
    s = _sess(sid)
    rawdf = s["raw"].get(name)
    if rawdf is None:
        raise HTTPException(404, "No such sheet.")
    if not 0 <= req.header_row < min(len(rawdf), 20):
        raise HTTPException(400, "Header row must be within the first 20 rows.")
    hdr = prep.detect_header(rawdf, force_row=req.header_row)
    s["headers"][name] = hdr
    s["banners"][name] = " ".join(
        str(v) for v in rawdf.iloc[:hdr["row"]].values.flatten() if pd.notna(v))[:400]
    s["sheets"][name] = prep.reheader(rawdf, hdr["row"], hdr["tiers"])
    _reset_downstream(s)
    _log(s, "You", "approval", {"context": "prep2_header", "sheet": name,
                                "header_row": req.header_row})
    return {"sheets": _sheets(s)}


# --------------------------------------------------------------- 2. profile

@router.post("/prep2/{sid}/profile")
def do_profile(sid: str) -> dict:
    """Combine (deterministic proposal) then deeply understand the table."""
    s = _sess(sid)
    if not s["sheets"]:
        raise HTTPException(400, "Add at least one file first.")
    proposal = prep.propose_combine(s["sheets"])
    if proposal["strategy"] == "review":
        proposal = {**proposal, "strategy": "single", "pick": list(s["sheets"])[0]}
    try:
        combined, report = prep.apply_combine(s["sheets"], proposal)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    banner = " ".join(s["banners"].get(n, "") for n in proposal.get("sheets", []))[:400]
    prof = profile_table(combined, banner)
    prof["pii_columns"] = [{"column": f["column"], "kind": f["kind"]}
                           for f in detect_pii(combined)]
    s["combined"], s["profile"], s["combine_report"] = combined, prof, report
    narrative = _narrate(prof, report)
    _log(s, "Prep profiler", "profile",
         {"context": "prep2_profile", "rows": int(len(combined)),
          "cols": int(combined.shape[1]), "mode": narrative["mode"]})
    return {"combine": report, "profile": prof, "narrative": narrative,
            "preview": _preview(combined)}


def _narrate(prof: dict, report: dict) -> dict:
    """The agent's read of the profile, in plain language. Metadata only."""
    rc = prof["role_counts"]
    fb = (f"{prof['n_rows']:,} rows and {prof['n_cols']} columns: "
          f"{rc['measure']} measure(s), {rc['dimension'] + rc['geography']} grouping "
          f"column(s), {rc['period']} period column(s). "
          + ("The periods run across the columns, so this reads as a report rather "
             "than a table. " if prof.get("wide_blocks") else "")
          + ("Personal data is present and must be handled before anything else. "
             if prof.get("pii_columns") else ""))
    fallback = {"message": fb.strip(), "mode": "fallback"}
    provider = instrumented_provider()
    if provider is None:
        return fallback
    current_agent.set("Prep profiler")
    try:
        meta = {
            "rows": prof["n_rows"], "cols": prof["n_cols"],
            "roles": rc,
            "wide_blocks": bool(prof.get("wide_blocks")),
            "table_unit": (prof.get("table_unit") or {}).get("unit"),
            "banner": prof.get("banner_text"),
            "columns": [{"name": c["source_name"], "type": c["dtype"],
                         "role": c["role"], "missing_pct": c["missing_pct"],
                         "issues": [q["kind"] for q in c["quality"]]}
                        for c in prof["columns"][:40]],
            "grain_candidates": [g["columns"] for g in prof.get("grain_candidates", [])],
            "duplicate_rows": prof.get("duplicate_rows"),
        }
        raw = provider.complete_json(
            "You are a data-preparation analyst. From this PROFILE (column "
            "names, types, roles and counts - you never see values), write "
            "'message': 3-4 short sentences telling the officer what this "
            "table appears to be, what one row seems to stand for, and the "
            "biggest thing to decide before using it. State facts from the "
            "profile only - never invent numbers. Plain hyphens; put a colon "
            "before any number.",
            json.dumps(meta),
            schema={"type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"]},
            max_tokens=450,
        )
        return {"message": str(raw.get("message", ""))[:900] or fb, "mode": "llm"}
    except Exception:
        return fallback


def _preview(df: pd.DataFrame, n: int = 30) -> dict:
    head = df.head(n)
    return {"columns": [str(c) for c in df.columns],
            "rows": json.loads(head.to_json(orient="records", date_format="iso")),
            "n_rows": int(len(df)), "n_cols": int(df.shape[1])}


# ------------------------------------------------------------- 3. interview

@router.post("/prep2/{sid}/interview")
def interview(sid: str) -> dict:
    s = _sess(sid)
    if s["profile"] is None:
        raise HTTPException(400, "Profile the data first.")
    qs = build_interview(s["profile"], s["combined"])
    s["interview"] = qs
    _log(s, "Prep guide", "query_plan",
         {"context": "prep2_interview", "n_questions": len(qs)})
    return {"questions": qs}


# ------------------------------------------------------------- 4. blueprint

@router.post("/prep2/{sid}/blueprint")
def make_blueprint(sid: str, req: AnswersRequest) -> dict:
    s = _sess(sid)
    if s["profile"] is None:
        raise HTTPException(400, "Profile the data first.")
    s["answers"] = req.answers or {}
    bp = propose_blueprint(s["profile"], s["answers"], s["combined"])
    s["blueprint"] = bp
    _log(s, "Prep architect", "query_plan",
         {"context": "prep2_blueprint", "columns": len(bp["columns"]),
          "reshape": bool(bp.get("reshape")), "grain": bp.get("grain")})
    return {"blueprint": bp}


@router.post("/prep2/{sid}/build")
def build(sid: str, req: BlueprintRequest) -> dict:
    """Apply the (possibly hand-edited) blueprint and certify the result."""
    s = _sess(sid)
    if s["combined"] is None:
        raise HTTPException(400, "Profile the data first.")
    bp = req.blueprint
    if not bp.get("columns"):
        raise HTTPException(400, "The blueprint has no columns.")
    kept = [c for c in bp["columns"] if c.get("action") != "drop"]
    if not kept:
        raise HTTPException(400, "Every column is marked drop - nothing would be left.")
    names = [c["name"] for c in kept]
    if len(names) != len(set(names)):
        raise HTTPException(400, "Two columns share the same final name - rename one.")
    try:
        built, steps = apply_blueprint(s["combined"], bp)
    except Exception as exc:
        raise HTTPException(400, f"The blueprint could not be applied: {exc}") from exc
    cert = certify(built, bp)
    s["blueprint"], s["built"], s["cert"], s["steps"] = bp, built, cert, steps
    _log(s, "You", "approval",
         {"context": "prep2_build", "rows": int(len(built)),
          "cols": int(built.shape[1]), "verdict": cert["verdict"]})
    return {"steps": steps, "certificate": cert, "preview": _preview(built),
            "dictionary": data_dictionary(built, bp)}


# ---------------------------------------------------------------- 5. bundle

@router.get("/prep2/{sid}/export/{kind}")
def export(sid: str, kind: str) -> StreamingResponse:
    s = _sess(sid)
    built = s.get("built")
    if built is None:
        raise HTTPException(400, "Build the table first.")
    bp = s["blueprint"]
    if kind == "csv":
        buf = io.StringIO()
        built.to_csv(buf, index=False)
        return _stream(buf.getvalue(), "text/csv", "prepared.csv")
    if kind == "dictionary":
        return _stream(data_dictionary(built, bp), "text/markdown", "data_dictionary.md")
    if kind == "schema":
        schema = {
            "grain": bp.get("grain"), "purpose": bp.get("purpose"),
            "row_rules": bp.get("row_rules"),
            "unit_conversion": bp.get("unit_conversion"),
            "columns": [{k: c.get(k) for k in
                         ("name", "label", "dtype", "role", "unit", "nullable",
                          "description", "source_name", "origin")}
                        for c in bp["columns"] if c.get("action") != "drop"],
            "certificate": s.get("cert"),
        }
        return _stream(json.dumps(schema, indent=2, default=str),
                       "application/json", "schema.json")
    if kind == "recipe":
        recipe = {"version": 1, "headers": {k: v for k, v in s["headers"].items()},
                  "answers": s.get("answers"), "blueprint": bp,
                  "steps": s.get("steps")}
        return _stream(json.dumps(recipe, indent=2, default=str),
                       "application/json", "prep_recipe.json")
    raise HTTPException(404, "Unknown export kind.")


def _stream(text: str, media: str, filename: str) -> StreamingResponse:
    return StreamingResponse(iter([text]), media_type=media,
                             headers={"Content-Disposition": f"attachment; filename={filename}"})


@router.post("/prep2/{sid}/register")
def register(sid: str, req: FinishRequest) -> dict:
    s = _sess(sid)
    built = s.get("built")
    if built is None:
        raise HTTPException(400, "Build the table first.")
    if s["cert"]["errors"]:
        raise HTTPException(400, "The table did not pass its checks - fix the "
                                 "blueprint before registering.")
    pii = detect_pii(built)
    if pii:
        cols = sorted({f["column"] for f in pii})
        raise HTTPException(400, "Personal data is still present in: " + ", ".join(cols)
                            + ". Mark those columns 'drop' in the blueprint first.")
    name = (req.name.strip() or "prepared-data") + ".csv"
    ds = store.add_dataset(built, filename=name,
                           pii={"status": "clean", "findings": []},
                           project_id=req.project_id)
    _log(s, "You", "approval", {"context": "prep2_register", "dataset_id": ds.id,
                                "rows": int(len(built)), "name": name})
    return {"dataset_id": ds.id, "filename": name, "project_id": ds.project_id,
            "rows": int(len(built))}
