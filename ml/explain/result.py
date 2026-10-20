"""One explanation, independent of the method that produced it (ADR-031).

`assemble` is the single place where the totals are computed, so TreeSHAP and Integrated Gradients
cannot disagree about what "structure", "whole-molecule" and "unmapped" mean, and where the
completeness error is measured rather than asserted.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from rdkit import Chem

from explain.structure import FragmentScore, fragment_scores

TOP_DESCRIPTORS = 12


@dataclass(frozen=True)
class DescriptorScore:
    name: str
    value: float | None
    score: float


@dataclass(frozen=True)
class ExplanationResult:
    endpoint: str
    method: str  # mars_contracts.ExplainMethod value
    model_id: str
    output_space: str  # mars_contracts.ExplainOutputSpace value
    n_seeds: int
    base_value: float
    output_value: float
    baseline: str
    atom_attributions: tuple[float, ...]
    fragments: tuple[FragmentScore, ...]
    descriptors: tuple[DescriptorScore, ...]  # largest by |score|
    whole_molecule_rest: float
    structure_total: float
    whole_molecule_total: float
    unmapped_total: float
    completeness_error: float
    n_steps: int | None = None


def _finite(x: float) -> float | None:
    return float(x) if np.isfinite(x) else None


def assemble(
    *,
    endpoint: str,
    method: str,
    model_id: str,
    output_space: str,
    n_seeds: int,
    base_value: float,
    output_value: float,
    baseline: str,
    mol: Chem.Mol,
    atom_scores: np.ndarray,
    descriptor_names: list[str],
    descriptor_values: np.ndarray,
    descriptor_scores: np.ndarray,
    unmapped_total: float,
    n_steps: int | None = None,
    top_descriptors: int = TOP_DESCRIPTORS,
) -> ExplanationResult:
    """Build the result and measure how far base + parts is from the output (the completeness error)."""
    if len(atom_scores) != mol.GetNumAtoms():
        raise ValueError(f"{len(atom_scores)} atom scores for a molecule with {mol.GetNumAtoms()} atoms")
    structure_total = float(np.sum(atom_scores))
    whole_total = float(np.sum(descriptor_scores))
    order = np.argsort(-np.abs(descriptor_scores), kind="stable")[:top_descriptors]
    listed = [
        DescriptorScore(descriptor_names[i], _finite(descriptor_values[i]), float(descriptor_scores[i])) for i in order
    ]
    rest = whole_total - sum(d.score for d in listed)
    error = abs(base_value + structure_total + whole_total + unmapped_total - output_value)
    return ExplanationResult(
        endpoint=endpoint,
        method=method,
        model_id=model_id,
        output_space=output_space,
        n_seeds=n_seeds,
        base_value=float(base_value),
        output_value=float(output_value),
        baseline=baseline,
        atom_attributions=tuple(float(s) for s in atom_scores),
        fragments=tuple(fragment_scores(mol, atom_scores)),
        descriptors=tuple(listed),
        whole_molecule_rest=float(rest),
        structure_total=structure_total,
        whole_molecule_total=whole_total,
        unmapped_total=float(unmapped_total),
        completeness_error=float(error),
        n_steps=n_steps,
    )
