"""
Phase 0 contract — locked interface between ML (Person A) and API (Person B).
A's inference wrapper must produce output matching EndpointPrediction/PredictionResponse.
B's /predict route must accept PredictionRequest and return PredictionResponse.
Changing field names here is a breaking change and requires a re-sync.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from .endpoints import Endpoint


class PredictionRequest(BaseModel):
    smiles: str = Field(..., description="Input SMILES string, not yet standardized")
    endpoints: list[Endpoint] | None = Field(
        default=None,
        description="Subset of endpoints to predict. None = all 14.",
    )


class EndpointPrediction(BaseModel):
    endpoint: Endpoint
    value: float = Field(..., description="Regression value, or classification probability [0,1]")
    unit: str | None = Field(default=None, description="e.g. 'logS', 'logP', 'mL/min/kg'; null for classification")
    confidence_low: float = Field(..., description="Lower bound of ensemble-spread confidence interval")
    confidence_high: float = Field(..., description="Upper bound of ensemble-spread confidence interval")
    in_domain: bool = Field(..., description="Module 5 k-NN applicability-domain flag for THIS endpoint's training set")
    knn_distance: float = Field(..., description="Mean 5-NN Tanimoto distance used to compute in_domain")


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
