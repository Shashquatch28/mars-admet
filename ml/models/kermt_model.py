"""
KERMT model wrapper for MARS ADMET endpoints (blueprint Module 4, M2 KERMT track).

Architecture (per the 2026-09-18 KERMT integration decision — see
``documentation/AIMS/decisions.md``):

    MARS standardized SMILES + labels
        -> ml.featurize.kermt_adapter (CSV contract, chirality verification)
        -> official NVIDIA-BioNeMo/KERMT CLI, run inside the `kermt:latest`
           Docker container (isolation: KERMT's environment.yml pins
           rdkit==2025.9.1 + an unconditional `import cuik_molmaker` at
           module load time in kermt/data/molgraph.py and kermtdataset.py —
           NOT actually optional despite `--use_cuikmolmaker_featurization`
           defaulting to False — so KERMT cannot be imported into MARS's own
           .venv without either building cuik_molmaker from source or
           accepting rdkit==2025.9.1 in place of MARS's own >=2026.3.1 pin.
           The container sidesteps both: it ships NVIDIA's own tested
           cuik_molmaker build and its own isolated rdkit, with zero
           shared-environment surface against ml/.venv.)
        -> this wrapper (KermtModel, implements models.base.MARSModel)
        -> existing MARS eval/calibration/tracking (unchanged)

KERMT is NOT imported in-process anywhere in this file — every actual
model operation (checkpoint load, forward/backward, finetuning, inference)
happens inside the container via subprocess calls to
``agent/scripts/kermt_container.sh`` in the vendored KERMT checkout. This
file only prepares CSVs, invokes documented CLI entry points exactly as
their own SKILL.md files specify, and parses the resulting JSON/CSV back
into MARS's numpy-array model interface. No KERMT CLI argument here is
invented — every flag traces to a script in the KERMT repo (see the
docstring of each method for the exact source).

Known, verified limitation — NOT worked around here
-----------------------------------------------------
KERMT's own ``main.py finetune`` takes a single ``--dataset_type`` value
for the whole run (``kermt/util/parsing.py`` L598: ``assert
args.dataset_type is not None``; L613/618 branch on it as one scalar; used
verbatim to pick ONE loss function in ``task/train.py`` via
``get_loss_func(args, model)``). MARS's blueprint mixed-type multi-task
clusters — Metabolism (3 classification + 1 regression) and Absorption &
Distribution (4 regression + 3 classification) — therefore CANNOT be
finetuned as a single heterogeneous ``main.py finetune`` call against the
stock CLI. ``KermtModel`` supports:
  * single-task (any one endpoint, classification or regression), and
  * multi-task clusters where every target shares the same task type
    (e.g. Toxicity: hERG + AMES, both classification),
via KERMT's native masked multi-task head (``ffn_num_task_specific_layers``)
on top of a per-task masked loss in ``task/train.py``'s ``train()``:
``loss = loss_func(preds, targets) * class_weights * mask``.

EQUAL WEIGHTING ONLY — this path cannot do Kendall or GradNorm
---------------------------------------------------------------
KERMT *does* ship a Kendall/homoscedastic-uncertainty ``MTLLoss``
(``kermt/util/loss.py``, ``precision = 0.5*exp(-2*log_sigma)``), but
``task/train.py`` only builds it under ``if args.use_mtl_loss:`` and the
wrapper script MARS actually invokes — ``agent/scripts/run_finetune_local.py``
— **never forwards that flag** (it is absent from its ``TRAINING_FLAGS`` /
``TASK_FLAGS`` / ``FFN_FLAGS`` passthrough tuples) and uses strict
``parse_args``, so passing it is an unrecognized-argument failure rather than
a no-op. Every run through this class is therefore **equal-weighted**, which
is exactly blueprint Module 4's mandatory fixed/equal baseline arm.

Kendall and GradNorm — for pure-type clusters as well as mixed ones — come
from the MARS-owned Tier-1 trainer, not from here. See
``documentation/AIMS/decisions.md`` (2026-09-20, finding 2).

Mixed-type clusters
-------------------
KERMT's CLI takes one ``--dataset_type`` per run and ``KermtFinetuneTask`` has
a single ``self.classification`` bool, so a cluster mixing classification and
regression cannot be trained here at all. That is resolved at the MARS level by
the three-tier ladder (``decisions.md`` 2026-09-20), **not** by forking KERMT.
This class deliberately stays the stock-CLI path (a); mixed-type training lives
in ``models.kermt_mixed_model``. Constructing ``KermtModel`` with targets of
differing task types raises — see ``_assert_homogeneous_targets``.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from featurize.kermt_adapter import (
    assert_chirality_preserved,
    read_predictions_csv,
    write_finetune_csv,
    write_predict_csv,
)
from mars_contracts.endpoints import ENDPOINT_METADATA, Endpoint, TaskType

from models.base import MARSModel

MODEL_ID_SINGLE = "mars-kermt-single-v1"
MODEL_ID_MULTITASK = "mars-kermt-multitask-v1"

_ENV_KERMT_REPO = "MARS_KERMT_REPO"
_ENV_KERMT_IMAGE = "MARS_KERMT_IMAGE"
_DEFAULT_KERMT_IMAGE = "kermt:latest"


class KermtUnavailableError(RuntimeError):
    """Raised when the KERMT repo checkout or its docker image aren't ready."""


