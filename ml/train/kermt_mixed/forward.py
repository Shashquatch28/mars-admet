"""
Forward pass that exposes both KERMT views, in training *and* eval mode.

Why this is re-implemented rather than called
---------------------------------------------
``KermtFinetuneTask.forward`` (``kermt/model/models.py``, pinned tag ``v2.0.0``)

* in **train** mode returns ``(atom_preds, bond_preds)`` of raw values, but
* in **eval** mode collapses them to ONE tensor, applying a sigmoid to *every*
  column when ``self.classification`` (a single bool from ``args.dataset_type``)
  and none otherwise.

A mixed run has both kinds of column, so the eval-mode collapse is wrong for it by
construction. This module reproduces the forward verbatim (same sub-modules, same
order, same dropout behaviour) and returns the two raw views in either mode. The
type-dependent combination then happens per column in :func:`combine_views`.

It is checked against a verbatim copy of the stock forward in
``ml/tests/test_kermt_mixed_forward.py`` and, against the real model, by gate G1.

Imports torch only; the model is duck-typed (``kermt``, ``readout``,
``mol_atom_from_{atom,bond}_ffn``, ``..._task_specific``, ``iscuda``).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import torch
from torch import nn

from .common import probability_to_logit  # noqa: F401  (re-exported)


def mixed_forward(
    model: nn.Module, batch: Any, features_batch: Sequence[Any]
) -> tuple[torch.Tensor, torch.Tensor]:
    """Return ``(atom_preds, bond_preds)``, each ``[B, T]``, raw (pre-sigmoid)."""
    _, _, _, _, _, a_scope, _, _ = batch

    output = model.kermt(batch)
    mol_atom_from_bond_output = model.readout(output["atom_from_bond"], a_scope)
    mol_atom_from_atom_output = model.readout(output["atom_from_atom"], a_scope)

    if features_batch[0] is not None:
        feats = torch.from_numpy(np.stack(features_batch)).float()
        if model.iscuda:
            feats = feats.cuda()
        feats = feats.to(output["atom_from_atom"])
        if len(feats.shape) == 1:
            feats = feats.view([1, feats.shape[0]])
    else:
        feats = None

    if feats is not None:
        mol_atom_from_atom_output = torch.cat([mol_atom_from_atom_output, feats], 1)
        mol_atom_from_bond_output = torch.cat([mol_atom_from_bond_output, feats], 1)

    atom_ffn_output = model.mol_atom_from_atom_ffn(mol_atom_from_atom_output)
    bond_ffn_output = model.mol_atom_from_bond_ffn(mol_atom_from_bond_output)

    atom_heads = model.mol_atom_from_atom_ffn_task_specific
    if atom_heads is not None:
        bond_heads = model.mol_atom_from_bond_ffn_task_specific
        atom_preds = torch.hstack([layer(atom_ffn_output) for layer in atom_heads])
        bond_preds = torch.hstack([layer(bond_ffn_output) for layer in bond_heads])
        return atom_preds, bond_preds
    return atom_ffn_output, bond_ffn_output


def combine_views(
    atom: torch.Tensor, bond: torch.Tensor, is_classification: Sequence[bool]
) -> torch.Tensor:
    """Eval-mode combination, per column.

    Classification: ``(sigmoid(a) + sigmoid(b)) / 2`` — a probability, identical to
    stock. Regression: ``(a + b) / 2`` — in *scaled* units; invert with the scaler.
    """
    cls = torch.as_tensor(list(is_classification), dtype=torch.bool, device=atom.device)
    prob = (torch.sigmoid(atom) + torch.sigmoid(bond)) / 2
    reg = (atom + bond) / 2
    return torch.where(cls.unsqueeze(0), prob, reg)


