"""
Harness-level tests for the KERMT calibration wiring in train/train_kermt_cluster.py.

``KermtModel`` is replaced by ``StubKermt`` — a TEST DOUBLE. It is not KERMT and
its scores are arbitrary deterministic numbers keyed on the SMILES string. These
tests verify DATA FLOW ONLY: which molecules reach fit(), which reach the
calibrator, which reach the test scorer, and what is persisted. They establish
nothing about KERMT's real logits or about how well a real model calibrates.

The GPU-dependent portion — real KERMT logits on the held-out calibration and
test sets — is exercised only during a real lab run.
"""

from __future__ import annotations

import json
import zlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from configs.clusters import type_homogeneous_subgroups
from configs.experiment_config import ExperimentConfig
from data.cluster_loaders import SMILES_COL, load_cluster
from eval import cluster_calibration as cc
from eval.cluster_calibration import REQUIRED_RECORD_KEYS
from mars_contracts.endpoints import TaskType
from train import train_kermt_cluster as harness

# 20 distinct ring scaffolds x 6 substituent lengths = 120 valid, distinct molecules.
_SCAFFOLDS = [
    "C1CC1", "C1CCC1", "C1CCCC1", "C1CCCCC1", "C1CCCCCC1", "C1CCCCCCC1",
    "c1ccccc1", "c1ccncc1", "c1cncnc1", "c1cnccn1", "c1ccsc1", "c1ccoc1",
    "c1cc[nH]c1", "c1cnc[nH]1", "c1ccc2ccccc2c1", "c1ccc2[nH]ccc2c1",
    "C1CCNCC1", "C1CCOC1", "C1CCNC1", "C1COCCN1",
]
_PER = 6


def _group(i: int) -> list[str]:
    return ["C" * k + _SCAFFOLDS[i] for k in range(_PER)]


def _mols(scaffold_ids) -> list[str]:
    return [m for i in scaffold_ids for m in _group(i)]


def _write(ds: Path, name: str, smiles: list[str], labels: list[float]) -> None:
    pd.DataFrame({SMILES_COL: smiles, "label": labels}).to_csv(ds / f"{name}.csv", index=False)


def _labels(smiles: list[str], mod: int, *, offset: int = 0) -> list[float]:
    return [float((zlib.crc32(s.encode()) + offset) % mod == 0) for s in smiles]


@pytest.fixture
def toxicity_prep(tmp_path: Path) -> Path:
    """Two classification endpoints with deliberately DIFFERENT test sets.

    herg tests on scaffolds {0,1}; ames tests on {1,2}. So scaffold 2 is herg
    train_val but ames test — the cross-endpoint leak the cluster loader removes.
    """
    root = tmp_path / "20260921T000000Z"
    spec = {
        "herg_cardiotoxicity": dict(test=[0, 1], tv=list(range(2, 20)), cal=[18, 19], mod=2),
        "ames_mutagenicity": dict(test=[1, 2], tv=[0] + list(range(3, 20)), cal=[17, 18], mod=3),
    }
    for key, s in spec.items():
        ds = root / key
        ds.mkdir(parents=True)
        tv, te, ca = _mols(s["tv"]), _mols(s["test"]), _mols(s["cal"])
        # Alternate labels so every split carries both classes.
        _write(ds, "train_val", tv, [float(i % s["mod"] == 0) for i in range(len(tv))])
        _write(ds, "test", te, [float(i % s["mod"] == 0) for i in range(len(te))])
        _write(ds, "calibration", ca, [float(i % 2 == 0) for i in range(len(ca))])
        (ds / "provenance.json").write_text(json.dumps({"split_method": "adopt_benchmark"}))
    return root


