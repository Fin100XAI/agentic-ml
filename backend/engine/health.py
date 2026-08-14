"""Data health checks: catch edge cases early and tell the human what to do.

Every issue carries a severity, a plain-language explanation, and a concrete
suggestion. The list is attached to the profile, shown prominently in the UI,
and fed to the recommendation agent so it can reason around the problems.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

INFO = "info"
WARNING = "warning"
CRITICAL = "critical"


def _issue(severity: str, title: str, detail: str, suggestion: str) -> dict[str, str]:
    return {"severity": severity, "title": title, "detail": detail, "suggestion": suggestion}


def assess_health(df: pd.DataFrame, profile: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    n_rows, n_cols = df.shape
    columns = profile["columns"]

    # --- Size ---------------------------------------------------------------
    if n_rows < 50:
        issues.append(_issue(
            CRITICAL, "Very few rows",
            f"Only {n_rows} rows. Models need examples to learn from - results on this little data are unreliable.",
            "Treat any result as a rough hint only. If possible, collect more data (a few hundred rows minimum) before acting on findings.",
        ))
    elif n_rows < 200:
        issues.append(_issue(
            WARNING, "Small dataset",
            f"{n_rows} rows is workable but small; patterns may not generalize.",
            "Prefer simpler models (they overfit less on small data) and read the evidence-strength panel carefully.",
        ))
    elif n_rows > 100_000:
        issues.append(_issue(
            INFO, "Large dataset",
            f"{n_rows:,} rows - great for reliability. Training may take noticeably longer.",
            "Nothing to fix. If runs feel slow, compare models on defaults first, then tune only the winner.",
        ))

    # --- Missing data -------------------------------------------------------
    pct_missing = profile["missingness"].get("pct_missing") or 0
    if pct_missing > 30:
        issues.append(_issue(
            CRITICAL, "Heavy missing data",
            f"{pct_missing}% of all cells are empty. Models fill gaps with typical values, which can badly distort patterns at this level.",
            "Check whether the export went wrong or whether certain columns are simply unused - consider removing near-empty columns and re-uploading.",
        ))
    elif pct_missing > 5:
        issues.append(_issue(
            WARNING, "Noticeable missing data",
            f"{pct_missing}% of cells are empty. Gaps are filled with typical values during modeling, which can soften real patterns.",
            "Review the columns with most gaps (see column details). If a column is >50% empty, dropping it is usually better than filling it.",
        ))

    for c in columns:
        if (c.get("missing_pct") or 0) > 50:
            issues.append(_issue(
                WARNING, f"'{c.get('display_name', c['name'])}' is mostly empty",
                f"{c['missing_pct']}% of its values are missing.",
                "Consider excluding this column - a mostly-empty column adds noise, not signal.",
            ))

    # --- Constant / duplicate ----------------------------------------------
    constant = [c for c in columns if c["unique_count"] <= 1 and c["missing_count"] < n_rows]
    if constant:
        names = ", ".join(c.get("display_name", c["name"]) for c in constant[:3])
        issues.append(_issue(
            INFO, "Constant column(s)",
            f"{names} {'has' if len(constant) == 1 else 'have'} the same value in every row.",
            "These carry no information and are ignored automatically - no action needed.",
        ))

    n_dupes = int(df.duplicated().sum())
    if n_dupes > 0 and n_dupes / n_rows > 0.05:
        issues.append(_issue(
            WARNING, "Duplicate rows",
            f"{n_dupes:,} rows ({n_dupes / n_rows:.0%}) are exact duplicates.",
            "If duplicates are data errors, deduplicate and re-upload; if they are legitimate repeated events, no action needed.",
        ))

    # --- Class imbalance (any low-cardinality candidate target) -------------
    for c in columns:
        if c["role"] in ("boolean", "categorical") and 2 <= c["unique_count"] <= 10:
            vc = df[c["name"]].value_counts(normalize=True)
            if len(vc) >= 2 and vc.iloc[0] > 0.9:
                issues.append(_issue(
                    WARNING, f"'{c.get('display_name', c['name'])}' is very one-sided",
                    f"{vc.iloc[0]:.0%} of rows have the value '{vc.index[0]}'. If you predict this column, a lazy model can look accurate by always guessing the majority.",
                    "Judge models by recall / F1 rather than accuracy, and treat the rare class as the one that matters.",
                ))

    # --- Structure-specific -------------------------------------------------
    numeric_count = sum(1 for c in columns if c["role"] == "numeric")
    if numeric_count == 0:
        issues.append(_issue(
            WARNING, "No numeric columns",
            "Everything is text/categories/dates. Clustering and forecasting need numbers to work with.",
            "Classification can still work (categories are encoded automatically). For other analyses, add numeric measures to the data.",
        ))

    has_datetime = any(c["role"] == "datetime" for c in columns)
    if has_datetime and n_rows < 30:
        issues.append(_issue(
            WARNING, "Short time series",
            f"Only {n_rows} time points - too few to separate trend from noise reliably.",
            "Forecasts need at least ~30 points (ideally 100+). Use any forecast as a rough direction only.",
        ))

    id_like = sum(1 for c in columns if c["role"] == "identifier")
    if id_like >= max(2, n_cols // 2):
        issues.append(_issue(
            INFO, "Many ID-like columns",
            f"{id_like} columns look like identifiers (unique per row) and are excluded from modeling.",
            "No action needed - just be aware models only learn from the remaining columns.",
        ))

    # --- Overall score ------------------------------------------------------
    if any(i["severity"] == CRITICAL for i in issues):
        score = "poor"
    elif any(i["severity"] == WARNING for i in issues):
        score = "caution"
    else:
        score = "good"

    return {"score": score, "issues": issues}
