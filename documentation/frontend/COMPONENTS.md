# MARS component inventory

Pass 1 covers the shell and the Predict workspace. Batch, Compare and Library
components are named where the shell already implies them, and specified later.

> **Built vs specified (verified against `frontend/src` 2026-10-14).** This file
> is the design inventory, not a file listing. What exists as a component:
> `AppShell`, `NavRail`, `TopBar`, `StatusBar`, `CommandPalette` (`shell/`);
> `EndpointRow`, `EndpointList`, `EndpointDetail` (the inspector body),
> `EndpointSelector` (the subset popover) and `StructureViewer`
> (`workspaces/predict/`); `IntervalTrack`, `ADGauge`, `NumericInterval`,
> `ReliabilityTag` and the `scale.ts` helper that is `BoundedTrack`'s role
> (`components/dataviz/`); `BatchWorkspace`/`BatchGrid`; `Gated` and
> `AccountForm` (`auth/`), `ConfirmDialog`, `SaveControl`, `PrintReport` and `usePrintReport`
> (`components/report/`, ADR-029), `CompareWorkspace` and
> `LibraryWorkspace` (not in this inventory).
> Named below but **not separate components**: `MoleculeInput`,
> `MoleculeIdentity`, `EndpointGroup`, `WorkspaceHeader`, `WorkspacePanel` and
> `Inspector` are regions inside `PredictWorkspace.tsx` / `EndpointList.tsx` /
> `EndpointDetail.tsx`; `ScrollRegion` is plain CSS. **None of the "Primitives"
> exist yet**: buttons, fields, the popover and the segmented controls are
> styled elements in the workspace CSS modules. Prop shapes in the code differ
> from the sketches here: `EndpointRow` takes a reconciled `row`, plus `focused`,
> `loading`, `rowIndex`; `ADGauge` also takes `endpoint` (for the one-time
> settle). The honesty guarantees (no `variant`/`tone` prop, required `domain`)
> hold as written. The status bar shows served_at, latency, cache state and key
> hints; there is no rate-budget readout because the service sends no rate-limit
> headers.

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
| `StatusBar` | served_at, latency, cache state, keyboard hints (rate budget is **not** shown: the service sends none) | readouts only; never the sole home of information |

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
| `StructureEditor` | the "Draw a structure" trigger under the SMILES field and the Ketcher panel it toggles (ADR-035). Mounted once in `PredictWorkspace`, no props: it reads and writes `usePredictSession().smiles` and nothing else | closed / open; status is `idle`, `written`, `drawn`, `empty`, `unusable`, `undrawable` or `reported` (`domain/structureEditor.ts`). **Never overwrites typed text with an empty or unconvertible drawing**; says so in words |
| `EndpointGroup` | one `EndpointCategory` heading and its rows | shows cluster provenance in the header |
| `EndpointRow` | one endpoint, all seven states | see below |
| `BoundedTrack` | the shared track geometry: height, radius, 0–1 mapping | not used directly; `IntervalTrack` and `ADGauge` are its only consumers |
| `IntervalTrack` | bounded-axis interval and point tick | **refuses to render without an explicit domain** |
| `ADGauge` | covered zone, threshold tick, distance marker | the only gauge in MARS (ADR-012) |
| `NumericInterval` | low … high in mono | the regression default |
| `ReliabilityTag` | OOD / STUB / RULE tags. NOT RETURNED and NOT REQUESTED carry no tag: the value cell says it in words and the edge is solid or dashed (ADR-028) | no other variants exist; the switch is exhaustive |
| `EndpointDetail` | inspector body: value, seed spread, AD distance, provenance | |

### `StructureEditor` — a third-party interior inside a MARS frame

- **Files.** `StructureEditor.tsx` (trigger, panel frame, sync, focus; MARS's own), `KetcherCanvas.tsx` (the only importer of `ketcher-*`, loaded with
  `lazy(() => import(...))`, so the main bundle does not carry it), `structureEditor.module.css` (frame tokens, then the containment overrides),
  `domain/structureEditor.ts` (pure rules, unit-tested), `vendor/nodeAssert.ts` (a build stand-in). `tests/structureEditorGuard.test.ts` pins the lazy
  boundary, the frame's CSS and that the editor never imports the API layer.
- **Sync.** Canvas to field and field to canvas, each after 300 ms of quiet; the user still presses Run. A canvas that is empty, holds a reaction, or fails to
  convert leaves the field alone. Typed text with an unbalanced bracket or an unclosed ring bond is not drawn. The editor's rewording of the user's own typed
  SMILES is not written back over it.
- **Not allowed here.** A `variant`/`tone`/`status` prop, a second live region (problems go through `useAnnounce`), animation or a radius over 3px in MARS's
  own CSS, or any import of `ketcher-*` outside `KetcherCanvas.tsx`.
- **Ketcher's interior is Ketcher's.** It is light, its toolbar is icon-only with tooltip names, and drawing needs a pointer. What the frame overrides (typeface,
  radius, shadow, motion) and what it cannot is listed in ADR-035. The SMILES field is the keyboard route to the same result.
- **Focus.** The trigger toggles it; opening focuses the panel, then Ketcher takes focus into its own canvas; Close is after the canvas in Tab order; Esc closes
  from the panel chrome (not from inside the canvas, where it is Ketcher's); focus returns to the trigger. `data-owns-keys` stops keys 1-4 switching workspace.

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
