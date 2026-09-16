"""
CLI entry point: train XGBoost baseline for one endpoint × one seed.

Usage
-----
    cd ml
    python train/run_xgboost_baseline.py \\
        --endpoint ames_mutagenicity \\
        --seed 0 \\
        --prep-id 20260830T200000Z \\
        [--use-augmented-dili] \\
        [--cache-root ml/data/cache] \\
        [--runs-dir ml/runs]

One ExperimentRun is created per invocation.  To run all 5 seeds, loop over
--seed 0..4, or use train_xgboost_all_seeds() from train.train_xgboost directly.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_xgboost_baseline",
        description="Train XGBoost baseline for one MARS endpoint × one seed.",
    )
    p.add_argument("--endpoint", required=True, help="Endpoint key, e.g. ames_mutagenicity")
    p.add_argument("--seed", type=int, required=True, help="Random seed (0–4 for FIXED_SEEDS)")
    p.add_argument("--prep-id", required=True, dest="prep_id", help="M1 prep_id, e.g. 20260830T200000Z")
    p.add_argument(
        "--use-augmented-dili",
        action="store_true",
        default=False,
        dest="use_augmented_dili",
        help="Load DILIst-augmented training set (DILI endpoint only)",
    )
    p.add_argument(
        "--processed-dir",
        default=None,
        dest="processed_dir",
        help="Path to ml/data/processed/ (default: auto-detected relative to script)",
    )
    p.add_argument(
        "--cache-root",
        default=None,
        dest="cache_root",
        help="Path to feature cache root (default: ml/data/cache/)",
    )
    p.add_argument(
        "--runs-dir",
        default=None,
        dest="runs_dir",
        help="Path to experiment runs directory (default: ml/runs/)",
    )
    p.add_argument(
        "--no-wandb",
        action="store_true",
        default=False,
        dest="no_wandb",
        help="Disable W&B mirroring (ON by default for this production entry point)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    # Resolve repo root relative to this script's location (ml/train/)
    repo_root = Path(__file__).resolve().parents[2]
    ml_root = repo_root / "ml"

    processed_dir = Path(args.processed_dir) if args.processed_dir else ml_root / "data" / "processed"
    prep_dir = processed_dir / args.prep_id
    if not prep_dir.exists():
        print(f"ERROR: prep_dir not found: {prep_dir}", file=sys.stderr)
        return 1

    cache_root = Path(args.cache_root) if args.cache_root else ml_root / "data" / "cache"
    runs_dir = Path(args.runs_dir) if args.runs_dir else ml_root / "runs"

    # Deferred imports so argparse --help works even without ml deps installed
    from configs.experiment_config import ExperimentConfig
    from data.loaders import load_endpoint
    from featurize.cache import FeatureCache

    from train.train_xgboost import train_one_seed

    print(f"Loading endpoint: {args.endpoint} (prep_id={args.prep_id})")
    endpoint_data = load_endpoint(
        prep_dir,
        args.endpoint,
        use_augmented_dili=args.use_augmented_dili,
    )

    config = ExperimentConfig(
        endpoint=args.endpoint,
        model_family="xgboost",
        seed=args.seed,
        prep_id=args.prep_id,
        use_augmented_dili=args.use_augmented_dili,
    )

    cache = FeatureCache(cache_root)

    use_wandb = not args.no_wandb
    print(f"Training seed={args.seed} … (W&B: {'on' if use_wandb else 'off'})")
    result = train_one_seed(
        endpoint_data,
        config,
        cache,
        args.seed,
        runs_dir=runs_dir,
        repo_root=repo_root,
        use_wandb=use_wandb,
    )

    print(f"Run ID : {result.run_id}")
    print(f"n_train: {result.n_train}  n_val: {result.n_val}")
    if result.best_iteration is not None:
        print(f"Best iteration: {result.best_iteration}")
    if result.wandb_url:
        print(f"W&B run: {result.wandb_url}")

    m = result.val_metrics
    for field_name in m.__dataclass_fields__:
        val = getattr(m, field_name)
        if isinstance(val, float):
            print(f"  {field_name}: {val:.4f}")
        else:
            print(f"  {field_name}: {val}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
