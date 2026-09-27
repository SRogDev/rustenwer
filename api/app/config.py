"""Application configuration via pydantic-settings.

Env vars (see .env.example):
  API_HOST, API_PORT, LOG_LEVEL, ENV,
  SUPABASE_URL, SUPABASE_JWT_SECRET  -- Phase 1, unused in Phase 0.
  RUSTENWER_DATA_DIR, TRAINING_MAX_WORKERS -- Phase 2, training execution.
  DO_TOKEN, DO_REGION, DO_GPU_SIZE, DO_SSH_KEY_IDS, DO_SSH_PRIVATE_KEY
    -- Phase 2, DigitalOcean GPU provider (credential-blocked).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_API_ROOT = Path(__file__).resolve().parent.parent  # api/


class Settings(BaseSettings):
    """Runtime settings, loaded from the environment (and an optional .env)."""

    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", populate_by_name=True
    )

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    log_level: str = "INFO"
    env: str = "dev"

    # Phase 1 — unused in Phase 0. No Supabase project exists yet, so real
    # JWT verification cannot be wired; auth is a clearly-marked stub
    # (see app/auth.py and docs/DECISIONS.md).
    supabase_url: str | None = None
    supabase_jwt_secret: str | None = None

    # Phase 2 — training execution. RUSTENWER_DATA_DIR holds the persistent
    # runtime state the repo must never track: the queue DB, run attempt
    # dirs (events.jsonl, checkpoints, exports), and the artifact store.
    data_dir: Path = Field(
        default=_API_ROOT / "data", validation_alias="RUSTENWER_DATA_DIR"
    )
    training_max_workers: int = 2
    local_rate_usd_per_hour: float = 0.02

    # Phase 2 — DigitalOcean GPU provider (code-complete, credential-blocked).
    do_token: str | None = None
    do_region: str = "nyc3"
    do_gpu_size: str = "gpu-rtx4000x1-20gb"
    do_ssh_key_ids: str = ""
    do_ssh_private_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Process-wide cached settings instance."""
    return Settings()
