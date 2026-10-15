"""
GPU-session readiness report.

Answers one question honestly: *can the first GPU smoke test be run, and if not, exactly
what blocks it?* Output verdict is binary - ``READY_FOR_GPU_SMOKE_TEST`` or ``BLOCKED`` -
with every blocker listed.

Principles
----------
* **Substance, not existence.** A check passes only if it *exercised* the thing: hashes
  re-computed against a manifest, a cluster actually loaded and its leakage measured, a
  calibration micro-run actually executed, an RNG state actually round-tripped. A file
  merely being present never counts.
* **Gates are explicit.** Each check declares what it gates:
    ``smoke``       - a FAIL blocks the GPU smoke test  -> verdict BLOCKED
    ``comparison``  - a FAIL/WARN blocks the KERMT-vs-XGBoost *comparison*, not the smoke
                      test; reported separately so it neither over-blocks nor hides
    ``info``        - recorded, never gating
* **Scope is explicit.** ``cpu`` checks run anywhere. ``workstation`` checks (Docker
  image, GPU, checkpoint binary, KERMT checkout) can only be true on the GPU machine:
  with ``--target laptop`` they are reported ``NOT_EVALUATED`` and listed as pending; with
  ``--target workstation`` they are evaluated for real and can block.
  A laptop ``READY_FOR_GPU_SMOKE_TEST`` therefore means "CPU-side prerequisites are
  satisfied" - the report says so in its header, and lists what the workstation must
  still confirm. It never claims more.

Statuses: PASS, WARN (does not gate), FAIL, NOT_EVALUATED.

Usage
-----
    cd ml && PYTHONPATH=. python train/readiness_report.py
    cd ml && PYTHONPATH=. python train/readiness_report.py --target workstation
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

PASS, WARN, FAIL, NOT_EVALUATED = "PASS", "WARN", "FAIL", "NOT_EVALUATED"
GATE_SMOKE, GATE_COMPARISON, GATE_INFO = "smoke", "comparison", "info"
SCOPE_CPU, SCOPE_WORKSTATION = "cpu", "workstation"

READY = "READY_FOR_GPU_SMOKE_TEST"
BLOCKED = "BLOCKED"

DEFAULT_PREP_ID = "20260830T200000Z"
DEFAULT_SMOKE_SUBGROUP = "dili_standalone__cls"
EXPECTED_SEEDS = (0, 1, 2, 3, 4)
CHECKPOINT_FILE = "kermt_contrastive_v2.0.pt"
# KERMT's documented finetune floor at batch_size 32 (kermt_integration_status.md sec 6).
MIN_GPU_MIB = 8192
BLUEPRINT_CALIBRATION_FLOOR = 50


@dataclass
class CheckResult:
    id: str
    category: str
    title: str
    gate: str
    scope: str
    status: str
    evidence: str
    blocker: str | None = None


@dataclass
class ReadinessContext:
    repo_root: Path
    ml_root: Path
    prep_id: str = DEFAULT_PREP_ID
    smoke_subgroup: str = DEFAULT_SMOKE_SUBGROUP
    target: str = "laptop"  # "laptop" | "workstation"
    expected_image_id: str | None = None
    workstation_fingerprint: Path | None = None

    @property
    def prep_dir(self) -> Path:
        return self.ml_root / "data" / "processed" / self.prep_id

    @property
    def is_workstation(self) -> bool:
        return self.target == "workstation"


_Check = Callable[[ReadinessContext], CheckResult]
_REGISTRY: list[_Check] = []


def check(fn: _Check) -> _Check:
    _REGISTRY.append(fn)
    return fn


def _r(id_: str, cat: str, title: str, gate: str, scope: str, status: str, evidence: str,
       blocker: str | None = None) -> CheckResult:
    return CheckResult(id_, cat, title, gate, scope, status, evidence, blocker)


def _guard(id_: str, cat: str, title: str, gate: str, scope: str, fn: Callable[[], CheckResult]) -> CheckResult:
    """A check that crashes is a FAIL with the exception as evidence - never silently skipped."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - deliberate: report, don't hide
        return _r(id_, cat, title, gate, scope, FAIL, f"check raised {type(exc).__name__}: {exc}",
                  f"{id_} could not be evaluated: {exc}")


def _run(cmd: list[str], timeout: int = 25) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)


def _not_evaluated(id_: str, cat: str, title: str, gate: str, why: str) -> CheckResult:
    return _r(id_, cat, title, gate, SCOPE_WORKSTATION, NOT_EVALUATED, why)


# ============================================================================ #
# DATA
# ============================================================================ #


