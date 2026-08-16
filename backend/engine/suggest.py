"""Data-aware hyperparameter suggestions.

Computes suggested hyperparameters for every model of a use case *from the
actual dataset* - e.g. sweeping k by silhouette for clustering, detecting the
seasonal period for forecasting - each with a plain-language rationale the UI
shows next to the pre-filled form.
"""
from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import pandas as pd

from .catalog.preprocess import RANDOM_SEED, scale, select_feature_frame

SAMPLE = 500  # cap for the cheap sweeps below


def _classification(df: pd.DataFrame, target: str | None) -> dict[str, dict[str, Any]]:
    n = len(df)
    X = select_feature_frame(df, target=target)
    f = X.shape[1]

    imbalance = ""
    imbalanced = False
    pos_ratio = 1.0
    if target and target in df.columns:
        vc = df[target].value_counts(normalize=True)
        if len(vc) >= 2 and vc.iloc[0] > 0.75:
            imbalanced = True
            pos_ratio = round(float(vc.iloc[0] / max(vc.iloc[-1], 1e-6)), 1)
            imbalance = (f" Outcomes are lopsided ({vc.iloc[0]:.0%} majority), so the rare "
                         "class is weighted up - and tune the decision threshold on the "
                         "results screen rather than trusting 0.5.")

    test_size = 0.25 if n < 500 else 0.2
    size_txt = f"{n:,} rows and {f} usable features"

    return {
        "logistic_regression": {
            "hyperparams": {"C": 1.0, "max_iter": 2000 if f > 50 else 1000,
                            "class_weight": "balanced" if imbalanced else "none",
                            "test_size": test_size},
            "rationale": f"Standard regularization for {size_txt}; a solid baseline to beat.{imbalance}",
        },
        "random_forest": {
            "hyperparams": {
                "n_estimators": 100 if n < 1000 else 200 if n < 10000 else 300,
                "max_depth": 8 if f <= 10 else 12,
                "min_samples_leaf": 1 if n < 2000 else 5,
                "class_weight": "balanced" if imbalanced else "none",
                "test_size": test_size,
            },
            "rationale": f"Tree count and depth scaled to {size_txt} to balance accuracy and overfitting.{imbalance}",
        },
        "xgboost": {
            "hyperparams": {
                "n_estimators": 150 if n < 1000 else 300,
                "max_depth": 4 if n < 1000 else 6,
                "learning_rate": 0.1 if n < 2000 else 0.05,
                "subsample": 0.9,
                "scale_pos_weight": pos_ratio if imbalanced else 1.0,
                "test_size": test_size,
            },
            "rationale": f"Learning rate and rounds tuned for {size_txt}: smaller datasets get a faster rate with fewer rounds.{imbalance}",
        },
    }


def _regression(df: pd.DataFrame, target: str | None) -> dict[str, dict[str, Any]]:
    n = len(df)
    X = select_feature_frame(df, target=target)
    f = X.shape[1]
    test_size = 0.25 if n < 500 else 0.2
    size_txt = f"{n:,} rows and {f} usable features"

    # More features -> lean on regularization a bit harder.
    alpha = 0.05 if f <= 5 else 0.1 if f <= 20 else 0.5

    return {
        "elastic_net": {
            "hyperparams": {"alpha": alpha, "l1_ratio": 0.5, "test_size": test_size},
            "rationale": f"Light regularization (alpha {alpha}) for {size_txt}; a 50/50 L1 mix "
                         "shrinks noisy coefficients without discarding features outright.",
        },
        "rf_regressor": {
            "hyperparams": {
                "n_estimators": 100 if n < 1000 else 200 if n < 10000 else 300,
                "max_depth": 10 if f <= 10 else 14,
                "min_samples_leaf": 2 if n < 2000 else 5,
                "test_size": test_size,
            },
            "rationale": f"Tree count and depth scaled to {size_txt} to balance fit and overfitting.",
        },
        "xgb_regressor": {
            "hyperparams": {
                "n_estimators": 200 if n < 1000 else 400,
                "max_depth": 4 if n < 1000 else 6,
                "learning_rate": 0.1 if n < 2000 else 0.05,
                "subsample": 0.9,
                "test_size": test_size,
            },
            "rationale": f"Learning rate and rounds tuned for {size_txt}: smaller datasets get a faster rate with fewer rounds.",
        },
    }


