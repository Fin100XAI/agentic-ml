"""Multi-series (panel) forecasting: one forecast per group, honestly.

Detects group columns (categoricals with repeated dates per group), fits the
chosen forecaster per group, and rolls the results up. Groups whose history is
too short are flagged and skipped with a reason - never silently forecast.
A compact per-group table feeds ONE cross-group LLM summary downstream
(never one call per group).
"""
from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import pandas as pd

from .catalog import get_model

MIN_POINTS = 20          # matches the forecasters' own minimum
MAX_GROUPS = 60
BACKTEST_CUT = 0.7       # earlier origin for the per-group backtest
DIRECTION_EPS = 2.0      # percent change below this reads as flat


def detect_group_columns(
    df: pd.DataFrame, target: str | None, time_column: str | None
) -> list[dict[str, Any]]:
    """Categorical columns that partition the data into repeated time series."""
    if not time_column or time_column not in df.columns:
        return []
    out = []
    n = len(df)
    for col in df.columns:
        if col in (target, time_column):
            continue
        s = df[col]
        nunique = s.nunique(dropna=True)
        if not (2 <= nunique <= MAX_GROUPS):
            continue
        if pd.api.types.is_numeric_dtype(s) and nunique > 12:
            continue  # continuous numerics are not groups
        avg_points = n / nunique
        if avg_points < MIN_POINTS:
            continue  # even the average group would be too short
        # dates must repeat across groups (panel shape, not one long series)
        dates_per_group = df.groupby(s, observed=True)[time_column].nunique()
        if dates_per_group.median() < MIN_POINTS:
            continue
        out.append({
            "column": str(col),
            "n_groups": int(nunique),
            "avg_points": round(float(avg_points), 1),
        })
    out.sort(key=lambda c: -c["avg_points"])
    return out


def forecast_groups(
    df: pd.DataFrame,
    model_key: str,
    hyperparams: dict[str, Any],
    target: str,
    time_column: str,
    group_column: str,
    agg: str = "sum",
) -> dict[str, Any]:
    plugin = get_model(model_key)
    agg = agg if agg in ("sum", "mean") else "sum"

    names = [str(g) for g in df[group_column].dropna().unique()][:MAX_GROUPS]
    groups: list[dict[str, Any]] = []

    def fit_one(name: str) -> dict[str, Any]:
        sub = df[df[group_column].astype(str) == name]
        n_points = int(pd.to_numeric(sub[target], errors="coerce").notna().sum())
        if n_points < MIN_POINTS:
            return {"name": name, "n_points": n_points, "status": "skipped",
                    "reason": f"only {n_points} usable points - fewer than the {MIN_POINTS} a forecast needs"}
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                out = plugin.run(sub, hyperparams, target=target, time_column=time_column)
        except Exception as exc:
            return {"name": name, "n_points": n_points, "status": "skipped",
                    "reason": f"model could not fit this series ({str(exc)[:80]})"}
        series = out["artifacts"]["series"]
        forecast = out["artifacts"]["forecast"]
        mape = out["metrics"].get("mape_pct")

        # one earlier-origin backtest per group (same seed rules, bounded cost)
        backtest = None
        try:
            cut = sub.head(int(len(sub) * BACKTEST_CUT))
            if pd.to_numeric(cut[target], errors="coerce").notna().sum() >= MIN_POINTS:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    earlier = plugin.run(cut, hyperparams, target=target, time_column=time_column)
                m2 = earlier["metrics"].get("mape_pct")
                if isinstance(mape, (int, float)) and isinstance(m2, (int, float)):
                    spread = abs(mape - m2) / max(abs(np.mean([mape, m2])), 1e-9)
                    backtest = {"folds": [round(float(m2), 2), round(float(mape), 2)],
                                "verdict": "stable" if spread <= 0.5 else "variable"}
        except Exception:
            pass

        actuals = [p["actual"] for p in series if p.get("actual") is not None]
        h = len(forecast)
        recent = float(np.sum(actuals[-h:])) if actuals else 0.0
        projected = float(np.sum([p["forecast"] for p in forecast]))
        delta_pct = ((projected - recent) / abs(recent) * 100) if recent else 0.0
        direction = ("up" if delta_pct > DIRECTION_EPS
                     else "down" if delta_pct < -DIRECTION_EPS else "flat")
        return {
            "name": name, "n_points": n_points, "status": "ok",
            "mape_pct": round(float(mape), 2) if isinstance(mape, (int, float)) else None,
            "direction": direction, "delta_pct": round(delta_pct, 1),
            "backtest": backtest, "series": series, "forecast": forecast,
        }

    try:
        from joblib import Parallel, delayed

        groups = list(Parallel(n_jobs=4, prefer="threads")(delayed(fit_one)(n) for n in names))
    except Exception:
        groups = [fit_one(n) for n in names]

    ok = [g for g in groups if g["status"] == "ok"]
    skipped = [g for g in groups if g["status"] == "skipped"]

    rollup = _rollup(ok, agg)
    mapes = [g["mape_pct"] for g in ok if g["mape_pct"] is not None]
    metrics = {
        "groups_total": len(groups),
        "groups_forecast": len(ok),
        "groups_skipped": len(skipped),
        "mape_median": round(float(np.median(mapes)), 2) if mapes else None,
        "mape_worst": round(float(np.max(mapes)), 2) if mapes else None,
        "horizon": len(rollup["forecast"]) if rollup else 0,
    }
    # compact table for the ONE cross-group summary call downstream
    summary_table = [
        {"group": g["name"], "status": g["status"],
         **({"direction": g["direction"], "mape_pct": g["mape_pct"],
             "delta_pct": g["delta_pct"]} if g["status"] == "ok" else {"reason": g["reason"]})}
        for g in groups
    ]
    return {
        "metrics": metrics,
        "artifacts": {
            **(rollup or {}),
            "multi": {"group_column": group_column, "agg": agg, "groups": groups},
            "multi_summary_table": summary_table,
        },
    }


def _rollup(ok: list[dict[str, Any]], agg: str) -> dict[str, Any] | None:
    """Aggregate the per-group histories and forecasts into one series."""
    if not ok:
        return None
    hist: dict[str, list[float]] = {}
    for g in ok:
        for p in g["series"]:
            if p.get("actual") is not None:
                hist.setdefault(p["t"], []).append(float(p["actual"]))
    h = max(len(g["forecast"]) for g in ok)
    fc: list[list[float]] = [[] for _ in range(h)]
    for g in ok:
        for i, p in enumerate(g["forecast"]):
            fc[i].append(float(p["forecast"]))
    combine = (lambda v: float(np.sum(v))) if agg == "sum" else (lambda v: float(np.mean(v)))
    series = [{"t": t, "actual": round(combine(vals), 4)} for t, vals in sorted(hist.items())]
    forecast = [{"t": f"+{i + 1}", "forecast": round(combine(vals), 4)}
                for i, vals in enumerate(fc) if vals]
    return {"series": series, "forecast": forecast}
