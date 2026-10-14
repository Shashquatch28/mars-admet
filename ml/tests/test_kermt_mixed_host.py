"""
Host-side tests for Tier 1: the model wrapper (container mocked), the gate
evaluators, and the per-seed driver (model replaced by a TEST DOUBLE).

Nothing here runs KERMT. The container is a Python function that creates the files
the real container scripts would create; that checks the MARS side's sequencing,
arguments, staging and file handling — not that KERMT accepts them (gates G1/G2).
"""

from __future__ import annotations

import csv
import json
import subprocess
import zlib
from pathlib import Path

import numpy as np
import pytest
from configs.experiment_config import ExperimentConfig
from data.cluster_loaders import load_cluster
from mars_contracts.endpoints import TaskType
from models import kermt_mixed_model as kmm
from models.kermt_mixed_model import KermtMixedModel, stage_trainer
from train import train_kermt_mixed as driver
from train.kermt_mixed import gates
from train.kermt_mixed.common import MODES, probability_to_logit

from tests.test_train_kermt_cluster_calibration import _mols, _write

TT = {
    "herg_cardiotoxicity": TaskType.CLASSIFICATION,
    "ames_mutagenicity": TaskType.CLASSIFICATION,
    "clearance_microsomal": TaskType.REGRESSION,
}
NAMES = list(TT)


# --------------------------- fake container ----------------------------------


class FakeContainer:
    """Stands in for ``_run_container``; records commands, writes expected files."""

    def __init__(self, *, fail_fit: bool = False):
        self.calls: list[dict] = []
        self.fail_fit = fail_fit

    def __call__(self, repo, image, *, data=None, ckpt=None, run_dir=None, command=""):
        self.calls.append({"data": data, "ckpt": ckpt, "run_dir": run_dir, "command": command})
        ok = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        if "check_checkpoint.py" in command:
            ok.stdout = json.dumps({"ok": True})
        elif "prepare_data.py" in command:
            out = Path(run_dir) / "data"
            out.mkdir(parents=True, exist_ok=True)
            (out / "prepare_data.json").write_text("{}")
        elif "--dry-run" in command:
            (Path(run_dir) / "run.json").write_text(
                json.dumps({"argv": ["python", "-u", "main.py", "finetune", "--seed", "0"]})
            )
        elif "--mode fit" in command:
            if self.fail_fit:
                return subprocess.CompletedProcess(
                    [], 1, stdout=json.dumps({"ok": False, "errors": ["boom"]}), stderr="trace"
                )
            d = Path(run_dir) / "ckpt" / "fold_0" / "model_0"
            d.mkdir(parents=True, exist_ok=True)
            (d / "model.pt").write_bytes(b"weights")
            (d / "mixed_meta.json").write_text(json.dumps({"best_epoch": 4}))
            ok.stdout = "banner\n" + json.dumps(
                {"ok": True, "summary": {"best_epoch": 4, "log_sigma_final": {n: 0.1 * i for i, n in enumerate(NAMES)}}}
            )
        elif "--mode predict" in command:
            # The staged spec is on the host side of the /data mount.
            smiles = [r[0] for r in csv.reader(open(next(Path(data).glob("smiles.csv"))))][1:]
            out = Path(run_dir) / "out"
            out.mkdir(parents=True, exist_ok=True)
            with (out / "predictions.csv").open("w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["smiles", *NAMES])
                for s in smiles:
                    u = (zlib.crc32(s.encode()) % 1000) / 1000.0
                    w.writerow([s, 0.2 + 0.6 * u, 0.9 * u + 0.05, 80.0 + 40 * u])
        return ok


@pytest.fixture
def container(monkeypatch):
    c = FakeContainer()
    monkeypatch.setattr(kmm, "_run_container", c)
    monkeypatch.setattr(kmm, "_kermt_repo", lambda: Path("/fake/kermt"))
    return c


def _model(tmp_path, **kw):
    tmp_path.mkdir(parents=True, exist_ok=True)
    ckpt = tmp_path / "pre.pt"
    ckpt.write_bytes(b"x")
    kw.setdefault("loss_mode", "fixed_task")
    kw.setdefault("min_per_task", 2)
    kw.setdefault("hyperparameter_source", "test-fixture")
    if kw["loss_mode"] == "gradnorm":
        kw.setdefault("gradnorm_alpha", 0.5)  # fixture values, not recommendations
        kw.setdefault("gradnorm_lr", 0.05)
    return KermtMixedModel(TT, ckpt, seed=3, work_dir=tmp_path / "work", **kw)


def _xy(n=12):
    smiles = [f"C{'C' * i}O" for i in range(n)]
    y = np.full((n, 3), np.nan)
    y[:, 0] = np.arange(n) % 2
    y[::2, 1] = 1.0
    y[::3, 2] = 100.0
    return smiles, y


# --------------------------- wrapper ------------------------------------------


def test_guards_and_surface(container, tmp_path):
    ckpt = tmp_path / "p.pt"
    ckpt.write_bytes(b"x")
    common = dict(min_per_task=2, hyperparameter_source="t")
    with pytest.raises(ValueError, match="non-empty"):
        KermtMixedModel({}, ckpt, loss_mode="fixed", **common)
    with pytest.raises(ValueError, match=">= 2 targets"):
        KermtMixedModel({"a": TaskType.REGRESSION}, ckpt, loss_mode="kendall", **common)
    with pytest.raises(ValueError, match="loss_mode"):
        KermtMixedModel(TT, ckpt, loss_mode="adam", **common)
    with pytest.raises(FileNotFoundError):
        KermtMixedModel(TT, tmp_path / "missing.pt", loss_mode="fixed", **common)
    # No silent defaults: the arm, the batch floor and the provenance are all required.
    with pytest.raises(TypeError):
        KermtMixedModel(TT, ckpt)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        KermtMixedModel(TT, ckpt, loss_mode="fixed")  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="hyperparameter_source"):
        KermtMixedModel(TT, ckpt, loss_mode="fixed", min_per_task=0, hyperparameter_source="")
    with pytest.raises(ValueError, match="gradnorm_alpha"):
        KermtMixedModel(TT, ckpt, loss_mode="gradnorm", **common)
    with pytest.raises(ValueError, match="only valid"):
        KermtMixedModel(TT, ckpt, loss_mode="kendall", gradnorm_alpha=1.0, gradnorm_lr=0.1, **common)
    m = _model(tmp_path)
    assert m.target_names == NAMES and m.target_task_types == TT
    assert m.model_id == "mars-kermt-mixed-v1" and m.supports_loss_weighting
    with pytest.raises(TypeError, match="no single task type"):
        _ = m.task_type
    assert set(MODES) == {"fixed", "fixed_task", "kendall", "gradnorm"}


