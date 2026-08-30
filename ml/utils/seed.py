"""
Global reproducibility utilities for MARS experiments.

Every reproducible training, splitting, or evaluation entry point should
initialize its random state through set_global_seed() before creating datasets,
splits, models, or data loaders.

torch is optional: Milestone 1 (data + featurization) and the XGBoost baselines
run CPU-only without torch installed (blueprint Module 10). When torch is
absent, Python + NumPy RNGs are still seeded and the torch step is skipped
(reported via the return value). See CF-5.
"""

from __future__ import annotations

import os
import random
from typing import Any


def set_global_seed(
    seed: int,
    *,
    deterministic: bool = True,
) -> dict[str, Any]:
    """
    Initialize the random number generators used by MARS experiments.

    Seeds Python and NumPy always; seeds PyTorch (and configures deterministic
    algorithms when ``deterministic=True``) only if torch is importable.

    Parameters
    ----------
    seed:
        Integer seed used across all supported RNGs.
    deterministic:
        Whether to enable deterministic PyTorch behavior (ignored if torch is
        not installed).

    Returns
    -------
    dict
        ``{"seed": seed, "numpy": True, "torch": bool, "deterministic": bool}``
        — a small record suitable for logging into run provenance.
    """
    if not isinstance(seed, int):
        raise TypeError(f"seed must be an int, got {type(seed).__name__}")

    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)

    import numpy as np

    np.random.seed(seed)

    result: dict[str, Any] = {
        "seed": seed,
        "numpy": True,
        "torch": False,
        "deterministic": False,
    }

    try:
        import torch
    except ModuleNotFoundError:
        return result

    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
    result["torch"] = True

    if deterministic:
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True
        torch.use_deterministic_algorithms(True)
        result["deterministic"] = True
    else:
        torch.backends.cudnn.benchmark = True
        torch.backends.cudnn.deterministic = False

    return result
