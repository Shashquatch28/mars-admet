"""
Explanation of one served prediction, `/molecule/{id}/explain?endpoint=X` (Module 6, ADR-031, ADR-035).

A KERMT-served explanation is a background job (minutes, not milliseconds): `POST` starts or joins it,
`GET` reads it, `DELETE` cancels it. While it runs the body is an `ExplainJobStatus`; when it is done it
is an `ExplainResponse`. An XGBoost-served explanation is instant and answers `POST` with the result.

The model that served the value explains it: `method` and `model_id` say which. An attribution
is signed: positive pushed the model's output UP from its reference, negative pushed it DOWN. It
is never a risk or a favourable/unfavourable judgement, and no field here may be read as one.

Everything below sums: `base_value + structure_total + whole_molecule_total + unmapped_total`
equals `output_value`. `completeness_error` says how far the METHOD's own identity was from holding (see the field). Atom attributions are the additive layer;
fragment attributions are sums over (possibly overlapping) atom sets and do not add up.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from .endpoints import Endpoint


class ExplainMethod(str, Enum):
    TREE_SHAP = "tree_shap"
    INTEGRATED_GRADIENTS = "integrated_gradients"


class ExplainOutputSpace(str, Enum):
    LOG_ODDS = "log_odds"  # XGBoost classification: TreeSHAP on the raw margin
    SCORE = "score"  # KERMT classification: the 0-1 score shown (mean of the two heads' sigmoids)
    NATIVE_UNIT = "native_unit"  # regression: the endpoint's own unit


class FragmentAttribution(BaseModel):
    name: str = Field(..., description="Group name from the fragment catalogue, e.g. 'carboxylic acid' or 'ring system'")
    smarts: str = Field(..., description="The pattern that matched, so the grouping is reproducible")
    atom_indices: list[int] = Field(..., description="Indices into `atom_attributions` (RDKit atom order of smiles_standardized)")
    score: float = Field(..., description="Sum of the member atoms' attributions, in `output_space`. Fragments may overlap: scores do not add up.")


class DescriptorAttribution(BaseModel):
    name: str = Field(..., description="Whole-molecule descriptor name (an RDKit 2D descriptor)")
    value: float | None = Field(default=None, description="This molecule's value for the descriptor; null if it was not finite")
    score: float = Field(..., description="Signed contribution in `output_space`")


class ExplainResponse(BaseModel):
    molecule_id: str
    endpoint: Endpoint
    method: ExplainMethod
    model_id: str = Field(..., description="The artifact explained; equals the `model_id` of the prediction it explains")
    output_space: ExplainOutputSpace
    unit: str | None = Field(default=None, description="Unit of the endpoint for `native_unit`; null otherwise")
    n_seeds: int = Field(..., description="Seeds the attribution was averaged over")
    base_value: float = Field(..., description="Model output at the reference (TreeSHAP expected value; IG baseline output), in `output_space`")
    output_value: float = Field(..., description="Model output being explained, in `output_space`")
    baseline: str = Field(..., description="The reference, in words, so no explanation has a silent baseline")
    atom_attributions: list[float] = Field(..., description="One signed value per atom of smiles_standardized (RDKit order, no hydrogens)")
    fragment_attributions: list[FragmentAttribution]
    whole_molecule_attributions: list[DescriptorAttribution] = Field(
        ..., description="Largest whole-molecule descriptor contributions by absolute size; the rest are in `whole_molecule_rest`"
    )
    whole_molecule_rest: float = Field(..., description="Sum of the descriptor contributions not listed above")
    structure_total: float = Field(..., description="Sum of `atom_attributions`")
    whole_molecule_total: float = Field(..., description="Sum of every descriptor contribution (listed + rest)")
    unmapped_total: float = Field(
        ...,
        description="Part of the output change that is on neither an atom nor a descriptor: fingerprint bits absent from this "
        "molecule or not placeable on atoms (TreeSHAP), or the completeness residual (IG).",
    )
    completeness_error: float = Field(
        ...,
        description="How far the method's own identity was from holding, in `output_space`. Integrated Gradients: the integration residual |sum of attributions - (output_value - base_value)|, which `unmapped_total` carries (so the parts above still sum exactly). TreeSHAP: the additivity error |sum of contributions - the model's own margin|, about 1e-6.",
    )
    converged: bool | None = Field(
        default=None,
        description="Integrated Gradients only: whether `completeness_error` met the service's tolerance after the final step count. A result that did not converge is still returned, flagged, never hidden. Null for TreeSHAP, which has no iteration to converge.",
    )
    seed_agreement: float | None = Field(
        default=None,
        description="Median pairwise cosine similarity of the per-seed atom attributions the average was taken over (1 = every seed agrees, near 0 = unrelated). Null when only one seed was averaged. A summary of how much the seeds disagree, not a guarantee.",
    )
    n_steps: int | None = Field(default=None, description="Integrated Gradients interpolation steps; null for TreeSHAP")
    model_version: str = Field(..., description="Serving version the explanation was computed under (also part of its cache key)")


class ExplainJobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExplainJobStatus(BaseModel):
    """Where a background explanation is. Returned with HTTP 202 while it is queued or running, and from `DELETE`
    (state `cancelled`). A finished job is read as an `ExplainResponse`; a failed one is an error response."""

    job_id: str = Field(..., description="Stable for one (molecule, endpoint, serving version): the same request joins the same job")
    molecule_id: str
    endpoint: Endpoint
    state: ExplainJobState
    queue_position: int | None = Field(default=None, description="1 = next to run; null once it is running or finished")
    seeds_done: int = Field(..., description="Seeds (checkpoints) fully attributed so far")
    seeds_total: int
    stage: str | None = Field(
        default=None,
        description="What it is doing now, in words, e.g. 'seed 2 of 3, 128 steps'. There is deliberately no percentage or "
        "estimate: the step count escalates adaptively, so the total is not known in advance.",
    )
    elapsed_seconds: float = Field(..., description="Since it was submitted")
    submitted_at: datetime
    error: str | None = Field(default=None, description="Why it failed, when it did")
