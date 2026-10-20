"""In-process KERMT inference for the Tier-0 finetuned checkpoints (CPU).

Runs only inside the KERMT inference image (`Dockerfile` next to this file), where
`kermt` (NVIDIA-BioNeMo/KERMT @ e402473) and torch are importable. The API image never
imports this module; it talks to `app.py` over HTTP.

Why not `KermtModel.predict()`: that wraps NVIDIA's CLI and starts several `docker run`
containers per call, re-loading the checkpoint each time. This engine loads each
checkpoint once and reuses KERMT's own `task.predict.predict` forward loop, so the
numbers are the ones `main.py predict` would produce:

    SMILES -> rdkit_2d_normalized features (descriptastorus, as `scripts/save_features.py`)
           -> MoleculeDatapoint -> MolCollator -> model.eval() forward -> target scaler inverse

The one place this diverges from `task.predict.make_predictions` is `torch.cuda.set_device`,
which cannot run on a CPU build. `test_kermt_parity` (in this directory's tests) and
`parity_check.py` hold the engine to the stock-CLI predictions recorded in W&B.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from argparse import ArgumentParser, Namespace
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

logger = logging.getLogger("mars.kermt_engine")

FEATURES_GENERATOR = "rdkit_2d_normalized"  # `prepare_data.py` DEFAULT_FEATURES_GENERATOR["inference"]
DEFAULT_BATCH_SIZE = 32  # agent/config/defaults_inference.json


@dataclass
class LoadedModel:
    arm: str
    seed: int
    model_id: str
    task_type: str
    target_names: list[str]
    model_sha256: str
    path: Path
    model: object
    scaler: object
    args: Namespace
    load_seconds: float


@dataclass
class ArmResult:
    arm: str
    model_id: str
    task_type: str
    target_names: list[str]
    # seed -> (n_molecules, n_targets); NaN where the molecule could not be featurized
    by_seed: dict[int, np.ndarray] = field(default_factory=dict)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class KermtEngine:
    """Loads `<root>/<arm>/seed_<n>/{model.pt,metadata.json}` and predicts on CPU."""

    def __init__(
        self,
        root: Path | str,
        *,
        arms: list[str] | None = None,
        seeds: list[int] | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        threads: int | None = None,
        verify_hash: bool = True,
    ) -> None:
        import torch

        self.root = Path(root)
        self._arms_filter = set(arms) if arms else None
        self._seeds_filter = set(seeds) if seeds is not None else None
        self.batch_size = batch_size
        self.verify_hash = verify_hash
        torch.set_num_threads(threads or effective_cpus())
        self._models: dict[str, list[LoadedModel]] = {}
        # torch modules are not safe to run concurrently with a shared `shared_dict`/args; one forward at a time.
        self._lock = threading.Lock()
        self._feature_fn = None
        self._newest_train_args: Namespace | None = None

    # ------------------------------------------------------------------ loading

    def discover(self) -> list[tuple[str, int, Path]]:
        found = []
        if not self.root.exists():
            return found
        for arm_dir in sorted(p for p in self.root.iterdir() if p.is_dir()):
            if self._arms_filter and arm_dir.name not in self._arms_filter:
                continue
            for seed_dir in sorted(arm_dir.glob("seed_*")):
                seed = int(seed_dir.name.removeprefix("seed_"))
                if self._seeds_filter is not None and seed not in self._seeds_filter:
                    continue
                if (seed_dir / "model.pt").exists() and (seed_dir / "metadata.json").exists():
                    found.append((arm_dir.name, seed, seed_dir))
        return found

    def load_all(self) -> int:
        for arm, seed, seed_dir in self.discover():
            self._load_one(arm, seed, seed_dir)
        return sum(len(v) for v in self._models.values())

    def _build_args(self, ckpt: Path) -> Namespace:
        """The `args` namespace `task.predict.make_predictions` would hold for one checkpoint."""
        from kermt.util.parsing import add_predict_args, get_newest_train_args
        from kermt.util.utils import load_args

        parser = ArgumentParser()
        add_predict_args(parser)
        args = parser.parse_args(
            ["--data_path", "unused.csv", "--output_path", "unused.csv",
             "--batch_size", str(self.batch_size), "--seed", "0", "--no_cuda"]
        )
        # `modify_predict_args` without its filesystem side effect (makedirs of the output path).
        args.parser_name = "predict"
        args.checkpoint_dir = None
        args.checkpoint_path = str(ckpt)
        args.checkpoint_paths = [str(ckpt)]
        args.cuda = False
        del args.no_cuda
        args.fingerprint = False
        args.gpu = None

        train_args = load_args(str(ckpt))
        for key, value in vars(train_args).items():
            if not hasattr(args, key):
                setattr(args, key, value)
        if self._newest_train_args is None:  # identical for every checkpoint and slow to build (~5 s)
            self._newest_train_args = get_newest_train_args()
        for key, value in vars(self._newest_train_args).items():
            if not hasattr(args, key):
                setattr(args, key, value)
        args.debug = True
        args.task_names = list(train_args.task_names)
        args.num_tasks = int(train_args.num_tasks)
        return args

    def _load_one(self, arm: str, seed: int, seed_dir: Path) -> LoadedModel:
        from kermt.util.utils import load_checkpoint, load_scalars

        t0 = time.perf_counter()
        ckpt = seed_dir / "model.pt"
        meta = json.loads((seed_dir / "metadata.json").read_text(encoding="utf-8"))
        digest = _sha256(ckpt) if self.verify_hash else meta["model_sha256"]
        if digest != meta["model_sha256"]:
            raise RuntimeError(f"{ckpt}: sha256 {digest} does not match metadata {meta['model_sha256']}")

        args = self._build_args(ckpt)
        scaler, features_scaler = load_scalars(str(ckpt))
        if features_scaler is not None or getattr(args, "features_scaling", False):
            raise RuntimeError(f"{ckpt}: feature scaling is on; the Tier-0 models were trained with --no_features_scaling")
        model, _ = load_checkpoint(str(ckpt), cuda=False, current_args=args, logger=_Quiet())
        model.eval()
        loaded = LoadedModel(
            arm=arm,
            seed=seed,
            model_id=meta["model_id"],
            task_type=meta["task_type"],
            target_names=list(meta["target_names"]),
            model_sha256=digest,
            path=ckpt,
            model=model,
            scaler=scaler,
            args=args,
            load_seconds=time.perf_counter() - t0,
        )
        if args.task_names != loaded.target_names:
            raise RuntimeError(f"{ckpt}: checkpoint tasks {args.task_names} != metadata {loaded.target_names}")
        self._models.setdefault(arm, []).append(loaded)
        logger.info("loaded %s seed %d in %.1fs", arm, seed, loaded.load_seconds)
        return loaded

    # ------------------------------------------------------------------ description

    def describe(self) -> dict:
        return {
            arm: {
                "model_id": ms[0].model_id,
                "task_type": ms[0].task_type,
                "target_names": ms[0].target_names,
                "seeds": sorted(m.seed for m in ms),
                "model_sha256": {str(m.seed): m.model_sha256 for m in sorted(ms, key=lambda m: m.seed)},
            }
            for arm, ms in sorted(self._models.items())
        }

    def arms(self) -> list[str]:
        return sorted(self._models)

    # ------------------------------------------------------------------ prediction

    def _features(self, smiles: list[str]) -> tuple[list[np.ndarray | None], list[bool]]:
        from kermt.data.molfeaturegenerator import get_features_generator

        if self._feature_fn is None:
            self._feature_fn = get_features_generator(FEATURES_GENERATOR)
        feats: list[np.ndarray | None] = []
        for smi in smiles:
            try:
                f = np.asarray(self._feature_fn(smi), dtype=float)
                feats.append(None if f.size == 0 else f)
            except Exception:
                logger.warning("feature generation failed for %r", smi)
                feats.append(None)
        return feats, [f is not None for f in feats]

    def predict(self, smiles: list[str], arms: list[str] | None = None) -> dict[str, ArmResult]:
        """Per-arm, per-seed predictions for already-standardized SMILES.

        Classification values are probabilities (KERMT's eval-mode two-view mean); regression
        values are in the endpoint's own unit (target scaler inverted). Rows KERMT cannot
        featurize come back as NaN, never as a made-up number.
        """
        wanted = arms or self.arms()
        unknown = [a for a in wanted if a not in self._models]
        if unknown:
            raise KeyError(f"arms not loaded: {unknown}")

        with self._lock:
            feats, ok = self._features(smiles)
            good = [i for i, o in enumerate(ok) if o]
            # KERMT caches each molecule's graph in this dict (as `make_predictions` does across a
            # checkpoint ensemble), so the graph is built once per request, not once per model.
            shared_dict: dict = {}

            # Checkpoints run one after another, each on all the CPUs. Measured 2026-10-19 on 4 vCPUs:
            # running several at once (2x2 or 4x1 threads) was no faster than one at 4 threads, because the
            # cost is the matmuls in the model, not Python overhead, and oversubscribing threads made it worse.
            jobs = [(arm, lm) for arm in wanted for lm in sorted(self._models[arm], key=lambda m: m.seed)]
            arrays = [self._forward(lm, smiles, feats, good, shared_dict) for _, lm in jobs]

            out: dict[str, ArmResult] = {}
            for (arm, lm), full in zip(jobs, arrays, strict=True):
                if arm not in out:
                    first = self._models[arm][0]
                    out[arm] = ArmResult(arm=arm, model_id=first.model_id, task_type=first.task_type,
                                         target_names=first.target_names)
                out[arm].by_seed[lm.seed] = full
            return out

    def _forward(self, lm: LoadedModel, smiles: list[str], feats: list, good: list[int], shared_dict: dict) -> np.ndarray:
        """One checkpoint's predictions for the featurizable molecules; NaN rows for the rest."""
        from kermt.data import MoleculeDataset
        from kermt.data.moldataset import MoleculeDatapoint
        from task.predict import predict as kermt_predict

        full = np.full((len(smiles), len(lm.target_names)), np.nan)
        if not good:
            return full
        data = MoleculeDataset([MoleculeDatapoint(line=[smiles[i]], args=lm.args, features=feats[i]) for i in good])
        lm.args.features_size = data.features_size()
        preds, _ = kermt_predict(
            model=lm.model, data=data, args=lm.args, batch_size=self.batch_size,
            loss_func=None, logger=None, shared_dict=shared_dict, scaler=lm.scaler,
        )
        full[good, :] = np.asarray(preds, dtype=float).reshape(len(good), -1)
        return full


class _Quiet:
    """KERMT's loaders call `logger.debug(...)` once per parameter; keep that out of the log."""

    def debug(self, *a, **k) -> None:  # noqa: D401
        return None

    info = warning = error = debug


def effective_cpus() -> int:
    """CPUs this process may really use. `os.cpu_count()` reports the host's CPUs inside a container
    with a CPU limit (18 on the dev machine under `--cpus 4`), and sizing torch's thread pool from it
    oversubscribes the limit and is several times slower, so read the cgroup quota first."""
    limits = [os.cpu_count() or 1]
    try:
        limits.append(len(os.sched_getaffinity(0)))
    except AttributeError:
        pass
    try:  # cgroup v2: "max 100000" or "<quota> <period>"
        quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()[:2]
        if quota != "max":
            limits.append(max(1, round(int(quota) / int(period))))
    except (OSError, ValueError):
        try:  # cgroup v1
            quota = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read_text())
            period = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read_text())
            if quota > 0:
                limits.append(max(1, round(quota / period)))
        except (OSError, ValueError):
            pass
    return max(1, min(limits))


def env_int(name: str, default: int | None = None) -> int | None:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default
