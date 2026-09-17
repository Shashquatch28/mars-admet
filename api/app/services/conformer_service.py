"""Module 8 `GET /molecule/{id}/3d` — real conformer generation, reusing
Module 3 Stage 5 (`ml/featurize/conformers.py`, ETKDGv3 + MMFF94/UFF,
already built and tested in M1). Lazily imports the ml stack the same way
`prediction_service.py` does — real when rdkit is installed (the container),
`conformer_available=False` otherwise (root `.venv`).
"""

from __future__ import annotations

import sys
from pathlib import Path

from mars_contracts import ConformerResponse

conformer_available = False
try:
    _ml_root = Path(__file__).resolve().parents[3] / "ml"
    if str(_ml_root) not in sys.path:
        sys.path.insert(0, str(_ml_root))
    from featurize.conformers import generate_conformer  # noqa: E402

    conformer_available = True
except ImportError:
    pass


def get_conformer(molecule_id: str, smiles_standardized: str) -> ConformerResponse:
    """Raises `RuntimeError` if the ml stack isn't available (callers must
    check `conformer_available` first) and `ValueError` if conformer
    generation genuinely fails for this molecule (e.g. embedding failure) —
    the latter is a real per-molecule outcome, not fabricated as a success.
    """
    if not conformer_available:
        raise RuntimeError("rdkit is not installed in this environment — cannot generate a conformer")

    result = generate_conformer(smiles_standardized)
    if not result.ok:
        raise ValueError(f"conformer generation failed ({result.reason})")
    return ConformerResponse(**result.to_contract_dict(molecule_id))
