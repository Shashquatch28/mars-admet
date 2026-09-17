"""Module 8 rate limiting — anonymous per-IP, fixed 60s window (blueprint:
"Anonymous, per-IP: 60 single-molecule predictions/minute"). Batch upload is
account-gated instead (Module 8) and not rate-limited here."""

from __future__ import annotations

import time
import warnings

import redis.asyncio as redis
from fastapi import Depends, HTTPException, Request

from app.core.config import get_settings
from app.services.redis_client import get_redis


async def enforce_predict_rate_limit(
    request: Request,
    r: redis.Redis = Depends(get_redis),
) -> None:
    """Fails OPEN if Redis is unreachable — a down cache/rate-limiter must not
    take `/predict` down with it. Local dev/tests without a running Redis
    (see docker-compose) hit this path and correctly skip rate limiting
    rather than erroring; a real deployment losing Redis degrades the same
    way rather than 500ing every anonymous request."""
    try:
        client_ip = request.client.host if request.client else "unknown"
        window = int(time.time() // 60)
        key = f"ratelimit:predict:{client_ip}:{window}"

        count = await r.incr(key)
        if count == 1:
            await r.expire(key, 60)
    except redis.RedisError as exc:
        warnings.warn(f"Rate limiter unavailable, failing open: {exc}", stacklevel=2)
        return

    limit = get_settings().rate_limit_anon_per_minute
    if count > limit:
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded: {limit}/minute per IP")
