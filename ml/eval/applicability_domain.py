"""
Module 5 CORE — k-NN applicability domain (blueprint §"CORE — k-NN
applicability domain distance").

Method: 5-NN distance (Tanimoto, ECFP4 fingerprint space) from a query
molecule to its 5 nearest neighbors in the endpoint's training set.

Threshold: flag "outside reliable domain" when the query's 5-NN mean distance
exceeds a percentile-based cutoff — the 90th percentile of the training set's
own internal 5-NN distances (leave-one-out), computed once per endpoint and
cached. Self-calibrating per endpoint since chemical density varies a lot
across the 14 datasets (DILI's ~1,300 compounds vs. hERG's ~13,000).

No calibration split needed — reuses Module 3's ECFP4 fingerprints and
Module 1's finalized train_val pool, both already on disk.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from featurize.fingerprints import MorganConfig, morgan_fingerprints_batch

AD_VERSION = "mars-ad-knn-tanimoto-v1"
DEFAULT_K = 5
DEFAULT_PERCENTILE = 90.0


def bulk_tanimoto_distance(query: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """Vectorized Tanimoto distance (1 - similarity) from each query row to
    each reference row.

    Parameters
    ----------
    query: (n_query, n_bits) uint8/bool bit matrix
    reference: (n_ref, n_bits) uint8/bool bit matrix

    Returns
    -------
    (n_query, n_ref) distance matrix. Uses the standard popcount-via-matmul
    trick (intersection = row dot product on 0/1 vectors) so it scales to
    thousands of reference compounds without a Python-level double loop.
    """
    if query.ndim != 2 or reference.ndim != 2:
        raise ValueError("query and reference must be 2-D bit matrices")
    if query.shape[1] != reference.shape[1]:
        raise ValueError(
            f"Bit-width mismatch: query has {query.shape[1]}, reference has {reference.shape[1]}"
        )
    q = query.astype(np.float64)
    r = reference.astype(np.float64)
    intersection = q @ r.T
    q_sum = q.sum(axis=1, keepdims=True)
    r_sum = r.sum(axis=1, keepdims=True).T
    union = q_sum + r_sum - intersection
    with np.errstate(divide="ignore", invalid="ignore"):
        similarity = np.where(union > 0, intersection / union, 0.0)
    return 1.0 - similarity


def _knn_mean_distance(distances: np.ndarray, k: int, *, exclude_nearest: bool) -> float:
    """Mean of the k smallest distances in a 1-D distance row.

    exclude_nearest: drop the single smallest entry first — used for
    leave-one-out threshold calibration where a reference compound's distance
    to itself (0.0) would otherwise dominate its own k-NN.
    """
    sorted_d = np.sort(distances)
    if exclude_nearest:
        sorted_d = sorted_d[1:]
    if len(sorted_d) < k:
        raise ValueError(f"Not enough neighbors to compute {k}-NN: only {len(sorted_d)} available")
    return float(np.mean(sorted_d[:k]))


@dataclass
class ADIndex:
    """Precomputed applicability-domain index for one endpoint."""

    endpoint_key: str
    reference_smiles: list[str]
    reference_fingerprints: np.ndarray  # (n_ref, n_bits)
    k: int
    percentile: float
    threshold: float
    morgan_cache_key: str
    ad_version: str = AD_VERSION

    def save(self, path: Path) -> None:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        np.save(path / "reference_fingerprints.npy", self.reference_fingerprints)
        meta = {
            "endpoint_key": self.endpoint_key,
            "reference_smiles": self.reference_smiles,
            "k": self.k,
            "percentile": self.percentile,
            "threshold": self.threshold,
            "morgan_cache_key": self.morgan_cache_key,
            "ad_version": self.ad_version,
        }
        (path / "metadata.json").write_text(
            json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    @classmethod
    def load(cls, path: Path) -> ADIndex:
        path = Path(path)
        meta = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
        fps = np.load(path / "reference_fingerprints.npy")
        return cls(
            endpoint_key=meta["endpoint_key"],
            reference_smiles=meta["reference_smiles"],
            reference_fingerprints=fps,
            k=meta["k"],
            percentile=meta["percentile"],
            threshold=meta["threshold"],
            morgan_cache_key=meta["morgan_cache_key"],
            ad_version=meta.get("ad_version", AD_VERSION),
        )


def build_ad_index(
    endpoint_key: str,
    train_val_smiles: list[str],
    *,
    k: int = DEFAULT_K,
    percentile: float = DEFAULT_PERCENTILE,
    morgan_config: MorganConfig | None = None,
) -> ADIndex:
    """Build a per-endpoint AD index from the training pool.

    The threshold is the given percentile of the training set's own
    leave-one-out k-NN Tanimoto distances — self-calibrating per endpoint,
    matching the blueprint's DILI-vs-hERG density concern.
    """
    cfg = morgan_config or MorganConfig()
    fps, dropped = morgan_fingerprints_batch(train_val_smiles, cfg)
    dropped_set = set(dropped)
    kept_smiles = [s for i, s in enumerate(train_val_smiles) if i not in dropped_set]

    if len(kept_smiles) <= k:
        raise ValueError(
            f"{endpoint_key}: need more than k={k} training compounds to build an AD "
            f"index; got {len(kept_smiles)} after dropping {len(dropped_set)} unfeaturizable SMILES"
        )

    self_distances = bulk_tanimoto_distance(fps, fps)
    loo_knn = np.array(
        [_knn_mean_distance(self_distances[i], k, exclude_nearest=True) for i in range(fps.shape[0])]
    )
    threshold = float(np.percentile(loo_knn, percentile))

    return ADIndex(
        endpoint_key=endpoint_key,
        reference_smiles=kept_smiles,
        reference_fingerprints=fps,
        k=k,
        percentile=percentile,
        threshold=threshold,
        morgan_cache_key=cfg.cache_key(),
    )


@dataclass(frozen=True)
class ADResult:
    smiles: str
    knn_mean_distance: float
    in_domain: bool


def query_ad(
    index: ADIndex,
    query_smiles: list[str],
    *,
    morgan_config: MorganConfig | None = None,
) -> list[ADResult]:
    """Return an in/out-of-domain flag for each query molecule.

    Query molecules that fail featurization are silently omitted from the
    output (same drop-invalid-and-report convention as the rest of Module 3) —
    callers that need the full-length alignment should check len(result) vs.
    len(query_smiles) themselves, mirroring XGBoostModel.predict's dropped-SMILES
    handling.
    """
    cfg = morgan_config or MorganConfig()
    if index.reference_fingerprints.shape[1:] and cfg.n_bits != index.reference_fingerprints.shape[1]:
        raise ValueError(
            f"morgan_config.n_bits ({cfg.n_bits}) does not match the index's fingerprint "
            f"width ({index.reference_fingerprints.shape[1]}); rebuild the index or pass "
            f"the matching config."
        )
    fps, dropped = morgan_fingerprints_batch(query_smiles, cfg)
    dropped_set = set(dropped)
    kept_idx = [i for i in range(len(query_smiles)) if i not in dropped_set]

    if fps.shape[0] == 0:
        return []

    dist_matrix = bulk_tanimoto_distance(fps, index.reference_fingerprints)
    results: list[ADResult] = []
    for row_i, orig_i in enumerate(kept_idx):
        mean_dist = _knn_mean_distance(dist_matrix[row_i], index.k, exclude_nearest=False)
        results.append(
            ADResult(
                smiles=query_smiles[orig_i],
                knn_mean_distance=mean_dist,
                in_domain=mean_dist <= index.threshold,
            )
        )
    return results
