"""Tests for the pure-Python parts of ml/models/kermt_model.py — construction,
config/env validation, and hyperparameter/target-shape logic that don't
require docker, the KERMT checkout, or a GPU.

Container-level behavior (checkpoint validation, finetune, inference) is
covered by the Smoke 1-6 sequence in documentation/AIMS/decisions.md, not
here — those need `MARS_KERMT_REPO` + the built `kermt:latest` image.
"""

from __future__ import annotations

import json
import subprocess

import numpy as np
import pytest
from mars_contracts.endpoints import TaskType
from models.kermt_model import (
    KermtConfig,
    KermtModel,
    KermtUnavailableError,
    _kermt_repo,
    _parse_json_stdout,
)


@pytest.fixture(autouse=True)
def _clear_kermt_env(monkeypatch):
    monkeypatch.delenv("MARS_KERMT_REPO", raising=False)
    monkeypatch.delenv("MARS_KERMT_IMAGE", raising=False)


def test_kermt_repo_env_missing_raises():
    with pytest.raises(KermtUnavailableError, match="MARS_KERMT_REPO is not set"):
        _kermt_repo()


def test_kermt_repo_env_set_but_not_a_checkout_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("MARS_KERMT_REPO", str(tmp_path))
    with pytest.raises(KermtUnavailableError, match="does not look like a KERMT checkout"):
        _kermt_repo()


def test_kermt_repo_env_set_to_valid_checkout(tmp_path, monkeypatch):
    helper = tmp_path / "agent" / "scripts" / "kermt_container.sh"
    helper.parent.mkdir(parents=True)
    helper.write_text("#!/bin/bash\n")
    monkeypatch.setenv("MARS_KERMT_REPO", str(tmp_path))
    assert _kermt_repo() == tmp_path


def _fake_ckpt(tmp_path):
    ckpt = tmp_path / "kermt_contrastive_v2.0.pt"
    ckpt.write_bytes(b"not a real checkpoint, just needs to exist")
    return ckpt


def test_model_id_single_vs_multitask(tmp_path, monkeypatch):
    monkeypatch.setenv("MARS_KERMT_REPO", str(tmp_path))
    (tmp_path / "agent" / "scripts").mkdir(parents=True)
    (tmp_path / "agent" / "scripts" / "kermt_container.sh").write_text("#!/bin/bash\n")
    ckpt = _fake_ckpt(tmp_path)

    single = KermtModel(TaskType.CLASSIFICATION, ckpt, ["herg_cardiotoxicity"])
    assert single.model_id == "mars-kermt-single-v1"
    assert single.task_type == TaskType.CLASSIFICATION
    assert not single.is_fitted

    multi = KermtModel(TaskType.CLASSIFICATION, ckpt, ["herg_cardiotoxicity", "ames_mutagenicity"])
    assert multi.model_id == "mars-kermt-multitask-v1"


def test_missing_checkpoint_raises_filenotfound(tmp_path, monkeypatch):
    monkeypatch.setenv("MARS_KERMT_REPO", str(tmp_path))
    (tmp_path / "agent" / "scripts").mkdir(parents=True)
    (tmp_path / "agent" / "scripts" / "kermt_container.sh").write_text("#!/bin/bash\n")
    with pytest.raises(FileNotFoundError):
        KermtModel(TaskType.REGRESSION, tmp_path / "does_not_exist.pt", ["solubility_logs"])


def test_empty_target_names_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("MARS_KERMT_REPO", str(tmp_path))
    (tmp_path / "agent" / "scripts").mkdir(parents=True)
    (tmp_path / "agent" / "scripts" / "kermt_container.sh").write_text("#!/bin/bash\n")
    ckpt = _fake_ckpt(tmp_path)
    with pytest.raises(ValueError, match="target_names must be non-empty"):
        KermtModel(TaskType.REGRESSION, ckpt, [])