def test_stage_trainer_copies_every_file_and_hashes_it(tmp_path):
    prov = stage_trainer(tmp_path)
    for name in kmm.STAGED_FILES:
        assert (tmp_path / "kermt_mixed" / name).exists()
        assert len(prov["files"][name]) == 64
    assert prov["trainer_version"]


def test_staged_set_is_exactly_the_trainer_package():
    """A new module added to the package but not to STAGED_FILES would be missing
    in the container and fail only on the GPU."""
    on_disk = {p.name for p in kmm._TRAINER_SRC.glob("*.py")} - set(kmm.HOST_ONLY_FILES)
    assert on_disk == set(kmm.STAGED_FILES)


def test_staged_modules_use_only_relative_intra_package_imports():
    for name in kmm.STAGED_FILES:
        text = (kmm._TRAINER_SRC / name).read_text(encoding="utf-8")
        assert "from train.kermt_mixed" not in text and "import train.kermt_mixed" not in text, name


def test_fit_runs_the_stock_steps_then_the_trainer(container, tmp_path):
    m = _model(tmp_path, loss_mode="kendall", min_per_task=3)
    smiles, y = _xy()
    m.fit(smiles[:8], y[:8], X_val=smiles[8:], y_val=y[8:])
    cmds = [c["command"] for c in container.calls]

    assert "check_checkpoint.py --mode finetune_init" in cmds[0]
    assert "prepare_data.py --mode finetune" in cmds[1]
    assert "--targets herg_cardiotoxicity ames_mutagenicity clearance_microsomal" in cmds[1]
    dry = cmds[2]
    assert "run_finetune_local.py --dry-run" in dry
    assert "--dataset-type classification --metric auc" in dry  # parse-time only
    assert "--ffn-num-task-specific-layers 1" in dry and "--ffn-task-specific-hidden-size 64" in dry
    assert "--seed 3" in dry
    fit = cmds[3]
    assert "python -u -m kermt_mixed.train_mixed --mode fit" in fit
    assert "--run-json /runs/run.json" in fit and "CUBLAS_WORKSPACE_CONFIG" in fit
    assert "PYTHONPATH=/data/_mars_trainer:" in fit

    assert m.is_fitted and m.fit_summary["best_epoch"] == 4
    work = tmp_path / "work"
    spec = json.loads((work / "input" / "_mars_trainer" / "spec.json").read_text())
    assert spec["target_names"] == NAMES
    assert spec["task_types"] == ["classification", "classification", "regression"]
    assert spec["loss"]["mode"] == "kendall" and spec["min_per_task"] == 3 and spec["seed"] == 3
    prov = json.loads((work / "trainer_provenance.json").read_text())
    assert set(prov["files"]) == set(kmm.STAGED_FILES)


