# MARS design system — tokens

Rendered reference: **Foundations** artboard on the Design canvas.
Dark is the only theme. There is no light mode and none is planned; see
`DECISIONS.md` ADR-004.

Token names below are the CSS custom-property names to emit at implementation.
No component may use a raw hex value.

## Surfaces

Five grounds, separated by hairlines rather than shadow.

| Token | Value | Use |
|---|---|---|
| `--surface-void` | `#0B0D0E` | application ground, results canvas |
| `--surface-chrome` | `#0E1112` | top bar, nav rail, status bar, group headers |
| `--surface-panel` | `#101315` | input column, inspector |
| `--surface-raised` | `#15191B` | selected row, active nav item |
| `--surface-overlay` | `#1F2528` | popover, drawer, modal — the only elevated surface |

Elevation: `--shadow-overlay: 0 12px 28px rgba(0,0,0,0.55)`, applied to
`--surface-overlay` and nothing else.

## Borders

| Token | Value | Use |
|---|---|---|
| `--line-hairline` | `#14181A` | row separators inside a dense list |
| `--line-subtle` | `#1E2427` | section rules inside a panel |
| `--line-default` | `#272F33` | panel and region edges |
| `--line-strong` | `#384347` | inputs, buttons, anything interactive |

## Text

| Token | Value | Use | Contrast on `--surface-void` |
|---|---|---|---|
| `--text-primary` | `#E9EDEE` | values, endpoint names, headings | 16.5:1 |
| `--text-secondary` | `#A8B2B5` | supporting prose, metadata values | 9.0:1 |
| `--text-tertiary` | `#859093` | field labels, units, section labels | 5.9:1 |
| `--text-quiet` | `#6E797C` | explanatory notes, status bar | 4.4:1 — **below 4.5, non-essential text only** |
| `--text-disabled` | `#5C6669` | disabled controls only (WCAG-exempt) | 3.3:1 |

`--text-quiet` is the one token that needs care: at 4.4:1 it sits just below the
4.5:1 threshold and must not
carry information that exists nowhere else. Status-bar readouts duplicated in
the workspace header are the intended use.

## Semantic colour

Five colours, one meaning each. A colour with no meaning is not used. Every
pair differs in lightness as well as hue, so the system survives monochrome and
colour-vision deficiency — the reason no red/green pairing carries meaning
anywhere in MARS.

| Token | Value | Means | Never means |
|---|---|---|---|
| `--accent` | `#49AEC4` | interaction, focus, selection | a data value, a quality judgement, decoration |
| `--caution` | `#D99A3C` | reliability compromised: OOD, stub-served, sample data | "this molecule is risky" |
| `--error` | `#D9615A` | a request, upload or row genuinely failed | a high predicted value, a toxic-sounding endpoint |
| `--success` | `#6FA860` | a named operation completed: saved, exported, ready | a favourable prediction |
| `--unavailable` | `#859093` | requested but not returned, or not applicable | anything hidden |

Derived washes: `--accent-wash: rgba(73,174,196,0.14)`,
`--caution-wash: rgba(217,154,60,0.10)`,
`--caution-line: rgba(217,154,60,0.40)`.

Hatch (not a colour):
`--hatch-unreal: repeating-linear-gradient(135deg, rgba(217,154,60,0.22) 0 3px, transparent 3px 6px)`.

## Typography

One family, three widths. **IBM Plex** — drawn for technical products, true
tabular figures in both sans and mono, and not the face every generated
dashboard arrives wearing. Rationale and rejected alternatives: ADR-003.

| Family | Weights | Use |
|---|---|---|
| IBM Plex Sans | 400 / 500 / 600 | interface, prose, endpoint names |
| IBM Plex Sans Condensed | 600 | caps labels, column heads, tags, nav |
| IBM Plex Mono | 400 / 500 | **every** number, SMILES, id, timestamp, model_id |

The mono rule is absolute: if it is a quantity or an identifier, it is mono.
Columns of numbers must align without manual padding.

**Numeric features are set on the root** (pass 2), so they hold everywhere a
number lives without a class on every span:

```css
font-feature-settings: "zero" 1;
font-variant-numeric: tabular-nums;
```

The slashed zero is not decoration: at 9px it is the difference between `0.58`
and `O.58` on a gauge label. MARS opts into it across both Plex families
deliberately.

### Scale

| Size | Family | Use |
|---|---|---|
| 26px | mono 500 | inspector headline value — the largest type in the product |
| 18px | sans 400 | workspace-level section title (rare) |
| 13.5px | sans 500 | panel title / inspector subject |
| 12px | mono 400 | table value |
| 11.5px | sans 400 | body, row text, controls |
| 10.5px | sans 400 | metadata labels and paired values |
| 10px | sans 400 | explanatory notes |
| 9px | condensed 600, `letter-spacing: 0.12em` | micro label, column head |
| 9px | condensed 600, `letter-spacing: 0.09em` | tags, nav labels |

**9px is the floor** (pass 2). Pass 1 used 8px nav labels and 8.5px tags and
column heads; all were raised. Condensed-caps tracking went from `0.08em` to
`0.09em` at the same time — small caps need more optical tracking than the
metric value suggests. See `OPEN_QUESTIONS.md` Q14.