@check
def data_prep_present(ctx: ReadinessContext) -> CheckResult:
    def go() -> CheckResult:
        from mars_contracts.endpoints import ML_ENDPOINTS

        manifest = ctx.prep_dir / "manifest.json"
        if not manifest.exists():
            return _r("data.prep_present", "Data", "Canonical prepared snapshot present", GATE_SMOKE,
                      SCOPE_CPU, FAIL, f"no manifest at {manifest}", f"prep {ctx.prep_id} missing")
        m = json.loads(manifest.read_text(encoding="utf-8"))
        missing, empty = [], []
        for e in ML_ENDPOINTS:
            for split in ("train_val", "test", "calibration"):
                f = ctx.prep_dir / e.value / f"{split}.csv"
                if not f.exists():
                    missing.append(f"{e.value}/{split}")
                elif f.stat().st_size < 20:
                    empty.append(f"{e.value}/{split}")
        if missing or empty:
            return _r("data.prep_present", "Data", "Canonical prepared snapshot present", GATE_SMOKE,
                      SCOPE_CPU, FAIL, f"missing={missing} empty={empty}",
                      f"{len(missing) + len(empty)} split file(s) missing/empty")
        return _r("data.prep_present", "Data", "Canonical prepared snapshot present", GATE_SMOKE,
                  SCOPE_CPU, PASS,
                  f"prep_id={m.get('prep_id')} acquisition_id={m.get('acquisition_id')} "
                  f"split_version={m.get('split_version')}; all {len(ML_ENDPOINTS)} ML endpoints "
                  "have non-empty train_val/test/calibration")

    return _guard("data.prep_present", "Data", "Canonical prepared snapshot present", GATE_SMOKE, SCOPE_CPU, go)


@check
def data_manifest_integrity(ctx: ReadinessContext) -> CheckResult:
    def go() -> CheckResult:
        from eval.heldout_evaluation import sha256_file

        m = json.loads((ctx.prep_dir / "manifest.json").read_text(encoding="utf-8"))
        n, bad = 0, []
        for ds, entry in m["datasets"].items():
            for name, rec in entry["provenance"].get("files", {}).items():
                f = ctx.prep_dir / ds / f"{name}.csv"
                n += 1
                if not f.exists() or sha256_file(f) != rec["sha256"]:
                    bad.append(f"{ds}/{name}")
        status = FAIL if bad else PASS
        return _r("data.manifest_integrity", "Data", "Split files match their recorded SHA-256", GATE_SMOKE,
                  SCOPE_CPU, status, f"re-hashed {n} files against manifest.json; mismatches={bad}",
                  f"{len(bad)} split file(s) differ from the manifest" if bad else None)

    return _guard("data.manifest_integrity", "Data", "Split files match their recorded SHA-256",
                  GATE_SMOKE, SCOPE_CPU, go)


@check
def data_lockfile_consistency(ctx: ReadinessContext) -> CheckResult:
    def go() -> CheckResult:
        meta = ctx.ml_root / "data" / "metadata"
        m = json.loads((ctx.prep_dir / "manifest.json").read_text(encoding="utf-8"))
        acq = m["acquisition_id"]
        tracked = json.loads((meta / "datasets.lock.json").read_text(encoding="utf-8"))
        tracked_acq = tracked["acquisition"]["acq_id"]
        hist = meta / "history" / f"datasets.lock.{acq}.json"
        lock = tracked if tracked_acq == acq else (
            json.loads(hist.read_text(encoding="utf-8")) if hist.exists() else None)
        if lock is None:
            return _r("data.lockfile_consistency", "Data", "Acquisition lockfile matches the snapshot",
                      GATE_SMOKE, SCOPE_CPU, FAIL,
                      f"snapshot acquisition {acq}; tracked lockfile is {tracked_acq}; no history lockfile",
                      f"no lockfile describes acquisition {acq}")
        mismatched = [
            ds for ds, e in m["datasets"].items()
            if ds in lock["datasets"]
            and e["provenance"].get("acq_snapshot_sha256") != lock["datasets"][ds]["snapshot_sha256"]
        ]
        if mismatched:
            return _r("data.lockfile_consistency", "Data", "Acquisition lockfile matches the snapshot",
                      GATE_SMOKE, SCOPE_CPU, FAIL, f"snapshot digests differ for {mismatched}",
                      "raw-data digests in the manifest disagree with the lockfile")
        if tracked_acq != acq:
            same = sum(
                1 for k, v in tracked["datasets"].items()
                if k in lock["datasets"] and v["snapshot_sha256"] == lock["datasets"][k]["snapshot_sha256"]
            )
            return _r("data.lockfile_consistency", "Data", "Acquisition lockfile matches the snapshot",
                      GATE_SMOKE, SCOPE_CPU, WARN,
                      f"tracked lockfile is acquisition {tracked_acq} (workstation); this snapshot is "
                      f"{acq}, verified against history/. Raw content identical: {same}/"
                      f"{len(tracked['datasets'])} snapshot_sha256 match. 3 of the 5 known "
                      "failures in test_acquisition_lockfile.py fail for this reason (the "
                      "other 2 are stale post-Option-C expectations).")
        return _r("data.lockfile_consistency", "Data", "Acquisition lockfile matches the snapshot",
                  GATE_SMOKE, SCOPE_CPU, PASS, f"acquisition {acq}: all snapshot digests match")

    return _guard("data.lockfile_consistency", "Data", "Acquisition lockfile matches the snapshot",
                  GATE_SMOKE, SCOPE_CPU, go)


