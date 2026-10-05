# frontend/ — UI (M4, in progress)

Owns blueprint Module 9 (design system), Module 7 viewer wiring, Module 12/13 UI.

**Runnable.** The Vite entry now exists and the Predict workspace is built.

```bash
cd frontend
npm install
npm run dev     # http://localhost:5173
npm run build   # tsc && vite build — type-checks and bundles
```

**Dependency note (2026-10-06).** Vite 7, vitest 4, plugin-react 5 and
react-router-dom 7 — the patched lines; `npm audit` reports 0 vulnerabilities.
npm 10.9.3's resolver crashes (`Cannot read properties of null (reading
'edgesOut')`) when *resolving* vitest 4, so a fresh lockfile must be generated
with npm 11 (`npx npm@11 install`). Installing from the committed
`package-lock.json` (`npm ci`) works on npm 10.

## What's built (pass 3, 2026-10-01)

- **Shell**: nav rail, top bar (serving generation, API status, account), status
  bar, and the ⌘K command palette (fuzzy search over endpoints / molecules /
  commands; reliability tags travel into the results).
- **Predict workspace**: molecule input + identity + structure-viewer shell; the
  full 15-row endpoint roster reconciled from the contract (14 ML + the
  rule-based SA score in its own group); the six derived row states; the
  applicability-domain gauge; the inspector; full keyboard roving (↑↓ / Home /
  End / Enter), hover, focus and selection as distinct channels; density toggle;
  reduced-motion support.
- **Batch / Compare / Library**: routed placeholders — same shell, built later.

Values are an **illustrative fixture** (`src/domain/fixtures.ts`), not model
output; the app shows a "design prototype" strip accordingly. Going live is one
change: swap the fixture for a real `/predict` response. The roster, state
derivation and reconciliation already come from `ENDPOINT_METADATA`, never the
response (ADR-008).

## Architecture

- Stack: Vite + React 18 + TypeScript, React Router (ADR-001). No Next.js.
- Styling: CSS Modules over the token layer in `src/styles/tokens.css`
  (ADR-016). No raw hex in a component.
- `src/domain/` is load-bearing: `deriveRowState` is the single pure function
  that decides an endpoint row's trustworthiness, and nothing else does
  (ARCHITECTURE.md). Unit-test it against the API fixtures.
- `src/types/contracts.ts` mirrors `contracts/mars_contracts` and now **includes
  `model_id`** — the drift ADR-009 flagged is closed. A CI check to keep it in
  sync is still to be written.

Layout:

```
src/
  app/            uiState (selected endpoint, palette, density)
  shell/          AppShell, NavRail, TopBar, StatusBar, CommandPalette
  workspaces/
    predict/      PredictWorkspace + EndpointList/Row/Detail, StructureViewer
    StubWorkspace (batch/compare/library/settings)
  components/dataviz/  BoundedTrack scale, IntervalTrack, ADGauge, NumericInterval, ReliabilityTag
  domain/         endpoints, rowState, reconcile, format, fixtures
  types/          contracts.ts (contract mirror)
  styles/         tokens.css
```

## Testing

```bash
npm test        # vitest run — pure-domain unit tests
npm run test:watch
```

Covers the load-bearing pure functions: `deriveRowState` (the single trust
decision), `reconcile` (roster + counts, SA excluded) and the formatters. 18
tests. Extend these against the same fixtures the API tests use.

## Running against the real API

```bash
cp .env.example .env
# set VITE_API_BASE=http://localhost:8000  (docker compose up -d api)
npm run dev
```

With `VITE_API_BASE` unset the UI runs on the fixture and shows the "design
prototype" strip. With it set, `/predict` drives the result, the strip clears,
and the AD-gauge threshold is read from the response (`ad_threshold`) when
present, falling back to the local table until the contract supplies it (Q19).

## Read first

- `../AGENTS.md` and `DESIGN.md` — the guardrails any coding agent must follow
  (the "never do" list, the type contracts, the tokens).
- `../documentation/frontend/` — the full design system, ADRs, and open
  questions. The visual source of truth is the Claude Design canvas linked from
  its README; the live interactive reference is the published MARS Predict
  artifact.

## Open before this goes live

- **Q19** — the AD-gauge threshold is not in the prediction response; it uses a
  placeholder table. Needs real Module-5 thresholds (preferably added to the
  contract) before the gauge is shown on real predictions.
- The API is real (`docker compose up -d api`) — wire `/predict` and replace the
  fixture.
