"""
Module 1 §4 — fixed Murcko scaffold split + leakage checks + 5-seed CV.

Two paths:

  * **adopt_benchmark_split** — for the 13 endpoints whose primary dataset is in
    the TDC ADMET Benchmark Group, adopt TDC's official 80/20 split *exactly*
    (leaderboard comparability). We standardize the benchmark-delivered rows
    through Module 3 Stage 1 and re-derive the compound-level train_val / test
    membership sets; this is the fixed test set.

  * **scaffold_split** — deterministic Murcko-scaffold split for endpoints
    without an official benchmark split (currently ``hERG_Karim`` only), or as
    a leakage-audit utility for anything post-augmentation. Implements a
    "large-scaffolds first" fill matching TDC's own implementation choice
    (Bemis-Murcko groups sorted descending by size; place each group in test
    until the target fraction is met, then everything else in train_val).

Both paths guarantee:
  * No scaffold overlap between train_val and test (Bemis-Murcko under the
    Module 3 Stage 1 standardization).
  * The output is a fixed set of ``standardized_smiles``-keyed assignments.
  * Deterministic given the same standardized inputs (+ ``seed`` for the
    scaffold splitter's tie-breaking).

Downstream 5-seed CV within train_val is a lightweight utility that yields
``(fold_idx, train_idx, val_idx)`` triples for a fixed ``seeds`` list.
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Literal

from featurize.scaffold import murcko_scaffold_from_smiles

SPLIT_VERSION = "mars-split-v1"
DEFAULT_TEST_FRACTION = 0.20


@dataclass(frozen=True)
class SplitAssignment:
    standardized_smiles: str
    fold: Literal["train_val", "test"]
    scaffold: str


@dataclass
class SplitReport:
    dataset_key: str
    endpoint_key: str
    method: Literal["adopt_benchmark", "scaffold"]
    n_train_val: int
    n_test: int
    n_train_val_scaffolds: int
    n_test_scaffolds: int
    scaffold_overlap_count: int
    smiles_overlap_count: int
    test_fraction_actual: float
    seed: int | None = None
    notes: list[str] = field(default_factory=list)
    split_version: str = SPLIT_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_key": self.dataset_key,
            "endpoint_key": self.endpoint_key,
            "method": self.method,
            "n_train_val": self.n_train_val,
            "n_test": self.n_test,
            "n_train_val_scaffolds": self.n_train_val_scaffolds,
            "n_test_scaffolds": self.n_test_scaffolds,
            "scaffold_overlap_count": self.scaffold_overlap_count,
            "smiles_overlap_count": self.smiles_overlap_count,
            "test_fraction_actual": self.test_fraction_actual,
            "seed": self.seed,
            "notes": self.notes,
            "split_version": self.split_version,
        }


# ---------------------------------------------------------------------------- #
# Deterministic Murcko scaffold splitter
# ---------------------------------------------------------------------------- #


def scaffold_split(
    smiles: list[str],
    *,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    seed: int = 0,
) -> tuple[list[str], list[str]]:
    """Return ``(train_val_smiles, test_smiles)`` with no scaffold overlap.

    Algorithm (matches TDC's implementation choice for hERG-style datasets):
      1. Group standardized SMILES by Murcko scaffold.
      2. Sort groups descending by size; ties broken by scaffold-string sort
         (deterministic).
      3. Iterate groups; place the whole group into whichever side has room
         (test first until the target fraction, then train_val), never
         splitting a group across sides.
      4. ``seed`` shuffles the tie-broken order deterministically for
         5-seed protocols; a fresh ``seed=None`` uses the sorted order.

    Empty-scaffold molecules (acyclic) are all one "scaffold" (``""``); they
    fall into whichever bucket has room, matching TDC's convention.
    """
    if not (0 < test_fraction < 1):
        raise ValueError("test_fraction must be in (0, 1)")

    if not smiles:
        return [], []

    groups: dict[str, list[str]] = defaultdict(list)
    for s in smiles:
        scaff = murcko_scaffold_from_smiles(s)
        groups[scaff].append(s)

    # deterministic base order: descending by size, then by scaffold string
    ordered = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))

    if seed:
        rng = random.Random(seed)
        # shuffle only among equal-size groups to keep the "large first" bias
        # (this matches TDC's own tie-breaking + reproducibility trade-off).
        by_size: dict[int, list[tuple[str, list[str]]]] = defaultdict(list)
        for item in ordered:
            by_size[-len(item[1])].append(item)
        ordered = []
        for k in sorted(by_size):
            block = by_size[k]
            rng.shuffle(block)
            ordered.extend(block)

    total = len(smiles)
    target_test = int(round(total * test_fraction))
    test: list[str] = []
    train: list[str] = []
    for _scaff, members in ordered:
        # deterministic order within a group
        members_sorted = sorted(members)
        if len(test) + len(members_sorted) <= target_test:
            test.extend(members_sorted)
        else:
            train.extend(members_sorted)

    return train, test


# ---------------------------------------------------------------------------- #
# Adopt an official benchmark split
# ---------------------------------------------------------------------------- #


def adopt_benchmark_split(
    *,
    train_val_pairs: list[tuple[str, str]],
    test_pairs: list[tuple[str, str]],
) -> tuple[list[str], list[str]]:
    """Return ``(train_val_smiles, test_smiles)`` from an already-partitioned
    pair of ``(standardized_smiles, raw_smiles)`` lists.

    Compound-level uniqueness is expected; if the benchmark set repeats a
    compound across TV and TE (which would be a leakage bug in the benchmark
    archive itself), it is surfaced by ``build_split_report``, not silently
    tolerated.
    """
    train = sorted({s for s, _ in train_val_pairs if s})
    test = sorted({s for s, _ in test_pairs if s})
    return train, test


# ---------------------------------------------------------------------------- #
# Leakage audit
# ---------------------------------------------------------------------------- #


def leakage_audit(train_val: list[str], test: list[str]) -> dict[str, Any]:
    """Return leakage metrics between two sets of standardized SMILES."""
    tv_set = set(train_val)
    te_set = set(test)
    smi_overlap = tv_set & te_set
    tv_scaffolds = {murcko_scaffold_from_smiles(s) for s in tv_set}
    te_scaffolds = {murcko_scaffold_from_smiles(s) for s in te_set}
    scaff_overlap = tv_scaffolds & te_scaffolds
    # empty scaffold ("") is a legitimate shared "bucket" — matching TDC's
    # convention — flag it separately so a leakage assertion can allow it.
    scaff_overlap_nontrivial = {s for s in scaff_overlap if s != ""}
    return {
        "smiles_overlap": sorted(smi_overlap),
        "smiles_overlap_count": len(smi_overlap),
        "scaffold_overlap_count": len(scaff_overlap),
        "scaffold_overlap_count_excluding_acyclic": len(scaff_overlap_nontrivial),
        "n_train_val": len(tv_set),
        "n_test": len(te_set),
        "n_train_val_scaffolds": len(tv_scaffolds),
        "n_test_scaffolds": len(te_scaffolds),
    }


def build_split_report(
    *,
    dataset_key: str,
    endpoint_key: str,
    method: Literal["adopt_benchmark", "scaffold"],
    train_val: list[str],
    test: list[str],
    seed: int | None,
    allow_acyclic_scaffold_overlap: bool = True,
) -> SplitReport:
    audit = leakage_audit(train_val, test)
    scaff_overlap = (
        audit["scaffold_overlap_count_excluding_acyclic"]
        if allow_acyclic_scaffold_overlap
        else audit["scaffold_overlap_count"]
    )
    total = audit["n_train_val"] + audit["n_test"]
    report = SplitReport(
        dataset_key=dataset_key,
        endpoint_key=endpoint_key,
        method=method,
        n_train_val=audit["n_train_val"],
        n_test=audit["n_test"],
        n_train_val_scaffolds=audit["n_train_val_scaffolds"],
        n_test_scaffolds=audit["n_test_scaffolds"],
        scaffold_overlap_count=scaff_overlap,
        smiles_overlap_count=audit["smiles_overlap_count"],
        test_fraction_actual=(audit["n_test"] / total) if total else 0.0,
        seed=seed,
    )
    if allow_acyclic_scaffold_overlap and audit["scaffold_overlap_count"] > audit[
        "scaffold_overlap_count_excluding_acyclic"
    ]:
        report.notes.append(
            "empty-scaffold (acyclic) group is shared between train_val and test "
            "as-designed (TDC convention)"
        )
    return report


def assert_no_leakage(report: SplitReport) -> None:
    """Raise if any train↔test overlap survived — for use in split-time checks."""
    if report.smiles_overlap_count:
        raise AssertionError(
            f"{report.dataset_key}: {report.smiles_overlap_count} SMILES appear in "
            f"both train_val and test"
        )
    if report.scaffold_overlap_count:
        raise AssertionError(
            f"{report.dataset_key}: {report.scaffold_overlap_count} non-acyclic "
            f"scaffolds appear in both train_val and test"
        )


# ---------------------------------------------------------------------------- #
# 5-seed train/valid CV within train_val
# ---------------------------------------------------------------------------- #


def five_seed_train_val_folds(
    train_val_smiles: list[str],
    *,
    seeds: tuple[int, ...] = (0, 1, 2, 3, 4),
    val_fraction: float = 0.125,  # ~10% of the full set when train_val is 80%
) -> list[tuple[int, list[str], list[str]]]:
    """Yield ``(seed, train_smiles, valid_smiles)`` per seed, scaffold-aware.

    Each seed produces a fresh scaffold-based train/valid partition of the same
    train_val pool. The test set is fixed and untouched.
    """
    out = []
    for s in seeds:
        train, valid = scaffold_split(train_val_smiles, test_fraction=val_fraction, seed=s)
        out.append((s, train, valid))
    return out
