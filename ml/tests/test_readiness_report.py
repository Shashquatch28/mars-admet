"""
Tests for train/readiness_report.py.

The point of these tests is the report's own honesty: it must NOT pass merely because a
file exists, must keep smoke-test blockers separate from comparison concerns, must never
claim a workstation fact from a laptop, and must never leak a credential.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from train import readiness_report as rr
from train.readiness_report import (
    BLOCKED,
    FAIL,
    GATE_COMPARISON,
    GATE_INFO,
    GATE_SMOKE,
    NOT_EVALUATED,
    PASS,
    READY,
    SCOPE_CPU,
    WARN,
    CheckResult,
    ReadinessContext,
    summarize,
)

_ML = Path(__file__).resolve().parents[1]
_HAVE_DATA = (_ML / "data" / "processed" / rr.DEFAULT_PREP_ID / "manifest.json").exists()


def _ctx(tmp_path: Path, target: str = "laptop", **kw) -> ReadinessContext:
    ml = tmp_path / "ml"
    (ml / "data" / "metadata").mkdir(parents=True, exist_ok=True)
    return ReadinessContext(repo_root=tmp_path, ml_root=ml, target=target, **kw)


def _res(id_, gate, status, scope=SCOPE_CPU, blocker=None):
    return CheckResult(id_, "Cat", id_, gate, scope, status, "ev", blocker)


# ---------------------------------------------------------------------------- #
# Verdict logic
# ---------------------------------------------------------------------------- #


def test_a_failing_smoke_check_blocks_and_is_named(tmp_path):
    rep = summarize([_res("a", GATE_SMOKE, PASS), _res("b", GATE_SMOKE, FAIL, blocker="boom")], _ctx(tmp_path))
    assert rep["verdict"] == BLOCKED
    assert rep["smoke_test_blockers"] == ["b: boom"]


def test_all_smoke_checks_passing_is_ready(tmp_path):
    rep = summarize([_res("a", GATE_SMOKE, PASS), _res("b", GATE_SMOKE, WARN)], _ctx(tmp_path))
    assert rep["verdict"] == READY == "READY_FOR_GPU_SMOKE_TEST"
    assert rep["smoke_test_blockers"] == []


def test_warnings_never_block(tmp_path):
    rep = summarize([_res(str(i), GATE_SMOKE, WARN) for i in range(5)], _ctx(tmp_path))
    assert rep["verdict"] == READY


def test_comparison_failures_are_reported_separately_and_do_not_block_the_smoke_test(tmp_path):
    rep = summarize(
        [_res("smoke_ok", GATE_SMOKE, PASS), _res("cmp", GATE_COMPARISON, FAIL, blocker="no test eval")],
        _ctx(tmp_path),
    )
    assert rep["verdict"] == READY
    assert rep["smoke_test_blockers"] == []
    assert rep["comparison_blockers"] == ["[FAIL] cmp: no test eval"]


def test_info_checks_never_gate_even_when_failing(tmp_path):
    rep = summarize([_res("i", GATE_INFO, FAIL), _res("s", GATE_SMOKE, PASS)], _ctx(tmp_path))
    assert rep["verdict"] == READY and rep["smoke_test_blockers"] == []


def test_laptop_verdict_states_its_limited_scope_and_lists_pending_workstation_checks(tmp_path):
    rep = summarize(
        [_res("ok", GATE_SMOKE, PASS), _res("gpu", GATE_SMOKE, NOT_EVALUATED, scope="workstation")],
        _ctx(tmp_path, "laptop"),
    )
    assert rep["verdict"] == READY
    assert rep["pending_on_workstation"] == ["gpu"]
    assert "CPU-side only" in rep["verdict_scope"] and "NOT_EVALUATED" in rep["verdict_scope"]


def test_workstation_target_scope_claims_full_evaluation(tmp_path):
    rep = summarize([_res("ok", GATE_SMOKE, PASS)], _ctx(tmp_path, "workstation"))
    assert rep["target"] == "workstation" and "workstation" in rep["verdict_scope"]
    assert "CPU-side only" not in rep["verdict_scope"]


def test_a_crashing_check_is_a_failure_with_its_exception_not_a_silent_skip():
    res = rr._guard("x.y", "Cat", "t", GATE_SMOKE, SCOPE_CPU, lambda: 1 / 0)
    assert res.status == FAIL and "ZeroDivisionError" in res.evidence and res.blocker


def test_every_registered_check_declares_a_valid_gate_scope_and_category(tmp_path):
    assert len(rr._REGISTRY) >= 20
    ctx = _ctx(tmp_path)
    for fn in rr._REGISTRY:
        r = fn(ctx)  # against an empty tree: must return a CheckResult, never raise
        assert r.gate in (GATE_SMOKE, GATE_COMPARISON, GATE_INFO)
        assert r.scope in (SCOPE_CPU, "workstation")
        assert r.status in (PASS, WARN, FAIL, NOT_EVALUATED)
        assert r.category and r.evidence


# ---------------------------------------------------------------------------- #
# Substance, not existence
# ---------------------------------------------------------------------------- #


def _synthetic_prep(ctx: ReadinessContext, tamper: bool = False) -> None:
    import hashlib

    ds = ctx.prep_dir / "ames_mutagenicity"
    ds.mkdir(parents=True)
    files = {}
    for name, body in (("train_val", "a,b\n1,2\n"), ("test", "a,b\n3,4\n"), ("calibration", "a,b\n5,6\n")):
        (ds / f"{name}.csv").write_bytes(body.encode())
        files[name] = {"sha256": hashlib.sha256(body.encode()).hexdigest()}
    if tamper:
        (ds / "test.csv").write_text("a,b\n9,9\n")  # exists, but is no longer what was recorded
    (ctx.prep_dir / "manifest.json").write_text(json.dumps({
        "prep_id": ctx.prep_id, "acquisition_id": "acq1",
        "datasets": {"ames_mutagenicity": {"provenance": {"files": files, "acq_snapshot_sha256": "d1"}}},
    }))


def test_manifest_integrity_passes_only_when_bytes_match(tmp_path):
    ok = _ctx(tmp_path / "ok")
    _synthetic_prep(ok)
    assert rr.data_manifest_integrity(ok).status == PASS

    bad = _ctx(tmp_path / "bad")
    _synthetic_prep(bad, tamper=True)
    r = rr.data_manifest_integrity(bad)
    assert r.status == FAIL and "ames_mutagenicity/test" in r.evidence  # the file EXISTS, still fails


def _write_lock(path: Path, acq: str, digest: str) -> None:
    path.write_text(json.dumps({"acquisition": {"acq_id": acq},
                                "datasets": {"ames_mutagenicity": {"snapshot_sha256": digest}}}))


def test_lockfile_consistency_states(tmp_path):
    # tracked lockfile IS the snapshot's acquisition and digests agree -> PASS
    a = _ctx(tmp_path / "a")
    _synthetic_prep(a)
    _write_lock(a.ml_root / "data" / "metadata" / "datasets.lock.json", "acq1", "d1")
    assert rr.data_lockfile_consistency(a).status == PASS

    # tracked lockfile is a different acquisition, history file matches -> WARN (not silent)
    b = _ctx(tmp_path / "b")
    _synthetic_prep(b)
    meta = b.ml_root / "data" / "metadata"
    _write_lock(meta / "datasets.lock.json", "acq2", "d1")
    (meta / "history").mkdir()
    _write_lock(meta / "history" / "datasets.lock.acq1.json", "acq1", "d1")
    assert rr.data_lockfile_consistency(b).status == WARN

    # digest disagrees -> FAIL
    c = _ctx(tmp_path / "c")
    _synthetic_prep(c)
    _write_lock(c.ml_root / "data" / "metadata" / "datasets.lock.json", "acq1", "DIFFERENT")
    assert rr.data_lockfile_consistency(c).status == FAIL

    # no lockfile describes the snapshot at all -> FAIL
    d = _ctx(tmp_path / "d")
    _synthetic_prep(d)
    _write_lock(d.ml_root / "data" / "metadata" / "datasets.lock.json", "acq2", "d1")
    assert rr.data_lockfile_consistency(d).status == FAIL


def _write_checkpoint_lock(ml: Path, sha: str = "a" * 64, verified: bool = True) -> None:
    files = {f: {"sha256": sha} for f in (
        "kermt_contrastive_v2.0.pt", "pretrain_atom_vocab.json", "pretrain_bond_vocab.json",
        "pretrain_smiles_vocab.pkl")}
    (ml / "data" / "metadata" / "kermt_checkpoint.lock.json").write_text(json.dumps({
        "model": {"huggingface_repo": "nvidia/x", "huggingface_repo_sha": "b" * 40, "source_code_tag": "v2.0.0",
                  "source_code_commit": "c" * 40, "architecture": {"variant": "contrastive"}},
        "files": files, "local_path": "ml/data/checkpoints/kermt/x/",
        "verification_status": {"loaded_with_official_kermt_code": verified},
    }))


def test_checkpoint_lock_requires_real_hashes_and_a_verification_record(tmp_path):
    ctx = _ctx(tmp_path)
    _write_checkpoint_lock(ctx.ml_root)
    assert rr.model_checkpoint_lock(ctx).status == PASS

    _write_checkpoint_lock(ctx.ml_root, sha="")  # lockfile exists, hashes empty
    assert rr.model_checkpoint_lock(ctx).status == FAIL

    _write_checkpoint_lock(ctx.ml_root, verified=False)  # hashes fine, never actually loaded
    r = rr.model_checkpoint_lock(ctx)
    assert r.status == FAIL and "loaded_with_official_kermt_code" in r.blocker


# ---------------------------------------------------------------------------- #
# Workstation scope
# ---------------------------------------------------------------------------- #


@pytest.mark.parametrize("fn", [rr.model_checkpoint_binary, rr.model_kermt_source,
                                rr.env_docker_image, rr.env_gpu])
def test_workstation_facts_are_never_claimed_from_the_laptop(fn, tmp_path):
    r = fn(_ctx(tmp_path, "laptop"))
    assert r.status == NOT_EVALUATED and r.scope == "workstation"


def test_workstation_target_fails_loudly_when_the_tools_are_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(rr, "_run", lambda cmd, timeout=25: (127, "not found"))
    monkeypatch.delenv("MARS_KERMT_REPO", raising=False)
    ctx = _ctx(tmp_path, "workstation")
    assert rr.env_docker_image(ctx).status == FAIL
    assert rr.env_gpu(ctx).status == FAIL
    assert rr.model_kermt_source(ctx).status == FAIL
    _write_checkpoint_lock(ctx.ml_root)
    assert rr.model_checkpoint_binary(ctx).status == FAIL  # binary not on disk


def test_gpu_check_enforces_the_documented_vram_floor(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, "workstation")
    monkeypatch.setattr(rr, "_run", lambda cmd, timeout=25: (0, "NVIDIA RTX A4000, 16376, 580.173.02\n"))
    assert rr.env_gpu(ctx).status == PASS
    monkeypatch.setattr(rr, "_run", lambda cmd, timeout=25: (0, "Tiny GPU, 4096, 580.0\n"))
    r = rr.env_gpu(ctx)
    assert r.status == FAIL and "8192" in r.blocker


def test_docker_image_identity_is_recorded_but_flagged_unpinned(tmp_path, monkeypatch):
    monkeypatch.setattr(rr, "_run", lambda cmd, timeout=25: (0, "sha256:" + "d" * 64 + "\n"))
    unpinned = rr.env_docker_image(_ctx(tmp_path, "workstation"))
    assert unpinned.status == WARN and "No pinned expected image id" in unpinned.evidence

    pinned_ok = rr.env_docker_image(_ctx(tmp_path, "workstation", expected_image_id="sha256:" + "d" * 64))
    assert pinned_ok.status == PASS
    pinned_bad = rr.env_docker_image(_ctx(tmp_path, "workstation", expected_image_id="sha256:" + "e" * 64))
    assert pinned_bad.status == FAIL


def test_checkpoint_binary_hash_is_verified_when_present(tmp_path):
    import hashlib

    ctx = _ctx(tmp_path, "workstation")
    body = b"pretend checkpoint"
    _write_checkpoint_lock(ctx.ml_root, sha=hashlib.sha256(body).hexdigest())
    ck = ctx.ml_root / "data" / "checkpoints" / "kermt" / "x"
    ck.mkdir(parents=True)
    (ck / "kermt_contrastive_v2.0.pt").write_bytes(body)
    assert rr.model_checkpoint_binary(ctx).status == PASS
    (ck / "kermt_contrastive_v2.0.pt").write_bytes(b"tampered")
    assert rr.model_checkpoint_binary(ctx).status == FAIL


# ---------------------------------------------------------------------------- #
# Credentials, W&B, provenance
# ---------------------------------------------------------------------------- #


def test_wandb_check_never_leaks_a_credential_value(tmp_path):
    ctx = _ctx(tmp_path)
    (tmp_path / ".env").write_text("WANDB_API_KEY=SUPERSECRET123\nWANDB_PROJECT=proj\nWANDB_ENTITY=ent\n")
    r = rr.tracking_wandb(ctx)
    blob = json.dumps(r.__dict__)
    assert "SUPERSECRET123" not in blob
    assert "project=proj" in r.evidence and "api_key_in_env=True" in r.evidence


def test_wandb_problems_warn_but_do_not_block(tmp_path):
    r = rr.tracking_wandb(_ctx(tmp_path))  # no .env at all
    assert r.gate == GATE_INFO and r.status in (WARN, PASS)


def test_run_naming_and_provenance_checks_exercise_the_real_code(tmp_path):
    ctx = ReadinessContext(repo_root=_ML.parent, ml_root=_ML)
    assert rr.tracking_run_naming(ctx).status == PASS
    r = rr.tracking_provenance(ctx)
    assert r.status == PASS and "config.json round-trips" in r.evidence


def test_seed_and_rng_check_runs_a_real_round_trip():
    r = rr.repro_seed_and_rng(ReadinessContext(repo_root=_ML.parent, ml_root=_ML))
    assert r.status == PASS and "reproduces continuation=True" in r.evidence


def test_calibration_microrun_executes_the_real_code_path():
    r = rr.eval_calibration_microrun(ReadinessContext(repo_root=_ML.parent, ml_root=_ML))
    assert r.status == PASS and "Synthetic input" in r.evidence


def test_readiness_says_rng_is_not_yet_integrated_into_training(tmp_path):
    ctx = ReadinessContext(repo_root=_ML.parent, ml_root=_ML)
    r = rr.repro_gaps(ctx)
    assert r.gate == GATE_INFO and "NOT ESTABLISHED" in r.evidence  # CUDA determinism


# ---------------------------------------------------------------------------- #
# Held-out evaluation presence is judged by content
# ---------------------------------------------------------------------------- #


def test_heldout_check_requires_14_complete_test_split_reports(tmp_path):
    ctx = _ctx(tmp_path)
    assert rr.eval_xgboost_heldout(ctx).status == FAIL  # nothing there

    d = ctx.ml_root / "runs" / "test_evaluations"
    d.mkdir(parents=True)
    eps = [f"ep{i}" for i in range(14)]
    for ep in eps:
        (d / f"{ep}.json").write_text(json.dumps({"split": "test", "seeds": [0, 1, 2, 3, 4]}))
    (d / "summary.json").write_text(json.dumps({"evaluated": eps, "blocked": {}}))
    assert rr.eval_xgboost_heldout(ctx).status == PASS

    (d / "ep3.json").write_text(json.dumps({"split": "validation", "seeds": [0, 1, 2, 3, 4]}))
    r = rr.eval_xgboost_heldout(ctx)
    assert r.status == FAIL and "ep3" in r.evidence  # a validation report is not a test report

    (d / "summary.json").write_text(json.dumps({"evaluated": eps[:13], "blocked": {"ep13": "x"}}))
    assert rr.eval_xgboost_heldout(ctx).status == FAIL


# ---------------------------------------------------------------------------- #
# End to end on the real repository
# ---------------------------------------------------------------------------- #


@pytest.mark.skipif(not _HAVE_DATA, reason="canonical processed snapshot not present")
def test_full_report_on_the_real_repository_is_serializable_and_complete():
    ctx = ReadinessContext(repo_root=_ML.parent, ml_root=_ML)
    rep = rr.build_readiness_report(ctx)
    json.dumps(rep)
    assert rep["verdict"] in (READY, BLOCKED)
    assert {c["category"] for c in rep["checks"]} == {
        "Data", "Model", "Environment", "Tracking", "Evaluation", "Reproducibility"}
    assert rep["counts"][NOT_EVALUATED] == 4  # the four workstation-only facts
    rendered = rr.render(rep)
    assert rep["verdict"] in rendered.splitlines()[0]
