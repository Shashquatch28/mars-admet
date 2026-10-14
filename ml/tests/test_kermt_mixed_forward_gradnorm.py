"""
CPU tests for the Tier-1 forward pass (vs a verbatim stock forward) and GradNorm.

``_StockFinetuneTask`` is ``KermtFinetuneTask.forward`` copied verbatim from
``kermt/model/models.py`` at the pinned tag (read 2026-10-14); only the encoder
(``kermt``) and ``readout`` are replaced by tiny stand-ins, because those are the
parts that need KERMT's graph featurization. Everything the mixed forward must
reproduce — the FFN heads, task-specific heads, feature concatenation, the
train/eval split, the sigmoid placement — is exercised for real.
"""

from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch")
from torch import nn  # noqa: E402
from train.kermt_mixed.forward import (  # noqa: E402
    combine_views,
    mixed_forward,
    probability_to_logit,
)
from train.kermt_mixed.gradnorm import (  # noqa: E402
    GradNormWeights,
    default_shared_parameter,
)

H = 8  # hidden size


class _Encoder(nn.Module):
    """Stand-in for KERMTEmbedding: atom_from_atom / atom_from_bond tensors."""

    def __init__(self):
        super().__init__()
        self.lin_a = nn.Linear(4, H)
        self.lin_b = nn.Linear(4, H)

    def forward(self, batch):
        x = batch[0]  # [n_atoms, 4]
        return {"atom_from_atom": self.lin_a(x), "atom_from_bond": self.lin_b(x)}


class _Readout(nn.Module):
    def forward(self, atom_x, a_scope):
        return torch.stack([atom_x[s : s + n].mean(0) for s, n in a_scope])


