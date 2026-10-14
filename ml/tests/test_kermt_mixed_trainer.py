"""CPU tests for the mixed trainer's epoch loop (toy model, synthetic mixed labels)."""

from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch")
from torch import nn  # noqa: E402
from train.kermt_mixed.losses import MixedLoss, MixedLossConfig  # noqa: E402
from train.kermt_mixed.sampler import stratified_batches  # noqa: E402
from train.kermt_mixed.trainer import TrainSettings, evaluate_task_losses, fit  # noqa: E402

IS_CLS = [True, True, False]  # two classification tasks, one sparse regression task


class _Toy(nn.Module):
    """Shared trunk + per-task heads, two 'views' like KermtFinetuneTask."""

    def __init__(self, d=6, h=8, t=3):
        super().__init__()
        self.mol_atom_from_atom_ffn = nn.Sequential(nn.Linear(d, h), nn.ReLU(), nn.Linear(h, 4))
        self.mol_atom_from_atom_ffn_task_specific = nn.ModuleList([nn.Linear(4, 1) for _ in range(t)])
        self.bond = nn.Sequential(nn.Linear(d, h), nn.ReLU(), nn.Linear(h, t))

    def forward_views(self, x):
        z = self.mol_atom_from_atom_ffn(x)
        atom = torch.hstack([head(z) for head in self.mol_atom_from_atom_ffn_task_specific])
        return atom, self.bond(x)


def _forward(model, batch, feats):
    return model.forward_views(batch)


def _data(n=480, seed=0):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, 6)).astype(np.float32)
    w = rng.normal(size=(6, 3)).astype(np.float32)
    z = x @ w
    y = np.stack([(z[:, 0] > 0), (z[:, 1] > 0), z[:, 2]], axis=1).astype(np.float32)
    mask = np.stack(
        [rng.random(n) < 0.9, rng.random(n) < 0.8, rng.random(n) < 0.08], axis=1
    )  # task 2 is sparse
    return x, y, mask


def _loader(x, y, mask, idx_batches):
    for b in idx_batches:
        yield (
            torch.from_numpy(x[b]),
            [None] * len(b),
            torch.from_numpy(mask[b].astype(np.float32)),
            torch.from_numpy(np.where(mask[b], y[b], 0.0).astype(np.float32)),
        )


def _run(mode, epochs=12, min_per_task=2, seed=0, lr=0.01):
    torch.manual_seed(seed)
    x, y, mask = _data()
    n_tr = 360
    model = _Toy()
    loss = MixedLoss(IS_CLS, MixedLossConfig(mode=mode, dist_coff=0.1))
    params = list(model.parameters())
    if loss.log_sigma is not None:
        params.append(loss.log_sigma)
    opt = torch.optim.Adam(params, lr=lr)

    def train_batches(epoch):
        idx = stratified_batches(mask[:n_tr], 32, min_per_task=min_per_task, seed=seed, epoch=epoch)
        return _loader(x[:n_tr], y[:n_tr], mask[:n_tr], idx)

    def val_batches():
        idx = [np.arange(n_tr, 480)[i : i + 60] for i in range(0, 120, 60)]
        return _loader(x, y, mask, idx)

    saved: list[int] = []
    res = fit(
        model,
        loss,
        opt,
        None,
        train_batches,
        val_batches,
        # alpha / lr below are TEST FIXTURE values, not recommendations.
        TrainSettings(
            epochs=epochs, mode=mode, dist_coff=0.1,
            gradnorm_alpha=0.5 if mode == "gradnorm" else None,
            gradnorm_lr=0.05 if mode == "gradnorm" else None,
        ),
        IS_CLS,
        forward_fn=_forward,
        on_best=lambda e, m: saved.append(e),
        shared_param=model.mol_atom_from_atom_ffn[2].weight,
    )
    return res, saved, loss


@pytest.mark.parametrize("mode", ["fixed", "fixed_task", "kendall", "gradnorm"])
def test_every_mode_learns_and_selects_a_best_epoch(mode):
    res, saved, _ = _run(mode)
    first, best = res.history[0].val_selection_loss, res.best_selection_loss
    assert best < first
    assert res.best_epoch == min(res.history, key=lambda r: r.val_selection_loss).epoch
    assert saved and saved[-1] == res.best_epoch
    assert [r.is_best for r in res.history].count(True) == len(saved)
    assert all(np.isfinite(r.train_loss) for r in res.history)


