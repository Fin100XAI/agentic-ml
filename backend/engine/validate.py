"""Stability checks: does the headline score survive resampling?

Each use case gets the check that fits how its models are evaluated:

- classification: stratified k-fold cross-validation (the split-based score
  from training is one draw; this shows the spread across k draws)
- forecasting: rolling-origin backtests - the model is re-fit on earlier cuts
  of the history so the error is measured from several forecast origins
- clustering: subsample stability - the model is re-run on 80% draws to see
  whether the grouping quality depends on particular rows

Everything is seeded and deterministic. Returns None when no meaningful check
exists, or a dict with ``skipped: True`` and a note when the data is too small
or too large to check honestly.
"""
from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd

from .catalog import get_model
from .catalog.preprocess import RANDOM_SEED, encode_target, structural_frame

MAX_ROWS = 50_000


def stability_check(
    df: pd.DataFrame, config: dict[str, Any], result_metrics: dict[str, Any]
) -> dict[str, Any] | None:
    use_case = config.get("use_case")
    if len(df) > MAX_ROWS:
        return {
            "skipped": True,
            "label": "Stability check",
            "note": f"Skipped: {len(df):,} rows would make repeated retraining slow. "
                    "The single held-out evaluation stands on its own at this size.",
        }
    started = time.time()
    if use_case == "classification":
        out = _kfold_classification(df, config)
    elif use_case == "regression":
        out = _kfold_regression(df, config)
    elif use_case == "forecasting":
        out = _rolling_origin(df, config, result_metrics)
    elif use_case == "clustering":
        out = _subsample_clustering(df, config)
    else:
        out = None
    if out and not out.get("skipped"):
        out["elapsed_s"] = round(time.time() - started, 1)
    return out


def _kfold_classification(df: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any] | None:
    target = config.get("target")
    if not target or target not in df.columns:
        return None
    plugin = get_model(config["model_key"])
    if not hasattr(plugin, "build_estimator"):
        return None
    data = df.dropna(subset=[target])
    y, class_names = encode_target(data[target])
    counts = np.bincount(y)
    k = 5 if (len(data) >= 150 and counts.min() >= 5) else 3
    if len(data) < 60 or counts.min() < k:
        return {
            "skipped": True,
            "label": "Cross-validation",
            "note": "Skipped: too few rows (or too few examples of the rarest outcome) "
                    "to split the data into folds without breaking the class balance.",
        }

    from sklearn.metrics import f1_score
    from sklearn.model_selection import StratifiedKFold

    # Structural prep only; the estimator is a full Pipeline, so imputation
    # and encoding REFIT inside each fold - no cross-fold statistics.
    X = structural_frame(data, target=target, features=config.get("features"))
    average = "binary" if len(class_names) == 2 else "weighted"
    scores: list[float] = []
    skf = StratifiedKFold(n_splits=k, shuffle=True, random_state=RANDOM_SEED)
    for train_idx, test_idx in skf.split(X, y):
        est = plugin.build_estimator(config["hyperparams"])
        est.fit(X.iloc[train_idx], y[train_idx])
        pred = est.predict(X.iloc[test_idx])
        scores.append(float(f1_score(y[test_idx], pred, average=average, zero_division=0)))
    return _summarize(
        "stratified_kfold", f"{k}-fold cross-validation", "f1", scores, higher_is_better=True
    )


def _kfold_regression(df: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any] | None:
    target = config.get("target")
    if not target or target not in df.columns:
        return None
    plugin = get_model(config["model_key"])
    if not hasattr(plugin, "build_estimator"):
        return None
    y_all = pd.to_numeric(df[target], errors="coerce")
    data = df[y_all.notna()]
    y = y_all[y_all.notna()].values.astype(float)
    k = 5 if len(data) >= 150 else 3
    if len(data) < 60:
        return {
            "skipped": True,
            "label": "Cross-validation",
            "note": "Skipped: too few rows to split into folds and still train meaningfully.",
        }

    from sklearn.metrics import mean_squared_error
    from sklearn.model_selection import KFold

    # Structural prep only; per-fold pipelines refit imputation/encoding.
    X = structural_frame(data, target=target, features=config.get("features"))
    scores: list[float] = []
    kf = KFold(n_splits=k, shuffle=True, random_state=RANDOM_SEED)
    for train_idx, test_idx in kf.split(X):
        est = plugin.build_estimator(config["hyperparams"])
        est.fit(X.iloc[train_idx], y[train_idx])
        pred = est.predict(X.iloc[test_idx])
        scores.append(float(np.sqrt(mean_squared_error(y[test_idx], pred))))
    return _summarize(
        "kfold", f"{k}-fold cross-validation", "rmse", scores, higher_is_better=False
    )


