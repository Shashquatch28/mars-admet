"""The torch-free parts of Integrated Gradients on KERMT's graph inputs (ADR-031). numpy only.

KERMT's input to the message-passing encoder is two tensors, both indexed from 1 (row 0 is padding):

* `f_atoms[a]`  - the features of atom a;
* `f_bonds[b]`  - the features of directed bond b: the features of its SOURCE atom (`b2a[b]`) followed by
  the bond's own features.

Integrated Gradients attributes the output to every number in those tensors (and to the whole-molecule
descriptor vector). `fold_to_atoms` turns that into one number per atom without losing or inventing any of
it: the source-atom block of a directed bond belongs to its source atom, and a bond's own features are
split equally between the bond's two atoms. The atom scores therefore sum to exactly the total attribution
placed on the two graph tensors.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np


def midpoint_alphas(steps: int) -> np.ndarray:
    """Midpoints of `steps` equal intervals of [0, 1]: the interpolation points of the midpoint rule."""
    if steps < 1:
        raise ValueError("steps must be at least 1")
    return (np.arange(steps) + 0.5) / steps


def power_quadrature(steps: int, power: int = 2) -> tuple[np.ndarray, np.ndarray]:
    """Interpolation points and weights for integrating over alpha in [0, 1] with the substitution
    alpha = u**power, midpoint rule in u. Points crowd toward alpha = 0, where KERMT's output changes
    fastest (measured on a randomly initialised model: most of the change happens for alpha < 0.05, which a
    uniform grid samples only a few times). The weights sum to 1, so `sum(w * g(alpha))` replaces the plain
    mean of gradients. power = 1 is the uniform midpoint rule."""
    if steps < 1 or power < 1:
        raise ValueError("steps and power must be at least 1")
    u = (np.arange(steps) + 0.5) / steps
    return u**power, power * u ** (power - 1) / steps


def fold_to_atoms(
    attr_atoms: np.ndarray,
    attr_bonds: np.ndarray,
    b2a: np.ndarray,
    b2revb: np.ndarray,
    atom_fdim: int,
) -> np.ndarray:
    """Per-atom scores from attributions on `f_atoms` and `f_bonds` (both with a padding row 0).

    attr_atoms: (n_atoms + 1, atom_fdim); attr_bonds: (n_bonds + 1, atom_fdim + bond_feature_dim);
    b2a, b2revb: (n_bonds + 1,) integer maps, 1-based, entry 0 unused. Returns (n_atoms,).
    """
    n_atoms = attr_atoms.shape[0] - 1
    scores = np.zeros(n_atoms, dtype=np.float64)
    scores += attr_atoms[1:].sum(axis=1)
    for b in range(1, attr_bonds.shape[0]):
        source = int(b2a[b])
        partner = int(b2a[int(b2revb[b])])
        own = float(attr_bonds[b, atom_fdim:].sum())
        scores[source - 1] += float(attr_bonds[b, :atom_fdim].sum()) + own / 2.0
        scores[partner - 1] += own / 2.0
    return scores


@dataclass(frozen=True)
class IGOutcome:
    """One Integrated Gradients run at a fixed step count, for one scalar output."""

    steps: int
    total_attribution: float  # sum of every input attribution
    delta: float  # f(x) - f(baseline)
    payload: object  # whatever the caller needs back (the per-input attributions)

    @property
    def error(self) -> float:
        return abs(self.total_attribution - self.delta)


def within_tolerance(error: float, delta: float, rel_tol: float, abs_tol: float) -> bool:
    """Completeness holds when the error is small against the change being explained, with a floor so a
    near-zero change is not asked for impossible relative precision."""
    return error <= max(rel_tol * abs(delta), abs_tol)


def adaptive_ig(
    run: Callable[[int], IGOutcome], schedule: tuple[int, ...], *, rel_tol: float, abs_tol: float
) -> IGOutcome:
    """Run at each step count in `schedule` (increasing) until completeness holds, and return the first run
    that satisfies it; if none does, the last (finest) run, whose `error` the caller reports as it is."""
    if not schedule:
        raise ValueError("schedule must not be empty")
    outcome = None
    for steps in schedule:
        outcome = run(steps)
        if within_tolerance(outcome.error, outcome.delta, rel_tol, abs_tol):
            return outcome
    assert outcome is not None
    return outcome
