"""
Module 1 §3 — deduplication + tiered conflict resolution.

Every acquired dataset is standardized (Module 3 Stage 1) and then reduced to
one row per unique standardized molecule using an **EDA-gated** policy chosen
per endpoint:

| Conflict rate (per endpoint, over multi-measurement molecules) | Policy |
|---|---|
| Low (< ~5%) | ``drop_conflicting`` — keep singletons and consensus groups; drop groups with any label disagreement |
| Moderate/high, OR dataset is small (e.g. DILI) | Regression: ``average``.  Classification: ``majority_vote``. Ties in majority-vote (even split) drop only that molecule. |

Small-dataset override applies to any endpoint whose full-set N is below
``SMALL_DATASET_N``. Blueprint calls this out explicitly for DILI; in practice
DILI has 0 conflicts, so the override is a safety net rather than a change.

**Auditable.** ``dedup_dataset`` returns a ``ResolutionReport`` naming every
molecule that was collapsed, dropped, averaged, or majority-voted, so
downstream code can persist the trail for Module 11 self-audit.

The policy chosen per endpoint by ``select_policy_from_eda`` is **derived from
the Run-2 EDA numbers**; the policy table (below) records the decision as-of
2026-08-30 so it is greppable and stays in sync with the EDA report.

Policy table (from ``ml/data/eda/20260830T191149Z/rollup.json``):

    solubility_logs   (reg, 94% conflict)  -> average
    lipophilicity_logp(reg,  0% conflict)  -> drop_conflicting  (no-op)
    caco2_permeability(reg, 67% conflict)  -> average
    hia_absorption   (clf,  0% conflict)   -> drop_conflicting  (no-op)
    pgp_inhibition   (clf,  0% conflict)   -> drop_conflicting  (no-op)
    bbb_permeability (clf, 18% conflict)   -> majority_vote
    ppb_binding      (reg,  0% conflict)   -> drop_conflicting  (no-op)
                        (see status/ppbr_az_investigation.md — split TBD)
    cyp3a4_inhibition(clf,  3% conflict)   -> drop_conflicting
    cyp2d6_inhibition(clf, 14% conflict)   -> majority_vote
    cyp2c9_inhibition(clf, 16% conflict)   -> majority_vote
    clearance_microsomal(reg, 0% conflict) -> drop_conflicting  (no-op)
    herg_cardiotoxicity(clf, 5.6% conflict, LARGE) -> majority_vote  (borderline; conservative)
    herg_cardiotoxicity__benchmark(clf, 23% conflict, SMALL) -> majority_vote
    ames_mutagenicity(clf,  0% conflict)   -> drop_conflicting  (no-op)
    dili_liver_injury(clf,  0% conflict, SMALL) -> majority_vote via small-dataset override
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Policy = Literal["drop_conflicting", "average", "majority_vote"]
Task = Literal["regression", "classification"]

DEDUP_VERSION = "mars-dedup-v1"

# Blueprint §3 threshold: "Low (~<5% of molecules have conflicting duplicate labels)".
# We interpret "molecules" as unique multi-measurement molecules (the denominator
# EDA reports as conflict_rate_over_multi_measurement_molecules).
LOW_CONFLICT_THRESHOLD = 0.05

# Blueprint calls DILI out by name. Extend to any dataset under this size when
# choosing policy from EDA. 1500 keeps DILI + HIA + Caco2 + Clearance + Pgp + PPB
# (human single_pred) + hERG-benchmark in the "small" bucket; hERG_Karim (13k)
# is not.
SMALL_DATASET_N = 1500


@dataclass(frozen=True)
class DedupOptions:
    policy: Policy
    task: Task
    rationale: str


@dataclass(frozen=True)
class DedupOutcome:
    """One resolved row: the standardized molecule + a single float label."""

    standardized_smiles: str
    label: float
    source_row_count: int
    action: Literal["kept", "averaged", "majority_vote", "consensus_kept"]


@dataclass
class ResolutionReport:
    dataset_key: str
    endpoint_key: str
    policy: Policy
    rationale: str
    n_input_valid: int
    n_output: int
    n_dropped_conflicting: int = 0
    n_dropped_tie: int = 0
    n_averaged: int = 0
    n_majority_voted: int = 0
    n_consensus_kept: int = 0
    n_singletons: int = 0
    dropped_smiles: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_key": self.dataset_key,
            "endpoint_key": self.endpoint_key,
            "policy": self.policy,
            "rationale": self.rationale,
            "n_input_valid": self.n_input_valid,
            "n_output": self.n_output,
            "n_dropped_conflicting": self.n_dropped_conflicting,
            "n_dropped_tie": self.n_dropped_tie,
            "n_averaged": self.n_averaged,
            "n_majority_voted": self.n_majority_voted,
            "n_consensus_kept": self.n_consensus_kept,
            "n_singletons": self.n_singletons,
            "dropped_smiles": self.dropped_smiles,
            "dedup_version": DEDUP_VERSION,
        }


# ---------------------------------------------------------------------------- #
# Policy selection
# ---------------------------------------------------------------------------- #


def select_policy(
    *,
    task: Task,
    conflict_rate_over_multi: float,
    dataset_n: int,
) -> DedupOptions:
    """Deterministic policy pick, per the blueprint's tiered rule."""
    is_small = dataset_n < SMALL_DATASET_N
    is_low = conflict_rate_over_multi < LOW_CONFLICT_THRESHOLD

    if is_low and not is_small:
        return DedupOptions(
            policy="drop_conflicting",
            task=task,
            rationale=(
                f"conflict rate {conflict_rate_over_multi:.1%} < "
                f"{LOW_CONFLICT_THRESHOLD:.0%} and dataset N={dataset_n} >= "
                f"{SMALL_DATASET_N}"
            ),
        )
    # Moderate/high OR small dataset → preserve sample size
    return DedupOptions(
        policy="average" if task == "regression" else "majority_vote",
        task=task,
        rationale=(
            f"conflict rate {conflict_rate_over_multi:.1%} "
            + ("(low but dataset is small) " if is_low else "(moderate/high) ")
            + f"and N={dataset_n} — preserve size per blueprint §3"
        ),
    )