def test_single_target_g3_arm_has_no_task_specific_heads_like_stock_single_task(container, tmp_path):
    ckpt = tmp_path / "p.pt"
    ckpt.write_bytes(b"x")
    m = KermtMixedModel(
        {"ames_mutagenicity": TaskType.CLASSIFICATION}, ckpt, loss_mode="fixed",
        min_per_task=0, hyperparameter_source="parity-gate", work_dir=tmp_path / "w1",
    )
    smiles = [f"C{'C' * i}O" for i in range(10)]
    y = np.array([[float(i % 2)] for i in range(10)])
    m.fit(smiles[:7], y[:7], X_val=smiles[7:], y_val=y[7:])
    dry = next(c["command"] for c in container.calls if "--dry-run" in c["command"])
    assert "task-specific" not in dry
    assert m.target_names == ["ames_mutagenicity"]


def test_fit_writes_empty_cells_for_missing_labels(container, tmp_path):
    m = _model(tmp_path)
    smiles, y = _xy()
    m.fit(smiles[:8], y[:8], X_val=smiles[8:], y_val=y[8:])
    rows = list(csv.reader((tmp_path / "work" / "input" / "train.csv").open()))
    assert rows[0] == ["smiles", *NAMES]
    assert rows[1][2] == "" or rows[2][2] == ""  # clearance is sparse -> blanks


def test_fit_requires_validation_and_a_work_dir(container, tmp_path):
    ckpt = tmp_path / "p.pt"
    ckpt.write_bytes(b"x")
    m = KermtMixedModel(TT, ckpt, loss_mode="fixed_task", min_per_task=2, hyperparameter_source="t")
    smiles, y = _xy()
    with pytest.raises(ValueError, match="X_val"):
        m.fit(smiles, y)
    with pytest.raises(ValueError, match="run_dir"):
        m.fit(smiles[:8], y[:8], X_val=smiles[8:], y_val=y[8:])
    with pytest.raises(ValueError, match=r"\(n, 3\)"):
        _model(tmp_path).fit(smiles, y[:, :2], X_val=smiles, y_val=y[:, :2])


def test_trainer_failure_surfaces_stderr_and_leaves_model_unfitted(monkeypatch, tmp_path):
    monkeypatch.setattr(kmm, "_run_container", FakeContainer(fail_fit=True))
    monkeypatch.setattr(kmm, "_kermt_repo", lambda: Path("/fake"))
    m = _model(tmp_path)
    smiles, y = _xy()
    with pytest.raises(RuntimeError, match="mixed trainer failed.*boom"):
        m.fit(smiles[:8], y[:8], X_val=smiles[8:], y_val=y[8:])
    assert not m.is_fitted


def test_predict_shape_order_and_logits_only_on_classification_columns(container, tmp_path):
    m = _model(tmp_path)
    smiles, y = _xy()
    m.fit(smiles[:8], y[:8], X_val=smiles[8:], y_val=y[8:])
    with pytest.raises(RuntimeError, match="not been fitted"):
        _model(tmp_path / "other").predict(smiles)

    p = m.predict(smiles[:5])
    assert p.shape == (5, 3)
    assert ((p[:, :2] > 0) & (p[:, :2] < 1)).all() and (p[:, 2] > 70).all()

    lg = m.predict_logits(smiles[:5])
    np.testing.assert_allclose(lg[:, :2], probability_to_logit(p[:, :2]))
    np.testing.assert_array_equal(lg[:, 2], p[:, 2])  # regression column untouched


