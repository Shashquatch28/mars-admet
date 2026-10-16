"""
Cluster-level (multi-endpoint) dataset loader for multi-task training.

Builds the wide label table a multi-task run needs — one row per molecule, one
NaN-able column per endpoint — on top of ``data.loaders.load_endpoint``.

THE REASON THIS MODULE EXISTS: cross-endpoint split leakage
------------------------------------------------------------
Twelve of MARS's endpoints adopt their *own* TDC benchmark split. Those splits
were computed independently, so a molecule can legitimately be ``train_val`` for
``solubility_logs`` and ``test`` for ``hia_absorption``. In single-task training
that is harmless — the two models share nothing. In multi-task training they
share an encoder, so fitting on that molecule's solubility label contaminates
the HIA test set *through the encoder*, and every existing leakage check still
passes because all of them are within-endpoint.

Fix, applied unconditionally here: the union of every member endpoint's test set
is removed from the shared ``train_val`` (and from the shared calibration split)
**in all columns**. The cost in discarded labels is measured, not assumed — see
:class:`ClusterSplitReport`, which must be inspected before any GPU time is spent.

Per-endpoint test metrics are still computed on that endpoint's own test rows (a
subset of the union), which preserves comparability with the XGBoost baselines
and with the TDC leaderboard.

See ``documentation/AIMS/decisions.md`` (2026-09-20, finding 1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from configs.clusters import endpoint_task_types
from mars_contracts.endpoints import TaskType

from data.loaders import EndpointData, load_endpoint
from data.split import leakage_audit

SMILES_COL = "standardized_smiles"


@dataclass
class ClusterSplitReport:
    """Audit of what leakage-safe cluster assembly cost, per endpoint.

    ``labels_sacrificed`` is the number of usable training labels an endpoint
    lost because the molecule carrying them sits in *another* member endpoint's
    test set. A large sacrifice is a legitimate reason to narrow a cluster's
    membership — inspect this before training, not after.
    """

    cluster_key: str
    endpoint_keys: list[str]
    n_train_val_rows: int
    n_test_rows: int
    n_calibration_rows: int
    n_rows_dropped_from_train_val: int
    n_rows_dropped_from_calibration: int
    labels_sacrificed: dict[str, int] = field(default_factory=dict)
    labels_retained: dict[str, int] = field(default_factory=dict)
    smiles_overlap_count: int = 0
    scaffold_overlap_count_excluding_acyclic: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def sacrifice_fraction(self) -> dict[str, float]:
        """Fraction of each endpoint's original train_val labels that were dropped."""
        out: dict[str, float] = {}
        for key, lost in self.labels_sacrificed.items():
            total = lost + self.labels_retained.get(key, 0)
            out[key] = (lost / total) if total else 0.0
        return out

    def to_dict(self) -> dict:
        d = {
            "cluster_key": self.cluster_key,
            "endpoint_keys": list(self.endpoint_keys),
            "n_train_val_rows": self.n_train_val_rows,
            "n_test_rows": self.n_test_rows,
            "n_calibration_rows": self.n_calibration_rows,
            "n_rows_dropped_from_train_val": self.n_rows_dropped_from_train_val,
            "n_rows_dropped_from_calibration": self.n_rows_dropped_from_calibration,
            "labels_sacrificed": dict(self.labels_sacrificed),
            "labels_retained": dict(self.labels_retained),
            "sacrifice_fraction": self.sacrifice_fraction,
            "smiles_overlap_count": self.smiles_overlap_count,
            "scaffold_overlap_count_excluding_acyclic": (
                self.scaffold_overlap_count_excluding_acyclic
            ),
            "notes": list(self.notes),
        }
        return d


