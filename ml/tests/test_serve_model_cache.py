"""ModelRegistry in-memory caching (2026-10-18 serving fix).

Serving used to deserialise all 70 XGBoost files on every /predict. The registry now
keeps loaded models / AD indexes / calibrators per endpoint, keyed on the files'
(mtime_ns, size). These tests pin the two promises that make that safe:

  * a cached prediction is identical to an uncached one (and to the plain per-model
    `predict` path) - caching and featurize-once change cost, never values;
  * replacing or adding an artifact on disk invalidates the cache - no stale model.

Tiny synthetic models on a handful of real SMILES: no processed data, no sweep.
"""

from __future__ import annotations

import os
import threading
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest
from eval.applicability_domain import (
    _distances_to_reference,
    build_ad_index,
    bulk_tanimoto_distance,
)
from featurize.cache import FeatureCache
from featurize.fingerprints import MorganConfig, morgan_fingerprints_batch
from mars_contracts.endpoints import TaskType
from models.xgboost_model import XGBoostModel
from serve.predictor import predict_endpoint, predict_endpoints
from serve.registry import ModelRegistry

pytest.importorskip("xgboost", reason="xgboost not installed in this environment")

CLS = "hia_absorption"
REG = "solubility_logs"
SMILES = [
    "CCO",
    "c1ccccc1",
    "CC(=O)Oc1ccccc1C(=O)O",
    "Cn1c(=O)c2c(ncn2C)n(c1=O)C",
    "OCC1OC(O)C(O)C(O)C1O",
    "CCN(CC)CC",
    "c1ccc2c(c1)[nH]c1ccccc12",
    "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
]
QUERIES = ["O=C(O)c1ccccc1O", "CCCCO", "CC(C)O"]


@pytest.fixture(scope="module")
def cache(tmp_path_factory):
    return FeatureCache(tmp_path_factory.mktemp("feature_cache"))


def _train_and_save(cache, root: Path, endpoint: str, seed: int, y: np.ndarray) -> Path:
    task = TaskType.CLASSIFICATION if endpoint == CLS else TaskType.REGRESSION
    model = XGBoostModel(task_type=task, cache=cache, seed=seed)
    model.fit(SMILES, y, X_val=SMILES, y_val=y)
    path = root / endpoint / f"seed_{seed}"
    model.save(path)
    return path


def _bump_mtime(path: Path) -> None:
    """Make 'replaced' unambiguous on filesystems with coarse mtime resolution."""
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))


@pytest.fixture()
def artifacts(tmp_path, cache):
    root = tmp_path / "artifacts"
    labels_c = np.array([0, 1, 0, 1, 0, 1, 1, 0], dtype=float)
    labels_r = np.array([1.0, 2.5, 0.3, 4.1, 2.2, 3.3, 0.9, 1.7])
    for seed in (0, 1):
        _train_and_save(cache, root, CLS, seed, labels_c)
        _train_and_save(cache, root, REG, seed, labels_r)
    for ep in (CLS, REG):
        build_ad_index(ep, SMILES, k=3).save(root / ep / "ad_index")
    return root


def _snapshot(result: dict) -> dict:
    return {k: (asdict(v) if v is not None else None) for k, v in result.items()}


def test_cached_prediction_equals_uncached(artifacts, cache):
    cached = ModelRegistry(cache, artifacts_root=artifacts)
    for smi in QUERIES:
        warm = _snapshot(predict_endpoints(cached, smi, [CLS, REG]))
        again = _snapshot(predict_endpoints(cached, smi, [CLS, REG]))  # served from memory
        cold = _snapshot(
            predict_endpoints(ModelRegistry(cache, artifacts_root=artifacts), smi, [CLS, REG])
        )
        assert warm == again == cold


