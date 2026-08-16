"""Feeds engine events into the unified activity log.

The engine stays pure: the orchestrator exposes an ``on_event`` hook and the
LLM provider an ``on_call`` hook; this module attaches both to the store.
Run/dataset context for provider calls travels via contextvars because the
provider has no knowledge of runs.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from app.store import store
from engine.llm import get_provider
from engine.orchestrator import Orchestrator, Run

current_run_id: ContextVar[str | None] = ContextVar("current_run_id", default=None)
current_dataset_id: ContextVar[str | None] = ContextVar("current_dataset_id", default=None)


def set_run_context(run: Run) -> None:
    current_run_id.set(run.id)
    current_dataset_id.set(run.dataset_id)


def _on_llm_call(info: dict[str, Any]) -> None:
    store.log_event(
        "llm-provider", "agent_call",
        run_id=current_run_id.get(),
        dataset_id=current_dataset_id.get(),
        provider=info.get("provider"), model=info.get("model"),
        tokens_in=info.get("tokens_in"), tokens_out=info.get("tokens_out"),
        latency_ms=info.get("latency_ms"), mode="llm",
        payload={"error": info["error"]} if info.get("error") else None,
    )


def _on_orchestrator_event(run: Run, event: dict[str, Any]) -> None:
    store.log_event(
        event.get("actor", "system"), event.get("event_type", "agent_call"),
        run_id=run.id, dataset_id=run.dataset_id,
        mode=event.get("mode"), latency_ms=event.get("latency_ms"),
        payload=event.get("payload"),
    )


def instrumented_provider():
    provider = get_provider()
    if provider is not None:
        provider.on_call = _on_llm_call
    return provider


def _on_artifact(run: Run, df, transform_type: str, params: dict[str, Any]) -> str:
    """Materialize a derived artifact for a run-time transformation."""
    ds = store.datasets.get(run.dataset_id)
    parent = run.artifact_id or (ds.artifact_id if ds else None)
    art = store.add_derived_artifact(
        df, [parent] if parent else [], transform_type, params,
        project_id=ds.project_id if ds else None,
    )
    return art.id


def instrumented_orchestrator() -> Orchestrator:
    orch = Orchestrator(instrumented_provider())
    orch.on_event = _on_orchestrator_event
    orch.on_artifact = _on_artifact
    return orch
