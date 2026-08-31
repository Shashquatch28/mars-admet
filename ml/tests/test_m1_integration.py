"""
M1 end-to-end integration — run a slice of a real processed dataset through the
full Module 3 pipeline + the feature cache, and assert round-trip identity,
determinism, and no leakage of the fixed test set into anything.

Skips cleanly if no acquisition + prepare has been run on this machine.
"""

from __future__ import annotations

import csv
import glob
from pathlib import Path

import numpy as np
import pytest
from featurize.cache import FeatureCache
from featurize.pipeline import PipelineConfig, featurize_batch

REPO = Path(__file__).resolve().parents[2]


def _newest_processed() -> Path | None:
    dirs = sorted(glob.glob(str(REPO / "ml" / "data" / "processed" / "*")))
    return Path(dirs[-1]) if dirs else None


PROCESSED = _newest_processed()


def _read_smiles(path: Path, n: int) -> list[str]:
    with path.open(newline="", encoding="utf-8") as fh:
        return [r["standardized_smiles"] for r in csv.DictReader(fh)][:n]


@pytest.fixture(scope="module")
def dili_train():
    if PROCESSED is None:
        pytest.skip("no processed datasets on disk")
    p = PROCESSED / "dili_liver_injury" / "train_val.csv"
    if not p.exists():
        pytest.skip("no processed DILI on disk")
    return _read_smiles(p, 40)


def test_pipeline_over_real_processed_slice_is_dense_and_aligned(dili_train):
    b = featurize_batch(dili_train, PipelineConfig(want_conformers=False))
    n = len(b.standardized_smiles)
    assert n >= 30  # processed SMILES are already standardized → ~all survive
    assert len(b.graphs) == n
    assert b.morgan.shape == (n, 2048)
    assert b.descriptors.shape[0] == n


def test_processed_smiles_are_already_standardization_fixed_points(dili_train):
    """Prepare.py wrote standardized SMILES; re-standardizing them must be a
    no-op (canonical form is idempotent)."""
    b = featurize_batch(dili_train)
    # every input survived and maps to itself
    assert b.kept_input_indices == list(range(len(dili_train)))
    assert b.standardized_smiles == dili_train


def test_cache_roundtrip_matches_direct_pipeline(tmp_path, dili_train):
    direct = featurize_batch(dili_train, PipelineConfig(want_conformers=False))
    cache = FeatureCache(tmp_path)

    m1, _d1, s1 = cache.morgan_cached(dili_train)
    m2, _d2, s2 = cache.morgan_cached(dili_train)
    assert s1.computed > 0 and s2.hits == len(dili_train)
    assert np.array_equal(m1, m2)
    assert np.array_equal(m1, direct.morgan)

    g1, _gd1, _gs1 = cache.graphs_cached(dili_train)
    for a, b in zip(g1, direct.graphs, strict=True):
        assert np.array_equal(a.atom_features, b.atom_features)


def test_five_seed_folds_never_touch_the_test_set():
    """Blueprint Module 1 §4 — the fixed test set is off-limits to CV."""
    if PROCESSED is None:
        pytest.skip("no processed datasets on disk")
    from data.split import five_seed_train_val_folds

    tv_path = PROCESSED / "hia_absorption" / "train_val.csv"
    te_path = PROCESSED / "hia_absorption" / "test.csv"
    if not tv_path.exists():
        pytest.skip("no processed HIA on disk")
    tv = _read_smiles(tv_path, 10_000)
    te = set(_read_smiles(te_path, 10_000))

    folds = five_seed_train_val_folds(tv, seeds=(0, 1, 2, 3, 4))
    assert len(folds) == 5
    for seed, train, valid in folds:
        assert set(train).isdisjoint(te), seed
        assert set(valid).isdisjoint(te), seed
        assert set(train).isdisjoint(valid), seed
    # different seeds → different partitions (not all identical)
    assert len({tuple(sorted(v)) for _s, _t, v in folds}) > 1


def test_conformer_energies_are_finite_on_a_real_slice(dili_train):
    cache_dir = REPO / "ml" / "data" / "cache" / "_pytest_scratch"
    cache = FeatureCache(cache_dir)
    try:
        results, stats = cache.conformers_cached(dili_train[:8])
        ok = [r for r in results if r.ok]
        assert len(ok) >= 6  # most drug-like molecules embed fine
        for r in ok:
            assert r.energy_kcal_mol == r.energy_kcal_mol  # finite
            assert r.force_field in ("MMFF94", "UFF")
    finally:
        import shutil

        shutil.rmtree(cache_dir, ignore_errors=True)
