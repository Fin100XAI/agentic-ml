"""Cross-sheet join scout: proposes how to combine a multi-sheet workbook.

Deterministic: for every sheet pair it looks for a join key - a column pair
where the right side looks like a lookup key (mostly unique) and the left
side's values are mostly found in it. Same-name columns get a small bonus.
The proposal includes the actual merged shape (the merge is executed once to
verify it does not multiply rows), so the human approves something concrete.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

_SAMPLE = 2000
MIN_CONTAINMENT = 0.5  # at least half the left values must find a match


def _norm(col: str) -> str:
    return str(col).strip().lower().replace(" ", "_")


def propose_stack(book: dict[str, pd.DataFrame]) -> dict[str, Any] | None:
    """Largest group of sheets sharing a normalized column set -> stack offer.

    Quarterly or yearly tabs of the same report usually differ only in
    header case/spacing; combining them row-wise with a source_sheet column
    is the natural assembly.
    """
    groups: dict[frozenset, list[str]] = {}
    for name, frame in book.items():
        groups.setdefault(frozenset(_norm(c) for c in frame.columns), []).append(name)
    best = max(groups.values(), key=len)
    if len(best) < 2:
        return None
    return {
        "sheets": best,
        "n_rows": int(sum(len(book[s]) for s in best)),
        "note": (
            f"{len(best)} sheets share the same columns - combine them into one "
            "table (rows appended, with a source_sheet column recording where "
            "each row came from)."
        ),
    }


def perform_multi_stack(book: dict[str, pd.DataFrame], sheets: list[str]) -> pd.DataFrame:
    """Append the chosen sheets row-wise, aligning headers by normalization.

    The first sheet's spelling wins; every row keeps its origin in
    ``source_sheet``. Refuses sheets whose columns do not line up.
    """
    chosen = [s for s in sheets if s in book]
    if len(chosen) < 2:
        raise ValueError("Pick at least two sheets to combine.")
    canon = {_norm(c): str(c) for c in book[chosen[0]].columns}
    frames = []
    for name in chosen:
        frame = book[name]
        if {_norm(c) for c in frame.columns} != set(canon):
            raise ValueError(
                f"Sheet '{name}' has different columns than '{chosen[0]}' - "
                "sheets can only be combined when they hold the same table."
            )
        renamed = frame.rename(columns={c: canon[_norm(c)] for c in frame.columns})
        frames.append(renamed.assign(source_sheet=name))
    return pd.concat(frames, ignore_index=True)


def propose_join(book: dict[str, pd.DataFrame]) -> dict[str, Any] | None:
    names = list(book)
    best: dict[str, Any] | None = None
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            for left, right in ((a, b), (b, a)):
                cand = _best_key(book[left], book[right])
                if cand and (best is None or cand["score"] > best["score"]):
                    best = {"left": left, "right": right, **cand}
    if best is None:
        return None

    try:
        merged = perform_join(
            book, best["left"], best["right"], best["on_left"], best["on_right"]
        )
    except ValueError:
        return None  # key multiplies rows - not a safe proposal

    lf = book[best["left"]]
    same_key = best["on_left"].strip().lower() == best["on_right"].strip().lower()
    key_txt = (
        f"'{best['on_left']}'" if same_key
        else f"'{best['on_left']}' matching '{best['on_right']}'"
    )
    return {
        "left": best["left"],
        "right": best["right"],
        "on_left": best["on_left"],
        "on_right": best["on_right"],
        "how": "left",
        "match_pct": best["match_pct"],
        "joined_rows": int(len(merged)),
        "joined_cols": int(merged.shape[1]),
        "note": (
            f"Every row of '{best['left']}' can pull in extra columns from "
            f"'{best['right']}' via {key_txt} - {best['match_pct']}% of rows find a match. "
            f"Combined: {len(merged):,} rows x {merged.shape[1]} columns."
        ),
    }


def _best_key(left: pd.DataFrame, right: pd.DataFrame) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    for lc in left.columns:
        lvals = left[lc].dropna()
        if lvals.nunique() < 2:
            continue
        lset = set(lvals.astype(str).head(_SAMPLE))
        if not lset:
            continue
        for rc in right.columns:
            rvals = right[rc].dropna()
            if rvals.nunique() < 2 or len(rvals) == 0:
                continue
            uniqueness = rvals.nunique() / len(rvals)
            if uniqueness < 0.5:
                continue  # right side must look like a lookup key
            rset = set(rvals.astype(str).head(_SAMPLE))
            containment = len(lset & rset) / len(lset)
            if containment < MIN_CONTAINMENT:
                continue
            name_bonus = 0.15 if lc.strip().lower() == rc.strip().lower() else 0.0
            score = containment * (0.5 + 0.5 * uniqueness) + name_bonus
            if best is None or score > best["score"]:
                best = {
                    "score": round(score, 4),
                    "on_left": str(lc),
                    "on_right": str(rc),
                    "match_pct": round(containment * 100, 1),
                }
    return best


def perform_join(
    book: dict[str, pd.DataFrame],
    left: str,
    right: str,
    on_left: str,
    on_right: str,
    how: str = "left",
) -> pd.DataFrame:
    if left not in book or right not in book:
        raise ValueError("Sheet not found in the workbook.")
    lf, rf = book[left], book[right]
    if on_left not in lf.columns or on_right not in rf.columns:
        raise ValueError("Join column not found on its sheet.")
    merged = lf.merge(
        rf, left_on=on_left, right_on=on_right,
        how="left" if how not in ("left", "inner") else how,
        suffixes=("", f"_{right}"),
    )
    if len(merged) > max(len(lf), len(rf)) * 3:
        raise ValueError(
            "Joining these sheets multiplies rows - the key is not unique enough "
            "on either side. Pick a single sheet instead."
        )
    if on_right != on_left and on_right in merged.columns:
        merged = merged.drop(columns=[on_right])  # same info as the left key
    return merged
