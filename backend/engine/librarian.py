"""Multi-file librarian: classifies a new file against a project's holdings.

When a file lands in a non-empty project, the librarian proposes how to use it:

- STACK: same schema fingerprint as an existing dataset -> union the rows
  (a source_file column records provenance)
- JOIN: different schema but a shared high-overlap key -> promote the
  sheet-level join scout to file level, same safety rules
- SCORE ROUTE: schema matches a registered model's training schema -> route
  toward scoring / drift checking (the route exists now; scoring itself
  arrives with the model registry tasks)

Everything is a proposal - the human approves, and every assembly becomes a
derived artifact with transform_type stack|join.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

import pandas as pd

from .joins import _best_key

MIN_STACK_MATCH = 1.0  # fingerprints must match exactly to propose stacking


def _normalize(col: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(col).strip().lower()).strip("_")


def schema_fingerprint(columns: list[str]) -> str:
    """Hash of the normalized column set (order-independent)."""
    normalized = sorted(_normalize(c) for c in columns)
    return hashlib.sha256("|".join(normalized).encode()).hexdigest()[:16]


def column_mapping(new_cols: list[str], existing_cols: list[str]) -> dict[str, str] | None:
    """Map new-file columns onto existing names via normalization; None if not 1:1."""
    existing_by_norm = {_normalize(c): c for c in existing_cols}
    mapping = {}
    for c in new_cols:
        target = existing_by_norm.get(_normalize(c))
        if target is None:
            return None
        mapping[c] = target
    return mapping if len(mapping) == len(existing_cols) else None


def classify_file(
    new_df: pd.DataFrame,
    new_filename: str,
    existing: list[dict[str, Any]],  # [{"id", "filename", "df"}]
    registry_schemas: list[dict[str, Any]] | None = None,  # [{"model_id", "version", "purpose", "columns"}]
) -> list[dict[str, Any]]:
    """Return ranked proposals for how this file relates to the project."""
    proposals: list[dict[str, Any]] = []
    new_fp = schema_fingerprint(list(new_df.columns))

    # (d) matches a registered model's training schema -> score/drift route
    for entry in registry_schemas or []:
        feats = entry.get("columns") or []
        if feats and schema_fingerprint(feats) == new_fp:
            proposals.append({
                "kind": "score_route",
                "model_id": entry.get("model_id"),
                "version": entry.get("version"),
                "note": f"This file matches the data '{entry.get('purpose', 'a registered model')}' was trained on - "
                        "it can be scored or drift-checked against that model.",
            })
            break

    for ds in existing:
        ex_df: pd.DataFrame = ds["df"]
        # (b) identical fingerprint -> STACK
        if schema_fingerprint(list(ex_df.columns)) == new_fp:
            proposals.append({
                "kind": "stack",
                "target_dataset_id": ds["id"],
                "target_filename": ds["filename"],
                "new_rows": int(len(new_df)),
                "existing_rows": int(len(ex_df)),
                "combined_rows": int(len(new_df) + len(ex_df)),
                "note": f"Same columns as '{ds['filename']}' - stacking unions the rows "
                        f"({len(ex_df):,} + {len(new_df):,} = {len(new_df) + len(ex_df):,}) and a "
                        "source_file column records where each row came from.",
            })
            continue
        # (c) shared high-overlap key -> JOIN (new file's rows pull the
        # existing file's columns; the existing side must look like a lookup)
        cand = _best_key(new_df, ex_df)
        if cand:
            proposals.append({
                "kind": "join",
                "target_dataset_id": ds["id"],
                "target_filename": ds["filename"],
                "on_left": cand["on_left"],
                "on_right": cand["on_right"],
                "match_pct": cand["match_pct"],
                "note": f"'{cand['on_left']}' lines up with '{cand['on_right']}' in '{ds['filename']}' "
                        f"({cand['match_pct']}% of values match) - joining pulls that file's columns "
                        "onto this one's rows.",
            })

    # Best proposal first: score_route > stack > join, then by match quality.
    order = {"score_route": 0, "stack": 1, "join": 2}
    proposals.sort(key=lambda p: (order[p["kind"]], -(p.get("match_pct") or 100)))
    return proposals[:3]


def perform_stack(
    new_df: pd.DataFrame, existing_df: pd.DataFrame,
    new_filename: str, existing_filename: str,
) -> pd.DataFrame:
    """Union rows of two same-schema frames, recording provenance per row."""
    mapping = column_mapping(list(new_df.columns), list(existing_df.columns))
    if mapping is None:
        raise ValueError("These files do not share the same columns - stacking would scramble them.")
    aligned = new_df.rename(columns=mapping)[list(existing_df.columns)]
    a = existing_df.copy()
    b = aligned.copy()
    a["source_file"] = existing_filename
    b["source_file"] = new_filename
    return pd.concat([a, b], ignore_index=True)