def _model(tmp_path, monkeypatch, task_type=TaskType.CLASSIFICATION, targets=None):
    monkeypatch.setenv("MARS_KERMT_REPO", str(tmp_path))
    (tmp_path / "agent" / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "agent" / "scripts" / "kermt_container.sh").write_text("#!/bin/bash\n")
    ckpt = _fake_ckpt(tmp_path)
    return KermtModel(task_type, ckpt, targets or ["herg_cardiotoxicity"])


def test_targets_dict_single_task(tmp_path, monkeypatch):
    m = _model(tmp_path, monkeypatch, targets=["herg_cardiotoxicity"])
    y = np.array([1.0, 0.0, 1.0])
    d = m._targets_dict(y)
    assert list(d.keys()) == ["herg_cardiotoxicity"]
    np.testing.assert_array_equal(d["herg_cardiotoxicity"], y)


def test_targets_dict_single_task_rejects_2d(tmp_path, monkeypatch):
    m = _model(tmp_path, monkeypatch, targets=["herg_cardiotoxicity"])
    with pytest.raises(ValueError, match="single-task: y must be 1-D"):
        m._targets_dict(np.zeros((3, 1)))


def test_targets_dict_multitask(tmp_path, monkeypatch):
    m = _model(tmp_path, monkeypatch, targets=["herg_cardiotoxicity", "ames_mutagenicity"])
    y = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, np.nan]])
    d = m._targets_dict(y)
    assert list(d.keys()) == ["herg_cardiotoxicity", "ames_mutagenicity"]
    np.testing.assert_array_equal(d["herg_cardiotoxicity"], [1.0, 0.0, 1.0])
    assert np.isnan(d["ames_mutagenicity"][2])


def test_targets_dict_multitask_rejects_shape_mismatch(tmp_path, monkeypatch):
    m = _model(tmp_path, monkeypatch, targets=["herg_cardiotoxicity", "ames_mutagenicity"])
    with pytest.raises(ValueError, match="multi-task: y must be 2-D"):
        m._targets_dict(np.zeros(3))
    with pytest.raises(ValueError, match="multi-task: y must be 2-D"):
        m._targets_dict(np.zeros((3, 3)))


def test_dataset_type_flag(tmp_path, monkeypatch):
    # Targets must match the declared task type — the homogeneity guard added
    # 2026-09-20 rejects a regression run declared over a classification endpoint.
    clf = _model(tmp_path, monkeypatch, task_type=TaskType.CLASSIFICATION)
    reg = _model(
        tmp_path, monkeypatch, task_type=TaskType.REGRESSION, targets=["solubility_logs"]
    )
    assert clf._dataset_type_flag() == "classification"
    assert reg._dataset_type_flag() == "regression"


def test_hyperparam_flags_only_includes_set_values(tmp_path, monkeypatch):
    m = _model(tmp_path, monkeypatch)
    m._cfg = KermtConfig(epochs=2, batch_size=8)
    flags = m._hyperparam_flags()
    assert "--epochs 2" in flags
    assert "--batch-size 8" in flags
    assert "--init-lr" not in flags
    assert "--dropout" not in flags


def test_hyperparam_flags_defaults_metric_by_task_type(tmp_path, monkeypatch):
    """Regression test: agent/config/defaults_finetune.json's task.metric
    default is unconditionally "mae" (regression-oriented); passing that
    through for a classification run trips kermt/util/parsing.py's
    dataset_type/metric validation (caught live 2026-09-18 on the AMES smoke
    test: 'Metric "mae" invalid for dataset type "classification"'). The
    wrapper must always resolve a task_type-correct metric itself."""
    clf = _model(tmp_path, monkeypatch, task_type=TaskType.CLASSIFICATION)
    reg = _model(
        tmp_path, monkeypatch, task_type=TaskType.REGRESSION, targets=["solubility_logs"]
    )
    assert "--metric auc" in clf._hyperparam_flags()
    assert "--metric mae" in reg._hyperparam_flags()


def test_hyperparam_flags_respects_explicit_metric_override(tmp_path, monkeypatch):
    m = _model(tmp_path, monkeypatch, task_type=TaskType.CLASSIFICATION)
    m._cfg = KermtConfig(metric="prc-auc")
    assert "--metric prc-auc" in m._hyperparam_flags()


