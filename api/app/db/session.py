from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

# NullPool: no connection is held open/reused across requests — each checkout
# opens a fresh asyncpg connection and closes it on release. Two reasons:
# (1) matches the Cloud Run target (short-lived/scale-to-zero instances,
#     `min-instances=0` — a long-lived pool has little to reuse anyway,
#     same rationale the blueprint gives for Upstash's request-based Redis);
# (2) a pooled connection binds to the asyncio event loop active when it was
#     opened, and reusing it from a DIFFERENT loop later raises "Event loop
#     is closed" — this bit hard in tests, where each `TestClient` spins its
#     own loop (see `app/services/redis_client.py`'s docstring for the same
#     failure mode on the Redis side). NullPool sidesteps it entirely rather
#     than papering over it with per-test engine teardown.
_engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
SessionLocal = async_sessionmaker(_engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
