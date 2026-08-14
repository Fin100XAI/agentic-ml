"""Model catalog: importing the modules registers all plugins."""
from . import classification, clustering, forecasting  # noqa: F401
from .base import ModelPlugin, all_models, get_model, models_for_use_case

__all__ = ["ModelPlugin", "all_models", "get_model", "models_for_use_case"]
