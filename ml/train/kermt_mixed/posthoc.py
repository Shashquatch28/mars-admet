"""
Re-score a finished run's validation predictions under any selection rule.

The trainer saves, for every epoch, the raw ``(atom, bond)`` views on the
validation fold (``<run>/logs/val_views.npz``, keys ``atom_e000``, ``bond_e000``,
...). That makes two questions answerable *without retraining*:

* "Would a different selection metric (mean AUROC, per-task MAE, ...) have picked a
  different epoch?"
* "What would the model have scored had training stopped at epoch 7?" — for the
  *selection* part of the question. Note this is **not** equivalent to training
  with ``--epochs 7``: KERMT's Noam schedule is a function of the total epoch
  count, so a shorter schedule is a different learning-rate trajectory. Whether
  ``epochs`` matters is a tuning-protocol axis (``tuning.py``), not something this
  module can answer.

Numpy only. Metrics are injected, so the module imports neither sklearn nor MARS
evaluation code; the caller passes ``eval.metrics``-compatible callables.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import numpy as np

from .scaling import ColumnScaler


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def combine_views_np(
    atom: np.ndarray, bond: np.ndarray, is_classification: Sequence[bool]
) -> np.ndarray:
    """NumPy twin of ``forward.combine_views``: probabilities / scaled values."""
    cls = np.asarray(list(is_classification), dtype=bool)[None, :]
    return np.where(cls, (_sigmoid(atom) + _sigmoid(bond)) / 2.0, (atom + bond) / 2.0)


def epoch_predictions(
    npz_path: Path | str, scaler: ColumnScaler, is_classification: Sequence[bool]
) -> dict[int, np.ndarray]:
    """``{epoch: (n_val, T)}`` in served units (probability / raw regression units)."""
    out: dict[int, np.ndarray] = {}
    with np.load(npz_path) as z:
        epochs = sorted(int(k.split("_e")[1]) for k in z.files if k.startswith("atom_e"))
        for e in epochs:
            comb = combine_views_np(z[f"atom_e{e:03d}"], z[f"bond_e{e:03d}"], is_classification)
            out[e] = scaler.inverse_transform(comb)
    return out


def per_epoch_task_scores(
    preds_by_epoch: Mapping[int, np.ndarray],
    y_val: np.ndarray,
    is_classification: Sequence[bool],
    *,
    cls_metric: Callable[[np.ndarray, np.ndarray], float],
    reg_metric: Callable[[np.ndarray, np.ndarray], float],
) -> tuple[list[int], np.ndarray]:
    """``(epochs, scores[E, T])``; each column scored on its own labeled rows.

    A column with fewer than two distinct labels (so AUROC is undefined) is NaN.
    """
    y = np.asarray(y_val, dtype=float)
    epochs = sorted(preds_by_epoch)
    scores = np.full((len(epochs), y.shape[1]), np.nan)
    for i, e in enumerate(epochs):
        p = preds_by_epoch[e]
        if p.shape != y.shape:
            raise ValueError(f"epoch {e}: predictions {p.shape} != labels {y.shape}")
        for t, is_cls in enumerate(is_classification):
            ok = ~np.isnan(y[:, t])
            if ok.sum() == 0:
                continue
            yt, pt = y[ok, t], p[ok, t]
            if is_cls and len(np.unique(yt)) < 2:
                continue
            scores[i, t] = (cls_metric if is_cls else reg_metric)(yt, pt)
    return epochs, scores


def best_epoch(
    epochs: Sequence[int],
    scores: np.ndarray,
    is_classification: Sequence[bool],
    *,
    rule: str,
) -> int:
    """Pick an epoch by a named rule over the ``(E, T)`` score matrix.

    ``rule`` — ``"mean_rank"``: mean over tasks of each epoch's rank within that
    task (scale-free, so AUROC and MAE can be combined without choosing weights);
    ``"task:<j>"``: optimize one task alone. Classification scores are
    higher-is-better, regression scores (errors) lower-is-better.
    """
    s = np.asarray(scores, dtype=float)
    higher = np.asarray(list(is_classification), dtype=bool)
    if rule.startswith("task:"):
        j = int(rule.split(":", 1)[1])
        col = s[:, j]
        return int(epochs[int(np.nanargmax(col) if higher[j] else np.nanargmin(col))])
    if rule != "mean_rank":
        raise ValueError(f"unknown rule {rule!r}")
    ranks = np.full_like(s, np.nan)
    for t in range(s.shape[1]):
        col = s[:, t]
        if np.isnan(col).all():
            continue
        order = np.argsort(-col if higher[t] else col, kind="stable")
        r = np.empty(len(col))
        r[order] = np.arange(len(col))
        r[np.isnan(col)] = np.nan
        ranks[:, t] = r
    return int(epochs[int(np.nanargmin(np.nanmean(ranks, axis=1)))])
