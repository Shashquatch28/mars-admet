# Frontend session handoff

**Written 2026-10-07; §1–§4 updated after Predict went live, and the gates,
repository hazards and stale notes re-audited 2026-10-14.
Branch `milestone/m4-frontend`.**
Everything below was checked against the repository on those dates, not recalled.
Where a claim could not be verified it says so.

This is the file to read first when picking the frontend up in a new session.
It does not restate the design system; it says where the work stands, what is
broken or missing, and what to do next.

---

## 1. Where things stand

The design is **locked** (passes 1–2.1, 2026-10-01). **Predict is live**: with
`VITE_API_BASE=/api` it takes a typed SMILES, Run submits it to `/predict`
through a Vite dev proxy, and the status bar and top bar read the real response
and a real `/health` check. It was exercised in a browser against the real model
path (see §2a). Batch runs against the API too (upload, progress, results; §2b); Library, delete-account and Compare exist (§2c, §2f).

| Gate (run 2026-10-19, branch `fix/ship-quick-wins`, Docker stack up) | Result |
|---|---|
| `npx tsc --noEmit` | clean |
| `npm run lint` | 0 errors, 6 warnings (`app/authSession.tsx`, `batchSession.tsx`, `compareSession.tsx`, `predictSession.tsx`, `savedMarks.tsx`, `uiState.tsx` fast-refresh, accepted) |
| `npm test` | 202 / 202 passed, 17 files |
| `ruff check contracts api ml` | clean |
| `contracts/tests` + `api/tests` (root `.venv`, Postgres/Redis up) | 88 passed, 1 skipped (`rdkit` not installed), 1 failed: `api/tests/test_predict.py::test_predict_returns_all_14_ml_endpoints` sees 15 rows (the rule-based SA row) because this environment has the ml stack; it fails the same way on `main` and expects 14 only where CI has no ml stack. Not caused by this branch. |
| `ml/tests` (**`ml/.venv`**, not the root env) | 708 passed, 21 skipped (10 min 41 s) |
| `npm run build`, `npm audit` | last run 2026-10-07: build succeeds, 0 vulnerabilities; not re-run |

## 2. What exists

| Area | Files | Notes |
|---|---|---|
| Shell | `src/shell/` | AppShell, NavRail, TopBar, StatusBar, CommandPalette. Keys 1–4 switch workspace, ⌘K opens the palette. |
| Predict | `src/workspaces/predict/` | Roster of 15 rows (14 ML + rule-based SA), seven derived row states (incl. NOT REQUESTED, ADR-028), endpoint-subset selector, inspector, AD gauge, keyboard roving, live 3D viewer (placeholder SVG in fixture mode). |
| Batch | `src/workspaces/batch/`, `src/domain/batch.ts`, `src/domain/batchJob.ts`, `src/app/batchSession.tsx` | Live: choose or drop a CSV/SDF, optional SMILES column, Run, progress for queued jobs, rows into the grid. Without an API: 240-molecule deterministic fixture. Virtualized `role="grid"`, raw numeric sort, filters, molecule inspector. |
| Data-viz | `src/components/dataviz/` | `ADGauge`, `IntervalTrack` (both require an explicit `domain`, no default), `NumericInterval`, `ReliabilityTag`. |
| Domain | `src/domain/` | `rowState` (the one trust decision), `reconcile` (full roster every time), `format`, `endpoints`, `fixtures`, `batch`. This is the tested layer. |
| Data | `src/data/` | `client.ts` (predict, conformer, health, auth, batch: `postBatch`, `followBatchProgress`, `fetchBatchResults`) + `useApiHealth`, `useConformer`. |
| Auth | `src/auth/`, `src/app/authSession.tsx`, `src/domain/session.ts` | `Gated` sign-in state, `AccountForm`, session provider (unknown / anonymous / signed in), global 401 handler. ADR-022 phase 1. |
| Tooling | `.eslintrc.cjs`, `vitest.config.ts` | ESLint enforces two AGENTS.md rules in **TS/TSX only**. |
| Backend (this branch) | `ml/serve/rule_based.py`, `contracts/…/prediction.py` | API now serves the SA score (ADR-019) and `ad_threshold` per prediction (ADR-020). |

### 2a. Predict going live — what was done and learned

- **State** lives above the router (`src/app/predictSession.tsx`): the SMILES
  draft, the last result (response + measured latency + the string submitted),
  running/error. Run is a mutation, not a query — the server owns the 48 h cache
  and reports it via `cache_hit`, so the client keeps no second cache.
- **Shell readouts** come from that result: `served_at`, `CACHE HIT/MISS`, measured
  ms, and `model_version`. Absent until a request exists (`no request yet`). The
  fabricated "computed now · cached for 48 h" and "rate 7/60 per min" are gone —
  the service sends neither (no rate-limit headers).
- **API badge** (`src/data/useApiHealth.ts`): `No API` (unset) · `Checking` ·
  `Ready` · `Unreachable`, polled every 30 s against `/health` (liveness only).
