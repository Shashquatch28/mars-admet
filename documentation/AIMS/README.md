# AIMS — AI Memory System

Purpose: bootstrap a fresh chat with everything needed to continue MARS without
re-deriving context. These files are hand-maintained memory, not generated.

## How to start a new working session

Paste, in this order:

1. The standing project instructions (source-of-truth rules, git restrictions,
   milestone-by-milestone discipline, reproducibility requirements — the same
   preamble used to start this project).
2. `documentation/mars-blueprint_v4.md` — the authoritative spec.
3. These AIMS files: `context.md`, `decisions.md`, `next_steps.md`,
   `mistakes.md`, `glossary.md`.
4. `documentation/status/mars-status_M1.md` (current milestone matrix + Run
   status). `documentation/status/mars-status_M0.md` only if the work touches M0.
5. `documentation/FUTURE_SCOPE.md` if the work is near a deferred item.

Then state the task.

## How to maintain AIMS

Update at the end of any session that changes project state:

| File | Update when… |
|---|---|
| `context.md` | milestone advances, stack/env changes, a new fact becomes load-bearing |
| `decisions.md` | any decision resolving a blueprint ambiguity or gating a milestone — newest first, with rationale + blueprint tie-in + open follow-ups |
| `next_steps.md` | a step is done or re-ordered; keep it to the *current* + *next* milestone only |
| `mistakes.md` | something broke, was found broken, or a trap was identified — so it isn't repeated |
| `glossary.md` | rarely — only when a new term becomes common |

Keep entries dated (absolute dates, not "yesterday"). Prune stale content rather
than letting it accumulate. Do not paste code diffs here — link to files.

## Rules the AI must not forget (recap — full text in the project preamble)

- `mars-blueprint_v4.md` is source of truth. Do not weaken/reinterpret
  requirements to make the code look compliant. Report conflicts explicitly.
- **No git write operations.** No commit / add / push / rebase / reset /
  cherry-pick / branch changes. Inspect only. The user commits manually.
- Work milestone-by-milestone in dependency order. Don't jump ahead.
- Verify before claiming done. Smallest tests first. Distinguish
  "code verified locally" / "smoke-tested" / "trained on GPU" / "fully evaluated".
- Don't waste GPU: tiny-data sanity check → smoke test → real run.
- Research reproducibility is first-class: run id, seed, dataset hash,
  config, env, git SHA, checkpoint, W&B — captured, not bolted on. No noise runs.
- Test set is never used for model selection, tuning, calibration, or iterative
  development.
- Important decisions: verify with the user first.