@pytest.fixture
def clearance_prep(tmp_path: Path) -> Path:
    root = tmp_path / "20260921T000001Z"
    ds = root / "clearance_microsomal"
    ds.mkdir(parents=True)
    tv, te, ca = _mols(range(3, 20)), _mols([0, 1]), _mols([18, 19])
    _write(ds, "train_val", tv, [float(i) * 0.5 for i in range(len(tv))])
    _write(ds, "test", te, [float(i) * 0.5 for i in range(len(te))])
    _write(ds, "calibration", ca, [float(i) * 0.5 for i in range(len(ca))])
    (ds / "provenance.json").write_text(json.dumps({"split_method": "adopt_benchmark"}))
    return root


class StubKermt:
    """TEST DOUBLE — not KERMT. Deterministic pseudo-scores keyed on SMILES."""

    log: list[tuple] = []

    def __init__(self, task_type, checkpoint, target_names, *, seed=0, config=None):
        self.task_type = task_type
        self.target_names = list(target_names)
        self.model_id = "stub-not-kermt"
        self.fit_args = None
        StubKermt.instances.append(self)

    instances: list[StubKermt] = []

    def _raw(self, X):
        cols = len(self.target_names)
        return np.array(
            [
                [(zlib.crc32(f"{s}|{j}".encode()) % 2000) / 250.0 - 4.0 for j in range(cols)]
                for s in X
            ]
        )

    def fit(self, X_train, y_train, *, X_val=None, y_val=None, run_dir=None):
        StubKermt.log.append(("fit", len(X_train), len(X_val)))
        self.fit_args = (list(X_train), np.array(y_train), list(X_val), np.array(y_val))

    def _shape(self, out):
        return out[:, 0] if len(self.target_names) == 1 else out

    def predict(self, X, run_dir=None):
        StubKermt.log.append(("predict", tuple(X)))
        raw = self._raw(X)
        if self.task_type is TaskType.CLASSIFICATION:
            raw = 1.0 / (1.0 + np.exp(-raw))
        return self._shape(raw)

    def predict_logits(self, X, run_dir=None):
        assert self.task_type is TaskType.CLASSIFICATION
        StubKermt.log.append(("predict_logits", tuple(X)))
        return self._shape(self._raw(X))

    def save(self, path):
        Path(path).mkdir(parents=True, exist_ok=True)
        (Path(path) / "stub.txt").write_text("test double", encoding="utf-8")


@pytest.fixture(autouse=True)
def _stub(monkeypatch):
    StubKermt.log = []
    StubKermt.instances = []
    monkeypatch.setattr(harness, "KermtModel", StubKermt)


def _run(prep, tmp_path, *, subgroup_key, endpoints, cluster, **kw):
    cd = load_cluster(prep, endpoints, cluster_key=subgroup_key)
    spec = type_homogeneous_subgroups(cluster)[subgroup_key]
    cfg = ExperimentConfig(
        endpoint=subgroup_key, model_family=spec.model_family, seed=0, prep_id=cd.prep_id
    )
    result = harness.train_one_seed(
        cd, spec, cfg, 0, checkpoint=Path("stub.pt"), runs_dir=tmp_path / "runs", **kw
    )
    return cd, result


_TOX = dict(
    subgroup_key="toxicity__cls",
    endpoints=["herg_cardiotoxicity", "ames_mutagenicity"],
    cluster="toxicity",
)


# ---------------------------------------------------------------------------- #
# Training pool: calibration molecules are held out of train AND val
# ---------------------------------------------------------------------------- #


def test_calibration_molecules_never_reach_fit(toxicity_prep, tmp_path):
    cd, _ = _run(toxicity_prep, tmp_path, **_TOX)
    cal = cd.calibration_molecules()
    assert len(cal) > 0
    x_train, _, x_val, _ = StubKermt.instances[0].fit_args
    assert not cal & set(x_train)
    assert not cal & set(x_val)  # val selects the epoch, so it must be clean too


def test_test_molecules_never_reach_fit(toxicity_prep, tmp_path):
    cd, _ = _run(toxicity_prep, tmp_path, **_TOX)
    test = set(cd.smiles("test"))
    x_train, _, x_val, _ = StubKermt.instances[0].fit_args
    assert not test & set(x_train)
    assert not test & set(x_val)


