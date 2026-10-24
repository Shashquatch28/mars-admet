# MARS frontend decision log

ADR format: decision, rationale, rejected alternatives, consequences.
Newest last. Every entry is from the design phase and is reversible until
implementation starts.

---

## ADR-001 — Vite + React SPA, not Next.js

**Date:** 2026-09-30 · **Status:** accepted (pass 1)

**Decision.** Keep the existing Vite + React 18 + TypeScript stack. Do not
adopt Next.js or any SSR framework.

**Rationale.** MARS has no public surface to index, no marketing pages and no
server-rendered content. Auth is an opaque server-side session in an HttpOnly
cookie (Module 13) — there is no JWT for a Node layer to verify. Serving is
Cloud Run on a $0 budget; a second runtime is a second cost and a second
deployment. Vite emits a static bundle the API container or a CDN can serve.

**Rejected.** *Next.js* — real benefits (RSC, route handlers, image
optimisation) all target problems MARS does not have, at the cost of a second
auth boundary and runtime. *Remix* — same. *Plain SPA with no router* —
Router 6 is already pinned and four workspaces need real URLs.

**Consequences.** Deep links work via client routing; the server needs an
SPA fallback route. No SEO. Initial bundle size becomes a budget to watch.

---

## ADR-002 — Source-owned components over Radix primitives, not a component library

**Date:** 2026-09-30 · **Status:** accepted

**Decision.** Copy component source into `frontend/src/components/` in the
shadcn/ui manner, built over Radix (or Base UI) primitives, styled with
Tailwind v4 semantic tokens.

**Rationale.** Two MARS-specific reasons beyond the general ownership
argument. First, scientific honesty is best enforced in a component's type
signature — a MARS `ReliabilityTag` must not be able to render a green "LOW
RISK" chip, and removing that possibility requires owning the source. Second,
AI-assisted iteration is reliable against explicit local source with named
variants, and unreliable against a themed dependency API.

**Rejected.** *MUI / Mantine / Ant* — heavy theming layers, opinionated
aesthetics that fight the instrument-panel direction, and variants we would
spend the project suppressing. *Fully hand-rolled* — focus trapping and ARIA
wiring for dialog and popover are exactly the work worth not redoing.

**Consequences.** Component updates are manual. Accessibility of primitives is
inherited; accessibility of MARS components is ours.

---

## ADR-003 — IBM Plex as the single type family

**Date:** 2026-09-30 · **Status:** accepted

**Decision.** IBM Plex Sans (interface), IBM Plex Sans Condensed (micro-labels
and tags), IBM Plex Mono (every number, SMILES and identifier).

**Rationale.** Plex was drawn for technical products, has true tabular figures
in both sans and mono, and its condensed cut gives dense column headers real
character without a second family. One family in three widths reads as a
system; three unrelated families read as a moodboard.

**Rejected.** *Inter* — the default of every generated dashboard; using it
would undercut the anti-generic goal before a single pixel of layout. *Roboto,
Arial, system-ui* — same problem, less character. *A display serif paired with
a sans* — correct for editorial work, wrong for an instrument panel; there is
no display type in MARS at all. *JetBrains Mono for numerals* — good face, but
pairing it with Plex Sans gains nothing over Plex Mono and loses the shared
metrics.

**Consequences.** Three Google Fonts families to load, subset to Latin. A
self-hosted fallback should be considered before launch.

---

## ADR-004 — Dark only

**Date:** 2026-09-30 · **Status:** accepted

**Decision.** One theme. No light mode, no theme toggle.

**Rationale.** The semantic colour system is tuned for a dark ground: amber and
cyan both clear 7:1 there and are distinguishable by lightness as well as hue.
Re-tuning five semantic colours for a light ground doubles the surface on which
a colour could accidentally imply a judgement, and MARS's audience works in
dark technical tooling by default.

**Rejected.** *Light mode at launch* — cost now, unclear demand. *A toggle with
an untuned light palette* — the worst option; it ships a palette nobody
validated.

**Consequences.** Printing and PDF export (`/molecule/{id}/report`, M4) need a
separate light treatment. That is a report design problem, not an app theme,
and is deferred with that framing.

---

## ADR-005 — Interval tracks only on bounded axes

**Date:** 2026-09-30 · **Status:** accepted

**Decision.** Draw the interval as a track-and-tick only where the axis is
genuinely bounded — today, classification probabilities on 0–1. Every
regression endpoint prints the interval numerically instead.
`IntervalTrack` requires an explicit `domain` prop with no default.

**Rationale.** Drawing a bar requires a scale. MARS has no validated display
range for logS, logP, Caco-2, PPB or clearance. Choosing one — from the
training set's range, say — would encode an unvalidated claim about what
"high" means for that endpoint, in the one channel users read fastest. The type
signature makes this unskippable rather than a convention.

**Rejected.** *Normalise to the training-set range* — invents a scale the model
does not have. *Normalise per result set* — the same bar would mean different
things on different molecules. *Draw a relative-width spread bar* — visually
suggests comparability between endpoints that do not share units.

**Consequences.** Regression rows are numerically denser and less scannable
than classification rows. That asymmetry is honest and is left visible. If a
per-endpoint display domain is ever validated, this ADR is superseded (Q3).

---

## ADR-006 — Reliability and magnitude are separate visual channels

**Date:** 2026-09-30 · **Status:** accepted

**Decision.** Reliability markers (OOD, stub, not-returned) use the row's 2px
left edge and a text tag. They never recolour, embolden, strike through or
otherwise restyle the value. Selection uses a different CSS property again, so
model state and user state cannot overwrite each other.

**Rationale.** Colouring a value amber because it is out of domain reads as
"this value is bad", which is a claim about the molecule rather than about the
model's coverage. Since MARS has no risk threshold, no such claim is available
to make.

**Rejected.** *Amber value text for OOD* — conflates unreliable with
unfavourable. *Dimming or striking through OOD values* — implies the value is
void when it is simply unreliable. *A single "status" colour per row* —
collapses two orthogonal facts.

**Consequences.** Rows carry more distinct marks than a conventional dashboard
row. That is the intended density.

---

## ADR-007 — `per_endpoint_winner` is not consumed

**Date:** 2026-09-30 · **Status:** accepted

**Decision.** The Compare workspace ignores `CompareResponse.per_endpoint_winner`
entirely. No winner, no rank, no ordering by favourability, and no
`CompareEndpointRow` prop that could express one.

**Rationale.** The contract's own docstring says direction-of-good is
endpoint-specific and "the resolution table is finalised in M3/M4", and the
field is nullable with "None = not computed". Rendering a winner from a field
the backend itself describes as unresolved would fabricate the single most
consequential claim in the product.

**Rejected.** *Render it when non-null* — the field being populated is not
evidence the direction table was validated. *Render it behind a disclaimer* —
users read the highlight, not the disclaimer.

**Consequences.** Compare is descriptive: side-by-side values with identical
row grammar. If direction-of-good is validated later, this is revisited as its
own decision with its own evidence (Q5).

---

## ADR-008 — The full endpoint roster is always rendered

**Date:** 2026-09-30 · **Status:** accepted

**Decision.** The client holds the canonical endpoint roster from
`ENDPOINT_METADATA` and reconciles every response against it, synthesising a
`not_returned` row for anything absent from `predictions[]`. Workspace headers
print the reconciliation: requested, returned, out of domain, stub-served.

**Rationale.** Per-endpoint model coverage is genuinely partial and changes
over time (`API_ROUTES.md`: some endpoints promoted, others on the stub). A UI
that renders only what came back makes a partial result indistinguishable from
a complete one.

**Rejected.** *Render the response as-is* — silent omission. *Show a single
"some endpoints unavailable" banner* — tells you that something is missing but
not what, which is the only part that matters.

**Consequences.** The roster is client-side state that must track the contract.
Drift between `ENDPOINT_METADATA` and `contracts.ts` becomes a UI correctness
bug, which is why ADR-009 exists.

---

## ADR-009 — Contract drift is a build failure

**Date:** 2026-09-30 · **Status:** proposed

**Decision.** `frontend/src/types/contracts.ts` must be checked against
`contracts/mars_contracts` in CI. Drift fails the build rather than producing a
review comment.

**Rationale.** The drift is already real: `contracts.ts` is missing
`EndpointPrediction.model_id`, added to the Python contract in M3 and required
by ADR-008's stub detection. `frontend/README.md` states the UI depends on that
field. The file's own header predicted this failure mode.

**Rejected.** *Hand-sync at handoff* — already demonstrably insufficient.
*Generate TypeScript from the OpenAPI schema* — attractive and possibly
correct, but it is an implementation-phase decision with its own tradeoffs;
noted rather than settled here.

**Consequences.** Needs a CI job that does not exist yet. Not fixed in this
design-only pass; tracked as Q10.

---

## ADR-010 — Sample and stub values carry a hatch, not a colour

**Date:** 2026-09-30 · **Status:** accepted

**Decision.** Any value not produced by a promoted model — `model_id ==
"stub-v0"`, demo fixtures, design prototypes — is marked with a diagonal hatch
texture. Design artboards additionally carry a full-width prototype strip.

**Rationale.** "Not real data" is a different kind of fact from "unreliable" or
"failed", and giving it a colour would place it on the same scale as the
semantic states. A texture sits outside that scale, survives greyscale
printing, and is visible in a screenshot pasted into a paper draft — which is
exactly where a stub value would otherwise do damage.

**Rejected.** *A grey value* — indistinguishable from a muted or disabled
state. *A dedicated colour* — implies a severity ranking against the other
semantic colours. *A tooltip only* — invisible in screenshots and exports.

**Consequences.** Hatch must be legible at 8.5px tag size and must not moiré at
common zoom levels. To be checked during implementation.

---

## ADR-011 — The machined highlight is allowed; drop shadows still are not

**Date:** 2026-10-01 · **Status:** accepted (pass 2)

**Decision.** Add `--highlight-machined: inset 0 1px 0 rgba(255,255,255,0.04)`
to the selected row and the active nav item. Nowhere else. Drop shadow remains
restricted to true overlays.

**Rationale.** Pass 1's flat fills read as wireframe. An inset top highlight is
categorically different from a drop shadow: a shadow asserts that an element
floats above the plane, which is what ADR-006's no-floating-cards rule
forbids; a highlight asserts that a surface is catching light, which deepens
the hairline elevation model instead of replacing it. It buys material quality
at zero cost to the information architecture.

**Rejected.** *A border on selected rows* — competes with the accent ring and
the reliability edge, both already at that boundary. *A brighter fill* —
reduces value contrast in the cell that matters most. *Applying it to all
panels* — it would stop meaning "this one is active" and become texture.

**Consequences.** Two `box-shadow` layers on a selected row; the highlight
needs `-1px` spread to clear the ring's own pixel. Worth checking on
non-retina displays, where a 4% white line can disappear.

---

## ADR-012 — The AD gauge is a sibling of IntervalTrack, not an instance of it

**Date:** 2026-10-01 · **Status:** accepted (pass 2)

**Decision.** Introduce `ADGauge(value, threshold, domain)` alongside
`IntervalTrack(low, high, value, domain)`. Both are built on a shared
`BoundedTrack` geometry primitive. Both require an explicit `domain` with no
default.

**Rationale.** The pass-2 brief asked to reuse `IntervalTrack` for the
applicability-domain readout. The two marks encode different things:
`IntervalTrack` draws an interval, `ADGauge` draws a reading against a
reference threshold. Forcing one API to serve both means either synthesising a
fake interval from a threshold, or adding optional props that silently change
what the mark means — exactly the ambiguity ADR-005's required `domain` exists
to prevent. Sharing the geometry keeps them visually identical where it
matters; splitting the API keeps each one honest about what it draws.

**Rejected.** *One component with a `mode` prop* — the mode would change the
semantics of `value`, which is how a component starts lying. *Rendering the
gauge as an interval from 0 to the distance* — implies a range where there is a
point estimate.

**Consequences.** Two components to keep visually in sync; the shared
`BoundedTrack` is what prevents drift. 5-NN distance is currently the only
non-probability axis in MARS that qualifies for either.

---

## ADR-013 — One bounded exception to "nothing draws itself"

**Date:** 2026-10-01 · **Status:** accepted (pass 2)

**Decision.** The AD-gauge marker eases to its placed position on first render
of an endpoint's detail, using the spring (`duration 0.5, bounce 0.15`). The
track, covered zone and threshold tick are drawn instantly. It does not repeat
on re-render, and under `prefers-reduced-motion` the marker is placed with no
animation.

**Rationale.** `UX_PRINCIPLES.md` §8 forbids charts drawing themselves, and
this is the only sanctioned crossing of that line. The distinction: a chart
drawing itself withholds information over time, which is what makes it
objectionable in a scientific tool. A single marker settling into a position
where every other mark is already drawn withholds nothing — the axis, the
covered zone and the threshold are all present from frame one, and the
marker's final position is the only thing in motion. It draws the eye to the
one reading on the screen that users most need to notice.

**Rejected.** *No animation at all* — defensible, and the reduced-motion path
proves the UI works without it. *Animating the covered zone too* — that would
genuinely be a chart drawing itself. *Repeating on every render* — turns a
one-time cue into a tic.

**Consequences.** The rule is now "nothing draws itself, except one marker,
once". That is a narrower rule to state and an easier one to police than a
blanket ban with undocumented drift. Any request to extend it needs its own ADR.

---

## ADR-014 — The endpoint name rests at --text-primary (reversal)

**Date:** 2026-10-01 · **Status:** accepted (pass 2.1) · **Supersedes** the
pass-2 version of this ADR, which demoted the name to `--text-secondary`

**Decision.** Endpoint names rest at `--text-primary` and stay there in every
interaction state. Values likewise. Hover's affordance is the surface lift
(`#0B0D0E` → `#101315`) plus the row-rule brighten (`#14181A` → `#1E2427`).

**Rationale for the reversal.** The demotion treated the endpoint name as a
field label. It is not — it is the **row identifier**, the first-column address
a reader scans to locate a row. Table practice keeps the row identifier
prominent and demotes only field labels and column headers, which in MARS means
units, the `REG`/`CLS` glyph, column heads and the source readout; those
already rest at `--text-tertiary` and stay there. In a 1,000-row batch grid the
identifier column does the most scanning work in the product, and dimming it
taxes the primary task to pay for a hover effect.

