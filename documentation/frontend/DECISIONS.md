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

**Date:** 2026-10-01 · **Status:** accepted (M4)

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

