# MARS — GPU Lab Session Tasks

_Written 2026-09-21 for the next KERMT GPU lab session (RTX A4000 workstation). Operational
checklist for Claude Code, to be followed **top to bottom**. It is not a general project
document — for context, decisions and history see `context.md`, `decisions.md`, `next_steps.md`._

> **STRATEGY CHANGE 2026-09-28 — read this before §10.** Training is now **breadth-first**: seed 0 of every Tier-0 arm
> first (**Pass 1**), then seeds 1–4 (**Pass 2**) — not five seeds of one arm in a row. Rationale, blueprint tie-in and
> the reporting caveats are in `decisions.md` 2026-09-28. Practical effects on this file: (a) §10's "Seeds to launch"
> column and launch order are replaced by the Pass-2 table P-6 above (Pass 1 is done); (b) `s_agg.py` refuses to aggregate < 5
> seeds, so Pass-1 results are read from each run's `lab_summary.json` and are **provisional single-seed numbers**
> (never write "± std" for one seed — `aggregate_seed_metrics` would print 0.0); (c) `toxicity__cls` seeds 2–4
> (≈ 4.75 h) are deferred to Pass 2. Everything else (verification, STOP rules, no git writes) is unchanged.
>
> **UPDATE 2026-10-06.** Pass-2 session 1 on `c1f0f04` finished `metabolism__reg` and `absorption_distribution__cls` (seeds 1–4, both 5-seed complete). **Resume at P-6 order 3,
> `metabolism__cls` seeds 1–4**, then `absorption_distribution__reg`, then `toxicity__cls` 2–4. See `status/kermt_gpu_session_2026-10-06.md`. Known: `tier0_artifacts.py` fails on regression arms.
>
> **CURRENT STATE (2026-09-30).** **Pass 1 is COMPLETE** and verified (session `status/kermt_gpu_session_2026-09-30.md`):
> seed 0 of all four remaining arms plus DILI seeds 0–4 and `toxicity__cls` seeds 0–1 — 11 KERMT models, all in W&B.
> Repository baseline: `origin/milestone/m2-kermt` @ `ad6eaf1`; the code that trained Pass 1 is `ae5d28d` (identical `ml/`
> code). **Pass 2 (seeds 1–4; toxicity 2–4) is governed by `decisions.md` 2026-09-30** — every §4.4 item is decided there — and
> is executed with the **Pass-2 procedure immediately below**. Sections 0–9 are the historical first-session checklist and
> stay valid as the *detailed command reference* for the steps the procedure points to; **where they disagree with the
> procedure or with `decisions.md` 2026-09-30, those win.** `EXPECTED_SHA` is **never** a constant written in this file:
> it is the full SHA the maintainer pushes after reviewing the 2026-09-30 protocol commit (see step P-0).

## Pass-2 procedure (authoritative — follow in order)

Standing rules unchanged: one run at a time, `s_verify.py` PASS before the next launch; a crashed run is never re-run over or
deleted; the test set is never used for selection, tuning or calibration; **no AI git writes** (no add/commit/push/reset/
checkout) — the maintainer commits; no code, data, config or hyperparameter change (a change needs a new `decisions.md` entry
first, because all five seeds of an arm share one protocol).

**P-0 Preconditions (maintainer, before leaving the laptop).** `decisions.md` 2026-09-30 and this runbook are committed and
pushed. The maintainer gives the session the **40-character SHA of that pushed tip** as `EXPECTED_SHA`. None of `7475342`,
`f51cb8f`, `6df4bab`, `ae5d28d`, `ad6eaf1` is a valid `EXPECTED_SHA` (they are the Pass-1 baselines, not the Pass-2 tip). **STOP** if no
SHA is supplied or `decisions.md` has no `2026-09-30 — Tier-0 Pass-2 protocol frozen` entry in the checkout.

**P-1 Synchronize the repository.** §1 (session env file; `EXPECTED_SHA` in `~/mars-work/lab_env.sh` **replaced**, not appended
— `grep -c '^export EXPECTED_SHA=' ~/mars-work/lab_env.sh` must print 1, since the file currently pins `ae5d28d`) then §2 (fetch, collision
check, `git pull --ff-only`, `HEAD == EXPECTED_SHA`, clean tree). The helper scripts `s_ckpt.py`/`s_run.py`/`s_verify.py`/`s_ames.py`
must be byte-identical to §2's text (the 2026-09-30 session confirmed this except a defensive `.get()` in `s_agg.py`); install the
new `s_protocol.py` (P-5).

**P-2 Verify the expected SHA and the frozen code.**

```bash
source ~/mars-work/lab_env.sh && cd "$MARS_REPO"
test "$(git rev-parse HEAD)" = "$EXPECTED_SHA" && echo "HEAD == EXPECTED_SHA" || echo "STOP: HEAD != EXPECTED_SHA"
git merge-base --is-ancestor ad6eaf1 HEAD && echo "descends from ad6eaf1" || echo "STOP: not a descendant of ad6eaf1"
PROTO="ml/train/train_kermt_cluster.py ml/models/kermt_model.py ml/data/cluster_loaders.py ml/data/loaders.py ml/data/split.py \
ml/configs/clusters.py ml/configs/experiment_config.py ml/eval/cluster_calibration.py ml/eval/calibration.py \
ml/eval/calibration_diagnostics.py ml/featurize/kermt_adapter.py ml/data/metadata/kermt_checkpoint.lock.json"
git diff --quiet ae5d28d HEAD -- $PROTO && echo "protocol files identical to ae5d28d (the Pass-1 training commit)" || echo "STOP: protocol file changed since Pass 1"
git status --short                                    # MUST be empty
```

**STOP** on any line starting `STOP` or a non-empty `git status --short`. A changed protocol file is not fixed on the workstation:
report it; the maintainer records a decision first. (Docs, tests, reporting/aggregation code and lint fixes do not trip this guard. `ml/eval/metrics.py` is deliberately **not** in the list — the planned
single-seed-std fix lives there — so if it differs from `ae5d28d`, read the diff by hand and confirm `compute_metrics`, ECE and Brier are untouched.)

**P-3 Verify the checkpoint and KERMT identity.** §5c (`s_ckpt.py`: all lockfile files PASS; `sha256sum` of
`kermt_contrastive_v2.0.pt` must print `e9e6649bc96503fbdb3023e312764ecbbbafd686d9a62865a1fec9466cea6be3`) and §4's KERMT
checks (`git -C "$MARS_KERMT_REPO" rev-parse HEAD` = `e402473376ace30fa0092dad0578a88bf7f67287`, tag `v2.0.0`, clean). Record the
`kermt:latest` image id (Pass 1 ran on `sha256:2918726c6bd041339ee00534f7b7b9c547466282dc73df71ca365887f3d5d87d`; a different id is
not an automatic STOP because no pin exists, but it **must be reported before launching** — it changes the meaning of "same
protocol").

**P-4 Verify environment, GPU, data, W&B.** §3 (GPU idle, CUDA visible in the container), §4 (host imports; CPU test subset), §5b
(`compare_prep`: every dataset used by the arms about to run must be `A_BYTE_IDENTICAL`/`B_…`; the known `D` for
`dili_liver_injury__augmented` is expected and irrelevant to Pass 2), §5d (readiness `READY_FOR_GPU_SMOKE_TEST`), §5e (preflight
counts unchanged), §6 (W&B login as `shashquatch28`, entity `shashquatch`, project `mars-admet`; a Tier-0 run must not run without W&B).
The smoke tests (§7) are **not** repeated (gate passed 2026-09-22, regression path exercised 2026-09-30).

**P-5 Verify the protocol configuration (banner check before every launch; `s_protocol.py` after every run).** Install once:

```bash
source ~/mars-work/lab_env.sh
cat > "$LAB/s_protocol.py" <<'PY'
import json
import os
import re
import sys
from pathlib import Path

arm = os.environ["SUBGROUP"]
run = Path("runs") / os.environ["RUN_ID"]
ref = Path(os.environ.get("REF_ROOT", "../documentation/status/kermt_tier0_results")) / arm / "seed0"
KEYS = ["endpoint", "model_family", "variant", "prep_id", "calibrate", "holdout_calibration", "use_augmented_dili",
        "loss_weighting", "hyperparams", "cluster_split_report", "labels_held_out_for_calibration"]


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def find(obj, key):  # first value stored under `key`, at any depth
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = find(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find(v, key)
            if r is not None:
                return r
    return None


new, old = load(run / "config.json"), load(ref / "config.json")
bad = [f"config.{k}: run={new.get(k)!r} seed0={old.get(k)!r}" for k in KEYS if new.get(k) != old.get(k)]
cmd_new = find(load(run / "artifacts" / "kermt" / "run.json"), "cmd_replay")
cmd_old = find(load(ref / "artifact_metadata.json"), "cmd_replay")
if not cmd_new or not cmd_old:
    bad.append(f"cmd_replay not found (run: {bool(cmd_new)}, seed0 record: {bool(cmd_old)})")
elif re.sub(r"--seed \d+", "--seed N", cmd_new) != re.sub(r"--seed \d+", "--seed N", cmd_old):
    bad.append(f"KERMT command differs from seed 0 beyond --seed:\n  run  : {cmd_new}\n  seed0: {cmd_old}")
for b in bad:
    print("[FAIL]", b)
print("PROTOCOL:", "MISMATCH vs seed 0 - " + str(len(bad)) + " difference(s)" if bad else f"MATCH (config + KERMT command identical to {arm} seed 0 except seed)")
sys.exit(1 if bad else 0)
PY
```

Run it as `SUBGROUP=$ARM RUN_ID=<run id> $PY "$LAB/s_protocol.py" | tee "$LOGS/protocol_<run id>.txt"` after each run (the reference is the arm's committed
`seed0/` record, present in the checkout). **[Tested on the laptop against the committed records: passes a matching run, fails a
flipped `holdout_calibration` and a changed `--epochs`. Not verifiable here: the exact position of `cmd_replay` inside the real
`artifacts/kermt/run.json` — the helper searches at any depth and prints `[FAIL] cmd_replay not found` rather than passing silently.]**

The pre-launch banner (`s_run.py`) must show, per arm — **STOP and kill the job** on any difference (`n_train`/`n_val` vary by seed and
are not compared):

| Arm | `model_family` | `train_pool_labels_lost_to_calibration_holdout` | `git_dirty` |
|---|---|---|---|
| `metabolism__reg` | `kermt_single` | `clearance_microsomal` 88 | false |
| `absorption_distribution__cls` | `kermt_multitask_subgroup` | `hia_absorption` 65, `pgp_inhibition` 105, `bbb_permeability` 163 | false |
| `metabolism__cls` | `kermt_multitask_subgroup` | `cyp3a4_inhibition` 715, `cyp2d6_inhibition` 836, `cyp2c9_inhibition` 803 | false |
| `absorption_distribution__reg` | `kermt_multitask_subgroup` | `solubility_logs` 789, `lipophilicity_logp` 316, `caco2_permeability` 77, `ppb_binding` 114 | false |
| `toxicity__cls` | `kermt_multitask_subgroup` | `herg_cardiotoxicity` 1056, `ames_mutagenicity` 576 | false |

Also required in every banner: `prep_id` `20260918T090433Z`, `seeds` a single seed from the tables below, `checkpoint_sha256`
`e9e6649b…6cea6be3`, `kermt_config` with every field `null`/empty except `gpu` 0 (**never** pass `EPOCHS`/`BATCH`/any hyperparameter — the protocol is the
KERMT defaults: 30 epochs, batch 32, lr 1e-4 → 2e-5, dropout 0.0, bond-drop 0.1, dist-coff 0.15, FFN 700×3, `scaffold_balanced`, metric
`auc`/`mae`, ensemble 1, one fold), `use_wandb` true, `wandb_entity` `shashquatch`, `wandb_project` `mars-admet`, no `variant`.

**P-6 Execute Pass 2 (per `decisions.md` 2026-09-30).** One arm, one seed per launch, cheapest first, launch pattern of §10.
No "explicit go" is needed for `absorption_distribution__cls` (HIA) or `metabolism__cls` (Option A) any more — both are decided; the
disk/VRAM check before `metabolism__cls` remains.

| Order | `ARM` | `SEEDS` (one per launch) | Measured cost / seed | Notes |
|---:|---|---|---|---|
| 1 | `metabolism__reg` | 1, 2, 3, 4 | ≈ 7 min | regression, no calibration |
| 2 | `absorption_distribution__cls` | 1, 2, 3, 4 | ≈ 18 min | HIA calibration N=47 (46/1) and `[WARN]` are expected every seed |
| 3 | `metabolism__cls` | 1, 2, 3, 4 | ≈ 57 min | Option A; `df -h .` and VRAM first |
| 4 | `absorption_distribution__reg` | 1, 2, 3, 4 | ≈ 57 min | regression, no calibration |
| 5 | `toxicity__cls` | 2, 3, 4 | ≈ 95 min | last; seeds 0–1 done |
| — | `dili_standalone__cls` | — | — | complete (0–4); **no DILI run in Pass 2** |

Total ≈ 9.3 h (arms 1–4) + 4.75 h (arm 5): more than one session. Do not start a run you cannot finish; a partial seed set is
recorded as partial. Tell the maintainer the remaining-time estimate before starting an arm.

**P-7 Verify each run before launching the next.** All of: `RUN_ID=<id> $PY "$LAB/s_verify.py"` → `VERDICT: PASS` (expected `[WARN]`s
only: HIA N=47; nothing else is expected — anything else is reported); `s_protocol.py` → `PROTOCOL: MATCH`; `grep -c "UserWarning: W&B"
<launch log>` = 0; `run.json` `completed`; the **saved epoch** (`N` of the last `Saving model at epoch N` line in
`finetune.log`; that wording comes from the 2026-09-30 session note and has not been seen on the laptop — if the line is absent, STOP, §12) recorded —
**never** the epoch on the final `best validation … on epoch` line (KERMT logging bug; `decisions.md` 2026-09-30 D1) — and its val score equal to
KERMT's logged best score within 1e-3. `ml/eval/tier0_artifacts.py` now reports the **saved epoch** (`seed_summary.json` → `saved_epoch_resolution`, from `ml/eval/kermt_log.py`: derived from the per-epoch
`auc_val` rows and cross-checked against the logged best score and any `Saving model` line); `tier0_present.py` refuses summaries that lack it. Packages generated before
2026-10-01 carry KERMT's misleading epoch — regenerate them (read-only, no GPU). The derivation rests on an assumption not yet confirmed on a real log: on the first Pass-2
run, `saved_epoch_resolution.consistent_with_logged_best_score` must be `true`. Read numbers from `lab_summary.json`.