@dataclass
class ClusterData:
    """Wide multi-endpoint splits for one cluster or type-homogeneous subgroup.

    ``train_val``/``test``/``calibration`` all have the shape
    ``[standardized_smiles, <endpoint_1>, ..., <endpoint_T>]`` with ``NaN``
    wherever that molecule carries no label for that endpoint.
    """

    cluster_key: str
    endpoint_keys: list[str]
    task_types: dict[str, TaskType]
    prep_id: str
    train_val: pd.DataFrame
    test: pd.DataFrame
    calibration: pd.DataFrame
    split_report: ClusterSplitReport
    per_endpoint: dict[str, EndpointData] = field(default_factory=dict)

    @property
    def n_targets(self) -> int:
        return len(self.endpoint_keys)

    def label_matrix(self, split: str = "train_val") -> np.ndarray:
        """Return the ``(n_rows, n_targets)`` label matrix for *split*.

        Column order is ``endpoint_keys`` order. Missing labels are ``np.nan``,
        which is the convention both ``featurize.kermt_adapter.write_finetune_csv``
        (empty cell) and the Tier-1 masked loss expect.
        """
        df = getattr(self, split)
        return df[self.endpoint_keys].to_numpy(dtype=float)

    def smiles(self, split: str = "train_val") -> list[str]:
        df = getattr(self, split)
        return df[SMILES_COL].tolist()

    def positive_rates(self, split: str = "train_val") -> dict[str, float | None]:
        """Positive rate per **classification** endpoint in *split*.

        ``None`` when an endpoint has no labelled rows there. Regression
        endpoints are omitted — a "positive rate" is meaningless for them.
        """
        df = getattr(self, split)
        out: dict[str, float | None] = {}
        for key in self.endpoint_keys:
            if self.task_types[key] is not TaskType.CLASSIFICATION:
                continue
            col = df[key].dropna()
            out[key] = float(col.mean()) if len(col) else None
        return out

    def calibration_molecules(self) -> set[str]:
        """Every molecule in ANY member endpoint's calibration split."""
        return set(self.calibration[SMILES_COL])

    def train_pool(
        self, *, holdout_calibration: bool = True
    ) -> tuple[pd.DataFrame, dict[str, int]]:
        """The rows a model may train on and select epochs against.

        With ``holdout_calibration=True`` (the default) every molecule in any
        member endpoint's calibration split is removed from the pool **in all
        columns**.

        Why this is needed, and why it is stricter than per-column masking:

        * ``train_val.csv`` *contains* the calibration molecules (M1 carves the
          calibration split out of train_val; ``assignments.csv`` merely labels
          them). Nothing stops a caller from training on them.
        * KERMT selects its best epoch on the validation fold. On the M1
          snapshot the calibration split makes up most of that fold, so leaving
          it in would mean the calibrator is fit on molecules the model was
          *selected* on — the exact thing calibration must not do.
        * A calibration molecule for endpoint A may still carry a label for
          endpoint B in the same cluster. Keeping it in training via B's label
          would still expose the shared encoder to it, and CYP labels in
          particular are strongly correlated across the Veith screens. So the
          whole molecule is held out, not just A's column.

        Returns
        -------
        (pool, labels_held_out)
            ``labels_held_out`` counts, per endpoint, the training labels lost
            to this holdout — measured, so its cost is never a surprise. This is
            *additional* to the union-test removal already reported in
            ``split_report``.
        """
        if not holdout_calibration:
            return self.train_val.copy(), {k: 0 for k in self.endpoint_keys}

        held = self.calibration_molecules()
        mask = self.train_val[SMILES_COL].isin(held)
        lost = {
            k: int(self.train_val.loc[mask, k].notna().sum()) for k in self.endpoint_keys
        }
        return self.train_val[~mask].reset_index(drop=True), lost

    def endpoint_test_frame(self, endpoint_key: str) -> pd.DataFrame:
        """That endpoint's own test rows — the subset with a non-NaN label.

        This is what per-endpoint test metrics must be computed on so cluster
        results stay comparable with the single-task and XGBoost baselines.
        """
        if endpoint_key not in self.endpoint_keys:
            raise ValueError(
                f"{endpoint_key!r} is not a member of cluster {self.cluster_key!r}"
            )
        sub = self.test[[SMILES_COL, endpoint_key]]
        return sub[sub[endpoint_key].notna()].reset_index(drop=True)


def _wide_frame(
    frames: dict[str, pd.DataFrame], endpoint_keys: list[str]
) -> pd.DataFrame:
    """Outer-join per-endpoint ``[smiles, label]`` frames into one wide table."""
    wide: pd.DataFrame | None = None
    for key in endpoint_keys:
        df = frames[key]
        dup = df[SMILES_COL].duplicated()
        if dup.any():
            n = int(dup.sum())
            raise ValueError(
                f"{key}: {n} duplicate {SMILES_COL} values in a processed split. "
                "M1 dedup should have removed these; a multi-task outer join "
                "would silently fan them out into a cartesian product."
            )
        part = df[[SMILES_COL, "label"]].rename(columns={"label": key})
        wide = part if wide is None else wide.merge(part, on=SMILES_COL, how="outer")
    assert wide is not None  # endpoint_keys is validated non-empty by the caller
    return wide.reset_index(drop=True)


