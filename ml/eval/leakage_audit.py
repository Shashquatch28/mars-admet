"""
Module 1/4/5 self-audit — leakage checks as live assertions against the
current M2 pipeline, not just historical M1 test coverage.

M1 (`data/split.py`) already guarantees train_val/test scaffold isolation at
prepare-time. This module re-verifies that guarantee against whatever
processed snapshot is actually loaded right now, and extends the audit to
M2-specific surfaces M1 never had to check: per-seed CV fold isolation,
calibration-split isolation, applicability-domain reference-set isolation,
and calibrator fit-sample-count isolation. Ten checks total, each a small
pure function returning a `LeakageCheckResult`; `run_leakage_audit` runs the
checks that apply given what was passed in and returns a full report.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from data.loaders import EndpointData
from data.split import five_seed_train_val_folds
from featurize.scaffold import murcko_scaffold_from_smiles

if TYPE_CHECKING:
    from eval.applicability_domain import ADIndex
    from eval.calibration import PlattCalibrator, TemperatureScaler

LEAKAGE_AUDIT_VERSION = "mars-leakage-audit-v1"


@dataclass(frozen=True)
class LeakageCheckResult:
    name: str
    passed: bool
    detail: str


@dataclass
class LeakageAuditReport:
    endpoint_key: str
    checks: list[LeakageCheckResult]
    version: str = LEAKAGE_AUDIT_VERSION

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failed_checks(self) -> list[LeakageCheckResult]:
        return [c for c in self.checks if not c.passed]


def assert_no_leakage(report: LeakageAuditReport) -> None:
    """Raise AssertionError listing every failed check, or return silently."""
    if not report.all_passed:
        failures = "\n".join(f"  - {c.name}: {c.detail}" for c in report.failed_checks)
        raise AssertionError(
            f"{report.endpoint_key}: {len(report.failed_checks)} leakage check(s) failed:\n{failures}"
        )


# ---------------------------------------------------------------------------- #
# Individual checks (1-6): EndpointData splits only
# ---------------------------------------------------------------------------- #


def check_test_disjoint_from_train_val_smiles(endpoint_data: EndpointData) -> LeakageCheckResult:
    test_smiles = set(endpoint_data.test["standardized_smiles"])
    tv_smiles = set(endpoint_data.train_val["standardized_smiles"])
    overlap = test_smiles & tv_smiles
    return LeakageCheckResult(
        name="test_disjoint_from_train_val_smiles",
        passed=not overlap,
        detail=f"{len(overlap)} overlapping SMILES" if overlap else "no overlap",
    )


def check_test_disjoint_from_train_val_scaffolds(endpoint_data: EndpointData) -> LeakageCheckResult:
    test_scaffolds = {murcko_scaffold_from_smiles(s) for s in endpoint_data.test["standardized_smiles"]}
    tv_scaffolds = {murcko_scaffold_from_smiles(s) for s in endpoint_data.train_val["standardized_smiles"]}
    # empty-scaffold (acyclic) bucket is a documented, allowed shared bucket (M1 convention)
    overlap = (test_scaffolds & tv_scaffolds) - {""}
    return LeakageCheckResult(
        name="test_disjoint_from_train_val_scaffolds",
        passed=not overlap,
        detail=f"{len(overlap)} overlapping non-acyclic scaffolds" if overlap else "no overlap",
    )


def check_calibration_subset_of_train_val(endpoint_data: EndpointData) -> LeakageCheckResult:
    cal_smiles = set(endpoint_data.calibration["standardized_smiles"])
    tv_smiles = set(endpoint_data.train_val["standardized_smiles"])
    not_in_tv = cal_smiles - tv_smiles
    return LeakageCheckResult(
        name="calibration_subset_of_train_val",
        passed=not not_in_tv,
        detail=f"{len(not_in_tv)} calibration SMILES not in train_val" if not_in_tv else "fully contained",
    )


def check_calibration_disjoint_from_test(endpoint_data: EndpointData) -> LeakageCheckResult:
    cal_smiles = set(endpoint_data.calibration["standardized_smiles"])
    test_smiles = set(endpoint_data.test["standardized_smiles"])
    overlap = cal_smiles & test_smiles
    return LeakageCheckResult(
        name="calibration_disjoint_from_test",
        passed=not overlap,
        detail=f"{len(overlap)} overlapping SMILES" if overlap else "no overlap",
    )


def check_no_duplicate_smiles_within_train_val(endpoint_data: EndpointData) -> LeakageCheckResult:
    smiles = endpoint_data.train_val["standardized_smiles"]
    n_dupes = len(smiles) - len(set(smiles))
    return LeakageCheckResult(
        name="no_duplicate_smiles_within_train_val",
        passed=n_dupes == 0,
        detail=f"{n_dupes} duplicate rows" if n_dupes else "no duplicates",
    )


def check_no_duplicate_smiles_within_test(endpoint_data: EndpointData) -> LeakageCheckResult:
    smiles = endpoint_data.test["standardized_smiles"]
    n_dupes = len(smiles) - len(set(smiles))
    return LeakageCheckResult(
        name="no_duplicate_smiles_within_test",
        passed=n_dupes == 0,
        detail=f"{n_dupes} duplicate rows" if n_dupes else "no duplicates",
    )


# ---------------------------------------------------------------------------- #
# Checks 7-8: per-seed CV fold isolation (M2-specific — five_seed_train_val_folds)
# ---------------------------------------------------------------------------- #


def check_seed_fold_scaffold_isolation(endpoint_data: EndpointData) -> LeakageCheckResult:
    """For each of the 5 seeds, that seed's own train/val partition must share
    no non-acyclic scaffold — the same guarantee M1 enforces for train_val/test,
    now re-checked for every per-seed CV fold M2 actually trains on."""
    tv_smiles = endpoint_data.train_val["standardized_smiles"].tolist()
    folds = five_seed_train_val_folds(tv_smiles)
    violations: list[str] = []
    for seed, train_s, val_s in folds:
        train_scaffolds = {murcko_scaffold_from_smiles(s) for s in train_s}
        val_scaffolds = {murcko_scaffold_from_smiles(s) for s in val_s}
        overlap = (train_scaffolds & val_scaffolds) - {""}
        if overlap:
            violations.append(f"seed={seed}: {len(overlap)} overlapping scaffolds")
    return LeakageCheckResult(
        name="seed_fold_scaffold_isolation",
        passed=not violations,
        detail="; ".join(violations) if violations else "all 5 seeds clean",
    )


def check_seed_folds_cover_train_val(endpoint_data: EndpointData) -> LeakageCheckResult:
    """Each seed's train ∪ val must reconstruct the full train_val pool —
    catches a fold-construction bug that silently drops molecules."""
    tv_smiles = endpoint_data.train_val["standardized_smiles"].tolist()
    tv_set = set(tv_smiles)
    folds = five_seed_train_val_folds(tv_smiles)
    violations: list[str] = []
    for seed, train_s, val_s in folds:
        covered = set(train_s) | set(val_s)
        missing = tv_set - covered
        extra = covered - tv_set
        if missing or extra:
            violations.append(f"seed={seed}: {len(missing)} missing, {len(extra)} extraneous")
    return LeakageCheckResult(
        name="seed_folds_cover_train_val",
        passed=not violations,
        detail="; ".join(violations) if violations else "all 5 seeds fully cover train_val",
    )


# ---------------------------------------------------------------------------- #
# Checks 9-10: AD index + calibrator isolation (optional — only run if provided)
# ---------------------------------------------------------------------------- #


def check_ad_index_disjoint_from_test(endpoint_data: EndpointData, ad_index: ADIndex) -> LeakageCheckResult:
    ad_smiles = set(ad_index.reference_smiles)
    test_smiles = set(endpoint_data.test["standardized_smiles"])
    overlap = ad_smiles & test_smiles
    return LeakageCheckResult(
        name="ad_index_disjoint_from_test",
        passed=not overlap,
        detail=f"{len(overlap)} test SMILES leaked into AD reference set" if overlap else "no overlap",
    )


def check_calibrator_fit_sample_count(
    endpoint_data: EndpointData,
    calibrator: PlattCalibrator | TemperatureScaler,
) -> LeakageCheckResult:
    """A calibrator's n_fit_samples must not exceed the calibration split
    size — a value larger than that would mean it was (at least partly) fit
    on train_val or test data instead of the calibration split alone."""
    n_cal = len(endpoint_data.calibration)
    passed = calibrator.n_fit_samples <= n_cal
    return LeakageCheckResult(
        name="calibrator_fit_sample_count_within_calibration_split",
        passed=passed,
        detail=(
            f"n_fit_samples={calibrator.n_fit_samples} <= calibration split size={n_cal}"
            if passed
            else f"n_fit_samples={calibrator.n_fit_samples} EXCEEDS calibration split size={n_cal}"
        ),
    )


# ---------------------------------------------------------------------------- #
# Orchestrator
# ---------------------------------------------------------------------------- #


def run_leakage_audit(
    endpoint_data: EndpointData,
    *,
    ad_index: ADIndex | None = None,
    calibrator: PlattCalibrator | TemperatureScaler | None = None,
) -> LeakageAuditReport:
    """Run all applicable leakage checks for one endpoint.

    The 6 EndpointData-only checks and the 2 per-seed-fold checks always run.
    The AD-index check runs only if `ad_index` is given; the calibrator check
    runs only if `calibrator` is given — both are optional artifacts that may
    not exist yet for every endpoint at call time.
    """
    checks = [
        check_test_disjoint_from_train_val_smiles(endpoint_data),
        check_test_disjoint_from_train_val_scaffolds(endpoint_data),
        check_calibration_subset_of_train_val(endpoint_data),
        check_calibration_disjoint_from_test(endpoint_data),
        check_no_duplicate_smiles_within_train_val(endpoint_data),
        check_no_duplicate_smiles_within_test(endpoint_data),
        check_seed_fold_scaffold_isolation(endpoint_data),
        check_seed_folds_cover_train_val(endpoint_data),
    ]
    if ad_index is not None:
        checks.append(check_ad_index_disjoint_from_test(endpoint_data, ad_index))
    if calibrator is not None:
        checks.append(check_calibrator_fit_sample_count(endpoint_data, calibrator))

    return LeakageAuditReport(endpoint_key=endpoint_data.endpoint_key, checks=checks)
