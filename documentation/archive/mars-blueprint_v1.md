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

---

## Module 1: Data
`STATUS: LOCKED`

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

**Pipeline stages, in order:**

1. **Standardization** (RDKit) — canonicalize, strip salts/counterions, normalize tautomers/charge states, reject invalid SMILES with a clear error
2. **Molecular graph representation** — atom/bond-level features feeding the shared pretrained backbone (Module 4)
3. **ECFP/Morgan fingerprints** — radius-2, 2048-bit, feeding classical ML baselines and chemical-space similarity search
4. **RDKit 2D physicochemical descriptors** (~200: MolWt, TPSA, logP, HBD/HBA, rotatable bonds, etc.) — auxiliary model input + directly surfaced in UI
5. **3D conformer generation** — ETKDG embedding + MMFF94 optimization, single lowest-energy conformer (default; revisit only if a future feature needs an ensemble), cached per molecule rather than regenerated per request

**Critical non-negotiable requirement:** the entire pipeline (stages 1-4, and 5 where relevant) must run efficiently across a **batch of molecules**, not just one at a time — standardization and featurization steps should be parallelized/vectorized over the batch. This is a real, primary workflow (see Module 12: batch library triage is one of the most common real-world use cases for this class of tool), not an edge case, so single-molecule latency cannot be the only design target.

## Module 4: Models
`STATUS: PROVISIONAL — architecture direction set, open to revision if further evidence changes clustering/backbone choice`

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

**Single-task (standalone fine-tune of pretrained backbone):**

| Endpoint | Rationale |
|---|---|
| DILI | *Original rationale (475 compounds): too small and mechanistically distinct to safely cluster.* **Re-evaluation flagged:** with DILIst augmentation (Module 1 §6, Module 2), DILI's training pool grows to ~1,303 compounds — crossing into range where joint training with the Toxicity cluster (hERG/AMES) may now be worth empirically testing per the KERMT evidence (MT benefit scales with data size for correlated tasks). Decision should be re-tested empirically once the augmented dataset is in hand, not assumed from the original 475-compound justification. |

**Mandatory baselines per endpoint, empirical winner selected on held-out scaffold-split test set:**
- Classical ML: XGBoost/Random Forest on ECFP fingerprints
- Single-task fine-tune of the same pretrained backbone

**Evaluation discipline:** scaffold splits (not random) throughout; report against published TDC leaderboard numbers where available for credibility.

## Module 5: Uncertainty & Applicability Domain
`STATUS: LOCKED`

