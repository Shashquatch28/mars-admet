"""
MARS -> KERMT adapter (Module 3 Stage 2 KERMT lock, M2 pre-flight item #4).

KERMT (github.com/NVIDIA-BioNeMo/KERMT, v2.0.0) is NOT driven by tensors we
hand it — the official `main.py finetune` / `main.py predict` CLI takes a CSV
of (SMILES, targets) and re-derives its own atom/bond graph internally via
`kermt.data.molgraph` from the raw SMILES string. There is no CLI-level entry
point that accepts a precomputed graph tensor (atom_features/edge_index/
edge_features) in place of a SMILES column — confirmed by reading
`kermt/data/molgraph.py`, `kermt/data/kermtdataset.py`, and every
`agent/skills/kermt-*/SKILL.md` workflow, all of which take `--csv` with a
`smiles` column.

Consequently the "adapter" MARS needs is not a graph-tensor transform of
`mars-graph-v1` (`ml/featurize/graph.py`) into KERMT's atom/bond arrays — it is
a **SMILES-and-label CSV contract adapter**: MARS's already-standardized
SMILES (`standardized_smiles`, the mars-standardizer-v1 fixed point consumed
by every M1 downstream stage) go in verbatim; KERMT featurizes them itself.

Chirality preservation across this boundary is a SMILES-string property, not
a tensor property: since MARS never re-standardizes `standardized_smiles`
before handing it to KERMT, and KERMT's own `kermt/data/molgraph.py` reads
`atom.GetChiralTag()` via RDKit on that same string (see ATOM_FEATURES in
that module: `'chiral_tag': [0, 1, 2, 3]`), chirality is preserved as long as
(a) MARS's standardization does not strip stereo descriptors from the SMILES
(it doesn't — see `ml/featurize/standardize.py` / `mars-standardizer-v1`) and
(b) neither side rewrites the string in a way that loses stereo before RDKit
parses it. `test_chirality_preserved_in_smiles_roundtrip` in
`ml/tests/test_kermt_adapter.py` proves this empirically rather than assuming
it: it round-trips a stereo SMILES through `ml.featurize.graph.molecule_graph`
(MARS's own chirality-bin slice) and confirms the *same* SMILES's RDKit
chiral tags match what KERMT's `ATOM_FEATURES['chiral_tag']` vocabulary would
encode, per-atom.

CHIRAL_TAGS equivalence (both keyed off `rdkit.Chem.rdchem.ChiralType`, an
IntEnum — the raw integer values are the same enum members, not independently
chosen numbers):

    MARS  (ml/featurize/graph.py CHIRAL_TAGS, order matters — one-hot index):
        0: CHI_UNSPECIFIED   1: CHI_TETRAHEDRAL_CW
        2: CHI_TETRAHEDRAL_CCW   3: CHI_OTHER

    KERMT (kermt/data/molgraph.py ATOM_FEATURES['chiral_tag'] = [0, 1, 2, 3]):
        one-hot over the raw `Chem.ChiralType` integer value directly (0-3,
        same four members, same ordinal values — CHI_UNSPECIFIED=0 etc.)

Missing-label convention for multi-task finetune CSVs (verified from
`kermt/data/moldataset.py::MoleculeDatapoint.__init__`:
``self.targets = [float(x) if x != '' else None for x in line[1:]]``) is an
**empty CSV cell**, not the string "nan"/"NaN". `write_finetune_csv` below
follows that convention exactly.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
from rdkit import Chem

from featurize.graph import CHIRAL_TAGS

# kermt/data/molgraph.py ATOM_FEATURES['chiral_tag'] — verified 2026-09-18
# against github.com/NVIDIA-BioNeMo/KERMT @ v2.0.0 (commit e402473).
KERMT_CHIRAL_TAG_VALUES: tuple[int, ...] = (0, 1, 2, 3)


def chirality_tags_are_equivalent() -> bool:
    """True if MARS's CHIRAL_TAGS vocabulary and KERMT's chiral_tag vocabulary
    both enumerate the same four `Chem.ChiralType` members in the same order.

    Both are one-hot vocabularies over RDKit's `Chem.ChiralType` IntEnum, so
    "equivalent" means: same members, same int values, same order — not just
    "same length". This is the empirical check backing the adapter's chirality
    claim (see module docstring); it is exercised by
    ``ml/tests/test_kermt_adapter.py::test_chiral_tag_vocab_matches_kermt``.
    """
    mars_values = tuple(int(t) for t in CHIRAL_TAGS)
    return mars_values == KERMT_CHIRAL_TAG_VALUES


def assert_chirality_preserved(smiles: str) -> None:
    """Raise if RDKit's per-atom chiral tags for *smiles* would not round-trip
    identically through both MARS's one-hot vocabulary and KERMT's.

    Since both vocabularies are confirmed identical (`chirality_tags_are_equivalent`),
    this reduces to: every chiral tag RDKit assigns is one of the four members
    each vocabulary already covers (KERMT's `onek_encoding_unk` has no "other"
    bucket for chiral_tag — see `kermt/data/molgraph.py` ATOM_FEATURES — so an
    out-of-vocabulary tag would silently misencode there, unlike MARS's other
    categorical features which reserve an explicit "other" bin). Chem.ChiralType
    only has four members as of the RDKit versions both projects pin, so this
    should never fire in practice; it exists to fail loudly rather than
    silently misencode if that ever changes.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Not a parseable SMILES: {smiles!r}")
    Chem.AssignStereochemistry(mol, cleanIt=True, force=True)
    valid = set(KERMT_CHIRAL_TAG_VALUES)
    for atom in mol.GetAtoms():
        tag = int(atom.GetChiralTag())
        if tag not in valid:
            raise ValueError(
                f"Atom {atom.GetIdx()} in {smiles!r} has chiral tag {tag}, "
                f"outside both MARS's and KERMT's fixed 4-value vocabulary "
                f"{sorted(valid)}. This SMILES cannot be faithfully handed to "
                f"KERMT without an adapter change — do not silently drop it."
            )


