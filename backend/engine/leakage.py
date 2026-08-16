"""Leakage sentinel: columns that would not be known at prediction time.

Runs when a target is chosen (classification and regression). Deterministic
checks only - each flag becomes a human question ("Would you know this at
prediction time?") with keep/exclude buttons. Exclusions are recorded on the
run and applied at train time; the data artifact is never modified.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .catalog.preprocess import RANDOM_SEED

# Editable in one place: column-name tokens that smell like the outcome itself.
OUTCOME_TOKENS = (
    "status", "result", "resolved", "closed", "outcome", "final", "settled",
    "decision", "verdict", "completion", "churn_date", "cancel_date", "paid_date",
)

CORR_THRESHOLD = 0.98
CRAMERS_V_THRESHOLD = 0.95
ID_CARDINALITY = 0.95
SINGLE_FEATURE_RATIO = 0.95
SAMPLE = 2000


def screen_leakage(df: pd.DataFrame, target: str, use_case: str) -> list[dict[str, Any]]:
    if use_case not in ("classification", "regression") or target not in df.columns:
        return []
    data = df.dropna(subset=[target])
    if len(data) > SAMPLE:
        data = data.sample(SAMPLE, random_state=RANDOM_SEED)
    y_num = _encode_target(data[target])

    flags: list[dict[str, Any]] = []
    for col in data.columns:
        if col == target:
            continue
        s = data[col]
        reasons: list[str] = []

        # (b) ID-like: nearly one distinct value per row predicts nothing real.
        # Continuous floats are naturally near-unique, so only text and
        # integer columns can be IDs.
        nunique = s.nunique(dropna=True)
        is_idable = s.dtype == object or pd.api.types.is_integer_dtype(s)
        if is_idable and nunique >= ID_CARDINALITY * len(data) and len(data) > 50:
            reasons.append("id_like")

        # (a) near-perfect association with the target
        assoc = _association(s, data[target], y_num)
        if assoc is not None and assoc >= (
            CORR_THRESHOLD if pd.api.types.is_numeric_dtype(s) else CRAMERS_V_THRESHOLD
        ):
            reasons.append("near_perfect_association")

        # (c) outcome-ish column name
        if any(tok in str(col).lower() for tok in OUTCOME_TOKENS):
            reasons.append("outcome_name")

        if not reasons:
            continue
        flags.append({
            "column": str(col),
            "reasons": reasons,
            "association": round(float(assoc), 4) if assoc is not None else None,
            "severity": "warn",
            "question": f"Would you actually know '{col}' at the moment you need the prediction?",
            "detail": _detail(reasons, assoc),
        })

    # (d) single-feature model test on flagged columns: escalate if one flagged
    # column alone nearly matches the full-feature score.
    if flags:
        full = _quick_score(data, target, y_num, use_case, feature_cols=None)
        for f in flags:
            solo = _quick_score(data, target, y_num, use_case, feature_cols=[f["column"]])
            f["single_feature_score"] = round(solo, 4) if solo is not None else None
            f["full_score"] = round(full, 4) if full is not None else None
            if (
                full is not None and solo is not None and full > 0
                and solo >= SINGLE_FEATURE_RATIO * full
            ):
                f["severity"] = "critical"
                f["detail"] += (
                    " On its own, this single column nearly matches the whole model's score - "
                    "a classic sign it IS the outcome in disguise."
                )
    return flags


def _encode_target(y: pd.Series) -> np.ndarray:
    if pd.api.types.is_numeric_dtype(y):
        return pd.to_numeric(y, errors="coerce").values.astype(float)
    return pd.factorize(y.astype(str))[0].astype(float)


def _association(s: pd.Series, y_raw: pd.Series, y_num: np.ndarray) -> float | None:
    try:
        if pd.api.types.is_numeric_dtype(s):
            corr = pd.Series(pd.to_numeric(s, errors="coerce").values).corr(pd.Series(y_num))
            return abs(float(corr)) if pd.notna(corr) else None
        if s.nunique(dropna=True) > 50:
            return None  # contingency table would be meaningless
        return _cramers_v(s.astype(str), y_raw.astype(str))
    except Exception:
        return None


def _cramers_v(a: pd.Series, b: pd.Series) -> float | None:
    from scipy.stats import chi2_contingency

    table = pd.crosstab(a, b)
    if table.size == 0 or min(table.shape) < 2:
        return None
    chi2 = chi2_contingency(table)[0]
    n = table.values.sum()
    r, k = table.shape
    denom = n * (min(r, k) - 1)
    return float(np.sqrt(chi2 / denom)) if denom else None


def _quick_score(
    data: pd.DataFrame, target: str, y_num: np.ndarray,
    use_case: str, feature_cols: list[str] | None,
) -> float | None:
    """Depth-limited tree score: full features (depth 3) or one column (depth 2)."""
    from sklearn.model_selection import cross_val_score
    from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

    from .catalog.preprocess import select_feature_frame

    try:
        X = select_feature_frame(data, target=target, features=feature_cols)
        if X.shape[1] == 0 or len(X) < 40:
            return None
        depth = 2 if feature_cols else 3
        if use_case == "classification":
            y = pd.factorize(data[target].astype(str))[0]
            if np.bincount(y).min() < 3:
                return None
            est = DecisionTreeClassifier(max_depth=depth, random_state=RANDOM_SEED)
            return float(np.mean(cross_val_score(est, X, y, cv=3, scoring="f1_weighted")))
        est = DecisionTreeRegressor(max_depth=depth, random_state=RANDOM_SEED)
        return float(max(0.0, np.mean(cross_val_score(est, X, y_num, cv=3, scoring="r2"))))
    except Exception:
        return None


def _detail(reasons: list[str], assoc: float | None) -> str:
    parts = []
    if "near_perfect_association" in reasons:
        parts.append(
            f"It moves almost perfectly with the target (association {assoc:.2f}) - "
            "information that strong is usually recorded AFTER the outcome happened."
        )
    if "outcome_name" in reasons:
        parts.append("Its name suggests it describes the outcome itself, not something known beforehand.")
    if "id_like" in reasons:
        parts.append("It is unique per row like an ID - the model would memorize records, not learn patterns.")
    return " ".join(parts)
