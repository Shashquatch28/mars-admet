"""Answers KERMT-routed endpoints for one molecule, in the same shape as the XGBoost path.

Used by `serve.predictor.predict_endpoints` (and so by every route that predicts). Given the
standardized SMILES and the endpoints requested, it:

  1. keeps only the endpoints the routing table sends to KERMT;
  2. makes one service call for the arms those endpoints need (a multi-task arm costs one pass
     however many of its endpoints are asked for);
  3. ensembles the per-seed values exactly as the XGBoost path does (mean, +/- 1 std over seeds),
     attaches the same applicability-domain fields, and for regression the KERMT held-out-error
     band when one has been built;
  4. returns only what it could answer. An endpoint missing from the result is served by XGBoost
     by the caller. Nothing here fabricates, defaults or smooths a value.

Classification values are served raw (C0, decisions.md 2026-10-08): the temperature scalers fitted
for KERMT are not applied, matching the XGBoost path where the Platt calibrators are off.
"""

from __future__ import annotations

import logging

import numpy as np
from mars_contracts.endpoints import ENDPOINT_METADATA, Endpoint, TaskType

from serve.kermt_client import ArmValues, KermtClient, KermtUnavailable
from serve.predictor import RealPrediction, applicability_domain
from serve.registry import KERMT_ERROR_BAND_FILENAME, ModelRegistry
from serve.routing import KERMT_ARMS, RoutingTable

logger = logging.getLogger("mars.kermt_router")


class KermtRouter:
    def __init__(self, routing: RoutingTable, client: KermtClient, registry: ModelRegistry) -> None:
        self.routing = routing
        self.client = client
        self.registry = registry

    def served_by_kermt(self) -> frozenset[str]:
        return self.routing.kermt_endpoint_set()

    def predict(self, smiles_standardized: str, endpoint_keys: list[str]) -> dict[str, RealPrediction]:
        wanted = self.routing.kermt_endpoints(endpoint_keys)
        if not wanted:
            return {}
        arms = self.routing.arms_for(endpoint_keys)
        try:
            by_arm = self.client.predict(smiles_standardized, arms)
        except KermtUnavailable:
            return {}  # the client already logged and opened its breaker
        out: dict[str, RealPrediction] = {}
        for endpoint in wanted:
            pred = self._one(endpoint, by_arm.get(self.routing.route(endpoint).kermt_arm), smiles_standardized)
            if pred is not None:
                out[endpoint] = pred
        return out

    def _one(self, endpoint: str, arm: ArmValues | None, smiles_standardized: str) -> RealPrediction | None:
        if arm is None or endpoint not in arm.values:
            logger.warning("KERMT reply has no values for %s", endpoint)
            return None
        task = ENDPOINT_METADATA[Endpoint(endpoint)]["task_type"]
        expected_task = TaskType.CLASSIFICATION if arm.task_type == "classification" else TaskType.REGRESSION
        if task != expected_task or endpoint not in KERMT_ARMS.get(arm.arm, ()):
            logger.error("KERMT arm %s disagrees with the contract for %s (%s)", arm.arm, endpoint, arm.task_type)
            return None
        per_seed = np.array([v for v in arm.values[endpoint] if v is not None], dtype=float)
        if per_seed.size == 0 or not np.all(np.isfinite(per_seed)):
            return None  # not featurizable by KERMT: let XGBoost answer
        mean, std = float(per_seed.mean()), float(per_seed.std())
        in_domain, knn_distance, ad_threshold = applicability_domain(self.registry, endpoint, smiles_standardized)
        band = self.registry.load_error_band(endpoint, KERMT_ERROR_BAND_FILENAME) if task == TaskType.REGRESSION else None
        return RealPrediction(
            endpoint=endpoint,
            value=mean,
            confidence_low=mean - std,
            confidence_high=mean + std,
            in_domain=in_domain,
            knn_distance=knn_distance,
            model_id=arm.model_id,
            n_seeds=int(per_seed.size),
            ad_threshold=ad_threshold,
            heldout_error_halfwidth=band.halfwidth if band else None,
            heldout_error_level=band.level if band else None,
            heldout_error_n=band.n_residuals if band else None,
        )