def test_fit_requires_val(tmp_path, monkeypatch):
    m = _model(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="requires X_val/y_val"):
        m.fit(["CCO"], np.array([1.0]))


def test_predict_before_fit_raises(tmp_path, monkeypatch):
    m = _model(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match="has not been fitted"):
        m.predict(["CCO"])


def test_save_before_fit_raises(tmp_path, monkeypatch):
    m = _model(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match="has not been fitted"):
        m.save(tmp_path / "out")


def test_parse_json_stdout_handles_banner_prefixed_pretty_json():
    """Regression test: kermt_container.sh's output is prefixed with container/
    CUDA banner text before the script's `json.dumps(..., indent=2)` output —
    caught live during the 2026-09-18 AMES smoke test (check_checkpoint.py's
    real JSON was discarded because the naive parser tried whole-stdout then
    single-line parsing, neither of which handles banner-prefixed multi-line
    pretty JSON)."""
    stdout = (
        "[kermt] image 'kermt:latest' already present (sha256:abc123)\n"
        "\n==========\n== CUDA ==\n==========\n\n"
        "Some NVIDIA license banner text.\n\n"
        '{\n  "ok": true,\n  "model_type": "hybrid",\n  "nested": {"a": 1}\n}\n'
    )
    proc = subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")
    result = _parse_json_stdout(proc, context="test")
    assert result == {"ok": True, "model_type": "hybrid", "nested": {"a": 1}}


def test_parse_json_stdout_raises_when_no_json_present():
    proc = subprocess.CompletedProcess(args=[], returncode=1, stdout="no json here\n", stderr="boom")
    with pytest.raises(RuntimeError, match="expected JSON on stdout"):
        _parse_json_stdout(proc, context="test")


def _fake_completed(stdout="", returncode=0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def test_fit_resolves_checkpoint_via_host_run_dir_not_container_path(tmp_path, monkeypatch):
    """Regression test: run_finetune_local.py's run.json records
    save_dir="/runs/ckpt" (a CONTAINER path, since we pass --out /runs) — the
    wrapper must translate that back to the HOST path under run_dir rather
    than treating the container string as a host Path. Caught live during
    the 2026-09-18 AMES smoke test (attempt 3): finetune had actually
    succeeded but the wrapper raised "expected finetuned checkpoint not
    found at /runs/ckpt/fold_0/model_0/model.pt" (a container path that
    doesn't exist on the host)."""
    m = _model(tmp_path, monkeypatch, task_type=TaskType.CLASSIFICATION)
    run_dir = tmp_path / "run"

    ok_checkpoint_json = json.dumps({"ok": True, "errors": []})

    def fake_run_container(kermt_repo, image, *, data=None, ckpt=None, run_dir=None, command):
        if "check_checkpoint.py" in command:
            return _fake_completed(ok_checkpoint_json)
        if "prepare_data.py" in command:
            (run_dir / "data").mkdir(parents=True, exist_ok=True)
            (run_dir / "data" / "prepare_data.json").write_text("{}")
            return _fake_completed("{}")
        if "run_finetune_local.py" in command:
            ckpt_dir = run_dir / "ckpt" / "fold_0" / "model_0"
            ckpt_dir.mkdir(parents=True, exist_ok=True)
            (ckpt_dir / "model.pt").write_bytes(b"fake finetuned weights")
            (run_dir / "run.json").write_text(
                json.dumps({"status": "ok", "save_dir": "/runs/ckpt"})
            )
            return _fake_completed("{}")
        raise AssertionError(f"unexpected command: {command}")

    import models.kermt_model as km

    monkeypatch.setattr(km, "_run_container", fake_run_container)

    m.fit(
        ["CCO", "CCN"], np.array([1.0, 0.0]),
        X_val=["c1ccccc1"], y_val=np.array([1.0]),
        run_dir=run_dir,
    )
    assert m.is_fitted
    assert m._finetuned_checkpoint == run_dir / "ckpt" / "fold_0" / "model_0" / "model.pt"
    assert m._finetuned_checkpoint.read_bytes() == b"fake finetuned weights"


def test_predict_resolves_output_csv_via_host_run_dir_not_container_path(tmp_path, monkeypatch):
    """Same container-vs-host path bug as the fit() test above, for
    run_inference.py's output_csv="/runs/out/predictions.csv"."""
    m = _model(tmp_path, monkeypatch, task_type=TaskType.REGRESSION, targets=["solubility_logs"])
    m._finetuned_checkpoint = tmp_path / "finetuned.pt"
    m._finetuned_checkpoint.write_bytes(b"pretend")
    m._work_dir = tmp_path / "fit_run"

    ok_checkpoint_json = json.dumps({"ok": True, "errors": []})

    def fake_run_container(kermt_repo, image, *, data=None, ckpt=None, run_dir=None, command):
        if "check_checkpoint.py" in command:
            return _fake_completed(ok_checkpoint_json)
        if "prepare_data.py" in command:
            (run_dir / "data").mkdir(parents=True, exist_ok=True)
            (run_dir / "data" / "prepare_data.json").write_text("{}")
            return _fake_completed("{}")
        if "run_inference.py" in command:
            out_dir = run_dir / "out"
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "predictions.csv").write_text("smiles,solubility_logs\nCCO,-0.5\n")
            (run_dir / "run.json").write_text(
                json.dumps({"status": "ok", "output_csv": "/runs/out/predictions.csv"})
            )
            return _fake_completed("{}")
        raise AssertionError(f"unexpected command: {command}")

    import models.kermt_model as km

    monkeypatch.setattr(km, "_run_container", fake_run_container)

    preds = m.predict(["CCO"], run_dir=tmp_path / "predict_run")
    np.testing.assert_allclose(preds, [-0.5])


