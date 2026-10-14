"""
Stratified batch composition for sparse tasks (blueprint Module 4, mitigation #2).

The problem: in a mixed cluster one task can be far sparser than the rest
(``clearance_microsomal`` has ~1,100 compounds against 12,000+ per CYP). A random
batch of 32 then holds, on average, well under one clearance label, and many
batches hold none. A per-task loss estimated from 0-2 samples is noisy, and under
Kendall weighting that noise reaches ``log sigma_t``. This sampler guarantees each
task a minimum number of labeled rows per batch **by adding rows**, never by
dropping any: the base permutation is the stock one, so with ``min_per_task=0`` the
output is exactly "shuffle, then chunk" (what ``DataLoader(shuffle=True)`` does).

Deterministic given ``seed`` and ``epoch``. Identical across the fixed / Kendall /
GradNorm arms by construction (the arm is not an input), which is what lets the
ablation isolate the weighting.

A batch may therefore exceed ``batch_size`` by up to ``sum(deficits)`` rows. That is
reported, not hidden: :func:`batch_stats` returns the sizes and per-task counts.

Numpy only.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np


def stratified_batches(
    label_mask: np.ndarray,
    batch_size: int,
    *,
    min_per_task: int,
    seed: int,
    epoch: int,
) -> list[np.ndarray]:
    """Index batches for one epoch.

    Parameters
    ----------
    label_mask:
        ``(n, T)`` boolean, True where row ``i`` has a label for task ``t``.
    batch_size:
        Base batch size; the number of batches is ``ceil(n / batch_size)`` (the
        stock ``DataLoader`` count, ``drop_last=False``).
    min_per_task:
        Minimum labeled rows per task per batch. ``0`` disables stratification.
        A task with fewer than ``min_per_task`` labeled rows *overall* is topped up
        with everything it has (best effort, never an error).
    seed, epoch:
        RNG is ``default_rng([seed, epoch])`` — reproducible per epoch.
    """
    mask = np.asarray(label_mask, dtype=bool)
    if mask.ndim != 2:
        raise ValueError(f"label_mask must be 2-D, got {mask.shape}")
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    if min_per_task < 0:
        raise ValueError("min_per_task must be >= 0")
    n, n_tasks = mask.shape
    if n == 0:
        return []

    rng = np.random.default_rng([int(seed), int(epoch)])
    perm = rng.permutation(n)
    n_batches = math.ceil(n / batch_size)
    batches = [perm[i * batch_size : (i + 1) * batch_size] for i in range(n_batches)]
    if min_per_task == 0:
        return batches

    per_task_rows = [np.flatnonzero(mask[:, t]) for t in range(n_tasks)]
    out: list[np.ndarray] = []
    for batch in batches:
        extra: list[int] = []
        present = set(batch.tolist())
        counts = mask[batch].sum(axis=0)
        for t in range(n_tasks):
            deficit = int(min_per_task - counts[t])
            if deficit <= 0:
                continue
            pool = per_task_rows[t]
            if pool.size == 0:
                continue
            # Candidates not already in the batch; sample without replacement.
            candidates = pool[~np.isin(pool, list(present))] if present else pool
            if candidates.size == 0:
                continue
            take = min(deficit, int(candidates.size))
            chosen = rng.choice(candidates, size=take, replace=False)
            extra.extend(int(c) for c in chosen)
            present.update(int(c) for c in chosen)
            # Added rows may carry other tasks' labels too; keep counts honest.
            counts = counts + mask[chosen].sum(axis=0)
        out.append(np.concatenate([batch, np.asarray(extra, dtype=perm.dtype)]) if extra else batch)
    return out


def batch_stats(
    batches: Sequence[np.ndarray], label_mask: np.ndarray
) -> dict[str, object]:
    """Sizes and per-task labeled counts per batch — for the run record."""
    mask = np.asarray(label_mask, dtype=bool)
    sizes = np.array([len(b) for b in batches], dtype=int)
    counts = np.stack([mask[b].sum(axis=0) for b in batches]) if len(batches) else np.zeros((0, mask.shape[1]), int)
    return {
        "n_batches": int(len(batches)),
        "size_min": int(sizes.min()) if sizes.size else 0,
        "size_max": int(sizes.max()) if sizes.size else 0,
        "per_task_min": counts.min(axis=0).tolist() if counts.size else [],
        "per_task_mean": counts.mean(axis=0).round(3).tolist() if counts.size else [],
        "batches_with_zero_labels_per_task": (counts == 0).sum(axis=0).tolist() if counts.size else [],
    }
