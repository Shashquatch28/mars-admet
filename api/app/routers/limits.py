"""`GET /limits` (frontend ADR-034 item 8) - the deployed policy numbers, read from the settings the service
enforces, so the UI never states a cap, a threshold or a retention period of its own. Anonymous, like
`/generations`; it reads configuration only and depends on nothing else."""

from __future__ import annotations

from fastapi import APIRouter
from mars_contracts import LimitsResponse

from app.core.config import get_settings

router = APIRouter()


@router.get("/limits", response_model=LimitsResponse)
def limits() -> LimitsResponse:
    s = get_settings()
    return LimitsResponse(
        batch_size_cap=s.batch_size_cap,
        batch_interactive_threshold=s.batch_interactive_threshold,
        batch_result_retention_hours=s.batch_upload_retention_hours,
        anon_predict_rate_per_minute=s.rate_limit_anon_per_minute,
        password_reset_ttl_minutes=s.password_reset_ttl_minutes,
    )
