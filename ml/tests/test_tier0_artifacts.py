"""Tests for ml/eval/tier0_artifacts.py — regression arms are refused before any classification-only artifact is read.

Regression arms have no temperature scaler by design (decisions.md D2), so loading one used to die with a bare
FileNotFoundError on ``temperature_scaler.json``. matplotlib is required by the module itself, so the file is skipped
where it is absent.
"""

from __future__ import annotations

import pytest

pytest.importorskip("matplotlib")

from configs.clusters import all_subgroups  # noqa: E402
from eval.tier0_artifacts import require_classification  # noqa: E402


@pytest.mark.parametrize("key", ["metabolism__reg", "absorption_distribution__reg"])
def test_regression_arm_is_refused(key):
    with pytest.raises(NotImplementedError, match="classification-only"):
        require_classification(key, all_subgroups()[key])


@pytest.mark.parametrize("key", ["toxicity__cls", "absorption_distribution__cls", "dili_standalone__cls"])
def test_classification_arm_is_accepted(key):
    require_classification(key, all_subgroups()[key])
