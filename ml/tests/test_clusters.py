"""Tests for the cluster / type-homogeneous subgroup registry."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from configs.clusters import (
    CLUSTER_KEYS,
    SubgroupSpec,
    all_subgroups,
    cluster_members,
    endpoint_task_types,
    is_mixed_cluster,
    mixed_clusters,
    multitask_subgroups,
    type_homogeneous_subgroups,
)
from mars_contracts.endpoints import ENDPOINT_METADATA, TaskType


def test_cluster_keys_match_contract_exactly():
    """The registry must be DERIVED from ENDPOINT_METADATA, never re-listed.

    If someone adds a cluster to the contract and this file hardcoded its own
    list, cluster training would silently ignore the new cluster.
    """
    from_contract = {
        m["cluster"] for m in ENDPOINT_METADATA.values() if m["cluster"] is not None
    }
    assert set(CLUSTER_KEYS) == from_contract


def test_every_ml_endpoint_belongs_to_exactly_one_cluster():
    seen: dict[str, str] = {}
    for cluster in CLUSTER_KEYS:
        for key in cluster_members(cluster):
            assert key not in seen, f"{key} appears in both {seen[key]} and {cluster}"
            seen[key] = cluster
    expected = {
        ep.value
        for ep, m in ENDPOINT_METADATA.items()
        if m["task_type"] is not TaskType.RULE_BASED
    }
    assert set(seen) == expected


def test_rule_based_endpoint_is_not_in_any_cluster():
    all_members = {k for c in CLUSTER_KEYS for k in cluster_members(c)}
    assert "synthetic_accessibility" not in all_members


def test_unknown_cluster_raises():
    with pytest.raises(ValueError, match="Unknown cluster"):
        cluster_members("not_a_cluster")


def test_unknown_endpoint_raises():
    with pytest.raises(ValueError, match="Unknown endpoint key"):
        endpoint_task_types(["not_an_endpoint"])


def test_metabolism_splits_into_three_cls_and_one_reg():
    subs = type_homogeneous_subgroups("metabolism")
    assert set(subs) == {"metabolism__cls", "metabolism__reg"}
    cls = subs["metabolism__cls"]
    reg = subs["metabolism__reg"]
    assert cls.task_type is TaskType.CLASSIFICATION
    assert set(cls.endpoints) == {
        "cyp3a4_inhibition",
        "cyp2d6_inhibition",
        "cyp2c9_inhibition",
    }
    assert reg.task_type is TaskType.REGRESSION
    assert reg.endpoints == ("clearance_microsomal",)


def test_absorption_distribution_splits_three_cls_four_reg():
    subs = type_homogeneous_subgroups("absorption_distribution")
    assert set(subs["absorption_distribution__cls"].endpoints) == {
        "hia_absorption",
        "pgp_inhibition",
        "bbb_permeability",
    }
    assert set(subs["absorption_distribution__reg"].endpoints) == {
        "solubility_logs",
        "lipophilicity_logp",
        "caco2_permeability",
        "ppb_binding",
    }


def test_pure_cluster_yields_a_single_subgroup():
    subs = type_homogeneous_subgroups("toxicity")
    assert list(subs) == ["toxicity__cls"]
    assert not is_mixed_cluster("toxicity")


def test_mixed_clusters_are_exactly_metabolism_and_absorption_distribution():
    assert set(mixed_clusters()) == {"metabolism", "absorption_distribution"}


def test_subgroup_endpoints_all_share_its_task_type():
    for spec in all_subgroups().values():
        types = set(endpoint_task_types(list(spec.endpoints)).values())
        assert types == {spec.task_type}, f"{spec.key} is not homogeneous"


def test_subgroups_partition_their_cluster():
    for cluster in CLUSTER_KEYS:
        covered: list[str] = []
        for spec in type_homogeneous_subgroups(cluster).values():
            covered.extend(spec.endpoints)
        assert sorted(covered) == sorted(cluster_members(cluster))


def test_single_task_subgroup_is_flagged_and_routed_to_the_baseline_family():
    """metabolism__reg is the mandatory single-task baseline, NOT a cluster arm.

    Reporting it as multi-task would fabricate a multi-task result out of a
    single-task run — see documentation/AIMS/decisions.md (2026-09-20).
    """
    reg = type_homogeneous_subgroups("metabolism")["metabolism__reg"]
    assert reg.is_single_task
    assert reg.model_family == "kermt_single"

    cls = type_homogeneous_subgroups("metabolism")["metabolism__cls"]
    assert not cls.is_single_task
    assert cls.model_family == "kermt_multitask_subgroup"


def test_multitask_subgroups_excludes_single_task_ones():
    mt = multitask_subgroups()
    assert "metabolism__reg" not in mt
    assert set(mt) == {
        "metabolism__cls",
        "absorption_distribution__cls",
        "absorption_distribution__reg",
        "toxicity__cls",
    }
    assert all(not s.is_single_task for s in mt.values())


def test_subgroup_spec_is_frozen():
    spec = type_homogeneous_subgroups("toxicity")["toxicity__cls"]
    assert isinstance(spec, SubgroupSpec)
    with pytest.raises(FrozenInstanceError):
        spec.key = "mutated"  # type: ignore[misc]


def test_endpoint_task_types_preserves_input_order():
    keys = ["ames_mutagenicity", "herg_cardiotoxicity"]
    assert list(endpoint_task_types(keys)) == keys
