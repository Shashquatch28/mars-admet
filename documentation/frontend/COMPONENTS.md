# MARS component inventory

Pass 1 covers the shell and the Predict workspace. Batch, Compare and Library
components are named where the shell already implies them, and specified later.

Rule: a component's **type signature is where scientific honesty is enforced**.
If a variant would let a caller imply something MARS cannot support, that
variant does not exist.

## Shell

| Component | Owns | Notes |
|---|---|---|
| `AppShell` | the 1440×900 frame: rail, top bar, workspace slot, status bar | the only component that positions regions; workspaces never set their own chrome |
| `NavRail` | 68px primary nav, 4 destinations + settings | icon + 8px condensed caps label; active = accent left edge + raised surface + `aria-current="page"` |
| `TopBar` | workspace label, command input, serving generation, API status, account | the serving generation (`model_version`) is **permanent** here, not per-panel; a plain readout while the API reports one generation, a picker only when it reports several (ADR-026) |
| `CommandPalette` | ⌘K search over molecules, endpoints, commands | overlay; the only shell component using `--surface-overlay` + shadow |
| `StatusBar` | served_at, latency, cache state, rate budget, keyboard hints | readouts only; never the sole home of information |

## Workspace scaffolding

| Component | Owns |
|---|---|
| `WorkspaceHeader` | 34px strip: title, reconciliation counts, actions, density toggle |
| `WorkspacePanel` | a bounded region with a hairline edge and an optional section header |
| `Inspector` | the 332px right column: detail for the selected object, or its own empty state |
| `ScrollRegion` | an explicitly bounded internal scroll container — the only place scrolling is allowed |

## Predict

| Component | Owns | State model |
|---|---|---|
| `MoleculeInput` | SMILES textarea, run control, endpoint subset selector | `idle` / `invalid` / `ready` / `running` |
| `MoleculeIdentity` | input SMILES, standardized SMILES, `molecule_id` | flags whether the standardizer rewrote the input; long SMILES truncate with an expand affordance, never wrap into the layout |
| `StructureViewer` | 3Dmol.js host, hero and analysis modes | `loading` / `ready` / `unavailable (404)` / `unsupported (501)` — a 404 is a normal state, not an error |
| `EndpointGroup` | one `EndpointCategory` heading and its rows | shows cluster provenance in the header |
| `EndpointRow` | one endpoint, all seven states | see below |
| `BoundedTrack` | the shared track geometry: height, radius, 0–1 mapping | not used directly; `IntervalTrack` and `ADGauge` are its only consumers |
| `IntervalTrack` | bounded-axis interval and point tick | **refuses to render without an explicit domain** |
| `ADGauge` | covered zone, threshold tick, distance marker | the only gauge in MARS (ADR-012) |
| `NumericInterval` | low … high in mono | the regression default |
| `ReliabilityTag` | OOD / STUB / RULE tags. NOT RETURNED and NOT REQUESTED carry no tag: the value cell says it in words and the edge is solid or dashed (ADR-028) | no other variants exist; the switch is exhaustive |
| `EndpointDetail` | inspector body: value, interval, AD distance, provenance | |

### `EndpointRow` — the load-bearing component

```ts
interface EndpointRowProps {
  endpoint: Endpoint;
  metadata: EndpointMetadata;        // task_type, category, cluster
  prediction?: EndpointPrediction;   // undefined => not_returned, or not_requested when the
                                     // endpoint was left out of the request (ADR-028; derived upstream)
  selected: boolean;                 // user attention channel
  density: "compact" | "comfortable";
  onSelect(endpoint: Endpoint): void;
}
```

There is deliberately **no** `variant`, `tone`, `severity`, `status` or
`highlight` prop. Every visual state is derived inside the component from
`deriveRowState()` (see `ARCHITECTURE.md`), so no caller anywhere in the app
can colour a row by what it thinks the number means.

The visual channels are structurally separate, each on its own CSS property, so
one cannot overwrite another (`CRAFT_AND_INTERACTION.md` §3):

| Channel | Owner | Property |
|---|---|---|
| reliability | the model | left edge element |
| magnitude | the model | the value cell — never restyled by any user state |
| selection | the user | `background` (level 2) + `box-shadow` |
| hover | the pointer | `background` (level 1) + `border-bottom` |
| keyboard focus | the user | `outline` |

Hover and selection share the surface ladder with selection winning; the model
channels are untouchable from the interaction layer either way.

The endpoint **name** is the row identifier and rests at `--text-primary` in
every state, as does the value (ADR-014). No interaction state changes the
contrast of any text — hover moves the surface instead.

### `IntervalTrack` refuses unbounded axes

```ts
interface IntervalTrackProps {
  low: number;
  high: number;
  value: number;
  domain: readonly [number, number];   // required, no default
}
```

`domain` has no default because MARS has no validated display range for any
regression endpoint. A caller that cannot supply one must use
`NumericInterval`. This is a type-level guard against inventing a scale — see
`DECISIONS.md` ADR-005 and `OPEN_QUESTIONS.md` Q3.

### `ADGauge` — a reading against a reference, not an interval

```ts
interface ADGaugeProps {
  value: number;                       // 5-NN Tanimoto distance
  threshold: number;                   // validated, per endpoint
  domain: readonly [number, number];   // required, as above
  inDomain: boolean;                   // drives the marker colour only
}
```

A sibling of `IntervalTrack`, not an instance of it: one draws an interval, the
other a point against a reference (ADR-012). `inDomain` colours the **marker**
and nothing else — the marker is never coloured by its position along the axis,
only by which side of the threshold it falls on, which is the one binary the
model actually asserts.

Every instance renders its caption. It is not optional text: a bounded gauge is
the mark in this UI most likely to be misread as a quality score.

## Primitives

`Button` (default / primary / ghost, plus disabled), `Tag`, `Field` and
`Label`, `TextArea`, `Select`, `Toggle`, `SegmentedControl` (density, viewer
mode), `Dialog`, `Popover`, `Tooltip`, `Kbd`, `Rule`.

Constraints on all of them: radius at most 3px, no shadow outside overlays, no
gradient, no pill shape, focus ring always visible, and an icon-only variant
always requires `aria-label` in its type.

## Named but not yet specified

`BatchGrid`, `BatchRowInspector`, `BatchUpload`, `JobProgress`,
`CompareColumns`, `CompareEndpointRow`, `LibraryTable`, `SavedMoleculeCard`.

`CompareEndpointRow` will have no winner, rank or ordering prop (ADR-007).
