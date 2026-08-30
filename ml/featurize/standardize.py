"""
Module 3 Stage 1 — RDKit molecule standardization.

Blueprint requirements this implements:

  1. Parse and validate SMILES (reject invalid with a clear, deterministic reason)
  2. Strip salts / counterions (largest organic fragment)
  3. Normalize charge state (RDKit ``Uncharger``; neutralize where possible)
  4. Apply RDKit's normalization rules (nitro / azide / iminium / …)
  5. Canonicalize output (round-tripped through canonical SMILES)
  6. Preserve *defined* stereochemistry; do NOT fabricate undefined stereo
  7. Deterministic: same input → same output on any run, any machine
  8. Batched: designed for lists of molecules, not one-at-a-time

This is a **library**, not a script. Every downstream stage (dedup, split,
augmentation, featurization) calls into it — never re-implements standardization.

Tautomer handling is *not* applied by default (see design note below).

Design decisions worth reading
------------------------------

**Why not the built-in ``rdMolStandardize.CleanupInPlace`` alone?**
The blueprint requires a specific ordered pipeline (§Module 3 Stage 1), an
auditable rejection reason per molecule, and no fabricated stereochemistry. We
compose the individual RDKit components in a deterministic order and record the
outcome per input, which the one-shot cleanup does not do.

**Why is tautomer canonicalization off by default?**
RDKit's ``TautomerEnumerator.Canonicalize`` gives a canonical tautomer but is
sometimes chemically counter-intuitive (e.g. it will pick an enol form for some
keto molecules). Blueprint Module 3 says "normalize tautomers/charge state"
without prescribing a specific canonical form. We expose it as an option
(``canonicalize_tautomer=True``) so an EDA-gated decision can flip it on later
per endpoint if it materially changes conflict rates; keeping it off by default
avoids silently reshaping every input.

**Why isomeric-canonical SMILES?**
Two enantiomers must produce different canonical SMILES so they hash to
different snapshot/dedup identities. ``Chem.MolToSmiles(mol, isomericSmiles=True)``
is the RDKit contract we depend on. Blueprint Module 3 §Stereochemistry
requires stereo information to survive standardization.

Rejection reasons are drawn from a fixed enum-like set of short kebab-case
codes so downstream code (Module 11 self-audit, EDA reports) can group them
without parsing free text.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem  # noqa: F401  (loads reaction/SMARTS backends)
from rdkit.Chem.MolStandardize import rdMolStandardize

# Silence RDKit's C++ warning stream; we capture per-mol errors ourselves.
_LOGGER = RDLogger.logger()
_LOGGER.setLevel(RDLogger.CRITICAL)


# ---------------------------------------------------------------------------- #
# Configuration + result types
# ---------------------------------------------------------------------------- #

STANDARDIZER_VERSION = "mars-standardizer-v1"
"""Bumped when the pipeline's semantic output can change. Cached feature stores
must key on this value; a mismatch invalidates the cache."""


REJECTION_REASONS = frozenset(
    {
        "empty-input",
        "smiles-parse-failed",
        "sanitize-failed",
        "no-heavy-atoms-after-fragment-strip",
        "unexpected-standardizer-error",
    }
)


@dataclass(frozen=True)
class StandardizedMolecule:
    """One row of the standardization output.

    ``ok=True``  → ``canonical_smiles`` is the standardized SMILES.
    ``ok=False`` → ``reason`` is one of ``REJECTION_REASONS``; ``detail`` may
    add context (RDKit error text). ``canonical_smiles`` is empty in that case.
    """

    input_smiles: str
    canonical_smiles: str
    ok: bool
    reason: str | None = None
    detail: str | None = None
    fragment_stripped: bool = False
    charge_changed: bool = False
    had_defined_stereo: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "input_smiles": self.input_smiles,
            "canonical_smiles": self.canonical_smiles,
            "ok": self.ok,
            "reason": self.reason,
            "detail": self.detail,
            "fragment_stripped": self.fragment_stripped,
            "charge_changed": self.charge_changed,
            "had_defined_stereo": self.had_defined_stereo,
        }


@dataclass(frozen=True)
class StandardizerConfig:
    """Deterministic knobs for the pipeline.

    Defaults implement blueprint Module 3 Stage 1 as written. The version
    string is part of the cache key for downstream featurization.
    """

    version: str = STANDARDIZER_VERSION
    normalize: bool = True
    keep_largest_fragment: bool = True
    reionize: bool = True
    neutralize_charge: bool = True
    canonicalize_tautomer: bool = False
    remove_hs: bool = True
    keep_isomeric_smiles: bool = True


# ---------------------------------------------------------------------------- #
# Public API
# ---------------------------------------------------------------------------- #


def standardize(smiles: str, config: StandardizerConfig | None = None) -> StandardizedMolecule:
    """Standardize one SMILES string. Never raises for input errors."""
    cfg = config or StandardizerConfig()
    return _standardize_one(smiles, cfg, _build_components(cfg))


def standardize_batch(
    smiles_iter: Iterable[str],
    config: StandardizerConfig | None = None,
) -> list[StandardizedMolecule]:
    """Standardize a list of SMILES.

    The batched entry point exists so downstream callers do not fall into the
    "loop over the single-molecule API" anti-pattern the blueprint calls out.
    Components are constructed once per batch, not per molecule.
    """
    cfg = config or StandardizerConfig()
    comps = _build_components(cfg)
    return [_standardize_one(s, cfg, comps) for s in smiles_iter]


def rejection_summary(rows: Sequence[StandardizedMolecule]) -> dict[str, int]:
    """Counts per rejection reason (plus ``"ok"``). Useful for EDA + tests."""
    counts: dict[str, int] = {"ok": 0}
    for r in rows:
        if r.ok:
            counts["ok"] += 1
        else:
            key = r.reason or "unexpected-standardizer-error"
            counts[key] = counts.get(key, 0) + 1
    return counts


# ---------------------------------------------------------------------------- #
# Internals
# ---------------------------------------------------------------------------- #


def _build_components(cfg: StandardizerConfig) -> dict[str, Any]:
    """Instantiate RDKit's standardizer components once per batch."""
    return {
        "normalizer": rdMolStandardize.Normalizer() if cfg.normalize else None,
        "fragment_chooser": (
            rdMolStandardize.LargestFragmentChooser()
            if cfg.keep_largest_fragment
            else None
        ),
        "reionizer": rdMolStandardize.Reionizer() if cfg.reionize else None,
        "uncharger": rdMolStandardize.Uncharger() if cfg.neutralize_charge else None,
        "tautomerer": (
            rdMolStandardize.TautomerEnumerator()
            if cfg.canonicalize_tautomer
            else None
        ),
    }


