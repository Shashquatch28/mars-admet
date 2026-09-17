"""Shared fixtures for the database/auth/batch integration tier.

These tests need a live Postgres + Redis (`docker compose up -d postgres
redis`) — they are the "database/auth tests" tier from the testing
philosophy, distinct from `test_predict.py`'s pure-stub unit tests. They
skip (not fail) when that infra isn't reachable, so the fast tier stays
runnable without Docker.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
import redis.asyncio as redis
from app.core.config import get_settings
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def _infra_available() -> bool:
    """Uses fully throwaway engine/client instances, never the app's shared
    `get_db`/`get_redis` singletons — this runs inside its own `asyncio.run()`
    loop at collection time, and reusing a shared async client here would
    bind its connections to a loop that's closed before any test runs
    (see `app/services/redis_client.py`'s docstring for the same pitfall)."""

    async def _check() -> bool:
        try:
            engine = create_async_engine(get_settings().database_url)
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            await engine.dispose()
        except Exception:
            return False
        try:
            r = redis.from_url(get_settings().redis_url, socket_connect_timeout=1.0)
            await r.ping()
            await r.aclose()
        except Exception:
            return False
        return True

    return asyncio.run(_check())


requires_infra = pytest.mark.skipif(
    not _infra_available(), reason="Postgres/Redis not reachable — run `docker compose up -d postgres redis`"
)


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def registered_user(client):
    """Registers + logs in a fresh user with a random email; deletes the
    account (cascade) at teardown so tests don't accumulate rows."""
    email = f"test-{uuid.uuid4().hex[:12]}@example.com"
    password = "correct-horse-battery"

    resp = client.post(
        "/auth/register", json={"email": email, "password": password, "turnstile_token": "test"}
    )
    assert resp.status_code == 201, resp.text
    user_id = resp.json()["user_id"]

    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text

    yield {"email": email, "password": password, "user_id": user_id, "client": client}

    client.request("DELETE", "/account", json={"password": password})
