"""Settings loaded from environment (`.env` locally, platform env vars in
prod) — see `.env.example` for every key's meaning and default."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(default="postgresql+asyncpg://mars:mars_dev_password@localhost:55432/mars_dev")
    # ^ asyncpg driver, NOT the sync psycopg2 default — SQLAlchemy's async
    # engine needs the +asyncpg suffix explicitly or it tries to import
    # psycopg2 (not installed, and wrong API for `AsyncSession` regardless).
    redis_url: str = Field(default="redis://localhost:6379/0")
    secret_key: str = Field(
        default="mars-dev-secret-change-me",
        description="Signs password-reset tokens (itsdangerous). MUST be overridden in prod via env var.",
    )

    session_ttl_days: int = Field(default=7)
    session_cookie_name: str = Field(default="mars_session")
    session_cookie_secure: bool = Field(default=False)
    password_hash_scheme: str = Field(default="bcrypt")

    cloudflare_turnstile_secret_key: str = Field(default="")
    resend_api_key: str = Field(default="")

    rate_limit_anon_per_minute: int = Field(default=60)
    batch_size_cap: int = Field(default=50_000)
    batch_interactive_threshold: int = Field(default=1_000)
    batch_upload_retention_hours: int = Field(default=24)

    model_version: str = Field(default="v0.1.0-dev")
    model_artifact_dir: str = Field(default="./ml/artifacts")
    ml_data_cache_dir: str = Field(default="./ml/data/cache")
    prediction_cache_ttl_seconds: int = Field(default=172_800)

    s3_endpoint_url: str = Field(default="http://localhost:9000")
    s3_access_key_id: str = Field(default="mars_minio")
    s3_secret_access_key: str = Field(default="mars_minio_password")
    s3_bucket_uploads: str = Field(default="mars-batch-uploads")


@lru_cache
def get_settings() -> Settings:
    return Settings()
