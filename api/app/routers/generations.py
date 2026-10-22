"""`GET /generations` (ADR-026) — which model generation this deployment serves.

Deliberately minimal: no registry, no cache-key change. `active` is the string `/predict`
stamps once a real model has served a row: the configured `model_version`, plus the
`+kermt.<routing digest>` suffix when KERMT serving is on, so the top bar and a result
always name the same version. `available` is `[active]` until a second generation exists;
`kermt_endpoints` lists the endpoints routed to KERMT (empty when it is off). It is not on
`/health`, which stays a liveness probe that depends on nothing. No account needed."""

from __future__ import annotations

from fastapi import APIRouter
from mars_contracts import GenerationsResponse

from app.services.prediction_service import kermt_endpoints, serving_version

router = APIRouter()


@router.get("/generations", response_model=GenerationsResponse)
def generations() -> GenerationsResponse:
    active = serving_version()
    return GenerationsResponse(active=active, available=[active], kermt_endpoints=kermt_endpoints())
