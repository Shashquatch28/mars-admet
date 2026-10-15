# MARS interaction model

## Navigation

Four destinations in the rail: Predict, Batch, Compare, Library. They are one
product, not four dashboards — the shell, the endpoint row grammar, the
reliability language and the provenance readout are identical in all of them.

Molecules travel between workspaces without re-entry: a Predict result can open
in Compare; a Batch row can open in Predict; a Library entry can open in
either. The molecule is the shared object, and `molecule_id` identifies it
everywhere.

## Keyboard model

| Key | Context | Action |
|---|---|---|
| ⌘K / Ctrl+K | global | command palette |
| ⌘⏎ | Predict | run prediction |
| ↑ ↓ | endpoint list, batch grid | move the focused row |
| ← → | batch grid | move the focused cell |
| ⏎ | focused row | open in inspector |
| Esc | inspector, overlay | close and return focus to the originating row |
| Tab | anywhere | move between regions, never cell-by-cell |
| Home / End | list or grid | first / last row |
| 1–4 | global | switch workspace |

The dense grids use the WCAG grid pattern: `role="grid"`, roving `tabindex`, a
single Tab stop for the whole grid, arrow keys for spatial movement, Enter to
enter an actionable cell and Escape to leave it. Tab-stopping every cell of a
1,000-row batch result is the failure mode this avoids.

## Selection

Selection is a **user** channel and never overwrites a **model** channel
(`UX_PRINCIPLES.md` §2). Selecting an out-of-domain row shows both markers.

- Single selection: click or Enter; drives the inspector.
- Multi-selection (Batch only): Shift+click for a range, ⌘/Ctrl+click to
  toggle, with a persistent count and a clear action in the workspace header.
- Selection survives sorting and filtering. If a selected row is filtered out,
  the count says so rather than silently dropping it.

## Scroll containment

No primary workflow scrolls the page. At 1440×900 the Predict workspace fits
without scrolling at all. Where data genuinely exceeds the region — batch
results, a long library — scrolling happens inside an explicitly bounded
`ScrollRegion` whose section header and column headers stay fixed. The
application frame itself never scrolls, and never scrolls horizontally.

## Overlays

| Surface | Use | Dismissal |
|---|---|---|
| Inspector (inline column) | endpoint or row detail | Esc, close button — not modal |
| Drawer | batch job detail, export configuration | Esc, backdrop click |
| Modal | destructive confirmation only (delete account, delete saved report) | explicit action only |
| Popover | endpoint subset selector, serving-generation picker (only when more than one generation exists, ADR-026) | Esc, outside click |
| Tooltip | shortcut hints and icon labels only | hover or focus out |

A tooltip is never the only place a state is explained. Every reliability state
is legible in the row itself without hovering.

## Loading

Rows keep their final height while loading, so nothing reflows when values
arrive. The roster is known before the result is, so skeletons appear in the
exact rows the values will occupy. No shimmer animation.

Batch has a real progress phase: `completed / total` from
`/batch/progress/{job_id}`, rendered as a 2px accent rail plus a mono count.

## Errors

| Kind | Surface | Colour |
|---|---|---|
| Request failed (422 invalid SMILES, 5xx) | inline in the workspace, with status code and message | `--error` |
| Endpoint not returned | a row in the list | `--unavailable` |
| Conformer unavailable (404 or 501) | inside the viewer region | `--text-tertiary`, no error colour |
| Rate limited (429) | status bar, input disabled with a countdown | `--caution` |
| Results expired (410 on save) | inline, with what to do next | `--caution` |

Red appears only where something genuinely failed and can be retried.

## Motion

Full spec: `DESIGN_SYSTEM.md` and `CRAFT_AND_INTERACTION.md` §7, rendered on
the **Interaction & motion** artboard.

Ease is `cubic-bezier(0.23, 1, 0.32, 1)` for every enter and settle; never
ease-in. Overlays are asymmetric — 200ms in, ≤140ms out. Springs
(`duration 0.5, bounce 0.15`) apply to three things only: inspector travel, the
selection lift, and the AD-gauge marker settling on first render.

Workspace switching (keys 1–4, rail clicks) and cache-hit results have **zero**
animation. These are the highest-frequency paths in the product.

Forbidden: counting numbers, rows entering, charts drawing themselves, skeleton
shimmer, decorative movement. The single bounded exception is ADR-013.

`prefers-reduced-motion` zeroes all of it, and nothing becomes ambiguous as a
result — which is the test each motion must pass before it ships.

## Robustness

Three expectations that separate a comp from a product
(`CRAFT_AND_INTERACTION.md` §8):

- **A held arrow key retargets, it does not restart.** Key repeat outruns a
  140ms transition; the selection must retarget from its current interpolated
  position to the new row. This is why the selection lift is a spring.
- **Virtualized focus follows the model row, not the rendered window.** Focus
  belongs to the row's index in the data. Scrolling it out of view must not
  drop focus to the body.
- **A cache hit shows no skeleton.** `cache_hit` means the result is already in
  hand; a skeleton frame would manufacture latency that does not exist. The
  status bar carries `CACHE HIT` as a first-class readout so the speed is
  explained rather than mysterious.