def test_featurize_once_path_equals_plain_per_model_predict(artifacts, cache):
    registry = ModelRegistry(cache, artifacts_root=artifacts)
    for smi in QUERIES:
        shared = predict_endpoint(registry, CLS, smi, prepared={})
        plain = predict_endpoint(registry, CLS, smi)  # prepared=None -> model.predict per model
        assert asdict(shared) == asdict(plain)
        raw = np.array([m.predict([smi])[0] for m in registry.load_models(CLS)])
        assert shared.value == float(np.mean(raw))
        assert shared.confidence_low == float(np.mean(raw) - np.std(raw))


def test_models_are_loaded_once_and_reused(artifacts, cache, monkeypatch):
    calls = []
    real = XGBoostModel.load_with_cache.__func__

    def counting(cls, path, c, **kw):
        calls.append(Path(path).name)
        return real(cls, path, c, **kw)

    monkeypatch.setattr(XGBoostModel, "load_with_cache", classmethod(counting))
    registry = ModelRegistry(cache, artifacts_root=artifacts)
    first = registry.load_models(CLS)
    second = registry.load_models(CLS)
    assert len(calls) == 2  # seed_0, seed_1 - once each
    assert all(a is b for a, b in zip(first, second, strict=True))
    assert first is not second  # callers get a copy of the list, never the cached list itself
    registry.load_ad_index(CLS)
    assert registry.load_ad_index(CLS) is registry.load_ad_index(CLS)
    registry.load_models(REG)
    assert len(calls) == 4  # the other endpoint loads its own seeds


def test_replacing_an_artifact_invalidates_the_cache(artifacts, cache):
    registry = ModelRegistry(cache, artifacts_root=artifacts, revalidate_seconds=0)
    smi = QUERIES[0]
    before_models = registry.load_models(REG)
    other_before = registry.load_models(CLS)
    before = predict_endpoint(registry, REG, smi)

    # Re-promote seed_0 with different labels -> a genuinely different model file.
    flipped = np.array([4.0, 0.1, 3.9, 0.2, 3.8, 0.3, 3.7, 0.4])
    model_json = _train_and_save(cache, artifacts, REG, 0, flipped) / "model.json"
    _bump_mtime(model_json)

    after_models = registry.load_models(REG)
    assert after_models[0] is not before_models[0]  # reloaded
    assert registry.load_models(CLS)[0] is other_before[0]  # other endpoints stay cached
    after = predict_endpoint(registry, REG, smi)
    assert after.value != before.value  # the new artifact is what serves
    fresh = predict_endpoint(ModelRegistry(cache, artifacts_root=artifacts), REG, smi)
    assert asdict(after) == asdict(fresh)  # and equals an uncached read of the new files


def test_adding_a_seed_invalidates_the_cache(artifacts, cache):
    registry = ModelRegistry(cache, artifacts_root=artifacts, revalidate_seconds=0)
    assert len(registry.load_models(CLS)) == 2
    _train_and_save(cache, artifacts, CLS, 2, np.array([1, 0, 1, 0, 1, 0, 0, 1], dtype=float))
    assert len(registry.load_models(CLS)) == 3
    assert predict_endpoint(registry, CLS, QUERIES[0]).n_seeds == 3


def test_replacing_the_ad_index_and_calibrator_invalidates_them(artifacts, cache):
    registry = ModelRegistry(cache, artifacts_root=artifacts, revalidate_seconds=0)
    old = registry.load_ad_index(CLS)
    assert registry.load_calibrator(CLS) is None  # fixture wrote none
    build_ad_index(CLS, SMILES[:6], k=2).save(artifacts / CLS / "ad_index")
    for f in (artifacts / CLS / "ad_index").iterdir():
        _bump_mtime(f)
    new = registry.load_ad_index(CLS)
    assert new is not old
    assert new.k == 2 and len(new.reference_smiles) == 6

    from eval.calibration import PlattCalibrator

    PlattCalibrator(A=1.0, B=0.0, n_fit_samples=5).save(artifacts / CLS / "calibrator.json")
    cal = registry.load_calibrator(CLS)
    assert cal.A == 1.0
    PlattCalibrator(A=2.0, B=0.5, n_fit_samples=9).save(artifacts / CLS / "calibrator.json")
    _bump_mtime(artifacts / CLS / "calibrator.json")
    assert registry.load_calibrator(CLS).A == 2.0


