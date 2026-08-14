"""Pydantic request models for the API."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StartRunRequest(BaseModel):
    dataset_id: str
    question: str = ""


class ApproveEdaRequest(BaseModel):
    comment: str = ""


class ApproveConfigRequest(BaseModel):
    model_key: str
    hyperparams: dict[str, Any] = Field(default_factory=dict)
    target: str | None = None
    features: list[str] | None = None
    time_column: str | None = None


class CompareRequest(BaseModel):
    target: str | None = None
    time_column: str | None = None
