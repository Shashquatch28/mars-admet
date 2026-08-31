"""
Module 3 — the batched featurization pipeline façade.

Blueprint "critical non-negotiable requirement": the entire pipeline (stages 1-4,
and 5 where relevant) must run efficiently across a **batch of molecules**, not
one at a time. This module is the single batch entry point that every caller
(training feature-matrix build, k-NN AD index build, batch prediction) uses.

Stages:
  1. standardize     (featurize.standardize)      — always
  2. graph           (featurize.graph)            — opt-in
  3. morgan / ECFP   (featurize.fingerprints)     — opt-in
  4. rdkit 2d descr. (featurize.descriptors)      — opt-in
  5. 3d conformers   (featurize.conformers)       — opt-in, expensive, off by
                                                    default (blueprint: lazy)

Design:
  * **Standardize once.** Every downstream stage runs on the *standardized*
    SMILES, computed a single time for the whole batch. A raw SMILES that fails
    standardization is dropped once, here, and never reaches a stage.
  * **Aligned outputs.** For a batch of N inputs, the result carries the list of
    surviving (standardized) SMILES and, for each requested stage, an output
    aligned to that list. Callers align their labels/metadata via
    ``kept_input_indices``.
  * **One provenance/version bundle** for the whole call — the set of stage
    versions + config cache keys that produced these features. This is what a
    feature cache keys on and what a training run records.
  * No hidden per-molecule Python loop at a higher layer — each stage's own
    batch function is called once.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from featurize.conformers import (
    CONFORMER_VERSION,
    ConformerConfig,
    ConformerResult,
    generate_conformers_batch,
)
from featurize.descriptors import (
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
from featurize.standardize import (
    StandardizerConfig,
    rejection_summary,
    standardize_batch,
)

PIPELINE_VERSION = "mars-featurize-pipeline-v1"


@dataclass(frozen=True)
class PipelineConfig:
    standardizer: StandardizerConfig = field(default_factory=StandardizerConfig)
    graph: GraphFeaturizerConfig = field(default_factory=GraphFeaturizerConfig)
    morgan: MorganConfig = field(default_factory=MorganConfig)
    descriptors: DescriptorConfig = field(default_factory=DescriptorConfig)
    conformers: ConformerConfig = field(default_factory=ConformerConfig)

    want_graph: bool = True
    want_morgan: bool = True
    want_descriptors: bool = True
    want_conformers: bool = False  # expensive; lazy per blueprint

    def provenance(self) -> dict[str, Any]:
        prov: dict[str, Any] = {
            "pipeline_version": PIPELINE_VERSION,
            "standardizer_version": self.standardizer.version,
        }
        if self.want_graph:
            prov["graph_version"] = GRAPH_FEATURE_VERSION
            prov["graph_cache_key"] = self.graph.cache_key()
        if self.want_morgan:
            prov["morgan_version"] = MORGAN_FP_VERSION
            prov["morgan_cache_key"] = self.morgan.cache_key()
        if self.want_descriptors:
            prov["descriptor_version"] = DESCRIPTOR_VERSION
            prov["descriptor_cache_key"] = self.descriptors.cache_key()
        if self.want_conformers:
            prov["conformer_version"] = CONFORMER_VERSION
            prov["conformer_cache_key"] = self.conformers.cache_key()
        return prov


@dataclass
class FeaturizedBatch:
    """Everything aligned to ``standardized_smiles`` (length = n surviving)."""

    n_input: int
    standardized_smiles: list[str]
    kept_input_indices: list[int]
    standardization_rejects: dict[str, int]

    graphs: list[MoleculeGraph] | None = None
    graph_dropped: list[int] = field(default_factory=list)

    morgan: np.ndarray | None = None  # (n_surviving_fp, n_bits)
    morgan_dropped: list[int] = field(default_factory=list)

    descriptors: np.ndarray | None = None  # (n_surviving_desc, DESCRIPTOR_COUNT)
    descriptor_finite_mask: np.ndarray | None = None
    descriptor_dropped: list[int] = field(default_factory=list)
    descriptor_non_finite: list[dict[str, float]] = field(default_factory=list)

    conformers: list[ConformerResult] | None = None

    provenance: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        s: dict[str, Any] = {
            "n_input": self.n_input,
            "n_standardized": len(self.standardized_smiles),
            "standardization_rejects": self.standardization_rejects,
        }
        if self.graphs is not None:
            s["n_graphs"] = len(self.graphs)
            s["graph_dropped"] = len(self.graph_dropped)
        if self.morgan is not None:
            s["morgan_shape"] = list(self.morgan.shape)
            s["morgan_dropped"] = len(self.morgan_dropped)
        if self.descriptors is not None:
            s["descriptor_shape"] = list(self.descriptors.shape)
            s["descriptor_dropped"] = len(self.descriptor_dropped)
            s["descriptor_non_finite_cells"] = (
                int((~self.descriptor_finite_mask).sum())
                if self.descriptor_finite_mask is not None
                else 0
            )
        if self.conformers is not None:
            s["n_conformers_ok"] = sum(1 for c in self.conformers if c.ok)
            s["n_conformers_failed"] = sum(1 for c in self.conformers if not c.ok)
        return s


def featurize_batch(
    raw_smiles: Sequence[str],
    config: PipelineConfig | None = None,
) -> FeaturizedBatch:
    """Standardize once, then run each requested stage's batch function once."""
    cfg = config or PipelineConfig()

    std_rows = standardize_batch(raw_smiles, cfg.standardizer)
    kept_idx: list[int] = []
    std_smiles: list[str] = []
    for i, row in enumerate(std_rows):
        if row.ok:
            kept_idx.append(i)
            std_smiles.append(row.canonical_smiles)

    out = FeaturizedBatch(
        n_input=len(raw_smiles),
        standardized_smiles=std_smiles,
        kept_input_indices=kept_idx,
        standardization_rejects={
            k: v for k, v in rejection_summary(std_rows).items() if k != "ok"
        },
        provenance=cfg.provenance(),
    )

    if not std_smiles:
        return out

    if cfg.want_graph:
        out.graphs, out.graph_dropped = molecule_graphs_batch(std_smiles, cfg.graph)

    if cfg.want_morgan:
        out.morgan, out.morgan_dropped = morgan_fingerprints_batch(std_smiles, cfg.morgan)

    if cfg.want_descriptors:
        (
            out.descriptors,
            out.descriptor_finite_mask,
            out.descriptor_dropped,
            out.descriptor_non_finite,
        ) = descriptor_matrix(std_smiles, cfg.descriptors)

    if cfg.want_conformers:
        out.conformers = generate_conformers_batch(std_smiles, cfg.conformers)

    return out
