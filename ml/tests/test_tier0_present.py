"""Tests for ml/eval/tier0_present.py — the aggregate presenter refuses inputs it cannot present correctly.

Synthetic five-seed fixture; matplotlib is required by the module itself, so the file is skipped where it is absent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("matplotlib")

import numpy as np  # noqa: E402
from eval import tier0_present  # noqa: E402
from eval.cluster_calibration import (  # noqa: E402
    aggregate_calibration_across_seeds,
    aggregate_test_metrics_across_seeds,
)
from eval.kermt_log import resolve_saved_epoch  # noqa: E402

EP = "some_endpoint"
PEAK_EPOCH, LOGGED_EPOCH = 18, 29


def _log(seed: int) -> str:
    lines = [
        f"Epoch: {e} loss_train: {1.2 - 0.02 * e:.4f} loss_val: {0.9 - 0.005 * e:.4f} "
        f"auc_val: {0.93 - 0.004 * abs(PEAK_EPOCH - e) + 0.001 * seed:.4f} cur_lr: 0.0001 t_time: 5.0s v_time: 1.0s"
        for e in range(30)
    ]
    lines.append(f"best validation auc = {0.93 + 0.001 * seed:.4f} on epoch {LOGGED_EPOCH}")
    return "\n".join(lines) + "\n"


def _metrics(rng) -> dict:
    return {
        "auroc": float(rng.uniform(0.82, 0.88)),
        "auprc": float(rng.uniform(0.85, 0.92)),
        "brier_score": float(rng.uniform(0.15, 0.22)),
        "ece": float(rng.uniform(0.05, 0.15)),
        "n_samples": 96,
        "n_positive": 50,
        "auroc_valid": True,
    }


def _make_runs(runs_dir: Path, arm: str, seeds=(0, 1, 2, 3, 4), *, resolution: bool = True) -> tuple[list[str], dict]:
    rng = np.random.default_rng(11)
    run_ids, records, summaries = [], [], []
    for seed in seeds:
        rid = f"kermt_st_{arm}_seed{seed}_20260922T0{seed}0000Z"
        run_ids.append(rid)
        raw, cal = _metrics(rng), _metrics(rng)
        cal["auroc"], cal["auprc"] = raw["auroc"], raw["auprc"]
        records.append(
            {
                "endpoint_key": EP, "task_type": "classification", "test_metrics_raw": raw,
                "test_metrics_calibrated": cal, "temperature": 1.0 + 0.1 * seed, "at_boundary": False,
                "optimizer_success": True, "nll_improved": True, "ece_improved": True, "status": "fitted",
            }
        )
        art = runs_dir / rid / "artifacts"
        for sub in ("plots", "metrics", "tables", "kermt/logs"):
            (art / sub).mkdir(parents=True)
        text = _log(seed)
        (art / "kermt" / "logs" / "finetune.log").write_text(text, encoding="utf-8")
        summary = {
            "seed": seed, "run_id": rid, "best_epoch": PEAK_EPOCH, "best_val_auroc": 0.93, "final_val_auroc": 0.91,
            "test_metrics_raw": raw, "test_metrics_calibrated": cal,
            "calibration_metrics": {"temperature": 1.0 + 0.1 * seed, "at_boundary": False, "optimizer_success": True},
            "git_dirty": bool(seed), "wandb_url": f"https://wandb.ai/x/y/runs/{rid}", "wall_seconds": 234.0,
            "overfitting_diagnostics": {"gap": 0.01}, "config": {"epochs": 30},
            "counts": {"train": 100, "val": 20, "calibration": 10, "test": 30},
            "class_balance": {s: {"positive": 5, "negative": 5} for s in ("train", "val", "calibration", "test")},
            "git_sha": "a" * 40, "kermt_source_commit": "e402473", "prep_id": "20260918T090433Z",
            "checkpoint_sha256": "e9e6649b" + "0" * 56,
        }
        if resolution:
            summary["saved_epoch_resolution"] = resolve_saved_epoch(text).to_dict()
        summaries.append(summary)
        (art / "metrics" / "seed_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    aggregate = {
        "subgroup": arm,
        "prep_id": "20260918T090433Z",
        "test_metrics_across_seeds": aggregate_test_metrics_across_seeds(records),
        "calibration_stability_across_seeds": aggregate_calibration_across_seeds(records),
    }
    (runs_dir / f"kermt_tier0_{arm}_aggregate.json").write_text(json.dumps(aggregate), encoding="utf-8")
    return run_ids, {"aggregate": aggregate, "summaries": summaries}


# ---------------------------------------------------------------------------- #
# validate_presentable
# ---------------------------------------------------------------------------- #


@pytest.fixture
def complete(tmp_path):
    _, data = _make_runs(tmp_path, "toy__cls")
    return data["aggregate"], data["summaries"]


def test_complete_single_endpoint_classification_arm_is_accepted(complete):
    aggregate, summaries = complete
    assert tier0_present.validate_presentable(aggregate, summaries) == EP


def test_partial_seed_set_is_refused(complete):
    aggregate, summaries = complete
    with pytest.raises(ValueError, match="fixed seeds"):
        tier0_present.validate_presentable(aggregate, summaries[:4])


def test_multi_endpoint_aggregate_is_refused_not_silently_truncated(complete):
    aggregate, summaries = complete
    aggregate["test_metrics_across_seeds"]["another_endpoint"] = aggregate["test_metrics_across_seeds"][EP]
    with pytest.raises(NotImplementedError, match="single-endpoint"):
        tier0_present.validate_presentable(aggregate, summaries)


def test_regression_arm_is_refused(complete):
    aggregate, summaries = complete
    aggregate["test_metrics_across_seeds"][EP]["task_type"] = "regression"
    with pytest.raises(NotImplementedError, match="classification-only"):
        tier0_present.validate_presentable(aggregate, summaries)


def test_undefined_std_in_the_aggregate_is_refused(complete):
    aggregate, summaries = complete
    aggregate["test_metrics_across_seeds"][EP]["raw"]["auroc_std"] = None
    with pytest.raises(ValueError, match="complete 5-seed mean"):
        tier0_present.validate_presentable(aggregate, summaries)


def test_missing_calibrated_aggregate_is_refused(complete):
    aggregate, summaries = complete
    aggregate["test_metrics_across_seeds"][EP]["calibrated"] = None
    with pytest.raises(ValueError, match="raw or calibrated"):
        tier0_present.validate_presentable(aggregate, summaries)


def test_old_seed_summaries_without_a_saved_epoch_resolution_are_refused(tmp_path):
    _, data = _make_runs(tmp_path, "toy__cls", resolution=False)
    with pytest.raises(ValueError, match="saved_epoch_resolution"):
        tier0_present.validate_presentable(data["aggregate"], data["summaries"])


def test_saved_epoch_inconsistent_with_the_logged_score_is_refused(complete):
    aggregate, summaries = complete
    summaries[2]["saved_epoch_resolution"]["consistent_with_logged_best_score"] = False
    with pytest.raises(ValueError, match="seed 2"):
        tier0_present.validate_presentable(aggregate, summaries)


# ---------------------------------------------------------------------------- #
# present() end to end
# ---------------------------------------------------------------------------- #


def test_present_for_a_non_dili_arm_carries_no_dili_specific_claims(tmp_path, monkeypatch):
    monkeypatch.setattr(tier0_present, "RUNS_DIR", tmp_path)
    run_ids, _ = _make_runs(tmp_path, "toy__cls")
    out = tier0_present.present("toy__cls", run_ids, "pkg")
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert readme.startswith("# Tier-0 KERMT — toy__cls / some_endpoint")
    assert "DILI" not in readme
    assert "seed 0 was recorded clean" not in readme
    assert "Expected per the runbook: train 287" not in readme
    assert "pkg/" in readme  # directory guide names the real output directory
    # saved epoch is what is reported, with KERMT's own (misleading) logged epoch alongside for audit
    assert f"saved epoch {PEAK_EPOCH}; KERMT's own log names epoch {LOGGED_EPOCH}" in readme
    assert (out / "tables" / "summary_metrics.json").exists() and (out / "plots" / "10_best_epoch_by_seed.png").exists()


def test_present_for_the_dili_arm_keeps_the_dili_specific_notes(tmp_path, monkeypatch):
    monkeypatch.setattr(tier0_present, "RUNS_DIR", tmp_path)
    arm = tier0_present.DILI_ARM
    run_ids, _ = _make_runs(tmp_path, arm)
    readme = (tier0_present.present(arm, run_ids, "pkg") / "README.md").read_text(encoding="utf-8")
    assert "seed 0 was recorded clean" in readme
    assert "Expected per the runbook: train 287" in readme


def test_present_refuses_a_partial_arm_before_writing_anything(tmp_path, monkeypatch):
    monkeypatch.setattr(tier0_present, "RUNS_DIR", tmp_path)
    run_ids, _ = _make_runs(tmp_path, "toy__cls", seeds=(0, 1, 2))
    with pytest.raises(ValueError, match="fixed seeds"):
        tier0_present.present("toy__cls", run_ids, "pkg")
    assert not (tmp_path / "pkg").exists()
