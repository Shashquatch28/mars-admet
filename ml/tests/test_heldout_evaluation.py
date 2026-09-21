"""
Tests for eval/heldout_evaluation.py and train/evaluate_xgboost_test.py.

Logic tests use a stub model loader (no featurizer, no xgboost) over synthetic splits and
a synthetic artifacts tree. Two integration tests run against the REAL promoted artifacts
and skip cleanly on a machine that does not have them.
"""

from __future__ import annotations

import json
import zlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from data.loaders import EndpointData
from eval.calibration import fit_platt_calibrator
from eval.heldout_evaluation import (
    EvaluationBlocked,
    HeldOutEvaluationReport,
    evaluate_endpoint_on_test,
    sha256_file,
    sha256_tree,
)
from mars_contracts.endpoints import TaskType

CLF, REG = TaskType.CLASSIFICATION, TaskType.REGRESSION
KEY = "cyp3a4_inhibition"


def _frame(prefix: str, n: int, seed: int, clf: bool) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    smiles = [f"{prefix}{i}" for i in range(n)]
    label = (rng.random(n) < 0.4).astype(float) if clf else rng.normal(0, 1, n)
    return pd.DataFrame({"standardized_smiles": smiles, "label": label})


def _endpoint(clf: bool = True, key: str = KEY) -> EndpointData:
    return EndpointData(
        endpoint_key=key,
        dataset_key=key,
        task_type=CLF if clf else REG,
        prep_id="20260830T200000Z",
        train_val=_frame("tv", 200, 1, clf),
        test=_frame("te", 120, 2, clf),
        calibration=_frame("ca", 90, 3, clf),
        provenance={"split_method": "adopt_benchmark"},
    )


class StubModel:
    """Deterministic, label-informative scores keyed on the SMILES string."""

    calls: list[tuple[int, tuple[str, ...]]] = []

    def __init__(self, seed: int, truth: dict[str, float], clf: bool, nan_for: set[str]):
        self.seed, self.truth, self.clf, self.nan_for = seed, truth, clf, nan_for

    def predict(self, X):
        StubModel.calls.append((self.seed, tuple(X)))
        out = []
        for s in X:
            if s in self.nan_for:
                out.append(np.nan)
                continue
            rng = np.random.default_rng(zlib.crc32(f"{self.seed}|{s}".encode()))
            y = self.truth[s]
            out.append(float(np.clip(0.25 + 0.5 * y + rng.normal(0, 0.15), 0.01, 0.99)) if self.clf
                       else float(y + rng.normal(0, 0.3)))
        return np.array(out)


def _make_loader(data: EndpointData, nan_for: frozenset[str] = frozenset()):
    truth = {}
    for df in (data.test, data.calibration, data.train_val):
        truth.update(dict(zip(df["standardized_smiles"], df["label"], strict=True)))
    clf = data.task_type is CLF

    def loader(seed_dir, cache):
        seed = json.loads((Path(seed_dir) / "metadata.json").read_text())["seed"]
        return StubModel(seed, truth, clf, set(nan_for))

    return loader


def _write_artifacts(root: Path, data: EndpointData, *, calibrator: str = "seed4",
                     seeds=(0, 1, 2, 3, 4), loader=None) -> Path:
    ep = root / data.endpoint_key
    for s in seeds:
        d = ep / f"seed_{s}"
        d.mkdir(parents=True)
        (d / "metadata.json").write_text(json.dumps({"seed": s, "task_type": data.task_type.value}))
        (d / "model.json").write_text(f'{{"stub_model_seed": {s}}}')
    if data.task_type is CLF and calibrator == "seed4":
        truth = {}
        for df in (data.test, data.calibration, data.train_val):
            truth.update(dict(zip(df["standardized_smiles"], df["label"], strict=True)))
        model = StubModel(4, truth, True, set())  # independent of whether seed_4/ exists
        cal_s = data.calibration["standardized_smiles"].tolist()
        preds = model.predict(cal_s)
        y = data.calibration["label"].astype(float).to_numpy()
        fit_platt_calibrator(preds, y).save(ep / "calibrator.json")
    return root


