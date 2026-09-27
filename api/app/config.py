"""Application configuration via pydantic-settings.

Env vars (see .env.example):
  API_HOST, API_PORT, LOG_LEVEL, ENV,
  SUPABASE_URL, SUPABASE_JWT_SECRET  -- Phase 1, unused in Phase 0.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings, loaded from the environment (and an optional .env)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    log_level: str = "INFO"
    env: str = "dev"

    # Phase 1 — unused in Phase 0. No Supabase project exists yet, so real
    # JWT verification cannot be wired; auth is a clearly-marked stub
    # (see app/auth.py and docs/DECISIONS.md).
    supabase_url: str | None = None
    supabase_jwt_secret: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Process-wide cached settings instance."""
    return Settings()