def test_save_and_load_metadata_roundtrip(tmp_path, monkeypatch):
    m = _model(tmp_path, monkeypatch, task_type=TaskType.REGRESSION, targets=["solubility_logs"])
    fake_finetuned = tmp_path / "finetuned.pt"
    fake_finetuned.write_bytes(b"pretend finetuned weights")
    m._finetuned_checkpoint = fake_finetuned

    save_dir = tmp_path / "saved"
    m.save(save_dir)
    assert (save_dir / "model.pt").exists()
    assert (save_dir / "metadata.json").exists()

    reloaded = KermtModel.load(save_dir)
    assert reloaded.model_id == "mars-kermt-single-v1"
    assert reloaded.task_type == TaskType.REGRESSION
    assert reloaded.is_fitted
    assert reloaded._target_names == ["solubility_logs"]


# ---------------------------------------------------------------------------- #
# Endpoint-homogeneity guard (added 2026-09-20 — the module docstring had
# claimed this existed since the wrapper was written, but it did not)
# ---------------------------------------------------------------------------- #


def test_mixed_task_type_targets_are_rejected(tmp_path, monkeypatch):
    """The core blocker: one --dataset_type cannot serve both column types.

    Without this guard the regression column comes back squashed through a
    sigmoid — a plausible-looking wrong number rather than an error.
    """
    with pytest.raises(ValueError, match="mixed classification/regression"):
        _model(
            tmp_path,
            monkeypatch,
            task_type=TaskType.CLASSIFICATION,
            targets=["cyp3a4_inhibition", "clearance_microsomal"],
        )


def test_declared_task_type_must_match_the_endpoints(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="was declared but targets"):
        _model(
            tmp_path,
            monkeypatch,
            task_type=TaskType.REGRESSION,
            targets=["ames_mutagenicity"],
        )


def test_homogeneous_multitask_targets_are_accepted(tmp_path, monkeypatch):
    m = _model(
        tmp_path,
        monkeypatch,
        task_type=TaskType.CLASSIFICATION,
        targets=["herg_cardiotoxicity", "ames_mutagenicity"],
    )
    assert m.model_id == "mars-kermt-multitask-v1"