@check
def data_cluster_leakage(ctx: ReadinessContext) -> CheckResult:
    def go() -> CheckResult:
        from configs.clusters import all_subgroups
        from data.cluster_loaders import load_cluster

        rows, bad = [], []
        for key, spec in sorted(all_subgroups().items()):
            cd = load_cluster(ctx.prep_dir, list(spec.endpoints), cluster_key=key)
            overlap = cd.split_report.smiles_overlap_count
            pool, _ = cd.train_pool(holdout_calibration=True)
            leaked = set(pool["standardized_smiles"]) & (set(cd.smiles("test")) | cd.calibration_molecules())
            rows.append(f"{key}: smiles_overlap={overlap} pool_vs_test/cal={len(leaked)}")
            if overlap or leaked:
                bad.append(key)
        return _r("data.cluster_leakage", "Data", "Cluster leakage checked on real data", GATE_SMOKE,
                  SCOPE_CPU, FAIL if bad else PASS, "; ".join(rows),
                  f"train pool overlaps test/calibration for {bad}" if bad else None)

    return _guard("data.cluster_leakage", "Data", "Cluster leakage checked on real data", GATE_SMOKE, SCOPE_CPU, go)


@check
def data_calibration_availability(ctx: ReadinessContext) -> CheckResult:
    def go() -> CheckResult:
        from configs.clusters import all_subgroups
        from data.cluster_loaders import load_cluster
        from mars_contracts.endpoints import TaskType

        smoke_ok, notes, warn = True, [], []
        smoke_reason = None
        for key, spec in sorted(all_subgroups().items()):
            if spec.task_type is not TaskType.CLASSIFICATION:
                continue
            cd = load_cluster(ctx.prep_dir, list(spec.endpoints), cluster_key=key)
            for ep in spec.endpoints:
                c = cd.calibration[ep].dropna()
                n, pos = len(c), int(c.sum())
                neg = n - pos
                tag = f"{key}/{ep}: N={n} pos={pos} neg={neg}"
                notes.append(tag)
                usable = n > 0 and pos > 0 and neg > 0
                if key == ctx.smoke_subgroup and not usable:
                    smoke_ok, smoke_reason = False, f"{tag} cannot be temperature-scaled (needs both classes)"
                if usable and n < BLUEPRINT_CALIBRATION_FLOOR:
                    warn.append(f"{ep} N={n} < blueprint floor {BLUEPRINT_CALIBRATION_FLOOR}")
                if usable and min(pos, neg) <= 1:
                    warn.append(f"{ep} has {min(pos, neg)} minority-class example(s)")
        status = FAIL if not smoke_ok else (WARN if warn else PASS)
        ev = "; ".join(notes)
        if warn:
            ev += " || concerns (do not block the smoke test): " + "; ".join(warn)
        return _r("data.calibration_availability", "Data", "Calibration data usable for the smoke endpoint",
                  GATE_SMOKE, SCOPE_CPU, status, ev, smoke_reason)

    return _guard("data.calibration_availability", "Data", "Calibration data usable for the smoke endpoint",
                  GATE_SMOKE, SCOPE_CPU, go)


@check
def data_workstation_identity(ctx: ReadinessContext) -> CheckResult:
    def go() -> CheckResult:
        fp_local = ctx.ml_root / "data" / "metadata" / f"prep_fingerprint.{ctx.prep_id}.json"
        if ctx.workstation_fingerprint is None:
            return _r("data.workstation_identity", "Data",
                      "Workstation processed data identical to canonical", GATE_COMPARISON, SCOPE_WORKSTATION,
                      WARN,
                      "NOT ESTABLISHED. Repository holds no workstation processed data. Raw acquisition is "
                      "byte-identical per lockfile hashes, but processed splits (20260918T090433Z) are "
                      f"unverified. On the workstation: python data/compare_prep.py fingerprint --prep-dir "
                      f"data/processed/<id> --out ws.json, then compare against {fp_local.name}.")
        from data.compare_prep import (
            BYTE_IDENTICAL,
            CONTENT_IDENTICAL,
            MATERIALLY_DIFFERENT,
            compare_fingerprints,
        )

        res = compare_fingerprints(fp_local, ctx.workstation_fingerprint)
        st = {BYTE_IDENTICAL: PASS, CONTENT_IDENTICAL: PASS, MATERIALLY_DIFFERENT: FAIL}.get(res["overall"], WARN)
        return _r("data.workstation_identity", "Data", "Workstation processed data identical to canonical",
                  GATE_COMPARISON, SCOPE_WORKSTATION, st, f"overall={res['overall']} counts={res['counts']}",
                  "workstation data is materially different" if st == FAIL else None)

    return _guard("data.workstation_identity", "Data", "Workstation processed data identical to canonical",
                  GATE_COMPARISON, SCOPE_WORKSTATION, go)


# ============================================================================ #
# MODEL
# ============================================================================ #


