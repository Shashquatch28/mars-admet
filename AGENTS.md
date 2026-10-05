# AGENTS.md — MARS

Guidance for any AI coding agent (Claude Code, Cursor, v0, Copilot) working in
this repo. Human-facing docs live in `documentation/frontend/`; the rendered
visual system is the Design canvas linked there. **This file is the short,
non-negotiable layer. The full reference is `frontend/DESIGN.md`.**

MARS is a desktop scientific workstation that predicts ADMET endpoints for drug
molecules. It talks to a FastAPI service. Frontend stack: Vite + React 18 + TS;
CSS Modules over a token layer (`src/styles/tokens.css`, ADR-016 — Tailwind is
not installed); source-owned components over Radix. Do **not** add Next.js, a
component library with its own theme, or a charting library.

## The one rule that outranks the others

The UI must never imply a capability the model does not have. MARS has no
validated risk threshold and no validated direction-of-good. Therefore **no
predicted value is ever coloured by magnitude, ranked, scored, or called good /
safe / favourable / better.** Reliability (out-of-domain, stub-served,
not-returned) is a *separate visual channel* from the value and never recolours
it.

## Never do these (an AI UI will reach for every one — reject them)

1. Colour, bold, dim, or strike a predicted value by its magnitude. The value
   cell is `mono, tabular, --text-primary`, always, in every row state.
2. Add a `variant` / `tone` / `severity` / `status` / `highlight` prop to
   `EndpointRow`, or any "LOW RISK" / "HIGH" style badge. Row state is *derived*
   inside the component from the contract, never passed in.
3. Rank, sort by favourability, or mark a winner in Compare.
   `per_endpoint_winner` is not consumed. Raw numeric sort is allowed and is
   clearly a raw sort.
4. Draw an interval bar on an unbounded axis. Regression endpoints print the
   interval as text. `IntervalTrack` and `ADGauge` require an explicit `domain`
   with **no default** — this is the type-level guard against inventing a scale.
5. Hide an endpoint the service did not return. Absence is a `NOT RETURNED` row,
   never a gap. The full roster renders every time, reconciled client-side.
6. Show a stub / sample value without the diagonal hatch.
7. Animate a number counting, a row entering, a chart drawing itself, or a
   skeleton shimmer. Workspace switching (keys 1–4, rail) is instant — zero
   animation. (One bounded exception: the AD-gauge marker settles once on first
   render — ADR-013.)
8. Use a tooltip as the only place a state is explained.
9. Introduce Inter / Roboto / system-ui, purple-violet gradients, rounded-xl,
   bento grids, one-card-per-row, or any shadow outside a true overlay. Radius
   ≤ 3px. Dark theme only.

## Roster (resolved 2026-10-01)

14 ML endpoints across 5 ADMET categories (ABSORPTION 5, DISTRIBUTION 2,
METABOLISM 3, EXCRETION 1, TOXICITY 3). `synthetic_accessibility` is
**rule-based**, shown in its own `RULE-BASED` group, and **excluded** from the
endpoint count and from the requested/returned/OOD/stub reconciliation — it is a
computed rule, not a model prediction. Headline count is **14**.

## Workflow that holds the line

- Tokens are the source. No raw hex in a component — reference a CSS custom
  property (`var(--surface-panel)`) from a scoped `.module.css`. Token table:
  `frontend/DESIGN.md`.
- Enforce honesty in the *type signature*, not in review. If a variant would let
  a caller imply something MARS can't support, the variant must not exist.
- Generate against this system (point v0 / tooling at the Storybook, not a blank
  prompt), then **audit against the "Never do" list above before merge.**
- Contract types mirror `contracts/mars_contracts`; drift is a build failure
  (ADR-009). `frontend/src/types/contracts.ts` now includes
  `EndpointPrediction.model_id` (ADR-017); the CI drift check is still unwritten.

Full rationale for every rule: `documentation/frontend/` (UX_PRINCIPLES,
DECISIONS ADR-001…015, COMPONENTS, DESIGN_SYSTEM, CRAFT_AND_INTERACTION).
