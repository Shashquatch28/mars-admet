"""
CPU tests for the Tier-1 mixed loss, including gate G4.

The references below are VERBATIM copies of KERMT's own loss code at the pinned
tag (``v2.0.0`` / ``e402473``), read 2026-10-14 — so these tests compare the MARS
loss to what stock KERMT actually computes, not to the MARS author's idea of it.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

torch = pytest.importorskip("torch")
from torch import nn  # noqa: E402
from train.kermt_mixed.losses import MixedLoss, MixedLossConfig  # noqa: E402

DIST = 0.1


# ---- verbatim references -----------------------------------------------------


class _KermtMTLLoss(nn.Module):
    """kermt/util/loss.py::MTLLoss, verbatim."""

    def __init__(self, num_tasks):
        super().__init__()
        assert num_tasks > 1, "Number of tasks must be greater than 1"
        self.num_tasks = num_tasks
        self.log_sigma = nn.Parameter(torch.zeros(num_tasks))

    def get_precisions(self):
        return 0.5 * torch.exp(-2.0 * self.log_sigma)

    def forward(self, loss_terms):
        total_loss = 0
        precisions = self.get_precisions()
        for task in range(self.num_tasks):
            total_loss += precisions[task] * loss_terms[task] + self.log_sigma[task]
        return total_loss


def _kermt_loss_func(dt, dist_coff):
    """KermtFinetuneTask.get_loss_func, verbatim (train-mode branch)."""

    def loss_func(preds, targets):
        pred_loss = nn.BCEWithLogitsLoss(reduction="none") if dt == "classification" else nn.MSELoss(reduction="none")
        dist_loss = nn.MSELoss(reduction="none")
        dist = dist_loss(preds[0], preds[1])
        return pred_loss(preds[0], targets) + pred_loss(preds[1], targets) + dist_coff * dist

    return loss_func


def _stock_train_loss(atom, bond, targets, mask, dt, mtl=None):
    """task/train.py::train inner loss, verbatim reductions."""
    loss = _kermt_loss_func(dt, DIST)((atom, bond), targets) * torch.ones(targets.shape) * mask
    if mtl is not None:
        task_mask_sum = torch.clamp(mask.sum(axis=0), min=1.0)
        return mtl(loss.sum(axis=0) / task_mask_sum)
    return loss.sum() / mask.sum()


# ---- fixtures ----------------------------------------------------------------


def _batch(is_cls, b=64, seed=0, label_rate=0.7):
    g = torch.Generator().manual_seed(seed)
    t = len(is_cls)
    atom = torch.randn(b, t, generator=g) * 2
    bond = atom + 0.3 * torch.randn(b, t, generator=g)
    mask = (torch.rand(b, t, generator=g) < label_rate).float()
    y = torch.randn(b, t, generator=g)
    cls = torch.tensor(is_cls)
    y = torch.where(cls, (y > 0).float(), y)
    return atom, bond, y, mask


def _loss(is_cls, mode, **kw):
    return MixedLoss(is_cls, MixedLossConfig(mode=mode, dist_coff=DIST, **kw))


# ---- parity with stock KERMT -------------------------------------------------


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_fixed_matches_stock_on_classification_only(seed):
    is_cls = [True, True, True]
    atom, bond, y, mask = _batch(is_cls, seed=seed)
    ours = _loss(is_cls, "fixed")(atom, bond, y, mask).total
    ref = _stock_train_loss(atom, bond, y, mask, "classification")
    assert ours.item() == pytest.approx(ref.item(), rel=1e-6)


def test_fixed_matches_stock_on_regression_only():
    is_cls = [False, False]
    atom, bond, y, mask = _batch(is_cls, seed=4)
    ours = _loss(is_cls, "fixed")(atom, bond, y, mask).total
    ref = _stock_train_loss(atom, bond, y, mask, "regression")
    assert ours.item() == pytest.approx(ref.item(), rel=1e-6)


def test_fixed_ignores_unlabeled_targets_even_if_they_are_nan():
    is_cls = [True, False]
    atom, bond, y, mask = _batch(is_cls, seed=5)
    y_nan = torch.where(mask.bool(), y, torch.tensor(float("nan")))
    a = _loss(is_cls, "fixed")(atom, bond, y, mask).total
    b = _loss(is_cls, "fixed")(atom, bond, y_nan, mask).total
    assert torch.isfinite(b)
    assert a.item() == pytest.approx(b.item(), rel=1e-6)


def test_mixed_element_loss_is_bce_for_cls_and_mse_for_reg():
    is_cls = [True, False]
    atom = torch.tensor([[0.3, 1.5]])
    bond = torch.tensor([[0.1, 1.0]])
    y = torch.tensor([[1.0, 0.25]])
    el = _loss(is_cls, "fixed").element_loss(atom, bond, y)[0]
    bce = lambda p, t: float(nn.functional.binary_cross_entropy_with_logits(torch.tensor(p), torch.tensor(t)))  # noqa: E731
    want0 = bce(0.3, 1.0) + bce(0.1, 1.0) + DIST * (0.3 - 0.1) ** 2
    want1 = (1.5 - 0.25) ** 2 + (1.0 - 0.25) ** 2 + DIST * (1.5 - 1.0) ** 2
    assert el[0].item() == pytest.approx(want0, rel=1e-6)
    assert el[1].item() == pytest.approx(want1, rel=1e-6)


# ---- G4: Kendall at log_sigma = 0 -------------------------------------------


def test_G4_kendall_at_zero_logsigma_is_half_per_regression_and_one_per_classification():
    is_cls = [True, True, False, False]
    atom, bond, y, mask = _batch(is_cls, seed=7, label_rate=0.9)
    fixed = _loss(is_cls, "fixed_task")(atom, bond, y, mask)
    kendall = _loss(is_cls, "kendall")(atom, bond, y, mask)
    expected = sum(
        (1.0 if is_cls[t] else 0.5) * fixed.task_means[t].item() for t in range(4)
    )
    assert kendall.total.item() == pytest.approx(expected, rel=1e-6, abs=1e-9)


def test_G4_logsigma_term_is_added_once_per_active_task():
    is_cls = [True, False]
    atom, bond, y, mask = _batch(is_cls, seed=8, label_rate=1.0)
    m = _loss(is_cls, "kendall")
    with torch.no_grad():
        m.log_sigma.copy_(torch.tensor([0.4, -0.2]))
    out = m(atom, bond, y, mask)
    means = out.task_means
    want = (
        math.exp(-0.8) * means[0].item() + 0.4
        + 0.5 * math.exp(0.4) * means[1].item() - 0.2
    )
    assert out.total.item() == pytest.approx(want, rel=1e-6)


# ---- relation to KERMT's uniform MTLLoss ------------------------------------


def test_kendall_on_pure_classification_is_kermt_mtlloss_up_to_the_known_reparameterization():
    """decisions.md 2026-09-20 finding 4: s_k = s_c - 0.5 ln 2, per-task constant offset."""
    is_cls = [True, True, True]
    atom, bond, y, mask = _batch(is_cls, seed=9, label_rate=0.85)
    s_c = torch.tensor([0.3, -0.1, 0.5])

    ours = _loss(is_cls, "kendall")
    with torch.no_grad():
        ours.log_sigma.copy_(s_c)
    o = ours(atom, bond, y, mask)

    ref_mtl = _KermtMTLLoss(3)
    with torch.no_grad():
        ref_mtl.log_sigma.copy_(s_c - 0.5 * math.log(2))
    r = _stock_train_loss(atom, bond, y, mask, "classification", mtl=ref_mtl)

    # Same objective up to +0.5 ln2 per task (a constant: identical gradients).
    assert (o.total - r).item() == pytest.approx(3 * 0.5 * math.log(2), rel=1e-5)

    o.total.backward()
    r.backward()
    np.testing.assert_allclose(
        ours.log_sigma.grad.numpy(), ref_mtl.log_sigma.grad.numpy(), rtol=1e-5, atol=1e-7
    )


# ---- empty tasks -------------------------------------------------------------


def test_task_with_no_labels_in_batch_contributes_nothing_including_logsigma():
    is_cls = [True, False, False]
    atom, bond, y, mask = _batch(is_cls, seed=10, label_rate=1.0)
    mask[:, 2] = 0.0  # task 2 has no labels in this batch
    m = _loss(is_cls, "kendall")
    out = m(atom, bond, y, mask)
    assert not out.active[2]
    out.total.backward()
    assert m.log_sigma.grad[2].item() == 0.0  # no drift from an empty batch
    assert m.log_sigma.grad[0].item() != 0.0


def test_all_empty_batch_is_zero_not_nan():
    is_cls = [True, False]
    atom, bond, y, _ = _batch(is_cls, seed=11)
    for mode in ("fixed", "fixed_task", "kendall"):
        out = _loss(is_cls, mode)(atom, bond, y, torch.zeros(64, 2))
        assert torch.isfinite(out.total) and out.total.item() == 0.0


# ---- arms differ where they should ------------------------------------------


def test_fixed_underweights_the_sparse_task_but_fixed_task_does_not():
    """Why the ablation's 'fixed' arm is fixed_task: stock weights tasks by label count."""
    is_cls = [True, False]
    atom, bond, y, _ = _batch(is_cls, b=100, seed=12)
    mask = torch.zeros(100, 2)
    mask[:, 0] = 1.0  # dense classification task
    mask[:5, 1] = 1.0  # sparse regression task, 5 labels
    stock = _loss(is_cls, "fixed")(atom, bond, y, mask)
    per_task = _loss(is_cls, "fixed_task")(atom, bond, y, mask)
    # total = sum_t coef_t * m_t, so the coefficient is d total / d m_t.
    means = stock.task_means.detach().clone().requires_grad_(True)
    stock_total = (means * stock.n_labeled).sum() / stock.n_labeled.sum()
    assert stock_total.item() == pytest.approx(stock.total.item(), rel=1e-6)
    (coef,) = torch.autograd.grad(stock_total, means)
    assert coef[1].item() == pytest.approx(5 / 105)  # sparse task: <5% of the objective
    assert per_task.total.item() == pytest.approx(per_task.task_means.sum().item(), rel=1e-6)
    # fixed_task gives each active task coefficient 1 (checked by the line above).


def test_gradnorm_mode_uses_the_injected_weights():
    is_cls = [True, False]
    atom, bond, y, mask = _batch(is_cls, seed=13, label_rate=1.0)
    m = _loss(is_cls, "gradnorm")
    base = m(atom, bond, y, mask)
    with torch.no_grad():
        m.gradnorm_weights.copy_(torch.tensor([2.0, 0.5]))
    out = m(atom, bond, y, mask)
    want = 2.0 * base.task_means[0] + 0.5 * base.task_means[1]
    assert out.total.item() == pytest.approx(want.item(), rel=1e-6)


def test_config_and_construction_guards():
    with pytest.raises(ValueError):
        MixedLossConfig(mode="nope", dist_coff=0.1)
    with pytest.raises(TypeError):  # no default weighting arm, no default dist_coff
        MixedLossConfig()  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        MixedLossConfig(mode="fixed")  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="kendall"):
        _loss([True], "kendall")
    with pytest.raises(ValueError):
        MixedLoss([], MixedLossConfig(mode="fixed", dist_coff=0.1))
