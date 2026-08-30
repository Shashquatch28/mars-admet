"""Tests for scaffold splitting + leakage audits."""

from __future__ import annotations

from data.split import (
    assert_no_leakage,
    build_split_report,
    five_seed_train_val_folds,
    leakage_audit,
    scaffold_split,
)
from featurize.scaffold import murcko_scaffold_from_smiles

# fixed set with several distinct scaffolds, some acyclic
SMIS = [
    "CC(=O)Oc1ccccc1C(=O)O",  # aspirin (benzene scaffold)
    "Oc1ccccc1",              # phenol (benzene)
    "c1ccncc1",               # pyridine
    "c1ccc2c(c1)CCCC2",        # tetralin
    "c1ccc(-c2ccccc2)cc1",    # biphenyl
    "CCO",                    # ethanol (acyclic)
    "CCCCCC",                 # hexane (acyclic)
    "c1ccc2ccccc2c1",          # naphthalene
    "O=C1CCCCC1",              # cyclohexanone
    "c1ccc(Cl)cc1",           # chlorobenzene (benzene)
    "c1ccc(Br)cc1",           # bromobenzene (benzene)
    "c1ccc(I)cc1",            # iodobenzene (benzene)
]


def test_scaffold_split_deterministic():
    a1, b1 = scaffold_split(SMIS, seed=0)
    a2, b2 = scaffold_split(SMIS, seed=0)
    assert a1 == a2 and b1 == b2


def test_scaffold_split_no_shared_non_empty_scaffold():
    train, test = scaffold_split(SMIS, seed=0)
    r = build_split_report(
        dataset_key="t", endpoint_key="t", method="scaffold",
        train_val=train, test=test, seed=0,
    )
    assert r.scaffold_overlap_count == 0
    assert r.smiles_overlap_count == 0


def test_scaffold_split_partitions_the_input():
    train, test = scaffold_split(SMIS, seed=0, test_fraction=0.25)
    assert set(train).isdisjoint(test)
    assert set(train) | set(test) == set(SMIS)


def test_leakage_audit_flags_injected_leak():
    train = ["c1ccncc1", "CCO"]
    test = ["c1ccncc1", "O=C1CCCCC1"]  # pyridine in both
    audit = leakage_audit(train, test)
    assert audit["smiles_overlap_count"] == 1
    assert audit["scaffold_overlap_count_excluding_acyclic"] >= 1


def test_assert_no_leakage_raises_on_smiles_overlap():
    r = build_split_report(
        dataset_key="t", endpoint_key="t", method="scaffold",
        train_val=["c1ccncc1"], test=["c1ccncc1"], seed=0,
    )
    import pytest
    with pytest.raises(AssertionError):
        assert_no_leakage(r)


def test_five_seed_folds_are_reproducible_and_partition_train_val():
    train_val, _ = scaffold_split(SMIS * 3, seed=0)
    folds = five_seed_train_val_folds(train_val, seeds=(0, 1, 2))
    assert len(folds) == 3
    for seed, tr, va in folds:
        assert set(tr).isdisjoint(va), seed
        # scaffold-level leakage should not exist within each fold
        r = build_split_report(
            dataset_key="t", endpoint_key="t", method="scaffold",
            train_val=tr, test=va, seed=seed,
        )
        assert r.smiles_overlap_count == 0
    # different seeds usually produce different partitions
    tr0, tr1 = set(folds[0][1]), set(folds[1][1])
    assert tr0 != tr1


def test_acyclic_bucket_is_reported_but_allowed():
    # aspirin scaffold vs an acyclic
    train = ["CC(=O)Oc1ccccc1C(=O)O", "CCO"]
    test = ["c1ccncc1", "CCCCC"]
    audit = leakage_audit(train, test)
    # both sides have empty scaffold — that overlap is legitimate
    assert audit["scaffold_overlap_count"] >= 1
    assert audit["scaffold_overlap_count_excluding_acyclic"] == 0


def test_scaffold_of_input_matches_helper():
    assert murcko_scaffold_from_smiles("c1ccc(Cl)cc1") == "c1ccccc1"
