"""
Experiment run management for MARS.

Each experiment gets an isolated run directory containing its configuration,
provenance, metrics, and generated artifacts.

This module is intentionally independent of W&B. Local experiment records
remain the source of truth, while external tracking services can mirror them.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tracking.provenance import collect_provenance


class ExperimentRun:
    """
    Manage the local lifecycle and artifacts of one experiment.
    """

    def __init__(
        self,
        name: str,
        repo_root: Path | str,
        config: dict[str, Any],
        runs_dir: Path | str | None = None,
    ) -> None:
        self.name = self._validate_name(name)
        self.repo_root = Path(repo_root).resolve()
        self.config = config

        if runs_dir is None:
            self.runs_dir = self.repo_root / "ml" / "runs"
        else:
            self.runs_dir = Path(runs_dir).resolve()

        self.run_id = self._generate_run_id(self.name)

        self.run_dir = self.runs_dir / self.run_id
        self.artifacts_dir = self.run_dir / "artifacts"
        self.provenance: dict[str, Any] = {}

    @staticmethod
    def _validate_name(name: str) -> str:
        """
        Normalize an experiment name into a filesystem-safe identifier.
        """
        normalized = name.strip().lower()

        normalized = re.sub(
            r"[^a-z0-9_-]+",
            "_",
            normalized,
        )

        normalized = normalized.strip("_-")

        if not normalized:
            raise ValueError(
                "Experiment name must contain at least one "
                "alphanumeric character."
            )

        return normalized

    @staticmethod
    def _generate_run_id(name: str) -> str:
        """
        Generate a timestamped experiment identifier.

        Example:
        xgb_solubility_20260825T143015Z
        """
        timestamp = datetime.now(UTC).strftime(
            "%Y%m%dT%H%M%SZ"
        )

        return f"{name}_{timestamp}"

    def start(
        self,
        *,
        run_tags: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize the experiment directory and save initial metadata.

        Parameters
        ----------
        run_tags:
            Optional flat dict of M2-level fields merged into ``run.json``
            for fast filtering without parsing ``config.json``.  Typical keys:
            ``endpoint``, ``model_family``, ``seed``, ``prep_id``.
        """
        if self.run_dir.exists():
            raise FileExistsError(
                f"Experiment run directory already exists: {self.run_dir}"
            )

        self.artifacts_dir.mkdir(
            parents=True,
            exist_ok=False,
        )

        self._write_json(
            self.run_dir / "config.json",
            self.config,
        )

        self.provenance = collect_provenance(
            self.repo_root,
        )

        self._write_json(
            self.run_dir / "provenance.json",
            self.provenance,
        )

        metadata: dict[str, Any] = {
            "run_id": self.run_id,
            "name": self.name,
            "status": "running",
            "started_at": datetime.now(
                UTC
            ).isoformat(),
        }

        if run_tags:
            metadata.update(run_tags)

        self._write_json(
            self.run_dir / "run.json",
            metadata,
        )

    def log_metrics(
        self,
        metrics: dict[str, Any],
        *,
        step: int | None = None,
    ) -> None:
        """
        Append a metrics record to metrics.jsonl.

        JSON Lines allows metrics to be logged incrementally during
        long-running experiments.
        """
        if not self.run_dir.exists():
            raise RuntimeError(
                "Experiment has not been started. "
                "Call start() first."
            )

        record = {
            "timestamp_utc": datetime.now(
                UTC
            ).isoformat(),
            "step": step,
            "metrics": metrics,
        }

        metrics_path = self.run_dir / "metrics.jsonl"

        with metrics_path.open(
            "a",
            encoding="utf-8",
        ) as file:
            file.write(
                json.dumps(record, default=str)
                + "\n"
            )

    def artifact_path(
        self,
        filename: str,
    ) -> Path:
        """
        Return a path inside this experiment's artifact directory.
        """
        if not self.run_dir.exists():
            raise RuntimeError(
                "Experiment has not been started. "
                "Call start() first."
            )

        path = self.artifacts_dir / filename

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        return path

    def finish(
        self,
        status: str = "completed",
    ) -> None:
        """
        Mark the experiment as finished.
        """
        run_path = self.run_dir / "run.json"

        if not run_path.exists():
            raise RuntimeError(
                "Experiment has not been started."
            )

        with run_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            metadata = json.load(file)

        metadata["status"] = status
        metadata["finished_at"] = datetime.now(
            UTC
        ).isoformat()

        self._write_json(
            run_path,
            metadata,
        )

    @staticmethod
    def _write_json(
        path: Path,
        data: dict[str, Any],
    ) -> None:
        """
        Write JSON with stable formatting.
        """
        with path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                data,
                file,
                indent=2,
                sort_keys=True,
                default=str,
            )
            file.write("\n")