"""explain.graph_ig: the numpy half of Integrated Gradients on KERMT graph inputs (ADR-029)."""

from __future__ import annotations

import numpy as np
import pytest
from explain.graph_ig import (
    IGOutcome,
    adaptive_ig,
    fold_to_atoms,
    midpoint_alphas,
    power_quadrature,
    within_tolerance,
)

# Ethanol-like chain a1 - a2 - a3. KERMT indexes atoms and bonds from 1 (row 0 is padding). Each undirected
# bond is two directed ones: b1 = a1->a2, b2 = a2->a1, b3 = a2->a3, b4 = a3->a2.
B2A = np.array([0, 1, 2, 2, 3])
B2REVB = np.array([0, 2, 1, 4, 3])


def test_fold_conserves_everything_and_splits_bond_features_between_endpoints():
    rng = np.random.default_rng(0)
    atom_fdim, bond_dim = 4, 3
    attr_atoms = np.vstack([np.zeros(atom_fdim), rng.normal(size=(3, atom_fdim))])
    attr_bonds = np.vstack([np.zeros(atom_fdim + bond_dim), rng.normal(size=(4, atom_fdim + bond_dim))])
    scores = fold_to_atoms(attr_atoms, attr_bonds, B2A, B2REVB, atom_fdim)
    assert scores.shape == (3,)
    assert scores.sum() == pytest.approx(attr_atoms.sum() + attr_bonds.sum())


def test_a_directed_bonds_source_block_goes_to_its_source_atom_and_its_own_features_are_shared():
    atom_fdim = 2
    attr_atoms = np.zeros((4, atom_fdim))
    attr_bonds = np.zeros((5, atom_fdim + 1))
    attr_bonds[3, :atom_fdim] = [1.0, 2.0]  # b3 = a2 -> a3: its source-atom block belongs to a2
    attr_bonds[3, atom_fdim] = 4.0  # b3's own bond feature: split between a2 and a3
    scores = fold_to_atoms(attr_atoms, attr_bonds, B2A, B2REVB, atom_fdim)
    assert scores.tolist() == [0.0, 3.0 + 2.0, 2.0]


def test_padding_rows_are_ignored():
    atom_fdim = 2
    attr_atoms = np.zeros((4, atom_fdim))
    attr_bonds = np.zeros((5, atom_fdim + 1))
    attr_atoms[0] = 99.0  # padding row: no atom, must not leak into any atom
    attr_bonds[0] = 99.0
    assert not fold_to_atoms(attr_atoms, attr_bonds, B2A, B2REVB, atom_fdim).any()


def test_midpoint_alphas_are_interior_and_even():
    a = midpoint_alphas(4)
    assert a.tolist() == [0.125, 0.375, 0.625, 0.875]
    assert midpoint_alphas(1).tolist() == [0.5]
    with pytest.raises(ValueError):
        midpoint_alphas(0)


def test_midpoint_rule_integrates_a_quadratic_exactly_enough():
    # IG of f(x)=x^2 from 0 to 3 along the straight line is x * mean(df/dx at alpha*x) = 3 * mean(2*3*alpha) = 9.
    x = 3.0
    for steps, tol in [(4, 0.1), (32, 1e-3)]:
        grads = 2 * (midpoint_alphas(steps) * x)
        assert x * grads.mean() == pytest.approx(9.0, abs=tol)


def test_power_quadrature_weights_sum_to_one_and_power_one_is_the_uniform_rule():
    for power in (1, 2, 3):
        alphas, weights = power_quadrature(32, power)
        assert weights.sum() == pytest.approx(1.0, rel=1e-2)
        assert alphas.min() > 0 and alphas.max() < 1
    a1, w1 = power_quadrature(8, 1)
    assert a1.tolist() == midpoint_alphas(8).tolist() and np.allclose(w1, 1 / 8)


def test_power_quadrature_crowds_points_toward_the_baseline_and_still_integrates():
    uniform = midpoint_alphas(32)
    cubic, w = power_quadrature(32, 3)
    assert (cubic < 0.05).sum() > (uniform < 0.05).sum()
    # integral of 4*alpha^3 over [0, 1] is 1; of cos(10*alpha) is sin(10)/10
    assert (w * 4 * cubic**3).sum() == pytest.approx(1.0, abs=1e-2)
    assert (w * np.cos(10 * cubic)).sum() == pytest.approx(np.sin(10) / 10, abs=1e-2)
    fine, wf = power_quadrature(128, 3)
    assert (wf * 4 * fine**3).sum() == pytest.approx(1.0, abs=1e-3)
    with pytest.raises(ValueError):
        power_quadrature(0, 3)


def test_tolerance_has_a_floor_for_tiny_changes():
    assert within_tolerance(0.04, 1.0, 0.05, 1e-3)
    assert not within_tolerance(0.06, 1.0, 0.05, 1e-3)
    assert within_tolerance(5e-4, 1e-5, 0.05, 1e-3)  # a near-zero change is not asked for relative precision


def test_adaptive_ig_stops_at_the_first_schedule_entry_that_satisfies_completeness():
    calls = []

    def run(steps):
        calls.append(steps)
        return IGOutcome(steps, total_attribution=1.0 + 1.0 / steps, delta=1.0, payload=steps)

    out = adaptive_ig(run, (4, 16, 64), rel_tol=0.1, abs_tol=0.0)
    assert out.steps == 16 and calls == [4, 16]  # 1/4 = 0.25 fails, 1/16 = 0.0625 passes


def test_adaptive_ig_returns_the_finest_run_unchanged_when_nothing_satisfies_it():
    out = adaptive_ig(lambda s: IGOutcome(s, 5.0, 1.0, s), (2, 8), rel_tol=0.01, abs_tol=0.0)
    assert out.steps == 8 and out.error == pytest.approx(4.0)  # reported as it is, never hidden
    with pytest.raises(ValueError):
        adaptive_ig(lambda s: out, (), rel_tol=0.1, abs_tol=0.0)
