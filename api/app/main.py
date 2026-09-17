import logging
import warnings
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers import account, auth, batch, compare, health, molecule, molecules, predict, reports

logger = logging.getLogger("mars.startup")


def _warn_on_insecure_config() -> None:
    """Module 10 "production-safe containerization": catch the specific,
    concrete mistake of a dev default silently riding into a real deployment
    — not a general secrets-scanner, just the one default this codebase
    itself ships (`Settings.secret_key`) that would quietly make every
    password-reset token forgeable if left unchanged."""
    settings = get_settings()
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten before prod deploy
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
