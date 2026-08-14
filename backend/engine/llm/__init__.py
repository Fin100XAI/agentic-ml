"""LLM provider factory."""
from __future__ import annotations

from app.config import settings

from .base import LLMProvider
from .claude import ClaudeProvider


def get_provider() -> LLMProvider | None:
    """Return a configured provider, or ``None`` when no key is set.

    Agents treat ``None`` as "run in heuristic mode" so the whole pipeline still
    works without an API key.
    """
    if not settings.llm_enabled:
        return None
    return ClaudeProvider(api_key=settings.anthropic_api_key, model=settings.anthropic_model)


__all__ = ["LLMProvider", "ClaudeProvider", "get_provider"]