class _StockFinetuneTask(nn.Module):
    """KermtFinetuneTask structure + forward, verbatim apart from encoder/readout."""

    def __init__(self, num_tasks, classification, task_specific, features_size=0):
        super().__init__()
        self.iscuda = False
        self.kermt = _Encoder()
        self.readout = _Readout()
        ts_hidden = 6
        out = ts_hidden if task_specific else num_tasks
        first = H + features_size
        self.mol_atom_from_atom_ffn = nn.Sequential(nn.Dropout(0.2), nn.Linear(first, out))
        self.mol_atom_from_bond_ffn = nn.Sequential(nn.Dropout(0.2), nn.Linear(first, out))
        if task_specific:
            self.mol_atom_from_atom_ffn_task_specific = nn.ModuleList(
                [nn.Sequential(nn.Dropout(0.2), nn.Linear(ts_hidden, 1)) for _ in range(num_tasks)]
            )
            self.mol_atom_from_bond_ffn_task_specific = nn.ModuleList(
                [nn.Sequential(nn.Dropout(0.2), nn.Linear(ts_hidden, 1)) for _ in range(num_tasks)]
            )
        else:
            self.mol_atom_from_atom_ffn_task_specific = None
            self.mol_atom_from_bond_ffn_task_specific = None
        self.classification = classification
        if classification:
            self.sigmoid = nn.Sigmoid()

    def forward(self, batch, features_batch):  # verbatim from kermt/model/models.py
        _, _, _, _, _, a_scope, _, _ = batch

        output = self.kermt(batch)
        mol_atom_from_bond_output = self.readout(output["atom_from_bond"], a_scope)
        mol_atom_from_atom_output = self.readout(output["atom_from_atom"], a_scope)

        if features_batch[0] is not None:
            features_batch = torch.from_numpy(np.stack(features_batch)).float()
            if self.iscuda:
                features_batch = features_batch.cuda()
            features_batch = features_batch.to(output["atom_from_atom"])
            if len(features_batch.shape) == 1:
                features_batch = features_batch.view([1, features_batch.shape[0]])
        else:
            features_batch = None

        if features_batch is not None:
            mol_atom_from_atom_output = torch.cat([mol_atom_from_atom_output, features_batch], 1)
            mol_atom_from_bond_output = torch.cat([mol_atom_from_bond_output, features_batch], 1)

        if self.training:
            atom_ffn_output = self.mol_atom_from_atom_ffn(mol_atom_from_atom_output)
            bond_ffn_output = self.mol_atom_from_bond_ffn(mol_atom_from_bond_output)
            atom_preds = []
            bond_preds = []
            if self.mol_atom_from_atom_ffn_task_specific is not None:
                for _, task_layer in enumerate(self.mol_atom_from_atom_ffn_task_specific):
                    atom_preds.append(task_layer(atom_ffn_output))
                for _, task_layer in enumerate(self.mol_atom_from_bond_ffn_task_specific):
                    bond_preds.append(task_layer(bond_ffn_output))
                return torch.hstack(atom_preds), torch.hstack(bond_preds)
            else:
                return atom_ffn_output, bond_ffn_output
        else:
            atom_ffn_output = self.mol_atom_from_atom_ffn(mol_atom_from_atom_output)
            bond_ffn_output = self.mol_atom_from_bond_ffn(mol_atom_from_bond_output)

            if self.mol_atom_from_atom_ffn_task_specific is not None:
                atom_preds_list = []
                bond_preds_list = []
                for _, task_layer in enumerate(self.mol_atom_from_atom_ffn_task_specific):
                    atom_preds_list.append(task_layer(atom_ffn_output))
                for _, task_layer in enumerate(self.mol_atom_from_bond_ffn_task_specific):
                    bond_preds_list.append(task_layer(bond_ffn_output))
                atom_preds = torch.hstack(atom_preds_list)
                bond_preds = torch.hstack(bond_preds_list)
                if self.classification:
                    atom_preds = self.sigmoid(atom_preds)
                    bond_preds = self.sigmoid(bond_preds)
                    output = (atom_preds + bond_preds) / 2
                else:
                    output = (atom_preds + bond_preds) / 2
            else:
                if self.classification:
                    atom_ffn_output = self.sigmoid(atom_ffn_output)
                    bond_ffn_output = self.sigmoid(bond_ffn_output)
                    output = (atom_ffn_output + bond_ffn_output) / 2
                else:
                    output = (atom_ffn_output + bond_ffn_output) / 2

        return output


def _batch():
    torch.manual_seed(0)
    x = torch.randn(11, 4)
    scope = [(0, 4), (4, 3), (7, 4)]
    return (x, None, None, None, None, scope, None, None)


@pytest.mark.parametrize("classification", [True, False])
@pytest.mark.parametrize("task_specific", [True, False])
@pytest.mark.parametrize("with_features", [True, False])
def test_eval_combination_matches_stock_forward(classification, task_specific, with_features):
    fs = 3 if with_features else 0
    torch.manual_seed(1)
    model = _StockFinetuneTask(3, classification, task_specific, fs)
    feats = [np.random.default_rng(i).normal(size=fs) for i in range(3)] if fs else [None] * 3
    batch = _batch()

    model.eval()
    with torch.no_grad():
        stock = model(batch, feats)
        atom, bond = mixed_forward(model, batch, feats)
        ours = combine_views(atom, bond, [classification] * 3)
    torch.testing.assert_close(ours, stock, rtol=1e-6, atol=1e-7)


@pytest.mark.parametrize("task_specific", [True, False])
def test_train_mode_views_match_stock_train_forward(task_specific):
    model = _StockFinetuneTask(2, True, task_specific, 0)
    batch, feats = _batch(), [None] * 3
    model.train()
    torch.manual_seed(5)
    stock_atom, stock_bond = model(batch, feats)
    torch.manual_seed(5)  # same dropout draws
    atom, bond = mixed_forward(model, batch, feats)
    torch.testing.assert_close(atom, stock_atom)
    torch.testing.assert_close(bond, stock_bond)


