"""FastAPI application entry point."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_activity import router as activity_router
from app.api.routes_datasets import router as datasets_router
from app.api.routes_intake import router as intake_router
from app.api.routes_projects import router as projects_router
from app.api.routes_registry import router as registry_router
from app.api.routes_runs import router as runs_router
from app.config import settings

app = FastAPI(title="Agentic ML Workbench", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects_router, prefix="/api")
app.include_router(registry_router, prefix="/api")
app.include_router(datasets_router, prefix="/api")
app.include_router(runs_router, prefix="/api")
app.include_router(activity_router, prefix="/api")
app.include_router(intake_router, prefix="/api")


@app.on_event("startup")
def check_llm_reachable() -> None:
    """One minimal provider ping at boot. Failure never crashes the app -
    it logs a prominent error event and flips the health flag the UI
    watches, so heuristic mode is a visible state, not a silent one."""
    if not settings.llm_enabled:
        return
    from app import llm_status
    from app.store import store
    from app.telemetry import instrumented_provider

    provider = instrumented_provider()
    try:
        provider.complete_text("Reply with the single word OK.", "ping", max_tokens=8)
        llm_status.record(True)
    except Exception as exc:
        llm_status.record(False, str(exc))
        store.log_event(
            "llm-provider", "error",
            payload={"warning": "LLM unreachable at startup - all agents will run "
                                "in heuristic mode until the provider recovers.",
                     "model": settings.anthropic_model, "error": str(exc)[:300]},
        )


@app.get("/api/health")
def health() -> dict:
    from app import llm_status

    return {
        "status": "ok",
        "llm_enabled": settings.llm_enabled,
        "model": settings.anthropic_model,
        "llm_ok": llm_status.status["ok"],
        "llm_error": llm_status.status["error"],
    }
