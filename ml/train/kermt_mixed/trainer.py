"""
The epoch loop of the mixed trainer — KERMT-agnostic.

Everything KERMT-specific (building ``args``, the dataset, the collator, the model,
the optimizer and scheduler) lives in ``train_mixed.py`` and is handed in here as
plain callables and objects. That is what lets this loop be unit-tested on a laptop
with a toy model, while the KERMT wiring is validated on the workstation by gates
G1 and G2.

Mirrors ``task/train.py::run_training`` where it can, and says so where it cannot:

* per-batch: ``model.zero_grad()`` -> forward -> loss -> ``backward()`` ->
  ``optimizer.step()`` -> ``scheduler.step()`` (stock steps ``NoamLR`` per batch);
* per-epoch: evaluate, record, keep the best epoch.

Differences from stock, all deliberate and all recorded:

* **Epoch selection.** Stock saves on best average validation *metric* (AUROC for
  classification, MAE for regression) or best average validation loss. A mixed run
  cannot average AUROC and MAE, and raw-unit MAE is PPB-dominated (decisions D1).
  Here the selection score is ``sum_t`` of the per-task mean validation loss on
  *scaled* targets under ``fixed_task`` weighting — the same for every arm, so the
  fixed / Kendall / GradNorm ablation never differs in how its epoch was chosen.
  Per-epoch per-task validation losses are logged so any other rule can be applied
  post hoc without retraining.
* **NaN guard.** Stock does not check; a silent NaN loss trains a garbage model for
  hours. This raises with the epoch and batch.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import torch
from torch import nn

from .forward import mixed_forward
from .gradnorm import GradNormWeights, default_shared_parameter
from .losses import MixedLoss, MixedLossConfig

BatchItem = tuple[Any, Any, torch.Tensor, torch.Tensor]  # batch, features, mask, targets


@dataclass(frozen=True)
class TrainSettings:
    """Run settings. ``mode`` and ``dist_coff`` are always required; the GradNorm
    pair is required exactly when ``mode == "gradnorm"``. No value here is a default
    chosen by MARS: each comes from the stock argv or from a tuning trial."""

    epochs: int
    mode: str
    dist_coff: float
    gradnorm_alpha: float | None = None
    gradnorm_lr: float | None = None

    def __post_init__(self) -> None:
        if self.epochs < 1:
            raise ValueError("epochs must be >= 1")
        if self.mode == "gradnorm" and (self.gradnorm_alpha is None or self.gradnorm_lr is None):
            raise ValueError("mode='gradnorm' requires gradnorm_alpha and gradnorm_lr")


@dataclass
class EpochRecord:
    epoch: int
    train_loss: float
    train_task_means: list[float]
    val_task_means: list[float | None]
    val_selection_loss: float
    n_batches: int
    log_sigma: list[float] | None = None
    gradnorm_weights: list[float] | None = None
    lr: list[float] | None = None
    seconds: float = 0.0
    is_best: bool = False


@dataclass
class FitResult:
    history: list[EpochRecord] = field(default_factory=list)
    best_epoch: int = -1
    best_selection_loss: float = float("inf")

    def to_dict(self) -> dict[str, Any]:
        return {
            "best_epoch": self.best_epoch,
            "best_selection_loss": self.best_selection_loss,
            "history": [asdict(r) for r in self.history],
        }


def evaluate_task_losses(
    model: nn.Module,
    batches: Iterable[BatchItem],
    is_classification: Sequence[bool],
    dist_coff: float,
    forward_fn: Callable[..., tuple[torch.Tensor, torch.Tensor]] = mixed_forward,
    collect_views: list[tuple[np.ndarray, np.ndarray]] | None = None,
) -> tuple[list[float | None], float]:
    """Per-task mean validation loss (scaled targets) and their sum over tasks.

    If ``collect_views`` is a list, each batch's raw ``(atom, bond)`` views are
    appended (in validation order) so predictions can be re-scored under any
    selection rule afterwards without retraining.
    """
    evaluator = MixedLoss(is_classification, MixedLossConfig(mode="fixed_task", dist_coff=dist_coff))
    n_tasks = len(is_classification)
    num = torch.zeros(n_tasks, dtype=torch.float64)
    den = torch.zeros(n_tasks, dtype=torch.float64)
    was_training = model.training
    model.eval()
    try:
        with torch.no_grad():
            dev = next(model.parameters()).device
            evaluator.to(dev)
            for batch, feats, mask, targets in batches:
                atom, bond = forward_fn(model, batch, feats)
                mask = mask.to(dev)
                targets = targets.to(dev)
                el = evaluator.element_loss(atom, bond, targets) * mask.to(atom.dtype)
                if collect_views is not None:
                    collect_views.append((atom.cpu().numpy(), bond.cpu().numpy()))
                num += el.sum(dim=0).double().cpu()
                den += mask.sum(dim=0).double().cpu()
    finally:
        model.train(was_training)
    means: list[float | None] = [
        (float(num[t] / den[t]) if den[t] > 0 else None) for t in range(n_tasks)
    ]
    total = float(sum(m for m in means if m is not None))
    return means, total


def fit(
    model: nn.Module,
    loss_module: MixedLoss,
    optimizer: torch.optim.Optimizer,
    scheduler: Any | None,
    train_batches: Callable[[int], Iterable[BatchItem]],
    val_batches: Callable[[], Iterable[BatchItem]],
    settings: TrainSettings,
    is_classification: Sequence[bool],
    *,
    start_epoch: int = 0,
    forward_fn: Callable[..., tuple[torch.Tensor, torch.Tensor]] = mixed_forward,
    on_best: Callable[[int, nn.Module], None] | None = None,
    log_fn: Callable[[dict[str, Any]], None] | None = None,
    shared_param: nn.Parameter | None = None,
    on_val_views: Callable[[int, np.ndarray, np.ndarray], None] | None = None,
) -> FitResult:
    """Run the epochs; call ``on_best(epoch, model)`` whenever selection improves."""
    result = FitResult()
    dev = next(model.parameters()).device
    loss_module.to(dev)

    gn: GradNormWeights | None = None
    if settings.mode == "gradnorm":
        assert settings.gradnorm_alpha is not None and settings.gradnorm_lr is not None
        gn = GradNormWeights(
            len(is_classification),
            alpha=settings.gradnorm_alpha,
            lr=settings.gradnorm_lr,
            device=dev,
        )
        shared_param = shared_param if shared_param is not None else default_shared_parameter(model)

    for epoch in range(start_epoch, settings.epochs):
        t0 = time.time()
        model.train()
        loss_sum = 0.0
        task_sum = torch.zeros(len(is_classification), dtype=torch.float64)
        task_n = torch.zeros(len(is_classification), dtype=torch.float64)
        n_batches = 0

        for step, (batch, feats, mask, targets) in enumerate(train_batches(epoch)):
            mask = mask.to(dev)
            targets = targets.to(dev)
            model.zero_grad()
            atom, bond = forward_fn(model, batch, feats)
            if gn is not None:
                with torch.no_grad():
                    loss_module.gradnorm_weights.copy_(gn.current())
            out = loss_module(atom, bond, targets, mask)
            if not torch.isfinite(out.total):
                raise FloatingPointError(
                    f"non-finite loss at epoch {epoch}, batch {step} "
                    f"(task means: {out.task_means.detach().cpu().tolist()})"
                )
            if gn is not None:
                assert shared_param is not None
                gn.step(out.task_means, out.active, shared_param)
            out.total.backward()
            optimizer.step()
            if scheduler is not None:
                scheduler.step()

            loss_sum += float(out.total.detach())
            task_sum += (out.task_means.detach().double() * out.n_labeled.double()).cpu()
            task_n += out.n_labeled.double().cpu()
            n_batches += 1

        views: list[tuple[np.ndarray, np.ndarray]] | None = [] if on_val_views else None
        val_means, val_total = evaluate_task_losses(
            model, val_batches(), is_classification, settings.dist_coff, forward_fn, views
        )
        if on_val_views is not None and views:
            on_val_views(
                epoch,
                np.concatenate([a for a, _ in views], axis=0),
                np.concatenate([b for _, b in views], axis=0),
            )
        rec = EpochRecord(
            epoch=epoch,
            train_loss=loss_sum / max(n_batches, 1),
            train_task_means=[
                float(task_sum[t] / task_n[t]) if task_n[t] > 0 else float("nan")
                for t in range(len(is_classification))
            ],
            val_task_means=val_means,
            val_selection_loss=val_total,
            n_batches=n_batches,
            log_sigma=(
                [float(v) for v in loss_module.log_sigma.detach().cpu()]
                if loss_module.log_sigma is not None
                else None
            ),
            gradnorm_weights=([float(v) for v in gn.current().cpu()] if gn is not None else None),
            lr=[float(g["lr"]) for g in optimizer.param_groups],
            seconds=time.time() - t0,
        )
        if val_total < result.best_selection_loss:
            result.best_selection_loss = val_total
            result.best_epoch = epoch
            rec.is_best = True
            if on_best is not None:
                on_best(epoch, model)
        result.history.append(rec)
        if log_fn is not None:
            log_fn({"event": "epoch", **asdict(rec)})
    return result
