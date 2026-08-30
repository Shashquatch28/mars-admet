"""
Weights & Biases integration for MARS experiments.

W&B mirrors experiment metadata and metrics to a remote dashboard.
The local ExperimentRun directory remains the source of truth.
"""

from __future__ import annotations

import os
from typing import Any

import wandb


class WandbLogger:
    """
    Thin wrapper around a W&B run.

    The logger is intentionally separate from ExperimentRun so that local
    experiment tracking works even when W&B is disabled or unavailable.
    """

    def __init__(
        self,
        *,
        run_id: str,
        config: dict[str, Any],
        provenance: dict[str, Any],
        project: str | None = None,
        entity: str | None = None,
        enabled: bool = True,
    ) -> None:
        self.run_id = run_id
        self.enabled = enabled
        self._run: wandb.sdk.wandb_run.Run | None = None

        self.project = project or os.getenv(
            "WANDB_PROJECT",
            "mars-admet",
        )

        self.entity = entity or os.getenv(
            "WANDB_ENTITY"
        )

        if not self.enabled:
            return

        merged_config = {
            **config,
            "provenance": provenance,
        }

        self._run = wandb.init(
            project=self.project,
            entity=self.entity,
            id=self.run_id,
            name=self.run_id,
            config=merged_config,
            resume="allow",
        )

    def log(
        self,
        metrics: dict[str, Any],
        *,
        step: int | None = None,
    ) -> None:
        """
        Log metrics to W&B.
        """
        if not self.enabled or self._run is None:
            return

        self._run.log(
            metrics,
            step=step,
        )

    def log_artifact(
        self,
        path: str,
        *,
        name: str,
        artifact_type: str,
    ) -> None:
        """
        Upload a local file or directory as a W&B artifact.
        """
        if not self.enabled or self._run is None:
            return

        artifact = wandb.Artifact(
            name=name,
            type=artifact_type,
        )

        artifact.add_file(path)

        self._run.log_artifact(artifact)

    def finish(self) -> None:
        """
        Finish the W&B run.
        """
        if not self.enabled or self._run is None:
            return

        self._run.finish()