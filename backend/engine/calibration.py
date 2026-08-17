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


def calibration_check(df: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any] | None:
    """Reliability curve + Brier score from out-of-fold CV probabilities.

    Returns None when calibration does not apply (not binary classification,
    no probability support) and an honest skip record when data is too
    small/large to check.
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
    for train_idx, test_idx in cv.split(X, y):
        fold_model = clone(est)
        fold_model.fit(X.iloc[train_idx], y[train_idx])
        proba[test_idx] = fold_model.predict_proba(X.iloc[test_idx])[:, 1]

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