There is no display type. 26px is the ceiling, and it belongs to the
inspector's headline value alone (`CRAFT_AND_INTERACTION.md` §5). A heading
larger than the data it introduces is a bug.

## Spacing

Base unit **4px**. Scale: 2, 4, 8, 12, 16, 20, 24, 32.

| Context | Value |
|---|---|
| table row, compact | 30px |
| table row, comfortable | 36px |
| group header | 24px |
| column header | 26px |
| panel section padding | 14–16px vertical, 16–20px horizontal |
| gap between endpoint groups | 7px **plus** a rule — never a gap alone |

Density is a user-level choice (compact / comfortable), not a fixed opinion.
Default: see `OPEN_QUESTIONS.md` Q8.

## Radius

`--radius-sm: 2px` (tags, inputs, buttons), `--radius: 3px` (overlays).
Nothing exceeds 3px. Nothing is pill-shaped.

## The machined highlight (pass 2)

`--highlight-machined: inset 0 1px 0 rgba(255,255,255,0.04)`

A 1px inset light line along the top edge — the opposite of a drop shadow. A
shadow says *this floats above*; a highlight says *this is a rendered surface*.
It deepens the hairline elevation model rather than replacing it, so the
no-floating-cards rule is intact.

Applied to exactly two things: the **selected row** and the **active nav
item**. On a selected row it is drawn one pixel inside the accent ring
(`inset 0 2px 0 -1px`), so the ring reads as the boundary and the highlight as
the bevel. Full rationale: `CRAFT_AND_INTERACTION.md` §1, ADR-011.

## Motion

| Token | Value | Use |
|---|---|---|
| `--dur-fast` | 80ms | hover / focus feedback on a control already under the pointer |
| `--dur-base` | 140ms | selection change, inspector content swap — **and every overlay exit** |
| `--dur-enter` | 200ms | inspector and drawer **enter** — the only movement that travels |
| `--spring` | `duration 0.5, bounce 0.15` | inspector travel, selection lift, AD-gauge marker settle — these three only |

Easing: `--ease: cubic-bezier(0.23, 1, 0.32, 1)`. One curve, for every enter
and settle. **Never ease-in** — a state change that starts slowly reads as lag.

**Asymmetric by design:** overlays enter at 200ms and leave at 140ms or less. A
slow exit makes the UI feel reluctant to get out of the way.

**Zero animation** for workspace switching (keys 1–4, rail clicks) and for a
`cache_hit` result, which skips the skeleton entirely. These are the
highest-frequency paths in the product.

Never animated: numbers, rows entering a table, charts drawing themselves,
skeleton shimmer, anything decorative. Under `prefers-reduced-motion: reduce`,
all durations become `0ms` and all transforms are dropped — the AD-gauge marker
is placed rather than settled, and every state stays legible.

The one bounded exception to "charts drawing themselves" is the AD-gauge
marker, recorded in ADR-013 and specified in `CRAFT_AND_INTERACTION.md` §7.

## Icons

Geometric stroke marks on a 20px grid, `stroke-width: 1.5`, `fill: none`,
sizes 13 / 16 / 19. Drawn from the product's own nouns (a molecule for Predict,
a grid for Batch, two panels for Compare, an archive for Library). No icon is
added for decoration. An icon-only control always carries `aria-label`.

## Data-visualisation primitives

Five marks carry every quantitative state. They compose and are never restyled
per screen. Full rationale: `DECISIONS.md` ADR-005, ADR-006, ADR-012.

1. **Interval track** — a 2px grey rail, a 4px `#3A4549` band for the interval,
   a 1px `--text-primary` tick for the point value. Drawn **only** where the
   axis is genuinely bounded, which today means classification probabilities on
   0–1.
2. **Numeric interval** — mono `low … high`. Used for every regression
   endpoint, because no validated per-endpoint display range exists and
   inventing an axis would invent a scale the model does not have.
3. **Reliability edge + tag** — 2px left edge plus a condensed-caps tag.
   Amber for OOD and stub, `--line-strong` for not-returned.
4. **Hatch** — the value did not come from a promoted model.
5. **Applicability-domain gauge** (pass 2) — a 6px track on a real 0–1 axis: a
   `#4A5558` covered zone from 0 to the threshold, a 1px `--text-tertiary`
   threshold tick, and an 8px diamond marker for this molecule's 5-NN distance.
   The tick is a sole-carrier reference line and clears 3:1 against both the
   track and the panel ground; the covered zone is a reinforcing fill and is
   tuned so every marker stays legible on it. Label collision rule and contrast
   working: `CRAFT_AND_INTERACTION.md` §4.
   The **only** gauge in MARS, because 5-NN Tanimoto distance is the only
   bounded, validated scale the product has. The marker takes the reliability
   colour of its state (amber past the threshold, `--text-secondary` inside
   it) and is never coloured by position along the axis. Every instance carries
   the caption *"It is not a statement about the molecule."* Anatomy:
   `CRAFT_AND_INTERACTION.md` §4.

### Interval labelling

`confidence_low` / `confidence_high` are **ensemble spread across the 5
cross-validation seeds** (blueprint Module 5 CORE), not a coverage-guaranteed
interval. The UI therefore labels the column `ENSEMBLE INTERVAL` and never
prints a percentage. Calling it a 95% interval would be a false precision
claim; conformal prediction, which would justify a coverage number, is
Post-MVP.
