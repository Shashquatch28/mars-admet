"""
Per-column, NaN-aware target scaling for a mixed classification/regression run.

Why this exists
---------------
Stock KERMT fits ONE ``StandardScaler`` over *all* target columns when
``dataset_type == 'regression'`` (``task/train.py::load_data``) and none when it is
``'classification'``. A mixed cluster needs the regression columns standardized and
the classification columns left alone, so the scaler is per column.

It deliberately reproduces ``kermt.data.scaler.StandardScaler`` numerics (checked
against the source at the pinned tag, 2026-10-14):

* ``means = nanmean`` along axis 0, ``nan`` -> 0;
* ``stds  = nanstd`` (population, ``ddof=0``), ``nan`` -> 1, ``0`` -> 1;
* ``transform = (x - mean) / std``; ``inverse = x * std + mean``.

Classification columns carry ``mean=0, std=1`` so that one (means, stds) pair can be
stored in a KERMT checkpoint's ``data_scaler`` slot and inverted column-wise without
touching a probability.

Fit on the **train fold only** (never val, calibration or test).

Numpy only — no torch, no KERMT — so it runs on the laptop and in every env.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class ColumnScaler:
    """Standardizes regression columns; passes classification columns through."""

    names: tuple[str, ...]
    is_regression: tuple[bool, ...]
    means: tuple[float, ...]
    stds: tuple[float, ...]

    def __post_init__(self) -> None:
        n = len(self.names)
        for field_name in ("is_regression", "means", "stds"):
            if len(getattr(self, field_name)) != n:
                raise ValueError(f"{field_name} must have one entry per column ({n})")
        for name, reg, mean, std in zip(
            self.names, self.is_regression, self.means, self.stds, strict=True
        ):
            if not reg and (mean != 0.0 or std != 1.0):
                raise ValueError(
                    f"classification column {name!r} must have mean=0, std=1 "
                    f"(got {mean}, {std}); scaling a label would corrupt it"
                )
            if not np.isfinite(mean) or not np.isfinite(std) or std <= 0:
                raise ValueError(f"column {name!r}: mean/std must be finite, std > 0")

    # -- fitting -------------------------------------------------------------

    @classmethod
    def fit(
        cls,
        y_train: np.ndarray,
        names: Sequence[str],
        is_regression: Sequence[bool],
    ) -> ColumnScaler:
        """Fit on a train-fold label matrix ``(n, T)`` with NaN for missing."""
        y = np.asarray(y_train, dtype=float)
        if y.ndim != 2 or y.shape[1] != len(names):
            raise ValueError(f"y_train must be (n, {len(names)}), got {y.shape}")
        if len(is_regression) != len(names):
            raise ValueError("is_regression must have one entry per column")

        means: list[float] = []
        stds: list[float] = []
        for j, reg in enumerate(is_regression):
            if not reg:
                means.append(0.0)
                stds.append(1.0)
                continue
            col = y[:, j]
            col = col[~np.isnan(col)]
            if col.size == 0:
                # KERMT: all-NaN column -> mean 0, std 1 (does not crash).
                means.append(0.0)
                stds.append(1.0)
                continue
            std = float(np.std(col))
            means.append(float(np.mean(col)))
            stds.append(std if std > 0 else 1.0)
        return cls(
            names=tuple(names),
            is_regression=tuple(bool(r) for r in is_regression),
            means=tuple(means),
            stds=tuple(stds),
        )

    # -- application ---------------------------------------------------------

    def _mu_sigma(self) -> tuple[np.ndarray, np.ndarray]:
        return np.asarray(self.means, dtype=float), np.asarray(self.stds, dtype=float)

    def transform(self, y: np.ndarray) -> np.ndarray:
        """Scale ``(n, T)`` labels; NaN stays NaN; classification columns untouched."""
        mu, sd = self._mu_sigma()
        return (np.asarray(y, dtype=float) - mu) / sd

    def inverse_transform(self, y: np.ndarray) -> np.ndarray:
        """Undo :meth:`transform` on ``(n, T)`` values."""
        mu, sd = self._mu_sigma()
        return np.asarray(y, dtype=float) * sd + mu

    # -- persistence ---------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "names": list(self.names),
            "is_regression": list(self.is_regression),
            "means": list(self.means),
            "stds": list(self.stds),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ColumnScaler:
        return cls(
            names=tuple(d["names"]),
            is_regression=tuple(bool(r) for r in d["is_regression"]),
            means=tuple(float(m) for m in d["means"]),
            stds=tuple(float(s) for s in d["stds"]),
        )


def to_kermt_targets(y: np.ndarray) -> list[list[float | None]]:
    """``(n, T)`` array with NaN -> the list-of-lists KERMT's dataset expects.

    KERMT's collator derives its loss mask from ``target is not None``, and its own
    ``StandardScaler.transform`` replaces NaN with ``None`` for exactly that reason.
    Handing it ``float('nan')`` instead would mark the entry *labeled* and poison
    the loss with NaN. Every target list that reaches ``MoleculeDataset.set_targets``
    must go through here.
    """
    a = np.asarray(y, dtype=float)
    if a.ndim != 2:
        raise ValueError(f"expected a 2-D label matrix, got shape {a.shape}")
    return [[None if np.isnan(v) else float(v) for v in row] for row in a]


def from_kermt_targets(targets: Sequence[Sequence[float | None]]) -> np.ndarray:
    """Inverse of :func:`to_kermt_targets` (``None`` -> NaN)."""
    return np.array(
        [[np.nan if v is None else float(v) for v in row] for row in targets], dtype=float
    ).reshape(len(targets), -1)
