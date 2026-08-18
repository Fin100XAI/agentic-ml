"""Shape Scout: recognize WHAT KIND of dataset arrived, so the exploration
can lead with the right questions. Fully deterministic and explainable -
the classification is shown on the board and the user can read the why.

Shapes:
- cross_section: one row per entity, measures across columns, no time
  (a census district table)
- time_series:   one row per period (monthly collections)
- panel:         entities observed repeatedly across periods
  (district x month enrollment)
- transactional: one row per event, with event dates
  (applications, transactions)
- survey:        mostly categorical answer columns, little numeric
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from .starter import _is_numberish_text, _plausible_period
from .readiness import _find_period_column


def _usable_cats(df: pd.DataFrame, period: str | None) -> list[str]:
    out = []
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_numeric_dtype(s) or str(c) == period:
            continue
        n = s.nunique(dropna=True)
        if 2 <= n <= 500 and n < len(df) and not _is_numberish_text(s):
            out.append(str(c))
    return out


def classify_shape(df: pd.DataFrame) -> dict[str, Any]:
    """-> {shape, label, reasoning, period, panel_entity}."""
    period = _find_period_column(df)
    if period is not None and not _plausible_period(df[period]):
        period = None
    numerics = [str(c) for c in df.columns
                if pd.api.types.is_numeric_dtype(df[c])
                and df[c].nunique(dropna=True) > 2]
    cats = _usable_cats(df, period)
    n_rows = len(df)

    if period is not None:
        n_periods = int(df[period].nunique(dropna=True))
        # Panel: some entity is observed across several periods, with roughly
        # ONE row per (entity, period) pair. Many rows per pair means the
        # rows are EVENTS (transactional), even though a category repeats.
        for cat in cats:
            n_ent = int(df[cat].nunique(dropna=True))
            if not 2 <= n_ent <= 200:
                continue
            per_entity = df.groupby(cat)[period].nunique()
            pair_sizes = df.groupby([cat, period]).size()
            if float(per_entity.median()) >= 3 and float(pair_sizes.median()) <= 1.2:
                return {
                    "shape": "panel",
                    "label": f"{n_ent} {cat} values tracked across {n_periods} {period} periods",
                    "reasoning": f"Each {cat} appears in several {period} periods - "
                                 f"this is repeated observation, so trends per {cat} "
                                 f"and who-rose-vs-fell lead the exploration.",
                    "period": period, "panel_entity": cat,
                }
        if n_periods >= 0.8 * n_rows:
            return {
                "shape": "time_series",
                "label": f"a {period} time series ({n_periods} periods)",
                "reasoning": f"Roughly one row per {period} - movement over time "
                             f"is the main story, so trends and period-over-period "
                             f"changes lead.",
                "period": period, "panel_entity": None,
            }
        return {
            "shape": "transactional",
            "label": f"event records with {period} dates ({n_rows:,} rows)",
            "reasoning": f"Many rows share each {period} value - each row reads as "
                         f"an event, so volumes over time and splits by category lead.",
            "period": period, "panel_entity": None,
        }

    if len(cats) >= 3 and len(numerics) <= max(1, len(cats) // 2):
        return {
            "shape": "survey",
            "label": f"answer-style data ({len(cats)} category columns)",
            "reasoning": "Mostly categorical columns with little numeric measure - "
                         "counts and response shares lead; averaging codes would "
                         "be meaningless.",
            "period": None, "panel_entity": None,
        }

    return {
        "shape": "cross_section",
        "label": f"a snapshot across {n_rows:,} rows ({len(numerics)} measures)",
        "reasoning": "One row per entity with measures across columns and no time "
                     "axis - rankings, relationships and domain views lead; trend "
                     "charts would be misleading here.",
        "period": None, "panel_entity": None,
    }
