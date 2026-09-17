from __future__ import annotations

import redis.asyncio as redis

from app.core.config import get_settings


def get_redis() -> redis.Redis:
    """Deliberately NOT cached/singleton: redis-py's async connection pool
    binds its sockets to whichever asyncio event loop is active when a
    connection is first opened, and this dependency is called from
    different event loops across the app's lifetime (each test's
    `TestClient` spins its own loop; Cloud Run can recycle the process's
    loop between cold starts too). A cached client would carry dead
    connections across loop boundaries and raise "Event loop is closed" on
    the next command. This matches the blueprint's own Upstash/serverless
    Redis model anyway — "sub-millisecond and independent of whether the
    Cloud Run backend instance is warm or cold" already assumes frequent
    reconnects, not a long-lived pooled connection.

    Short connect timeout: rate limiting and prediction caching both fail
    open when Redis is unreachable (see their own docstrings) — a slow
    timeout there would make every /predict call pay that latency instead
    of degrading fast.
    """
    return redis.from_url(get_settings().redis_url, decode_responses=True, socket_connect_timeout=1.0)