- **CORS**: confirmed in a browser that `credentials: "include"` against `*` is
  rejected. Dev goes through a same-origin proxy (`/api` → `localhost:8000`,
  override with `MARS_API_PROXY_TARGET`). The API now also allows an explicit
  origin list with credentials (`CORS_ALLOW_ORIGINS`, default the Vite dev
  origin; approved and done 2026-10-07, `api/tests/test_cors.py`), so
  `credentials: "include"` is back and works cross-origin too. Cookies are
  `SameSite=Lax`: SPA and API must be same-site; a fully cross-site deploy would
  also need `SameSite=None; Secure` (not done).
- **Also fabricated in live mode, now fixed**: the Structure panel drew fixed
  geometry and a fixed "−42.8 kcal/mol" for any molecule. It now renders the real
  `/molecule/{id}/3d` conformer with 3Dmol (see "3D viewer" below); the Identity panel's "Rewritten by standardizer" is
  derived rather than constant; a live session with nothing run shows quiet
  placeholder rows and "No request yet", not NOT RETURNED rows and not the
  "design prototype" strip (nothing on screen is illustrative).
- **3D viewer** (`StructureViewer`, `useConformer`, `domain/conformer.ts`): live mode
  fetches `/molecule/{id}/3d` and draws the SDF with 3Dmol (lazy-loaded). States are
  derived in one pure function: idle / loading / ready / unavailable (404, a normal
  state: the id expires with the prediction cache) / unsupported (501) / error.
  Atoms use the `--viewer-*` element tokens, nothing animates. The caption is the
  service's own energy (`ETKDG · MMFF94 · 60.0 kcal/mol` for celecoxib; the old
  literal said −42.8). **Hero** = ball-and-stick, heavy atoms; **Analysis** = all
  atoms as sticks with hydrogens visible, no labels (the maintainer's choice,
  2026-10-08: Hero hides hydrogens so the modes really differ, and atom numbering
  would be a claim nothing cites yet — labels can return with Q11). The 404/501
  *panel states* are verified by tests, not in a browser (no way to force them
  without editing Redis).
- **Real responses** are saved in `src/domain/real-responses/` (README there has
  provenance) and tested in `src/domain/realResponses.test.ts`.

**What the real responses showed that our fixtures hid**

1. `unit` is `null` on all 14 model rows. The 1-dp rule for `% bound` was keyed on
   `unit === "% bound"` and silently didn't apply; now `decimalPlaces(endpoint)`.
2. `smiles_input` comes back already standardized, so it can't tell you whether
   the input was rewritten. The client keeps what was submitted.
3. A cache hit returns the **original** `served_at`, so the status-bar timestamp
   is "computed at", not "requested at".
4. Celecoxib is out of domain on 5 of 14 endpoints; the design fixture had 2.
5. First `/predict` after an API restart took ~20 s (model load). The UI shows
   Running… throughout; there is no cold-start affordance.
6. Top-level `model_version` was `"stub-v0"` even with every row served by a real
   model. **Fixed and verified 2026-10-07** in `prediction_service._route_to_models`
   (it now stamps `settings.model_version` once a real model has served a row;
   per-row truth stays in `model_id`).
7. A fresh `docker compose build api` failed at import: `sqlalchemy>=2.0` without
   `[asyncio]` (no `greenlet`). **Fixed and verified 2026-10-07**: the same one-line
   change as `df4baa5` on `fix/ci-sqlalchemy-asyncio`, applied to
   `api/requirements.txt` (identical, so merging that branch is clean), image
   rebuilt, container healthy, all 14 endpoints served by the real model plus the SA row.
   An image built before `rule_based.py` existed serves **stub-v0 for every endpoint
   and no SA row, with nothing in the logs**. It now logs a warning at startup
   (`app.main` reads `prediction_service.ml_import_error`).
8. **The prediction cache key did not change when the response did.** The key is
   `predict_cache:{smiles}:{endpoints}:{MODEL_VERSION}` and `MODEL_VERSION` was a
   static `v0.1.0-dev`, so stub, SA-less responses survived the rebuild for 48 h.
   Bumped to `v0.2.0-dev` (`config.py`, `.env.example`). **Bump it whenever the
   response shape or routing changes.** A better fix (derive the tag from the
   promoted-artifact set so it cannot be forgotten) is not done.

### 2b. Batch against the API — what was done and what was not checked

- **Flow** (`src/app/batchSession.tsx`, held above the router like Predict so switching
  workspace keeps the file and a running job): `POST /batch/predict` (multipart). Up to
  1,000 molecules come back in that response (`job_id` null). Larger files are queued: the
  client follows `GET /batch/progress/{job_id}` with fetch streaming (not `EventSource`, so a
  401/404 goes through the same error handling), then fetches `GET /batch/results/{job_id}`.