**Evidence base:** A 2024 study (Li et al., J. Chem. Inf. Model.) introducing conformalized fusion regression (CFR) — combining a GNN with joint mean-quantile regression loss and ensemble-based conformal prediction — found it outperforms existing uncertainty quantification methods across ADMET tasks, and separately noted that most ADMET models are applied single-task, failing to leverage shared biochemical information across correlated properties (validating Module 4's multi-task clustering). A 2026 industrial UQ study (Novartis) validated k-NN distance (5-NN) to the training set in feature space as an applicability domain measure, finding degraded reliability for compounds further from the training set.

### CORE — basic ensembling confidence bands (ships with MVP, zero extra training cost)
Reuses the 5 seeds already trained per endpoint for cross-validation (Module 1 §4 / Module 11 §2) as a natural ensemble:
- Regression: mean ± std across the 5 ensemble predictions
- Classification: mean predicted probability ± std (or predictive entropy) across the ensemble
- No new training infrastructure required — direct byproduct of the already-locked CV protocol

### DEFERRED — conformal prediction + applicability domain (novelty track, per Module 12)
- **Conformal prediction:** ensemble-based conformal prediction calibrated on a held-out calibration split (carved from train_val, distinct from training and the fixed TDC test set), following the CFR approach — statistically valid coverage guarantees rather than an empirical spread
- **Applicability domain:** k-NN distance (5-NN) in fingerprint or learned-embedding space to the training set, flagging query molecules genuinely outside the model's training distribution
- Left as design sketches only — full specification deferred until this track is actually tackled, consistent with Module 12's build philosophy (novelty features must not block the core MVP)

## Module 6: Explainability
`STATUS: LOCKED`

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
An "explain this prediction" action automatically dims everything except the substructure Module 6's Integrated Gradients attribution flagged as important for a chosen endpoint — turning the 2D explainability heatmap into a spatial 3D view of *why* a toxicophore matters (relevant since liabilities like hERG binding are genuinely about 3D shape/pocket fit, not just 2D connectivity). This is a genuine differentiator with no direct competitor equivalent, and a natural byproduct of Module 6's already-locked attribution output rather than new scope.

## Module 8: API / Serving
`STATUS: LOCKED`

**API style:** REST, with Server-Sent Events (SSE) specifically for batch job progress instead of polling. Chosen over GraphQL because our data model is fixed and well-known (14 endpoints, defined schema per molecule) rather than deeply relational with many optional query shapes — the scenario GraphQL is built for. REST also pairs naturally with the Redis caching already locked below, and batch file upload needs a REST-style multipart endpoint regardless. gRPC was ruled out (poor fit for a browser-facing API without a proxy layer).

### Core endpoints

| Endpoint | Purpose |
|---|---|
| `POST /predict` | Single molecule — SMILES in, all 14 endpoint predictions + basic uncertainty (Module 5 core) out |
| `POST /batch/predict` | Batch upload (CSV/SDF); returns immediately if ≤1,000 molecules (interactive tier, Module 12), else returns a `job_id` |
| `GET /batch/progress/{job_id}` (SSE) | Real-time push of batch job progress — replaces polling |
| `GET /batch/results/{job_id}` | Retrieve results once ready |
| `GET /molecule/{id}/3d` | Conformer data for the 3D viewer (Module 7) — computed lazily |
| `GET /molecule/{id}/explain?endpoint=X` | Explainability attribution for a specific endpoint (Module 6) — computed lazily |
| `POST /compare` | Comparison mode, 2-3 molecules |
| `GET /molecule/{id}/report` | PDF report export |

### Key design decision: lazy computation for the expensive stuff
`/predict` returns only tabular predictions + basic ensembling confidence bands — stays fast, matches the Module 12 core/novelty split. **3D conformers and explainability attribution are computed on-demand**, only when the user opens that specific view, keeping the default path cheap.

### Model serving logic
Module 4's multi-task clusters (Metabolism, Absorption/Distribution, Toxicity) plus standalone DILI model mean a single forward pass through a cluster model yields multiple endpoint predictions at once. The API layer maintains a **routing table** (endpoint → serving model/cluster, plus which variant won empirically per Module 11's ablation) so overlapping-cluster requests trigger one inference call, not several.

### Caching
Redis cache keyed on (standardized SMILES + requested endpoint set) for `/predict` results, **and** on lazily-computed 3D conformers and explainability attributions once generated — avoids recomputation on repeat views, not just repeat predictions.

### Batch handling
Matches Module 12's two-tier design: ≤1,000 molecules interactive (target <10s), >1,000 routed to the Celery/RQ job queue with SSE progress.

### Versioning in responses
Every response includes which model version served the prediction — extends Module 1's data-versioning discipline into serving for reproducibility.

## Module 9: Frontend / UI
`STATUS: LOCKED`

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
1. **Prediction panel:** 5 ADMET-category sections, responsive card grid, Toxicity prioritized (larger cards, rendered first)
2. **Confidence intervals:** horizontal range bar per card — teal fill for interval, cyan tick for point estimate, exact numeric range in Plex Mono
3. **Explainability color scale:** bidirectional — risk-red gradient (danger-increasing substructures) vs. teal-cyan gradient (danger-decreasing), shared neutral "grey-out" mechanism with Module 7; draggable magnitude threshold legend
4. **Batch upload:** full state set — idle/drag-over/uploading/per-row validation (non-blocking per-molecule errors)/complete summary
5. **Toast/notification system:** top-right stack, reuses the existing left-border-accent grammar (cyan=success, risk=error) already defined for table error rows
6. **Comparison mode:** 2-3 dense columns mirroring single-molecule cards, per-endpoint cyan-tint "winner" highlighting
7. **Radar chart:** low-opacity teal "ideal zone" polygon vs. solid cyan actual-trace, weight sliders positioned below for adjacent cause/effect
8. **Ultra-wide handling:** panel content max-width 1600px centered beyond 1920px; sidebar/viewer stay full-bleed
9. **Motion tiering:** full scan-line sweep reserved for ≥50% endpoint recompute; smaller in-card shimmer for partial/live-edit recomputes — keeps the signature element meaningful rather than firing on every keystroke
10. **Structure editor constraint (documented, not solved):** Ketcher/JSME contained in its own bordered panel, signals "specialized instrument" rather than attempting full re-skin of third-party canvas UI

