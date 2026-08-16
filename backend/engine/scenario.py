"""What-if scenarios on a registered supervised model.

Start from a typical record (training-time medians/modes), perturb one to
three features, and see how the prediction moves. Values outside the observed
training range are flagged as extrapolation - the model is guessing there.
All framing is explicitly correlation-not-causation.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .scoring import rebuild_and_score

CURVE_POINTS = 25

CAUSAL_CAVEAT = (
    "This shows how the model's PREDICTION responds, not what would happen if "
    "you changed the real world - the relationship is correlation until a "
    "controlled pilot proves otherwise."
)


def _predict_frame(
    rows: list[dict[str, Any]],
    entry: dict[str, Any],
    model: Any,
    train_config: dict[str, Any],
    remediation: dict[str, Any] | None,
    class_names: list[str] | None,
) -> list[float]:
    """Predict a handful of constructed rows through the training lineage.

    Returns a numeric response per row: the positive-class probability for
    binary classification (falls back to the label index), or the raw
    prediction for regression.
    """
    frame = pd.DataFrame(rows)
    result = rebuild_and_score(
        frame, entry, model, train_config,
        pii_actions=None, pii_findings=None,  # baselines are synthetic, no PII
        remediation=remediation, class_names=class_names,
    )
    scored = result["scored"]
    if "probability" in scored.columns:
        return [float(v) for v in scored["probability"]]
    if entry["use_case"] == "classification":
        names = class_names or []
        return [float(names.index(v)) if v in names else 0.0 for v in scored["prediction"]]
    return [float(v) for v in scored["prediction"]]


def run_scenario(
    entry: dict[str, Any],
    model: Any,
    train_config: dict[str, Any],
    remediation: dict[str, Any] | None,
    class_names: list[str] | None,
    perturbations: dict[str, Any],
) -> dict[str, Any]:
    baseline = dict(entry.get("baseline") or {})
    if not baseline:
        raise ValueError("This model version predates scenario support - retrain it once to enable what-if.")
    ranges = entry.get("feature_ranges") or {}

    perturbed = dict(baseline)
    extrapolations = []
    for col, val in perturbations.items():
        if col not in baseline:
            raise ValueError(f"'{col}' is not an input of this model.")
        perturbed[col] = val
        rng = ranges.get(col)
        if rng is not None:
            try:
                v = float(val)
                if v < rng[0] or v > rng[1]:
                    extrapolations.append({"column": col, "value": v, "observed": rng})
            except (TypeError, ValueError):
                pass

    base_v, new_v = _predict_frame(
        [baseline, perturbed], entry, model, train_config, remediation, class_names
    )
    is_proba = entry["use_case"] == "classification"
    return {
        "response": "probability" if is_proba else "prediction",
        "baseline": round(base_v, 4),
        "perturbed": round(new_v, 4),
        "change": round(new_v - base_v, 4),
        "perturbations": perturbations,
        "extrapolations": extrapolations,
        "caveat": CAUSAL_CAVEAT,
    }


def response_curve(
    entry: dict[str, Any],
    model: Any,
    train_config: dict[str, Any],
    remediation: dict[str, Any] | None,
    class_names: list[str] | None,
    feature: str,
    others: dict[str, Any] | None = None,
) -> dict[str, Any]:
    baseline = dict(entry.get("baseline") or {})
    ranges = entry.get("feature_ranges") or {}
    if feature not in ranges:
        raise ValueError(f"'{feature}' has no observed numeric range to sweep.")
    if not baseline:
        raise ValueError("This model version predates scenario support.")
    lo, hi = ranges[feature]
    xs = np.linspace(lo, hi, CURVE_POINTS)
    rows = []
    for x in xs:
        row = dict(baseline)
        row.update(others or {})
        row[feature] = float(x)
        rows.append(row)
    ys = _predict_frame(rows, entry, model, train_config, remediation, class_names)
    return {
        "feature": feature,
        "response": "probability" if entry["use_case"] == "classification" else "prediction",
        "points": [{"x": round(float(x), 4), "y": round(float(y), 4)} for x, y in zip(xs, ys)],
        "observed": [lo, hi],
        "caveat": CAUSAL_CAVEAT,
    }
