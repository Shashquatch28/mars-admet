import json

import pytest

from train.kermt_mixed.tuning import Axis, Protocol, ProtocolError, preregister
from train.run_tuning import finalize, load_protocol, plan, run_all


def _proto(**kw):
    base = dict(
        name="t", cluster="metabolism", arm="fixed_task",
        space=(Axis("epochs", "choice", values=(5, 10, 15)), Axis("max_lr", "loguniform", low=1e-5, high=1e-3)),
        reference={"epochs": 10, "max_lr": 1e-4}, n_trials=4, sampling_seed=1, tuning_seeds=(0, 1),
        objective="val_selection_loss", lower_is_better=True, min_improvement_in_stds=2.0, notes="test",
    )
    base.update(kw)
    return Protocol(**base)


def _reg(tmp_path, proto):
    path = tmp_path / "reg.json"
    preregister(proto, path)
    return path


def test_roundtrip_registration(tmp_path):
    p = _proto()
    assert load_protocol(_reg(tmp_path, p)).sha256() == p.sha256()


def test_edited_registration_is_refused(tmp_path):
    path = _reg(tmp_path, _proto())
    doc = json.loads(path.read_text())
    doc["protocol"]["n_trials"] = 5
    path.write_text(json.dumps(doc))
    with pytest.raises(ProtocolError):
        load_protocol(path)


def test_plan_counts_runs():
    r = plan(_proto(), 1.1)
    assert r["runs"] == 8 and r["gpu_hours_estimate"] == 8.8


def test_run_finalize_and_no_rerun(tmp_path):
    p = _proto()
    calls = []

    def runner(trial, seed, tag, cfg, mixed):
        calls.append((trial, seed))
        assert tag.startswith("tuning:") and mixed == {}
        return {"objective": 1.0 + 0.01 * seed - (0.5 if trial == 2 else 0.0)}

    res = tmp_path / "res"
    assert run_all(p, res, runner, max_runs=3) == 3
    with pytest.raises(ProtocolError):
        finalize(p, res)  # partial
    assert run_all(p, res, runner) == 5
    assert len(calls) == 8 and len(set(calls)) == 8
    out = finalize(p, res)
    assert out["chosen_trial"] == 2 and out["moved_off_reference"]
    assert (res / "selection.json").exists()


def test_crashed_run_blocks(tmp_path):
    p = _proto()
    res = tmp_path / "res"

    def boom(*a):
        raise RuntimeError("gpu fell over")

    with pytest.raises(RuntimeError):
        run_all(p, res, boom)
    with pytest.raises(ProtocolError, match="crashed"):
        run_all(p, res, lambda *a: {"objective": 1.0})
