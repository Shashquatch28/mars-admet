"""
Torch-free definitions shared by the host side and the in-container trainer.

The host environment (``ml/.venv``) has no torch, and ``models.kermt_mixed_model``
must import cleanly there; the torch-only modules (``losses``, ``forward``,
``gradnorm``, ``trainer``) re-export from here rather than the other way round.
"""

from __future__ import annotations

import numpy as np

#: Loss weighting arms. ``fixed`` is stock KERMT's reduction (parity gates);
#: ``fixed_task`` is the like-for-like baseline for ``kendall``. See ``losses``.
MODES: tuple[str, ...] = ("fixed", "fixed_task", "kendall", "gradnorm")


def probability_to_logit(p: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    """``logit`` of the served probability, clipped like ``KermtModel.predict_logits``.

    Calibration is fit on exactly this quantity for the Tier-0 runs
    (``ml/models/kermt_model.py::predict_logits``), so Tier-1 classification columns
    use the same definition and stay directly comparable. It is *not* the mean of
    the two heads' logits; the two views' raw logits are also written by the
    trainer (``views.csv``) for anyone who wants them.
    """
    clipped = np.clip(np.asarray(p, dtype=float), eps, 1.0 - eps)
    return np.log(clipped / (1.0 - clipped))
