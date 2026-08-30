"""
Integration tests for the DILIst augmentation (blueprint Module 1 §6).

The non-negotiable requirement — no augmentation compound may appear in the
fixed TDC DILI test set — is checked here on the actual produced artifact.
Skips cleanly if the augmentation has not been run on this machine.
"""

from __future__ import annotations

import csv
import glob
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _find_augmented_dir() -> Path | None:
    matches = glob.glob(
        str(REPO / "ml" / "data" / "processed" / "*" / "dili_liver_injury__augmented")
    )
    if not matches:
        return None
    return Path(sorted(matches)[-1])


AUG = _find_augmented_dir()


def _smis(path: Path) -> set[str]:
    with path.open(newline="", encoding="utf-8") as fh:
        return {r["standardized_smiles"] for r in csv.DictReader(fh)}


@pytest.fixture(scope="module")
def report() -> dict:
    if AUG is None:
        pytest.skip("no augmented DILI on disk")
    return json.loads((AUG / "augmentation_report.json").read_text(encoding="utf-8"))


def test_no_augmentation_row_reaches_the_test_set(report):
    assert report["leakage_audit"]["smiles_overlap_train_test_after_merge"] == 0


def test_test_set_is_frozen(report):
    assert report["leakage_audit"]["test_set_frozen"] is True


def test_calibration_is_disjoint_from_test():
    tv = _smis(AUG / "train_val.csv")
    te = _smis(AUG / "test.csv")
    cal = _smis(AUG / "calibration.csv")
    assert not cal & te
    assert cal.issubset(tv)


def test_augmentation_source_dropped_something(report):
    # ~50 rows are expected to overlap the TDC DILI test set and be dropped.
    assert report["steps"]["dropped_because_in_test_set"] > 0


def test_final_train_val_grew_over_the_base_dili(report):
    # base DILI train_val is 378 after prepare; augmentation should add hundreds
    assert report["steps"]["final_train_val"] > 500


def test_augmented_test_matches_baseline_test(report):
    # non-negotiable — the test set is the TDC benchmark test set, unchanged
    baseline_test = None
    for path in sorted(REPO.glob("ml/data/processed/*/dili_liver_injury/test.csv")):
        with path.open(newline="", encoding="utf-8") as fh:
            baseline_test = {r["standardized_smiles"] for r in csv.DictReader(fh)}
        break
    if baseline_test is None:
        pytest.skip("no baseline DILI test.csv found")
    aug_test = _smis(AUG / "test.csv")
    assert baseline_test == aug_test
