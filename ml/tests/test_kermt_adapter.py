"""Tests for the MARS -> KERMT SMILES/CSV adapter (ml/featurize/kermt_adapter.py).

These tests do NOT require docker, the KERMT checkout, or a GPU — they only
exercise the adapter's pure-Python CSV contract and the chirality-vocabulary
equivalence claim, both of which are checkable without invoking KERMT itself.
Container-level smoke tests (import, checkpoint load, forward/backward,
finetune, MARS-eval integration) are separate and documented in
documentation/AIMS/decisions.md, not here.
"""

from __future__ import annotations

import csv

import numpy as np
import pytest
from featurize.graph import chirality_bit_slice, molecule_graph
from featurize.kermt_adapter import (
    KERMT_CHIRAL_TAG_VALUES,
    assert_chirality_preserved,
    chirality_tags_are_equivalent,
    read_predictions_csv,
    write_finetune_csv,
    write_predict_csv,
)

# A molecule with two defined stereocenters (R,R and variants) — canonical
# chiral SMILES for threonine-like backbone; exact identity doesn't matter,
# only that RDKit assigns CHI_TETRAHEDRAL_CW/CCW to at least one atom.
_CHIRAL_SMILES = "C[C@H](N)C(=O)O"  # L-alanine
_ACHIRAL_SMILES = "CCO"  # ethanol — no stereocenters


# --- chirality vocabulary equivalence --------------------------------------


def test_chiral_tag_vocab_matches_kermt():
    assert chirality_tags_are_equivalent()


def test_kermt_chiral_tag_values_are_four_rdkit_members():
    # CHI_UNSPECIFIED=0, CHI_TETRAHEDRAL_CW=1, CHI_TETRAHEDRAL_CCW=2, CHI_OTHER=3
    assert KERMT_CHIRAL_TAG_VALUES == (0, 1, 2, 3)


def test_assert_chirality_preserved_accepts_chiral_and_achiral():
    assert_chirality_preserved(_CHIRAL_SMILES)
    assert_chirality_preserved(_ACHIRAL_SMILES)


def test_assert_chirality_preserved_rejects_bad_smiles():
    with pytest.raises(ValueError):
        assert_chirality_preserved("NOT_A_SMILES")


def test_chirality_bit_survives_into_mars_graph_for_chiral_smiles():
    """Ground truth: MARS's own graph featurizer must actually set a non-
    CHI_UNSPECIFIED bin for the stereocenter atom in _CHIRAL_SMILES — this is
    the MARS-side half of the adapter's chirality claim; the KERMT-side half
    is that KERMT's ATOM_FEATURES['chiral_tag'] vocabulary is the same one
    (test_chiral_tag_vocab_matches_kermt, above)."""
    g = molecule_graph(_CHIRAL_SMILES)
    assert g is not None
    start, end = chirality_bit_slice()
    chiral_bins = g.atom_features[:, start:end]
    # CHI_UNSPECIFIED is index 0 within the slice; a defined stereocenter
    # should have some atom NOT in the CHI_UNSPECIFIED bin.
    non_unspecified = chiral_bins[:, 1:].sum()
    assert non_unspecified >= 1, (
        "Expected at least one atom with a defined (non-CHI_UNSPECIFIED) "
        "chiral tag for a chiral input SMILES."
    )


# --- CSV contract: single-task ----------------------------------------------


def test_write_finetune_csv_single_task(tmp_path):
    smiles = ["CCO", "c1ccccc1", _CHIRAL_SMILES]
    y = np.array([1.0, 0.0, 1.0])
    path = write_finetune_csv(tmp_path / "train.csv", smiles, {"herg_cardiotoxicity": y})

    with path.open(newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["smiles", "herg_cardiotoxicity"]
    assert rows[1] == ["CCO", "1.0"]
    assert rows[2] == ["c1ccccc1", "0.0"]
    assert rows[3] == [_CHIRAL_SMILES, "1.0"]


def test_write_finetune_csv_preserves_chiral_smiles_verbatim(tmp_path):
    """The adapter must not re-canonicalize or otherwise rewrite the SMILES
    string — MARS's standardized_smiles is already a fixed point and KERMT
    re-derives its own graph from whatever string it's given."""
    path = write_finetune_csv(tmp_path / "train.csv", [_CHIRAL_SMILES], {"t": np.array([0.0])})
    with path.open(newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[1][0] == _CHIRAL_SMILES


# --- CSV contract: missing-label masking (multi-task) -----------------------


def test_write_finetune_csv_missing_label_is_empty_cell_not_nan_string(tmp_path):
    """Verified from kermt/data/moldataset.py::MoleculeDatapoint.__init__:
    `self.targets = [float(x) if x != '' else None for x in line[1:]]` —
    a literal "nan" string would NOT hit that branch and would instead raise
    inside float("nan") -> nan (actually succeeds) but is semantically wrong:
    KERMT's own convention is an empty cell, not the string "nan"."""
    smiles = ["CCO", "c1ccccc1"]
    y = np.array([1.0, np.nan])
    path = write_finetune_csv(tmp_path / "train.csv", smiles, {"cyp3a4_inhibition": y})
    with path.open(newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[1] == ["CCO", "1.0"]
    assert rows[2] == ["c1ccccc1", ""]  # empty cell, not "nan"


def test_write_finetune_csv_multitask_independent_missing_masks(tmp_path):
    smiles = ["CCO", "c1ccccc1", "CCN"]
    targets = {
        "herg_cardiotoxicity": np.array([1.0, np.nan, 0.0]),
        "ames_mutagenicity": np.array([np.nan, 1.0, 0.0]),
    }
    path = write_finetune_csv(tmp_path / "train.csv", smiles, targets)
    with path.open(newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["smiles", "herg_cardiotoxicity", "ames_mutagenicity"]
    assert rows[1] == ["CCO", "1.0", ""]
    assert rows[2] == ["c1ccccc1", "", "1.0"]
    assert rows[3] == ["CCN", "0.0", "0.0"]


def test_write_finetune_csv_rejects_length_mismatch(tmp_path):
    with pytest.raises(ValueError):
        write_finetune_csv(tmp_path / "train.csv", ["CCO", "CCN"], {"t": np.array([1.0])})


def test_write_finetune_csv_rejects_empty_targets(tmp_path):
    with pytest.raises(ValueError):
        write_finetune_csv(tmp_path / "train.csv", ["CCO"], {})


# --- CSV contract: inference -------------------------------------------------


def test_write_predict_csv_smiles_only_header(tmp_path):
    path = write_predict_csv(tmp_path / "predict.csv", ["CCO", "c1ccccc1"])
    with path.open(newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["smiles"]
    assert rows[1] == ["CCO"]
    assert rows[2] == ["c1ccccc1"]


def test_read_predictions_csv_roundtrip(tmp_path):
    path = tmp_path / "predictions.csv"
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["smiles", "herg_cardiotoxicity", "ames_mutagenicity"])
        writer.writerow(["CCO", "0.12", "0.87"])
        writer.writerow(["c1ccccc1", "0.55", ""])

    out = read_predictions_csv(path, ["herg_cardiotoxicity", "ames_mutagenicity"])
    assert out["herg_cardiotoxicity"].tolist() == pytest.approx([0.12, 0.55])
    assert out["ames_mutagenicity"][0] == pytest.approx(0.87)
    assert np.isnan(out["ames_mutagenicity"][1])