def test_from_finetuned_wraps_an_existing_checkpoint_for_inference(container, tmp_path):
    ft = tmp_path / "stock.pt"
    ft.write_bytes(b"w")
    pre = tmp_path / "pre.pt"
    pre.write_bytes(b"x")
    m = KermtMixedModel.from_finetuned(ft, TT, pre, work_dir=tmp_path / "w")
    assert m.is_fitted
    smiles, _ = _xy()
    assert m.predict(smiles[:3]).shape == (3, 3)
    with pytest.raises(FileNotFoundError):
        KermtMixedModel.from_finetuned(tmp_path / "nope.pt", TT, pre, work_dir=tmp_path / "w")


def test_save_load_roundtrip(container, tmp_path):
    m = _model(tmp_path, loss_mode="gradnorm", min_per_task=1, gradnorm_alpha=0.7, gradnorm_lr=0.03)
    smiles, y = _xy()
    m.fit(smiles[:8], y[:8], X_val=smiles[8:], y_val=y[8:])
    m.save(tmp_path / "saved")
    meta = json.loads((tmp_path / "saved" / "metadata.json").read_text())
    assert meta["loss_mode"] == "gradnorm" and meta["target_names"] == NAMES
    assert meta["gradnorm"] == {"alpha": 0.7, "lr": 0.03}
    assert meta["hyperparameter_source"] == "test-fixture"
    assert (tmp_path / "saved" / "mixed_meta.json").exists()
    back = KermtMixedModel.load(tmp_path / "saved")
    assert back.is_fitted and back.loss_mode == "gradnorm" and back.target_task_types == TT


# --------------------------- gates --------------------------------------------


def _csv(path, smiles, cols, vals):
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["smiles", *cols])
        for s, row in zip(smiles, vals, strict=True):
            w.writerow([s, *row])
    return path


def test_g1_passes_within_tolerance_and_fails_beyond(tmp_path):
    smi = [f"C{i}" for i in range(64)]
    base = np.random.default_rng(0).random((64, 2))
    a = _csv(tmp_path / "a.csv", smi, ["x", "y"], base)
    b = _csv(tmp_path / "b.csv", smi, ["x", "y"], base + 5e-7)
    c = _csv(tmp_path / "c.csv", smi, ["x", "y"], base + 1e-3)
    assert gates.g1_forward_parity(a, b).passed
    r = gates.g1_forward_parity(a, c)
    assert not r.passed and r.evidence["per_column_max_abs_diff"]["x"] == pytest.approx(1e-3, rel=1e-3)
    assert not gates.g1_forward_parity(a, _csv(tmp_path / "d.csv", smi[::-1], ["x", "y"], base)).passed
    assert not gates.g1_forward_parity(
        _csv(tmp_path / "s.csv", smi[:10], ["x"], base[:10, :1]),
        _csv(tmp_path / "t.csv", smi[:10], ["x"], base[:10, :1]),
    ).passed  # under 64 rows


def test_g2_reads_stock_log_and_applies_the_band():
    log = "x\nEpoch: 0000 loss_train: 0.824100 loss_val: 0.7 auc_val: 0.7\nEpoch: 0001 loss_train: 0.6\n"
    assert gates.parse_stock_epoch_losses(log) == {0: 0.8241, 1: 0.6}
    assert gates.g2_loss_parity(log, 0.84).passed
    r = gates.g2_loss_parity(log, 0.95)
    assert not r.passed and r.evidence["relative_difference"] > 0.05
    assert not gates.g2_loss_parity("no epochs here", 0.8).passed


def test_g3_rule_both_conditions_required():
    stock = [0.890, 0.893, 0.887, 0.895, 0.891]
    ok = [0.891, 0.892, 0.888, 0.894, 0.890]
    assert gates.g3_auroc_parity(stock, ok).passed
    shifted = [v - 0.015 for v in stock]  # each pair within 0.02, mean far outside the band
    r = gates.g3_auroc_parity(stock, shifted)
    assert not r.passed and "mean diff" in r.summary
    noisy = [0.91, 0.87, 0.90, 0.88, 0.891]  # one pair ok, mean ok, but paired fails
    assert not gates.g3_auroc_parity(stock, noisy).passed
    assert not gates.g3_auroc_parity(stock[:1], ok[:1]).passed
    assert not gates.g3_auroc_parity(stock, [np.nan] * 5).passed


