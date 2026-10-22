# MARS accessibility

Target: **WCAG 2.2 AA**, with the grid-specific requirements below treated as
hard requirements rather than aspirations. A data-dense scientific tool that is
keyboard-hostile is unusable for its actual audience, so this is a usability
document as much as a compliance one.

## Colour and contrast

Measured against `--surface-void` (`#0B0D0E`):

| Token | Ratio on void | Worst surface (overlay, washes) | Verdict |
|---|---|---|---|
| `--text-primary` `#E9EDEE` | 16.5:1 | 12.8:1 | any size |
| `--text-secondary` `#A8B2B5` | 9.0:1 | 6.9:1 | any size |
| `--text-tertiary` `#859093` | 5.9:1 | 4.6:1 | any size |
| `--text-quiet` `#848F92` | 5.9:1 | 4.5:1 | any size (since 2026-10-19; was `#6E797C`, 4.4:1 on void and 3.4:1 on overlay) |
| `--accent` `#49AEC4` | 7.6:1 | 5.8:1 | any size |
| `--caution` `#D99A3C` | 8.0:1 | 6.2:1 | any size |
| `--error` `#E06861` | 5.9:1 | 4.5:1 | any size (since 2026-10-19; was `#D9615A`, 4.3:1 on overlay) |
| `--success` `#6FA860` | 6.9:1 | 5.3:1 | any size |

Every text token clears 4.5:1 on every surface and on both washes (`accent-wash`, `caution-wash` over the panel);
`tests/a11yGuard.test.ts` computes this from `tokens.css`, so a changed value cannot slip below AA unnoticed.
`--text-quiet` is now one step from `--text-tertiary`: AA on the overlay surface leaves no room for a dimmer step,
so the hierarchy has one fewer rung (ADR-030). `--text-disabled` (`#5C6669`, 3.2:1) is below AA on purpose and is
allowed **only** on disabled controls, which WCAG exempts; a test fails if a non-disabled rule uses it. A readable
separator or placeholder uses `--text-quiet`, and a decorative separator is `aria-hidden`.

**Non-text marks that carry meaning** (the AD-gauge threshold tick) must clear 3:1 against everything they cross, so
they use `--text-tertiary`.

### Colour is never the only channel

- Out-of-domain: amber edge **plus** an `OOD` text tag **plus** the k-NN
  distance in the inspector.
- Stub-served: amber hatch **plus** a `STUB` text tag — and hatch is a texture,
  so it survives greyscale and colour-vision deficiency.
- Not returned: solid muted edge **plus** the literal words `NOT RETURNED`.
- Not requested: dashed muted edge **plus** the literal words `NOT REQUESTED`.
  The edges differ in pattern, not hue, so the two stay distinguishable in
  greyscale and for colour-vision deficiency (ADR-028).
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
- A not-returned row announces the endpoint and "not returned"; a
  not-requested row announces "not requested", so absence, and its cause, are
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

## Target size

WCAG 2.5.8 (Target Size, Minimum): no control is smaller than 24 x 24 CSS px. The base `button` rule sets
`min-width` and `min-height` of 24px, the Batch filter chips and search box are 24px or taller, and the Settings
checkbox is 24px. The dense 30px grid rows are already larger.

## Reflow, zoom and narrow windows

The shell keeps a 1080px canvas. Below that width (a narrow window, or browser zoom beyond about 133% on a 1440px
screen) the page **scrolls sideways** and a one-line note says so; nothing is blocked or hidden (ADR-030, which
replaces the blocking "minimum width" notice). Text zoom to 200% therefore works by scrolling, not by reflow.
Two-dimensional content (the grids) is the WCAG 1.4.10 exception for content that needs both axes.

## Keyboard shortcuts

The 1-4 workspace keys are single-character shortcuts (WCAG 2.1.4), so they can be turned off: Settings, Keyboard,
"Single-key shortcuts". On by default, remembered in this browser. They already ignore keystrokes while a text field
has focus. Ctrl or Command + K (command palette) is a modifier shortcut and is not affected.

## Implementation status (verified in a browser 2026-10-19, branch `feat/a11y-pass`)

**Built and checked**
- Landmarks: `header`, `nav` ("Workspaces"), one `main` (id `main`), `aside` inspectors, `footer`. A **skip link**
  ("Skip to workspace") is the first Tab stop, visible only while focused, and moves focus to `main`.
- Headings: the workspace name is the page `h1` (top bar); the Predict endpoint groups are `h2`. Each workspace sets
  its own page title ("Predict · MARS ADMET Rapid Screening").
- The Predict endpoint list is a valid ARIA grid: the column headers are `columnheader`s inside the grid, every cell is
  a `gridcell` (the endpoint name a `rowheader`), group rows are `rowgroup`s with a heading, and the roving focus is
  exposed with `aria-activedescendant`. Decorative edges and separators are `aria-hidden`. The Batch grid already
  had this structure.
- One polite live region (`app/announce.tsx`) announces a finished prediction ("Prediction complete. 14 of 14
  endpoints returned, 2 out of domain.") and a batch's start, each quarter and finish. Nothing else is live; the
  per-event progress line is not (it fired every half second). Failures are `role="alert"`.
- Sign-in errors are linked to their fields (`aria-invalid`, `aria-describedby`).
- Contrast, the 9px floor, the 24px targets, icon-only button names and "no clickable non-control without a role" are
  guarded by `tests/a11yGuard.test.ts`. An in-browser audit of every workspace (computed contrast of every visible
  text node, accessible names, target sizes) reported nothing after the fixes.
- Reduced motion, real labels, `aria-label` on icon-only controls, `aria-current` on the rail, the visible focus ring.

**Not built or not checked**
- Not tested with a screen reader (NVDA, VoiceOver) or by keyboard in a real session: the announcements and the grid
  structure were verified from the DOM and the accessibility roles, not by listening.
- "Closing the inspector returns focus to the row" and "every overlay closes with Escape" hold for the command palette,
  the subset popover and the confirm dialog; the Ketcher sketcher panel was not audited.
- The Batch grid's keyboard model (arrow keys between cells) was not re-tested in this pass.
- No automated engine (axe) ran: it is not a dependency. The audit script and the guards are the substitute.
- The icon-only `aria-label` rule is a test, not a component type, because no shared `Button` exists.
