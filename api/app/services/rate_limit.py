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


def client_ip(request: Request) -> str:
    """The address the rate limiter counts against.

    By default the socket peer. Behind a proxy that peer is the proxy, so every visitor would
    share one bucket. With `TRUSTED_PROXY_HOPS=N` the client is the N-th entry from the right
    of `X-Forwarded-For`: the entries our own proxies appended. Anything to the left was sent
    by the client and can be forged, so it is never read. A header with fewer entries than
    hops means the request did not come through the proxy; fall back to the peer."""
    peer = request.client.host if request.client else "unknown"
    hops = get_settings().trusted_proxy_hops
    if hops <= 0:
        return peer
    forwarded = [part.strip() for part in request.headers.get("x-forwarded-for", "").split(",") if part.strip()]
    if len(forwarded) < hops:
        return peer
    return forwarded[-hops]


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
        window = int(time.time() // 60)
        key = f"ratelimit:predict:{client_ip(request)}:{window}"

        count = await r.incr(key)
        if count == 1:
            await r.expire(key, 60)
    except redis.RedisError as exc:
        warnings.warn(f"Rate limiter unavailable, failing open: {exc}", stacklevel=2)
        return

    limit = get_settings().rate_limit_anon_per_minute
    if count > limit:
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded: {limit}/minute per IP")