**P-8 Record artifacts (in the gitignored area, so the tree stays clean for every launch).** Per run, collect into
`ml/runs/lab_logs/` the same set as the Pass-1 records: `lab_summary.json`, `config.json`, `run.json`, `provenance.json`, the
`<endpoint>__calibration_diagnostics.json` (+ `__temperature_scaler.json` for classification), `verify.txt`, the `s_protocol.py`
output, the launch log and the VRAM trace, plus `artifact_metadata.json` and `wandb_artifact.json` once P-9 has produced them. Session note goes there too. Move them under
`documentation/status/kermt_tier0_results/<arm>/seed<N>/` only **after the last run of the session**.

**P-9 Upload and verify W&B artifacts.** Per run, follow the 2026-09-30 convention exactly (`status/kermt_gpu_session_2026-09-30.md` §5):
type `model`, files `model.pt` + `metadata.json` only, aliases `final` + `latest`, logged by resuming the original training run,
one version `v0`; plus the additive `run-record` artifact; then verify from W&B (state `COMMITTED`, exactly those files, full-download
SHA-256 == local `model.pt`). The helpers used on 2026-09-30 (`s_upload.py`, `s_wandb_verify.py`) live only on `CL502-18` under
`ml/runs/lab_helpers/` and are **not in this repo**; use them, do not reinvent them, and do not upload until `s_verify.py` and
`s_protocol.py` have passed for that run. Entity is `shashquatch` (login `shashquatch28`; `shashquatch28/mars-admet` does not exist).

**P-10 Aggregate and hand over.** Aggregate an arm only when all five seeds exist (`s_agg.py` refuses otherwise): mean ± std over
**test** metrics, raw and calibrated side by side; HIA calibrated metrics are omitted (D4); DILI is labelled "base pool" (D6). Before a
partial arm is reported, every number is labelled provisional single-seed and no "± std" is printed. End-of-session §13, then the
maintainer commits and pushes the result records — the session itself commits and pushes nothing. Update the session note with what
ran, what did not, and the verification results.


**How to use this file**

- Every step has a command, an *expected* result, and a **STOP** rule. If a STOP rule fires,
  stop, report the exact output, and wait for the maintainer. Do not "work around" a STOP.
- Standing rules (`README.md` in this folder): **no git write operations** (no `add`, `commit`,
  `push`, `reset`, `rebase`, `checkout` of files, branch changes) — the maintainer commits
  manually. The single sanctioned mutation is the fast-forward pull in section 2, and only after the
  maintainer says go. The test set is never used for selection, tuning or calibration.
- Verification tags used below: **[ran here]** executed on the laptop on 2026-09-21 against this
  repo (KERMT replaced by a labelled test double where it would be needed — this proves imports,
  signatures, file paths and data flow, and says nothing about real KERMT). **[recorded 9-18]**
  executed on the workstation on 2026-09-18 per `../status/kermt_integration_status.md`.
  **[not verifiable here]** depends on the workstation and has never been run.