def select_policy_from_eda(
    dataset_key: str,
    eda_rollup: dict,
) -> DedupOptions:
    entry = next(e for e in eda_rollup["datasets"] if e["dataset_key"] == dataset_key)
    return select_policy(
        task=entry["task"],
        conflict_rate_over_multi=entry["conflict_rate_over_multi_measurement_molecules"],
        dataset_n=entry["n_raw_rows"],
    )


# ---------------------------------------------------------------------------- #
# Core dedup
# ---------------------------------------------------------------------------- #


def _majority_vote(labels: list[float]) -> float | None:
    """Return the majority integer class label; ``None`` on a tie."""
    counts = Counter(int(x) for x in labels)
    top = counts.most_common()
    if len(top) > 1 and top[0][1] == top[1][1]:
        return None
    return float(top[0][0])


def _labels_agree_classification(labels: list[float]) -> bool:
    return len({int(x) for x in labels}) == 1


def _labels_agree_regression(labels: list[float], rel_tol: float = 0.05, abs_tol: float = 1e-6) -> bool:
    lo, hi = min(labels), max(labels)
    mean_abs = sum(abs(x) for x in labels) / len(labels)
    tol = max(abs_tol, rel_tol * mean_abs)
    return (hi - lo) <= tol


def dedup(
    *,
    dataset_key: str,
    endpoint_key: str,
    pairs: list[tuple[str, float]],
    options: DedupOptions,
) -> tuple[list[DedupOutcome], ResolutionReport]:
    """Apply ``options`` to ``pairs`` (standardized SMILES → label).

    Groups by standardized SMILES; singletons pass through with ``action="kept"``.
    Groups where all labels agree are collapsed with ``action="consensus_kept"``
    regardless of policy — no information is lost. Only *conflicting* groups
    exercise the policy.
    """
    groups: dict[str, list[float]] = defaultdict(list)
    for smi, y in pairs:
        groups[smi].append(y)

    outcomes: list[DedupOutcome] = []
    report = ResolutionReport(
        dataset_key=dataset_key,
        endpoint_key=endpoint_key,
        policy=options.policy,
        rationale=options.rationale,
        n_input_valid=len(pairs),
        n_output=0,
    )

    agree = _labels_agree_classification if options.task == "classification" else _labels_agree_regression

    for smi in sorted(groups):  # deterministic order
        ys = groups[smi]
        if len(ys) == 1:
            outcomes.append(DedupOutcome(smi, ys[0], 1, "kept"))
            report.n_singletons += 1
            continue

        if agree(ys):
            label = float(sum(ys) / len(ys)) if options.task == "regression" else float(int(ys[0]))
            outcomes.append(DedupOutcome(smi, label, len(ys), "consensus_kept"))
            report.n_consensus_kept += 1
            continue

        # conflicting group
        if options.policy == "drop_conflicting":
            report.n_dropped_conflicting += 1
            report.dropped_smiles.append(smi)
            continue

        if options.policy == "average":
            label = sum(ys) / len(ys)
            outcomes.append(DedupOutcome(smi, float(label), len(ys), "averaged"))
            report.n_averaged += 1
            continue

        if options.policy == "majority_vote":
            v = _majority_vote(ys)
            if v is None:
                # tie → drop only that molecule
                report.n_dropped_tie += 1
                report.dropped_smiles.append(smi)
                continue
            outcomes.append(DedupOutcome(smi, v, len(ys), "majority_vote"))
            report.n_majority_voted += 1
            continue

        raise AssertionError(f"unknown policy {options.policy!r}")

    report.n_output = len(outcomes)
    return outcomes, report


# ---------------------------------------------------------------------------- #
# Persistence helpers
# ---------------------------------------------------------------------------- #


def load_eda_rollup(data_root: Path, eda_id: str | None = None) -> dict:
    """Load the newest EDA rollup if ``eda_id`` is None."""
    eda_root = data_root / "eda"
    if eda_id is not None:
        path = eda_root / eda_id / "rollup.json"
    else:
        candidates = sorted(p for p in eda_root.iterdir() if p.is_dir())
        if not candidates:
            raise FileNotFoundError(f"no EDA outputs under {eda_root}")
        path = candidates[-1] / "rollup.json"
    return json.loads(path.read_text(encoding="utf-8"))


def write_resolution_report(path: Path, report: ResolutionReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