- **Pure parts** (`src/domain/batchJob.ts`, tested): file validation (.csv/.sdf, non-empty),
  SSE framing across chunk boundaries, percent, status words, and what the final event means
  (`unknown` = no record of the job, shown as an error, never as a result).
- **Honesty rules held:** rows go through the same `buildBatch`/`reconcile` as Predict (full
  roster, failed rows kept with their error, no ranking). The bar is determinate and appears
  only once the service has reported a total; nothing animates; limits are written in the
  panel, not in a tooltip. `isSample` is false in live mode (only the fixture is illustrative).
- **Checked:** 23 new vitest tests (136 total; client tests run the real `client.ts` against a
  stubbed `fetch`). In a browser (1440 px) against a **stand-in API that serves only the
  /batch routes and /auth/me, built on a real captured `/predict` response**: interactive
  tier, queued tier with incremental progress, wrong extension, empty file, a 422 from the
  service, job and file surviving a workspace switch, and a 401 dropping to the sign-in state.
- **Not checked:** the real service from a browser. Docker was not running, so Postgres and
  Redis were unavailable and the real `/batch/*` routes were not exercised end to end from the
  UI; the backend side is covered by its own API tests (skipped without the stack, run in CI).
  Not exercised at all: an SDF upload, a file near the 50,000-molecule cap, a failed server job
  (`status: failed`) and an expired result (410) are covered by unit tests only.

### 2c. Library and delete-account (ADR-022 phase 2) — what was done and what was not checked

- **Library** (`src/workspaces/library/`, `src/domain/library.ts`): lists the account's saved
  molecules and saved reports (`GET /molecules`, `GET /reports`), newest first, with a text
  filter. Every entry is a **frozen snapshot**: the detail column says which `model_version`
  made it and when it was saved, and never calls it a current prediction. A saved molecule shows
  the full roster through `reconcile` (an endpoint the snapshot lacks is a marked row), values in
  the normal value-cell grammar, stub and out-of-domain as a separate mark. A report shows its
  size, failed rows and model versions, read defensively (an unexpected snapshot shape is said to
  be unrecognised, not shown as zero rows). Deleting a saved molecule is an inline
  Delete / Cancel; deleting a saved report uses the modal (INTERACTIONS.md allows it). A 404 on
  delete is treated as already gone; any other failure says nothing was deleted.
- **Delete account** (`src/workspaces/settings/DeleteAccount.tsx`, `src/components/ConfirmDialog.tsx`):
  Settings, signed in. A modal (`role="alertdialog"`, focus into the password field, Tab trapped,
  Esc = Cancel, backdrop click does nothing, focus returns to the opener, no animation) lists what
  is removed, asks for the password, and sends `DELETE /account`. A wrong password (403) or any
  other failure keeps the dialog open and says nothing was deleted. On success the app drops to
  anonymous, the library cache is removed and the Batch file/result is cleared.
- **Contract**: `contracts.ts` now mirrors `SavedMoleculeResponse`, `SavedReportResponse` and
  `DeleteAccountRequest`; `contracts/tests/test_frontend_drift.py` covers them (36 contract tests pass).
- **Checked:** 24 new vitest tests (160 total). In a browser at 1440 px against a **stand-in API**
  (`/auth/me`, `/molecules`, `/reports`, `DELETE` routes and `DELETE /account`, built on real captured
  `/predict` responses): list, filter and its count note, inline delete including a server 500
  (nothing removed, message shown) and a success, the report modal (Cancel, Esc, backdrop click,
  confirm), delete-account with a wrong password then the right one, the return to the sign-in
  state, and Library showing the gate afterwards with no stale rows.
- **Not checked:** the real service (Docker was not running); a screenshot of the dialog (the
  pane timed out, so it was checked through the DOM: role, name, focus, text); large libraries
  (the list is not virtualized); the real cascade of `DELETE /account` (backend API tests cover it
  and run in CI).
- **Saving:** Library fills through Save (§2d).

### 2d. Save to library — what was done and what was not checked

- **Where:** Predict (`Save to library`, inspector footer) saves the molecule on screen; Batch has
  `Save molecule` (the row selected in the inspector) and `Save report` (the whole result, in the
  strip under the upload controls). One control, `src/components/SaveControl.tsx`; pure parts in
  `src/domain/save.ts`. A "single" report from Predict is not offered: a saved molecule is the
  same snapshot.
- **Snapshot-on-save:** the client sends back the response it already holds
  (`POST /molecules/save`, `POST /reports/save`); the service freezes it. The panel says so before
  the user commits: a frozen copy, with the model version, that does not update, and that stub
  values are saved as stub values. A batch report keeps failed rows and records the job id as
  provenance only; `molecule_ids` stays empty (those would be links to separately saved
  molecules, which this flow does not create).
