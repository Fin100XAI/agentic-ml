"""Data remediation: deterministic fix proposals from health-check findings.

Runs between the health check and EDA. Every proposal is optional and
human-approved; applying the approved set produces ONE derived artifact and
the run continues on the fixed frame. The original data never changes.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

DROP_MISSING_THRESHOLD = 0.40  # above this, imputation would invent the column
WINSOR_Z = 4.0


def propose_fixes(df: pd.DataFrame) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    n = len(df)

    # 1. Exact duplicate rows
    dupes = int(df.duplicated().sum())
    if dupes > 0:
        proposals.append({
            "id": "dedupe",
            "kind": "dedupe",
            "column": None,
            "description": f"Remove {dupes:,} exact duplicate row{'s' if dupes != 1 else ''}",
            "reasoning": "Identical rows double-count records and bias every rate and average.",
            "affected_rows": dupes,
            "recommended": True,
        })

    for col in df.columns:
        s = df[col]
        missing = int(s.isna().sum())
        miss_frac = missing / n if n else 0

        # 2. Type coercion: object columns that are really numbers
        if s.dtype == object:
            sample = s.dropna().astype(str).head(200)
            if len(sample) >= 10:
                as_num = pd.to_numeric(sample.str.replace(",", "", regex=False), errors="coerce")
                if as_num.notna().mean() > 0.9 and sample.nunique() > 5:
                    proposals.append({
                        "id": f"coerce:{col}",
                        "kind": "coerce_numeric",
                        "column": str(col),
                        "description": f"Treat '{col}' as numbers (currently text)",
                        "reasoning": "Values like '1,200' are stored as text, so models and charts ignore them.",
                        "affected_rows": int(s.notna().sum()),
                        "recommended": True,
                    })
                    continue  # imputation proposal would use the wrong dtype

        # 3. Missing values: impute or drop
        if missing > 0:
            if miss_frac > DROP_MISSING_THRESHOLD:
                proposals.append({
                    "id": f"dropcol:{col}",
                    "kind": "drop_column",
                    "column": str(col),
                    "description": f"Drop '{col}' ({miss_frac:.0%} missing)",
                    "reasoning": "With most values absent, filling them in would invent data rather than repair it.",
                    "affected_rows": missing,
                    "recommended": True,
                })
            elif pd.api.types.is_numeric_dtype(s):
                med = s.median()
                proposals.append({
                    "id": f"impute:{col}",
                    "kind": "impute_median",
                    "column": str(col),
                    "description": f"Fill {missing:,} missing '{col}' values with the median ({med:g})",
                    "reasoning": "The median is robust to outliers and keeps every row usable.",
                    "affected_rows": missing,
                    "recommended": True,
                })
            else:
                mode = s.mode()
                mode_v = str(mode.iloc[0]) if len(mode) else ""
                proposals.append({
                    "id": f"impute:{col}",
                    "kind": "impute_mode",
                    "column": str(col),
                    "description": f"Fill {missing:,} missing '{col}' values with the most common value ('{mode_v}')",
                    "reasoning": "Keeps every row usable; the most common category is the least-assuming fill.",
                    "affected_rows": missing,
                    "recommended": True,
                })

        # 4. Optional winsorizing of extreme outliers (default UNTICKED)
        if pd.api.types.is_numeric_dtype(s) and s.notna().sum() > 50:
            vals = s.dropna().astype(float)
            std = vals.std()
            if std and std > 0:
                z = (vals - vals.mean()).abs() / std
                extreme = int((z > WINSOR_Z).sum())
                if extreme > 0 and extreme / len(vals) < 0.05:
                    proposals.append({
                        "id": f"winsor:{col}",
                        "kind": "winsorize",
                        "column": str(col),
                        "description": f"Cap {extreme:,} extreme '{col}' outliers at the 1st/99th percentile",
                        "reasoning": "A few far-out values can dominate averages and trends. Only tick this if "
                                     "they are errors - real extremes may be the story.",
                        "affected_rows": extreme,
                        "recommended": False,
                    })

    return proposals


def apply_fixes(
    df: pd.DataFrame, proposals: list[dict[str, Any]], accepted_ids: list[str]
) -> pd.DataFrame:
    """Apply the approved subset. Never mutates the input frame."""
    accepted = {p["id"]: p for p in proposals if p["id"] in set(accepted_ids)}
    work = df.copy()

    if "dedupe" in accepted:
        work = work.drop_duplicates().reset_index(drop=True)

    for p in accepted.values():
        col = p.get("column")
        if not col or col not in work.columns:
            continue
        kind = p["kind"]
        if kind == "coerce_numeric":
            work[col] = pd.to_numeric(
                work[col].astype(str).str.replace(",", "", regex=False), errors="coerce"
            )
        elif kind == "drop_column":
            work = work.drop(columns=[col])
        elif kind == "impute_median":
            work[col] = work[col].fillna(work[col].median())
        elif kind == "impute_mode":
            mode = work[col].mode()
            if len(mode):
                work[col] = work[col].fillna(mode.iloc[0])
        elif kind == "winsorize":
            vals = pd.to_numeric(work[col], errors="coerce")
            lo, hi = vals.quantile(0.01), vals.quantile(0.99)
            work[col] = vals.clip(lower=lo, upper=hi)

    return work