def _resolved_target_task_types(target_names: list[str]) -> dict[str, TaskType]:
    """Task type for each target name that resolves to a known endpoint.

    Names that are not ``Endpoint`` members are skipped rather than rejected:
    the Tier-2 ordinal path deliberately uses synthetic column names such as
    ``solubility_logs__gt3``, which are binary by construction and carry no
    endpoint metadata of their own.
    """
    out: dict[str, TaskType] = {}
    for name in target_names:
        try:
            ep = Endpoint(name)
        except ValueError:
            continue
        out[name] = ENDPOINT_METADATA[ep]["task_type"]
    return out


def _assert_homogeneous_targets(target_names: list[str], task_type: TaskType) -> None:
    """Reject target sets this stock-CLI path cannot honestly train.

    Two distinct failure modes, both of which would otherwise produce
    plausible-looking wrong numbers rather than an error:

    1. **Mixed task types in one target list.** KERMT applies one
       ``--dataset_type`` and one ``self.classification`` bool to the whole
       output tensor, so a regression column in a classification run comes back
       squashed through a sigmoid.
    2. **Declared ``task_type`` disagreeing with the endpoints' real types** —
       same consequence, arrived at from the other direction.

    The module docstring has claimed this guard existed since the wrapper was
    written; it did not until 2026-09-20.
    """
    resolved = _resolved_target_task_types(target_names)
    if not resolved:
        return

    distinct = set(resolved.values())
    if len(distinct) > 1:
        by_type: dict[str, list[str]] = {}
        for name, tt in resolved.items():
            by_type.setdefault(tt.value, []).append(name)
        raise ValueError(
            "KermtModel cannot train mixed classification/regression targets: "
            f"{ {k: sorted(v) for k, v in sorted(by_type.items())} }. "
            "KERMT's stock CLI takes one --dataset_type per run. Use a "
            "type-homogeneous subgroup (configs.clusters.type_homogeneous_subgroups) "
            "or the mixed-type trainer (models.kermt_mixed_model)."
        )

    actual = distinct.pop()
    if actual is not task_type:
        raise ValueError(
            f"task_type={task_type.value!r} was declared but targets "
            f"{sorted(resolved)} are {actual.value!r} endpoints. This would apply "
            "the wrong loss and the wrong output activation."
        )


