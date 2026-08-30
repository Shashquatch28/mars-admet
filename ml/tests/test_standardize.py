"""Unit tests for Module 3 Stage 1 standardization."""

from __future__ import annotations

import pytest
from featurize.standardize import (
    REJECTION_REASONS,
    StandardizerConfig,
    rejection_summary,
    standardize,
    standardize_batch,
)

# --- happy path -----------------------------------------------------------

def test_valid_smiles_is_canonicalized():
    r = standardize("CCO")
    assert r.ok
    assert r.canonical_smiles == "CCO"


def test_batched_matches_singleton():
    xs = ["CCO", "c1ccccc1O", "CC(=O)O"]
    batch = standardize_batch(xs)
    singleton = [standardize(s) for s in xs]
    for a, b in zip(batch, singleton, strict=True):
        assert a.canonical_smiles == b.canonical_smiles
        assert a.ok == b.ok
        assert a.reason == b.reason


def test_output_is_deterministic():
    a = standardize("C[C@@H](N)C(=O)O")
    b = standardize("C[C@@H](N)C(=O)O")
    assert a == b


# --- salt/fragment stripping ----------------------------------------------

def test_salt_is_stripped_to_largest_organic_fragment():
    r = standardize("CC[O-].[Na+]")
    assert r.ok
    assert r.canonical_smiles == "CCO"
    assert r.fragment_stripped is True
    assert r.charge_changed is True


def test_pure_salt_still_produces_output_from_largest_fragment():
    # NaCl — no organic; largest fragment is Cl (an atom), pipeline must not crash.
    # Blueprint reserves rejection for genuinely unusable molecules; this one has
    # atoms, so it is not rejected here — dedup handles it downstream.
    r = standardize("[Na+].[Cl-]")
    assert r.ok
    assert r.canonical_smiles == "Cl"


# --- charge normalization -------------------------------------------------

def test_zwitterion_is_neutralized():
    r = standardize("[NH3+]CC(=O)[O-]")  # glycine
    assert r.ok
    assert r.canonical_smiles == "NCC(=O)O"


# --- stereochemistry ------------------------------------------------------

def test_defined_stereocenters_survive():
    L = standardize("C[C@@H](N)C(=O)O")
    D = standardize("C[C@H](N)C(=O)O")
    assert L.ok and D.ok
    assert L.had_defined_stereo is True
    assert D.had_defined_stereo is True
    assert L.canonical_smiles != D.canonical_smiles  # ENANTIOMERS STAY DISTINCT


def test_undefined_stereo_is_not_fabricated():
    r = standardize("CC(N)C(=O)O")  # no [C@…] annotation on the racemic center
    assert r.ok
    assert r.had_defined_stereo is False
    # canonical SMILES also carries no [C@…] mark
    assert "@" not in r.canonical_smiles


def test_bond_stereo_survives():
    # (E)-2-butene should keep its E designation
    e = standardize("C/C=C/C")
    z = standardize("C/C=C\\C")
    assert e.ok and z.ok
    assert e.had_defined_stereo is True
    assert e.canonical_smiles != z.canonical_smiles


# --- rejections -----------------------------------------------------------

def test_empty_input_is_rejected_deterministically():
    for bad in ["", "   ", None]:
        r = standardize(bad)  # type: ignore[arg-type]
        assert not r.ok
        assert r.reason == "empty-input"


def test_invalid_smiles_is_rejected_with_named_reason():
    r = standardize("NOT_A_SMILES")
    assert not r.ok
    assert r.reason == "smiles-parse-failed"


def test_no_heavy_atoms_case_is_named():
    r = standardize("[H][H]")
    assert not r.ok
    assert r.reason == "no-heavy-atoms-after-fragment-strip"


def test_rejection_reason_set_is_closed():
    # Any reason we emit must be in the documented enum.
    rows = standardize_batch(["CCO", "", "NOT_A_SMILES", "[H][H]"])
    for r in rows:
        if not r.ok:
            assert r.reason in REJECTION_REASONS


# --- summary + config -----------------------------------------------------

def test_rejection_summary_counts_reasons():
    rows = standardize_batch(["CCO", "", "NOT_A_SMILES", "CCO", ""])
    s = rejection_summary(rows)
    assert s["ok"] == 2
    assert s["empty-input"] == 2
    assert s["smiles-parse-failed"] == 1


def test_config_version_is_versioned_string():
    cfg = StandardizerConfig()
    assert cfg.version.startswith("mars-standardizer-")


def test_tautomer_option_off_by_default():
    # 2-hydroxypyridine <-> 2-pyridone are tautomers. With the default off, we
    # must NOT collapse them to the same canonical form.
    a = standardize("Oc1ccccn1")
    b = standardize("O=c1cccc[nH]1")
    assert a.ok and b.ok
    assert a.canonical_smiles != b.canonical_smiles


def test_tautomer_option_on_canonicalizes():
    cfg = StandardizerConfig(canonicalize_tautomer=True)
    a = standardize("Oc1ccccn1", cfg)
    b = standardize("O=c1cccc[nH]1", cfg)
    assert a.ok and b.ok
    # they should now collapse; assert equality without specifying which form wins
    assert a.canonical_smiles == b.canonical_smiles


# --- integration with the acquired data set ------------------------------

def test_small_real_batch_from_dili(tmp_path):
    """Run a tiny slice of the acquired DILI dataset through the pipeline.
    Skips if the raw file is not on disk (CI without the ~22 MB pull)."""
    import csv
    import glob
    matches = glob.glob("data/raw/DILI/*/DILI.full.csv")
    if not matches:
        pytest.skip("no acquired DILI on disk")
    with open(matches[0], newline="", encoding="utf-8") as fh:
        smis = [row["Drug"] for row in csv.DictReader(fh)][:64]
    rows = standardize_batch(smis)
    ok_rate = sum(1 for r in rows if r.ok) / len(rows)
    assert ok_rate > 0.9, f"validity too low on real data: {ok_rate}"
    # every rejected one has a named reason
    for r in rows:
        if not r.ok:
            assert r.reason in REJECTION_REASONS
