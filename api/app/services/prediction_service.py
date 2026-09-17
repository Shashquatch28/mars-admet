"""Module 8 routing table (API side): for each requested endpoint, use a real
trained model if `ml/serve/` has one promoted, otherwise fall back to the
Module 8 stub for that endpoint only. Mixed responses (some real, some stub)
are expected and honest — see `EndpointPrediction.model_id` and
`contracts/API_ROUTES.md`'s "Cross-cutting" section.

The api container's root environment does NOT have rdkit/xgboost installed
(that's `ml/.venv`, kept deliberately separate — see
`documentation/AIMS/mars-aims-and-envs.md`). Only the production Docker image
(built from `api/Dockerfile`, which additionally installs
`ml/requirements-serving.txt` and copies `ml/serve|featurize|models|eval`)
has the real path available. Everywhere else — local `api/tests` runs, a bare
`uvicorn` from `.venv` — this module correctly, silently falls back to the
stub for every endpoint, which is the right behavior for a dev loop that
doesn't need real inference.

Note: when the real path IS available, SMILES are standardized twice on the
happy path — once here (real RDKit standardization, to keep molecule_id and
smiles_standardized consistent with whatever endpoint actually served the
prediction) and again inside `predict_stub` (a no-op `.strip()` on an
already-canonical string). Not worth de-duplicating for the sole purpose of
saving one cheap RDKit call.

Module 3 Stage 1 validation enforcement ("reject invalid SMILES with a clear
error") is now applied at this boundary WHEN the real ml stack is available
(the production container): `standardize_or_raise` propagates a `ValueError`
for genuinely invalid SMILES, and callers (`routers/predict.py`,
`routers/compare.py`, `routers/batch.py`'s per-row handling) turn that into a
422 / a per-row `ok=False` error rather than a fabricated prediction. When
the ml stack is NOT available (root `.venv`, fast local tests — no rdkit),
there is no way to validate chemistry at all, so this stays lenient and
passes whatever string it's given straight to the stub — a known,
environment-gated limitation, not silently "fixed" by a fake regex check
that would just be wrong some of the time.
"""

from __future__ import annotations

import sys
import warnings
from functools import lru_cache
from pathlib import Path

from mars_contracts import ML_ENDPOINTS, Endpoint, EndpointPrediction, PredictionResponse

from app.core.config import get_settings
from app.services.stub_predictor import predict_stub

_ml_available = False
try:
    # ml/ is not a package (no top-level __init__.py) — its subpackages
    # (serve/, featurize/, models/, eval/) are imported as if ml/ were on
    # sys.path directly, matching how ml/.venv's own tests run
    # (`PYTHONPATH=ml pytest`) and how api/Dockerfile sets `ENV PYTHONPATH`.
    _ml_root = Path(__file__).resolve().parents[3] / "ml"
    if str(_ml_root) not in sys.path:
        sys.path.insert(0, str(_ml_root))
    from featurize.cache import FeatureCache  # noqa: E402
    from serve.predictor import predict_endpoints, standardize_or_raise  # noqa: E402
    from serve.registry import ModelRegistry  # noqa: E402

    _ml_available = True
except ImportError:
    pass


@lru_cache
def _get_registry():
    if not _ml_available:
        return None
    settings = get_settings()
    cache = FeatureCache(Path(settings.ml_data_cache_dir))
    return ModelRegistry(cache, artifacts_root=Path(settings.model_artifact_dir))


def predict(smiles: str, endpoints: list[Endpoint] | None = None) -> PredictionResponse:
    """Raises `ValueError` for a chemically invalid SMILES — but ONLY when
    the real ml stack is available to actually judge validity (see module
    docstring). Callers must catch this and turn it into a 422 / per-row
    error, not let it become an unhandled 500."""
    targets = endpoints or ML_ENDPOINTS

    smiles_for_stub = smiles
    if _ml_available:
        smiles_for_stub = standardize_or_raise(smiles)  # raises ValueError on invalid input

    response = predict_stub(smiles_for_stub, targets)
    registry = _get_registry()
    if registry is None:
        return response

    endpoint_keys = [ep.value for ep in targets if ep != Endpoint.SA_SCORE]
    try:
        real_results = predict_endpoints(registry, response.smiles_standardized, endpoint_keys)
    except ValueError as exc:
        warnings.warn(f"Real inference failed, falling back to stub: {exc}", stacklevel=2)
        return response

    by_endpoint: dict[Endpoint, EndpointPrediction] = {p.endpoint: p for p in response.predictions}
    for key, real in real_results.items():
        if real is None:
            continue
        ep = Endpoint(key)
        by_endpoint[ep] = EndpointPrediction(
            endpoint=ep,
            value=real.value,
            unit=None,  # neither the stub nor XGBoostModel populates a unit string today
            confidence_low=real.confidence_low,
            confidence_high=real.confidence_high,
            in_domain=real.in_domain,
            knn_distance=real.knn_distance,
            model_id=real.model_id,
        )

    response.predictions = [by_endpoint[ep] for ep in targets if ep in by_endpoint]
    return response