def test_views_are_raw_in_eval_mode_where_stock_would_have_collapsed_them():
    model = _StockFinetuneTask(2, True, True, 0)
    model.eval()
    with torch.no_grad():
        atom, bond = mixed_forward(model, _batch(), [None] * 3)
        stock = model(_batch(), [None] * 3)
    assert atom.shape == bond.shape == (3, 2)
    assert not torch.allclose(atom, stock)  # stock returned sigmoids; ours are raw


def test_mixed_columns_get_sigmoid_only_where_classification():
    atom = torch.tensor([[2.0, 2.0]])
    bond = torch.tensor([[0.0, 0.0]])
    out = combine_views(atom, bond, [True, False])
    assert out[0, 0].item() == pytest.approx((torch.sigmoid(torch.tensor(2.0)).item() + 0.5) / 2)
    assert out[0, 1].item() == pytest.approx(1.0)  # (2 + 0) / 2, no sigmoid


def test_probability_to_logit_matches_kermtmodel_predict_logits_definition():
    p = np.array([0.0, 1.0, 0.5, 0.9])
    out = probability_to_logit(p)
    assert np.isfinite(out).all()
    assert out[2] == pytest.approx(0.0)
    assert out[3] == pytest.approx(np.log(9.0))


# ---- GradNorm ----------------------------------------------------------------


class _Toy(nn.Module):
    def __init__(self):
        super().__init__()
        self.mol_atom_from_atom_ffn = nn.Sequential(nn.Linear(4, 5), nn.ReLU(), nn.Linear(5, 3))
        self.mol_atom_from_atom_ffn_task_specific = nn.ModuleList([nn.Linear(3, 1) for _ in range(2)])


def test_default_shared_parameter_is_last_shared_linear_and_needs_task_heads():
    m = _Toy()
    assert default_shared_parameter(m) is m.mol_atom_from_atom_ffn[2].weight
    m.mol_atom_from_atom_ffn_task_specific = None
    with pytest.raises(ValueError, match="task_specific|per-task"):
        default_shared_parameter(m)


def _scaled_tasks(shared, c):
    s = (shared**2).sum()
    return torch.stack([c[0] * s, c[1] * s])


def test_gradnorm_raises_the_weight_of_the_task_that_is_training_slower():
    shared = nn.Parameter(torch.ones(3, 3))
    gn = GradNormWeights(2, alpha=1.5, lr=0.05)
    active = torch.tensor([True, True])
    gn.step(_scaled_tasks(shared, [1.0, 1.0]), active, shared)  # records L(0) = (3x, 3x)
    w_before = gn.current()
    # Task 0 has made fast progress (loss x0.1); task 1 has not.
    diag = gn.step(_scaled_tasks(shared, [0.1, 1.0]), active, shared)
    w = gn.current()
    assert diag is not None
    assert w[1] > w[0]
    assert w.sum().item() == pytest.approx(2.0, rel=1e-5)  # renormalized to T
    assert (w > 0).all()
    assert not torch.allclose(w, w_before)


def test_gradnorm_needs_two_active_tasks_and_leaves_weights_alone_otherwise():
    shared = nn.Parameter(torch.ones(2, 2))
    gn = GradNormWeights(2, alpha=1.0, lr=0.01)
    before = gn.current()
    assert gn.step(_scaled_tasks(shared, [1.0, 1.0]), torch.tensor([True, False]), shared) is None
    torch.testing.assert_close(gn.current(), before)


def test_gradnorm_validation():
    with pytest.raises(ValueError):
        GradNormWeights(1, alpha=1.0, lr=0.01)
    with pytest.raises(ValueError):
        GradNormWeights(2, alpha=-1, lr=0.01)
    with pytest.raises(ValueError):
        GradNormWeights(2, alpha=1.0, lr=0)
    with pytest.raises(TypeError):  # alpha and lr have no defaults
        GradNormWeights(2)  # type: ignore[call-arg]
