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

from dataclasses import dataclass

import numpy as np
from featurize.standardize import standardize
from mars_contracts.endpoints import ENDPOINT_METADATA, Endpoint, TaskType

from serve.registry import ModelRegistry


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


def standardize_or_raise(smiles: str) -> str:
    result = standardize(smiles)
    if not result.ok:
        raise ValueError(f"Invalid SMILES ({result.reason}): {smiles!r}")
    return result.canonical_smiles


def predict_endpoint(
    registry: ModelRegistry,
    endpoint_key: str,
    smiles_standardized: str,
) -> RealPrediction | None:
    """Real prediction for one (endpoint, molecule), or None if uncovered."""
    models = registry.load_models(endpoint_key)
    if not models:
        return None

    raw_preds = np.array([m.predict([smiles_standardized])[0] for m in models])
    if np.all(np.isnan(raw_preds)):
        # Registry has a model but featurization failed for this molecule
        # (e.g. an element outside the training feature space). Not "no
        # coverage" — a real failure the caller should surface, not mask.
        raise ValueError(f"Featurization failed for {endpoint_key}: {smiles_standardized!r}")
    raw_preds = raw_preds[~np.isnan(raw_preds)]

    endpoint = Endpoint(endpoint_key)
    task_type = ENDPOINT_METADATA[endpoint]["task_type"]

    calibrator = registry.load_calibrator(endpoint_key)
    if task_type == TaskType.CLASSIFICATION and calibrator is not None:
        raw_preds = calibrator.transform(raw_preds)

    mean = float(np.mean(raw_preds))
    std = float(np.std(raw_preds))

    ad_index = registry.load_ad_index(endpoint_key)
    if ad_index is not None:
        from eval.applicability_domain import query_ad

        ad_results = query_ad(ad_index, [smiles_standardized])
        in_domain = ad_results[0].in_domain if ad_results else False
        knn_distance = ad_results[0].knn_mean_distance if ad_results else float("nan")
    else:
        in_domain = False
        knn_distance = float("nan")

    return RealPrediction(
        endpoint=endpoint_key,
        value=mean,
        confidence_low=mean - std,
        confidence_high=mean + std,
        in_domain=in_domain,
        knn_distance=knn_distance,
        model_id=models[0].model_id,
        n_seeds=len(models),
    )


def predict_endpoints(
    registry: ModelRegistry,
    smiles: str,
    endpoint_keys: list[str],
) -> dict[str, RealPrediction | None]:
    """Real predictions for a batch of endpoints on one molecule.

    Standardizes once, reuses the result across all requested endpoints.
    Value at each key is `None` when the registry has no promoted model for
    that endpoint — the caller (API layer) decides the fallback.
    """
    smiles_std = standardize_or_raise(smiles)
    return {ep: predict_endpoint(registry, ep, smiles_std) for ep in endpoint_keys}
