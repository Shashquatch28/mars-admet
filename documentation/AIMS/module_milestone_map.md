# module_milestone_map.md

_Authoritative Module ↔ Milestone navigation map. Derived directly from
`mars-blueprint_v4.md` Module 14 (build order + milestone table) cross-checked
against every module's own `LAUNCH SCOPE` line, plus current repo state as of
2026-09-16. Re-verify against the blueprint if it is edited; do not let this
drift silently._

## Mapping table

| Module | Name | Milestone(s) | What's implemented in each | Status |
|---|---|---|---|---|
| 1 | Data | **M1** | Acquisition (14 TDC datasets + hERG dual-acquire), standardization, tiered dedup, scaffold split (adopted-benchmark ×12 + self-generated ×2: hERG_Karim, PPB-human), 5-seed CV split, calibration split, DILIst augmentation, licensing audit. *(PPB all-species pooled ablation is data-ready but execution deferred until M2's training cost is confirmed — a within-Module-1 deferral, not a milestone slip.)* | ✅ COMPLETE (2026-08-30) |
| 2 | Endpoint Selection | **M1** (dataset choice) + **M2** (cluster/task-type metadata consumed by Module 4) | Not a build task — a spec. Realized as `contracts/mars_contracts/endpoints.py` (`Endpoint` enum + `ENDPOINT_METADATA`: task_type/category/cluster for all 14). No explicit milestone row names Module 2 in the blueprint's own table (see inconsistency #3 below) — milestone ownership here is inferred, not stated. | ✅ COMPLETE (spec fixed; consumed by M1 + M2) |
| 3 | Featurization | **M1** | Stages 1-5 (standardize, graph w/ explicit chirality, Morgan r2/2048 useChirality=True, 217 RDKit descriptors + SHA drift guard, ETKDGv3+MMFF94 conformers), batched `featurize_batch`, on-disk `FeatureCache`. | ✅ COMPLETE (2026-08-30) |
| 4 | Models | **M2** | XGBoost baseline: **production sweep COMPLETE 2026-09-17** — 70/70 runs (14 endpoints × 5 seeds), real artifacts promoted for all 14. Single-task GNN fine-tune / multi-task KERMT clusters: **not started** — KERMT pre-flight (checkpoint identity, CPU-inference latency, 16GB smoke-finetune) incomplete; this is the entire remaining Module 4 scope. | 🟡 PARTIAL — baseline complete for all 14 endpoints, GNN/KERMT entirely unbuilt |
| 5 | Uncertainty & Applicability Domain | **M2** (CORE) | Basic 5-seed ensembling: **now run for real** — all 14 endpoints have 5 real promoted seeds each, ensembled at inference time by `ml/serve/predictor.py`. k-NN AD index (`ADIndex`/Tanimoto) built from real training data for all 14. Probability calibration: Platt fit on real calibration-split predictions for all 9 classification endpoints; TemperatureScaler for GNN still interface-only (no real KERMT logits exist). DEFERRED conformal prediction (Post-MVP) has **no milestone slot at all** in the current 6-row plan (see inconsistency #4). | 🟢 CORE COMPLETE for the XGBoost baseline (all 14 endpoints); GNN-side calibration still pending KERMT |
| 6 | Explainability | **M4** | Not started. Post-MVP by design; ships with M4 per the milestone table. | ⬜ NOT STARTED |
| 7 | 3D Rendering | **M4** (viewer) — data dependency (Module 3 Stage 5 conformers) already satisfied in **M1** | Conformer generation done (M1). Viewer component (3Dmol.js, both tracks) not started. | 🟡 PARTIAL — data ready, viewer not built |
| 8 | API / Serving | **M0** (contracts + stub) + **M3** (real build) | M0: contracts + FastAPI skeleton + stub `/predict`. M3: real `ml/serve/` model registry (1/14 endpoints — `hia_absorption` — actually trained and promoted; rest honestly fall back to stub via per-endpoint `model_id`), `/compare`, `/batch/predict` (CSV + SDF, interactive + async tiers) + SSE progress + `/batch/results`, `/molecule/{id}/3d` (real ETKDG+MMFF94 conformers, reusing M1's Module 3 Stage 5), Redis caching (48h) + per-IP rate limiting (fail-open), real Module 3 Stage 1 SMILES validation (422) when the ml stack is present. `/molecule/{id}/explain` remains M4/Post-MVP (Module 6 dependency). | 🟢 LOCALLY/CONTAINER COMPLETE for everything CPU-only and blueprint-required — container-verified against real Postgres/Redis/rdkit |
| 9 | Frontend / UI | **M4** | `package.json` + `src/types/contracts.ts` only — no Vite entry, not runnable. | ⬜ NOT STARTED |
| 10 | Infra / Deployment | **M0** (skeleton) + **M3** (real deploy) | M0: `docker-compose.yml` (postgres+redis+minio+api, valid), CI (`ruff`+`pytest`+image build+`/predict` smoke), `.env.example` fully scaffolded for Cloud Run/Neon/Upstash/R2/Resend. M3: actual Cloud Run/Neon/Upstash/R2 deployment, Sentry/UptimeRobot monitoring — **not started**, and per the M3 execution rules, real cloud deploy needs explicit user approval before it happens (no paid-service surprise). | 🟡 PARTIAL — local skeleton done, cloud deploy is M3's open task |
| 11 | Evaluation & Benchmarking | **M2** (§1-5 MVP infra, built ahead of its nominal slot) + **M5** (§6 full ablation matrix + §5.5 robustness check + final reporting) | `ml/eval/metrics.py`, `evaluate.py`, `leakage_audit.py` (10 checks), `tdc_comparison.py` all built and tested during M2 Run 2b — i.e. Module 11's MVP infra shipped *inside* M2, not M5. What's still M5-only: actually running the full ablation matrix (14 endpoints × {baseline, single-task, multi-task} × 5 seeds × 6 axes), significance testing, and the final baseline-comparison tables — impossible before Module 4's real runs exist. | 🟡 PARTIAL — infra ahead of schedule, execution blocked on Module 4 |
| 12 | Feature Catalog | Not milestone-owned itself — **N/A** by blueprint's own declaration; each row's *novelty* track is explicitly slotted into **M4**; CORE rows are implemented piecemeal by whichever milestone owns the underlying capability (e.g. AD flag → M2/Module 5; prediction panel → M4/Module 9; approved-drug reference comparison → cheap post-hoc batch job, earliest at M2 once real models exist) | This is a spec/catalog document, not a build target — confirmed explicitly in the blueprint's own Module 12 text ("no ownership table needed since there's only one owner"). | N/A (spec; individual rows partially realized via other modules) |
| 13 | Auth & Persistence | **M3** | `.env.example` has session/Turnstile/Resend vars scaffolded; `API_ROUTES.md` documents the auth-stub request/response shapes. No DB schema, no session code, no Postgres tables exist yet. | ⬜ NOT STARTED (contract-level stub only) |
| 14 | Work Plan & Milestones | All (**M0-M5**) | This is the plan itself — the source of this table. Actively maintained (this file + `next_steps.md`/`decisions.md`). | ✅ COMPLETE / living |

## Milestone summary

| Milestone | Name | Target dates | Modules involved | Status |
|---|---|---|---|---|
| M0 | Contracts & Scaffolding | Aug 25–26 | 8 (partial), 10 (partial), 13 (contract-stub only), 11 (W&B setup) | ✅ COMPLETE |
| M1 | Data & Featurization | Aug 27–Sep 2 | 1, 3 (+ 2 as consumed spec) | ✅ COMPLETE (2026-08-30) |
| M2 | Modeling | Sep 3–13 | 4, 5 (+ 11 infra spillover, + 2 as consumed spec) | 🟡 IN PROGRESS — **XGBoost baseline sweep COMPLETE (70/70, 2026-09-17)**, all 14 endpoints have real promoted artifacts; **KERMT pre-flight still not done** (single-task/multi-task GNN entirely unbuilt — that's the remaining M2 scope). 4 days past its target end date as of 2026-09-17. |
| M3 | Serving & Infra | Sep 14–19 | 8, 13, 10 | 🟢 LOCALLY/CONTAINER COMPLETE (2026-09-17) — real serving (1/14 endpoints, `hia_absorption`, honestly labeled via `model_id`), auth/persistence, batch, caching/rate-limiting, health checks all implemented + tested + container-verified. Real Cloud Run/Cloud Tasks deployment intentionally not started (needs GCP credentials + explicit approval — see `decisions.md`). |
| M4 | Frontend, Explainability & Novelty | Sep 20–26 | 9, 7, 6, 12 (novelty track) | ⬜ NOT STARTED |
| M5 | Evaluation, Polish, Launch | Sep 27–30 | 11 (full ablation + reporting) | ⬜ NOT STARTED |

## Answers

1. **14 modules** in the blueprint (1–14, including Module 13 added post-launch-review and Module 14 the planning module itself).
2. **6 milestone rows exist in the table (M0–M5)**, but Module 14's own prose says "**Five** milestones, sequential" — a direct textual inconsistency (see below). Treating M0 as a real, already-completed milestone (which it is, per `context.md`), the working plan has 6 stages.
3. **Fully complete:** Modules 1, 2, 3, 14.
4. **Partially complete:** Modules 4, 5, 7, 8, 10, 11, 12.
5. **Not started:** Modules 6, 9, 13.
6. **Modules spanning multiple milestones:** 2 (M1+M2, spec consumption), 8 (M0+M3), 10 (M0+M3), 11 (M2 infra + M5 execution), 7 (data dep in M1, viewer in M4), 12 (cross-cutting by design — M2/M3/M4 depending on row).
7. **Inconsistencies found (reported, not silently resolved):**
   - **Blueprint text says "Five milestones, sequential" but the table that immediately follows lists six rows (M0–M5).** Module 14, "Milestones — targeting Sep 30, 2026" section. Not resolved here — flagged for the maintainer to fix the prose or the table.
   - **Module 2 (Endpoint Selection) has no explicit milestone row** in Module 14's table (unlike Module 12, which explicitly states it needs no ownership table). Its M1/M2 mapping above is inferred from where its outputs (dataset list, cluster metadata) are actually consumed, not stated by the blueprint.
   - **Module 5's DEFERRED item (conformal prediction) has no milestone slot anywhere** in the 6-row Sep-30 plan — it is Post-MVP, but that means it sits outside the entire dated roadmap, not just "later, in M5."
   - **Stale AIMS note (not a blueprint problem, a doc-drift problem):** `decisions.md`'s 2026-08-30 "No paid compute" entry says the serving hosting stack "still names Render Starter (~$7/mo)... NOT changed — M3 scope, flagged to maintainer." The current `mars-blueprint_v4.md` Module 10 **already fully describes Cloud Run**, with no Render mention anywhere in that module. This AIMS note is stale and should not be read as a live blocker — corrected inline in `decisions.md` today.
   - **Schedule risk (not a mapping inconsistency, but load-bearing context):** today is 2026-09-16 — 3 days past M2's Sep 13 target end and 2 days into M3's Sep 14-19 window — with M2's actual production runs (70 XGBoost + KERMT single/multi-task) still at zero. The blueprint itself flags M2 as "the single highest-risk milestone for slipping past its dates." The Sep 30 full-scope target is already under pressure independent of any M3 work.
