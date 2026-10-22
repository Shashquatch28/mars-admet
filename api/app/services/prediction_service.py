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

import hashlib
import logging
import sys
import threading
import warnings
from pathlib import Path

from mars_contracts import (
    ALL_ENDPOINTS,
    Endpoint,
    EndpointPrediction,
    MoleculeProperties,
    PredictionResponse,
    StructuralAlert,
)

from app.core.config import get_settings
from app.services.stub_predictor import predict_stub

_ml_available = False
ml_import_error: ImportError | None = None  # surfaced at startup (app.main); never silent
try:
    # ml/ is not a package (no top-level __init__.py) — its subpackages
    # (serve/, featurize/, models/, eval/) are imported as if ml/ were on
    # sys.path directly, matching how ml/.venv's own tests run
    # (`PYTHONPATH=ml pytest`) and how api/Dockerfile sets `ENV PYTHONPATH`.
    _ml_root = Path(__file__).resolve().parents[3] / "ml"
    if str(_ml_root) not in sys.path:
        sys.path.insert(0, str(_ml_root))
    from featurize.cache import FeatureCache  # noqa: E402
    from serve.kermt_client import KermtClient  # noqa: E402
    from serve.kermt_router import KermtRouter  # noqa: E402
    from serve.predictor import predict_endpoints, standardize_or_raise  # noqa: E402
    from serve.properties import compute_properties  # noqa: E402
    from serve.registry import ModelRegistry  # noqa: E402
    from serve.routing import RoutingTable  # noqa: E402
    from serve.rule_based import SA_MODEL_ID, SA_UNIT, compute_sa_score  # noqa: E402

    _ml_available = True
except ImportError as exc:
    ml_import_error = exc


logger = logging.getLogger("mars.prediction")

_registry = None
_registry_lock = threading.Lock()
_router_lock = threading.Lock()
_kermt_router = None
_kermt_router_built = False


def _get_registry():
    """The process-wide registry. Built once under a lock: predictions run on worker
    threads, and two registries would each hold (and each load) their own 70 models."""
    global _registry
    if not _ml_available:
        return None
    with _registry_lock:
        if _registry is None:
            settings = get_settings()
            cache = FeatureCache(Path(settings.ml_data_cache_dir))
            _registry = ModelRegistry(cache, artifacts_root=Path(settings.model_artifact_dir))
        return _registry


def _get_kermt_router():
    """The KERMT router, or None when KERMT serving is off (no service URL configured, no ml
    stack, or an unusable routing table). Built once; a bad table is logged loudly and then
    treated as "everything on XGBoost" rather than taking the API down."""
    global _kermt_router, _kermt_router_built
    if not _ml_available or not get_settings().kermt_service_url:
        return None
    with _router_lock:
        if _kermt_router_built:
            return _kermt_router
        settings = get_settings()
        try:
            routing = RoutingTable.load(settings.kermt_routing_path or None)
            client = KermtClient(
                settings.kermt_service_url,
                token=settings.kermt_service_token,
                timeout_seconds=settings.kermt_timeout_seconds,
            )
            _kermt_router = KermtRouter(routing, client, _get_registry())
            logger.info("KERMT serving on: %s", routing.as_dict())
        except Exception:
            logger.exception("KERMT routing table unusable; serving every endpoint from XGBoost")
        _kermt_router_built = True
        return _kermt_router


def reset_kermt_router() -> None:
    """Forget the cached router (tests, and settings changes in a long-lived process)."""
    global _kermt_router, _kermt_router_built
    with _router_lock:
        _kermt_router, _kermt_router_built = None, False


def serving_version() -> str:
    """The version string for responses and the cache key.

    `settings.model_version` names the deployed generation. When KERMT serving is on, a short
    digest of the routing table is appended, so a change of which endpoints KERMT serves can
    never reuse a cache entry written under another routing (the .env's MODEL_VERSION is shared
    and may not be bumped by whoever changes routing)."""
    base = get_settings().model_version
    router = _get_kermt_router()
    if router is None:
        return base
    digest = hashlib.sha256(repr(sorted(router.routing.as_dict().items())).encode()).hexdigest()[:8]
    return f"{base}+kermt.{digest}"


def kermt_endpoints() -> list[str]:
    """Endpoint names the deployed routing sends to KERMT, sorted; empty when KERMT serving is off."""
    router = _get_kermt_router()
    return sorted(router.served_by_kermt()) if router is not None else []


def is_degraded(response: PredictionResponse) -> bool:
    """True when an endpoint the routing sends to KERMT was answered by something else (the
    service was unreachable). Such a response is correct but must not be cached for 48 h under
    the healthy version key."""
    router = _get_kermt_router()
    if router is None:
        return False
    got = {p.endpoint.value: p.model_id for p in response.predictions}
    for endpoint in router.served_by_kermt():
        model_id = got.get(endpoint)
        if model_id is not None and not model_id.startswith("mars-kermt"):
            return True
    return False


