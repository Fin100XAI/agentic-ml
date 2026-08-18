"""Deterministic plan-vs-plan diff for follow-up questions.

When the planner modifies a prior plan, the user must see EXACTLY what
changed - especially anything that was silently dropped (the classic
wrong-answer risk: a follow-up that loses a filter). The diff is computed
here in Python from the two plans; the LLM has no say in it.
"""
from __future__ import annotations

from typing import Any


def _phrase(step: dict[str, Any]) -> str:
    op = step.get("op")
    if op == "filter":
        operator = step.get("operator")
        if operator in ("is_null", "not_null"):
            return f"filter: {step.get('column')} {'is empty' if operator == 'is_null' else 'is filled in'}"
        return f"filter: {step.get('column')} {operator} {step.get('value')}"
    if op == "time_window":
        if step.get("last_n"):
            return f"time window: last {step['last_n']} periods of {step.get('column')}"
        return f"time window: {step.get('column')} from {step.get('start') or 'start'} to {step.get('end') or 'end'}"
    if op == "derive":
        return f"derived value: {step.get('name')} ({step.get('kind')} of {step.get('left')} and {step.get('right')})"
    if op == "group_by":
        return f"grouping: by {', '.join(step.get('columns', []))}"
    if op == "aggregate":
        return f"calculation: {step.get('fn')} of {step.get('column')}"
    if op == "sort":
        return f"sort: by {step.get('column')}, {'lowest' if step.get('dir') == 'asc' else 'highest'} first"
    if op == "top_n":
        return f"row limit: first {step.get('n')} rows"
    if op == "pivot":
        return f"pivot: {step.get('index')} by {step.get('columns')}"
    if op == "delta_vs_period":
        return f"change vs {step.get('lag', 1)} period(s) earlier in {step.get('column')}"
    return str(op)


def _steps(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(s) for s in plan.get("steps", [])]


def diff_plans(prior: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """-> {added, removed, changed, unchanged_count}. Steps are matched by
    exact content; a same-type removal + addition pair is shown as changed."""
    prior_steps = _steps(prior)
    new_steps = _steps(new)

    remaining_new = list(new_steps)
    unchanged = 0
    removed_raw: list[dict[str, Any]] = []
    for s in prior_steps:
        if s in remaining_new:
            remaining_new.remove(s)
            unchanged += 1
        else:
            removed_raw.append(s)
    added_raw = remaining_new

    changed: list[str] = []
    still_removed: list[dict[str, Any]] = []
    for s in removed_raw:
        # Pair with an added step of the same op (first match) -> "changed".
        mate = next((a for a in added_raw if a.get("op") == s.get("op")), None)
        if mate is not None:
            added_raw.remove(mate)
            changed.append(f"{_phrase(s)}  ->  {_phrase(mate)}")
        else:
            still_removed.append(s)

    return {
        "added": [_phrase(s) for s in added_raw],
        "removed": [_phrase(s) for s in still_removed],
        "changed": changed,
        "unchanged_count": unchanged,
    }
