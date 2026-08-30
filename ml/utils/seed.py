"""
Global reproducibility utilities for MARS experiments.

Every reproducible training or evaluation entry point should initialize
its random state through set_global_seed() before creating datasets,
splits, models, or data loaders.
"""

from __future__ import annotations

import os
import random

import numpy as np
import torch


def set_global_seed(
    seed: int,
    *,
    deterministic: bool = True,
) -> None:
    """
    Initialize random number generators used by MARS experiments.

    This seeds Python, NumPy, and PyTorch RNGs. When deterministic=True,
    PyTorch is configured to prefer deterministic algorithms where
    possible.

    Parameters
    ----------
    seed:
        Integer seed used across all supported RNGs.

    deterministic:
        Whether to enable deterministic PyTorch behavior.
    """
    if not isinstance(seed, int):
        raise TypeError(f"seed must be an int, got {type(seed).__name__}")

    random.seed(seed)

    np.random.seed(seed)

    torch.manual_seed(seed)

    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)

    os.environ["PYTHONHASHSEED"] = str(seed)

    if deterministic:
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True
        torch.use_deterministic_algorithms(True)
    else:
        torch.backends.cudnn.benchmark = True
        torch.backends.cudnn.deterministic = False