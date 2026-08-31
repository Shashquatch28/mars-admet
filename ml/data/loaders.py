"""
M2 dataset loader — loads processed M1 splits for a given endpoint.

Consumes the ``ml/data/processed/<prep_id>/`` directory written by
``ml/data/prepare.py`` (M1). Never re-standardizes SMILES (they are canonical
fixed-points from M1). Never touches the test set for any purpose beyond
evaluation.

Public API
----------
load_endpoint(prep_dir, endpoint_key, ...)  →  EndpointData
load_manifest(prep_dir)                     →  dict
list_available_endpoints(prep_dir)          →  list[str]
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from mars_contracts.endpoints import ENDPOINT_METADATA, Endpoint, TaskType

_DILI_KEY = "dili_liver_injury"
_AUGMENTED_DILI_KEY = "dili_liver_injury__augmented"

# Dataset-key variants not in the Endpoint enum but with a known task type
_VARIANT_TASK_TYPES: dict[str, TaskType] = {
    _AUGMENTED_DILI_KEY: TaskType.CLASSIFICATION,
    "herg_cardiotoxicity__benchmark": TaskType.CLASSIFICATION,
}


@dataclass
class EndpointData:
    """All split DataFrames and metadata for one endpoint.

    Attributes
    ----------
    endpoint_key:
        Canonical endpoint key (e.g. ``"solubility_logs"``).
    dataset_key:
        Actual directory name under ``prep_dir/``; equals ``endpoint_key``
        unless the augmented DILI variant is loaded.
    task_type:
        Classification or regression, sourced from ``ENDPOINT_METADATA``.
    prep_id:
        The ``prep_dir.name`` identifying the M1 snapshot.
    train_val:
        Training + validation pool. Columns: ``standardized_smiles``, ``label``.
    test:
        Held-out test set. **Must not be used for fitting or selection.**
    calibration:
        Calibration split (subset of train_val, scaffold-disjoint from test).
    provenance:
        Per-dataset provenance dict from ``provenance.json``.
    """

    endpoint_key: str
    dataset_key: str
    task_type: TaskType
    prep_id: str
    train_val: pd.DataFrame
    test: pd.DataFrame
    calibration: pd.DataFrame
    provenance: dict


def load_manifest(prep_dir: Path | str) -> dict:
    """Return the parsed ``manifest.json`` for *prep_dir*."""
    prep_dir = Path(prep_dir)
    path = prep_dir / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(f"manifest.json not found in {prep_dir}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_available_endpoints(prep_dir: Path | str) -> list[str]:
    """Return sorted list of dataset directory names present in *prep_dir*."""
    prep_dir = Path(prep_dir)
    if not prep_dir.exists():
        raise FileNotFoundError(f"Processed data directory not found: {prep_dir}")
    return sorted(p.name for p in prep_dir.iterdir() if p.is_dir())


def _resolve_dataset_key(endpoint_key: str, *, use_augmented_dili: bool) -> str:
    if endpoint_key == _DILI_KEY and use_augmented_dili:
        return _AUGMENTED_DILI_KEY
    return endpoint_key


def _get_task_type(endpoint_key: str) -> TaskType:
    if endpoint_key in _VARIANT_TASK_TYPES:
        return _VARIANT_TASK_TYPES[endpoint_key]
    try:
        ep = Endpoint(endpoint_key)
    except ValueError:
        valid = sorted(e.value for e in Endpoint)
        raise ValueError(
            f"Unknown endpoint key {endpoint_key!r}. Valid values: {valid}"
        ) from None
    meta = ENDPOINT_METADATA.get(ep)
    if meta is None:
        raise KeyError(f"No metadata found for endpoint {ep!r}")
    return meta["task_type"]


def _read_split(path: Path) -> pd.DataFrame:
    """Read a processed split CSV; validate required columns."""
    df = pd.read_csv(path, dtype={"standardized_smiles": str})
    missing = {"standardized_smiles", "label"} - set(df.columns)
    if missing:
        raise ValueError(
            f"{path.name} is missing required columns: {sorted(missing)}"
        )
    return df.reset_index(drop=True)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_endpoint(
    prep_dir: Path | str,
    endpoint_key: str,
    *,
    use_augmented_dili: bool = False,
    validate_checksums: bool = False,
) -> EndpointData:
    """Load all splits for *endpoint_key* from a processed M1 snapshot.

    Parameters
    ----------
    prep_dir:
        Path to ``ml/data/processed/<prep_id>/``.
    endpoint_key:
        Canonical endpoint key from ``Endpoint`` enum (e.g. ``"solubility_logs"``).
    use_augmented_dili:
        When True and ``endpoint_key == "dili_liver_injury"``, load the
        DILIst-augmented dataset (``dili_liver_injury__augmented``).
    validate_checksums:
        When True, verify SHA-256 digests of each split file against the
        manifest. Slow (re-reads files); use for audit runs only.

    Returns
    -------
    EndpointData
        DataFrames for train_val, test, calibration + metadata.

    Raises
    ------
    ValueError
        If *endpoint_key* is not a known endpoint.
    FileNotFoundError
        If *prep_dir* or the dataset directory does not exist.
    """
    prep_dir = Path(prep_dir).resolve()
    prep_id = prep_dir.name

    dataset_key = _resolve_dataset_key(endpoint_key, use_augmented_dili=use_augmented_dili)
    task_type = _get_task_type(endpoint_key)

    ds_dir = prep_dir / dataset_key
    if not ds_dir.exists():
        available = list_available_endpoints(prep_dir)
        raise FileNotFoundError(
            f"Dataset directory not found: {ds_dir}\n"
            f"Available endpoints in {prep_dir.name}: {available}"
        )

    provenance: dict = {}
    prov_path = ds_dir / "provenance.json"
    if prov_path.exists():
        provenance = json.loads(prov_path.read_text(encoding="utf-8"))

    train_val = _read_split(ds_dir / "train_val.csv")
    test = _read_split(ds_dir / "test.csv")
    calibration = _read_split(ds_dir / "calibration.csv")

    if validate_checksums:
        manifest = load_manifest(prep_dir)
        files_meta = (
            manifest.get("datasets", {})
            .get(dataset_key, {})
            .get("provenance", {})
            .get("files", {})
        )
        for split_name in ("train_val", "test", "calibration"):
            expected = files_meta.get(split_name, {}).get("sha256")
            if not expected:
                continue
            actual = _sha256_file(ds_dir / f"{split_name}.csv")
            if actual != expected:
                raise ValueError(
                    f"Checksum mismatch for {dataset_key}/{split_name}.csv: "
                    f"expected {expected}, got {actual}"
                )

    return EndpointData(
        endpoint_key=endpoint_key,
        dataset_key=dataset_key,
        task_type=task_type,
        prep_id=prep_id,
        train_val=train_val,
        test=test,
        calibration=calibration,
        provenance=provenance,
    )
