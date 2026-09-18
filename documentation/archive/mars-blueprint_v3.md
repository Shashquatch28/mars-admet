# AI-Powered ADMET & Drug Safety Screening Platform — Blueprint

## 0. System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                          FRONTEND                                │
│  Molecule Editor | 3D Viewer | Prediction Panel | Chemical Space │
│  Map | Batch Triage Grid | Comparison Mode | Report Export       │
└───────────────────────────┬───────────────────────────────────────┘
                             │ REST / WebSocket
┌───────────────────────────▼───────────────────────────────────────┐
│                            API LAYER                              │
│  FastAPI — molecule validation, prediction requests, batch jobs   │
└──────┬───────────────┬───────────────┬───────────────┬───────────┘
       │               │               │               │
┌──────▼─────┐  ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
│ Featurize  │  │ Model       │ │ Async Job   │ │ Explainability│
│ (RDKit)    │  │ Registry    │ │ Queue       │ │ Engine       │
│            │  │ (per-endpt) │ │ (batch)     │ │              │
└────────────┘  └─────────────┘ └─────────────┘ └──────────────┘
       │               │               │               │
       └───────────────┴───────────────┴───────────────┘
                             │
                   ┌─────────▼─────────┐
                   │  Data Layer         │
                   │  Postgres + Cache   │
                   └─────────────────────┘
