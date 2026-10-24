"""Outgoing email, behind one small interface (frontend ADR-042).

Two backends, chosen by `EMAIL_BACKEND`:

* `log` (the default): writes the message to the server log instead of sending it. This is how development works with no
  provider: the password-reset link is printed where the developer is looking. It must not be used in production, and the
  service warns at startup if it is selected next to a secure cookie.
* `resend`: sends through Resend's HTTP API. `RESEND_API_KEY` and `RESEND_FROM_EMAIL` come from the environment and nowhere
  else; the key is never logged, never put in an error message and never committed. The service refuses to start with this
  backend selected and either one missing, so a half-configured deployment fails loudly instead of silently sending nothing.

A send never raises into a request: the caller is a background task and the response has already gone. A failure is logged
with a status or an exception class only (a provider's error body can echo the address it was sent to).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"
_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text: str


class EmailSender(Protocol):
    async def send(self, message: EmailMessage) -> bool:
        """Send, and say whether the provider accepted it. Never raises."""
        ...


class LogEmailSender:
    """Development: the message goes to the log, in full. That includes any link in it, which is the point."""

    async def send(self, message: EmailMessage) -> bool:
        logger.warning(
            "EMAIL_BACKEND=log, not sent. To: %s | Subject: %s\n%s",
            message.to,
            message.subject,
            message.text,
        )
        return True


class ResendEmailSender:
    def __init__(self, api_key: str, from_email: str, client: httpx.AsyncClient | None = None) -> None:
        self._api_key = api_key
        self._from = from_email
        self._client = client  # a test passes one with a mock transport

    async def send(self, message: EmailMessage) -> bool:
        payload = {"from": self._from, "to": [message.to], "subject": message.subject, "text": message.text}
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        try:
            if self._client is not None:
                resp = await self._client.post(RESEND_URL, json=payload, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                    resp = await client.post(RESEND_URL, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            logger.error("Resend request failed: %s", type(exc).__name__)  # the class only: a message can carry the URL or a header
            return False
        if resp.status_code >= 300:
            logger.error("Resend refused the message: HTTP %s", resp.status_code)
            return False
        return True


def email_config_problem(settings: Settings) -> str | None:
    """Why the configured backend cannot work, or None. Names the missing settings, never a value."""
    if settings.email_backend == "resend":
        missing = [n for n, v in (("RESEND_API_KEY", settings.resend_api_key), ("RESEND_FROM_EMAIL", settings.resend_from_email)) if not v.strip()]
        if missing:
            return f"EMAIL_BACKEND=resend needs {' and '.join(missing)}"
    return None


def get_email_sender() -> EmailSender:
    settings = get_settings()
    problem = email_config_problem(settings)
    if problem:
        raise RuntimeError(problem)
    if settings.email_backend == "resend":
        return ResendEmailSender(settings.resend_api_key, settings.resend_from_email)
    return LogEmailSender()
