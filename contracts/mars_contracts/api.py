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
        default=None, description="Subset to predict. None = all 14 ML endpoints, plus the rule-based SA score when the server can compute it."
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
    Interactive tier (<= the service's interactive threshold, 100 by default): job_id is None, results is populated.
    Async tier (above that threshold): job_id is set, results is None; poll /batch/progress and
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


# --- GET /generations (no account; ADR-026 parts 1-2) ---------------------------
class GenerationsResponse(BaseModel):
    """Which model generation this deployment serves. Minimal on purpose: `available` holds
    only `active` until a second generation exists, so a client that renders a picker from
    it shows no choice that is not real. `/predict` takes no generation parameter yet."""

    active: str = Field(..., description="the deployed generation: the same string stamped on predictions as `model_version`")
    available: list[str] = Field(..., description="every generation this deployment can serve; today exactly [active]")
