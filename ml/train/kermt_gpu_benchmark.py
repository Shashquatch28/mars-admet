"""
KERMT GPU/VRAM batch-size characterization (M2 pre-flight, RTX A4000 workstation).

Empirically determines the usable batch-size envelope for KERMT single-task
finetuning on this GPU before committing to a production configuration.
Not a training run — each config does exactly one epoch over a fixed, real
512-molecule AMES train / 128-molecule AMES val subset (never the held-out
test set) so peak VRAM and throughput are comparable across batch sizes.

Reuses the existing MARS tracking stack exactly as `train_xgboost.py` does —
`tracking.experiment.ExperimentRun` (local, source of truth, always on) +
`tracking.wandb_logger.WandbLogger` (opt-in, mirrors to W&B, fails soft if
wandb isn't installed/authenticated). No parallel tracking system.

KERMT itself is never modified or imported in-process here — every actual
model operation happens inside the `kermt:latest` container via
`models.kermt_model.KermtModel`, exactly as designed for the M2 KERMT
integration (see documentation/AIMS/decisions.md, 2026-09-18 entries).
"""

from __future__ import annotations

import json
import re
import subprocess
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from mars_contracts.endpoints import TaskType
from models.kermt_model import KermtConfig, KermtModel
from tracking.experiment import ExperimentRun

CHECKPOINT_PATH = Path(
    "data/checkpoints/kermt/NV-KERMT-70M-v2/kermt_contrastive_v2.0.pt"
)
CHECKPOINT_SHA256 = (
    "e9e6649bc96503fbdb3023e312764ecbbbafd686d9a62865a1fec9466cea6be3"
)
KERMT_COMMIT = "e402473376ace30fa0092dad0578a88bf7f67287"  # v2.0.0 tag
ENDPOINT = "ames_mutagenicity"


@dataclass
class BenchmarkResult:
    batch_size: int
    status: str  # "ok" | "oom"
    n_train: int
    n_val: int
    steps: int | None
    samples_processed: int | None
    wall_seconds: float | None
    train_epoch_seconds: float | None
    samples_per_sec: float | None
    steps_per_sec: float | None
    peak_vram_mib: int | None
    baseline_vram_mib: int | None
    loss_train: float | None
    loss_finite: bool | None
    gpu_util_pct: float | None
    error_text: str | None
    error_phase: str | None
    run_id: str
    wandb_url: str | None = None


def _gpu_baseline_vram_mib() -> int:
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, check=True,
    )
    return int(out.stdout.strip().splitlines()[0])


def _poll_gpu(log_path: Path, stop_flag: Path) -> None:
    """Run as a subprocess: append timestamp+mem+util lines until stop_flag exists."""
    script = (
        "import subprocess, time, pathlib, sys\n"
        f"stop = pathlib.Path({str(stop_flag)!r})\n"
        f"log = open({str(log_path)!r}, 'w')\n"
        "while not stop.exists():\n"
        "    r = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,utilization.gpu',"
        " '--format=csv,noheader,nounits'], capture_output=True, text=True)\n"
        "    log.write(r.stdout)\n"
        "    log.flush()\n"
        "    time.sleep(1)\n"
    )
    subprocess.Popen(["python3", "-c", script])


def _parse_gpu_poll(log_path: Path) -> tuple[int | None, float | None]:
    if not log_path.exists():
        return None, None
    mem_vals, util_vals = [], []
    for line in log_path.read_text().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 2 and parts[0].isdigit():
            mem_vals.append(int(parts[0]))
            if parts[1].isdigit():
                util_vals.append(int(parts[1]))
    peak_mem = max(mem_vals) if mem_vals else None
    avg_util = (sum(util_vals) / len(util_vals)) if util_vals else None
    return peak_mem, avg_util


def _classify_oom_phase(log_text: str) -> str:
    """Best-effort phase classification from the traceback context — no KERMT
    source modification; purely reading the existing traceback KERMT already
    prints on failure."""
    tail = log_text[-6000:]
    if "backward" in tail.lower() or ".backward(" in tail:
        return "backward"
    if "optimizer.step" in tail or "opt.step" in tail:
        return "optimizer_step"
    if "DataLoader" in tail or "collate" in tail.lower():
        return "data_loading"
    if "forward" in tail.lower():
        return "forward"
    return "unknown"


