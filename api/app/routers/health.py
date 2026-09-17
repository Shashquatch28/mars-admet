"""Module 10 health checks — liveness vs. readiness, kept deliberately
separate. `/health` (liveness: "is the process up") must NOT depend on
Postgres/Redis — it's what the CI smoke-predict job and any future Cloud Run
health check hit, and both may run without those services present.
`/health/ready` (readiness: "can this instance actually serve traffic")
checks real connectivity to both, for use as a deploy/rollout gate."""

from __future__ import annotations

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.redis_client import get_redis

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(
    response: Response,
    db: AsyncSession = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
):
    checks = {"database": False, "redis": False}

    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        pass

    try:
        await r.ping()
        checks["redis"] = True
    except Exception:
        pass

    ready = all(checks.values())
    response.status_code = 200 if ready else 503
    return {"status": "ready" if ready else "not_ready", "checks": checks}
