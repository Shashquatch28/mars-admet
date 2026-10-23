"""`POST /depict` (frontend ADR-039) - a 2D drawing of a molecule, from `ml/serve/depiction.py`.

Imported the way `conformer_service.py` imports its half of the ml stack: real where rdkit is installed (the built
container), `depiction_available = False` where it is not (the root `.venv`), which the route turns into a 501 rather than a
made-up picture.
"""

from __future__ import annotations

import sys
from pathlib import Path

depiction_available = False
try:
    _ml_root = Path(__file__).resolve().parents[3] / "ml"
    if str(_ml_root) not in sys.path:
        sys.path.insert(0, str(_ml_root))
    from serve.depiction import DEPICTION_VERSION, canonical_smiles, draw_svg  # noqa: E402

    depiction_available = True
except ImportError:
    DEPICTION_VERSION = ""

    def canonical_smiles(smiles: str) -> str:  # pragma: no cover - only reached without rdkit, where the route 501s first
        raise RuntimeError("rdkit is not installed in this environment")

    def draw_svg(canonical: str) -> str:  # pragma: no cover
        raise RuntimeError("rdkit is not installed in this environment")
