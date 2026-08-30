"""
Stub predictor — returns contract-shaped fake predictions so the API and
frontend can be built and demoed end-to-end before Person A's trained
models are ready. Swap this out at the A -> B integration sync (Phase 2,
sync #1) for the real inference wrapper. Do NOT let real logic leak in
here; keep it deterministic and obviously fake.
"""

import hashlib
import random
from datetime import UTC, datetime

from mars_contracts import (
    ENDPOINT_METADATA,
    ML_ENDPOINTS,
    Endpoint,
    EndpointPrediction,
    PredictionResponse,
    TaskType,
)


def _molecule_id(smiles_standardized: str) -> str:
    return hashlib.sha256(smiles_standardized.encode()).hexdigest()[:16]


def standardize_stub(smiles: str) -> str:
    # Real standardization (RDKit canonicalize/salt-strip/tautomer-normalize)
    # lives in ml/featurize once Person A builds Module 3 Stage 1.
    return smiles.strip()


def predict_stub(smiles: str, endpoints: list[Endpoint] | None = None) -> PredictionResponse:
    smiles_std = standardize_stub(smiles)
    mol_id = _molecule_id(smiles_std)
    rng = random.Random(mol_id)  # deterministic per molecule, not truly random

    targets = endpoints or ML_ENDPOINTS
    preds = []
    for ep in targets:
        meta = ENDPOINT_METADATA[ep]
        if meta["task_type"] == TaskType.CLASSIFICATION:
            value = round(rng.uniform(0.05, 0.95), 3)
        elif meta["task_type"] == TaskType.RULE_BASED:
            continue  # SA score served by rdkit rule, not the ML stub
        else:
            value = round(rng.uniform(-2.0, 2.0), 3)
        spread = round(abs(rng.gauss(0, 0.1)), 3)
        preds.append(
            EndpointPrediction(
                endpoint=ep,
                value=value,
                unit=None,
                confidence_low=round(value - spread, 3),
                confidence_high=round(value + spread, 3),
                in_domain=rng.random() > 0.1,
                knn_distance=round(rng.uniform(0.0, 0.5), 3),
            )
        )

    return PredictionResponse(
        smiles_input=smiles,
        smiles_standardized=smiles_std,
        molecule_id=mol_id,
        predictions=preds,
        model_version="stub-v0",
        served_at=datetime.now(UTC),
        cache_hit=False,
    )