def _reject(input_smiles: str, reason: str, detail: str | None = None) -> StandardizedMolecule:
    assert reason in REJECTION_REASONS, reason  # guards enum drift
    return StandardizedMolecule(
        input_smiles=input_smiles,
        canonical_smiles="",
        ok=False,
        reason=reason,
        detail=detail,
    )


def _mol_has_defined_stereo(mol: Chem.Mol) -> bool:
    """True if the molecule carries any explicitly defined stereocenter or bond stereo."""
    for atom in mol.GetAtoms():
        tag = atom.GetChiralTag()
        if tag not in (
            Chem.ChiralType.CHI_UNSPECIFIED,
            Chem.ChiralType.CHI_OTHER,
        ):
            return True
    for bond in mol.GetBonds():
        if bond.GetStereo() not in (
            Chem.BondStereo.STEREONONE,
            Chem.BondStereo.STEREOANY,
        ):
            return True
    return False


def _standardize_one(
    smiles: str,
    cfg: StandardizerConfig,
    comps: dict[str, Any],
) -> StandardizedMolecule:
    if smiles is None or not isinstance(smiles, str) or not smiles.strip():
        return _reject(smiles or "", "empty-input")

    raw = smiles.strip()

    mol = Chem.MolFromSmiles(raw, sanitize=False)
    if mol is None:
        return _reject(raw, "smiles-parse-failed")

    try:
        Chem.SanitizeMol(mol)
    except Exception as exc:  # noqa: BLE001 — RDKit raises many concrete classes
        return _reject(raw, "sanitize-failed", str(exc))

    Chem.AssignStereochemistry(mol, cleanIt=True, force=True)
    had_stereo = _mol_has_defined_stereo(mol)

    try:
        if comps["normalizer"] is not None:
            mol = comps["normalizer"].normalize(mol)

        fragment_stripped = False
        if comps["fragment_chooser"] is not None:
            before_atoms = mol.GetNumHeavyAtoms()
            mol = comps["fragment_chooser"].choose(mol)
            fragment_stripped = mol.GetNumHeavyAtoms() < before_atoms

        if mol is None or mol.GetNumHeavyAtoms() == 0:
            return _reject(raw, "no-heavy-atoms-after-fragment-strip")

        charge_before = Chem.GetFormalCharge(mol)
        if comps["uncharger"] is not None:
            mol = comps["uncharger"].uncharge(mol)
        if comps["reionizer"] is not None:
            mol = comps["reionizer"].reionize(mol)
        charge_changed = Chem.GetFormalCharge(mol) != charge_before

        if comps["tautomerer"] is not None:
            mol = comps["tautomerer"].Canonicalize(mol)

        if cfg.remove_hs:
            mol = Chem.RemoveHs(mol)

        # re-assign stereo after the mutations above (charges/normalization can
        # shift atom indices; be explicit about the final state)
        Chem.AssignStereochemistry(mol, cleanIt=True, force=True)

        canonical = Chem.MolToSmiles(
            mol,
            isomericSmiles=cfg.keep_isomeric_smiles,
            canonical=True,
        )
    except Exception as exc:  # noqa: BLE001
        return _reject(raw, "unexpected-standardizer-error", str(exc))

    if not canonical:
        return _reject(raw, "unexpected-standardizer-error", "empty-canonical-smiles")

    return StandardizedMolecule(
        input_smiles=raw,
        canonical_smiles=canonical,
        ok=True,
        fragment_stripped=fragment_stripped,
        charge_changed=charge_changed,
        had_defined_stereo=had_stereo,
    )