@check
def model_checkpoint_lock(ctx: ReadinessContext) -> CheckResult:
    def go() -> CheckResult:
        lock = json.loads((ctx.ml_root / "data" / "metadata" / "kermt_checkpoint.lock.json").read_text("utf-8"))
        files = lock["files"]
        need = (CHECKPOINT_FILE, "pretrain_atom_vocab.json", "pretrain_bond_vocab.json", "pretrain_smiles_vocab.pkl")
        problems = [f for f in need if not files.get(f, {}).get("sha256") or len(files[f]["sha256"]) != 64]
        vs = lock.get("verification_status", {})
        if not vs.get("loaded_with_official_kermt_code"):
            problems.append("verification_status.loaded_with_official_kermt_code is not true")
        for k in ("huggingface_repo_sha", "source_code_commit"):
            if not lock["model"].get(k):
                problems.append(f"model.{k} missing")
        ev = (f"{lock['model']['huggingface_repo']} sha={lock['model']['huggingface_repo_sha'][:12]} "
              f"kermt={lock['model']['source_code_tag']}@{lock['model']['source_code_commit'][:12]} "
              f"ckpt_sha256={files[CHECKPOINT_FILE]['sha256'][:16]}... variant={lock['model']['architecture']['variant'][:40]}")
        return _r("model.checkpoint_lock", "Model", "Checkpoint identity + hashes locked and verified",
                  GATE_SMOKE, SCOPE_CPU, FAIL if problems else PASS, ev,
                  "; ".join(problems) if problems else None)

    return _guard("model.checkpoint_lock", "Model", "Checkpoint identity + hashes locked and verified",
                  GATE_SMOKE, SCOPE_CPU, go)


@check
def model_family_wiring(ctx: ReadinessContext) -> CheckResult:
    def go() -> CheckResult:
        from configs.clusters import all_subgroups
        from mars_contracts.endpoints import TaskType
        from models.kermt_model import KermtModel

        spec = all_subgroups()[ctx.smoke_subgroup]
        try:
            KermtModel(TaskType.CLASSIFICATION, Path("does_not_matter.pt"),
                       ["cyp3a4_inhibition", "clearance_microsomal"])
            guard = False
        except ValueError:
            guard = True
        weighting = KermtModel.supports_loss_weighting
        ok = guard and weighting is False
        return _r("model.family_wiring", "Model", "Model family + stock-path guards behave", GATE_SMOKE,
                  SCOPE_CPU, PASS if ok else FAIL,
                  f"smoke subgroup {ctx.smoke_subgroup} -> model_family={spec.model_family}; mixed-type "
                  f"targets rejected={guard}; stock path supports_loss_weighting={weighting} "
                  "(equal weighting only)",
                  None if ok else "KermtModel guard or weighting marker is wrong")

    return _guard("model.family_wiring", "Model", "Model family + stock-path guards behave", GATE_SMOKE, SCOPE_CPU, go)


@check
def model_checkpoint_binary(ctx: ReadinessContext) -> CheckResult:
    title = "Checkpoint binary present and hash-verified"
    if not ctx.is_workstation:
        return _not_evaluated("model.checkpoint_binary", "Model", title, GATE_SMOKE,
                              "checkpoint binaries live on the workstation only")

    def go() -> CheckResult:
        from eval.heldout_evaluation import sha256_file

        lock = json.loads((ctx.ml_root / "data" / "metadata" / "kermt_checkpoint.lock.json").read_text("utf-8"))
        path = ctx.ml_root / lock["local_path"].replace("ml/", "", 1) / CHECKPOINT_FILE
        if not path.exists():
            return _r("model.checkpoint_binary", "Model", title, GATE_SMOKE, SCOPE_WORKSTATION, FAIL,
                      f"not found: {path}", f"checkpoint missing at {path}")
        got, want = sha256_file(path), lock["files"][CHECKPOINT_FILE]["sha256"]
        return _r("model.checkpoint_binary", "Model", title, GATE_SMOKE, SCOPE_WORKSTATION,
                  PASS if got == want else FAIL, f"sha256={got[:16]}... expected {want[:16]}...",
                  None if got == want else "checkpoint hash differs from the lockfile")

    return _guard("model.checkpoint_binary", "Model", title, GATE_SMOKE, SCOPE_WORKSTATION, go)


@check
def model_kermt_source(ctx: ReadinessContext) -> CheckResult:
    title = "KERMT checkout is at the locked commit"
    if not ctx.is_workstation:
        return _not_evaluated("model.kermt_source", "Model", title, GATE_SMOKE,
                              "KERMT checkout (MARS_KERMT_REPO) lives on the workstation only")

    def go() -> CheckResult:
        repo = os.environ.get("MARS_KERMT_REPO")
        if not repo or not (Path(repo) / "agent" / "scripts" / "kermt_container.sh").exists():
            return _r("model.kermt_source", "Model", title, GATE_SMOKE, SCOPE_WORKSTATION, FAIL,
                      f"MARS_KERMT_REPO={repo!r} is unset or not a KERMT checkout",
                      "MARS_KERMT_REPO not set to a KERMT v2.0.0 checkout")
        rc, out = _run(["git", "-C", repo, "rev-parse", "HEAD"])
        lock = json.loads((ctx.ml_root / "data" / "metadata" / "kermt_checkpoint.lock.json").read_text("utf-8"))
        want = lock["model"]["source_code_commit"]
        got = out.strip()
        ok = rc == 0 and got == want
        return _r("model.kermt_source", "Model", title, GATE_SMOKE, SCOPE_WORKSTATION, PASS if ok else FAIL,
                  f"HEAD={got[:12]} expected {want[:12]}", None if ok else "KERMT checkout is not at the locked commit")

    return _guard("model.kermt_source", "Model", title, GATE_SMOKE, SCOPE_WORKSTATION, go)


