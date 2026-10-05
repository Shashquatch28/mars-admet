"""Rule-based (non-ML) endpoint computation for the serving layer.

`synthetic_accessibility` is a computed rule, not a model prediction: the
Ertl & Schuffenhauer (2009) SA score, 1 (easy to make) to 10 (very hard),
from RDKit's bundled Contrib `SA_Score`. It has no training set, no ensemble
and no applicability domain, so nothing here touches the model registry.

The scorer ships inside the `rdkit` wheel (`RDConfig.RDContribDir`), so this
adds no dependency to `requirements-serving.txt`. It is loaded by file path
rather than by editing `sys.path`, so the global import namespace stays clean.
If it cannot be loaded or the molecule cannot be parsed this returns `None`
and the caller reports the endpoint as not returned — never a made-up value.
"""

from __future__ import annotations

import importlib.util
import math
import os
import warnings
from functools import lru_cache
from types import ModuleType

from rdkit import Chem
from rdkit.Chem import RDConfig

SA_MODEL_ID = "rdkit-sascore"
SA_UNIT = "SA score"


@lru_cache(maxsize=1)
def _load_sascorer() -> ModuleType | None:
    path = os.path.join(RDConfig.RDContribDir, "SA_Score", "sascorer.py")
    if not os.path.isfile(path):
        warnings.warn(f"RDKit SA_Score contrib not found at {path}", stacklevel=2)
        return None
    spec = importlib.util.spec_from_file_location("mars_rdkit_sascorer", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # sascorer resolves fpscores.pkl.gz from its own __file__
    return module


def compute_sa_score(smiles_standardized: str) -> float | None:
    """SA score for an already-standardized SMILES, or None if not computable."""
    scorer = _load_sascorer()
    if scorer is None:
        return None
    mol = Chem.MolFromSmiles(smiles_standardized)
    if mol is None or mol.GetNumAtoms() == 0:  # "" parses to a valid zero-atom mol
        return None
    score = scorer.calculateScore(mol)
    if score is None or not math.isfinite(score):
        return None
    return float(score)
