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


# --- POST /depict (no account; frontend ADR-039) ----------------------------------
class DepictRequest(BaseModel):
    """A molecule to draw. The response is `image/svg+xml`, not JSON, so it has no response model (like the report's PDF):
    plain black line art, one ink, nothing highlighted or labelled. POST so the SMILES stays out of URLs and logs."""

    smiles: str = Field(
        ...,
        description="Input SMILES string; drawn from its RDKit canonical form, so every way of writing a molecule gives one drawing",
    )


# --- GET /limits (no account; frontend ADR-034 item 8) --------------------------
class LimitsResponse(BaseModel):
    """The deployed service's policy numbers, so no client writes them into its own copy. Each is the
    setting the service itself enforces (`batch_size_cap`, `batch_interactive_threshold`,
    `batch_upload_retention_hours`, `rate_limit_anon_per_minute`)."""

    batch_size_cap: int = Field(..., description="most molecules one batch file may hold; larger files are refused")
    batch_interactive_threshold: int = Field(
        ...,
        description="largest batch answered inside the upload request; larger files are queued as a job with progress",
    )
    batch_result_retention_hours: int = Field(
        ..., description="how long the results of a queued batch job are kept; smaller batches are never stored"
    )
    anon_predict_rate_per_minute: int = Field(..., description="single-molecule predictions per minute per IP without an account")


# --- GET /generations (no account; ADR-026 parts 1-2) ---------------------------
class GenerationsResponse(BaseModel):
    """Which model generation this deployment serves. Minimal on purpose: `available` holds
    only `active` until a second generation exists, so a client that renders a picker from
    it shows no choice that is not real. `/predict` takes no generation parameter yet."""

    active: str = Field(..., description="the deployed generation: the same string stamped on predictions as `model_version`")
    available: list[str] = Field(..., description="every generation this deployment can serve; today exactly [active]")
    kermt_endpoints: list[str] = Field(
        default_factory=list,
        description="endpoint names this deployment routes to KERMT (empty when KERMT serving is off). Provenance, "
        "not a ranking: a row's own `model_id` says what actually answered it, and differs from this when the "
        "KERMT service did not answer and XGBoost served the endpoint for that request.",
    )