# ============================================================================ #
# ENVIRONMENT
# ============================================================================ #


@check
def env_python(ctx: ReadinessContext) -> CheckResult:
    def go() -> CheckResult:
        from importlib import metadata

        def ver(p: str) -> str:
            try:
                return metadata.version(p)
            except metadata.PackageNotFoundError:
                return "absent"

        pk = {p: ver(p) for p in ("numpy", "pandas", "scikit-learn", "rdkit", "xgboost", "scipy", "wandb", "torch")}
        need = [p for p in ("numpy", "pandas", "scikit-learn", "rdkit", "scipy") if pk[p] == "absent"]
        return _r("env.python", "Environment", "Host Python environment has the CPU-side stack", GATE_SMOKE,
                  SCOPE_CPU, FAIL if need else PASS,
                  f"python {sys.version.split()[0]} on {sys.platform}; {pk}. torch is intentionally "
                  "absent on the host - KERMT runs in its own container.",
                  f"missing required packages: {need}" if need else None)

    return _guard("env.python", "Environment", "Host Python environment has the CPU-side stack",
                  GATE_SMOKE, SCOPE_CPU, go)


@check
def env_docker_image(ctx: ReadinessContext) -> CheckResult:
    title = "KERMT docker image present (identity recorded)"
    if not ctx.is_workstation:
        return _not_evaluated("env.docker_image", "Environment", title, GATE_SMOKE,
                              "docker daemon + kermt:latest live on the workstation")
    image = os.environ.get("MARS_KERMT_IMAGE", "kermt:latest")
    rc, out = _run(["docker", "image", "inspect", image, "--format", "{{.Id}}"])
    if rc != 0:
        return _r("env.docker_image", "Environment", title, GATE_SMOKE, SCOPE_WORKSTATION, FAIL,
                  out.strip()[:200], f"docker image {image} not available")
    image_id = out.strip()
    if ctx.expected_image_id:
        ok = image_id == ctx.expected_image_id
        return _r("env.docker_image", "Environment", title, GATE_SMOKE, SCOPE_WORKSTATION, PASS if ok else FAIL,
                  f"{image} id={image_id[:24]}... expected {ctx.expected_image_id[:24]}...",
                  None if ok else "image id differs from the expected pin")
    return _r("env.docker_image", "Environment", title, GATE_SMOKE, SCOPE_WORKSTATION, WARN,
              f"{image} id={image_id[:30]}... RECORD THIS. No pinned expected image id exists anywhere in "
              "the repository, so identity cannot be verified, only recorded (provenance gap).")


@check
def env_gpu(ctx: ReadinessContext) -> CheckResult:
    title = "CUDA GPU with enough VRAM for KERMT fine-tuning"
    if not ctx.is_workstation:
        return _not_evaluated("env.gpu", "Environment", title, GATE_SMOKE, "GPU is on the workstation only")
    rc, out = _run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"])
    if rc != 0:
        return _r("env.gpu", "Environment", title, GATE_SMOKE, SCOPE_WORKSTATION, FAIL, out.strip()[:200],
                  "nvidia-smi failed - no usable NVIDIA GPU/driver")
    name, mem, drv = [x.strip() for x in out.strip().splitlines()[0].split(",")]
    ok = float(mem) >= MIN_GPU_MIB
    return _r("env.gpu", "Environment", title, GATE_SMOKE, SCOPE_WORKSTATION, PASS if ok else FAIL,
              f"{name} {mem} MiB driver {drv}; KERMT fine-tune floor {MIN_GPU_MIB} MiB at batch 32 "
              "(documented in kermt_integration_status.md sec 6)",
              None if ok else f"{mem} MiB < documented finetune floor {MIN_GPU_MIB} MiB")


@check
def env_requirements(ctx: ReadinessContext) -> CheckResult:
    return _r("env.requirements", "Environment", "GPU/CUDA requirements", GATE_INFO, SCOPE_CPU, PASS,
              "GPU REQUIRED: KERMT fine-tune/inference (container: nvidia/cuda 12.6.3 base, torch 2.9.1, "
              "cuik_molmaker). GPU NOT required: XGBoost, cluster loading, calibration, held-out evaluation, "
              "this report. No paid compute anywhere.")


# ============================================================================ #
# TRACKING
# ============================================================================ #


@check
def tracking_wandb(ctx: ReadinessContext) -> CheckResult:
    def go() -> CheckResult:
        env = ctx.repo_root / ".env"
        vals: dict[str, str] = {}
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.split("=", 1)
                    vals[k.strip()] = v.strip()
        project, entity = vals.get("WANDB_PROJECT"), vals.get("WANDB_ENTITY")
        netrc = any((Path.home() / n).exists() for n in ("_netrc", ".netrc"))
        api_key_set = bool(vals.get("WANDB_API_KEY"))
        installed = importlib.util.find_spec("wandb") is not None
        problems = []
        if not (project and entity):
            problems.append("WANDB_PROJECT/WANDB_ENTITY not set in .env")
        if not installed:
            problems.append("wandb not importable")
        if not (netrc or api_key_set):
            problems.append("no credentials (no _netrc, no WANDB_API_KEY)")
        return _r("tracking.wandb", "Tracking", "W&B configured (credential values never read)", GATE_INFO,
                  SCOPE_CPU, WARN if problems else PASS,
                  f"project={project} entity={entity} wandb_installed={installed} netrc_present={netrc} "
                  f"api_key_in_env={api_key_set}. W&B failure never fails a run; the local ExperimentRun "
                  "is the source of truth." + (f" Problems: {problems}" if problems else ""))

    return _guard("tracking.wandb", "Tracking", "W&B configured (credential values never read)",
                  GATE_INFO, SCOPE_CPU, go)


