"""`GET /generations` (ADR-026) — which model generation this deployment serves.

Deliberately minimal: one setting, no registry, no cache-key change. `active` is the
configured `model_version` (the same string `/predict` stamps once a real model has
served a row); `available` is `[active]` until a second generation exists. It is not on
`/health`, which stays a liveness probe that depends on nothing. No account needed."""

from __future__ import annotations

from fastapi import APIRouter
from mars_contracts import GenerationsResponse

from app.core.config import get_settings

router = APIRouter()


@router.get("/generations", response_model=GenerationsResponse)
def generations() -> GenerationsResponse:
    active = get_settings().model_version
    return GenerationsResponse(active=active, available=[active])
