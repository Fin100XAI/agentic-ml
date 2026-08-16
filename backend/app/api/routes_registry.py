"""Model registry endpoints: versioned trained models, retraining, scoring."""
from __future__ import annotations

import io
import pickle
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.store import store
from app.telemetry import instrumented_orchestrator, instrumented_provider, set_run_context
from engine.orchestrator import Run
from engine.scoring import rebuild_and_score, summary_template

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


@router.post("/models/{model_id}/{version}/score")
async def score_new_data(model_id: str, version: int, file: UploadFile) -> dict:
    """Apply a registered model version to a fresh file."""
    try:
        entry = store.get_registry_entry(model_id, version)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    if not entry.get("checkpoint_path") or not Path(entry["checkpoint_path"]).exists():
        raise HTTPException(409, "This model version has no loadable checkpoint - only "
                                 "classification and regression models can score new data.")
    train_run = store.runs.get(entry.get("run_id") or "")
    if train_run is None or not train_run.config:
        raise HTTPException(409, "The training run behind this version is no longer available.")

    name = (file.filename or "").lower()
    raw = await file.read()
    try:
        if name.endswith((".xlsx", ".xls")):
            new_df = pd.read_excel(io.BytesIO(raw))
        else:
            new_df = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:
        raise HTTPException(400, f"Could not parse the file: {exc}") from exc

    model = pickle.loads(Path(entry["checkpoint_path"]).read_bytes())
    ds = store.datasets.get(train_run.dataset_id)
    try:
        result = rebuild_and_score(
            new_df, entry, model, train_run.config,
            pii_actions=(ds.pii or {}).get("actions") if ds else None,
            pii_findings=(ds.pii or {}).get("findings") if ds else None,
            remediation=train_run.remediation,
            class_names=(train_run.result or {}).get("class_names"),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    scored = result["scored"]
    art = store.add_derived_artifact(
        scored, [entry["artifact_id"]] if entry.get("artifact_id") else [],
        "score", {"model_id": model_id, "version": version, "source_file": file.filename},
        project_id=entry.get("project_id"),
    )

    summary = summary_template(entry, result, len(scored))
    generated_by = "heuristic"
    provider = instrumented_provider()
    if provider is not None:
        try:
            summary = provider.complete_text(
                "You summarize model scoring results for non-experts in 2-3 plain sentences. "
                "Never invent numbers; only rephrase the given facts. Style rule: use plain "
                "hyphens (-) only; never use em dashes or en dashes.",
                f"Facts: {summary}\nDistribution: {result['distribution']}",
                max_tokens=300,
            )
            generated_by = "claude"
        except Exception:
            pass

    store.log_event(
        "user", "score", dataset_id=train_run.dataset_id, artifact_id=art.id,
        project_id=entry.get("project_id"),
        payload={"model_id": model_id, "version": version,
                 "file": file.filename, "rows": int(len(scored))},
    )
    preview_cols = list(scored.columns)[:8] + [c for c in ("prediction", "probability") if c in scored.columns]
    preview_cols = list(dict.fromkeys(preview_cols))
    return {
        "n": int(len(scored)),
        "reconciliation": {k: v for k, v in result["reconciliation"].items() if k != "mapping"},
        "distribution": result["distribution"],
        "threshold_note": result["threshold_note"],
        "summary": summary,
        "generated_by": generated_by,
        "artifact_id": art.id,
        "preview": scored[preview_cols].head(50).where(pd.notna(scored[preview_cols].head(50)), None).to_dict("records"),
    }


@router.post("/models/{model_id}/{version}/drift")
async def check_drift(model_id: str, version: int, file: UploadFile) -> dict:
    """Compare a fresh file against a model version's training data."""
    from engine.drift import drift_check
    from engine.scoring import rebuild_and_score

    try:
        entry = store.get_registry_entry(model_id, version)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    train_run = store.runs.get(entry.get("run_id") or "")
    if train_run is None or not train_run.config:
        raise HTTPException(409, "The training run behind this version is no longer available.")

    name = (file.filename or "").lower()
    raw = await file.read()
    try:
        new_df = (pd.read_excel(io.BytesIO(raw)) if name.endswith((".xlsx", ".xls"))
                  else pd.read_csv(io.BytesIO(raw)))
    except Exception as exc:
        raise HTTPException(400, f"Could not parse the file: {exc}") from exc

    target = train_run.config.get("target")
    # Score only when the outcome came along AND a checkpoint exists -
    # that unlocks the performance-decay check.
    scored = None
    has_outcome = bool(target) and any(
        str(c).strip().lower().replace(" ", "_") == str(target).strip().lower()
        for c in new_df.columns
    )
    if has_outcome and entry.get("checkpoint_path") and Path(entry["checkpoint_path"]).exists():
        try:
            model = pickle.loads(Path(entry["checkpoint_path"]).read_bytes())
            ds = store.datasets.get(train_run.dataset_id)
            scored = rebuild_and_score(
                new_df, entry, model, train_run.config,
                pii_actions=(ds.pii or {}).get("actions") if ds else None,
                pii_findings=(ds.pii or {}).get("findings") if ds else None,
                remediation=train_run.remediation,
                class_names=(train_run.result or {}).get("class_names"),
            )["scored"]
        except ValueError:
            scored = None  # schema too broken to score; drift report still runs

    try:
        report = drift_check(entry, train_run.df, new_df, target, scored)
    except Exception as exc:
        raise HTTPException(400, f"Drift check failed: {exc}") from exc

    narrative = report["note"]
    generated_by = "heuristic"
    provider = instrumented_provider()
    if provider is not None:
        try:
            narrative = provider.complete_text(
                "You explain a model drift report to a non-expert in 2-4 plain sentences: "
                "is the incoming data still like the training data, which columns moved, "
                "did accuracy hold, and what to do. Never invent numbers. Style rule: use "
                "plain hyphens (-) only; never use em dashes or en dashes.",
                f"Verdict: {report['verdict']}\nFacts: {report['note']}\n"
                f"Shifted columns: {[c for c in report['columns'] if c['label'] != 'stable']}\n"
                f"Decay: {report['decay']}",
                max_tokens=300,
            )
            generated_by = "claude"
        except Exception:
            pass

    store.log_event(
        "user", "drift", dataset_id=train_run.dataset_id, project_id=entry.get("project_id"),
        payload={"model_id": model_id, "version": version, "file": file.filename,
                 "verdict": report["verdict"], "n_shifted": report["n_shifted"]},
    )
    return {**report, "narrative": narrative, "generated_by": generated_by,
            "model_name": entry["model_name"], "version": version}


def _load_scenario_context(model_id: str, version: int):
    try:
        entry = store.get_registry_entry(model_id, version)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    if entry["use_case"] not in ("classification", "regression"):
        raise HTTPException(409, "What-if works on classification and regression models only.")
    if not entry.get("checkpoint_path") or not Path(entry["checkpoint_path"]).exists():
        raise HTTPException(409, "This model version has no loadable checkpoint.")
    train_run = store.runs.get(entry.get("run_id") or "")
    if train_run is None or not train_run.config:
        raise HTTPException(409, "The training run behind this version is no longer available.")
    model = pickle.loads(Path(entry["checkpoint_path"]).read_bytes())
    return entry, train_run, model


@router.get("/models/{model_id}/{version}/scenario/meta")
def scenario_meta(model_id: str, version: int) -> dict:
    entry, train_run, _ = _load_scenario_context(model_id, version)
    if not entry.get("baseline"):
        raise HTTPException(409, "This model version predates scenario support - retrain it once to enable what-if.")
    labels = train_run.labels()
    features = [
        {"column": col, "label": labels.get(col, col),
         "min": rng[0], "max": rng[1],
         "baseline": (entry.get("baseline") or {}).get(col)}
        for col, rng in (entry.get("feature_ranges") or {}).items()
    ]
    return {"features": features, "response": "probability" if entry["use_case"] == "classification" else "prediction"}


@router.post("/models/{model_id}/{version}/scenario")
def what_if(model_id: str, version: int, req: dict) -> dict:
    from engine.scenario import run_scenario

    entry, train_run, model = _load_scenario_context(model_id, version)
    perturbations = req.get("perturbations") or {}
    if not perturbations or len(perturbations) > 3:
        raise HTTPException(400, "Perturb between one and three features.")
    try:
        result = run_scenario(
            entry, model, train_run.config, train_run.remediation,
            (train_run.result or {}).get("class_names"), perturbations,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    phrased = None
    provider = instrumented_provider()
    if provider is not None:
        try:
            phrased = provider.complete_text(
                "In 2-3 plain sentences, explain a what-if result on a prediction model "
                "to a non-expert. Always keep the correlation-not-causation framing from "
                "the caveat. Never invent numbers. Style rule: use plain hyphens (-) "
                "only; never use em dashes or en dashes.",
                f"Facts: {result}",
                max_tokens=250,
            )
        except Exception:
            pass
    store.log_event(
        "user", "score", project_id=entry.get("project_id"),
        payload={"kind": "scenario", "model_id": model_id, "version": version,
                 "perturbations": perturbations},
    )
    return {**result, "phrased": phrased}


@router.post("/models/{model_id}/{version}/scenario/curve")
def scenario_curve(model_id: str, version: int, req: dict) -> dict:
    from engine.scenario import response_curve

    entry, train_run, model = _load_scenario_context(model_id, version)
    feature = str(req.get("feature") or "")
    try:
        return response_curve(
            entry, model, train_run.config, train_run.remediation,
            (train_run.result or {}).get("class_names"), feature,
            others=req.get("others") or None,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/artifacts/{artifact_id}/download")
def download_artifact_csv(artifact_id: str) -> Response:
    """Any frame artifact as CSV - used for scored outputs."""
    try:
        art = store.get_artifact(artifact_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    path = Path(art.file_path)
    if not path.exists() or not art.file_path.endswith(".pkl"):
        raise HTTPException(409, "This artifact is not a downloadable table.")
    frame = pickle.loads(path.read_bytes())
    csv_bytes = frame.to_csv(index=False).encode("utf-8-sig")
    store.log_event("user", "export", artifact_id=artifact_id,
                    payload={"format": "csv", "rows": int(len(frame))})
    return Response(
        content=csv_bytes, media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{art.transform_type}_{artifact_id}.csv"'},
    )


@router.post("/models/{model_id}/{version}/threshold")
def set_threshold(model_id: str, version: int, req: dict) -> dict:
    """Store the human-approved decision threshold; scoring uses it."""
    thr = req.get("threshold")
    if not isinstance(thr, (int, float)) or not (0.01 <= float(thr) <= 0.99):
        raise HTTPException(400, "Threshold must be between 0.01 and 0.99.")
    try:
        store.set_decision_threshold(model_id, version, float(thr))
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    store.log_event("user", "approval",
                    payload={"gate": "decision_threshold", "model_id": model_id,
                             "version": version, "threshold": float(thr)})
    return {"model_id": model_id, "version": version, "threshold": float(thr)}


@router.post("/models/{model_id}/{version}/archive")
def archive_model_version(model_id: str, version: int) -> dict:
    try:
        store.archive_model(model_id, version)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    store.log_event("user", "approval",
                    payload={"gate": "registry_archive", "model_id": model_id, "version": version})
    return {"archived": f"{model_id} v{version}"}