- **States, all in words beside the control:** disabled with the reason (no API, no result yet,
  running, no row selected, a failed row); anonymous gets "Saving needs an account" with a link to
  sign-in and no form; a failure says nothing was saved and keeps what was typed; success becomes
  "Saved to Library" with a link. `src/app/savedMarks.tsx` remembers what was saved this session
  (keyed by molecule id plus `served_at`, or by batch result) so a second click cannot save the
  same thing twice; marks are dropped when the session is not signed in. Typed tags are trimmed and
  de-duplicated ignoring case; blank label and notes are sent as null. No length limits are
  invented: the database columns are unbounded text.
- **Contract:** `contracts.ts` mirrors `SaveMoleculeRequest` and `SaveReportRequest`; the drift
  test covers them (38 contract tests).
- **Checked:** 15 new vitest tests since the Library work (175 total). In a browser at 1440 px
  against a stand-in API (real captured responses): Predict save with a server 500 first (typed
  values kept, "Nothing was saved"), then success; the exact request bodies (label trimmed, tags
  de-duplicated, same payload on retry); Batch report save and selected-molecule save; a failed
  row disables Save with its reason; the new entries appear in Library without a reload; after
  sign-out the control shows the account message and no form.
- **Found while checking:** the control passed a disabled reason even when saving was possible,
  so it always read as disabled. Fixed before commit; no test covers the component's rendering
  (the frontend suite is node-only), so this is covered by the browser run only.
- **Not checked:** the real service (Docker was not running); saving a very large batch
  (the whole result, up to 50,000 rows, is sent as one JSON body: payload size and any server
  limit are unmeasured, and the panel states the row count); the `410` the route table mentions
  for saves of expired results (the current route has no such check, since the client sends the
  results in hand).

### 2e. Real-stack check, 2026-10-18 (Docker, Postgres, Redis, the rebuilt API image)

Run after the stand-in checks above, once Docker was started: `docker compose up -d --build api`,
migrations already at head (`d5be9f4ca6e0`), a private Vite on :5174 against the canonical API on
:8000, a throwaway account created and deleted through the UI.

- **Worked on the real service:** anonymous Predict (15 rows, real XGBoost, `v0.2.0-dev`) and the
  anonymous Save message; create account; Save molecule (row checked in Postgres: label trimmed, tags
  `coxib, Coxib, demo` stored as `{coxib,demo}`, snapshot of 15 predictions); a 5-row Batch (4 out of
  domain, 1 failed row kept); Save report (5 rows, tags `{pilot,real}`) and Save molecule from a
  Batch row; Library list, detail (with the real OUT OF DOMAIN mark) and both deletes (rows gone in
  Postgres); delete-account with a wrong password (403, dialog stays, "Nothing was deleted") then the
  right one. Afterwards `users`, `saved_molecules`, `saved_reports` and `batch_jobs` were all 0, so
  the cascade works.
- **The C0 change is live in the rebuilt image** (`platt_enabled()` is False; the `.dockerignore`
  allowlist builds, and `/app/ml` holds only `serve`, `featurize`, `models`, `eval`, `artifacts`, `data`).
- **Serving speed, fixed later the same day (2026-10-18, ml/serve, measured on the real stack).** The 18 to
  37 s per new molecule was model loading, as profiled. Fix: `ModelRegistry` keeps loaded models, AD indexes
  and calibrators in memory per endpoint, keyed on the files' (mtime, size) and re-checked at most every 5 s
  (a re-promoted artifact is picked up within that window, no restart, no stale model); a molecule is
  featurized once for all 70 models; serving models predict on one thread; the AD query intersects only the
  query's set bits. **Measured** in a private container (same image recipe, `ml/artifacts` bind-mounted,
  empty feature cache, empty Redis db): **21.9 s per new molecule before (6 molecules, 20.3 to 24.0 s) and
  0.18 s median after (13 molecules after the first; 0.14 to 0.34 s, one 0.87 s outlier)**, about 120x. The first request after a container starts still
  pays the one-off load of all 70 models, 12.7 s. The 6 molecules' `/predict` bodies are identical before and
  after (all fields except `served_at`), and a 6 x 14 golden comparison of `predict_endpoints` is
  byte-identical; C0 (raw ensemble) and the contract are untouched. Two things surfaced only inside Docker:
  XGBoost's all-core thread team cost 47 ms per single-row call in an 18-CPU container (1.2 ms with one
  thread), and `stat` on the Windows bind mount costs about 5 ms, which is why the file stamp is re-checked
  on a 5 s window rather than per request.
- **Queued Batch with real models, run:** 1,200 distinct valid SMILES uploaded to `POST /batch/predict`
  (over the 1,000 threshold, so queued), real XGBoost, new feature cache. It finished **done, 1,200 of
  1,200 rows ok, 0 failed, in about 9.5 minutes (0.47 s per row)**, 16,800 model predictions plus 1,200
  rule-based scores, no stubs. Progress and results were read back through the real routes. This is the
  first real-model queued run. The interactive tier (up to 1,000 rows) is now minutes, not hours, but it
  still holds one HTTP request open with no progress.
