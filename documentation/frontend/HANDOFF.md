# Frontend session handoff

**Written 2026-10-07. Branch `milestone/m4-frontend`, verified at `f7a41db`.**
Everything below was checked against the repository on that date, not recalled.
Where a claim could not be verified it says so.

This is the file to read first when picking the frontend up in a new session.
It does not restate the design system; it says where the work stands, what is
broken or missing, and what to do next.

---

## 1. Where things stand

The design is **locked** (passes 1–2.1, 2026-10-01). The M4 frontend is **built
on fixture data**: shell, Predict workspace, and a Batch triage matrix. Nothing
runs against the live API yet, and **it cannot yet** — see §3.

| Gate (run 2026-10-07) | Result |
|---|---|
| `npx tsc --noEmit` | clean |
| `npm run lint` | 0 errors, 1 warning (`uiState.tsx` fast-refresh, accepted) |
| `npm test` | 31 / 31 passed, 4 files |
| `npm run build` | succeeds |
| `npm audit` | 0 vulnerabilities |
| API + contract tests | 52 passed, 1 skipped (root `.venv`) |
| `ml/tests/test_serve_registry.py` | 7 passed (**`ml/.venv`**, not the root env) |

## 2. What exists

| Area | Files | Notes |
|---|---|---|
| Shell | `src/shell/` | AppShell, NavRail, TopBar, StatusBar, CommandPalette. Keys 1–4 switch workspace, ⌘K opens the palette. |
| Predict | `src/workspaces/predict/` | Roster of 15 rows (14 ML + rule-based SA), six derived row states, inspector, AD gauge, keyboard roving. Viewer is a placeholder SVG. |
| Batch | `src/workspaces/batch/`, `src/domain/batch.ts` | 240-molecule deterministic fixture, virtualized `role="grid"`, raw numeric sort, filters, molecule inspector. |
| Data-viz | `src/components/dataviz/` | `ADGauge`, `IntervalTrack` (both require an explicit `domain`, no default), `NumericInterval`, `ReliabilityTag`. |
| Domain | `src/domain/` | `rowState` (the one trust decision), `reconcile` (full roster every time), `format`, `endpoints`, `fixtures`, `batch`. This is the tested layer. |
| Data | `src/data/` | `client.ts` + `usePrediction.ts` — single-molecule `/predict` only. No batch client. |
| Tooling | `.eslintrc.cjs`, `vitest.config.ts` | ESLint enforces two AGENTS.md rules in **TS/TSX only**. |
| Backend (this branch) | `ml/serve/rule_based.py`, `contracts/…/prediction.py` | API now serves the SA score (ADR-019) and `ad_threshold` per prediction (ADR-020). |

## 3. What is broken or missing — read before touching anything

These are ordered by how badly they would bite.

### 3.1 Predict cannot take input. "Going live" is not one change.

`PredictWorkspace.tsx` hard-codes `const smiles = CELECOXIB_SMILES`. The textarea
has only a `defaultValue`; **Run prediction, Clear, Compare molecule, Save to
library, Export and the endpoint-subset selector have no handlers.** Setting
`VITE_API_BASE` would query the API for celecoxib and nothing else, ever.

