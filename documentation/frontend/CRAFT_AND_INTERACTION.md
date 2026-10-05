# MARS craft & interaction spec

Pass 2, 2026-10-01. Written record of the craft layer added on top of the
pass-1 grammar. Rendered reference: the **Interaction & motion** artboard on
the Design canvas, plus the updated **Predict — result state** and
**Foundations** artboards.

Pass 1 established a correct grammar that read as austere — close to a
wireframe. Pass 2 does not fix that with decoration. It adds interaction
density and material craft: the same marks, machined. Nothing here adds a data
point to the screen.

---

## 1. The machined surface

`--highlight-machined: inset 0 1px 0 rgba(255,255,255,0.04)`

A 1px inset light line along the top edge. It is the opposite of a drop shadow:
a shadow says *this floats above*, a highlight says *this is a rendered
surface, catching light*. It deepens the hairline elevation model rather than
replacing it, so the no-floating-cards rule (`UX_PRINCIPLES.md` §6) is intact.

It appears on exactly two things and nowhere else:

- the **selected row** in any list or grid
- the **active nav item** in the rail

On a selected row it is drawn one pixel *inside* the accent ring:

```css
box-shadow:
  inset 0 0 0 1px var(--accent),          /* the boundary */
  inset 0 2px 0 -1px rgba(255,255,255,0.045);  /* the bevel, 1px inside it */
```

The negative spread is what pushes the highlight off the ring's own pixel.
Without it the two collide at y=0 and the highlight is invisible.

---

## 2. The row identifier stays prominent

The endpoint name rests at `--text-primary` and **stays there in every state**.
So does the value.

Pass 2 briefly demoted the name to `--text-secondary` to give hover somewhere
to go. That was wrong and is reverted (ADR-014, now recorded as a reversal).
The endpoint name is the **row identifier** — the first-column address a
reader scans to locate a row in a 15-row list or a 1,000-row grid. Table
practice keeps the row identifier prominent and demotes only *field labels*.

What legitimately rests at `--text-tertiary`, and stays there:

- units (`logS`, `probability`, `mL/min/kg`)
- the task glyph (`REG` / `CLS` / `RULE`)
- column heads (`ENDPOINT`, `ENSEMBLE INTERVAL`, `DOMAIN`, `SOURCE`)
- the source readout (`v1`)

Hover's affordance therefore comes from the **surface and the row rule**, never
from the identifier's contrast — see §3. Nothing in the interaction layer
changes the contrast of text that carries data.

---

## 3. Composing channels

A row carries up to five independent facts. The **model** channels and the
**user** channels never share a property, so no interaction state can disturb
what the model asserts.

| Fact | Owner | CSS property | Treatment |
|---|---|---|---|
| Reliability | the model | left edge element | 2px amber (OOD, stub) or `--line-strong` (not returned) |
| Magnitude | the model | the value cell | mono, tabular, `--text-primary`, **always** |
| Selection | the user | `background` (level 2) + `box-shadow` | `#15191B`, accent inset ring, machined highlight |
| Hover | the pointer | `background` (level 1) + `border-bottom` | `#101315`, hairline `#14181A` → `#1E2427` |
| Keyboard focus | the user | `outline` | 2px accent, offset 1px |

**Hover and selection share the surface ladder** — `#0B0D0E` → `#101315` →
`#15191B` — with selection winning when a row is both. That is a precedence
rule between two user channels, which is fine; what matters is that neither can
touch the left edge or the value cell.

The separation is structural, not conventional. A selected out-of-domain row
shows both markers at full strength, which is the case pass 1 already drew and
pass 2 renders with the bevel.

**No interaction state changes the contrast of any text.** Hover moves the
surface, not the type (§2).

**Implementation note.** `outline-offset: 1px` bleeds 3px into the neighbouring
row in a 30px dense list. It is correct on the Predict list, where rows have
room. In the virtualized batch grid, `outline-offset: -1px` may be necessary to
avoid clipping at the scroll-region edge — decide against the real grid, not in
the comp.

---

## 4. The applicability-domain gauge

**The only gauge in MARS.** Every other quantity either has no validated
display range (all regression endpoints, ADR-005) or already has a track
(classification on 0–1).

5-NN Tanimoto distance is genuinely bounded on `[0, 1]` and its threshold is
validated per endpoint — the 90th percentile of the training set's own internal
5-NN distances (blueprint Module 5). That makes a scale here honest in a way it
is nowhere else in the product, which is why this mark gets the most craft.

