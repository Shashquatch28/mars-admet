"""
On-disk feature + conformer cache (blueprint Module 3 §"cached per molecule",
Module 12 "ECFP fingerprints … persisted").

Contract this enforces:

  * **Cache key = stable molecular identity + featurization config/version.**
    Identity is the *standardized* SMILES (the Module 3 Stage 1 canonical form —
    the caller is responsible for passing standardized input, exactly as the
    non-cached featurizers require). Config/version is the stage's
    ``cache_key()`` string (which already folds in every knob + a version tag).

  * **A cache built with one config is never silently reused with an
    incompatible one.** The key includes the config's ``cache_key()``, so a
    changed radius / bit count / descriptor set / graph schema / conformer
    settings produces different key files. ``_config.json`` per stage records
    every ``cache_key()`` the cache has ever been written under, with first-seen
    time and entry count, so the divergence is visible, not hidden.

  * **Deterministic keys.** ``sha256(stage \x1f cache_key \x1f smiles)``.

  * **Provenance preserved.** ``_config.json`` also records the library
    versions and a creation timestamp.

Layout::

    <root>/
      morgan/       _config.json   <kk[:2]>/<keyhash>.npy
      descriptors/  _config.json   <kk[:2]>/<keyhash>.npz   (values + finite_mask + non_finite)
      graph/        _config.json   <kk[:2]>/<keyhash>.npz   (atom_features, edge_index, edge_features)
      conformer/    _config.json   <kk[:2]>/<keyhash>.json

Each ``<stage>_cached(...)`` helper: look up every input in the cache, compute
the misses in ONE batched call to the underlying featurizer, persist them, and
return the result aligned to the input list (same drop-invalid-and-report
convention as the non-cached batch APIs).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from featurize.conformers import (
    CONFORMER_VERSION,
    ConformerAtom,
    ConformerBond,
    ConformerConfig,
    ConformerResult,
    generate_conformers_batch,
)
from featurize.descriptors import (
    DESCRIPTOR_COUNT,
    DESCRIPTOR_VERSION,
    DescriptorConfig,
    descriptor_matrix,
)
from featurize.fingerprints import (
    MORGAN_FP_VERSION,
    MorganConfig,
    morgan_fingerprints_batch,
)
from featurize.graph import (
    GRAPH_FEATURE_VERSION,
    GraphFeaturizerConfig,
    MoleculeGraph,
    molecule_graphs_batch,
)

CACHE_SCHEMA_VERSION = 1
_STAGES = ("morgan", "descriptors", "graph", "conformer")
_SEP = "\x1f"


def _lib_versions() -> dict[str, str]:
    import numpy
    import rdkit

    return {
        "numpy": numpy.__version__,
        "rdkit": rdkit.__version__,
        "morgan": MORGAN_FP_VERSION,
        "descriptors": DESCRIPTOR_VERSION,
        "graph": GRAPH_FEATURE_VERSION,
        "conformer": CONFORMER_VERSION,
        "cache_schema": str(CACHE_SCHEMA_VERSION),
    }


def entry_key(stage: str, cache_key: str, smiles: str) -> str:
    """Deterministic content-addressed key for one (stage, config, molecule)."""
    return hashlib.sha256(
        f"{stage}{_SEP}{cache_key}{_SEP}{smiles}".encode()
    ).hexdigest()


@dataclass
class CacheStats:
    stage: str
    hits: int
    misses: int
    computed: int
    invalid: int  # inputs the featurizer could not parse


class FeatureCache:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        for stage in _STAGES:
            (self.root / stage).mkdir(parents=True, exist_ok=True)

    # --- low-level ------------------------------------------------------- #
    def _path(self, stage: str, key: str, ext: str) -> Path:
        return self.root / stage / key[:2] / f"{key}.{ext}"

    def _record_config(self, stage: str, cache_key: str, added: int) -> None:
        meta_path = self.root / stage / "_config.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        else:
            meta = {
                "stage": stage,
                "created_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "library_versions": _lib_versions(),
                "configs_seen": {},
            }
        seen = meta["configs_seen"].setdefault(
            cache_key,
            {"first_seen_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
             "n_entries": 0},
        )
        seen["n_entries"] += added
        meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def configs_seen(self, stage: str) -> dict:
        meta_path = self.root / stage / "_config.json"
        if not meta_path.exists():
            return {}
        return json.loads(meta_path.read_text(encoding="utf-8"))["configs_seen"]

    # --- morgan ------------------------------------------------------------ #
    def morgan_cached(
        self,
        standardized_smiles: Sequence[str],
        config: MorganConfig | None = None,
    ) -> tuple[np.ndarray, list[int], CacheStats]:
        cfg = config or MorganConfig()
        ck = cfg.cache_key()
        n = len(standardized_smiles)
        out: list[np.ndarray | None] = [None] * n
        missing_idx: list[int] = []
        hits = 0
        for i, smi in enumerate(standardized_smiles):
            p = self._path("morgan", entry_key("morgan", ck, smi), "npy")
            if p.exists():
                out[i] = np.load(p)
                hits += 1
            else:
                missing_idx.append(i)

        computed = 0
        invalid_positions: set[int] = set()
        if missing_idx:
            miss_smiles = [standardized_smiles[i] for i in missing_idx]
            matrix, dropped = morgan_fingerprints_batch(miss_smiles, cfg)
            dropped_set = set(dropped)
            row = 0
            for local_i, orig_i in enumerate(missing_idx):
                if local_i in dropped_set:
                    invalid_positions.add(orig_i)
                    continue
                vec = matrix[row].astype(np.uint8, copy=False)
                row += 1
                out[orig_i] = vec
                key = entry_key("morgan", ck, standardized_smiles[orig_i])
                p = self._path("morgan", key, "npy")
                p.parent.mkdir(parents=True, exist_ok=True)
                np.save(p, vec)
                computed += 1
            self._record_config("morgan", ck, computed)

        kept_rows = [v for v in out if v is not None]
        dropped_idx = sorted(i for i, v in enumerate(out) if v is None)
        result = (
            np.vstack(kept_rows).astype(np.uint8, copy=False)
            if kept_rows
            else np.zeros((0, cfg.n_bits), dtype=np.uint8)
        )
        return result, dropped_idx, CacheStats("morgan", hits, len(missing_idx), computed, len(invalid_positions))

    # --- descriptors ---------------------------------------------------- #
    def descriptors_cached(
        self,
        standardized_smiles: Sequence[str],
        config: DescriptorConfig | None = None,
    ) -> tuple[np.ndarray, np.ndarray, list[int], list[dict[str, float]], CacheStats]:
        cfg = config or DescriptorConfig()
        ck = cfg.cache_key()
        n = len(standardized_smiles)
        vals: list[np.ndarray | None] = [None] * n
        nfs: list[dict[str, float] | None] = [None] * n
        missing_idx: list[int] = []
        hits = 0
        for i, smi in enumerate(standardized_smiles):
            p = self._path("descriptors", entry_key("descriptors", ck, smi), "npz")
            if p.exists():
                z = np.load(p, allow_pickle=True)
                vals[i] = z["values"]
                nfs[i] = json.loads(str(z["non_finite"]))
                hits += 1
            else:
                missing_idx.append(i)

        computed = 0
        if missing_idx:
            miss_smiles = [standardized_smiles[i] for i in missing_idx]
            matrix, _mask, dropped, nf_list = descriptor_matrix(miss_smiles, cfg)
            dropped_set = set(dropped)
            row = 0
            for local_i, orig_i in enumerate(missing_idx):
                if local_i in dropped_set:
                    continue
                v = matrix[row]
                nf = nf_list[row]
                row += 1
                vals[orig_i] = v
                nfs[orig_i] = nf
                key = entry_key("descriptors", ck, standardized_smiles[orig_i])
                p = self._path("descriptors", key, "npz")
                p.parent.mkdir(parents=True, exist_ok=True)
                np.savez(p, values=v, non_finite=json.dumps(nf, sort_keys=True))
                computed += 1
            self._record_config("descriptors", ck, computed)

        kept = [v for v in vals if v is not None]
        kept_nf = [nfs[i] for i, v in enumerate(vals) if v is not None]
        dropped_idx = sorted(i for i, v in enumerate(vals) if v is None)
        if kept:
            m = np.vstack(kept)
        else:
            m = np.zeros((0, DESCRIPTOR_COUNT), dtype=np.float64)
        mask = np.isfinite(m)
        invalid = len(dropped_idx)
        return m, mask, dropped_idx, kept_nf, CacheStats(
            "descriptors", hits, len(missing_idx), computed, invalid
        )

    # --- graph -------------------------------------------------------- #
    def graphs_cached(
        self,
        standardized_smiles: Sequence[str],
        config: GraphFeaturizerConfig | None = None,
    ) -> tuple[list[MoleculeGraph], list[int], CacheStats]:
        cfg = config or GraphFeaturizerConfig()
        ck = cfg.cache_key()
        n = len(standardized_smiles)
        out: list[MoleculeGraph | None] = [None] * n
        missing_idx: list[int] = []
        hits = 0
        for i, smi in enumerate(standardized_smiles):
            p = self._path("graph", entry_key("graph", ck, smi), "npz")
            if p.exists():
                z = np.load(p)
                out[i] = MoleculeGraph(
                    n_atoms=int(z["n_atoms"]),
                    n_bonds=int(z["n_bonds"]),
                    atom_features=z["atom_features"],
                    edge_index=z["edge_index"],
                    edge_features=z["edge_features"],
                    smiles=smi,
                )
                hits += 1
            else:
                missing_idx.append(i)

        computed = 0
        if missing_idx:
            miss_smiles = [standardized_smiles[i] for i in missing_idx]
            graphs, dropped = molecule_graphs_batch(miss_smiles, cfg)
            dropped_set = set(dropped)
            gi = 0
            for local_i, orig_i in enumerate(missing_idx):
                if local_i in dropped_set:
                    continue
                g = graphs[gi]
                gi += 1
                out[orig_i] = g
                key = entry_key("graph", ck, standardized_smiles[orig_i])
                p = self._path("graph", key, "npz")
                p.parent.mkdir(parents=True, exist_ok=True)
                np.savez(
                    p,
                    n_atoms=g.n_atoms,
                    n_bonds=g.n_bonds,
                    atom_features=g.atom_features,
                    edge_index=g.edge_index,
                    edge_features=g.edge_features,
                )
                computed += 1
            self._record_config("graph", ck, computed)

        kept = [g for g in out if g is not None]
        dropped_idx = sorted(i for i, g in enumerate(out) if g is None)
        return kept, dropped_idx, CacheStats("graph", hits, len(missing_idx), computed, len(dropped_idx))

    # --- conformer -------------------------------------------------- #
    def conformers_cached(
        self,
        standardized_smiles: Sequence[str],
        config: ConformerConfig | None = None,
    ) -> tuple[list[ConformerResult], CacheStats]:
        cfg = config or ConformerConfig()
        ck = cfg.cache_key()
        n = len(standardized_smiles)
        out: list[ConformerResult | None] = [None] * n
        missing_idx: list[int] = []
        hits = 0
        for i, smi in enumerate(standardized_smiles):
            p = self._path("conformer", entry_key("conformer", ck, smi), "json")
            if p.exists():
                out[i] = _conformer_from_dict(json.loads(p.read_text(encoding="utf-8")))
                hits += 1
            else:
                missing_idx.append(i)

        computed = 0
        if missing_idx:
            miss_smiles = [standardized_smiles[i] for i in missing_idx]
            results = generate_conformers_batch(miss_smiles, cfg)
            for local_i, orig_i in enumerate(missing_idx):
                r = results[local_i]
                out[orig_i] = r
                key = entry_key("conformer", ck, standardized_smiles[orig_i])
                p = self._path("conformer", key, "json")
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps(_conformer_to_dict(r), sort_keys=True), encoding="utf-8")
                computed += 1
            self._record_config("conformer", ck, computed)

        # conformers are never "dropped" — a failure is a stored ConformerResult(ok=False)
        final = [r for r in out if r is not None]
        n_fail = sum(1 for r in final if not r.ok)
        return final, CacheStats("conformer", hits, len(missing_idx), computed, n_fail)


# --- conformer (de)serialisation ------------------------------------------ #
def _conformer_to_dict(r: ConformerResult) -> dict:
    return {
        "smiles": r.smiles,
        "ok": r.ok,
        "reason": r.reason,
        "force_field": r.force_field,
        "energy_kcal_mol": r.energy_kcal_mol,
        "n_conformers_tried": r.n_conformers_tried,
        "version": r.version,
        "atoms": [[a.element, a.x, a.y, a.z, a.partial_charge] for a in r.atoms],
        "bonds": [[b.atom_index_1, b.atom_index_2, b.order] for b in r.bonds],
        "sdf_block": r.sdf_block,
    }


def _conformer_from_dict(d: dict) -> ConformerResult:
    return ConformerResult(
        smiles=d["smiles"],
        ok=d["ok"],
        reason=d.get("reason"),
        force_field=d.get("force_field"),
        energy_kcal_mol=d.get("energy_kcal_mol"),
        n_conformers_tried=d.get("n_conformers_tried", 0),
        version=d.get("version", CONFORMER_VERSION),
        atoms=[ConformerAtom(el, x, y, z, q) for el, x, y, z, q in d.get("atoms", [])],
        bonds=[ConformerBond(a1, a2, o) for a1, a2, o in d.get("bonds", [])],
        sdf_block=d.get("sdf_block"),
    )