- **Event loop, fixed (2026-10-18).** `predict_one` used to run synchronously on the event loop in
  `POST /predict` and in both Batch tiers, so the whole API answered nothing else while a molecule was
  predicted. Now `POST /predict` and the Batch loops call it through `asyncio.to_thread` (`POST /compare` is
  a plain `def`, so FastAPI already ran it on a worker thread). Made safe first: `FeatureCache` writes every
  entry via temp file + `os.replace` and serialises the `_config.json` read-modify-write (on Windows a
  concurrent replace raises `PermissionError`, retried and, for content-addressed entries, dropped if the
  file is already there); the registry is built once under a lock. The registry is also **warmed in the
  background at start-up** (`prediction_service.warm_up`, 14 endpoints in about 9 s), so the server accepts
  requests at once and the first prediction no longer pays 12.7 s. **Measured on the real stack:**
  `/health` answered in 7 to 37 ms during that warm-up, 6 to 23 ms (48 samples) through a 300-row
  interactive Batch (62 s, 0.21 s per row), and at worst 29 ms (64 samples) through a queued 1,200-row job,
  which finished in 222 s with all 1,200 rows ok and **every row identical to the pre-threading run** (the
  222 s is not a like-for-like speed-up: 300 of those molecules were already in that container's feature
  cache). Tests: `api/tests/test_predict_off_event_loop.py` (fails if the call goes back on the loop),
  `ml/tests/test_cache_concurrency.py`, and a concurrent-prediction equality test in
  `ml/tests/test_serve_model_cache.py`. Not done: a cap on concurrent predictions (the default thread pool
  allows 40; each prediction is single-threaded, so size it to the container's CPUs before deploying), and
  the interactive tier (up to 1,000 rows) still holds one HTTP request open with no progress.
- **Method note for the next session:** `docker compose up -d --build api` from a worktree bind-mounts that
  worktree's (absent) `ml/artifacts`; build the image from the worktree and run a private, differently named
  container instead (see AGENTS.md shared-environment rules).

### 2f. Compare (ADR-007) — what was done and what was checked

- **Screen** (`src/workspaces/compare/`, `src/domain/compare.ts`, `src/app/compareSession.tsx`): two or
  three SMILES inputs, Run, and one table: rows are the fixed roster in its fixed order, one column per
  molecule plus the unit. Every molecule runs through the same `reconcile()` as Predict, so each has a cell
  on every endpoint and a missing one reads "not returned". Value cells keep the grammar (mono, tabular,
  `--text-primary` in every state; stub hatched); out-of-domain, stub and rule-based are separate marks on
  a 2px cell edge and a tag. Each column header counts its own out-of-domain, stub-served and not-returned
  cells. It says when the molecules were served by different model versions.
- **ADR-007 held in the type and the test:** no winner, rank, highlight, difference column or ordering by
  value; `per_endpoint_winner` is never read (a unit test feeds a response that carries one and asserts the
  comparison is identical). The empty state says why: a higher or lower value is not a better or worse
  molecule.
- **Hand-off:** Predict's **Compare molecule** (enabled once a result exists) puts what the user typed into
  slot 1 and opens Compare. State lives above the router, so slots and the last result survive a workspace
  switch. `/compare` is anonymous, so Compare is never gated. A failure (a 422 names the offending SMILES,
  as the service words it) keeps the inputs and clears the table, never showing a stale result.
- **Checked on the real stack** (Docker, 2026-10-18): Predict to Compare hand-off; 2 molecules in 20 s and
  3 in 33 s; 15 rows x N cells in roster order; every value rendered in one colour; no evaluative word on
  screen; a 422 for `not-a-smiles` with the inputs kept; adding and removing the third slot. 12 new tests
  (187 total), contract drift test covers `CompareRequest` (39 contract tests).
- **Not built:** Library to Compare, Batch to Compare, an endpoint subset for Compare (the request sends none).

### 2g. Held-out-error band (ADR-024) — what was done and what was checked

- **Backend:** `ml/eval/error_band.py`, `ml/train/build_error_bands.py`, `ModelRegistry.load_error_band`, three additive
  `EndpointPrediction` fields (`heldout_error_halfwidth`, `heldout_error_level`, `heldout_error_n`). Level 90%. The band files
  live in `ml/artifacts/<endpoint>/error_band.json`, which is git-ignored: on a new machine run
  `cd ml && PYTHONPATH=. python train/build_error_bands.py` (about 6 minutes) or the regression rows carry no band.
- **Frontend:** `src/domain/errorBand.ts` (tested) and two rows in the Predict inspector for regression endpoints: "Held-out
  error ±X" and a note saying what was measured. Text only, never a bar, never coloured; absent when the service sent none.
  Batch and Compare do not show it.
- **Checked on the real stack** (2026-10-18): `/predict` returns the five bands (solubility 1.677, logP 1.103, Caco-2 0.615,
  PPB 18.07, clearance 51.21) and null on the nine classification rows and the rule-based row; the inspector shows the band on a
  regression row and none on a classification row. Test coverage of the bands: `documentation/status/heldout_error_bands.md`.
- **Note:** predictions cached in Redis before this change have no band until their entry expires or is flushed.

### 2h. Export (CSV) — what was done and what was checked

- **What it is:** a client-side CSV of what is on screen, no API call. Predict's **Export** downloads the current result;
  Batch's **Export results** downloads every row of the run (run order, not the filtered view) and **Export row** the
  selected one. The sample data (no API) and a failed or empty state cannot be exported: the buttons are disabled.
- **Format** (`src/domain/exportCsv.ts`, `src/data/download.ts`): long format, one line per molecule x endpoint, in fixed
  roster order, every roster endpoint present. Columns: `row`, `smiles_input`, `smiles_standardized`, `molecule_id`,
  `endpoint`, `task`, `value`, `unit`, `state`, `seed_spread_low/high`, `heldout_error_halfwidth/level/n`, `knn_distance`,
  `ad_threshold`, `model_id`, `model_version`, `served_at`, `error`. `state` is the screen's own word (ok, out_of_domain,
  stub_served, not_returned, not_requested, rule_based, row_failed), kept apart from `value`. Numbers are full precision.
  A failed Batch row is one `row_failed` line with its error. The rule-based score exports no spread. Text fields that start
  with `= + - @` get a leading apostrophe so a spreadsheet does not read them as a formula; numbers are untouched.
