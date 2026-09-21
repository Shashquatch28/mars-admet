# frontend/ — UI (M4, not started)

Owns blueprint Module 9 (design system), Module 7 viewer wiring, Module 12/13 UI.

**Not runnable.** `package.json` and `src/types/contracts.ts` exist; the Vite
entry (`index.html`, `src/main.tsx`, `vite.config.ts`, `tsconfig.json`) is M4
work that has not started. `npm install` works; `npm run dev` does not.

The earlier "Person C track" framing is retired — the build is solo and
dependency-ordered (blueprint Module 14). This is a module grouping, not a person.

## When M4 starts

- The API is already real, not a mock: `docker compose up -d api` serves genuine
  predictions for all 14 endpoints. Build against that, not hand-built fixtures.
- `contracts/mars_contracts` is the source of truth for field names; mirror it in
  `src/types/`. `contracts/API_ROUTES.md` documents every route, including the
  Module 13 auth/persistence table.
- Every `EndpointPrediction` carries a `model_id`, so the UI can distinguish a
  real prediction from a stub (`"stub-v0"`) rather than assuming.
- Design direction: see Module 9 in the blueprint — analytical
  lab-instrumentation vernacular, not generic SaaS dashboard.
