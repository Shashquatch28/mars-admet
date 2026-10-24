from __future__ import annotations

import redis.asyncio as redis
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from mars_contracts import (
    LoginRequest,
    LoginResponse,
    MeResponse,
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
from app.deps import _session_token_from_request, get_current_user
from app.services.password_reset import (
    allow_confirm,
    allow_request,
    redeem_token,
    send_reset_if_account,
)
from app.services.rate_limit import client_ip
from app.services.redis_client import get_redis
from app.services.security import hash_password, verify_password
from app.services.sessions import create_session, delete_all_sessions_for_user, delete_session
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


@router.get("/me", response_model=MeResponse)
async def me(user: User = Depends(get_current_user)) -> MeResponse:
    """Whoami for the SPA (ADR-022): the session cookie is HttpOnly, so this is the only way the
    client can learn whether it has a session. 401 (from `get_current_user`) means it does not."""
    return MeResponse(user_id=str(user.id), email=user.email)


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
    request: Request,
    background: BackgroundTasks,
    r: redis.Redis = Depends(get_redis),
) -> None:
    """Always 202 with an empty body, at the same speed, whether or not the address has an account, and whether or not a limit
    was hit (frontend ADR-043). Everything that differs (the lookup, the token, the email) happens in a background task after
    the response has gone, so neither the body nor the timing can be used to find out which addresses have accounts."""
    if await allow_request(r, req.email, client_ip(request)):
        background.add_task(send_reset_if_account, req.email)
    return None


_BAD_RESET_TOKEN = "Invalid or expired reset token"


@router.post("/password-reset/confirm", status_code=204)
async def password_reset_confirm(
    req: PasswordResetConfirmRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
) -> None:
    """Set a new password with a single-use link token. Every way the token can be wrong (unknown, used, expired) answers the same
    400, so nothing says which. On success all of the account's sessions are ended; the caller is NOT signed in."""
    if not await allow_confirm(r, client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")
    try:
        new_hash = hash_password(req.new_password)  # before the token is used: a password that cannot be stored must not burn the link
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    user = await redeem_token(db, req.token)
    if user is None:
        raise HTTPException(status_code=400, detail=_BAD_RESET_TOKEN)
    user.password_hash = new_hash
    await db.commit()  # the password and the used token commit together
    await delete_all_sessions_for_user(r, str(user.id))
    return None
