"""
MARS dataset registry — the single, dependency-free source of truth for which
TDC datasets back which endpoint, plus their licensing and benchmark-group
status (blueprint Module 1 §1/§4/§7, Module 2 endpoint table).

Intentionally imports nothing beyond the standard library so it can be used by:
  * the isolated acquisition environment (WSL, PyTDC only — no mars_contracts),
  * the ml/.venv working environment (Runs 2-4),
  * host-side verification tests (which additionally assert this stays in sync
    with contracts.Endpoint — see ml/tests/test_dataset_registry.py).

Endpoint key strings below are the locked ``mars_contracts.Endpoint`` values
(M0 contract, "source of truth for field names"). The drift guard test fails
loudly if they ever diverge.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# TDC's own per-dataset license pages were verified in blueprint Module 1 §7:
# all 14 endpoint datasets redistribute under CC BY 4.0 regardless of the
# original source's stated terms.
_TDC_CC_BY_4 = "CC BY 4.0"


@dataclass(frozen=True)
class DatasetSpec:
    """One acquirable dataset snapshot."""

    dataset_key: str
    """Unique key for this dataset in the lockfile. Equals ``endpoint_key`` for
    the primary dataset of an endpoint; suffixed for secondary/alternate pulls."""

    endpoint_key: str
    """The ``mars_contracts.Endpoint`` value this dataset serves."""

    tdc_name: str
    """Exact dataset name passed to the PyTDC loader."""

    tdc_loader: str
    """PyTDC single-prediction loader class: ``"ADME"`` or ``"Tox"``."""

    task: str
    """``"regression"`` or ``"classification"`` (matches contracts metadata)."""

    in_admet_benchmark_group: bool
    """True if TDC's ADMET Benchmark Group publishes an official fixed
    80/20 scaffold split for this dataset (blueprint Module 1 §4)."""

    license: str
    license_ref: str

    variant: str = "primary"
    """``"primary"`` = the dataset the endpoint trains/evaluates on;
    ``"benchmark_alt"`` = an extra pull kept for comparison / a deferred decision."""

    approx_n: int | None = None
    """Blueprint Module 2 headline N, for a post-download sanity check only.
    Small deviations are expected (TDC revises datasets)."""

    notes: str = ""

    aliases: tuple[str, ...] = field(default_factory=tuple)
    """Other names TDC may resolve this dataset under (recorded, not used)."""


# --- Absorption / Distribution / Metabolism / Excretion (11 ADME datasets) ----
_ADME: list[DatasetSpec] = [
    DatasetSpec(
        dataset_key="solubility_logs",
        endpoint_key="solubility_logs",
        tdc_name="Solubility_AqSolDB",
        tdc_loader="ADME",
        task="regression",
        in_admet_benchmark_group=True,
        license=_TDC_CC_BY_4,
        license_ref="https://tdcommons.ai/single_pred_tasks/adme/#solubility-aqsoldb",
        approx_n=9982,
    ),
    DatasetSpec(
        dataset_key="lipophilicity_logp",
        endpoint_key="lipophilicity_logp",
        tdc_name="Lipophilicity_AstraZeneca",
        tdc_loader="ADME",
        task="regression",
        in_admet_benchmark_group=True,
        license=_TDC_CC_BY_4,
        license_ref="https://tdcommons.ai/single_pred_tasks/adme/#lipophilicity-astrazeneca",
        approx_n=4200,
        notes="AstraZeneca 2016 disclosure; TDC redistribution is CC BY 4.0 (Module 1 §7).",
    ),
    DatasetSpec(
        dataset_key="caco2_permeability",
        endpoint_key="caco2_permeability",
        tdc_name="Caco2_Wang",
        tdc_loader="ADME",
        task="regression",
        in_admet_benchmark_group=True,
        license=_TDC_CC_BY_4,
        license_ref="https://tdcommons.ai/single_pred_tasks/adme/#caco-2-cell-effective-permeability-wang-et-al",
        approx_n=906,
    ),
    DatasetSpec(
        dataset_key="hia_absorption",
        endpoint_key="hia_absorption",
        tdc_name="HIA_Hou",
        tdc_loader="ADME",
        task="classification",
        in_admet_benchmark_group=True,
        license=_TDC_CC_BY_4,
        license_ref="https://tdcommons.ai/single_pred_tasks/adme/#hia-human-intestinal-absorption-hou-et-al",
        approx_n=578,
    ),
    DatasetSpec(
        dataset_key="pgp_inhibition",
        endpoint_key="pgp_inhibition",
        tdc_name="Pgp_Broccatelli",
        tdc_loader="ADME",
        task="classification",
        in_admet_benchmark_group=True,
        license=_TDC_CC_BY_4,
        license_ref="https://tdcommons.ai/single_pred_tasks/adme/#pgp-p-glycoprotein-inhibition-broccatelli-et-al",
        approx_n=1212,
    ),
    DatasetSpec(
        dataset_key="bbb_permeability",
        endpoint_key="bbb_permeability",
        tdc_name="BBB_Martins",
        tdc_loader="ADME",
        task="classification",
        in_admet_benchmark_group=True,
        license=_TDC_CC_BY_4,
        license_ref="https://tdcommons.ai/single_pred_tasks/adme/#bbb-blood-brain-barrier-martins-et-al",
        approx_n=1975,
        notes="PharmaBench augmentation dropped (Module 1 §7, CC BY-NC-ND). TDC-only.",
    ),
    # PPB — Option C locked 2026-08-30: primary MARS endpoint is *human only*
    # (blueprint Module 1 §4 PPB exception + Module 2 table). The all-species
    # pooled dataset is retained as a comparability ablation (variant below),
    # not on the M2 critical path.
    #
    # Species filter reproducibility (blueprint Option C §1 requirement):
    #   Source dataset:  PPBR_AZ (Astrazeneca, TDC redistribution CC BY 4.0)
    #   Loader:          tdc.single_pred.ADME(name="PPBR_AZ") — filters the raw
    #                    5-species tab (2,828 rows / 1,797 unique compounds) to
    #                    Species == "Homo sapiens" (1,614 rows / 1,614 compounds).
    #   Inclusion:       every human measurement returned by the loader.
    #   Exclusion:       non-human species measurements (Rattus, Canis, Mus,
    #                    Cavia porcellus). Dropped: 1,214 rows.
    #   Dedup + conflict: run through the tiered policy per blueprint §3
    #                    (Module 1) using the same code path as every other
    #                    endpoint (drop_conflicting since human PPBR_AZ has
    #                    0 % conflict rate per Run-2 EDA).
    #   Snapshot hash:   canonical (SMILES,Y) digest — recorded in the lockfile
    #                    per acquisition; split hashes recorded in the processed
    #                    dataset's split_report.json and provenance.json.
    DatasetSpec(
        dataset_key="ppb_binding",
        endpoint_key="ppb_binding",
        tdc_name="PPBR_AZ",
        tdc_loader="ADME",
        task="regression",
        # False under Option C: the TDC benchmark split is defined against the
        # ALL-SPECIES pool, not against the human subset (2,790 measurements
        # vs 1,614 human compounds — the benchmark split does not partition the
        # human subset), so it cannot be adopted for the primary endpoint. The
        # ablation variant below is the one that adopts the official split.
        in_admet_benchmark_group=False,
        license=_TDC_CC_BY_4,
        license_ref="https://tdcommons.ai/single_pred_tasks/adme/#ppbr-plasma-protein-binding-rate-astrazeneca",
        approx_n=1614,
        notes=(
            "PRIMARY MARS PPB endpoint under Option C (human only via "
            "tdc.single_pred.ADME's Homo-sapiens filter, N=1614). Split is an "
            "independent deterministic Murcko scaffold split (same policy shape "
            "as hERG_Karim). Not directly TDC-leaderboard-comparable; the "
            "ppb_binding__all_species variant is the leaderboard-comparable "
            "ablation."
        ),
    ),
    DatasetSpec(
        dataset_key="ppb_binding__all_species",
        endpoint_key="ppb_binding",
        tdc_name="PPBR_AZ",
        tdc_loader="ADME",
        task="regression",
        in_admet_benchmark_group=True,
        license=_TDC_CC_BY_4,
        license_ref="https://tdcommons.ai/benchmark/admet_group/17ppbr_az/",
        variant="benchmark_alt",
        approx_n=1797,
        notes=(
            "SECONDARY (all-species pooled) PPB dataset, retained as a "
            "comparability ablation under Option C. Uses TDC benchmark_group "
            "PPBR_AZ (2,790 measurements over 1,797 unique compounds, all 5 "
            "species pooled with species column dropped). "
            "NOT on the M2 critical path — the ablation is scheduled after the "
            "primary 14-endpoint system trains cleanly, and only executed if "
            "its compute cost is acceptable (specifically: whether swapping the "
            "PPB target requires re-training the multi-task cluster for each "
            "seed vs only PPB-specific runs). Kept provenance-tracked so the "
            "ablation can be run without re-derivation."
        ),
    ),
    DatasetSpec(
        dataset_key="cyp3a4_inhibition",
        endpoint_key="cyp3a4_inhibition",
        tdc_name="CYP3A4_Veith",
        tdc_loader="ADME",
        task="classification",
        in_admet_benchmark_group=True,
        license=_TDC_CC_BY_4,
        license_ref="https://tdcommons.ai/single_pred_tasks/adme/#cyp-p450-3a4-inhibition-veith-et-al",
        approx_n=12328,
    ),
    DatasetSpec(
        dataset_key="cyp2d6_inhibition",
        endpoint_key="cyp2d6_inhibition",
        tdc_name="CYP2D6_Veith",
        tdc_loader="ADME",
        task="classification",
        in_admet_benchmark_group=True,
        license=_TDC_CC_BY_4,
        license_ref="https://tdcommons.ai/single_pred_tasks/adme/#cyp-p450-2d6-inhibition-veith-et-al",
        approx_n=13130,
    ),
    DatasetSpec(
        dataset_key="cyp2c9_inhibition",
        endpoint_key="cyp2c9_inhibition",
        tdc_name="CYP2C9_Veith",
        tdc_loader="ADME",
        task="classification",
        in_admet_benchmark_group=True,
        license=_TDC_CC_BY_4,
        license_ref="https://tdcommons.ai/single_pred_tasks/adme/#cyp-p450-2c9-inhibition-veith-et-al",
        approx_n=12092,
        notes="Stereochemistry-sensitive endpoint (blueprint Module 3): EDA must log stereo-defined ratio.",
    ),
    DatasetSpec(
        dataset_key="clearance_microsomal",
        endpoint_key="clearance_microsomal",
        tdc_name="Clearance_Microsome_AZ",
        tdc_loader="ADME",
        task="regression",
        in_admet_benchmark_group=True,
        license=_TDC_CC_BY_4,
        license_ref="https://tdcommons.ai/single_pred_tasks/adme/#clearance-astrazeneca",
        approx_n=1102,
        notes="PharmaBench HLMC augmentation dropped (Module 1 §7). TDC-only.",
    ),
]

# --- Toxicity (4 Tox datasets, incl. two hERG variants — see FUTURE_SCOPE.md) --
_TOX: list[DatasetSpec] = [
    DatasetSpec(
        dataset_key="herg_cardiotoxicity",
        endpoint_key="herg_cardiotoxicity",
        tdc_name="hERG_Karim",
        tdc_loader="Tox",
        task="classification",
        in_admet_benchmark_group=False,
        license=_TDC_CC_BY_4,
        license_ref="https://tdcommons.ai/single_pred_tasks/tox/#herg-blockers-karim-et-al",
        variant="primary",
        approx_n=13445,
        notes=(
            "Blueprint Module 2 primary hERG dataset. NOT in TDC's ADMET Benchmark "
            "Group -> no official fixed split; Run 2 generates a deterministic Murcko "
            "scaffold split replicating TDC methodology. Not leaderboard-comparable "
            "against the 655-compound benchmark 'hERG'. See documentation/FUTURE_SCOPE.md."
        ),
    ),
    DatasetSpec(
        dataset_key="herg_cardiotoxicity__benchmark",
        endpoint_key="herg_cardiotoxicity",
        tdc_name="hERG",
        tdc_loader="Tox",
        task="classification",
        in_admet_benchmark_group=True,
        license=_TDC_CC_BY_4,
        license_ref="https://tdcommons.ai/benchmark/admet_group/21herg/",
        variant="benchmark_alt",
        approx_n=655,
        notes=(
            "TDC ADMET Benchmark Group hERG (Wang et al.). Acquired for comparison; "
            "endpoint->dataset choice deferred to Run 2 EDA (decision 2026-08-30)."
        ),
    ),
    DatasetSpec(
        dataset_key="ames_mutagenicity",
        endpoint_key="ames_mutagenicity",
        tdc_name="AMES",
        tdc_loader="Tox",
        task="classification",
        in_admet_benchmark_group=True,
        license=_TDC_CC_BY_4,
        license_ref="https://tdcommons.ai/single_pred_tasks/tox/#ames-mutagenicity",
        approx_n=7255,
    ),
    DatasetSpec(
        dataset_key="dili_liver_injury",
        endpoint_key="dili_liver_injury",
        tdc_name="DILI",
        tdc_loader="Tox",
        task="classification",
        in_admet_benchmark_group=True,
        license=_TDC_CC_BY_4,
        license_ref="https://tdcommons.ai/single_pred_tasks/tox/#dili-drug-induced-liver-injury",
        approx_n=475,
        notes=(
            "DILIst augmentation (Module 1 §6, FDA/NCTR, public domain 17 U.S.C. §105) "
            "is NOT a TDC dataset — acquisition deferred to Run 2 with its own provenance."
        ),
    ),
]

DATASET_SPECS: dict[str, DatasetSpec] = {s.dataset_key: s for s in (*_ADME, *_TOX)}

# Endpoint keys that MUST have a primary dataset here (all ML endpoints; the
# rule-based SA score has none). Kept as a plain set so the acquisition env does
# not need mars_contracts; the host test cross-checks it against the enum.
ML_ENDPOINT_KEYS: frozenset[str] = frozenset(
    s.endpoint_key for s in DATASET_SPECS.values() if s.variant == "primary"
)

# The rule-based endpoint deliberately has no dataset.
NON_DATASET_ENDPOINT_KEYS: frozenset[str] = frozenset({"synthetic_accessibility"})


def primary_specs() -> list[DatasetSpec]:
    """The 14 datasets an endpoint actually depends on (excludes benchmark_alt)."""
    return [s for s in DATASET_SPECS.values() if s.variant == "primary"]


def benchmark_group_specs() -> list[DatasetSpec]:
    """Datasets with an official TDC ADMET Benchmark Group fixed split."""
    return [s for s in DATASET_SPECS.values() if s.in_admet_benchmark_group]
