"""Module 13 — password hashing and opaque session tokens (reset tokens: services/password_reset.py).

Session strategy is server-side Redis sessions, NOT JWT (blueprint-locked,
`documentation/AIMS/decisions.md` 2026-08-30): an opaque `secrets.token_urlsafe`
token maps to `session:{token} -> user_id` in Redis with a sliding TTL;
logout/account-deletion deletes the key for instant revocation.

Password hashing uses the `bcrypt` library directly, NOT passlib — passlib
1.7.4's bcrypt-backend probe breaks on bcrypt>=4.1 (see mistakes.md 2026-09-16).
"""

from __future__ import annotations

import secrets

import bcrypt

_BCRYPT_MAX_BYTES = 72  # bcrypt hard limit; longer inputs are silently truncated by the C lib


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
