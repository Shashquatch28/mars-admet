"""
M3 contract — Module 13 persistence (saved molecules/reports), pinned to the
blueprint's Postgres schema (`users`, `saved_molecules`, `saved_reports`,
`batch_jobs`). Snapshot-on-save: the client sends back the `PredictionResponse`
/ `BatchPredictResponse` it already received, and the server freezes it into
`predictions_snapshot` / `results_snapshot` at that moment rather than
re-running inference or keeping a live pointer into the ephemeral cache/R2
bucket (Module 13 "save-vs-purge race condition" fix).

Changing field names here is a breaking change and requires a re-sync.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .api import BatchPredictResponse
from .prediction import PredictionResponse


class SaveMoleculeRequest(BaseModel):
    prediction: PredictionResponse = Field(..., description="The prediction result to freeze, exactly as received from /predict")
    label: str | None = None
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)


class SavedMoleculeResponse(BaseModel):
    id: str
    smiles: str = Field(..., description="Standardized SMILES, from predictions_snapshot")
    label: str | None
    notes: str | None
    tags: list[str]
    predictions_snapshot: PredictionResponse
    model_version: str
    created_at: datetime
    updated_at: datetime


class SaveReportRequest(BaseModel):
    type: str = Field(..., description='"single" | "batch"')
    source_batch_job_id: str | None = Field(
        default=None, description="Provenance only (job-history display) — NOT a live data dependency once saved"
    )
    results: BatchPredictResponse | PredictionResponse = Field(
        ..., description="The result set to freeze into results_snapshot"
    )
    molecule_ids: list[str] = Field(default_factory=list, description="FK array -> saved_molecules, if any of this report's molecules were also saved individually")
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)


class SavedReportResponse(BaseModel):
    id: str
    type: str
    source_batch_job_id: str | None
    results_snapshot: dict = Field(..., description="Frozen BatchPredictResponse or PredictionResponse, as originally saved")
    molecule_ids: list[str]
    notes: str | None
    tags: list[str]
    created_at: datetime


class DeleteAccountRequest(BaseModel):
    password: str = Field(..., description="Re-confirmation of password required before a cascading, irreversible delete")


__all__ = [
    "SaveMoleculeRequest",
    "SavedMoleculeResponse",
    "SaveReportRequest",
    "SavedReportResponse",
    "DeleteAccountRequest",
]
