"""
Phase 0 contract — API route request/response shapes for Module 8's endpoint
table beyond the single `/predict` call (which lives in prediction.py).

Scope of this file: the MVP routes whose shapes the ml/ and api/ tracks build
against before M3. Lazy/Post-MVP routes (`/molecule/{id}/explain`,
`/molecule/{id}/report`) are documented in contracts/API_ROUTES.md but not
modelled here until their owning milestone (M4).

Changing field names here is a breaking change and requires a re-sync.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .endpoints import Endpoint
from .prediction import PredictionResponse


# --- POST /batch/predict (account required; CSV/SDF via multipart) -----------
# The uploaded file is a multipart part, not JSON. These are the non-file
# options that accompany it (sent as form fields or a JSON blob part).
class BatchPredictOptions(BaseModel):
    smiles_column: str | None = Field(
        default=None,
        description="Column name holding SMILES in a CSV upload. None = auto-detect / SDF.",
    )
    endpoints: list[Endpoint] | None = Field(
        default=None, description="Subset to predict. None = all 14."
    )
    retrain_opt_in: bool = Field(
        default=False,
        description="Module 8 per-upload opt-in: allow this data to improve future models. "
        "Default False = no retention beyond serving results.",
    )


class BatchRowResult(BaseModel):
    row_index: int
    smiles_input: str
    ok: bool = Field(..., description="False = this row failed validation/standardization; see error.")
    error: str | None = Field(default=None, description="Non-blocking per-row error message (Module 9 gap-fill #4).")
    prediction: PredictionResponse | None = Field(
        default=None, description="Populated when ok=True."
    )


class BatchPredictResponse(BaseModel):
    """
    Interactive tier (<=1000 molecules): job_id is None, results is populated.
    Async tier (>1000): job_id is set, results is None; poll /batch/progress and
    fetch /batch/results.
    """

    job_id: str | None = None
    status: str = Field(..., description='"done" (interactive) | "queued" | "running" | "failed"')
    total: int
    completed: int = 0
    results: list[BatchRowResult] | None = None


# --- POST /compare (no account; 2-3 molecules) ------------------------------
class CompareRequest(BaseModel):
    smiles: list[str] = Field(..., min_length=2, max_length=3)
    endpoints: list[Endpoint] | None = None


class CompareResponse(BaseModel):
    molecules: list[PredictionResponse]
    per_endpoint_winner: dict[Endpoint, int] | None = Field(
        default=None,
        description="endpoint -> index into `molecules` of the most favourable value. "
        "Direction-of-good is endpoint-specific (e.g. lower clearance vs higher HIA); "
        "the resolution table is finalised in M3/M4. None = not computed.",
    )
