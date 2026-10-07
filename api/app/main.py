import logging
import warnings
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers import account, auth, batch, compare, health, molecule, molecules, predict, reports
from app.services import prediction_service

logger = logging.getLogger("mars.startup")


def _warn_on_insecure_config() -> None:
    """Module 10 "production-safe containerization": catch the specific,
    concrete mistake of a dev default silently riding into a real deployment
    — not a general secrets-scanner, just the one default this codebase
    itself ships (`Settings.secret_key`) that would quietly make every
    password-reset token forgeable if left unchanged."""
    settings = get_settings()
    if prediction_service.ml_import_error is not None:
        # Falling back to stubs is deliberate for local dev (no rdkit), but an image that
        # *should* have the ml stack and doesn't — e.g. built before ml/serve gained a
        # module — otherwise serves stub-v0 for every endpoint with nothing in the logs.
        logger.warning(
            "Real ML stack unavailable (%s) — every endpoint is served by the stub.",
            prediction_service.ml_import_error,
        )
    if settings.secret_key == "mars-dev-secret-change-me":
        warnings.warn(
            "SECRET_KEY is at its insecure development default — password-reset "
            "tokens are forgeable. Set a real SECRET_KEY before deploying.",
            stacklevel=1,
        )
        logger.warning("SECRET_KEY is at its insecure development default.")
    if not settings.cloudflare_turnstile_secret_key:
        logger.info(
            "CLOUDFLARE_TURNSTILE_SECRET_KEY is unset — registration Turnstile "
            "verification is SKIPPED (dev/test mode). Set it before deploying."
        )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _warn_on_insecure_config()
    yield


app = FastAPI(
    title="MARS API",
    description="Molecular ADMET Rapid Screening — prediction, batch, and molecule-detail serving.",
    version="0.1.0-dev",
    lifespan=lifespan,
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

app.include_router(health.router)
app.include_router(predict.router, prefix="/predict", tags=["predict"])
app.include_router(compare.router, prefix="/compare", tags=["compare"])
app.include_router(molecule.router, prefix="/molecule", tags=["molecule"])
app.include_router(batch.router, prefix="/batch", tags=["batch"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(molecules.router, prefix="/molecules", tags=["molecules"])
app.include_router(reports.router, prefix="/reports", tags=["reports"])
app.include_router(account.router, prefix="/account", tags=["account"])
