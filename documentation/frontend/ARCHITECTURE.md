# MARS frontend architecture

Status: **partly implemented (2026-10-07).** This document is the original
architecture *proposal* and is kept for its reasoning. Where the build diverged,
the divergence is recorded below and in `DECISIONS.md`; read `HANDOFF.md` for
current state.

> **Superseded in part — styling.** The sections below propose Tailwind v4.
> That was **not adopted**: ADR-016 chose CSS Modules over the token layer in
> `src/styles/tokens.css`, and Tailwind is not installed. Read every "Tailwind"
> reference below as "CSS Modules + tokens". The no-raw-values rule is unchanged
> and still the point. `@tanstack/react-table` and `radix-ui` are also not
> installed yet; `@tanstack/react-query` and `@tanstack/react-virtual` are.
> The "What already exists" section describes the *pre-build* scaffold and is
> historical.

## What already exists

`frontend/` contains `package.json`, `README.md`, and
`src/types/contracts.ts`. There is no Vite entry, no `tsconfig.json`, no
`vite.config.ts`, no component. Pinned today: React 18.3, React Router 6.23,
Vite 5.2, TypeScript 5.4, ESLint 8.57, **3dmol 2.1**.

There is therefore no existing architecture to preserve — only an existing
*stack intent*, which this document evaluates rather than assumes.

**One live defect found during this review:** `src/types/contracts.ts` is
missing `EndpointPrediction.model_id`, which the Python contract added in M3
and which `frontend/README.md` itself says the UI depends on. The file's own
header warns that drift is a sync bug. Logged as ADR-009 / Q10; not fixed in
this design-only pass.

## Stack decision

**Keep Vite + React 18 + TypeScript. Add Tailwind v4 and source-owned
components over Radix primitives. Do not adopt Next.js.**

### Why Vite, not Next.js

MARS is a desktop workstation talking to a FastAPI service (Predict and Compare are
anonymous; Batch and Library need a session, ADR-022). It
has no public surface to index, no marketing pages, no content to render on a
server. Sessions are opaque server-side tokens in an HttpOnly cookie
(`contracts/API_ROUTES.md`, Module 13) — there is no JWT for a Node layer to
verify and no reason to introduce one. Adding Next.js would add a second
runtime, a second deployment target and a second auth boundary to a project
whose serving budget is explicitly $0 on Cloud Run. Vite builds a static bundle
the existing API container or a CDN can serve. Rejected alternative recorded in
ADR-001.

### Why source-owned components, not a component library

The dominant 2026 pattern — shadcn/ui's model — is to copy component source
into the repository rather than depend on a package, keeping markup, variants
and APIs under direct control. That matters more for MARS than for a typical
app, for two reasons:

1. **Every component needs MARS semantics baked in.** A generic `Badge` will
   happily render a green "LOW RISK" chip. A MARS `ReliabilityTag` cannot,
   because the variants that would allow it do not exist in its type. The
   safest place to enforce scientific honesty is the component's own type
   signature, which requires owning the source.
2. **AI-assisted iteration needs stable, readable boundaries.** Copied source
   with explicit variants is the thing an agent can reliably edit; a
   node_modules dependency with a themed API is not.

Radix (or Base UI) supplies the unstyled primitives where accessibility is
genuinely hard: dialog, popover, dropdown, tooltip, tabs. Those are not
re-implemented.

### Why Tailwind v4 with semantic tokens only

Tailwind v4 defines its theme in CSS custom properties, which lets the token
table in `DESIGN_SYSTEM.md` be the literal source of the utility classes.
Arbitrary values (`bg-[#0B0D0E]`) are banned by lint rule; components use
`bg-surface-panel`. A three-tier token structure — raw scale, semantic alias,
component-scoped — is what makes an assistant's output consistent rather than
averaged, and it is the difference between a design system an agent follows and
one it approximates.

### Additional dependencies, with justification

| Package | For | Why not hand-rolled |
|---|---|---|
| `@tanstack/react-table` | Batch grid: sorting, column sizing, grouping | correct headless table semantics are a genuine time sink |
| `@tanstack/react-virtual` | Batch: up to 1,000 interactive rows | virtualization must be correct or nothing else matters |
| `@tanstack/react-query` | `/predict`, `/batch`, `/compare` caching + SSE-adjacent polling | the API already has a 48h cache and a `cache_hit` flag; client cache must not contradict it |
| `radix-ui` primitives | dialog, popover, dropdown, tooltip, tabs | focus trapping and ARIA wiring |
| `3dmol` (already pinned) | Module 7 viewer, both modes | the blueprint already settled this |

Explicitly **not** adopted: a charting library. MARS's four data-viz primitives
are twenty lines of markup each (`DESIGN_SYSTEM.md`). Importing a chart library
would invite chart types the data does not support.

## Proposed layout

```
frontend/src/
  app/              route definitions, providers, error boundaries
  shell/            AppShell, NavRail, TopBar, StatusBar, CommandPalette
  workspaces/
    predict/        PredictWorkspace + its panels
    batch/          BatchWorkspace
    compare/        CompareWorkspace
    library/        LibraryWorkspace
  domain/           endpoint metadata, state derivation, formatters
  components/       source-owned primitives (Button, Tag, Field, Dialog…)
  data/             API client, query hooks, generated types
  styles/           tokens.css, tailwind theme
  types/            contracts.ts (mirror of mars_contracts)
```

`domain/` is load-bearing and deliberately separate. It holds the pure
functions that turn a contract response into the UI's state vocabulary — and
nothing else in the app is allowed to decide those states:

```ts
type EndpointRowState =
  | { kind: 'ok' }
  | { kind: 'out_of_domain'; knnDistance: number }
  | { kind: 'stub_served'; modelId: string }
  | { kind: 'not_returned' }
  | { kind: 'rule_based' };

function deriveRowState(
  endpoint: Endpoint,
  prediction: EndpointPrediction | undefined,
): EndpointRowState;
```

Centralising this is what makes principle 1 enforceable: there is one place
where "is this trustworthy?" is decided, it is pure, and it is unit-testable
against the same fixtures the API tests use.

## Data layer

- One generated/mirrored type module, checked against
  `contracts/mars_contracts` in CI. Drift is a build failure, not a comment.
- The client requests **all** endpoints by default and reconciles the response
  against the canonical roster, synthesising `not_returned` rows for anything
  absent. The roster comes from `ENDPOINT_METADATA`, never from the response.
- `model_version` and per-endpoint `model_id` are surfaced, never averaged away.
- `cache_hit` is displayed in the status bar; a cached result is still a result
  and is not visually distinguished beyond that readout.
- Batch: `POST /batch/predict` returns either inline results (≤1,000) or a
  `job_id`. The UI treats these as one state machine with a progress phase, and
  consumes `/batch/progress/{job_id}` as SSE.

## What this phase does not decide

Build/deploy target, bundle budget, testing stack, and the Storybook-vs-canvas
question. Those belong to the implementation plan, which is deliberately not
written yet.
