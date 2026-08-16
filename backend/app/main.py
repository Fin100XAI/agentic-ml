"""FastAPI application entry point."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_activity import router as activity_router
from app.api.routes_datasets import router as datasets_router
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


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "llm_enabled": settings.llm_enabled, "model": settings.anthropic_model}