- **Not in it:** any rank, winner, score, colour or favourability column (a test pins the column list), and the 3D structure.
  The JSON snapshot that Save keeps is a separate thing and is not exported.
- **Checked on the real stack** (2026-10-18): Predict export of a real molecule (15 lines in roster order, band and spread
  present on the regression line, none on the rule-based line); a two-row Batch (one valid, one invalid) exported 15 lines
  for row 1 and one `row_failed` line for row 2 with the service's error. **Export row** was not clicked through in a
  browser (it shares the same builder). The command palette's "Export results" entry is still a placeholder, like the rest
  of the palette's commands.

### 2i. Report (print / Save as PDF, ADR-029) — what was done and what was checked

- **What it is:** a **Report** button beside Predict's Export and in Batch's molecule inspector opens the browser's print
  dialog on a light, print-only document for that molecule; Save as PDF there makes the PDF. No server route (the blueprint's
  `/molecule/{id}/report` is superseded, see ADR-029). Disabled in the same cases as the CSV export.
- **Code:** `src/domain/report.ts` (pure model, tested in `report.test.ts`), `src/components/report/` (`PrintReport`,
  `usePrintReport`, `report.module.css`), `--report-*` tokens in `tokens.css`.
- **Checked:** against a live API (stub-served, so every value is hatched and the SA row is NOT RETURNED): the button mounts the
  report, calls `window.print()` once, the report is `display: none` and `aria-hidden` on screen, and the page title becomes the
  report name. The print stylesheet was re-applied on screen to look at the layout: 15 rows in 5 groups plus the rule-based
  group, aligned columns, hatch on every stub value, the reading notes at the end. **Not checked:** the real print dialog and a
  saved PDF (the in-app browser cannot drive one), the multi-page break behaviour on paper, an out-of-domain row and a
  held-out-error cell rendered in the page (both are covered by the tests on real captured responses, not by a screenshot).
- **Not in it:** a 2D structure drawing and drug-likeness flags. The service provides neither.

## 3. What is broken or missing — read before touching anything

These are ordered by how badly they would bite.

### 3.1 ~~Predict cannot take input.~~ Resolved 2026-10-07
SMILES entry, Run and Clear work; the endpoint-subset selector landed 2026-10-08
(a deselected endpoint is a `NOT REQUESTED` row, ADR-028). Save to library works (§2d).
Compare molecule and Export (CSV) work (§2f, §2h).

### 3.2 ~~The status bar and top bar show fabricated values~~ Resolved 2026-10-07
The status bar reads the real response (`served_at`, `cache_hit`, measured
latency, `model_version`); the API badge polls `/health`. A value with no source
renders as absent, never as a plausible number.

### 3.3 ~~CORS~~ Resolved 2026-10-07 (dev proxy + explicit origin list with credentials)
Confirmed in a browser. **Production:** an explicit origin list is not enough,
because the session cookie is `SameSite=Lax` and does not travel on cross-site
`fetch()`. Production serves one origin (ADR-025, Q22). That ADR is accepted as
a design; the `/api` mount and the multi-stage Dockerfile are **not
implemented**.

### 3.4 ~~CSS is entirely unguarded~~ Resolved 2026-10-07 (no stylelint needed)
`frontend/tests/cssGuard.test.ts` fails the build on any hex / `rgb()` / `hsl()`
literal in a `.module.css`. New tokens: `--track`, `--band`, `--on-accent`,
`--scrim`, `--highlight-selected`. The 50% status dots are recorded as ADR-021.
The guard lives in `tests/` because it reads the filesystem and the project has
no `@types/node`.

