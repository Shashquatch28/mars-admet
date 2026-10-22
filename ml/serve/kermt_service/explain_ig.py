"""Integrated Gradients for the Tier-0 KERMT checkpoints (ADR-031). Runs only inside the KERMT image.

What is attributed. One scalar: the checkpoint's own eval-mode output for one target, exactly what
`engine.predict` returns before the inverse target scaler (classification: the mean of the two heads'
sigmoids, a 0-1 score; regression: the scaled value, converted to the endpoint's unit afterwards). The
inputs are the three things the model reads: the atom feature tensor, the directed-bond feature tensor
(which carries each bond's source-atom features) and the whole-molecule RDKit descriptor vector.

The path. A straight line from the baseline to the molecule, on all three inputs together, integrated with the
midpoint rule after the substitution alpha = u**3 (`explain.graph_ig.power_quadrature`). A uniform grid does not
converge: measured on a randomly initialised KERMT, most of the output change happens for alpha < 0.05 and the
completeness error of the uniform midpoint rule was erratic (5-100% of the change at 16-256 steps), while the
cubic substitution reached 0.1-2% by 128 steps. That measurement was on a toy model and must be repeated on the
real checkpoints (the KERMT image). The baseline for the two graph tensors is zero (an empty graph); the
descriptor baseline is a constant chosen by the caller and echoed in the response. The gradient at each
point comes from KERMT's unmodified `forward` (eval mode, no dropout): the graph tensors are made leaf
tensors, and the gradient with respect to the descriptors is read from the input of the two readout FFNs,
which is where the descriptors enter (`cat([readout, features])`), so the model is not re-implemented here.
`steps` copies of the molecule go through as one batch (they are independent: the encoder never mixes
graphs), `chunk` at a time, and the engine lock is held only per chunk so predictions interleave.

Completeness: sum(attributions) = f(x) - f(baseline). The residual is measured, and the step count is raised
(`schedule`) until it is within tolerance; whatever remains is returned as `unmapped_total`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from explain.graph_ig import IGOutcome, adaptive_ig, fold_to_atoms, power_quadrature

logger = logging.getLogger("mars.kermt_ig")

DEFAULT_SCHEDULE = (64, 128, 256)
DEFAULT_CHUNK = 16
DEFAULT_REL_TOL = 0.05
DEFAULT_ABS_TOL = 1e-3
DEFAULT_DESCRIPTOR_BASELINE = 0.0
DEFAULT_POWER = 3  # alpha = u**3: points crowd toward the baseline, where the output changes fastest


@dataclass(frozen=True)
class SeedAttribution:
    atom_scores: np.ndarray  # (n_atoms,), in the model's own output units for this seed
    descriptor_scores: np.ndarray  # (n_descriptors,)
    f_x: float
    f_baseline: float
    steps: int


def _scaler_params(lm, target_index: int) -> tuple[float, float] | None:
    """(mean, std) of the target for a regression checkpoint, or None when there is no scaler."""
    scaler = lm.scaler
    if scaler is None:
        return None
    means = np.asarray(scaler.means, dtype=float).reshape(-1)
    stds = np.asarray(scaler.stds, dtype=float).reshape(-1)
    return float(means[target_index]), float(stds[target_index])


def attribute_checkpoint(
    lm,
    smiles: str,
    descriptors: np.ndarray,
    target_index: int,
    *,
    shared_dict: dict,
    lock,
    schedule: tuple[int, ...] = DEFAULT_SCHEDULE,
    chunk: int = DEFAULT_CHUNK,
    rel_tol: float = DEFAULT_REL_TOL,
    abs_tol: float = DEFAULT_ABS_TOL,
    descriptor_baseline: float = DEFAULT_DESCRIPTOR_BASELINE,
    power: int = DEFAULT_POWER,
) -> SeedAttribution:
    """Integrated Gradients of one checkpoint's output for `target_index` on one molecule."""
    import torch
    from kermt.data.molgraph import get_atom_fdim, mol2graph

    model, args = lm.model, lm.args
    model.eval()
    args.bond_drop_rate = 0
    x_desc = np.asarray(descriptors, dtype=np.float64)
    b_desc = np.full_like(x_desc, descriptor_baseline)
    d = x_desc.shape[0]
    atom_fdim = get_atom_fdim()

    def graph(copies: int):
        return mol2graph([smiles] * copies, shared_dict, args).get_components()

    one = graph(1)
    f_atoms1, f_bonds1, _a2b, b2a1, b2revb1 = one[0], one[1], one[2], one[3], one[4]
    n_atoms, n_bonds = f_atoms1.shape[0] - 1, f_bonds1.shape[0] - 1

    def evaluate(alphas: list[float], *, grad: bool, weights: np.ndarray | None = None):
        """Outputs (k,) and, if `grad`, the weighted sum over the k copies of the gradients for atoms, bonds and descriptors."""
        k = len(alphas)
        comps = graph(k)
        a_t = torch.tensor(alphas, dtype=torch.float32)
        atoms_alpha = torch.cat([torch.zeros(1), a_t.repeat_interleave(n_atoms)])
        bonds_alpha = torch.cat([torch.zeros(1), a_t.repeat_interleave(n_bonds)])
        f_atoms = (comps[0] * atoms_alpha[:, None]).detach().requires_grad_(grad)
        f_bonds = (comps[1] * bonds_alpha[:, None]).detach().requires_grad_(grad)
        feats = [b_desc + a * (x_desc - b_desc) for a in alphas]
        captured: list = []

        def grab(_module, inputs):
            captured.append(inputs[0])

        hooks = [
            model.mol_atom_from_atom_ffn.register_forward_pre_hook(grab),
            model.mol_atom_from_bond_ffn.register_forward_pre_hook(grab),
        ]
        try:
            with lock:
                with torch.set_grad_enabled(grad):
                    out = model((f_atoms, f_bonds, *comps[2:]), feats)
                    y = out[:, target_index]
                    if grad:
                        # Copies are independent, so d(weighted sum)/d(input) is each copy's own gradient times its
                        # weight. autograd.grad asks for the inputs only: .backward() would also compute, and keep in
                        # every parameter's .grad, the gradient of all ~70M weights, which IG never uses (measured
                        # 2026-10-22: it made one explanation take minutes and about 2.8 GB of working memory).
                        wsum = (y * torch.as_tensor(weights, dtype=y.dtype)).sum()
                        grads = torch.autograd.grad(wsum, [f_atoms, f_bonds, *captured])
        finally:
            for h in hooks:
                h.remove()
        values = y.detach().cpu().numpy().astype(np.float64)
        if not grad:
            return values, None
        # explicit widths, not -1: a molecule with no bonds (methane) has zero bond rows and -1 is ambiguous
        g_atoms = grads[0][1:].reshape(k, n_atoms, grads[0].shape[1]).sum(0).cpu().numpy()
        g_bonds = grads[1][1:].reshape(k, n_bonds, grads[1].shape[1]).sum(0).cpu().numpy()
        g_desc = sum(g[:, -d:] for g in grads[2:]).sum(0).cpu().numpy()
        return values, (g_atoms, g_bonds, g_desc)

    f_x = float(evaluate([1.0], grad=False)[0][0])
    f_b = float(evaluate([0.0], grad=False)[0][0])
    x_atoms = f_atoms1[1:].cpu().numpy().astype(np.float64)
    x_bonds = f_bonds1[1:].cpu().numpy().astype(np.float64)
    b2a, b2revb = b2a1.cpu().numpy(), b2revb1.cpu().numpy()

    def run(steps: int) -> IGOutcome:
        g_a = np.zeros_like(x_atoms)
        g_b = np.zeros_like(x_bonds)
        g_d = np.zeros(d)
        alphas, weights = power_quadrature(steps, power)
        for start in range(0, steps, chunk):
            sl = slice(start, start + chunk)
            _, (ga, gb, gd) = evaluate(alphas[sl].tolist(), grad=True, weights=weights[sl])
            g_a += ga
            g_b += gb
            g_d += gd
        attr_atoms = x_atoms * g_a  # (x - 0) * quadrature-weighted gradient
        attr_bonds = x_bonds * g_b
        attr_desc = (x_desc - b_desc) * g_d
        total = float(attr_atoms.sum() + attr_bonds.sum() + attr_desc.sum())
        return IGOutcome(steps, total, f_x - f_b, (attr_atoms, attr_bonds, attr_desc))

    outcome = adaptive_ig(run, schedule, rel_tol=rel_tol, abs_tol=abs_tol)
    attr_atoms, attr_bonds, attr_desc = outcome.payload
    atom_scores = fold_to_atoms(_pad(attr_atoms), _pad(attr_bonds), b2a, b2revb, atom_fdim)
    return SeedAttribution(atom_scores, attr_desc, f_x, f_b, outcome.steps)


