"""
Module 3 Stage 4 — RDKit 2D physicochemical descriptors.

Blueprint requirements this implements:

  * ~200 RDKit 2D descriptors (MolWt, TPSA, logP, HBD/HBA, rotatable bonds, …).
  * **Deterministic descriptor ordering.**
  * **Stable feature names** — no silent feature-column drift.
  * Invalid / undefined descriptor values handled **explicitly** (non-finite →
    recorded, not silently passed through as inf/NaN into a model).
  * The descriptor configuration is **versionable** — the exact frozen name list
    is hashed into ``DESCRIPTOR_SET_SHA`` and into the cache key.

Stereo note (blueprint Module 3): 2D descriptors are stereo-insensitive by
construction (MolWt, TPSA, logP, HBD/HBA, ring counts, …). No chirality handling
is needed or possible here — that is expected, not an omission.

Design decisions
----------------

**Why the full ``Descriptors._descList`` (217) rather than a hand-picked ~200?**
The blueprint says "~200 … MolWt, TPSA, logP, HBD/HBA, rotatable bonds, etc." —
i.e. the standard RDKit 2D descriptor block, not a curated subset. Taking the
whole list (a) removes a subjective selection step that would itself need
justifying, (b) is what every RDKit-based ADMET baseline in the literature uses,
and (c) is trivially reproducible. The list is *frozen at import time* into
``DESCRIPTOR_NAMES`` (sorted), so a future RDKit that adds/removes a descriptor
does not silently change MARS's feature matrix — the version check will catch it
(``assert_descriptor_set_matches``).

**Non-finite handling.** A handful of descriptors (notably ``Ipc``) can overflow
to ``inf`` on large molecules, and a few can be ``NaN`` for degenerate graphs.
We do NOT drop those columns (that would be silent column drift) and we do NOT
pass inf/NaN downstream. Instead ``descriptor_row`` returns the raw values plus
a ``non_finite`` dict naming exactly which descriptors were non-finite for that
molecule; ``descriptor_matrix`` additionally returns a boolean mask so a
training pipeline can impute per-column with a documented strategy rather than
discovering NaNs mid-fit.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import numpy as np
from rdkit import Chem, RDLogger
from rdkit.Chem import Descriptors
from rdkit.ML.Descriptors import MoleculeDescriptors

_LOGGER = RDLogger.logger()
_LOGGER.setLevel(RDLogger.CRITICAL)


# Frozen, sorted list of every RDKit 2D descriptor available at import time.
DESCRIPTOR_NAMES: tuple[str, ...] = tuple(sorted(n for n, _ in Descriptors._descList))
DESCRIPTOR_COUNT: int = len(DESCRIPTOR_NAMES)
DESCRIPTOR_SET_SHA: str = hashlib.sha256(
    "\n".join(DESCRIPTOR_NAMES).encode("utf-8")
).hexdigest()

DESCRIPTOR_VERSION = "mars-rdkit2d-v1"

_CALCULATOR = MoleculeDescriptors.MolecularDescriptorCalculator(list(DESCRIPTOR_NAMES))


@dataclass(frozen=True)
class DescriptorConfig:
    version: str = DESCRIPTOR_VERSION
    descriptor_set_sha: str = DESCRIPTOR_SET_SHA
    count: int = DESCRIPTOR_COUNT

    def cache_key(self) -> str:
        return f"{self.version}|n={self.count}|set={self.descriptor_set_sha[:16]}"


@dataclass(frozen=True)
class DescriptorRow:
    smiles: str
    values: np.ndarray  # (DESCRIPTOR_COUNT,) float64 — raw, may contain inf/nan
    non_finite: dict[str, float]  # descriptor name -> the offending raw value

    @property
    def ok(self) -> bool:
        return self.values.size == DESCRIPTOR_COUNT


def assert_descriptor_set_matches(config: DescriptorConfig) -> None:
    """Raise if the running RDKit's descriptor set differs from what a cache /
    lockfile was built against."""
    if config.descriptor_set_sha != DESCRIPTOR_SET_SHA:
        raise RuntimeError(
            "RDKit 2D descriptor set has changed since this config was created "
            f"(expected {config.descriptor_set_sha[:16]}, running "
            f"{DESCRIPTOR_SET_SHA[:16]}). Feature-column drift — bump "
            "DESCRIPTOR_VERSION and re-featurize."
        )


def descriptor_row(smiles: str, config: DescriptorConfig | None = None) -> DescriptorRow | None:
    """Compute the descriptor vector for one standardized SMILES.

    Returns ``None`` for an unparseable SMILES. Never raises for descriptor-level
    numerical issues — non-finite values are captured in ``non_finite``.
    """
    _ = config  # only used for the cache key; calculation is fixed
    mol = Chem.MolFromSmiles(smiles) if smiles else None
    if mol is None:
        return None
    raw = _CALCULATOR.CalcDescriptors(mol)
    values = np.asarray(raw, dtype=np.float64)
    non_finite = {
        DESCRIPTOR_NAMES[i]: float(v)
        for i, v in enumerate(raw)
        if not math.isfinite(v)
    }
    return DescriptorRow(smiles=smiles, values=values, non_finite=non_finite)


def descriptor_matrix(
    smiles_list: Iterable[str],
    config: DescriptorConfig | None = None,
) -> tuple[np.ndarray, np.ndarray, list[int], list[dict[str, float]]]:
    """Batched descriptor computation.

    Returns ``(matrix, finite_mask, dropped_indices, non_finite_per_row)``:
      * ``matrix``      — ``(n_valid, DESCRIPTOR_COUNT) float64`` raw values
      * ``finite_mask`` — same shape, ``True`` where the value is finite
      * ``dropped_indices`` — input positions that failed to parse (same
        convention as the graph / fingerprint batch APIs)
      * ``non_finite_per_row`` — per surviving row, ``{descriptor: value}``

    The matrix keeps raw values (inf/nan included) on purpose — imputation is a
    modelling decision (Module 4), not a featurization one. ``finite_mask`` makes
    that decision explicit and auditable.
    """
    cfg = config or DescriptorConfig()
    assert_descriptor_set_matches(cfg)

    rows: list[np.ndarray] = []
    nf_list: list[dict[str, float]] = []
    dropped: list[int] = []
    for idx, smi in enumerate(smiles_list):
        r = descriptor_row(smi, cfg)
        if r is None:
            dropped.append(idx)
            continue
        rows.append(r.values)
        nf_list.append(r.non_finite)

    if not rows:
        empty = np.zeros((0, DESCRIPTOR_COUNT), dtype=np.float64)
        return empty, np.zeros((0, DESCRIPTOR_COUNT), dtype=bool), dropped, []

    matrix = np.vstack(rows)
    finite_mask = np.isfinite(matrix)
    return matrix, finite_mask, dropped, nf_list


def summary(matrix: np.ndarray, finite_mask: np.ndarray) -> dict[str, Any]:
    if matrix.size == 0:
        return {"n": 0, "n_descriptors": DESCRIPTOR_COUNT, "columns_with_non_finite": 0}
    col_has_nf = (~finite_mask).any(axis=0)
    return {
        "n": int(matrix.shape[0]),
        "n_descriptors": int(matrix.shape[1]),
        "columns_with_non_finite": int(col_has_nf.sum()),
        "non_finite_column_names": [
            DESCRIPTOR_NAMES[i] for i in np.flatnonzero(col_has_nf)
        ],
        "total_non_finite_cells": int((~finite_mask).sum()),
    }
