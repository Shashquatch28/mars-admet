# MARS responsive strategy

## Position

MARS is a **desktop scientific workstation**. It is designed for 1440×900 and
optimised for nothing else in this phase. Phone and tablet layouts are
explicitly out of scope for pass 1 and are not sketched, not tokenised, and not
accounted for in the component APIs.

This is a deliberate choice, not an omission. A chemist triaging a 400-molecule
batch is at a desk. Designing the phone case first would force the dense grid
into a card list, and the card list would then leak back into the desktop
design as the "shared" component — which is precisely how a workstation turns
into a generic dashboard.

## Canonical viewport

**1440 × 900**, the size every artboard is drawn at.

Predict at that size, exactly:

| Region | Width | Height |
|---|---|---|
| prototype strip (design only, not shipped) | 1440 | 22 |
| top bar | 1440 | 44 |
| nav rail | 68 | 806 |
| molecule column | 356 | 806 |
| results column | 684 (flexible) | 806 |
| inspector | 332 | 806 |
| status bar | 1440 | 28 |

All fifteen endpoints, their groups, and the workspace footnote fit in the
results column without scrolling. That is the density target: the whole result
is one glance.

## Boundaries

| Range | Behaviour |
|---|---|
| < 1280 | **not supported in pass 1.** A blocking notice stating the minimum width, rather than a broken layout. |
| 1280–1439 | inspector collapses to a toggle; molecule column narrows to 320; results column keeps its geometry |
| 1440 (canonical) | the drawn design |
| 1441–1920 | results column absorbs the extra width; molecule column and inspector stay fixed |
| > 1920 | content max-width 1920, centred, with the void ground either side |

The rule above 1440 matters: extra width goes to the **data**, never to
proportional growth of every region. A wider screen should show more molecules
per view, not a larger inspector. Making the whole application wider is exactly
the failure this rule prevents.

## Vertical

The shell is fixed: top bar, workspace, status bar. Only `ScrollRegion`
scrolls. Below roughly 720px tall the workspace footnote and the status bar's
hint cluster drop before anything structural does.

## Why fixed-pixel comps and flexible implementation both

The canvas is drawn at fixed pixels so that density, alignment and type size
can be judged honestly. The implementation uses flexible regions with fixed
side columns so that text zoom to 200% (`ACCESSIBILITY.md`) and the 1280–1920
range both work. The comp is the specification of proportion, not of literal
CSS widths.

## When mobile becomes in scope

If it ever does, it is a **separate product surface** with its own information
architecture — most plausibly a read-only result viewer for a shared prediction
link, not a compressed workstation. It will not be derived by adding breakpoints
to these components, and this document should be revisited before any such work
starts.
