"""Start-up delivery of the trained model artifacts (ship checklist C7; runbook `documentation/DEPLOY.md`).

`ml/artifacts/` is gitignored and not in the image. With `MODEL_ARTIFACT_BUCKET` set, `ensure_model_artifacts`
downloads the release named by `MODEL_ARTIFACT_RELEASE` into `MODEL_ARTIFACT_DIR`, verifies every file's SHA-256
and checks that all 14 ML endpoints are covered. Any failure raises, the app does not start, and the platform
keeps the previous revision: a service that quietly answers with the stub is the failure this exists to prevent.

Without a bucket nothing is fetched (development, and the docker-compose bind mount). `REQUIRE_REAL_MODELS=true`
makes that mode strict too: the directory must already cover every endpoint.

The logic lives in `ml/serve/artifact_store.py`, shared with the publish script; this module is the settings glue.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from app.core.config import Settings, get_settings
from app.services.s3_client import make_s3_client

# A child of uvicorn's logger so its INFO lines reach the container log; plain `mars.*` loggers have no handler
# under uvicorn and their INFO output is dropped.
logger = logging.getLogger("uvicorn.error.mars.model_artifacts")


def _artifact_store():
    """`serve.artifact_store`, importable the same way `prediction_service` imports the rest of ml/ (ml/ is not a package)."""
    ml_root = Path(__file__).resolve().parents[3] / "ml"
    if str(ml_root) not in sys.path:
        sys.path.insert(0, str(ml_root))
    from serve import artifact_store

    return artifact_store


def _kermt_regression_endpoints(settings: Settings) -> list[str]:
    """Regression endpoints the routing sends to KERMT; their KERMT error band must ship with the models."""
    if not settings.kermt_service_url:
        return []
    from mars_contracts.endpoints import ENDPOINT_METADATA, Endpoint, TaskType
    from serve.routing import RoutingTable

    routing = RoutingTable.load(settings.kermt_routing_path or None)
    served = routing.kermt_endpoint_set()
    return sorted(k for k in served if ENDPOINT_METADATA[Endpoint(k)]["task_type"] == TaskType.REGRESSION)


def ensure_model_artifacts(settings: Settings | None = None, client=None):
    """Fetch and verify the configured release, or check the directory in strict mode. Returns the fetch report
    (None when nothing was fetched). Raises `ArtifactError` or `RuntimeError` on any problem; never falls back."""
    settings = settings or get_settings()
    store = _artifact_store()
    dest = Path(settings.model_artifact_dir)

    if not settings.model_artifact_bucket:
        if settings.require_real_models:
            from app.services import prediction_service

            if prediction_service.ml_import_error is not None:
                raise RuntimeError(f"REQUIRE_REAL_MODELS is set but the ml stack cannot be imported: {prediction_service.ml_import_error}")
            store.raise_for_roster(dest, kermt_regression=_kermt_regression_endpoints(settings), what="model artifacts")
            logger.info("Model artifacts in %s cover every endpoint.", dest)
        return None

    if not settings.model_artifact_release:
        raise store.ArtifactError("MODEL_ARTIFACT_BUCKET is set but MODEL_ARTIFACT_RELEASE is not: say which release to serve")
    if client is None:
        client = make_s3_client(
            settings,
            access_key_id=settings.model_artifact_access_key_id,
            secret_access_key=settings.model_artifact_secret_access_key,
        )
    logger.info("Fetching model release %s from bucket %s ...", settings.model_artifact_release[:12], settings.model_artifact_bucket)
    return store.fetch(
        client,
        settings.model_artifact_bucket,
        settings.model_artifact_release,
        dest,
        prefix=settings.model_artifact_prefix,
        kermt_regression=_kermt_regression_endpoints(settings),
        log=logger.info,
    )