def test_revalidation_window_bounds_how_often_disk_is_checked(artifacts, cache, monkeypatch):
    """Within the window no stat/listdir at all; after it, a changed file is seen."""
    now = [1000.0]
    monkeypatch.setattr("serve.registry.time.monotonic", lambda: now[0])
    registry = ModelRegistry(cache, artifacts_root=artifacts, revalidate_seconds=5.0)
    first = registry.load_models(REG)

    stats = []
    real_stamp = __import__("serve.registry", fromlist=["_file_stamp"])._file_stamp
    monkeypatch.setattr("serve.registry._file_stamp", lambda p: stats.append(p) or real_stamp(p))
    now[0] += 1.0
    assert registry.load_models(REG)[0] is first[0]
    assert stats == []  # inside the window: served from memory, disk untouched

    model_json = _train_and_save(cache, artifacts, REG, 0, np.arange(8, dtype=float)) / "model.json"
    _bump_mtime(model_json)
    now[0] += 1.0
    assert registry.load_models(REG)[0] is first[0]  # still inside the window: not yet seen
    now[0] += 10.0
    assert registry.load_models(REG)[0] is not first[0]  # window elapsed: re-promotion picked up
    assert stats  # and the check really did touch the files


def test_serving_models_predict_on_one_thread_with_identical_values(artifacts, cache):
    loaded = ModelRegistry(cache, artifacts_root=artifacts).load_models(REG)[0]
    default = XGBoostModel.load_with_cache(artifacts / REG / "seed_0", cache)
    assert loaded._model.get_params()["n_jobs"] == 1
    for smi in QUERIES:
        assert np.array_equal(loaded.predict([smi]), default.predict([smi]))
    batch = SMILES + QUERIES
    assert np.array_equal(loaded.predict(batch), default.predict(batch))


def test_concurrent_first_loads_deserialise_each_seed_once(artifacts, cache, monkeypatch):
    calls = []
    real = XGBoostModel.load_with_cache.__func__

    def counting(cls, path, c, **kw):
        calls.append(Path(path).name)
        return real(cls, path, c, **kw)

    monkeypatch.setattr(XGBoostModel, "load_with_cache", classmethod(counting))
    registry = ModelRegistry(cache, artifacts_root=artifacts)
    results: list = []
    barrier = threading.Barrier(8)

    def work():
        barrier.wait()
        results.append(registry.load_models(CLS))

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 2
    assert all(r[0] is results[0][0] for r in results)


def test_ad_fast_path_matches_the_matmul_distance_exactly():
    index = build_ad_index(CLS, SMILES, k=3)
    fps, _ = morgan_fingerprints_batch(QUERIES + SMILES[:2], MorganConfig())
    fast = _distances_to_reference(fps, index)
    slow = bulk_tanimoto_distance(fps, index.reference_fingerprints)
    assert fast.shape == slow.shape
    assert np.array_equal(fast, slow)  # bit-for-bit, not approx


def test_concurrent_predictions_equal_sequential(artifacts, cache):
    """The API predicts on worker threads against shared, cached models."""
    registry = ModelRegistry(cache, artifacts_root=artifacts)
    mols = QUERIES + SMILES
    expected = {s: _snapshot(predict_endpoints(registry, s, [CLS, REG])) for s in mols}
    got: dict = {}
    barrier = threading.Barrier(6)

    def work(i):
        barrier.wait()
        for s in mols[i % len(mols):] + mols[: i % len(mols)]:
            got[(i, s)] = _snapshot(predict_endpoints(registry, s, [CLS, REG]))

    threads = [threading.Thread(target=work, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(got) == 6 * len(mols)
    assert all(v == expected[s] for (_, s), v in got.items())
