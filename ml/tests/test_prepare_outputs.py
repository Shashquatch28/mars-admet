"""
Integration tests that the persisted M1 processed outputs are internally
consistent (no leakage in what actually went to disk).

Skips cleanly if no acquisition + prepare have been run on this machine.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from data.split import build_split_report
from featurize.scaffold import murcko_scaffold_from_smiles

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "ml" / "data"


def _newest_prep_id() -> str | None:
    root = DATA / "processed"
    if not root.exists():
        return None
    ids = sorted(p.name for p in root.iterdir() if p.is_dir())
    return ids[-1] if ids else None


PREP_ID = _newest_prep_id()


def _read_col(path: Path, col: str) -> list[str]:
    with path.open(newline="", encoding="utf-8") as fh:
        return [r[col] for r in csv.DictReader(fh)]


def _dataset_dirs() -> list[Path]:
    if PREP_ID is None:
        return []
    return sorted(
        p for p in (DATA / "processed" / PREP_ID).iterdir() if p.is_dir()
    )


@pytest.fixture(scope="module")
def manifest():
    if PREP_ID is None:
        pytest.skip("no processed outputs")
    return json.loads((DATA / "processed" / PREP_ID / "manifest.json").read_text(encoding="utf-8"))


def test_manifest_names_versions(manifest):
    assert manifest["standardizer_version"].startswith("mars-standardizer-")
    assert manifest["dedup_version"].startswith("mars-dedup-")
    assert manifest["split_version"].startswith("mars-split-")
    assert manifest["prep_id"]


@pytest.mark.parametrize("ds", _dataset_dirs())
def test_processed_files_exist_and_are_disjoint(ds):
    prov = json.loads((ds / "provenance.json").read_text(encoding="utf-8"))
    if prov.get("note", "").startswith("split intentionally skipped"):
        pytest.skip(f"{ds.name}: split deferred")
    for name in ("train_val.csv", "test.csv", "calibration.csv", "assignments.csv"):
        assert (ds / name).exists(), name

    tv = set(_read_col(ds / "train_val.csv", "standardized_smiles"))
    te = set(_read_col(ds / "test.csv", "standardized_smiles"))
    cal = set(_read_col(ds / "calibration.csv", "standardized_smiles"))
    # test is fixed and never touched by tv or calibration
    assert not tv & te, f"{ds.name}: train_val ∩ test != ∅"
    assert not cal & te, f"{ds.name}: calibration ∩ test != ∅"
    # calibration is carved out of train_val (subset)
    assert cal.issubset(tv), f"{ds.name}: calibration ⊄ train_val"


@pytest.mark.parametrize("ds", _dataset_dirs())
def test_no_smiles_leakage_between_train_val_and_test(ds):
    prov = json.loads((ds / "provenance.json").read_text(encoding="utf-8"))
    if prov.get("note", "").startswith("split intentionally skipped"):
        pytest.skip(f"{ds.name}: split deferred")
    tv = _read_col(ds / "train_val.csv", "standardized_smiles")
    te = _read_col(ds / "test.csv", "standardized_smiles")
    r = build_split_report(
        dataset_key=ds.name, endpoint_key=ds.name,
        method="scaffold", train_val=tv, test=te, seed=None,
    )
    assert r.smiles_overlap_count == 0


@pytest.mark.parametrize("ds", _dataset_dirs())
def test_self_generated_split_has_no_scaffold_overlap(ds):
    """For our self-generated hERG_Karim split, non-empty scaffolds must not overlap
    train_val and test. Adopted TDC benchmark splits are exempted (the overlap
    is a property of TDC's split under our stricter Murcko definition; recorded
    in split_report.json)."""
    prov = json.loads((ds / "provenance.json").read_text(encoding="utf-8"))
    if prov.get("split_method") != "scaffold":
        pytest.skip("adopted benchmark split")
    tv_scaffs = {murcko_scaffold_from_smiles(s) for s in _read_col(ds / "train_val.csv", "standardized_smiles")}
    te_scaffs = {murcko_scaffold_from_smiles(s) for s in _read_col(ds / "test.csv", "standardized_smiles")}
    overlap = {s for s in tv_scaffs & te_scaffs if s != ""}
    assert overlap == set(), f"{ds.name}: {len(overlap)} shared non-empty scaffolds"


@pytest.mark.parametrize("ds", _dataset_dirs())
def test_provenance_records_versions_and_hashes(ds):
    prov = json.loads((ds / "provenance.json").read_text(encoding="utf-8"))
    if prov.get("note", "").startswith("split intentionally skipped"):
        pytest.skip(f"{ds.name}: split deferred")
    for k in ("standardizer_version", "dedup_version", "split_version"):
        assert prov[k]
    for name in ("train_val", "test", "calibration"):
        f = prov["files"][name]
        assert (REPO / "ml" / f["path"]).exists()
        # sha256 present and looks like a hex digest
        assert len(f["sha256"]) == 64 and all(c in "0123456789abcdef" for c in f["sha256"])
