"""
Module 11 section 6: DILI trained on the DILIst-augmented pool against TDC-only.

Question
--------
The served DILI model learned from 1,119 molecules: the 378 TDC molecules plus DILIst rows, a pool that
shares 19 Murcko scaffolds with the test set (``self_audit.md``). Does the augmentation change the
held-out result?

Design
------
* Same 96 test molecules for both (checked equal, in order).
* TDC-only: XGBoost retrained here on the base ``train_val`` (378) with the unchanged protocol
  (``train_xgboost.train_one_seed``: same featurisation, hyperparameters, early stopping, five seeds 0-4).
  Scratch run directory and feature cache; nothing under ``ml/runs`` or ``ml/artifacts`` is touched.
* Augmented: the promoted production models, scored the same way.
* Per-seed AUROC, AUPRC, Brier and ECE (raw), mean ± sample std; then the five-seed mean score for each
  model, a *paired* bootstrap of the AUROC difference over the test molecules (augmented minus TDC-only),
  and the same on two subsets: test molecules that share no scaffold with the augmented pool (71) and
  those that do (25).

What it can and cannot show
---------------------------
* 96 test molecules. The paired interval is the honest summary: if it contains zero the data cannot
  separate the two pools. No winner is named either way.
* The pools differ in size (378 against 1,119) and in the molecules the early-stopping folds see, so the
  difference is the augmentation *and* its side effects.
* The shared-scaffold subset is a leakage diagnostic for the augmented model, not a second test set.

Usage (from ``ml/``)
    PYTHONPATH=. python eval/dili_augmentation_ablation.py --prep-root <.../processed> \\
        --artifacts-root <.../artifacts> --runs-dir <scratch> --cache-root <scratch>
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

DEFAULT_PREP_ID = "20260830T200000Z"
ML_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_ROOT.parent
N_BOOT = 4000
BOOT_SEED = 20261025
ENDPOINT = "dili_liver_injury"


def paired_auroc_difference(
    y: np.ndarray, p_a: np.ndarray, p_b: np.ndarray, *, n_boot: int = N_BOOT, seed: int = BOOT_SEED
) -> tuple[float, float, float, int]:
    """AUROC(a) - AUROC(b) on the same molecules, with a 95 % percentile bootstrap over the molecules.

    Returns (difference, low, high, resamples used). Resamples with a single class are skipped.
    """
    y = np.asarray(y, dtype=float)
    rng = np.random.default_rng(seed)
    n = len(y)
    diffs = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        yb = y[idx]
        if yb.min() == yb.max():
            continue
        diffs.append(roc_auc_score(yb, p_a[idx]) - roc_auc_score(yb, p_b[idx]))
    if not diffs:
        raise ValueError("every resample had a single class")
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return float(roc_auc_score(y, p_a) - roc_auc_score(y, p_b)), float(lo), float(hi), len(diffs)


def _pair(values: list[float]) -> tuple[float, float]:
    arr = np.array(values, dtype=float)
    return float(arr.mean()), float(arr.std(ddof=1))


def _fmt(pair: tuple[float, float]) -> str:
    return f"{pair[0]:.3f} ± {pair[1]:.3f}"


def render_markdown(res: dict, *, today: str, prep_id: str) -> str:
    rows = []
    labels = {"auroc": "AUROC", "auprc": "AUPRC", "brier": "Brier", "ece": "ECE"}
    for name, label in labels.items():
        a, b = res["augmented"][name], res["tdc_only"][name]
        rows.append(f"| {label} | {_fmt(b)} | {_fmt(a)} | {a[0] - b[0]:+.3f} |")
    sub = res["subsets"]
    lines = [
        "# DILI: augmented pool against TDC-only (Module 11 section 6)",
        "",
        f"Generated {today} by `ml/eval/dili_augmentation_ablation.py` on snapshot `{prep_id}`. Same {res['n_test']} "
        "test molecules for both models, raw scores, five seeds each. The TDC-only models were retrained for this "
        "comparison with the unchanged protocol (scratch directories; nothing promoted or overwritten); the "
        "augmented models are the promoted production ones. **This is a comparison of numbers, not a ranking.**",
        "",
        f"| metric (test, mean ± std over 5 seeds) | TDC-only ({res['n_train_base']} molecules) | augmented ({res['n_train_aug']} molecules) | augmented minus TDC-only |",
        "|---|---|---|---|",
        *rows,
        "",
        "## Paired bootstrap of the AUROC difference (five-seed mean score of each model)",
        "",
        "Augmented minus TDC-only on the same molecules; 95 % percentile interval over resampled test molecules "
        f"({N_BOOT} resamples, those with a single class skipped).",
        "",
        "| test molecules | n | TDC-only AUROC | augmented AUROC | difference [95 % interval] |",
        "|---|---|---|---|---|",
    ]
    for key, label in (("all", "all"), ("free", "share no scaffold with the augmented pool"), ("shared", "share a scaffold with the augmented pool")):
        s = sub[key]
        lines.append(
            f"| {label} | {s['n']} | {s['auroc_base']:.3f} | {s['auroc_aug']:.3f} | "
            f"{s['diff']:+.3f} [{s['low']:+.3f}, {s['high']:+.3f}] ({s['used']} resamples) |"
        )
    contains_zero = sub["all"]["low"] <= 0.0 <= sub["all"]["high"]
    lines += [
        "",
        "## Reading it",
        "",
        "- On all test molecules the paired interval "
        + ("contains zero: these 96 molecules cannot separate the two pools." if contains_zero
           else "does not contain zero; read the subset rows before treating that as an effect of the augmentation alone.")
        ,
        f"- The per-seed means and the five-seed ensemble differ by {abs(res['augmented']['auroc'][0] - res['tdc_only']['auroc'][0] - sub['all']['diff']):.3f} "
        "in the AUROC difference and can even differ in sign. Both are inside the noise of 96 molecules; the paired "
        "interval is the figure to read.",
        f"- **Calibration quality moves much more than ranking.** Positive rate: TDC-only pool {res['pos_rates']['tdc_only_pool']:.2f}, "
        f"augmented pool {res['pos_rates']['augmented_pool']:.2f}, test set {res['pos_rates']['test']:.2f}. Brier and ECE are "
        "computed on raw scores, so a model whose training pool has a different positive rate from the test set "
        "can report scores shifted by that difference even when it ranks molecules equally well. A gap in Brier and "
        "ECE with no gap in AUROC is consistent with that; this comparison does not isolate it (the pools also "
        "differ in label source and size), so it is a reading, not a finding.",
        "- The augmented pool shares 19 scaffolds with the test set (`self_audit.md`). The two subset rows are a "
        "leakage diagnostic: a gap that appears only on the molecules sharing a scaffold would point at the overlap. "
        "With 71 and 25 molecules each interval is wide.",
        "- The pools differ in size and in the molecules the early-stopping folds see, so the difference is the "
        "augmentation plus those side effects. DILI labels from DILIst and from the TDC set are curated "
        "differently; the augmented labels were merged by majority vote (`augmentation_report.json`).",
        "- No hyperparameter was tuned for either model.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--prep-id", default=DEFAULT_PREP_ID)
    p.add_argument("--prep-root", default=str(ML_ROOT / "data" / "processed"))
    p.add_argument("--artifacts-root", default=str(ML_ROOT / "artifacts"))
    p.add_argument("--runs-dir", required=True, help="Scratch directory for the retraining run records.")
    p.add_argument("--cache-root", required=True, help="Scratch feature cache.")
    p.add_argument("--out-md", default=str(REPO_ROOT / "documentation" / "status" / "dili_augmentation_ablation.md"))
    p.add_argument("--out-json", default=str(REPO_ROOT / "documentation" / "status" / "dili_augmentation_ablation.json"))
    args = p.parse_args(argv)

    from configs.experiment_config import FIXED_SEEDS, ExperimentConfig
    from data.loaders import load_endpoint
    from featurize.cache import FeatureCache
    from featurize.scaffold import murcko_scaffold_from_smiles
    from models.xgboost_model import XGBoostModel
    from train.train_xgboost import train_one_seed

    from eval.metrics import compute_classification_metrics

    prep_dir = Path(args.prep_root) / args.prep_id
    base = load_endpoint(prep_dir, ENDPOINT, use_augmented_dili=False)
    aug = load_endpoint(prep_dir, ENDPOINT, use_augmented_dili=True)
    if not base.test.reset_index(drop=True).equals(aug.test.reset_index(drop=True)):
        raise SystemExit("the base and augmented DILI test sets differ; the comparison is not on the same molecules")

    cache = FeatureCache(Path(args.cache_root))
    te_s = base.test["standardized_smiles"].tolist()
    y = base.test["label"].astype(float).to_numpy()

    # TDC-only: retrain, five seeds, unchanged protocol.
    config = ExperimentConfig(endpoint=ENDPOINT, model_family="xgboost", seed=FIXED_SEEDS[0], prep_id=args.prep_id)
    base_preds = []
    for seed in FIXED_SEEDS:
        result = train_one_seed(base, config, cache, seed, runs_dir=Path(args.runs_dir), repo_root=REPO_ROOT)
        model = XGBoostModel.load_with_cache(result.model_path, cache)
        base_preds.append(np.asarray(model.predict(te_s), dtype=float))
        print(f"TDC-only seed {seed}: n_train {result.n_train}", flush=True)
    # Augmented: the promoted production models.
    aug_preds = []
    for seed in FIXED_SEEDS:
        model = XGBoostModel.load_with_cache(Path(args.artifacts_root) / ENDPOINT / f"seed_{seed}", cache)
        aug_preds.append(np.asarray(model.predict(te_s), dtype=float))

    stacked = np.vstack([*base_preds, *aug_preds])
    ok = ~np.isnan(stacked).any(axis=0)
    y_ok = y[ok]

    def per_seed(preds: list[np.ndarray]) -> dict[str, tuple[float, float]]:
        ms = [compute_classification_metrics(y_ok, p[ok]) for p in preds]
        return {
            "auroc": _pair([m.auroc for m in ms]),
            "auprc": _pair([m.auprc for m in ms]),
            "brier": _pair([m.brier_score for m in ms]),
            "ece": _pair([m.ece for m in ms]),
        }

    res = {
        "n_test": int(ok.sum()),
        "n_train_base": len(base.train_val),
        "n_train_aug": len(aug.train_val),
        "tdc_only": per_seed(base_preds),
        "augmented": per_seed(aug_preds),
        "pos_rates": {
            "tdc_only_pool": float(base.train_val["label"].astype(float).mean()),
            "augmented_pool": float(aug.train_val["label"].astype(float).mean()),
            "test": float(y_ok.mean()),
        },
    }
    pb, pa = np.mean(base_preds, axis=0)[ok], np.mean(aug_preds, axis=0)[ok]
    aug_scaf = {murcko_scaffold_from_smiles(s) for s in aug.train_val["standardized_smiles"]} - {""}
    shares = np.array([murcko_scaffold_from_smiles(s) in aug_scaf for s, k in zip(te_s, ok, strict=True) if k], dtype=bool)
    subsets = {}
    for key, mask in (("all", np.ones_like(shares)), ("free", ~shares), ("shared", shares)):
        diff, lo, hi, used = paired_auroc_difference(y_ok[mask], pa[mask], pb[mask])
        subsets[key] = {
            "n": int(mask.sum()),
            "auroc_base": float(roc_auc_score(y_ok[mask], pb[mask])),
            "auroc_aug": float(roc_auc_score(y_ok[mask], pa[mask])),
            "diff": diff,
            "low": lo,
            "high": hi,
            "used": used,
        }
    res["subsets"] = subsets

    Path(args.out_md).write_text(render_markdown(res, today=date.today().isoformat(), prep_id=args.prep_id), encoding="utf-8", newline="\n")
    Path(args.out_json).write_text(json.dumps(res, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
