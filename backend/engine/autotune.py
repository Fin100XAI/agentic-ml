"""Auto-tune: try hyperparameter combinations for every model of a use case.

For each model, candidates are sampled around the data-aware suggestion and
scored on held-out data (same fixed split for every candidate, so scores are
comparable). A per-model time budget keeps slow models (e.g. seasonal ARIMA)
from stalling the whole sweep.
"""
from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd

from .catalog import models_for_use_case
from .catalog.base import ModelPlugin, ParamSpec

# Structural parameters reflect user intent / data shape - not tuned.
SKIP_PARAMS = {"test_size", "horizon", "seasonal_period"}

CANDIDATES = {"classification": 8, "clustering": 8, "forecasting": 4}
TIME_BUDGET_S = 60  # per model

PRIMARY_METRIC = {
    "classification": ("f1", True),
    "clustering": ("silhouette", True),
    "forecasting": ("mape_pct", False),
}


def _sample_candidate(
    specs: list[ParamSpec], base: dict[str, Any], rng: np.random.Generator
) -> dict[str, Any]:
    """Jitter tunable params around the base suggestion, within schema bounds."""
    hp = dict(base)
    for spec in specs:
        if spec.name in SKIP_PARAMS:
            continue
        if spec.type == "select":
            if spec.options and rng.random() < 0.5:
                hp[spec.name] = spec.options[int(rng.integers(len(spec.options)))]
        elif spec.type == "bool":
            if rng.random() < 0.3:
                hp[spec.name] = not bool(base.get(spec.name, spec.default))
        else:
            b = float(base.get(spec.name, spec.default) or spec.default or 1)
            factor = float(rng.uniform(0.5, 2.0))
            v = b * factor
            if spec.min is not None:
                v = max(v, float(spec.min))
            if spec.max is not None:
                v = min(v, float(spec.max))
            hp[spec.name] = int(round(v)) if spec.type == "int" else round(v, 4)
    return hp


def _score(model: ModelPlugin, df: pd.DataFrame, hp: dict[str, Any],
           target: str | None, time_column: str | None, metric: str) -> float | None:
    try:
        out = model.run(df, model.coerce_hyperparams(hp), target=target, time_column=time_column)
        out["artifacts"].pop("labels", None)
        v = out["metrics"].get(metric)
        return float(v) if isinstance(v, (int, float)) else None
    except Exception:
        return None


def autotune(
    df: pd.DataFrame,
    use_case: str,
    target: str | None,
    time_column: str | None,
    model_configs: dict[str, Any],
    n_candidates: int | None = None,
) -> dict[str, Any]:
    metric, higher_better = PRIMARY_METRIC[use_case]
    recommended = CANDIDATES.get(use_case, 6)
    # User-chosen count, clamped to sane bounds; default to the recommendation.
    n_candidates = max(3, min(20, int(n_candidates))) if n_candidates else recommended
    rng = np.random.default_rng(42)

    results: dict[str, Any] = {}
    for model in models_for_use_case(use_case):
        base = model.coerce_hyperparams(
            (model_configs.get(model.key) or {}).get("hyperparams", {})
        )
        specs = model.param_schema()

        tried: list[dict[str, Any]] = []
        seen: set[str] = set()
        started = time.time()

        candidates = [base] + [_sample_candidate(specs, base, rng) for _ in range(n_candidates * 2)]
        for hp in candidates:
            key = str(sorted(hp.items()))
            if key in seen:
                continue
            seen.add(key)
            if len(tried) >= n_candidates or time.time() - started > TIME_BUDGET_S:
                break
            score = _score(model, df, hp, target, time_column, metric)
            tried.append({"hyperparams": hp, "score": score})

        valid = [t for t in tried if t["score"] is not None]
        if valid:
            best = max(valid, key=lambda t: t["score"]) if higher_better else min(valid, key=lambda t: t["score"])
            suggested_score = tried[0]["score"]  # first candidate is the suggestion
            improvement = None
            if isinstance(suggested_score, (int, float)) and suggested_score:
                delta = (best["score"] - suggested_score) if higher_better else (suggested_score - best["score"])
                improvement = round(delta / abs(suggested_score) * 100, 1)
            results[model.key] = {
                "model_name": model.name,
                "tried": tried,
                "n_tried": len(tried),
                "best_hyperparams": best["hyperparams"],
                "best_score": best["score"],
                "suggested_score": suggested_score,
                "improvement_pct": improvement,
                "elapsed_s": round(time.time() - started, 1),
                "error": None,
            }
        else:
            results[model.key] = {
                "model_name": model.name,
                "tried": tried,
                "n_tried": len(tried),
                "best_hyperparams": base,
                "best_score": None,
                "suggested_score": None,
                "improvement_pct": None,
                "elapsed_s": round(time.time() - started, 1),
                "error": "No candidate produced a valid score (check target/data).",
            }

    return {
        "use_case": use_case,
        "metric": metric,
        "higher_is_better": higher_better,
        "n_candidates": n_candidates,
        "recommended_candidates": recommended,
        "models": results,
    }
