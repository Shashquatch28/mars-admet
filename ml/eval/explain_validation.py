"""Blueprint Module 6 "dual validation" for the explainers (ADR-029), measured not asserted.

1. **Perturbation check.** Take the group with the largest absolute structure attribution, delete its
   atoms, re-run the model, and ask whether the output moved the way the attribution said it would
   (a group that pushed the output UP should lower it when removed). Reported next to a control that
   deletes an equally sized, randomly placed connected set of atoms, so "better than coin-flip" is
   something this script shows rather than assumes. Deleting atoms also changes the whole-molecule
   descriptors, which the structure attribution does not describe, so concordance well below 100% is
   expected; the honest number is the lift over the control.
2. **Structural-alert cross-check.** For the endpoints where the blueprint expects explanations to find
   known liabilities, compare the mean atom attribution inside PAINS/Brenk alert matches with the
   rest of the same molecule, and with a size-matched random set, on the held-out test molecules.

Both run on the held-out test split and report what they found, including when it is weak. They say
nothing about the biology of a group; they test whether the model's own output agrees with its
explanation, and whether the attribution lines up with published alert definitions.
"""

from __future__ import annotations

import argparse
import random
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from rdkit import Chem
from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams

ALERT_CATALOGS = {
    "PAINS": FilterCatalogParams.FilterCatalogs.PAINS,
    "Brenk": FilterCatalogParams.FilterCatalogs.BRENK,
}
# Where the blueprint expects explanations to surface known toxicophores.
ALERT_ENDPOINTS = ("ames_mutagenicity", "dili_liver_injury", "herg_cardiotoxicity")


def remove_atoms(mol: Chem.Mol, atoms: set[int]) -> Chem.Mol | None:
    """`mol` without `atoms`, keeping the largest remaining connected piece. None if nothing sensible remains."""
    if not atoms or len(atoms) >= mol.GetNumAtoms():
        return None
    rw = Chem.RWMol(mol)
    try:
        # Deleting part of an aromatic ring leaves atoms flagged aromatic with no ring; kekulize first so
        # the remainder is an ordinary valid molecule.
        Chem.Kekulize(rw, clearAromaticFlags=True)
        for idx in sorted(atoms, reverse=True):
            rw.RemoveAtom(idx)
        pieces = Chem.GetMolFrags(rw.GetMol(), asMols=True, sanitizeFrags=True)
    except Exception:
        return None
    if not pieces:
        return None
    biggest = max(pieces, key=lambda m: m.GetNumAtoms())
    return biggest if biggest.GetNumAtoms() >= 3 else None


def random_connected_atoms(mol: Chem.Mol, size: int, rng: random.Random) -> set[int]:
    """A random connected set of `size` atoms (breadth-first from a random start); fewer if the molecule is smaller."""
    n = mol.GetNumAtoms()
    size = min(size, n)
    start = rng.randrange(n)
    chosen = [start]
    seen = {start}
    frontier = [start]
    while frontier and len(chosen) < size:
        nxt = []
        for a in frontier:
            neighbours = [x.GetIdx() for x in mol.GetAtomWithIdx(a).GetNeighbors() if x.GetIdx() not in seen]
            rng.shuffle(neighbours)
            for b in neighbours:
                if len(chosen) >= size:
                    break
                seen.add(b)
                chosen.append(b)
                nxt.append(b)
        frontier = nxt
    return set(chosen)


def alert_matches(mol: Chem.Mol, catalogs: dict[str, FilterCatalogParams.FilterCatalogs] = ALERT_CATALOGS) -> list[tuple[str, str, set[int]]]:
    """(catalog, alert description, matched atoms) for every PAINS/Brenk match in `mol`."""
    out = []
    for name, which in catalogs.items():
        params = FilterCatalogParams()
        params.AddCatalog(which)
        catalog = FilterCatalog(params)
        for entry in catalog.GetMatches(mol):
            for match in entry.GetFilterMatches(mol):
                out.append((name, entry.GetDescription(), {mol_idx for _q, mol_idx in match.atomPairs}))
    return out


@dataclass(frozen=True)
class PerturbationResult:
    n: int
    concordance: float  # share of molecules whose output moved against the top group's sign
    control_concordance: float
    mean_abs_delta: float
    control_mean_abs_delta: float


def perturbation_check(
    smiles: list[str],
    explain: Callable[[str], tuple[np.ndarray, list[tuple[tuple[int, ...], float]], float] | None],
    output_of: Callable[[str], float | None],
    *,
    seed: int = 0,
) -> PerturbationResult:
    """`explain(smi)` -> (atom_scores, [(group atoms, group score)] largest first, output) or None.
    `output_of(smi)` -> the model output for a (modified) molecule, or None if it cannot be scored."""
    rng = random.Random(seed)
    hit = ctl_hit = n = 0
    deltas, ctl_deltas = [], []
    for smi in smiles:
        exp = explain(smi)
        if exp is None:
            continue
        atom_scores, groups, out0 = exp
        if not groups:
            continue
        mol = Chem.MolFromSmiles(smi)
        atoms, score = groups[0]
        ctl_atoms = random_connected_atoms(mol, len(atoms), rng)
        ctl_score = float(atom_scores[list(ctl_atoms)].sum())
        pert, ctl_pert = remove_atoms(mol, set(atoms)), remove_atoms(mol, ctl_atoms)
        if pert is None or ctl_pert is None or score == 0 or ctl_score == 0:
            continue
        out1, out_c = output_of(Chem.MolToSmiles(pert)), output_of(Chem.MolToSmiles(ctl_pert))
        if out1 is None or out_c is None:
            continue
        n += 1
        d, dc = out1 - out0, out_c - out0
        hit += d * score < 0  # removing a group that pushed the output up should lower it
        ctl_hit += dc * ctl_score < 0
        deltas.append(abs(d))
        ctl_deltas.append(abs(dc))
    if n == 0:
        return PerturbationResult(0, float("nan"), float("nan"), float("nan"), float("nan"))
    return PerturbationResult(n, hit / n, ctl_hit / n, float(np.mean(deltas)), float(np.mean(ctl_deltas)))


