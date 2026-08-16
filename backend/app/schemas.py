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
    feature_ids: list[str] | None = None  # approved engineered-feature ids


class CompareRequest(BaseModel):
    target: str | None = None
    time_column: str | None = None
    n_candidates: int | None = None  # autotune only; clamped 3-20 server-side


class AskRequest(BaseModel):
    question: str
    history: list[dict[str, str]] = Field(default_factory=list)


class PiiReviewRequest(BaseModel):
    actions: dict[str, str] = Field(default_factory=dict)  # column -> mask|drop|keep


class RemediateRequest(BaseModel):
    accepted_ids: list[str] = Field(default_factory=list)
    skip: bool = False
