# frontend/ — MARS UI (M4, in progress)

Vite + React 18 + TypeScript single-page app. Owns blueprint Module 9 (design
system), Module 7 viewer wiring, and the Module 12/13 UI.

## Status

| Workspace | State |
|---|---|
| **Predict** | Live. Typed SMILES, Run, endpoint-subset selector, 15-row reconciled roster, inspector, AD gauge, 3D viewer (3Dmol), keyboard roving. |
| **Batch** | Live: upload a CSV/SDF, progress for queued jobs over SSE, results in a virtualized `role="grid"` with raw numeric sort, filters and a molecule inspector; Save molecule and Save report. Without an API it shows a 240-molecule fixture. Behind the sign-in gate. |
| **Compare** | Live: two or three molecules side by side, descriptive only (no winner, ADR-007); reached from Predict's Compare molecule. Anonymous. |
| **Library** | Live: saved molecules and reports as frozen snapshots, delete. Behind the sign-in gate. |
| **Settings** | Account section: sign in or out, delete account (confirmation modal). |
| **Auth** | Sign in, create account, sign out, `GET /auth/me` session probe, global 401 handler. Password reset, Turnstile and delete-account are not built. |

Without `VITE_API_BASE` the app has no API to talk to: Run, Batch upload and Save are off and every
workspace says so, with no sample values anywhere (ADR-031). With it set, the app shows only what the
service returned.

Where things stand, what is broken, and what to do next:
`../documentation/frontend/HANDOFF.md`.

## Run

```bash
cd frontend
npm install
cp .env.example .env.local   # then set VITE_API_BASE=/api
npm run dev                  # http://localhost:5173
npm run build                # tsc && vite build
```

The dev server proxies `/api/*` to the API with the prefix stripped
(default `http://localhost:8000`, from `docker compose up -d api` at the repo
root), so the browser makes same-origin requests and CORS never applies. To aim
your own server at a different API, set `MARS_API_PROXY_TARGET` in the
**process** environment, never in `.env.local`
(`../AGENTS.md`, "Shared dev environment").

The proxy exists only in the dev server. A deployed SPA must reach the API
same-site: the session cookie is `SameSite=Lax` and does not travel on
cross-site `fetch()`. The production topology (one origin, API under `/api`) is
ADR-025 and is not implemented yet.

**Dependency note.** Vite 7, vitest 4, plugin-react 5 and react-router-dom 7.
npm 10's resolver crashes when *resolving* vitest 4, so a fresh lockfile must be
generated with npm 11 (`npx npm@11 install`). Installing from the committed
`package-lock.json` (`npm ci`) works on npm 10.

## Architecture

- Stack: Vite + React 18 + TypeScript, React Router, TanStack Query and Virtual,
  3Dmol. No Next.js, no charting library, no component library with its own
  theme (ADR-001).
- Styling: CSS Modules over the token layer in `src/styles/tokens.css`
  (ADR-016). No raw colour literal in a component; `tests/cssGuard.test.ts`
  fails the build on one.
- `src/domain/` is the load-bearing layer. `deriveRowState` is the single pure
  function that decides an endpoint row's trustworthiness and nothing else does.
  The roster comes from `ENDPOINT_METADATA`, never from the response (ADR-008).
- `src/types/contracts.ts` mirrors `contracts/mars_contracts`. The CI check
  `contracts/tests/test_frontend_drift.py` fails on a field or enum-name drift
  (names only, not types; ADR-009).

```
src/
  app/            providers: uiState, predictSession, authSession, queryClient
  auth/           Gated (sign-in state), AccountForm
  shell/          AppShell, NavRail, TopBar, StatusBar, CommandPalette
  workspaces/
    predict/      PredictWorkspace, EndpointList/Row/Detail/Selector, StructureViewer
    batch/        BatchWorkspace, BatchGrid (virtualized), BatchUpload
    compare/      CompareWorkspace
    library/      LibraryWorkspace
    settings/     SettingsWorkspace, DeleteAccount
  components/dataviz/  scale, IntervalTrack, ADGauge, NumericInterval, ReliabilityTag
  domain/         endpoints, rowState, reconcile, format, conformer, session,
                  batch, palette, real-responses/ (captured API payloads; tests only)
  testSupport/    test-only fixtures (never imported by the app)
  data/           client (predict, conformer, health, auth), useApiHealth, useConformer
  types/          contracts.ts
  styles/         tokens.css
tests/            cssGuard.test.ts
```

## Verify

```bash
npm test             # vitest run: 187 tests in 15 files
npm run lint         # eslint, TS/TSX only; does not read .module.css
npx tsc --noEmit
```

Numbers above are from the audit of 2026-10-14: `tsc` clean, 113/113 tests,
lint 0 errors and 3 fast-refresh warnings (`app/*.tsx` exports a provider and a
hook from one file; accepted).

The tests cover the pure domain layer (`rowState`, `reconcile`, formatters,
batch build/sort/filter, conformer state, session gating), the real captured
API responses in `src/domain/real-responses/` (provenance in the README there),
and the CSS literal guard.

## Read first

- `../AGENTS.md` and `DESIGN.md`: the guardrails any coding agent must follow
  (the "never do" list, the type contracts, the tokens).
- `../documentation/frontend/`: the design system, ADR log and open questions.
