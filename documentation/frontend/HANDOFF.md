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
path (see §2a). Batch runs against the API too (upload, progress, results; §2b); Compare/Library/Settings are
stubs.

| Gate (run 2026-10-14, working tree incl. uncommitted edits) | Result |
|---|---|
| `npx tsc --noEmit` | clean |
| `npm run lint` | 0 errors, 3 warnings (`app/authSession.tsx`, `predictSession.tsx`, `uiState.tsx` fast-refresh, accepted) |
| `npm test` | 113 / 113 passed, 9 files (136 / 136 in 11 files after Batch live, 2026-10-18) |
| `ruff check contracts api ml` | clean |
| `contracts/tests` + `api/tests` (root `.venv`) | 51 passed, 26 skipped. The skips are the Postgres/Redis-backed tests, which skip when the stack is down; CI runs them for real. |
| `ml/tests` (**`ml/.venv`**, not the root env) | 400 passed, 15 skipped (about 9 min) |
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

## 3. What is broken or missing — read before touching anything

These are ordered by how badly they would bite.

### 3.1 ~~Predict cannot take input.~~ Resolved 2026-10-07
SMILES entry, Run and Clear work; the endpoint-subset selector landed 2026-10-08
(a deselected endpoint is a `NOT REQUESTED` row, ADR-028). Still inert:
**Compare molecule, Save to library, Export** (no handlers; Compare and Save
depend on those workspaces).

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

- **Batch gaps.** No multi-select; "Open in Predict" / "Export row" are inert; no
  endpoint subset for a batch (the request sends none, so the service runs all); no way to
  reopen an earlier job after a reload (the job id is held in memory only).
- **No empty/entry state.** The *Predict — entry state* artboard (draw/upload/
  recents, "what MARS does not do") is not implemented; the roster merely renders
  from `emptyResponse`. I did not verify any dedicated empty-state view exists.
- ~~**3Dmol is installed but unused.**~~ Wired 2026-10-07 (see "3D viewer" in §2a).
  Fixture mode still shows the placeholder geometry, labelled as illustrative.
- **Compare and Library** are `StubWorkspace` (Library is behind the sign-in gate). Settings holds the Account section only.
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
   above the router and survives a 401 (ADR-022 item 3). Next: Library, delete-account.
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