def warm_up() -> int:
    """Load every promoted model, AD index and calibrator into the registry now, so the
    first request does not pay for it (about 12 s for 70 models). Blocking: call it on a
    worker thread. Returns the number of endpoints loaded; never raises, because a
    failure here only means the first request loads lazily as before."""
    registry = _get_registry()
    if registry is None:
        return 0
    try:
        endpoints = registry.available_endpoints()
        for key in endpoints:
            registry.load_models(key)
            registry.load_ad_index(key)
            registry.load_calibrator(key)
        return len(endpoints)
    except Exception:
        logger.exception("Registry warm-up failed; models will load on first use")
        return 0


def predict(smiles: str, endpoints: list[Endpoint] | None = None) -> PredictionResponse:
    """Raises `ValueError` for a chemically invalid SMILES — but ONLY when
    the real ml stack is available to actually judge validity (see module
    docstring). Callers must catch this and turn it into a 422 / per-row
    error, not let it become an unhandled 500.

    `endpoints=None` means every endpoint the environment can serve: the 14 ML
    endpoints (real model or per-endpoint stub) plus the rule-based SA score
    when RDKit is available. Without the ml stack the SA score is simply absent
    — it is never stubbed — and the client reports it as not returned."""
    targets = endpoints or ALL_ENDPOINTS

    smiles_for_stub = smiles
    if _ml_available:
        smiles_for_stub = standardize_or_raise(smiles)  # raises ValueError on invalid input

    response = _route_to_models(predict_stub(smiles_for_stub, targets), targets)
    return _add_properties(_add_rule_based(response, targets))


def _route_to_models(response: PredictionResponse, targets: list[Endpoint]) -> PredictionResponse:
    """Swap stub values for real model output wherever a promoted model exists."""
    registry = _get_registry()
    if registry is None:
        return response

    endpoint_keys = [ep.value for ep in targets if ep != Endpoint.SA_SCORE]
    try:
        real_results = predict_endpoints(
            registry, response.smiles_standardized, endpoint_keys, kermt=_get_kermt_router()
        )
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
            ad_threshold=real.ad_threshold,
            heldout_error_halfwidth=real.heldout_error_halfwidth,
            heldout_error_level=real.heldout_error_level,
            heldout_error_n=real.heldout_error_n,
            model_id=real.model_id,
        )

    response.predictions = [by_endpoint[ep] for ep in targets if ep in by_endpoint]
    if any(real is not None for real in real_results.values()):
        # `predict_stub` stamps "stub-v0"; once a promoted model has served any
        # endpoint the response belongs to the deployed routing table, which is
        # what `model_version` (and the cache key) names. Per-row truth stays in
        # `EndpointPrediction.model_id`.
        response.model_version = serving_version()
    return response


def _add_rule_based(response: PredictionResponse, targets: list[Endpoint]) -> PredictionResponse:
    """Append the computed synthetic-accessibility score when requested.

    The contract has no "no interval / no domain" shape, so the interval
    collapses to the point and the domain fields carry their neutral values
    (`in_domain=True`, `knn_distance=0.0`). Those are placeholders for a rule
    that has no applicability domain; clients must key off the endpoint's
    `RULE_BASED` task type (and `model_id`), not read them as a measured domain.
    """
    if Endpoint.SA_SCORE not in targets or not _ml_available:
        return response
    score = compute_sa_score(response.smiles_standardized)
    if score is None:
        return response  # not computable -> the client shows NOT RETURNED, honestly
    response.predictions.append(
        EndpointPrediction(
            endpoint=Endpoint.SA_SCORE,
            value=score,
            unit=SA_UNIT,
            confidence_low=score,
            confidence_high=score,
            in_domain=True,
            knn_distance=0.0,
            model_id=SA_MODEL_ID,
        )
    )
    order = {ep: i for i, ep in enumerate(targets)}
    response.predictions.sort(key=lambda p: order.get(p.endpoint, len(order)))
    return response


def _add_properties(response: PredictionResponse) -> PredictionResponse:
    """Attach the RDKit-computed properties and structural alerts (frontend ADR-034 item 3).

    They describe the molecule, not a model, so they are added whatever endpoints were asked for and whichever
    model answered them, and a KERMT outage does not touch them. Without the ml stack, or for a molecule RDKit
    cannot parse, `properties` stays null: the client says nothing rather than showing a made-up number."""
    if not _ml_available:
        return response
    try:
        props = compute_properties(response.smiles_standardized)
    except Exception:  # never let a descriptor failure turn a prediction into a 500
        logger.exception("computed properties failed for %s", response.molecule_id)
        return response
    if props is None:
        return response
    response.properties = MoleculeProperties(
        mol_weight=props.mol_weight,
        crippen_logp=props.crippen_logp,
        h_bond_donors=props.h_bond_donors,
        h_bond_acceptors=props.h_bond_acceptors,
        tpsa=props.tpsa,
        rotatable_bonds=props.rotatable_bonds,
        qed=props.qed,
        lipinski_criteria_exceeded=props.lipinski_criteria_exceeded,
        alerts=[StructuralAlert(catalog=c, name=n) for c, n in props.alerts],  # type: ignore[arg-type]
    )
    return response
