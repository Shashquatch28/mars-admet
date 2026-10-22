"""FeatureCache under concurrent writers (the API predicts on worker threads).

Before 2026-10-18 `_record_config` did an unlocked read-modify-write of `_config.json` and
entries were written in place, so two threads could corrupt the config or let a reader see
a half-written `.npy`/`.npz`. Entries are now written via temp file + `os.replace` and the
config update is serialised.
"""

from __future__ import annotations

import json
import threading

import numpy as np
from featurize.cache import FeatureCache, _atomic_write
from featurize.descriptors import DescriptorConfig
from featurize.fingerprints import MorganConfig

SMILES = [
    "CCO", "c1ccccc1", "CC(=O)Oc1ccccc1C(=O)O", "Cn1c(=O)c2c(ncn2C)n(c1=O)C",
    "OCC1OC(O)C(O)C(O)C1O", "CCN(CC)CC", "c1ccc2c(c1)[nH]c1ccccc12", "CCCCO",
    "CC(C)O", "CCOC(=O)C=C", "c1ccncc1", "Clc1ccc(Cl)cc1",
]


def _run_threads(n, fn):
    errors = []
    barrier = threading.Barrier(n)

    def work(i):
        try:
            barrier.wait()
            fn(i)
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors


def test_concurrent_featurization_keeps_config_valid_and_results_identical(tmp_path):
    cache = FeatureCache(tmp_path)
    reference = FeatureCache(tmp_path / "ref")
    ref_morgan, _, _ = reference.morgan_cached(SMILES)
    ref_desc, _, _, _, _ = reference.descriptors_cached(SMILES)
    seen = []

    def work(i):
        # every thread featurizes the same cold molecules, in a different order
        order = SMILES[i % len(SMILES):] + SMILES[: i % len(SMILES)]
        m, dropped, _ = cache.morgan_cached(order)
        d, _, dropped_d, _, _ = cache.descriptors_cached(order)
        assert not dropped and not dropped_d
        seen.append((order, m, d))

    _run_threads(8, work)

    for order, m, d in seen:
        idx = [SMILES.index(s) for s in order]
        assert np.array_equal(m, ref_morgan[idx])
        assert np.array_equal(d, ref_desc[idx], equal_nan=True)
    for stage in ("morgan", "descriptors"):
        meta = json.loads((tmp_path / stage / "_config.json").read_text(encoding="utf-8"))
        assert meta["configs_seen"]  # parseable, and the key was recorded
    assert not list(tmp_path.rglob("*.tmp"))  # no temp files left behind
    # every stored entry loads cleanly
    for p in (tmp_path / "morgan").rglob("*.npy"):
        np.load(p)
    for p in (tmp_path / "descriptors").rglob("*.npz"):
        np.load(p, allow_pickle=True)["values"]
    assert MorganConfig().cache_key() in cache.configs_seen("morgan")
    assert DescriptorConfig().cache_key() in cache.configs_seen("descriptors")


def test_atomic_write_leaves_no_partial_file_on_failure(tmp_path):
    target = tmp_path / "entry.npy"

    def boom(f):
        f.write(b"partial")
        raise RuntimeError("disk full")

    try:
        _atomic_write(target, boom)
    except RuntimeError:
        pass
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []
