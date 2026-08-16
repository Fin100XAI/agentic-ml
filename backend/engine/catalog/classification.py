"""Classification models: Logistic Regression, Random Forest, XGBoost."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

from .base import ModelPlugin, ParamSpec, register
from .preprocess import RANDOM_SEED, encode_target, select_feature_frame


def _evaluate_classifier(
    model: Any,
    X: pd.DataFrame,
    y: np.ndarray,
    class_names: list[str],
    test_size: float,
) -> dict[str, Any]:
    """Shared train/test split + fit + metric/artifact computation."""
    stratify = y if np.bincount(y).min() >= 2 else None
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=RANDOM_SEED, stratify=stratify
    )
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    average = "binary" if len(class_names) == 2 else "weighted"
    metrics: dict[str, Any] = {
        "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        "precision": round(float(precision_score(y_test, y_pred, average=average, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, y_pred, average=average, zero_division=0)), 4),
        "f1": round(float(f1_score(y_test, y_pred, average=average, zero_division=0)), 4),
        "n_train": int(len(y_train)),
        "n_test": int(len(y_test)),
    }
    if len(class_names) == 2 and hasattr(model, "predict_proba"):
        try:
            metrics["roc_auc"] = round(float(roc_auc_score(y_test, model.predict_proba(X_test)[:, 1])), 4)
        except ValueError:
            pass

    cm = confusion_matrix(y_test, y_pred)
    artifacts: dict[str, Any] = {
        "confusion_matrix": {"labels": class_names, "matrix": cm.tolist()},
        "class_distribution": [
            {"label": class_names[i], "count": int(c)} for i, c in enumerate(np.bincount(y, minlength=len(class_names)))
        ],
    }

    importances = None
    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
    elif hasattr(model, "coef_"):
        importances = np.abs(model.coef_).mean(axis=0)
    if importances is not None:
        order = np.argsort(importances)[::-1][:15]
        artifacts["feature_importance"] = [
            {"feature": str(X.columns[i]), "importance": round(float(importances[i]), 4)} for i in order
        ]

    return {
        "metrics": metrics,
        "artifacts": artifacts,
        "features_used": [str(c) for c in X.columns],
        "class_names": class_names,
        "fitted_model": model,  # popped by the orchestrator before serialization
    }


def _require_target(target: str | None, df: pd.DataFrame) -> str:
    if not target or target not in df.columns:
        raise ValueError("Classification requires a valid target column.")
    return target


@register
class LogisticRegressionModel(ModelPlugin):
    key = "logistic_regression"
    name = "Logistic Regression"
    use_case = "classification"
    description = "Linear classifier estimating class probabilities; fast and interpretable."
    strengths = "Best as a strong baseline; interpretable coefficients; works well on linearly separable data and small datasets."

    def param_schema(self) -> list[ParamSpec]:
        return [
            ParamSpec("C", "Regularization strength (C)", "float", 1.0,
                      "Inverse regularization; smaller = stronger regularization.", min=0.001, max=100, step=0.001),
            ParamSpec("max_iter", "Max iterations", "int", 1000, "Solver iteration limit.", min=100, max=10000, step=100),
            ParamSpec("test_size", "Test split fraction", "float", 0.2, "Held-out fraction for evaluation.", min=0.1, max=0.5, step=0.05),
        ]

    def build_estimator(self, hyperparams):
        return LogisticRegression(C=hyperparams["C"], max_iter=hyperparams["max_iter"], random_state=RANDOM_SEED)

    def run(self, df, hyperparams, target=None, features=None, time_column=None):
        target = _require_target(target, df)
        data = df.dropna(subset=[target])
        y, class_names = encode_target(data[target])
        X = select_feature_frame(data, target=target, features=features)
        return _evaluate_classifier(self.build_estimator(hyperparams), X, y, class_names, hyperparams["test_size"])


@register
class RandomForestModel(ModelPlugin):
    key = "random_forest"
    name = "Random Forest"
    use_case = "classification"
    description = "Ensemble of decision trees; robust to noise and mixed feature types."
    strengths = "Handles non-linear relationships and feature interactions; little tuning needed; gives feature importances."

    def param_schema(self) -> list[ParamSpec]:
        return [
            ParamSpec("n_estimators", "Number of trees", "int", 200, "More trees = more stable, slower.", min=10, max=1000, step=10),
            ParamSpec("max_depth", "Max tree depth", "int", 10, "Limits overfitting; 0 = unlimited.", min=0, max=50, step=1),
            ParamSpec("min_samples_leaf", "Min samples per leaf", "int", 1, "Larger = smoother model.", min=1, max=50, step=1),
            ParamSpec("test_size", "Test split fraction", "float", 0.2, "Held-out fraction for evaluation.", min=0.1, max=0.5, step=0.05),
        ]

    def build_estimator(self, hyperparams):
        return RandomForestClassifier(
            n_estimators=hyperparams["n_estimators"],
            max_depth=hyperparams["max_depth"] or None,
            min_samples_leaf=hyperparams["min_samples_leaf"],
            random_state=RANDOM_SEED,
            n_jobs=-1,
        )

    def run(self, df, hyperparams, target=None, features=None, time_column=None):
        target = _require_target(target, df)
        data = df.dropna(subset=[target])
        y, class_names = encode_target(data[target])
        X = select_feature_frame(data, target=target, features=features)
        return _evaluate_classifier(self.build_estimator(hyperparams), X, y, class_names, hyperparams["test_size"])


@register
class XGBoostModel(ModelPlugin):
    key = "xgboost"
    name = "XGBoost"
    use_case = "classification"
    description = "Gradient-boosted trees; state-of-the-art accuracy on tabular data."
    strengths = "Usually the top performer on structured/tabular data; handles imbalance and missing values well; needs some tuning."

    def param_schema(self) -> list[ParamSpec]:
        return [
            ParamSpec("n_estimators", "Boosting rounds", "int", 200, "Number of boosted trees.", min=10, max=1000, step=10),
            ParamSpec("max_depth", "Max tree depth", "int", 6, "Deeper trees fit more complex patterns.", min=1, max=15, step=1),
            ParamSpec("learning_rate", "Learning rate", "float", 0.1, "Lower = more robust with more rounds.", min=0.01, max=1.0, step=0.01),
            ParamSpec("subsample", "Row subsample", "float", 1.0, "Fraction of rows per tree.", min=0.3, max=1.0, step=0.05),
            ParamSpec("test_size", "Test split fraction", "float", 0.2, "Held-out fraction for evaluation.", min=0.1, max=0.5, step=0.05),
        ]

    def build_estimator(self, hyperparams):
        from xgboost import XGBClassifier

        return XGBClassifier(
            n_estimators=hyperparams["n_estimators"],
            max_depth=hyperparams["max_depth"],
            learning_rate=hyperparams["learning_rate"],
            subsample=hyperparams["subsample"],
            random_state=RANDOM_SEED,
            eval_metric="logloss",
        )

    def run(self, df, hyperparams, target=None, features=None, time_column=None):
        target = _require_target(target, df)
        data = df.dropna(subset=[target])
        y, class_names = encode_target(data[target])
        X = select_feature_frame(data, target=target, features=features)
        return _evaluate_classifier(self.build_estimator(hyperparams), X, y, class_names, hyperparams["test_size"])
