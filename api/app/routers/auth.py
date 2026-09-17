from __future__ import annotations

import uuid

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from mars_contracts import (
    LoginRequest,
    LoginResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequestModel,
    RegisterRequest,
    RegisterResponse,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import User
from app.db.session import get_db
from app.deps import _session_token_from_request
from app.services.redis_client import get_redis
from app.services.security import (
    hash_password,
    make_password_reset_token,
    verify_password,
    verify_password_reset_token,
)
from app.services.sessions import create_session, delete_session
from app.services.turnstile import verify_turnstile

router = APIRouter()


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_days * 86_400,
    )


@router.post("/register", status_code=201, response_model=RegisterResponse)
async def register(
    req: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    if not await verify_turnstile(req.turnstile_token):
        raise HTTPException(status_code=400, detail="Turnstile verification failed")

    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(email=req.email, password_hash=hash_password(req.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return RegisterResponse(user_id=str(user.id))


@router.post("/login", response_model=LoginResponse)
async def login(
    req: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
) -> LoginResponse:
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = await create_session(r, str(user.id))
    _set_session_cookie(response, token)
    return LoginResponse(user_id=str(user.id))


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    r: redis.Redis = Depends(get_redis),
) -> None:
    token = _session_token_from_request(request)
    if token is not None:
        await delete_session(r, token)
    response.delete_cookie(get_settings().session_cookie_name)


@router.post("/password-reset/request", status_code=202)
async def password_reset_request(
    req: PasswordResetRequestModel,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Always 202, whether or not the email exists — no account enumeration.
    Real Resend delivery is not wired here (see next_steps.md); this issues
    and would email the signed token."""
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if user is not None:
        make_password_reset_token(str(user.id))  # would be emailed via Resend
    return None


@router.post("/password-reset/confirm", status_code=204)
async def password_reset_confirm(
    req: PasswordResetConfirmRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    user_id = verify_password_reset_token(req.token)
    if user_id is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user.password_hash = hash_password(req.new_password)
    await db.commit()
    return None