@check
def tracking_run_naming(ctx: ReadinessContext) -> CheckResult:
    def go() -> CheckResult:
        from configs.clusters import all_subgroups
        from configs.experiment_config import FIXED_SEEDS, ExperimentConfig

        spec = all_subgroups()[ctx.smoke_subgroup]
        names = {
            ExperimentConfig(spec.key, spec.model_family, s, ctx.prep_id, variant=v).run_name()
            for s in FIXED_SEEDS for v in ("", "kendall")
        }
        ok = len(names) == len(FIXED_SEEDS) * 2 and all(spec.key.split("__")[0] in n for n in names)
        return _r("tracking.run_naming", "Tracking", "Run names are unique per seed and variant", GATE_SMOKE,
                  SCOPE_CPU, PASS if ok else FAIL, f"{len(names)} distinct names, e.g. {sorted(names)[0]}",
                  None if ok else "run names collide across seeds/variants")

    return _guard("tracking.run_naming", "Tracking", "Run names are unique per seed and variant",
                  GATE_SMOKE, SCOPE_CPU, go)


@check
def tracking_provenance(ctx: ReadinessContext) -> CheckResult:
    def go() -> CheckResult:
        from tracking.experiment import ExperimentRun

        probe_cfg = {"probe": True, "seed": 0}
        with tempfile.TemporaryDirectory(prefix="mars_ready_") as tmp:
            run = ExperimentRun(name="readiness_probe", repo_root=ctx.repo_root,
                                config=probe_cfg, runs_dir=Path(tmp))
            run.start(run_tags={"seed": 0, "prep_id": ctx.prep_id})
            prov = run.provenance
            git = prov.get("git", {})
            env = prov.get("environment", {})
            # Config and seed live in their own files (config.json / run.json), not inside
            # provenance.json - so verify what is actually written to disk.
            cfg_file = run.run_dir / "config.json"
            run_file = run.run_dir / "run.json"
            cfg_ok = cfg_file.exists() and json.loads(cfg_file.read_text(encoding="utf-8")) == probe_cfg
            seed_ok = run_file.exists() and json.loads(run_file.read_text(encoding="utf-8")).get("seed") == 0
            have = {"provenance.git.commit": bool(git.get("commit")),
                    "provenance.git.branch": bool(git.get("branch")),
                    "provenance.environment.python_version": bool(env.get("python_version")),
                    "provenance.environment.platform": bool(env.get("platform")),
                    "config.json round-trips": cfg_ok, "run.json records seed": seed_ok}
            missing = [k for k, v in have.items() if not v]
            run.finish("completed")
        return _r("tracking.provenance", "Tracking", "A real ExperimentRun captures provenance fields",
                  GATE_SMOKE, SCOPE_CPU, FAIL if missing else PASS,
                  f"started a probe run; captured {sorted(k for k, v in have.items() if v)}; missing={missing}",
                  f"provenance missing {missing}" if missing else None)

    return _guard("tracking.provenance", "Tracking", "A real ExperimentRun captures provenance fields",
                  GATE_SMOKE, SCOPE_CPU, go)


# ============================================================================ #
# EVALUATION
# ============================================================================ #


@check
def eval_test_split(ctx: ReadinessContext) -> CheckResult:
    def go() -> CheckResult:
        from configs.clusters import all_subgroups
        from data.cluster_loaders import load_cluster

        spec = all_subgroups()[ctx.smoke_subgroup]
        cd = load_cluster(ctx.prep_dir, list(spec.endpoints), cluster_key=spec.key)
        pool, _ = cd.train_pool(holdout_calibration=True)
        test = set(cd.smiles("test"))
        ok = len(test) > 0 and not (test & set(pool["standardized_smiles"]))
        return _r("eval.test_split", "Evaluation", "Smoke endpoint has a non-empty test split disjoint from training",
                  GATE_SMOKE, SCOPE_CPU, PASS if ok else FAIL,
                  f"{spec.key}: test={len(test)} molecules, pool={len(pool)}, overlap={len(test & set(pool['standardized_smiles']))}",
                  None if ok else "test split empty or overlaps the training pool")

    return _guard("eval.test_split", "Evaluation", "Smoke endpoint has a non-empty test split disjoint from training",
                  GATE_SMOKE, SCOPE_CPU, go)


