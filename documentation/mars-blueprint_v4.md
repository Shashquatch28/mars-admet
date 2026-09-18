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
14. **Work Distribution & Milestones Module** — solo build order and phased milestones targeting end-of-September delivery (revised from an earlier 3-person split)

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
**80% train_val / 20% test**, scaffold split (Murcko scaffolds, no shared scaffolds across splits), with **5-seed cross-validation on the train/valid division within train_val** — this is TDC's own ADMET Benchmark Group protocol, not an arbitrary choice, and is the specific split required to make our results directly comparable to published TDC leaderboard numbers **where an official benchmark split exists** (a commitment already locked in Module 4's evaluation section). It's also specifically designed to reduce split-variance on small datasets like DILI (475 compounds) via the 5-seed averaging.

**hERG exception (verified 2026-08-30 during M1 acquisition).** MARS's chosen hERG dataset (`hERG_Karim`, Module 2, N ≈ 13,445) is *not* part of the TDC ADMET Benchmark Group — the published TDC hERG leaderboard is computed on the smaller `hERG` (Wang, ≈ 655 compounds). For hERG we therefore generate an **independent, deterministic Murcko scaffold split** replicating the same 80/20 / no-shared-scaffolds methodology, and results are reported as **not directly leaderboard-comparable**. The `hERG_Karim` choice is deliberate — large-data regime for the KERMT backbone and the multi-task Toxicity cluster — and the comparability trade-off is stated honestly, not routed around. A merged multi-source hERG superset (`hERG_Karim + ChEMBL + PubChem`, mirroring 2025–2026 frontier work: UnihERG_DB, the Zhang/Chen series) is logged as citable future work in `documentation/FUTURE_SCOPE.md`.

**PPB exception (verified 2026-08-30 during M1 preparation — same policy shape as hERG).** The raw TDC PPBR_AZ file pools **five species** (*Homo sapiens*, *Rattus norvegicus*, *Canis lupus familiaris*, *Mus musculus*, *Cavia porcellus* — 2,828 measurements over 1,797 unique compounds); TDC's ADMET Benchmark Group split for PPBR_AZ pools all five species (2,790 measurements) into one compound-level scaffold split and drops the species column. Because the model would then be trained to regress a scalar that is a mixture of species-specific PPB values *without a species covariate*, this is a real hidden-assumption problem for a clinically relevant endpoint.
**Decision — Option C.** *Primary MARS PPB endpoint = human only* (via `tdc.single_pred.ADME(name='PPBR_AZ')`, which filters to *Homo sapiens*, N = 1,614 compounds). Split is an **independent, deterministic Murcko scaffold split** — the official benchmark split does not partition the human subset. *Secondary all-species pooled dataset is retained, provenance-tracked, and scheduled as a comparability ablation only* — not on the M2 critical path, and only executed after M2's training architecture and compute cost are confirmed (a full re-training of the multi-task cluster for the ablation is a stretch experiment, not core). Primary human PPB results are reported as **not directly leaderboard-comparable**; the ablation is what carries the TDC-comparability caveat. Full derivation, hashing, and split reports are versioned under `ml/data/processed/<prep_id>/ppb_binding/` (primary) and `ppb_binding__all_species/` (ablation, populated when the ablation is scheduled).

### 5. Data versioning
Pin exact TDC package version + dataset snapshot hashes in a lightweight lockfile for reproducibility; full data-versioning tooling (DVC) only if the project scales enough to need it.

### 6. Cross-source data augmentation (endpoint-specific, evidence-gated)
Where a higher-quality/larger public dataset exists for a specific endpoint beyond its primary TDC source, it may be used to augment the **training/validation pool only**, subject to:
1. Standardization through the identical Module 3 pipeline before any comparison
2. Deduplication against TDC's **held-out test set** — non-negotiable, prevents leakage that would invalidate leaderboard comparability
3. For sources with an independent curation methodology (i.e., not a same-lineage superset), a label-concordance check on overlapping compounds before merging — same tiered logic as Section 3's conflict resolution, applied across datasets rather than within one

