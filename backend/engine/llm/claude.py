"""Claude (Anthropic) implementation of ``LLMProvider``.

Uses the official ``anthropic`` SDK. Structured output is produced with
``output_config.format`` (JSON schema) so agent responses parse deterministically.
"""
from __future__ import annotations

import json
import time
from typing import Any

import anthropic

from .base import LLMProvider


def _strict(node: Any) -> Any:
    """Every object in a response schema must forbid extra properties.

    The API rejects an object schema that does not say so, with a 400 that
    an agent's ``except`` clause then swallows into a silent fallback - the
    agent looks like it ran and chose the rule-based answer. Enforcing it
    here means a new agent cannot reintroduce that failure by forgetting a
    line, which is exactly how the column interpreter shipped dead.
    """
    if isinstance(node, dict):
        out = {k: _strict(v) for k, v in node.items()}
        if out.get("type") == "object":
            out["additionalProperties"] = False
        return out
    if isinstance(node, list):
        return [_strict(v) for v in node]
    return node


class ClaudeProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        # Explicit timeout: the SDK default (10 minutes) would let one hung
        # request freeze an agent call; heuristic fallbacks exist for a reason.
        self._client = anthropic.Anthropic(api_key=api_key, timeout=120.0, max_retries=2)
        self._model = model

    def _create(self, **kwargs: Any):
        """One instrumented call: telemetry fires on success and on failure."""
        started = time.time()
        try:
            resp = self._client.messages.create(model=self._model, **kwargs)
        except Exception as exc:
            self._emit({
                "provider": "anthropic", "model": self._model,
                "tokens_in": None, "tokens_out": None,
                "latency_ms": int((time.time() - started) * 1000),
                "error": str(exc)[:300],
            })
            raise
        usage = getattr(resp, "usage", None)
        self._emit({
            "provider": "anthropic", "model": self._model,
            "tokens_in": getattr(usage, "input_tokens", None),
            "tokens_out": getattr(usage, "output_tokens", None),
            "latency_ms": int((time.time() - started) * 1000),
        })
        if resp.stop_reason == "refusal":
            raise RuntimeError("Claude declined the request.")
        return resp

    def complete_text(self, system: str, prompt: str, max_tokens: int = 2048) -> str:
        resp = self._create(
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    def complete_json(
        self, system: str, prompt: str, schema: dict[str, Any], max_tokens: int = 4096
    ) -> dict[str, Any]:
        resp = self._create(
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema",
                                      "schema": _strict(schema)}},
        )
        text = next(b.text for b in resp.content if b.type == "text")
        return json.loads(text)
