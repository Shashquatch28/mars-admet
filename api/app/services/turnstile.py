"""Module 8 registration gate — Cloudflare Turnstile verification.

Only the registration endpoint is gated (login/password-reset are not — see
blueprint Module 8 "Registration gate"). When `CLOUDFLARE_TURNSTILE_SECRET_KEY`
is unset (local dev, tests), verification is skipped and every token is
accepted — this must never be true in a deployed environment; `main.py`
surfaces a startup warning if it is.
"""

from __future__ import annotations

import httpx

from app.core.config import get_settings

_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify_turnstile(token: str) -> bool:
    secret = get_settings().cloudflare_turnstile_secret_key
    if not secret:
        return True  # dev/test mode — no secret configured

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(_VERIFY_URL, data={"secret": secret, "response": token})
    resp.raise_for_status()
    return bool(resp.json().get("success", False))