def _kermt_repo() -> Path:
    raw = os.environ.get(_ENV_KERMT_REPO)
    if not raw:
        raise KermtUnavailableError(
            f"{_ENV_KERMT_REPO} is not set. KermtModel shells out to the official "
            "github.com/NVIDIA-BioNeMo/KERMT CLI (v2.0.0) inside its own docker "
            "container — it does not vendor or reimplement KERMT. Clone the repo "
            "(git clone --branch v2.0.0 https://github.com/NVIDIA-BioNeMo/KERMT) "
            f"and set {_ENV_KERMT_REPO}=<path to that checkout>."
        )
    repo = Path(raw)
    helper = repo / "agent" / "scripts" / "kermt_container.sh"
    if not helper.exists():
        raise KermtUnavailableError(
            f"{_ENV_KERMT_REPO}={raw} does not look like a KERMT checkout "
            f"(missing {helper})."
        )
    return repo


@dataclass
class KermtConfig:
    """Hyperparameters passed through to `main.py finetune` (agent/config/defaults_finetune.json
    fields the wrapper knows how to override — anything omitted uses KERMT's own default)."""

    epochs: int | None = None
    batch_size: int | None = None
    init_lr: float | None = None
    max_lr: float | None = None
    final_lr: float | None = None
    dropout: float | None = None
    bond_drop_rate: float | None = None
    dist_coff: float | None = None
    gpu: int = 0
    metric: str | None = None
    ffn_hidden_size: int | None = None
    ffn_num_layers: int | None = None
    extra_finetune_flags: dict[str, Any] = field(default_factory=dict)


def _run_container(
    kermt_repo: Path,
    image: str,
    *,
    data: Path | None = None,
    ckpt: Path | None = None,
    run_dir: Path | None = None,
    command: str,
) -> subprocess.CompletedProcess[str]:
    """Invoke `agent/scripts/kermt_container.sh run [mounts] -- "<command>"` and
    return the completed process (stdout/stderr captured as text).

    Mirrors exactly the mount-flag / `--` separator contract documented in
    `kermt_container.sh`'s own header comment and every `kermt-*` SKILL.md.
    """
    helper = kermt_repo / "agent" / "scripts" / "kermt_container.sh"
    argv: list[str] = [str(helper), "run"]
    if data is not None:
        argv += ["--data", str(data)]
    if ckpt is not None:
        argv += ["--ckpt", str(ckpt)]
    if run_dir is not None:
        argv += ["--run-dir", str(run_dir)]
    argv += ["--", command]

    env = os.environ.copy()
    env["KERMT_REPO"] = str(kermt_repo)
    env["KERMT_IMAGE"] = image
    return subprocess.run(argv, env=env, capture_output=True, text=True)