@pytest.fixture(autouse=True)
def _reset_calls():
    StubModel.calls = []


def _run(data, root, **kw):
    return evaluate_endpoint_on_test(
        data, endpoint_key=data.endpoint_key, artifacts_root=root, cache=None,
        prep_id=data.prep_id, model_loader=kw.pop("model_loader", _make_loader(data)), **kw,
    )


# ---------------------------------------------------------------------------- #
# What is scored, and what is never touched
# ---------------------------------------------------------------------------- #


def test_test_split_is_scored_and_train_data_is_never_predicted(tmp_path):
    data = _endpoint()
    root = _write_artifacts(tmp_path, data)
    _run(data, root)

    test_smiles = tuple(data.test["standardized_smiles"])
    cal_smiles = tuple(data.calibration["standardized_smiles"])
    train = set(data.train_val["standardized_smiles"])
    seen = {s for _, X in StubModel.calls for s in X}
    assert not seen & train  # training molecules never scored
    assert {X for _, X in StubModel.calls} == {test_smiles, cal_smiles}


def test_nothing_under_artifacts_is_written_or_modified(tmp_path):
    data = _endpoint()
    root = _write_artifacts(tmp_path, data)
    before_tree = sha256_tree(root)
    before_cal = sha256_file(root / KEY / "calibrator.json")

    _run(data, root)

    assert sha256_tree(root) == before_tree
    assert sha256_file(root / KEY / "calibrator.json") == before_cal


def test_test_labels_cannot_change_the_served_calibrator_or_its_verification(tmp_path):
    """Calibration provenance uses the calibration split only."""
    data = _endpoint()
    root = _write_artifacts(tmp_path, data)
    a = _run(data, root)

    scrambled = _endpoint()
    scrambled.test["label"] = 1.0 - scrambled.test["label"]  # garbage test labels
    b = evaluate_endpoint_on_test(
        scrambled, endpoint_key=KEY, artifacts_root=root, cache=None, prep_id="p",
        model_loader=_make_loader(data),
    )
    assert a.calibrator == b.calibrator  # A, B, sha, seeds_reproducing: all identical
    assert a.aggregated_test_raw != b.aggregated_test_raw  # ...while the scores did change


# ---------------------------------------------------------------------------- #
# Metrics
# ---------------------------------------------------------------------------- #


def test_classification_reports_raw_and_calibrated_and_project_metrics(tmp_path):
    data = _endpoint()
    rep = _run(data, _write_artifacts(tmp_path, data))
    assert rep.split == "test" and rep.model_family == "xgboost" and rep.task_type == "classification"
    for arm in (rep.aggregated_test_raw, rep.aggregated_test_calibrated):
        assert {"auroc_mean", "auroc_std", "auprc_mean", "brier_score_mean", "ece_mean", "ece_std"} <= set(arm)
        assert arm["n_seeds"] == 5.0
    # Platt with A>0 is monotone, so ranking metrics are untouched by calibration.
    assert rep.aggregated_test_calibrated["auroc_mean"] == pytest.approx(rep.aggregated_test_raw["auroc_mean"])


def test_aggregate_is_the_mean_and_sample_std_over_seeds(tmp_path):
    data = _endpoint()
    rep = _run(data, _write_artifacts(tmp_path, data))
    aurocs = [s["test_metrics_raw"]["auroc"] for s in rep.per_seed]
    assert len(aurocs) == 5
    assert rep.aggregated_test_raw["auroc_mean"] == pytest.approx(np.mean(aurocs))
    assert rep.aggregated_test_raw["auroc_std"] == pytest.approx(np.std(aurocs, ddof=1))


def test_regression_uses_the_canonical_metric_and_has_no_calibration(tmp_path):
    data = _endpoint(clf=False, key="clearance_microsomal")
    rep = _run(data, _write_artifacts(tmp_path, data))
    assert rep.task_type == "regression"
    assert "mae_mean" in rep.aggregated_test_raw and "auroc_mean" not in rep.aggregated_test_raw
    assert rep.aggregated_test_calibrated is None and rep.calibrator is None
    assert all(s["test_metrics_calibrated"] is None for s in rep.per_seed)


