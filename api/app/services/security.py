"""Module 13 — password hashing, opaque session tokens, signed reset tokens.

Session strategy is server-side Redis sessions, NOT JWT (blueprint-locked,
`documentation/AIMS/decisions.md` 2026-08-30): an opaque `secrets.token_urlsafe`
token maps to `session:{token} -> user_id` in Redis with a sliding TTL;
logout/account-deletion deletes the key for instant revocation.

Password hashing uses the `bcrypt` library directly, NOT passlib — passlib
1.7.4's bcrypt-backend probe breaks on bcrypt>=4.1 (see mistakes.md 2026-09-16).
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import get_settings

_BCRYPT_MAX_BYTES = 72  # bcrypt hard limit; longer inputs are silently truncated by the C lib
_RESET_TOKEN_SALT = "mars-password-reset"
_RESET_TOKEN_MAX_AGE_SECONDS = 60 * 60  # 1 hour


def hash_password(password: str) -> str:
    if len(password.encode("utf-8")) > _BCRYPT_MAX_BYTES:
        raise ValueError(f"Password must be <= {_BCRYPT_MAX_BYTES} bytes")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def session_redis_key(token: str) -> str:
    return f"session:{token}"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt=_RESET_TOKEN_SALT)


def make_password_reset_token(user_id: str) -> str:
    return _serializer().dumps({"user_id": user_id, "issued_at": datetime.now(UTC).isoformat()})


def verify_password_reset_token(token: str) -> str | None:
    """Return the user_id if the token is valid and unexpired, else None."""
    try:
        data = _serializer().loads(token, max_age=_RESET_TOKEN_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("user_id")
