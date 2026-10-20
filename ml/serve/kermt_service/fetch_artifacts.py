"""Download the 30 Tier-0 KERMT models from W&B into the serving layout, hash-verified.

    ml/artifacts_kermt/<arm>/seed_<n>/model.pt
    ml/artifacts_kermt/<arm>/seed_<n>/metadata.json

Runs in `ml/.venv` (needs `wandb`, logged in as the `shashquatch` entity). Each artifact is
downloaded to a temporary directory, its `model.pt` SHA-256 is compared with the
`model_sha256` its own `metadata.json` records (the same value the results README tabulates),
and only then moved into place. An existing seed directory whose hash already matches is left
alone, so the command is safe to re-run.

    PYTHONPATH=. python serve/kermt_service/fetch_artifacts.py            # all arms, 5 seeds
    PYTHONPATH=. python serve/kermt_service/fetch_artifacts.py --arm toxicity__cls --seeds 0 1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

ENTITY_PROJECT = "shashquatch/mars-admet"
DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "artifacts_kermt"

# arm -> W&B artifact stem (`kermt-<stem>-seed<N>:v0`, results README, "Model artifacts")
ARM_ARTIFACT_STEM = {
    "dili_standalone__cls": "dili",
    "toxicity__cls": "toxicity",
    "metabolism__cls": "metabolism-cls",
    "metabolism__reg": "metabolism-reg",
    "absorption_distribution__cls": "absorption-distribution-cls",
    "absorption_distribution__reg": "absorption-distribution-reg",
}
SEEDS = (0, 1, 2, 3, 4)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def already_good(seed_dir: Path) -> bool:
    meta, model = seed_dir / "metadata.json", seed_dir / "model.pt"
    if not (meta.exists() and model.exists()):
        return False
    return sha256_of(model) == json.loads(meta.read_text(encoding="utf-8"))["model_sha256"]


def fetch_one(api, arm: str, seed: int, root: Path) -> str:
    seed_dir = root / arm / f"seed_{seed}"
    if already_good(seed_dir):
        return "kept (hash matches)"
    ref = f"{ENTITY_PROJECT}/kermt-{ARM_ARTIFACT_STEM[arm]}-seed{seed}:v0"
    artifact = api.artifact(ref, type="model")
    with tempfile.TemporaryDirectory(dir=root.parent) as tmp:
        got = Path(artifact.download(root=tmp))
        meta = json.loads((got / "metadata.json").read_text(encoding="utf-8"))
        digest = sha256_of(got / "model.pt")
        if digest != meta["model_sha256"]:
            raise RuntimeError(f"{ref}: model.pt sha256 {digest} != metadata {meta['model_sha256']}")
        if meta["endpoint"] != arm or int(meta["seed"]) != seed:
            raise RuntimeError(f"{ref}: metadata says {meta['endpoint']} seed {meta['seed']}")
        if seed_dir.exists():
            shutil.rmtree(seed_dir)
        seed_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(got), str(seed_dir))
    return f"downloaded, sha256 {digest[:12]}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--arm", action="append", choices=sorted(ARM_ARTIFACT_STEM), help="repeatable; default all")
    parser.add_argument("--seeds", type=int, nargs="*", default=list(SEEDS))
    args = parser.parse_args(argv)

    import wandb

    api = wandb.Api()
    args.root.mkdir(parents=True, exist_ok=True)
    failures = 0
    for arm in args.arm or sorted(ARM_ARTIFACT_STEM):
        for seed in args.seeds:
            try:
                print(f"{arm} seed {seed}: {fetch_one(api, arm, seed, args.root)}", flush=True)
            except Exception as exc:  # report every failure, then exit non-zero
                failures += 1
                print(f"{arm} seed {seed}: FAILED - {exc}", file=sys.stderr, flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