def test_unscoreable_molecules_are_counted_not_hidden(tmp_path):
    data = _endpoint()
    bad = frozenset(data.test["standardized_smiles"].iloc[:3])
    rep = _run(data, _write_artifacts(tmp_path, data), model_loader=_make_loader(data, bad))
    for s in rep.per_seed:
        assert s["n_dropped"] == 3 and s["n_scored"] == s["n_test"] - 3


# ---------------------------------------------------------------------------- #
# Calibrator provenance (the one-file-per-endpoint overwrite)
# ---------------------------------------------------------------------------- #


def test_served_calibrator_is_traced_to_the_seed_that_produced_it(tmp_path):
    data = _endpoint()
    rep = _run(data, _write_artifacts(tmp_path, data))
    assert rep.calibrator["seeds_reproducing_served_calibrator"] == [4]
    matched = {s["seed"]: s["calibrator_is_seed_matched"] for s in rep.per_seed}
    assert matched == {0: False, 1: False, 2: False, 3: False, 4: True}
    assert any("NOT fit on those seeds" in n for n in rep.notes)


def test_calibrator_verification_can_be_disabled(tmp_path):
    data = _endpoint()
    rep = _run(data, _write_artifacts(tmp_path, data), verify_calibrator_seed=False)
    assert rep.calibrator["verified"] is False
    assert all(s["calibrator_is_seed_matched"] is None for s in rep.per_seed)


def test_calibration_split_metrics_are_reported_separately_from_test(tmp_path):
    data = _endpoint()
    rep = _run(data, _write_artifacts(tmp_path, data))
    s = rep.per_seed[0]
    assert s["calibration_split_metrics_raw"]["n_samples"] == len(data.calibration)
    assert s["test_metrics_raw"]["n_samples"] == len(data.test)  # distinct splits, distinct n


# ---------------------------------------------------------------------------- #
# Blocked, never substituted
# ---------------------------------------------------------------------------- #


def test_missing_seed_artifact_blocks_instead_of_substituting(tmp_path):
    data = _endpoint()
    root = _write_artifacts(tmp_path, data, seeds=(0, 1, 2, 3))  # seed 4 absent
    with pytest.raises(EvaluationBlocked, match="not substituting validation metrics") as ei:
        _run(data, root)
    assert ei.value.endpoint_key == KEY and "seed 4" in ei.value.reason


def test_incomplete_seed_directory_blocks(tmp_path):
    data = _endpoint()
    root = _write_artifacts(tmp_path, data)
    (root / KEY / "seed_2" / "model.json").unlink()
    with pytest.raises(EvaluationBlocked, match="seed 2"):
        _run(data, root)


def test_classification_without_a_served_calibrator_blocks(tmp_path):
    data = _endpoint()
    root = _write_artifacts(tmp_path, data, calibrator="none")
    with pytest.raises(EvaluationBlocked, match="no served calibrator"):
        _run(data, root)


def test_missing_endpoint_directory_blocks(tmp_path):
    with pytest.raises(EvaluationBlocked, match="no promoted artifacts"):
        _run(_endpoint(), tmp_path)


def test_empty_test_split_blocks(tmp_path):
    data = _endpoint()
    data.test = data.test.iloc[:0]
    with pytest.raises(EvaluationBlocked, match="test split is empty"):
        _run(data, _write_artifacts(tmp_path, data))


# ---------------------------------------------------------------------------- #
# Provenance + persistence
# ---------------------------------------------------------------------------- #


