"""G3 overnight driver. Runs seeds 0-4 of g3_seed.py ONE AT A TIME, with the runbook's pre-launch
config check and post-run checks. Any failed check kills the job and halts the whole sweep (STOP file).
Resumable: seeds that already have a completed run are skipped. No code/config/hyperparameter choice here."""
import glob, hashlib, json, os, subprocess, sys, time
from pathlib import Path

RUNS = Path("runs"); LOGS = Path(os.environ["LOGS"]); GATES = RUNS / "tier1_gates"
STATE = GATES / "g3_state.json"; STOP = GATES / "g3_STOP.txt"; EVENTS = LOGS / "g3_driver.log"
EXPECT = {"model_family": "kermt_mixed", "loss_weighting": "fixed", "min_per_task": 0,
          "hyperparameter_source": "parity-gate", "prep_id": os.environ["PREP_ID"],
          "holdout_calibration": True}

def log(m):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {m}"
    print(line, flush=True)
    with open(EVENTS, "a") as f: f.write(line + "\n")

def stop(reason, proc=None):
    if proc is not None and proc.poll() is None:
        proc.kill(); proc.wait()
    STOP.write_text(reason + "\n"); log("STOP: " + reason); sys.exit(2)

def jload(p):
    try: return json.loads(Path(p).read_text())
    except Exception: return None

def mixed_dirs(): return {d for d in glob.glob(str(RUNS / "*")) if Path(d).name.startswith("kermt_mx_toxicity__cls_seed") and Path(d).is_dir()}

def status(d):
    r = jload(Path(d) / "run.json") or {}; return r.get("status")

def completed_dir(seed):
    for d in sorted(mixed_dirs()):
        c = jload(Path(d) / "config.json") or {}; r = jload(Path(d) / "run.json") or {}
        if r.get("status") == "completed" and (r.get("seed", c.get("seed")) == seed):
            last = [l for l in (Path(d) / "artifacts" / "kermt" / "logs" / "mixed_epochs.jsonl").read_text().splitlines() if l.strip()]
            if last and json.loads(last[-1]).get("event") == "summary": return d
    return None

def field(d, key):
    for fn in ("config.json", "run.json", "provenance.json"):
        j = jload(Path(d) / fn) or {}
        if key in j: return j[key]
    return None

def pre_check(d, seed):
    bad = []
    for k, v in EXPECT.items():
        got = field(d, k)
        if got != v: bad.append(f"{k}: expected {v!r}, got {got!r}")
    got = field(d, "seed")
    if got != seed: bad.append(f"seed: expected {seed}, got {got!r}")
    dirty = ((jload(Path(d) / "provenance.json") or {}).get("git") or {}).get("dirty")
    if dirty is not False: bad.append(f"git dirty: expected False, got {dirty!r}")
    return bad

def post_check(d, seed, logf):
    bad, warn = [], []
    if status(d) != "completed": bad.append(f"run.json status={status(d)!r}")
    ep = Path(d) / "artifacts" / "kermt" / "logs" / "mixed_epochs.jsonl"
    lines = [l for l in ep.read_text().splitlines() if l.strip()] if ep.exists() else []
    summ = json.loads(lines[-1]) if lines else {}
    if summ.get("event") != "summary": bad.append("last mixed_epochs.jsonl line is not the summary event")
    prov = (jload(Path(d) / "artifacts" / "kermt" / "trainer_provenance.json") or {}).get("files", {})
    for name, h in prov.items():
        actual = hashlib.sha256((Path("train/kermt_mixed") / name).read_bytes()).hexdigest()
        if actual != h: bad.append(f"trainer provenance mismatch: {name}")
    if not prov: bad.append("trainer_provenance.json missing/empty")
    txt = Path(logf).read_text(errors="replace")
    if "FloatingPointError" in txt: bad.append("FloatingPointError in log")
    if txt.count("UserWarning: W&B"): warn.append(f"{txt.count('UserWarning: W&B')} 'UserWarning: W&B' lines (W&B logging degraded; training valid, metrics local)")
    return bad, warn, summ

def vram_peak(csv):
    m = 0
    for l in Path(csv).read_text().splitlines():
        try: m = max(m, int(l.split(",")[1].strip().split()[0]))
        except Exception: pass
    return m

state = jload(STATE) or {"seeds": {}}
def save(): STATE.write_text(json.dumps(state, indent=1))

if STOP.exists(): log(f"refusing to start: {STOP} exists"); sys.exit(2)
log(f"driver start pid={os.getpid()} HEAD-check env EXPECTED_SHA={os.environ.get('EXPECTED_SHA')}")

def running_seed():
    out = subprocess.run(["pgrep", "-f", "runs/tier1_gates/g3_seed.py"], capture_output=True, text=True).stdout.split()
    for pid in out:
        try:
            argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
            if any(a.endswith(b"g3_seed.py") for a in argv): return int(pid), int([a for a in argv if a][-1])
        except Exception: pass
    return None, None

