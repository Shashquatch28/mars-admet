"""Held-out-error band for the regression endpoints (frontend ADR-024, AIMS decisions.md 2026-10-08).

The served `confidence_low` / `confidence_high` are a seed spread, not an error range: on the five
regression endpoints the printed mean +/- 1 std contained the true value for 9-14% of held-out
molecules. This module builds the replacement that can be labelled with what was measured:

    one constant half-width per endpoint, taken from the pooled absolute residuals of the promoted
    seeds on their own scaffold-held-out validation folds ("90% of held-out errors fell within +/-X").

It is a minimal split-conformal-style construction, not full conformal prediction. Three things it
does not claim, and callers must not claim for it:

  * it is marginal, not per-molecule: every molecule of an endpoint gets the same half-width;
  * it is not a guarantee for an out-of-domain molecule (the band under-covers there, which is why the
    applicability-domain flag stays beside it);
  * it describes the error of the seed ensemble mean, which is what is served as `value`.

`build_error_band` is the only place residuals are computed; `ErrorBand.save` writes
`<artifacts>/<endpoint>/error_band.json`, which `serve.registry.ModelRegistry.load_error_band` reads.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

ERROR_BAND_VERSION = "mars-error-band-v1"
ERROR_BAND_FILENAME = "error_band.json"
DEFAULT_LEVEL = 0.90
METHOD = "pooled out-of-fold absolute residuals of the promoted seeds, split-conformal quantile"


class _Predictor(Protocol):
    def predict(self, smiles: list[str]) -> np.ndarray: ...


@dataclass(frozen=True)
class ErrorBand:
    endpoint: str
    level: float  # fraction of held-out errors that fell within +/- halfwidth, by construction
    halfwidth: float  # in the endpoint's own unit
    n_residuals: int  # pooled held-out residuals the quantile was taken over
    n_seeds: int
    version: str = ERROR_BAND_VERSION
    method: str = METHOD

    def save(self, path: Path | str) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path | str) -> ErrorBand:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if raw.get("version") != ERROR_BAND_VERSION:
            raise ValueError(f"{path}: unsupported error-band version {raw.get('version')!r}")
        return cls(**raw)


def conformal_halfwidth(residuals: Sequence[float] | np.ndarray, level: float) -> float:
    """The ceil((n+1)*level)-th smallest absolute residual.

    Refuses rather than extrapolating: with too few residuals that rank exceeds n and the honest
    answer is that the level cannot be stated.
    """
    if not 0.0 < level < 1.0:
        raise ValueError(f"level must be in (0, 1), got {level!r}")
    r = np.sort(np.abs(np.asarray(residuals, dtype=float)))
    if r.size == 0 or np.isnan(r).any():
        raise ValueError("residuals must be non-empty and free of NaN")
    k = math.ceil((r.size + 1) * level)
    if k > r.size:
        raise ValueError(f"{r.size} residuals are too few for a {level:.0%} band (needs at least {math.ceil(level / (1 - level))})")
    return float(r[k - 1])


def pooled_residuals(
    models_by_seed: Mapping[int, _Predictor],
    folds: Sequence[tuple[int, list[str], list[str]]],
    labels: Mapping[str, float],
) -> np.ndarray:
    """Each seed's absolute residuals on its own validation fold, pooled.

    A seed's model never trained on its validation fold (that is what the scaffold partition is for),
    so these are held-out errors. Rows the model could not featurize (NaN) are dropped, not imputed.
    """
    out: list[float] = []
    for seed, _train, valid in folds:
        if seed not in models_by_seed:
            raise ValueError(f"no promoted model for seed {seed}; the band needs every fold's model")
        pred = np.asarray(models_by_seed[seed].predict(valid), dtype=float)
        y = np.array([labels[s] for s in valid], dtype=float)
        ok = ~np.isnan(pred)
        out.extend(np.abs(y[ok] - pred[ok]).tolist())
    return np.array(out, dtype=float)


def build_error_band(
    endpoint: str,
    models_by_seed: Mapping[int, _Predictor],
    folds: Sequence[tuple[int, list[str], list[str]]],
    labels: Mapping[str, float],
    *,
    level: float = DEFAULT_LEVEL,
) -> ErrorBand:
    residuals = pooled_residuals(models_by_seed, folds, labels)
    return ErrorBand(
        endpoint=endpoint,
        level=level,
        halfwidth=conformal_halfwidth(residuals, level),
        n_residuals=int(residuals.size),
        n_seeds=len(folds),
    )
