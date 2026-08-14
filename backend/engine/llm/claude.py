"""Claude (Anthropic) implementation of ``LLMProvider``.

Uses the official ``anthropic`` SDK. Structured output is produced with
``output_config.format`` (JSON schema) so agent responses parse deterministically.
"""
from __future__ import annotations

import json
from typing import Any

import anthropic

from .base import LLMProvider


class ClaudeProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def complete_text(self, system: str, prompt: str, max_tokens: int = 2048) -> str:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError("Claude declined the request.")
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    def complete_json(
        self, system: str, prompt: str, schema: dict[str, Any], max_tokens: int = 4096
    ) -> dict[str, Any]:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError("Claude declined the request.")
        text = next(b.text for b in resp.content if b.type == "text")
        return json.loads(text)