> An earlier version of `frontend/README.md` (and this project's own advice)
> described going live as "swap the fixture for a real response". That
> understated the work and has been corrected.

### 3.2 The status bar and top bar show fabricated values in live mode

- `StatusBar.tsx` reads `FIXTURE_RESPONSE` directly: the timestamp, `CACHE MISS`,
  `412 ms`, `rate 7/60 per min` and `cached for 48 h` are all literals. Against a
  live response they would be presented as real. This violates the project's own
  rule that sample data must never look like live data.
- `TopBar.tsx` hard-codes `API Ready` and `mars-routing@v0.3.1`. The badge would
  stay green with the API down.

Fix: drive the status bar from the actual response (`served_at`, `cache_hit`,
measured latency, `model_version`) and the API badge from a real `/health`
check. Until a value has a source, render it as absent, not as a plausible number.

### 3.3 The first live browser request will probably fail on CORS

`api/app/main.py` sets `allow_origins=["*"]` with **no** `allow_credentials`.
`client.ts` sends `credentials: "include"`. Browsers reject a credentialed
request answered with a wildcard origin. **Not verified in a browser** — this is
from the CORS specification, so confirm it when you get there.

Options: (a) Vite dev proxy `/api → localhost:8000`, which makes dev same-origin
and needs no backend change (recommended for dev); (b) drop `credentials` for the
anonymous `/predict` call only; (c) backend: explicit origin list +
`allow_credentials=True` (needed for auth and prod anyway — the code comment says
"tighten before prod deploy"). (c) touches `api/`, which is your call.

### 3.4 CSS is entirely unguarded

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

- **Batch is fixture-only.** No upload (`POST /batch/predict` needs an account —
  **Q7**), no SSE progress for the >1000 async tier, no multi-select, "Open in
  Predict" / "Export row" are inert.
- **No empty/entry state.** The *Predict — entry state* artboard (draw/upload/
  recents, "what MARS does not do") is not implemented; the roster merely renders
  from `emptyResponse`. I did not verify any dedicated empty-state view exists.
- **3Dmol is installed but unused.** `StructureViewer` is placeholder geometry
  with a toggle that only changes local state. No `/molecule/{id}/3d` call.
- **Compare, Library, Settings, auth UI** are `StubWorkspace`.
- **ADR-009 CI drift check** is unwritten. `ad_threshold` just changed the
  contract in three places at once; nothing would have caught a miss.
- **Bump `MODEL_VERSION` on release.** `/predict` caches 48 h; responses cached
  before ADR-019/020 lack the SA row and `ad_threshold`. (The gauge hides on
  them rather than being wrong.)
- **ADR-020 known gap:** a promoted endpoint with no AD index returns
  `in_domain=False` with a NaN distance, which the UI would read as "outside
  domain". All currently promoted endpoints have an index.

## 4. Recommended order

1. **Make Predict real** (§3.1): controlled SMILES input, Run submits it, loading
   / error / invalid-SMILES states, fixture fallback kept for no-API-base.
2. **Remove the fabricated readouts** (§3.2) in the same change — they would
   otherwise sit next to real data.
3. **Settle CORS** (§3.3), then run the API (`docker compose up -d api`) and
   exercise the real states in a browser: SA row, `ad_threshold`, stub-served,
   out-of-domain, NOT RETURNED, cache hit vs miss. **Save real responses as
   vitest fixtures** — every fixture so far was written by us, so they only test
   our assumptions.
4. **Close the CSS guard** (§3.4).
5. **Batch live**: needs Q7 answered first; then upload + SSE hook.
6. **ADR-009 drift check.**
7. Then 3Dmol, Compare, Library, auth.

Do not build more surfaces on fixtures before 1–3.

## 5. Open questions

All 20 live in `OPEN_QUESTIONS.md`. Resolved: Q1, Q2, Q14, Q15, Q17, Q19 (ADR-020). Open: Q3–Q13,
Q16, Q18, Q20.

Only these affect the next steps:
- **Q7** (auth boundary in the shell) blocks Batch upload, rail gating, Library.
- **Q8** (default density) and **Q12** (accent) are confirmations, not blockers.
- **Q3/Q4** (regression interval axis, narrow-CI flagging): `OPEN_QUESTIONS.md`
  files these under *Blocking*. They do not block the next steps here, because the
  build already took the honest default (print the interval, don't flag width) —
  but that is a judgment, and the maintainer has not signed off on it.

## 6. Hard rules

`AGENTS.md` (repo root) is the non-negotiable layer; `frontend/DESIGN.md` is the
token table. The rule that outranks the others: **never imply a capability the
model does not have** — no value coloured by magnitude, nothing ranked, sorted by
favourability or called better. Reliability is a separate channel from the value.
Read `DECISIONS.md` before changing any visual choice; each has rejected
alternatives recorded.

## 7. Repository and branch hazards

- **Push only to `milestone/m4-frontend`.** `milestone/m2-kermt` is the KERMT
  training branch and is in use by a separate session. Do not touch `ml/` beyond
  `ml/serve/`, and do not commit AIMS or training notes here.
- **Duplicate docs on this branch.** Commit `f7a41db` ("ship on Tier 0…") added
  10 `documentation/AIMS/`, blueprint and `FUTURE_SCOPE` files here. `m2-kermt`
  carries the same content (`5da3091`) and the 10 files are **byte-identical
  today**. They exist as adds on both branches because `documentation/` was
  gitignored on `main`. This is harmless now and becomes an **add/add merge
  conflict** as soon as `m2-kermt` edits any of them during training — which it
  will. Cheapest fix is `git revert f7a41db` on this branch (non-destructive),
  after which `m2-kermt` supplies those files at merge time. Not done here;
  your call.
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
