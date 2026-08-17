"""Boot-time LLM reachability, surfaced via /api/health.

Heuristic mode is a valid state - it just must be a VISIBLE state. The
startup ping records whether the configured provider actually answers;
the UI shows a banner when it does not.
"""
from __future__ import annotations

from datetime import datetime, timezone

status: dict = {"ok": None, "error": None, "checked_at": None}


def record(ok: bool, error: str | None = None) -> None:
    status["ok"] = ok
    status["error"] = (error or "")[:300] or None
    status["checked_at"] = datetime.now(timezone.utc).isoformat()