def _pad(a: np.ndarray) -> np.ndarray:
    """Prepend KERMT's padding row 0 (no atom, no bond)."""
    return np.vstack([np.zeros((1, a.shape[1])), a])


def raw_descriptor_values(smiles: str, names: list[str]) -> list[float | None]:
    """This molecule's raw (un-normalised) value for each named RDKit descriptor, for display. The model reads
    the normalised value; the raw one is what a chemist recognises. None where RDKit does not list the name or
    the value is not finite."""
    from rdkit import Chem
    from rdkit.Chem import Descriptors

    mol = Chem.MolFromSmiles(smiles)
    table = dict(Descriptors._descList)
    out: list[float | None] = []
    for name in names:
        fn = table.get(name)
        try:
            v = float(fn(mol)) if fn is not None and mol is not None else None
        except Exception:
            v = None
        out.append(v if v is not None and np.isfinite(v) else None)
    return out


def descriptor_names(n: int) -> list[str]:
    """Names of KERMT's `rdkit_2d_normalized` features. descriptastorus lists a leading 'calculated' flag
    that the generator drops (`process(smiles)[1:]`); if the names cannot be matched to the vector, say so
    rather than guess."""
    try:
        from descriptastorus.descriptors import rdNormalizedDescriptors

        names = [c[0] if isinstance(c, (tuple, list)) else str(c) for c in rdNormalizedDescriptors.RDKit2DNormalized().columns][1:]
        if len(names) == n:
            return names
        logger.warning("descriptastorus lists %d descriptors but the model reads %d", len(names), n)
    except Exception:  # pragma: no cover - depends on the image
        logger.warning("could not read descriptor names from descriptastorus")
    return [f"rdkit2d_feature_{i}" for i in range(n)]
