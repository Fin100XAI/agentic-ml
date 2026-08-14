"""Insight extraction: turn a model run into decision-ready findings.

The models are evidence engines; this module converts their output plus the raw
data into the material a policy maker actually needs — drivers, segments,
outlooks — each with plain-language statements and the numbers behind them.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

TOP_DRIVERS = 4
MAX_TRAITS = 4


def _pct(x: float) -> float:
    return round(float(x) * 100, 1)


# --------------------------------------------------------------------------- #
# Classification → drivers of the outcome
# --------------------------------------------------------------------------- #

def _positive_class(series: pd.Series) -> Any:
    """Pick the 'event' class for rate statements: minority class in binary data."""
    vc = series.value_counts()
    return vc.index[-1] if len(vc) == 2 else vc.index[0]


def _original_column(feature: str, columns: list[str]) -> str | None:
    """Map a (possibly one-hot) feature name back to its source column."""
    if feature in columns:
        return feature
    for col in sorted(columns, key=len, reverse=True):
        if feature.startswith(col + "_"):
            return col
    return None


def _driver_groups(df: pd.DataFrame, col: str, target: str, positive: Any) -> list[dict[str, Any]]:
    """Outcome rate per group of a driver column (quartiles for numeric, categories otherwise)."""
    work = df[[col, target]].dropna()
    if work.empty:
        return []
    is_event = (work[target] == positive).astype(float)

    if pd.api.types.is_numeric_dtype(work[col]) and work[col].nunique() > 8:
        try:
            bins = pd.qcut(work[col], 4, duplicates="drop")
        except ValueError:
            return []
        grouped = is_event.groupby(bins, observed=True)
        labels = [f"{iv.left:g}–{iv.right:g}" for iv in grouped.mean().index]
    else:
        grouped = is_event.groupby(work[col].astype(str))
        labels = [str(i) for i in grouped.mean().index]

    rates = grouped.mean()
    counts = grouped.size()
    return [
        {"label": labels[i], "rate_pct": _pct(rates.iloc[i]), "count": int(counts.iloc[i])}
        for i in range(len(rates))
    ]


def classification_insights(
    df: pd.DataFrame, target: str, artifacts: dict[str, Any], names: dict[str, str]
) -> dict[str, Any]:
    data = df.dropna(subset=[target])
    positive = _positive_class(data[target])
    overall = _pct((data[target] == positive).mean())
    n = len(data)
    target_lbl = names.get(target, target)

    findings: list[dict[str, str]] = [
        {
            "headline": f"{overall}% of records have outcome '{positive}'",
            "detail": f"Across {n:,} records, {overall}% fall in the '{target_lbl} = {positive}' group — the baseline any intervention would move.",
        }
    ]

    drivers: list[dict[str, Any]] = []
    seen: set[str] = set()
    for fi in artifacts.get("feature_importance", []):
        col = _original_column(fi["feature"], [str(c) for c in df.columns])
        if not col or col == target or col in seen:
            continue
        seen.add(col)
        groups = _driver_groups(data, col, target, positive)
        if len(groups) < 2:
            continue
        col_lbl = names.get(col, col)
        rates = [g["rate_pct"] for g in groups]
        hi, lo = max(rates), min(rates)
        lift = round(hi / lo, 1) if lo > 0 else None
        hi_group = groups[rates.index(hi)]
        lo_group = groups[rates.index(lo)]
        drivers.append({"feature": col, "label": col_lbl, "groups": groups, "lift": lift})
        findings.append(
            {
                "headline": f"{col_lbl} separates outcomes {f'{lift}×' if lift else 'sharply'}",
                "detail": (
                    f"Records with {col_lbl.lower()} in '{hi_group['label']}' show a {hi}% rate vs {lo}% for "
                    f"'{lo_group['label']}'"
                    + (f" — {lift}× higher. " if lift else ". ")
                    + "A strong candidate lever for targeted action."
                ),
            }
        )
        if len(drivers) >= TOP_DRIVERS:
            break

    return {
        "outcome_summary": f"{overall}% of {n:,} records have outcome '{positive}' ({target_lbl})",
        "findings": findings,
        "drivers": drivers,
    }


# --------------------------------------------------------------------------- #
# Clustering → segment profiles
# --------------------------------------------------------------------------- #

def clustering_insights(df: pd.DataFrame, labels: list[int], names: dict[str, str] | None = None) -> dict[str, Any]:
    names = names or {}
    numeric_cols = [
        c for c in df.columns
        if pd.api.types.is_numeric_dtype(df[c]) and df[c].nunique() > 2
    ]
    work = df[numeric_cols].copy()
    work["_cluster"] = labels[: len(work)]
    overall_mean = work[numeric_cols].mean()
    overall_std = work[numeric_cols].std().replace(0, np.nan)
    n = len(work)

    segments: list[dict[str, Any]] = []
    findings: list[dict[str, str]] = []
    letters = "ABCDEFGHIJ"

    cluster_ids = sorted({int(l) for l in labels})
    for cid in cluster_ids:
        part = work[work["_cluster"] == cid]
        share = _pct(len(part) / n)
        if cid == -1:
            findings.append(
                {
                    "headline": f"{share}% of records don't fit any group",
                    "headline_alt": "",
                    "detail": f"{len(part):,} records ({share}%) were flagged as outliers — unusual cases worth individual review.",
                }
            )
            segments.append(
                {"cluster": -1, "name": "Outliers", "share_pct": share, "count": int(len(part)), "traits": []}
            )
            continue

        # Traits: features where this segment deviates most from the average.
        z = ((part[numeric_cols].mean() - overall_mean) / overall_std).dropna()
        z = z.reindex(z.abs().sort_values(ascending=False).index)
        traits = [
            {
                "feature": feat,
                "label": names.get(feat, feat),
                "value": round(float(part[feat].mean()), 2),
                "overall": round(float(overall_mean[feat]), 2),
                "direction": "above" if z[feat] > 0 else "below",
            }
            for feat in z.index[:MAX_TRAITS]
            if abs(z[feat]) > 0.25
        ]
        name = f"Segment {letters[len([s for s in segments if s['cluster'] != -1]) % len(letters)]}"
        segments.append(
            {"cluster": cid, "name": name, "share_pct": share, "count": int(len(part)), "traits": traits}
        )

        if traits:
            lead = traits[0]
            findings.append(
                {
                    "headline": f"{name}: {share}% of records, defined by {lead['label']} {lead['direction']} average",
                    "detail": (
                        f"{name} covers {len(part):,} records ({share}%). Typical profile: "
                        + "; ".join(
                            f"{t['label']} {t['direction']} average ({t['value']} vs {t['overall']})"
                            for t in traits[:3]
                        )
                        + ". Policies can be tailored to this group's profile."
                    ),
                }
            )

    n_real = len([s for s in segments if s["cluster"] != -1])
    return {
        "outcome_summary": f"{n:,} records fall into {n_real} distinct group{'s' if n_real != 1 else ''}",
        "findings": findings,
        "segments": segments,
    }


# --------------------------------------------------------------------------- #
# Forecasting → outlook
# --------------------------------------------------------------------------- #

def forecasting_insights(
    artifacts: dict[str, Any], metrics: dict[str, Any], target: str
) -> dict[str, Any]:
    series = [p["actual"] for p in artifacts.get("series", []) if p.get("actual") is not None]
    forecast = [p["forecast"] for p in artifacts.get("forecast", [])]
    if not series or not forecast:
        return {"outcome_summary": "Not enough data for an outlook.", "findings": []}

    h = len(forecast)
    recent = series[-h:]
    projected_total = float(np.sum(forecast))
    recent_total = float(np.sum(recent))
    delta_pct = round((projected_total - recent_total) / abs(recent_total) * 100, 1) if recent_total else None

    # Long-run trend from a linear fit over the full history (a short window
    # would be fooled by seasonal swings).
    tail = series
    slope = float(np.polyfit(range(len(tail)), tail, 1)[0])
    level = float(np.mean(tail)) or 1.0
    trend_pct_per_step = round(slope / abs(level) * 100, 2)
    direction = "rising" if trend_pct_per_step > 0.05 else "falling" if trend_pct_per_step < -0.05 else "flat"

    mape = metrics.get("mape_pct")
    uncertainty = round(float(mape), 1) if isinstance(mape, (int, float)) else None

    findings = [
        {
            "headline": f"{target} is {direction}"
            + (f" ≈ {abs(trend_pct_per_step)}% per period" if direction != "flat" else ""),
            "detail": (
                f"Recent history shows a {direction} trend"
                + (f" of about {abs(trend_pct_per_step)}% per period" if direction != "flat" else "")
                + f". The projection extends this {h} periods ahead."
            ),
        },
        {
            "headline": f"Next {h} periods projected at {projected_total:,.0f}"
            + (f" ({'+' if (delta_pct or 0) >= 0 else ''}{delta_pct}% vs the last {h})" if delta_pct is not None else ""),
            "detail": (
                f"The model projects a total of {projected_total:,.0f} over the next {h} periods, vs "
                f"{recent_total:,.0f} over the most recent {h}"
                + (f" — a change of {'+' if delta_pct >= 0 else ''}{delta_pct}%." if delta_pct is not None else ".")
            ),
        },
    ]
    if uncertainty is not None:
        findings.append(
            {
                "headline": f"Typical forecast error: ±{uncertainty}%",
                "detail": (
                    f"On held-back history the model was off by about {uncertainty}% on average — read the "
                    f"projection as a range of roughly {projected_total * (1 - uncertainty / 100):,.0f} to "
                    f"{projected_total * (1 + uncertainty / 100):,.0f}, not a single number."
                ),
            }
        )

    return {
        "outcome_summary": f"{target} {direction}; next {h} periods ≈ {projected_total:,.0f}"
        + (f" ±{uncertainty}%" if uncertainty is not None else ""),
        "findings": findings,
        "outlook": {
            "direction": direction,
            "trend_pct_per_period": trend_pct_per_step,
            "horizon": h,
            "projected_total": round(projected_total, 1),
            "recent_total": round(recent_total, 1),
            "delta_pct": delta_pct,
            "uncertainty_pct": uncertainty,
        },
    }


# --------------------------------------------------------------------------- #
# Confidence: model quality → plain-language evidence strength
# --------------------------------------------------------------------------- #

def evidence_strength(use_case: str, metrics: dict[str, Any], n_rows: int, pct_missing: float) -> dict[str, Any]:
    level = "limited"
    reason = "The model's ability to separate outcomes could not be established."

    if use_case == "classification":
        auc = metrics.get("roc_auc") or 0
        f1 = metrics.get("f1") or 0
        score = max(auc, f1)
        if score >= 0.8:
            level, reason = "strong", f"The model distinguishes outcomes reliably (score {score})."
        elif score >= 0.65:
            level, reason = "moderate", f"The model finds real but imperfect patterns (score {score})."
        else:
            reason = f"The model separates outcomes only weakly (score {score}) — treat drivers as hypotheses."
    elif use_case == "clustering":
        sil = metrics.get("silhouette") or 0
        if sil >= 0.5:
            level, reason = "strong", f"Groups are clearly separated (silhouette {sil})."
        elif sil >= 0.25:
            level, reason = "moderate", f"Groups exist but overlap somewhat (silhouette {sil})."
        else:
            reason = f"Group boundaries are fuzzy (silhouette {sil}) — profiles are indicative only."
    elif use_case == "forecasting":
        mape = metrics.get("mape_pct")
        if isinstance(mape, (int, float)):
            if mape <= 10:
                level, reason = "strong", f"Backtested forecasts were within {mape}% on average."
            elif mape <= 25:
                level, reason = "moderate", f"Backtested forecasts were off by {mape}% on average."
            else:
                reason = f"Backtested error was high ({mape}%) — use the direction, not the numbers."

    caveats = ["These patterns are correlations in the data — confirm causation before major policy changes."]
    if n_rows < 500:
        caveats.append(f"Sample is small ({n_rows:,} records); findings may not generalize.")
    if pct_missing and pct_missing > 5:
        caveats.append(f"{pct_missing}% of values are missing, which can bias the picture.")

    return {"level": level, "reason": reason, "caveats": caveats}


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def build_insights(
    df: pd.DataFrame,
    use_case: str,
    target: str | None,
    metrics: dict[str, Any],
    artifacts: dict[str, Any],
    cluster_labels: list[int] | None,
    n_rows: int,
    pct_missing: float,
    display_labels: dict[str, str] | None = None,
) -> dict[str, Any]:
    names = display_labels or {}
    if use_case == "classification" and target:
        core = classification_insights(df, target, artifacts, names)
    elif use_case == "clustering" and cluster_labels:
        core = clustering_insights(df, cluster_labels, names)
    elif use_case == "forecasting":
        core = forecasting_insights(artifacts, metrics, names.get(target or "", target or "the series"))
    else:
        core = {"outcome_summary": "", "findings": []}

    core["use_case"] = use_case
    core["evidence"] = evidence_strength(use_case, metrics, n_rows, pct_missing)
    return core