@dataclass(frozen=True)
class AlertResult:
    endpoint: str
    n_molecules: int  # test molecules with at least one alert match
    mean_alert: float  # mean atom attribution inside alert atoms
    mean_rest: float  # ... in the other atoms of the same molecules
    mean_random: float  # ... in size-matched random atoms
    share_alert_above_rest: float
    share_alert_above_random: float


def alert_check(
    smiles: list[str], atom_scores_of: Callable[[str], np.ndarray | None], endpoint: str, *, seed: int = 0
) -> AlertResult:
    rng = random.Random(seed)
    a_means, r_means, c_means = [], [], []
    for smi in smiles:
        mol = Chem.MolFromSmiles(smi)
        matches = alert_matches(mol) if mol is not None else []
        if not matches:
            continue
        scores = atom_scores_of(smi)
        if scores is None:
            continue
        alert_atoms = set().union(*(m[2] for m in matches))
        rest = [i for i in range(mol.GetNumAtoms()) if i not in alert_atoms]
        if not rest:
            continue
        a_means.append(float(scores[list(alert_atoms)].mean()))
        r_means.append(float(scores[rest].mean()))
        ctl = random_connected_atoms(mol, len(alert_atoms), rng)
        c_means.append(float(scores[list(ctl)].mean()))
    if not a_means:
        return AlertResult(endpoint, 0, *([float("nan")] * 5))
    a, r, c = np.array(a_means), np.array(r_means), np.array(c_means)
    return AlertResult(endpoint, len(a), float(a.mean()), float(r.mean()), float(c.mean()), float((a > r).mean()), float((a > c).mean()))


def _cli() -> None:  # pragma: no cover - needs promoted artifacts and processed data
    import sys
    from pathlib import Path

    import pandas as pd
    from data.loaders import load_endpoint
    from explain.tree_shap import explain_xgboost
    from featurize.cache import FeatureCache
    from serve.registry import ModelRegistry

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--artifacts", type=Path, default=Path(__file__).resolve().parents[1] / "artifacts")
    ap.add_argument("--cache", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "cache")
    ap.add_argument("--prep-dir", type=Path, required=True, help="ml/data/processed/<prep_id>")
    ap.add_argument("--endpoints", nargs="+", default=list(ALERT_ENDPOINTS) + ["solubility_logs", "lipophilicity_logp", "caco2_permeability"])
    ap.add_argument("--n", type=int, default=150, help="held-out test molecules per endpoint")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    registry = ModelRegistry(FeatureCache(args.cache), artifacts_root=args.artifacts)
    lines = ["| endpoint | molecules | top-group concordance | control concordance | mean abs shift (top) | mean abs shift (control) |", "|---|---|---|---|---|---|"]
    alert_lines = ["| endpoint | molecules with an alert | mean attribution in alert atoms | in the rest | in random atoms | alert > rest | alert > random |", "|---|---|---|---|---|---|---|"]
    for ep in args.endpoints:
        data = load_endpoint(args.prep_dir, ep)
        test: pd.DataFrame = data.test.sample(n=min(args.n, len(data.test)), random_state=args.seed)
        smiles = test["standardized_smiles"].tolist()
        cache: dict[str, object] = {}

        def explained(smi: str, _ep=ep, _cache=cache):
            if smi not in _cache:
                try:
                    _cache[smi] = explain_xgboost(registry, _ep, smi)
                except ValueError:
                    _cache[smi] = None
            return _cache[smi]

        def for_perturbation(smi: str):
            r = explained(smi)
            if r is None:
                return None
            groups = [(f.atom_indices, f.score) for f in r.fragments]
            return np.asarray(r.atom_attributions), groups, r.output_value

        def output_of(smi: str):
            r = explained(smi)
            return None if r is None else r.output_value

        res = perturbation_check(smiles, for_perturbation, output_of, seed=args.seed)
        lines.append(f"| {ep} | {res.n} | {res.concordance:.2f} | {res.control_concordance:.2f} | {res.mean_abs_delta:.3f} | {res.control_mean_abs_delta:.3f} |")
        if ep in ALERT_ENDPOINTS:
            al = alert_check(smiles, lambda s: None if explained(s) is None else np.asarray(explained(s).atom_attributions), ep, seed=args.seed)
            alert_lines.append(
                f"| {ep} | {al.n_molecules} | {al.mean_alert:+.4f} | {al.mean_rest:+.4f} | {al.mean_random:+.4f} | {al.share_alert_above_rest:.2f} | {al.share_alert_above_random:.2f} |"
            )
        print(f"done {ep}", file=sys.stderr)

    print("## Perturbation check\n\n" + "\n".join(lines) + "\n\n## Structural-alert cross-check\n\n" + "\n".join(alert_lines))


if __name__ == "__main__":
    _cli()
