"""Exact TreeSHAP for the promoted XGBoost seeds (ADR-031: the serving model explains).

The feature matrix is [217 RDKit descriptors | 2048 Morgan bits] (`models.xgboost_model`). The
descriptor part is whole-molecule and stays whole-molecule; the Morgan part is placed on atoms
through the environments that set each bit (`explain.structure.bits_to_atoms`). Contributions are
averaged over the promoted seeds, which is what the served value is (mean over seeds), except that
a classifier is explained on its raw margin (log-odds): the sigmoid of a mean margin is not the mean
of the sigmoids, so the explained quantity is reported as `log_odds`, not as the displayed score.
"""

from __future__ import annotations

import numpy as np
from featurize.descriptors import DESCRIPTOR_COUNT, DESCRIPTOR_NAMES
from featurize.fingerprints import MorganConfig
from mars_contracts.endpoints import ENDPOINT_METADATA, Endpoint, TaskType
from rdkit import Chem

from explain.result import ExplanationResult, assemble
from explain.structure import bits_to_atoms

BASELINE_TEXT = (
    "TreeSHAP expected value: each tree's cover-weighted mean output over its own training data, "
    "summed over trees and averaged over the promoted seeds. Not a molecule."
)


def explain_xgboost(registry, endpoint_key: str, smiles_standardized: str) -> ExplanationResult | None:
    """Explain one endpoint for one molecule, or None when the registry has no promoted seed for it.

    Raises ValueError when the molecule cannot be parsed or featurized, like `predict_endpoint`.
    """
    models = registry.load_models(endpoint_key)
    if not models:
        return None
    mol = Chem.MolFromSmiles(smiles_standardized)
    if mol is None:
        raise ValueError(f"Invalid SMILES: {smiles_standardized!r}")

    keys = {m.feature_key for m in models}
    if len(keys) != 1:
        raise ValueError(f"{endpoint_key}: promoted seeds disagree on their feature set: {sorted(keys)}")
    feat, valid_idx, _dropped = models[0].prepare([smiles_standardized])
    if not valid_idx:
        raise ValueError(f"Featurization failed for {endpoint_key}: {smiles_standardized!r}")

    per_seed = np.stack([m.contributions_prepared(feat)[0] for m in models])  # (seeds, features + 1)
    contribs = per_seed.mean(axis=0)
    n_features = feat.shape[1]
    morgan_cfg = MorganConfig()
    if n_features != DESCRIPTOR_COUNT + morgan_cfg.n_bits:
        raise ValueError(f"Unexpected feature width {n_features}")

    descriptor_scores = contribs[:DESCRIPTOR_COUNT]
    bit_scores = contribs[DESCRIPTOR_COUNT:n_features]
    atom_scores, unplaced = bits_to_atoms(mol, bit_scores, morgan_cfg)

    task_type = ENDPOINT_METADATA[Endpoint(endpoint_key)]["task_type"]
    return assemble(
        endpoint=endpoint_key,
        method="tree_shap",
        model_id=models[0].model_id,
        output_space="log_odds" if task_type == TaskType.CLASSIFICATION else "native_unit",
        n_seeds=len(models),
        base_value=float(contribs[-1]),
        output_value=float(contribs.sum()),
        baseline=BASELINE_TEXT,
        mol=mol,
        atom_scores=atom_scores,
        descriptor_names=list(DESCRIPTOR_NAMES),
        descriptor_values=feat[0, :DESCRIPTOR_COUNT],
        descriptor_scores=descriptor_scores,
        unmapped_total=unplaced,
    )