@check
def eval_calibration_microrun(ctx: ReadinessContext) -> CheckResult:
    def go() -> CheckResult:
        from eval.cluster_calibration import REQUIRED_RECORD_KEYS, calibrate_endpoints
        from mars_contracts.endpoints import TaskType

        rng = np.random.default_rng(0)
        logits = rng.normal(0, 3, 200)
        y = (rng.random(200) < 1 / (1 + np.exp(-logits / 2.5))).astype(float)
        out = calibrate_endpoints(
            endpoint_keys=["dili_liver_injury"], task_types={"dili_liver_injury": TaskType.CLASSIFICATION},
            seed=0, cal_scores=logits[:100, None], cal_labels=y[:100, None],
            test_scores=logits[100:, None], test_labels=y[100:, None], provenance={"prep_id": ctx.prep_id},
        )["dili_liver_injury"]
        rec = out.to_record()
        missing = [k for k in REQUIRED_RECORD_KEYS if k not in rec]
        ok = out.scaler is not None and not missing and out.test_metrics_calibrated is not None
        return _r("eval.calibration_microrun", "Evaluation",
                  "Calibration -> held-out scoring executes end to end (synthetic logits)", GATE_SMOKE, SCOPE_CPU,
                  PASS if ok else FAIL,
                  f"status={out.status} T={out.temperature:.3f} record_keys_missing={missing}. Synthetic input: "
                  "proves the code path, says nothing about real KERMT logits.",
                  None if ok else f"calibration micro-run failed (missing={missing})")

    return _guard("eval.calibration_microrun", "Evaluation",
                  "Calibration -> held-out scoring executes end to end (synthetic logits)", GATE_SMOKE, SCOPE_CPU, go)


@check
def eval_artifact_paths(ctx: ReadinessContext) -> CheckResult:
    def go() -> CheckResult:
        runs = ctx.ml_root / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=runs, prefix=".probe_", delete=True):
            pass
        return _r("eval.artifact_paths", "Evaluation", "Output paths are writable", GATE_SMOKE, SCOPE_CPU, PASS,
                  f"{runs} writable. Per run: runs/<run_id>/artifacts/{{kermt,model,calibration/<endpoint>/}}, "
                  "metrics.jsonl. XGBoost held-out reports: runs/test_evaluations/<endpoint>.json.")

    return _guard("eval.artifact_paths", "Evaluation", "Output paths are writable", GATE_SMOKE, SCOPE_CPU, go)


@check
def eval_xgboost_heldout(ctx: ReadinessContext) -> CheckResult:
    title = "XGBoost held-out TEST evaluation complete (14 endpoints x 5 seeds)"

    def go() -> CheckResult:
        d = ctx.ml_root / "runs" / "test_evaluations"
        summary = d / "summary.json"
        if not summary.exists():
            return _r("eval.xgboost_heldout", "Evaluation", title, GATE_COMPARISON, SCOPE_CPU, FAIL,
                      f"{summary} not found", "no XGBoost test-set evaluation exists; KERMT-vs-XGBoost not comparable")
        s = json.loads(summary.read_text(encoding="utf-8"))
        bad = []
        for ep in s["evaluated"]:
            r = json.loads((d / f"{ep}.json").read_text(encoding="utf-8"))
            if r.get("split") != "test" or list(r.get("seeds", [])) != list(EXPECTED_SEEDS):
                bad.append(ep)
        n = len(s["evaluated"])
        ok = n == 14 and not s["blocked"] and not bad
        return _r("eval.xgboost_heldout", "Evaluation", title, GATE_COMPARISON, SCOPE_CPU, PASS if ok else FAIL,
                  f"evaluated={n} blocked={s['blocked']} malformed={bad}",
                  None if ok else f"held-out evaluation incomplete: {14 - n} missing, blocked={list(s['blocked'])}")

    return _guard("eval.xgboost_heldout", "Evaluation", title, GATE_COMPARISON, SCOPE_CPU, go)


# ============================================================================ #
# REPRODUCIBILITY
# ============================================================================ #


@check
def repro_git(ctx: ReadinessContext) -> CheckResult:
    rc, sha = _run(["git", "-C", str(ctx.repo_root), "rev-parse", "HEAD"])
    rc2, status = _run(["git", "-C", str(ctx.repo_root), "status", "--short"])
    if rc != 0:
        return _r("repro.git_sha", "Reproducibility", "Git SHA capturable", GATE_SMOKE, SCOPE_CPU, FAIL,
                  sha.strip()[:200], "not a git repository / git unavailable")
    dirty = [line for line in status.splitlines() if line.strip()]
    if dirty:
        return _r("repro.git_sha", "Reproducibility", "Git SHA capturable, tree clean", GATE_SMOKE, SCOPE_CPU, WARN,
                  f"HEAD={sha.strip()[:12]} but {len(dirty)} uncommitted change(s): runs will record "
                  "git.dirty=True and the recorded SHA will NOT describe the code that ran. Commit before the lab.")
    return _r("repro.git_sha", "Reproducibility", "Git SHA capturable, tree clean", GATE_SMOKE, SCOPE_CPU, PASS,
              f"HEAD={sha.strip()[:12]}, clean")


