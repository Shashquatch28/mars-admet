# Frontend session handoff

**Written 2026-10-07; §1–§4 updated later the same day after Predict went live.
Branch `milestone/m4-frontend`.**
Everything below was checked against the repository on that date, not recalled.
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
path (see §2a). Batch is still fixture-only (§3.5); Compare/Library/Settings are
stubs.

| Gate (run 2026-10-07) | Result |
|---|---|
| `npx tsc --noEmit` | clean |
| `npm run lint` | 0 errors, 1 warning (`uiState.tsx` fast-refresh, accepted) |
| `npm test` | 51 / 51 passed, 5 files (20 new, against real captured responses) |
| `npm run build` | succeeds |
| `npm audit` | 0 vulnerabilities |
| API + contract tests | 52 passed, 1 skipped (root `.venv`) |
| `ml/tests/test_serve_registry.py` | 7 passed (**`ml/.venv`**, not the root env) |

## 2. What exists

| Area | Files | Notes |
|---|---|---|
| Shell | `src/shell/` | AppShell, NavRail, TopBar, StatusBar, CommandPalette. Keys 1–4 switch workspace, ⌘K opens the palette. |
| Predict | `src/workspaces/predict/` | Roster of 15 rows (14 ML + rule-based SA), seven derived row states (incl. NOT REQUESTED, ADR-028), endpoint-subset selector, inspector, AD gauge, keyboard roving, live 3D viewer (placeholder SVG in fixture mode). |
| Batch | `src/workspaces/batch/`, `src/domain/batch.ts` | 240-molecule deterministic fixture, virtualized `role="grid"`, raw numeric sort, filters, molecule inspector. |
| Data-viz | `src/components/dataviz/` | `ADGauge`, `IntervalTrack` (both require an explicit `domain`, no default), `NumericInterval`, `ReliabilityTag`. |
| Domain | `src/domain/` | `rowState` (the one trust decision), `reconcile` (full roster every time), `format`, `endpoints`, `fixtures`, `batch`. This is the tested layer. |
| Data | `src/data/` | `client.ts` + `usePrediction.ts` — single-molecule `/predict` only. No batch client. |
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

## 3. What is broken or missing — read before touching anything

These are ordered by how badly they would bite.

### 3.1 ~~Predict cannot take input.~~ Resolved 2026-10-07 for SMILES + Run + Clear
**Endpoint-subset selector: done 2026-10-08** (popover; a deselected endpoint is a
`NOT REQUESTED` row, ADR-028). Still inert: **Compare molecule, Save to library,
Export** (no handlers; Compare/Save depend on those workspaces and on ADR-022).
Original note:

`PredictWorkspace.tsx` hard-codes `const smiles = CELECOXIB_SMILES`. The textarea
has only a `defaultValue`; **Run prediction, Clear, Compare molecule, Save to
library, Export and the endpoint-subset selector have no handlers.** Setting
`VITE_API_BASE` would query the API for celecoxib and nothing else, ever.

