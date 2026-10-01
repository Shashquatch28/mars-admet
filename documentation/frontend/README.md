# documentation/frontend/ — MARS frontend design & engineering

This directory is the **written source of truth** for MARS frontend work.
The **visual source of truth** is the Claude Design canvas:

> **MARS Frontend Design System** — https://claude.ai/artifact/G4Xn8GJCABLWRZ2qXrotzg

Five artboards, with strict ownership (ADR-015 — do not duplicate a taxonomy
across two of them):

| Artboard | Owns |
|---|---|
| Predict — result state | the canonical workspace, on a freshly computed result |
| Predict — entry state | the empty workspace and the endpoint roster |
| Semantic state language | the six data/contract states |
| Interaction & motion | interaction taxonomy, ⌘K palette, gauge anatomy, motion spec |
| Design system foundations | tokens |

Phase status: **design phase, pass 1 (2026-09-30).** No production frontend
code has been written. `frontend/` remains the M4 scaffold described in
`frontend/README.md` — do not treat anything here as implemented.

## Why this directory exists separately

Frontend decisions were previously implicit (blueprint Module 9 prose,
`frontend/README.md`, scattered AIMS entries). Module 9 is a *specification*
of what the UI must contain; it is not a design system and does not pin
tokens, states, component boundaries or accessibility behaviour. This
directory holds those, and does not restate what the blueprint already says.

| Source | Owns |
|---|---|
| `documentation/mars-blueprint_v4.md` | Module 7 / 9 / 12 / 13 product scope |
| `contracts/mars_contracts/*.py` | field names, endpoint list, task types |
| `contracts/API_ROUTES.md` | routes, auth, rate limits, cache semantics |
| `documentation/frontend/` (here) | tokens, IA, interaction, a11y, component architecture |
| the Design canvas | the rendered visual system |

## Files

| File | Contents |
|---|---|
| `UX_PRINCIPLES.md` | the eight rules every screen is judged against |
| `DESIGN_SYSTEM.md` | tokens: colour, type, spacing, surfaces, borders, motion, icons, data-viz |
| `CRAFT_AND_INTERACTION.md` | pass-2 craft layer: machined surfaces, composing state channels, the AD gauge, motion spec, robustness |
| `ARCHITECTURE.md` | stack decision, project layout, data layer, state model |
| `COMPONENTS.md` | component inventory and boundaries, with prop-level state models |
| `INTERACTIONS.md` | keyboard model, selection, navigation, motion rules |
| `ACCESSIBILITY.md` | contrast, focus, grid semantics, reduced motion |
| `RESPONSIVE_STRATEGY.md` | desktop-first boundaries and what is explicitly out of scope |
| `DECISIONS.md` | ADR log: every major decision with rationale and rejected alternatives |
| `RESEARCH_REFERENCES.md` | external references and why each one applies to MARS |
| `OPEN_QUESTIONS.md` | decisions that need the maintainer, blocking and non-blocking |

## The one rule that outranks the others

The UI must never imply a capability the model does not have. MARS has no
validated `risk_threshold` and no validated `direction_of_good`. Therefore no
predicted value is ever coloured by magnitude, ranked, scored, or described as
good, safe, favourable or better. Reliability markers (out-of-domain, stub-
served, not-returned) are a separate visual channel from the value itself and
never recolour it. See `UX_PRINCIPLES.md` §1–3.
