"""
Multi-task cluster registry and type-homogeneous subgroup decomposition.

Why this lives in ``ml/configs/`` and NOT in ``contracts/``
-----------------------------------------------------------
``ENDPOINT_METADATA[...]["cluster"]`` is the *serving/routing* contract — the
four clusters consumed by ``api/`` and ``frontend/``. The subgroups defined here
are a **training-time artifact** of a third-party limitation: KERMT's finetune
CLI accepts one ``--dataset_type`` per run, so a cluster mixing classification
and regression endpoints cannot be trained by it in a single run. That is an
implementation detail of one model family and must not leak into the public
contract.

Everything here is **derived** from ``ENDPOINT_METADATA``, never re-listed, so
the two cannot drift (pinned by ``ml/tests/test_clusters.py``).

See ``documentation/AIMS/decisions.md`` (2026-09-20) for the three-tier ladder
this supports, and ``next_steps.md`` for the live work breakdown.
"""

from __future__ import annotations

from dataclasses import dataclass

from mars_contracts.endpoints import ENDPOINT_METADATA, TaskType

CLS_SUFFIX = "__cls"
REG_SUFFIX = "__reg"

_TASK_SUFFIX: dict[TaskType, str] = {
    TaskType.CLASSIFICATION: CLS_SUFFIX,
    TaskType.REGRESSION: REG_SUFFIX,
}


def _cluster_of(meta: dict) -> str | None:
    return meta["cluster"]


# Deterministic: dict insertion order of ENDPOINT_METADATA, which follows the
# Endpoint enum declaration order.
CLUSTER_KEYS: tuple[str, ...] = tuple(
    dict.fromkeys(
        c for m in ENDPOINT_METADATA.values() if (c := _cluster_of(m)) is not None
    )
)


def cluster_members(cluster: str) -> list[str]:
    """Return the endpoint keys belonging to *cluster*, in enum order.

    Raises
    ------
    ValueError
        If *cluster* is not a known cluster key.
    """
    if cluster not in CLUSTER_KEYS:
        raise ValueError(
            f"Unknown cluster {cluster!r}. Valid clusters: {list(CLUSTER_KEYS)}"
        )
    return [
        ep.value for ep, m in ENDPOINT_METADATA.items() if _cluster_of(m) == cluster
    ]


def endpoint_task_types(endpoint_keys: list[str]) -> dict[str, TaskType]:
    """Map each endpoint key to its ``TaskType``, preserving input order."""
    by_key = {ep.value: m["task_type"] for ep, m in ENDPOINT_METADATA.items()}
    out: dict[str, TaskType] = {}
    for key in endpoint_keys:
        if key not in by_key:
            valid = sorted(by_key)
            raise ValueError(f"Unknown endpoint key {key!r}. Valid values: {valid}")
        out[key] = by_key[key]
    return out


@dataclass(frozen=True)
class SubgroupSpec:
    """One type-homogeneous group of endpoints trainable by KERMT's stock CLI.

    Attributes
    ----------
    key:
        Subgroup identifier, e.g. ``"metabolism__cls"``. Used as the
        ``ExperimentConfig.endpoint`` value for cluster-level runs.
    cluster:
        The parent blueprint cluster this was derived from.
    endpoints:
        Member endpoint keys, all sharing ``task_type``.
    task_type:
        The single task type shared by every member — this is exactly the value
        that can be handed to KERMT's ``--dataset_type``.
    """

    key: str
    cluster: str
    endpoints: tuple[str, ...]
    task_type: TaskType

    @property
    def is_single_task(self) -> bool:
        """True when this subgroup has exactly one member endpoint.

        A single-task subgroup is **not a multi-task cluster arm**. It is the
        mandatory single-task baseline that blueprint Module 4 already requires
        for that endpoint, and it must be run and reported as such
        (``model_family="kermt_single"``). Reporting it as a multi-task result
        would fabricate a multi-task number out of a single-task run.

        ``metabolism__reg`` (= ``clearance_microsomal`` alone) is the live
        instance of this.
        """
        return len(self.endpoints) == 1

    @property
    def model_family(self) -> str:
        """The ``ExperimentConfig.model_family`` this subgroup must be run under."""
        return "kermt_single" if self.is_single_task else "kermt_multitask_subgroup"


def type_homogeneous_subgroups(cluster: str) -> dict[str, SubgroupSpec]:
    """Split *cluster* into groups that each share one task type.

    A pure cluster yields a single subgroup; a mixed cluster yields two. Order
    is classification-then-regression when both are present.
    """
    members = cluster_members(cluster)
    types = endpoint_task_types(members)

    out: dict[str, SubgroupSpec] = {}
    for task_type in (TaskType.CLASSIFICATION, TaskType.REGRESSION):
        group = tuple(k for k in members if types[k] == task_type)
        if not group:
            continue
        key = f"{cluster}{_TASK_SUFFIX[task_type]}"
        out[key] = SubgroupSpec(
            key=key, cluster=cluster, endpoints=group, task_type=task_type
        )
    return out


def all_subgroups() -> dict[str, SubgroupSpec]:
    """Every type-homogeneous subgroup across every cluster, keyed by subgroup key."""
    out: dict[str, SubgroupSpec] = {}
    for cluster in CLUSTER_KEYS:
        out.update(type_homogeneous_subgroups(cluster))
    return out


def is_mixed_cluster(cluster: str) -> bool:
    """True when *cluster* contains both classification and regression endpoints.

    These are the clusters KERMT's stock CLI cannot train in one run, and the
    ones the Tier-1 mixed trainer and Tier-2 ordinal encoding exist for.
    """
    return len(type_homogeneous_subgroups(cluster)) > 1


def mixed_clusters() -> tuple[str, ...]:
    """The clusters requiring Tier 1 / Tier 2 treatment, in cluster order."""
    return tuple(c for c in CLUSTER_KEYS if is_mixed_cluster(c))


def multitask_subgroups() -> dict[str, SubgroupSpec]:
    """Subgroups that are genuine multi-task arms (>1 endpoint).

    Excludes single-task subgroups, which belong to the single-task baseline
    track — see :attr:`SubgroupSpec.is_single_task`.
    """
    return {k: s for k, s in all_subgroups().items() if not s.is_single_task}
