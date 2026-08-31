"""
Integrity + drift-guard tests for the dataset registry.

The registry (ml/data/dataset_registry.py) hardcodes endpoint key strings so the
isolated acquisition environment does not need mars_contracts. These tests run in
the working env where mars_contracts IS available, and fail loudly if the two
ever diverge.
"""

from __future__ import annotations

import pytest
from data.dataset_registry import (
    DATASET_SPECS,
    ML_ENDPOINT_KEYS,
    NON_DATASET_ENDPOINT_KEYS,
    primary_specs,
)

mars_contracts = pytest.importorskip("mars_contracts")


def test_every_ml_endpoint_has_exactly_one_primary_dataset():
    from mars_contracts import Endpoint

    ml_keys = {e.value for e in Endpoint} - NON_DATASET_ENDPOINT_KEYS
    primary_keys = [s.endpoint_key for s in primary_specs()]

    assert sorted(primary_keys) == sorted(ml_keys)
    assert len(primary_keys) == len(set(primary_keys)) == 14


def test_registry_endpoint_keys_are_valid_contract_values():
    from mars_contracts import Endpoint

    valid = {e.value for e in Endpoint}
    for spec in DATASET_SPECS.values():
        assert spec.endpoint_key in valid, spec.dataset_key


def test_ml_endpoint_keys_constant_matches_contracts():
    from mars_contracts import Endpoint

    assert ML_ENDPOINT_KEYS == frozenset(
        {e.value for e in Endpoint} - NON_DATASET_ENDPOINT_KEYS
    )


def test_sa_score_has_no_dataset():
    assert "synthetic_accessibility" not in {s.endpoint_key for s in DATASET_SPECS.values()}


def test_task_type_matches_contracts_metadata():
    from mars_contracts import ENDPOINT_METADATA, Endpoint, TaskType

    want = {
        TaskType.REGRESSION: "regression",
        TaskType.CLASSIFICATION: "classification",
    }
    for spec in DATASET_SPECS.values():
        meta = ENDPOINT_METADATA[Endpoint(spec.endpoint_key)]
        assert want[meta["task_type"]] == spec.task, spec.dataset_key


def test_both_herg_variants_present_and_distinct():
    herg = [s for s in DATASET_SPECS.values() if s.endpoint_key == "herg_cardiotoxicity"]
    assert {s.variant for s in herg} == {"primary", "benchmark_alt"}
    primary = next(s for s in herg if s.variant == "primary")
    alt = next(s for s in herg if s.variant == "benchmark_alt")
    assert primary.tdc_name == "hERG_Karim"
    assert primary.in_admet_benchmark_group is False
    assert alt.tdc_name == "hERG"
    assert alt.in_admet_benchmark_group is True


def test_all_datasets_are_cc_by_4():
    # blueprint Module 1 §7 — all 14 TDC endpoint datasets confirmed CC BY 4.0
    for spec in DATASET_SPECS.values():
        assert spec.license == "CC BY 4.0", spec.dataset_key


def test_primary_datasets_split_between_benchmark_and_self_generated():
    """Blueprint Module 1 §4 policy: adopt TDC benchmark split where an official
    one exists; self-generate a Murcko scaffold split where it does not.

    As of the 2026-08-30 Option C decision (PPB) and the 2026-08-30 hERG choice,
    two primary endpoints (herg_cardiotoxicity, ppb_binding) use a self-generated
    scaffold split rather than an official TDC benchmark split — see the blueprint
    "hERG exception" and "PPB exception" paragraphs in §4.
    """
    in_group = [s for s in primary_specs() if s.in_admet_benchmark_group]
    out_group = [s for s in primary_specs() if not s.in_admet_benchmark_group]
    assert len(in_group) == 12
    assert sorted(s.endpoint_key for s in out_group) == ["herg_cardiotoxicity", "ppb_binding"]


def test_ppb_has_both_primary_human_and_all_species_ablation_variants():
    ppb = [s for s in DATASET_SPECS.values() if s.endpoint_key == "ppb_binding"]
    assert {s.variant for s in ppb} == {"primary", "benchmark_alt"}
    primary = next(s for s in ppb if s.variant == "primary")
    ablation = next(s for s in ppb if s.variant == "benchmark_alt")
    assert primary.in_admet_benchmark_group is False, (
        "the TDC benchmark split pools all 5 species and does not partition the "
        "human subset — it cannot be adopted for the primary human endpoint"
    )
    assert ablation.in_admet_benchmark_group is True
    assert primary.approx_n == 1614
    assert ablation.approx_n == 1797