**Currently applied:** DILI augmented with DILIst (FDA/NCTR, same lineage/superset as TDC's source — adopted directly). The FDA LTKB DILIst release ships drug names + labels but no structures; independent reproductions have to build a name→SMILES resolution step. To avoid rebuilding that step, structures come from the **DILIPredictor "DILI_Goldstandard_1111.csv"** (Seal, Williams, Hosseini-Gerami, Mahale, Carpenter, Spjuth, Bender — Cambridge / Broad / Uppsala, bioRxiv 2024) — 1,111 SMILES-resolved drugs curated directly from DILIst + DILIrank, MIT-licensed (clears Module 1 §7), and already used as a 2025 comparison baseline. The FDA LTKB page remains the cited source-of-truth for the label methodology. Post-resolution attrition (~13 %) is expected and consistent with the independent replications. BBB and Clearance's candidate augmentation source (PharmaBench) was **dropped following the licensing check in §7** — remain TDC-only for now.

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
| 7 | Plasma protein binding (PPB) | Distribution | Regression | **PPBR_AZ (human only, primary MARS endpoint)**; all-species pooled kept as secondary comparability ablation — see Module 1 §4 hERG-style exception | 1,614 (human) / 1,797 compounds pooled | Medium |
| 8 | CYP3A4 inhibition | Metabolism | Classification | CYP3A4_Veith | 12,328 | Large |
| 9 | CYP2D6 inhibition | Metabolism | Classification | CYP2D6_Veith | 13,130 | Large |
| 10 | CYP2C9 inhibition | Metabolism | Classification | CYP2C9_Veith | 12,092 | Large |
| 11 | Clearance (microsomal) | Excretion | Regression | Clearance_Microsome_AZ *(TDC only — PharmaBench HLMC augmentation dropped per Module 1 §7 licensing check, CC BY-NC-ND 4.0 conflicts with project goals)* | 1,102 | Medium |
| 12 | hERG cardiotoxicity | Toxicity | Classification | hERG_Karim | 13,445 | Large |
| 13 | AMES mutagenicity | Toxicity | Classification | AMES | 7,255 | Large |
| 14 | DILI (liver injury) | Toxicity | Classification | TDC DILI test set retained + **DILIst augmentation adopted** (FDA source; SMILES-resolved via the DILIPredictor gold standard, MIT-licensed) | 1,111 (augmented, post SMILES resolution) | Small→Medium (re-evaluate) |
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
Matches Module 12's two-tier design: ≤1,000 molecules interactive (target <10s), >1,000 enqueued on **Google Cloud Tasks**, which delivers the job to a dedicated Cloud Run worker endpoint (retry/backoff handled by Cloud Tasks). The worker writes progress to Redis; the backend streams it to the client via SSE on `GET /batch/progress/{job_id}`.

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

**Direction:** serverless-container hosting on **Google Cloud Run**, chosen so the whole stack is **$0 at demo scale** (Cloud Run's always-free tier — 2M requests/mo, 360k GB-s memory, 180k vCPU-s/mo — covers demo and light real traffic; cost only begins under sustained load, pay-per-use). This is a deliberate change from the earlier Render Starter (~$7/mo/service) plan, made 2026-08-30 alongside the project-wide no-paid-compute constraint (see Training compute budget below). Cloud Run scale-to-zero has a ~1–3 s container cold start — far better than the 30–50 s free-tier wake penalty that ruled out Render's free tier — and is accepted for the demo; `min-instances` stays 0 (no always-on cost).

### Hosting stack

| Component | Choice | Why |
|---|---|---|
| Backend (FastAPI) | **Google Cloud Run** service, `min-instances=0` | Serverless containers, scale-to-zero, always-free tier covers demo + light real traffic ($0). ~1–3 s cold start accepted. Same container image as local `docker-compose`. |
| Async batch worker | **Google Cloud Run** service (HTTP-triggered) + **Google Cloud Tasks** queue | GCP-native serverless queue: `POST /batch/predict` enqueues a Cloud Task per job; Cloud Tasks delivers to a dedicated Cloud Run worker endpoint with automatic ret/backoff. No always-on worker process, no Celery broker to run. Stays in the Cloud Tasks + Cloud Run free tiers at v1 scale. SSE progress (Module 8) is served from the backend reading job state in Redis. |
| Database (Postgres) | Neon or Supabase (free tier) | Generous free tiers, serverless Postgres. Unchanged. |
| Cache (Redis) | Upstash (free tier) | Serverless, request-based — fits the Module 8 caching pattern without paying for an always-on instance |
| Frontend | Vercel (free tier) | Best-in-class React hosting, decoupled from the stateful backend |
| Object storage (model weights, batch uploads, cached conformers) | Cloudflare R2 | S3-compatible, no egress fees — matters for batch upload/download bandwidth. Unchanged (kept over GCS specifically for the zero egress fee). |
| Transactional email (Module 13 password reset) | Resend, free tier | 3,000 emails/mo, 100/day cap, 1 domain — free tier confirmed active as of mid-2026, comfortably covers password-reset volume at v1 scale; added when Module 13 was scoped |
| Training compute (separate from serving) | **College lab A100s (free, primary)** with **free-tier cloud notebooks (Kaggle / Colab, free) as the fallback**. No paid GPU rental anywhere in the plan. | Inference doesn't need GPU at our model scale (CPU sufficient per Module 3 estimates); only training benefits from GPU, and it's a bursty not continuous need. See full budget below. |

**Estimated serving cost: $0 at demo scale.** Cloud Run + Cloud Tasks free tiers cover the demo and light real usage; Neon / Upstash / Vercel / R2 / Resend all stay on their free tiers. Cost only begins under sustained real traffic, and then only pay-per-use on Cloud Run's per-request/CPU-second billing — there is no always-on instance charge.

**No-paid-compute constraint (project-wide).** Nothing in MARS's training or evaluation pipeline uses paid compute, including as a fallback. If lab A100 access does not line up with a deadline, the fallback is free-tier cloud notebooks (Kaggle Notebooks: P100 16 GB or 2×T4, 30 GPU-hr/week quota; Colab free: T4-class, session-limited), not a paid GPU rental. This is a deliberate constraint, not a cost estimate — see the Training compute budget below for how the workload fits inside it.

### Training compute budget
`LAUNCH SCOPE: MVP` for the base budget, `Post-MVP-parallel` for the ablation-matrix extension.

**What runs locally (your laptop — Intel Core Ultra 5 125H, 16GB RAM, integrated Arc graphics) vs. what needs cloud GPU:**
- **Local, free:** the entire Module 3 featurization pipeline (RDKit is CPU-only and fast — thousands of molecules/second for standardization and fingerprinting), all XGBoost baseline training (CPU-friendly, 14 cores is plenty), backend/frontend development, and small-scale code-correctness testing (1-2 epochs on a handful of molecules to verify a training script runs before committing GPU time to it).
- **GPU, required for all GNN training:** the integrated Arc graphics has no practical CUDA path for standard GNN training stacks (PyTorch Geometric / DGL-class libraries), and 16GB shared system RAM would be tight regardless. This isn't a corner that can be optimized away — but every GPU option MARS uses is free (lab A100s primary; free-tier cloud notebooks fallback).
- **Free-tier fallback GPU: Kaggle Notebooks (P100 16 GB / 2×T4) or Colab free (T4-class).** MARS's backbone (GROVER/KERMT-scale, not an LLM) does not need large hardware — but KERMT's own docs recommend ≥32 GB VRAM for finetuning (see Module 4 decisions), which a 16 GB free-tier card does not meet. On the free fallback, GNN training therefore requires gradient checkpointing + small batch + gradient accumulation, and multi-task cluster runs (the largest) are the ones most likely to need to wait for a lab A100 session rather than run on the free tier. Single-task fine-tunes on the small/medium endpoints fit the free tier comfortably with memory optimisation; XGBoost baselines never touch a GPU at all (local CPU).

### GPU strategy: college lab A100s (primary) + free-tier cloud notebooks (fallback)
`LAUNCH SCOPE: MVP` — given confirmed access to college lab A100s. **Neither tier costs anything.**

**Primary: lab A100s, free.** A100 is fast and has ample VRAM headroom (40/80 GB) for larger batch sizes, so wall-clock time for any run comes in comfortably inside the GPU-hour estimates in the tables below. The real constraint isn't compute, it's **availability**: access is walk-up/interactive, and the session ends when the lab is needed for a class. This changes the engineering requirement, not just the schedule:

- **Checkpointing is now mandatory, not optional.** Every training run — single-task, multi-task cluster, and every ablation variant — must save model + optimizer + LR-scheduler state at frequent intervals (every epoch, or every N minutes for longer-epoch runs), synced to Cloudflare R2 (already in the stack, per Module 8/10), not left on local lab disk. Shared lab machines frequently wipe home directories or enforce quotas between logins — losing a checkpoint because it wasn't pushed off-machine before leaving is a real, avoidable failure mode.
- **RNG state must be part of the checkpoint, not just model weights.** This is a specific reproducibility risk, not a generic engineering nicety: Module 11's protocol reports mean ± std across 5 fixed seeds and treats that as reproducible. If a run is interrupted and resumed without restoring the exact RNG state (data shuffling order, dropout masks, augmentation randomness), that seed's trajectory silently diverges from what a true uninterrupted run would have produced — the seed number stays "5" but stops meaning what Module 11 claims it means. Resume logic needs to restore Python/NumPy/PyTorch RNG state alongside model weights, not just get training loss decreasing again.
- **Session-sized planning:** given A100's speed, most single-task fine-tunes (the smaller/medium datasets especially) should plausibly complete within one lab session. Multi-task cluster runs and the larger single-task endpoints (CYP series, hERG, AMES) are the ones most likely to span multiple sessions — budget those as the checkpoint/resume-dependent runs, and prioritize starting them early in a session rather than as the last thing before a class kicks you out.
- **Worth a quick check, not a blocker:** confirm with the lab/department that personal-research (not directly coursework-assigned) GPU use is permitted under their policy — this varies by institution and is a five-minute question, not a redesign.

**Fallback: free-tier cloud notebooks (Kaggle / Colab), free.** Use when lab access doesn't line up with a deadline or to absorb ablation-matrix workload if lab time runs short. Kaggle's 30 GPU-hr/week quota means the ~100 GPU-hr MVP budget fits inside ~3–4 weeks of Kaggle alone, and far faster combined with lab A100 sessions. Trade-off vs. a paid card: free-tier sessions are time-boxed and pre-emptible (so the checkpoint/resume + RNG-state discipline below is doubly load-bearing), and the 16 GB VRAM ceiling forces memory optimisation for KERMT finetuning. A run that genuinely needs a single uninterrupted multi-hour block waits for a lab A100 session; it does not get a paid card.

**MVP budget (mandatory baselines + primary shipped models — Module 4):**

| Run type | Count | Est. GPU-hr each | Total GPU-hr |
|---|---|---|---|
| XGBoost baseline (14 endpoints × 5 seeds) | 70 | 0 (local, CPU) | 0 |
| Single-task GNN fine-tune (14 endpoints × 5 seeds) | 70 | ~0.3-1.5 (dataset-size dependent: DILI/HIA small, CYP/hERG/AMES large) | ~49 |
| Multi-task cluster GNN (3 clusters × 5 seeds) | 15 | ~2 (larger combined dataset, masked loss) | ~30 |
| **Subtotal** | | | **~79** |
| +25% buffer (debugging, false starts, reruns — realistic for first-time complex multi-task setups) | | | **~99, round to ~100** |

**MVP compute cost: $0.** ~100 GPU-hours, all on free infrastructure (lab A100s + free-tier notebooks). The number that matters is GPU-hours against the 30/week free-tier quota and lab-session availability, not dollars.

**Post-MVP-parallel budget (full ablation matrix — Module 11 §6, plus §5.5's robustness check):**

| Run type | Count | Est. GPU-hr each | Total GPU-hr |
|---|---|---|---|
| DILI augmented vs. non-augmented (extra: non-augmented version) | 5 | ~0.3 | ~1.5 |
| Pretrained vs. non-pretrained backbone | 15 (scoped to the 3 multi-task clusters only, not all 85 single/multi-task runs — see note) | ~2.5 (non-pretrained needs more epochs to converge) | ~37.5 |
| Loss-balancing method (2 extra methods × Metabolism + A&D × 5 seeds) | 20 | ~2 | ~40 |
| Calibration method comparison | — | ~0 (CPU-only post-processing — temperature scaling is a single scalar fit on frozen model outputs, minutes not hours) | ~0 |
| Scaffold-split robustness check (§5.5, BBB priority) | ~5-10 | ~1 | ~5-10 |
| **Subtotal** | | | **~84-89** |

**Post-MVP-parallel compute cost: $0** (~85-90 GPU-hours, same free infrastructure).

**Grand total: ~185-190 GPU-hours, $0.** All on free infrastructure (lab A100s primary, free-tier notebooks fallback). The only real constraint is schedule/attention — 100+ discrete runs, checkpoint discipline, and session planning around lab availability + the free-tier weekly quota — never cost.

**Scope note on the pretrained-vs-non-pretrained ablation:** rather than doubling the entire 85-run single-task + multi-task matrix (which would roughly double the whole budget for one ablation axis), this is deliberately scoped to just the 3 multi-task clusters. This is a real narrowing of the ablation's completeness, not a free simplification — worth revisiting if reviewers at the target venue (MLSB/AI4Science) push for the full comparison.

**Practical workflow to avoid wasting GPU-hours:** write and sanity-check training scripts locally against a tiny data subset (a few dozen molecules, 1-2 epochs) before consuming a lab A100 session or free-tier quota for the real run. Bugs caught locally cost nothing; bugs caught mid-run burn a scarce lab session or a chunk of the 30-hr weekly free-tier quota.

### Supporting infrastructure
- **Containerization:** Docker for backend/worker; `docker-compose` for local dev matching production topology
- **CI/CD:** GitHub Actions — lint/test on PR, build the container image, on merge to `main` push it to Artifact Registry and `gcloud run deploy` the backend + worker services; includes a smoke-test prediction against a known molecule to catch silent regressions (ties into Module 11's reproducibility discipline)
- **Secrets:** environment variables via platform dashboard / GitHub Actions secrets, never committed
- **Monitoring:** Sentry (free tier) for error tracking, UptimeRobot (free tier) for uptime checks
- **Domain/SSL:** free via Cloud Run (managed certs) / Vercel / Cloudflare

## Module 11: Evaluation & Benchmarking
`LAUNCH SCOPE: Split` — §1-5 (metrics, CV/reporting protocol, significance testing, reproducibility-gated leaderboard comparison, self-audit protocol) are **MVP**: need to know models actually work before shipping predictions to users. §5.5 (supplementary prospective-performance robustness check) and §6 (full ablation matrix — 14 endpoints × {baseline, single-task, multi-task} × 5 seeds × 6 ablation axes) are both **Post-MVP-parallel**: valuable for the publication/credibility angle, doesn't block product launch. **Compute budget (Module 10)** — $0: ~100 GPU-hr MVP / ~185 GPU-hr total, all on free infrastructure (lab A100s + free-tier notebooks), never paid. It's real wall-clock time across 100+ discrete runs to launch and monitor, but not a cost blocker. §7 (baseline comparison table format) follows whichever of the above it's reporting on.

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
| Batch upload | CSV/SDF upload; interactive tier up to ~1,000 molecules (<10s), async tier 1,000–50,000+ via Cloud Tasks → Cloud Run worker (Module 8) |
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
**Server-side sessions in Redis, not JWT.** Redis (Upstash) is already deployed for caching (Module 10). Session lookup is one Redis GET per request; against Upstash's request-based serverless Redis this is sub-millisecond and independent of whether the Cloud Run backend instance is warm or cold, so it adds no meaningful latency. Accounts exist specifically to gate the abuse-prone batch endpoint (Module 8), which makes instant revocation of a compromised or abusive account more important than usual — JWTs make that hard without reinventing a server-side blocklist, which just becomes this anyway. Session key: `session:{token} → user_id`, sliding 7-day TTL refreshed on activity.

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
| `batch_jobs` | `id`, `user_id` (FK, required — matches Module 8's account-gating), `status`, `molecule_count`, `r2_result_path`, `created_at`, `completed_at` | Gives job history now that accounts exist; the row is created when the Cloud Task is enqueued (Module 8) and updated by the Cloud Run worker as the job runs |

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

## Module 14: Work Plan & Milestones
`LAUNCH SCOPE: N/A` — this is a process/planning module, not a product feature. Revised from an earlier 3-person track split to a **solo build**, sequenced by dependency order rather than by parallel track, targeting full delivery by **end of September 2026**.

**Assumption stated up front:** every module (1-13) is built by one person, in sequence where a real dependency exists and in whatever order is convenient where it doesn't. There is no parallelization to coordinate and no cross-person handoff risk — the only thing that matters here is *build order*, so nothing gets started before its actual inputs exist. Time/hours-per-day is deliberately not modeled in this version; the milestones below are date-boxed against the end-of-September deadline on the assumption that the full scope gets shipped, not a hint at how many hours that requires.

### Build order (dependency chain, not a team split)

The system's own layers (Module 0's architecture diagram) still determine what can be built before what — that logic doesn't disappear just because one person is doing all of it:

1. **Contracts first** — even solo, writing down the `/predict` response shape, the API route table, and the conformer/3D data shape *before* touching code is worth keeping. It's not for handoff anymore; it's so the model, the API, and the frontend don't quietly drift out of sync with each other as the same person context-switches between them over five weeks.
2. **Data → Featurization → Models → Uncertainty/AD** (Modules 1, 3, 4, 5) — nothing here has any external input; this is the one stretch of the project that's genuinely self-contained, and it's also the longest, least-interruptible piece (GPU training), so it goes first while there's no downstream code depending on it yet.
3. **API/Serving + Auth (Modules 8, 13)** — needs the prediction contract (already written in step 1) and, for real (non-stubbed) inference, the trained models from step 2. Can start against a stub predictor earlier if it helps momentum, but isn't "done" until wired to real model output.
4. **Frontend/UI + 3D Rendering (Modules 9, 7)** — needs the API contract (step 1) and benefits from a live API (step 3) to swap out mocks. Design-system and shell work can start any time; real data wiring waits on step 3.
5. **Infra/Deployment (Module 10)** — the pieces that don't depend on anything (docker-compose, CI/CD skeleton) can and should start on day one; the actual deploy-to-prod step waits until API + frontend are both real.
6. **Evaluation & Benchmarking, Explainability, novelty track (Modules 11, 6, 12's deferred items)** — these depend on a finalized model backbone (step 2) and are what turns this from "a working app" into "a publication-credible, portfolio-differentiated one." Not optional in this plan — see milestone M4/M5 below — but correctly sequenced last since everything upstream needs to be stable first.

### Phase 0 — Contracts (do this before anything else, even solo)

Same three artifacts as before, just self-authored rather than handed off:

| Contract | Contents |
|---|---|
| **Prediction response contract** | JSON shape of a `/predict` response: per-endpoint value, units, confidence interval format (Module 5 core), AD in/out-of-domain flag, model version field (Module 8) |
| **API route contract** | Module 8's endpoint table, confirmed with concrete request/response field names |
| **Conformer/3D data contract** | Output format of Module 3 Stage 5 (ETKDG + MMFF94) that Module 7's viewer will consume — coordinate format, units |

### Module 12 (Feature Catalog) — still a spec, not a build task

Same as before: each row is implemented by whichever step in the build order above owns the underlying capability (e.g. the prediction panel is implemented once both the model output and the frontend shell exist — no ownership table needed since there's only one owner).

### Milestones — targeting Sep 30, 2026

Five milestones, sequential, covering full MVP + the publication/portfolio-credibility work (evaluation matrix, explainability, novelty track) rather than stopping at a bare launch — per the instruction to assume the full scope ships by end of month.

| Milestone | Target dates | Scope |
|---|---|---|
| **M0 — Contracts & Scaffolding** | Aug 25 – Aug 26 | Phase 0 contracts written (prediction response, API route, conformer/3D). Monorepo skeleton, docker-compose, CI/CD skeleton, `.env` template, W&B project set up. |
| **M1 — Data & Featurization** | Aug 27 – Sep 2 | Module 1: acquire all 14 TDC datasets, standardize, dedup (tiered conflict resolution), scaffold split (80/20, 5-seed), lockfile with dataset hashes, DILIst augmentation. Module 3: full featurization pipeline (standardization, graph repr, ECFP, RDKit descriptors, 3D conformers), vectorized/batched. |
| **M2 — Modeling** | Sep 3 – Sep 13 | Module 4: XGBoost baselines + single-task GNN fine-tunes (14 endpoints × 5 seeds) + multi-task cluster models (Absorption/Distribution, Metabolism, Toxicity, DILI standalone), checkpointing + RNG-state restoration throughout. Module 5: probability calibration, k-NN applicability domain (core). This is the GPU-bound, least-interruptible stretch — sequence lab A100 sessions here first. |
| **M3 — Serving & Infra** | Sep 14 – Sep 19 | Module 8: API skeleton → real routes, routing table wired to trained models (swap out any stub), Redis caching (model-version-keyed), Cloud Tasks → Cloud Run worker batch queue + SSE progress, auth/rate limiting, retention policy enforcement. Module 13: accounts, saved molecules/reports (snapshot-on-save), account deletion. Module 10: deploy to Cloud Run / Neon / Upstash / R2, monitoring (Sentry, UptimeRobot). |
| **M4 — Frontend, Explainability & Novelty Track** | Sep 20 – Sep 26 | Module 9: design system, molecule input, prediction panel, batch triage grid, comparison mode, report export, auth UI. Module 7: 3D viewer (both tracks) wired to real conformer data. Module 6: Integrated Gradients explainability + dual validation. Module 12 novelty track: `mmpdb` MMP suggestions + chemical-space map, wired to the explainability output. |
| **M5 — Evaluation, Polish, Launch** | Sep 27 – Sep 30 | Module 11: full ablation matrix (baseline/single-task/multi-task × 5 seeds × ablation axes), significance testing, self-audit, TDC leaderboard comparison tables. Final QA, WCAG/accessibility pass, smoke tests, production promotion. |

**Note on M2:** this is the single highest-risk milestone for slipping past its dates — it's the only stretch gated on physical GPU availability (lab A100 walk-up access) rather than just focused hours. If lab sessions don't line up, the free-tier cloud-notebook fallback (Kaggle / Colab, Module 10 — free, no paid card anywhere) absorbs single-task and smaller runs to keep M2 from cascading into M3-M5; multi-task cluster runs may still have to wait for a lab session, which is the residual schedule risk this milestone carries.
