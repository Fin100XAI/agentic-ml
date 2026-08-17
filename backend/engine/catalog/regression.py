"""Regression models: ElasticNet linear, Random Forest, XGBoost."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import ElasticNet, LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

from sklearn.pipeline import Pipeline

from .base import ModelPlugin, ParamSpec, register
from .preprocess import (
    RANDOM_SEED,
    build_preprocessor,
    processed_feature_names,
    structural_frame,
)

_SCATTER_CAP = 500  # points sent to the predicted-vs-actual chart


def _require_numeric_target(target: str | None, df: pd.DataFrame) -> pd.Series:
    if not target or target not in df.columns:
        raise ValueError("Regression requires a numeric target column.")
    y = pd.to_numeric(df[target], errors="coerce")
    if y.notna().sum() < 20:
        raise ValueError(f"'{target}' has too few numeric values to model.")
    return y


def _evaluate_regressor(
    model: Any, X: pd.DataFrame, y: np.ndarray, test_size: float
) -> dict[str, Any]:
    """Shared train/test split + fit + metric/artifact computation."""
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=RANDOM_SEED
    )
    model.fit(X_train, y_train)
    pred = model.predict(X_test)

    rmse = float(np.sqrt(mean_squared_error(y_test, pred)))
    metrics: dict[str, Any] = {
        "rmse": round(rmse, 4),
        "mae": round(float(mean_absolute_error(y_test, pred)), 4),
        "r2": round(float(r2_score(y_test, pred)), 4),
        "n_train": int(len(y_train)),
        "n_test": int(len(y_test)),
    }

    # Predicted vs actual scatter (sampled) + residual distribution.
    rng = np.random.default_rng(RANDOM_SEED)
    idx = np.arange(len(y_test))
    if len(idx) > _SCATTER_CAP:
        idx = rng.choice(idx, _SCATTER_CAP, replace=False)
    points = [
        {"actual": round(float(y_test[i]), 4), "predicted": round(float(pred[i]), 4)}
        for i in idx
    ]
    residuals = y_test - pred
    counts, edges = np.histogram(residuals, bins=min(20, max(6, len(y_test) // 10)))
    residual_hist = [
        {"mid": round(float((edges[i] + edges[i + 1]) / 2), 4), "count": int(c)}
        for i, c in enumerate(counts)
    ]

    artifacts: dict[str, Any] = {
        "predicted_vs_actual": {"points": points},
        "residual_hist": residual_hist,
    }

    inner = model.named_steps["model"] if hasattr(model, "named_steps") else model
    names = processed_feature_names(model) or [str(c) for c in X.columns]
    importances = None
    if hasattr(inner, "feature_importances_"):
        importances = inner.feature_importances_
    elif hasattr(inner, "coef_"):
        importances = np.abs(np.asarray(inner.coef_)).ravel()
    if importances is not None and len(importances) == len(names):
        order = np.argsort(importances)[::-1][:15]
        artifacts["feature_importance"] = [
            {"feature": names[i], "importance": round(float(importances[i]), 4)}
            for i in order
        ]

    return {
        "metrics": metrics,
        "artifacts": artifacts,
        "features_used": [str(c) for c in X.columns],
        "fitted_model": model,  # popped by the orchestrator before serialization
        # Held-out predictions for slice analysis; popped before serialization.
        "eval_rows": {
            "index": list(X_test.index),
            "y_true": [round(float(v), 4) for v in y_test],
            "y_pred": [round(float(v), 4) for v in pred],
        },
    }


def _prepare(df: pd.DataFrame, target: str | None, features: list[str] | None):
    y_all = _require_numeric_target(target, df)
    data = df[y_all.notna()]
    y = y_all[y_all.notna()].values.astype(float)
    X = structural_frame(data, target=target, features=features)
    return X, y


@register
class ElasticNetModel(ModelPlugin):
    key = "elastic_net"
    name = "Linear Regression (ElasticNet)"
    use_case = "regression"
    description = "Linear model with tunable regularization; alpha 0 = plain least squares."
    strengths = "Interpretable coefficients; the regularization dial handles many/correlated features; strong baseline."

    def param_schema(self) -> list[ParamSpec]:
        return [
            ParamSpec("alpha", "Regularization (alpha)", "float", 0.1,
                      "0 = plain linear regression; higher shrinks coefficients.", min=0.0, max=10.0, step=0.05),
            ParamSpec("l1_ratio", "L1 ratio", "float", 0.5,
                      "0 = ridge (spread shrinkage), 1 = lasso (drops features).", min=0.0, max=1.0, step=0.05),
            ParamSpec("test_size", "Test split fraction", "float", 0.2,
                      "Held-out fraction for evaluation.", min=0.1, max=0.5, step=0.05),
        ]

    def build_estimator(self, hyperparams):
        if hyperparams["alpha"] <= 0:
            model = LinearRegression()
        else:
            model = ElasticNet(
                alpha=hyperparams["alpha"], l1_ratio=hyperparams["l1_ratio"],
                random_state=RANDOM_SEED, max_iter=5000,
            )
        return Pipeline([("prep", build_preprocessor()), ("model", model)])

    def run(self, df, hyperparams, target=None, features=None, time_column=None):
        X, y = _prepare(df, target, features)
        return _evaluate_regressor(self.build_estimator(hyperparams), X, y, hyperparams["test_size"])


@register
class RandomForestRegressorModel(ModelPlugin):
    key = "rf_regressor"
    name = "Random Forest Regressor"
    use_case = "regression"
    description = "Ensemble of decision trees averaging their predictions; robust to noise and mixed features."
    strengths = "Captures non-linear relationships with little tuning; gives feature importances; hard to break."

    def param_schema(self) -> list[ParamSpec]:
        return [
            ParamSpec("n_estimators", "Number of trees", "int", 200, "More trees = more stable, slower.", min=10, max=1000, step=10),
            ParamSpec("max_depth", "Max tree depth", "int", 12, "Limits overfitting; 0 = unlimited.", min=0, max=50, step=1),
            ParamSpec("min_samples_leaf", "Min samples per leaf", "int", 2, "Larger = smoother model.", min=1, max=50, step=1),
            ParamSpec("test_size", "Test split fraction", "float", 0.2, "Held-out fraction for evaluation.", min=0.1, max=0.5, step=0.05),
        ]

    def build_estimator(self, hyperparams):
        return Pipeline([
            ("prep", build_preprocessor()),
            ("model", RandomForestRegressor(
                n_estimators=hyperparams["n_estimators"],
                max_depth=hyperparams["max_depth"] or None,
                min_samples_leaf=hyperparams["min_samples_leaf"],
                random_state=RANDOM_SEED,
                n_jobs=-1,
            )),
        ])

    def run(self, df, hyperparams, target=None, features=None, time_column=None):
        X, y = _prepare(df, target, features)
        return _evaluate_regressor(self.build_estimator(hyperparams), X, y, hyperparams["test_size"])


@register
class XGBRegressorModel(ModelPlugin):
    key = "xgb_regressor"
    name = "XGBoost Regressor"
    use_case = "regression"
    description = "Gradient-boosted trees; state-of-the-art accuracy on tabular numeric prediction."
    strengths = "Usually the top performer on structured data; handles missing values and interactions well; needs some tuning."

    def param_schema(self) -> list[ParamSpec]:
        return [
            ParamSpec("n_estimators", "Boosting rounds", "int", 300, "Number of boosted trees.", min=10, max=1000, step=10),
            ParamSpec("max_depth", "Max tree depth", "int", 6, "Deeper trees fit more complex patterns.", min=1, max=15, step=1),
            ParamSpec("learning_rate", "Learning rate", "float", 0.05, "Lower = more robust with more rounds.", min=0.01, max=1.0, step=0.01),
            ParamSpec("subsample", "Row subsample", "float", 0.9, "Fraction of rows per tree.", min=0.3, max=1.0, step=0.05),
            ParamSpec("test_size", "Test split fraction", "float", 0.2, "Held-out fraction for evaluation.", min=0.1, max=0.5, step=0.05),
        ]

    def build_estimator(self, hyperparams):
        from xgboost import XGBRegressor

        return Pipeline([
            ("prep", build_preprocessor()),
            ("model", XGBRegressor(
                n_estimators=hyperparams["n_estimators"],
                max_depth=hyperparams["max_depth"],
                learning_rate=hyperparams["learning_rate"],
                subsample=hyperparams["subsample"],
                random_state=RANDOM_SEED,
            )),
        ])

    def run(self, df, hyperparams, target=None, features=None, time_column=None):
        X, y = _prepare(df, target, features)
        return _evaluate_regressor(self.build_estimator(hyperparams), X, y, hyperparams["test_size"])
