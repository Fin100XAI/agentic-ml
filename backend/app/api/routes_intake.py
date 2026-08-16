"""Intake rules + inbox: standing instructions for recurring files.

A rule ties a registered model version to an action (score / drift-check /
retrain). New uploads whose columns match the rule land in the inbox as
pending items. Nothing executes until a human approves - approve runs the
action through the exact same code paths as doing it by hand; decline
discards the proposal. Cadence is an expectation, not a scheduler: overdue
rules are flagged, never auto-fired.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.routes_registry import drift_frame, score_frame, start_retrain
from app.store import store
from engine.librarian import _normalize

router = APIRouter()

ACTIONS = ("score", "drift", "retrain")
CADENCES = ("none", "weekly", "monthly")


class RuleRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    model_id: str
    version: int
    action: str
    cadence: str = "none"
    name: str | None = None


class ResolveRequest(BaseModel):
    decision: str  # "approve" | "decline"


@router.get("/projects/{project_id}/intake")
def get_intake(project_id: str) -> dict:
    if project_id not in store.projects:
        raise HTTPException(404, f"Unknown project: {project_id}")
    rules = store.list_intake_rules(project_id)
    by_id = {r["id"]: r for r in rules}
    items = store.list_intake_items(project_id)
    for item in items:
        rule = by_id.get(item["rule_id"])
        item["rule_name"] = rule["name"] if rule else "(deleted rule)"
        item["action"] = rule["action"] if rule else None
    return {"rules": rules, "items": items}


@router.post("/projects/{project_id}/intake-rules")
def create_rule(project_id: str, req: RuleRequest) -> dict:
    if project_id not in store.projects:
        raise HTTPException(404, f"Unknown project: {project_id}")
    if req.action not in ACTIONS:
        raise HTTPException(400, f"Action must be one of {ACTIONS}.")
    if req.cadence not in CADENCES:
        raise HTTPException(400, f"Cadence must be one of {CADENCES}.")
    try:
        entry = store.get_registry_entry(req.model_id, req.version)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    if req.action in ("score", "drift") and not entry.get("checkpoint_path"):
        raise HTTPException(409, "That version has no loadable checkpoint - only "
                                 "classification and regression models can score or drift-check.")

    # Match on the training schema minus the target: score files won't carry
    # the outcome, and retrain/drift files simply have one extra column.
    train_run = store.runs.get(entry.get("run_id") or "")
    target = (train_run.config or {}).get("target") if train_run else None
    required = sorted({
        _normalize(str(c)) for c in entry.get("raw_columns") or []
        if not target or _normalize(str(c)) != _normalize(str(target))
    })
    if not required:
        raise HTTPException(409, "That version recorded no training columns to match on.")

    name = req.name or f"{entry['model_name']} - {req.action} incoming files"
    rule = store.add_intake_rule(
        project_id, name, req.model_id, req.version, req.action, req.cadence, required,
    )
    store.log_event(
        "user", "approval", project_id=project_id,
        payload={"gate": "intake_rule_created", "rule_id": rule["id"], "name": name,
                 "model_id": req.model_id, "version": req.version,
                 "action": req.action, "cadence": req.cadence},
    )
    rule["overdue"] = False
    return rule


@router.delete("/intake-rules/{rule_id}")
def delete_rule(rule_id: str) -> dict:
    try:
        rule = store.get_intake_rule(rule_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    store.delete_intake_rule(rule_id)
    store.log_event(
        "user", "decline", project_id=rule["project_id"],
        payload={"gate": "intake_rule_deleted", "rule_id": rule_id, "name": rule["name"]},
    )
    return {"deleted": rule_id}


@router.post("/intake/{item_id}/resolve")
def resolve_item(item_id: str, req: ResolveRequest) -> dict:
    if req.decision not in ("approve", "decline"):
        raise HTTPException(400, "Decision must be approve or decline.")
    try:
        item = store.get_intake_item(item_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    if item["status"] != "pending":
        raise HTTPException(409, f"This intake item is already {item['status']}.")

    if req.decision == "decline":
        store.resolve_intake_item(item_id, "declined")
        store.log_event(
            "user", "decline", dataset_id=item["dataset_id"], project_id=item["project_id"],
            payload={"gate": "intake_item", "item_id": item_id, "file": item["filename"]},
        )
        return {"item": store.get_intake_item(item_id)}

    try:
        rule = store.get_intake_rule(item["rule_id"])
        entry = store.get_registry_entry(rule["model_id"], rule["version"])
        ds = store.get_dataset(item["dataset_id"])
    except KeyError as exc:
        raise HTTPException(409, f"Cannot execute this intake anymore: {exc}") from exc
    if ds.pii and ds.pii.get("status") == "pending":
        raise HTTPException(409, "PII review pending on that dataset - approve its privacy screen first.")
    train_run = store.runs.get(entry.get("run_id") or "")
    if rule["action"] in ("score", "drift") and (train_run is None or not train_run.config):
        raise HTTPException(409, "The training run behind this model version is no longer available.")

    try:
        if rule["action"] == "score":
            res = score_frame(entry, train_run, ds.df, item["filename"] or ds.filename)
            results = {"kind": "score", "n": res["n"], "summary": res["summary"],
                       "distribution": res["distribution"], "artifact_id": res["artifact_id"],
                       "threshold_note": res.get("threshold_note")}
        elif rule["action"] == "drift":
            res = drift_frame(entry, train_run, ds.df, item["filename"] or ds.filename)
            results = {"kind": "drift", "verdict": res["verdict"], "n_shifted": res["n_shifted"],
                       "narrative": res["narrative"], "decay": res.get("decay")}
        else:  # retrain: advances to the configure gate; training still needs approval
            res = start_retrain(entry, ds)
            results = {"kind": "retrain", "run_id": res["run"]["id"], "prefill": res["prefill"]}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    store.resolve_intake_item(item_id, "approved", results)
    store.touch_intake_rule(rule["id"])
    store.log_event(
        "user", "approval", dataset_id=item["dataset_id"], project_id=item["project_id"],
        payload={"gate": "intake_item", "item_id": item_id, "file": item["filename"],
                 "action": rule["action"], "rule": rule["name"]},
    )
    return {"item": store.get_intake_item(item_id)}
