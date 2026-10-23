# MARS ship checklist

Written 2026-10-19. **Definition of complete: the Tier 0 MVP is shipped** (XGBoost-served
workstation, KERMT Tier 0 written up honestly, deployed, accessible, launched).
Everything under "Beyond the MVP" moves to `FUTURE_SCOPE.md` when the MVP ships, the same
way Tier 1/2 did on 2026-10-07 and was revisited on 2026-10-14. That cut is the maintainer's
call; if the full blueprint is the target, "Beyond the MVP" is part of the list.

Tick top to bottom. Tags: `[here]` doable on this machine, `[you]` needs your decision or
approval, `[lab]` needs the GPU workstation.

## A. Quick wins and verification (do first, about a day)

- [x] A1 `[here]` Start Docker; smoke-test the live stack. POST one SMILES to `localhost:8000/predict` and `localhost:5173/api/predict`; `model_version` must match (`v0.2.0-dev`). This also runs the 26 Postgres/Redis tests that skip locally.
- [x] A2 `[here]` Confirm the `ml/tests` run finished green (started 2026-10-19; HANDOFF last recorded 400 passed, 15 skipped on an older tree).
- [x] A3 `[here]` Batch grid `▲N` / `—N` row flags are explained only by `title=` (`frontend/src/workspaces/batch/BatchGrid.tsx:225,230`). Add visible text or a legend (AGENTS.md never-do #8).
- [x] A4 `[here]` Refresh HANDOFF §1 gate table: 202 frontend tests, 6 lint warnings, 63 API/contract passed.
- [x] A5 `[here]` Fix the stale contract text: "probability" at `prediction.py:25`, "cluster" in `endpoints.py`. Change the frontend mirror and the drift test in the same commit.
- [ ] A6 `[you]` Housekeeping, needs your OK to delete: local branch `perf/serving-model-cache` (merged in PR #9) and the stale worktree `.claude/worktrees/hopeful-franklin-202401`.
- [x] A7 `[here]` Refresh the project tracker artifact (last as-of 2026-10-18).
  Refreshed 2026-10-19 after the chunks below (same URL, version 24).

## B. Science that must be settled before any public claim

- [ ] B1 `[lab]` Commit and push the `toxicity__cls` seed 2-4 run records and session note (include the crashed seed-4 attempt).
- [ ] B2 `[lab]` Aggregate the 5 seeds; run `tier0_artifacts`; write the Tier-0 results.
- [ ] B3 `[lab]` Write the single-task CYP baseline driver (it does not exist), then run CYP3A4 / CYP2D6 / CYP2C9 on their full original splits.
- [x] B4 `[here]` Pool-matched KERMT vs XGBoost comparison table. **Fallback if B3 is not done:** make no KERMT-vs-XGBoost claim on classification, and say so in the write-up.
  Done for 8 endpoints (5 regression, HIA, Pgp, BBB): `documentation/status/kermt_vs_xgboost_pool_matched.md`, from XGBoost retrained on exactly KERMT's pool (`ml/train/run_pool_matched_xgboost.py`, results in `kermt_pool_matched_xgboost.json`). Classification fallback table without a comparison: `kermt_vs_xgboost_classification.md`. Still no KERMT-vs-XGBoost claim for the CYPs (needs B3), DILI (base vs augmented pool) or toxicity (2 of 5 seeds).
- [ ] B5 `[you]` Decide Tier 1: stays provisional / out of the MVP (your 2026-10-18 statement), so the Tier 1 gates, tuning and arms move to Beyond the MVP.

## C. Make it deployable

- [x] C1 `[here]` Production topology (ADR-025, Q22): API under `/api`, frontend served from the API container (multi-stage Dockerfile), secure cookie. (Verified 2026-10-19 in a container built from this branch's code on the compose image: bundle, client-route fallback, `/api` routes, real predict, direct and queued Batch, `Secure` cookie. The full Dockerfile's pip layer did not finish locally because the download was corrupted on a slow connection, so the CI `build-api-image` job is its first full build.)
- [x] C2 `[here]` Verify the client address the rate limiter sees behind Cloud Run. (Code and tests done; observing it on a deployed service stays with C7.)
- [x] C3 `[here]` Cap concurrent predictions to the container's CPUs (default thread pool is 40; each prediction is single-threaded).
- [x] C4 `[here]` Interactive Batch tier (up to 1,000 rows) still holds one request open with no progress; add progress or lower the threshold.
- [x] C5 `[here]` Decide password reset: build it (API issues a token, no email is sent) or launch without account recovery and say so (ADR-022 item 7).
- [ ] C6 `[you]` Approve the cloud deploy and supply GCP credentials.
- [ ] C7 `[you]` Deploy: Cloud Run, Neon, Upstash, R2. Rebuild the held-out error bands on the deploy machine (`build_error_bands.py`, about 6 min) or regression rows carry no band.
- [x] C8 `[here]` Cloud Tasks batch worker (needs a deployed worker)
  Code done: jobs run as resumable slices through a blob store (Redis or S3/R2) and a queue (local or Cloud Tasks) with a secret-guarded worker endpoint; unit-tested against fakes and, for S3, against local MinIO. Not run against a real Cloud Tasks project; the post-deploy checks are in `api/README.md`..
- [x] C9 `[here]` Sentry and UptimeRobot monitoring. (Sentry is code-complete and tested; both need a real account and the deployed URL, so the setup is the runbook in `documentation/MONITORING.md`.)

## D. Launch quality (M5 minimum)

- [ ] D1 `[you]` Decide the open design questions (non-blocking): Q5, Q8, Q11, Q12, Q16, Q18; confirm Q13, Q20. Q5 removes `per_endpoint_winner` from the contract and retires the one never-do hazard.
- [ ] D2 `[here]` Calibration C1: recalibrate on label-representative data and validate per endpoint (or ship raw scores and say so; C0 is already live).
- [ ] D3 `[here]` Evaluation: ablation matrix (agree a reduced scope; the full 14 x 3 x 5 x 5 is large), significance testing and self-audit.
- [ ] D4 `[here]` TDC leaderboard comparison tables.
- [x] D5 `[here]` Report export (the CSV export is done; a report is a separate item).
  Done as a print-only light report (Save as PDF), frontend ADR-029; no server route. No 2D structure or drug-likeness flags: the service has neither.
- [x] D6 `[here]` WCAG / accessibility pass.
  Done in code and verified in a browser (ADR-030, `ACCESSIBILITY.md`). Not done: a screen-reader test, the Ketcher panel, the Batch grid's keyboard re-test; no axe run. Plan these into D7 (final QA).
- [x] D7 `[here]` Final QA: re-run the AGENTS.md "Never do" audit in a browser at 1440 px, run every screen in `documentation/frontend/LOCAL_TESTING.md`, re-check the stub-served row state (no mixed real+stub response has ever been captured).
  Done 2026-10-19 on the merged `main` as the production topology with real models (HANDOFF 2k): all nine LOCAL_TESTING steps and the report pass; the first mixed real-and-stub response was captured and pinned; the never-do audit holds and is now a source guard; one violation fixed (the palette's enter animation). Not run: the real print dialog and PDF, a screen reader, other browsers, NOT RETURNED against a live service, a 1,200-row queued batch, the full Dockerfile build, and anything deployed.
- [ ] D8 `[you]` Launch.

## D2. Frontend scope decided in ADR-034 (build order, hours are estimates)

- [x] D9 `[here]` `GET /limits` (batch cap, interactive threshold, result retention hours, anon rate) and `blob_store` reading `batch_upload_retention_hours`; UI copy reads it (about 3 h).
  Done 2026-10-22. Checked on a private stack with cap 7,000, threshold 20 and retention 12 h: the sign-in gate and the Batch note showed those numbers, and a queued job's result blob in Redis had a TTL of about 43,200 s (it was 86,400 whatever the setting said). A guard test fails if "50,000", "24 hours" or "100 molecules" is written into runtime copy.
- [x] D10 `[here]` Model family and † in Batch inspector, Compare and the printed report (about 4 h).
  Done 2026-10-22. Checked on a private stack with a real KERMT service: while it was still loading, the six routed endpoints showed `XGBoost †` in the Batch inspector, in every Compare cell (with a sentence under the header counting them) and in the printed report's Model column with a footnote; once it was ready the same six showed `KERMT` with no dagger and no note anywhere. The real print dialog was not driven (the report was read from its DOM).
- [x] D11 `[here]` Status-bar echo of the latest announcement, no timer (about 1 h).
  Done 2026-10-22. Checked live: before a run the bar reads "no request yet"; after a run it echoes "Prediction complete. 14 of 14 endpoints returned, 1 out of domain."; the palette's Copy molecule_id (which closes the palette and had no visible confirmation) now shows "Copied molecule_id". The echo equals the live region's text, is hidden from assistive technology and is not a second live region (a guard test pins that).
- [x] D12 `[here]` Batch coverage table, text only, no outlier flag (about 6 h; needs D10).
  Done 2026-10-22. A "Coverage by endpoint" view beside Rows in Batch. Checked live with a real KERMT service on 8- and 6-molecule batches: while KERMT was loading the six routed endpoints read 7 under "† fell back" and 0 under XGBoost and KERMT, with a note saying why; once ready they read 6 under KERMT, 0 fell back and no note. A failed row was named in the caption and left out of every count; every row reconciled (requested = returned + not returned; the family columns plus stub-served = returned).
- [x] D13 `[here]` Computed molecule properties and structural alerts: `properties` on `PredictionResponse`, Predict panel, report; share the alert matcher with the explainability validation; bump `MODEL_VERSION` (about 12 h).
  Done 2026-10-22. RDKit properties and PAINS/Brenk alerts in `ml/serve/properties.py` and `ml/serve/alerts.py`; `properties` on `PredictionResponse` (contract, TS mirror, drift test); a "Computed properties" panel in the Predict molecule column and a table in the printed report. Cache safety is a `RESPONSE_SHAPE` tag in the cache key, not a `MODEL_VERSION` bump (see ADR-034 note). Checked live: a rhodanine returned PAINS `ene_rhod_A(235)` and two Brenk alerts, the cached repeat kept them, and the panel and the report showed them. Still to do on `feat/explainability`: its `ml/eval/explain_validation.py` should import `serve.alerts.alert_matches` instead of keeping its own copy (same signature).
- [ ] D14 `[you]` Turnstile as a deploy gate: honeypot and register rate limit first, then the widget with the site key from `/limits`; only once the public deploy (C6) is approved (about 4 h).

## E. Polish if time allows (not MVP-blocking)

- [ ] E1 Structure sketcher (Ketcher, ADR-027). Audit never-do #7/#8 and measure the chunk on first integration.
- [x] E2 Hand-offs: Library or Batch to Compare, Batch "Open in Predict", endpoint subset for Batch and Compare.
  Done 2026-10-23 on `feat/handoffs` (ADR-038). Also fixed on the way: `POST /batch/predict` ignored `?endpoints=` and ran all 14 (now `Query()`, tested). Checked live on a private stack with real models. Not done: a saved molecule from a subset run still reads NOT RETURNED in Library (the snapshot does not record the request; needs a contract field). Not run: the queued tier with a subset, a screen reader.
- [ ] E3 JSON export of the saved snapshot; the command palette's placeholder commands become real; Batch multi-select and reopening an earlier job after reload.
- [ ] E4 Decide whether the seed spread stays on classification rows (ADR-024 item 4); decide the 410 on saving expired results.

## Beyond the MVP (blueprint items; move to FUTURE_SCOPE.md at ship, or keep if the full blueprint is the target)

- [ ] F1 Explainability (Module 6)
- [ ] F2 Novelty-track features (Module 12)
- [ ] F3 Tier 1: gates G4, G1, G2, G3; registered tuning protocol; arms at the selected and reference configuration. Needs your tuning numbers first.
- [ ] F4 Tier 2 ordinal run, only if GPU budget remains after Tier 1
- [ ] F5 KERMT serving path (no KERMT code in `ml/serve`; no generation dimension in the registry)
- [ ] F6 Generation switching (ADR-026 parts 2-5), blocked until a second generation exists
- [ ] F7 Recalibration C2 (KERMT temperature scaling, GPU-gated)
- [ ] F8 Conformal prediction (no milestone slot)
- [ ] F9 Tier 1 W&B uploader
