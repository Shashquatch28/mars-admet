# MARS UX principles

Eight rules. Every screen, component and review is judged against them.
They are ordered: when two conflict, the lower number wins.

## 1. Never imply a capability the model does not have

MARS returns a value, an interval, a domain flag and a provenance id. It does
**not** return a threshold, a direction of good, a ranking or a verdict. The UI
stops exactly where the contract stops.

Concretely, and permanently until the underlying science changes:

- No predicted value is coloured by magnitude.
- No molecule is ever "better". `CompareResponse.per_endpoint_winner` is not
  consumed (see `DECISIONS.md` ADR-007).
- No endpoint is sorted by favourability. Sorting by raw value is allowed and
  is clearly a raw numeric sort.
- No aggregate score across endpoints exists, because no weighting is validated.

## 2. Reliability and magnitude are separate visual channels

A number's *size* and a number's *trustworthiness* are unrelated facts, and
merging them is the single most damaging thing this UI could do.

- Magnitude lives in the value cell: mono, tabular, `--text-primary`, always.
- Reliability lives in the row's 2px left edge and a tag: out-of-domain,
  stub-served, not-returned, not-requested.
- A reliability marker **never** restyles the value.

## 3. Absence is a state, not a gap

The full endpoint roster is rendered on every result, in every workspace,
whether or not the service returned each one. An endpoint that is missing from
`predictions[]` gets a row. If the service was asked for it and did not answer,
the row reads `NOT RETURNED` with a solid muted edge. If the user left it out of
the run, it reads `NOT REQUESTED` with a dashed edge (ADR-028): the two causes
are never described by the same word. An endpoint is never silently dropped,
and the count in the workspace header always reconciles: *requested · returned ·
out of domain · stub-served*.

This also makes the empty state informative: before any molecule is entered,
the roster is already visible, so the shape of a result is legible in advance
and nothing reflows when values land.

## 4. Sample data must be unmistakable

Anything that did not come from a promoted model carries a **diagonal hatch**:
`model_id == "stub-v0"`, demo fixtures, design prototypes. Hatch is a texture,
not a colour, so it cannot be confused with a semantic state and survives
greyscale printing and screenshots.

## 5. Density is the point, and it must stay calm

This is a triage tool for computational chemists. Fifteen endpoints must be
scannable without scrolling on a 1440×900 screen. Density is achieved by
hairlines, tabular figures, consistent column geometry and restraint — never by
shrinking text below 9px or removing labels.

Calm comes from what is absent: no card per row, no shadow per panel, no icon
without a job, no colour without a meaning.

## 6. The application is one surface, divided

MARS is a workstation, not a dashboard. Regions are bounded by 1px rules and
sit flush against each other. There are no floating cards, and elevation exists
only for genuine overlays (popover, drawer, modal). Radius never exceeds 3px.

## 7. Keyboard is a first-class input

A chemist triaging 400 molecules uses arrow keys, not a mouse. Every primary
workflow is completable from the keyboard, the focused element is always
visibly focused, and focus is never trapped or lost across a state change. See
`ACCESSIBILITY.md` and `INTERACTIONS.md`.

## 8. Motion communicates state or it does not happen

Three durations exist (80 / 140 / 200ms). Motion is permitted for hover and
focus feedback, selection change, and overlay entry. Never for numbers counting
up, rows entering a table, charts drawing themselves, or anything decorative.
`prefers-reduced-motion` removes transform and duration entirely; every state
change remains legible without it.
