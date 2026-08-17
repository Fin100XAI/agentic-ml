"""Shared preprocessing helpers for catalog models."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder, StandardScaler

RANDOM_SEED = 42


def _expand_datetime(work: pd.DataFrame) -> pd.DataFrame:
    """Turn date columns into model-usable parts instead of dropping them.

    Emits ``col__days_since`` (recency vs the latest date), ``col__month`` and
    ``col__day_of_week`` - each only when it actually varies. Recognizes both
    true datetime dtypes and object columns that parse as dates.
    """
    for col in list(work.columns):
        s = work[col]
        ts = None
        if pd.api.types.is_datetime64_any_dtype(s):
            ts = s
        elif s.dtype == object:
            sample = s.dropna().astype(str).head(50)
            if len(sample) > 0:
                parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
                if parsed.notna().mean() > 0.9:
                    ts = pd.to_datetime(s.astype(str), errors="coerce", format="mixed")
        if ts is None:
            continue
        latest = ts.max()
        parts = {
            f"{col}__days_since": (latest - ts).dt.days,
            f"{col}__month": ts.dt.month,
            f"{col}__day_of_week": ts.dt.dayofweek,
        }
        for name, vals in parts.items():
            if vals.nunique(dropna=True) > 1:
                work[name] = vals.astype(float)
        work = work.drop(columns=[col])
    return work


def select_feature_frame(
    df: pd.DataFrame,
    target: str | None = None,
    features: list[str] | None = None,
    max_onehot_cardinality: int = 12,
) -> pd.DataFrame:
    """Build a numeric feature matrix: expand dates, one-hot low-card cats, drop ids."""
    work = df.copy()
    if target and target in work.columns:
        work = work.drop(columns=[target])
    if features:
        keep = [c for c in features if c in work.columns]
        work = work[keep]

    work = _expand_datetime(work)

    drop: list[str] = []
    for col in work.columns:
        s = work[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            drop.append(col)  # unparseable leftovers
        elif not pd.api.types.is_numeric_dtype(s):
            nunique = s.nunique(dropna=True)
            if nunique > max_onehot_cardinality or nunique >= 0.9 * len(work):
                drop.append(col)  # high-cardinality text/id → drop
    work = work.drop(columns=drop)

    cat_cols = [c for c in work.columns if not pd.api.types.is_numeric_dtype(work[c])]
    if cat_cols:
        work = pd.get_dummies(work, columns=cat_cols, drop_first=True, dtype=float)

    # Impute numeric missing values with the median.
    for col in work.columns:
        if work[col].isna().any():
            med = work[col].median()
            work[col] = work[col].fillna(0.0 if pd.isna(med) else med)

    return work.astype(float)


def structural_frame(
    df: pd.DataFrame,
    target: str | None = None,
    features: list[str] | None = None,
    max_onehot_cardinality: int = 12,
) -> pd.DataFrame:
    """Stateless/structural prep only: select features, expand dates, drop
    IDs and high-cardinality text. Raw dtypes are KEPT - every fitted step
    (imputation, encoding, scaling) lives inside the model Pipeline so it
    refits per fold during validation and travels with the checkpoint.
    """
    work = df.copy()
    if target and target in work.columns:
        work = work.drop(columns=[target])
    if features:
        keep = [c for c in features if c in work.columns]
        work = work[keep]

    work = _expand_datetime(work)

    drop: list[str] = []
    for col in work.columns:
        s = work[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            drop.append(col)  # unparseable leftovers
        elif not pd.api.types.is_numeric_dtype(s):
            nunique = s.nunique(dropna=True)
            if nunique > max_onehot_cardinality or nunique >= 0.9 * len(work):
                drop.append(col)  # high-cardinality text/id -> drop
    work = work.drop(columns=drop)

    for col in work.columns:
        if pd.api.types.is_bool_dtype(work[col]):
            work[col] = work[col].astype(float)
        elif not pd.api.types.is_numeric_dtype(work[col]):
            work[col] = work[col].astype(object)
    return work


def build_preprocessor():
    """Fold-safe preprocessing as fitted transformers.

    Median-imputes numerics; most-frequent-imputes then one-hot encodes
    categoricals (unknown levels at scoring time encode to all-zeros).
    Column membership is decided by dtype selectors at fit time.
    """
    from sklearn.compose import ColumnTransformer, make_column_selector
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline as SkPipeline
    from sklearn.preprocessing import OneHotEncoder

    cat = SkPipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])
    return ColumnTransformer(
        [
            ("num", SimpleImputer(strategy="median"),
             make_column_selector(dtype_include=np.number)),
            ("cat", cat, make_column_selector(dtype_exclude=np.number)),
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )


def processed_feature_names(fitted_pipeline) -> list[str]:
    """Human-readable names of the columns the model actually saw."""
    try:
        return [str(n) for n in fitted_pipeline.named_steps["prep"].get_feature_names_out()]
    except Exception:
        return []


def encode_target(series: pd.Series) -> tuple[np.ndarray, list[str]]:
    """Label-encode a classification target; returns (y, class_names)."""
    le = LabelEncoder()
    y = le.fit_transform(series.astype(str))
    return y, [str(c) for c in le.classes_]


def scale(X: pd.DataFrame) -> np.ndarray:
    return StandardScaler().fit_transform(X.values)