def load_cluster(
    prep_dir: Path | str,
    endpoint_keys: list[str],
    *,
    cluster_key: str,
    use_augmented_dili: bool = False,
) -> ClusterData:
    """Load a leakage-safe wide label table for a set of endpoints.

    Parameters
    ----------
    prep_dir:
        Path to ``ml/data/processed/<prep_id>/``.
    endpoint_keys:
        Member endpoint keys. Column order in the returned frames follows this
        order exactly — it is the target order the KERMT adapter and the Tier-1
        trainer both key off.
    cluster_key:
        Identifier for this grouping (a cluster key like ``"metabolism"`` or a
        subgroup key like ``"metabolism__cls"``). Recorded in the report and
        used as ``ExperimentConfig.endpoint``.
    use_augmented_dili:
        Forwarded to ``load_endpoint`` for the DILI member, if present.

    Returns
    -------
    ClusterData
        With the union of all member test sets already removed from
        ``train_val`` and ``calibration``.

    Raises
    ------
    ValueError
        If *endpoint_keys* is empty or contains an unknown key.
    AssertionError
        If any molecule still appears in both the assembled ``train_val`` and
        the union test set after removal (should be impossible by construction —
        this is a guard against a future refactor breaking the invariant).
    """
    if not endpoint_keys:
        raise ValueError("endpoint_keys must be non-empty")
    if len(set(endpoint_keys)) != len(endpoint_keys):
        raise ValueError(f"endpoint_keys contains duplicates: {endpoint_keys}")

    task_types = endpoint_task_types(endpoint_keys)
    for key, tt in task_types.items():
        if tt is TaskType.RULE_BASED:
            raise ValueError(
                f"{key!r} is rule-based and cannot take part in a trained cluster"
            )

    prep_dir = Path(prep_dir)
    per_endpoint: dict[str, EndpointData] = {
        key: load_endpoint(prep_dir, key, use_augmented_dili=use_augmented_dili)
        for key in endpoint_keys
    }
    prep_id = per_endpoint[endpoint_keys[0]].prep_id

    train_val = _wide_frame(
        {k: d.train_val for k, d in per_endpoint.items()}, endpoint_keys
    )
    test = _wide_frame({k: d.test for k, d in per_endpoint.items()}, endpoint_keys)
    calibration = _wide_frame(
        {k: d.calibration for k, d in per_endpoint.items()}, endpoint_keys
    )

    # --- the leakage fix: drop the union of member test molecules everywhere ---
    cluster_test_smiles: set[str] = set(test[SMILES_COL])

    labels_before = {k: int(train_val[k].notna().sum()) for k in endpoint_keys}
    tv_contaminated = train_val[SMILES_COL].isin(cluster_test_smiles)
    cal_contaminated = calibration[SMILES_COL].isin(cluster_test_smiles)

    n_tv_dropped = int(tv_contaminated.sum())
    n_cal_dropped = int(cal_contaminated.sum())

    train_val = train_val[~tv_contaminated].reset_index(drop=True)
    calibration = calibration[~cal_contaminated].reset_index(drop=True)

    labels_after = {k: int(train_val[k].notna().sum()) for k in endpoint_keys}
    sacrificed = {k: labels_before[k] - labels_after[k] for k in endpoint_keys}

    audit = leakage_audit(train_val[SMILES_COL].tolist(), sorted(cluster_test_smiles))

    report = ClusterSplitReport(
        cluster_key=cluster_key,
        endpoint_keys=list(endpoint_keys),
        n_train_val_rows=len(train_val),
        n_test_rows=len(test),
        n_calibration_rows=len(calibration),
        n_rows_dropped_from_train_val=n_tv_dropped,
        n_rows_dropped_from_calibration=n_cal_dropped,
        labels_sacrificed=sacrificed,
        labels_retained=labels_after,
        smiles_overlap_count=audit["smiles_overlap_count"],
        scaffold_overlap_count_excluding_acyclic=audit[
            "scaffold_overlap_count_excluding_acyclic"
        ],
    )

    if audit["smiles_overlap_count"]:
        raise AssertionError(
            f"{cluster_key}: {audit['smiles_overlap_count']} molecules remain in "
            "both the cluster train_val and the union test set after removal. "
            "The union-test-removal invariant is broken."
        )

    # Scaffold-bucket overlap is REPORTED, never fatal. RDKit-vs-TDC Murcko
    # bucket assignment differs for a handful of molecules in adopted benchmark
    # splits — documented since M1 Run 2 and re-confirmed by the M2 preflight.
    # Treating it as blocking caused two false-alarm STOPs already; see
    # documentation/AIMS/mistakes.md.
    if report.scaffold_overlap_count_excluding_acyclic:
        report.notes.append(
            f"{report.scaffold_overlap_count_excluding_acyclic} non-acyclic scaffold "
            "buckets are shared between cluster train_val and the union test set. "
            "Benign RDKit-vs-TDC bucket noise (documented M1 Run 2); zero exact "
            "SMILES overlap is the binding guarantee and it holds."
        )

    return ClusterData(
        cluster_key=cluster_key,
        endpoint_keys=list(endpoint_keys),
        task_types=task_types,
        prep_id=prep_id,
        train_val=train_val,
        test=test,
        calibration=calibration,
        split_report=report,
        per_endpoint=per_endpoint,
    )
