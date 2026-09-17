from __future__ import annotations

import uuid

import redis.asyncio as redis
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import User
from app.db.session import get_db
from app.services.redis_client import get_redis
from app.services.sessions import get_session_user_id


def _session_token_from_request(request: Request) -> str | None:
    return request.cookies.get(get_settings().session_cookie_name)


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
) -> User:
    """Resolve the session cookie -> Redis -> user_id -> User row.

    Raises 401 if there is no cookie, the session has expired/been revoked,
    or the user row no longer exists.
    """
    token = _session_token_from_request(request)
    if token is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = await get_session_user_id(r, token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