# --------------------------- driver -------------------------------------------


class FakeMixedModel:
    """TEST DOUBLE — not KERMT."""

    instances: list[FakeMixedModel] = []

    def __init__(self, cluster_data, checkpoint, seed, kermt_config, loss_mode, min_per_task,
                 hp_source, gn_alpha, gn_lr):
        self.hp_source = hp_source
        self.keys = list(cluster_data.endpoint_keys)
        self.types = cluster_data.task_types
        self.loss_mode = loss_mode
        self.model_id = "stub-not-kermt-mixed"
        self.fit_summary = {"best_epoch": 2, "log_sigma_final": {k: 0.05 * i for i, k in enumerate(self.keys)}}
        self.calls: list[tuple] = []
        FakeMixedModel.instances.append(self)

    def _raw(self, X):
        return np.array(
            [[(zlib.crc32(f"{s}|{j}".encode()) % 2000) / 250.0 - 4.0 for j in range(len(self.keys))] for s in X]
        )

    def fit(self, X_train, y_train, *, X_val=None, y_val=None, run_dir=None):
        self.fit_args = (list(X_train), np.array(y_train), list(X_val), np.array(y_val))

    def predict(self, X, run_dir=None):
        out = self._raw(X)
        for j, k in enumerate(self.keys):
            if self.types[k] is TaskType.CLASSIFICATION:
                out[:, j] = 1 / (1 + np.exp(-out[:, j]))
        return out

    def predict_logits(self, X, run_dir=None):
        self.calls.append(("logits", len(X)))
        return self._raw(X)

    def save(self, path):
        Path(path).mkdir(parents=True, exist_ok=True)
        (Path(path) / "stub.txt").write_text("double")


def _factory(cd, ckpt, seed, cfg, loss_mode, mpt, hp, ga, gl):
    return FakeMixedModel(cd, ckpt, seed, cfg, loss_mode, mpt, hp, ga, gl)


@pytest.fixture
def mixed_prep(tmp_path) -> Path:
    root = tmp_path / "20261014T000000Z"
    layout = {
        "herg_cardiotoxicity": dict(test=[0, 1], tv=range(2, 20), cal=[18, 19], mod=2),
        "ames_mutagenicity": dict(test=[1, 2], tv=[0, *range(3, 20)], cal=[17, 18], mod=3),
        "clearance_microsomal": dict(test=[0, 1], tv=range(3, 20), cal=[18, 19], mod=None),
    }
    for key, s in layout.items():
        ds = root / key
        ds.mkdir(parents=True)
        tv, te, ca = _mols(s["tv"]), _mols(s["test"]), _mols(s["cal"])
        if s["mod"] is None:
            lab = lambda n: [0.5 * i for i in range(n)]  # noqa: E731
        else:
            lab = lambda n, m=s["mod"]: [float(i % m == 0) for i in range(n)]  # noqa: E731
        _write(ds, "train_val", tv, lab(len(tv)))
        _write(ds, "test", te, lab(len(te)))
        _write(ds, "calibration", ca, [float(i % 2 == 0) for i in range(len(ca))] if s["mod"] else lab(len(ca)))
        (ds / "provenance.json").write_text(json.dumps({"split_method": "adopt_benchmark"}))
    return root


@pytest.fixture(autouse=True)
def _reset():
    FakeMixedModel.instances = []


def _go(prep, tmp_path, **kw):
    cd = load_cluster(prep, NAMES, cluster_key="mixed_cluster")
    cfg = ExperimentConfig("mixed_cluster", "kermt_mixed", 0, cd.prep_id)
    kw.setdefault("loss_mode", "fixed_task")
    kw.setdefault("min_per_task", 2)
    kw.setdefault("hyperparameter_source", "test-fixture")
    if kw["loss_mode"] == "gradnorm":
        kw.setdefault("gradnorm_alpha", 0.5)  # fixture values, not recommendations
        kw.setdefault("gradnorm_lr", 0.05)
    res = driver.train_one_seed_mixed(
        cd, cfg, 0, checkpoint=Path("stub.pt"), runs_dir=tmp_path / "runs",
        model_factory=_factory, **kw,
    )
    return cd, res


