"""
GradNorm (Chen et al., 2018) loss weights — the *ablation* arm, not the default.

Per step, for the tasks that have at least one label in the batch:

1. ``G_i = || d(w_i * L_i) / dW ||_2`` on a chosen **shared** parameter ``W``;
2. relative inverse training rate ``r_i = (L_i / L_i(0)) / mean_j(L_j / L_j(0))``;
3. target ``G_avg * r_i ** alpha`` (a constant — no gradient through it);
4. ``L_grad = sum_i | G_i - target_i |``, differentiated w.r.t. the weights ``w`` only;
5. step ``w``, then renormalize so ``sum(w) == T`` (over all tasks).

Cost: one extra autograd pass per task per step (``create_graph=True``), which is
why the blueprint budgets about 1.4x for this arm. ``alpha`` is the asymmetry
hyperparameter and ``lr`` the learning rate of the weights themselves. **Neither has
a default here.** Chen et al. report an optimum near ``alpha = 1.5`` on NYUv2
(scene understanding) and used ``0.12`` on their synthetic regression problem — a
12x spread across two problems, and none of it is ADMET. Their NYUv2 weight learning
rate was 0.025. For MARS both are search-space axes of the tuning protocol
(``tuning.py``), chosen on validation data only.

``W`` must be genuinely shared. Use :func:`default_shared_parameter`, which picks
the last ``Linear`` of ``mol_atom_from_atom_ffn`` — the layer *before* the per-task
heads. That requires ``--ffn_num_task_specific_layers > 0``; with no per-task heads
the "shared" FFN output layer has one row per task and GradNorm is meaningless.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import nn


def default_shared_parameter(model: nn.Module) -> nn.Parameter:
    """Last shared ``Linear`` weight of ``KermtFinetuneTask`` (see module docstring)."""
    heads = getattr(model, "mol_atom_from_atom_ffn_task_specific", None)
    if heads is None:
        raise ValueError(
            "GradNorm needs per-task heads (--ffn_num_task_specific_layers > 0); "
            "without them there is no layer shared by all tasks."
        )
    ffn = getattr(model, "mol_atom_from_atom_ffn", None)
    if ffn is None:
        raise ValueError("model has no mol_atom_from_atom_ffn")
    linears = [m for m in ffn.modules() if isinstance(m, nn.Linear)]
    if not linears:
        raise ValueError("mol_atom_from_atom_ffn contains no Linear layer")
    return linears[-1].weight


@dataclass
class GradNormDiagnostics:
    weights: list[float]
    grad_norms: list[float]
    targets: list[float]
    l_grad: float


class GradNormWeights:
    """Owns the weights ``w`` and their optimizer; call :meth:`step` once per batch."""

    def __init__(
        self,
        num_tasks: int,
        *,
        alpha: float,
        lr: float,
        device: torch.device | str = "cpu",
    ) -> None:
        if num_tasks < 2:
            raise ValueError("GradNorm needs >= 2 tasks")
        if alpha < 0:
            raise ValueError("alpha must be >= 0")
        if lr <= 0:
            raise ValueError("lr must be > 0")
        self.num_tasks = num_tasks
        self.alpha = alpha
        self.w = nn.Parameter(torch.ones(num_tasks, device=device))
        self._opt = torch.optim.Adam([self.w], lr=lr)
        self._l0: torch.Tensor | None = None  # initial per-task loss, NaN until seen

    def current(self) -> torch.Tensor:
        """Detached weights for the main loss this step."""
        return self.w.detach().clone()

    def step(
        self,
        task_means: torch.Tensor,
        active: torch.Tensor,
        shared: nn.Parameter,
    ) -> GradNormDiagnostics | None:
        """Update ``w`` from this batch. Returns ``None`` if < 2 tasks are active.

        ``task_means`` must still carry the autograd graph of the forward pass; this
        method does not call ``backward`` on the main loss and does not free it.
        """
        act = active.bool()
        if int(act.sum()) < 2:
            return None
        if self._l0 is None:
            self._l0 = torch.full((self.num_tasks,), float("nan"), device=task_means.device)
        l0 = self._l0.to(task_means.device)
        first_seen = torch.isnan(l0) & act
        if bool(first_seen.any()):
            l0 = torch.where(first_seen, task_means.detach(), l0)
            self._l0 = l0

        idx = torch.nonzero(act, as_tuple=False).flatten()
        w = self.w.to(task_means.device)
        grad_norms = []
        for i in idx.tolist():
            g = torch.autograd.grad(
                w[i] * task_means[i], shared, retain_graph=True, create_graph=True
            )[0]
            grad_norms.append(torch.linalg.vector_norm(g))
        g_norm = torch.stack(grad_norms)

        with torch.no_grad():
            rel = task_means.detach()[idx] / torch.clamp(l0[idx], min=1e-12)
            r = rel / torch.clamp(rel.mean(), min=1e-12)
            target = (g_norm.detach().mean() * r**self.alpha).detach()
        l_grad = (g_norm - target).abs().sum()

        self._opt.zero_grad(set_to_none=True)
        w_grad = torch.autograd.grad(l_grad, self.w, retain_graph=True, allow_unused=True)[0]
        self.w.grad = w_grad if w_grad is not None else torch.zeros_like(self.w)
        self._opt.step()
        with torch.no_grad():
            self.w.clamp_(min=1e-4)
            self.w.mul_(self.num_tasks / self.w.sum())

        return GradNormDiagnostics(
            weights=[float(v) for v in self.w.detach().cpu()],
            grad_norms=[float(v) for v in g_norm.detach().cpu()],
            targets=[float(v) for v in target.cpu()],
            l_grad=float(l_grad.detach().cpu()),
        )