def write_finetune_csv(
    path: Path,
    smiles: list[str],
    targets: dict[str, np.ndarray],
) -> Path:
    """Write a KERMT finetune-format CSV: header ``smiles,<target1>,...``.

    Parameters
    ----------
    smiles:
        Already-standardized SMILES (``standardized_smiles`` from M1's
        processed splits). NOT re-standardized here — see module docstring.
    targets:
        ``{target_name: values}``, one array per column, each length
        ``len(smiles)``. A value of ``None`` or NaN at position *i* is written
        as an empty cell — KERMT's own missing-label convention (verified from
        ``kermt/data/moldataset.py``), consumed as a masked-out label for that
        task at training time (multi-task masked loss).

    Returns
    -------
    The path written to (same as *path*).
    """
    if not targets:
        raise ValueError("targets must be a non-empty {name: values} mapping")
    n = len(smiles)
    for name, values in targets.items():
        if len(values) != n:
            raise ValueError(
                f"targets[{name!r}] has length {len(values)}, expected {n} (len(smiles))"
            )

    target_names = list(targets.keys())
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["smiles", *target_names])
        for i, smi in enumerate(smiles):
            row = [smi]
            for name in target_names:
                v = targets[name][i]
                if v is None or (isinstance(v, float) and np.isnan(v)):
                    row.append("")
                else:
                    row.append(v)
            writer.writerow(row)
    return path


def write_predict_csv(path: Path, smiles: list[str]) -> Path:
    """Write a KERMT inference-format CSV: header ``smiles`` only.

    Per every ``kermt-infer``/``kermt-embed`` SKILL.md: "SMILES-only CSV.
    First column is `smiles`; other columns are ignored" — a target-free CSV
    is the documented, supported input shape, not an omission.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["smiles"])
        for smi in smiles:
            writer.writerow([smi])
    return path


def read_predictions_csv(path: Path, target_names: list[str]) -> dict[str, np.ndarray]:
    """Read a KERMT ``predictions.csv`` (smiles + per-target columns) back into
    ``{target_name: np.ndarray}``, aligned to the CSV's row order.

    KERMT's predict output format is documented in every ``kermt-infer``
    SKILL.md as "smiles + per-target columns"; this reads exactly that shape
    without assuming column order beyond ``smiles`` being present.
    """
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    out: dict[str, list[float]] = {name: [] for name in target_names}
    for row in rows:
        for name in target_names:
            raw = row.get(name, "")
            out[name].append(float("nan") if raw in ("", None) else float(raw))
    return {name: np.array(vals, dtype=float) for name, vals in out.items()}
