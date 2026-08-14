"""Swappable LLM provider interface.

Agents talk to Claude only through this interface, so the model backend can be
replaced later (open-source, local, etc.) by adding one more implementation and
changing the factory in ``__init__``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """A minimal text + structured-JSON completion surface."""

    @abstractmethod
    def complete_text(self, system: str, prompt: str, max_tokens: int = 2048) -> str:
        """Return a plain-text completion."""

    @abstractmethod
    def complete_json(
        self, system: str, prompt: str, schema: dict[str, Any], max_tokens: int = 4096
    ) -> dict[str, Any]:
        """Return a JSON object validated against ``schema``."""
