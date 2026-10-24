"""Settings loaded from environment (`.env` locally, platform env vars in
prod) — see `.env.example` for every key's meaning and default."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

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

    cors_allow_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        description="Comma-separated browser origins allowed to make credentialed requests (the SPA's "
        "origin). Defaults are the Vite dev server. Set the deployed frontend origin in prod; a bare '*' "
        "is accepted but disables credentials, because browsers reject '*' with cookies.",
    )

    static_dir: str = Field(
        default="",
        description="Directory holding the built frontend (Vite `dist`). When set and it exists, the API "
        "serves it at `/` with an index.html fallback for client routes (ADR-025). Empty in development, "
        "where Vite serves the frontend. The Docker image sets it.",
    )

    session_ttl_days: int = Field(default=7)
    session_cookie_name: str = Field(default="mars_session")
    session_cookie_secure: bool = Field(default=False)
    password_hash_scheme: str = Field(default="bcrypt")

    cloudflare_turnstile_secret_key: str = Field(default="")
    resend_api_key: str = Field(default="")

    rate_limit_anon_per_minute: int = Field(default=60)
    rate_limit_depict_per_minute: int = Field(
        default=240,
        description="Structure drawings per minute per IP. Separate from the prediction limit: a Library or a Compare page draws "
        "several molecules at once, a drawing is cheap, and the cache answers repeats.",
    )
    depiction_cache_ttl_seconds: int = Field(
        default=7 * 24 * 3600,
        description="How long a drawing is kept. A drawing is a pure function of the molecule and DEPICTION_VERSION, so this is "
        "only about memory, not freshness.",
    )
    rate_limit_name_per_minute: int = Field(
        default=120,
        description="Name lookups per minute per IP (`POST /name`, frontend ADR-043), counted whether or not the cache answers. "
        "Its own counter, so naming a page of molecules never spends the prediction budget.",
    )
    name_lookup_enabled: bool = Field(
        default=True,
        description="Master switch for asking the name source anything. False answers every lookup as unavailable, in words, "
        "without a network call: the way to switch the external lookup off on a deployment that must not send a key out.",
    )
    name_lookup_base_url: str = Field(
        default="https://pubchem.ncbi.nlm.nih.gov/rest/pug",
        description="PubChem PUG REST root. Only the InChIKey is ever appended to it.",
    )
    name_lookup_timeout_seconds: float = Field(
        default=4.0,
        description="Longest MARS waits for one request to the name source. A lookup makes at most two, in sequence, so a slow "
        "source costs one lookup at most about twice this and never touches /predict.",
    )
    name_lookup_max_per_second: float = Field(
        default=3.0,
        description="Requests per second this process may send the name source (PubChem asks for no more than 5). Each lookup "
        "makes up to two; a lookup that would have to wait longer than its time budget is answered as busy instead.",
    )
    name_breaker_failures: int = Field(
        default=5, description="Consecutive failed requests to the name source after which MARS stops asking for a while"
    )
    name_breaker_open_seconds: float = Field(
        default=60.0, description="How long MARS stops asking the name source after the breaker opens, then it tries once"
    )
    name_cache_ttl_seconds: int = Field(
        default=7 * 24 * 3600, description="How long a found name is kept; the source can rename a record, so it is not forever"
    )
    name_not_found_ttl_seconds: int = Field(
        default=24 * 3600, description="How long 'the source has no record' is kept; compounds are added to PubChem every day"
    )
    name_max_synonyms: int = Field(default=5, description="Synonyms returned with a name")
    trusted_proxy_hops: int = Field(
        default=0,
        description="How many proxies in front of the API append to X-Forwarded-For. 0 (default) means the "
        "socket peer is the client. N > 0 means the client is the N-th entry from the right of the header, "
        "the only entries an attacker cannot forge. Behind Cloud Run set 1, then verify after deploy.",
    )
    max_concurrent_predictions: int = Field(
        default=0,
        description="Cap on predictions running at once. 0 (default) means one per CPU available to this "
        "process. Cloud Run does not always report its vCPU limit to the process, so set this to the "
        "service's vCPU count there.",
    )
    sentry_dsn: str = Field(default="", description="Sentry project DSN. Empty (default) turns error reporting off.")
    sentry_environment: str = Field(default="development", description="Shown on every event, e.g. 'production'.")
    sentry_release: str = Field(default="", description="Release label, e.g. the git commit the image was built from.")
    sentry_traces_sample_rate: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Share of requests traced for performance. 0 spends the free quota on errors."
    )
    batch_size_cap: int = Field(default=50_000)
    batch_interactive_threshold: int = Field(
        default=100,
        description="Largest batch answered inside the upload request. Larger files are queued and report "
        "progress. A real prediction costs about 0.2-0.5 s, so 100 rows is under a minute.",
    )
    batch_upload_retention_hours: int = Field(default=24)

    model_version: str = Field(default="v0.2.0-dev")  # bump when the response shape or routing changes: it is part of the 48 h cache key
    model_artifact_dir: str = Field(default="./ml/artifacts")
    ml_data_cache_dir: str = Field(default="./ml/data/cache")
    prediction_cache_ttl_seconds: int = Field(default=172_800)

    kermt_service_url: str = Field(
        default="",
        description="Base URL of the KERMT inference service (ml/serve/kermt_service). Empty (default) turns KERMT "
        "serving off: every endpoint is served by XGBoost, whatever ml/serve/routing.json says.",
    )
    kermt_service_token: str = Field(default="", description="Sent as X-Kermt-Token; must match the service's KERMT_TOKEN.")
    kermt_timeout_seconds: float = Field(
        default=30.0,
        description="How long one prediction waits for the KERMT service before those endpoints fall back to XGBoost.",
    )
    kermt_routing_path: str = Field(default="", description="Override for ml/serve/routing.json (empty = the packaged table).")

    s3_endpoint_url: str = Field(default="http://localhost:9000")
    s3_access_key_id: str = Field(default="mars_minio")
    s3_secret_access_key: str = Field(default="mars_minio_password")
    s3_bucket_uploads: str = Field(default="mars-batch-uploads")
    s3_region: str = Field(default="us-east-1", description="Cloudflare R2 wants 'auto'; MinIO ignores it.")

    # --- Batch jobs: where their bytes live and what runs them (ship checklist C8) ---
    batch_blob_backend: Literal["redis", "s3"] = Field(
        default="redis",
        description="Where job input, slice results and final results are stored. 'redis' for development; "
        "'s3' (Cloudflare R2 in production, MinIO locally) for anything that must hold a large batch.",
    )
    batch_queue_backend: Literal["local", "cloud_tasks"] = Field(
        default="local",
        description="'local' runs jobs inside this process. 'cloud_tasks' enqueues each slice as a Cloud Task "
        "that calls this service's /api/internal/batch/run endpoint.",
    )
    batch_slice_rows: int = Field(default=250, ge=1, description="Molecules predicted per worker invocation.")
    batch_worker_secret: str = Field(
        default="", description="Shared secret Cloud Tasks sends to the worker endpoint. Empty disables the endpoint."
    )
    batch_task_deadline_seconds: int = Field(
        default=900, ge=15, le=1800, description="How long Cloud Tasks waits for one slice (HTTP targets: 15 s to 30 min)."
    )
    batch_task_max_attempts: int = Field(
        default=5, ge=1, description="Must equal the queue's max attempts; after the last one the job is marked failed."
    )
    gcp_project_id: str = Field(default="")
    gcp_region: str = Field(default="us-central1")
    cloud_tasks_queue: str = Field(default="mars-batch")
    worker_base_url: str = Field(default="", description="This service's public URL, e.g. https://mars-api-xyz.run.app")


@lru_cache
def get_settings() -> Settings:
    return Settings()
