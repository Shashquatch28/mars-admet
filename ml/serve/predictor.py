"""Per-molecule real-model prediction path (Module 8 serving, ml side).

`predict_endpoints` is the one function the API layer calls. For each
requested endpoint it either returns a real ensembled prediction (if the
registry has at least one promoted seed for that endpoint) or `None`
(caller falls back to Module 8's stub predictor for that endpoint only —
this module never fabricates a result for missing coverage).

Ensembling: mean +/- std across whatever promoted seeds exist. With only one
seed promoted (true for most/all endpoints as of 2026-09-16, since MARS has
not run its 70-run production sweep), std is 0 and the confidence interval
collapses to a point — this is an honest reflection of having a single
model, not a bug to paper over.
"""

from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np
from featurize.standardize import standardize
from mars_contracts.endpoints import ENDPOINT_METADATA, Endpoint, TaskType

from serve.registry import ModelRegistry

logger = logging.getLogger("mars.predictor")

# C0 (AIMS decisions.md 2026-10-08): the served Platt calibrators were worse than
# the raw ensemble on held-out Brier for 9 of 9 classification endpoints, so they
# are not applied by default. MARS_APPLY_PLATT=1 restores the old behaviour.
APPLY_PLATT_ENV = "MARS_APPLY_PLATT"


