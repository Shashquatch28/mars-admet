"""Password reset (frontend ADR-043): single-use, short-lived tokens, stored hashed.

* The raw token is 32 random bytes (`secrets.token_urlsafe`). Only its SHA-256 is stored, so a copy of the database cannot
  be turned into a working reset link. The raw token exists in the email and nowhere else.
* A token works once and for `PASSWORD_RESET_TTL_MINUTES`. Issuing a new one retires the user's earlier unused tokens, and a
  successful reset retires all of them.
* The link puts the token in the URL fragment (`/reset-password#token=...`), which a browser never sends to a server, so it
  is not in access logs or a Referer header.
* What the request route answers does not depend on whether the address has an account, and neither does when it answers:
  the lookup, the token and the email all happen in a background task after the 202 has been sent.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
import uuid
from datetime import datetime, timedelta

import redis.asyncio as redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import PasswordResetToken, User
from app.db.session import SessionLocal
from app.services.batch_runner import now_naive_utc
from app.services.email_sender import EmailMessage, EmailSender, get_email_sender

logger = logging.getLogger(__name__)

SUBJECT = "Reset your MARS password"


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def new_token() -> tuple[str, str]:
    """(raw token, its stored hash)."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def reset_link(raw: str) -> str:
    base = get_settings().app_base_url.rstrip("/")
    return f"{base}/reset-password#token={raw}"


def reset_message(to: str, raw: str) -> EmailMessage:
    minutes = get_settings().password_reset_ttl_minutes
    text = (
        "Someone asked to reset the password of the MARS account for this address.\n\n"
        f"Open this link to choose a new password. It works once and expires in {minutes} minutes:\n\n"
        f"{reset_link(raw)}\n\n"
        "If you did not ask for this, ignore this email: your password has not changed and nothing else happens.\n"
    )
    return EmailMessage(to=to, subject=SUBJECT, text=text)


async def issue_token(db: AsyncSession, user_id: uuid.UUID, now: datetime | None = None) -> str:
    """Retire the user's unused tokens, store a fresh one hashed, and return the raw token (for the email only)."""
    now = now or now_naive_utc()
    await db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user_id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    raw, digest = new_token()
    db.add(
        PasswordResetToken(
            user_id=user_id,
            token_hash=digest,
            expires_at=now + timedelta(minutes=get_settings().password_reset_ttl_minutes),
        )
    )
    await db.commit()
    return raw


async def redeem_token(db: AsyncSession, raw: str, now: datetime | None = None) -> User | None:
    """The user a valid, unused, unexpired token belongs to, with the token marked used (and the user's other unused tokens
    retired); None for anything else, with no way to tell the reasons apart. The caller commits after setting the password."""
    now = now or now_naive_utc()
    row = (
        await db.execute(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(raw)).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None or row.used_at is not None or row.expires_at <= now:
        return None
    user = (await db.execute(select(User).where(User.id == row.user_id))).scalar_one_or_none()
    if user is None:
        return None
    await db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == row.user_id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    return user


async def allow_request(r: redis.Redis, email: str, ip: str) -> bool:
    """Silent rate limit for the request route: per address (default 3 an hour) and per IP (default 10 an hour).

    Over a limit the route still answers 202 and sends nothing, so the limit tells a caller nothing about the address. An address
    is counted by its hash, so no email is written into Redis. Fails CLOSED: if Redis cannot be reached nothing is sent (and
    nobody can sign in either, since sessions live there), which is safer than an unlimited mail cannon."""
    s = get_settings()
    window = int(time.time() // 3600)
    digest = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
    try:
        ok = True
        for key, limit in (
            (f"ratelimit:pwreset-email:{digest}:{window}", s.password_reset_per_email_per_hour),
            (f"ratelimit:pwreset-ip:{ip}:{window}", s.password_reset_per_ip_per_hour),
        ):
            count = await r.incr(key)
            if count == 1:
                await r.expire(key, 3600)
            if count > limit:
                ok = False
        return ok
    except redis.RedisError as exc:
        logger.warning("Password-reset limiter unavailable, sending nothing: %s", type(exc).__name__)
        return False


async def allow_confirm(r: redis.Redis, ip: str) -> bool:
    """Per-IP limit on confirm attempts (default 20 an hour). Fails open here: a refused confirm costs a real user their reset,
    and a token is 256 random bits, so guessing one is not what this limit is for; it bounds bcrypt work and noise."""
    window = int(time.time() // 3600)
    key = f"ratelimit:pwreset-confirm:{ip}:{window}"
    try:
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, 3600)
    except redis.RedisError:
        return True
    return count <= get_settings().password_reset_confirm_per_ip_per_hour


async def send_reset_if_account(email: str, sender: EmailSender | None = None) -> None:
    """The background task behind the request route. Looks the address up, and only if an account has it, issues a token and sends
    the email. Never raises: whatever happens, nothing here can change what the caller already answered."""
    try:
        async with SessionLocal() as db:
            user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if user is None:
                return
            raw = await issue_token(db, user.id)
        await (sender or get_email_sender()).send(reset_message(email, raw))
    except Exception as exc:  # a task after the response: log the class, never the address or the token
        logger.error("Password-reset email task failed: %s", type(exc).__name__)