def _rolling_origin(
    df: pd.DataFrame, config: dict[str, Any], result_metrics: dict[str, Any]
) -> dict[str, Any] | None:
    plugin = get_model(config["model_key"])
    time_column = config.get("time_column")
    work = df
    if time_column and time_column in df.columns:
        ts = pd.to_datetime(df[time_column], errors="coerce", format="mixed")
        work = df.assign(_ts=ts).dropna(subset=["_ts"]).sort_values("_ts").drop(columns=["_ts"])

    # The main run already measured the latest origin; add two earlier ones.
    # Each origin calls plugin.run on ONLY the training-window head-cut, so
    # lag features and any prep statistics are computed inside the window -
    # nothing from the future leaks backward.
    scores: list[float] = []
    for frac in (0.6, 0.8):
        cut = work.head(int(len(work) * frac))
        if len(cut) < 30:
            continue
        try:
            res = plugin.run(
                cut, config["hyperparams"],
                target=config.get("target"), features=config.get("features"),
                time_column=time_column,
            )
        except Exception:
            continue
        m = res["metrics"].get("mape_pct")
        if m is not None:
            scores.append(float(m))
    latest = result_metrics.get("mape_pct")
    if latest is not None:
        scores.append(float(latest))
    if len(scores) < 2:
        return {
            "skipped": True,
            "label": "Rolling-origin backtest",
            "note": "Skipped: the series is too short to re-test the model from earlier points in time.",
        }
    return _summarize(
        "rolling_origin", f"Rolling-origin backtest ({len(scores)} origins)",
        "mape_pct", scores, higher_is_better=False,
    )


def _subsample_clustering(df: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any] | None:
    plugin = get_model(config["model_key"])
    scores: list[float] = []
    for seed in (RANDOM_SEED, RANDOM_SEED + 1, RANDOM_SEED + 2):
        sample = df.sample(frac=0.8, random_state=seed)
        try:
            res = plugin.run(sample, config["hyperparams"], features=config.get("features"))
        except Exception:
            continue
        s = res["metrics"].get("silhouette")
        if s is not None:
            scores.append(float(s))
    if len(scores) < 2:
        return {
            "skipped": True,
            "label": "Subsample stability",
            "note": "Skipped: the grouping could not be re-scored on data subsamples.",
        }
    return _summarize(
        "subsample", "Subsample stability (3 draws of 80%)",
        "silhouette", scores, higher_is_better=True,
    )


def _summarize(
    method: str, label: str, metric: str, scores: list[float], higher_is_better: bool
) -> dict[str, Any]:
    arr = np.asarray(scores, dtype=float)
    mean, std = float(arr.mean()), float(arr.std())
    if metric in ("f1", "silhouette"):
        # Bounded 0-1 scores: absolute spread is what a reader feels.
        verdict = "stable" if std <= 0.05 else "variable"
    else:
        # Error metrics (mape): relative spread; 1.5% vs 2.0% is the same ballpark.
        verdict = "stable" if (abs(mean) < 1e-9 or std / abs(mean) <= 0.25) else "variable"
    if verdict == "stable":
        note = ("The score barely moves when the data is resampled - "
                "the headline result does not hinge on one lucky split.")
    else:
        note = ("The score moves noticeably between resamples - treat the headline "
                "number as approximate and plan around the range shown here.")
    return {
        "method": method,
        "label": label,
        "metric": metric,
        "folds": [round(s, 4) for s in scores],
        "mean": round(mean, 4),
        "std": round(std, 4),
        "higher_is_better": higher_is_better,
        "verdict": verdict,
        "note": note,
    }
