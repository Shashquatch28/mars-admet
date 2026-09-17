"""Module 13 account deletion — the actual privacy lever (not a TTL).
Cascades to saved_molecules/saved_reports/batch_jobs via the DB's ON DELETE
CASCADE (see `db/models.py`), then revokes every active session."""

from __future__ import annotations

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException
from mars_contracts import DeleteAccountRequest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.session import get_db
from app.deps import get_current_user
from app.services.redis_client import get_redis
from app.services.security import verify_password
from app.services.sessions import delete_all_sessions_for_user

router = APIRouter()


@router.delete("", status_code=204)
async def delete_account(
    req: DeleteAccountRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
) -> None:
    if not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=403, detail="Incorrect password")

    await delete_all_sessions_for_user(r, str(user.id))
    await db.delete(user)
    await db.commit()
