"""
Experiment configuration for MARS M2 training runs.

Every training run — XGBoost baseline or KERMT fine-tune — is parameterized
by one ExperimentConfig. The config is serialized into ExperimentRun.config
and W&B so results are always traceable to the exact setup that produced them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Fixed five seeds for all MARS experiments (blueprint Module 1 §4 / Module 11).
# Matches the default in data.split.five_seed_train_val_folds.
FIXED_SEEDS: tuple[int, ...] = (0, 1, 2, 3, 4)

VALID_MODEL_FAMILIES: frozenset[str] = frozenset(
    {"xgboost", "kermt_single", "kermt_multitask"}
)

# Short prefix used in run names and artifact paths
_MODEL_FAMILY_PREFIX: dict[str, str] = {
    "xgboost": "xgb",
    "kermt_single": "kermt_st",
    "kermt_multitask": "kermt_mt",
}


@dataclass
class ExperimentConfig:
    """Full specification of one MARS training run.

    Attributes
    ----------
    endpoint:
        Endpoint key (e.g. ``"solubility_logs"``) for single-task models, or
        cluster name (e.g. ``"absorption_distribution"``) for multi-task.
    model_family:
        One of ``"xgboost"``, ``"kermt_single"``, ``"kermt_multitask"``.
    seed:
        Integer random seed for this run (must be from ``FIXED_SEEDS`` in
        normal experiments, but not enforced — allows smoke-test seeds).
    prep_id:
        Identifier of the M1 processed dataset snapshot used (e.g.
        ``"20260830T200000Z"``). Ties the model to an exact data state.
    use_augmented_dili:
        When True and endpoint == ``"dili_liver_injury"``, load the DILIst-
        augmented training set instead of the base TDC set.
    hyperparams:
        Model-family-specific hyperparameters (e.g. XGBoost tree depth).
        Stored verbatim in run provenance — no schema enforced at this level.
    notes:
        Free-text annotation (reason for run, ablation axis, etc.).
    """

    endpoint: str
    model_family: str
    seed: int
    prep_id: str
    use_augmented_dili: bool = False
    hyperparams: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    def __post_init__(self) -> None:
        if self.model_family not in VALID_MODEL_FAMILIES:
            raise ValueError(
                f"model_family must be one of {sorted(VALID_MODEL_FAMILIES)}, "
                f"got {self.model_family!r}"
            )
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise TypeError(
                f"seed must be a plain int, got {type(self.seed).__name__}"
            )
        if not self.endpoint:
            raise ValueError("endpoint must be a non-empty string")
        if not self.prep_id:
            raise ValueError("prep_id must be a non-empty string")

    def to_tracking_config(self) -> dict[str, Any]:
        """Serialize to a flat dict for ExperimentRun.config / W&B."""
        return asdict(self)

    def run_name(self) -> str:
        """Canonical run name passed to ExperimentRun.

        Pattern: ``<prefix>_<endpoint>_seed<n>``

        Example: ``xgb_solubility_logs_seed0``,
                 ``kermt_st_ames_mutagenicity_seed2``.
        """
        prefix = _MODEL_FAMILY_PREFIX[self.model_family]
        return f"{prefix}_{self.endpoint}_seed{self.seed}"
