"""
Tier 2 — ordinal/CDF encoding of a regression target as binary columns.

Purpose
-------
KERMT's stock CLI takes one ``--dataset_type`` per run, so a cluster mixing
classification and regression endpoints cannot be trained by it. This module
removes the mixture at the *data* level instead of the code level: a continuous
target ``y`` becomes M binary columns ``y > t_1 ... y > t_M``, so a mixed cluster
becomes a single **all-classification** run through the completely unmodified
stock CLI. The scalar is recovered afterwards from the predicted survival
function.

This is the classical ordinal binary decomposition (Frank & Hall 2001; Li & Lin
2007), and sits in the same family as the "regression as classification" result
that binned cross-entropy can beat direct MSE regression, with the largest
margins reported in *multi-task* settings (Farebrother et al. 2024).

Two things it buys beyond unblocking the CLI: the decomposition yields a full
predictive CDF per molecule (useful to Module 5's uncertainty work), and every
column is binary so temperature scaling applies to all of them.

Known cost, measure it before trusting it
-----------------------------------------
Discretization puts a floor under the achievable MAE no matter how good the
model is. :func:`discretization_ceiling_mae` measures that floor **at zero GPU
cost** by encoding true labels and decoding them straight back. Run it, and pick
``n_bins`` from it, before any GPU training — see ``documentation/AIMS/next_steps.md``.

Column naming is ``<endpoint_key>__gt<m>``, which keeps
``featurize.kermt_adapter.write_finetune_csv`` / ``read_predictions_csv``
unchanged — they are already task-type-agnostic on the wire.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

ORDINAL_VERSION = "mars-ordinal-cdf-v1"

Strategy = Literal["quantile", "uniform"]


def ordinal_column_names(endpoint_key: str, n_thresholds: int) -> list[str]:
    """``["logS__gt0", "logS__gt1", ...]`` — one per threshold, in order."""
    return [f"{endpoint_key}__gt{m}" for m in range(n_thresholds)]


@dataclass(frozen=True)
class OrdinalCdfCodec:
    """Thresholds + per-bin representative values for one regression endpoint.

    Attributes
    ----------
    thresholds:
        Strictly increasing cut points ``t_0 < t_1 < ... < t_{M-1}``. Column *m*
        of the encoding answers "is ``y > thresholds[m]``?".
    bin_representatives:
        ``M + 1`` values, one per bin, used to reconstruct a scalar. Bin 0 is
        ``(-inf, t_0]``, bin *k* is ``(t_{k-1}, t_k]``, bin *M* is ``(t_{M-1}, inf)``.
        Fit as the mean of the training labels falling in that bin, so the
        reconstruction is calibrated to the data rather than to bin midpoints.
    strategy:
        How the thresholds were placed.
    """

    thresholds: tuple[float, ...]
    bin_representatives: tuple[float, ...]
    strategy: str
    version: str = ORDINAL_VERSION

    def __post_init__(self) -> None:
        if len(self.bin_representatives) != len(self.thresholds) + 1:
            raise ValueError(
                f"bin_representatives must have len(thresholds)+1 = "
                f"{len(self.thresholds) + 1} entries, got "
                f"{len(self.bin_representatives)}"
            )
        t = np.asarray(self.thresholds, dtype=float)
        if t.size and not np.all(np.diff(t) > 0):
            raise ValueError(f"thresholds must be strictly increasing, got {self.thresholds}")

    @property
    def n_thresholds(self) -> int:
        return len(self.thresholds)

    @property
    def n_bins(self) -> int:
        return len(self.bin_representatives)

    def column_names(self, endpoint_key: str) -> list[str]:
        return ordinal_column_names(endpoint_key, self.n_thresholds)

    def to_dict(self) -> dict:
        return {
            "thresholds": list(self.thresholds),
            "bin_representatives": list(self.bin_representatives),
            "strategy": self.strategy,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict) -> OrdinalCdfCodec:
        return cls(
            thresholds=tuple(float(x) for x in data["thresholds"]),
            bin_representatives=tuple(float(x) for x in data["bin_representatives"]),
            strategy=str(data["strategy"]),
            version=str(data.get("version", ORDINAL_VERSION)),
        )


def fit_ordinal_codec(
    y: np.ndarray,
    *,
    n_bins: int = 8,
    strategy: Strategy = "quantile",
) -> OrdinalCdfCodec:
    """Fit thresholds and bin representatives on **training-fold labels only**.

    Parameters
    ----------
    y:
        1-D labels; ``NaN`` entries are ignored.
    n_bins:
        Number of bins. Produces ``n_bins - 1`` thresholds. Ties may collapse
        duplicate quantiles, yielding fewer.
    strategy:
        ``"quantile"`` (default) places cut points at equal-count quantiles —
        correct for MARS's skewed targets (logS, Caco-2 have long tails).
        ``"uniform"`` places them evenly across the observed range.

    Raises
    ------
    ValueError
        If ``n_bins < 2``, ``y`` is not 1-D, or fewer than 2 non-NaN labels are
        present (nothing to discretize).
    """
    y = np.asarray(y, dtype=float)
    if y.ndim != 1:
        raise ValueError(f"y must be 1-D, got {y.ndim}-D")
    if n_bins < 2:
        raise ValueError(f"n_bins must be >= 2, got {n_bins}")

    finite = y[~np.isnan(y)]
    if finite.size < 2:
        raise ValueError(
            f"need at least 2 non-NaN labels to fit a codec, got {finite.size}"
        )
    if float(finite.min()) == float(finite.max()):
        # Every threshold would sit on the single observed value, so every
        # encoded column is constant. Caught here rather than producing a
        # perfectly-learnable, perfectly-useless set of binary tasks.
        raise ValueError(
            "all labels are identical; an ordinal encoding carries no information"
        )

    if strategy == "quantile":
        qs = np.linspace(0.0, 1.0, n_bins + 1)[1:-1]
        raw = np.quantile(finite, qs)
    elif strategy == "uniform":
        raw = np.linspace(finite.min(), finite.max(), n_bins + 1)[1:-1]
    else:
        raise ValueError(f"unknown strategy {strategy!r}; use 'quantile' or 'uniform'")

    # Heavily tied data (e.g. censored assay readouts) can produce repeated
    # quantiles. Collapsing them is correct — a zero-width bin can never receive
    # a label — and it keeps the strictly-increasing invariant real rather than
    # asserted away.
    thresholds = tuple(float(t) for t in np.unique(raw))

    # Representative = mean of the training labels in each bin, so decoding is
    # calibrated to the data. Empty bins fall back to the bin's midpoint.
    edges = np.asarray(thresholds, dtype=float)
    idx = np.searchsorted(edges, finite, side="left")
    reps: list[float] = []
    lo_guard = float(finite.min())
    hi_guard = float(finite.max())
    for k in range(len(thresholds) + 1):
        members = finite[idx == k]
        if members.size:
            reps.append(float(members.mean()))
            continue
        left = lo_guard if k == 0 else float(edges[k - 1])
        right = hi_guard if k == len(thresholds) else float(edges[k])
        reps.append((left + right) / 2.0)

    return OrdinalCdfCodec(
        thresholds=thresholds,
        bin_representatives=tuple(reps),
        strategy=strategy,
    )


def encode(codec: OrdinalCdfCodec, y: np.ndarray) -> np.ndarray:
    """Encode ``y`` as ``(n, n_thresholds)`` binary survival indicators.

    Column *m* is ``1.0`` where ``y > thresholds[m]``, else ``0.0``. A ``NaN``
    label produces an all-``NaN`` row, which is how the KERMT adapter writes a
    missing label (empty CSV cell) and how the masked loss skips it.
    """
    y = np.asarray(y, dtype=float)
    if y.ndim != 1:
        raise ValueError(f"y must be 1-D, got {y.ndim}-D")
    edges = np.asarray(codec.thresholds, dtype=float)
    out = (y[:, None] > edges[None, :]).astype(float)
    out[np.isnan(y), :] = np.nan
    return out


def decode(codec: OrdinalCdfCodec, p: np.ndarray) -> np.ndarray:
    """Recover scalar predictions from predicted survival probabilities.

    ``p[i, m]`` is the model's ``P(y_i > thresholds[m])``. A true survival
    function is non-increasing in *m*, but Frank-Hall style decomposition learns
    each column independently and gives no such guarantee, so monotonicity is
    enforced here with a running minimum before integrating.

    ``E[y] = sum_k P(bin_k) * representative_k``, where the bin probabilities are
    the successive differences of the (padded) survival function.
    """
    p = np.asarray(p, dtype=float)
    if p.ndim != 2:
        raise ValueError(f"p must be 2-D, got {p.ndim}-D")
    if p.shape[1] != codec.n_thresholds:
        raise ValueError(
            f"p has {p.shape[1]} columns but the codec has "
            f"{codec.n_thresholds} thresholds"
        )

    s = np.clip(p, 0.0, 1.0)
    s = np.minimum.accumulate(s, axis=1)

    n = s.shape[0]
    padded = np.concatenate(
        [np.ones((n, 1)), s, np.zeros((n, 1))], axis=1
    )  # S_0 = 1, S_{M+1} = 0
    bin_probs = padded[:, :-1] - padded[:, 1:]  # (n, n_bins)

    reps = np.asarray(codec.bin_representatives, dtype=float)
    return bin_probs @ reps


def discretization_ceiling_mae(codec: OrdinalCdfCodec, y: np.ndarray) -> float:
    """MAE floor imposed by discretization alone — the zero-GPU gate.

    Encodes true labels to exact 0/1 columns and decodes them straight back, so
    the only error left is the information the binning threw away. No model can
    beat this on the given labels. Compare against the direct-regression
    baseline MAE for the same endpoint to choose ``n_bins`` **before** spending
    any GPU time.
    """
    y = np.asarray(y, dtype=float)
    mask = ~np.isnan(y)
    if not mask.any():
        raise ValueError("y has no non-NaN labels")
    recovered = decode(codec, encode(codec, y[mask]))
    return float(np.mean(np.abs(recovered - y[mask])))
