"""
CF-5 regression guard: provenance + seeding must work in a CPU-only environment
without torch installed (Milestone 1 / XGBoost-baseline runs, blueprint Module 10).
"""

from __future__ import annotations

import importlib.util

from tracking.provenance import collect_environment, collect_provenance
from utils.seed import set_global_seed

TORCH_INSTALLED = importlib.util.find_spec("torch") is not None


def test_collect_environment_runs_without_torch():
    env = collect_environment()
    assert env["python_version"]
    assert "numpy_version" in env
    assert "torch_installed" in env
    if not TORCH_INSTALLED:
        assert env["torch_installed"] is False
        assert env["torch_version"] is None
        assert env["cuda_available"] is None
    # M1 working env has these:
    assert env["rdkit_version"]
    assert env["pandas_version"]


def test_collect_provenance_shape(tmp_path):
    prov = collect_provenance(tmp_path)
    assert set(prov) == {"git", "environment"}
    assert "commit" in prov["git"]


def test_set_global_seed_without_torch_returns_record():
    rec = set_global_seed(1234)
    assert rec["seed"] == 1234
    assert rec["numpy"] is True
    assert rec["torch"] is TORCH_INSTALLED


def test_set_global_seed_is_reproducible_for_numpy():
    import numpy as np

    set_global_seed(7)
    a = np.random.rand(5)
    set_global_seed(7)
    b = np.random.rand(5)
    assert np.array_equal(a, b)


def test_set_global_seed_rejects_non_int():
    import pytest

    with pytest.raises(TypeError):
        set_global_seed("5")  # type: ignore[arg-type]