### 3.5 Smaller gaps

- **Batch gaps.** No multi-select; "Open in Predict" is inert; no
  endpoint subset for a batch (the request sends none, so the service runs all); no way to
  reopen an earlier job after a reload (the job id is held in memory only).
- **No empty/entry state.** The *Predict — entry state* artboard (draw/upload/
  recents, "what MARS does not do") is not implemented; the roster merely renders
  from `emptyResponse`. I did not verify any dedicated empty-state view exists.
- ~~**3Dmol is installed but unused.**~~ Wired 2026-10-07 (see "3D viewer" in §2a).
  Fixture mode still shows the placeholder geometry, labelled as illustrative.
- **Export** is CSV only (§2h); there is no JSON export, and the command palette's commands are placeholders. Settings holds the Account section and delete-account.
- ~~**ADR-009 CI drift check** is unwritten.~~ Written 2026-10-07:
  `contracts/tests/test_frontend_drift.py` (names only, not types).
- ~~**Bump `MODEL_VERSION` on release.**~~ Done (`v0.2.0-dev`); see §2a item 8.
- **ADR-020 known gap:** a promoted endpoint with no AD index returns
  `in_domain=False` with a NaN distance, which the UI would read as "outside
  domain". All currently promoted endpoints have an index.

## 4. Recommended order

1. ~~Make Predict real~~ — done.
2. ~~Remove the fabricated readouts~~ — done.
3. ~~Settle CORS; exercise real states; save real responses~~ — done, with two
   gaps: no mixed real+stub response could be captured (every promoted
   endpoint was served by a real model), so the stub-served *row* state is
   covered only by the all-stub capture; and the browser pass was manual.
   The endpoint-subset selector is now wired (ADR-028). NOT RETURNED is still
   unreachable live from the UI by design: it now means only "asked for, service
   did not answer". Remaining Predict buttons (§3.1) wait on Compare/Library.
4. ~~Close the CSS guard~~ — done.
5. **Auth UI (ADR-022 Phase 1) — done 2026-10-08; then Batch live.** Built: `GET /auth/me` +
   `MeResponse` (contract, route, `API_ROUTES.md`, `contracts.ts`, drift test, API tests);
   `AuthSessionProvider` (unknown / anonymous / signed in); lock glyphs on Batch and Library
   (with "account required" in their accessible names); an in-workspace sign-in state
   (`src/auth/Gated.tsx`) explaining why, what stays free, with sign-in and create-account
   forms; a real top-bar readout (Sign in / initial + Sign out) replacing the hard-coded "SK";
   a Settings Account section; a global 401 handler (`setUnauthorizedHandler`, not fired for
   `/auth/*`); fixture mode never gates. Create-account signs in straight away. Real auth
   responses are fixtures (`real-responses/auth-*`). **Not built:** password reset (ADR-022 item
   7), Turnstile, delete-account modal (Phase 2). **Known limit:** nothing in the UI makes a
   gated call yet, so the 401-drops-to-anonymous path is covered by unit tests only; a session
   that expires (or an account deleted) while the app is open is noticed on the first gated call
   or a reload. Batch live is done (§2b), so a gated call now exists; the chosen file is held
   above the router and survives a 401 (ADR-022 item 3). Library, delete-account, Save, Compare and Export are built (§2c, §2d, §2f, §2h).
6. ~~ADR-009 drift check~~ — done.
7. ~~3Dmol~~ — done. Then Compare, Library.
8. ~~**Relabel classification units as `score`**~~ — done 2026-10-14 (ADR-023): `DISPLAY_UNIT` and `unitLabel`, pinned by a test.
9. ~~**Rename `ENSEMBLE INTERVAL` to `SEED SPREAD ±1σ`**~~ — done 2026-10-14 (ADR-024), including the inspector rows
   (`Seed spread ±1σ`, `Spread width`).
10. **Production topology** (ADR-025; Q22): API under `/api`, frontend served from the API
    container, secure cookie. Before the first deploy, verify the client address the rate
    limiter sees behind Cloud Run.
11. ~~**Top-bar serving readout**~~ — done 2026-10-14 (ADR-026 part 1): a plain readout (no button role, tab stop or
    chevron) of the generation from the new `GET /generations`; fixture mode labels itself a fixture.
12. **Structure sketcher** (ADR-027): Ketcher standalone, lazy-loaded, in a bordered panel on Predict.
    Measure the chunk and audit never-do #7/#8 on first integration.
13. **Generation switching** (ADR-026 parts 2-5): `GET /generations`, request `model_version`, versioned
    routing table. Blocked until a second generation exists; build against two fixture registries.

Do not build more surfaces on fixtures before 1–3.

## 5. Open questions

