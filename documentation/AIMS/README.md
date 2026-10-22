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
   `mistakes.md`, `glossary.md`, `module_milestone_map.md`.
4. `documentation/status/mars-status_M1.md` (M1 matrix + Run status).
   `documentation/status/mars-status_M0.md` only if the work touches M0.
   `documentation/status/kermt_integration_status.md` if the work touches KERMT.
5. `documentation/FUTURE_SCOPE.md` if the work is near a deferred item (it keeps the 2026-10-07 deferral text and the original loss-balancing design as history; Tier 1 was revived and Tier 2 made conditional on 2026-10-14 — see `decisions.md`).
6. `documentation/AIMS/lab_session_tier1.md` if the work is Tier 1 / Tier 2 (gates G1–G4, tuning protocol, arms). `documentation/AIMS/lab_session_tasks.md` if the work is a Tier-0 GPU lab session — a sequential,
   operational checklist (pull, GPU/data/W&B verification, smoke test, first real run, Tier-0, stop
   conditions). It supersedes the ordered checklist in `next_steps.md` for lab use.

**Note:** `documentation/` has been git-tracked since `1c252ac` (2026-09-18), so
AIMS files now show up in diffs and review. Update them in the same session as
the work they describe rather than retroactively.

Then state the task.

## Branch scope (added 2026-10-14)

AIMS, the blueprint, `FUTURE_SCOPE.md` and `status/kermt_integration_status.md`
are mirrored on `milestone/m2-kermt` and `milestone/m4-frontend`; edit both
copies in the same commit. Some files named above exist only on
`milestone/m2-kermt`: `mistakes.md`, `status/mars-status_M0.md`,
`status/mars-status_M1.md`, `status/ppbr_az_investigation.md`,
`status/kermt_gpu_session_*.md`, `status/kermt_tier0_results/`,
`MARS_M1_TECHNICAL_REFERENCE.md`. The KERMT code these files cite
(`ml/models/kermt_model.py`, `ml/train/train_kermt_cluster.py`, `ml/eval/tier0_*.py`,
`ml/featurize/kermt_adapter.py`, …) is also only on that branch. A path that does not resolve on
`milestone/m4-frontend` is not necessarily wrong: check the other branch before
"fixing" it. Frontend work (Modules 9/7) is recorded in
`documentation/frontend/`, not here.

## How to maintain AIMS

Update at the end of any session that changes project state:

| File | Update when… |
|---|---|
| `context.md` | milestone advances, stack/env changes, a new fact becomes load-bearing |
| `decisions.md` | any decision resolving a blueprint ambiguity or gating a milestone — newest first, with rationale + blueprint tie-in + open follow-ups |
| `next_steps.md` | a step is done or re-ordered; keep it to the *current* + *next* milestone only |
| `mistakes.md` | something broke, was found broken, or a trap was identified — so it isn't repeated |
| `glossary.md` | rarely — only when a new term becomes common |
| `module_milestone_map.md` | a module's status changes, or the blueprint is edited |

Keep entries dated (absolute dates, not "yesterday"). Prune stale content rather
than letting it accumulate. Do not paste code diffs here — link to files.

## Rules the AI must not forget (recap — full text in the project preamble)

- `mars-blueprint_v4.md` is source of truth. Do not weaken/reinterpret
  requirements to make the code look compliant. Report conflicts explicitly.
- **Git write operations are allowed (2026-10-14), with a condition: leave no trace of the tool.** Branch, worktree,
  commit and merge are fine; no `Co-Authored-By` / "generated with" trailer, no tool name in commit messages, files or docs;
  commits carry the maintainer's configured identity. **Push, branch deletion and history rewriting are not covered — ask.** Before
  a merge, verify it is a fast-forward or conflict-free and say what was checked. Never commit hunks another session left
  uncommitted in a shared checkout. (Lab sessions: HEAD must equal `EXPECTED_SHA` at every launch, so commit finished records only
  after the launch sequence.)
- Work milestone-by-milestone in dependency order. Don't jump ahead.
- Verify before claiming done. Smallest tests first. Distinguish
  "code verified locally" / "smoke-tested" / "trained on GPU" / "fully evaluated".
- Don't waste GPU: tiny-data sanity check → smoke test → real run.
- Research reproducibility is first-class: run id, seed, dataset hash,
  config, env, git SHA, checkpoint, W&B — captured, not bolted on. No noise runs.
- Test set is never used for model selection, tuning, calibration, or iterative
  development.
- Important decisions: verify with the user first.