def run_one_batch_size(
    batch_size: int,
    train_smiles: list[str],
    y_train: np.ndarray,
    val_smiles: list[str],
    y_val: np.ndarray,
    *,
    repo_root: Path,
    runs_dir: Path,
    use_wandb: bool,
) -> BenchmarkResult:
    run_name = f"kermt_gpu_bench_bs{batch_size}"
    baseline_vram = _gpu_baseline_vram_mib()

    # Under runs_dir (ml/runs/, already gitignored wholesale) — NOT
    # runs_dir.parent — so per-config working directories (finetuned
    # checkpoints, features, logs) don't leak into ml/ as untracked,
    # partially-ignored clutter (caught after the first real sweep left
    # 3.4GB under ml/kermt_gpu_bench/ with inconsistent .gitignore coverage).
    run_dir = runs_dir / "kermt_gpu_bench" / f"bs{batch_size}"
    poll_log = run_dir / "gpu_poll.log"
    stop_flag = run_dir / "STOP"
    run_dir.mkdir(parents=True, exist_ok=True)
    stop_flag.unlink(missing_ok=True)

    tracking_config: dict[str, Any] = {
        "experiment_type": "kermt_gpu_benchmark",
        "endpoint": ENDPOINT,
        "batch_size": batch_size,
        "epochs": 1,
        "n_train": len(train_smiles),
        "n_val": len(val_smiles),
        "seed": 0,
        "checkpoint_sha256": CHECKPOINT_SHA256,
        "kermt_commit": KERMT_COMMIT,
        "gpu": "NVIDIA RTX A4000",
    }

    run = ExperimentRun(name=run_name, repo_root=repo_root, config=tracking_config, runs_dir=runs_dir)
    run.start(run_tags={"experiment_type": "kermt_gpu_benchmark", "batch_size": batch_size})

    wandb_logger = None
    if use_wandb:
        try:
            from tracking.wandb_logger import WandbLogger

            wandb_logger = WandbLogger(run_id=run.run_id, config=tracking_config, provenance=run.provenance)
        except Exception as exc:  # noqa: BLE001
            warnings.warn(f"W&B logging disabled for {run.run_id}: {exc}", UserWarning, stacklevel=2)
            wandb_logger = None

    model = KermtModel(
        TaskType.CLASSIFICATION,
        CHECKPOINT_PATH,
        [ENDPOINT],
        seed=0,
        config=KermtConfig(epochs=1, batch_size=batch_size, gpu=0),
    )

    _poll_gpu(poll_log, stop_flag)
    t0 = time.time()
    status = "ok"
    error_text = None
    error_phase = None
    loss_train = None
    steps = None
    train_wall = None  # pure KERMT-reported epoch training time, excludes
    # container/checkpoint-validation/data-prep overhead (~15-20s fixed cost
    # per config) that would otherwise dominate at small batch sizes and
    # distort samples/sec comparisons across configs.
    try:
        model.fit(train_smiles, y_train, X_val=val_smiles, y_val=y_val, run_dir=run_dir)
        wall = time.time() - t0
        log_text = (run_dir / "logs" / "finetune.log").read_text()
        m = re.search(r"loss_train:\s*([0-9.eE+-]+)", log_text)
        loss_train = float(m.group(1)) if m else None
        t_time_m = re.search(r"t_time:\s*([0-9.eE+-]+)s", log_text)
        train_wall = float(t_time_m.group(1)) if t_time_m else None
        steps = max(1, len(train_smiles) // batch_size + (1 if len(train_smiles) % batch_size else 0))
    except RuntimeError as exc:
        wall = time.time() - t0
        msg = str(exc)
        is_oom = "out of memory" in msg.lower() or "CUDA error" in msg
        log_path = run_dir / "logs" / "finetune.log"
        log_text = log_path.read_text() if log_path.exists() else msg
        if is_oom or "out of memory" in log_text.lower():
            status = "oom"
            oom_match = re.search(r"(RuntimeError|torch\.cuda\.OutOfMemoryError):[^\n]*", log_text)
            error_text = oom_match.group(0) if oom_match else msg[-500:]
            error_phase = _classify_oom_phase(log_text)
        else:
            raise
    finally:
        stop_flag.write_text("stop")
        time.sleep(1.2)  # let the poller subprocess observe the flag and exit

    peak_vram, gpu_util = _parse_gpu_poll(poll_log)
    n_samples = len(train_smiles)
    # Throughput uses the pure KERMT-reported epoch time (train_wall), not the
    # outer fit()-call wall clock, which includes ~15-20s of fixed per-config
    # container/checkpoint-validation/data-prep overhead that would otherwise
    # swamp the signal at small batch sizes. Fall back to outer wall only if
    # t_time couldn't be parsed (e.g. an OOM before any epoch completed).
    throughput_basis = train_wall if (status == "ok" and train_wall) else wall
    samples_per_sec = (n_samples / throughput_basis) if (status == "ok" and throughput_basis) else None
    steps_per_sec = (steps / throughput_basis) if (status == "ok" and steps and throughput_basis) else None
    loss_finite = bool(np.isfinite(loss_train)) if loss_train is not None else None

    metrics_dict: dict[str, Any] = {
        "batch_size": batch_size,
        "status": status,
        "n_train": n_samples,
        "n_val": len(val_smiles),
        "steps": steps,
        "samples_processed": n_samples if status == "ok" else None,
        "wall_seconds": wall,
        "train_epoch_seconds": train_wall,
        "samples_per_sec": samples_per_sec,
        "steps_per_sec": steps_per_sec,
        "peak_vram_mib": peak_vram,
        "baseline_vram_mib": baseline_vram,
        "loss_train": loss_train,
        "loss_finite": loss_finite,
        "gpu_util_pct": gpu_util,
        "error_text": error_text,
        "error_phase": error_phase,
        "gpu": "NVIDIA RTX A4000",
        "cuda_container": "12.8",
        "pytorch_version": "2.9.1",
        "kermt_commit": KERMT_COMMIT,
        "checkpoint_sha256": CHECKPOINT_SHA256,
        "dataset": ENDPOINT,
        "seed": 0,
    }
    run.log_metrics(metrics_dict)
    if wandb_logger is not None:
        wandb_logger.log(metrics_dict)

    run.finish("completed" if status == "ok" else "oom")

    wandb_url = None
    if wandb_logger is not None:
        wandb_url = getattr(wandb_logger._run, "url", None)
        wandb_logger.finish()

    return BenchmarkResult(
        batch_size=batch_size,
        status=status,
        n_train=n_samples,
        n_val=len(val_smiles),
        steps=steps,
        samples_processed=n_samples if status == "ok" else None,
        wall_seconds=wall,
        train_epoch_seconds=train_wall,
        samples_per_sec=samples_per_sec,
        steps_per_sec=steps_per_sec,
        peak_vram_mib=peak_vram,
        baseline_vram_mib=baseline_vram,
        loss_train=loss_train,
        loss_finite=loss_finite,
        gpu_util_pct=gpu_util,
        error_text=error_text,
        error_phase=error_phase,
        run_id=run.run_id,
        wandb_url=wandb_url,
    )


def main(batch_sizes: list[int], *, use_wandb: bool) -> list[BenchmarkResult]:
    repo_root = Path(__file__).resolve().parents[2]
    runs_dir = repo_root / "ml" / "runs"

    with open("/tmp/claude-1001/kermt_bench_subset.json") as f:
        d = json.load(f)
    train_smiles, y_train = d["train_smiles"], np.array(d["y_train"])
    val_smiles, y_val = d["val_smiles"], np.array(d["y_val"])

    results: list[BenchmarkResult] = []
    prev_samples_per_sec = None
    for bs in batch_sizes:
        print(f"=== batch_size={bs} ===", flush=True)
        result = run_one_batch_size(
            bs, train_smiles, y_train, val_smiles, y_val,
            repo_root=repo_root, runs_dir=runs_dir, use_wandb=use_wandb,
        )
        results.append(result)
        print(json.dumps(result.__dict__, indent=2), flush=True)
        if result.status == "oom":
            print(f"OOM at batch_size={bs}; stopping sweep.", flush=True)
            break
        if (
            prev_samples_per_sec is not None
            and result.samples_per_sec is not None
            and result.samples_per_sec < prev_samples_per_sec * 1.05
        ):
            print(
                f"Throughput plateaued at batch_size={bs} "
                f"({result.samples_per_sec:.1f} vs prior {prev_samples_per_sec:.1f} samples/sec); "
                "stopping sweep (no useful benefit from a larger batch).",
                flush=True,
            )
            break
        prev_samples_per_sec = result.samples_per_sec
    return results


if __name__ == "__main__":
    import sys

    use_wandb = "--no-wandb" not in sys.argv
    results = main([8, 16, 32, 64, 128], use_wandb=use_wandb)
    summary_path = Path("/tmp/claude-1001/kermt_gpu_bench_summary.json")
    summary_path.write_text(json.dumps([r.__dict__ for r in results], indent=2))
    print(f"\nWrote summary to {summary_path}")
