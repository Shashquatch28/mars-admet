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

**Type-homogeneous subgroups** (training-time only, 2026-09-20 — these are an
artifact of KERMT's one-`--dataset_type`-per-run CLI and deliberately do NOT
appear in `contracts/`, which keeps the 4 clusters above as the serving/routing
contract): `metabolism__cls` (CYP3A4/2D6/2C9), `metabolism__reg` (Clearance —
**a single-task run and the mandatory single-task baseline, never reported as a
multi-task arm**), `absorption_distribution__cls` (HIA/P-gp/BBB),
`absorption_distribution__reg` (logS/logP/Caco-2/PPB), `toxicity__cls`
(hERG/AMES — identical to the `toxicity` cluster, which is already pure).

**Calibration holdout** (`ClusterData.train_pool`, `holdout_calibration=True`) — every
molecule in any member endpoint's calibration split is removed from the KERMT training
pool, in all columns, because `train_val.csv` *contains* the calibration molecules and
KERMT selects epochs on the validation fold. Without it the temperature scaler would be
fit on molecules the model was selected against. Costs ~10% more training labels.

**`at_boundary` / `fitted_at_boundary`** — the fitted temperature sits at an end of its
search interval (0.05 or 10.0), meaning the NLL had no interior optimum (perfectly
separable or anti-correlated calibration logits). Reported, never silently accepted.

**Cluster-level test isolation** — because 12 endpoints adopt their own TDC
split, a molecule can be `train_val` for one cluster member and `test` for
another. Any shared-encoder cluster run must first remove the union of all member
test sets from the shared `train_val`, in every column. Not doing so leaks
through the encoder.

## Milestones (blueprint Module 14, solo, → Sep 30 2026)

| M | Scope | State |
|---|---|---|
| M0 | Contracts & scaffolding | **COMPLETE** (2026-08-30) |
| M1 | Data (Module 1) + Featurization (Module 3) | **COMPLETE** (2026-08-30). Ref: `MARS_M1_TECHNICAL_REFERENCE.md` |
| M2 | Modeling (Module 4) + calibration/AD (Module 5). GPU-bound. | **current** — XGBoost 70/70 done (2026-09-17); KERMT integrated + GPU-validated (2026-09-18); mixed-type blocker resolved (2026-09-20); GNN runs outstanding |
| M3 | Serving/API (Module 8) + Auth/DB (Module 13) + deploy (Module 10) | **locally/container COMPLETE** (2026-09-17, `bad0b02`); cloud deploy not started (needs GCP creds + approval) |
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
  Source/CLI: `github.com/NVIDIA-BioNeMo/KERMT` (v2.0.0, commit `e402473`) —
  NOT bundled in the HF repo. Runs in **its own official Docker container**
  (`kermt:latest`); `ml/.venv` is never given torch/`cuik_molmaker`, because
  `cuik_molmaker` is an *unconditional* import in `kermt/data/molgraph.py`
  (CPU-only install is not possible, confirmed 2026-09-18). Vendored outside
  the MARS git tree at `~/mars-work/kermt-src/` via `MARS_KERMT_REPO`.
  **Stock KERMT is a pinned, unforked dependency — MARS never patches it.**
- **KERMT mixed-type limitation** — KERMT's finetune CLI takes ONE
  `--dataset_type` per run and `KermtFinetuneTask` has a single
  `self.classification` bool, so a cluster mixing classification and regression
  endpoints cannot be jointly finetuned against the stock CLI. Inherited from
  its Chemprop/GROVER lineage, not a KERMT bug. Resolved 2026-09-20 by the
  **three-tier ladder** below.
- **Tier 0 / path (a)** — type-homogeneous subgroups (`metabolism__cls`,
  `absorption_distribution__reg`, …) trained by the **stock** KERMT CLI.
  `model_family` = `kermt_multitask_subgroup`. Same design ADMET-AI ships.
- **Tier 1 / path (b)** — MARS-owned mixed-type trainer that **imports KERMT as
  a library** inside its container. `model_family` = `kermt_mixed`. The only
  path that satisfies Module 11's mixed-cluster loss-balancing ablation axis.
- **Tier 2 / path (c)** — ordinal-CDF homogenization: a regression endpoint
  encoded as M binary `y > quantile_m` columns so a mixed cluster becomes one
  all-classification **stock-CLI** run; scalar decoded from the survival
  function. `model_family` = `kermt_ordinal`. (Frank & Hall 2001; Li & Lin 2007.)
- **`--use_mtl_loss`** — KERMT's own opt-in flag enabling `MTLLoss` (Kendall
  weighting) in `main.py finetune`. **Unreachable from MARS:**
  `agent/scripts/run_finetune_local.py`, the only finetune entry point MARS uses,
  never forwards it and parses strictly — so passing it is a hard argparse
  failure, not a no-op. The stock path is therefore **equal-weighting only**
  (= the blueprint's mandatory fixed/equal baseline). All three loss-balancing
  arms come from Tier 1. See decisions.md 2026-09-20 finding 2.
- **GradNorm** (Chen et al. 2018) — gradient-magnitude-equalizing alternative to
  Kendall weighting. Blueprint-mandated **ablation arm only**, never the default.
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
