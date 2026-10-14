"""
Type-correct masked multi-task loss for a mixed classification/regression run.

What KERMT does today (``task/train.py::train`` + ``KermtFinetuneTask.get_loss_func``,
read verbatim at the pinned tag, 2026-10-14), and what this reproduces
------------------------------------------------------------------------
In training mode the model returns TWO views ``(atom_preds, bond_preds)`` of raw
pre-sigmoid values, ``[B, T]``. The per-element loss is::

    l = pred_loss(p_atom, y) + pred_loss(p_bond, y) + dist_coff * (p_atom - p_bond)^2

with ``pred_loss`` ONE function for the whole run (BCE-with-logits for
classification, MSE for regression), then ``* mask``. Stock reductions:

* no MTL loss:  ``l.sum() / mask.sum()``  — mean over all labeled entries;
* ``--use_mtl_loss``: per-task mean ``l.sum(0) / clamp(mask.sum(0), 1)`` then
  ``sum_t 0.5 * exp(-2 s_t) * m_t + s_t`` — the SAME precision for every task.

Here ``pred_loss`` is chosen per column, so a mixed run is type-correct. The
``dist_coff`` consistency term is kept for every column (it is a squared difference
of raw outputs; it is meaningful for both types, and keeping it is what makes
``mode="fixed"`` match stock on classification-only data — gate G2).

Modes (``MixedLossConfig.mode``)
--------------------------------
``fixed``
    Stock reduction: global mean over labeled entries. Used for parity gates G2/G3
    because stock KERMT *is* this. Tasks are implicitly weighted by label count.
``fixed_task``
    Equal weight per task: ``sum_t m_t`` over tasks with at least one label in the
    batch. This is the like-for-like baseline for ``kendall`` (Kendall with every
    ``log sigma`` frozen at 0 reduces to it up to the 0.5 on regression terms).
    **The Module 11 ablation's "fixed" arm should be this one, not ``fixed``** —
    ``fixed`` under-weights Clearance 10:1 against a CYP by label count alone.
``kendall``
    Kendall, Gal & Cipolla (2018), type-correct: regression precision
    ``0.5 * exp(-2 s)``, classification precision ``exp(-2 s)``, plus ``s``.
    A task with no labeled row in the batch contributes NOTHING — including its
    ``s`` term — so an empty batch cannot drift ``log sigma``.
``gradnorm``
    ``sum_t w_t * m_t`` with ``w`` supplied by :class:`gradnorm.GradNormWeights`.

Relation to KERMT's uniform ``MTLLoss``: for a *pure* classification run KERMT's
``0.5 exp(-2 s_k)`` equals this module's ``exp(-2 s_c)`` under ``s_k = s_c - 0.5 ln 2``
(an exact reparameterization, ``decisions.md`` 2026-09-20 finding 4). Report
``log_sigma`` from this module as is; apply ``+0.5 ln 2`` only when comparing to a
KERMT-native ``MTLLoss`` run.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import torch
from torch import nn

from .common import MODES

Mode = Literal["fixed", "fixed_task", "kendall", "gradnorm"]


@dataclass(frozen=True)
class MixedLossConfig:
    """Loss settings. Both fields are required: there is no default weighting arm,
    and ``dist_coff`` must equal the stock run's ``--dist_coff`` (KERMT's own
    default is 0.15, not a number to be assumed here)."""

    mode: Mode
    dist_coff: float

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {self.mode!r}")
        if self.dist_coff < 0:
            raise ValueError("dist_coff must be >= 0")


@dataclass
class LossOutput:
    """One batch's loss and the pieces needed to log or re-weight it."""

    total: torch.Tensor  # scalar, with graph
    task_means: torch.Tensor  # [T], with graph: per-task masked mean of ``l``
    n_labeled: torch.Tensor  # [T], float, per-task labeled count in the batch
    active: torch.Tensor  # [T], bool, task had >= 1 label in the batch


class MixedLoss(nn.Module):
    """Masked, type-correct, optionally uncertainty-weighted multi-task loss."""

    def __init__(self, is_classification: Sequence[bool], config: MixedLossConfig) -> None:
        super().__init__()
        n = len(is_classification)
        if n == 0:
            raise ValueError("need at least one task")
        self.config = config
        self.num_tasks = n
        self.register_buffer(
            "is_cls", torch.tensor([bool(c) for c in is_classification], dtype=torch.bool)
        )
        if config.mode == "kendall":
            if n < 2:
                raise ValueError("kendall weighting needs >= 2 tasks (KERMT asserts the same)")
            self.log_sigma = nn.Parameter(torch.zeros(n))
        else:
            self.log_sigma = None
        # gradnorm weights are injected each step by the controller.
        self.register_buffer("gradnorm_weights", torch.ones(n))

    # -- pieces --------------------------------------------------------------

    def element_loss(
        self, atom: torch.Tensor, bond: torch.Tensor, targets: torch.Tensor
    ) -> torch.Tensor:
        """``[B, T]`` unmasked per-element loss, both views + consistency term."""
        y = torch.nan_to_num(targets, nan=0.0)
        bce_a = nn.functional.binary_cross_entropy_with_logits(atom, y, reduction="none")
        bce_b = nn.functional.binary_cross_entropy_with_logits(bond, y, reduction="none")
        mse_a = (atom - y) ** 2
        mse_b = (bond - y) ** 2
        cls = self.is_cls.to(atom.device).unsqueeze(0)
        first = torch.where(cls, bce_a, mse_a)
        second = torch.where(cls, bce_b, mse_b)
        return first + second + self.config.dist_coff * (atom - bond) ** 2

    def precisions(self) -> torch.Tensor:
        """Kendall precisions ``[T]``: ``exp(-2s)`` classification, ``0.5 exp(-2s)`` regression."""
        if self.log_sigma is None:
            raise RuntimeError("precisions() is only defined for mode='kendall'")
        base = torch.exp(-2.0 * self.log_sigma)
        return torch.where(self.is_cls.to(base.device), base, 0.5 * base)

    # -- forward -------------------------------------------------------------

    def forward(
        self,
        atom: torch.Tensor,
        bond: torch.Tensor,
        targets: torch.Tensor,
        mask: torch.Tensor,
    ) -> LossOutput:
        m = mask.to(atom.dtype)
        el = self.element_loss(atom, bond, targets) * m
        n_lab = m.sum(dim=0)
        active = n_lab > 0
        task_means = el.sum(dim=0) / torch.clamp(n_lab, min=1.0)
        mode = self.config.mode

        if mode == "fixed":
            total = el.sum() / torch.clamp(m.sum(), min=1.0)
        elif mode == "fixed_task":
            total = (task_means * active).sum()
        elif mode == "kendall":
            assert self.log_sigma is not None
            terms = self.precisions() * task_means + self.log_sigma
            total = (terms * active).sum()
        else:  # gradnorm
            w = self.gradnorm_weights.to(atom.device)
            total = (w * task_means * active).sum()
        return LossOutput(total=total, task_means=task_means, n_labeled=n_lab, active=active)

    # -- reporting -----------------------------------------------------------

    def log_sigma_report(self) -> dict[int, float] | None:
        """``{task_index: log sigma}`` for the run record, or ``None`` if not Kendall."""
        if self.log_sigma is None:
            return None
        return {i: float(v) for i, v in enumerate(self.log_sigma.detach().cpu())}