def test_kendall_moves_log_sigma_and_records_it():
    res, _, loss = _run("kendall")
    assert res.history[-1].log_sigma is not None
    assert any(abs(v) > 1e-4 for v in res.history[-1].log_sigma)
    assert loss.log_sigma_report() is not None


def test_non_kendall_modes_report_no_log_sigma():
    res, _, loss = _run("fixed_task", epochs=2)
    assert res.history[0].log_sigma is None and loss.log_sigma_report() is None


def test_gradnorm_records_weights_that_stay_normalized():
    res, _, _ = _run("gradnorm", epochs=3)
    w = res.history[-1].gradnorm_weights
    assert w is not None and sum(w) == pytest.approx(3.0, rel=1e-4) and min(w) > 0


def test_stratification_keeps_the_sparse_task_present_every_batch():
    _, _, mask = _data()
    plain = stratified_batches(mask[:360], 32, min_per_task=0, seed=0, epoch=0)
    strat = stratified_batches(mask[:360], 32, min_per_task=2, seed=0, epoch=0)
    assert any(mask[:360][b, 2].sum() == 0 for b in plain)
    assert all(mask[:360][b, 2].sum() >= 2 for b in strat)


def test_training_is_deterministic_for_a_seed():
    a, _, _ = _run("kendall", epochs=4, seed=3)
    b, _, _ = _run("kendall", epochs=4, seed=3)
    assert [r.val_selection_loss for r in a.history] == [r.val_selection_loss for r in b.history]


def test_nan_loss_raises_with_location_instead_of_training_on():
    model = _Toy()
    loss = MixedLoss(IS_CLS, MixedLossConfig(mode="fixed_task", dist_coff=0.1))
    opt = torch.optim.Adam(model.parameters(), lr=0.01)

    def bad_batches(epoch):
        x = torch.full((4, 6), float("nan"))
        yield x, [None] * 4, torch.ones(4, 3), torch.zeros(4, 3)

    with pytest.raises(FloatingPointError, match="epoch 0, batch 0"):
        fit(
            model, loss, opt, None, bad_batches, lambda: iter(()),
            TrainSettings(epochs=1, mode="fixed_task", dist_coff=0.1), IS_CLS, forward_fn=_forward,
        )


def test_evaluate_reports_none_for_a_task_with_no_validation_labels():
    model = _Toy()
    x = torch.randn(8, 6)
    mask = torch.ones(8, 3)
    mask[:, 2] = 0
    means, total = evaluate_task_losses(
        model, [(x, [None] * 8, mask, torch.zeros(8, 3))], IS_CLS, 0.1, _forward
    )
    assert means[2] is None and means[0] is not None
    assert total == pytest.approx(means[0] + means[1])
    assert model.training  # restored


def test_epochs_must_be_positive_and_gradnorm_params_are_required_not_defaulted():
    with pytest.raises(ValueError):
        TrainSettings(epochs=0, mode="fixed_task", dist_coff=0.1)
    with pytest.raises(ValueError, match="gradnorm_alpha"):
        TrainSettings(epochs=3, mode="gradnorm", dist_coff=0.1)
    with pytest.raises(TypeError):  # the arm and dist_coff have no defaults either
        TrainSettings(epochs=3)  # type: ignore[call-arg]


def test_every_epochs_validation_views_can_be_collected_for_posthoc_selection():
    x, y, mask = _data()
    model = _Toy()
    loss = MixedLoss(IS_CLS, MixedLossConfig(mode="fixed_task", dist_coff=0.1))
    opt = torch.optim.Adam(model.parameters(), lr=0.01)
    got: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    idx = [np.arange(360, 420), np.arange(420, 480)]
    fit(
        model, loss, opt, None,
        lambda e: _loader(x[:360], y[:360], mask[:360], [np.arange(0, 64)]),
        lambda: _loader(x, y, mask, idx),
        TrainSettings(epochs=3, mode="fixed_task", dist_coff=0.1), IS_CLS,
        forward_fn=_forward, on_val_views=lambda e, a, b: got.__setitem__(e, (a, b)),
    )
    assert sorted(got) == [0, 1, 2]
    for a, b in got.values():
        assert a.shape == b.shape == (120, 3)
    assert not np.allclose(got[0][0], got[2][0])  # the model moved between epochs


def test_container_selfcheck_passes_and_covers_g4():
    from train.kermt_mixed import selfcheck

    result = selfcheck.run()
    assert result["ok"], result["checks"]
    assert "G4_kendall_at_zero_is_1_per_cls_and_half_per_reg" in result["checks"]