def _parse_json_stdout(proc: subprocess.CompletedProcess[str], *, context: str) -> dict[str, Any]:
    """`check_checkpoint.py` / `check_data.py` / `run_*_local.py` all print a single
    JSON document to stdout (see their own docstrings). Container-launcher noise
    (conda activation banners, apt output) goes to stderr, not stdout, by
    convention of `kermt_container.sh`'s `conda run --no-capture-output` — but
    parse defensively (last JSON-looking line) since a crash before the script
    even runs would print a bash error to stdout instead.
    """
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        pass
    # The scripts pretty-print (`json.dumps(..., indent=2)`) as the LAST thing
    # they do, but stdout is prefixed with container/CUDA banner text — so a
    # single json.loads(whole stdout) fails, and so does "try each line" since
    # a multi-line pretty JSON has no single self-contained line. Instead, try
    # parsing from every line that looks like the start of a JSON object,
    # latest first, through the end of stdout.
    lines = proc.stdout.splitlines()
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip().startswith("{"):
            candidate = "\n".join(lines[i:])
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
    raise RuntimeError(
        f"{context}: expected JSON on stdout, got none.\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )


class KermtModel(MARSModel):
    """KERMT graph-transformer classifier/regressor, driven via the official
    NVIDIA-BioNeMo/KERMT CLI inside its own docker container.

    Parameters
    ----------
    task_type:
        Classification or regression. All ``target_names`` must share this
        task type — KERMT's stock loss function is one type per run (see
        module docstring); mixed clusters are not supported here.
    pretrained_checkpoint:
        Path to the KERMT pretrain checkpoint to finetune from (e.g.
        ``ml/data/checkpoints/kermt/NV-KERMT-70M-v2/kermt_contrastive_v2.0.pt``).
        Must be a pretrain ckpt per `check_checkpoint.py --mode
        finetune_init` (grover_base / cmim / hybrid) — an already-finetuned
        ckpt is rejected, matching the upstream `kermt-finetune` contract.
    target_names:
        Endpoint key(s) this instance predicts. Length 1 = single-task
        (``MODEL_ID_SINGLE``); length > 1 = multi-task cluster
        (``MODEL_ID_MULTITASK``), using KERMT's per-target FFN heads
        (``ffn_num_task_specific_layers``) and its native Kendall/MTL loss.
    seed, config:
        Training seed and hyperparameter overrides (see ``KermtConfig``).
    kermt_repo, docker_image:
        Override discovery of the vendored KERMT checkout / built image;
        default to the ``MARS_KERMT_REPO`` / ``MARS_KERMT_IMAGE`` env vars.
    """

    def __init__(
        self,
        task_type: TaskType,
        pretrained_checkpoint: Path,
        target_names: list[str],
        *,
        seed: int = 0,
        config: KermtConfig | None = None,
        kermt_repo: Path | None = None,
        docker_image: str | None = None,
        work_dir: Path | None = None,
    ) -> None:
        if not target_names:
            raise ValueError("target_names must be non-empty")
        _assert_homogeneous_targets(list(target_names), task_type)
        self._task_type = task_type
        self._pretrained_checkpoint = Path(pretrained_checkpoint)
        if not self._pretrained_checkpoint.exists():
            raise FileNotFoundError(
                f"pretrained checkpoint not found: {self._pretrained_checkpoint}"
            )
        self._target_names = list(target_names)
        self._seed = seed
        self._cfg = config or KermtConfig()
        self._kermt_repo = kermt_repo or _kermt_repo()
        self._docker_image = docker_image or os.environ.get(_ENV_KERMT_IMAGE, _DEFAULT_KERMT_IMAGE)
        self._work_dir = Path(work_dir) if work_dir is not None else None
        self._finetuned_checkpoint: Path | None = None

    @property
    def model_id(self) -> str:
        return MODEL_ID_SINGLE if len(self._target_names) == 1 else MODEL_ID_MULTITASK

    @property
    def task_type(self) -> TaskType:
        return self._task_type

    @property
    def target_names(self) -> list[str]:
        """Target column names, in the order predictions are returned."""
        return list(self._target_names)

    @property
    def target_task_types(self) -> dict[str, TaskType]:
        """Task type per target. Homogeneous here by construction (see the guard)."""
        return {name: self._task_type for name in self._target_names}

    #: This path shells out to KERMT's stock CLI, which cannot enable ``MTLLoss``
    #: (see the module docstring). Callers selecting a loss-balancing arm must
    #: check this rather than assume Kendall weighting is available.
    supports_loss_weighting: bool = False

    @property
    def is_fitted(self) -> bool:
        return self._finetuned_checkpoint is not None

    def _dataset_type_flag(self) -> str:
        return "classification" if self._task_type == TaskType.CLASSIFICATION else "regression"

    def _work(self) -> Path:
        if self._work_dir is None:
            raise RuntimeError("work_dir was not set; call fit() with a run directory")
        return self._work_dir

    # ------------------------------------------------------------------
    # fit()
    # ------------------------------------------------------------------

    def fit(
        self,
        X_train: list[str],
        y_train: np.ndarray,
        *,
        X_val: list[str] | None = None,
        y_val: np.ndarray | None = None,
        run_dir: Path | None = None,
    ) -> None:
        """Finetune the pretrained KERMT checkpoint on (X_train, y_train).

        `main.py finetune` requires EITHER both `--val-csv`/`--test-csv` OR
        neither (agent/scripts/prepare_data.py `_prepare_finetune`: "for
        finetune mode, either provide BOTH ... or NEITHER ... Got one but
        not both."). MARS's own protocol never lets a held-out test set
        touch training — so this wrapper passes MARS's val fold as BOTH
        `--val-csv` and `--test-csv`. KERMT's own internal
        `ckpt/fold_0/test_result.csv` is therefore a second look at the same
        val fold, not a real test-set score, and MUST NOT be read as MARS's
        test metric — MARS computes its own test metrics separately, later,
        via `predict()` on the real held-out test set (see module docstring
        and `ml/eval/evaluate.py`).

        For multi-task (`len(target_names) > 1`), `y_train`/`y_val` must be
        2-D arrays shaped `(n_samples, n_targets)` in `target_names` order;
        `np.nan` marks a missing label for that (molecule, task) pair and is
        written as an empty CSV cell (KERMT's own missing-label convention —
        see `ml/featurize/kermt_adapter.py`), consumed as a masked-out term
        in `task/train.py`'s `loss = loss_func(...) * class_weights * mask`.
        """
        if X_val is None or y_val is None:
            raise ValueError(
                "KermtModel.fit requires X_val/y_val (KERMT's finetune CLI needs a "
                "val split; MARS never trains without one — see docstring)."
            )
        for smi in X_train[: min(len(X_train), 200)]:
            assert_chirality_preserved(smi)

        work = Path(run_dir) if run_dir is not None else self._work_dir
        if work is None:
            raise ValueError("fit() needs run_dir (or work_dir set in __init__)")
        self._work_dir = work
        data_dir = work / "input"
        data_dir.mkdir(parents=True, exist_ok=True)

        targets_train = self._targets_dict(y_train)
        targets_val = self._targets_dict(y_val)

        train_csv = write_finetune_csv(data_dir / "train.csv", list(X_train), targets_train)
        val_csv = write_finetune_csv(data_dir / "val.csv", list(X_val), targets_val)
        # Deliberate duplication of val as "test" — see docstring above.
        test_csv = write_finetune_csv(data_dir / "test_placeholder.csv", list(X_val), targets_val)

        # 1. Validate the checkpoint (agent/skills/kermt-finetune/SKILL.md step 3).
        validator = self._check_checkpoint(mode="finetune_init")
        if not validator.get("ok"):
            raise RuntimeError(f"KERMT rejected the pretrain checkpoint: {validator.get('errors')}")

        # 2. Prepare data (SKILL.md step 5): both val+test given -> split_method=user_provided.
        prep_dir = work / "data"
        prep_cmd = (
            f"python agent/scripts/prepare_data.py --mode finetune "
            f"--csv /data/{train_csv.name} --val-csv /data/{val_csv.name} "
            f"--test-csv /data/{test_csv.name} --out /runs/data "
            f"--targets {' '.join(self._target_names)}"
        )
        proc = _run_container(
            self._kermt_repo, self._docker_image,
            data=data_dir, run_dir=work, command=prep_cmd,
        )
        prep_manifest_host = prep_dir / "prepare_data.json"
        if proc.returncode != 0 or not prep_manifest_host.exists():
            raise RuntimeError(
                f"prepare_data.py (finetune) failed (exit {proc.returncode}).\n"
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
            )

        # 3. Launch the finetune runner (SKILL.md step 8; blocking, not detached —
        #    the smoke tests and single/multi-task fits here are short enough
        #    that MARSModel.fit()'s synchronous contract is appropriate).
        ffn_mtl_flags = ""
        if len(self._target_names) > 1:
            n_layers = self._cfg.extra_finetune_flags.get("ffn_num_task_specific_layers", 1)
            hidden = self._cfg.extra_finetune_flags.get("ffn_task_specific_hidden_size", 64)
            ffn_mtl_flags = (
                f" --ffn-num-task-specific-layers {n_layers} "
                f"--ffn-task-specific-hidden-size {hidden}"
            )
        finetune_cmd = (
            f"python agent/scripts/run_finetune_local.py "
            f"--ckpt /ckpt --prepare-manifest /runs/data/prepare_data.json "
            f"--dataset-type {self._dataset_type_flag()} --out /runs "
            f"--gpus {self._cfg.gpu} --seed {self._seed}"
            + self._hyperparam_flags()
            + ffn_mtl_flags
        )
        proc = _run_container(
            self._kermt_repo, self._docker_image,
            ckpt=self._pretrained_checkpoint, run_dir=work, command=finetune_cmd,
        )
        run_json_path = work / "run.json"
        if not run_json_path.exists():
            raise RuntimeError(
                f"run_finetune_local.py produced no run.json (exit {proc.returncode}).\n"
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
            )
        run_manifest = json.loads(run_json_path.read_text())
        if run_manifest.get("status") != "ok":
            log_path = work / "logs" / "finetune.log"
            log_tail = log_path.read_text()[-4000:] if log_path.exists() else "(no log file)"
            raise RuntimeError(
                f"KERMT finetune failed (status={run_manifest.get('status')}, "
                f"exit_code={run_manifest.get('exit_code')}).\nlog tail:\n{log_tail}"
            )

        # run_manifest["save_dir"] is a CONTAINER-side path (e.g. "/runs/ckpt",
        # since we pass `--out /runs` to run_finetune_local.py) — not usable
        # directly from the host. `--run-dir work` bind-mounts `work` at
        # `/runs` (kermt_container.sh), so the host equivalent is always
        # `work / "ckpt"`, independent of whatever string run.json recorded.
        # (Found live during the 2026-09-18 AMES smoke test: the naive
        # `Path(run_manifest["save_dir"])` produced a nonexistent host path
        # even though the finetune itself had actually succeeded.)
        ckpt_path = work / "ckpt" / "fold_0" / "model_0" / "model.pt"
        if not ckpt_path.exists():
            raise RuntimeError(f"expected finetuned checkpoint not found at {ckpt_path}")
        self._finetuned_checkpoint = ckpt_path

    def _hyperparam_flags(self) -> str:
        flags = ""
        mapping = {
            "epochs": self._cfg.epochs,
            "batch-size": self._cfg.batch_size,
            "init-lr": self._cfg.init_lr,
            "max-lr": self._cfg.max_lr,
            "final-lr": self._cfg.final_lr,
            "dropout": self._cfg.dropout,
            "bond-drop-rate": self._cfg.bond_drop_rate,
            "dist-coff": self._cfg.dist_coff,
            # `agent/config/defaults_finetune.json`'s task.metric default is
            # "mae" unconditionally (it targets the regression common case per
            # its own _about) — passing that through for a classification task
            # trips kermt/util/parsing.py's dataset_type/metric validation
            # (found live during the 2026-09-18 AMES smoke test: "Metric 'mae'
            # invalid for dataset type 'classification'"). Always resolve an
            # explicit, task_type-correct metric rather than letting the
            # regression-oriented default config value leak through.
            "metric": self._cfg.metric or self._default_metric(),
            "ffn-hidden-size": self._cfg.ffn_hidden_size,
            "ffn-num-layers": self._cfg.ffn_num_layers,
        }
        for flag, value in mapping.items():
            if value is not None:
                flags += f" --{flag} {value}"
        return flags

    def _default_metric(self) -> str:
        # Matches KERMT's own args.metric-is-None fallback in
        # kermt/util/parsing.py::modify_train_args (auc / rmse) except we use
        # "mae" for regression to match MARS's own primary regression metric
        # (ml/eval/metrics.py) — both are accepted for dataset_type=regression.
        return "auc" if self._task_type == TaskType.CLASSIFICATION else "mae"

    def _targets_dict(self, y: np.ndarray) -> dict[str, np.ndarray]:
        y = np.asarray(y, dtype=float)
        if len(self._target_names) == 1:
            if y.ndim != 1:
                raise ValueError("single-task: y must be 1-D")
            return {self._target_names[0]: y}
        if y.ndim != 2 or y.shape[1] != len(self._target_names):
            raise ValueError(
                f"multi-task: y must be 2-D shaped (n_samples, {len(self._target_names)})"
            )
        return {name: y[:, i] for i, name in enumerate(self._target_names)}

    def _check_checkpoint(self, *, mode: str) -> dict[str, Any]:
        cmd = f"python agent/scripts/check_checkpoint.py --mode {mode} --ckpt /ckpt"
        proc = _run_container(
            self._kermt_repo, self._docker_image,
            ckpt=self._active_checkpoint(), command=cmd,
        )
        return _parse_json_stdout(proc, context=f"check_checkpoint.py --mode {mode}")

    def _active_checkpoint(self) -> Path:
        return self._finetuned_checkpoint or self._pretrained_checkpoint

    # ------------------------------------------------------------------
    # predict()
    # ------------------------------------------------------------------

    def predict(self, X: list[str], *, run_dir: Path | None = None) -> np.ndarray:
        """Run inference with the finetuned checkpoint.

        Single-task: returns a 1-D array (probabilities for classification,
        raw values for regression), matching `XGBoostModel.predict`'s shape
        contract so `eval/metrics.py` / calibration code needn't branch on
        model family.

        Multi-task: returns a 2-D array `(n_samples, n_targets)` in
        `target_names` order — callers that need XGBoostModel-style 1-D
        output should index a single-task `KermtModel` instead.
        """
        if not self.is_fitted:
            raise RuntimeError("Model has not been fitted. Call fit() first.")
        work = Path(run_dir) if run_dir is not None else self._work_dir
        if work is None:
            raise ValueError("predict() needs run_dir (or work_dir set at fit time)")
        predict_dir = work / f"predict_{abs(hash(tuple(X))) % 10**8}"
        data_dir = predict_dir / "input"
        data_dir.mkdir(parents=True, exist_ok=True)
        smiles_csv = write_predict_csv(data_dir / "smiles.csv", list(X))

        validator = self._check_checkpoint(mode="inference")
        if not validator.get("ok"):
            raise RuntimeError(f"KERMT rejected the finetuned checkpoint: {validator.get('errors')}")

        prep_cmd = (
            f"python agent/scripts/prepare_data.py --mode inference "
            f"--csv /data/{smiles_csv.name} --out /runs/data"
        )
        proc = _run_container(
            self._kermt_repo, self._docker_image,
            data=data_dir, run_dir=predict_dir, command=prep_cmd,
        )
        prep_manifest_host = predict_dir / "data" / "prepare_data.json"
        if proc.returncode != 0 or not prep_manifest_host.exists():
            raise RuntimeError(
                f"prepare_data.py (inference) failed (exit {proc.returncode}).\n"
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
            )

        infer_cmd = (
            f"python agent/scripts/run_inference.py --ckpt /ckpt "
            f"--prepare-manifest /runs/data/prepare_data.json --out /runs "
            f"--gpus {self._cfg.gpu} --seed {self._seed}"
        )
        proc = _run_container(
            self._kermt_repo, self._docker_image,
            ckpt=self._active_checkpoint(), run_dir=predict_dir, command=infer_cmd,
        )
        run_json_path = predict_dir / "run.json"
        if not run_json_path.exists():
            raise RuntimeError(
                f"run_inference.py produced no run.json (exit {proc.returncode}).\n"
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
            )
        run_manifest = json.loads(run_json_path.read_text())
        if run_manifest.get("status") != "ok":
            log_path = predict_dir / "logs" / "inference.log"
            log_tail = log_path.read_text()[-4000:] if log_path.exists() else "(no log file)"
            raise RuntimeError(
                f"KERMT inference failed (status={run_manifest.get('status')}).\nlog tail:\n{log_tail}"
            )

        # Same container-vs-host path translation as fit() above:
        # run_manifest["output_csv"] is "/runs/out/predictions.csv" (container
        # path); the host equivalent is always `predict_dir / "out" / ...`.
        preds = read_predictions_csv(predict_dir / "out" / "predictions.csv", self._target_names)
        if len(self._target_names) == 1:
            return preds[self._target_names[0]]
        return np.stack([preds[name] for name in self._target_names], axis=1)

    def predict_logits(self, X: list[str], *, run_dir: Path | None = None) -> np.ndarray:
        """Return logits suitable for ``eval.calibration.fit_temperature_scaler``.

        ``fit_temperature_scaler`` needs pre-sigmoid values; ``predict()`` returns
        probabilities, which is why temperature scaling had no usable input for
        any KERMT run. This closes that gap without needing the Tier-1 trainer.

        **What this actually is, stated precisely:** ``logit(p)`` where ``p`` is
        the served quantity — the *mean of the two views'* sigmoid outputs,
        ``(sigmoid(a) + sigmoid(b)) / 2``, as computed inside
        ``KermtFinetuneTask.forward()`` in eval mode. It is therefore **not** the
        pre-sigmoid activation of either individual head, and inverting the mean
        of two sigmoids is not the mean of the two logits. That distinction does
        not matter for temperature scaling: ``logit`` is strictly monotone, so
        this is a well-defined recalibration of exactly the number serving emits,
        fit on the calibration split, and it leaves AUROC/AUPRC untouched.
        (The Tier-1 mixed trainer does expose true per-head pre-sigmoid logits,
        since ``forward()`` returns logits in training mode.)

        Probabilities are clipped to ``[1e-6, 1-1e-6]`` before inversion — the
        predictions CSV carries finite decimal precision, so an exact 0.0 or 1.0
        is a rounding artifact rather than genuine infinite confidence.

        Raises
        ------
        RuntimeError
            If the model is not fitted.
        ValueError
            If this is a regression model — logits are meaningless there.
        """
        if self._task_type is not TaskType.CLASSIFICATION:
            raise ValueError(
                "predict_logits() is classification-only; this model is "
                f"{self._task_type.value}."
            )
        probs = self.predict(X, run_dir=run_dir)
        clipped = np.clip(probs, 1e-6, 1.0 - 1e-6)
        return np.log(clipped / (1.0 - clipped))

    # ------------------------------------------------------------------
    # save() / load()
    # ------------------------------------------------------------------

    def save(self, path: Path) -> None:
        if not self.is_fitted:
            raise RuntimeError("Model has not been fitted.")
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        import shutil

        shutil.copy2(self._finetuned_checkpoint, path / "model.pt")
        meta = {
            "model_id": self.model_id,
            "task_type": self._task_type.value,
            "seed": self._seed,
            "target_names": self._target_names,
            "pretrained_checkpoint": str(self._pretrained_checkpoint),
        }
        (path / "metadata.json").write_text(
            json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    @classmethod
    def load(cls, path: Path) -> KermtModel:
        path = Path(path)
        meta = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
        task_type = TaskType(meta["task_type"])
        inst = cls(
            task_type=task_type,
            pretrained_checkpoint=Path(meta["pretrained_checkpoint"]),
            target_names=meta["target_names"],
            seed=int(meta["seed"]),
        )
        inst._finetuned_checkpoint = path / "model.pt"
        return inst
