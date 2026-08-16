"""Swappable LLM provider interface.

Agents talk to Claude only through this interface, so the model backend can be
replaced later (open-source, local, etc.) by adding one more implementation and
changing the factory in ``__init__``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable


class LLMProvider(ABC):
    """A minimal text + structured-JSON completion surface.

    ``on_call`` is an optional telemetry hook: implementations invoke it after
    every model call with a dict {provider, model, tokens_in, tokens_out,
    latency_ms, error?}. The app layer attaches it to feed the activity log;
    the engine itself never depends on it.
    """

    on_call: Callable[[dict[str, Any]], None] | None = None

    @abstractmethod
    def complete_text(self, system: str, prompt: str, max_tokens: int = 2048) -> str:
        """Return a plain-text completion."""

    @abstractmethod
    def complete_json(
        self, system: str, prompt: str, schema: dict[str, Any], max_tokens: int = 4096
    ) -> dict[str, Any]:
        """Return a JSON object validated against ``schema``."""

    def _emit(self, info: dict[str, Any]) -> None:
        if self.on_call is not None:
            try:
                self.on_call(info)
            except Exception:
                pass  # telemetry must never break a model call
