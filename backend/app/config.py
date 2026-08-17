"""Application settings, loaded from environment / .env."""
from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    # Override with LLM_MODEL (or ANTHROPIC_MODEL) in the environment / .env.
    anthropic_model: str = Field(
        "claude-opus-5",
        validation_alias=AliasChoices("LLM_MODEL", "ANTHROPIC_MODEL", "anthropic_model"),
    )
    frontend_origin: str = "http://localhost:5173"

    @property
    def llm_enabled(self) -> bool:
        """True when a Claude key is configured; otherwise agents use heuristics."""
        return bool(self.anthropic_api_key.strip())


settings = Settings()