@check
def repro_seed_and_rng(ctx: ReadinessContext) -> CheckResult:
    def go() -> CheckResult:
        import random

        from configs.experiment_config import FIXED_SEEDS
        from utils.rng_state import capture_rng_state, restore_rng_state
        from utils.seed import set_global_seed

        set_global_seed(3)
        a = (random.random(), float(np.random.rand()))
        set_global_seed(3)
        b = (random.random(), float(np.random.rand()))
        seeded = a == b
        set_global_seed(5)
        st = capture_rng_state(include_torch=False)
        want = (random.random(), float(np.random.rand()))
        set_global_seed(0)
        restore_rng_state(st)
        rest = (random.random(), float(np.random.rand())) == want
        ok = seeded and rest and tuple(FIXED_SEEDS) == EXPECTED_SEEDS
        return _r("repro.seed_rng", "Reproducibility", "Seeding + RNG capture/restore work", GATE_SMOKE, SCOPE_CPU,
                  PASS if ok else FAIL,
                  f"FIXED_SEEDS={tuple(FIXED_SEEDS)}; reseed reproduces={seeded}; capture->restore "
                  f"reproduces continuation={rest}. Capability exists in utils/rng_state.py; it is NOT yet "
                  "called from any KERMT training path.",
                  None if ok else "seed/RNG round trip failed")

    return _guard("repro.seed_rng", "Reproducibility", "Seeding + RNG capture/restore work",
                  GATE_SMOKE, SCOPE_CPU, go)


@check
def repro_gaps(ctx: ReadinessContext) -> CheckResult:
    integrated = any(
        "rng_state" in p.read_text(encoding="utf-8")
        for p in (ctx.ml_root / "train").rglob("*.py") if p.name != "readiness_report.py"
    )
    return _r("repro.known_gaps", "Reproducibility", "Known reproducibility gaps (informational)", GATE_INFO,
              SCOPE_CPU, WARN,
              f"RNG capture wired into a training path: {integrated}. KERMT CUDA determinism: NOT ESTABLISHED. "
              "Docker image identity: recorded at run time, no pinned expectation. PYTHONHASHSEED cannot be "
              "restored in-process.")


# ============================================================================ #
# Driver
# ============================================================================ #


def build_readiness_report(ctx: ReadinessContext, checks: list[_Check] | None = None) -> dict[str, Any]:
    results = [c(ctx) for c in (checks if checks is not None else _REGISTRY)]
    return summarize(results, ctx)


def summarize(results: list[CheckResult], ctx: ReadinessContext) -> dict[str, Any]:
    blockers = [r for r in results if r.gate == GATE_SMOKE and r.status == FAIL]
    comparison = [r for r in results if r.gate == GATE_COMPARISON and r.status in (FAIL, WARN)]
    pending = [r for r in results if r.status == NOT_EVALUATED]
    verdict = BLOCKED if blockers else READY
    if ctx.is_workstation:
        scope = "workstation: CPU-side and workstation checks all evaluated"
    else:
        scope = (f"CPU-side only: {len(pending)} workstation check(s) NOT_EVALUATED - re-run with "
                 "--target workstation at the lab")
    return {
        "verdict": verdict,
        "verdict_scope": scope,
        "target": ctx.target,
        "prep_id": ctx.prep_id,
        "smoke_subgroup": ctx.smoke_subgroup,
        "smoke_test_blockers": [f"{r.id}: {r.blocker or r.evidence}" for r in blockers],
        "comparison_blockers": [f"[{r.status}] {r.id}: {r.blocker or r.evidence}" for r in comparison],
        "pending_on_workstation": [r.id for r in pending],
        "counts": {s: sum(1 for r in results if r.status == s) for s in (PASS, WARN, FAIL, NOT_EVALUATED)},
        "checks": [asdict(r) for r in results],
    }


def render(report: dict[str, Any]) -> str:
    lines = [f"{report['verdict']}   ({report['verdict_scope']})", ""]
    cat = None
    for c in report["checks"]:
        if c["category"] != cat:
            cat = c["category"]
            lines.append(f"-- {cat} --")
        lines.append(f"  [{c['status']:13s}] {c['id']:32s} gate={c['gate']:10s} {c['title']}")
    for head, key in (("SMOKE-TEST BLOCKERS", "smoke_test_blockers"),
                      ("COMPARISON BLOCKERS (do not block the smoke test)", "comparison_blockers"),
                      ("PENDING ON WORKSTATION", "pending_on_workstation")):
        lines += ["", f"{head}: {len(report[key]) or 'none'}"]
        lines += [f"  - {x}" for x in report[key]]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ml_root = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target", choices=("laptop", "workstation"), default="laptop")
    p.add_argument("--prep-id", default=DEFAULT_PREP_ID)
    p.add_argument("--smoke-subgroup", default=DEFAULT_SMOKE_SUBGROUP)
    p.add_argument("--expected-image-id", default=None)
    p.add_argument("--workstation-fingerprint", default=None)
    p.add_argument("--out", default=str(ml_root / "runs" / "readiness_report.json"))
    args = p.parse_args(argv)

    ctx = ReadinessContext(
        repo_root=ml_root.parent, ml_root=ml_root, prep_id=args.prep_id, smoke_subgroup=args.smoke_subgroup,
        target=args.target, expected_image_id=args.expected_image_id,
        workstation_fingerprint=Path(args.workstation_fingerprint) if args.workstation_fingerprint else None,
    )
    report = build_readiness_report(ctx)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(render(report))
    print(f"\nwrote {out}")
    return 0 if report["verdict"] == READY else 1


if __name__ == "__main__":
    raise SystemExit(main())
