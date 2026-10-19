"""Sentry error reporting (ship checklist C9). Off unless `SENTRY_DSN` is set.

What this reports: unhandled exceptions and their stack traces, with the route, status and release.
What it must not report: what users sent. A request carries SMILES (the molecule someone is working
on) and a session cookie, so the SDK is told never to attach request bodies and never to attach
cookies or auth headers, and `scrub_event` drops anything that slips through (extra data, breadcrumbs
that quote a body, local variables in stack frames, which can hold a SMILES). Performance tracing is
off by default (`SENTRY_TRACES_SAMPLE_RATE=0`) so the free quota goes to errors.

The browser is not instrumented. Only the API reports.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from app.core.config import Settings

logger = logging.getLogger("mars.observability")

_SENSITIVE_HEADERS = {"cookie", "set-cookie", "authorization", "x-mars-worker-secret"}


def scrub_event(event: dict, _hint: dict | None = None) -> dict | None:
    """Remove user data from an event before it leaves the process."""
    request = event.get("request")
    if isinstance(request, dict):
        for key in ("data", "cookies", "query_string"):
            request.pop(key, None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {k: v for k, v in headers.items() if k.lower() not in _SENSITIVE_HEADERS}
    event.pop("user", None)
    event.pop("extra", None)
    for crumb in (event.get("breadcrumbs") or {}).get("values", []) if isinstance(event.get("breadcrumbs"), dict) else []:
        crumb.pop("data", None)
    for exc in (event.get("exception") or {}).get("values", []):
        for frame in (exc.get("stacktrace") or {}).get("frames", []):
            frame.pop("vars", None)
    return event


def init_sentry(settings: Settings, *, transport: Callable | None = None) -> bool:
    """Start Sentry if a DSN is configured. Returns whether it started. Call before the app is created,
    so the FastAPI/Starlette integrations can patch it."""
    if not settings.sentry_dsn:
        return False
    import sentry_sdk

    options = {
        "dsn": settings.sentry_dsn,
        "environment": settings.sentry_environment,
        "release": settings.sentry_release or None,
        "traces_sample_rate": settings.sentry_traces_sample_rate,
        "send_default_pii": False,
        "max_request_body_size": "never",
        "include_local_variables": False,
        "before_send": scrub_event,
    }
    if transport is not None:
        options["transport"] = transport
    sentry_sdk.init(**options)
    logger.info("Sentry error reporting is on (environment=%s).", settings.sentry_environment)
    return True