The original problem was real — pass 1's hover had nowhere to go — but the fix
was aimed at the wrong element. Moving the surface solves it without touching
type contrast at all, which is the stronger rule: **no interaction state changes
the contrast of any text.** That now holds absolutely, rather than holding for
values and not for identifiers.

**Rejected.** *Keeping the demotion and accepting the scanning cost* — the cost
lands on the densest, most frequent workflow. *Giving hover an accent-tinted
surface* — accent means interaction, but a tinted row edges toward selection,
which already owns the stronger surface step.

**Consequences.** Hover and selection now share `background` with a precedence
rule (selection wins). That is a precedence relationship between two *user*
channels and does not weaken the invariant that matters: user channels never
touch the left edge or the value cell. The channel table in
`CRAFT_AND_INTERACTION.md` §3 is updated to state this explicitly rather than
claiming four strictly disjoint properties.

---

## ADR-015 — Artboard responsibility split: data states vs interaction states

**Date:** 2026-10-01 · **Status:** accepted (pass 2.1)

**Decision.** The **Semantic state language** artboard owns the six
data/contract states only: `in_domain`, `out_of_domain`, `stub_served`,
`not_returned`, `rule_based`, and the selected+OOD compound case. The
**Interaction & motion** artboard owns the entire interaction taxonomy —
default, hover, focus, active, primary, disabled — plus motion and robustness.

**Rationale.** Pass 2 added an interaction-states panel to the Interaction
artboard without removing the one already on the States artboard, leaving two
boards asserting the same taxonomy with different content. Two sources of truth
for one taxonomy is worse than either one alone: a reviewer cannot tell which is
current, and the two drift silently.

The split is along a real seam. Data states come from the contract and are the
same whoever is looking; interaction states come from the pointer and keyboard
and belong with the motion that expresses them. The compound case
(selected + OOD) stays on the States board because its whole point is that a
*data* state survives a user state untouched.

**Rejected.** *Keeping both and cross-referencing* — the drift problem is the
problem. *Moving the compound case to the Interaction board* — it demonstrates a
contract guarantee, not an interaction.

**Consequences.** The States board now carries an explicit pointer to the
Interaction board for the interaction taxonomy, so a reader who expects it there
is redirected rather than left guessing.

---

## ADR-016 — Implementation styling: CSS Modules over the token layer

**Date:** 2026-10-01 · **Status:** accepted (M4 scaffold)

**Decision.** Style components with **CSS Modules** that consume the CSS custom
properties in `src/styles/tokens.css`, rather than Tailwind utility classes.
Tailwind v4 is not installed in this pass. This narrows the styling half of
ADR-001/ARCHITECTURE (which anticipated Tailwind v4 semantic tokens); the token
layer, the "no raw hex in a component" rule, and the agent-editability goal are
all preserved — just expressed as `var(--token)` in a scoped `.module.css`
instead of `bg-surface-panel`.

**Rationale.** The instrument surface is pseudo-element and precise-grid work —
the 2px reliability edge, the machined bevel (`inset … -1px`), the bounded-track
geometry, the dense row grid. In Tailwind those become long arbitrary-value
strings, which ADR-001's own "no arbitrary values" lint would ban anyway. CSS
Modules keep the mechanics readable and scoped, keep raw hex out of components
(everything references a token), and remain straightforward for an agent to edit.

**Rejected.** *Tailwind utilities for everything* — verbose and arbitrary-value
heavy for this UI; higher risk of silent visual drift. *A single global
stylesheet* — loses scoping. *Styled-components / CSS-in-JS* — a runtime cost and
a second styling model.

**Consequences.** Tailwind can be reintroduced for utility-heavy surfaces (Batch
filters, forms, Compare) later without disturbing these components. If it is, the
`@theme` tokens must be generated from `tokens.css`, which stays the source.

---

## ADR-017 — Predict workspace implemented against the contract; contracts.ts drift fixed

**Date:** 2026-10-01 · **Status:** accepted (M4 started)

**Decision.** The Vite + React + TS app is scaffolded and the **Predict**
workspace is built for real: shell (rail, top bar, status bar, ⌘K palette),
the endpoint roster with the six derived row states, the AD gauge, the inspector,
and full keyboard roving. Batch / Compare / Library are routed placeholders.
`frontend/src/types/contracts.ts` now mirrors the Python contract **including
`EndpointPrediction.model_id`**, which closes the drift ADR-009 flagged (Q10).

**Rationale.** The design is locked (passes 1–2.1); the interaction claims
(spring-retarget, asymmetric motion, gauge settle) can only be judged running.
Building against the contract now, with fixtures, makes the only remaining step
to go live swapping the fixture for a `/predict` response — the roster, state
derivation and reconciliation already come from `ENDPOINT_METADATA`, not the
response (ADR-008).

**Rejected.** *Wait for the API wiring first* — the component layer is the long
pole and is contract-shaped already. *Keep iterating comps* — diminishing returns
once the grammar is locked.

**Consequences.** `deriveRowState` is the single pure trust-decision function and
wants unit tests against the same fixtures the API tests use. The CI drift check
(ADR-009) is still not written — the mirror is now correct but kept in sync by
hand until it exists. The AD-gauge threshold is not in the response (see
OPEN_QUESTIONS Q19).

---

## ADR-018 — Data layer: TanStack Query, with a fixture fallback

**Date:** 2026-10-01 · **Status:** accepted (M4); implementation superseded in part
2026-10-07: Run is a mutation held in `src/app/predictSession.tsx`
(`fetchPrediction` in `src/data/client.ts`), not a `usePrediction` query, because
the server owns the 48 h cache and the client keeps no second one. `src/data/usePrediction.ts`
never shipped; the fixture fallback and the `VITE_API_BASE` switch are unchanged.

**Decision.** `/predict` is fetched through `@tanstack/react-query`
(`src/data/usePrediction.ts` over a typed `src/data/client.ts`). The query is
**disabled unless `VITE_API_BASE` is set**, so the default build runs on the
fixture with zero network. When the base is set, the hook drives the real result;
the roster, state derivation and reconciliation still come from
`ENDPOINT_METADATA`, never the response (ADR-008). The session cookie is sent
with `credentials: "include"` (HttpOnly, Module 13) — no token handling on the
client.

**Rationale.** The API already has a 48h cache and a `cache_hit` flag; a client
cache must not contradict it, which is exactly what react-query's keying and
`staleTime` give for free. ARCHITECTURE pre-selected it. The fixture fallback
keeps the UI demoable and testable without a running backend, and makes going
live a one-line env change rather than a rewrite.

**Rejected.** *Plain fetch + useEffect* — re-implements caching, dedup and
request state worse. *SWR* — equivalent; react-query was already the pinned
choice. *Always hit the API* — breaks the offline/demo path and every test.

**Consequences.** The prototype strip is now gated on `isSample` (fixture, or no
real response yet) rather than always on. Loading renders placeholder rows at the
roster's known heights (no reflow, no shimmer); a failed request shows an inline
error with the status code. The `ad_threshold` the gauge needs is read from the
response when present and falls back to a local table (Q19). *Superseded by ADR-020: the field is in the
contract and the local table is gone.*

## ADR-019 — The API computes the rule-based SA score; the UI keeps NOT RETURNED honest

**Date:** 2026-10-06 · **Status:** accepted (resolves Q2 live-mode gap)

**Decision.** `synthetic_accessibility` is computed server-side with RDKit's
Ertl & Schuffenhauer scorer (`ml/serve/rule_based.py`) and returned in
`/predict` whenever the ml stack is present. `endpoints=None` now means all 15
enum members. Where the stack is absent (the root `.venv` dev loop) SA is
omitted — never stubbed — and the UI shows NOT RETURNED, which is then true. The
UI is unchanged: `deriveRowState` still checks "no prediction" first.

**Rationale.** The roster is 14 ML endpoints + 1 computed rule (Q1). The API
never returned SA on any path, so against the live service its row would have
claimed the service failed to return something it never computed. The blueprint
lists SA as a computed feature; computing it fills the gap rather than
redefining the row.

**Rejected.** *A distinct "not computed" UI state* — it would permanently
display an absence that the backend can simply remove, and adds a seventh row
state for a case that should not occur. *A stub SA value* — fabricates a number
for a rule that is cheap to compute for real. *Client-side RDKit (WASM)* — a
heavy dependency for one number, and it splits the source of truth.

**Consequences.** The contract has no "no interval / no domain" shape, so SA is
returned with `confidence_low == confidence_high == value`, `in_domain=true`,
`knn_distance=0.0` and `model_id="rdkit-sascore"`. These are neutral
placeholders; the UI keys off the endpoint's `RULE_BASED` task type and never
draws an interval or domain for it. **Deploy note:** cached `/predict` responses
are keyed by `MODEL_VERSION`; bump it (or flush Redis) on release or 14-entry
responses are served for up to 48 h.

## ADR-020 — The AD threshold travels with the prediction (resolves Q19)

**Date:** 2026-10-06 · **Status:** accepted (M4)

