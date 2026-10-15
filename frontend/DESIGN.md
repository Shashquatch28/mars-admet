# frontend/DESIGN.md — MARS design system, agent reference

The machine-readable companion to `documentation/frontend/`. An AI agent should
be able to build a correct MARS component from this file alone. When this file
and `documentation/frontend/` disagree, the docs win and this file is stale — fix
it. Read `AGENTS.md` (repo root) first for the non-negotiables.

Dark theme only. No light mode (ADR-004). No raw hex in components — every value
below is a CSS custom property to emit once and reference by name.

---

## Tokens

### Surfaces (separated by hairlines, not shadow)
```
--surface-void      #0B0D0E   application ground, results canvas
--surface-chrome    #0E1112   top bar, nav rail, status bar, group headers
--surface-panel     #101315   input column, inspector
--surface-raised    #15191B   selected row, active nav item
--surface-overlay   #1F2528   popover, drawer, modal — the ONLY elevated surface
--shadow-overlay    0 12px 28px rgba(0,0,0,0.55)   on --surface-overlay, nowhere else
```

### Borders
```
--line-hairline  #14181A   row separators in a dense list
--line-subtle    #1E2427   section rules inside a panel
--line-default   #272F33   panel and region edges
--line-strong    #384347   inputs, buttons, anything interactive
```

### Text (contrast on --surface-void)
```
--text-primary    #E9EDEE   16.5:1   values, endpoint names, headings
--text-secondary  #A8B2B5    9.0:1   supporting prose, metadata values
--text-tertiary   #859093    5.9:1   field labels, units, section labels
--text-quiet      #6E797C    4.4:1   BELOW AA — duplicated/non-essential text ONLY,
                                     never a meaning-carrying graphical mark (ADR-015)
--text-disabled   #5C6669    3.3:1   disabled controls only (WCAG-exempt)
```

### Semantic colour (one meaning each; a colour with no meaning is not used)
```
--accent       #49AEC4   interaction, focus, selection   NEVER a data value or judgement
--caution      #D99A3C   reliability compromised: OOD, stub, sample   NEVER "risky"
--error        #D9615A   a request/upload/row genuinely failed   NEVER a high value
--success      #6FA860   a named op completed: saved, exported   NEVER a favourable value
--unavailable  #859093   requested-but-not-returned, or n/a   NEVER anything hidden
```
Washes: `--accent-wash rgba(73,174,196,0.14)`, `--caution-wash rgba(217,154,60,0.10)`,
`--caution-line rgba(217,154,60,0.40)`.
Hatch (a texture, not a colour):
`--hatch-unreal: repeating-linear-gradient(135deg, rgba(217,154,60,0.22) 0 3px, transparent 3px 6px)`.