Anatomy:

| Mark | Treatment | Means |
|---|---|---|
| track | 6px, `#14181A` | the full 0–1 axis |
| covered zone | 6px, `#4A5558`, 0 → threshold | the span the training set covers |
| threshold tick | 1px, `--text-tertiary` (`#859093`), full height | the validated per-endpoint cutoff — a neutral reference |
| molecule marker | 8px diamond + 1px stem | this molecule's distance |
| scale | `0.00` / `1.00` mono at the ends, values called out above the track | |

### Contrast of the gauge marks

The **threshold tick** is a sole-carrier graphical reference line, so it must
clear 3:1 against everything it crosses. At `--text-tertiary` it reaches 5.4:1
against the track and 5.6:1 against the panel ground. It was previously
`--text-quiet`, which `ACCESSIBILITY.md` reserves for duplicated text and which
does not clear the bar — corrected in pass 2.1.

The **covered zone** is a reinforcing fill, not a sole carrier: the threshold
tick, the numeric labels, the legend and the caption all state the same
boundary. It therefore does not need 3:1 against the track, but it was raised
from `#2A3336` to `#4A5558` (1.45:1 → 2.32:1) so covered versus uncovered reads
at a glance. The value was chosen so that **every marker stays legible on it**:
an amber marker reads 3.1:1 against the zone and a neutral in-domain marker
3.6:1. A lighter zone would clear 3:1 against the track but drop the in-domain
marker below it — the zone is bounded from above by the marks it has to carry.

### Label collision rule

The threshold label and the marker label are both centred on their marks above
the track. When the two would overlap — roughly `|value − threshold| × trackWidth
< 26px` at 9px mono — the **threshold label drops below the track** onto the
scale row, prefixed `thr`. The marker label never moves: it is the reading, and
the reading holds its position. Both cases are drawn side by side on the
Interaction artboard.

The marker takes the **reliability colour of its state**: amber past the
threshold, `--text-secondary` inside it. It is never coloured by how far along
the axis it sits — only by which side of the threshold it falls on, which is
the one binary the model actually asserts.

Every gauge carries the sentence: *"Measures how well this endpoint's training
set covers this molecule. It is not a statement about the molecule."* This is
not boilerplate. A bounded gauge is the single mark in this UI most likely to
be misread as a quality score, and the caption is the mitigation.

### It is not literally `IntervalTrack`

`IntervalTrack(low, high, value, domain)` draws an *interval*.
`ADGauge(value, threshold, domain)` draws a *reading against a reference*.
Forcing one API to serve both would mean either a fake interval or optional
props that change the mark's meaning.

They are siblings over a shared `BoundedTrack` geometry primitive — same track
height, same radius, same 0–1 mapping, same requirement that `domain` be
explicit and have no default. That shared requirement is the part that matters:
neither can be rendered without a real axis.

---

## 5. The focal value

The inspector's 26px mono headline is the single most deliberate mark on
screen, and the only thing in the product above 18px.

- `letter-spacing: -0.01em`, `line-height: 1`
- unit at 11px `--text-tertiary`, baseline-aligned beside it
- 22px of quiet above, 18px below before anything else begins

Everything else in the inspector hangs off it. The hierarchy comes from the
silence around it, not from making it bigger.

---

## 6. The ⌘K palette

The signature power-user moment. Fuzzy search across molecules, endpoints and
commands, keyboard-first: opens focused, arrows move, ⏎ commits, Esc closes.

- `transform-origin` is the ⌘K field in the top bar, so the panel grows out of
  the control that summoned it rather than appearing from nowhere.
- `--surface-overlay` with `--shadow-overlay`. It is a genuine overlay, one of
  the few surfaces allowed to float.
- Selected result uses the same language as a selected row: raised surface,
  accent ring, machined highlight, 2px accent left edge.
- **Reliability language travels with the results.** A stub-served endpoint
  carries its hatched `STUB` tag in the palette exactly as it does in the
  table. A state that is visible in one place is visible everywhere it appears.

---

## 7. Motion

Updated from pass 1. Full table on the Interaction artboard.

**Ease:** `cubic-bezier(0.23, 1, 0.32, 1)` for every enter and settle.
**Never ease-in** — a state change that starts slowly reads as lag.

| Duration | What |
|---|---|
| 80ms | hover and focus feedback on a control already reached |
| 140ms | selection change, inspector content swap — **and every overlay exit** |
| 200ms | inspector and drawer **enter** |
| spring | inspector travel, selection lift, AD-gauge marker settle |
| 0ms | workspace switching, cache-hit results |