All 22 live in `OPEN_QUESTIONS.md`. Resolved: Q1, Q2, Q3, Q4 (ADR-024), Q7 (ADR-022), Q10, Q14,
Q6 (ADR-026), Q9 (ADR-027), Q15, Q17, Q19 (ADR-020), Q21 (ADR-023), Q22 (ADR-025). Open: Q5, Q8,
Q11, Q12, Q13 (resolved, confirm), Q16, Q18, Q20.

Only these affect the next steps:
- **Q7** resolved 2026-10-08 (ADR-022): the auth UI, not a decision, blocked Batch upload,
  rail gating and Library. Batch upload is built (§2b).
- **Q8** (default density) and **Q12** (accent) are confirmations, not blockers.
- **Q3** resolved 2026-10-07 (printed intervals, per AGENTS.md never-do #4). **Q4**
  resolved 2026-10-08 (ADR-024): never flag narrow spread; rename it `SEED SPREAD ±1σ`.
- **Q21** resolved 2026-10-08 (ADR-023): relabel as `score` now; stop applying the served Platt
  calibrators (C0) and recalibrate (C1) later.
- **Q6** resolved 2026-10-08 (ADR-026): real generation switching; the control is a readout until
  a second generation exists. **Q9** resolved 2026-10-08 (ADR-027): Ketcher in the MVP.

## 6. Hard rules

`AGENTS.md` (repo root) is the non-negotiable layer; `frontend/DESIGN.md` is the
token table. The rule that outranks the others: **never imply a capability the
model does not have** — no value coloured by magnitude, nothing ranked, sorted by
favourability or called better. Reliability is a separate channel from the value.
Read `DECISIONS.md` before changing any visual choice; each has rejected
alternatives recorded.

## 7. Repository and branch hazards

- **Push to `milestone/m4-frontend`.** `milestone/m2-kermt` is the KERMT
  training branch and is in use by a separate session. Do not touch `ml/` beyond
  `ml/serve/`, and keep training notes off this branch. The one exception is
  `documentation/AIMS/`: it is shared project guidance (AIMS decision, 2026-10-08),
  so an AIMS edit is committed on both branches the same day. Push that single
  commit to `m2-kermt` without checking the branch out.
- **Shared AIMS docs.** `documentation/AIMS/`, the blueprint and `FUTURE_SCOPE.md`
  exist on both this branch and `m2-kermt`. Checked 2026-10-14: this branch's
  AIMS files are byte-identical to `sync/aims-to-m2-kermt` (`e6c3dee`, the
  2026-10-08 decisions on calibration, seed spread and branch sync), which has
  not yet been merged into `m2-kermt`. Two files exist only on `m2-kermt`:
  `AIMS/mistakes.md` and `documentation/status/mars-status_M{0,1}.md`, so
  references to them from this branch (`README`, `.env.example`,
  `docker-compose.yml`, AIMS) resolve only there. Edit AIMS on both branches the
  same day; do not edit one copy alone.
- **Two sessions once shared `frontend/.env.local` and port 5173 — fixed
  2026-10-08, rules now in `AGENTS.md` ("Shared dev environment").** One session had
  set `MARS_API_PROXY_TARGET=http://localhost:18000` in that shared file (a
  `mars_api_real` container built from older code, still returning
  `model_version: "stub-v0"`), so every Vite server on the tree proxied to it. The
  line is removed; `.env.local` now holds only `VITE_API_BASE=/api`. A `mars_api_real`
  container may still exist in Docker (it could not be inspected when this was
  fixed and has not been re-checked): `docker ps -a`.
  Rule of thumb: private experiments use a process variable and their own port, never
  a shared file.
- **Concurrent sessions.** Other chats edit this repo. Files change under you
  ("changed on disk" notices are real). `git status` before and after any task.
- **Python envs are separate** (three of them). `rdkit` lives in `ml/.venv`; the
  root `.venv` runs API and contract tests. Don't merge them.
- CRLF/LF warnings on every `git add` are noise on this Windows checkout.
- Frontend commands: `cd frontend && npm test`, `npm run lint`,
  `npx tsc --noEmit`, `npm run build`. If npm 10 crashes resolving vitest 4,
  `npm ci` works; only a *fresh* lockfile needs `npx npm@11 install`.

## 8. Design source

The *MARS Frontend Design System* design canvas: five artboards with strict
ownership (ADR-015). It is held outside the repository and is not linked here;
everything it shows is written down in this directory and in
`frontend/DESIGN.md`. The design is locked; do not redesign. Changes to it need
an ADR.

## 9. Corrections made in this session worth not repeating

- Q19 was resolved by a parallel session (not this one): `ad_threshold` is a
  required contract field and the placeholder 0.58 table is gone.
- The "Batch CSS breaches" item was framed as Batch-specific. It is not — the
  same patterns are in `predict`, `shell` and `dataviz`; Batch inherited them.
- `ARCHITECTURE.md` still described Tailwind v4 after ADR-016 dropped it;
  a status note now sits at the top of it.
