"""
Tests for ml/data/cluster_loaders.py.

Runs against a synthetic processed-data directory rather than real M1 outputs,
so it exercises the leakage logic on this machine and in CI without needing the
(gitignored) datasets. The fixture deliberately plants a cross-endpoint leak:
molecule ``E`` is in ``clearance_microsomal``'s train_val AND in
``cyp3a4_inhibition``'s test set — exactly the situation that is harmless for
single-task training and silently contaminating for a shared encoder.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from data.cluster_loaders import SMILES_COL, load_cluster

# Valid, distinct SMILES so RDKit scaffold extraction in leakage_audit works.
A, B, C = "CCO", "CCC", "c1ccccc1"
D, E, F = "CCN", "CCCC", "c1ccncc1"
G, H = "CCCN", "c1ccc2ccccc2c1"

CYP = "cyp3a4_inhibition"
CLR = "clearance_microsomal"


def _write_split(ds_dir: Path, name: str, smiles: list[str], labels: list[float]) -> None:
    pd.DataFrame({SMILES_COL: smiles, "label": labels}).to_csv(
        ds_dir / f"{name}.csv", index=False
    )


@pytest.fixture
def prep_dir(tmp_path: Path) -> Path:
    root = tmp_path / "20260920T000000Z"

    cyp = root / CYP
    cyp.mkdir(parents=True)
    _write_split(cyp, "train_val", [A, B, C, D], [1.0, 0.0, 1.0, 0.0])
    _write_split(cyp, "test", [E, F], [1.0, 0.0])
    _write_split(cyp, "calibration", [A], [1.0])
    (cyp / "provenance.json").write_text(json.dumps({"split_method": "adopt_benchmark"}))

    clr = root / CLR
    clr.mkdir(parents=True)
    # E leaks: it is CYP's test molecule but carries a clearance train label.
    _write_split(clr, "train_val", [C, E, G], [12.5, 30.0, 4.0])
    _write_split(clr, "test", [H], [7.0])
    _write_split(clr, "calibration", [E], [30.0])
    (clr / "provenance.json").write_text(json.dumps({"split_method": "adopt_benchmark"}))

    return root


def test_wide_table_has_one_column_per_endpoint(prep_dir):
    cd = load_cluster(prep_dir, [CYP, CLR], cluster_key="metabolism")
    assert list(cd.train_val.columns) == [SMILES_COL, CYP, CLR]
    assert cd.n_targets == 2
    assert cd.prep_id == "20260920T000000Z"


def test_union_test_molecules_are_removed_from_train_val(prep_dir):
    """The whole point of this module: E must not survive in train_val."""
    cd = load_cluster(prep_dir, [CYP, CLR], cluster_key="metabolism")
    assert E not in set(cd.train_val[SMILES_COL])
    assert sorted(cd.train_val[SMILES_COL]) == sorted([A, B, C, D, G])
    assert cd.split_report.n_rows_dropped_from_train_val == 1


def test_leaked_molecule_is_removed_from_calibration_too(prep_dir):
    """Calibration is carved from train_val, so it inherits the same hazard."""
    cd = load_cluster(prep_dir, [CYP, CLR], cluster_key="metabolism")
    assert E not in set(cd.calibration[SMILES_COL])
    assert cd.split_report.n_rows_dropped_from_calibration == 1


def test_sacrifice_is_attributed_to_the_endpoint_that_lost_the_label(prep_dir):
    cd = load_cluster(prep_dir, [CYP, CLR], cluster_key="metabolism")
    rep = cd.split_report
    # Clearance loses E's label; CYP loses nothing (E was never its train label).
    assert rep.labels_sacrificed == {CYP: 0, CLR: 1}
    assert rep.labels_retained == {CYP: 4, CLR: 2}
    assert rep.sacrifice_fraction[CYP] == pytest.approx(0.0)
    assert rep.sacrifice_fraction[CLR] == pytest.approx(1 / 3)


def test_no_smiles_overlap_survives(prep_dir):
    cd = load_cluster(prep_dir, [CYP, CLR], cluster_key="metabolism")
    assert cd.split_report.smiles_overlap_count == 0
    assert not set(cd.train_val[SMILES_COL]) & set(cd.test[SMILES_COL])


def test_missing_labels_are_nan_not_zero(prep_dir):
    """A molecule labelled for one endpoint must be masked for the other.

    NaN (not 0.0) is what write_finetune_csv turns into an empty cell and what
    the masked loss skips; a 0.0 here would be a silently fabricated negative.
    """
    cd = load_cluster(prep_dir, [CYP, CLR], cluster_key="metabolism")
    row_a = cd.train_val[cd.train_val[SMILES_COL] == A].iloc[0]
    assert row_a[CYP] == 1.0
    assert np.isnan(row_a[CLR])

    row_g = cd.train_val[cd.train_val[SMILES_COL] == G].iloc[0]
    assert np.isnan(row_g[CYP])
    assert row_g[CLR] == 4.0


def test_shared_molecule_keeps_both_labels(prep_dir):
    cd = load_cluster(prep_dir, [CYP, CLR], cluster_key="metabolism")
    row_c = cd.train_val[cd.train_val[SMILES_COL] == C].iloc[0]
    assert row_c[CYP] == 1.0
    assert row_c[CLR] == 12.5


def test_label_matrix_shape_and_column_order(prep_dir):
    cd = load_cluster(prep_dir, [CYP, CLR], cluster_key="metabolism")
    m = cd.label_matrix("train_val")
    assert m.shape == (5, 2)
    assert m.dtype == float
    # Column order follows endpoint_keys, which is what the adapter keys off.
    assert cd.endpoint_keys == [CYP, CLR]


def test_endpoint_test_frame_returns_only_that_endpoints_rows(prep_dir):
    """Per-endpoint test metrics must use that endpoint's own test set."""
    cd = load_cluster(prep_dir, [CYP, CLR], cluster_key="metabolism")
    cyp_test = cd.endpoint_test_frame(CYP)
    assert sorted(cyp_test[SMILES_COL]) == sorted([E, F])
    clr_test = cd.endpoint_test_frame(CLR)
    assert list(clr_test[SMILES_COL]) == [H]