### Machined highlight (pass 2)
```
--highlight-machined  inset 0 1px 0 rgba(255,255,255,0.04)
```
A 1px inset top light line — a rendered-surface bevel, not a drop shadow, so the
no-floating-cards rule holds. Applied to exactly two things: the **selected row**
and the **active nav item**. On a selected row draw it one pixel inside the
accent ring: `inset 0 0 0 1px var(--accent), inset 0 2px 0 -1px rgba(255,255,255,0.045)`
(the negative spread clears the ring's own pixel). ADR-011.

### Radius / spacing
Radius: `--radius-sm 2px` (tags, inputs, buttons), `--radius 3px` (overlays).
Nothing exceeds 3px; nothing is pill-shaped. Base unit 4px; scale 2/4/8/12/16/20/24/32.
Row height: compact 30px, comfortable 36px (user choice). Group header 24px,
column header 26px. Endpoint groups separated by 7px **plus a rule**, never a gap.

---

## Typography (ADR-003)

One family, three widths — **IBM Plex**. Never Inter/Roboto/system-ui.
```
IBM Plex Sans            400/500/600   interface, prose, endpoint names
IBM Plex Sans Condensed  600           caps labels, column heads, tags, nav
IBM Plex Mono            400/500       EVERY number, SMILES, id, timestamp, model_id
```
Numeric features on the root, so they hold everywhere a number lives:
```css
font-feature-settings: "zero" 1;    /* slashed zero: 0.58 not O.58 at 9px */
font-variant-numeric: tabular-nums; /* columns align without manual padding */
```
Scale: 26px mono (inspector headline value — the ceiling, nothing larger; tracking
-0.01em, line-height 1) · 18px sans (rare section title) · 13.5px sans 500 (panel
title) · 12px mono (table value) · 11.5px sans (row text, controls) · 10.5px sans
(metadata) · 10px sans (notes) · 9px condensed 600 +0.12em (micro label/column
head) · 9px condensed 600 +0.09em (tags, nav labels). **9px is the floor** (ADR,
Q14) — no text smaller, anywhere.

---

## Motion

```
--dur-fast   80ms    hover/focus feedback on a control already under the pointer
--dur-base   140ms   selection change, inspector content swap, AND every overlay EXIT
--dur-enter  200ms   inspector + drawer ENTER — the only movement that travels
--spring     duration 0.5, bounce 0.15   inspector travel, selection lift,
                                         AD-gauge marker settle — these three ONLY
--ease       cubic-bezier(0.23, 1, 0.32, 1)   every enter/settle; NEVER ease-in
```
Asymmetric by design: 200ms in, ≤140ms out. **Zero animation** for workspace
switching (keys 1–4, rail) and cache-hit results — the highest-frequency paths.
Never animate: counting numbers, rows entering, charts drawing themselves,
skeleton shimmer, decoration. One bounded exception: AD-gauge marker (ADR-013) —
track/zone/threshold instant, one marker eases once on first render, placed (not
animated) under `prefers-reduced-motion`. `prefers-reduced-motion` zeroes all
durations and transforms; every state must stay legible without motion.

---

## Data-viz primitives (five; compose, never restyled per screen)

1. **Interval track** — 2px grey rail, 4px `#3A4549` band for the interval, 1px
   `--text-primary` tick for the point value. Only on a genuinely bounded axis
   (today: classification probability 0–1).
2. **Numeric interval** — mono `low … high`. Every regression endpoint (no
   validated display range exists — inventing one invents a scale; ADR-005).
3. **Reliability edge + tag** — 2px left edge + condensed-caps tag. Amber for OOD
   and stub; `--line-strong` for not-returned. Never touches the value cell.
4. **Hatch** — value did not come from a promoted model (`model_id=="stub-v0"`,
   sample, prototype).
5. **Applicability-domain gauge** (`ADGauge`) — 6px track on a real 0–1 axis:
   `#4A5558` covered zone 0→threshold, 1px `--text-tertiary` full-height threshold
   tick (the carrier; must stay visible under the marker), 8px diamond marker for
   this molecule's 5-NN Tanimoto distance. The marker takes the **reliability
   colour of its state** (amber past threshold, `--text-secondary` inside), never
   a colour by position. The ONLY gauge in MARS — 5-NN distance is the only
   bounded, validated scale the product has. Every instance carries the caption
   *"Measures how well this endpoint's training set covers this molecule. It is
   not a statement about the molecule."* ADR-012.

Interval label: `confidence_low/high` is **ensemble spread across 5 CV seeds**,
not a 95% CI. Column reads `ENSEMBLE INTERVAL`; never print a percentage.

---

## Component type contracts (honesty lives in the types)

```ts
// No variant/tone/severity/status/highlight. State is DERIVED, never passed.
interface EndpointRowProps {
  endpoint: Endpoint;
  metadata: EndpointMetadata;          // task_type, category, cluster
  prediction?: EndpointPrediction;     // undefined => not_returned
  selected: boolean;                   // the user attention channel
  density: "compact" | "comfortable";
  onSelect(endpoint: Endpoint): void;
}

// domain REQUIRED, no default — the type-level guard against an invented scale.
interface IntervalTrackProps { low: number; high: number; value: number;
  domain: readonly [number, number]; }

// Sibling of IntervalTrack over a shared BoundedTrack, not an instance of it.
// inDomain colours the MARKER only (which side of the threshold), nothing else.
interface ADGaugeProps { value: number; threshold: number;
  domain: readonly [number, number]; inDomain: boolean; }
```
Row channels, each on its own CSS property so none can overwrite another:
reliability → left-edge element (model) · selection → `background`+`box-shadow`
(user) · keyboard focus → `outline` (user) · hover → surface lift + row-rule
brighten (pointer) · magnitude → the value cell, never restyled by any of the
above. The endpoint **name rests at `--text-primary`** (it is the row identifier;
ADR-014 reversed) — hover's affordance is the surface lift, not the name's
contrast.

`deriveRowState()` is the single pure function that decides trustworthiness:
`'ok' | 'out_of_domain' | 'stub_served' | 'not_returned' | 'rule_based'`. Nothing
else in the app decides row state. Unit-test it against the API fixtures.

---

## Build workflow

1. Tokens live in `src/styles/tokens.css` as CSS custom properties. Components
   use CSS Modules referencing `var(--token)`; no raw hex in a component
   (ADR-016 — Tailwind is not installed in this pass).
2. Storybook renders every component in every state (the six EndpointRow states,
   the tags, loading/partial/failed workspace states) — it is both your review
   surface and the machine-readable spec generators read.
3. Generate against the Storybook, never a blank prompt.
4. **Audit against `AGENTS.md`'s "Never do" list before every merge** (the
   Anthropic `frontend-design` skill, or `npx @memi-design/cli diagnose .`).
5. Mirror `contracts/mars_contracts` in `src/types/contracts.ts`; drift fails CI
   (ADR-009).