### Technical stack
3Dmol.js via `molecule-3d-for-react` (Mol* flagged as future upgrade path if protein targets are added later); Radix UI primitives for accessible custom sliders/tabs/tooltips; Recharts for standard charts, hand-rolled SVG for the scan-line/trace visuals; IBM Carbon patterns referenced for data-table density and dark-theme spacing.

**Deliverables:** `style-guide.html` (live, real-CSS reference) + this written blueprint entry as the build source of truth.

## Module 10: Infra / Deployment
`STATUS: LOCKED`

**Direction:** managed hosting stack (chosen over self-hosted Hetzner+Coolify for lower setup/maintenance time, at modest extra cost) — verified against current 2026 pricing rather than outdated free-tier assumptions (Railway and Fly.io both removed free tiers in 2023-2024).

### Hosting stack

| Component | Choice | Why |
|---|---|---|
| Backend (FastAPI + Celery worker) | Render, Starter tier (~$7/mo/service) | Avoids free-tier cold starts (30-50s wake penalty) that would hurt the demo experience; native background-worker service type fits Module 8's async batch design directly |
| Database (Postgres) | Neon or Supabase (free tier) | Generous free tiers, serverless Postgres, avoids Render's separate DB pricing |
| Cache (Redis) | Upstash (free tier) | Serverless, request-based — fits the Module 8 caching pattern without paying for an always-on instance |
| Frontend | Vercel (free tier) | Best-in-class React hosting, decoupled from the stateful backend |
| Object storage (model weights, batch uploads, cached conformers) | Cloudflare R2 | S3-compatible, no egress fees — matters for batch upload/download bandwidth |
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

**1. Metrics per task type**
- Regression: MAE (matches TDC convention)
- Classification: AUROC + AUPRC — AUPRC specifically for imbalanced endpoints (DILI, hERG, any endpoint with skewed positive/negative ratio)

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

**7. Baseline comparison table format**
One table per endpoint: rows = {XGBoost baseline, single-task fine-tune, multi-task cluster, verified TDC leaderboard best}, columns = {metric, mean ± std, significance vs. our best}.

## Module 12: Feature Catalog
`STATUS: LOCKED`

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
| Basic uncertainty display | Confidence bands from model ensembling — standard technique (not the more elaborate conformal-prediction/applicability-domain version, which is noted below) |
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
| **Applicability domain / conformal prediction uncertainty** (upgrade beyond basic ensembling) | Conformal prediction is a known method but nontrivial to implement correctly and validate; not required for a functional product | Basic ensembling confidence bands (core feature above) are sufficient for v1 |
| **Chemical space map** (UMAP/t-SNE embedding of analogs, live property coloring) | Requires curating/hosting a reference compound library and tuning an embedding that's actually useful, not just decorative | Ship without it; batch triage grid already covers "explore many molecules at once" |
| **Matched molecular pair (MMP) suggestions** | The single biggest scope item: requires building an open MMP database from public bioactivity data (ChEMBL-derived) plus a substitution-effect algorithm — this is closer to a research project than a feature | Ship without it initially; this is the strongest long-term differentiation/publication candidate, but should never be a launch blocker |
| Generative "suggest an improved analog" (de novo design) | Already deferred pre-emptively (see below) — full generative modeling scope | Not part of any near-term plan |

### Features considered and deliberately deferred entirely
- **Multi-parameter optimization (Target Product Profile scoring)** — generalization of the tradeoff radar, folded into that core feature rather than built separately
- **Generative "suggest an improved analog" (de novo design)** — StarDrop's Nova module equivalent; a v2+ stretch goal at earliest, well beyond the novelty-feature track above
- **Real-time team collaboration** — enterprise/multi-user feature, not relevant to single-user v1 scope
