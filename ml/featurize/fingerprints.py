"""
Module 3 Stage 3 — Morgan / ECFP fingerprints.

Blueprint requirements this implements:

  * radius = 2
  * 2048 bits
  * ``useChirality=True`` — the RDKit default is OFF; two enantiomers otherwise
    produce identical ECFP4 fingerprints, and CYP2C9 is in-scope with a real
    stereoselective effect (blueprint Module 3 §Stereochemistry).
  * Deterministic (same input SMILES → same bit vector on any run, any machine).
  * Batched: designed for lists, not one-at-a-time.

Feeds:

  * classical ML baselines (XGBoost / RF on ECFP), blueprint Module 4
  * k-NN applicability domain distance in ECFP4 space, blueprint Module 5
  * chemical-space similarity search (Module 12 core: analog surfacing)

Design decisions
----------------

**Why the new ``rdFingerprintGenerator`` API and not ``AllChem.GetMorganFingerprintAsBitVect``?**
The generator API is what RDKit 2023+ documents as the supported entry point
(the older function is now deprecation-flagged in some releases). The generator
also returns a plain NumPy array directly, which avoids a per-call SparseIntVect
→ ExplicitBitVect conversion when we assemble batches into a matrix.

**Why we *don't* import the standardizer here.**
Fingerprints run on already-standardized SMILES. Downstream callers (dedup,
featurization for training, k-NN AD, batch prediction) are expected to have
already produced canonical, standardized output through
``featurize.standardize.standardize``. Duplicating the pipeline here would
either be silent double-work or an inconsistent second implementation.

The FP configuration is versioned (``MORGAN_FP_VERSION``); it must be part of
any downstream cache key. A change to radius / n_bits / chirality flag → new
version → cache invalidation.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import numpy as np
from rdkit import Chem, RDLogger
from rdkit.Chem import rdFingerprintGenerator

_LOGGER = RDLogger.logger()
_LOGGER.setLevel(RDLogger.CRITICAL)


MORGAN_FP_VERSION = "mars-morgan-r2-2048-chirality-v1"


@dataclass(frozen=True)
class MorganConfig:
    """Blueprint Module 3 Stage 3 defaults; treat as immutable in downstream code."""

    radius: int = 2
    n_bits: int = 2048
    use_chirality: bool = True
    use_features: bool = False  # standard ECFP, not FCFP
    version: str = MORGAN_FP_VERSION

    def cache_key(self) -> str:
        """A one-line string safe for use as a cache-key component."""
        return (
            f"{self.version}|r={self.radius}|n={self.n_bits}"
            f"|chi={int(self.use_chirality)}|feat={int(self.use_features)}"
        )


def _make_generator(cfg: MorganConfig):
    return rdFingerprintGenerator.GetMorganGenerator(
        radius=cfg.radius,
        fpSize=cfg.n_bits,
        includeChirality=cfg.use_chirality,
        useBondTypes=True,
    )


def morgan_fingerprint(
    smiles: str,
    config: MorganConfig | None = None,
) -> np.ndarray | None:
    """Return a ``(n_bits,) uint8`` bit vector, or ``None`` for an invalid SMILES.

    Assumes ``smiles`` is already standardized (see module docstring).
    """
    cfg = config or MorganConfig()
    mol = Chem.MolFromSmiles(smiles) if smiles else None
    if mol is None:
        return None
    gen = _make_generator(cfg)
    fp = gen.GetFingerprintAsNumPy(mol)
    # rdFingerprintGenerator returns uint8; enforce for downstream stability
    if fp.dtype != np.uint8:
        fp = fp.astype(np.uint8, copy=False)
    return fp


def morgan_fingerprints_batch(
    smiles_list: Iterable[str],
    config: MorganConfig | None = None,
) -> tuple[np.ndarray, list[int]]:
    """Return ``(matrix, dropped_indices)``.

    ``matrix`` is ``(n_valid, n_bits) uint8``; ``dropped_indices`` are positions
    in the input list that failed to parse (kept out of the matrix rather than
    silently zeroed — a zero row would look like a valid molecule with no
    on-bits). Downstream callers align labels/metadata using ``dropped_indices``.
    """
    cfg = config or MorganConfig()
    gen = _make_generator(cfg)

    rows: list[np.ndarray] = []
    dropped: list[int] = []
    for idx, smi in enumerate(smiles_list):
        mol = Chem.MolFromSmiles(smi) if smi else None
        if mol is None:
            dropped.append(idx)
            continue
        rows.append(gen.GetFingerprintAsNumPy(mol))

    if not rows:
        return np.zeros((0, cfg.n_bits), dtype=np.uint8), dropped

    stacked = np.vstack(rows)
    if stacked.dtype != np.uint8:
        stacked = stacked.astype(np.uint8, copy=False)
    return stacked, dropped


def tanimoto_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Tanimoto similarity between two same-length uint8 bit vectors.

    Reused by Module 5's k-NN AD when it lands (Run 4+ / M2).
    """
    if a.shape != b.shape:
        raise ValueError(f"shape mismatch: {a.shape} vs {b.shape}")
    a_bool = a.astype(bool)
    b_bool = b.astype(bool)
    inter = int(np.logical_and(a_bool, b_bool).sum())
    union = int(np.logical_or(a_bool, b_bool).sum())
    return inter / union if union else 0.0


def summary(matrix: np.ndarray) -> dict[str, Any]:
    """Cheap batch summary — mean on-bit count, bits with any signal. Diagnostic
    only; not part of any cache key."""
    if matrix.size == 0:
        return {"n": 0, "mean_on_bits": 0.0, "active_bit_positions": 0}
    on = matrix.astype(bool)
    return {
        "n": int(matrix.shape[0]),
        "n_bits": int(matrix.shape[1]),
        "mean_on_bits": float(on.sum(axis=1).mean()),
        "active_bit_positions": int(on.any(axis=0).sum()),
    }
