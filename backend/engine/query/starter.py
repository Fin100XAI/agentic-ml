"""Starter questions: what the exploring agents ask on the user's behalf.

Deterministic generation from the schema - each candidate is a natural
question WITH its ready-made QueryPlan, so execution never depends on an
LLM. The LLM's only later role is choosing which findings are worth
leading with and phrasing them (judge and phrase, rule 11).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from engine.profiler import friendly_name as _lbl

from .readiness import _find_entity_key, _find_period_column

MAX_STARTERS = 9
# Grouping columns may have up to 60 levels (India has 35+ states; charts
# guard their own category caps and top-N keeps rankings honest).
MAX_CAT_LEVELS = 60


def _is_numberish_text(s: pd.Series) -> bool:
    """Numbers stored as text ('4,076', '-', '959') must not be treated as
    categories - grouping by them is meaningless. The health screen already
    proposes fixing such columns properly."""
    non_null = s.dropna().astype(str).str.strip()
    non_null = non_null[~non_null.isin(["", "-", "NA", "N/A", "nan"])]
    if len(non_null) < 5:
        return False
    coerced = pd.to_numeric(non_null.str.replace(",", "", regex=False),
                            errors="coerce")
    return bool(coerced.notna().mean() > 0.6)


def _plausible_period(s: pd.Series) -> bool:
    """A time column must parse as PLAUSIBLE dates - '959' technically
    parses as the year 959 AD, which is how a sex-ratio column once became
    the timeline. Years must sit in 1900-2100."""
    sample = s.dropna().astype(str).head(60)
    if len(sample) < 3:
        return False
    parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
    ok = parsed.notna()
    if ok.mean() < 0.6:
        return False
    years = parsed.dropna().dt.year
    return bool(years.between(1900, 2100).mean() > 0.9)


def _is_monthly(series: pd.Series) -> bool:
    """True when the distinct periods parse as dates spaced ~one month."""
    vals = series.dropna().astype(str).unique()
    parsed = pd.to_datetime(pd.Series(sorted(vals)), errors="coerce", format="mixed")
    parsed = parsed.dropna().sort_values()
    if len(parsed) < 13:
        return False
    diffs = parsed.diff().dropna().dt.days
    return bool(diffs.between(28, 31).mean() > 0.8)


def _pick_columns(df: pd.DataFrame) -> dict[str, Any]:
    period = _find_period_column(df)
    if period is not None and not _plausible_period(df[period]):
        period = None
    key = _find_entity_key(df, period)
    numerics = [
        str(c) for c in df.columns
        if pd.api.types.is_numeric_dtype(df[c]) and df[c].nunique(dropna=True) > 2
        and str(c) != period
    ]
    cats = [
        str(c) for c in df.columns
        if not pd.api.types.is_numeric_dtype(df[c]) and str(c) != period
        and 2 <= df[c].nunique(dropna=True) <= MAX_CAT_LEVELS
        # all-unique text is an identifier, not a category worth counting
        and df[c].nunique(dropna=True) < len(df)
        # numbers-stored-as-text are broken measures, not categories
        and not _is_numberish_text(df[c])
    ]
    # Prefer the entity key as the main categorical; highest-spread numeric first.
    if key and key in cats:
        cats = [key] + [c for c in cats if c != key]
    numerics.sort(key=lambda c: float(df[c].std() or 0) / (abs(float(df[c].mean() or 0)) + 1e-9),
                  reverse=True)
    return {"period": period, "cats": cats, "numerics": numerics}


# The template menu the Question Scout may fill. The LLM only CHOOSES
# columns for these shapes - deterministic code builds every plan.
SCOUT_TEMPLATES = ("top_groups", "bottom_groups", "avg_per_group",
                   "relationship", "split", "count", "trend", "change",
                   "trend_by", "kpi")


def _build_from_selection(template: str, source: str, df: pd.DataFrame,
                          metric: str | None, group: str | None,
                          second_metric: str | None,
                          period: str | None) -> dict[str, Any] | None:
    """One template + validated columns -> the same deterministic plans the
    hand-written starters use. Returns None when inapplicable."""
    if template == "top_groups" and metric and group:
        n = min(10, int(df[group].nunique(dropna=True)))
        return {"question": f"Which {_lbl(group)} has the highest total {_lbl(metric)}?",
                "plan": {"source": source, "steps": [
                    {"op": "group_by", "columns": [group]},
                    {"op": "aggregate", "column": metric, "fn": "sum", "alias": f"total_{metric}"},
                    {"op": "sort", "column": f"total_{metric}", "dir": "desc"},
                    {"op": "top_n", "n": n}]}}
    if template == "bottom_groups" and metric and group:
        return {"question": f"Which {_lbl(group)} has the lowest total {_lbl(metric)}?",
                "plan": {"source": source, "steps": [
                    {"op": "group_by", "columns": [group]},
                    {"op": "aggregate", "column": metric, "fn": "sum", "alias": f"total_{metric}"},
                    {"op": "sort", "column": f"total_{metric}", "dir": "asc"},
                    {"op": "top_n", "n": 5}]}}
    if template == "avg_per_group" and metric and group:
        return {"question": f"What is the average {_lbl(metric)} per {_lbl(group)}?",
                "plan": {"source": source, "steps": [
                    {"op": "group_by", "columns": [group]},
                    {"op": "aggregate", "column": metric, "fn": "mean", "alias": f"avg_{metric}"},
                    {"op": "sort", "column": f"avg_{metric}", "dir": "desc"}]}}
    if template == "relationship" and metric and second_metric and group:
        return {"question": f"How do {_lbl(metric)} and {_lbl(second_metric)} move together across {_lbl(group)}?",
                "plan": {"source": source, "steps": [
                    {"op": "group_by", "columns": [group]},
                    {"op": "aggregate", "column": metric, "fn": "sum", "alias": f"total_{metric}"},
                    {"op": "aggregate", "column": second_metric, "fn": "sum", "alias": f"total_{second_metric}"}]}}
    if template == "split" and metric and group:
        return {"question": f"How does total {_lbl(metric)} split across {_lbl(group)}?",
                "plan": {"source": source, "steps": [
                    {"op": "group_by", "columns": [group]},
                    {"op": "aggregate", "column": metric, "fn": "sum", "alias": f"total_{metric}"},
                    {"op": "sort", "column": f"total_{metric}", "dir": "desc"}]}}
    if template == "count" and group:
        return {"question": f"How many rows fall under each {_lbl(group)}?",
                "plan": {"source": source, "steps": [
                    {"op": "group_by", "columns": [group]},
                    {"op": "aggregate", "column": group, "fn": "count", "alias": "count"},
                    {"op": "sort", "column": "count", "dir": "desc"}]}}
    if template == "trend" and metric and period:
        return {"question": f"How does total {_lbl(metric)} move across {_lbl(period)}?",
                "plan": {"source": source, "steps": [
                    {"op": "group_by", "columns": [period]},
                    {"op": "aggregate", "column": metric, "fn": "sum", "alias": f"total_{metric}"},
                    {"op": "sort", "column": period, "dir": "asc"}]}}
    if template == "change" and metric and period             and 3 <= int(df[period].nunique(dropna=True)) <= 120:
        return {"question": f"How did total {_lbl(metric)} change from one {_lbl(period)} to the next?",
                "plan": {"source": source, "steps": [
                    {"op": "group_by", "columns": [period]},
                    {"op": "aggregate", "column": metric, "fn": "sum", "alias": f"total_{metric}"},
                    {"op": "sort", "column": period, "dir": "asc"},
                    {"op": "delta_vs_period", "column": f"total_{metric}",
                     "period_column": period, "lag": 1}]}}
    if template == "trend_by" and metric and period and group             and 2 <= int(df[group].nunique(dropna=True)) <= 9:
        return {"question": f"How does total {_lbl(metric)} move across {_lbl(period)} in each {_lbl(group)}?",
                "plan": {"source": source, "steps": [
                    {"op": "group_by", "columns": [period, group]},
                    {"op": "aggregate", "column": metric, "fn": "sum", "alias": f"total_{metric}"},
                    {"op": "sort", "column": period, "dir": "asc"}]}}
    if template == "kpi" and metric:
        return {"question": f"What are the overall total and average of {_lbl(metric)}?",
                "plan": {"source": source, "steps": [
                    {"op": "aggregate", "column": metric, "fn": "sum", "alias": f"total_{metric}"},
                    {"op": "aggregate", "column": metric, "fn": "mean", "alias": f"avg_{metric}"}]}}
    return None


def starters_from_selections(selections: list[dict[str, Any]], df: pd.DataFrame,
                             source: str) -> list[dict[str, Any]]:
    """Validate the Question Scout's choices and build plans. Only real
    numeric metrics and usable grouping columns survive; at most 2
    questions per metric (the diversity guarantee is enforced HERE, not
    trusted to the LLM)."""
    picks = _pick_columns(df)
    valid_nums = set(picks["numerics"])
    valid_cats = set(picks["cats"])
    period = picks["period"]
    out: list[dict[str, Any]] = []
    metric_uses: dict[str, int] = {}
    seen: set[str] = set()
    # Template diversity is enforced HERE too: ranked questions (top/bottom)
    # dominate an all-bar board if left unchecked, and "highest X" plus
    # "lowest X" of the SAME metric is one insight wearing two tiles.
    _RANKED = ("top_groups", "bottom_groups")
    ranked_used = 0
    ranked_metrics: set[str] = set()
    used_templates: set[str] = set()
    for sel in selections:
        template = str(sel.get("template", ""))
        metric = sel.get("metric") or None
        group = sel.get("group") or None
        second = sel.get("second_metric") or None
        if template not in SCOUT_TEMPLATES:
            continue
        if metric and metric not in valid_nums:
            continue
        if second and second not in valid_nums:
            continue
        if group and group not in valid_cats:
            continue
        if metric and metric_uses.get(metric, 0) >= 2:
            continue
        if template in _RANKED:
            if ranked_used >= 3:
                continue
            if metric and metric in ranked_metrics:
                continue
        cand = _build_from_selection(template, source, df, metric, group,
                                     second, period)
        # The scout may phrase the question naturally (its proper role);
        # the PLAN stays exactly what the template built.
        natural = str(sel.get("question") or "").strip()
        if cand and 10 <= len(natural) <= 160:
            cand["question"] = natural
        if cand and cand["question"] not in seen:
            seen.add(cand["question"])
            out.append(cand)
            used_templates.add(template)
            if metric:
                metric_uses[metric] = metric_uses.get(metric, 0) + 1
            if template in _RANKED:
                ranked_used += 1
                if metric:
                    ranked_metrics.add(metric)
    # Guarantee a relationship (scatter) when the data offers one and the
    # scout skipped it - deterministically: the two highest-variation
    # measures the metric cap still allows.
    if "relationship" not in used_templates and len(valid_nums) >= 2:
        cv: list[tuple[float, str]] = []
        for c in picks["numerics"]:
            s = pd.to_numeric(df[c], errors="coerce")
            m = s.mean()
            sd = s.std()
            if m and sd == sd and metric_uses.get(c, 0) < 2:
                cv.append((abs(sd / m), c))
        cv.sort(reverse=True)
        # The template scatters per-group averages, so it needs a grouping
        # column - prefer one with enough distinct points to show a pattern.
        rel_group = next(
            (c for c in picks["cats"]
             if 5 <= int(df[c].nunique(dropna=True)) <= 60),
            picks["cats"][0] if picks["cats"] else None,
        )
        if len(cv) >= 2 and rel_group:
            cand = _build_from_selection("relationship", source, df,
                                         cv[0][1], rel_group, cv[1][1], period)
            if cand and cand["question"] not in seen:
                out.insert(min(2, len(out)), cand)
                seen.add(cand["question"])
    # Time data deserves time views: with a period column present, guarantee
    # the change view (diverging bars) and a per-group trend (small
    # multiples) whenever the data supports them - they replace the last
    # generic bars rather than growing the board.
    if period and valid_nums:
        t_metric = next((c for c in picks["numerics"]), None)
        if t_metric:
            if "trend" not in used_templates:
                cand = _build_from_selection("trend", source, df, t_metric,
                                             None, None, period)
                if cand and cand["question"] not in seen:
                    out.insert(min(2, len(out)), cand)
                    seen.add(cand["question"])
            if "change" not in used_templates:
                cand = _build_from_selection("change", source, df, t_metric,
                                             None, None, period)
                if cand and cand["question"] not in seen:
                    out.insert(min(3, len(out)), cand)
                    seen.add(cand["question"])
            if "trend_by" not in used_templates:
                mult_group = next(
                    (c for c in picks["cats"]
                     if 2 <= int(df[c].nunique(dropna=True)) <= 9), None)
                if mult_group:
                    cand = _build_from_selection("trend_by", source, df,
                                                 t_metric, mult_group, None,
                                                 period)
                    if cand and cand["question"] not in seen:
                        out.insert(min(4, len(out)), cand)
                        seen.add(cand["question"])
    return out[:MAX_STARTERS]


def _shape_leads(shape: dict[str, Any] | None, source: str, df: pd.DataFrame,
                 period: str | None, cats: list[str],
                 numerics: list[str]) -> list[dict[str, Any]]:
    """Shape-specific opening questions - what a good analyst would ask FIRST
    for this kind of dataset. The general starters fill in behind them."""
    if not shape:
        return []
    kind = shape.get("shape")
    num = numerics[0] if numerics else None
    leads: list[dict[str, Any]] = []

    if kind == "panel" and period and num and shape.get("panel_entity"):
        ent = shape["panel_entity"]
        if 2 <= int(df[ent].nunique(dropna=True)) <= 9:
            leads.append({
                "question": f"How does total {_lbl(num)} move across {_lbl(period)} for each {_lbl(ent)}?",
                "plan": {"source": source, "steps": [
                    {"op": "group_by", "columns": [period, ent]},
                    {"op": "aggregate", "column": num, "fn": "sum", "alias": f"total_{num}"},
                    {"op": "sort", "column": period, "dir": "asc"},
                ]},
            })
        leads.append({
            "question": f"Which {_lbl(ent)} leads in the latest {_lbl(period)}?",
            "plan": {"source": source, "steps": [
                {"op": "time_window", "column": period, "last_n": 1},
                {"op": "group_by", "columns": [ent]},
                {"op": "aggregate", "column": num, "fn": "sum", "alias": f"total_{num}"},
                {"op": "sort", "column": f"total_{num}", "dir": "desc"},
                {"op": "top_n", "n": min(10, int(df[ent].nunique(dropna=True)))},
            ]},
        })

    elif kind == "transactional" and period:
        leads.append({
            "question": f"How many records arrive per {_lbl(period)}?",
            "plan": {"source": source, "steps": [
                {"op": "group_by", "columns": [period]},
                {"op": "aggregate", "column": period, "fn": "count", "alias": "records"},
                {"op": "sort", "column": period, "dir": "asc"},
            ]},
        })
        if cats:
            leads.append({
                "question": f"How do records split across {_lbl(cats[0])}?",
                "plan": {"source": source, "steps": [
                    {"op": "group_by", "columns": [cats[0]]},
                    {"op": "aggregate", "column": cats[0], "fn": "count", "alias": "records"},
                    {"op": "sort", "column": "records", "dir": "desc"},
                ]},
            })

    elif kind == "survey":
        # Counts and shares across DIFFERENT answer columns - never averages
        # of codes.
        for cat in cats[:3]:
            leads.append({
                "question": f"How do responses split across {_lbl(cat)}?",
                "plan": {"source": source, "steps": [
                    {"op": "group_by", "columns": [cat]},
                    {"op": "aggregate", "column": cat, "fn": "count", "alias": "responses"},
                    {"op": "sort", "column": "responses", "dir": "desc"},
                ]},
            })

    return leads


def starter_questions(df: pd.DataFrame, source: str = "",
                      focus_columns: list[str] | None = None,
                      shape: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Up to MAX_STARTERS {question, plan} candidates, most interesting first.
    focus_columns (a chosen domain) restricts the measures explored; the
    grouping columns stay open so every domain can still be sliced. shape
    (from the Shape Scout) puts the right opening questions first."""
    picks = _pick_columns(df)
    period, cats, numerics = picks["period"], picks["cats"], picks["numerics"]
    if focus_columns:
        focus = {str(c) for c in focus_columns}
        focused = [n for n in numerics if n in focus]
        if focused:
            numerics = focused
    out: list[dict[str, Any]] = []
    out += _shape_leads(shape, source, df, period, cats, numerics)
    if shape and shape.get("shape") == "time_series" and period and numerics:
        # Movement IS the story: reorder so the trend leads (the general list
        # below re-adds it; dedupe keeps the first).
        num = numerics[0]
        out.append({
            "question": f"How does total {num} move across {period}?",
            "plan": {"source": source, "steps": [
                {"op": "group_by", "columns": [period]},
                {"op": "aggregate", "column": num, "fn": "sum", "alias": f"total_{num}"},
                {"op": "sort", "column": period, "dir": "asc"},
            ]},
        })

    if cats and numerics:
        cat, num = cats[0], numerics[0]
        n = min(10, int(df[cat].nunique(dropna=True)))
        out.append({
            "question": f"Which {_lbl(cat)} has the highest total {_lbl(num)}?",
            "plan": {"source": source, "steps": [
                {"op": "group_by", "columns": [cat]},
                {"op": "aggregate", "column": num, "fn": "sum", "alias": f"total_{num}"},
                {"op": "sort", "column": f"total_{num}", "dir": "desc"},
                {"op": "top_n", "n": n},
            ]},
        })
        # The lagging end matters as much as the leaders for policy work.
        if int(df[cat].nunique(dropna=True)) > 3:
            out.append({
                "question": f"Which {_lbl(cat)} has the lowest total {_lbl(num)}?",
                "plan": {"source": source, "steps": [
                    {"op": "group_by", "columns": [cat]},
                    {"op": "aggregate", "column": num, "fn": "sum", "alias": f"total_{num}"},
                    {"op": "sort", "column": f"total_{num}", "dir": "asc"},
                    {"op": "top_n", "n": min(5, n)},
                ]},
            })
        # Relationships first: how two measures move together across groups.
        if len(numerics) > 1:
            num2 = numerics[1]
            out.append({
                "question": f"How do {_lbl(num)} and {_lbl(num2)} move together across {_lbl(cat)}?",
                "plan": {"source": source, "steps": [
                    {"op": "group_by", "columns": [cat]},
                    {"op": "aggregate", "column": num, "fn": "sum", "alias": f"total_{num}"},
                    {"op": "aggregate", "column": num2, "fn": "sum", "alias": f"total_{num2}"},
                ]},
            })
        # Diversity: the average view uses the SECOND grouping column when
        # one exists, so the board is not one category's story on repeat.
        avg_cat = cats[1] if len(cats) > 1 else cats[0]
        avg_num = numerics[2] if len(numerics) > 2 else num
        out.append({
            "question": f"What is the average {_lbl(avg_num)} per {_lbl(avg_cat)}?",
            "plan": {"source": source, "steps": [
                {"op": "group_by", "columns": [avg_cat]},
                {"op": "aggregate", "column": avg_num, "fn": "mean", "alias": f"avg_{avg_num}"},
                {"op": "sort", "column": f"avg_{avg_num}", "dir": "desc"},
            ]},
        })

    if period and numerics:
        num = numerics[0]
        out.append({
            "question": f"How does total {num} move across {period}?",
            "plan": {"source": source, "steps": [
                {"op": "group_by", "columns": [period]},
                {"op": "aggregate", "column": num, "fn": "sum", "alias": f"total_{num}"},
                {"op": "sort", "column": period, "dir": "asc"},
            ]},
        })
        # The comparison view: period-over-period change (diverging bars).
        if int(df[period].nunique(dropna=True)) >= 3:
            out.append({
                "question": f"How did total {_lbl(num)} change from one {_lbl(period)} to the next?",
                "plan": {"source": source, "steps": [
                    {"op": "group_by", "columns": [period]},
                    {"op": "aggregate", "column": num, "fn": "sum", "alias": f"total_{num}"},
                    {"op": "sort", "column": period, "dir": "asc"},
                    {"op": "delta_vs_period", "column": f"total_{num}",
                     "period_column": period, "lag": 1},
                ]},
            })
        # Seasonal honesty: monthly data spanning a year+ compares each month
        # with the SAME month a year earlier, not just the month before.
        if _is_monthly(df[period]) and int(df[period].nunique(dropna=True)) >= 13:
            out.append({
                "question": f"How does each {_lbl(period)} compare with the same {_lbl(period)} a year earlier?",
                "plan": {"source": source, "steps": [
                    {"op": "group_by", "columns": [period]},
                    {"op": "aggregate", "column": num, "fn": "sum", "alias": f"total_{num}"},
                    {"op": "sort", "column": period, "dir": "asc"},
                    {"op": "delta_vs_period", "column": f"total_{num}",
                     "period_column": period, "lag": 12},
                ]},
            })

    # A second lens: how the metric splits across the OTHER grouping column.
    if len(cats) > 1 and numerics:
        cat2, num = cats[1], numerics[0]
        out.append({
            "question": f"How does total {num} split across {cat2}?",
            "plan": {"source": source, "steps": [
                {"op": "group_by", "columns": [cat2]},
                {"op": "aggregate", "column": num, "fn": "sum", "alias": f"total_{num}"},
                {"op": "sort", "column": f"total_{num}", "dir": "desc"},
            ]},
        })

    # A second measure, when the data carries one.
    if cats and len(numerics) > 1:
        cat, num2 = cats[0], numerics[1]
        out.append({
            "question": f"Which {_lbl(cat)} has the highest total {_lbl(num2)}?",
            "plan": {"source": source, "steps": [
                {"op": "group_by", "columns": [cat]},
                {"op": "aggregate", "column": num2, "fn": "sum", "alias": f"total_{num2}"},
                {"op": "sort", "column": f"total_{num2}", "dir": "desc"},
                {"op": "top_n", "n": min(10, int(df[cat].nunique(dropna=True)))},
            ]},
        })

    if cats:
        cat = cats[1] if len(cats) > 1 else cats[0]
        out.append({
            "question": f"How many rows fall under each {cat}?",
            "plan": {"source": source, "steps": [
                {"op": "group_by", "columns": [cat]},
                {"op": "aggregate", "column": cat, "fn": "count", "alias": "count"},
                {"op": "sort", "column": "count", "dir": "desc"},
            ]},
        })

    if numerics:
        num = numerics[0]
        out.append({
            "question": f"What are the overall total and average of {_lbl(num)}?",
            "plan": {"source": source, "steps": [
                {"op": "aggregate", "column": num, "fn": "sum", "alias": f"total_{num}"},
                {"op": "aggregate", "column": num, "fn": "mean", "alias": f"avg_{num}"},
            ]},
        })

    # Dedupe by question text (shape leads may overlap the general list).
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for cand in out:
        if cand["question"] not in seen:
            seen.add(cand["question"])
            unique.append(cand)
    return unique[:MAX_STARTERS]
