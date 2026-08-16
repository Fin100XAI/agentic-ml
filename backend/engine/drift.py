"""Drift monitor: has the world moved away from what a model was trained on?

Given a registered model version and a fresh file, three deterministic checks:

(a) schema drift  - missing / renamed / new columns via keyword matching
(b) distribution shift - PSI per shared numeric column, chi-square for
    low-cardinality categoricals, rolled into one overall shift score
(c) performance decay - when the fresh file carries the outcome column, the
    model is scored on it and its metrics compared to training time

Verdict: stable / drifting / degraded. Degraded links to the retrain flow.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .rundiff import PSI_MODERATE, PSI_STABLE, psi
from .scoring import reconcile_schema

CAT_MAX_LEVELS = 30
DECAY_RELATIVE = 0.15  # >15% worse on the primary metric = degraded

_PRIMARY = {"classification": ("f1", True), "regression": ("rmse", False)}


def drift_check(
    entry: dict[str, Any],
    train_df: pd.DataFrame,
    new_df: pd.DataFrame,
    target: str | None,
    scored: pd.DataFrame | None = None,  # rebuild_and_score output when outcome present
) -> dict[str, Any]:
    # (a) schema drift
    recon = reconcile_schema(list(new_df.columns), entry["raw_columns"], target)
    work = new_df.rename(columns=recon["mapping"])

    # (b) distribution shift on shared columns
    columns: list[dict[str, Any]] = []
    shared = [c for c in entry["raw_columns"] if c != target and c in work.columns]
    for col in shared:
        a, b = train_df.get(col), work[col]
        if a is None:
            continue
        if pd.api.types.is_numeric_dtype(a) and a.nunique() > 2:
            v = psi(a, b)
            if v is not None:
                columns.append({
                    "column": str(col), "kind": "numeric", "score": round(v, 4),
                    "label": "stable" if v < PSI_STABLE else "moderate shift" if v < PSI_MODERATE else "major shift",
                })
        elif a.nunique(dropna=True) <= CAT_MAX_LEVELS:
            p = _chi_square_p(a, b)
            if p is not None:
                columns.append({
                    "column": str(col), "kind": "categorical", "score": round(p, 4),
                    "label": "stable" if p >= 0.05 else "moderate shift" if p >= 0.001 else "major shift",
                })
    columns.sort(key=lambda c: (c["label"] == "stable", c["column"]))
    n_shifted = sum(1 for c in columns if c["label"] != "stable")
    numeric_psis = [c["score"] for c in columns if c["kind"] == "numeric"]
    overall = round(float(np.mean(numeric_psis)), 4) if numeric_psis else 0.0

    # (c) performance decay when the outcome came along
    decay = None
    if scored is not None and target and target in new_df.columns:
        decay = _performance_decay(entry, new_df[target], scored)

    # Verdict
    schema_broken = bool(recon["missing"])
    if decay and decay["degraded"]:
        verdict = "degraded"
    elif schema_broken or n_shifted > 0 and (
        any(c["label"] == "major shift" for c in columns) or n_shifted / max(len(columns), 1) > 0.3
    ):
        verdict = "drifting"
    elif n_shifted > 0:
        verdict = "drifting" if overall >= PSI_STABLE else "stable"
    else:
        verdict = "stable"

    return {
        "verdict": verdict,
        "schema": {"missing": recon["missing"], "renamed": recon["renamed"], "extra": recon["extra"]},
        "columns": columns,
        "n_shifted": n_shifted,
        "overall_shift": overall,
        "decay": decay,
        "note": _note(verdict, columns, decay, recon),
    }


def _chi_square_p(a: pd.Series, b: pd.Series) -> float | None:
    from scipy.stats import chi2_contingency

    ca = a.astype(str).value_counts()
    cb = b.astype(str).value_counts()
    levels = sorted(set(ca.index) | set(cb.index))
    if len(levels) < 2 or len(a.dropna()) < 20 or len(b.dropna()) < 20:
        return None
    table = np.array([[ca.get(l, 0) for l in levels], [cb.get(l, 0) for l in levels]]) + 1
    try:
        return float(chi2_contingency(table)[1])
    except Exception:
        return None


def _performance_decay(
    entry: dict[str, Any], actual: pd.Series, scored: pd.DataFrame
) -> dict[str, Any] | None:
    use_case = entry["use_case"]
    if use_case not in _PRIMARY or "prediction" not in scored.columns:
        return None
    metric, higher_better = _PRIMARY[use_case]
    train_value = (entry.get("metrics") or {}).get(metric)
    if not isinstance(train_value, (int, float)):
        return None

    if use_case == "classification":
        from sklearn.metrics import f1_score

        y_true = actual.astype(str).values
        y_pred = scored["prediction"].astype(str).values
        labels = sorted(set(y_true) | set(y_pred))
        average = "binary" if len(labels) == 2 else "weighted"
        try:
            new_value = float(f1_score(y_true, y_pred, average=average,
                                       pos_label=labels[-1] if average == "binary" else 1,
                                       zero_division=0))
        except Exception:
            return None
    else:
        y_true = pd.to_numeric(actual, errors="coerce")
        y_pred = pd.to_numeric(scored["prediction"], errors="coerce")
        ok = y_true.notna() & y_pred.notna()
        if ok.sum() < 20:
            return None
        new_value = float(np.sqrt(np.mean((y_true[ok] - y_pred[ok]) ** 2)))

    worse = (train_value - new_value) if higher_better else (new_value - train_value)
    rel = worse / abs(train_value) if train_value else 0.0
    return {
        "metric": metric,
        "train": round(float(train_value), 4),
        "new": round(new_value, 4),
        "relative_change_pct": round(rel * 100, 1),
        "degraded": rel > DECAY_RELATIVE,
    }


def _note(verdict: str, columns: list[dict], decay: dict | None, recon: dict) -> str:
    shifted = [c["column"] for c in columns if c["label"] != "stable"]
    if verdict == "degraded" and decay:
        return (f"The model's {decay['metric']} on this new data is {decay['new']} vs {decay['train']} "
                f"at training time - about {abs(decay['relative_change_pct'])}% worse. "
                "The world has moved; retraining on recent data is the standard fix.")
    if verdict == "drifting":
        parts = []
        if recon["missing"]:
            parts.append("expected columns are missing: " + ", ".join(recon["missing"]))
        if shifted:
            parts.append("these columns look different from training: " + ", ".join(shifted[:4]))
        return ("The new data has drifted from what the model learned on - "
                + "; ".join(parts) + ". Predictions still run, but treat them more cautiously, "
                "and consider retraining.")
    return ("The new data looks statistically similar to the training data - "
            "the model is operating on familiar ground.")
