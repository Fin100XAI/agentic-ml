"""Score a fresh file with a registered model version.

The whole point of storing lineage params: the new file goes through the SAME
preprocessing the model was trained with - PII masking config, approved
remediation fixes, engineered features, leakage exclusions - reconstructed
from the training run, then aligned to the exact trained feature list.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .catalog.preprocess import select_feature_frame
from .features import apply_features
from .librarian import _normalize
from .pii import apply_pii_actions
from .remediation import apply_fixes

PREVIEW_ROWS = 50
HIST_BINS = 15


def reconcile_schema(
    new_cols: list[str], raw_columns: list[str], target: str | None
) -> dict[str, Any]:
    """Map incoming columns onto the training schema via keyword normalization."""
    expected = [c for c in raw_columns if c != target]
    new_by_norm = {_normalize(c): c for c in new_cols}
    mapping: dict[str, str] = {}   # new-file name -> expected name
    renamed: list[dict[str, str]] = []
    missing: list[str] = []
    for exp in expected:
        src = new_by_norm.get(_normalize(exp))
        if src is None:
            missing.append(exp)
        else:
            mapping[src] = exp
            if src != exp:
                renamed.append({"from": src, "to": exp})
    extra = [c for c in new_cols if c not in mapping and _normalize(c) != _normalize(target or "")]
    return {"mapping": mapping, "renamed": renamed, "missing": missing, "extra": extra,
            "ok": not missing}


def rebuild_and_score(
    new_df: pd.DataFrame,
    entry: dict[str, Any],
    model: Any,
    train_config: dict[str, Any],
    pii_actions: dict[str, str] | None,
    pii_findings: list[dict[str, Any]] | None,
    remediation: dict[str, Any] | None,
    class_names: list[str] | None,
    threshold: float = 0.5,
) -> dict[str, Any]:
    """Apply the training-time lineage to a reconciled frame and predict."""
    target = train_config.get("target")
    recon = reconcile_schema(list(new_df.columns), entry["raw_columns"], target)
    if not recon["ok"]:
        raise ValueError(
            "This file is missing columns the model needs: "
            + ", ".join(f"'{m}'" for m in recon["missing"])
            + ". The model can only score data with the same information it was trained on."
        )

    work = new_df.rename(columns=recon["mapping"])

    # 1. Same PII protection the training data had.
    if pii_actions and pii_findings:
        effective = {c: a for c, a in pii_actions.items() if a != "keep"}
        if effective:
            work = apply_pii_actions(work, pii_findings, effective)

    # 2. Same approved data fixes (dedupe is skipped - every incoming row
    #    deserves a prediction, even a duplicate).
    if remediation and remediation.get("status") == "applied":
        proposals = [p for p in remediation.get("proposals", []) if p["kind"] != "dedupe"]
        accepted = [i for i in remediation.get("applied_ids", []) if i != "dedupe"]
        work = apply_fixes(work, proposals, accepted)

    # 3. Same engineered features and leakage exclusions.
    work = apply_features(work, train_config.get("engineered") or [])
    work = work.drop(columns=train_config.get("excluded") or [], errors="ignore")

    # 4. Same numeric frame, aligned to the exact trained columns (unseen
    #    one-hot categories become 0; anything extra is dropped).
    X = select_feature_frame(work, target=target, features=train_config.get("features"))
    X = X.reindex(columns=entry["feature_list"], fill_value=0.0)

    preds = model.predict(X)
    out = new_df.copy()
    use_case = entry["use_case"]
    probability = None
    if use_case == "classification":
        if class_names and len(class_names) > 0:
            labels = [class_names[int(p)] if 0 <= int(p) < len(class_names) else str(p) for p in preds]
        else:
            labels = [str(p) for p in preds]
        out["prediction"] = labels
        if hasattr(model, "predict_proba"):
            proba = model.predict_proba(X)
            if proba.shape[1] == 2:
                probability = np.round(proba[:, 1], 4)
                out["probability"] = probability
    else:
        out["prediction"] = np.round(np.asarray(preds, dtype=float), 4)

    return {
        "scored": out,
        "reconciliation": recon,
        "distribution": _distribution(out, use_case),
        "threshold_note": (
            f"Class labels use the standard 0.5 probability threshold."
            if use_case == "classification" and probability is not None else None
        ),
    }


def _distribution(out: pd.DataFrame, use_case: str) -> dict[str, Any]:
    if use_case == "classification":
        counts = out["prediction"].value_counts()
        return {"kind": "classes",
                "data": [{"label": str(k), "count": int(v)} for k, v in counts.items()]}
    vals = pd.to_numeric(out["prediction"], errors="coerce").dropna()
    counts, edges = np.histogram(vals, bins=min(HIST_BINS, max(5, len(vals) // 10 or 5)))
    return {"kind": "histogram",
            "data": [{"mid": round(float((edges[i] + edges[i + 1]) / 2), 4), "count": int(c)}
                     for i, c in enumerate(counts)]}


def summary_template(entry: dict[str, Any], result: dict[str, Any], n: int) -> str:
    dist = result["distribution"]
    if dist["kind"] == "classes":
        parts = ", ".join(f"{d['count']:,} ({d['count']/n:.0%}) '{d['label']}'" for d in dist["data"][:4])
        return (f"Scored {n:,} records with {entry['model_name']} v{entry['version']}: {parts}. "
                "Predictions inherit the model's training-time accuracy - treat borderline "
                "probabilities as review candidates, not verdicts.")
    vals = [d["mid"] for d in dist["data"] for _ in range(d["count"])]
    mean = float(np.mean(vals)) if vals else 0.0
    return (f"Scored {n:,} records with {entry['model_name']} v{entry['version']}: predictions "
            f"average {mean:,.1f}. Read each number with the model's typical training error "
            "as a margin, not as an exact value.")
