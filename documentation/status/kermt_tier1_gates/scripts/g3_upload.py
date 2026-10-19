"""Upload finished G3 (Tier-1 parity-gate) mixed models to W&B, one artifact per seed.
Convention follows the Tier-0 uploader: type `model`, files model.pt + metadata.json, aliases final+latest, logged by
RESUMING the original training run (job_type model-upload), plus an additive `run-record` artifact.
Names are kermt-mixed-toxicity-seed<N>-parity-gate (never collides with Tier-0 kermt-toxicity-seed<N>).
Usage: g3_upload.py once <seed> | g3_upload.py watch   (watch: upload every completed seed, retry while offline)"""
import hashlib, json, os, sys, time, traceback
from pathlib import Path

ENTITY, PROJECT = os.environ["WANDB_ENTITY"], os.environ["WANDB_PROJECT"]
STATE = Path("runs/tier1_gates/g3_state.json"); MARK = "g3_upload_done.json"
LOG = Path(os.environ.get("LOGS", "runs/lab_logs")) / "g3_upload.log"

def log(m):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {m}"; print(line, flush=True)
    with open(LOG, "a") as f: f.write(line + "\n")

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()

def upload(seed, run_dir):
    import wandb
    d = Path(run_dir); mark = d / "artifacts" / MARK
    if mark.exists(): return "already-uploaded"
    meta_run = json.loads((d / "run.json").read_text()); cfg = json.loads((d / "config.json").read_text())
    prov = json.loads((d / "provenance.json").read_text())
    model = d / "artifacts/model/kermt_mixed/model.pt"; mmeta = d / "artifacts/model/kermt_mixed/metadata.json"
    run_id = meta_run["run_id"]; name = f"kermt-mixed-toxicity-seed{seed}-parity-gate"
    msha = sha(model)
    checks = {
        "run.json status completed": meta_run["status"] == "completed",
        "run seed == seed": meta_run["seed"] == seed and f"_seed{seed}_" in run_id,
        "model.pt byte-identical to ckpt/fold_0/model_0/model.pt": msha == sha(d / "artifacts/kermt/ckpt/fold_0/model_0/model.pt"),
        "config fixed / min_per_task 0 / parity-gate": (cfg.get("loss_weighting"), cfg.get("min_per_task"), cfg.get("hyperparameter_source")) == ("fixed", 0, "parity-gate"),
        "git clean at run time": prov["git"]["dirty"] is False,
        "epochs log ends with summary": json.loads([l for l in (d / "artifacts/kermt/logs/mixed_epochs.jsonl").read_text().splitlines() if l.strip()][-1]).get("event") == "summary",
    }
    api = wandb.Api()
    try: api.artifact(f"{ENTITY}/{PROJECT}/{name}:latest"); checks["artifact name not yet used"] = False
    except Exception: checks["artifact name not yet used"] = True
    checks["W&B run exists and finished"] = api.run(f"{ENTITY}/{PROJECT}/{run_id}").state == "finished"
    for k, ok in checks.items(): log(f"seed {seed}: [{'PASS' if ok else 'FAIL'}] {k}")
    if not all(checks.values()): raise RuntimeError(f"seed {seed}: pre-upload check failed; nothing uploaded")
    metadata = {**json.loads(mmeta.read_text()), "model_sha256": msha, "model_size_bytes": model.stat().st_size,
                "run_id": run_id, "git_sha": prov["git"]["commit"], "git_branch": prov["git"]["branch"],
                "git_dirty": prov["git"]["dirty"], "prep_id": meta_run["prep_id"], "model_family": "kermt_mixed",
                "role": "G3 parity-gate model (stock values, loss_mode=fixed, min_per_task=0); not a Tier-1 arm result",
                "wandb_run_url": f"https://wandb.ai/{ENTITY}/{PROJECT}/runs/{run_id}"}
    wr = wandb.init(entity=ENTITY, project=PROJECT, id=run_id, resume="must", job_type="model-upload")
    try:
        art = wandb.Artifact(name, type="model", metadata=metadata,
                             description=f"G3 parity-gate mixed-type KERMT model, toxicity__cls seed {seed} ({run_id})")
        art.add_file(str(model), name="model.pt"); art.add_file(str(mmeta), name="metadata.json")
        wr.log_artifact(art, aliases=["final", "latest"])
        rec = wandb.Artifact(f"{name}-record", type="run-record", metadata={"run_id": run_id, "seed": seed, "model_sha256": msha,
                             "git_sha": prov["git"]["commit"], "model_artifact": f"{name}:v0"},
                             description=f"Reproducibility record for {run_id}")
        for rel in ["run.json", "config.json", "provenance.json", "metrics.jsonl", "artifacts/kermt/run.json",
                    "artifacts/kermt/trainer_provenance.json", "artifacts/kermt/logs/mixed_epochs.jsonl",
                    "artifacts/model/kermt_mixed/mixed_meta.json"]:
            if (d / rel).exists(): rec.add_file(str(d / rel), name=rel)
        wr.log_artifact(rec, aliases=["latest"])
    finally:
        wr.finish()
    # verify from W&B: committed, exact files, full-download sha == local
    a = api.artifact(f"{ENTITY}/{PROJECT}/{name}:v0")
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        p = a.download(root=t); ok_sha = sha(Path(p) / "model.pt") == msha
        files = sorted(x.name for x in Path(p).iterdir())
    ok = a.state == "COMMITTED" and ok_sha and files == ["metadata.json", "model.pt"] and set(a.aliases) >= {"final", "latest"}
    log(f"seed {seed}: VERIFY {'PASS' if ok else 'FAIL'} state={a.state} files={files} sha_ok={ok_sha} aliases={a.aliases}")
    if not ok: raise RuntimeError(f"seed {seed}: post-upload verify failed")
    mark.write_text(json.dumps({"artifact": f"{ENTITY}/{PROJECT}/{name}:v0", "model_sha256": msha, "digest": a.digest,
                                "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, indent=1))
    return f"uploaded {name}:v0"

def completed():
    st = json.loads(STATE.read_text()) if STATE.exists() else {"seeds": {}}
    return {int(s): v["run_dir"] for s, v in st["seeds"].items() if v.get("run_dir")}

if __name__ == "__main__":
    if sys.argv[1] == "once":
        s = int(sys.argv[2]); print(upload(s, completed()[s]))
    else:
        while True:
            todo = {s: r for s, r in completed().items() if not (Path(r) / "artifacts" / MARK).exists()
                    and json.loads((Path(r) / "run.json").read_text()).get("status") == "completed"}
            for s, r in sorted(todo.items()):
                try: log(f"seed {s}: {upload(s, r)}")
                except Exception as e:
                    log(f"seed {s}: upload failed ({type(e).__name__}: {str(e)[:160]}); will retry"); break
            allup = len(completed()) == 5 and all((Path(r) / "artifacts" / MARK).exists() for r in completed().values())
            if allup: log("all five seeds uploaded; watcher exiting"); break
            time.sleep(120)