def test_driver_runs_a_mixed_cluster_end_to_end(mixed_prep, tmp_path):
    cd, res = _go(mixed_prep, tmp_path, loss_mode="kendall")
    assert res.cluster_key == "mixed_cluster" and res.endpoint_keys == NAMES
    assert res.log_sigma_final == {"herg_cardiotoxicity": 0.0, "ames_mutagenicity": 0.05, "clearance_microsomal": 0.1}
    assert type(res.per_endpoint_metrics["clearance_microsomal"]).__name__ == "RegressionMetrics"
    assert type(res.per_endpoint_metrics["herg_cardiotoxicity"]).__name__ == "ClassificationMetrics"
    assert res.calibration["clearance_microsomal"]["status"] == "skipped_regression"
    assert res.calibration["herg_cardiotoxicity"]["status"] in ("fitted", "fitted_at_boundary")
    assert res.calibration["herg_cardiotoxicity"]["model_id"] == "stub-not-kermt-mixed"


def test_driver_keeps_calibration_and_test_molecules_out_of_fit(mixed_prep, tmp_path):
    cd, _ = _go(mixed_prep, tmp_path)
    x_train, _, x_val, _ = FakeMixedModel.instances[0].fit_args
    fit_mols = set(x_train) | set(x_val)
    assert cd.calibration_molecules() and not cd.calibration_molecules() & fit_mols
    assert not set(cd.smiles("test")) & fit_mols


def test_run_name_carries_the_arm_so_arms_never_collide(mixed_prep, tmp_path):
    _, res = _go(mixed_prep, tmp_path, loss_mode="gradnorm")
    assert res.run_id.startswith("kermt_mx_mixed_cluster_seed0_gradnorm_")
    _, res2 = _go(mixed_prep, tmp_path, loss_mode="fixed_task")
    assert "_fixed_task_" in res2.run_id and res.run_id != res2.run_id


def test_driver_refuses_wrong_family_bad_mode_and_uncalibratable_combo(mixed_prep, tmp_path):
    cd = load_cluster(mixed_prep, NAMES, cluster_key="mixed_cluster")
    base = dict(
        checkpoint=Path("s.pt"), runs_dir=tmp_path / "r", model_factory=_factory,
        min_per_task=0, hyperparameter_source="t",
    )
    with pytest.raises(ValueError, match="kermt_mixed"):
        driver.train_one_seed_mixed(
            cd, ExperimentConfig("c", "kermt_multitask_subgroup", 0, cd.prep_id), 0,
            loss_mode="fixed_task", **base,
        )
    cfg = ExperimentConfig("c", "kermt_mixed", 0, cd.prep_id)
    with pytest.raises(ValueError, match="loss_mode"):
        driver.train_one_seed_mixed(cd, cfg, 0, loss_mode="sgd", **base)
    with pytest.raises(ValueError, match="requires holdout_calibration"):
        driver.train_one_seed_mixed(
            cd, cfg, 0, loss_mode="fixed_task", holdout_calibration=False, calibrate=True, **base
        )


def test_driver_persists_fit_summary_and_the_two_stage_inference_order(mixed_prep, tmp_path):
    cd, res = _go(mixed_prep, tmp_path)
    run_dir = Path(res.model_path).parents[1]
    summary = json.loads((run_dir / "model" / "fit_summary.json").read_text())
    assert summary["best_epoch"] == 2
    assert [c[1] for c in FakeMixedModel.instances[0].calls] == [
        len(cd.smiles("calibration")),
        len(cd.smiles("test")),
    ]


def test_tuning_trial_never_reads_the_test_or_calibration_split(mixed_prep, tmp_path):
    """calibrate=False is how a tuning trial runs: only the validation fold is scored."""
    cd, res = _go(mixed_prep, tmp_path, calibrate=False)
    model = FakeMixedModel.instances[0]
    assert model.calls == []  # predict_logits (cal + test) never called
    assert res.calibration is None
    assert model.hp_source == "test-fixture"
    assert set(res.per_endpoint_metrics) == set(NAMES)
    assert cd.smiles("test")  # the split exists; it was simply not touched


def test_hyperparameter_source_is_recorded_in_the_run_config(mixed_prep, tmp_path):
    _go(mixed_prep, tmp_path, hyperparameter_source="tuning:abc123def456:3")
    cfgs = list((tmp_path / "runs").rglob("config.json"))
    assert cfgs
    blob = cfgs[0].read_text()
    assert "tuning:abc123def456:3" in blob and '"min_per_task"' in blob