def test_endpoint_test_frame_rejects_non_member(prep_dir):
    cd = load_cluster(prep_dir, [CYP, CLR], cluster_key="metabolism")
    with pytest.raises(ValueError, match="not a member"):
        cd.endpoint_test_frame("ames_mutagenicity")


def test_task_types_come_from_the_contract(prep_dir):
    from mars_contracts.endpoints import TaskType

    cd = load_cluster(prep_dir, [CYP, CLR], cluster_key="metabolism")
    assert cd.task_types[CYP] is TaskType.CLASSIFICATION
    assert cd.task_types[CLR] is TaskType.REGRESSION


def test_single_endpoint_cluster_is_allowed(prep_dir):
    """metabolism__reg is a legitimate one-member subgroup."""
    cd = load_cluster(prep_dir, [CLR], cluster_key="metabolism__reg")
    assert cd.n_targets == 1
    # H is CLR's own test molecule, so it is removed from train_val as before.
    assert H not in set(cd.train_val[SMILES_COL])


def test_report_serializes(prep_dir):
    cd = load_cluster(prep_dir, [CYP, CLR], cluster_key="metabolism")
    d = cd.split_report.to_dict()
    assert d["cluster_key"] == "metabolism"
    assert d["labels_sacrificed"][CLR] == 1
    json.dumps(d)  # must be JSON-serializable for provenance


def test_duplicate_smiles_in_a_split_is_rejected(tmp_path):
    """An outer join over duplicated keys silently fans out to a cartesian product."""
    root = tmp_path / "prep"
    ds = root / CYP
    ds.mkdir(parents=True)
    _write_split(ds, "train_val", [A, A, B], [1.0, 0.0, 1.0])
    _write_split(ds, "test", [F], [0.0])
    _write_split(ds, "calibration", [B], [1.0])
    with pytest.raises(ValueError, match="duplicate"):
        load_cluster(root, [CYP], cluster_key="x")


def test_empty_and_duplicate_endpoint_keys_are_rejected(prep_dir):
    with pytest.raises(ValueError, match="non-empty"):
        load_cluster(prep_dir, [], cluster_key="x")
    with pytest.raises(ValueError, match="duplicates"):
        load_cluster(prep_dir, [CYP, CYP], cluster_key="x")


def test_rule_based_endpoint_is_rejected(prep_dir):
    with pytest.raises(ValueError, match="rule-based"):
        load_cluster(prep_dir, ["synthetic_accessibility"], cluster_key="x")


# ---------------------------------------------------------------------------- #
# train_pool / positive_rates (calibration holdout wiring, 2026-09-21)
# ---------------------------------------------------------------------------- #


def test_train_pool_holds_out_every_calibration_molecule(prep_dir):
    """A is CYP's calibration molecule; it must leave the pool in ALL columns."""
    cd = load_cluster(prep_dir, [CYP, CLR], cluster_key="metabolism")
    pool, lost = cd.train_pool(holdout_calibration=True)
    assert A not in set(pool[SMILES_COL])
    assert not cd.calibration_molecules() & set(pool[SMILES_COL])
    assert len(pool) == len(cd.train_val) - 1


def test_train_pool_reports_the_label_cost_per_endpoint(prep_dir):
    cd = load_cluster(prep_dir, [CYP, CLR], cluster_key="metabolism")
    _, lost = cd.train_pool(holdout_calibration=True)
    assert lost == {CYP: 1, CLR: 0}  # A carried a CYP label and no clearance label


def test_train_pool_without_holdout_is_unchanged_and_costs_nothing(prep_dir):
    cd = load_cluster(prep_dir, [CYP, CLR], cluster_key="metabolism")
    pool, lost = cd.train_pool(holdout_calibration=False)
    assert len(pool) == len(cd.train_val)
    assert lost == {CYP: 0, CLR: 0}


def test_train_pool_does_not_mutate_the_cluster_data(prep_dir):
    cd = load_cluster(prep_dir, [CYP, CLR], cluster_key="metabolism")
    before = cd.train_val.copy()
    cd.train_pool(holdout_calibration=True)
    pd.testing.assert_frame_equal(cd.train_val, before)


def test_positive_rates_cover_classification_endpoints_only(prep_dir):
    cd = load_cluster(prep_dir, [CYP, CLR], cluster_key="metabolism")
    rates = cd.positive_rates("train_val")
    assert set(rates) == {CYP}  # clearance is regression: no positive rate exists
    # Surviving CYP labels after union removal: A=1, B=0, C=1, D=0.
    assert rates[CYP] == pytest.approx(0.5)
