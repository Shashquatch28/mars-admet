"""
Experiment provenance collection for MARS.

Captures the code and runtime environment associated with an experiment
so that results can be traced back to the exact repository state and
software environment that produced them.
"""

from __future__ import annotations

import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# NOTE: numpy / torch are imported lazily inside collect_environment() on
# purpose. Milestone 1 (data + featurization) runs CPU-only and does not install
# torch (blueprint Module 10); provenance capture for those runs must not
# ImportError just because the GNN stack is absent. See CF-5.


def _run_git_command(
    args: list[str],
    repo_root: Path,
) -> str | None:
    """
    Run a git command and return its stripped stdout.

    Returns None when git is unavailable or the command fails.
    """
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
    ):
        return None


def get_git_info(repo_root: Path) -> dict[str, Any]:
    """
    Capture the current Git repository state.
    """
    commit = _run_git_command(
        ["rev-parse", "HEAD"],
        repo_root,
    )

    branch = _run_git_command(
        ["rev-parse", "--abbrev-ref", "HEAD"],
        repo_root,
    )

    status = _run_git_command(
        ["status", "--porcelain"],
        repo_root,
    )

    return {
        "commit": commit,
        "branch": branch,
        "dirty": bool(status) if status is not None else None,
    }


def _get_package_version(
    package_name: str,
) -> str | None:
    """
    Return an installed package version without failing the experiment
    if the package is unavailable.
    """
    try:
        from importlib.metadata import version

        return version(package_name)

    except Exception:
        return None


def _torch_info() -> dict[str, Any]:
    """
    Torch/CUDA details when torch is installed; explicit nulls when it is not
    (CPU-only Milestone 1 / XGBoost-baseline runs — CF-5).
    """
    try:
        import torch
    except ModuleNotFoundError:
        return {
            "torch_installed": False,
            "torch_version": None,
            "cuda_available": None,
            "cuda_version": None,
            "cudnn_version": None,
            "gpu_name": None,
        }

    cuda = torch.cuda.is_available()
    return {
        "torch_installed": True,
        "torch_version": torch.__version__,
        "cuda_available": cuda,
        "cuda_version": torch.version.cuda,
        "cudnn_version": torch.backends.cudnn.version() if cuda else None,
        "gpu_name": torch.cuda.get_device_name(0) if cuda else None,
    }


def collect_environment() -> dict[str, Any]:
    """
    Collect the Python, OS, and core ML environment information.

    Works with or without the GNN stack installed: numpy and torch are probed
    lazily so CPU-only data/featurization runs can still record provenance.
    """
    try:
        import numpy as np

        numpy_version = np.__version__
    except ModuleNotFoundError:
        numpy_version = None

    return {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "python_version": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "numpy_version": numpy_version,
        **_torch_info(),
        "rdkit_version": _get_package_version("rdkit"),
        "scikit_learn_version": _get_package_version("scikit-learn"),
        "xgboost_version": _get_package_version("xgboost"),
        "pandas_version": _get_package_version("pandas"),
        "pytdc_version": _get_package_version("PyTDC"),
    }


def collect_provenance(
    repo_root: Path | str,
) -> dict[str, Any]:
    """
    Collect complete experiment provenance.

    Parameters
    ----------
    repo_root:
        Path to the root of the MARS repository.

    Returns
    -------
    dict
        A serializable dictionary containing Git and environment metadata.
    """
    repo_root = Path(repo_root).resolve()

    return {
        "git": get_git_info(repo_root),
        "environment": collect_environment(),
    }