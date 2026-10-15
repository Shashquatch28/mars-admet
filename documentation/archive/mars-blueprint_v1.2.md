# AI-Powered ADMET & Drug Safety Screening Platform — Blueprint

Status: DRAFT — modules finalized one at a time. Each module below is a skeleton until we lock it in.

---

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

## Module List (finalize in this order — adjustable)

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

---

## Module 1: Data
`STATUS: LOCKED`
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

**Currently applied:** DILI augmented with DILIst (FDA, same lineage/superset as TDC's source — adopted directly). BBB and Clearance have candidate augmentation sources (PharmaBench) flagged pending the concordance check above before adoption.

## Module 2: Endpoint Selection
`STATUS: LOCKED`
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
| 6 | BBB permeability | Distribution | Classification | BBB_Martins *(TDC test set retained; PharmaBench augmentation pending EDA concordance check — see Module 1 §6)* | 1,975 | Medium |
| 7 | Plasma protein binding (PPB) | Distribution | Regression | PPBR_AZ | 1,797 | Medium |
| 8 | CYP3A4 inhibition | Metabolism | Classification | CYP3A4_Veith | 12,328 | Large |
| 9 | CYP2D6 inhibition | Metabolism | Classification | CYP2D6_Veith | 13,130 | Large |
| 10 | CYP2C9 inhibition | Metabolism | Classification | CYP2C9_Veith | 12,092 | Large |
| 11 | Clearance (microsomal) | Excretion | Regression | Clearance_Microsome_AZ *(TDC test set retained; PharmaBench HLMC augmentation pending EDA concordance check — see Module 1 §6)* | 1,102 | Medium |
| 12 | hERG cardiotoxicity | Toxicity | Classification | hERG_Karim | 13,445 | Large |
| 13 | AMES mutagenicity | Toxicity | Classification | AMES | 7,255 | Large |
| 14 | DILI (liver injury) | Toxicity | Classification | TDC DILI test set retained + **DILIst augmentation adopted** (FDA, same-lineage superset) | ~1,303 (augmented) | Small→Medium (re-evaluate) |
| — | Synthetic accessibility (SA score) | N/A | Rule-based (Ertl & Schuffenhauer) | Computed via RDKit, no dataset needed | — | — |

### Endpoints deliberately excluded and why
- Half-life, Carcinogenicity, Skin Reaction — small/noisy datasets, checked later in real development (not early-triage priorities), risk of unreliable models undermining trust in the whole platform
- VDss — more specialist PK parameter than fast-triage focus warrants
- CYP substrate variants (as opposed to inhibition) — inhibition is the more clinically decision-relevant signal for drug-drug interaction risk

## Module 3: Featurization
`STATUS: LOCKED`
`LAUNCH SCOPE: MVP` — the full pipeline (stages 1-5) is required for both training and serving.

**Pipeline stages, in order:**

1. **Standardization** (RDKit) — canonicalize, strip salts/counterions, normalize tautomers/charge states, reject invalid SMILES with a clear error
2. **Molecular graph representation** — atom/bond-level features feeding the shared pretrained backbone (Module 4)
3. **ECFP/Morgan fingerprints** — radius-2, 2048-bit, feeding classical ML baselines and chemical-space similarity search
4. **RDKit 2D physicochemical descriptors** (~200: MolWt, TPSA, logP, HBD/HBA, rotatable bonds, etc.) — auxiliary model input + directly surfaced in UI
5. **3D conformer generation** — ETKDG embedding + MMFF94 optimization, single lowest-energy conformer (default; revisit only if a future feature needs an ensemble), cached per molecule rather than regenerated per request

**Critical non-negotiable requirement:** the entire pipeline (stages 1-4, and 5 where relevant) must run efficiently across a **batch of molecules**, not just one at a time — standardization and featurization steps should be parallelized/vectorized over the batch. This is a real, primary workflow (see Module 12: batch library triage is one of the most common real-world use cases for this class of tool), not an edge case, so single-molecule latency cannot be the only design target.

## Module 4: Models
`STATUS: PROVISIONAL — architecture direction set, open to revision if further evidence changes clustering/backbone choice`
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
`LAUNCH SCOPE: MVP` — resolved 2026-08-21, previously unaddressed (flagged in review).

**Which clusters actually need this:** two of the three clusters mix task types — Metabolism (3 classification: CYP3A4/2D6/2C9 + 1 regression: Clearance) and Absorption & Distribution (4 regression: logS/logP/Caco-2/PPB + 3 classification: HIA/P-gp/BBB). Toxicity (hERG, AMES) is classification-only. This matters because it changes which method is actually well-matched to the problem — see below.

**Evidence base:** The most directly domain-matched paper found (QW-MTL, Zhang et al. 2025 — the first systematic multi-task study across all 13 TDC ADMET classification tasks, built on Chemprop-RDKit) uses a learnable, data-scale-aware exponential weighting scheme and outperforms single-task baselines on 12/13 tasks, with the largest gains (≈7%) on the smallest datasets (DILI, CYP2C9/2D6 Substrate). **However, it explicitly excludes regression tasks from its scope** ("tasks related to excretion... are primarily regression tasks, and thus are excluded from the scope of this study") — meaning the one paper that matches our domain doesn't actually solve our specific problem, since two of our three clusters mix MAE and BCE losses. This is a real gap in the literature, not just in our own doc, and worth being explicit about rather than citing QW-MTL as if it settles the question.

For the actual mixed regression/classification case, the standard reference is **Kendall, Gal & Cipolla 2018** (homoscedastic uncertainty weighting) — notably, this method was originally developed and validated on exactly this kind of mix (depth regression + semantic segmentation classification, jointly), not adapted to it after the fact. Each task gets a learnable log-variance parameter σₜ; regression losses are weighted by 1/(2σₜ²), classification losses by 1/σₜ², with a log σₜ regularization term that prevents the trivial solution of driving all weights to zero. Simple to implement (a handful of extra learnable scalars, no architecture change), well-established (1,000+ citations, used across vision/robotics/molecular domains per the broader search), and directly applicable to Metabolism and A&D as specified without modification.

**Alternative — GradNorm** (Chen et al. 2018): dynamically reweights by equalizing gradient magnitudes/training rates across tasks rather than assuming a likelihood form. More robust to tasks with pathologically different loss scales, but requires an extra backward pass through a shared layer per step and more tuning (an asymmetry hyperparameter α). Worth keeping as the empirical alternative given Module 4's existing "empirical winner selection" philosophy, but not the default.

**Decision:**
- **Metabolism, Absorption & Distribution (mixed-type clusters):** Kendall uncertainty weighting as the default method — directly matches the problem shape, low implementation cost, strong precedent.
- **Toxicity (hERG, AMES — classification-only):** either uncertainty weighting (consistent with the other two clusters) or QW-MTL's simpler data-scale exponential weighting (directly domain-validated for pure-classification ADMET) are both reasonable; since Toxicity is only two tasks, the choice matters less than for the 4-7 task clusters.
- **Fixed/equal weighting** stays in as the mandatory baseline comparison, not the shipped method — Module 11 already treats "multi-task cluster vs. single-task" as an ablation axis; loss-balancing method (fixed vs. uncertainty-weighted vs. GradNorm) should be added as an additional ablation axis given how much this choice can affect results, rather than picked once and left untested.

**Single-task (standalone fine-tune of pretrained backbone):**

| Endpoint | Rationale |
|---|---|
| DILI | *Original rationale (475 compounds): too small and mechanistically distinct to safely cluster.* **Re-evaluation flagged:** with DILIst augmentation (Module 1 §6, Module 2), DILI's training pool grows to ~1,303 compounds — crossing into range where joint training with the Toxicity cluster (hERG/AMES) may now be worth empirically testing per the KERMT evidence (MT benefit scales with data size for correlated tasks). Decision should be re-tested empirically once the augmented dataset is in hand, not assumed from the original 475-compound justification. |

**Mandatory baselines per endpoint, empirical winner selected on held-out scaffold-split test set:**
- Classical ML: XGBoost/Random Forest on ECFP fingerprints
- Single-task fine-tune of the same pretrained backbone

**Evaluation discipline:** scaffold splits (not random) throughout; report against published TDC leaderboard numbers where available for credibility.

### Probability calibration
`LAUNCH SCOPE: MVP` — resolved 2026-08-21, previously unaddressed (flagged in review: AUROC/AUPRC measure ranking, not whether "73% probability of hERG inhibition" actually means 73%).

**Evidence base:** Guo et al. 2018 (ICML, the foundational reference on this problem — one of the most-cited calibration papers in ML) established that modern neural networks are systematically overconfident, and that **temperature scaling** — a single scalar parameter rescaling the logits before softmax, fit on a held-out set — is "surprisingly effective," in most cases matching or beating more flexible methods like isotonic regression or vector/matrix scaling. The key mechanism: any calibration method with many parameters overfits a small held-out set even with regularization, while a 1-parameter method structurally can't. This directly matters for MARS — HIA (578 compounds) and DILI (~1,303 augmented) mean any calibration split carved from these is small, exactly the regime where isotonic regression's flexibility becomes a liability rather than an asset (a finding echoed in general ML literature: isotonic requires more data and is prone to overfitting on smaller sets, vs. Platt/temperature scaling's stronger data efficiency). A separate, very recent large-scale study (2026) found Platt scaling and isotonic regression can actively *degrade* proper scoring performance for strong modern tabular models (XGBoost-class), with Venn-Abers and Beta calibration performing better in that setting — relevant because Module 4's mandatory XGBoost baseline is exactly this kind of model, and is not the same problem as calibrating the GNN's softmax outputs.

**Decision — method differs by model type, not one-size-fits-all:**
- **GNN (multi-task clusters + single-task DILI):** temperature scaling as default. One scalar per endpoint (or shared per cluster, tested empirically), fit on a held-out calibration split. Does not change class rankings, so AUROC/AUPRC are unaffected — purely fixes the meaning of the reported probability.
- **XGBoost baseline:** Platt scaling or isotonic regression (the review's original suggestion) remains reasonable here, since XGBoost doesn't have the softmax-overconfidence failure mode temperature scaling specifically targets — but given the 2026 finding above, isotonic's degradation risk on tabular models should be checked empirically rather than assumed safe, and Platt scaling is the safer default for this component.

**Held-out calibration split — shared infrastructure, not built twice:** requires a small held-out split, distinct from training and the fixed TDC test set — the same kind of split Module 5's deferred conformal prediction will eventually need. Rather than build this twice, carve out one small calibration split (~10% of train_val, held out before the 5-seed CV division) now, sized appropriately per endpoint given how small some datasets are (HIA, DILI). This split becomes shared infrastructure: calibration uses it now, conformal prediction reuses it if/when that Post-MVP item is built.

**Evaluation:** calibration quality needs its own metrics, not just AUROC/AUPRC — added to Module 11 (see below): Expected Calibration Error (ECE) and Brier score, reported alongside the existing classification metrics, with reliability diagrams as a diagnostic during development.

## Module 5: Uncertainty & Applicability Domain
`STATUS: LOCKED` (basic ensembling + k-NN AD) / `DRAFT` (conformal prediction)
`LAUNCH SCOPE: Split` — see below. Re-scoped 2026-08-20: k-NN applicability domain was previously bundled with conformal prediction under one "DEFERRED" label; split out because it's nearly free given work already done in Modules 1 and 3, and it's the one directly named in the problem statement's first paragraph ("identify molecules outside the model's reliable chemical domain").

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
- **Infra note (added 2026-08-21):** Module 4's probability calibration (temperature scaling) already carves out exactly this kind of held-out split for classification endpoints. When this item is eventually built, reuse that existing split rather than creating a second one — same purpose, same constraints (distinct from training and test).
- Left as a design sketch only — full specification deferred until this track is actually tackled, consistent with Module 12's build philosophy (novelty features must not block the core MVP)
- Genuinely nontrivial: needs new calibration-split infrastructure that basic ensembling and k-NN AD don't require

## Module 6: Explainability
`STATUS: LOCKED`
`LAUNCH SCOPE: Post-MVP` — matches this module's own "Placement" section below. This tag is now authoritative for downstream dependents (Module 7's explainability integration subsection, Module 9's color scale component) — both already updated to match.

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
`STATUS: LOCKED`
`LAUNCH SCOPE: MVP` — both Track 1 (hero/auto-rotate) and Track 2 (analysis mode) ship in v1. Confirmed 2026-08-20: Track 2 was previously unscoped (specced but absent from Module 12's core feature list); now explicitly MVP.

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
`STATUS: LOCKED`
`LAUNCH SCOPE: MVP` — all of it ships in v1. Previously-missing subsections (auth/rate-limiting, cache-key versioning, retention/confidentiality policy) resolved 2026-08-21 — see their own subsections below. **New dependency created:** stub accounts here mean Module 13 (auth & persistence, not yet scoped) inherits a `user_id` and an account-gating boundary already in place, rather than starting from scratch.

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
Redis cache keyed on (standardized SMILES + requested endpoint set + **serving model version**) for `/predict` results, **and** on lazily-computed 3D conformers and explainability attributions once generated — avoids recomputation on repeat views, not just repeat predictions. **Model version is part of the key, not just the response** (fixed 2026-08-21, per review): without this, deploying a new model would silently serve stale predictions labeled with the new version — a worse failure mode than no caching at all, in a tool where provenance matters. Deploying a new model naturally invalidates old cache entries by producing new keys; no explicit cache-flush step needed.

### Batch handling
Matches Module 12's two-tier design: ≤1,000 molecules interactive (target <10s), >1,000 routed to the Celery/RQ job queue with SSE progress.

### Authentication & rate limiting
`LAUNCH SCOPE: MVP` — resolved 2026-08-21, previously an unstated gap flagged in review.

**Auth model:** stub accounts — email/password only, no OAuth/SSO/MFA scope in v1. Deliberately lightweight: exists so Module 13 (auth & persistence, not yet scoped) has a `user_id` to build on later, without Module 8 taking on Module 13's full scope now. This is a real dependency, not a nice-to-have — **Module 13's scoping session needs to start from "wire up persistence on top of this stub," not from a blank auth design.**

**What requires an account vs. not:**
- Single-molecule prediction (`POST /predict`) — **no account required**, anonymous access, rate-limited by IP
- Batch upload (`POST /batch/predict`) — **account required**. Batch jobs are the expensive, abuse-prone path (up to 50,000 molecules on a $7/mo instance per the review's flag) and are also the natural anchor point for Module 13's future "job history" feature, so gating here now avoids a migration later
- Comparison mode, report export — no account required (operate on data already returned from a prediction call, not a new expensive computation)

**Rate limits (starting point, tune post-launch against real usage):**
- Anonymous, per-IP: 60 single-molecule predictions/minute
- Per-account: 5 concurrent batch jobs, 50,000-molecule batch size cap (matches existing Module 12 tier design), no daily cap in v1 — revisit if abuse patterns emerge

### Data retention & confidentiality
`LAUNCH SCOPE: MVP` — resolved 2026-08-21, previously the most strongly flagged gap in review ("a chemist won't paste a real candidate into a tool with an undefined data policy").

**Cache TTL:** Redis-cached predictions, conformers, and explainability attributions expire after **48 hours**. This is a performance cache, not storage — nothing about a submitted molecule persists past this window unless the user explicitly opts in (below).

**Batch uploads (R2):** deleted automatically 24 hours after job completion. This grace period exists only so a user can retrieve results/re-download; it is not a retention feature.

**Retraining use — opt-in only, per upload:** by default, no submitted molecule (single or batch) is used for anything beyond serving that user's own prediction. A per-upload opt-in checkbox ("allow this data to be used to improve future model versions") is required for any other use. Opted-in data is stored separately from the serving cache/upload bucket, not commingled with the default no-retention path, and its own retention terms are shown at the point of opt-in.

**Stated posture (for the UI/ToS, not just internal policy):** "MARS does not retain your molecules beyond the time needed to serve your results, and never uses your data to improve our models unless you explicitly opt in for that specific upload."

### Versioning in responses
Every response includes which model version served the prediction — extends Module 1's data-versioning discipline into serving for reproducibility.

## Module 9: Frontend / UI
`STATUS: LOCKED`
`LAUNCH SCOPE: Split` — see per-component tags below. Re-scoped 2026-08-20: component 3 (explainability color scale) was previously listed as an untagged "Gap-fill component" alongside core items, implying MVP, while the feature it renders (Module 6) is explicitly Post-MVP. Re-flagged to match.

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
`STATUS: LOCKED`
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
| Training compute (separate from serving) | On-demand GPU rental (RunPod/Lambda Labs), rented only during active training/ablation runs | Inference doesn't need GPU at our model scale (CPU sufficient per Module 3 estimates); only training benefits from GPU, and it's a bursty not continuous need |

**Estimated cost:** ~$15-20/month for a fully live, always-on demo, plus occasional GPU rental during training phases only.

### Supporting infrastructure
- **Containerization:** Docker for backend/worker; `docker-compose` for local dev matching production topology
- **CI/CD:** GitHub Actions — lint/test on PR, build image, auto-deploy on merge to main; includes a smoke-test prediction against a known molecule to catch silent regressions (ties into Module 11's reproducibility discipline)
- **Secrets:** environment variables via platform dashboard / GitHub Actions secrets, never committed
- **Monitoring:** Sentry (free tier) for error tracking, UptimeRobot (free tier) for uptime checks
- **Domain/SSL:** free via Render/Vercel/Cloudflare

## Module 11: Evaluation & Benchmarking
`STATUS: LOCKED — provisional, subject to revision if further evidence emerges`
`LAUNCH SCOPE: Split` — §1-5 (metrics, CV/reporting protocol, significance testing, reproducibility-gated leaderboard comparison, self-audit protocol) are **MVP**: need to know models actually work before shipping predictions to users. §6 (full ablation matrix — 14 endpoints × {baseline, single-task, multi-task} × 5 seeds × 6 ablation axes as of 2026-08-21's calibration addition, 100+ training runs per the review's compute-budget flag, growing not shrinking) is **Post-MVP-parallel**: the core scientific/publication contribution, doesn't block product launch, but is the single most likely item to blow the timeline if left unscheduled. §7 (baseline comparison table format) follows whichever of the above it's reporting on.

**1. Metrics per task type**
- Regression: MAE (matches TDC convention)
- Classification: AUROC + AUPRC — AUPRC specifically for imbalanced endpoints (DILI, hERG, any endpoint with skewed positive/negative ratio)
- Classification calibration (added 2026-08-21, Module 4): Expected Calibration Error (ECE) and Brier score, reported alongside AUROC/AUPRC — these measure whether reported probabilities are meaningful, which ranking metrics don't capture. Reliability diagrams used as a development-time diagnostic, not a reported metric.

**2. Cross-validation & reporting protocol**
5-seed train/valid split (Module 1), fixed test set. Report **mean ± std across seeds** for every metric — never a single-run point estimate.

**3. Statistical significance testing**
Nemenyi post-hoc test when comparing multiple model variants (XGBoost / single-task / multi-task-cluster / augmented vs. non-augmented) across endpoints.

**4. Leaderboard comparison — reproducibility-gated**
A 2026 audit of TDC ADMET leaderboards found only 3 methods (CaliciBoost, MapLight, MapLight+GNN) passed a full reproducibility/leakage check, with identified data leakage in several top-ranked entries (including MiniMol, GradientBoost, XGBoost submissions). We report against these **verified-reproducible** entries as the primary comparison; unverified top leaderboard entries may be mentioned but explicitly flagged as unaudited.

**5. Self-audit protocol**
Before reporting any result: (a) confirm no scaffold overlap between train and test sets, especially post-augmentation (enforces Module 1 §6's leakage rule), (b) document hyperparameter tuning extent and what data it touched, (c) note code/environment reproducibility. Directly inoculates against the failure mode identified in the 2026 leaderboard audit.

**6. Ablation studies (core scientific contribution)**
- Multi-task cluster vs. single-task, per endpoint (empirically validates Module 4's clustering decisions)
- DILI: augmented (DILIst) vs. non-augmented (TDC-only)
- Pretrained backbone vs. non-pretrained
- Classical ML (XGBoost) vs. GNN, per endpoint
- Loss-balancing method for mixed-type clusters (Metabolism, A&D): fixed/equal weighting vs. Kendall uncertainty weighting vs. GradNorm (Module 4) — added 2026-08-21, since this choice materially affects results and shouldn't be picked once and left untested
- Calibration method: temperature scaling vs. Platt scaling vs. isotonic regression, per model type (GNN vs. XGBoost baseline) — added 2026-08-21 (Module 4), given the 2026 finding that Platt/isotonic can degrade tabular-model calibration while temperature scaling targets GNN-specific overconfidence

**7. Baseline comparison table format**
One table per endpoint: rows = {XGBoost baseline, single-task fine-tune, multi-task cluster, verified TDC leaderboard best}, columns = {metric, mean ± std, significance vs. our best}.

## Module 12: Feature Catalog
`STATUS: LOCKED`
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
| Applicability domain flag | 5-NN Tanimoto distance in ECFP4 space, per-endpoint self-calibrating threshold (Module 5) — in/out-of-domain flag alongside each prediction. Promoted to core 2026-08-20: nearly free given Module 3's fingerprints and Module 1's training set are already built |
| Multi-property radar/tradeoff view | Weighted radar across selected endpoints; open equivalent of SwissADME's Bioavailability Radar |
| Drug-likeness rules & structural alerts | Lipinski Ro5, QED, PAINS/Brenk alerts (RDKit rule-based) — cheap, table-stakes |
| SA score | Rule-based synthetic accessibility (Ertl & Schuffenhauer) |

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
| **Matched molecular pair (MMP) suggestions** | The single biggest scope item: requires building an open MMP database from public bioactivity data (ChEMBL-derived) plus a substitution-effect algorithm — this is closer to a research project than a feature | Ship without it initially; this is the strongest long-term differentiation/publication candidate, but should never be a launch blocker |
| Generative "suggest an improved analog" (de novo design) | Already deferred pre-emptively (see below) — full generative modeling scope | Not part of any near-term plan |

### Features considered and deliberately deferred entirely
- **Multi-parameter optimization (Target Product Profile scoring)** — generalization of the tradeoff radar, folded into that core feature rather than built separately
- **Generative "suggest an improved analog" (de novo design)** — StarDrop's Nova module equivalent; a v2+ stretch goal at earliest, well beyond the novelty-feature track above
- **Real-time team collaboration** — enterprise/multi-user feature, not relevant to single-user v1 scope

---

## Module 13: Auth & Persistence
`STATUS: DRAFT — first pass, scoped 2026-08-21`
`LAUNCH SCOPE: Split` — see per-component tags below. Not in the review; added because MARS has no way to save molecules or reports without it. Builds directly on Module 8's stub accounts rather than starting fresh — Module 8 already establishes `user_id` and the account-gating boundary (batch upload requires an account, single prediction doesn't).

### Session strategy
**Server-side sessions in Redis, not JWT.** Redis is already deployed for caching (Module 10), and the backend runs as a persistent Render service rather than serverless/edge, so a per-request session lookup adds no meaningful latency. Accounts exist specifically to gate the abuse-prone batch endpoint (Module 8), which makes instant revocation of a compromised or abusive account more important than usual — JWTs make that hard without reinventing a server-side blocklist, which just becomes this anyway. Session key: `session:{token} → user_id`, sliding 7-day TTL refreshed on activity.

### Auth flow
`LAUNCH SCOPE: MVP`
- **Registration/login:** email + password, bcrypt/argon2 hashed, on top of Module 8's existing stub
- **Password reset:** email-based, MVP scope (confirmed 2026-08-21). Uses Resend (free tier, 3,000 emails/mo — added to Module 10's infra table) for the reset-link email. Standard flow: request reset → time-limited signed token emailed → new password form
- **No OAuth/SSO/MFA** in v1 — explicitly out of scope, consistent with Module 8's "lightweight stub" framing

### Database schema (Postgres)
`LAUNCH SCOPE: MVP` for all tables below unless noted.

| Table | Key columns | Notes |
|---|---|---|
| `users` | `id` (uuid), `email` (unique), `password_hash`, `created_at`, `last_login_at` | Extends Module 8's stub |
| `saved_molecules` | `id`, `user_id` (FK), `smiles` (standardized), `label` (optional name), `notes` (text), `tags` (text[]), `predictions_snapshot` (jsonb), `model_version`, `created_at`, `updated_at` | `predictions_snapshot` freezes predictions + model version at save time rather than live-refreshing — avoids results silently changing under a saved item; a "re-run against latest model" action is explicit, not automatic (Post-MVP, see below) |
| `saved_reports` | `id`, `user_id` (FK), `type` (single/batch), `source_batch_job_id` (nullable FK → `batch_jobs`), `molecule_ids` (FK array → `saved_molecules`), `notes`, `tags` (text[]), `created_at` | Covers both single-molecule and full batch report saves per your scope call |
| `batch_jobs` | `id`, `user_id` (FK, required — matches Module 8's account-gating), `status`, `molecule_count`, `r2_result_path`, `created_at`, `completed_at` | Gives job history now that accounts exist; ties directly into Module 8's existing Celery/RQ job queue rather than adding a new one |

**Tagging is deliberately flat** — a `text[]` column on `saved_molecules`/`saved_reports`, not a separate tag table with its own taxonomy/color management. Matches "basic tagging/notes" scope; a fuller tag system is Post-MVP if it turns out to matter.

### Retention — how this interacts with Module 8
`LAUNCH SCOPE: MVP`
**Indefinite, until the user deletes it** — not the 48h/24h defaults Module 8 set for anonymous/unsaved data. The point of a "save" action is to create an expectation of persistence; a candidate-molecule library that quietly expired would undermine both the feature and the confidentiality posture already stated in Module 8. Account deletion cascades to delete all saved data — that's the actual privacy lever, not a TTL. This needs to be stated explicitly since it's a deliberate exception to Module 8's default no-retention policy, not an oversight.

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
