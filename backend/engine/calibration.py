"""Calibration check: can the model's probabilities be read literally?

Out-of-fold probabilities from a stratified cross-validation drive a
reliability curve (10 bins), a Brier score, and a plain-language verdict.
Binary classification only; every number is computed here in Python.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.model_selection import StratifiedKFold

from .catalog import get_model
from .catalog.preprocess import RANDOM_SEED, encode_target, structural_frame

MIN_ROWS = 100
MAX_ROWS = 20_000  # beyond this, repeated refits get slow; skip honestly
WELL_ECE = 0.05    # weighted gap below this reads as well calibrated
N_BINS = 10

_NOTES = {
    "well calibrated": (
        "Predicted probabilities track observed outcomes closely. A 0.7 really "
        "means roughly a 70% chance - probabilities can be read literally."
    ),
    "overconfident": (
        "The model's probabilities are more extreme than reality: outcomes it "
        "calls near-certain happen less often than claimed. Treat probabilities "
        "as a ranking (higher = more likely), not as literal chances."
    ),
    "underconfident": (
        "The model's probabilities are too cautious: outcomes happen more "
        "decisively than the numbers suggest. The ranking is trustworthy, but "
        "the literal percentages understate how separable the outcomes are."
    ),
}


def compute_oof(df: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any] | None:
    """Out-of-fold probabilities from a stratified CV - the single source of
    truth for calibration, threshold tuning, and cross-validated metrics.

    Returns None when OOF does not apply (not binary classification, no
    probability support) and {"skipped": True, "note"} when the data is too
    small/large to check honestly.
    """
    if config.get("use_case") != "classification":
        return None
    target = config.get("target")
    if not target or target not in df.columns:
        return None
    plugin = get_model(config["model_key"])
    if not hasattr(plugin, "build_estimator"):
        return None

    data = df.dropna(subset=[target])
    y, class_names = encode_target(data[target])
    if len(class_names) != 2:
        return None
    counts = np.bincount(y)
    if len(data) < MIN_ROWS or counts.min() < 10:
        return {
            "skipped": True,
            "note": "Skipped: too few rows (or too few examples of the rarer outcome) "
                    "to measure probability quality reliably.",
        }
    if len(data) > MAX_ROWS:
        return {
            "skipped": True,
            "note": f"Skipped: {len(data):,} rows would make the repeated refits slow.",
        }

    est = plugin.build_estimator(config["hyperparams"])
    if not hasattr(est, "predict_proba"):
        return None
    # Structural prep only; the pipeline refits impute/encode per fold.
    X = structural_frame(data, target=target, features=config.get("features"))
    k = 5 if counts.min() >= 5 else 3
    cv = StratifiedKFold(n_splits=k, shuffle=True, random_state=RANDOM_SEED)
    # Manual out-of-fold loop (cross_val_predict trips on xgboost/sklearn
    # tag interop); every row is predicted by a model that never saw it.
    proba = np.zeros(len(y))
    fold_ids = np.zeros(len(y), dtype=int)
    for fold, (train_idx, test_idx) in enumerate(cv.split(X, y)):
        fold_model = clone(est)
        fold_model.fit(X.iloc[train_idx], y[train_idx])
        proba[test_idx] = fold_model.predict_proba(X.iloc[test_idx])[:, 1]
        fold_ids[test_idx] = fold

    return {
        "skipped": False,
        "proba": [round(float(p), 6) for p in proba],
        "y_true": [int(v) for v in y],
        "fold": [int(f) for f in fold_ids],
        "class_names": class_names,
        "cv_folds": k,
        "n": int(len(y)),
    }


def calibration_from_oof(oof: dict[str, Any]) -> dict[str, Any]:
    """Reliability curve + Brier score from a computed OOF vector."""
    proba = np.asarray(oof["proba"], dtype=float)
    y = np.asarray(oof["y_true"], dtype=int)
    class_names = oof["class_names"]
    k = oof["cv_folds"]

    brier = float(np.mean((proba - y) ** 2))
    bins: list[dict[str, Any]] = []
    ece = 0.0        # weighted |predicted - observed| across bins
    extremity = 0.0  # + when probabilities are more extreme than outcomes
    edges = np.linspace(0.0, 1.0, N_BINS + 1)
    for i in range(N_BINS):
        lo, hi = edges[i], edges[i + 1]
        mask = (proba >= lo) & (proba < hi) if i < N_BINS - 1 else (proba >= lo) & (proba <= hi)
        cnt = int(mask.sum())
        if cnt == 0:
            continue
        pred = float(proba[mask].mean())
        obs = float(y[mask].mean())
        bins.append({
            "midpoint": round((lo + hi) / 2, 2),
            "predicted": round(pred, 4),
            "observed": round(obs, 4),
            "count": cnt,
        })
        gap = pred - obs
        ece += cnt * abs(gap)
        # Above 0.5 an overconfident model predicts too high; below 0.5, too low.
        extremity += cnt * (gap if pred >= 0.5 else -gap)
    ece /= len(y)
    extremity /= len(y)

    if ece <= WELL_ECE:
        verdict = "well calibrated"
    elif extremity > 0:
        verdict = "overconfident"
    else:
        verdict = "underconfident"

    return {
        "skipped": False,
        "verdict": verdict,
        "brier": round(brier, 4),
        "ece": round(float(ece), 4),
        "n": int(len(y)),
        "cv_folds": k,
        "labels": class_names,
        "bins": bins,
        "note": _NOTES[verdict],
    }


def threshold_curve_from_oof(oof: dict[str, Any]) -> dict[str, Any]:
    """Precision/recall/F1 across 19 thresholds, from OOF predictions ONLY.

    A threshold selected and evaluated on the same in-sample predictions
    inflates the reported metric; out-of-fold selection is honest.
    """
    proba = np.asarray(oof["proba"], dtype=float)
    y = np.asarray(oof["y_true"], dtype=int)
    points = []
    best_f1, best_thr = -1.0, 0.5
    for thr in np.arange(0.05, 0.96, 0.05):
        yp = (proba >= thr).astype(int)
        tp = int(((yp == 1) & (y == 1)).sum())
        fp = int(((yp == 1) & (y == 0)).sum())
        fn = int(((yp == 0) & (y == 1)).sum())
        tn = int(((yp == 0) & (y == 0)).sum())
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f = 2 * p * r / (p + r) if p + r else 0.0
        points.append({
            "threshold": round(float(thr), 2),
            "precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        })
        if f > best_f1:
            best_f1, best_thr = f, round(float(thr), 2)
    return {
        "labels": oof["class_names"],
        "suggested": best_thr,
        "points": points,
        "source": "oof_cv",
        "n": int(len(y)),
        "cv_folds": oof["cv_folds"],
    }


def cv_metrics_from_oof(oof: dict[str, Any], threshold: float) -> dict[str, float]:
    """Cross-validated headline metrics at the chosen operating point."""
    from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score, roc_auc_score

    proba = np.asarray(oof["proba"], dtype=float)
    y = np.asarray(oof["y_true"], dtype=int)
    yp = (proba >= threshold).astype(int)
    out = {
        "f1_cv": round(float(f1_score(y, yp, zero_division=0)), 4),
        "precision_cv": round(float(precision_score(y, yp, zero_division=0)), 4),
        "recall_cv": round(float(recall_score(y, yp, zero_division=0)), 4),
    }
    try:
        out["roc_auc_cv"] = round(float(roc_auc_score(y, proba)), 4)
        out["pr_auc_cv"] = round(float(average_precision_score(y, proba)), 4)
    except ValueError:
        pass
    return out


def calibration_check(df: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any] | None:
    """Back-compat wrapper: compute OOF then the reliability verdict."""
    oof = compute_oof(df, config)
    if oof is None or oof.get("skipped"):
        return oof
    return calibration_from_oof(oof)
