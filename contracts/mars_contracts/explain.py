"""
Explanation of one served prediction, `GET /molecule/{id}/explain?endpoint=X` (Module 6, ADR-031).

The model that served the value explains it: `method` and `model_id` say which. An attribution
is signed: positive pushed the model's output UP from its reference, negative pushed it DOWN. It
is never a risk or a favourable/unfavourable judgement, and no field here may be read as one.

Everything below sums: `base_value + structure_total + whole_molecule_total + unmapped_total`
equals `output_value` (to `completeness_error`). Atom attributions are the additive layer;
fragment attributions are sums over (possibly overlapping) atom sets and do not add up.
"""

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
        ..., description="|base_value + structure_total + whole_molecule_total + unmapped_total - output_value|; ~0 by construction for TreeSHAP"
    )
    n_steps: int | None = Field(default=None, description="Integrated Gradients interpolation steps; null for TreeSHAP")
    model_version: str = Field(..., description="Serving version the explanation was computed under (also part of its cache key)")