```

---

## Module List

1. **Data Module** — sources, curation pipeline, splitting strategy
2. **Endpoint Selection Module** — which ADMET properties, why, task type
3. **Featurization Module** — fingerprints, graph representations, 3D conformers
4. **Model Module** — architectures per endpoint, multi-task setup, ensembling
5. **Uncertainty & Applicability Domain Module**
6. **Explainability Module**
7. **3D Rendering Module** — conformer generation + rotating viewer
8. **API / Serving Module**
9. **Frontend / UI Module** — editor, dashboards, chemical space map, batch view
10. **Infra / Deployment Module**
11. **Evaluation & Benchmarking Module**
12. **Feature Catalog Module** — full list of webapp-facing features with technical descriptions
13. **Auth & Persistence Module** — accounts, saved molecules/reports, database schema (added post-launch-review, not in original 12)
14. **Work Distribution & Milestones Module** — 3-person parallel work split, per-task cross-person prerequisites, phased milestones (added for team scaling, not in original 12)

---

## Module 1: Data
`LAUNCH SCOPE: MVP` — foundational, nothing trains without it.

### 1. Acquisition
All 14 datasets pulled via the **TDC (Therapeutics Data Commons) Python package** — programmatic, versioned access, reproducible by construction.

### 2. Standardization consistency
Every compound across all 14 datasets run through the Module 3 Stage 1 RDKit standardization pipeline (canonicalization, salt stripping, tautomer/charge normalization) **before** deduplication or splitting.

### 3. Deduplication & conflict resolution — EDA-gated, tiered
Computed per endpoint during an EDA pass (conflict rates will genuinely differ across the 14 datasets):

| Conflict rate (per endpoint) | Action |
|---|---|
| Low (~<5% of molecules have conflicting duplicate labels) | Drop conflicting entries |
| Moderate/high, **or** dataset is already small (e.g. DILI) | Average (regression) / majority-vote (classification) instead — preserves sample size where it's precious |
| Ties in majority-vote (even split) | Drop only that specific molecule |

### 4. Scaffold-based splitting — matches TDC's official benchmark methodology
**80% train_val / 20% test**, scaffold split (Murcko scaffolds, no shared scaffolds across splits), with **5-seed cross-validation on the train/valid division within train_val** — this is TDC's own ADMET Benchmark Group protocol, not an arbitrary choice, and is the specific split required to make our results directly comparable to published TDC leaderboard numbers (a commitment already locked in Module 4's evaluation section). It's also specifically designed to reduce split-variance on small datasets like DILI (475 compounds) via the 5-seed averaging.

### 5. Data versioning
Pin exact TDC package version + dataset snapshot hashes in a lightweight lockfile for reproducibility; full data-versioning tooling (DVC) only if the project scales enough to need it.

### 6. Cross-source data augmentation (endpoint-specific, evidence-gated)
Where a higher-quality/larger public dataset exists for a specific endpoint beyond its primary TDC source, it may be used to augment the **training/validation pool only**, subject to:
1. Standardization through the identical Module 3 pipeline before any comparison
2. Deduplication against TDC's **held-out test set** — non-negotiable, prevents leakage that would invalidate leaderboard comparability
3. For sources with an independent curation methodology (i.e., not a same-lineage superset), a label-concordance check on overlapping compounds before merging — same tiered logic as Section 3's conflict resolution, applied across datasets rather than within one

**Currently applied:** DILI augmented with DILIst (FDA, same lineage/superset as TDC's source — adopted directly). BBB and Clearance's candidate augmentation source (PharmaBench) was **dropped following the licensing check in §7** — remain TDC-only for now.

### 7. Dataset licensing check
`LAUNCH SCOPE: MVP` — dataset licensing must be verified against project goals before any source is used, not assumed.

**All 14 TDC-sourced endpoint datasets (Module 2) confirmed CC BY 4.0**, verified directly against TDC's own per-dataset license pages — this includes all three AstraZeneca-released sets (Lipophilicity_AstraZeneca, PPBR_AZ, Clearance_Microsome_AZ). Several show "Not Specified. CC BY 4.0" — meaning the *original* source (e.g. AstraZeneca's 2016 disclosure) didn't itself declare a license, but TDC's own redistribution terms are CC BY 4.0 regardless, which is what governs downstream use. Attribution-only, commercial use permitted.

**DILIst** (FDA/National Center for Toxicological Research, already adopted as the DILI augmentation source) is a US federal government work product — public domain under 17 U.S.C. § 105. Low risk, no action needed.

**PharmaBench** (candidate augmentation source for BBB/Clearance) is licensed **CC BY-NC-ND 4.0** per its official Nature *Scientific Data* publication — confirmed directly from the paper's Rights and Permissions section, not inferred. This is a real constraint, not a formality:
- **NonCommercial** conflicts with MARS being explicitly modeled after commercial platforms (Insilico, Recursion, Deep Genomics) and framed as portfolio-worthy work with potential further development.
- **NoDerivatives** blocks sharing "adapted material" — and MARS's pipeline (standardization, deduplication, merging with TDC, re-splitting) is inherently derivative. Whether *training a model on* NC-ND data internally (vs. *redistributing* the merged dataset) counts as "sharing adapted material" is a genuinely unsettled question in ML data licensing — not something to resolve by assumption.

**Decision: PharmaBench dropped as a candidate augmentation source.** Given the ambiguity sits directly across MARS's stated goals — publication, potential code/data sharing, commercial-platform styling — the lower-risk call is to not build on an assumption about an unsettled legal question. BBB and Clearance stay TDC-only (CC BY 4.0), which was already the retained fallback if the concordance check failed, so this doesn't require any pipeline redesign — just removing PharmaBench from the augmentation candidate list in §6 and Module 2's endpoint table.

## Module 2: Endpoint Selection
`LAUNCH SCOPE: MVP` — all 14 endpoints ship in v1.

**Selection criteria:** clinically/practically used in real drug discovery triage, backed by a paper-published, publicly available dataset (primarily TDC / ADMET Benchmark Group), and covering all ADMET categories without redundant/low-value endpoints.

### Final 14 endpoints (13 ML-trained + 1 rule-based)

| # | Endpoint | Category | Task Type | Dataset | N (compounds) | Data Tier |
|---|---|---|---|---|---|---|
| 1 | Solubility (logS) | Absorption/Physchem | Regression | Solubility_AqSolDB | 9,982 | Large |
| 2 | Lipophilicity (logP) | Absorption/Physchem | Regression | Lipophilicity_AstraZeneca | 4,200 | Medium |
| 3 | Caco-2 permeability | Absorption | Regression | Caco2_Wang | 906 | Small |
| 4 | HIA (intestinal absorption) | Absorption | Classification | HIA_Hou | 578 | Small |
| 5 | P-gp inhibition | Absorption | Classification | Pgp_Broccatelli | 1,212 | Medium |
| 6 | BBB permeability | Distribution | Classification | BBB_Martins *(TDC only — PharmaBench augmentation dropped per Module 1 §7 licensing check, CC BY-NC-ND 4.0 conflicts with project goals)* | 1,975 | Medium |
| 7 | Plasma protein binding (PPB) | Distribution | Regression | PPBR_AZ | 1,797 | Medium |
| 8 | CYP3A4 inhibition | Metabolism | Classification | CYP3A4_Veith | 12,328 | Large |
| 9 | CYP2D6 inhibition | Metabolism | Classification | CYP2D6_Veith | 13,130 | Large |
| 10 | CYP2C9 inhibition | Metabolism | Classification | CYP2C9_Veith | 12,092 | Large |
| 11 | Clearance (microsomal) | Excretion | Regression | Clearance_Microsome_AZ *(TDC only — PharmaBench HLMC augmentation dropped per Module 1 §7 licensing check, CC BY-NC-ND 4.0 conflicts with project goals)* | 1,102 | Medium |
| 12 | hERG cardiotoxicity | Toxicity | Classification | hERG_Karim | 13,445 | Large |
| 13 | AMES mutagenicity | Toxicity | Classification | AMES | 7,255 | Large |
| 14 | DILI (liver injury) | Toxicity | Classification | TDC DILI test set retained + **DILIst augmentation adopted** (FDA, same-lineage superset) | ~1,303 (augmented) | Small→Medium (re-evaluate) |
| — | Synthetic accessibility (SA score) | N/A | Rule-based (Ertl & Schuffenhauer) | Computed via RDKit, no dataset needed | — | — |

### Endpoints deliberately excluded and why
- Half-life, Carcinogenicity, Skin Reaction — small/noisy datasets, checked later in real development (not early-triage priorities), risk of unreliable models undermining trust in the whole platform
- VDss — more specialist PK parameter than fast-triage focus warrants
- CYP substrate variants (as opposed to inhibition) — inhibition is the more clinically decision-relevant signal for drug-drug interaction risk

## Module 3: Featurization
`LAUNCH SCOPE: MVP` — the full pipeline (stages 1-5) is required for both training and serving.

**Pipeline stages, in order:**

1. **Standardization** (RDKit) — canonicalize, strip salts/counterions, normalize tautomers/charge states, reject invalid SMILES with a clear error
2. **Molecular graph representation** — atom/bond-level features feeding the shared pretrained backbone (Module 4)
3. **ECFP/Morgan fingerprints** — radius-2, 2048-bit, feeding classical ML baselines and chemical-space similarity search
4. **RDKit 2D physicochemical descriptors** (~200: MolWt, TPSA, logP, HBD/HBA, rotatable bonds, etc.) — auxiliary model input + directly surfaced in UI
5. **3D conformer generation** — ETKDG embedding + MMFF94 optimization, single lowest-energy conformer (default; revisit only if a future feature needs an ensemble), cached per molecule rather than regenerated per request

**Critical non-negotiable requirement:** the entire pipeline (stages 1-4, and 5 where relevant) must run efficiently across a **batch of molecules**, not just one at a time — standardization and featurization steps should be parallelized/vectorized over the batch. This is a real, primary workflow (see Module 12: batch library triage is one of the most common real-world use cases for this class of tool), not an edge case, so single-molecule latency cannot be the only design target.

### Stereochemistry handling
`LAUNCH SCOPE: MVP` — default RDKit/ECFP settings can silently include or strip stereochemistry depending on configuration, so this needs an explicit decision rather than relying on defaults.

**Evidence base:** RDKit's Morgan/ECFP fingerprint generation has an optional chirality flag (`useChirality`) that **defaults to off** — two molecules differing only in R/S configuration produce identical ECFP4 fingerprints unless this is explicitly enabled. This isn't a theoretical concern for MARS specifically: a quantitative meta-analysis (Nakamura et al., spanning 45 metabolic reactions across 19 substrates) found that while most CYP isoforms show only modest R/S enantiomer differences in metabolic rate (median Km/Vmax ratios 0.80–1.53 for CYP1A2/2B6/2C19/2D6/3A4), **CYP2C9 — one of MARS's three CYP endpoints — shows systematic, larger differences** (median Vmax and CLint ratios of 0.43 and 0.60). The textbook case is warfarin: S-warfarin is metabolized by CYP2C9, R-warfarin by CYP1A2/CYP3A4 — different enzymes entirely, not just different rates. Stereoselectivity is also documented at the transporter level (relevant to P-gp, BBB, Caco-2 permeability endpoints), so this isn't limited to the CYP cluster.

**Decision, stage by stage:**
- **Stage 1 (Standardization):** RDKit's canonical SMILES generation preserves defined stereocenters by default — confirm this survives salt/tautomer/charge normalization unmodified (should be a no-op change, just an explicit verification step, not a redesign).
- **Stage 2 (Molecular graph representation):** atom/bond features feeding the GNN backbone must include chirality tags explicitly — same silent-default risk as ECFP, just at the graph level instead of the fingerprint level.
- **Stage 3 (ECFP/Morgan fingerprints):** enable `useChirality=True` explicitly. Given CYP2C9 is already in MARS's endpoint list and shows exactly the effect size where this matters, defaulting to stereo-blind fingerprints would be a real, not theoretical, accuracy risk for that endpoint specifically.
- **Stage 4 (RDKit 2D descriptors):** no change needed — descriptors like MolWt, TPSA, logP, HBD/HBA are inherently stereo-insensitive by definition, so there's nothing to silently strip here.
- **Stage 5 (3D conformer generation):** no change needed — ETKDG conformer generation is inherently stereo-aware, since 3D coordinates directly encode a stereocenter's spatial configuration.

**Undefined stereocenters:** many compounds in public datasets (TDC sources pulled from varied original studies) have stereocenters that are simply unspecified in the source SMILES, not because they don't exist but because the original data didn't resolve them. Don't attempt to enumerate or guess — leave the chiral tag unset for that atom (RDKit's default behavior), consistent with not fabricating data. **EDA-gated per endpoint** (matching Module 1's existing methodology): during EDA, log the proportion of stereo-defined vs. stereo-undefined molecules per endpoint, with particular attention to CYP2C9, CYP3A4, CYP2D6, Caco-2, P-gp, and BBB given the literature link above — this determines how much practical impact the fix actually has per endpoint, rather than assuming uniformly.

## Module 4: Models
`LAUNCH SCOPE: MVP` — clusters, baselines, and empirical winner selection all ship in v1; design status is still open, launch scope is not.

**Guiding evidence (from literature review, not just heuristic):**
- Multi-task learning (MT) with a shared *pretrained* encoder rarely underperforms single-task (ST) models, and the MT benefit **grows with data size** when tasks are correlated — contrary to the intuition that only small-data endpoints need help (Adrian et al., Merck & NVIDIA, 2025, KERMT study).
- Pretrained MT models outperform non-pretrained MT (e.g., plain Chemprop) specifically when trained on **>5 correlated tasks and >50,000 combined datapoints**; below that, benefit is marginal or reverses.
- The MT performance gain tracks **task correlation**, not just task count — reinforcing that clusters must be mechanism/correlation-driven, not arbitrary groupings.
- For genuinely small, mechanistically distinct endpoints, single-task fine-tuning of a (simpler) pretrained encoder — or classical ML — outperforms forcing them into an unrelated multi-task cluster.
- Negative transfer risk rises sharply with severe label imbalance across tasks combined with low task correlation — a real risk for our 475→13,445 compound spread, hence the correlation-gated clustering below rather than one giant 14-way model.

### Architecture

**Shared backbone:** One pretrained molecular graph encoder (GROVER/KERMT-style checkpoint, publicly available — not pretrained from scratch) shared across all clusters below.

**Correlation-informed multi-task clusters (fine-tuned jointly, masked loss for missing labels):**

| Cluster | Endpoints | Rationale |
|---|---|---|
| Metabolism | CYP3A4, CYP2D6, CYP2C9, Clearance (microsomal) | Strongest literature-validated joint-training case; same enzyme family, clearance mechanistically caused by CYP activity |
| Absorption & Distribution | logS, logP, Caco-2, HIA, P-gp, BBB, PPB | Shared physicochemical drivers (lipophilicity, TPSA, H-bonding) |
| Toxicity (large-data) | hERG, AMES | Both large enough to test jointly; correlation weaker/mechanistically distinct — empirically validate, don't assume |

### Multi-task loss balancing
`LAUNCH SCOPE: MVP`

**Which clusters actually need this:** two of the three clusters mix task types — Metabolism (3 classification: CYP3A4/2D6/2C9 + 1 regression: Clearance) and Absorption & Distribution (4 regression: logS/logP/Caco-2/PPB + 3 classification: HIA/P-gp/BBB). Toxicity (hERG, AMES) is classification-only. This matters because it changes which method is actually well-matched to the problem — see below.

**Evidence base:** The most directly domain-matched paper found (QW-MTL, Zhang et al. 2025 — the first systematic multi-task study across all 13 TDC ADMET classification tasks, built on Chemprop-RDKit) uses a learnable, data-scale-aware exponential weighting scheme and outperforms single-task baselines on 12/13 tasks, with the largest gains (≈7%) on the smallest datasets (DILI, CYP2C9/2D6 Substrate). **However, it explicitly excludes regression tasks from its scope** ("tasks related to excretion... are primarily regression tasks, and thus are excluded from the scope of this study") — meaning the one paper that matches our domain doesn't actually solve our specific problem, since two of our three clusters mix MAE and BCE losses. This is a real gap in the literature, not just in our own doc, and worth being explicit about rather than citing QW-MTL as if it settles the question.

For the actual mixed regression/classification case, the standard reference is **Kendall, Gal & Cipolla 2018** (homoscedastic uncertainty weighting) — notably, this method was originally developed and validated on exactly this kind of mix (depth regression + semantic segmentation classification, jointly), not adapted to it after the fact. Each task gets a learnable log-variance parameter σₜ; regression losses are weighted by 1/(2σₜ²), classification losses by 1/σₜ², with a log σₜ regularization term that prevents the trivial solution of driving all weights to zero. Simple to implement (a handful of extra learnable scalars, no architecture change), well-established (1,000+ citations, used across vision/robotics/molecular domains per the broader search), and directly applicable to Metabolism and A&D as specified without modification.

**Alternative — GradNorm** (Chen et al. 2018): dynamically reweights by equalizing gradient magnitudes/training rates across tasks rather than assuming a likelihood form. More robust to tasks with pathologically different loss scales, but requires an extra backward pass through a shared layer per step and more tuning (an asymmetry hyperparameter α). Worth keeping as the empirical alternative given Module 4's existing "empirical winner selection" philosophy, but not the default.

**Decision:**
- **Metabolism, Absorption & Distribution (mixed-type clusters):** Kendall uncertainty weighting as the default method — directly matches the problem shape, low implementation cost, strong precedent.
- **Toxicity (hERG, AMES — classification-only):** either uncertainty weighting (consistent with the other two clusters) or QW-MTL's simpler data-scale exponential weighting (directly domain-validated for pure-classification ADMET) are both reasonable; since Toxicity is only two tasks, the choice matters less than for the 4-7 task clusters.
- **Fixed/equal weighting** stays in as the mandatory baseline comparison, not the shipped method — Module 11 already treats "multi-task cluster vs. single-task" as an ablation axis; loss-balancing method (fixed vs. uncertainty-weighted vs. GradNorm) should be added as an additional ablation axis given how much this choice can affect results, rather than picked once and left untested.

**Kendall weighting under masked/sparse labels.** MARS's clusters use masked loss for missing labels (a compound isn't necessarily labeled for every endpoint in its cluster), and the interaction between that masking and Kendall's learned per-task $\log\sigma_t$ hadn't been worked through. The combination itself isn't novel risk — recent multi-task work (a 2026 wireless-channel-modeling paper) uses exactly this pattern, computing a presence-masked per-task loss (only labeled entries contribute) and then applying Kendall weighting on top of the resulting per-task scalars. The actual risk sits one level down: **batch-level label sparsity**, not the masking mechanism itself. If a given training batch happens to contain few or no labeled examples for a sparse task (e.g. Clearance inside the Metabolism cluster, given its 1,102-compound size against CYP3A4/CYP2D6/CYP2C9's 12,000+), that task's masked loss estimate for the batch is noisy — and since $\log\sigma_t$ is updated from these noisy per-batch values, its learned uncertainty can drift or become unstable for the sparsest task in a cluster, independent of whether the overall method is theoretically sound.

**Decision — layered mitigation, not a single fix:**
1. **Monitor by default (mandatory, cheap):** log each task's $\log\sigma_t$ trajectory during training as a standard diagnostic, not just a debugging afterthought — visible instability (oscillation, divergence) on a sparse endpoint is the concrete signal that the risk described above is actually occurring, rather than staying a theoretical concern.
2. **Stratified batch composition (primary preventive fix):** construct training batches to guarantee a minimum number of labeled examples per task within a cluster (oversampling compounds carrying the sparser labels) — this addresses the mechanism directly, rather than only detecting it after the fact.
3. **Fallback — fixed weight for a persistently unstable task:** if monitoring under #1 shows a specific task's $\log\sigma_t$ isn't stabilizing even with #2 in place, that task drops to a fixed (non-learned) weight within its cluster rather than forcing uncertainty weighting to work where the data doesn't support it — a targeted exception, not an abandonment of Kendall weighting for the cluster as a whole.

This is written in as a layered decision (do #1 always, apply #2 as the default engineering practice, reserve #3 as an evidence-gated escape hatch) rather than picking one option in isolation, since #1 costs nothing and #3 is only meaningful once #1 has actually surfaced a problem.

**Single-task (standalone fine-tune of pretrained backbone):**

| Endpoint | Rationale |
|---|---|
| DILI | *Original rationale (475 compounds): too small and mechanistically distinct to safely cluster.* **Re-evaluation flagged:** with DILIst augmentation (Module 1 §6, Module 2), DILI's training pool grows to ~1,303 compounds — crossing into range where joint training with the Toxicity cluster (hERG/AMES) may now be worth empirically testing per the KERMT evidence (MT benefit scales with data size for correlated tasks). Decision should be re-tested empirically once the augmented dataset is in hand, not assumed from the original 475-compound justification. |

**Mandatory baselines per endpoint, empirical winner selected on held-out scaffold-split test set:**
- Classical ML: XGBoost/Random Forest on ECFP fingerprints
- Single-task fine-tune of the same pretrained backbone

**Evaluation discipline:** scaffold splits (not random) throughout; report against published TDC leaderboard numbers where available for credibility. **Known limitation:** scaffold-split results likely overestimate real prospective performance. A July 2026 study running the same-scale TDC sources MARS uses (BBB, HIA, CYP2D6, DILI, PPBR, Solubility) found a structural-frontier holdout — molecules in the sparsest, most physicochemically remote regions of chemical space — increases equally weighted primary error by a **median of 87.0%** relative to a matched scaffold control, and for BBB specifically causes a genuine **ranking inversion** (AUROC falls from 0.879 to 0.409, i.e. worse than chance), an effect that persists even under a higher-capacity graph-network encoder. None of the training-time robustness fixes tested in that study reliably closed the gap — the paper's conclusion is that this is a data-support problem, not something a clever loss function fixes. This doesn't invalidate scaffold-split as TDC's required leaderboard-comparability protocol, but the resulting numbers should be reported with this caveat, not presented as a prospective-performance estimate. See Module 11 for the supplementary robustness check this motivates.

### Probability calibration
`LAUNCH SCOPE: MVP` — AUROC/AUPRC measure ranking, not whether "73% probability of hERG inhibition" actually means 73%; calibration is what fixes that.

**Evidence base:** Guo et al. 2018 (ICML, the foundational reference on this problem — one of the most-cited calibration papers in ML) established that modern neural networks are systematically overconfident, and that **temperature scaling** — a single scalar parameter rescaling the logits before softmax, fit on a held-out set — is "surprisingly effective," in most cases matching or beating more flexible methods like isotonic regression or vector/matrix scaling. The key mechanism: any calibration method with many parameters overfits a small held-out set even with regularization, while a 1-parameter method structurally can't. This directly matters for MARS — HIA (578 compounds) and DILI (~1,303 augmented) mean any calibration split carved from these is small, exactly the regime where isotonic regression's flexibility becomes a liability rather than an asset (a finding echoed in general ML literature: isotonic requires more data and is prone to overfitting on smaller sets, vs. Platt/temperature scaling's stronger data efficiency). A separate, very recent large-scale study (2026) found Platt scaling and isotonic regression can actively *degrade* proper scoring performance for strong modern tabular models (XGBoost-class), with Venn-Abers and Beta calibration performing better in that setting — relevant because Module 4's mandatory XGBoost baseline is exactly this kind of model, and is not the same problem as calibrating the GNN's softmax outputs.

**Decision — method differs by model type, not one-size-fits-all:**
- **GNN (multi-task clusters + single-task DILI):** temperature scaling as default. One scalar per endpoint (or shared per cluster, tested empirically), fit on a held-out calibration split. Does not change class rankings, so AUROC/AUPRC are unaffected — purely fixes the meaning of the reported probability.
- **XGBoost baseline:** Platt scaling or isotonic regression remains reasonable here, since XGBoost doesn't have the softmax-overconfidence failure mode temperature scaling specifically targets — but given the 2026 finding above, isotonic's degradation risk on tabular models should be checked empirically rather than assumed safe, and Platt scaling is the safer default for this component.

**Held-out calibration split — shared infrastructure, not built twice:** requires a small held-out split, distinct from training and the fixed TDC test set — the same kind of split Module 5's deferred conformal prediction will eventually need. Rather than build this twice, carve out one small calibration split (held out before the 5-seed CV division) now, sized per the rule below. This split becomes shared infrastructure: calibration uses it now, conformal prediction reuses it if/when that Post-MVP item is built.

**Sizing rule:** no clean literature consensus exists for a minimum-N specifically for temperature scaling (unlike the isotonic-vs-Platt data-efficiency finding above, which does have direct support) — so rather than assert a number that isn't actually backed by anything, the rule is a pragmatic percentage-with-floor, consistent with how Module 1 already special-cases small datasets: **10% of train_val, or a floor of 50 compounds, whichever is larger.** For context against MARS's actual endpoint sizes: HIA (578 total) and DILI (~1,303 augmented) both fall under the floor at a flat 10% (≈46 and ≈104 respectively pre-floor on train_val) — the floor is specifically what keeps HIA's calibration split from being unusably thin, while large endpoints (hERG, CYP series, 12,000+ compounds) are unaffected by it since 10% already clears 50 comfortably. This is a starting rule, not a validated optimum — if HIA's ECE looks unstable across the 5 seeds once real numbers are in hand, that's the signal to revisit the floor upward rather than assume 50 was sufficient by construction.

**Evaluation:** calibration quality needs its own metrics, not just AUROC/AUPRC — added to Module 11 (see below): Expected Calibration Error (ECE) and Brier score, reported alongside the existing classification metrics, with reliability diagrams as a diagnostic during development.

## Module 5: Uncertainty & Applicability Domain
`LAUNCH SCOPE: Split` — see below. k-NN applicability domain is split out from conformal prediction because it's nearly free given work already done in Modules 1 and 3, and it's the one directly named in the problem statement's first paragraph ("identify molecules outside the model's reliable chemical domain").

**Evidence base:** A 2024 study (Li et al., J. Chem. Inf. Model.) introducing conformalized fusion regression (CFR) — combining a GNN with joint mean-quantile regression loss and ensemble-based conformal prediction — found it outperforms existing uncertainty quantification methods across ADMET tasks, and separately noted that most ADMET models are applied single-task, failing to leverage shared biochemical information across correlated properties (validating Module 4's multi-task clustering). A 2026 industrial UQ study (Novartis) validated k-NN distance (5-NN) to the training set in feature space as an applicability domain measure, finding degraded reliability for compounds further from the training set.

### CORE — basic ensembling confidence bands
`LAUNCH SCOPE: MVP` — zero extra training cost.
Reuses the 5 seeds already trained per endpoint for cross-validation (Module 1 §4 / Module 11 §2) as a natural ensemble:
- Regression: mean ± std across the 5 ensemble predictions
- Classification: mean predicted probability ± std (or predictive entropy) across the ensemble
- No new training infrastructure required — direct byproduct of the already-locked CV protocol

### CORE — k-NN applicability domain distance
`LAUNCH SCOPE: MVP` — promoted from the deferred track. Nothing new to build: reuses Module 3's ECFP4 fingerprints (already computed per molecule) and Module 1's finalized training set (already on disk).
- **Method:** 5-NN distance (Tanimoto, ECFP4 fingerprint space — matches the Novartis validation study cited above, and avoids depending on a learned embedding that could shift across model versions) from the query molecule to its 5 nearest neighbors in the endpoint's training set.
- **Threshold:** flag as "outside reliable domain" when 5-NN mean distance exceeds a percentile-based cutoff (e.g. 90th percentile of the training set's own internal 5-NN distances, computed once at training time, cached per endpoint) — self-calibrating per endpoint rather than one fixed global cutoff, since chemical density varies a lot across the 14 datasets (DILI's ~1,300 compounds vs. hERG's ~13,000).
- **Output:** a simple in/out-of-domain flag alongside each prediction (surfaces in Module 8's `/predict` response and Module 9's prediction panel), computed per-endpoint since a molecule can be in-domain for one endpoint's training set and out-of-domain for another's.
- **Cost:** one nearest-neighbor lookup against a precomputed fingerprint index per endpoint — no retraining, no calibration split, sub-millisecond at our dataset sizes.

### DEFERRED — conformal prediction
`LAUNCH SCOPE: Post-MVP` — the actual novelty-track item now that k-NN AD has moved to core.
- Ensemble-based conformal prediction calibrated on a held-out calibration split (carved from train_val, distinct from training and the fixed TDC test set), following the CFR approach — statistically valid coverage guarantees rather than an empirical spread
- **Infra note:** Module 4's probability calibration (temperature scaling) already carves out exactly this kind of held-out split for classification endpoints. When this item is eventually built, reuse that existing split rather than creating a second one — same purpose, same constraints (distinct from training and test).
- Left as a design sketch only — full specification deferred until this track is actually tackled, consistent with Module 12's build philosophy (novelty features must not block the core MVP)
- Genuinely nontrivial: needs new calibration-split infrastructure that basic ensembling and k-NN AD don't require

## Module 6: Explainability
`LAUNCH SCOPE: Post-MVP` — matches this module's "Placement" section below; Module 7's explainability integration and Module 9's color scale component both inherit this scope.

**Evidence base:** A JCTC benchmark of gradient-based explanation methods (CAM, GradCAM, smoothGrad, integrated gradients, attention) for GNN molecular predictions found integrated gradients and CAM perform best, while attention-based attribution is contested (weights frequently fail to correlate with gradient-based importance). Domain-specific precedent (Interpretable-ADMET, a published ADMET web service) independently confirms this gradient-based family (via Grad-CAM) for substructure-level ADMET explainability. Recent work (MMGX, AdapGNN, Lamole) shows pure atom-level heatmaps are a known limitation — chemists reason in terms of functional groups/substructures, not individual atom scores — so attribution must be aggregated up, not left at atom level. A consistency-benchmark study found only modest agreement between different XAI methods individually, but strong biological enrichment (up to 76% within 2Å of known binding pockets) in *consensus* attributions across methods — motivating a dual-method validation approach rather than trusting one method alone.

### Method
**Primary:** Integrated Gradients, computed at atom level, then **aggregated to functional-group/substructure level** for UI display — avoids the atom-level oversimplification critique and matches current best practice.

**Validation (dual, both cheap — no new models required):**
1. Cross-check against structural alerts already in the core feature set (PAINS/Brenk, Module 12) — if the heatmap reliably highlights known toxicophores on toxicity endpoints (hERG, AMES, DILI), that's a concrete, reportable quality signal
2. Perturbation-based sanity check — re-run inference with a highlighted fragment removed/modified, confirm the prediction shifts in the expected direction; cheap since it reuses existing inference, no additional training

### Design integration with Module 12
Explainability output is intended to feed directly into the Matched Molecular Pair suggestions feature (Module 12 novelty track) — this pairing (explain the problem substructure → suggest a fix) is not speculative; it mirrors the published Interpretable-ADMET platform's own design (Grad-CAM explainability + MMP-rule-based optimization module), reinforcing that this is an established, effective pattern in the ADMET domain specifically.

### Placement
Remains in the deferred/novelty track (Module 12) — aggregation logic, dual validation, and downstream MMP integration make this a genuinely nontrivial build, appropriately isolated from the core MVP per Module 12's build philosophy.

## Module 7: 3D Rendering
`LAUNCH SCOPE: MVP` — both Track 1 (hero/auto-rotate) and Track 2 (analysis mode) ship in v1.

**Library:** 3Dmol.js (confirmed technically sufficient) — supports atom-property-based selection/styling, clickable interactivity, multiple representation styles (stick/sphere/line/cartoon), surface rendering with property-based coloring, and native rotation. Reuses the Module 3 conformer generation pipeline as its data source.

**Architecture:** single shared viewer component with two modes, not two separate viewers — avoids duplicated rendering logic.

### Track 1 — Aesthetic/Hero mode (default view)
- Auto-rotating, minimal UI chrome — the default "wow" moment when a molecule is entered
- Styling (material shading, background, color scheme) follows Module 9's design language

### Track 2 — Analysis mode (toggled via a "Study Structure" control)
- Rotation pauses to user-controlled orbit (click-drag)
- **Grey-out/opacity controls**, selectable by functional group, element type, ring vs. non-ring atoms, or freehand atom click-selection
- **Representation toggles**: stick / ball-and-stick / space-filling (CPK) / wireframe
- Explicit hydrogen toggle
- Atom/bond labels (element, index)
- **Electrostatic potential surface view** — solvent-accessible surface colored by partial charge gradient, useful for reasoning about H-bond donor/acceptor regions relevant to solubility, PPB, and BBB endpoints
- **Distance-measurement tool** — click two atoms, display the distance; standard in serious molecular viewers, cheap to implement via the same selection API

### Explainability integration (direct link to Module 6)
`LAUNCH SCOPE: Post-MVP` — depends on Module 6 (Post-MVP), so this subsection ships with Module 6, not with the rest of Module 7. Tracks 1 and 2 above are unaffected and MVP.

An "explain this prediction" action automatically dims everything except the substructure Module 6's Integrated Gradients attribution flagged as important for a chosen endpoint — turning the 2D explainability heatmap into a spatial 3D view of *why* a toxicophore matters (relevant since liabilities like hERG binding are genuinely about 3D shape/pocket fit, not just 2D connectivity). This is a genuine differentiator with no direct competitor equivalent, and a natural byproduct of Module 6's already-locked attribution output rather than new scope.

## Module 8: API / Serving
`LAUNCH SCOPE: MVP` — all of it ships in v1; see the auth/rate-limiting, cache-key versioning, and retention/confidentiality subsections below. **Dependency:** stub accounts here mean Module 13 (auth & persistence) inherits a `user_id` and an account-gating boundary already in place, rather than starting from scratch.

**API style:** REST, with Server-Sent Events (SSE) specifically for batch job progress instead of polling. Chosen over GraphQL because our data model is fixed and well-known (14 endpoints, defined schema per molecule) rather than deeply relational with many optional query shapes — the scenario GraphQL is built for. REST also pairs naturally with the Redis caching already locked below, and batch file upload needs a REST-style multipart endpoint regardless. gRPC was ruled out (poor fit for a browser-facing API without a proxy layer).

### Core endpoints

| Endpoint | Purpose | Auth |
|---|---|---|
| `POST /predict` | Single molecule — SMILES in, all 14 endpoint predictions + basic uncertainty (Module 5 core) out | None (IP rate-limited) |
| `POST /batch/predict` | Batch upload (CSV/SDF); returns immediately if ≤1,000 molecules (interactive tier, Module 12), else returns a `job_id` | **Account required** |
| `GET /batch/progress/{job_id}` (SSE) | Real-time push of batch job progress — replaces polling | Account required |
| `GET /batch/results/{job_id}` | Retrieve results once ready | Account required |
| `GET /molecule/{id}/3d` | Conformer data for the 3D viewer (Module 7) — computed lazily | None |
| `GET /molecule/{id}/explain?endpoint=X` | Explainability attribution for a specific endpoint (Module 6) — computed lazily | None |
| `POST /compare` | Comparison mode, 2-3 molecules | None |
| `GET /molecule/{id}/report` | PDF report export | None |

### Key design decision: lazy computation for the expensive stuff
`/predict` returns only tabular predictions + basic ensembling confidence bands — stays fast, matches the Module 12 core/novelty split. **3D conformers and explainability attribution are computed on-demand**, only when the user opens that specific view, keeping the default path cheap.

### Model serving logic
Module 4's multi-task clusters (Metabolism, Absorption/Distribution, Toxicity) plus standalone DILI model mean a single forward pass through a cluster model yields multiple endpoint predictions at once. The API layer maintains a **routing table** (endpoint → serving model/cluster, plus which variant won empirically per Module 11's ablation) so overlapping-cluster requests trigger one inference call, not several.

### Caching
Redis cache keyed on (standardized SMILES + requested endpoint set + **serving model version**) for `/predict` results, **and** on lazily-computed 3D conformers and explainability attributions once generated — avoids recomputation on repeat views, not just repeat predictions. **Model version is part of the key, not just the response:** without this, deploying a new model would silently serve stale predictions labeled with the new version — a worse failure mode than no caching at all, in a tool where provenance matters. Deploying a new model naturally invalidates old cache entries by producing new keys; no explicit cache-flush step needed.

### Batch handling
Matches Module 12's two-tier design: ≤1,000 molecules interactive (target <10s), >1,000 routed to the Celery/RQ job queue with SSE progress.

### Authentication & rate limiting
`LAUNCH SCOPE: MVP`

**Auth model:** stub accounts — email/password only, no OAuth/SSO/MFA scope in v1. Deliberately lightweight: exists so Module 13 (auth & persistence, not yet scoped) has a `user_id` to build on later, without Module 8 taking on Module 13's full scope now. This is a real dependency, not a nice-to-have — **Module 13's scoping session needs to start from "wire up persistence on top of this stub," not from a blank auth design.**

**Registration gate — CAPTCHA required.** Gating the batch endpoint behind "an account" only controls abuse if creating an account costs an attacker something; without a check, a scripted adversary can mint accounts for free and route straight through the batch gate it's supposed to stop. **Cloudflare Turnstile** (free, low-friction, no third-party tracking cookie unlike reCAPTCHA) is required on the registration form specifically — this is the actual countermeasure to scripted account creation, not a nice-to-have alongside rate limiting. Login and password-reset requests are not gated (Turnstile at registration is what controls the supply of new accounts; gating login itself would just add friction for legitimate returning users without addressing the actual attack surface).

**What requires an account vs. not:**
- Single-molecule prediction (`POST /predict`) — **no account required**, anonymous access, rate-limited by IP
- Batch upload (`POST /batch/predict`) — **account required**. Batch jobs are the expensive, abuse-prone path (up to 50,000 molecules on a $7/mo instance) and are also the natural anchor point for Module 13's future "job history" feature, so gating here now avoids a migration later
- Comparison mode, report export — no account required (operate on data already returned from a prediction call, not a new expensive computation)

**Rate limits (starting point, tune post-launch against real usage):**
- Anonymous, per-IP: 60 single-molecule predictions/minute
- Per-account: 5 concurrent batch jobs, 50,000-molecule batch size cap (matches existing Module 12 tier design), no daily cap in v1 — revisit if abuse patterns emerge

### Data retention & confidentiality
`LAUNCH SCOPE: MVP` — a chemist won't paste a real candidate into a tool with an undefined data policy, so this needs to be explicit.

**Cache TTL:** Redis-cached predictions, conformers, and explainability attributions expire after **48 hours**. This is a performance cache, not storage — nothing about a submitted molecule persists past this window unless the user explicitly opts in (below).

**Batch uploads (R2):** deleted automatically 24 hours after job completion. This grace period exists only so a user can retrieve results/re-download; it is not a retention feature.

**Retraining use — opt-in only, per upload:** by default, no submitted molecule (single or batch) is used for anything beyond serving that user's own prediction. A per-upload opt-in checkbox ("allow this data to be used to improve future model versions") is required for any other use. Opted-in data is stored separately from the serving cache/upload bucket, not commingled with the default no-retention path, and its own retention terms are shown at the point of opt-in.

**Stated posture (for the UI/ToS, not just internal policy):** "MARS does not retain your molecules beyond the time needed to serve your results, and never uses your data to improve our models unless you explicitly opt in for that specific upload."

### Versioning in responses
Every response includes which model version served the prediction — extends Module 1's data-versioning discipline into serving for reproducibility.

## Module 9: Frontend / UI
`LAUNCH SCOPE: Split` — see per-component tags below. Component 3 (explainability color scale) is Post-MVP, matching Module 6 (the feature it renders), not core.

**Design philosophy:** analytical lab instrumentation vernacular (spectrometer readouts, chromatography traces, oscilloscope sweeps) — not generic SaaS-dashboard-with-a-chemistry-skin. Explicitly rejects the three current AI-design defaults (warm-cream-serif-terracotta, near-black-with-acid-accent, zero-radius broadsheet). Full design system delivered as a living HTML style guide (`style-guide.html`) plus this written specification — every choice traces to either how a real lab instrument communicates state, or a genuine data-density need of a chemist scanning results.

### Core token system
- **Color:** `--ink` (#14161A) base, `--panel` (#1A1D22) raised surfaces, `--teal` (#1B6F72) resting/structural accent, `--cyan` (#5EEAD4) live/active accent, `--risk` (#E2725B) danger flags only — never decorative. Discipline rule: teal = "it's there," cyan = "it's happening now."
- **Typography:** IBM Plex Sans (display/body), IBM Plex Mono (data/SMILES/numeric values — functional, not decorative, for column/decimal alignment). Type scale 11px–31px on a 1.25 ratio.
- **Spacing/Radius:** 8pt grid (4px–96px); radius 4/8/12px, deliberately between the two AI-cliché extremes.
- **Elevation:** surface + hairline border (shadows don't read on near-black).
- **Layout:** fixed app shell (sidebar + fixed-height 3D viewer + tabbed panels), not a scrolling page — panels scroll internally, shell stays put.
- **Motion:** signature scan-line sweep for full prediction compute; atoms-assemble on load; count-up value landing; structural-alert pulse; `prefers-reduced-motion` respected throughout.
- **Iconography:** Lucide, 1.5px stroke.
- **Command palette:** Cmd/Ctrl+K — mode switch, molecule jump, re-run prediction, export, jump to past batch.
- **Accessibility:** full WCAG 2.1 contrast audit complete (teal restricted to large text/borders only — fails AA at body size); visible focus rings; full keyboard nav; color never the sole encoding of a result.
- **Responsive strategy:** desktop/workstation-first, honest degradation (batch triage explicitly unsupported below 768px rather than faking a broken mobile grid).

### Gap-fill component specifications
1. **[MVP] Prediction panel:** 5 ADMET-category sections, responsive card grid, Toxicity prioritized (larger cards, rendered first)
2. **[MVP] Confidence intervals:** horizontal range bar per card — teal fill for interval, cyan tick for point estimate, exact numeric range in Plex Mono
3. **[Post-MVP] Explainability color scale:** bidirectional — risk-red gradient (danger-increasing substructures) vs. teal-cyan gradient (danger-decreasing), shared neutral "grey-out" mechanism with Module 7; draggable magnitude threshold legend. Depends on Module 6's attribution output (Post-MVP) and Module 7's explainability integration subsection (Post-MVP) — ships together with those, not with the rest of Module 9.
4. **[MVP] Batch upload:** full state set — idle/drag-over/uploading/per-row validation (non-blocking per-molecule errors)/complete summary
5. **[MVP] Toast/notification system:** top-right stack, reuses the existing left-border-accent grammar (cyan=success, risk=error) already defined for table error rows
6. **[MVP] Comparison mode:** 2-3 dense columns mirroring single-molecule cards, per-endpoint cyan-tint "winner" highlighting
7. **[MVP] Radar chart:** low-opacity teal "ideal zone" polygon vs. solid cyan actual-trace, weight sliders positioned below for adjacent cause/effect — maps to Module 12's core "Multi-property radar/tradeoff view"
8. **[MVP] Ultra-wide handling:** panel content max-width 1600px centered beyond 1920px; sidebar/viewer stay full-bleed
9. **[MVP] Motion tiering:** full scan-line sweep reserved for ≥50% endpoint recompute; smaller in-card shimmer for partial/live-edit recomputes — keeps the signature element meaningful rather than firing on every keystroke
10. **[MVP] Structure editor constraint (documented, not solved):** Ketcher/JSME contained in its own bordered panel, signals "specialized instrument" rather than attempting full re-skin of third-party canvas UI

### Technical stack
3Dmol.js via `molecule-3d-for-react` (Mol* flagged as future upgrade path if protein targets are added later); Radix UI primitives for accessible custom sliders/tabs/tooltips; Recharts for standard charts, hand-rolled SVG for the scan-line/trace visuals; IBM Carbon patterns referenced for data-table density and dark-theme spacing.

**Deliverables:** `style-guide.html` (live, real-CSS reference) + this written blueprint entry as the build source of truth.

## Module 10: Infra / Deployment
`LAUNCH SCOPE: MVP` — required to ship anything at all.

**Direction:** managed hosting stack (chosen over self-hosted Hetzner+Coolify for lower setup/maintenance time, at modest extra cost) — verified against current 2026 pricing rather than outdated free-tier assumptions (Railway and Fly.io both removed free tiers in 2023-2024).

### Hosting stack

| Component | Choice | Why |
|---|---|---|
| Backend (FastAPI + Celery worker) | Render, Starter tier (~$7/mo/service) | Avoids free-tier cold starts (30-50s wake penalty) that would hurt the demo experience; native background-worker service type fits Module 8's async batch design directly |
| Database (Postgres) | Neon or Supabase (free tier) | Generous free tiers, serverless Postgres, avoids Render's separate DB pricing |
| Cache (Redis) | Upstash (free tier) | Serverless, request-based — fits the Module 8 caching pattern without paying for an always-on instance |
| Frontend | Vercel (free tier) | Best-in-class React hosting, decoupled from the stateful backend |
| Object storage (model weights, batch uploads, cached conformers) | Cloudflare R2 | S3-compatible, no egress fees — matters for batch upload/download bandwidth |
| Transactional email (Module 13 password reset) | Resend, free tier | 3,000 emails/mo, 100/day cap, 1 domain — free tier confirmed active as of mid-2026, comfortably covers password-reset volume at v1 scale; added when Module 13 was scoped |
| Training compute (separate from serving) | On-demand GPU rental (RunPod, RTX 4090 tier), rented only during active training/ablation runs | Inference doesn't need GPU at our model scale (CPU sufficient per Module 3 estimates); only training benefits from GPU, and it's a bursty not continuous need. See full budget below. |

**Estimated cost:** ~$15-20/month for a fully live, always-on demo, plus training compute per the budget below.

### Training compute budget
`LAUNCH SCOPE: MVP` for the base budget, `Post-MVP-parallel` for the ablation-matrix extension.

**What runs locally (your laptop — Intel Core Ultra 5 125H, 16GB RAM, integrated Arc graphics) vs. what needs cloud GPU:**
- **Local, free:** the entire Module 3 featurization pipeline (RDKit is CPU-only and fast — thousands of molecules/second for standardization and fingerprinting), all XGBoost baseline training (CPU-friendly, 14 cores is plenty), backend/frontend development, and small-scale code-correctness testing (1-2 epochs on a handful of molecules to verify a training script runs before committing GPU time to it).
- **Cloud GPU, required (as fallback):** all GNN training — the integrated Arc graphics has no practical CUDA path for standard GNN training stacks (PyTorch Geometric / DGL-class libraries), and 16GB shared system RAM would be tight regardless. This isn't a corner that can be optimized away.
- **Recommended GPU tier: RTX 4090** on RunPod (~$0.34-0.59/hr on-demand, cheaper on spot/community tiers) as the fallback option. MARS's backbone (GROVER/KERMT-scale, not an LLM) doesn't need anything larger — 24GB VRAM is comfortable headroom. No reason to pay for A100/H100-class hardware as a *default* — see hybrid strategy below for when access to a free A100 changes this.

### Hybrid strategy: college lab A100s (primary) + RunPod (fallback)
`LAUNCH SCOPE: MVP` — given confirmed access to college lab A100s.

**Primary: lab A100s, free.** A100 is faster than the RTX 4090 baseline above (more compute, more VRAM headroom for larger batch sizes), so wall-clock time for any given run should come in under the RTX 4090 estimates in the tables below — actual GPU-hours needed will likely be somewhat lower than budgeted. The real constraint isn't compute, it's **availability**: access is walk-up/interactive, and the session ends when the lab is needed for a class. This changes the engineering requirement, not just the schedule:

- **Checkpointing is now mandatory, not optional.** Every training run — single-task, multi-task cluster, and every ablation variant — must save model + optimizer + LR-scheduler state at frequent intervals (every epoch, or every N minutes for longer-epoch runs), synced to Cloudflare R2 (already in the stack, per Module 8/10), not left on local lab disk. Shared lab machines frequently wipe home directories or enforce quotas between logins — losing a checkpoint because it wasn't pushed off-machine before leaving is a real, avoidable failure mode.
- **RNG state must be part of the checkpoint, not just model weights.** This is a specific reproducibility risk, not a generic engineering nicety: Module 11's protocol reports mean ± std across 5 fixed seeds and treats that as reproducible. If a run is interrupted and resumed without restoring the exact RNG state (data shuffling order, dropout masks, augmentation randomness), that seed's trajectory silently diverges from what a true uninterrupted run would have produced — the seed number stays "5" but stops meaning what Module 11 claims it means. Resume logic needs to restore Python/NumPy/PyTorch RNG state alongside model weights, not just get training loss decreasing again.
- **Session-sized planning:** given A100's speed, most single-task fine-tunes (the smaller/medium datasets especially) should plausibly complete within one lab session. Multi-task cluster runs and the larger single-task endpoints (CYP series, hERG, AMES) are the ones most likely to span multiple sessions — budget those as the checkpoint/resume-dependent runs, and prioritize starting them early in a session rather than as the last thing before a class kicks you out.
- **Worth a quick check, not a blocker:** confirm with the lab/department that personal-research (not directly coursework-assigned) GPU use is permitted under their policy — this varies by institution and is a five-minute question, not a redesign.

**Fallback: RunPod RTX 4090, paid.** Use when lab access doesn't line up with a deadline, when a run needs guaranteed uninterrupted completion (e.g., final numbers before a submission), or to absorb ablation-matrix workload if lab time runs short. The $40 MVP / ~$75 total budget below remains accurate as the **worst-case ceiling** — actual spend could land anywhere from that down to near $0 depending on how much of the workload the lab A100s absorb.

**MVP budget (mandatory baselines + primary shipped models — Module 4):**

| Run type | Count | Est. GPU-hr each (RTX 4090 baseline) | Total GPU-hr |
|---|---|---|---|
| XGBoost baseline (14 endpoints × 5 seeds) | 70 | 0 (local, CPU) | 0 |
| Single-task GNN fine-tune (14 endpoints × 5 seeds) | 70 | ~0.3-1.5 (dataset-size dependent: DILI/HIA small, CYP/hERG/AMES large) | ~49 |
| Multi-task cluster GNN (3 clusters × 5 seeds) | 15 | ~2 (larger combined dataset, masked loss) | ~30 |
| **Subtotal** | | | **~79** |
| +25% buffer (debugging, false starts, reruns — realistic for first-time complex multi-task setups) | | | **~99, round to ~100** |

**MVP cost ceiling: ~100 GPU-hours × ~$0.40/hr (RTX 4090 fallback rate) ≈ $40** if entirely cloud-funded; likely less in practice given free lab A100 access.

**Post-MVP-parallel budget (full ablation matrix — Module 11 §6, plus §5.5's robustness check):**

| Run type | Count | Est. GPU-hr each | Total GPU-hr |
|---|---|---|---|
| DILI augmented vs. non-augmented (extra: non-augmented version) | 5 | ~0.3 | ~1.5 |
| Pretrained vs. non-pretrained backbone | 15 (scoped to the 3 multi-task clusters only, not all 85 single/multi-task runs — see note) | ~2.5 (non-pretrained needs more epochs to converge) | ~37.5 |
| Loss-balancing method (2 extra methods × Metabolism + A&D × 5 seeds) | 20 | ~2 | ~40 |
| Calibration method comparison | — | ~0 (CPU-only post-processing — temperature scaling is a single scalar fit on frozen model outputs, minutes not hours) | ~0 |
| Scaffold-split robustness check (§5.5, BBB priority) | ~5-10 | ~1 | ~5-10 |
| **Subtotal** | | | **~84-89** |

**Post-MVP-parallel cost ceiling: ~85-90 GPU-hours × ~$0.40/hr ≈ $34-36** if entirely cloud-funded.

**Grand total ceiling (MVP + full ablation matrix): ~185-190 GPU-hours, ~$75 worst case.** With lab A100 access as primary and RunPod as fallback, realistic spend is likely well under this — possibly near $0 if lab availability covers most sessions. Either way, the number that matters most isn't the dollar figure: it's that this is genuinely a small compute footprint for what looked like a large ambiguous risk in the original review, and the actual constraint is schedule/attention (100+ discrete runs, checkpoint discipline, session planning around lab availability) rather than cost.

**Scope note on the pretrained-vs-non-pretrained ablation:** rather than doubling the entire 85-run single-task + multi-task matrix (which would roughly double the whole budget for one ablation axis), this is deliberately scoped to just the 3 multi-task clusters. This is a real narrowing of the ablation's completeness, not a free simplification — worth revisiting if reviewers at the target venue (MLSB/AI4Science) push for the full comparison.

**Practical workflow to avoid wasting GPU-hours:** write and sanity-check training scripts locally against a tiny data subset (a few dozen molecules, 1-2 epochs) before spinning up a cloud GPU pod for the real run. Bugs caught locally cost nothing; bugs caught mid-cloud-run cost real money and time.

### Supporting infrastructure
- **Containerization:** Docker for backend/worker; `docker-compose` for local dev matching production topology
- **CI/CD:** GitHub Actions — lint/test on PR, build image, auto-deploy on merge to main; includes a smoke-test prediction against a known molecule to catch silent regressions (ties into Module 11's reproducibility discipline)
- **Secrets:** environment variables via platform dashboard / GitHub Actions secrets, never committed
- **Monitoring:** Sentry (free tier) for error tracking, UptimeRobot (free tier) for uptime checks
- **Domain/SSL:** free via Render/Vercel/Cloudflare

## Module 11: Evaluation & Benchmarking
`LAUNCH SCOPE: Split` — §1-5 (metrics, CV/reporting protocol, significance testing, reproducibility-gated leaderboard comparison, self-audit protocol) are **MVP**: need to know models actually work before shipping predictions to users. §5.5 (supplementary prospective-performance robustness check) and §6 (full ablation matrix — 14 endpoints × {baseline, single-task, multi-task} × 5 seeds × 6 ablation axes) are both **Post-MVP-parallel**: valuable for the publication/credibility angle, doesn't block product launch. **Compute budget (Module 10)** — actual cost is small (~$40 MVP, ~$75 total including the full ablation matrix), so this isn't the schedule risk it looked like on paper; it's still real wall-clock time across 100+ discrete runs to launch and monitor, but not a cost blocker. §7 (baseline comparison table format) follows whichever of the above it's reporting on.

**1. Metrics per task type**
- Regression: MAE (matches TDC convention)
- Classification: AUROC + AUPRC — AUPRC specifically for imbalanced endpoints (DILI, hERG, any endpoint with skewed positive/negative ratio)
- Classification calibration (Module 4): Expected Calibration Error (ECE) and Brier score, reported alongside AUROC/AUPRC — these measure whether reported probabilities are meaningful, which ranking metrics don't capture. Reliability diagrams used as a development-time diagnostic, not a reported metric.

**2. Cross-validation & reporting protocol**
5-seed train/valid split (Module 1), fixed test set. Report **mean ± std across seeds** for every metric — never a single-run point estimate.

**3. Statistical significance testing**
Nemenyi post-hoc test when comparing multiple model variants (XGBoost / single-task / multi-task-cluster / augmented vs. non-augmented) across endpoints.

**4. Leaderboard comparison — reproducibility-gated**
A 2026 audit of TDC ADMET leaderboards found only 3 methods (CaliciBoost, MapLight, MapLight+GNN) passed a full reproducibility/leakage check, with identified data leakage in several top-ranked entries (including MiniMol, GradientBoost, XGBoost submissions). We report against these **verified-reproducible** entries as the primary comparison; unverified top leaderboard entries may be mentioned but explicitly flagged as unaudited.

**5. Self-audit protocol**
Before reporting any result: (a) confirm no scaffold overlap between train and test sets, especially post-augmentation (enforces Module 1 §6's leakage rule), (b) document hyperparameter tuning extent and what data it touched, (c) note code/environment reproducibility. Directly inoculates against the failure mode identified in the 2026 leaderboard audit.

**5.5. Supplementary prospective-performance robustness check** `LAUNCH SCOPE: Post-MVP-parallel` — motivated by Module 4's scaffold-split limitation caveat.
Rather than build the full structural-frontier methodology from scratch (a paper's worth of method — descriptor-space frontier construction, multi-view novelty scoring — disproportionate to what MARS needs), reuse an established off-the-shelf hard splitter with a public implementation as a supplementary check: **Lo-Hi** (low-similarity benchmark) or **DataSAIL** (leakage-aware partitioning), both used as comparison baselines in the July 2026 study above. Run on a subset of endpoints — **BBB is the priority**, since it showed the most severe effect (including the ranking inversion) in the closest available evidence. Report results *beside* the primary scaffold-split numbers, not as a replacement, matching the source study's own stated recommendation. This is explicitly Post-MVP-parallel: valuable for the publication's credibility and honesty about limitations, not required to ship the product.

**6. Ablation studies (core scientific contribution)**
- Multi-task cluster vs. single-task, per endpoint (empirically validates Module 4's clustering decisions)
- DILI: augmented (DILIst) vs. non-augmented (TDC-only)
- Pretrained backbone vs. non-pretrained
- Classical ML (XGBoost) vs. GNN, per endpoint
- Loss-balancing method for mixed-type clusters (Metabolism, A&D): fixed/equal weighting vs. Kendall uncertainty weighting vs. GradNorm (Module 4) — this choice materially affects results and shouldn't be picked once and left untested
- Calibration method: temperature scaling vs. Platt scaling vs. isotonic regression, per model type (GNN vs. XGBoost baseline) (Module 4) — given the 2026 finding that Platt/isotonic can degrade tabular-model calibration while temperature scaling targets GNN-specific overconfidence

**7. Baseline comparison table format**
One table per endpoint: rows = {XGBoost baseline, single-task fine-tune, multi-task cluster, verified TDC leaderboard best}, columns = {metric, mean ± std, significance vs. our best}.

## Module 12: Feature Catalog
`LAUNCH SCOPE: N/A — this module IS the MVP/Post-MVP source of truth.` Its own CORE FEATURES / NOVELTY FEATURES split already implements the LAUNCH SCOPE system; other modules' tags should trace back to their corresponding row here. Known open items: MMP suggestions description overstates novelty relative to existing prior art (Interpretable-ADMET, OptADMET, ADMETopt2, admetSAR3.0 all ship this already — still a valid differentiator vs. SwissADME/ADMETlab 2.0, just needs reframing); ADMET-AI's ~2,500-approved-drug reference-set comparison is a cheap idea absent from this catalog entirely, worth adding to core.

**Competitive basis:** benchmarked against the free/academic tier (SwissADME, ADMETlab 2.0/3.0, admetSAR, pkCSM) and the enterprise tier (Optibrium StarDrop) to (a) match table-stakes expectations and (b) identify genuine gaps worth filling for differentiation/novelty.

**Build philosophy:** core features (below) form the complete, shippable MVP on their own — none of them depend on the novelty features. Novelty features are isolated in their own section specifically so they can be built, prototyped, or descoped independently without holding up the main platform.

---

### CORE FEATURES (MVP — build first, fully self-contained)

#### Input & Molecule Handling
| Feature | Technical Description |
|---|---|
| Single molecule input | SMILES text entry or 2D structure editor (Ketcher/JSME); runs through Module 3 pipeline on submit |
| Batch upload | CSV/SDF upload; interactive tier up to ~1,000 molecules (<10s), async tier 1,000–50,000+ via job queue (Module 8) |
| Structure editor (draw-to-predict) | Live 2D editor; debounced re-prediction on edit |

#### Prediction & Analysis
| Feature | Technical Description |
|---|---|
| ADMET prediction panel | All 14 endpoints (Module 2), grouped by category, point estimate + confidence interval |
| Basic uncertainty display | Confidence bands from model ensembling — standard technique (not the more elaborate conformal-prediction version, which is noted below) |
| Applicability domain flag | 5-NN Tanimoto distance in ECFP4 space, per-endpoint self-calibrating threshold (Module 5) — in/out-of-domain flag alongside each prediction. Promoted to core: nearly free given Module 3's fingerprints and Module 1's training set are already built |
| Multi-property radar/tradeoff view | Weighted radar across selected endpoints; open equivalent of SwissADME's Bioavailability Radar |
| Drug-likeness rules & structural alerts | Lipinski Ro5, QED, PAINS/Brenk alerts (RDKit rule-based) — cheap, table-stakes |
| SA score | Rule-based synthetic accessibility (Ertl & Schuffenhauer) |
| **Approved-drug reference comparison** | Absent from the original catalog until now. Each prediction paired with its percentile against a reference set of approved drugs, mirroring ADMET-AI's design (2,579 DrugBank-sourced drugs, percentile shown alongside every prediction, radar plot for a quick summary). **Reference set source: ChEMBL, max_phase=4 (approved) compounds** — not DrugBank, whose main content is CC BY-NC 4.0 (same NonCommercial pattern flagged for PharmaBench in Module 1 §7); ChEMBL's approved-drug filter is unambiguously open, and MARS already plans to use ChEMBL for the MMP feature below, so this reuses infrastructure rather than adding a new licensing dependency. **Compute cost: negligible** — a one-time batch prediction run through MARS's own already-trained models once training completes, not a per-request cost; doesn't reopen the Module 10 compute budget. UI: reuses Module 9's existing radar chart component (gap-fill component 7) rather than building a new visualization. Genuinely more actionable to a chemist than an absolute number — "how does this compare to actual approved drugs" is a real triage aid, matching the problem statement's "efficient triage/comparison" goal directly. |

#### Exploration
| Feature | Technical Description |
|---|---|
| 3D rotating viewer | Auto-rotating conformer render (Module 3/7) via 3Dmol.js/NGL — cheap and well-established (RDKit ETKDG + MMFF94), not a risk item despite being a genuine gap vs. free-tier competitors |
| Comparison mode | Pin 2-3 molecules side by side; diff structure + properties |

#### Batch Workflows
| Feature | Technical Description |
|---|---|
| Batch triage grid | Sortable/filterable table; per-property visual fingerprint per row; sort/filter by endpoint or pass/fail threshold |
| Batch summary stats | Aggregate distributions per endpoint across uploaded set, outlier flagging |

#### Output
| Feature | Technical Description |
|---|---|
| Report export | Per-molecule PDF — structure, predictions, confidence, drug-likeness flags |
| Batch export | CSV/Excel of triaged batch results |

---

### NOVELTY / HIGH-EFFORT FEATURES (separate track — build after core MVP is stable; not a blocker for launch)

These are flagged separately because they are research-heavy, computationally nontrivial, and/or open-ended enough that they could otherwise absorb unbounded time. Each should be scoped, prototyped, and time-boxed independently, with a clear fallback of "ship without it" if it stalls.

| Feature | Why it's flagged | Fallback if descoped |
|---|---|---|
| **Explainability heatmap** (atom-level attribution) | Requires integrated gradients / attention-extraction work on top of the GNN backbone; genuinely open-ended tuning to get chemically sensible highlights. No free-tier precedent to copy from (StarDrop's version is proprietary) | Ship without it; prediction panel + confidence intervals still stand alone as a complete, credible tool |
| **Conformal prediction uncertainty** (upgrade beyond basic ensembling; k-NN applicability domain has moved to core — see Module 5) | Statistically valid coverage guarantees require a new held-out calibration split and nontrivial implementation/validation work; not required for a functional product | Basic ensembling confidence bands + k-NN AD flag (both core) are sufficient for v1 |
| **Chemical space map** (UMAP/t-SNE embedding of analogs, live property coloring) | Requires curating/hosting a reference compound library and tuning an embedding that's actually useful, not just decorative | Ship without it; batch triage grid already covers "explore many molecules at once" |
| **Matched molecular pair (MMP) suggestions** | Reframed: original framing ("closer to a research project than a feature") overstated the build cost and understated existing prior art. Interpretable-ADMET, OptADMET, ADMETopt2, and admetSAR3.0 all ship MMP-based suggestions already (OptADMET alone has ~188,000 transformation rules across 32 ADMET properties) — still a legitimate differentiator against SwissADME/ADMETlab 2.0, but not a novel technique. **Revised approach: use `mmpdb`** (open-source, RDKit-affiliated, actively maintained) as the engine rather than building fragmentation/indexing/stereochemistry-handling from scratch — this is the actual hard algorithmic part or peer implementations, and it's already solved. **Data source: MARS's own already-curated, license-clean TDC training data** (Module 1), not a separately-licensed ChEMBL pull — reuses data already on hand rather than adding a new dependency. **Genuine differentiator, honestly stated:** rules calibrated directly on MARS's own 14 trained endpoints, paired with Module 6's explainability output (explain the problem substructure → suggest a fix) — this pairing is the same design pattern Interpretable-ADMET itself uses, cited honestly rather than claimed as original. Effort has dropped from "closer to a research project" to "moderate integration effort using established tooling," but still real work (14 endpoint-specific rule databases, UI, tying to explainability) — remains Post-MVP given Module 6's own Post-MVP status, not because of algorithmic novelty risk anymore. | Ship without it initially; still the strongest long-term differentiation/publication candidate given the risk reduction from `mmpdb`, but should never be a launch blocker |
| Generative "suggest an improved analog" (de novo design) | Already deferred pre-emptively (see below) — full generative modeling scope | Not part of any near-term plan |

### Features considered and deliberately deferred entirely
- **Multi-parameter optimization (Target Product Profile scoring)** — generalization of the tradeoff radar, folded into that core feature rather than built separately
- **Generative "suggest an improved analog" (de novo design)** — StarDrop's Nova module equivalent; a v2+ stretch goal at earliest, well beyond the novelty-feature track above
- **Real-time team collaboration** — enterprise/multi-user feature, not relevant to single-user v1 scope

---

## Module 13: Auth & Persistence
`LAUNCH SCOPE: Split` — see per-component tags below. Added because MARS has no way to save molecules or reports without it. Builds directly on Module 8's stub accounts rather than starting fresh — Module 8 already establishes `user_id` and the account-gating boundary (batch upload requires an account, single prediction doesn't).

### Session strategy
**Server-side sessions in Redis, not JWT.** Redis is already deployed for caching (Module 10), and the backend runs as a persistent Render service rather than serverless/edge, so a per-request session lookup adds no meaningful latency. Accounts exist specifically to gate the abuse-prone batch endpoint (Module 8), which makes instant revocation of a compromised or abusive account more important than usual — JWTs make that hard without reinventing a server-side blocklist, which just becomes this anyway. Session key: `session:{token} → user_id`, sliding 7-day TTL refreshed on activity.

### Auth flow
`LAUNCH SCOPE: MVP`
- **Registration/login:** email + password, bcrypt/argon2 hashed, on top of Module 8's existing stub
- **Password reset:** email-based, MVP scope. Uses Resend (free tier, 3,000 emails/mo — added to Module 10's infra table) for the reset-link email. Standard flow: request reset → time-limited signed token emailed → new password form
- **No OAuth/SSO/MFA** in v1 — explicitly out of scope, consistent with Module 8's "lightweight stub" framing

### Database schema (Postgres)
`LAUNCH SCOPE: MVP` for all tables below unless noted.

| Table | Key columns | Notes |
|---|---|---|
| `users` | `id` (uuid), `email` (unique), `password_hash`, `created_at`, `last_login_at` | Extends Module 8's stub |
| `saved_molecules` | `id`, `user_id` (FK), `smiles` (standardized), `label` (optional name), `notes` (text), `tags` (text[]), `predictions_snapshot` (jsonb), `model_version`, `created_at`, `updated_at` | `predictions_snapshot` freezes predictions + model version at save time rather than live-refreshing — avoids results silently changing under a saved item; a "re-run against latest model" action is explicit, not automatic (Post-MVP, see below) |
| `saved_reports` | `id`, `user_id` (FK), `type` (single/batch), `source_batch_job_id` (nullable FK → `batch_jobs`, provenance only — see retention note below), `results_snapshot` (jsonb), `molecule_ids` (FK array → `saved_molecules`), `notes`, `tags` (text[]), `created_at` | Covers both single-molecule and full batch report saves per your scope call. `results_snapshot` copies the actual batch result data (per-molecule predictions, model version, molecule count) into Postgres at save time — same freezing pattern as `saved_molecules.predictions_snapshot` above |
| `batch_jobs` | `id`, `user_id` (FK, required — matches Module 8's account-gating), `status`, `molecule_count`, `r2_result_path`, `created_at`, `completed_at` | Gives job history now that accounts exist; ties directly into Module 8's existing Celery/RQ job queue rather than adding a new one |

**Tagging is deliberately flat** — a `text[]` column on `saved_molecules`/`saved_reports`, not a separate tag table with its own taxonomy/color management. Matches "basic tagging/notes" scope; a fuller tag system is Post-MVP if it turns out to matter.

### Retention — how this interacts with Module 8
`LAUNCH SCOPE: MVP`
**Indefinite, until the user deletes it** — not the 48h/24h defaults Module 8 set for anonymous/unsaved data. The point of a "save" action is to create an expectation of persistence; a candidate-molecule library that quietly expired would undermine both the feature and the confidentiality posture already stated in Module 8. Account deletion cascades to delete all saved data — that's the actual privacy lever, not a TTL. This needs to be stated explicitly since it's a deliberate exception to Module 8's default no-retention policy, not an oversight.

**The save-vs-purge race condition.** Module 8 purges batch results from R2 24 hours after job completion; a naive `saved_reports` row pointing at that R2 path via `source_batch_job_id` could reference already-deleted data if the user saves right at the edge of that window, or tries to save after it's closed. Two changes close this:

1. **Snapshot-on-save (structural fix).** Saving a batch report **copies the result data into `results_snapshot` (Postgres) at the moment of saving**, rather than keeping a live pointer into the ephemeral R2 bucket as the source of truth. This is the same design already locked for `saved_molecules.predictions_snapshot` — extended here rather than invented fresh, since the same problem (data changing/disappearing out from under a saved reference) applies to both tables. Once snapshotted, `saved_reports` no longer depends on R2's 24h lifecycle at all; `source_batch_job_id` remains only as a provenance link (for job-history display), not a data dependency. This removes the race structurally: there is no window in which a completed save can point at deleted data, because nothing is deleted that a save still needs.
2. **Countdown in the UI (user-facing courtesy, doesn't replace #1).** The batch results view shows a visible "N hours remaining to save this batch" countdown once a job completes, so a logged-in user isn't relying on knowing the 24h policy exists. This doesn't do any of the actual race-prevention work — #1 does — but it means a user who wants to save isn't surprised by a disappearing "Save" affordance, and it surfaces the real policy in-product rather than leaving it only in Module 8's internal spec.

**What the user sees if they try to save after the window closes:** since the save action reads from the still-live batch job result (R2) at the moment `POST` to a future `/reports/save` endpoint is called, a save attempted after purge simply fails with a clear "these results have expired and can no longer be saved" message — not a silent success referencing dead data. This should be stated explicitly in the Module 8 API surface once that endpoint is specified, so it isn't left as an implicit assumption the way the original gap was.

### MVP vs Post-MVP within this module
| Feature | Scope |
|---|---|
| Registration, login, password reset | MVP |
| Save molecule + predictions snapshot, with tags/notes | MVP |
| Save batch report, with tags/notes | MVP |
| View/delete saved items, account deletion (cascades) | MVP |
| "Re-run against latest model" action on a saved molecule | Post-MVP |
| Tag taxonomy/colors, saved collections/folders | Post-MVP |
| Sharing saved libraries with others | Out of scope entirely — Module 12 already deferred real-time team collaboration; this would reopen that |

---

## Module 14: Work Distribution & Milestones
`LAUNCH SCOPE: N/A` — this is a process/planning module, not a product feature. It exists to let three people work on Modules 1-13 simultaneously without blocking or overwriting each other, by making every cross-person dependency explicit up front rather than discovered mid-build.

**Assumption stated up front:** no names were given, so this module assigns work by **track** (ML, Backend, Frontend) rather than by person — substitute names for Person A/B/C freely. The split follows the system's own three layers (Module 0's architecture diagram), which is deliberate: it's the split that minimizes the number of files/systems two people touch in the same week, not an arbitrary even division of 13 modules by 3.

### Track assignments

| Track | Owns (modules) | Owns (cross-cutting) |
|---|---|---|
| **Person A — ML/Modeling** | Module 1 (Data), Module 2 (Endpoint Selection — already locked, no build work), Module 3 (Featurization), Module 4 (Models), Module 5 (Uncertainty & AD), Module 11 (Evaluation), Module 6 (Explainability, Post-MVP) | Structural alerts/SA score logic, MMP rule generation (Post-MVP), all training/ablation runs (Module 10's compute budget) |
| **Person B — Backend/Infra** | Module 8 (API/Serving), Module 10 (Infra/Deployment), Module 13 (Auth & Persistence) | Redis caching, Celery/RQ batch queue, rate limiting, retention policy enforcement, CI/CD |
| **Person C — Frontend/UI** | Module 9 (Frontend/UI), Module 7 (3D Rendering — viewer component only; conformer *generation* stays with Person A), UI implementation of Module 12's catalog | Structure editor integration (Ketcher/JSME), batch triage grid, report export UI, style guide |

**Module 12 (Feature Catalog) is a spec, not a build task** — it doesn't get its own owner. Each row in its tables is implemented by whichever track owns the underlying capability:

| Module 12 feature | Implementing track(s) |
|---|---|
| Single molecule input, structure editor | C (UI) — no cross-track dependency to start |
| Batch upload | C (UI) + B (job queue/endpoint) — joint |
| ADMET prediction panel, confidence display, AD flag | A (values/logic) + C (rendering) — joint |
| Drug-likeness rules, SA score | A (rule-based, RDKit) |
| Approved-drug reference comparison | A (batch prediction run + percentile calc) + C (radar chart reuse) |
| 3D rotating viewer, comparison mode | C (UI) + B (endpoints) |
| Batch triage grid, batch summary stats | C (UI) + B (data pipe) |
| Report export, batch export | C (UI) + B (file generation/serving) |
| Explainability heatmap, MMP suggestions (novelty track) | A (method) + C (UI), Post-MVP |

### Phase 0 — Shared contracts (the one blocking gate before parallel work starts)

Everything downstream depends on three short documents existing in at least draft form. These are schema sketches, not finished modules — each should take under a day, and **no one should start deep Phase 1 work before all three exist**, because guessing at these shapes is the single most likely source of throwaway rework across all three tracks.

| Contract | Owner | Consumed by | Contents |
|---|---|---|---|
| **Prediction response contract** | Person A | B, C | JSON shape of a `/predict` response: per-endpoint value, units, confidence interval format (Module 5 core), AD in/out-of-domain flag, model version field (Module 8) |
| **API route contract** | Person B | C | Module 8's endpoint table (already drafted above) confirmed with concrete request/response field names, even while internals are mocked |
| **Conformer/3D data contract** | Person A | C | Output format of Module 3 Stage 5 (ETKDG + MMFF94) that Module 7's viewer will consume — coordinate format, how multiple conformers (if ever) would be represented, units |

### Phase 1 — Parallel core build: per-task prerequisites

"Needed to start" vs. "needed to finish" matters throughout — most tasks below can *start* against a mock/stub the moment Phase 0 closes, but cannot *finish* (i.e., be marked done, not just demoable) until the real dependency lands. Anything marked **hard block** cannot be feature-complete without the listed handoff, no matter how it's mocked in the meantime.

#### Person A (ML/Modeling)
| Task | Needs from | What exactly | Start without it? |
|---|---|---|---|
| Module 1: Data | — | Nothing | Yes — start immediately |
| Module 3: Featurization | — | Nothing (depends on own Module 1) | Yes, in parallel with late Module 1 work |
| Module 4: Models | — | Nothing external (needs own Modules 1 & 3 complete) | No — sequenced after own upstream work |
| Module 5: Uncertainty & AD | — | Nothing external (needs own Modules 3 & 4) | No — sequenced after own upstream work |
| Module 11: Evaluation | — | Nothing external (needs own Module 4 outputs) | No — sequenced after own upstream work |
| Module 6: Explainability (Post-MVP) | — | Nothing external (needs own Module 4 finalized backbone) | No — sequenced |
| Trained model artifacts + inference wrapper (deliverable to B) | — | Nothing to produce it; but B's live serving is a **hard block** waiting on this | N/A — this is A's output, not input |
| `mmpdb` integration + rule generation (novelty track) | — | Nothing external — runs against A's own already-curated TDC data | Yes — scheduled inside GPU-training wait time, runs the whole way through rather than waiting for MVP to finish |

Person A is the only track with **zero cross-person inputs** to get moving — by design, so training (the longest, least interruptible work, per Module 10's lab-A100 constraints) can start on day one.

#### Person B (Backend/Infra)
| Task | Needs from | What exactly | Start without it? |
|---|---|---|---|
| Module 10: Infra scaffolding (Render/Neon/Upstash/R2/Vercel, docker-compose, CI/CD) | — | Nothing | Yes — start immediately |
| Module 8: API skeleton, routes, request/response validation | A | Prediction response contract (Phase 0) | Draft-only version yes; final schema no |
| Redis caching layer | — | Nothing | Yes |
| Celery/RQ batch queue + SSE progress | — | Nothing blocking (Module 3's "batch must be vectorized" requirement is already locked, informational only) | Yes |
| Live model serving + routing table (real predictions, not mocked) | A | Trained model artifacts + inference wrapper (function signature: batch of standardized SMILES → per-endpoint predictions + ensemble spread) | **Hard block** — everything else in Module 8 can be built and demoed against a stub predictor, but this specific piece cannot be called done without A's delivery |
| `/molecule/{id}/3d` endpoint | A | Conformer/3D data contract (Phase 0) | Draft-only version yes; final version no |
| `/molecule/{id}/explain` endpoint (Post-MVP) | A | Module 6 attribution output format | No — sequenced after A's Module 6 |
| Module 13: Auth & Persistence (schema, sessions, reset flow) | — (own Module 8 stub accounts) | Nothing external | Yes, once own Module 8 stub exists |
| Auth endpoint contract (for C's login/register/reset forms) | — | Nothing to produce it; C's auth UI needs this to wire up (not to build the shell) | N/A — this is B's output |
| Retention/confidentiality policy text | — | Nothing; C needs this copy for the UI disclaimer | N/A — this is B's output |

#### Person C (Frontend/UI)
| Task | Needs from | What exactly | Start without it? |
|---|---|---|---|
| Module 9: design tokens, style guide, component shells | — | Nothing | Yes — start immediately |
| Molecule input UI (SMILES entry, 2D editor) | — | Nothing to build the shell; needs B's `/predict` to wire submission | Yes, UI-only; wiring waits on B |
| Prediction panel + confidence interval cards | A, B | A's prediction response contract (field names/units); B's `/predict` endpoint (mock acceptable to start, real needed to finish) | Yes with a hand-built mock response matching A's contract |
| 3D viewer (Module 7 Tracks 1 & 2) | A, B | A's conformer/3D data contract; B's `/molecule/{id}/3d` endpoint | Yes with a static sample conformer; real integration waits on B |
| Batch upload + triage grid | B | Batch API shape (`job_id`, SSE progress events, results endpoint) | Yes against a mocked job lifecycle; real integration is a **hard block** for finishing |
| Comparison mode, report export UI | B | `/compare`, `/molecule/{id}/report` endpoints | Yes against mocks; final wiring waits on B |
| Auth UI (login/register/password reset forms) | B | Module 13 auth endpoint contract | Yes, shell only; wiring waits on B |
| Retention/data-policy disclaimer copy | B | Policy text (Module 8 §"Data retention & confidentiality") | No — needs the actual wording, not a placeholder, before this can ship |
| Explainability color scale (Post-MVP) | A, B | A's Module 6 attribution output; B's `/molecule/{id}/explain` endpoint | No — sequenced after both |
| MMP-panel UI shell, chemical-space map prototype (novelty track) | A | Rough shape of A's `mmpdb` rule output for the panel; can start against static/sample data | Yes — early UI scaffolding starts once the prediction panel is stable, ahead of A's rule DB being final |

### Phase 2 — Integration syncs (where mocks get swapped for the real thing)

These are the three moments parallel work actually has to meet up. Treat each as a short, scheduled sync rather than something that happens silently in a PR:

1. **A → B:** trained model checkpoints + inference wrapper handed off. B swaps the stub predictor in Module 8's routing table for real inference. This is the single highest-risk handoff on the critical path — it's gated behind all of A's training (Module 10's ~100 GPU-hour MVP budget), so B should sequence *everything else* in Module 8/10/13 to be finished before this lands, not after.
2. **B → C:** live (non-mocked) `/predict`, `/batch/*`, `/molecule/{id}/3d` endpoints handed off. C swaps mocked API calls for real ones across the prediction panel, 3D viewer, and batch triage grid.
3. **A ↔ C (indirect, via B):** conformer data and (Post-MVP) explainability attributions flow from A through B's endpoints to C's viewer — same integration moment as #2, just naming the data source explicitly since it's easy to assume "the API is live" covers this when the underlying data (e.g., explainability) may lag behind.

### Timeline — 38 days, 5 milestones

Assumes **~5 hours/day average per person** (~190 person-hours each across 38 days) — lighter on weekday-class days, heavier on weekends. If actual bandwidth differs, these day counts scale roughly linearly.

The novelty track doesn't wait for MVP to finish. Person A's GPU training has real wait time built in — a training run doesn't need attention every minute — and that dead time is CPU-only, which is exactly what `mmpdb` integration needs (it runs against already-curated TDC data, no GPU). So Person A gets novelty-track hours embedded inside GPU-training days from Milestone 1 onward, and Person C gets early UI scaffolding for the MMP panel/chemical-space map once the prediction panel is stable — both running the whole way through rather than starting after Milestone 3.

| Milestone | Days | Person A (ML) | Person B (Backend) | Person C (Frontend) |
|---|---|---|---|---|
| **M0 — Contracts** | 1 | Draft prediction response + conformer contracts (~4h) | Draft API route contract (~4h) | Attend sync, review contracts (~2h) |
| **M1 — Core Sprint 1** | 2-11 (10d) | Module 1 Data (d2-4) → Module 3 Featurization (d5-7) → Module 4 kickoff + first GNN training sessions (d8-11). **~50h.** + Novelty: `mmpdb` groundwork during GPU waits, d8-11 (~6h) | Module 10 infra (d2-3) → Module 8 API skeleton + Redis (d4-7) → Celery/RQ batch queue + registration CAPTCHA (d8-11). **~50h** | Module 9 tokens/style guide (d2-4) → molecule input UI (d5-7) → prediction panel vs. A's mock contract (d8-11). **~50h.** + Novelty: MMP-panel UI shell, d9-11 (~5h) |
| **M2 — Core Sprint 2** | 12-21 (10d) | Multi-task cluster training + calibration (d12-18) → Module 5 uncertainty/AD (d19-21). **~55h.** + Novelty: rule-DB integration continues during training waits (~10h) | Module 13 Auth/Persistence incl. snapshot-on-save fix (d12-17) → retention/cache-versioning logic (d18-21). **~50h** | 3D viewer vs. contract+mock (d12-16) → batch triage grid vs. mock (d17-21). **~50h.** + Novelty: chemical-space map prototype, static data (~6h) |
| **M3 — Integration** | 22-27 (6d) | Deliver trained models + inference wrapper (d22-23) → support integration debugging (~3h/day) → finalize novelty rule DBs now models are stable. **~30h** | **A→B handoff**: wire live model serving into routing table (d23-25) → hand live API to C (d25-27). **~30h** | **B→C handoff**: swap mocks for real `/predict`, `/batch/*`, `/3d` calls (d25-27). **~30h** |
| **M4 — Auth UI + Post-MVP** | 28-33 (6d) | Module 6 Explainability (integrated gradients + dual validation) now backbone is final. **~30h** | Finalize Module 13 auth contract for C, support integration. **~20h** | Auth UI (d28-30) → retention/ToS copy → explainability color scale + MMP suggestion UI wired to real A output (d31-33). **~30h** |
| **M5 — Eval, Polish, Launch** | 34-38 (5d) | Module 11 full ablation matrix, self-audit, benchmark tables. **~28h** | Deployment, monitoring/uptime checks, smoke tests, CI/CD promotion. **~25h** | WCAG audit, motion tiering, responsive edge cases, final QA. **~25h** |

**Totals:** A ≈ 197h, B ≈ 179h, C ≈ 189h across 38 days. The two hard-block handoffs (A's trained models → B, day ~22-23; B's live API → C, day ~25-27) sit at the M2→M3 boundary — everything else in Phase 1 is scheduled to finish before then, not after, per the Phase 2 sequencing note above.

### Phase 3 — Auth/Persistence & Post-MVP track

- **B leads Module 13**, **C builds the corresponding auth UI** — these should be worked genuinely in parallel against the auth endpoint contract from Phase 0-style handoff (B drafts it early, doesn't wait until Module 13 is "done" to share it).
- **A leads Module 6 (Explainability)** once Module 4 is stable; **C builds the explainability color scale (Module 9 component 3)** and **wires Module 7's explainability integration** once A's attribution output format is fixed — both are explicitly gated behind A, per Module 6/7/9's own Post-MVP tags.
- **Novelty track (Module 12):** MMP suggestions and the chemical-space map are joint A+C efforts (A: `mmpdb` integration/rule generation; C: UI), run **in parallel with MVP work from early on**, not gated behind MVP stabilizing — see the Timeline below for how this is scheduled without displacing core deliverables.

### Phase 4 — Evaluation, polish, launch

- **A** runs Module 11's full ablation matrix in parallel with everything above once MVP models are trained — this is publication-track work, not launch-blocking, and shouldn't pull A off any hard-block deliverable to B.
- **B** owns deployment mechanics (CI/CD promotion, monitoring setup, domain/SSL) and is the natural owner of final pre-launch smoke testing.
- **C** owns final visual/accessibility polish (WCAG audit, motion tiering, responsive edge cases) once real data is flowing end-to-end.
- **All three** contribute to the paper: A owns methods/results, B and C contribute system-description sections (architecture, UI/UX rationale) relevant to a NeurIPS-workshop/ISMB/RECOMB-style systems or applications track.

### Sync cadence (recommendation, not a hard rule)
Given the hard blocks above are few but high-impact (A→B model handoff; B→C API handoff), a lightweight **short weekly check-in** plus **ad-hoc pings at each Phase 0/2 handoff** should be enough to keep three people unblocked without needing constant coordination overhead — most of Phase 1 is genuinely parallelizable and doesn't need daily sync.