> An earlier version of `frontend/README.md` (and this project's own advice)
> described going live as "swap the fixture for a real response". That
> understated the work and has been corrected.

### 3.2 ~~The status bar and top bar show fabricated values~~ Resolved 2026-10-07
Original note:

- `StatusBar.tsx` reads `FIXTURE_RESPONSE` directly: the timestamp, `CACHE MISS`,
  `412 ms`, `rate 7/60 per min` and `cached for 48 h` are all literals. Against a
  live response they would be presented as real. This violates the project's own
  rule that sample data must never look like live data.
- `TopBar.tsx` hard-codes `API Ready` and `mars-routing@v0.3.1`. The badge would
  stay green with the API down.

Fix: drive the status bar from the actual response (`served_at`, `cache_hit`,
measured latency, `model_version`) and the API badge from a real `/health`
check. Until a value has a source, render it as absent, not as a plausible number.

### 3.3 ~~CORS~~ Resolved 2026-10-07 (dev proxy + explicit origin list with credentials)
Confirmed in a browser. **Production:** an explicit origin list is not enough, because the session cookie is
`SameSite=Lax` and does not travel on cross-site `fetch()`. Production serves one origin (ADR-025, Q22). Original note:

`api/app/main.py` sets `allow_origins=["*"]` with **no** `allow_credentials`.
`client.ts` sends `credentials: "include"`. Browsers reject a credentialed
request answered with a wildcard origin. **Not verified in a browser** — this is
from the CORS specification, so confirm it when you get there.

Options: (a) Vite dev proxy `/api → localhost:8000`, which makes dev same-origin
and needs no backend change (recommended for dev); (b) drop `credentials` for the
anonymous `/predict` call only; (c) backend: explicit origin list +
`allow_credentials=True` (needed for auth and prod anyway — the code comment says
"tighten before prod deploy"). (c) touches `api/`, which is your call.

### 3.4 ~~CSS is entirely unguarded~~ Resolved 2026-10-07 (no stylelint needed)
`frontend/tests/cssGuard.test.ts` fails the build on any hex / `rgb()` / `hsl()` literal in a `.module.css`.
New tokens: `--track`, `--band`, `--on-accent`, `--scrim`, `--highlight-selected`; every literal listed below is
replaced. The two near-identical ink colours (`#07191d`, `#06181d`) are now one token. The 50% status dots are
recorded as ADR-021. The guard lives in `tests/` because it reads the filesystem and the project has no
`@types/node`. Original note:

ESLint does not read `.module.css`, so the "no raw hex" rule only covers TS/TSX.
Current violations, verified by grep:

- Raw hex: `dataviz.module.css:13` (`#2a3236`), `:19` (`#3a4549`);
  `batch.module.css:498` (`#07191d`); `predict.module.css:76` (`#06181d`).
- The selection bevel `inset 0 2px 0 -1px rgba(255,255,255,0.045)` is
  hard-coded in `shell`, `batch` and `predict` modules. ADR-011 says it should be
  a token; `--highlight-machined` currently covers only the nav variant.
- `border-radius: 50%` on two status dots (`shell.module.css:172`,
  `batch.module.css:555`). **This is probably not a violation** — "radius ≤ 3px"
  governs surfaces, not a 6px status dot, and the design drew them as circles.
  But no ADR records the exception yet. Write one rather than "fixing" the dots.

Fix is two tokens, a stylelint config, and that ADR — not a Batch-only patch.

### 3.5 Smaller gaps

- **Batch is fixture-only.** No upload (`POST /batch/predict` needs an account and
  the auth UI, ADR-022), no SSE progress for the >1000 async tier, no multi-select, "Open in
  Predict" / "Export row" are inert.
- **No empty/entry state.** The *Predict — entry state* artboard (draw/upload/
  recents, "what MARS does not do") is not implemented; the roster merely renders
  from `emptyResponse`. I did not verify any dedicated empty-state view exists.
- ~~**3Dmol is installed but unused.**~~ Wired 2026-10-07 (see "3D viewer" in §2a).
  Fixture mode still shows the placeholder geometry, labelled as illustrative.
- **Compare, Library, Settings, auth UI** are `StubWorkspace`.
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
5. **Auth UI, then Batch live** (ADR-022; Q7 resolved 2026-10-08). Phase 1: `GET /auth/me` +
   `MeResponse`, session context (unknown / anonymous / signed in), lock glyphs on Batch and
   Library, in-workspace sign-in state, a real top-bar account readout (replaces the
   hard-coded "SK"), global 401 handling, tests. Then the upload + SSE hook, Library, and the
   Settings account section.
6. ~~ADR-009 drift check~~ — done.
7. ~~3Dmol~~ — done. Then Compare, Library.
8. **Relabel classification units as `score`** (ADR-023; Q21 resolved 2026-10-08). Small and
   user-visible: `DISPLAY_UNIT` and `unitLabel`. Do it before any demo.
9. **Rename `ENSEMBLE INTERVAL` to `SEED SPREAD ±1σ`** (ADR-024). Text only; do it with item 8.
10. **Production topology** (ADR-025; Q22): API under `/api`, frontend served from the API
    container, secure cookie. Before the first deploy, verify the client address the rate
    limiter sees behind Cloud Run.
11. **Top-bar serving readout** (ADR-026 part 1): drop the button role, tab stop and chevron; show the
    deployed generation from the API. Small; do it with items 8-9.
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
- **Q7** resolved 2026-10-08 (ADR-022): the auth UI, not a decision, now blocks Batch upload,
  rail gating and Library.
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
- **Duplicate docs on this branch.** Commit `f7a41db` ("ship on Tier 0…") added
  10 `documentation/AIMS/`, blueprint and `FUTURE_SCOPE` files here. `m2-kermt`
  carries the same content (`5da3091`) and the 10 files are **byte-identical
  today**. They exist as adds on both branches because `documentation/` was
  gitignored on `main`. **Re-checked 2026-10-07:** `main` now carries the same
  files too (`c8269b7`), and all copies are byte-identical, so merging this branch
  to `main` is clean. The only remaining conflict is `m2-kermt` → `main` *after*
  `m2-kermt` edits one of them, and it is trivial (take `m2-kermt`'s version).
  Reverting `f7a41db` is no longer worth doing.
- **Two sessions once shared `frontend/.env.local` and port 5173 — fixed
  2026-10-08, rules now in `AGENTS.md` ("Shared dev environment").** One session had
  set `MARS_API_PROXY_TARGET=http://localhost:18000` in that shared file (a
  `mars_api_real` container built from older code, still returning
  `model_version: "stub-v0"`), so every Vite server on the tree proxied to it. The
  line is removed; `.env.local` now holds only `VITE_API_BASE=/api`. A `mars_api_real`
  container may still exist in Docker (Docker Desktop was off when this was fixed, so
  it could not be inspected or stopped): check `docker ps -a` when Docker is back.
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

Claude Design canvas: https://claude.ai/artifact/G4Xn8GJCABLWRZ2qXrotzg — five
artboards with strict ownership (ADR-015). The design is locked; do not
redesign. Changes to it need an ADR.

## 9. Corrections made in this session worth not repeating

- Q19 was resolved by a parallel session (not this one): `ad_threshold` is a
  required contract field and the placeholder 0.58 table is gone.
- The "Batch CSS breaches" item was framed as Batch-specific. It is not — the
  same patterns are in `predict`, `shell` and `dataviz`; Batch inherited them.
- `ARCHITECTURE.md` still described Tailwind v4 after ADR-016 dropped it;
  a status note now sits at the top of it.