def platt_enabled() -> bool:
    return os.environ.get(APPLY_PLATT_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class RealPrediction:
    endpoint: str
    value: float
    confidence_low: float
    confidence_high: float
    in_domain: bool
    knn_distance: float
    model_id: str
    n_seeds: int
    # The cutoff in_domain was judged against; None when the endpoint has no AD index.
    ad_threshold: float | None = None
    # Held-out-error band (ADR-024): the share of held-out validation errors that fell within
    # +/- halfwidth, and how many residuals that was taken over. None for classification and for
    # any regression endpoint whose band has not been built.
    heldout_error_halfwidth: float | None = None
    heldout_error_level: float | None = None
    heldout_error_n: int | None = None


def standardize_or_raise(smiles: str) -> str:
    result = standardize(smiles)
    if not result.ok:
        raise ValueError(f"Invalid SMILES ({result.reason}): {smiles!r}")
    return result.canonical_smiles


_kermt_executor: ThreadPoolExecutor | None = None
_kermt_executor_lock = threading.Lock()


def _kermt_pool() -> ThreadPoolExecutor:
    """Threads that wait on the KERMT service (I/O, not CPU), so the request thread can keep working."""
    global _kermt_executor
    with _kermt_executor_lock:
        if _kermt_executor is None:
            _kermt_executor = ThreadPoolExecutor(max_workers=16, thread_name_prefix="kermt-call")
        return _kermt_executor


def applicability_domain(registry: ModelRegistry, endpoint_key: str, smiles_standardized: str) -> tuple[bool, float, float | None]:
    """(in_domain, knn_distance, threshold) from the endpoint's AD index.

    The index is built from the endpoint's training pool and does not depend on which model
    serves the endpoint, so XGBoost- and KERMT-served rows share it. No index -> not in domain,
    distance NaN, threshold None."""
    ad_index = registry.load_ad_index(endpoint_key)
    if ad_index is None:
        return False, float("nan"), None
    from eval.applicability_domain import query_ad

    ad_results = query_ad(ad_index, [smiles_standardized])
    in_domain = ad_results[0].in_domain if ad_results else False
    knn_distance = ad_results[0].knn_mean_distance if ad_results else float("nan")
    return in_domain, knn_distance, ad_index.threshold


def _model_predict(model, smiles_standardized: str, prepared: dict | None) -> float:
    """One model's raw prediction for one molecule.

    When `prepared` is given (a per-molecule scratch dict owned by the caller) and the
    model can expose its feature identity, the molecule is featurized once per distinct
    feature set and shared by every model that uses it. Models without that interface
    (test doubles) just `predict`.
    """
    key = getattr(model, "feature_key", None)
    if prepared is None or key is None:
        return model.predict([smiles_standardized])[0]
    if key not in prepared:
        prepared[key] = model.prepare([smiles_standardized])
    return model.predict_prepared(1, *prepared[key])[0]


def predict_endpoint(
    registry: ModelRegistry,
    endpoint_key: str,
    smiles_standardized: str,
    *,
    prepared: dict | None = None,
) -> RealPrediction | None:
    """Real prediction for one (endpoint, molecule), or None if uncovered.

    `prepared` is an optional per-molecule featurization memo shared across endpoints
    (see `predict_endpoints`); it changes cost, never values.
    """
    models = registry.load_models(endpoint_key)
    if not models:
        return None

    raw_preds = np.array([_model_predict(m, smiles_standardized, prepared) for m in models])
    if np.all(np.isnan(raw_preds)):
        # Registry has a model but featurization failed for this molecule
        # (e.g. an element outside the training feature space). Not "no
        # coverage" — a real failure the caller should surface, not mask.
        raise ValueError(f"Featurization failed for {endpoint_key}: {smiles_standardized!r}")
    raw_preds = raw_preds[~np.isnan(raw_preds)]

    endpoint = Endpoint(endpoint_key)
    task_type = ENDPOINT_METADATA[endpoint]["task_type"]

    if task_type == TaskType.CLASSIFICATION and platt_enabled():
        calibrator = registry.load_calibrator(endpoint_key)
        if calibrator is not None:
            raw_preds = calibrator.transform(raw_preds)

    mean = float(np.mean(raw_preds))
    std = float(np.std(raw_preds))

    in_domain, knn_distance, ad_threshold = applicability_domain(registry, endpoint_key, smiles_standardized)

    band = registry.load_error_band(endpoint_key) if task_type == TaskType.REGRESSION else None

    return RealPrediction(
        endpoint=endpoint_key,
        value=mean,
        confidence_low=mean - std,
        confidence_high=mean + std,
        in_domain=in_domain,
        knn_distance=knn_distance,
        model_id=models[0].model_id,
        n_seeds=len(models),
        ad_threshold=ad_threshold,
        heldout_error_halfwidth=band.halfwidth if band else None,
        heldout_error_level=band.level if band else None,
        heldout_error_n=band.n_residuals if band else None,
    )


def predict_endpoints(
    registry: ModelRegistry,
    smiles: str,
    endpoint_keys: list[str],
    *,
    kermt=None,
) -> dict[str, RealPrediction | None]:
    """Real predictions for a batch of endpoints on one molecule.

    Standardizes once and featurizes once, reusing both across all requested
    endpoints and all of their seed models.
    Value at each key is `None` when the registry has no promoted model for
    that endpoint — the caller (API layer) decides the fallback.

    `kermt` is an optional `serve.kermt_router.KermtRouter`. Endpoints the routing table
    sends to KERMT are asked of it in one call per arm; any endpoint it cannot answer
    (service down, molecule not featurizable) falls through to the XGBoost path below, so
    routing never turns an answerable endpoint into a missing one.
    """
    smiles_std = standardize_or_raise(smiles)
    prepared: dict = {}
    results: dict[str, RealPrediction | None] = {}

    routed = [ep for ep in endpoint_keys if ep in kermt.served_by_kermt()] if kermt is not None else []
    # The KERMT call is the slow part (about 0.15 s per checkpoint). Start it first so the XGBoost
    # endpoints are computed while it runs, instead of one after the other.
    pending = _kermt_pool().submit(kermt.predict, smiles_std, endpoint_keys) if routed else None
    for ep in endpoint_keys:
        if ep not in routed:
            results[ep] = predict_endpoint(registry, ep, smiles_std, prepared=prepared)
    from_kermt: dict[str, RealPrediction] = {}
    if pending is not None:
        try:
            from_kermt = pending.result()
        except Exception:  # a KERMT-side bug must cost this request its KERMT rows, never the request
            logger.exception("KERMT routing failed; serving %s from XGBoost", routed)
    for ep in routed:
        results[ep] = from_kermt[ep] if ep in from_kermt else predict_endpoint(registry, ep, smiles_std, prepared=prepared)
    return {ep: results[ep] for ep in endpoint_keys}