def test_report_carries_endpoint_seed_model_and_prep_provenance(tmp_path):
    data = _endpoint()
    root = _write_artifacts(tmp_path, data)
    csv = tmp_path / "test.csv"
    data.test.to_csv(csv, index=False)
    rep = _run(data, root, test_csv_path=csv)

    assert rep.endpoint_key == KEY and rep.prep_id == "20260830T200000Z" and rep.seeds == [0, 1, 2, 3, 4]
    assert rep.test_set_sha256 == sha256_file(csv)
    assert rep.n_test == len(data.test)
    for s in rep.per_seed:
        assert s["model_sha256"] == sha256_file(Path(s["model_dir"]) / "model.json")


def test_validation_numbers_are_echoed_only_as_a_labelled_reference(tmp_path):
    data = _endpoint()
    root = _write_artifacts(tmp_path, data)
    val = tmp_path / "val.json"
    val.write_text(json.dumps({"aggregated": {"auroc_mean": 0.999}}))
    rep = _run(data, root, validation_report_path=val)

    assert rep.validation_reference["split"] == "validation"
    assert "NOT test-set numbers" in rep.validation_reference["note"]
    assert rep.aggregated_test_raw["auroc_mean"] != 0.999  # never blended in


def test_report_roundtrips_through_disk(tmp_path):
    data = _endpoint()
    rep = _run(data, _write_artifacts(tmp_path, data))
    path = tmp_path / "out" / "r.json"
    rep.save(path)
    loaded = HeldOutEvaluationReport.load(path)
    assert loaded.split == "test" and loaded.per_seed == json.loads(json.dumps(rep.per_seed))


# ---------------------------------------------------------------------------- #
# CLI output-location guard
# ---------------------------------------------------------------------------- #


def test_cli_refuses_to_write_into_artifacts_or_validation_reports(tmp_path):
    from train.evaluate_xgboost_test import _assert_safe_output

    ml_root = tmp_path
    (ml_root / "artifacts").mkdir()
    (ml_root / "runs" / "evaluations").mkdir(parents=True)
    for bad in (ml_root / "artifacts", ml_root / "artifacts" / "x", ml_root / "runs" / "evaluations"):
        with pytest.raises(SystemExit, match="Refusing"):
            _assert_safe_output(bad, ml_root)
    _assert_safe_output(ml_root / "runs" / "test_evaluations", ml_root)  # fine


# ---------------------------------------------------------------------------- #
# Integration: REAL promoted artifacts (skip when absent)
# ---------------------------------------------------------------------------- #

_ML = Path(__file__).resolve().parents[1]
_PREP = _ML / "data" / "processed" / "20260830T200000Z"
_REAL = (_ML / "artifacts" / "hia_absorption" / "seed_4" / "model.json").exists() and _PREP.exists()


@pytest.mark.skipif(not _REAL, reason="promoted artifacts / processed snapshot not present")
def test_real_hia_artifacts_evaluate_on_the_real_test_split(tmp_path):
    from data.loaders import load_endpoint
    from featurize.cache import FeatureCache

    data = load_endpoint(_PREP, "hia_absorption")
    rep = evaluate_endpoint_on_test(
        data, endpoint_key="hia_absorption", artifacts_root=_ML / "artifacts",
        cache=FeatureCache(_ML / "data" / "cache"), prep_id="20260830T200000Z",
        test_csv_path=_PREP / "hia_absorption" / "test.csv",
    )
    assert rep.n_test == 117 and rep.seeds == [0, 1, 2, 3, 4] and rep.split == "test"
    assert rep.calibrator["seeds_reproducing_served_calibrator"] == [4]
    assert 0.9 < rep.aggregated_test_raw["auroc_mean"] <= 1.0


@pytest.mark.skipif(not _PREP.exists(), reason="processed snapshot not present")
def test_augmented_dili_test_split_is_bit_identical_to_the_base_split():
    """The evaluator scores DILI on the augmented variant (as the sweep trained it)."""
    from data.loaders import load_endpoint

    base = load_endpoint(_PREP, "dili_liver_injury", use_augmented_dili=False).test
    aug = load_endpoint(_PREP, "dili_liver_injury", use_augmented_dili=True).test
    pd.testing.assert_frame_equal(base.reset_index(drop=True), aug.reset_index(drop=True))
