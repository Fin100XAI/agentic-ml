"""Error-slice analysis: where does a supervised model do materially worse?

Scans the held-out test rows group by group - every low-cardinality
categorical column plus quartile bands of numeric columns - and computes the
primary metric per group. Groups clearly worse than overall are flagged red;
groups too small to judge are honestly skipped, not silently scored.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

MIN_GROUP = 20          # below this, a metric is noise - honest skip
MAX_LEVELS = 12         # categorical columns bigger than this are unreadable
MAX_COLUMNS = 8
RED_F1_DROP = 0.15      # absolute f1 drop vs overall
RED_RMSE_RATIO = 1.25   # rmse this much above overall
AMBER_F1_DROP = 0.07
AMBER_RMSE_RATIO = 1.10


def slice_scan(
    df: pd.DataFrame,
    target: str,
    use_case: str,
    test_index: list[Any],
    y_true: list[Any],
    y_pred: list[Any],
) -> dict[str, Any] | None:
    if use_case not in ("classification", "regression") or not test_index:
        return None
    test = df.loc[[i for i in test_index if i in df.index]].copy()
    if len(test) != len(y_true):
        return None
    test["_true"] = list(y_true)
    test["_pred"] = list(y_pred)

    metric = "f1" if use_case == "classification" else "rmse"
    overall = _metric(use_case, test["_true"], test["_pred"])
    if overall is None:
        return None

    rows: list[dict[str, Any]] = []
    scanned = 0
    for col in df.columns:
        if col == target or scanned >= MAX_COLUMNS:
            continue
        s = test[col]
        if pd.api.types.is_numeric_dtype(s) and s.nunique() > MAX_LEVELS:
            try:
                binned = pd.qcut(s, 4, duplicates="drop")
            except ValueError:
                continue
            groups = binned.map(
                lambda iv: f"{iv.left:g}-{iv.right:g}" if pd.notna(iv) else "missing"
            ).astype(str)
        elif s.nunique(dropna=True) <= MAX_LEVELS and s.nunique(dropna=True) >= 2:
            groups = s.astype(str)
        else:
            continue
        scanned += 1
        for g, part in test.groupby(groups, observed=True):
            n = int(len(part))
            if n < MIN_GROUP:
                rows.append({"column": str(col), "group": str(g), "n": n,
                             "value": None, "status": "too_small"})
                continue
            v = _metric(use_case, part["_true"], part["_pred"])
            if v is None:
                continue
            rows.append({"column": str(col), "group": str(g), "n": n,
                         "value": round(v, 4), "status": _status(use_case, v, overall)})

    reds = [r for r in rows if r["status"] == "red"]
    order = {"red": 0, "amber": 1, "ok": 2, "too_small": 3}
    rows.sort(key=lambda r: (order[r["status"]], r["column"], r["group"]))
    return {
        "metric": metric,
        "overall": round(overall, 4),
        "n_test": int(len(test)),
        "rows": rows,
        "red_groups": [f"{r['column']} = {r['group']}" for r in reds],
    }


def _metric(use_case: str, y_true: pd.Series, y_pred: pd.Series) -> float | None:
    try:
        if use_case == "classification":
            from sklearn.metrics import f1_score

            yt = y_true.astype(str)
            yp = y_pred.astype(str)
            labels = sorted(set(yt) | set(yp))
            if len(labels) < 2:
                return float((yt == yp).mean())  # single-class group: accuracy
            average = "binary" if len(labels) == 2 else "weighted"
            return float(f1_score(yt, yp, average=average,
                                  pos_label=labels[-1] if average == "binary" else 1,
                                  zero_division=0))
        yt = pd.to_numeric(y_true, errors="coerce")
        yp = pd.to_numeric(y_pred, errors="coerce")
        ok = yt.notna() & yp.notna()
        if ok.sum() < 5:
            return None
        return float(np.sqrt(np.mean((yt[ok] - yp[ok]) ** 2)))
    except Exception:
        return None


def _status(use_case: str, value: float, overall: float) -> str:
    if use_case == "classification":
        if value <= overall - RED_F1_DROP:
            return "red"
        if value <= overall - AMBER_F1_DROP:
            return "amber"
        return "ok"
    if overall <= 0:
        return "ok"
    if value >= overall * RED_RMSE_RATIO:
        return "red"
    if value >= overall * AMBER_RMSE_RATIO:
        return "amber"
    return "ok"
