"""
Module 11 — 5-seed evaluation aggregation, persisted as a durable report.

`eval.metrics.aggregate_seed_metrics` already computes mean ± std over
FIXED_SEEDS; `train.train_xgboost.train_xgboost_all_seeds` already trains all
5 seeds. What's missing is turning that in-memory aggregate into a citable,
reloadable artifact tied to which endpoint / model family / prep_id / seeds /
ExperimentRun ids produced it — this module is that artifact.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from mars_contracts.endpoints import TaskType
from train.train_xgboost import SeedResult

from eval.metrics import aggregate_seed_metrics

EVALUATE_VERSION = "mars-evaluate-v1"


@dataclass
class EvaluationReport:
    """Durable 5-seed evaluation summary for one endpoint × one model family."""

    endpoint_key: str
    model_family: str
    prep_id: str
    task_type: str
    seeds: list[int]
    run_ids: list[str]
    per_seed_metrics: list[dict[str, Any]]
    aggregated: dict[str, float]
    version: str = EVALUATE_VERSION

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> EvaluationReport:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**data)


def build_evaluation_report(
    results: list[SeedResult],
    *,
    endpoint_key: str,
    model_family: str,
    prep_id: str,
    task_type: TaskType,
) -> EvaluationReport:
    """Aggregate a list of per-seed training results into one EvaluationReport.

    Parameters
    ----------
    results:
        One SeedResult per seed, e.g. the output of
        `train.train_xgboost.train_xgboost_all_seeds`. Every seed must be
        unique — this is meant for one complete 5-seed sweep, not a partial
        or re-run set with accidental duplicates.
    """
    if not results:
        raise ValueError("results is empty")
    seeds = [r.seed for r in results]
    if len(seeds) != len(set(seeds)):
        raise ValueError(f"Duplicate seeds in results: {seeds}")

    per_seed_metrics = [r.val_metrics for r in results]
    aggregated = aggregate_seed_metrics(per_seed_metrics)
    per_seed_dicts = [asdict(m) for m in per_seed_metrics]

    return EvaluationReport(
        endpoint_key=endpoint_key,
        model_family=model_family,
        prep_id=prep_id,
        task_type=task_type.value,
        seeds=seeds,
        run_ids=[r.run_id for r in results],
        per_seed_metrics=per_seed_dicts,
        aggregated=aggregated,
    )
