# glossary.md

## The 14 endpoints (contract key → dataset, task, cluster)

| Endpoint key | Name | Task | Cluster | TDC dataset | ~N |
|---|---|---|---|---|---|
| `solubility_logs` | Aqueous solubility (logS) | reg | absorption_distribution | Solubility_AqSolDB | 9,982 |
| `lipophilicity_logp` | Lipophilicity (logP) | reg | absorption_distribution | Lipophilicity_AstraZeneca | 4,200 |
| `caco2_permeability` | Caco-2 permeability | reg | absorption_distribution | Caco2_Wang | 910 |
| `hia_absorption` | Human intestinal absorption | clf | absorption_distribution | HIA_Hou | 578 |
| `pgp_inhibition` | P-gp inhibition | clf | absorption_distribution | Pgp_Broccatelli | 1,218 |
| `bbb_permeability` | Blood-brain barrier | clf | absorption_distribution | BBB_Martins | 2,030 |
| `ppb_binding` | Plasma protein binding | reg | absorption_distribution | PPBR_AZ (human only, Option C) | 1,614 |
| `cyp3a4_inhibition` | CYP3A4 inhibition | clf | metabolism | CYP3A4_Veith | 12,328 |
| `cyp2d6_inhibition` | CYP2D6 inhibition | clf | metabolism | CYP2D6_Veith | 13,130 |
| `cyp2c9_inhibition` | CYP2C9 inhibition | clf | metabolism | CYP2C9_Veith | 12,092 |
| `clearance_microsomal` | Microsomal clearance | reg | metabolism | Clearance_Microsome_AZ | 1,102 |
| `herg_cardiotoxicity` | hERG cardiotoxicity | clf | toxicity | hERG_Karim | 13,445 |
| `ames_mutagenicity` | AMES mutagenicity | clf | toxicity | AMES | 7,255 |
| `dili_liver_injury` | Drug-induced liver injury | clf | dili_standalone | DILI + DILIst (DILIPredictor MIT) | 1,215 (aug) |
| `synthetic_accessibility` | SA score | rule_based | — | RDKit (Ertl & Schuffenhauer) | — |

reg = regression (metric: MAE). clf = classification (AUROC + AUPRC; + ECE +
Brier for calibration). 13 ML-trained + SA rule-based = 14.

## Clusters (multi-task, shared pretrained backbone, masked loss)

- **absorption_distribution** — 7 tasks (4 reg + 3 clf). Kendall uncertainty
  weighting.
- **metabolism** — 4 tasks (3 clf CYP + 1 reg Clearance). Kendall weighting.
  Clearance is the sparse task (1,102 vs 12k+) — watch its logσ_t.
- **toxicity** — hERG + AMES (2 clf). Weighting choice matters less (2 tasks).
- **dili_standalone** — DILI only. Re-test joining toxicity cluster once
  DILIst-augmented (blueprint flags this as an empirical question).

## Milestones (blueprint Module 14, solo, → Sep 30 2026)

| M | Scope | State |
|---|---|---|
| M0 | Contracts & scaffolding | **COMPLETE** (2026-08-30) |
| M1 | Data (Module 1) + Featurization (Module 3) | **COMPLETE** (2026-08-30). Ref: `MARS_M1_TECHNICAL_REFERENCE.md` |
| M2 | Modeling (Module 4) + calibration/AD (Module 5). GPU-bound. | **current** |
| M3 | Serving/API (Module 8) + Auth/DB (Module 13) + deploy (Module 10) | not started |
| M4 | Frontend (Module 9) + 3D (Module 7) + Explainability (Module 6) + novelty (MMP, chem-space) | not started |
| M5 | Eval matrix (Module 11) + polish + launch | not started |

## Acronyms

- **ADMET** — Absorption, Distribution, Metabolism, Excretion, Toxicity.
- **TDC** — Therapeutics Data Commons (PyTDC package; ADMET Benchmark Group).
- **AD** — Applicability Domain (k-NN, 5-NN Tanimoto in ECFP4 space).
- **ECFP / Morgan** — circular fingerprint; MARS: radius 2, 2048-bit,
  `useChirality=True`.
- **ETKDG / MMFF94** — RDKit conformer embedding / force-field optimization.
- **KERMT** — pretrained molecular graph transformer, GROVER successor
  (Adrian et al., Merck/NVIDIA 2025). Checkpoint `nvidia/NV-KERMT-70M-v2`
  — confirmed 2026-09-17 (pre-flight) to be the **contrastive v2.0**
  variant (`kermt_contrastive_v2.0.pt`; no base variant hosted at that
  repo). 70.6M params, hidden size 800, 6 layers, 4 heads, latent dim 512.
  Source/CLI: `github.com/NVIDIA-BioNeMo/KERMT` (v2.0.0) — NOT bundled in
  the HF repo. Official env needs GPU (`pytorch-gpu`, CUDA-native
  `cuik_molmaker`); CLI has `--no_cuda` but CPU feasibility is untested.
- **Kendall weighting** — homoscedastic uncertainty multi-task loss balancing
  (Kendall, Gal & Cipolla 2018); learnable per-task logσ_t.
- **ECE / Brier** — calibration metrics. **Temperature scaling** — 1-param
  logit rescale for GNN calibration. **Platt** — for the XGBoost baseline.
- **MMP** — Matched Molecular Pairs (novelty feature, `mmpdb` engine, Post-MVP).
- **R2** — Cloudflare R2 object storage (checkpoints, batch uploads, conformers).
- **Cloud Run** — Google serverless containers; MARS serving (backend + async
  worker). Async batch = Cloud Tasks → Cloud Run worker endpoint. $0 demo scale.
- **AIMS** — this AI Memory System.

## M1 version identifiers (all part of downstream cache keys / provenance)

`mars-standardizer-v1`, `mars-dedup-v1`, `mars-split-v1`, `mars-augmentation-v1`,
`mars-graph-v1`, `mars-morgan-r2-2048-chirality-v1`, `mars-rdkit2d-v1` (+ a
frozen 217-name descriptor set SHA), `mars-etkdgv3-mmff94-lowest-of-n-v1`,
`mars-featurize-pipeline-v1`, snapshot digest `mars-canonical-rows-v1`.
Acquisition `acq_id=20260830T181633Z` (PyTDC 1.1.15); EDA
`eda_id=20260830T191149Z`; prepare `prep_id=20260830T200000Z`.

## M1 exceptions to "adopt the TDC benchmark split"

- **hERG** — `hERG_Karim` (13,445) is not in the TDC ADMET Benchmark Group →
  self-generated deterministic Murcko split; NOT leaderboard-comparable.
- **PPB** — Option C: primary = human-only `PPBR_AZ` (1,614, `single_pred`) →
  self-generated Murcko split; NOT leaderboard-comparable. All-species pooled
  (`ppb_binding__all_species`) kept as a provenance-tracked ablation, off the
  M2 critical path.
The other 12 endpoints adopt the TDC 80/20 benchmark split verbatim.