def test_holdout_cost_is_measured_and_reported(toxicity_prep, tmp_path):
    cd, result = _run(toxicity_prep, tmp_path, **_TOX)
    pool, expected = cd.train_pool(holdout_calibration=True)
    assert result.labels_held_out_for_calibration == expected
    assert sum(expected.values()) > 0
    assert len(pool) < len(cd.train_val)


def test_calibrate_without_holdout_is_refused(toxicity_prep, tmp_path):
    """That combination would fit the scaler on molecules used to select epochs."""
    cd = load_cluster(toxicity_prep, _TOX["endpoints"], cluster_key="toxicity__cls")
    spec = type_homogeneous_subgroups("toxicity")["toxicity__cls"]
    cfg = ExperimentConfig("toxicity__cls", spec.model_family, 0, cd.prep_id)
    with pytest.raises(ValueError, match="requires holdout_calibration"):
        harness.train_one_seed(
            cd, spec, cfg, 0, checkpoint=Path("stub.pt"), runs_dir=tmp_path / "r",
            holdout_calibration=False, calibrate=True,
        )


def test_no_calibration_run_may_keep_the_full_pool(toxicity_prep, tmp_path):
    cd, result = _run(
        toxicity_prep, tmp_path, calibrate=False, holdout_calibration=False, **_TOX
    )
    assert result.calibration is None
    x_train, _, x_val, _ = StubKermt.instances[0].fit_args
    assert len(x_train) + len(x_val) == len(cd.train_val)


# ---------------------------------------------------------------------------- #
# Calibrate on the calibration split; score the test set afterwards
# ---------------------------------------------------------------------------- #


def test_fit_sees_calibration_labels_only_and_test_is_scored_after(
    toxicity_prep, tmp_path, monkeypatch
):
    seen: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    real = cc.diagnose_temperature_fit

    def spy(logits, y_true, **k):
        seen[k["endpoint_key"]] = (np.array(logits), np.array(y_true))
        return real(logits, y_true, **k)

    monkeypatch.setattr(cc, "diagnose_temperature_fit", spy)
    cd, _ = _run(toxicity_prep, tmp_path, **_TOX)

    oracle = StubKermt(TaskType.CLASSIFICATION, Path("x"), _TOX["endpoints"])
    for col, key in enumerate(_TOX["endpoints"]):
        assert key in seen
        fit_logits, fit_labels = seen[key]

        cal = cd.calibration[[SMILES_COL, key]].dropna()
        expected_cal_logits = oracle._raw(cal[SMILES_COL].tolist())[:, col]
        # Content check, not a length check: N happens to coincide with the test
        # N in this fixture, so only the actual values discriminate.
        np.testing.assert_allclose(np.sort(fit_logits), np.sort(expected_cal_logits))
        np.testing.assert_array_equal(np.sort(fit_labels), np.sort(cal[key].astype(int)))

        test = cd.endpoint_test_frame(key)
        test_logits = oracle._raw(test[SMILES_COL].tolist())[:, col]
        assert not np.allclose(np.sort(fit_logits), np.sort(test_logits))


def test_inference_order_is_fit_then_calibration_then_test(toxicity_prep, tmp_path):
    cd, _ = _run(toxicity_prep, tmp_path, **_TOX)
    kinds = [e[0] for e in StubKermt.log]
    assert kinds[0] == "fit"
    logits_calls = [e for e in StubKermt.log if e[0] == "predict_logits"]
    assert len(logits_calls) == 2
    assert list(logits_calls[0][1]) == cd.smiles("calibration")
    assert list(logits_calls[1][1]) == cd.smiles("test")
    # The test set is scored strictly after the calibration set.
    assert StubKermt.log.index(logits_calls[0]) < StubKermt.log.index(logits_calls[1])


