"""Module 13 session store — server-side, Redis-backed, opaque tokens."""

from __future__ import annotations

import redis.asyncio as redis

from app.core.config import get_settings
from app.services.security import new_session_token, session_redis_key


async def create_session(r: redis.Redis, user_id: str) -> str:
    token = new_session_token()
    ttl_seconds = get_settings().session_ttl_days * 86_400
    await r.set(session_redis_key(token), user_id, ex=ttl_seconds)
    return token


async def get_session_user_id(r: redis.Redis, token: str) -> str | None:
    """Look up the session and refresh its sliding TTL on access."""
    key = session_redis_key(token)
    user_id = await r.get(key)
    if user_id is not None:
        ttl_seconds = get_settings().session_ttl_days * 86_400
        await r.expire(key, ttl_seconds)
    return user_id


async def delete_session(r: redis.Redis, token: str) -> None:
    await r.delete(session_redis_key(token))


async def delete_all_sessions_for_user(r: redis.Redis, user_id: str) -> None:
    """Best-effort revoke-all (used on account deletion). Scans rather than
    KEYS to avoid blocking Redis on a large keyspace."""
    async for key in r.scan_iter(match="session:*"):
        stored_user_id = await r.get(key)
        if stored_user_id == user_id:
            await r.delete(key)
