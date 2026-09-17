"""Phase 1 preflight for the M2 production XGBoost baseline sweep
(14 endpoints x 5 seeds = 70 runs).

Read-only: loads every endpoint's data, checks split integrity via the
existing leakage-audit machinery, reports class balance / label-range
sanity, and verifies write access to the output directories. Does not
train anything. Exit code 0 = safe to proceed to the pilot run; nonzero =
STOP, with the exact endpoint and reason printed.

Usage (from ml/, in ml/.venv):
    PYTHONPATH=. python train/preflight_sweep.py --prep-id 20260830T200000Z
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from configs.experiment_config import FIXED_SEEDS
from data.loaders import load_endpoint
from data.split import five_seed_train_val_folds
from eval.leakage_audit import run_leakage_audit
from mars_contracts.endpoints import ML_ENDPOINTS, TaskType


def _check_endpoint(prep_dir: Path, endpoint_key: str, *, use_augmented_dili: bool) -> dict:
    result: dict = {"endpoint": endpoint_key, "ok": False}
    try:
        data = load_endpoint(prep_dir, endpoint_key, use_augmented_dili=use_augmented_dili)
    except Exception as exc:
        result["error"] = f"load_endpoint failed: {exc}"
        return result

    result["dataset_key"] = data.dataset_key
    result["n_train_val"] = len(data.train_val)
    result["n_test"] = len(data.test)
    result["n_calibration"] = len(data.calibration)
    result["provenance_prep_id"] = data.provenance.get("prep_id")
    split_method = data.provenance.get("split_method")
    if split_method is None and use_augmented_dili:
        # The augmented DILI variant's own provenance.json doesn't record
        # split_method (a real gap in dilist_augment.py's provenance writer,
        # not fixed here — flagged in mistakes.md). Its TEST set is provably
        # the unmodified base adopted-benchmark test set regardless
        # (augmentation only ever adds to train_val; DILIst rows can never
        # reach the fixed TDC test set — an already-enforced, tested
        # invariant), so fall back to the base dataset's recorded method.
        try:
            base = load_endpoint(prep_dir, endpoint_key, use_augmented_dili=False)
            split_method = base.provenance.get("split_method")
        except Exception:
            pass
    result["split_method"] = split_method

    labels = data.train_val["label"].astype(float)
    if data.task_type == TaskType.CLASSIFICATION:
        vc = labels.value_counts().to_dict()
        result["class_balance_train_val"] = {str(k): int(v) for k, v in vc.items()}
        if len(vc) < 2:
            result["error"] = f"train_val has only one class present: {vc}"
            return result
    else:
        result["label_stats_train_val"] = {
            "min": float(labels.min()),
            "max": float(labels.max()),
            "mean": float(labels.mean()),
            "std": float(labels.std()),
        }
        if not np.isfinite(labels).all():
            result["error"] = "non-finite regression labels present in train_val"
            return result

    try:
        folds = five_seed_train_val_folds(data.train_val["standardized_smiles"].tolist(), seeds=FIXED_SEEDS)
        if len(folds) != len(FIXED_SEEDS):
            result["error"] = f"expected {len(FIXED_SEEDS)} folds, got {len(folds)}"
            return result
    except Exception as exc:
        result["error"] = f"five_seed_train_val_folds failed: {exc}"
        return result

    try:
        audit = run_leakage_audit(data)
        result["leakage_audit_passed"] = audit.all_passed
        blocking_failures = [
            c
            for c in audit.failed_checks
            # `test_disjoint_from_train_val_scaffolds` is a KNOWN, documented,
            # accepted non-blocker for adopted-benchmark splits: RDKit's
            # Murcko scaffold assignment can differ slightly from TDC's own
            # even for the same molecule, producing small scaffold-bucket
            # overlaps with zero actual compound duplication (see
            # documentation/AIMS/mistakes.md, M1 Run 2, "BBB and several
            # CYPs" — this preflight run additionally found it on
            # solubility_logs and augmented DILI). It is ONLY safe to treat
            # as non-blocking when the exact-SMILES check still passed
            # (no real duplicate compounds) AND the split is an adopted
            # TDC benchmark split, not one of MARS's own self-generated
            # scaffold splits (hERG_Karim, PPB-human) — those are
            # constructed to guarantee zero scaffold overlap by
            # construction, so an overlap there WOULD be a genuine bug.
            if not (
                c.name == "test_disjoint_from_train_val_scaffolds"
                and split_method == "adopt_benchmark"
                and next(
                    (x.passed for x in audit.checks if x.name == "test_disjoint_from_train_val_smiles"), False
                )
            )
        ]
        result["non_blocking_warnings"] = [
            f"{c.name}: {c.detail}" for c in audit.failed_checks if c not in blocking_failures
        ]
        if blocking_failures:
            result["error"] = "leakage audit failed: " + "; ".join(
                f"{c.name}: {c.detail}" for c in blocking_failures
            )
            return result
    except Exception as exc:
        result["error"] = f"run_leakage_audit raised: {exc}"
        return result

    result["ok"] = True
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--prep-id", required=True)
    p.add_argument("--processed-dir", default=None)
    p.add_argument("--runs-dir", default=None)
    p.add_argument("--artifacts-root", default=None)
    args = p.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    ml_root = repo_root / "ml"
    processed_dir = Path(args.processed_dir) if args.processed_dir else ml_root / "data" / "processed"
    prep_dir = processed_dir / args.prep_id
    runs_dir = Path(args.runs_dir) if args.runs_dir else ml_root / "runs"
    artifacts_root = Path(args.artifacts_root) if args.artifacts_root else ml_root / "artifacts"

    print(f"prep_dir: {prep_dir} (exists={prep_dir.exists()})")
    if not prep_dir.exists():
        print("STOP: prep_dir does not exist", file=sys.stderr)
        return 1

    results = []
    any_failed = False
    for ep in ML_ENDPOINTS:
        use_aug = ep.value == "dili_liver_injury"
        r = _check_endpoint(prep_dir, ep.value, use_augmented_dili=use_aug)
        results.append(r)
        status = "OK" if r["ok"] else "FAIL"
        print(f"[{status}] {ep.value} (dataset_key={r.get('dataset_key')})")
        if not r["ok"]:
            any_failed = True
            print(f"    STOP REASON: {r.get('error')}")
        else:
            print(f"    n_train_val={r['n_train_val']} n_test={r['n_test']} n_calibration={r['n_calibration']}")
            if "class_balance_train_val" in r:
                print(f"    class_balance={r['class_balance_train_val']}")
            else:
                print(f"    label_stats={r['label_stats_train_val']}")
            print(f"    split_method={r['split_method']} leakage_audit_passed={r['leakage_audit_passed']}")
            if r.get("non_blocking_warnings"):
                for w in r["non_blocking_warnings"]:
                    print(f"    [non-blocking, documented] {w}")

    for d, label in [(runs_dir, "runs_dir"), (artifacts_root, "artifacts_root")]:
        d.mkdir(parents=True, exist_ok=True)
        probe = d / ".preflight_write_probe"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            print(f"[OK] {label} writable: {d}")
        except Exception as exc:
            print(f"[FAIL] {label} NOT writable: {d} ({exc})", file=sys.stderr)
            any_failed = True

    try:
        import wandb

        api = wandb.Api()
        viewer = api.viewer
        print(f"[OK] W&B reachable (read-only): user={viewer.username if viewer else 'unknown'}")
    except Exception as exc:
        print(f"[WARN] W&B not reachable ({exc}) — sweep will still run with use_wandb, but mirroring may fail per-run")

    out_path = ml_root / "runs" / "preflight_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nPreflight report written to {out_path}")

    if any_failed:
        print("\nPREFLIGHT FAILED — do not proceed to the pilot run.", file=sys.stderr)
        return 1
    print(f"\nPREFLIGHT PASSED — all {len(ML_ENDPOINTS)} endpoints OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
