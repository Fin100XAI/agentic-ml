"""LLM provider factory."""
from __future__ import annotations

from app.config import settings

from .base import LLMProvider
from .claude import ClaudeProvider

# One shared provider per configuration: the Anthropic client keeps an HTTP
# connection pool, so rebuilding it per request churned sockets for nothing.
_cached: LLMProvider | None = None
_cached_key: tuple[str | None, str | None] | None = None


def get_provider() -> LLMProvider | None:
    """Return a configured provider, or ``None`` when no key is set.

    Agents treat ``None`` as "run in heuristic mode" so the whole pipeline still
    works without an API key.
    """
    global _cached, _cached_key
    if not settings.llm_enabled:
        return None
    key = (settings.anthropic_api_key, settings.anthropic_model)
    if _cached is None or _cached_key != key:
        _cached = ClaudeProvider(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
        _cached_key = key
    return _cached


__all__ = ["LLMProvider", "ClaudeProvider", "get_provider"]