- Long commands (a real fine-tune, Tier-0 arms) must be launched detached (`nohup ... &`, or the
  harness's background-run option) and polled. A foreground call can hit the tool timeout and
  orphan a half-finished run.

**Identities pinned for this session**

| Item | Value | Source |
|---|---|---|
| Canonical prep ID (basis of the 70 XGBoost runs and their held-out test evaluation) | `20260830T200000Z` — exists on the laptop only | `ml/data/metadata/prep_fingerprint.20260830T200000Z.json` |
| Workstation prep ID (what KERMT will actually read) | `20260918T090433Z` — gitignored, workstation only | `next_steps.md`, `decisions.md` 2026-09-21 |
| Checkpoint sha256 | `e9e6649bc96503fbdb3023e312764ecbbbafd686d9a62865a1fec9466cea6be3` | `ml/data/metadata/kermt_checkpoint.lock.json` |
| KERMT source | `github.com/NVIDIA-BioNeMo/KERMT` tag `v2.0.0`, commit `e402473376ace30fa0092dad0578a88bf7f67287` | same lockfile |
| Docker image | `kermt:latest` — **no pinned image id exists anywhere**; record it at runtime | `train/readiness_report.py` (`env.docker_image`) |
| GPU | RTX A4000, 16376 MiB, driver 580.173.02 | `../status/kermt_integration_status.md` §6 [recorded 9-18] |
| W&B | entity `shashquatch`, project `mars-admet` | `.env.example`, `context.md` |
| First real run | `dili_standalone__cls`, seed 0, `kermt_single`, harness defaults | `next_steps.md` checklist item 4 |

---

## 0. Objective

**Primary:** get the first real KERMT fine-tune → calibrate → held-out-test runs completed, verified
and tracked in W&B — starting with `dili_standalone__cls`, seed 0.

**Secondary:**

1. Validate GPU execution end to end (host → container → GPU → back), including peak VRAM.
2. Validate calibration on **real KERMT logits** (until now only a test double has run through it).
3. Establish held-out KERMT **test** evaluation (raw and calibrated) with leakage proof from the
   run's own input files.
4. Begin Tier-0 (type-homogeneous subgroups, stock KERMT CLI, equal weighting) **only if** the smoke
   test and the first real run both pass.

Explicitly **not** in scope tomorrow: Tier-1 (mixed-type trainer) and gates G1–G4 (the trainer does
not exist — see section 11), Tier-2 GPU runs, any data regeneration, any change to the split or
calibration policy, any git commit/push.

---

## 1. Before touching the code

```bash
pwd
git status --short
git branch --show-current
git log -1 --oneline
git remote -v
```

Expect: the repo root (`.../mars-work/mars-admet`), an **empty** `git status --short` (ignored files
do not appear), branch `milestone/m2-kermt`, remote `origin git@github.com:Shashquatch28/mars-admet.git`.

Then create the session environment file **once**. Each later block starts with `source` of it,
because shell state does not persist between calls. Adjust the two paths if `pwd`/`ls ~/mars-work`
shows different locations (they are as recorded 2026-09-18).

```bash
mkdir -p ~/mars-work
cat > ~/mars-work/lab_env.sh <<'EOF'
export MARS_REPO="$HOME/mars-work/mars-admet"
export MARS_KERMT_REPO="$HOME/mars-work/kermt-src"
export MARS_KERMT_IMAGE="kermt:latest"
export WANDB_PROJECT="mars-admet"
export WANDB_ENTITY="shashquatch"
export PREP_ID="20260918T090433Z"
export CANON_PREP_ID="20260830T200000Z"
export PYTHONPATH=.
export PY="$MARS_REPO/.venv/bin/python"
export LAB="runs/lab_helpers"
export LOGS="runs/lab_logs"
cd "$MARS_REPO/ml"
EOF
source ~/mars-work/lab_env.sh && pwd && ls "$MARS_KERMT_REPO/agent/scripts/kermt_container.sh" && test -x "$PY" && echo "venv python ok"
```

`WANDB_ENTITY`/`WANDB_PROJECT` **must be exported**: `tracking/wandb_logger.py` reads only the
process environment. Nothing in `ml/` loads `.env` (grep-verified), so a value sitting in a `.env`
file is silently ignored and `entity` falls back to the logged-in account's default.

**Verify the expected commit.** The SHA is created when the maintainer commits and pushes on the
laptop. **Ask for it — never reuse an old one** (`~/mars-work/lab_env.sh` currently pins `ae5d28d`, the Pass-1 commit; it must be
**replaced**, not appended to, so exactly one `EXPECTED_SHA` line exists):

```bash
NEW_SHA=<paste the 40-char SHA the maintainer pushed>
sed -i.bak '/^export EXPECTED_SHA=/d' ~/mars-work/lab_env.sh       # drops the stale pin; keeps lab_env.sh.bak
echo "export EXPECTED_SHA=$NEW_SHA" >> ~/mars-work/lab_env.sh
source ~/mars-work/lab_env.sh
grep -c '^export EXPECTED_SHA=' ~/mars-work/lab_env.sh              # MUST print 1
git rev-parse HEAD          # BEFORE the pull this is the workstation's old commit — expected
git rev-parse origin/milestone/m2-kermt   # local view of the remote; stale until the fetch in section 2
```

```bash
[[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]] && echo "EXPECTED_SHA format ok" || echo "STOP: EXPECTED_SHA not set"
```

**STOP** if `EXPECTED_SHA` is empty or not 40 hex characters, if `git status --short` is non-empty,
or if the branch is not `milestone/m2-kermt`.

---

## 2. Pull latest repository

Goal: get the pushed commit without overwriting anything on the workstation that is not in Git.
Fetching and inspecting is read-only; the final `git pull --ff-only` is the one sanctioned mutation
and needs the maintainer's go-ahead.

```bash
source ~/mars-work/lab_env.sh
cd "$MARS_REPO"
git fetch origin
git status -sb                                             # ahead/behind vs origin, and dirtiness
git log --oneline HEAD..origin/milestone/m2-kermt          # what the pull will bring in
git log --oneline origin/milestone/m2-kermt..HEAD          # workstation-only commits; MUST be empty
git diff --stat HEAD origin/milestone/m2-kermt | tail -3   # size of the change
git rev-parse origin/milestone/m2-kermt                    # MUST equal $EXPECTED_SHA
```

Collision check — a pull refuses (or worse, surprises) when an untracked local file has the same path
as an incoming tracked file:

```bash
git ls-tree -r --name-only origin/milestone/m2-kermt | while read -r f; do
  if [ -e "$f" ] && ! git ls-files --error-unmatch "$f" >/dev/null 2>&1; then echo "COLLISION (untracked locally): $f"; fi
done; echo "collision scan done"
```

**STOP** (do not pull) if: the workstation has commits the remote lacks; `git status --short` is
non-empty (uncommitted local work); any `COLLISION` line prints; or the remote tip is not
`$EXPECTED_SHA`. Report and let the maintainer decide — never `stash`, `reset` or `checkout --` on
their behalf.

Pull (after go-ahead), then prove the checkout is what was intended:

```bash
git pull --ff-only origin milestone/m2-kermt
test "$(git rev-parse HEAD)" = "$EXPECTED_SHA" && echo "HEAD == EXPECTED_SHA" || echo "STOP: HEAD mismatch"
git status --short                                         # MUST be empty
for f in ml/train/train_kermt_cluster.py ml/eval/cluster_calibration.py ml/eval/calibration_diagnostics.py \
         ml/data/cluster_loaders.py ml/configs/clusters.py ml/data/compare_prep.py ml/train/readiness_report.py \
         ml/train/preflight_clusters.py ml/models/kermt_model.py ml/featurize/kermt_adapter.py \
         ml/utils/rng_state.py ml/data/metadata/kermt_checkpoint.lock.json \
         ml/data/metadata/prep_fingerprint.20260830T200000Z.json documentation/AIMS/lab_session_tasks.md; do
  test -f "$f" && echo "ok   $f" || echo "MISSING $f"
done
```

Expect: every file `ok`, HEAD == EXPECTED_SHA, clean tree. **STOP** on any `MISSING`.

Install the session helper scripts. They live under `ml/runs/` (gitignored, so the tree stays clean
and recorded `git.dirty` stays `False`). Each was executed here against a KERMT test double
**[ran here]**; the runbook text below is byte-identical to what was run.

```bash
source ~/mars-work/lab_env.sh
mkdir -p "$LAB" "$LOGS"

cat > "$LAB/s_ckpt.py" <<'PY'
import json
import sys
from pathlib import Path

from eval.heldout_evaluation import sha256_file

lock = json.loads(Path("data/metadata/kermt_checkpoint.lock.json").read_text(encoding="utf-8"))
root = Path(lock["local_path"].replace("ml/", "", 1))
bad = 0
for name, rec in lock["files"].items():
    f = root / name
    if not f.exists():
        print(f"[FAIL] {name}: missing at {f}")
        bad += "model card" not in rec["role"]  # the model card is provenance text, not needed to train
        continue
    ok = f.stat().st_size == rec["bytes"] and sha256_file(f) == rec["sha256"]
    bad += not ok and "model card" not in rec["role"]
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {f.stat().st_size} bytes, sha256 {'matches' if ok else 'DIFFERS from'} lockfile")
sys.exit(1 if bad else 0)
PY

cat > "$LAB/s_wandb.py" <<'PY'
import os

import wandb

viewer = wandb.Api().viewer  # read-only; creates nothing, prints no secret
print("wandb", wandb.__version__)
print("logged-in user:", viewer.username)
print("teams:", [t for t in getattr(viewer, "teams", [])])
print("WANDB_ENTITY env:", os.environ.get("WANDB_ENTITY"), "| WANDB_PROJECT env:", os.environ.get("WANDB_PROJECT"))
print("WANDB_API_KEY set in env:", bool(os.environ.get("WANDB_API_KEY")), "(value never printed)")
PY

cat > "$LAB/s_ames.py" <<'PY'
import json
import math
import os
from pathlib import Path

import numpy as np
from data.loaders import load_endpoint
from data.split import five_seed_train_val_folds
from eval.metrics import compute_metrics
from mars_contracts.endpoints import TaskType
from models.kermt_model import KermtConfig, KermtModel

prep = Path("data/processed") / os.environ["PREP_ID"]
ckpt = Path("data/checkpoints/kermt/NV-KERMT-70M-v2/kermt_contrastive_v2.0.pt")
work = Path("runs") / f"kermt_smoke_ames_{os.environ['SMOKE_TAG']}"
assert not work.exists(), f"{work} exists - a stale run.json would mask a failed fit; pick a new SMOKE_TAG"

ep = load_endpoint(prep, "ames_mutagenicity")
label = dict(zip(ep.train_val["standardized_smiles"], ep.train_val["label"].astype(float), strict=True))
_, train_smiles, val_smiles = five_seed_train_val_folds(ep.train_val["standardized_smiles"].tolist(), seeds=(0,))[0]
rng = np.random.default_rng(0)
train_sub = [train_smiles[i] for i in rng.choice(len(train_smiles), 300, replace=False)]
val_sub = [val_smiles[i] for i in rng.choice(len(val_smiles), 80, replace=False)]
y_train = np.array([label[s] for s in train_sub])
y_val = np.array([label[s] for s in val_sub])

m = KermtModel(TaskType.CLASSIFICATION, ckpt, ["ames_mutagenicity"], config=KermtConfig(epochs=3, batch_size=16))
m.fit(train_sub, y_train, X_val=val_sub, y_val=y_val, run_dir=work)
preds = m.predict(val_sub, run_dir=work)
m.save(work / "saved")
preds_reload = KermtModel.load(work / "saved").predict(val_sub, run_dir=work / "reload")
auroc = compute_metrics(y_val, preds, TaskType.CLASSIFICATION).auroc

checks = {
    "fit() returned (run.json status ok, checkpoint produced)": m.is_fitted,
    "finetuned model.pt exists": (work / "ckpt" / "fold_0" / "model_0" / "model.pt").exists(),
    "saved copy exists": (work / "saved" / "model.pt").exists(),
    "all predictions finite": bool(np.isfinite(preds).all()),
    "all predictions in [0, 1]": bool(((preds >= 0) & (preds <= 1)).all()),
    "reload reproduces predictions bit-identically": bool(np.array_equal(preds, preds_reload)),
    "val AUROC > 0.5 (recorded 2026-09-18: 0.7244)": bool(math.isfinite(auroc) and auroc > 0.5),
}
for name, ok in checks.items():
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
print(json.dumps({"val_auroc": auroc, "work_dir": str(work)}))
raise SystemExit(0 if all(checks.values()) else 1)
PY

cat > "$LAB/s_run.py" <<'PY'
import dataclasses
import json
import os
import subprocess
import time
from pathlib import Path

from configs.clusters import all_subgroups
from configs.experiment_config import ExperimentConfig
from data.cluster_loaders import load_cluster
from eval.heldout_evaluation import sha256_file
from models.kermt_model import KermtConfig
from train.train_kermt_cluster import train_one_seed

key = os.environ["SUBGROUP"]
seeds = [int(s) for s in os.environ.get("SEEDS", "0").split(",")]
variant = os.environ.get("VARIANT", "")
use_wandb = os.environ.get("WANDB", "0") == "1"
prep_id = os.environ["PREP_ID"]
kc = KermtConfig(
    epochs=int(os.environ["EPOCHS"]) if os.environ.get("EPOCHS") else None,
    batch_size=int(os.environ["BATCH"]) if os.environ.get("BATCH") else None,
)
ckpt = Path("data/checkpoints/kermt/NV-KERMT-70M-v2/kermt_contrastive_v2.0.pt")
lock = json.loads(Path("data/metadata/kermt_checkpoint.lock.json").read_text(encoding="utf-8"))
spec = all_subgroups()[key]
cd = load_cluster(Path("data/processed") / prep_id, list(spec.endpoints), cluster_key=key)


def git(*args):
    return subprocess.run(["git", "-C", "..", *args], capture_output=True, text=True).stdout.strip()


ckpt_sha = sha256_file(ckpt)
want_sha = lock["files"]["kermt_contrastive_v2.0.pt"]["sha256"]
assert ckpt_sha == want_sha, f"STOP: checkpoint sha256 {ckpt_sha} != lockfile {want_sha}"
print(
    json.dumps(
        {
            "git_sha": git("rev-parse", "HEAD"),
            "git_dirty": bool(git("status", "--porcelain")),
            "prep_id": cd.prep_id,
            "subgroup": key,
            "endpoints": list(spec.endpoints),
            "model_family": spec.model_family,
            "seeds": seeds,
            "variant": variant,
            "use_augmented_dili": False,
            "checkpoint_sha256": ckpt_sha,
            "kermt_source_commit": lock["model"]["source_code_commit"],
            "kermt_config": dataclasses.asdict(kc),
            "use_wandb": use_wandb,
            "wandb_project": os.environ.get("WANDB_PROJECT"),
            "wandb_entity": os.environ.get("WANDB_ENTITY"),
            "run_name_prefix": [
                ExperimentConfig(key, spec.model_family, s, cd.prep_id, variant=variant).run_name()
                for s in seeds
            ],
            "train_pool_labels_lost_to_calibration_holdout": cd.train_pool()[1],
            "sacrifice_fraction_vs_union_test_removal": cd.split_report.sacrifice_fraction,
        },
        indent=2,
    ),
    flush=True,
)

for seed in seeds:
    cfg = ExperimentConfig(
        endpoint=key,
        model_family=spec.model_family,
        seed=seed,
        prep_id=cd.prep_id,
        variant=variant,
        hyperparams=dataclasses.asdict(kc),
        notes=os.environ.get("NOTES", ""),
    )
    t0 = time.time()
    res = train_one_seed(
        cd, spec, cfg, seed, checkpoint=ckpt, kermt_config=kc,
        runs_dir=Path("runs"), use_wandb=use_wandb,
    )
    summary = {
        "run_id": res.run_id,
        "seed": seed,
        "wall_seconds": round(time.time() - t0, 1),
        "n_train": res.n_train,
        "n_val": res.n_val,
        "wandb_url": res.wandb_url,
        "model_path": str(res.model_path),
        "val_metrics": {k: dataclasses.asdict(m) for k, m in res.per_endpoint_metrics.items()},
        "calibration": res.calibration,
    }
    (Path("runs") / res.run_id / "lab_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, default=str), flush=True)
PY

cat > "$LAB/s_verify.py" <<'PY'
import csv
import json
import math
import os
import sys
from pathlib import Path

from data.cluster_loaders import load_cluster
from configs.clusters import all_subgroups

run = Path("runs") / os.environ["RUN_ID"]
lock = json.loads(Path("data/metadata/kermt_checkpoint.lock.json").read_text(encoding="utf-8"))
cfg = json.loads((run / "config.json").read_text(encoding="utf-8"))
meta = json.loads((run / "run.json").read_text(encoding="utf-8"))
prov = json.loads((run / "provenance.json").read_text(encoding="utf-8"))
metrics = [json.loads(line)["metrics"] for line in (run / "metrics.jsonl").read_text(encoding="utf-8").splitlines()]
spec = all_subgroups()[cfg["endpoint"]]
cd = load_cluster(Path("data/processed") / cfg["prep_id"], list(spec.endpoints), cluster_key=spec.key)

results: list[tuple[str, bool, str]] = []
warnings_: list[tuple[str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))


def warn_if(name: str, bad: bool, detail: str = "") -> None:
    if bad:
        warnings_.append((name, detail))


def finite(x) -> bool:
    return x is not None and math.isfinite(float(x))


check("run.json status == completed", meta.get("status") == "completed", str(meta.get("status")))
model_pt = run / "artifacts" / "model" / "kermt" / "model.pt"
check("finetuned model.pt saved and non-empty", model_pt.exists() and model_pt.stat().st_size > 0, str(model_pt))
val_recs = [m for m in metrics if m.get("split") == "val"]
cal_recs = [m for m in metrics if m.get("split") == "calibration+test"]
check("a val record per endpoint", len(val_recs) == len(spec.endpoints), f"{len(val_recs)} records")
for m in val_recs:
    key_metric = "auroc" if m["endpoint"] in cd.positive_rates() else "mae"
    check(f"val {key_metric} finite [{m['endpoint']}]", finite(m.get(key_metric)), f"{m.get(key_metric)}")
check("a calibration+test record per endpoint", len(cal_recs) == len(spec.endpoints), f"{len(cal_recs)} records")
for r in cal_recs:
    ep = r["endpoint_key"]
    raw = r["test_metrics_raw"]
    check(f"test metrics present [{ep}]", raw is not None, "")
    if r["task_type"] == "classification":
        check(f"calibration fitted [{ep}]", r["status"] in ("fitted", "fitted_at_boundary"), r["status"])
        check(f"temperature finite and > 0 [{ep}]", finite(r["temperature"]) and r["temperature"] > 0, str(r["temperature"]))
        check(f"optimizer_success [{ep}]", r["optimizer_success"] is True, str(r["optimizer_success"]))
        warn_if(f"temperature pinned at the search boundary [{ep}]", r["at_boundary"] is not False, str(r["temperature"]))
        warn_if(f"calibration N below blueprint floor of 50 [{ep}]", (r["n_fit_samples"] or 0) < 50, str(r["n_fit_samples"]))
        warn_if(f"NLL not improved by calibration [{ep}]", r["nll_improved"] is not True, "")
        check(f"calibration has both classes [{ep}]", (r["n_positive"] or 0) > 0 and (r["n_negative"] or 0) > 0,
              f"pos={r['n_positive']} neg={r['n_negative']} n={r['n_fit_samples']}")
        cal = r["test_metrics_calibrated"]
        check(f"raw AUROC == calibrated AUROC [{ep}]",
              cal is not None and abs(raw["auroc"] - cal["auroc"]) < 1e-6,
              f"raw={raw['auroc']} cal={None if cal is None else cal['auroc']}")
    check(f"checkpoint_sha256 recorded == lockfile [{r['endpoint_key']}]",
          r["checkpoint_sha256"] == lock["files"]["kermt_contrastive_v2.0.pt"]["sha256"], str(r["checkpoint_sha256"]))
    check(f"prep_id recorded [{r['endpoint_key']}]", r["prep_id"] == cfg["prep_id"], str(r["prep_id"]))

# Leakage proof on the ACTUAL files handed to KERMT for this run.
inp = run / "artifacts" / "kermt" / "input"
train = {row["smiles"] for row in csv.DictReader((inp / "train.csv").open(encoding="utf-8"))}
val = {row["smiles"] for row in csv.DictReader((inp / "val.csv").open(encoding="utf-8"))}
test, cal = set(cd.smiles("test")), cd.calibration_molecules()
check("train.csv disjoint from TEST", not (train & test), f"overlap={len(train & test)} train={len(train)}")
check("val.csv disjoint from TEST", not (val & test), f"overlap={len(val & test)} val={len(val)}")
check("train.csv disjoint from CALIBRATION", not (train & cal), f"overlap={len(train & cal)}")
check("val.csv disjoint from CALIBRATION", not (val & cal), f"overlap={len(val & cal)}")
check("train.csv disjoint from val.csv", not (train & val), f"overlap={len(train & val)}")
check("provenance has git commit", bool(prov.get("git", {}).get("commit")), str(prov.get("git", {}).get("commit")))
check("config.json records hyperparams + prep_id", "hyperparams" in cfg and bool(cfg.get("prep_id")), str(cfg.get("hyperparams")))

width = max(len(n) for n, _, _ in results)
for name, ok, detail in results:
    print(f"[{'PASS' if ok else 'FAIL'}] {name:<{width}}  {detail}")
for name, detail in warnings_:
    print(f"[WARN] {name}  {detail}")
print("git.dirty recorded for this run:", prov.get("git", {}).get("dirty"))
failed = [n for n, ok, _ in results if not ok]
print("\nVERDICT:", "FAIL - " + "; ".join(failed) if failed else "PASS")
sys.exit(1 if failed else 0)
PY

cat > "$LAB/s_agg.py" <<'PY'
import json
import os
from pathlib import Path

from eval.cluster_calibration import (
    aggregate_calibration_across_seeds,
    aggregate_test_metrics_across_seeds,
)

key = os.environ["SUBGROUP"]
variant = os.environ.get("VARIANT", "")
prep_id = os.environ["PREP_ID"]
latest: dict[int, tuple[str, Path]] = {}  # seed -> newest completed run
for run in sorted(Path("runs").glob("kermt_*")):  # run ids end in a UTC timestamp, so sorted == chronological
    if not (run / "config.json").exists():
        continue
    cfg = json.loads((run / "config.json").read_text(encoding="utf-8"))
    meta = json.loads((run / "run.json").read_text(encoding="utf-8"))
    if (cfg["endpoint"], cfg.get("variant", ""), cfg["prep_id"]) != (key, variant, prep_id):
        continue
    if meta.get("status") != "completed":
        print("SKIP (not completed):", run.name, meta.get("status"))
        continue
    latest[int(meta["seed"])] = (run.name, run)

records = []
for seed, (name, run) in sorted(latest.items()):
    for f in sorted((run / "artifacts" / "calibration").glob("*/calibration_diagnostics.json")):
        records.append(json.loads(f.read_text(encoding="utf-8")))
print("seeds found:", sorted(latest), "| runs:", [n for n, _ in latest.values()])
assert sorted(latest) == [0, 1, 2, 3, 4], "STOP: need completed runs for all 5 fixed seeds before reporting mean +/- std"
out = {
    "subgroup": key,
    "prep_id": prep_id,
    "test_metrics_across_seeds": aggregate_test_metrics_across_seeds(records),
    "calibration_stability_across_seeds": aggregate_calibration_across_seeds(records),
}
dest = Path("runs") / f"kermt_tier0_{key}{'_' + variant if variant else ''}_aggregate.json"
dest.write_text(json.dumps(out, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
print(json.dumps(out, indent=2, sort_keys=True, default=str))
print("wrote", dest)
PY

ls -l "$LAB"
```

What each helper is for: `s_ckpt.py` checkpoint files vs lockfile · `s_wandb.py` read-only W&B auth
check · `s_ames.py` the recorded tiny AMES fine-tune (smoke A) · `s_run.py` one subgroup × N seeds
through the real harness (`train_one_seed`) with a printed pre-launch banner · `s_verify.py`
PASS/FAIL audit of one finished run · `s_agg.py` 5-seed mean ± std after a Tier-0 arm.

---

## 3. Verify GPU

```bash
nvidia-smi
nvidia-smi --query-gpu=name,memory.total,memory.used,driver_version,compute_cap --format=csv
nvidia-smi --query-compute-apps=pid,name,used_memory --format=csv     # who else holds the GPU
docker run --rm --gpus all nvidia/cuda:12.6.3-base-ubuntu22.04 nvidia-smi
```

| Check | Expected / acceptable | STOP if |
|---|---|---|
| GPU | `NVIDIA RTX A4000` | no NVIDIA device listed |
| VRAM | `16376 MiB` total (KERMT floor: 8192 MiB at batch 32 — `readiness_report.py::MIN_GPU_MIB`) | total < 8192 MiB |
| Baseline `memory.used` | ~400 MiB (desktop process; 412 MiB on 9-18) | > 2000 MiB, or another compute app listed — record it, ask before proceeding |
| Driver | `580.173.02` recorded; any driver supporting CUDA 12.6+ is acceptable | driver older than the CUDA 12.6 runtime requirement |
| Docker GPU access | the `nvidia-smi` table prints from inside the container [recorded 9-18 with exactly this image] | `could not select device driver` / `unknown runtime` |

CUDA visibility **inside the KERMT container** (the only place torch runs — no torch on the host by
design). This uses the `--ckpt` mount contract that `models/kermt_model.py::_run_container` uses;
the inner `python -c` quoting is **[not verifiable here]** — if it errors on quoting only, rely on
the `check_checkpoint.py` run in section 4 plus the smoke test:

```bash
source ~/mars-work/lab_env.sh
CKPT="$PWD/data/checkpoints/kermt/NV-KERMT-70M-v2/kermt_contrastive_v2.0.pt"
"$MARS_KERMT_REPO/agent/scripts/kermt_container.sh" run --ckpt "$CKPT" -- \
  "python -c 'import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.device_count())'"
```

Expect `2.9.1 True 1` [recorded 9-18: torch 2.9.1, CUDA 12.8 runtime]. **STOP** on `False` or
`0` (CUDA unavailable) — do not fall back to CPU; KERMT is GPU-only here.

Record for the session log: `nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader`.

---

## 4. Verify repository dependencies

```bash
source ~/mars-work/lab_env.sh
$PY --version                                            # expect Python 3.11.x
$PY -c "import numpy, pandas, sklearn, scipy, rdkit, wandb, mars_contracts; print('numpy', numpy.__version__, '| pandas', pandas.__version__, '| sklearn', sklearn.__version__, '| rdkit', rdkit.__version__, '| wandb', wandb.__version__)"
$PY -c "import train.train_kermt_cluster, eval.cluster_calibration, models.kermt_model, data.compare_prep, eval.heldout_evaluation, train.readiness_report, train.preflight_clusters; print('harness imports ok')"
docker --version                                         # 29.1.3 recorded
docker info --format '{{json .Runtimes}}' | grep -o nvidia   # the nvidia runtime is registered
nvidia-ctk --version                                     # NVIDIA Container Toolkit; 1.20.0 recorded
git -C "$MARS_KERMT_REPO" rev-parse HEAD                 # MUST be e402473376ace30fa0092dad0578a88bf7f67287
git -C "$MARS_KERMT_REPO" describe --tags --exact-match  # expect v2.0.0
git -C "$MARS_KERMT_REPO" status --short                 # expect empty (unmodified upstream checkout)
docker image ls kermt:latest
docker image inspect kermt:latest --format '{{.Id}}  created {{.Created}}'
```

Expect: imports print without traceback; `torch` is not needed on the host (KERMT runs in its container; the
readiness report says so); KERMT HEAD equals the lockfile commit; the `kermt:latest` image exists.
**RECORD the image id** in the session log — there is no pinned expectation to compare it to, so
identity is recorded, not verified (a provenance gap; do not claim otherwise).

**STOP** if: a host import fails (install into the repo venv only — never into the container, never
touch `ml/.venv`'s laptop pins); the KERMT HEAD differs from `e402473...` or the checkout is dirty;
the image is missing. If only the image is missing, building it is long
(`"$MARS_KERMT_REPO/agent/scripts/kermt_container.sh" ensure_image`, per `kermt_integration_status.md`
§4) — ask the maintainer before starting it.

Run the CPU unit tests for everything on the tomorrow path (fast, no GPU, no data needed):

```bash
source ~/mars-work/lab_env.sh
$PY -m pytest -q -p no:cacheprovider tests/test_kermt_model.py tests/test_kermt_adapter.py \
  tests/test_train_kermt_cluster_calibration.py tests/test_cluster_calibration.py \
  tests/test_calibration_diagnostics.py tests/test_cluster_loaders.py tests/test_clusters.py \
  tests/test_cluster_eval.py tests/test_compare_prep.py tests/test_readiness_report.py \
  tests/test_experiment_config.py tests/test_calibration.py 2>&1 | tail -8
```

Expect **0 failed**: 219 passed on the laptop (2026-09-21, ~110 s) and **216 passed, 3 skipped** on the workstation (2026-09-30: the
canonical-snapshot tests ×2 are laptop-only, xgboost is not installed ×1); these tests need no data, no GPU and no
checkpoint, but `test_readiness_report.py` needs the checkout to be a git repository — it is). Any
failure here is a STOP: something differs between the pushed code and what was tested.
A clean export of the committable files (no `.git`) also passed everything except
`test_run_naming_and_provenance_checks_exercise_the_real_code`, which needs a git repo.
The full suite (`$PY -m pytest -q -p no:cacheprovider`, ~7 min on the laptop) is
optional and non-blocking; the only known failures are the 5 in `tests/test_acquisition_lockfile.py`
(on the workstation 3 of them may now pass because `raw/*/20260918T090143Z/` exists there).

---

## 5. Verify data

**Do not download or regenerate anything** unless a check below proves it is missing — and then ask.

**5a. Which snapshots exist**

```bash
source ~/mars-work/lab_env.sh
ls data/processed/                                        # expect 20260918T090433Z
test -f "data/processed/$PREP_ID/manifest.json" && echo "manifest present"
ls "data/processed/$PREP_ID" | head -30                   # 15 dataset dirs (+ __augmented / __benchmark variants) + manifest.json
df -h . | tail -1                                         # record free disk before any training
```

**5b. Workstation fingerprint vs canonical** (closes the open "processed identity D" item).
Manifests cannot be diffed — they embed absolute paths — so split files are hashed:

```bash
source ~/mars-work/lab_env.sh
$PY data/compare_prep.py fingerprint --prep-dir "data/processed/$PREP_ID" --out "$LOGS/ws_fingerprint.json"
$PY data/compare_prep.py compare --a data/metadata/prep_fingerprint.$CANON_PREP_ID.json --b "$LOGS/ws_fingerprint.json" \
  | tee "$LOGS/prep_compare.json" | grep -E '"overall"|"pipeline_version_mismatch"|"counts"' -A6 | head -24
```

**Acceptable:** `overall` = `A_BYTE_IDENTICAL` or `B_CONTENT_IDENTICAL_REGENERATED`. Expect **B**
rather than A: the laptop's CSVs are CRLF (verified) and the workstation's will be LF — the
comparison hashes canonical content for exactly this reason. `pipeline_version_mismatch` must be
`{}`. **STOP** on `C_MATERIALLY_DIFFERENT` (KERMT would not be comparable with the XGBoost
baselines) or `D_UNABLE_TO_VERIFY`. The exit code is 0 for A/B and 1 otherwise.

**5c. Checkpoint files and SHA-256** (all five files in the lockfile, size and hash):

```bash
source ~/mars-work/lab_env.sh
$PY "$LAB/s_ckpt.py"
sha256sum data/checkpoints/kermt/NV-KERMT-70M-v2/kermt_contrastive_v2.0.pt
# must print e9e6649bc96503fbdb3023e312764ecbbbafd686d9a62865a1fec9466cea6be3
```

**STOP** on any `[FAIL]` (missing file → the checkpoint dir was not populated; re-download is
`curl` from the HF URLs recorded in the lockfile — ask first, it is ~283 MB; hash mismatch →
never proceed).

**5d. Readiness report on the workstation.** Pass the **workstation** prep id. Do **not** pass
`--workstation-fingerprint`: `train/readiness_report.py` derives the canonical fingerprint's
filename from `--prep-id`, so with the workstation id it looks for a
`prep_fingerprint.20260918T090433Z.json` that does not exist (the check then errors — a
comparison-gate failure, not a smoke blocker, but noise). Identity is established by 5b instead.
(This corrects `next_steps.md` checklist item 2, which suggests passing it.)

```bash
source ~/mars-work/lab_env.sh
IMG_ID=$(docker image inspect kermt:latest --format '{{.Id}}'); echo "image id: $IMG_ID"
$PY train/readiness_report.py --target workstation --prep-id "$PREP_ID" --out "$LOGS/readiness_report_ws.json" | tee "$LOGS/readiness_report_ws.txt"
```

Expect `READY_FOR_GPU_SMOKE_TEST`. Acceptable non-blocking lines: `env.docker_image` WARN (no pinned
id — you have recorded it), `data.workstation_identity` WARN "NOT ESTABLISHED" (settled by 5b),
`repro.git_sha` must be PASS (clean tree), `eval.xgboost_heldout` FAIL with gate `comparison`
(`runs/test_evaluations/` exists only on the laptop — not needed here), `data.lockfile_consistency`
PASS (workstation acquisition equals the tracked lockfile), `data.calibration_availability` WARN (lists the
known small/one-class calibration sets — HIA N=47 with 1 negative — and does not block the DILI smoke
endpoint), `repro.known_gaps`/`tracking.wandb` WARN informational. **STOP** if the verdict is `BLOCKED` — the printed `SMOKE-TEST BLOCKERS` lines are the
diagnosis. Exit code 1 means BLOCKED.

**5e. Cluster preflight** (re-confirms leakage cost and the Tier-2 bin choice on this snapshot —
CPU only, the `xgb_mae` columns read `n/a` without `runs/evaluations/`):

```bash
source ~/mars-work/lab_env.sh
$PY train/preflight_clusters.py --prep-dir "data/processed/$PREP_ID" --out "$LOGS/cluster_preflight_ws.json" | tee "$LOGS/cluster_preflight_ws.txt" | head -30
```

Expect (laptop values on the canonical snapshot **[ran here]**; the workstation snapshot must
match): `dili_standalone__cls` train_val 378 rows / test 96 / calibration 50, dropped 0 (0.0%);
`toxicity__cls` 0.2% worst sacrifice; `absorption_distribution__cls` 4.6%;
`absorption_distribution__reg` 14.6%; `metabolism__reg` 0.0%; `metabolism__cls` **WARN** 29.2%
(5,625 rows dropped — Option A, confirmed in `decisions.md` 2026-09-30 D5); the two whole-cluster rows (`metabolism` WARN 29.2%,
`absorption_distribution` ok 16.1%) are informational. **STOP** on any `ok`/`warn` status
different from these, or a row count that differs.

---

## 6. Verify W&B

Never print, log or paste the API key. Credentials are proven by a **read-only** API call (creates
nothing on the dashboard); the key itself is never echoed.

```bash
source ~/mars-work/lab_env.sh
test -f ~/.netrc && echo "~/.netrc present" || echo "no ~/.netrc"
$PY "$LAB/s_wandb.py"
```

Expect: `logged-in user: shashquatch28`, `teams: ['shashquatch']` **[ran here on the laptop; the
workstation's login is unverified]**, and `WANDB_ENTITY env: shashquatch`, `WANDB_PROJECT env:
mars-admet`. If credentials are missing (`wandb.errors` / "not logged in"), **STOP and ask the
maintainer to run `wandb login` themselves** — Claude never enters credentials.

Do **not** create a throwaway W&B run: project convention is "no W&B runs for debugging iterations".
The first real run (section 8) is the first W&B run; it is launched with `WANDB=1`, and W&B init/log
failures inside the harness are caught and warned (local `ExperimentRun` stays authoritative), so an
auth problem cannot destroy a training run — but it does leave you without a dashboard record, so
section 8 checks for the warning.

Run naming is fixed by `configs/experiment_config.py::ExperimentConfig.run_name()` plus a UTC
timestamp from `ExperimentRun`: `kermt_<st|mtsub>_<subgroup>_seed<N>[_<variant>]_<YYYYmmddTHHMMSSZ>`
(e.g. `kermt_st_dili_standalone__cls_seed0_20260922T101500Z`). The W&B run **name and id are both
that run id**. The timestamp is assigned at launch, so the exact name cannot be printed in advance;
the pre-launch banner prints the prefix and the run id is printed afterwards.

---

## 7. KERMT smoke test

Two stages, cheapest first. Both use fresh output directories and `WANDB=0` (no dashboard noise).

**7a — the recorded AMES tiny fine-tune** (300 train / 80 val, 3 epochs, batch 16: the exact job
that passed on 2026-09-18, wall ≈ 50 s). Isolates container + GPU + wrapper from the cluster
harness. A **fresh** directory is mandatory: `KermtModel.fit` trusts a `run.json` in the work dir,
so a stale one from 9-18 would mask a failed fit.

```bash
source ~/mars-work/lab_env.sh
export SMOKE_TAG=$(date -u +%Y%m%dT%H%M%SZ)
nvidia-smi --query-gpu=timestamp,memory.used,utilization.gpu --format=csv,noheader -l 2 > "$LOGS/vram_smoke_ames.csv" &
echo $! > "$LOGS/vram_smoke_ames.pid"
( time $PY "$LAB/s_ames.py" ) 2>&1 | tee "$LOGS/smoke_ames_$SMOKE_TAG.log"
kill "$(cat "$LOGS/vram_smoke_ames.pid")"
awk -F', ' '{gsub(/ MiB/,"",$2); if ($2+0>m) m=$2+0} END{print "peak VRAM " m " MiB"}' "$LOGS/vram_smoke_ames.csv"
grep -nE "loss_train|auc_val" "runs/kermt_smoke_ames_$SMOKE_TAG/logs/finetune.log" | head -12
```

**PASS** iff `s_ames.py` prints seven `[PASS]` lines and exits 0 **and** the log shows finite,
falling `loss_train` and rising-or-stable `auc_val` across the 3 epochs (recorded 9-18:
`loss_train` 1.3317 → 1.0341 → 0.8531, `auc_val` 0.6575 → 0.6756 → 0.7244; peak 1,909 MiB total of
which ~412 MiB is the desktop baseline). The mapping to what you asked to confirm:

| To confirm | Evidence |
|---|---|
| checkpoint loads | `fit()` first runs `check_checkpoint.py --mode finetune_init`; a rejection raises `RuntimeError` |
| forward pass works, loss finite | finite `loss_train` at epoch 0 in `finetune.log` |
| backward pass + optimizer step | `loss_train` decreases and `auc_val` moves over 3 epochs. KERMT's CLI has **no isolated forward/backward hook**; this is inferred from training dynamics, as it was on 9-18 |
| output/checkpoint produced | `ckpt/fold_0/model_0/model.pt` and the `saved/model.pt` copy exist; reload reproduces predictions bit-identically |
| W&B logging | **not exercised in smoke by design** (no debug runs); exercised by section 8 |

The `grep` pattern is taken from the 9-18 record — the log format itself is **[not verifiable
here]**. If it prints nothing, read the log tail (`tail -40 …/logs/finetune.log`) and judge the same
things by eye.

**STOP** on any `[FAIL]`, `RuntimeError`, a NaN/inf loss, an OOM, or `AUROC ≤ 0.5`. Diagnose
before any real run: the container's own log is `runs/kermt_smoke_ames_$SMOKE_TAG/logs/finetune.log`
(fit) or `.../predict_*/logs/inference.log` (predict). Do not retry blindly and do not launch a
larger job.

**7b — the calibration smoke test through the real harness** (`dili_standalone__cls`, seed 0,
3 epochs, batch 16, `VARIANT=smoke` so its run name/dir cannot be mistaken for the real run). This
is the first time **real KERMT logits** reach `predict_logits` → `fit_temperature_scaler`.

```bash
source ~/mars-work/lab_env.sh
SUBGROUP=dili_standalone__cls SEEDS=0 VARIANT=smoke WANDB=0 EPOCHS=3 BATCH=16 NOTES="lab smoke: 3 epochs, not a result" \
  $PY "$LAB/s_run.py" 2>&1 | tee "$LOGS/smoke_dili.log"
RUN_ID=$(ls -d runs/kermt_st_dili_standalone__cls_seed0_smoke_* | tail -1 | xargs basename)
RUN_ID=$RUN_ID $PY "$LAB/s_verify.py"
```

**PASS** iff `s_verify.py` ends `VERDICT: PASS` (20 `[PASS]` lines for this arm **[ran here with
the double]**). Real-KERMT things to read with your own eyes and record: the calibration record's
`n_positive`/`n_negative` (expect **13 / 37** of 50), `temperature`, `at_boundary`,
`optimizer_success`, `nll_before → nll_after`, `ece_before → ece_after`. A `[WARN] temperature
pinned at the search boundary` is **not** a failure — with 3 epochs of training and a 50-molecule
calibration set it is plausible — but record it; it tells you what to expect from the real run.

**STOP** on `VERDICT: FAIL`. In particular a leakage line (`train.csv disjoint from TEST/CALIBRATION`)
failing means test or calibration molecules reached KERMT — **test leakage: stop everything.**

---

## 8. First real KERMT training run — `dili_standalone__cls`, seed 0

Configuration = the harness defaults, deliberately: `KermtConfig()` with every field unset, so
KERMT's own `agent/config/defaults_finetune.json` decides epochs/batch/LR (only `metric` is resolved,
to `auc`, by `KermtModel._default_metric`); equal weighting (the stock CLI cannot do anything else);
`holdout_calibration=True`; `use_augmented_dili=False`; seed 0; all of it recorded in the run's
`config.json`. **No hyperparameters were ever tuned or approved beyond these defaults** — if the
maintainer wants specific `EPOCHS`/`BATCH`, they pass them and they are recorded.

*(Historical — this section describes the 2026-09-22 DILI seed-0 run.)* Two decisions were open then and are **resolved in
`decisions.md` 2026-09-30**: DILI trains on the **base** pool (287 train; XGBoost used the augmented pool, 979) — kept, and labelled
as the non-augmented variant (D6); `holdout_calibration=True` — kept for every arm and seed (D2). Both are pinned in each run's
`config.json`.

Record KERMT's own defaults first (they are not in this repo):

```bash
source ~/mars-work/lab_env.sh
cat "$MARS_KERMT_REPO/agent/config/defaults_finetune.json" | tee "$LOGS/kermt_defaults_finetune.json" | head -60
df -h . | tail -1; test "$(git -C "$MARS_REPO" rev-parse HEAD)" = "$EXPECTED_SHA" && echo "git ok" || echo "STOP: HEAD != EXPECTED_SHA"
```

Launch detached, with a VRAM sampler. `s_run.py` first **prints the pre-launch banner** — git SHA,
dirty flag, prep id, endpoint, seed, model family, checkpoint sha256 (recomputed, and asserted equal
to the lockfile), KERMT config, W&B entity/project and run-name prefix — then trains, calibrates,
scores the test set and writes `runs/<run_id>/lab_summary.json`.

```bash
source ~/mars-work/lab_env.sh
TAG=$(date -u +%Y%m%dT%H%M%SZ)
nvidia-smi --query-gpu=timestamp,memory.used,utilization.gpu --format=csv,noheader -l 2 > "$LOGS/vram_dili_s0_$TAG.csv" &
echo $! > "$LOGS/vram_dili_s0.pid"
nohup env SUBGROUP=dili_standalone__cls SEEDS=0 WANDB=1 NOTES="first real KERMT run" \
  $PY "$LAB/s_run.py" > "$LOGS/dili_s0_$TAG.log" 2>&1 &
echo $! > "$LOGS/dili_s0.pid"; echo "launched pid $(cat "$LOGS/dili_s0.pid"), tag $TAG"
sleep 20; head -40 "$LOGS/dili_s0_$TAG.log"      # the banner — confirm it before walking away
```

Check the banner against the table at the top: `git_sha` = `$EXPECTED_SHA`, `git_dirty` false,
`prep_id` `20260918T090433Z`, `model_family` `kermt_single`, `seeds` `[0]`,
`checkpoint_sha256` = `e9e6649b…6cea6be3`, `train_pool_labels_lost_to_calibration_holdout`
`{"dili_liver_injury": 50}`. **STOP and kill the job** (`kill "$(cat "$LOGS/dili_s0.pid")"`) if any
of it is wrong.

Poll (do not poll faster than every ~30 s):

```bash
source ~/mars-work/lab_env.sh
TAG=<the tag printed above>
kill -0 "$(cat "$LOGS/dili_s0.pid")" 2>/dev/null && echo "still running" || echo "finished"
tail -5 "$LOGS/dili_s0_$TAG.log"
grep -c "UserWarning: W&B" "$LOGS/dili_s0_$TAG.log"      # must be 0: nonzero = W&B was disabled for this run
```

When finished, collect everything to record:

```bash
source ~/mars-work/lab_env.sh
TAG=<tag>
kill "$(cat "$LOGS/vram_dili_s0.pid")" 2>/dev/null
awk -F', ' '{gsub(/ MiB/,"",$2); if ($2+0>m) m=$2+0} END{print "peak VRAM " m " MiB"}' "$LOGS/vram_dili_s0_$TAG.csv"
RUN_ID=$(ls -d runs/kermt_st_dili_standalone__cls_seed0_2* | tail -1 | xargs basename); echo "$RUN_ID"
RUN_ID=$RUN_ID $PY "$LAB/s_verify.py" | tee "$LOGS/verify_$RUN_ID.txt"
grep -nE "loss_train|auc_val" "runs/$RUN_ID/artifacts/kermt/logs/finetune.log" | tail -30
$PY -c "import json,sys; s=json.load(open('runs/$RUN_ID/lab_summary.json')); print('wall_seconds',s['wall_seconds'],'| n_train',s['n_train'],'| n_val',s['n_val'],'| wandb',s['wandb_url']); print('val',s['val_metrics']); print({k:{x:v[x] for x in ('status','temperature','at_boundary','optimizer_success','n_positive','n_negative','ece_before','ece_after','nll_before','nll_after')} for k,v in s['calibration'].items()}); print('test_raw',{k:v['test_metrics_raw'] for k,v in s['calibration'].items()}); print('test_cal',{k:v['test_metrics_calibrated'] for k,v in s['calibration'].items()})"
ls -l "runs/$RUN_ID/artifacts/model/kermt/" "runs/$RUN_ID/artifacts/calibration/dili_liver_injury/"
du -sh "runs/$RUN_ID"      # per-run disk cost — use it to budget the Tier-0 arms
```

Record in the session log: **wall time** (`wall_seconds`; note it includes container/prepare
overhead, like the 9-18 figure); **peak VRAM** (sampler; subtract the ~412 MiB baseline for KERMT's
own delta); **training loss** and the **saved epoch** (the epoch whose checkpoint is `ckpt/fold_0/model_0/model.pt`: take `N` from the
**last `Saving model at epoch N` line** of `finetune.log` (wording per the 2026-09-30 session note; not verified against KERMT source or a log on the laptop). **Do NOT use the final `best validation … on epoch N` line** — KERMT logs the
wrong epoch there (3/3 checked runs: logged 29/saved 18, 28/19, 26/21; `decisions.md` 2026-09-30 D1). Cross-check: the saved epoch's
validation score equals KERMT's logged best score, within 1e-3, and MARS's own `val_metrics`); **validation metrics** (`val_metrics`); **checkpoint path**
(`runs/<run_id>/artifacts/model/kermt/model.pt`, KERMT's own copy under `artifacts/kermt/ckpt/`);
**calibration diagnostics** (`artifacts/calibration/dili_liver_injury/calibration_diagnostics.json`,
`temperature_scaler.json`); **held-out test metrics, raw and calibrated** (`test_raw`/`test_cal`
above). Check the run in W&B at `wandb_url` (entity `shashquatch`, project `mars-admet`).

**Known W&B gap — do not be surprised:** `train_kermt_cluster.py` sends only *scalar* calibration
fields to W&B (temperature, ECE/NLL before/after, counts) and the validation metrics. The nested
**test-metric dicts (`test_metrics_raw` / `test_metrics_calibrated`) are not logged to W&B**; they
live in `metrics.jsonl`, `calibration_diagnostics.json` and `lab_summary.json`. That is the current
code, not a failed run. Do not change it during the session; note it for next steps.

**PASS** iff `s_verify.py` says `VERDICT: PASS`, no W&B warning, the W&B run is visible, and
`wall_seconds`/peak VRAM/losses are recorded. **STOP** on FAIL, NaN loss, OOM (record the batch
size; do not silently lower it — ask), or `optimizer_success: False`.

---

## 9. Held-out evaluation

`s_verify.py` (run in sections 7b and 8) is the audit. It re-derives the guarantees **from the run's
own files**, not from documentation:

| Guarantee | Where it is checked |
|---|---|
| Test set untouched during training | `train.csv` and `val.csv` (the exact files `KermtModel.fit` wrote and KERMT read) are intersected with the cluster's test molecules: `overlap=0` for both |
| Calibration fitted only on calibration data | same files intersected with the calibration molecules: `overlap=0` (calibration molecules are removed from train **and** val, because KERMT selects epochs on val); structurally, `calibration.py::_fit_from_calibration_only` receives only calibration arrays |
| Test metrics produced | a `calibration+test` record with `test_metrics_raw` for every endpoint |
| Calibration diagnostics recorded | `calibration_diagnostics.json` per endpoint: `temperature`, `at_boundary`, `optimizer_success`, `nll_*`, `ece_*`, class counts, `train_val_positive_rate` vs `calibration_positive_rate` |
| Raw vs calibrated available | `test_metrics_raw` and `test_metrics_calibrated` side by side; AUROC must be equal (temperature scaling is monotone) — checked to 1e-6 |
| Provenance | `prep_id`, `model_id`, `checkpoint_sha256` in each record; `provenance.json` git commit; `config.json` hyperparameters |

Also re-run the two tests that pin the same properties on the code that produced the run:

```bash
source ~/mars-work/lab_env.sh
$PY -m pytest -q -p no:cacheprovider \
  "tests/test_train_kermt_cluster_calibration.py::test_test_molecules_never_reach_fit" \
  "tests/test_train_kermt_cluster_calibration.py::test_calibration_molecules_never_reach_fit" \
  "tests/test_cluster_calibration.py::test_test_labels_cannot_influence_the_fitted_temperature"
```

**Do not read `artifacts/kermt/ckpt/fold_0/test_result.csv` as a test result.** `KermtModel.fit`
passes the *validation* fold as KERMT's test file (the CLI demands both or neither), so that file is
a second look at validation. The real test metrics are the MARS-computed ones above.

**Caveats to record with the numbers, not hide** (`next_steps.md`, `decisions.md` 2026-09-21):
the calibration split is not label-representative (DILI: train_val positive rate ≈ 0.49 vs
calibration 0.26 — printed in the record) and a 50-molecule fit sits exactly at the blueprint floor;
`predict_logits` is `logit` of the two-view mean of sigmoids, not either head's pre-sigmoid value
(monotone, so ranking metrics are untouched).

**Calibration protocol in force for all Tier-0 runs (`decisions.md` 2026-09-30 D2–D4):** one fixed M1 calibration split per endpoint,
identical for every seed; its molecules are withheld from training and epoch selection in **every** arm (`holdout_calibration=True`,
classification and regression alike); temperature scaling is fitted on it for classification only — regression calibration is
**unused by design** (`skipped_regression`); the split is never changed inside Tier 0; raw and calibrated metrics are always reported
together; calibrated metrics count as results only if `n_fit_samples ≥ 50` with both classes present (so HIA's, N=47 with one negative,
do not).

**STOP** on any leakage `[FAIL]`, on a missing `test_metrics_raw`, or if calibrated AUROC differs
from raw AUROC.

---

## 10. Tier-0

**Gate:** 7a, 7b and 8 PASSED (2026-09-22) and **Pass 1 is complete** (2026-09-30). Tier-0 = stock KERMT CLI on
type-homogeneous subgroups, **equal weighting only**, `holdout_calibration=True`, fixed seeds `(0,1,2,3,4)`.
**Order (since 2026-09-28): breadth-first** — Pass 1 (seed 0 of every arm) is **DONE**; what remains is Pass 2. The Pass-2 order,
per-launch checks and per-seed cost are in the **Pass-2 procedure at the top of this file (P-6)** — that table is the only launch
order. Do not launch a run if the previous run's `s_verify.py` or `s_protocol.py` failed.

**Pass 1 — DONE 2026-09-30 (record only; do not repeat):** `metabolism__reg` seed 0 (7.1 min), `absorption_distribution__cls` seed 0
(18.2 min), `absorption_distribution__reg` seed 0 (56.7 min), `metabolism__cls` seed 0 (57.3 min) — all `VERDICT: PASS`, all on
`ae5d28d` with `git.dirty=false`; DILI seeds 0–4 and `toxicity__cls` seeds 0–1 were run 2026-09-22/24. Records:
`status/kermt_tier0_results/`. The old "explicit go" gates for HIA and for `metabolism__cls` (Option A) are **withdrawn** (`decisions.md` 2026-09-30 D4/D5).

**Pass 2 — seeds 1–4 (toxicity 2–4):** see P-6. Launch one seed at a time (`SEEDS=<n>`), verify (P-7), then the next.

Common launch (one arm; `SEEDS` chooses which seeds — **use a single seed per launch**; W&B on; detached; VRAM sampled):

```bash
source ~/mars-work/lab_env.sh
ARM=metabolism__reg; SEEDS=1                # <- one arm, one seed; set per the Pass-2 table (P-6). No EPOCHS/BATCH/VARIANT env vars.
TAG=$(date -u +%Y%m%dT%H%M%SZ); df -h . | tail -1
nohup env SUBGROUP=$ARM SEEDS=$SEEDS WANDB=1 NOTES="Tier-0 ${ARM} seed ${SEEDS}" $PY "$LAB/s_run.py" > "$LOGS/tier0_${ARM}_$TAG.log" 2>&1 &
echo $! > "$LOGS/tier0_$ARM.pid"; sleep 20; head -40 "$LOGS/tier0_${ARM}_$TAG.log"
```

Verify **every** finished run (P-7: `s_verify.py` **and** `s_protocol.py`). While an arm has fewer than five seeds, read the run's
`lab_summary.json` (provisional, single seed, no "± std"); aggregate only once all five seeds of an arm exist:

```bash
source ~/mars-work/lab_env.sh
ARM=toxicity__cls
for RUN_ID in $(ls -d runs/kermt_*_${ARM}_seed?_2* | xargs -n1 basename); do echo "== $RUN_ID"; RUN_ID=$RUN_ID $PY "$LAB/s_verify.py" | tail -3; done
SUBGROUP=$ARM PREP_ID=$PREP_ID $PY "$LAB/s_agg.py" | tee "$LOGS/agg_$ARM.txt" | tail -60
```

`s_agg.py` refuses to report unless completed runs exist for all five seeds (so it refuses until an arm has all five seeds), skips runs whose
`run.json` status is not `completed` (a crashed run stays `running` — see section 12), and writes
`runs/kermt_tier0_<arm>_aggregate.json`: mean ± std of the **test** metrics, raw and calibrated,
plus per-endpoint temperature stability. This — not the validation-fold numbers — is what the final
comparison against XGBoost must use.

Arm reference (this table is the **arm inventory** and status; for run *order* use the Pass-2 table P-6 at the top of this file).
All are `kermt_single` / `kermt_multitask_subgroup` families through
the **same** `train_one_seed`; W&B name = run id = `kermt_<prefix>_<arm>_seed<N>_<UTC>`:

| # | `ARM` | Family (run-name prefix) | Task | Endpoints | Seeds to launch | Notes / gate |
|---|---|---|---|---|---|---|
| 1 | `dili_standalone__cls` | `kermt_single` (`kermt_st`) | classification | `dili_liver_injury` | **0–4 DONE** — complete, do not repeat | **base pool, non-augmented variant** (287 train; XGBoost used the augmented pool, 979) — label it so; calibration N=50 (13/37). `decisions.md` 2026-09-30 D6 |
| 2 | `toxicity__cls` | `kermt_multitask_subgroup` (`kermt_mtsub`) | classification, 2 targets | `herg_cardiotoxicity`, `ames_mutagenicity` | **0, 1 done; 2,3,4 → Pass 2** | cleared to train (0.2% sacrifice). Known: hERG validation holds only 18–24 labels vs ~1,810 AMES, so hERG epoch selection is barely measured — record, don't fix |
| 3 | `metabolism__reg` | `kermt_single` (`kermt_st`) | regression | `clearance_microsomal` | **0 done; 1–4 → Pass 2** | this is the **single-task baseline**, cited in both roles; never label it a multi-task arm. No calibration (regression) |
| 4 | `absorption_distribution__reg` | `kermt_multitask_subgroup` | regression, 4 targets | `solubility_logs`, `lipophilicity_logp`, `caco2_permeability`, `ppb_binding` | **0 done; 1–4 → Pass 2** | cleared (14.6% sacrifice). No calibration. Epoch selection = stock raw-unit mean MAE, PPB-dominated — a stated limitation, not changed (D1) |
| 5 | `absorption_distribution__cls` | `kermt_multitask_subgroup` | classification, 3 targets | `hia_absorption`, `pgp_inhibition`, `bbb_permeability` | **0 done; 1–4 → Pass 2** | **Decided (D4):** HIA calibration N=47 (46 pos / 1 neg) is below the floor of 50 — the run is valid; HIA calibrated metrics/temperature are **not reportable** (raw only); the `[WARN]` is expected every seed; no per-launch go needed |
| 6 | `metabolism__cls` | `kermt_multitask_subgroup` | classification, 3 targets | `cyp3a4_inhibition`, `cyp2d6_inhibition`, `cyp2c9_inhibition` | **0 done; 1–4 → Pass 2** | **Option A, confirmed (D5)** (29% of each CYP's training labels removed by strict leakage prevention). Largest arm: check disk/VRAM first; no per-launch go needed |

Evaluation command for every arm is the verify-then-aggregate block above with that row's `ARM`.
Expected outputs per run: `runs/<run_id>/{config.json,provenance.json,run.json,metrics.jsonl,
lab_summary.json,artifacts/{kermt,model/kermt,calibration/<endpoint>/}}`; per arm:
`runs/kermt_tier0_<arm>_aggregate.json`; and 5 W&B runs.

**Not launchable from the registry:** the three single-task **CYP baselines** on their full
original splits (Option A). `KermtModel` supports them, but no harness path builds them and no
`SubgroupSpec` for them exists in `configs/clusters.py`. Deferred — needs a small decision and code.

**No KERMT sweep CLI exists** (`ml/train/run_kermt_subgroup_sweep.py` is planned, not written); that
is why every launch above goes through `s_run.py`.

**Per-run time is measured for every arm:** DILI ≈ 4 min/seed, `metabolism__reg` ≈ 7 min, `absorption_distribution__cls` ≈ 18 min,
`absorption_distribution__reg` ≈ 57 min, `metabolism__cls` ≈ 57 min, toxicity ≈ 95–96 min (peak VRAM ≈ 3.9–4.2 GiB incl. ≈ 0.6 GiB desktop;
≈ 0.9 GB disk per run incl. a 496 MB `last_checkpoint.pt`). Tell the maintainer before committing to a long run. A partial seed set is
recorded as partial — `s_agg.py` refuses to aggregate it; that is expected until an arm has all five seeds.

---

## 11. G1–G4 and Tier 1/2

Nothing under G1–G4 can be **executed** tomorrow. Confirmed absent in the repo: `ml/train/kermt_mixed/`
and `ml/models/kermt_mixed_model.py` do not exist (`ls` fails on both); there is no `losses.py`,
`sampler.py` or `train_mixed.py`.

| Gate | What it needs | Status tomorrow |
|---|---|---|
| **G1** forward/inference parity (~30 s, GPU) | `KermtMixedModel` inference path, plus a Tier-0 AMES checkpoint | **Blocked on Tier-1 implementation.** The Tier-0 AMES checkpoint it needs is a by-product of the smoke test (`saved/model.pt`) — keep it, don't delete it |
| **G2** one-epoch loss parity (~15 s, GPU) | Tier-1 trainer | **Blocked on Tier-1 implementation** |
| **G3** multi-seed AUROC parity (GPU) | Tier-1 trainer + Tier-0 `toxicity__cls`/`ames` results | **Blocked on Tier-1**; its Tier-0 half (`toxicity__cls`) is arm 2 above, so running that arm is the only useful G3 prep |
| **G4** Kendall-loss math unit test (CPU-only) | `losses.py` in the Tier-1 trainer | **Blocked on Tier-1 implementation** — CPU-only in nature, but there is no code to test. It could be written first, on the laptop; that is an implementation task and is **deferred** (out of scope for this session) |
| Tier 2 GPU runs (ordinal-encoded stock CLI, decoded-MAE-within-15% gate) | codec `featurize/ordinal.py` **exists**; zero-GPU ceiling gate **done** (`n_bins=16`); no harness path trains ordinal targets | **Deferred** until Tier 1 lands |

Executable tomorrow: everything in sections 3–10. CPU-only and already done: cluster preflight,
leakage audit, calibration logic, ordinal ceiling test. Blocked: G1–G4. Deferred: Tier 2, the CYP
single-task baselines, a sweep CLI, the final KERMT-vs-XGBoost table (it needs the laptop-only
`ml/runs/test_evaluations/*.json`).

---

## 12. Stop conditions

**MUST stop, report the exact output, and wait** — do not continue, retry blindly or work around:

| Condition | How you will see it |
|---|---|
| Unexpected git state | dirty tree; wrong branch; `HEAD != $EXPECTED_SHA`; workstation-only commits; pull collision; `EXPECTED_SHA` unset, malformed, or one of the old baselines (`7475342`, `f51cb8f`, `6df4bab`, `ae5d28d`, `ad6eaf1`) |
| Protocol drift | P-2 guard prints `STOP` (a protocol-critical file differs from `ae5d28d`); `s_protocol.py` prints `MISMATCH`; the banner differs from the P-5 table; any `EPOCHS`/`BATCH`/hyperparameter/`VARIANT` env var set; `decisions.md` lacks the 2026-09-30 entry; a `holdout_calibration`/`use_augmented_dili`/`loss_weighting` value differs from seed 0 |
| Model/epoch mismatch | `model.pt`'s MARS-computed val metric differs from KERMT's logged best score by more than 1e-3; the saved epoch cannot be found in `finetune.log` (never substitute the `best validation … on epoch` line) |
| Checkpoint mismatch | `s_ckpt.py` `[FAIL]`; `s_run.py` assertion `STOP: checkpoint sha256 … != lockfile` |
| Data fingerprint mismatch | `compare_prep.py` overall `C_…` or `D_…`; readiness `data.manifest_integrity` FAIL |
| Unexpected dataset counts | preflight or banner differ from section 5e / 8 (DILI: train_val 378, pool 328, seed-0 train 287 / val 41, calibration 50 with 13 positives, test 96) |
| Docker/KERMT mismatch | KERMT HEAD ≠ `e402473…`; dirty KERMT checkout; `kermt:latest` missing; `check_checkpoint.py` `ok: false` |
| CUDA unavailable | container prints `False`/`0`; `nvidia-smi` fails; `could not select device driver` |
| VRAM / OOM | a KERMT traceback mentioning `out of memory` — report the batch size; never lower it silently |
| NaN / inf loss | non-finite `loss_train` in `finetune.log`; non-finite val metric in `s_verify.py` |
| Failed backward / optimizer step | `loss_train` flat or rising across epochs in the smoke test; `auc_val` frozen |
| Calibration failure | `s_verify.py` FAIL on fitted/temperature/`optimizer_success`/class counts; status `skipped_invalid_calibration_data`; `at_boundary` **and** `nll_improved: false` together — stop and show the maintainer |
| Test leakage | any `train.csv`/`val.csv` overlap line FAIL; raw vs calibrated AUROC differ. **Highest severity — stop everything and quarantine the run** |
| W&B failure | `UserWarning: W&B logging disabled`; `s_wandb.py` auth error. A *smoke* run may proceed without W&B; a *real/Tier-0* run must not (a real run with no dashboard record is a lost result) — stop and ask for `wandb login` |
| Crashed run | `run.json` `status` stays `running` and the process is gone: the harness has no failure handler, so the run directory is left half-written. Do **not** rerun over it and do **not** delete it; report it. `s_agg.py` ignores it |
| Disk | free space (`df -h .`) could not hold the next run (≈ 0.9 GB for a toxicity-sized run; budget per-run `du -sh`), (each run keeps two finetuned checkpoints) — report and ask |
| Anything outside this runbook | a command you would have to invent, a fix you would have to write, a data file you would have to fetch |

---

## 13. End-of-session checklist

```bash
source ~/mars-work/lab_env.sh
cd "$MARS_REPO"
git status --short                          # MUST still be empty: nothing generated is tracked
git rev-parse HEAD                          # record; must equal $EXPECTED_SHA
git branch --show-current
cd ml
echo "prep_id=$PREP_ID canonical=$CANON_PREP_ID"; $PY -c "import json;print(json.load(open('$LOGS/prep_compare.json'))['overall'])"
docker image inspect kermt:latest --format '{{.Id}}'
git -C "$MARS_KERMT_REPO" rev-parse HEAD
sha256sum data/checkpoints/kermt/NV-KERMT-70M-v2/kermt_contrastive_v2.0.pt
nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
ls -d runs/kermt_*/ | wc -l; ls runs/kermt_tier0_*_aggregate.json 2>/dev/null
for r in $(ls -d runs/kermt_*_seed?_2* 2>/dev/null | xargs -n1 basename); do printf '%s  ' "$r"; $PY -c "import json;print(json.load(open('runs/$r/run.json'))['status'])"; done
du -sh runs; df -h . | tail -1
```

Then:

1. **Save outputs** — package everything small and useful (no `*.pt` checkpoints; they stay on the
   workstation) so it can be carried to the laptop for the comparison:
   `tar czf ~/mars-work/lab_out_$(date -u +%Y%m%d).tgz --exclude='*.pt' -C "$MARS_REPO/ml" runs/lab_logs runs/kermt_* runs/readiness_report.json`
2. **Verify W&B runs** — every completed run has a `wandb_url` in its `lab_summary.json`; open the
   project, confirm the count matches the number of completed runs and that no run is stuck "running".
3. **Verify checkpoints** — for each completed run `artifacts/model/kermt/model.pt` exists;
   the pretrained checkpoint sha256 still equals the lockfile (command above).
4. **Verify test reports** — every completed run has `VERDICT: PASS` in its `verify_<run_id>.txt`;
   every finished arm has an aggregate JSON; `ls` shows no arm with fewer than five verified seeds
   that you have reported as complete.
5. **Record identities** — git SHA, prep id (and the fingerprint verdict), Docker image id, KERMT
   commit, checkpoint sha256, GPU/driver, `kermt_defaults_finetune.json` copy. These go in the session
   note; the image id has no other home.
6. **`git status` must be empty.** **Do NOT commit generated artifacts** — `ml/runs/` is
   gitignored on purpose. Do not commit, add or push anything: if the session produced a code or
   documentation change worth keeping, describe it to the maintainer.
7. **Document what succeeded/failed** — write the outcome of each numbered step above (PASS / FAIL /
   not reached, with the run ids and numbers) into the session note for the maintainer; the AIMS
   files are updated by the maintainer's session, not blindly from here.
8. **Prepare next-session tasks** — carry over: remaining Pass-2 arms/seeds (P-6 table, minus what ran); the reporting work still
   open before any table (regression metrics beyond MAE; `tier0_present.py` covers single-endpoint classification arms only — the single-seed std and the partial-arm
   refusal landed 2026-10-01); regenerating pre-2026-10-01 tier-0 packages; pool-matching for the DILI comparison (`decisions.md` 2026-09-30 D6); the missing W&B test-metric logging; recording the
   effective KERMT hyperparameters and the Docker image digest in the run record; adding `s_upload.py`/`s_wandb_verify.py` to the repo;
   the missing sweep CLI and CYP single-task baselines; served-XGBoost-calibrator degradation; Tier-1 implementation (G1–G4); and the
   laptop-side KERMT-vs-XGBoost comparison using the carried aggregate JSONs against `ml/runs/test_evaluations/`. The protocol
   decisions themselves (HIA floor, `holdout_calibration`, calibration split, `metabolism__cls` Option A, DILI pool, epoch selection) are **closed** —
   do not re-open them in a session; report a concern and let the maintainer record a new decision.

---

## Appendix A — every command in this runbook, and where it lives

| Command / helper | Defined in | Checked how |
|---|---|---|
| `train/readiness_report.py --target --prep-id --out` (also `--smoke-subgroup`, `--expected-image-id`, `--workstation-fingerprint`) | `ml/train/readiness_report.py::main` (argparse, lines ≈ 799–807) | flags read from the parser; ran on the laptop 9-21 |
| `data/compare_prep.py fingerprint --prep-dir [--out]` · `compare --a --b` | `ml/data/compare_prep.py::main` (subparsers) | parser read; ran on both local snapshots |
| `train/preflight_clusters.py --prep-dir --out` | `ml/train/preflight_clusters.py::main` | parser read; ran 9-20/21 |
| `s_ckpt.py` | this file; uses `eval.heldout_evaluation.sha256_file`, lockfile keys `local_path`/`files[*].bytes`/`sha256` | executed [ran here] — correctly FAILs on the laptop (no checkpoint) |
| `s_wandb.py` | this file; `wandb.Api().viewer` | executed against the laptop's W&B login (read-only) |
| `s_ames.py` | this file; `data.loaders.load_endpoint`, `data.split.five_seed_train_val_folds`, `models.kermt_model.{KermtModel,KermtConfig}`, `eval.metrics.compute_metrics`; derived from `kermt_integration_status.md` §11 | executed [ran here] with a KERMT test double |
| `s_run.py` | this file; `configs.clusters.all_subgroups`, `data.cluster_loaders.load_cluster`, `train.train_kermt_cluster.train_one_seed` (signature read), `configs.experiment_config.ExperimentConfig` | executed [ran here] with a test double, incl. a mocked `wandb.init` pass on a 2-endpoint arm |
| `s_verify.py` | this file; reads the files `ExperimentRun` and `KermtModel.fit` write | executed [ran here]; PASS on a double-backed run |
| `s_agg.py` | this file; `eval.cluster_calibration.{aggregate_test_metrics_across_seeds,aggregate_calibration_across_seeds}` | executed [ran here] on 5 double-backed seeds |
| pytest node ids in sections 4 and 9 | `ml/tests/test_train_kermt_cluster_calibration.py:172,181` · `test_cluster_calibration.py:83` | names grepped; suite run |
| `kermt_container.sh run --ckpt … -- "<cmd>"`, `ensure_image` | KERMT checkout `agent/scripts/kermt_container.sh`; the mount/`--` contract is what `models/kermt_model.py::_run_container` uses | **[not verifiable here]** (script lives on the workstation) |
| `agent/config/defaults_finetune.json` | named in `models/kermt_model.py` (`KermtConfig` docstring) | **[not verifiable here]** |
| `git`, `docker`, `nvidia-smi`, `nvidia-ctk`, `sha256sum`, `awk`, `tee`, `nohup`, `tar`, `df`, `du`, `grep`, `sed`, `ls`, `curl` (only if the maintainer approves a re-download) | system tools | standard; the `awk` peak-VRAM line was executed on sample data |

## Appendix B — traps found while writing this (do not rediscover them)

1. `readiness_report.py` ties `--prep-id` to both the snapshot it reads *and* the canonical
   fingerprint's filename — see 5d. Its default `--prep-id` is the **laptop's** id; on the
   workstation always pass `20260918T090433Z`.
2. `WandbLogger` reads env vars only; `.env` is never loaded — export `WANDB_ENTITY`/`WANDB_PROJECT`.
3. `train_one_seed` has no `try/finally`: a crash leaves `run.json` at `status: running`, the W&B
   run unfinished, and — because the model is saved *after* calibration — no `model.pt`.
4. `KermtConfig` is not written into `config.json` by the harness (`hyperparams` is empty unless the
   caller sets it); `s_run.py` sets it. Do not call `train_one_seed` by hand without doing the same.
5. `KermtModel.predict()` names its scratch dir `predict_<hash of the inputs>`, and `fit`/`predict`
   trust `run.json` in it — never point a new run at an old directory.
6. `ml/train/kermt_gpu_benchmark.py` hard-codes `/tmp/claude-1001/...` input and output paths. It is
   not part of this runbook; do not run it as-is.
7. The Docker image id is not pinned anywhere and is **not** captured in run provenance (only the
   checkpoint sha and KERMT commit come from the lockfile) — the session log is its only record.
8. Per-run W&B carries no test-metric dicts (section 8).
