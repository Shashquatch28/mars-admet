"""
Phase 0 contract — locked interface between the ML serving layer (ml/serve) and
the API (api/). The inference wrapper must produce output matching
EndpointPrediction/PredictionResponse; the /predict route must accept
PredictionRequest and return PredictionResponse.
Changing field names here is a breaking change: it also breaks
frontend/src/types/contracts.ts (checked by contracts/tests/test_frontend_drift.py).
"""

from datetime import datetime

from pydantic import BaseModel, Field

from .endpoints import Endpoint


class PredictionRequest(BaseModel):
    smiles: str = Field(..., description="Input SMILES string, not yet standardized")
    endpoints: list[Endpoint] | None = Field(
        default=None,
        description="Subset of endpoints to predict. None = all 14 ML endpoints, plus the rule-based SA score when the server can compute it.",
    )


class EndpointPrediction(BaseModel):
    endpoint: Endpoint
    value: float = Field(..., description="Regression value, or classification score in [0,1]. The score is a bounded model output, "
        "not a validated probability: calibration has not been shown per endpoint (ADR-023).")
    unit: str | None = Field(default=None, description="e.g. 'logS', 'logP', 'mL/min/kg'; null for classification")
    confidence_low: float = Field(..., description="Lower bound of ensemble-spread confidence interval")
    confidence_high: float = Field(..., description="Upper bound of ensemble-spread confidence interval")
    in_domain: bool = Field(..., description="Module 5 k-NN applicability-domain flag for THIS endpoint's training set")
    knn_distance: float = Field(..., description="Mean 5-NN Tanimoto distance used to compute in_domain")
    ad_threshold: float | None = Field(
        default=None,
        description="The per-endpoint cutoff `in_domain` was judged against: the 90th percentile of the "
        "endpoint's training set's own leave-one-out 5-NN distances (Module 5). `in_domain` is "
        "`knn_distance <= ad_threshold`. Null when no applicability-domain index exists for the endpoint "
        "(stub-served, rule-based): there is no cutoff to draw, and clients must not invent one. "
        "Additive field (Q19); defaults to None so existing callers are unaffected.",
    )
    heldout_error_halfwidth: float | None = Field(
        default=None,
        description="Regression endpoints only. Half-width, in the endpoint's own unit, of the held-out-error band "
        "(ADR-024): `heldout_error_level` of the absolute errors the promoted seeds made on their own "
        "scaffold-held-out validation folds were at most this large. One constant per endpoint, taken from the "
        "pooled out-of-fold residuals; it is NOT a per-molecule interval and NOT a guarantee for this molecule "
        "(it under-covers out-of-domain molecules, so read it beside `in_domain`). Null for classification, "
        "stub-served and rule-based rows, and for a regression endpoint whose band has not been built: clients "
        "must not invent one. Additive field; defaults to None so existing callers are unaffected.",
    )
    heldout_error_level: float | None = Field(
        default=None,
        description="The share of held-out errors that fell within `heldout_error_halfwidth` (e.g. 0.9). Null exactly "
        "when `heldout_error_halfwidth` is null.",
    )
    heldout_error_n: int | None = Field(
        default=None,
        description="How many pooled held-out residuals the half-width was taken over. Null exactly when "
        "`heldout_error_halfwidth` is null.",
    )
    model_id: str = Field(
        default="stub-v0",
        description="Which trained artifact actually served THIS endpoint (e.g. "
        "'mars-xgboost-ecfp-desc-v1' vs 'stub-v0'). Endpoints in one response can "
        "differ here when only some have a promoted trained model (Module 8 "
        "routing table, M3) — the top-level PredictionResponse.model_version "
        "describes the serving generation as a whole, this field is per-endpoint "
        "ground truth. Additive field (M3); defaults to the M0 stub value so "
        "existing callers are unaffected.",
    )


class PredictionResponse(BaseModel):
    smiles_input: str
    smiles_standardized: str
    molecule_id: str = Field(..., description="Hash of standardized SMILES; used for /molecule/{id}/3d and /explain lookups")
    predictions: list[EndpointPrediction]
    model_version: str = Field(..., description="Routing-table version tag; also part of the Redis cache key (Module 8)")
    served_at: datetime
    cache_hit: bool = False


class BatchJobStatus(BaseModel):
    job_id: str
    status: str  # "queued" | "running" | "done" | "failed"
    total: int
    completed: int
    results_url: str | None = None
