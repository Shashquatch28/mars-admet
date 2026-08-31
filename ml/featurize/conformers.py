"""
Module 3 Stage 5 — 3D conformer generation.

Blueprint requirements this implements:

  * ETKDG embedding (ETKDGv3) + MMFF94 optimization
  * deterministic seed handling (fixed ``randomSeed``)
  * single **lowest-energy** conformer selected from a small ensemble
  * MMFF94 energy recorded
  * graceful handling of molecules for which MMFF optimization fails
    (fall back to UFF; record which force field was used)
  * **do NOT fabricate a conformer when generation fails** — return a typed
    failure record instead
  * output maps directly onto ``contracts.conformer.ConformerResponse``
    (atoms with Gasteiger ``partial_charge``, bonds with order incl. 1.5
    aromatic, ``energy_kcal_mol``, ``sdf_block``)
  * expensive → cache per molecule (the cache itself lands in Run 4; this
    module is written so the result object is trivially serialisable and
    keyed by ``(standardized_smiles, CONFORMER_VERSION)``)

Stereo note (blueprint Module 3 §Stereochemistry): ETKDG is inherently
stereo-aware — 3D coordinates directly encode a stereocenter's configuration.
No extra handling needed; a defined ``[C@]`` produces the correct geometry and
an undefined center is embedded in whatever configuration ETKDG's knowledge
distance-geometry picks (not "fabricated" chirality — the SMILES chiral tag is
still unset).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem

_LOGGER = RDLogger.logger()
_LOGGER.setLevel(RDLogger.CRITICAL)


CONFORMER_VERSION = "mars-etkdgv3-mmff94-lowest-of-n-v1"


@dataclass(frozen=True)
class ConformerConfig:
    n_conformers: int = 10
    random_seed: int = 0xC0FFEE
    mmff_max_iters: int = 2000
    uff_fallback: bool = True
    add_hydrogens: bool = True
    version: str = CONFORMER_VERSION

    def cache_key(self) -> str:
        return (
            f"{self.version}|n={self.n_conformers}|seed={self.random_seed}"
            f"|mmffit={self.mmff_max_iters}|uff={int(self.uff_fallback)}"
        )


@dataclass(frozen=True)
class ConformerAtom:
    element: str
    x: float
    y: float
    z: float
    partial_charge: float | None


@dataclass(frozen=True)
class ConformerBond:
    atom_index_1: int
    atom_index_2: int
    order: float  # 1, 1.5 (aromatic), 2, 3


@dataclass(frozen=True)
class ConformerResult:
    smiles: str
    ok: bool
    reason: str | None = None
    force_field: Literal["MMFF94", "UFF", None] = None
    energy_kcal_mol: float | None = None
    n_conformers_tried: int = 0
    atoms: list[ConformerAtom] = field(default_factory=list)
    bonds: list[ConformerBond] = field(default_factory=list)
    sdf_block: str | None = None
    version: str = CONFORMER_VERSION

    def to_contract_dict(self, molecule_id: str) -> dict[str, Any]:
        """Shape that constructs ``contracts.conformer.ConformerResponse``.

        Raises if this result is a failure — callers must check ``ok`` first
        (the contract has no representation for "no conformer", by design —
        Module 8 returns an error status instead).
        """
        if not self.ok:
            raise ValueError(f"conformer generation failed ({self.reason}); no contract payload")
        return {
            "molecule_id": molecule_id,
            "atoms": [
                {"element": a.element, "x": a.x, "y": a.y, "z": a.z, "partial_charge": a.partial_charge}
                for a in self.atoms
            ],
            "bonds": [
                {"atom_index_1": b.atom_index_1, "atom_index_2": b.atom_index_2, "order": b.order}
                for b in self.bonds
            ],
            "energy_kcal_mol": self.energy_kcal_mol,
            "sdf_block": self.sdf_block,
        }


REJECTION_REASONS = frozenset(
    {
        "smiles-parse-failed",
        "embedding-failed",
        "optimization-failed",
        "unexpected-error",
    }
)


def _fail(smiles: str, reason: str, tried: int = 0) -> ConformerResult:
    assert reason in REJECTION_REASONS, reason
    return ConformerResult(smiles=smiles, ok=False, reason=reason, n_conformers_tried=tried)


def generate_conformer(smiles: str, config: ConformerConfig | None = None) -> ConformerResult:
    """Embed an ETKDGv3 ensemble, optimise (MMFF94, UFF fallback), return the
    lowest-energy conformer. Never raises for a bad molecule."""
    cfg = config or ConformerConfig()
    if not smiles:
        return _fail(smiles or "", "smiles-parse-failed")

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return _fail(smiles, "smiles-parse-failed")

    try:
        work = Chem.AddHs(mol) if cfg.add_hydrogens else Chem.Mol(mol)

        params = AllChem.ETKDGv3()
        params.randomSeed = cfg.random_seed
        params.useRandomCoords = False
        conf_ids = list(
            AllChem.EmbedMultipleConfs(work, numConfs=cfg.n_conformers, params=params)
        )
        if not conf_ids:
            # one retry with random coords — still deterministic (fixed seed)
            params.useRandomCoords = True
            conf_ids = list(
                AllChem.EmbedMultipleConfs(work, numConfs=cfg.n_conformers, params=params)
            )
        if not conf_ids:
            return _fail(smiles, "embedding-failed")

        force_field, energies = _optimise(work, conf_ids, cfg)
        if energies is None:
            return _fail(smiles, "optimization-failed", tried=len(conf_ids))

        best_local = min(range(len(conf_ids)), key=lambda i: energies[i])
        best_cid = conf_ids[best_local]
        best_energy = float(energies[best_local])

        AllChem.ComputeGasteigerCharges(work)
        atoms = _atoms(work, best_cid)
        bonds = _bonds(work)
        sdf = Chem.MolToMolBlock(work, confId=best_cid)

        return ConformerResult(
            smiles=smiles,
            ok=True,
            force_field=force_field,
            energy_kcal_mol=best_energy,
            n_conformers_tried=len(conf_ids),
            atoms=atoms,
            bonds=bonds,
            sdf_block=sdf,
        )
    except Exception:  # noqa: BLE001 — RDKit raises many concrete classes
        return _fail(smiles, "unexpected-error")


def _optimise(mol: Chem.Mol, conf_ids: list[int], cfg: ConformerConfig):
    """Return ``(force_field_name, energies_list)`` or ``(None, None)`` on total failure."""
    # MMFF94 first
    if AllChem.MMFFHasAllMoleculeParams(mol):
        results = AllChem.MMFFOptimizeMoleculeConfs(mol, maxIters=cfg.mmff_max_iters)
        energies = [e for _conv, e in results]
        if energies and all(e == e for e in energies):  # no NaN
            return "MMFF94", energies

    if not cfg.uff_fallback:
        return None, None

    # UFF fallback
    results = AllChem.UFFOptimizeMoleculeConfs(mol, maxIters=cfg.mmff_max_iters)
    energies = [e for _conv, e in results]
    if energies and all(e == e for e in energies):
        return "UFF", energies
    return None, None


def _atoms(mol: Chem.Mol, conf_id: int) -> list[ConformerAtom]:
    conf = mol.GetConformer(conf_id)
    out: list[ConformerAtom] = []
    for atom in mol.GetAtoms():
        pos = conf.GetAtomPosition(atom.GetIdx())
        try:
            charge = float(atom.GetDoubleProp("_GasteigerCharge"))
            if charge != charge:  # NaN
                charge = None
        except KeyError:
            charge = None
        out.append(
            ConformerAtom(
                element=atom.GetSymbol(),
                x=float(pos.x),
                y=float(pos.y),
                z=float(pos.z),
                partial_charge=charge,
            )
        )
    return out


def _bonds(mol: Chem.Mol) -> list[ConformerBond]:
    return [
        ConformerBond(
            atom_index_1=b.GetBeginAtomIdx(),
            atom_index_2=b.GetEndAtomIdx(),
            order=float(b.GetBondTypeAsDouble()),  # 1.0 / 1.5 / 2.0 / 3.0
        )
        for b in mol.GetBonds()
    ]


def generate_conformers_batch(
    smiles_list: Iterable[str],
    config: ConformerConfig | None = None,
) -> list[ConformerResult]:
    """One :class:`ConformerResult` per input, in order (failures included, never
    dropped — the caller decides what to do with a failure)."""
    cfg = config or ConformerConfig()
    return [generate_conformer(s, cfg) for s in smiles_list]


def rejection_summary(results: list[ConformerResult]) -> dict[str, int]:
    counts: dict[str, int] = {"ok": 0, "MMFF94": 0, "UFF": 0}
    for r in results:
        if r.ok:
            counts["ok"] += 1
            counts[r.force_field or "MMFF94"] += 1
        else:
            key = r.reason or "unexpected-error"
            counts[key] = counts.get(key, 0) + 1
    return counts
