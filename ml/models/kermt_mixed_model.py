"""
Host-side wrapper for the Tier-1 mixed-type KERMT trainer (path b).

``KermtModel`` (path a) shells out to KERMT's stock CLI, which takes one
``--dataset_type`` per run. This class is the *separate* path-b model the
2026-09-20 decision called for ("a **separate** ``KermtMixedModel``, so the stock
path stays un-regressed"): it trains a cluster that mixes classification and
regression columns in ONE run, with a type-correct masked loss and a selectable
weighting arm, by running the MARS trainer (``train.kermt_mixed``) *inside* the
unmodified KERMT container.

How a fit is assembled — every step before the last reuses KERMT's own scripts
-------------------------------------------------------------------------------
1. ``check_checkpoint.py --mode finetune_init``       (stock validator)
2. ``prepare_data.py --mode finetune``                (stock; user_provided split)
3. ``run_finetune_local.py --dry-run``                (stock; writes the *exact*
   ``main.py finetune`` argv into ``run.json`` and executes nothing)
4. stage ``ml/train/kermt_mixed/`` + ``spec.json`` under ``<data>/_mars_trainer`` and
   run ``python -m kermt_mixed.train_mixed`` with that argv's args.

So the hyperparameters, architecture and data paths are derived by KERMT, not
re-derived here. ``kermt_container.sh`` is never extended and KERMT is never
patched: the trainer reaches KERMT only through ``import kermt`` (provenance:
``trainer_provenance.json`` carries the sha256 of every staged file).

``dataset_type`` — a parse-time detail
--------------------------------------
KERMT's argument parser requires ``--dataset-type`` and validates ``--metric``
against it. The dry-run is therefore invoked with ``classification``/``auc``; the
trainer never reads ``args.dataset_type`` for anything (loss and output activation
are per column), so this has no effect on the run.

Prediction
----------
``predict`` returns ``(n, T)``: probabilities in classification columns, raw
units in regression columns (the trainer inverts its own per-column scaling).
``predict_logits`` returns logits in classification columns and the raw values in
regression columns — the score-matrix convention of
``eval.cluster_calibration`` — using the same ``logit(clip(p))`` definition as the
Tier-0 ``KermtModel.predict_logits`` so calibration stays comparable.

Not runnable without the KERMT checkout, its image and a GPU. Everything that can
be checked without them is covered by ``ml/tests/test_kermt_mixed_*.py``; the
rest is gates G1 and G2 (``documentation/AIMS/lab_session_tier1.md``).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

import numpy as np
from featurize.kermt_adapter import (
    assert_chirality_preserved,
    read_predictions_csv,
    write_finetune_csv,
    write_predict_csv,
)
from mars_contracts.endpoints import TaskType
from train.kermt_mixed import TRAINER_VERSION
from train.kermt_mixed.common import MODES, probability_to_logit

from models.base import MARSModel
from models.kermt_model import (
    _DEFAULT_KERMT_IMAGE,
    _ENV_KERMT_IMAGE,
    KermtConfig,
    _kermt_repo,
    _parse_json_stdout,
    _run_container,
)

MODEL_ID_MIXED = "mars-kermt-mixed-v1"

#: Files copied into the container, relative to ``ml/train/kermt_mixed``.
STAGED_FILES: tuple[str, ...] = (
    "__init__.py",
    "common.py",
    "scaling.py",
    "sampler.py",
    "losses.py",
    "gradnorm.py",
    "forward.py",
    "trainer.py",
    "metrics_hooks.py",
    "selfcheck.py",
    "train_mixed.py",
)
#: Present in the package but never staged: they run on the host only.
HOST_ONLY_FILES: tuple[str, ...] = ("gates.py", "tuning.py", "posthoc.py")
_TRAINER_SRC = Path(__file__).resolve().parents[1] / "train" / "kermt_mixed"
_STAGE_DIRNAME = "_mars_trainer"


def stage_trainer(dest_root: Path, *, src: Path | None = None) -> dict[str, Any]:
    """Copy the trainer package to ``<dest_root>/kermt_mixed`` and return provenance.

    The returned dict is what ``trainer_provenance.json`` records: the trainer
    version and the sha256 of every staged file, so a run can be tied to the exact
    trainer bytes even though it executed inside a container.
    """
    src = src or _TRAINER_SRC
    pkg = Path(dest_root) / "kermt_mixed"
    pkg.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}
    for name in STAGED_FILES:
        s = src / name
        if not s.exists():
            raise FileNotFoundError(f"trainer file missing: {s}")
        shutil.copy2(s, pkg / name)
        files[name] = hashlib.sha256(s.read_bytes()).hexdigest()
    return {"trainer_version": TRAINER_VERSION, "files": files}


class KermtMixedModel(MARSModel):
    """Mixed classification/regression KERMT fine-tune, one forward pass per molecule.

    Parameters
    ----------
    target_task_types:
        Ordered ``{endpoint_key: TaskType}``; its key order is the column order of
        every array this model reads or returns. At least one classification and
        one regression column is *not* required (a pure-type cluster is the G3
        parity configuration), but at least two targets are.
    loss_mode:
        ``fixed`` (stock reduction; parity gates), ``fixed_task`` (equal task
        weight — the ablation's fixed arm), ``kendall`` or ``gradnorm``. Required:
        the weighting arm is the experimental factor and has no default.
    min_per_task:
        Stratified-batch floor of labeled rows per task per batch (``0`` = stock
        shuffling). Required: its value is a tuning-protocol axis, not a constant.
    gradnorm_alpha, gradnorm_lr:
        Required when ``loss_mode == "gradnorm"`` and rejected otherwise. Also
        tuning-protocol axes (see ``gradnorm.py`` for what is and is not known).
    hyperparameter_source:
        Where every non-stock value came from: ``"stock-default"``, or
        ``"tuning:<protocol sha256 prefix>:<trial id>"``, or ``"parity-gate"``.
        Required and written into the run record so a number can never be
        separated from the provenance of its settings.
    """

    supports_loss_weighting: bool = True

    def __init__(
        self,
        target_task_types: dict[str, TaskType],
        pretrained_checkpoint: Path,
        *,
        loss_mode: str,
        min_per_task: int,
        hyperparameter_source: str,
        seed: int = 0,
        config: KermtConfig | None = None,
        gradnorm_alpha: float | None = None,
        gradnorm_lr: float | None = None,
        kermt_repo: Path | None = None,
        docker_image: str | None = None,
        work_dir: Path | None = None,
    ) -> None:
        if not target_task_types:
            raise ValueError("target_task_types must be non-empty")
        if loss_mode not in MODES:
            raise ValueError(f"loss_mode must be one of {MODES}, got {loss_mode!r}")
        if len(target_task_types) == 1 and loss_mode in ("kendall", "gradnorm"):
            raise ValueError(
                f"loss_mode={loss_mode!r} needs >= 2 targets (a single task has nothing to "
                "balance). A single target is supported only for the G3 parity comparison, "
                "under 'fixed' or 'fixed_task'."
            )
        if min_per_task < 0:
            raise ValueError("min_per_task must be >= 0")
        if not hyperparameter_source:
            raise ValueError("hyperparameter_source must name where the settings came from")
        if loss_mode == "gradnorm" and (gradnorm_alpha is None or gradnorm_lr is None):
            raise ValueError("loss_mode='gradnorm' requires gradnorm_alpha and gradnorm_lr")
        if loss_mode != "gradnorm" and (gradnorm_alpha is not None or gradnorm_lr is not None):
            raise ValueError("gradnorm_alpha/gradnorm_lr are only valid with loss_mode='gradnorm'")
        self._ttypes = dict(target_task_types)
        self._names = list(self._ttypes)
        self._pretrained_checkpoint = Path(pretrained_checkpoint)
        if not self._pretrained_checkpoint.exists():
            raise FileNotFoundError(
                f"pretrained checkpoint not found: {self._pretrained_checkpoint}"
            )
        self._seed = seed
        self._cfg = config or KermtConfig()
        self._loss_mode = loss_mode
        self._min_per_task = min_per_task
        self._gn = (
            {"alpha": gradnorm_alpha, "lr": gradnorm_lr} if loss_mode == "gradnorm" else None
        )
        self._hp_source = hyperparameter_source
        self._kermt_repo = kermt_repo or _kermt_repo()
        self._docker_image = docker_image or os.environ.get(_ENV_KERMT_IMAGE, _DEFAULT_KERMT_IMAGE)
        self._work_dir = Path(work_dir) if work_dir is not None else None
        self._finetuned_checkpoint: Path | None = None
        self.fit_summary: dict[str, Any] | None = None

    # -- MARSModel surface ----------------------------------------------------

    @property
    def model_id(self) -> str:
        return MODEL_ID_MIXED

    @property
    def task_type(self) -> TaskType:
        raise TypeError(
            "KermtMixedModel has no single task type; read target_task_types. "
            "(MARSModel.task_type is single-valued by design — see models.base.)"
        )

    @property
    def target_names(self) -> list[str]:
        return list(self._names)

    @property
    def target_task_types(self) -> dict[str, TaskType]:
        return dict(self._ttypes)

    @property
    def is_fitted(self) -> bool:
        return self._finetuned_checkpoint is not None

    @property
    def loss_mode(self) -> str:
        return self._loss_mode

    # -- helpers --------------------------------------------------------------

    def _spec(self) -> dict[str, Any]:
        return {
            "trainer_version": TRAINER_VERSION,
            "target_names": self._names,
            "task_types": [self._ttypes[n].value for n in self._names],
            "loss": {"mode": self._loss_mode},
            "min_per_task": self._min_per_task,
            "gradnorm": self._gn,
            "hyperparameter_source": self._hp_source,
            "seed": self._seed,
        }

    def _stage(self, data_dir: Path) -> dict[str, Any]:
        root = data_dir / _STAGE_DIRNAME
        prov = stage_trainer(root)
        (root / "spec.json").write_text(
            json.dumps(self._spec(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return prov

    def _flags(self) -> str:
        c = self._cfg
        mapping = {
            "epochs": c.epochs,
            "batch-size": c.batch_size,
            "init-lr": c.init_lr,
            "max-lr": c.max_lr,
            "final-lr": c.final_lr,
            "dropout": c.dropout,
            "bond-drop-rate": c.bond_drop_rate,
            "dist-coff": c.dist_coff,
            "ffn-hidden-size": c.ffn_hidden_size,
            "ffn-num-layers": c.ffn_num_layers,
        }
        flags = "".join(f" --{k} {v}" for k, v in mapping.items() if v is not None)
        if len(self._names) == 1:
            # Same as KermtModel for a single task: no per-task heads, so the G3
            # single-task comparison is architecture-for-architecture.
            return flags
        # Per-task heads are mandatory for a multi-column run (the trainer refuses
        # without): a regression and a classification column must not share one
        # output layer, and GradNorm needs a layer shared *by* the heads.
        n_layers = c.extra_finetune_flags.get("ffn_num_task_specific_layers", 1)
        hidden = c.extra_finetune_flags.get("ffn_task_specific_hidden_size", 64)
        return (
            flags
            + f" --ffn-num-task-specific-layers {n_layers}"
            + f" --ffn-task-specific-hidden-size {hidden}"
        )

    def _targets_dict(self, y: np.ndarray) -> dict[str, np.ndarray]:
        y = np.asarray(y, dtype=float)
        if y.ndim != 2 or y.shape[1] != len(self._names):
            raise ValueError(f"y must be 2-D (n, {len(self._names)}), got {y.shape}")
        return {name: y[:, i] for i, name in enumerate(self._names)}

    def _validate_checkpoint(self, ckpt: Path, mode: str) -> None:
        proc = _run_container(
            self._kermt_repo,
            self._docker_image,
            ckpt=ckpt,
            command=f"python agent/scripts/check_checkpoint.py --mode {mode} --ckpt /ckpt",
        )
        out = _parse_json_stdout(proc, context=f"check_checkpoint.py --mode {mode}")
        if not out.get("ok"):
            raise RuntimeError(f"KERMT rejected the checkpoint ({mode}): {out.get('errors')}")

    @staticmethod
    def _require_manifest(proc: Any, manifest: Path, what: str) -> None:
        if proc.returncode != 0 or not manifest.exists():
            raise RuntimeError(
                f"{what} failed (exit {proc.returncode}).\n"
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
            )

    # -- fit ------------------------------------------------------------------

    def fit(
        self,
        X_train: list[str],
        y_train: np.ndarray,
        *,
        X_val: list[str] | None = None,
        y_val: np.ndarray | None = None,
        run_dir: Path | None = None,
    ) -> None:
        if X_val is None or y_val is None:
            raise ValueError("KermtMixedModel.fit requires X_val/y_val (epoch selection)")
        for smi in X_train[: min(len(X_train), 200)]:
            assert_chirality_preserved(smi)

        work = Path(run_dir) if run_dir is not None else self._work_dir
        if work is None:
            raise ValueError("fit() needs run_dir (or work_dir set in __init__)")
        self._work_dir = work
        data_dir = work / "input"
        data_dir.mkdir(parents=True, exist_ok=True)

        # As KermtModel.fit: val doubles as the CLI's mandatory "test" file. The
        # trainer never reads it; MARS scores the real test split via predict().
        tr = write_finetune_csv(data_dir / "train.csv", list(X_train), self._targets_dict(y_train))
        va = write_finetune_csv(data_dir / "val.csv", list(X_val), self._targets_dict(y_val))
        te = write_finetune_csv(
            data_dir / "test_placeholder.csv", list(X_val), self._targets_dict(y_val)
        )

        self._validate_checkpoint(self._pretrained_checkpoint, "finetune_init")

        prep = (
            "python agent/scripts/prepare_data.py --mode finetune "
            f"--csv /data/{tr.name} --val-csv /data/{va.name} --test-csv /data/{te.name} "
            f"--out /runs/data --targets {' '.join(self._names)}"
        )
        proc = _run_container(
            self._kermt_repo, self._docker_image, data=data_dir, run_dir=work, command=prep
        )
        self._require_manifest(proc, work / "data" / "prepare_data.json", "prepare_data.py (finetune)")

        dry = (
            "python agent/scripts/run_finetune_local.py --dry-run "
            "--ckpt /ckpt --prepare-manifest /runs/data/prepare_data.json "
            "--dataset-type classification --metric auc --out /runs "
            f"--gpus {self._cfg.gpu} --seed {self._seed}" + self._flags()
        )
        proc = _run_container(
            self._kermt_repo, self._docker_image,
            ckpt=self._pretrained_checkpoint, run_dir=work, command=dry,
        )
        run_json = work / "run.json"
        if not run_json.exists():
            raise RuntimeError(
                f"run_finetune_local.py --dry-run produced no run.json (exit {proc.returncode}).\n"
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
            )

        prov = self._stage(data_dir)
        (work / "trainer_provenance.json").write_text(
            json.dumps(prov, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        cmd = (
            f"CUDA_VISIBLE_DEVICES={self._cfg.gpu} CUBLAS_WORKSPACE_CONFIG=:4096:8 "
            f"PYTHONPATH=/data/{_STAGE_DIRNAME}:${{PYTHONPATH:-}} "
            "python -u -m kermt_mixed.train_mixed --mode fit "
            f"--run-json /runs/run.json --spec /data/{_STAGE_DIRNAME}/spec.json"
        )
        proc = _run_container(
            self._kermt_repo, self._docker_image,
            data=data_dir, ckpt=self._pretrained_checkpoint, run_dir=work, command=cmd,
        )
        logs = work / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        (logs / "mixed_fit.stdout.log").write_text(proc.stdout or "", encoding="utf-8")
        (logs / "mixed_fit.stderr.log").write_text(proc.stderr or "", encoding="utf-8")

        ckpt = work / "ckpt" / "fold_0" / "model_0" / "model.pt"
        try:
            result = _parse_json_stdout(proc, context="train_mixed --mode fit")
        except RuntimeError:
            result = {"ok": False, "errors": [f"no JSON on stdout (exit {proc.returncode})"]}
        if proc.returncode != 0 or not result.get("ok") or not ckpt.exists():
            raise RuntimeError(
                f"mixed trainer failed (exit {proc.returncode}): {result.get('errors')}\n"
                f"stderr tail:\n{(proc.stderr or '')[-4000:]}"
            )
        self.fit_summary = result.get("summary")
        self._finetuned_checkpoint = ckpt

    # -- predict --------------------------------------------------------------

    def predict(self, X: list[str], *, run_dir: Path | None = None) -> np.ndarray:
        if not self.is_fitted:
            raise RuntimeError("Model has not been fitted. Call fit() first.")
        work = Path(run_dir) if run_dir is not None else self._work_dir
        if work is None:
            raise ValueError("predict() needs run_dir (or work_dir set at fit time)")
        digest = hashlib.sha256("\n".join(X).encode()).hexdigest()[:12]
        pdir = work / f"predict_{digest}"
        data_dir = pdir / "input"
        data_dir.mkdir(parents=True, exist_ok=True)
        csv_path = write_predict_csv(data_dir / "smiles.csv", list(X))

        assert self._finetuned_checkpoint is not None
        self._validate_checkpoint(self._finetuned_checkpoint, "inference")

        prep = (
            "python agent/scripts/prepare_data.py --mode inference "
            f"--csv /data/{csv_path.name} --out /runs/data"
        )
        proc = _run_container(
            self._kermt_repo, self._docker_image, data=data_dir, run_dir=pdir, command=prep
        )
        self._require_manifest(proc, pdir / "data" / "prepare_data.json", "prepare_data.py (inference)")

        dry = (
            "python agent/scripts/run_inference.py --dry-run --ckpt /ckpt "
            "--prepare-manifest /runs/data/prepare_data.json --out /runs "
            f"--gpus {self._cfg.gpu} --seed {self._seed}"
        )
        proc = _run_container(
            self._kermt_repo, self._docker_image,
            ckpt=self._finetuned_checkpoint, run_dir=pdir, command=dry,
        )
        if not (pdir / "run.json").exists():
            raise RuntimeError(
                f"run_inference.py --dry-run produced no run.json (exit {proc.returncode}).\n"
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
            )

        self._stage(data_dir)
        cmd = (
            f"CUDA_VISIBLE_DEVICES={self._cfg.gpu} CUBLAS_WORKSPACE_CONFIG=:4096:8 "
            f"PYTHONPATH=/data/{_STAGE_DIRNAME}:${{PYTHONPATH:-}} "
            "python -u -m kermt_mixed.train_mixed --mode predict "
            f"--run-json /runs/run.json --spec /data/{_STAGE_DIRNAME}/spec.json "
            "--checkpoint /ckpt --out /runs/out"
        )
        proc = _run_container(
            self._kermt_repo, self._docker_image,
            data=data_dir, ckpt=self._finetuned_checkpoint, run_dir=pdir, command=cmd,
        )
        out_csv = pdir / "out" / "predictions.csv"
        if proc.returncode != 0 or not out_csv.exists():
            raise RuntimeError(
                f"mixed predict failed (exit {proc.returncode}).\n"
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
            )
        preds = read_predictions_csv(out_csv, self._names)
        out = np.stack([preds[n] for n in self._names], axis=1)
        if out.shape[0] != len(X):
            raise RuntimeError(f"expected {len(X)} prediction rows, got {out.shape[0]}")
        return out

    def predict_logits(self, X: list[str], *, run_dir: Path | None = None) -> np.ndarray:
        """Classification columns -> logit(clip(p)); regression columns unchanged."""
        out = self.predict(X, run_dir=run_dir).copy()
        for j, name in enumerate(self._names):
            if self._ttypes[name] is TaskType.CLASSIFICATION:
                out[:, j] = probability_to_logit(out[:, j])
        return out

    # -- persistence ----------------------------------------------------------

    def save(self, path: Path) -> None:
        if not self.is_fitted:
            raise RuntimeError("Model has not been fitted.")
        assert self._finetuned_checkpoint is not None
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self._finetuned_checkpoint, path / "model.pt")
        mixed_meta = self._finetuned_checkpoint.parent / "mixed_meta.json"
        if mixed_meta.exists():
            shutil.copy2(mixed_meta, path / "mixed_meta.json")
        meta = {
            "model_id": self.model_id,
            "trainer_version": TRAINER_VERSION,
            "seed": self._seed,
            "loss_mode": self._loss_mode,
            "min_per_task": self._min_per_task,
            "gradnorm": self._gn,
            "hyperparameter_source": self._hp_source,
            "target_names": self._names,
            "task_types": [self._ttypes[n].value for n in self._names],
            "pretrained_checkpoint": str(self._pretrained_checkpoint),
            "fit_summary": self.fit_summary,
        }
        (path / "metadata.json").write_text(
            json.dumps(meta, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )

    @classmethod
    def from_finetuned(
        cls,
        finetuned_checkpoint: Path,
        target_task_types: dict[str, TaskType],
        pretrained_checkpoint: Path,
        *,
        work_dir: Path,
        **kwargs: Any,
    ) -> KermtMixedModel:
        """Wrap an existing fine-tuned checkpoint for inference only.

        This is how gate G1 runs the mixed forward pass on a stock Tier-0 model
        (``toxicity__cls``): same weights, MARS's code path. ``target_task_types``
        must list the checkpoint's columns in its training order.
        """
        # Inference only: the training-time settings below are never used.
        kwargs.setdefault("loss_mode", "fixed")
        kwargs.setdefault("min_per_task", 0)
        kwargs.setdefault("hyperparameter_source", "inference-only")
        inst = cls(target_task_types, pretrained_checkpoint, work_dir=work_dir, **kwargs)
        ckpt = Path(finetuned_checkpoint)
        if not ckpt.exists():
            raise FileNotFoundError(f"finetuned checkpoint not found: {ckpt}")
        inst._finetuned_checkpoint = ckpt
        return inst

    @classmethod
    def load(cls, path: Path) -> KermtMixedModel:
        path = Path(path)
        meta = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
        inst = cls(
            {n: TaskType(t) for n, t in zip(meta["target_names"], meta["task_types"], strict=True)},
            Path(meta["pretrained_checkpoint"]),
            seed=int(meta["seed"]),
            loss_mode=meta["loss_mode"],
            min_per_task=int(meta["min_per_task"]),
            hyperparameter_source=meta["hyperparameter_source"],
            gradnorm_alpha=(meta.get("gradnorm") or {}).get("alpha"),
            gradnorm_lr=(meta.get("gradnorm") or {}).get("lr"),
        )
        inst._finetuned_checkpoint = path / "model.pt"
        inst.fit_summary = meta.get("fit_summary")
        return inst
