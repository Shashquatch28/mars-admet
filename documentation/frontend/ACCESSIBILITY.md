# MARS accessibility

Target: **WCAG 2.2 AA**, with the grid-specific requirements below treated as
hard requirements rather than aspirations. A data-dense scientific tool that is
keyboard-hostile is unusable for its actual audience, so this is a usability
document as much as a compliance one.

## Colour and contrast

Measured against `--surface-void` (`#0B0D0E`):

| Token | Ratio | Verdict |
|---|---|---|
| `--text-primary` `#E9EDEE` | 16.5:1 | any size |
| `--text-secondary` `#A8B2B5` | 9.0:1 | any size |
| `--text-tertiary` `#859093` | 5.9:1 | any size |
| `--text-quiet` `#6E797C` | 4.4:1 | **below AA** — non-essential or duplicated text only |
| `--accent` `#49AEC4` | 7.2:1 | any size |
| `--caution` `#D99A3C` | 7.6:1 | any size |
| `--error` `#D9615A` | 5.1:1 | any size |
| `--success` `#6FA860` | 6.6:1 | any size |

`--text-quiet` is the one token that fails AA for small body text. It is
permitted only for status-bar readouts and explanatory asides whose information
also appears elsewhere at an AA-compliant contrast. Any new use requires a
check that the information is genuinely duplicated.

**It is not permitted for graphical marks that carry meaning.** The AD-gauge
threshold tick initially used it; a sole-carrier reference line must clear 3:1
against everything it crosses, so it moved to `--text-tertiary` — 5.4:1 against
the gauge track (`#14181A`) and 5.6:1 against the panel ground. Non-text
contrast is a separate budget from text contrast, and `--text-quiet` clears
neither reliably.

### Colour is never the only channel

- Out-of-domain: amber edge **plus** an `OOD` text tag **plus** the k-NN
  distance in the inspector.
- Stub-served: amber hatch **plus** a `STUB` text tag — and hatch is a texture,
  so it survives greyscale and colour-vision deficiency.
- Not returned: muted edge **plus** the literal words `NOT RETURNED`.
- No red/green pairing carries meaning anywhere in MARS. The two states most
  often confused by colour-blind users are never asked to be distinguished by
  hue.

## Type size floor

**9px is the minimum** anywhere in the product (raised in pass 2 from pass 1's
8px nav labels and 8.5px tags). Condensed caps carry `letter-spacing: 0.09em`
at that size. Below 9px, condensed caps at 600 weight stop being reliably
legible on a standard-density display regardless of contrast, which makes size
an accessibility constraint here and not only a taste one.

## Focus

- The focus ring is `2px solid var(--accent)` at `outline-offset: 1px`, always
  visible, never removed. At 7.2:1 against every surface token it clears the
  3:1 non-text requirement comfortably.
- In a 30px dense row the +1px offset bleeds 3px into the neighbouring row. It
  is correct on the Predict list; the virtualized batch grid may need
  `outline-offset: -1px` to avoid clipping at the scroll-region edge. Decide
  against the real grid (`CRAFT_AND_INTERACTION.md` §3).
- The focused cell in a grid is visually distinct from the selected cell.
  Focus is an outline; selection is a raised surface plus an inset outline.
- Focus is never lost across a state change. Closing the inspector returns
  focus to the row that opened it; a re-run returns focus to the run control.
- No keyboard trap anywhere. Every overlay closes with Escape.

## Grid semantics

The Predict endpoint list and the Batch results grid both use the WCAG grid
pattern:

- `role="grid"` with `role="row"`, `role="columnheader"`, `role="gridcell"`.
- Roving `tabindex`: the grid is a single Tab stop.
- Two-dimensional arrow-key navigation; Home / End for row extremes.
- Enter puts a cell into actionable mode; Escape returns to navigation mode;
  Tab leaves the grid entirely.
- Virtualized rows carry `aria-rowcount`, `aria-rowindex`, `aria-colcount` and
  `aria-colindex`, so a screen reader reports "row 412 of 1,000" rather than
  the size of the rendered window.

Endpoint group headers are real headings within the grid structure, so the
category grouping is navigable rather than purely visual.

## Screen-reader content

- Every icon-only control has an `aria-label`. This is enforced in the
  component's type, not by review.
- Numbers are announced with their unit and state. An out-of-domain row
  announces the endpoint, the value, the unit, and "outside applicability
  domain" — the marker is real text, not decoration.
- A not-returned row announces the endpoint and "not returned", so absence is
  audible as well as visible.
- Live regions: the batch progress count and the prediction-complete
  announcement are `aria-live="polite"`. Nothing else is live — a dense grid
  that announces every change is worse than one that announces none.

## Forms

Every input has a real `<label>`, visible or visually hidden. The SMILES field
is a real `<textarea>`; the run control is a real `<button>`. No `div` carries
`role` and `onClick` anywhere in the system, including in static mockups, so
the tab order in a comp matches the tab order in the build.

Validation is inline, adjacent to the field, and describes what to fix. Error
text is associated by `aria-describedby`.

## Motion and preferences

`prefers-reduced-motion: reduce` sets every duration to `0ms` and drops every
transform. No state change depends on motion to be understood — each motion
must pass that test before it ships.

Text zoom to 200% must not break the shell. This is the constraint that keeps
the layout on flexible regions rather than fixed pixel columns, even though the
canvas is drawn at a fixed 1440×900.

## What is not yet verified

Nothing in this document has been tested against a real screen reader, because
nothing is implemented. Verification with NVDA and VoiceOver is an explicit
gate on the implementation phase, not an afterthought.