def test_result_carries_a_complete_record_per_endpoint(toxicity_prep, tmp_path):
    cd, result = _run(toxicity_prep, tmp_path, **_TOX)
    assert set(result.calibration) == set(_TOX["endpoints"])
    for key, rec in result.calibration.items():
        assert [k for k in REQUIRED_RECORD_KEYS if k not in rec] == []
        assert rec["seed"] == 0
        assert rec["prep_id"] == cd.prep_id
        assert rec["model_id"] == "stub-not-kermt"
        # train_val rate comes from the cluster data, not from the calibration split.
        assert rec["train_val_positive_rate"] == pytest.approx(cd.positive_rates()[key])
        assert rec["test_metrics_raw"] is not None


def test_checkpoint_provenance_is_recorded_when_the_lockfile_exists(toxicity_prep, tmp_path):
    _, result = _run(toxicity_prep, tmp_path, **_TOX)
    lock = Path(__file__).resolve().parents[2] / "ml/data/metadata/kermt_checkpoint.lock.json"
    if not lock.exists():
        pytest.skip("kermt_checkpoint.lock.json not present on this machine")
    rec = next(iter(result.calibration.values()))
    assert rec["checkpoint_sha256"] == json.loads(lock.read_text())["files"][
        "kermt_contrastive_v2.0.pt"
    ]["sha256"]


def test_artifacts_and_metrics_are_persisted(toxicity_prep, tmp_path):
    _, result = _run(toxicity_prep, tmp_path, **_TOX)
    artifacts = Path(result.model_path).parents[1]
    for key in _TOX["endpoints"]:
        ep = artifacts / "calibration" / key
        assert (ep / "calibration_diagnostics.json").exists()
        rec = json.loads((ep / "calibration_diagnostics.json").read_text(encoding="utf-8"))
        assert [k for k in REQUIRED_RECORD_KEYS if k not in rec] == []
        if rec["status"] in ("fitted", "fitted_at_boundary"):
            assert (ep / "temperature_scaler.json").exists()

    metrics = (artifacts.parent / "metrics.jsonl").read_text(encoding="utf-8").splitlines()
    splits = [json.loads(line)["metrics"].get("split") for line in metrics]
    assert "val" in splits and "calibration+test" in splits


# ---------------------------------------------------------------------------- #
# Regression subgroups never attempt classification calibration
# ---------------------------------------------------------------------------- #


def test_regression_subgroup_is_never_calibrated(clearance_prep, tmp_path, monkeypatch):
    calls: list[str] = []
    real = cc.diagnose_temperature_fit
    monkeypatch.setattr(
        cc, "diagnose_temperature_fit",
        lambda logits, y, **k: (calls.append(k["endpoint_key"]), real(logits, y, **k))[1],
    )
    _, result = _run(
        clearance_prep, tmp_path,
        subgroup_key="metabolism__reg", endpoints=["clearance_microsomal"], cluster="metabolism",
    )

    assert calls == []
    assert not any(e[0] == "predict_logits" for e in StubKermt.log)
    rec = result.calibration["clearance_microsomal"]
    assert rec["status"] == "skipped_regression"
    assert rec["temperature"] is None
    assert rec["test_metrics_raw"] is not None and "mae" in rec["test_metrics_raw"]


def test_single_task_regression_uses_the_baseline_family(clearance_prep, tmp_path):
    """metabolism__reg is the single-task baseline, never a multi-task arm."""
    _, result = _run(
        clearance_prep, tmp_path,
        subgroup_key="metabolism__reg", endpoints=["clearance_microsomal"], cluster="metabolism",
    )
    assert result.cluster_key == "metabolism__reg"
    assert result.endpoint_keys == ["clearance_microsomal"]


def test_wrong_model_family_is_still_refused(toxicity_prep, tmp_path):
    cd = load_cluster(toxicity_prep, _TOX["endpoints"], cluster_key="toxicity__cls")
    spec = type_homogeneous_subgroups("toxicity")["toxicity__cls"]
    bad = ExperimentConfig("toxicity__cls", "kermt_single", 0, cd.prep_id)
    with pytest.raises(ValueError, match="must run as"):
        harness.train_one_seed(
            cd, spec, bad, 0, checkpoint=Path("stub.pt"), runs_dir=tmp_path / "r"
        )