**Asymmetric by design:** 200ms in, ≤140ms out. A slow exit makes the UI feel
reluctant to get out of the way.

**Springs** (`duration 0.5, bounce 0.15`) apply to exactly three things and
nothing else. The selection lift is a spring specifically so that a *held*
arrow key retargets rather than restarting — see §8.

**Zero animation, always:**

- a number counting up or morphing between readings
- rows entering, staggering or fading into a table
- a chart or interval drawing itself
- skeleton shimmer
- workspace switching (keys 1–4, rail clicks) — the highest-frequency action in
  the product; animating it would tax every use to decorate the first

### The gauge-tick exception

`UX_PRINCIPLES.md` §8 forbids "charts drawing themselves". The AD-gauge marker
settling on first render is a deliberate, bounded exception, recorded as
ADR-013:

- the track, covered zone and threshold are **drawn instantly** — no reveal
- only the single marker eases to its placed position
- once, on first render of that endpoint's detail — never on re-render
- under `prefers-reduced-motion` it is **placed**, not animated

It is one mark settling, not a chart constructing itself. The distinction is
narrow on purpose; it is not a licence to animate other data marks.

---

## 8. Robustness expectations

**A held arrow key retargets, it does not restart.** Key repeat fires faster
than a 140ms transition completes. The selection transition must retarget from
its *current* interpolated position to the new row, not restart from the
previous row. Done wrong, holding ↓ stutters; done right, it glides. This is
the reason the selection lift is a spring rather than a fixed tween.

**Virtualized focus follows the model row, not the rendered window.** In a
1,000-row batch grid, focus belongs to the row's index in the data. Scrolling
the focused row out of the rendered window must not drop focus to the body, and
scrolling back must restore the ring to the same cell. `aria-rowindex` reports
the true index throughout (`ACCESSIBILITY.md`).

**A cache hit shows no skeleton.** When `cache_hit` is true the result is
already in hand; rendering a skeleton frame first would manufacture latency
that does not exist. No flash, no placeholder, no transition — the result is
simply there. The status bar carries `CACHE HIT` as a first-class readout so
the speed is explained rather than mysterious.

---

## 9. Typographic material

**Slashed zero and tabular figures are set on the root:**

```css
font-feature-settings: "zero" 1;
font-variant-numeric: tabular-nums;
```

Applied at `body` rather than per-element, so it holds everywhere a number
lives without sprinkling a class across forty spans. A slashed zero is not
decoration — at 9px it is the difference between `0.58` and `O.58` on a gauge
label. MARS opts into it across both Plex families deliberately; the product is
an instrument and reads consistently as one.

**Micro-type floor raised to 9px.** Pass 1 used 8px nav labels and 8.5px tags
and column heads. All are now 9px, with condensed-caps tracking loosened from
`0.08em` to `0.09em` — small caps need more optical tracking than the metric
value suggests, and the extra half-pixel of size makes the loosening necessary
rather than optional. See `OPEN_QUESTIONS.md` Q14: this contradicts the pass-2
brief's own reference to "8.5px tags", and the 9px floor was applied because it
was stated as a hard constraint.

**Optical alignment of the reliability edge.** The 2px edge is flush at `left:
0` and bleeds to the row's full height; row padding starts at 22px so the name
clears it optically rather than metrically. Tags carry asymmetric padding
(`1px 5px 1px 6px`) because condensed caps with letter-spacing accumulate
trailing space on the right — without it the tag reads as shifted left inside
its own border.

---

## 10. Which artboard owns what

Settled in pass 2.1 (ADR-015), after pass 2 left the interaction taxonomy
asserted on two boards at once.

| Artboard | Owns |
|---|---|
| **Predict — result state** | the canonical workspace: shell, row grammar, AD gauge, inspector, a freshly computed (cache MISS) result |
| **Predict — entry state** | the empty workspace and the endpoint roster before any result exists |
| **Semantic state language** | the six data/contract states, and the selected+OOD compound case that proves user state cannot disturb model state |
| **Interaction & motion** | the full interaction taxonomy, the ⌘K palette, gauge anatomy and collision rule, the motion spec, robustness expectations, and the cache-HIT variant |
| **Design system foundations** | tokens |

The seam is real: data states come from the contract and read the same to
everyone; interaction states come from the pointer and keyboard and belong with
the motion that expresses them.
