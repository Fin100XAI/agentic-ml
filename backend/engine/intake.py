"""Intake routing: match a newly arrived file to a project's standing rules.

A rule says "files shaped like model X's training data should be scored /
drift-checked / retrained". Routing is deterministic column matching - the
librarian's normalization, no LLM. Nothing executes without human approval;
routing only files the arrival into the inbox.
"""
from __future__ import annotations

from typing import Any

from .librarian import _normalize

MIN_COVERAGE = 0.9  # a rule needs 90% of its required columns present


def route_upload(columns: list[str], rules: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Best-matching rule for an uploaded file's columns, or None.

    Each rule dict needs `id` and `required_columns` (normalized names).
    Returns {rule_id, coverage, missing} for the highest-coverage match
    at or above MIN_COVERAGE.
    """
    have = {_normalize(c) for c in columns}
    best: dict[str, Any] | None = None
    for rule in rules:
        required = [c for c in rule.get("required_columns") or [] if c]
        if not required:
            continue
        hit = [c for c in required if c in have]
        coverage = len(hit) / len(required)
        if coverage >= MIN_COVERAGE and (best is None or coverage > best["coverage"]):
            best = {
                "rule_id": rule["id"],
                "coverage": round(coverage, 3),
                "missing": [c for c in required if c not in have],
            }
    return best


def cadence_overdue(cadence: str, last_iso: str | None, now_iso: str) -> bool:
    """True when a weekly/monthly rule has not fired within its window."""
    days = {"weekly": 7, "monthly": 30}.get(cadence)
    if not days or not last_iso:
        return False
    from datetime import datetime

    try:
        last = datetime.fromisoformat(last_iso.replace("Z", "+00:00"))
        now = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
    except ValueError:
        return False
    return (now - last).days > days