def test_unresolvable_target_names_are_tolerated(tmp_path, monkeypatch):
    """Tier-2 ordinal columns (`solubility_logs__gt0`) carry no endpoint metadata.

    They are binary by construction, so the guard must not reject them.
    """
    m = _model(
        tmp_path,
        monkeypatch,
        task_type=TaskType.CLASSIFICATION,
        targets=["solubility_logs__gt0", "solubility_logs__gt1"],
    )
    assert m.target_names == ["solubility_logs__gt0", "solubility_logs__gt1"]


# ---------------------------------------------------------------------------- #
# target_names / target_task_types / supports_loss_weighting
# ---------------------------------------------------------------------------- #


def test_target_properties(tmp_path, monkeypatch):
    m = _model(
        tmp_path,
        monkeypatch,
        task_type=TaskType.CLASSIFICATION,
        targets=["herg_cardiotoxicity", "ames_mutagenicity"],
    )
    assert m.target_names == ["herg_cardiotoxicity", "ames_mutagenicity"]
    assert m.target_task_types == {
        "herg_cardiotoxicity": TaskType.CLASSIFICATION,
        "ames_mutagenicity": TaskType.CLASSIFICATION,
    }
    # Mutating the returned list must not corrupt the model's own state.
    m.target_names.append("bogus")
    assert len(m.target_names) == 2


def test_stock_path_declares_it_cannot_do_loss_weighting(tmp_path, monkeypatch):
    """run_finetune_local.py never forwards --use_mtl_loss and parses strictly.

    So this path is equal-weighting only; Kendall/GradNorm come from Tier 1.
    See documentation/AIMS/decisions.md (2026-09-20, finding 2).
    """
    m = _model(tmp_path, monkeypatch)
    assert m.supports_loss_weighting is False


def test_no_mtl_loss_flag_is_ever_emitted(tmp_path, monkeypatch):
    """Emitting it would be an unrecognized-argument hard failure, exit 2."""
    m = _model(tmp_path, monkeypatch)
    m._cfg = KermtConfig(epochs=3, batch_size=16)
    flags = m._hyperparam_flags()
    assert "mtl" not in flags


# ---------------------------------------------------------------------------- #
# predict_logits — unblocks temperature scaling for every KERMT clf run
# ---------------------------------------------------------------------------- #


def test_predict_logits_inverts_the_served_probability(tmp_path, monkeypatch):
    m = _model(tmp_path, monkeypatch, task_type=TaskType.CLASSIFICATION)
    monkeypatch.setattr(
        KermtModel, "predict", lambda self, X, run_dir=None: np.array([0.5, 0.7310586])
    )
    out = m.predict_logits(["CCO", "CCC"])
    assert out[0] == pytest.approx(0.0, abs=1e-9)
    assert out[1] == pytest.approx(1.0, abs=1e-5)


def test_predict_logits_is_monotone_so_ranking_metrics_are_unchanged(tmp_path, monkeypatch):
    m = _model(tmp_path, monkeypatch, task_type=TaskType.CLASSIFICATION)
    probs = np.array([0.01, 0.2, 0.5, 0.85, 0.99])
    monkeypatch.setattr(KermtModel, "predict", lambda self, X, run_dir=None: probs)
    out = m.predict_logits(["a", "b", "c", "d", "e"])
    assert np.all(np.diff(out) > 0)


def test_predict_logits_clips_saturated_probabilities(tmp_path, monkeypatch):
    """0.0/1.0 in the CSV is decimal rounding, not infinite confidence."""
    m = _model(tmp_path, monkeypatch, task_type=TaskType.CLASSIFICATION)
    monkeypatch.setattr(
        KermtModel, "predict", lambda self, X, run_dir=None: np.array([0.0, 1.0])
    )
    out = m.predict_logits(["a", "b"])
    assert np.isfinite(out).all()
    assert out[0] < 0 < out[1]


def test_predict_logits_rejects_regression_models(tmp_path, monkeypatch):
    m = _model(
        tmp_path, monkeypatch, task_type=TaskType.REGRESSION, targets=["solubility_logs"]
    )
    with pytest.raises(ValueError, match="classification-only"):
        m.predict_logits(["CCO"])