**Decision.** `EndpointPrediction` gains `ad_threshold: float | None` (additive, default `None`). It is the cutoff
`in_domain` was judged against: the 90th percentile of the endpoint's training set's own leave-one-out 5-NN distances
(Module 5), read from the endpoint's AD index (`ADIndex.threshold`) at serve time, so `in_domain == (knn_distance <=
ad_threshold)` holds by construction. It is `null` for stub-served and rule-based rows, which have no AD index.
`contracts.ts` mirrors it as `number | null` (required, since the API always sends it). The local `AD_THRESHOLD`
table in `domain/endpoints.ts` is deleted.

**Rationale.** Q19 option (a): the number travels with the value it describes, cannot drift from the index that
produced the flag, and needs no second request or pinned table. The ML side already held the real value.

**Rejected.** *A `/metadata` endpoint* — a second source that can disagree with the response it annotates. *A pinned
threshold table* — drifts from the deployed artifacts, which is the exact failure the table was a stand-in for.
*Keeping the 0.58 fallback "just in case"* — on a live response it would draw the gauge tick at an invented position,
which AGENTS.md rule 4 forbids; absence of the number means absence of the tick.

**Consequences.** When `ad_threshold` is `null` the gauge is not drawn; the real `in_domain` boolean and the
out-of-domain explanation in words still show. The fixtures keep an illustrative `0.58` for numeric rows only and say so.
**Deploy note:** `/predict` responses cached before this release lack the field and revalidate to `null` for up to 48 h
(the gauge is hidden on them, never wrong); bump `MODEL_VERSION` on release, as for ADR-019. **Not addressed:** if a
promoted endpoint ever lacks an AD index, `predict_endpoint` returns `in_domain=False` with a NaN distance, which the
UI would read as "outside applicability domain"; all currently promoted endpoints have an index.

## ADR-021 — Status dots are circles; the radius cap governs surfaces

**Date:** 2026-10-07 · **Status:** accepted (M4)

**Decision.** `border-radius: 50%` is permitted on 6px status indicators (`.dot` in `shell.module.css` and
`batch.module.css`). The ≤3px radius rule (`--radius`, `--radius-sm`) governs *surfaces*: panels, buttons, inputs,
rows, tags.

**Rationale.** The rule exists to keep the product from reading as a soft consumer app (rounded-xl cards, pills). A
6px indicator is not a surface; at 3px radius it renders as a rounded square, which is a different mark from the
circle the locked design drew. HANDOFF §3.4 flagged these as "probably not a violation" and asked for the exception
to be recorded rather than the dots "fixed".

**Rejected.** *Squaring the dots* — changes a locked design to satisfy a rule's letter. *A general `50%` allowance* —
would let any element opt out of the cap.

**Consequences.** `tests/cssGuard.test.ts` checks colour literals only, not radius. If a stylelint radius rule is
ever added, allowlist `.dot`.

## ADR-022 — Auth boundary: gate the capability, not the app (resolves Q7)

**Date:** 2026-10-08 · **Status:** accepted · Phase 1 implemented 2026-10-08 (items 1-8); Phase 2 implemented 2026-10-18 (Batch upload and progress, Library list/delete, delete-account modal; Save is not part of it)

**Decision.**

1. Predict and Compare stay anonymous. Batch and Library require a session, as the API already enforces
   (`/batch/*`, `/molecules` and `/reports` depend on `get_current_user`).
2. All four rail destinations stay visible. Gated ones (Batch, Library) carry a lock glyph. An anonymous user who
   opens one lands in the workspace, which renders an in-workspace sign-in state: why an account is needed, what
   stays free, and the sign-in and create-account forms. No modal, no hidden rail item; keys 1-4 keep navigating.
3. Session state is a frontend context with three values: unknown, anonymous, signed in. The rail is neutral while
   the state is unknown. Any 401 from a gated call drops the app to anonymous and shows the sign-in state in place,
   keeping the user's selected file.
4. Add `GET /auth/me` (returns `user_id` and `email`; 401 without a session), a `MeResponse` model in
   `mars_contracts/auth.py`, a row in `API_ROUTES.md`, and the mirror in `contracts.ts` (ADR-009). The cookie is
   HttpOnly and no whoami route exists, so the client cannot otherwise know whether a session exists.
5. The top-bar account readout is driven by session state. The hard-coded "SK" is removed: anonymous shows
   "Sign in"; signed in shows the user's initial and a sign-out control.
6. Turnstile is not wired in the client for now. The server skips verification when
   `CLOUDFLARE_TURNSTILE_SECRET_KEY` is unset, and the register request sends a placeholder token. If the app is
   ever deployed publicly: honeypot field and a register rate limit first, then Turnstile (free). Confirmed and
   scheduled as a deploy gate by ADR-034 item 9.
7. MARS launches without account recovery (decided 2026-10-19). `/auth/password-reset/request` issues a token but
   Resend delivery is not wired, so a reset form would promise an email that is never sent. The sign-in form says
   in plain text that there is no password recovery and that a forgotten password loses the account. The two
   `/auth/password-reset/*` routes stay in the API, unused by the client, until an email provider exists.
8. Fixture mode (no API configured): Batch keeps working on its sample data, labelled as sample (`isSample`).
   Superseded by ADR-032: the app has no fixture mode and shows no sample data.
9. Phase 1 = items 1-8 plus tests. Phase 2, which depends on Phase 1 = live Batch upload and SSE progress, Library,
   and a Settings account section with delete-account behind a confirmation modal (the one modal use that
   INTERACTIONS.md allows).

**Rationale.** The anonymous path is what makes the tool easy to try; accounts exist for the expensive and stored
paths (blueprint Modules 8 and 13). Maintainer context, 2026-10-08: MARS stays a college project with no public
users and no paid services, so abuse and cost controls (Turnstile, rate-limit tuning, budget alerts) are not needed
now. Never-do #8 requires the reason a workspace is gated to be explained in the workspace, not only in a tooltip.
Never-do #5 is about endpoints the service did not return and applies here by analogy only: a gated destination
is shown, not hidden. The top-bar "SK" implied an identity the app did not have.

**Rejected.** *A hard login wall* - contradicts Module 8 (anonymous `/predict`), adds friction for anyone trying the
tool, and still needs session state and 401 handling. *Hiding gated rail items* - the rail would differ by login
state, and keys 2 and 4 (`WS_KEYS` in `AppShell.tsx`) would point at pages the rail does not show. *A modal on
entry* - interrupts the user and is likely to fight the global 1-4 shortcuts.

**Consequences.** One contract addition (`MeResponse`); the drift test covers names. `ARCHITECTURE.md` no longer
calls MARS an "authenticated" workstation, which contradicted Module 8. The anonymous per-IP limit
(`rate_limit_anon_per_minute`, 60) and the blueprint's Module 8 "$7/mo instance" wording are untouched; the latter
is stale against Module 10 ($0 on Cloud Run) and is not corrected here.

## ADR-023 — Classification values are labelled "score" until calibration is validated (resolves Q21)

**Date:** 2026-10-08 · **Status:** accepted · implemented 2026-10-14 (unit text; C0 and C1 are ML work and remain)

**Decision.**

1. Now (option a): the unit text for the nine classification endpoints changes from `probability` to `score` in
   `DISPLAY_UNIT` (`domain/endpoints.ts`) and the fallback in `unitLabel` (`domain/format.ts`). The unit stays
   per endpoint, so each one can return to `probability` on its own. The 0-1 axis (`PROB_DOMAIN`) is unchanged: a
   score is still bounded.
2. Later (option c), in order. **C0**: stop applying the served Platt calibrators (`ml/serve/predictor.py` applies
   `registry.load_calibrator` to each seed) and serve the raw ensemble, behind a switch. **C1**: recalibrate the
   XGBoost side on label-representative data (cross-validated out-of-fold predictions; the frozen calibration
   split is not changed) and validate against raw with ECE, Brier and reliability curves, with a pass bar per
   endpoint. An endpoint returns to `probability` only when it passes. **C2** (KERMT temperature scaling) stays
   GPU-gated and is not on the critical path while the API serves XGBoost.

**Rationale.** The calibration split is not label-representative (CYP3A4: 0.409 positive in train_val vs 0.113 in
calibration), and the `hia_absorption` calibrator was fit on 49 positives and 1 negative. The repo's own
like-for-like comparison on seed 4 (`AIMS/next_steps.md`) finds the served calibrators worse than the raw output on
Brier for 9 of 9 endpoints and on ECE for 7 of 9 (HIA ECE 0.045 to 0.209). Calling the output a probability implies
a calibration MARS has not shown, which is the project's top rule. The live aspirin value of 0.98 is directionally
right (aspirin is well absorbed) but cannot be read as a 98% likelihood.

**Rejected.** *(b) Keep "probability" with per-row caveats* - caveating only the two known cases implies the other
seven are fine; caveating all nine puts a warning on every row. *Fixing the calibrators before relabelling* - leaves
the unsupported claim on screen for the duration of the ML work.

**Consequences.** User-visible text changes in Predict and Batch. The contract description at
`contracts/mars_contracts/prediction.py:25` still says "classification probability [0,1]"; that is a contract
change and is not made here. Some endpoints (HIA with N=47, DILI with 50 calibration rows, hERG) may never pass the
C1 bar and would then stay `score`. Whether the endpoint detail panel also carries a one-line explanation is left to
implementation. ML-side record: `AIMS/decisions.md`, 2026-10-08. Rough effort, not measured: C0 half a day to a day,
C1 two to four working days, C2 weeks of calendar time.

## ADR-024 — Seed spread is not an interval: never flag it, and rename it (resolves Q4)

**Date:** 2026-10-08 · **Status:** accepted (wording implemented 2026-10-14; held-out-error band implemented 2026-10-18)

**Decision.**

1. Seed spread is never flagged as a reliability signal, in either direction (narrow as suspicious, narrow as
   reassuring). This is permanent, not "until conformal prediction lands".
2. The label `ENSEMBLE INTERVAL` becomes `SEED SPREAD ±1σ`. Text only; this also answers Q4's wording question.
3. Planned replacement for the five regression endpoints: a held-out-error band, with a per-endpoint half-width taken
   from the pooled out-of-fold residuals of the five seeds (their scaffold-held-out validation folds), served as new
   contract fields (names to be chosen) and labelled with what was measured, for example "90% of held-out errors fell
   within ±X". This is an optional upgrade: the claims are honest without it. Rough effort, not measured: 1-2 working
   days.
4. Not decided: whether the spread range is hidden on classification rows. The measurements below show it carries no
   information beyond the score, but hiding it touches the locked design (`IntervalTrack` on classification rows), so
   it stays open.

**Rationale.** On the five regression endpoints the printed mean ± 1σ range contained the true value for 9-14% of
held-out test molecules (a 1σ range would be expected to contain about 68%), and the typical error was about 4.7-6.5
times the median printed spread. Spread ranked errors only weakly (rank correlation 0.10-0.62), and in-domain and
out-of-domain molecules had almost the same median spread on three of the five endpoints, so agreement between seeds
is not evidence of being in-domain. On the nine classification endpoints spread is largely a function of the score
itself, and once the score is removed it predicts misclassification at AUROC 0.43-0.63 (chance is 0.5). A band built
from held-out residuals contained 86-93% of test errors at a 90% target. Full tables, method and caveats:
`AIMS/decisions.md`, 2026-10-08.

**Rejected.** *A per-endpoint reference distribution of interval widths* (Q4's first option) - it would describe how
much seeds agree, and the measurements show that is not how large the error is. *Flagging narrow spread as reassuring
or as suspicious* - both claim a calibration that does not exist. *Keeping the `ENSEMBLE INTERVAL` label* - an
"interval" next to a value reads as an error range.

**Consequences.** The original Q4 text says the seeds are "fit to the same ... training set". Each seed trains on a
different scaffold partition of the same train_val pool (`five_seed_train_val_folds`), so the spread includes
partition variance and is still far too narrow. The contract names `confidence_low` and `confidence_high` stay
misleading; renaming them is a breaking contract change and is not made here.

Implemented 2026-10-14. The inspector's own labels were renamed with the column head, because the same reasoning
applies to them: "Interval" is now `Seed spread ±1σ` and "Interval width" is `Spread width` (regression rows), "Ensemble"
is `Seed spread ±1σ` (classification rows), and the rule-based note and the inspector hint say "seed spread".
Spread is still shown on classification rows (item 4 stays open). No code identifier was renamed:
`NumericInterval`, `IntervalTrack`, `fmtInterval` and the contract's `confidence_low` / `confidence_high` keep their names.

Band implemented 2026-10-18 at the 90% level (AIMS `decisions.md` 2026-10-18). Contract fields on `EndpointPrediction`:
`heldout_error_halfwidth`, `heldout_error_level`, `heldout_error_n`, all additive and null when there is no band
(classification, stub-served, rule-based, or a regression endpoint whose band has not been built). The Predict inspector
prints it as text above the seed spread: "Held-out error ±1.68" with a note that says what was measured, that it is one value
for the whole endpoint, and that it is not a guarantee for an out-of-domain molecule. It is never drawn as a bar, never
coloured, and `errorBandOf` returns nothing for a partial or nonsensical band rather than showing half a claim. Batch and
Compare do not show it. Out-of-domain coverage is lower than in-domain at every endpoint but Caco-2, so the domain flag
stays beside it.

## ADR-025 — Production serves the frontend and the API from one origin (resolves Q22)

**Date:** 2026-10-08 · **Status:** accepted · implemented 2026-10-19 (items 1-3; item 5 is code-complete, see its note; item 4, the blueprint amendment, is still the maintainer's)

**Decision.**

1. In production the API container serves the built Vite bundle, with an `index.html` fallback for client routes. The
   browser makes no cross-origin calls.
2. The API is mounted under `/api` in every environment, and the dev proxy stops stripping the prefix, so development
   and production share one path. The prefix is required because four SPA routes (`/predict`, `/batch`, `/compare`,
   `/library`) collide with API routes of the same names. This changes the health-check paths, `API_ROUTES.md`, the
   tests and the CI smoke test.
3. Production settings: `SESSION_COOKIE_SECURE=true`; `CORS_ALLOW_ORIGINS` empty. The cookie stays HttpOnly and
   `SameSite=Lax`. The explicit-origin CORS policy stays for development and for any future split deployment.
4. This departs from blueprint Module 10, which names Vercel for the frontend. The blueprint amendment is the
   maintainer's and is pending.
5. Before the first deploy, verify which client address the anonymous rate limiter sees behind Cloud Run. Checked
   2026-10-19: uvicorn trusts `X-Forwarded-For` only from `127.0.0.1` by default, so behind Cloud Run the limiter
   would see the proxy's address and every visitor would share one 60/min bucket. Fixed in the app, not with
   `--forwarded-allow-ips '*'` (that trusts the forgeable leftmost entry): `TRUSTED_PROXY_HOPS=N` reads the N-th
   entry from the right of the header. Set 1 on Cloud Run. Still unverified on a deployed service: after the first
   deploy, send two requests with different forged `X-Forwarded-For` values and confirm they share a bucket.

**Rationale.** The CORS configuration (explicit origins plus credentials) is correct for a cross-origin deployment,
but it is not sufficient. The session cookie is `SameSite=Lax`, and MDN states that Lax cookies are not sent on
cross-site `fetch()` requests. A Vercel frontend and a Cloud Run API are different sites, so login would appear to
succeed while every gated call returned 401. One origin removes the whole class of problem (CORS drift, cookie site
mismatch, vendor proxy limits) at $0, and ADR-001 already anticipated serving the bundle from the API container.

**Rejected.** *`SameSite=None; Secure` cross-site cookie* - valid, but MDN notes Safari and Firefox restrict
third-party cookies by default. *Vercel rewrite to the API* - documented and same-origin to the browser, but its
documentation says nothing about timeouts, streaming or cookie handling, so batch progress (SSE) is unverified.
*Firebase Hosting rewrite to Cloud Run* - documented 60-second request timeout. *Custom domain with subdomains* - needs
a purchased domain.

**Implementation (2026-10-19).** Every router is included under `/api` (`app/main.py`), and docs move to `/api/docs`. `app/spa.py` serves the bundle when `STATIC_DIR` is set (the image sets it): a real file is served as is (hashed `/assets/*` cached for a year, everything else `no-cache`), an extensionless path gets `index.html`, a missing file is a 404 rather than HTML, and an unknown `/api/...` path is a JSON 404. The Dockerfile is multi-stage (Node builds the bundle with `VITE_API_BASE=/api`, then it is copied beside the API) and starts uvicorn on `$PORT`. The Vite dev proxy no longer strips the prefix. The API warns at start-up if it serves the bundle with `SESSION_COOKIE_SECURE` unset; production sets it to `true` and leaves `CORS_ALLOW_ORIGINS` empty. Tests, the CI smoke test, the compose health check and `API_ROUTES.md` use the prefixed paths.

**Consequences.** The first page load can include a Cloud Run cold start (the blueprint already accepts 1-3 s). The
Dockerfile becomes multi-stage. CI does not deploy yet, so nothing needs migrating. The comment at the top of
`client.ts` (SPA and API must be same-site) remains true and is satisfied by construction.

## ADR-026 — The serving generation is a real, switchable setting (resolves Q6)

**Date:** 2026-10-08 · **Status:** accepted (design). Part 1 implemented 2026-10-14, with a minimal `GET /generations`. Parts 2-5 are blocked until a second
generation exists.

**Decision.**

1. The top-bar control states only what exists. While the API reports one generation it is a plain readout: no button
   role, no tab stop, no chevron. It becomes a picker only when `GET /generations` lists more than one.
2. Its value is the deployed generation reported by the API, not the last prediction's `model_version`, so it is
   populated before the first run. In fixture mode it shows the fixture label and says it is a fixture.
3. The generation is a session-wide setting held in the shell. Switching it re-runs the open Predict molecule against
   the chosen generation, as an explicit action. It does not filter history. Saved molecules keep the version frozen at
   save time (blueprint Module 13). Batch jobs record the generation they ran against. Compare uses the active
   generation for every column.
4. API: `GET /generations` returns `{active, available}`. `/predict` takes an optional `model_version`; a value not in
   `available` is a 422, and the default is `active`. `build_cache_key` takes the requested version instead of reading
   the deployed setting.
5. A generation becomes data: a versioned routing table plus its artifact root. Today it is one settings string and one
   `model_artifact_dir`.

**Evidence (checked 2026-10-08).** `ml/artifacts/` holds 14 endpoint directories. The metadata read
(`caco2_permeability`) names one model, `mars-xgboost-ecfp-desc-v1`, seeds 0-4. The registry layout is
`<endpoint_key>/seed_<n>/` with no generation dimension (`ml/serve/registry.py`). `model_version` is one settings value
stamped onto every response (`prediction_service.py:134`), and the artifacts directory is git-ignored.

**Why this was chosen over the readout-only option.** The maintainer chose it. The cost is accepted: there is no second
generation to switch to. The first candidates are KERMT (GPU-gated, ADR-023 C2) and a retrained XGBoost set, and
neither exists. Parts 2-5 can be tested against two fixture registries, but not against real data.

**Rejected.** *A picker with one disabled entry* - implies a feature that does not exist (never-do #5).

**Consequences.** Touches `ml/serve/registry.py`, `prediction_service.py`, `prediction_cache.py`, a new route,
`API_ROUTES.md`, a new `GenerationsResponse` and a request field in `mars_contracts` and its frontend mirror (the drift
test covers both). The fixtures' `mars-routing@v0.3.1` disagrees with the API default `v0.2.0-dev`. `v0.2.0-dev` is the real string (`Settings.model_version`, which is also the
cache-key tag); `mars-routing@v0.3.1` exists only in the design fixtures, and the top bar labels it a fixture.
Implemented 2026-10-14: part 1, plus `GET /generations` returning `{active, available: [active]}` (contract, frontend
mirror, drift test, `API_ROUTES.md`, one API test). It is not on `/health`, and the registry and cache key are unchanged.

## ADR-027 — Predict gets a structure sketcher: Ketcher, standalone mode (resolves Q9)

**Date:** 2026-10-08 · **Status:** accepted; built 2026-10-23, see ADR-035 (which makes the sync live instead of accept-to-write)

**Decision.**

1. Predict offers "Draw a structure". It opens Ketcher in its own bordered panel (blueprint MVP item 10: a specialised
   instrument, not a re-skin). The SMILES textarea stays the source of truth: accepting a drawing writes SMILES into
   it, and the user still presses Run. Server-side standardisation is unchanged.
2. Standalone mode: Indigo runs as WebAssembly in the browser, so there is no Indigo Service to host.
   `ketcher-core`, `ketcher-react` and `ketcher-standalone` are pinned together.
3. Loaded by dynamic import, so the first load of the app does not pay for it. If WebAssembly is unavailable the panel
   says so (never-do #5) and the textarea still works.
4. The panel interior is third-party. AGENTS never-do #7 (no animation) and #8 (no tooltip-only state) bind MARS's own
   UI; whether Ketcher's interior breaks them is unaudited. Audit when built. Any exception is scoped to the panel
   interior and recorded here.

**Evidence (npm registry and the Ketcher README, 2026-10-08).** Apache-2.0. `ketcher-react` 3.18.0 has peer
`react ^18.2.0 || ^19.0.0`; the project is on 18.3.1. `ketcher-standalone` 3.17.2 depends on `indigo-ketcher` 1.45.1
(WASM), and the README says standalone uses Indigo WASM client-side and that the WASM bundle is larger. Unpacked npm
sizes: `ketcher-react` 29.8 MB, `ketcher-standalone` 109.7 MB. These are tarball sizes, not shipped bundle size, which
is unmeasured. `ketcher-react` depends on `@mui/material` and `@emotion`, a second styling system beside CSS Modules,
and it is not checked against the CSS guard (HANDOFF 3.4).

**Why this was chosen over deferral.** The maintainer chose it. The recommendation was to defer, because the API takes
SMILES and a sketcher can be added without a backend change. The costs are accepted: a heavy dependency, a second UI
system, a longer install and Docker build stage.

**Rejected.** *Deferral to post-MVP.* *JSME* - not evaluated; its licence and size were not checked.

**Consequences.** Measure the lazy chunk and the install and build time on first integration. Run the never-do #7/#8
audit and the CSS-guard check then. The empty-state spec gains the entry point; `PredictEmpty` is not built yet.

---

## ADR-028 — NOT REQUESTED is its own row state, distinct from NOT RETURNED

**Date:** 2026-10-08 · **Status:** accepted (the maintainer chose it; implemented the same day)

**Decision.** When the user runs a subset of the 14 ML endpoints, each endpoint left out stays in the roster as a row
reading `NOT REQUESTED`. `deriveRowState` returns `{ kind: "not_requested" }` for an endpoint with no prediction that
was not in the request, and `{ kind: "not_returned" }` only when it *was* requested. The two are told apart in words
(the value cell) and by edge: NOT RETURNED keeps the solid muted edge, NOT REQUESTED gets a dashed one. Neither has a
tag. The inspector for a NOT REQUESTED row says the user left it out, that this is not a failure, and how to get it.
The rule-based SA score is not selectable, is always part of a request, and is therefore never NOT REQUESTED.

**Rationale.** ADR-008 says every endpoint is rendered, and the subset selector (COMPONENTS: `MoleculeInput`) makes it
possible to ask for fewer. Without a second state the omitted rows would read "requested but the service did not
return it", which is false and would present a user's choice as a service failure. Keeping NOT RETURNED to mean "we
asked and it did not answer" is what ADR-019 relies on: its honesty argument is that NOT RETURNED is never shown for an
absence the service did not cause.

**Rejected.** *Reword NOT RETURNED so it covers both causes* — the one fact worth knowing, why it is absent, is
exactly what is lost. *Hide the omitted rows* — breaks ADR-008 and never-do #5. *Treat every absence as NOT RETURNED
and rely on the header count* — the count says how many, not which. ADR-019 rejected a "not computed" state because
the backend could simply remove that absence; this one differs: the absence is the user's choice and nothing the
backend does can remove it.

**Consequences.**
- `reconcile(response, requested)` derives the state from the request that was made. `PredictSession` records
  what each run sent (`TimedPrediction.sent`), so the roster follows the last run, not the selector's current ticks;
  changing the selector never relabels a result already on screen. `requested` is a fact about the request, not a
  presentational prop (never-do #2 still holds: `EndpointRow` has no `variant`, `tone`, `severity`, `status` or
  `highlight`).
- The header counts already reconcile: `requested` is the number asked for. A subset of 2 reads
  "2 requested · 2 returned".
- `Reliability` gains `notrequested`; `ReliabilityTag` is an exhaustive switch, so a further state cannot be added
  without deciding its tag.
- Edge style is a structural channel, not a colour: the dashed edge uses the same `--line-strong` as NOT RETURNED and
  survives greyscale.
- Docs changed with it: COMPONENTS (`ReliabilityTag` row, `EndpointRow` states), ACCESSIBILITY (both lists),
  UX_PRINCIPLES §3, DESIGN_SYSTEM (`--unavailable`).

---

## ADR-029 — The report is a print-only light document built in the client; PDF is the browser's "Save as PDF"

**Date:** 2026-10-19 · **Status:** accepted · implemented 2026-10-19 (ship checklist D5)

**Decision.**

1. Predict (Report button beside Export) and Batch (Report in the inspector) open one molecule's report through the
   browser's print dialog. The report is a `ReportModel` (`domain/report.ts`, pure, from the same `ExportMolecule` the CSV
   uses) rendered by `PrintReport` into a portal on `document.body`. On screen it is `display: none`; in print it is the
   only thing shown and `#root` is hidden. "Save as PDF" in the print dialog produces the PDF; the page title is set to
   `MARS prediction report <molecule id>` for the duration, which is the file's default name.
2. The report is a separate light treatment (ADR-004 deferred exactly this): ink on paper from `--report-*` tokens,
   no semantic colour. Reliability is carried by words (Status column), a left edge (solid for OUT OF DOMAIN, solid
   muted for NOT RETURNED, dashed for NOT REQUESTED) and, for a stub value, the diagonal hatch, which prints because
   the report sets `print-color-adjust: exact`.
3. It prints what the screen says and nothing more: the full roster including NOT RETURNED and NOT REQUESTED rows
   (ADR-008), the value in one ink in every state, seed spread and held-out error as text (ADR-024), applicability domain
   as a distance and cutoff in words, the served model per row, and the requested / returned / out-of-domain /
   stub-served / not-returned counts. A fixed "How to read this report" block (scores are not probabilities, no validated
   threshold or direction of good, what spread and held-out error are, what out of domain and stub mean, that every
   endpoint is listed, what is not included) is printed on every report.
4. Report is offered for a real result only, under the same condition as the CSV export: never the illustrative sample,
   never after a failure. A Batch row that failed before inference prints its reason and no table.
5. The blueprint's `GET /molecule/{id}/report` (server-side PDF) is **not built**. See rationale.

**Rationale.** The honesty rules live in the client: `deriveRowState` and `reconcile` decide what each row is and
guarantee the NOT RETURNED rows. A server-side PDF would need a second copy of that logic in Python, and the two would
drift (ADR-009 exists for the same reason). A PDF library would also be a new dependency to install, pin and audit,
and its output could not reuse the screen's formatters. The browser already makes a faithful PDF from a print stylesheet.
This departs from the blueprint's wording ("Per-molecule PDF"); the deliverable is the same file, made by the browser.

**Rejected.** *Server-side PDF (reportlab or similar)* - duplicates the reconcile logic and adds a dependency. *A
client-side PDF library* - same dependency cost, and no better than the print engine. *Printing the live workspace* -
it is a dark, fixed-height, overflow-hidden surface with controls in it. *Colouring rows on paper* - the semantic
colours imply a scale (never-do #1); paper gets words, edges and a hatch.

**Never-do audit.** (1) value cell is `--report-ink`, mono, tabular, in every state; (2) no prop on `EndpointRow`
(it is not used); (3) nothing ranked or sorted; (4) no interval bar, intervals are text; (5) all 15 roster rows print,
absence is a row; (6) stub values carry the hatch and the word STUB; (7) nothing animates; (8) every state is in
words in the table, none only in a tooltip (the report has no tooltips); (9) no shadow, radius 2px, light only for the
report as ADR-004 required.

**Consequences.** Not included, and said so on the page (the 2D drawing was added by ADR-039; the line now appears only when the service could not draw one): a 2D structure drawing (the service had no depiction route and
the 3D viewer is not printable) and drug-likeness flags (the service does not compute them). Adding either is a new
service capability first. The report cannot be previewed on screen except through the browser's print preview. The
frontend tests cover the model (`report.test.ts`: roster completeness, no marker inside values, hatch only on stubs,
NOT RETURNED versus NOT REQUESTED, no favourability wording, counts agree with the screen); the rendered layout was
checked in a browser against a live API with the print stylesheet applied.

---

## ADR-030 — Accessibility pass: AA text tokens, scroll instead of block, a switch for the 1-4 keys

**Date:** 2026-10-19 · **Status:** accepted · implemented 2026-10-19 (ship checklist D6)

**Decision.**

1. **Text tokens are AA on every surface.** `--text-quiet` becomes `#848F92` and `--error` `#E06861`. An audit of the
   running app found readable information in `--text-quiet` (3.5-4.4:1: the held-out-error explanation, the "illustrative,
   not model output" note, key hints) and in `--text-disabled` (3.2:1: row numbers, the `-N` not-returned flag, group
   counts), and error text under 4.5:1 on the dialog surface. `--text-disabled` is now for disabled controls only
   (WCAG exempts them) and a test enforces it.
2. **Narrow windows and high zoom scroll; nothing is blocked.** The blocking "minimum width" notice is replaced by a
   1080px canvas that scrolls sideways, with a one-line note. This amends RESPONSIVE_STRATEGY ("a blocking notice
   rather than a broken layout"): at 200% browser zoom on a 1440px screen the viewport is 720 CSS px, the notice
   replaced the whole app, and zoom users could not use it at all (WCAG 1.4.4, 1.4.10).
3. **The 1-4 keys can be turned off** (WCAG 2.1.4): Settings, Keyboard, "Single-key shortcuts", on by default, remembered
   in this browser. The alternative (require Alt+1-4) was declined because it changes the documented keys.
4. **Structure and announcements.** One `<main>`, a skip link, an `h1` per workspace and `h2` endpoint groups, per-workspace
   page titles, a valid ARIA grid on Predict (headers inside the grid, `gridcell`s, `aria-activedescendant`), one polite
   live region for "prediction complete" and batch start / quarters / finish, errors linked to their fields, a 24px
   minimum target size.

**Rationale.** WCAG 2.2 AA is the stated target (ACCESSIBILITY.md) and the doc already listed live regions, error
association, headings and focus return as specified but not built. The audit measured the rest.

**Rejected.** *Keep the block and record an exception* - fails 1.4.4 for exactly the users who need zoom. *Alt+1-4* -
see above. *Announce every batch progress event* - the service reports every half second; a screen reader would
talk over everything. *A new dependency (axe, jsx-a11y)* - not needed to catch the measured failures; the guards and
the audit script cover them, and a dependency can be added later.

**Consequences.** The `--text-quiet` rung of the hierarchy is nearly the same as `--text-tertiary`, so quiet text is
slightly brighter than designed. `--error` is a touch lighter. The app now scrolls at narrow widths instead of
refusing to run, which means small screens get an unrefined layout rather than a notice. Predict's rows carry no
`aria-rowindex` any more (not virtualized, and the old values did not match the group rows between them). Not done:
screen-reader testing, the Ketcher panel, the Batch grid's keyboard model (see ACCESSIBILITY.md, "Not built or not checked").

## ADR-032 — Nothing on screen is invented: the no-API prototype mode and the palette's sample molecules are removed

**Date:** 2026-10-20 · **Status:** accepted · implemented 2026-10-20 (demo-readiness pass)

**Decision.**
1. The app renders only what the service returned. The no-API "design prototype" mode is removed: no `FIXTURE_RESPONSE` on
   Predict, no 240-molecule sample on Batch, no placeholder 3D geometry, no "design prototype" strip, no `isSample` state, no
   `· fixture` serving label. With no `VITE_API_BASE` each workspace says there is no API and shows placeholders or an empty grid.
   Production and dev both set `VITE_API_BASE=/api`, so this only changes a build made without it.
2. The fixtures survive for tests only, in `src/testSupport/`. `tests/noHardcodedGuard.test.ts` fails if runtime code imports
   them, names a sample molecule, or ships a `<button>` with no handler, no `disabled` and no submit type.
3. The ⌘K palette lists only real things. Endpoints come from the fixed roster, with reliability tags taken from the last real
   result (none before one exists). The one molecule it can offer is the one Predict last returned; it keeps no history and invents
   none. Commands are Run prediction, Copy molecule_id, Export Predict result (CSV) and Toggle density; one that cannot run is
   listed with the reason beside it (not a tooltip) and does nothing when chosen. The leftover "transform-origin" note in its
   footer is gone.
4. Batch's "Open in Predict" now loads the selected row's SMILES into Predict (it does not run it). Predict's inspector "Close"
   button, which did nothing, is removed. The inspector no longer opens on a preselected endpoint (Caco-2) before any result.

**Rationale.** The headline rule is that the UI never implies a capability or a result the system does not have. Illustrative
values, an invented "recent" molecule and buttons that do nothing all imply one. For a demo, the cost of a fixture reaching a live
screen is higher than the cost of losing the offline design preview.

**Rejected.** *Keep the fixture mode behind a flag* - a flag is one config mistake from a fake celecoxib on a demo screen.
*Add a real recents list to the palette* - nothing stores one, and a new store is a feature, not a fix. *Show the palette commands
only when available* - a missing command is undiscoverable; a listed one with its reason teaches the screen.

**Consequences.** There is no offline way to look at the design with data on it; use a real response (or the saved ones under
`src/domain/real-responses/` in a test). Policy numbers still written in copy (Batch "50,000 molecules" in the sign-in panel,
"24 hours" in the expired-results message) mirror backend settings and are not read from the service; a `GET /limits` route would
remove that duplication.

## ADR-033 — KERMT serving is visible: the model that answered each row, one version string, and a stated fallback

**Date:** 2026-10-20 · **Status:** accepted · implemented 2026-10-20, verified 2026-10-22 against a live KERMT service (see Consequences)

**Decision.**
1. Predict's SOURCE column shows the model family read from the row's own `model_id` (`XGBoost`, `KERMT`, `RDKit`; a stub row stays
   blank because its hatch and STUB tag already say it). It replaces a constant "v1" that was printed on every real row. The
   inspector's Provenance gains a `model` line above the raw `model_id`.
2. `GET /generations` now reports the version `/predict` stamps (`<model_version>+kermt.<routing digest>` when KERMT serving is on),
   so the top bar and a result name the same string, and a new `kermt_endpoints` list (empty when KERMT is off).
3. A row the deployment routes to KERMT but that XGBoost answered (the KERMT service was down, slow or malformed) carries a `†`
   in SOURCE, a `routing` line in the inspector and a sentence under the table saying how many such rows there are and why. The
   fallback is derived in the component from the contract, not passed in as a prop (ADR-006).

**Rationale.** A response that mixes two model families must say which answered which row, and a version shown in one place must not
differ from the one shown in another. The fallback is correct output, but a reader who saw "KERMT serves bbb_permeability" and then
got an XGBoost value would otherwise have to read raw ids to notice.

**Rejected.** *Colour or order rows by family* - provenance only; nothing here says one family is better (AGENTS.md rules 1 and 3). The
routing reasons (AUROC gaps, noise margins) are **not** sent to the client for the same reason. *Infer the fallback in the client from the
`+kermt.` suffix alone* - it says KERMT is on, not which endpoints it serves. *Show family only in the inspector* - a column that is
blank or constant is the defect being fixed.

**Consequences.** Batch cells, Compare and the printed report still show no model family (Batch and Compare carry only the
version, the report prints the raw `model_id`); the CSV already has `model_id`. The `†` footnote appears only on Predict.

**Verified live, 2026-10-22** (private API and KERMT containers, 2 seeds per arm, real XGBoost and KERMT checkpoints, own Vite): while the
KERMT service was still loading, the six routed rows were answered by XGBoost and showed the `†`, the footnote and the `routing`
line, with the top bar and the inspector naming the same `v0.2.0-dev+kermt.<digest>`; once it was ready, those six rows showed `KERMT`
(inspector: `mars-kermt-multitask-v1`, a KERMT-specific held-out error on the regression row), no `†`, and a repeat of the molecule was
a cache hit, so the healthy response is cached and the degraded one was not. The palette (ADR-032) was checked in the same run: the one
molecule it offers is the one Predict returned, Copy molecule_id and Run prediction work, commands without a result say why. Export from
the palette was not clicked (it shares the Predict export builder). A fix found here: Copy molecule_id threw where the async Clipboard
API is missing (plain http off localhost) and was refused in the embedded browser; it now falls back to a selection copy.


## ADR-034 — Scope of the remaining frontend blueprint items: what is built, adapted and cut

**Date:** 2026-10-22 · **Status:** accepted · decisions below are final; the build order is a plan, nothing in this ADR is implemented yet

**Context.** An audit of `main` against `mars-blueprint_v4.md` (2026-10-20) found six blueprint UI items with no implementation and no
recorded decision, plus three loose ends. Each was checked against the code, the contract, the headline rule in AGENTS.md (no
invented scale, no direction of good, nothing ranked) and published work. Nothing below needs a new open question.

**Decisions.**

1. **Radar chart: cut.** Removed from the blueprint (Module 9 gap-fill, Module 12 core table). The 14 endpoints have five different units
   plus nine uncalibrated scores (ADR-023), so one radius means inventing a scale (never-do #4); the blueprint's "ideal zone" and weight
   sliders mean inventing a direction of good and a composite score (never-do #1; no weighting is validated). SwissADME's radar plots six
   *computed* properties against published ranges, not model outputs
   ([Daina 2017](https://pmc.ncbi.nlm.nih.gov/articles/PMC5335600)); ADMET-AI does not say how its radar axes are chosen or scaled
   ([Swanson 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11226862)); in a controlled comparison radar was the least effective of three
   radial charts ([Albo 2016](https://cris.haifa.ac.il/en/publications/off-the-radar-comparative-evaluation-of-radial-visualization-solu/)).
   The deferred "Target Product Profile scoring" bullet loses its "folded into the radar" clause and stays deferred.
2. **Approved-drug percentile: cut.** Not built. Measured on the training labels, the 90% held-out error band around the median spans
   percentiles 25-80 (solubility), 22-87 (logP), 25-84 (Caco-2), 18-100 (PPB) and 0-80 (clearance) (`ml/data/processed/20260830T200000Z/*/train_val.csv`
   against `status/heldout_error_bands.md`), so a percentile would carry far more precision than the model has; an approved-drug set is
   probably narrower, which would make it worse (not measured). ChEMBL is [CC BY-SA 3.0](https://chembl.gitbook.io/chembl-interface-documentation/frequently-asked-questions/general-questions):
   open, but adaptations must be redistributed under the same licence, so the blueprint's "unambiguously open" is withdrawn (this is a reading,
   not legal advice). Reference values would be needed per (endpoint, model family), so a row answered by XGBoost where KERMT is routed (†, ADR-033)
   could not use the KERMT table. ADMET-AI itself needs ATC-class subsets because acceptable toxicity differs by class, which is the missing
   direction of good again, and its paper does not discuss overlap between its reference drugs and its training data. Removed from the blueprint
   (Module 12 core table and "known open items").
3. **Drug-likeness: adapted to computed properties, not a verdict.** The service adds an optional `properties` object (`MoleculeProperties`) to
   `PredictionResponse`: molecular weight, RDKit Crippen logP (named as that, not as Lipinski's CLogP), H-bond donors and acceptors, TPSA,
   rotatable bonds, QED, the number of Lipinski criteria exceeded, and the PAINS and Brenk alerts matched (catalog and alert name). All come from RDKit
   in `ml/serve`, are deterministic and independent of which model served a row. Citations: [Lipinski 1997](https://doi.org/10.1016/S0169-409X(96)00423-1),
   [Bickerton 2012](https://pubmed.ncbi.nlm.nih.gov/22270643/), Baell and Holloway 2010 (PAINS), Brenk 2008 (ChemMedChem 3:435). Display rules: a
   "Computed properties" table beside the RULE-BASED group, outside the 14-endpoint count and the reconciliation, source label `RDKit`; plain values in
   the value-cell grammar, no colour, no pass or fail wording; QED is labelled as a published desirability function of eight properties that is not a MARS
   prediction; each alert is shown as a substructure match with the sentence that PAINS concerns assay interference, not toxicity
   ([Capuzzi 2017](https://pmc.ncbi.nlm.nih.gov/articles/PMC5778390) found most PAINS-flagged compounds show no interference), and no alert is drawn on the
   structure. Shown on Predict and in the printed report (which closes ADR-029's "no drug-likeness flags"); Batch and the CSV do not carry them (Compare does since ADR-036).
   Shipping it adds a response field, so `MODEL_VERSION` is bumped when it lands (HANDOFF 2a item 8) and the drift test is updated in the same change.
   Alert matching lives in one module under `ml/serve` that the explainability validation (`feat/explainability`, `ml/eval/explain_validation.py`) imports
   instead of keeping its own copy.
4. **Toasts: cut.** The toast stack (blueprint Module 9) is removed. The app already reports through inline messages and one polite live
   region (ADR-030); toasts enter the screen (never-do #7) and raise timing and status-message problems
   ([Primer](https://primer.style/accessibility/toasts/), [Roselli](https://adrianroselli.com/2020/01/defining-toast-messages.html)). The one gap found is
   that the palette's Copy molecule_id has no visible confirmation. The status bar therefore echoes the latest announcement as text, fed by the same
   `announce()` call as the live region, replaced by the next one, with no timer and no animation.
5. **Batch summary stats: adapted to a coverage table; outlier flagging cut.** A text table computed in the browser from the rows in hand, one line per
   endpoint: returned, not returned, out of domain, stub-served, count by model family, and the number of † fallbacks (counted separately from KERMT).
   Regression endpoints add the minimum, median and maximum "observed in this batch". No chart (no axis to choose) and no outlier flag: marking a value by its
   magnitude is never-do #1. No API change.
6. **24-hour countdown: cut.** Interactive-tier results are never stored server-side, Save snapshots the results the client holds so the purge race the
   countdown guarded does not exist (HANDOFF 2d), the job id lives only in memory and no route lists jobs, so after a reload there is no job to count
   down to, and the API exposes no expiry. Module 13's countdown paragraph is replaced by one static sentence in the Batch panel, driven by `/limits`
   (item 8): results of a queued batch are kept N hours, smaller batches are not stored.
7. **Model family in Batch, Compare and the report: built, narrowed.** Compare shows the family label and † under each value cell; the report prints the
   family label and † with a footnote in place of the raw `model_id`; Batch shows it in the molecule inspector's provenance and in item 5's table, and the
   dense grid cells are unchanged. All use `domain/modelFamily.ts` and `kermt_endpoints` from `/generations` (ADR-033).
8. **`GET /limits`: built.** Anonymous; returns `batch_size_cap`, `batch_interactive_threshold`, `batch_result_retention_hours` and
   `anon_predict_rate_per_minute`. UI copy that states those numbers reads them from here. `blob_store` takes its retention from
   `batch_upload_retention_hours` instead of the constant `RETENTION_SECONDS` it uses today (the setting is currently ignored). With KERMT serving on, the
   interactive threshold is about 20 (AIMS 2026-10-19), which is why the UI must not hard-code it.
9. **Turnstile: not built for the demo; a deploy gate.** The client keeps sending no real token and the server keeps skipping the check while
   `CLOUDFLARE_TURNSTILE_SECRET_KEY` is unset (startup warning stays). Before any public deployment (ship checklist C6), in this order: a honeypot field and a
   register rate limit, then the Turnstile widget with its site key served by `/limits` as `turnstile_site_key` (null when unset), tested with Cloudflare's published
   always-pass test key. This confirms ADR-022 item 6 and replaces the blueprint's unconditional "required" with "required before a public deploy".
10. **`retrain_opt_in`: removed.** The `BatchPredictOptions.retrain_opt_in` contract field is deleted. Nothing read it, no UI offered it, and no separate storage path
    exists, so the blueprint's per-upload opt-in and "opted-in data stored separately" described a feature that was never built. MARS does not use submitted molecules to
    train or improve models, and does not offer to. The stated posture changes accordingly and now names the one exception that always existed: what the user saves to
    their Library stays until they delete it (Module 13).

**Build order** (hours are estimates): `/limits` with the blob-store fix (3), model family in Batch/Compare/report (4), status-bar echo (1), Batch coverage
table (6; needs the family work), drug-likeness properties (12; the only contract change, last), then Turnstile only when a public deploy is approved (4).
About 26 hours before Turnstile. Tracked in `SHIP_CHECKLIST.md` D9-D14.

**Degraded results and caching, per item.** Items 3 and 5-7 never present a † row as KERMT: family text always comes from the row's own `model_id`, and
the coverage table counts † on its own. Properties (3) do not depend on the serving model, so a KERMT outage changes nothing about them, and a degraded response
is still not cached for 48 hours (ADR-033). Item 5 and the report are computed from the response in hand, so they add no cache. `/limits` is configuration and is
fetched with the same staleness as `/generations`.

**Rejected.** *Percentile as a regression-only number with no rank wording* - same reference-set, licence and per-family costs for 16-24 hours, and the same
spurious precision. *A physicochemical Bioavailability-style radar in place of the weighted one* - defensible (published ranges) but it is a second drug-likeness
display over the same six numbers item 3 already shows. *Toasts with pause-on-hover and a dismiss button* - fixes the timing complaint, keeps the animation and a
second place a state is explained. *Histograms in the batch table* - an axis decision for little information beyond min, median, maximum. *Keeping the retraining
opt-in as a dormant contract field* - it is a promise in the schema the system cannot keep. *Turnstile now* - no public users or paid services (ADR-022 rationale) and
nothing deployed.

**Consequences.** The blueprint is amended to match: Module 8 (retraining, posture, registration gate), Module 9 (toast and radar items removed, remaining
gap-fill items renumbered 5-8; only #4 is referenced elsewhere and keeps its number), Module 12 (radar, percentile, drug-likeness, batch summary, report rows and the
known-open-items sentence), Module 13 (countdown). Not decided here and still in the blueprint as written: Compare's "winner highlighting" (Module 9) and the motion
tiering and shimmer (Module 9), both of which conflict with never-do #3 and #7 and the decisions in ADR-007 and ADR-013.

**Implementation note (2026-10-22).** Item 8 (`GET /limits`, the blob-store retention fix, and UI copy read from it) is done and checked on a private stack: with the cap set
to 7,000, the interactive threshold to 20 and retention to 12 hours, the sign-in gate and the Batch note showed those numbers, and the Redis TTL of a queued job's result
blob was about 43,200 seconds (it had been 86,400 whatever the setting said). Until the service answers, copy built from `/limits` leaves the numbers out. The retention
sentence for item 6 is the Batch note. `turnstile_site_key` is added to `LimitsResponse` by the Turnstile work, not before.

**Implementation note (2026-10-22), item 7.** Done and checked live. Compare cells carry the family label and a dagger on a second line; the header sentence counts the daggers and says why;
the Batch inspector has a Source column and a note; the printed report's Model column prints the family (not the raw `model_id`), with a dagger and a footnote printed only when a row fell back.
Healthy KERMT rows show `KERMT` and no dagger in all three places. Observation, not changed: KERMT's `clearance_microsomal` returned negative values for two small molecules (-6.26 and
-29.34 mL/min/kg), which are shown as the model produced them; a value below zero is not a possible clearance, and the held-out error band (+/-42.6) is wider than any positive value near it.

**Implementation note (2026-10-22), item 4.** The status bar shows the latest announcement as text (`useLastAnnouncement`), fed by the same `announce()` call as the live region, hidden from assistive technology so nothing
is read twice, with no timer and no animation. `tests/a11yGuard.test.ts` fails if the echo becomes a second live region. Checked live, including the palette's Copy molecule_id.

**Implementation note (2026-10-22), item 5.** Done and checked live. Batch has a Rows / Coverage by endpoint switch; the coverage view (`domain/coverage.ts`, `BatchCoverage.tsx`) is computed in the browser from the rows in hand over the whole run, not the
filtered view, and replaces the filter bar while shown. One line per ML endpoint in roster order: requested, returned, not returned, out of domain, stub-served, XGBoost, KERMT, † fell back (kept out of both XGBoost and KERMT), and for
regression endpoints the minimum, median and maximum returned in this batch (stub values left out, out-of-domain values included, and the table says so). Every number is in the one value ink. Failed rows are named in the caption and
counted nowhere. The rule-based score is not in the table. `COVERAGE_NOTES` is printed with it and a test fails if it uses ranking or flagging words. Not built, by decision: a chart and an outlier flag.

**Implementation note (2026-10-22), item 3.** Done and checked live. `ml/serve/properties.py` computes molecular weight, Wildman-Crippen logP, donors, acceptors, TPSA, rotatable bonds, QED, the rule-of-five count and the distinct PAINS and Brenk alerts;
`ml/serve/alerts.py` is the one alert matcher (same `alert_matches(mol, catalogs)` signature and catalog labels as `feat/explainability`'s `explain_validation.py`, which should import it instead of keeping its own copy; the catalog is now built once). `PredictionResponse.properties` is optional and
null without RDKit, for an unparseable molecule, or on a response written before it existed; Batch and Compare responses carry it too but do not show it, as decided. Two refinements to the decision above, both recorded here instead of left implicit:
(a) the panel is in the molecule column under Identity, not beside the RULE-BASED group: the group is part of a role="grid" roster whose semantics a second table would break, and these are facts about the molecule rather than about an endpoint; it is still outside the roster and its counts.
(b) `MODEL_VERSION` is not bumped. The cache key gains a `RESPONSE_SHAPE` tag (`r2`) instead: `MODEL_VERSION` names a model generation, is pinned by each environment's `.env` (the shared one would have kept the old value), and a change that is not a model change should not move the generation shown in the top bar. Entries written before `properties`
existed are unreachable under the new key. Rule-of-five: a count of limits exceeded out of four, with the four limits stated beside it and no pass or fail wording. QED is shown as a number with its source and "not a MARS prediction". Alerts are listed by catalog and name, "no match" when empty, with the PAINS caveat and its citation in text beside them. The printed report gets the same table and notes,
and its fixed line "drug-likeness flags are not included" is gone. Checked live: a rhodanine returned PAINS `ene_rhod_A(235)` and the Brenk alerts `Michael_acceptor_1` and `Thiocarbonyl_group`; the cached repeat kept them; the panel (one ink, nothing coloured) and the report showed them; the roster and its counts were unchanged.

## ADR-035 — The structure editor: Ketcher in a non-modal panel, two-way with the SMILES field, contained rather than re-skinned

**Date:** 2026-10-23 · **Status:** accepted and built (implements ADR-027; amends its item 1)

**Decision.**

1. **Predict has a "Draw a structure" button under the SMILES field.** It toggles a panel that lies over the results and inspector
   columns and leaves the molecule column (the SMILES field, Run, the endpoint selector) visible and usable. It is `role="dialog"`,
   `aria-modal="false"`, named "Structure editor". It is non-modal on purpose: a modal would hide the field it is kept in step with.
2. **Two-way sync, not "accept".** ADR-027 item 1 had the drawing written into the field when accepted. It is now live: an edit on the
   canvas, after 300 ms of quiet, writes Indigo's SMILES into the field; text typed into the field, after 300 ms of quiet, is drawn.
   The user still presses Run, and `/predict`, the contract and the session are untouched (`StructureEditor` reads and writes only
   `usePredictSession().smiles`; a guard test pins that it imports nothing from the API layer). The blueprint's "debounced re-prediction
   on edit" is **not** adopted: it would send a request per pause while drawing against the anonymous rate limit and replace the results
   on screen under the user's hands.
3. **A refusal never overwrites typed text, and says so in words.** (`domain/structureEditor.ts`, unit-tested.)
   - Empty canvas: "The canvas is empty… The SMILES field was left as it was."
   - Not convertible (a reaction arrow, or Indigo throws): "This drawing cannot be turned into a SMILES: … The SMILES field was left as it was."
   - Typed text that cannot be drawn: "The SMILES in the field cannot be drawn: … The canvas was left as it was."
   - Indigo is lenient: `C(((` is drawn as methane without an error. So typed text with an unbalanced parenthesis or bracket, or a ring
     bond opened and never closed, is refused before it is drawn (`obviousSmilesFault`), and a drawn field is described as "The canvas
     shows the SMILES in the field. Run prediction checks that SMILES again on the server", never as a match. Anything subtler that Indigo
     tolerates is left to the server's standardiser, which rejects with its own 422.
   - The text that Indigo produces for the user's own typed SMILES is not written back over it (the editor remembers its rendering of
     the last typed value and ignores a change that only echoes it).
   - Problems are announced through the one announcer; the panel's status line is plain text, not a second live region.
4. **Loaded on demand.** `KetcherCanvas.tsx` is the only importer of `ketcher-*` (a guard test checks this, that the panel uses
   `lazy(() => import(...))`, and that the stylesheet is imported only there). If WebAssembly is missing, or the chunk fails to load,
   the panel says so (`role="alert"`) and the field still works.
5. **Contained, not re-skinned** (blueprint Module 9, item 8). See "What was overridden" below.
6. **Hidden tools.** Reactions (arrows, plus, mapping), R-groups, shapes, text, S-groups, monomers, the 3D viewer, image recognition,
   Ketcher's own property calculator, settings, help, about and full screen are hidden, not disabled: MARS takes one molecule's
   SMILES, and a property box from a second toolkit would sit beside the RDKit-computed properties MARS already shows (ADR-034 item 3)
   and could disagree with them. The macromolecule mode is switched off.

**Evidence (2026-10-23, Ketcher 3.18.0, Chromium in the app's browser pane, a real API on a private port).**

*Sizes* (`npm run build`, with `VITE_API_BASE=/api` so the real code paths are in; same command on `origin/main` for "before"):

| | before | after | change |
|---|---|---|---|
| main JS | 376.07 kB (gzip 119.59) | 383.07 kB (gzip 122.12) | +7.00 kB (+2.53 gzip) |
| main CSS | 62.35 kB (gzip 10.84) | 64.56 kB (gzip 11.18) | +2.21 kB (+0.34 gzip) |
| lazy, on first open | – | JS 7,795.61 + 1,238.77 + 440.86 + 69.87 kB, WASM 7,527.76 kB, CSS 183.34 kB | about 17.3 MB, about 3.8 MB gzip |

Without `VITE_API_BASE` the main JS went 347.25 kB to 353.46 kB (+6.21, +1.8%). The entry chunk only contains `import("./KetcherCanvas-….js")`;
`index.html` preloads nothing of Ketcher. The 3Dmol chunk (587 kB) is unchanged. First-open weight is large and uncached: it is the price of
running Indigo in the browser (ADR-027). Two `ketcher-standalone` builds were measured: the default entry inlines the WebAssembly as base64
(one 28.9 MB script, 8.5 MB gzip); `dist/binaryWasmNoRender` keeps Indigo's WASM as a separate 7.5 MB file (2.0 MB gzip) and drops the image
renderer the editor does not use. The second is built. Install and build time on this machine: adding the three packages took about 2.5 min
(`node_modules` and the lockfile grow by about 5,400 lines); `vite build` went from about 21 s to 75-105 s. Not measured: the Docker image build.

*Audit.* `npm audit` on `origin/main` already reported 3 vulnerabilities (vite 7.3.6 high; vitest and `@vitest/mocker` moderate). They were
cleared first, in their own commit, by vite 7.3.7 and vitest 5.0.5 (vitest 4.1.12, the patched 4.x, crashes npm 10.9.3 with
"Cannot read properties of null (reading 'edgesOut')"). With Ketcher added: 0 vulnerabilities. New direct dependencies, all pinned exactly:
`ketcher-core`, `ketcher-react`, `ketcher-standalone` 3.18.0 (Apache-2.0; they bring `indigo-ketcher` 1.46.0, `@mui/material` and
`@emotion/*`) and `events` 3.3.0.

**What was overridden, and what could not be.**

Ketcher's stylesheet (`ketcher-react/dist/index.css`, 183 kB) has no `html`, `body`, `*` or `:root` rule, no `@font-face`, and hashed class
names, so it does not restyle the rest of the app (it is loaded only when the panel first opens). MUI/Emotion add class-hashed `<style>` tags.
Inside the panel, `structureEditor.module.css` overrides, scoped to the box and with `!important` (Ketcher's rules are generated classes):

| Rule | Ketcher's own | Override | Checked from computed styles |
|---|---|---|---|
| #7 no animation | 26 elements with transitions; keyframes for loading dots and a caret blink; a ripple | `animation: none; transition: none` | 0 of 318 elements |
| #9 typeface | Inter, Roboto, FreeSans, Arimo, Helvetica (none loaded, so they fall back) | `--sans` on all HTML | 318 of 318 |
| #9 radius ≤ 3px | 4px on 112 elements, 20px, 50% | `--radius-sm` | 317 of 318 |
| #9 shadow outside an overlay | 32 elements | `none` | 31 of 32 |
| focus ring | none of its own | the app's accent outline, inset | – |

The leftover element, in both the radius and the shadow row, is one empty `div` inside the canvas SVG (`svg *` is excluded from the rule so
chemistry drawing is not touched). The two guards in `neverDoGuard.test.ts` that look for `animation` and `box-shadow` now accept the value
`none !important`; nothing else about them changed.

What could **not** be overridden, and is therefore an accepted exception scoped to the panel interior:
- **Dark theme only (#9).** The interior is Ketcher's light palette (white canvas, grey-blue toolbars). It has no theme switch; inverting it with a
  filter would change atom colours. `color-scheme: light` is set inside the box so its inputs and scrollbars agree with it.
- **Chemistry colours.** Atom symbols are coloured by element (red O, blue N) and the periodic-table dialog uses a multi-hue element palette. This is
  element identity, as in the 3D viewer's palette (`--viewer-*`), and carries no value or risk meaning.
- **No state explained only by a tooltip (#8).** Ketcher's toolbar buttons are icon-only, named by `title`, and the active tool is shown by a highlight
  alone. That cannot be changed from outside. What MARS needs to be unambiguous, what happened to the SMILES field, is in the text status line.
- **Atom-label typeface** in the SVG (Arial) and **icon set**: left alone.
- **Contrast** of Ketcher's own greys (disabled icons, tool-group frames) was not measured against the AA guard, which covers MARS tokens only.
- **JS-driven motion.** Only CSS motion was inspected. No scripted animation was seen while drawing, undoing and opening the periodic-table dialog; it was not read for exhaustively.

**Accessibility (what holds, what does not).**
- MARS's part: the panel is named; the trigger carries `aria-expanded`, `aria-controls` and `aria-haspopup="dialog"` and opens and closes with Enter or Space;
  Esc closes the panel from its own chrome and focus returns to the trigger (also after Close). Keys 1-4 do not switch workspace while focus is in the panel
  (`data-owns-keys`, read by `AppShell`). Close comes **after** the canvas in Tab order, because Ketcher moves focus into its own hidden, unlabelled
  `textarea` once it has loaded; Tab from there reaches Close (verified).
- **Esc inside the canvas is Ketcher's** (it cancels its tool or closes its dialogs), so it does not close the panel; use Tab to Close, or the trigger.
- **Not keyboard-accessible inside Ketcher:** placing a ring or drawing a bond at a chosen point needs a pointer. Ketcher has hotkeys for tools and atoms
  (its tooltips list them) but none that I found for choosing where something goes; I did not verify the hotkeys. The toolbars are reachable by Tab (counted in
  the DOM, hidden macromolecule controls included: 85 buttons, 77 tab stops; 71 buttons named by `title`, 1 by `aria-label`, 3 with no name), but a
  screen-reader user cannot draw. **The SMILES field is the keyboard-accessible route to
  the same result**, and the editor draws what is typed there.
- Not tested with a screen reader. Ketcher's own dialogs were not audited for focus trapping.

**Build integration** (all in `vite.config.ts`, because `ketcher-core` targets a bundler that supplies Node's globals):
- `events` and `assert` are Node built-ins that Vite externalises, which fails the build. `events` is aliased to the npm package of the same name; `assert`
  to `src/vendor/nodeAssert.ts` (the npm package reads `process` when it loads; ketcher-core only calls `assert(cond, message)`, 51 times).
- `global` is defined as `globalThis`.
- `ketcher-core` has `require("raphael")` inside an ES module. Left alone the built app fails to open the editor ("require is not defined") while the dev server
  works; `build.commonjsOptions.transformMixedEsModules` fixes it. This was found only by running the production build, not the dev server.
- Dev server only: the optimiser moves Indigo's worker and strands its `.wasm`, so the worker never answers. In dev, `binaryWasmNoRender` is aliased to the default
  self-contained entry. The first open in dev is slow while Vite transforms Ketcher.
- `KetcherCanvas` renders `<Editor>` into a React root of its own. `React.StrictMode`'s dev-only mount, unmount, mount makes Ketcher's cleanup tear down the
  instance its second mount just built ("couldn't find ketcher instance"). In production there is one mount either way.

**Rejected.**
- *Debounced re-prediction on edit* (blueprint): see decision 2.
- *Accept-to-write, as in ADR-027 item 1*: needs a second control, and a user who types while the panel is open would see a stale drawing.
- *A modal panel*: hides the field.
- *Inverting Ketcher with a CSS filter to look dark*: changes the atom palette and the greys unpredictably.
- *Another sketcher (JSME)*: no blocker was found, so ADR-027 stands.
- *Keeping the panel mounted while closed*: its document-level hotkeys would stay live on the page.

**Not verified.** The Docker image build and the cold `npm ci` time in CI. Firefox and Safari. A screen reader. Stereochemistry, charges, isotopes and large
drawings through both directions (aspirin, ethanol, a salt string and error cases were). Panel layout below the 1080 px design width. The macromolecule DOM
that Ketcher still renders but hides.

**Consequences.** `StructureEditor` is mounted once in `PredictWorkspace`. `shell.module.css` gives `.workspace` `position: relative` so the panel can anchor to
`<main>`. `AppShell` treats focus inside `[data-owns-keys]` like typing in a field. ADR-027's status line points here. Another session's 2D depiction component
in `PredictWorkspace.tsx` and this panel's mount are independent lines in the same file.

## ADR-036 — Compare shows the computed properties side by side, as values, with no difference column

**Date:** 2026-10-23 · **Status:** accepted · implemented 2026-10-23 on `feat/compare-properties`

**Decision.**

1. Compare gets a "Computed properties" block after the endpoint roster, in the same table: one column per molecule (two or three), one row per
   property in Predict's order and number format (`domain/properties.ts`: molecular weight, Wildman-Crippen logP, H-bond donors and acceptors, TPSA,
   rotatable bonds, QED, rule-of-five limits exceeded), then one row each for the PAINS and Brenk alerts, listing the names matched in that molecule
   ("no match" when none). The values come from `PredictionResponse.properties` of each molecule in `CompareResponse.molecules`; no API or contract
   change.
2. Every value is mono, tabular, `--text-primary`, in every cell. The block has no reliability edge, no hatch, no model-family line and no tag: these are
   RDKit calculations on the structure (ADR-034 item 3), not predictions, so none of the roster's marks apply and none is borrowed. Its header says
   `RDKit · not predictions`, and the same three notes Predict prints (what these values are, what QED and the rule-of-five count are, what a structural
   alert is and is not) are printed under the table as text.
3. A molecule the service sent no `properties` for (RDKit missing, an unparseable molecule, a response cached before the field existed) shows
   `not returned` in every row of its column, in the muted word style the roster uses. The block never drops a column or a row (ADR-008 by analogy).
4. **"Diff" is the reader's, not the app's.** The blueprint's Module 9 row reads "diff structure + properties". It is delivered as columns of plain values
   that can be read across, and the app computes no difference: no difference column, no Δ, no arrow, no marking of the higher or lower value in a row,
   no bolding of the column that differs. The values are not sorted or ranked either. Properties are not model output, so an equal or unequal pair carries
   no reliability message to add.
5. The roster, its flags (out of domain, stub-served, not returned), its counts and `per_endpoint_winner` handling (ADR-007) are unchanged. The block is outside
   the 14-endpoint reconciliation, as it is on Predict.
6. This amends ADR-034 item 3, which said Batch, Compare and the CSV do not carry the properties. Compare now does. Batch and the CSV still do not.

**Rationale.** Properties are the one thing in Compare that is a fact about the structure with a documented meaning, so showing them next to each other
is information the roster cannot give, and they cost no new service capability. The risk is that numbers in adjacent columns are read as a contest. Printing a
difference would make that reading the app's own claim: a delta of +1.2 in logP or of -23 in TPSA is a sign, and a sign is read as better or worse. MARS has no
validated direction of good for the model outputs (AGENTS.md rule 1), and although the rule-of-five limits give the properties a published reference, that
reference is already shown as a count of limits exceeded with no verdict, which is as far as ADR-034 item 3 went. The reader who wants the difference can subtract two
numbers that sit one cell apart.

**Where I would differ from the blueprint, said plainly.** The blueprint's word for the structure half is "diff structure". A literal structural diff (a
maximum-common-substructure alignment with the differing atoms marked) is a different thing from a property difference: it has no direction and could be shown
without ranking. It is not built here because it needs a structure drawing first (`feat/structure-depiction`), and the brief for that feature forbids highlighting
atoms. If a structure diff is wanted later it is its own decision, and it would have to be a plain depiction of each molecule with the shared core stated in
text, not drawn in a colour.

**Rejected.** *A difference column or per-row delta* - see Rationale. *Highlighting the cell that differs from the others* - draws the eye to one molecule and
reads as a verdict. *Folding the properties into the roster as a sixth group* - they are not predictions, the roster's marks would not apply, and the group
counts and reconciliation (14 ML endpoints) would have to carve them out. *Showing the properties only for a pinned reference molecule* - a reference is a
winner by another name.

**Never-do audit.** (1) every cell is one ink and mono; no value is coloured, bolded, dimmed or struck; (2) no prop is added to `EndpointRow`, which Compare
does not use; (3) nothing is ranked, sorted by value or marked as a winner, and a source guard (`tests/neverDoGuard.test.ts`) fails if the property block or its domain code
contains a difference, rank or favourable-side word; (4) no bar of any kind; (5) a molecule without properties has a labelled cell in every row, never a gap;
(6) nothing here is a stub or sample value; (7) nothing animates; (8) the source and the not-a-prediction statement are text under and in the header of the
block, not a tooltip; (9) no new radius, shadow or font.

**Consequences.** `domain/properties.ts` gains `propertyRowsAcross` and `alertRowsAcross` over the same spec Predict and the report use, so a number cannot be
written differently in two places. `domain/compare.ts` returns `Comparison.properties`. Tests cover row order and number format against `propertyLines`, the
null cell, the roster being untouched, and the absence of any comparative word. Checked live on a private stack with real model responses and three molecules
(aspirin, benzylidene thiazolidinedione, a rhodanine): the block showed the RDKit values, `ene_rhod_A(235)` under PAINS for the rhodanine only, and the Brenk names
per molecule; every value computed to `rgb(233, 237, 238)` (`--text-primary`) in IBM Plex Mono with no background.

## ADR-037 — Excel export of a Batch result: the same long format as the CSV, written with `write-excel-file`, loaded on click

**Date:** 2026-10-23 · **Status:** accepted. The maintainer confirmed the `write-excel-file` pick on 2026-10-23; implemented the same day on `feat/batch-export-xlsx` (see the implementation note at the end).

**Context.** Batch exports a CSV (`domain/exportCsv.ts`): one line per molecule x endpoint in roster order, a `state` column that says what the screen says, reliability apart from the
value, every roster endpoint present whether or not it was returned (ADR-008), full-precision numbers, no rank or winner column. An Excel file is wanted next to it. Writing an
`.xlsx` means writing a ZIP of XML parts, which the browser cannot do unaided, so this is a new dependency. The bar set for it: the lightest that works, loaded only when the button
is pressed, `npm audit` at 0, and a stated reason.

**Candidates**, measured on 2026-10-23 in a scratch project outside the repository (nothing was added to `frontend/package.json`). Bundle sizes are minified and gzipped, from an esbuild
bundle of a browser entry that writes one sheet to a `Blob`.

| | `write-excel-file` 4.1.1 | `exceljs` 4.4.0 | `xlsx` (SheetJS) 0.18.5 from npm | `fflate` + our own OOXML writer |
|---|---|---|---|---|
| Added to the bundle | 72 kB min, 20 kB gzip (includes its one dependency, `fflate`) | 947 kB min, 269 kB gzip | not built: see audit | `fflate` zip only, about 8 kB gzip, plus about 150 lines of ours |
| Packages installed | 3 (itself, `fflate`) | 194 | 10 | 2 |
| `npm audit` | 0 vulnerabilities | 2 moderate (`uuid`, bounds check in v3/v5/v6 with a caller-supplied buffer) | 1 high: prototype pollution and ReDoS, **no fixed version on npm** (the maintainers publish fixes only from their own CDN tarball) | 0 |
| Install scripts | none (only `prepublishOnly`) | none, but pulls `archiver`, `unzipper` and `tmp`, which are written for Node | none | none |
| Writes only, or reads too | writes only | reads and writes | reads and writes | writes only |
| Licence | MIT | MIT | Apache-2.0 | MIT |
| Maintenance | one maintainer; 4.1.1 released 2026-06-08, 107 releases, source on GitLab | last release 2024-12-20 | npm copy frozen at 0.18.5 | `fflate` is widely used, one maintainer; the writer is ours |

**Pick: `write-excel-file`, pinned to an exact version, imported as `write-excel-file/browser` through a dynamic `import()` in the click handler.**

- It is the only candidate that is small, audit-clean, and does exactly one job (write). Its whole closure is itself plus `fflate`, about 20 kB gzipped, and it is its own chunk that is fetched
  only when someone presses "Excel".
- `exceljs` is 13 times larger, brings 194 packages written for Node, and fails `npm audit` today. It also reads files, which MARS never does with a spreadsheet.
- SheetJS from npm is the best-known name and the wrong choice: the registry copy is the one with the open high-severity advisories and no patched release there, and the patched build is
  installed from a URL outside the registry, which sidesteps `npm audit` rather than satisfying it.
- Writing the OOXML ourselves with `fflate` is the lightest by a few kilobytes, but it makes MARS the owner of a file format that Excel is strict about (a wrong content type or style index
  produces a "repair this file" dialog), and there is no copy of Excel here to test it against. Twenty kB buys a library that real Excel and LibreOffice open.
- Risk accepted: a single maintainer and frequent releases. Mitigation: the version is pinned exactly (no caret), a bump is a reviewed change, and `npm audit` is part of the branch's checks.
  If the package ever becomes unavailable, the fallback is the `fflate`-only writer above; the export code is written so the spreadsheet writer sits behind one small function and the swap touches one file.
- If none of these were acceptable the answer would be to stay with CSV and say so. That is not the case here.

**Decision (what is built once the pick is confirmed).**

1. An "Export Excel" action beside "Export results" (the CSV) in Batch, offered under the same condition as the CSV: a real result, never a sample, never after a failure. (The palette's export command exports one Predict molecule, not a batch, so it stays CSV-only.)
2. One sheet, `Results`, with exactly the CSV's columns in the CSV's order, one line per molecule x endpoint in roster order, built from the same `ExportMolecule` list by one shared function so the two
   files cannot drift (a `buildExportTable()` returns typed cells; the CSV and the workbook are two writers over it). The sheet carries no rank, winner, score, flag or colour column, no conditional formatting
   and no cell fill. `state` is its own column and the `value` cell is the same cell in every state.
3. Cells keep their types: numbers are numeric cells at full precision (the screen's rounding is not applied), text is text. A text cell is written as a string cell, which a spreadsheet does not evaluate, so the
   CSV's leading-apostrophe guard against formula injection is not needed and is not applied (it would alter the data). A test opens the written file's XML and asserts that a SMILES or an error message beginning
   with `=`, `+`, `-` or `@` is a string cell and that no cell in the sheet is a formula cell. Missing values are empty cells, as the CSV leaves them.
4. A second sheet, `Read me`, in plain rows: what each column is, the list of `state` values and what each means, that the seed spread is not an interval, that `value` for a classification endpoint is a score
   and not a probability, and that nothing in the file ranks or scores a molecule. It is the report's "How to read" block reduced to the sheet's columns, taken from the same constants so the wording is not written twice.
5. Size: a sheet holds 1,048,576 rows, a batch is up to `batch_size_cap` molecules x 15 lines, and a browser holds the whole workbook in memory while it writes. The Excel action therefore has its own ceiling
   (5,000 molecules, 75,000 lines, to be re-measured on a real batch before it is fixed), and above it the button is replaced by one sentence saying the CSV has no such ceiling. The ceiling is a named constant, not a
   hidden failure.
6. File name `mars-batch-<n>-molecules-<date>.xlsx`, the CSV's pattern with the extension changed.

**Rejected.** *Writing the file in the API (openpyxl on the server)* - Batch results that are not saved live in the browser, so the rows would have to be posted back to be written, and the server would carry a second
copy of the reconcile logic (ADR-029 rejected the same shape for the PDF). *One wide sheet with a column per endpoint* - mixes state into value columns and invites sorting a column, which is a ranking by another
name; the long format is what ADR-008 and the CSV already chose. *Colouring out-of-domain rows in the sheet* - reliability colour in a file is still colour by a model property, and never-do #1 and #6 are about what the
product communicates, not only about its screens. *Dropping the `Read me` sheet* - a file leaves the app and loses the on-screen explanation; the notes are the part that should travel with it.

**Never-do audit (planned).** (1) numeric cells carry no format that depends on the value and no fill; (2) no prop added to `EndpointRow`; (3) no sort, rank or winner column, and the row order is the roster's; (4) no chart
and no data bar in the sheet; (5) every roster endpoint has a line, a not-returned or not-requested one with its state and an empty value; (6) a stub value is exported with `state = stub_served` and `model_id = stub-v0`,
as in the CSV; (7) nothing animates and the dependency is loaded without a counting spinner; (8) the states are explained in the `Read me` sheet in words; (9) no UI shadow, radius or font change.

**Implementation note (2026-10-23).** Built as decided, with these particulars.
- **Dependency.** `write-excel-file` 4.1.1 added to `frontend/package.json` as an exact version (no caret); its only dependency is `fflate`. `npm audit` for the whole project reports 0 vulnerabilities with it installed (checked after merging the `vite` and `vitest` bump that came in with the structure editor; before that merge the audit listed three advisories in those two packages, unrelated to this one).
- **Lazy.** The library is imported only inside `writeWorkbook` in `domain/exportXlsx.ts` (`await import("write-excel-file/browser")`); a guard test fails if any other file imports it statically. The production build has it as its own chunk of 72 kB (about 20 kB gzipped) next to the 353 kB main chunk, which grew by 5 kB for our own code; the first press fetches the chunk.
- **One table, two writers.** `buildExportRows` (in `exportCsv.ts`) returns typed cells (text, number or null) and `buildCsv` and the workbook are two writers over it; the CSV's output is unchanged (its eleven existing tests pass untouched). The Results sheet has the CSV's 20 columns in order, a bold frozen header row and column widths, and nothing else: no fill, number format or conditional format (a guard test searches the module for them).
- **No formula cell.** Every text cell is an explicit `String` cell. The test writes a real workbook, unzips it, and asserts that no worksheet contains `<f>`, that every cell is a shared or inline string or a number, that a number is a bare `<v>` and that text beginning `=`, `+`, `-` or `@` (a SMILES and an error message in the test) is present as data.
- **Read me sheet.** Defines each of the 20 columns and the seven `state` values, states that the file ranks nothing, and reuses the first four of the report's fixed statements word for word ("this report" read "this file"); a test pins both, and that every CSV column has a definition.
- **Ceiling.** `XLSX_MAX_MOLECULES = 5000` (75,000 lines). Above it the button is replaced by one sentence giving the run's size and saying the CSV has no such limit; `buildXlsxBlob` also refuses above it. The 5,000 is the figure proposed above, **not re-measured on a real batch of that size** (see below). A failure while building shows its message in the header (`role="alert"`) and the CSV button is unaffected.
- **Download.** `downloadBlob` beside `downloadText`; the file is `mars-batch-<n>-molecules-<date>.xlsx`.

**Verified live (2026-10-23, private stack with real models).** A three-row batch (two molecules and a row beginning `=`) ran; "Export Excel" appeared beside "Export results", produced `mars-batch-3-molecules-2026-10-23.xlsx` (9,736 bytes, the OOXML content type, a ZIP signature); the dev server served the library as its own module file, and the production build was checked to hold it as a separate chunk (not that the chunk loads only after the press, which was not timed). **Not run:** opening the file in Excel or LibreOffice (neither is on this machine; only the XML was inspected), the 5,000-molecule ceiling on a real batch (time and memory not measured), a queued batch, a screen reader on the new button.

## ADR-038 — Hand-offs into Compare from Library and Batch, and the endpoint subset for Batch and Compare

**Date:** 2026-10-23 · **Status:** accepted · implemented 2026-10-23 on `feat/handoffs` (ship checklist E2)

**Decision.**

1. **Library to Compare and Batch to Compare.** The Library's saved-molecule detail and the Batch molecule inspector each get an "Add to Compare" button beside the existing actions (Batch already had "Open in Predict";
   Predict already had "Compare molecule", which is unchanged). It sends the molecule's SMILES, not a result: Compare asks the service for it like any other slot. The button switches to Compare and **runs nothing**; a run stays a
   deliberate act, as it is for "Open in Predict". In Batch it is off for a row that failed (there is no molecule to compare, and the inspector already says why in words).
2. **Which slot.** `addToSlots` (pure, tested): the slot that already holds the same string, if any (nothing is added twice); else the first empty slot; else a third slot when only two exist; else the last slot is replaced.
   Replacing is the only case that loses something the user typed, so it is never silent: Compare's status line says which molecule was replaced and why. The hand-off also discards a stale result (its columns would no longer match the slots)
   and writes one sentence to the same status line naming the slot and the source. Two hand-offs in a row fill two slots.
3. **A saved molecule is not reused.** Compare predicts the SMILES again with the current model; the saved values are a frozen copy made by an earlier model version (ADR-022) and mixing them into a table of fresh values would put two generations
   in one row with nothing but a version string to tell them apart. The status line says "predicted again with the current model; the saved values are not reused" in words, in addition to the button's tooltip (never-do #8).
4. **Endpoint subset in Batch and Compare.** The Predict selector (`EndpointSelector`, a popover with All / None and ticks by group) is used as it is, beside "Run batch" and "Run comparison". The choice is session state above the router, in
   roster order, like Predict's. A run sends `endpointsForRequest(selected)` (the selection plus the always-requested rule-based score, or nothing when all 14 are ticked) and the session keeps what was sent with the result, so every cell is read
   against **what that run asked for** (ADR-028): an endpoint left out is NOT REQUESTED in every Compare column and every Batch row, including the rows that failed, and none is NOT RETURNED. Changing the selector after a run relabels nothing.
   `buildComparison` and `buildBatch` already took a `requested` list; no domain logic changed.
5. **Words next to the dashes.** The dense Batch grid shows a dash for both NOT REQUESTED and NOT RETURNED (the state is in each cell's accessible name and in the inspector's words). A run that asked for a subset therefore adds one sentence to the
   grid's footer: how many endpoints were asked for, that a dash for the others means NOT REQUESTED and nothing failed, and that the `—N` row flag counts only endpoints that were requested and not returned. Compare's status line gives the same count.
   Coverage by endpoint already reads "requested" per endpoint and needed no change.
6. **A server defect found on the way, fixed here.** `POST /batch/predict` declared `endpoints` as a bare list parameter, which FastAPI reads from the multipart body, so the `?endpoints=` the client sends (and `API_ROUTES.md` documents) was ignored and every endpoint
   ran whatever was asked for: the response carried all 15 predictions for a request of 2. It is now `Query(default=None)`. Tests pin a subset being honoured (checked to fail without the fix), no subset running everything, and an unknown name being a 422.
   The queued tier stores the same list with the job input, so it benefits identically. Confirmed on a private stack: a 3-row batch asking for two endpoints returned two ML values per row.

**Rationale.** E2 in the ship checklist is the last piece of the blueprint's "pin 2-3 molecules" flow that makes Compare usable from where molecules already are, and the subset is the one place ADR-028's state was specified for Batch and Compare but could not
occur there. Each decision above keeps a choice with the user: nothing runs by itself, nothing is replaced without being said, and a result is read against its own request.

**Rejected.** *Run the comparison as soon as the second molecule arrives* - Predict and Batch's "Open in Predict" do not run on hand-off, and a run is a request the user should start. *Silently overwrite slot 1, as Predict's hand-off does* - Predict has one molecule to hand over and
the user is looking at it; Library and Batch add to a set the user may have built. *Compare the saved values with a fresh run* - see item 3. *Move `EndpointSelector` to `components/`* - another session is editing `PredictWorkspace.tsx`, which imports it from its present path; a move adds a conflict
for no behaviour change. *Multi-select in Batch to send several rows at once* - Batch has no multi-select yet (checklist E3); the one-row action composes with the slot rules until it does.

**Not done, said plainly.** A molecule saved from a run that asked for a subset is still listed in Library against the full roster, so its left-out endpoints read NOT RETURNED there. This is not new (Predict has always been able to save a subset result) and it is wrong in the same way: the
saved snapshot does not record what was requested, and the service cannot tell the Library. It needs a contract field on the save request (for example `requested_endpoints`) and the drift test with it; it is left for its own change rather than guessed at from which predictions happen to be present.

**Never-do audit.** (1) nothing here touches a value cell; (2) no prop added to `EndpointRow`; (3) a hand-off orders nothing and Compare still has no winner; slot order is the order of arrival, which the status line states; (4) no bar of any kind; (5) every endpoint the run did not ask for is a NOT REQUESTED cell in each
Compare column and Batch row, and every roster row still renders; (6) nothing in a stub path changes; (7) nothing animates (the popover is the existing overlay); (8) the Library hand-off's "predicted again" and the dash legend are in text, with a tooltip only as a repeat; (9) no new radius, shadow or font.

**Verified live (2026-10-23, private stack, real models).** Batch with 2 of 14 endpoints on a three-row file (two molecules and one invalid): the grid had values only in the logS and hERG columns, the coverage table read "requested 2" for those and 0 elsewhere, the inspector showed NOT REQUESTED rows in words, the footer sentence
appeared, the invalid row stayed a row. "Add to Compare" from the inspector put the SMILES in Molecule 1 and navigated with the status sentence; from the Library it did the same and added the "predicted again" sentence. A Compare run with 2 of 14 endpoints read NOT REQUESTED in both columns for the other 12 and showed the count in the status line.
Not run: a screen reader on the new buttons, a three-molecule replace in the browser (covered by unit tests), and the queued Batch tier with a subset (the queued path stores the same list; no job above the interactive threshold was run).

## ADR-039 — A 2D structure drawing: one service route, plain black line art, shown in Predict, Compare, Library and the printed report

**Date:** 2026-10-23 · **Status:** accepted · implemented 2026-10-23 on `feat/structure-depiction`

**Decision.**

1. **One route.** `POST /depict` takes `DepictRequest {smiles}` and returns `image/svg+xml` (no account, anonymous like `/predict`). It is a POST so a user's SMILES is never written into a URL, an access log or a referrer. The response has no JSON model (like the
   report PDF the blueprint once described), so the contract change is one request model, mirrored in `frontend/src/types/contracts.ts` and added to the drift test's field comparison. `API_ROUTES.md` has the row.
2. **The drawing says nothing about the molecule but its shape.** `ml/serve/depiction.py` draws with RDKit's `MolDraw2DSVG` using the black-and-white atom palette, a transparent background, no atom or bond indices, no stereo annotations beyond the wedges the structure implies, and
   **no highlight arguments**. The only colour in the output is `#000000` (a test pins that, over aromatic, charged, stereo and multi-component molecules, and that the SVG holds no `<text>`, `<script>`, `<image>`, `<foreignObject>` or link). No atom is coloured by element, let alone by a property
   or an alert: a molecule that carries a PAINS match is drawn exactly like one that does not. Atom attribution is the explainability feature's to show, not this one's.
3. **One molecule, one drawing.** The route canonicalises the SMILES with RDKit and draws *from the canonical form*, because RDKit's 2D layout depends on atom order; two ways of writing aspirin give byte-identical drawings (tested) and share one cache entry (checked live: the second spelling was a cache hit).
   A SMILES that cannot be parsed, is empty, is over 1,000 characters or has over 250 heavy atoms is a 422 with the reason, never a drawing it could not make. Without RDKit the route is a 501, as the 3D route is.
4. **Cache.** Redis, keyed `depict_cache:<DEPICTION_VERSION>:<sha256(canonical SMILES)>` (the molecule is hashed, never written into a key), seven days (`depiction_cache_ttl_seconds`; a drawing is a pure function of the molecule and the version, so the TTL is about memory, not freshness). `DEPICTION_VERSION` is part of the
   key: changing the drawing options bumps it and older drawings become unreachable instead of being served as the new look (the same device as `RESPONSE_SHAPE`). A cache failure is a miss, never an error. The browser keeps each drawing for the session (React Query, `staleTime: Infinity`).
5. **Its own rate limit.** Drawings are counted apart from predictions (`ratelimit:depict:<ip>`, 240 a minute by default): a Compare or Library page draws several molecules at once and must not spend the 60-a-minute prediction budget. Same fixed window, same fail-open rule.
6. **The response is inert.** It is sent with `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; sandbox` and `nosniff`, and the client shows it through an `<img>` (where nothing in it can run), after a guard (`isDrawable`) that refuses anything with script or foreign content.
7. **Ink from a token.** The service draws in black; the client puts that one ink in a token's colour (`--text-secondary` on screen, `--report-ink` on paper) by replacing the single literal, after checking the colour is a plain hex or `rgb()` value. Nothing else is rewritten (a source guard counts the replacements). No raw hex lives in a component.
8. **A standalone component.** `StructureDepiction` takes a SMILES, an ink token name, a label and whether to print its caption, and nothing else: it has no prop that could carry a value, an endpoint, a state, a highlight or a judgement (a guard test lists the banned prop names). It renders nothing without a molecule, says "Drawing the structure…" in words while it waits (no counting, no shimmer) and says in words why a drawing is
   missing (no RDKit, a SMILES it cannot draw, rate limited, API unreachable). Its caption states what the drawing is: plain line art of the standardized structure, nothing marked, nothing about any prediction.
9. **Where it shows.** Predict: the molecule column, between Identity and the 3D viewer, once there is a result (one import and one line in `PredictWorkspace.tsx`, added last; `StructureViewer.tsx` and `EndpointDetail.tsx` are untouched). Compare: a "Structure" row under the molecule headers, one drawing per column, so the sticky header stays one line.
   Library: the saved molecule's detail, from the saved SMILES. The printed report: a drawing beside the molecule's identity, in `--report-ink`.
10. **The report no longer says a drawing is never included.** ADR-029's fixed line "Not included: a 2D structure drawing." is removed. A report now carries one of two statements: when a drawing is on the page, that it is plain line art of the standardized molecule drawn by RDKit with nothing marked and nothing said about any value in the report;
    when the service could not draw one (no RDKit, a SMILES it cannot draw, a timeout), "Not included: a 2D structure drawing." with the reason, so a gap is never silent. The print action fetches the drawing first and waits at most six seconds, then prints without it and says so; a slow service never blocks the print dialog.
    A Batch row that failed before inference has no structure and no statement about one. The report's rows, counts and values are unchanged (tested).
11. **A packaging fix found on the way.** `python:3.11-slim` lacks the shared libraries RDKit's drawing module links against, so on the stock image `from rdkit.Chem.Draw import rdMolDraw2D` failed with `libXrender.so.1` and then `libXext.so.6` and `libexpat.so.1`, and `/depict` answered 501 although RDKit was installed. `api/Dockerfile` now installs `libxrender1 libxext6 libexpat1`
    (no recommends, lists removed). That exact set was checked in a throwaway container from the existing image: the import and a drawing succeed with it, and `libsm6` is not needed. The full image was not rebuilt here.

**Rationale.** A drawing is the one display of a molecule that makes no claim, which is why it is allowed to be useful without a validated scale. The risk is not in drawing it but in what gets attached to it later (colour by contribution, a flagged substructure, a glow for an alert), so the type and the drawer are narrow on purpose and tests, not review, hold the line.
The route is separate from `/predict` because a drawing needs no model, no applicability domain and no row state, and it must work for a Library entry whose `molecule_id` has long left the cache, which `GET /molecule/{id}/3d` cannot.

**Rejected.** *`GET /molecule/{id}/2d`* - it would need the id-to-SMILES registry, which expires with the prediction cache, so a Library entry could not be drawn. *`GET /depict?smiles=`* - the SMILES would be in URLs and logs. *Drawing in the browser (RDKit.js or another JS depictor)* - a multi-megabyte WebAssembly dependency, a second RDKit with its own version, and nothing the service does not already have.
*Element colours or a coloured heteroatom* - colour by what an atom is is a legend the product would then have to own, and it would sit next to values coloured by nothing. *Highlighting a PAINS match or any atom* - an alert is a substructure match, not a verdict, and atom attribution belongs to the explainability feature. *Inline `<svg>` so `currentColor` could theme it* - markup from a service injected into the page for a cosmetic gain; an `<img>` is inert.
*A depiction in the CSV* - a file of values; nothing here changes it.

**Never-do audit.** (1) no value is coloured by anything; the drawing's one ink is a token and is the same for every molecule (tested at three levels: the drawer, the client replacement, a source guard on the component's props); (2) no prop on `EndpointRow`; (3) nothing is ranked, and Compare's drawings are in column order with no winner;
(4) no bar or scale; (5) a drawing that is missing says so in words in the place it would be, and the report names the gap; (6) nothing here involves a stub value; (7) nothing animates: the loading state is text; (8) every state of the component, including each failure, is in text, and the caption is text rather than a tooltip; (9) hairline frame, radius 2px, no shadow, tokens only, dark on screen and light only in the report.

**Verified live (2026-10-23, private stack with real models, own API container and Vite).** `POST /depict`: a rhodanine and two spellings of aspirin returned `image/svg+xml` (the second spelling a cache hit), a malformed SMILES and an empty one were 422s with their reasons. In the browser: Predict showed the drawing of the rhodanine in `#a8b2b5` (`--text-secondary`) with no mark on any atom and the caption;
Compare with two molecules (a rhodanine and L-alanine) showed one drawing per column in a Structure row; the Library detail of a saved molecule showed its drawing; the report built for aspirin (with `window.print` stubbed) held the drawing in `#15191b` (`--report-ink`) and the drawing statement. Not run: the real print dialog and PDF, the 501 and 429 states in the browser (covered by unit and API tests), the Docker image rebuild,
a screen reader on the drawings, and the run in a deployed environment.