def _best_k(Xs: np.ndarray) -> tuple[int, float]:
    """Cheap silhouette sweep on a sample to suggest k."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    rng = np.random.default_rng(RANDOM_SEED)
    if len(Xs) > SAMPLE:
        Xs = Xs[rng.choice(len(Xs), SAMPLE, replace=False)]
    best_k, best_s = 3, -1.0
    for k in range(2, min(9, len(Xs) - 1)):
        try:
            labels = KMeans(n_clusters=k, n_init=5, random_state=RANDOM_SEED).fit_predict(Xs)
            s = float(silhouette_score(Xs, labels))
            if s > best_s:
                best_k, best_s = k, s
        except ValueError:
            continue
    return best_k, best_s


def _knn_eps(Xs: np.ndarray) -> float:
    """DBSCAN eps from the median 5th-nearest-neighbor distance."""
    from sklearn.neighbors import NearestNeighbors

    rng = np.random.default_rng(RANDOM_SEED)
    if len(Xs) > SAMPLE:
        Xs = Xs[rng.choice(len(Xs), SAMPLE, replace=False)]
    k = min(5, len(Xs) - 1)
    nn = NearestNeighbors(n_neighbors=k + 1).fit(Xs)
    dists, _ = nn.kneighbors(Xs)
    return float(np.median(dists[:, -1]))


def _clustering(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    try:
        X = select_feature_frame(df)
        Xs = scale(X)
        k, sil = _best_k(Xs)
        eps = round(_knn_eps(Xs), 2)
        k_txt = f"k={k} scored best in a quick silhouette sweep (score {sil:.2f}) on a sample of your data"
        eps_txt = f"eps={eps} is the typical distance between close points in your (scaled) data"
    except Exception:
        k, eps = 3, 0.5
        k_txt = "default of 3 groups (data sweep unavailable)"
        eps_txt = "default neighborhood radius"

    return {
        "kmeans": {
            "hyperparams": {"n_clusters": k, "n_init": 10},
            "rationale": f"Suggested {k_txt}.",
        },
        "dbscan": {
            "hyperparams": {"eps": eps, "min_samples": 5},
            "rationale": f"Suggested {eps_txt}; points with fewer than 5 close neighbors become 'noise'.",
        },
        "agglomerative": {
            "hyperparams": {"n_clusters": k, "linkage": "ward"},
            "rationale": f"Same group count as K-Means ({k_txt}); 'ward' linkage suits compact groups.",
        },
    }


def _seasonal_period(df: pd.DataFrame, target: str | None, time_column: str | None) -> tuple[int, bool, int, str]:
    """Infer (period, is_seasonal, series_length, freq_label) from the time column."""
    series = pd.to_numeric(df[target], errors="coerce").dropna() if target and target in df.columns else pd.Series(dtype=float)
    L = len(series)

    period, freq_label = 0, "unknown cadence"
    if time_column and time_column in df.columns:
        ts = pd.to_datetime(df[time_column], errors="coerce", format="mixed").dropna().sort_values()
        if len(ts) > 2:
            delta = ts.diff().dropna().median()
            days = delta.total_seconds() / 86400 if pd.notna(delta) else 0
            if 0.9 <= days <= 1.1:
                period, freq_label = 7, "daily data (weekly cycle)"
            elif 6 <= days <= 8:
                period, freq_label = 52, "weekly data (yearly cycle)"
            elif 27 <= days <= 32:
                period, freq_label = 12, "monthly data (yearly cycle)"
            elif 85 <= days <= 95:
                period, freq_label = 4, "quarterly data (yearly cycle)"

    seasonal = False
    if period > 1 and L > 2 * period:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                ac = pd.Series(series.values).autocorr(lag=period)
                seasonal = bool(pd.notna(ac) and ac > 0.3)
            except Exception:
                seasonal = False
    return period, seasonal, L, freq_label


def _forecasting(df: pd.DataFrame, target: str | None, time_column: str | None) -> dict[str, dict[str, Any]]:
    period, seasonal, L, freq_label = _seasonal_period(df, target, time_column)
    horizon = int(np.clip(round(L * 0.15), 5, 30)) if L else 10
    season_txt = (
        f"Detected {freq_label} with a repeating pattern - seasonality enabled (period {period})."
        if seasonal
        else f"Detected {freq_label}; no strong repeating pattern found, so seasonality is off."
    )

    n_lags = period if (seasonal and L >= 3 * period) else max(2, min(12, L // 4 if L else 12))
    return {
        "arima": {
            "hyperparams": {"p": 2, "d": 1, "q": 2, "seasonal_period": period if seasonal else 0, "horizon": horizon},
            "rationale": f"{season_txt} Horizon of {horizon} steps ≈ 15% of your {L}-point history.",
        },
        "exp_smoothing": {
            "hyperparams": {
                "trend": "add",
                "seasonal": "add" if seasonal else "none",
                "seasonal_period": period if period > 1 else 12,
                "horizon": horizon,
            },
            "rationale": f"{season_txt} Additive trend fits steadily growing or declining series.",
        },
        "xgb_forecast": {
            "hyperparams": {"n_lags": int(n_lags), "n_estimators": 200, "learning_rate": 0.05, "horizon": horizon},
            "rationale": f"Lag window of {int(n_lags)} lets the model see one full cycle of your data. {season_txt}",
        },
    }


def suggest_hyperparams(
    df: pd.DataFrame,
    use_case: str,
    target: str | None = None,
    time_column: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Return {model_key: {"hyperparams": ..., "rationale": ...}} for a use case."""
    try:
        if use_case == "classification":
            return _classification(df, target)
        if use_case == "regression":
            return _regression(df, target)
        if use_case == "clustering":
            return _clustering(df)
        if use_case == "forecasting":
            return _forecasting(df, target, time_column)
    except Exception:
        pass
    return {}
