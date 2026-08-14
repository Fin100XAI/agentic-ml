"""Model plugin interface and registry.

Every ML model in the catalog is one ``ModelPlugin``. The plugin's
``param_schema`` drives the UI hyperparameter form; ``run`` executes end-to-end
(preprocess -> fit -> evaluate) and returns metrics + chart-ready artifacts.

Adding a model = subclass ModelPlugin + @register.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class ParamSpec:
    """One hyperparameter, described richly enough to auto-render a form field."""

    name: str
    label: str
    type: str  # "int" | "float" | "select" | "bool"
    default: Any
    description: str = ""
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "label": self.label,
            "type": self.type,
            "default": self.default,
            "description": self.description,
        }
        if self.min is not None:
            d["min"] = self.min
        if self.max is not None:
            d["max"] = self.max
        if self.step is not None:
            d["step"] = self.step
        if self.options:
            d["options"] = self.options
        return d


class ModelPlugin(ABC):
    """A self-describing, runnable ML model."""

    key: str  # unique, e.g. "logistic_regression"
    name: str  # display name
    use_case: str  # "classification" | "clustering" | "forecasting"
    description: str  # shown in UI + given to the recommendation agent
    strengths: str  # when this model shines (for the agent's reasoning)

    @abstractmethod
    def param_schema(self) -> list[ParamSpec]:
        ...

    def default_hyperparams(self) -> dict[str, Any]:
        return {p.name: p.default for p in self.param_schema()}

    def coerce_hyperparams(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Merge user values over defaults, coercing types per the schema."""
        out = self.default_hyperparams()
        specs = {p.name: p for p in self.param_schema()}
        for k, v in (raw or {}).items():
            if k not in specs or v is None:
                continue
            spec = specs[k]
            try:
                if spec.type == "int":
                    out[k] = int(v)
                elif spec.type == "float":
                    out[k] = float(v)
                elif spec.type == "bool":
                    out[k] = bool(v)
                else:
                    out[k] = v
            except (TypeError, ValueError):
                pass  # keep the default on bad input
        return out

    @abstractmethod
    def run(
        self,
        df: pd.DataFrame,
        hyperparams: dict[str, Any],
        target: str | None = None,
        features: list[str] | None = None,
        time_column: str | None = None,
    ) -> dict[str, Any]:
        """Execute the model end-to-end.

        Returns ``{"metrics": {...}, "artifacts": {...}}`` where artifacts are
        chart-ready structures (confusion matrix, cluster scatter, forecast
        series, feature importances, ...).
        """

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "use_case": self.use_case,
            "description": self.description,
            "strengths": self.strengths,
            "param_schema": [p.to_dict() for p in self.param_schema()],
        }


_REGISTRY: dict[str, ModelPlugin] = {}


def register(cls: type[ModelPlugin]) -> type[ModelPlugin]:
    instance = cls()
    _REGISTRY[instance.key] = instance
    return cls


def get_model(key: str) -> ModelPlugin:
    if key not in _REGISTRY:
        raise KeyError(f"Unknown model: {key}")
    return _REGISTRY[key]


def all_models() -> list[ModelPlugin]:
    return list(_REGISTRY.values())


def models_for_use_case(use_case: str) -> list[ModelPlugin]:
    return [m for m in _REGISTRY.values() if m.use_case == use_case]