ADOPT_PID, ADOPT_SEED = running_seed()
if ADOPT_PID: log(f"adopting already-running g3_seed.py pid={ADOPT_PID} seed={ADOPT_SEED}")

for seed in range(5):
    done = completed_dir(seed)
    if done:
        log(f"seed {seed}: already completed ({done}); skipping"); state["seeds"].setdefault(str(seed), {})["run_dir"] = done; save(); continue
    if ADOPT_PID and seed == ADOPT_SEED:
        t0 = time.time()
        cands = [d for d in mixed_dirs() if status(d) == "running" and field(d, "seed") == seed]
        if len(cands) != 1: stop(f"adopt: expected exactly one running dir for seed {seed}, got {sorted(cands)}")
        newdir = cands[0]; bad = pre_check(newdir, seed)
        if bad: stop(f"seed {seed} config check failed: {bad}")
        log(f"seed {seed}: config check OK ({newdir}) [adopted]")
        logf = sorted(glob.glob(str(LOGS / f"g3_seed{seed}_*.log")))[-1]
        vram = sorted(glob.glob(str(LOGS / f"vram_g3_seed{seed}_*.csv")))[-1]
        while Path(f"/proc/{ADOPT_PID}").exists(): time.sleep(10)
        subprocess.run(["pkill", "-f", f"vram_g3_seed{seed}_"]); subprocess.run(["pkill", "-f", f"-l 5.*{Path(vram).name}"])
        wall = time.time() - t0   # lower bound: observed from adoption, not from launch
        bad, warn, summ = post_check(newdir, seed, logf)
        if bad: stop(f"seed {seed} post-run check failed: {bad}")
        state["seeds"][str(seed)] = {"run_dir": newdir, "run_id": Path(newdir).name, "wall_s_observed_from_adoption": round(wall, 1),
            "peak_vram_mib": vram_peak(vram), "best_epoch": summ.get("best_epoch"), "warnings": warn, "log": logf, "vram": vram}
        save(); log(f"seed {seed}: DONE {state['seeds'][str(seed)]}"); continue
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if head != os.environ["EXPECTED_SHA"]: stop(f"HEAD {head} != EXPECTED_SHA before seed {seed}")
    if subprocess.run(["git", "status", "--short"], capture_output=True, text=True).stdout.strip():
        stop(f"git status not clean before seed {seed}")
    stale = [d for d in mixed_dirs() if status(d) == "running"]
    if stale: log(f"NOTE: non-completed (crashed?) mixed run dirs left untouched: {sorted(stale)}")
    before = mixed_dirs(); tag = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    logf = LOGS / f"g3_seed{seed}_{tag}.log"; vram = LOGS / f"vram_g3_seed{seed}_{tag}.csv"
    t0 = time.time()
    vp = subprocess.Popen(f"exec nvidia-smi --query-gpu=timestamp,memory.used,utilization.gpu --format=csv,noheader -l 5 > {vram}", shell=True)
    proc = subprocess.Popen([os.environ["PY"], "runs/tier1_gates/g3_seed.py", str(seed)],
                            stdout=open(logf, "w"), stderr=subprocess.STDOUT)
    log(f"seed {seed}: launched pid={proc.pid} log={logf}")
    newdir, checked = None, False
    while proc.poll() is None:
        time.sleep(10)
        if not checked:
            fresh = mixed_dirs() - before
            for d in fresh:
                if (Path(d) / "config.json").exists() and (Path(d) / "provenance.json").exists():
                    newdir = d; bad = pre_check(d, seed)
                    if bad: vp.kill(); stop(f"seed {seed} pre-launch config check failed: {bad}", proc)
                    log(f"seed {seed}: config check OK ({d})"); checked = True; break
    vp.kill()
    rc = proc.returncode; wall = time.time() - t0
    if rc != 0:
        stop(f"seed {seed}: g3_seed.py exited {rc}; see {logf} (traceback is in that log). No retry.")
    if newdir is None:
        fresh = mixed_dirs() - before; newdir = sorted(fresh)[-1] if fresh else None
    if newdir is None: stop(f"seed {seed}: no run dir found after exit")
    bad, warn, summ = post_check(newdir, seed, logf)
    if bad: stop(f"seed {seed} post-run check failed: {bad}")
    state["seeds"][str(seed)] = {"run_dir": newdir, "run_id": Path(newdir).name, "wall_s": round(wall, 1),
        "peak_vram_mib": vram_peak(vram), "best_epoch": summ.get("best_epoch"), "warnings": warn,
        "log": str(logf), "vram": str(vram)}
    save(); log(f"seed {seed}: DONE {state['seeds'][str(seed)]}")

log("ALL FIVE SEEDS COMPLETE"); state["all_complete"] = True; save()
