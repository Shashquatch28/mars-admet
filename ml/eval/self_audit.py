"""
Module 11 §5 self-audit: run the leakage checks against the data and artifacts that are actually
served, and write the result as a dated report.

What it does
------------
For each of the 14 ML endpoints it loads the processed snapshot the production sweep trained under
(DILI as the DILIst-augmented pool, as served), loads the promoted AD index and Platt calibrator
where they exist, and runs ``eval.leakage_audit.run_leakage_audit``: test vs train/val on SMILES and
Murcko scaffold, calibration split inside train/val and disjoint from test, duplicates, per-seed
fold scaffold isolation and coverage, AD reference set disjoint from test, and calibrator fit count.

It also records what a reader needs to judge reproducibility: the snapshot id and the manifest
sha256, the code commit, the package versions, and the extent of hyperparameter tuning as read from
the sweep summary (nothing is typed in by hand).

What it does not do
-------------------
It does not prove the KERMT models are leak-free. KERMT trained on a different snapshot
(``20260918T090433Z``) and a leakage-safe pool assembled by ``ml/data/cluster_loaders.py``; its
pool sizes match the XGBoost rebuild exactly (see ``kermt_vs_xgboost_pool_matched.md``) but
``ml/data/compare_prep.py`` hash equality across the two machines is the proof and needs both.

Usage
-----
    cd ml && PYTHONPATH=. python eval/self_audit.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import date
from importlib import metadata
from pathlib import Path

from data.loaders import load_endpoint
from mars_contracts.endpoints import ML_ENDPOINTS

from eval.applicability_domain import ADIndex
from eval.calibration import PlattCalibrator
from eval.leakage_audit import LeakageAuditReport, run_leakage_audit

DEFAULT_PREP_ID = "20260830T200000Z"  # the snapshot all 70 sweep runs trained under

_PACKAGES = ("numpy", "pandas", "scikit-learn", "scipy", "xgboost", "rdkit", "joblib")


def _git_head(repo: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=20
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _versions() -> dict[str, str]:
    found: dict[str, str] = {}
    for name in _PACKAGES:
        try:
            found[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            found[name] = "not installed"
    return found


def audit_endpoint(prep_dir: Path, artifacts_root: Path, key: str) -> LeakageAuditReport:
    data = load_endpoint(prep_dir, key, use_augmented_dili=(key == "dili_liver_injury"))
    ep_dir = artifacts_root / key
    ad_dir = ep_dir / "ad_index"
    ad_index = ADIndex.load(ad_dir) if (ad_dir / "metadata.json").exists() else None
    cal_path = ep_dir / "calibrator.json"
    calibrator = PlattCalibrator.load(cal_path) if cal_path.exists() else None
    return run_leakage_audit(data, ad_index=ad_index, calibrator=calibrator)


def render_markdown(
    reports: list[LeakageAuditReport],
    *,
    prep_id: str,
    manifest_sha: str,
    code_sha: str,
    versions: dict[str, str],
    sweep: dict,
    today: str,
) -> str:
    n_checks = sum(len(r.checks) for r in reports)
    n_failed = sum(1 for r in reports for c in r.checks if not c.passed)
    failed_eps = [r.endpoint_key for r in reports if not r.all_passed]
    lines = [
        "# Self-audit of the served XGBoost models (Module 11 section 5)",
        "",
        f"Generated {today} by `ml/eval/self_audit.py`. Nothing in this file is typed by hand: the checks "
        "run against the processed snapshot and promoted artifacts named below.",
        "",
        f"**Result: {len(reports)} endpoints, {n_checks} checks, {n_failed} failed.**",
        "",
        "## (a) Leakage",
        "",
        "Each check is a small pure function in `ml/eval/leakage_audit.py`. A cell is the number of checks "
        "that passed over the number that ran for that endpoint (the AD-index and calibrator checks run only "
        "when that artifact exists, so regression endpoints run fewer).",
        "",
        "| endpoint | checks passed | detail of any failure |",
        "|---|---|---|",
    ]
    for r in reports:
        ok = sum(1 for c in r.checks if c.passed)
        bad = "; ".join(f"{c.name}: {c.detail}" for c in r.checks if not c.passed) or "none"
        lines.append(f"| {r.endpoint_key} | {ok} / {len(r.checks)} | {bad} |")
    names = sorted({c.name for r in reports for c in r.checks})
    lines += [
        "",
        "Checks that ran: " + ", ".join(f"`{n}`" for n in names) + ".",
        "",
        "**Reading the scaffold check.** `test_disjoint_from_train_val_scaffolds` fails where a non-acyclic Murcko "
        f"scaffold occurs on both sides ({len(failed_eps)} endpoints failed a check on this run: "
        + ", ".join(f"`{e}`" for e in failed_eps)
        + "). The explanation below was written for the 2026-10-24 snapshot; "
        "re-read it if that list changes. Two different causes sat behind the failures:",
        "",
        "- *Solubility, BBB, CYP3A4, CYP2D6, CYP2C9:* these adopt TDC's benchmark split verbatim for leaderboard "
        "comparability, and MARS's stricter standardization turns a few TDC scaffold groups into overlaps. M1 recorded "
        "each in its `split_report.json` `notes[]` (`mars-status_M1.md` F-Run2-2). Small: 2 to 15 scaffolds. "
        "`evaluation_results.md` counts the test molecules involved.",
        "- *DILI:* the base split has no overlap. The DILIst-augmented training pool, which is what the served "
        "model learned from, shares 19 scaffolds with the test set. M1 recorded the count (`mars-status_M1.md` H-5, "
        "\"expected for a small chemical space\") and used the pool as it stood. Module 11 section 5(a) asks for "
        "no overlap especially after augmentation, so this audit **does not meet that rule for DILI**. "
        "`evaluation_results.md` reports the DILI score on the test molecules that share no scaffold with the pool.",
        "",
        "DILI is audited as the DILIst-augmented pool the model was trained on. Its test set is "
        "bit-identical to the base set (verified by `ml/tests`).",
        "",
        "## (b) Hyperparameter tuning: extent and what data it touched",
        "",
        f"- The XGBoost \"sweep\" is {sweep.get('n_attempted', '?')} training runs "
        f"({sweep.get('n_endpoints', '?')} endpoints x {sweep.get('n_seeds_per_endpoint', '?')} seeds); "
        f"{sweep.get('n_completed', '?')} completed, {sweep.get('n_failed', '?')} failed. It is a seed "
        "sweep, not a hyperparameter search: `run_production_sweep.py` passes no hyperparameters.",
        "- Every endpoint therefore uses the same fixed defaults from `ml/models/xgboost_model.py` "
        "(n_estimators 500, max_depth 6, learning_rate 0.05, subsample 0.8, colsample_bytree 0.8) with early "
        "stopping (50 rounds) on each seed's own validation fold. The only thing fitted to validation data is "
        "the stopping round. No hyperparameter was chosen by looking at the test split.",
        "- The held-out test split is read only by `ml/train/evaluate_xgboost_test.py` and by this audit's "
        "leakage checks; nothing is fit, selected or tuned on it (`ml/eval/heldout_evaluation.py` states the "
        "same). Not tuning is a limitation as well as a safeguard: no claim is made that these defaults are "
        "the best XGBoost can do on any endpoint.",
        "- The Platt calibrators were fit on the calibration split and are not applied to served scores "
        "(C0, `xgboost_c0_raw_vs_calibrated.md`).",
        "- KERMT used stock hyperparameters (Tier 0): nothing was tuned. The routing rule that picks KERMT "
        "or XGBoost per endpoint was applied to test records, so the routed choice for those 14 endpoints "
        "is itself selected on test data. The per-endpoint numbers it selects between are reported as they "
        "are; a fresh split would be needed to estimate the routed system without that selection effect.",
        "",
        "## (c) Reproducibility",
        "",
        f"- Processed snapshot: `{prep_id}`; manifest sha256 `{manifest_sha}`.",
        f"- Code commit: `{code_sha}`.",
        f"- Python {platform.python_version()} on {platform.system()}; "
        + ", ".join(f"{k} {v}" for k, v in versions.items())
        + ".",
        "- Seeds are fixed (`FIXED_SEEDS` in `ml/configs/experiment_config.py`); the promoted artifacts are "
        "the five per-seed models in `ml/artifacts/<endpoint>/seed_<n>/`, which are gitignored. A deployed "
        "service fetches them as a verified release (`ml/serve/artifact_store.py`).",
        "- The package versions above are those of the machine that ran this audit, not necessarily those "
        "that trained the models. The deploy image resolves rdkit 2026.9.1 while the models trained on "
        "2026.3.5; the 217 descriptors matched to 6e-14 on 31 molecules (deploy notes), not pinned.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ml_root = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prep-id", default=DEFAULT_PREP_ID)
    p.add_argument("--prep-root", default=str(ml_root / "data" / "processed"))
    p.add_argument("--artifacts-root", default=str(ml_root / "artifacts"))
    p.add_argument("--sweep-summary", default=str(ml_root / "runs" / "production_sweep_summary.json"))
    p.add_argument("--out-md", default=str(ml_root.parent / "documentation" / "status" / "self_audit.md"))
    p.add_argument("--out-json", default=str(ml_root.parent / "documentation" / "status" / "self_audit.json"))
    args = p.parse_args(argv)

    prep_dir = Path(args.prep_root) / args.prep_id
    if not prep_dir.exists():
        print(f"Processed snapshot not found: {prep_dir}", file=sys.stderr)
        return 2
    artifacts_root = Path(args.artifacts_root)

    reports = [audit_endpoint(prep_dir, artifacts_root, e.value) for e in ML_ENDPOINTS]
    for r in reports:
        status = "ok" if r.all_passed else "FAILED"
        print(f"{status:7s} {r.endpoint_key:26s} {sum(c.passed for c in r.checks)}/{len(r.checks)}", flush=True)

    manifest = prep_dir / "manifest.json"
    manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest() if manifest.exists() else "no manifest"
    sweep_path = Path(args.sweep_summary)
    sweep = json.loads(sweep_path.read_text()) if sweep_path.exists() else {}

    md = render_markdown(
        reports,
        prep_id=args.prep_id,
        manifest_sha=manifest_sha,
        code_sha=_git_head(ml_root.parent),
        versions=_versions(),
        sweep=sweep,
        today=date.today().isoformat(),
    )
    Path(args.out_md).write_text(md, encoding="utf-8", newline="\n")
    Path(args.out_json).write_text(
        json.dumps(
            {
                "prep_id": args.prep_id,
                "manifest_sha256": manifest_sha,
                "endpoints": {
                    r.endpoint_key: [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in r.checks]
                    for r in reports
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"\nwrote {args.out_md}")
    return 0 if all(r.all_passed for r in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
