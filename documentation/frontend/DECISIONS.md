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

**Date:** 2026-10-08 · **Status:** accepted (design; implementation pending)

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
   ever deployed publicly: honeypot field and a register rate limit first, then Turnstile (free).
7. Password-reset UI is deferred. `/auth/password-reset/request` issues a token but Resend delivery is not wired,
   so a form would promise an email that is never sent.
8. Fixture mode (no API configured): Batch keeps working on its sample data, labelled as sample (`isSample`).
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

**Date:** 2026-10-08 · **Status:** accepted (implementation pending)

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

**Date:** 2026-10-08 · **Status:** accepted (wording now; replacement band planned)

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

## ADR-025 — Production serves the frontend and the API from one origin (resolves Q22)

**Date:** 2026-10-08 · **Status:** accepted (design; implementation pending)

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
5. Before the first deploy, verify which client address the anonymous rate limiter sees behind Cloud Run: it keys on
   `request.client.host` and the Dockerfile starts uvicorn without proxy flags. Unverified; uvicorn's default trust
   setting could not be confirmed from its documentation.

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

**Consequences.** The first page load can include a Cloud Run cold start (the blueprint already accepts 1-3 s). The
Dockerfile becomes multi-stage. CI does not deploy yet, so nothing needs migrating. The comment at the top of
`client.ts` (SPA and API must be same-site) remains true and is satisfied by construction.

## ADR-026 — The serving generation is a real, switchable setting (resolves Q6)

**Date:** 2026-10-08 · **Status:** accepted (design). Part 1 ships now. Parts 2-5 are blocked until a second
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
test covers both). The fixtures' `mars-routing@v0.3.1` disagrees with the API default `v0.2.0-dev`; neither is
authoritative until part 2 lands.

## ADR-027 — Predict gets a structure sketcher: Ketcher, standalone mode (resolves Q9)

**Date:** 2026-10-08 · **Status:** accepted (design; implementation pending)

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
