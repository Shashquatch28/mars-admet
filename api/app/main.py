import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.observability import init_sentry
from app.routers import (
    account,
    auth,
    batch,
    compare,
    depict,
    generations,
    health,
    limits,
    molecule,
    molecules,
    predict,
    reports,
    worker,
)
from app.services import prediction_service
from app.services.email_sender import email_config_problem
from app.spa import mount_spa

logger = logging.getLogger("mars.startup")

# Before the app exists, so Sentry's FastAPI/Starlette integrations can patch it.
init_sentry(get_settings())


def _warn_on_insecure_config() -> None:
    """Module 10 "production-safe containerization": catch the specific,
    concrete mistakes of a dev default silently riding into a real deployment
    — not a general secrets-scanner. A half-configured email backend is the one
    that stops the service starting (frontend ADR-042)."""
    settings = get_settings()
    if prediction_service.ml_import_error is not None:
        # Falling back to stubs is deliberate for local dev (no rdkit), but an image that
        # *should* have the ml stack and doesn't — e.g. built before ml/serve gained a
        # module — otherwise serves stub-v0 for every endpoint with nothing in the logs.
        logger.warning(
            "Real ML stack unavailable (%s) — every endpoint is served by the stub.",
            prediction_service.ml_import_error,
        )
    problem = email_config_problem(settings)
    if problem:
        # A deployment that selected Resend and forgot the key or the From address would otherwise answer 202 and send nothing.
        raise RuntimeError(problem)
    if settings.email_backend == "log" and settings.session_cookie_secure:
        logger.warning(
            "EMAIL_BACKEND=log in a deployment with a secure cookie: password-reset emails are written to the log, not sent. "
            "Set EMAIL_BACKEND=resend with RESEND_API_KEY and RESEND_FROM_EMAIL."
        )
    if settings.static_dir and not settings.session_cookie_secure:
        logger.warning(
            "The frontend is served from this container (STATIC_DIR is set) but SESSION_COOKIE_SECURE is "
            "false: the session cookie would travel over plain HTTP. Set SESSION_COOKIE_SECURE=true "
            "behind HTTPS (ADR-025 item 3)."
        )
    if not settings.cloudflare_turnstile_secret_key:
        logger.info(
            "CLOUDFLARE_TURNSTILE_SECRET_KEY is unset — registration Turnstile "
            "verification is SKIPPED (dev/test mode). Set it before deploying."
        )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _warn_on_insecure_config()
    # Warm the model registry in the background: the server accepts requests at once, and a
    # request that arrives first simply waits on the registry lock for the same load.
    warm_task = asyncio.create_task(asyncio.to_thread(prediction_service.warm_up))
    try:
        yield
    finally:
        warm_task.cancel()


app = FastAPI(
    title="MARS API",
    description="Molecular ADMET Rapid Screening — prediction, batch, and molecule-detail serving.",
    version="0.1.0-dev",
    lifespan=lifespan,
    # Every route lives under /api in every environment (ADR-025): four SPA routes (/predict,
    # /batch, /compare, /library) would otherwise collide with API routes of the same name.
    docs_url="/api/docs",
    swagger_ui_oauth2_redirect_url="/api/docs/oauth2-redirect",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

def cors_policy() -> tuple[list[str], bool]:
    """(allowed origins, allow_credentials) from `Settings.cors_allow_origins`.

    Credentials need an explicit origin list: a browser rejects a credentialed
    request answered with `Access-Control-Allow-Origin: *`. If someone configures
    a bare `*` anyway it still works for anonymous calls, with credentials off.
    """
    origins = [o.strip().rstrip("/") for o in get_settings().cors_allow_origins.split(",") if o.strip()]
    return origins, "*" not in origins


_cors_origins, _cors_credentials = cors_policy()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api"
app.include_router(health.router, prefix=API_PREFIX)
app.include_router(generations.router, prefix=API_PREFIX)
app.include_router(limits.router, prefix=API_PREFIX)
app.include_router(predict.router, prefix=f"{API_PREFIX}/predict", tags=["predict"])
app.include_router(compare.router, prefix=f"{API_PREFIX}/compare", tags=["compare"])
app.include_router(depict.router, prefix=f"{API_PREFIX}/depict", tags=["depict"])
app.include_router(molecule.router, prefix=f"{API_PREFIX}/molecule", tags=["molecule"])
app.include_router(batch.router, prefix=f"{API_PREFIX}/batch", tags=["batch"])
app.include_router(auth.router, prefix=f"{API_PREFIX}/auth", tags=["auth"])
app.include_router(molecules.router, prefix=f"{API_PREFIX}/molecules", tags=["molecules"])
app.include_router(reports.router, prefix=f"{API_PREFIX}/reports", tags=["reports"])
app.include_router(account.router, prefix=f"{API_PREFIX}/account", tags=["account"])
app.include_router(worker.router, prefix=f"{API_PREFIX}/internal/batch")

# Last, so the catch-all never shadows an API route.
_static_dir = get_settings().static_dir
if _static_dir and (Path(_static_dir) / "index.html").is_file():
    mount_spa(app, Path(_static_dir))
elif _static_dir:
    logger.warning("STATIC_DIR=%s has no index.html; the frontend is not served.", _static_dir)
