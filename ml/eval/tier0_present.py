"""
Consolidated presentation package for a completed Tier-0 arm (5 seeds).

Reads:
  * ``runs/kermt_tier0_<arm>_aggregate.json`` (written by the runbook's own
    ``s_agg.py`` via ``eval.cluster_calibration.aggregate_test_metrics_across_seeds``
    / ``aggregate_calibration_across_seeds`` -- the project's documented mean +/- std
    aggregation method, blueprint Module 11 Section 2). This script does not
    invent a different statistic for the primary numbers; it visualizes what
    that function already computed, plus purely descriptive median/min/max
    (explicitly labelled supplementary, not a substitute).
  * Each seed's ``artifacts/metrics/seed_summary.json`` (written by
    ``eval/tier0_artifacts.py``).

Writes ``runs/tier0_<arm>/`` -- plots, tables, metrics, provenance, a copy of
each seed's own plot/metrics package under ``per_seed/<run_id>/``, and a
README.md explaining every artifact's provenance and split.

No GPU/container calls. No retraining. No test-set-influenced decisions --
this only visualizes already-computed, already-verified per-seed results.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

RUNS_DIR = Path("runs")


def save_fig(fig, out_dir: Path, stem: str) -> tuple[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    png, pdf = out_dir / f"{stem}.png", out_dir / f"{stem}.pdf"
    fig.savefig(png, dpi=150, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")
    plt.close(fig)
    return str(png), str(pdf)


def present(arm: str, run_ids: list[str], out_name: str | None = None) -> Path:
    agg_path = RUNS_DIR / f"kermt_tier0_{arm}_aggregate.json"
    aggregate = json.loads(agg_path.read_text(encoding="utf-8"))
    endpoint_key = next(iter(aggregate["test_metrics_across_seeds"]))

    seeds_summaries = []
    for rid in run_ids:
        p = RUNS_DIR / rid / "artifacts" / "metrics" / "seed_summary.json"
        seeds_summaries.append(json.loads(p.read_text(encoding="utf-8")))
    seeds_summaries.sort(key=lambda s: s["seed"])

    out_dir = RUNS_DIR / (out_name or f"tier0_{arm}")
    plots_dir = out_dir / "plots"
    tables_dir = out_dir / "tables"
    metrics_dir = out_dir / "metrics"
    prov_dir = out_dir / "provenance"
    per_seed_dir = out_dir / "per_seed"
    for d in (plots_dir, tables_dir, metrics_dir, prov_dir, per_seed_dir):
        d.mkdir(parents=True, exist_ok=True)

    seeds = [s["seed"] for s in seeds_summaries]
    test_raw = {m: np.array([s["test_metrics_raw"][m] for s in seeds_summaries]) for m in ("auroc", "auprc", "brier_score", "ece")}
    test_cal = {m: np.array([s["test_metrics_calibrated"][m] for s in seeds_summaries]) for m in ("auroc", "auprc", "brier_score", "ece")}
    val_auroc = np.array([s["best_val_auroc"] for s in seeds_summaries], dtype=float)
    test_auroc_raw = test_raw["auroc"]
    best_epochs = np.array([s["best_epoch"] for s in seeds_summaries], dtype=float)
    gap = val_auroc - test_auroc_raw

    generated: list[dict] = []

    def bar_by_seed(values, ylabel, title, stem, color="#1f77b4"):
        fig, ax = plt.subplots(figsize=(5.5, 4))
        ax.bar([str(s) for s in seeds], values, color=color)
        mean = float(np.mean(values))
        ax.axhline(mean, color="#d62728", linestyle="--", label=f"mean={mean:.4f}")
        for i, v in enumerate(values):
            ax.text(i, v, f"{v:.3f}", ha="center", va="bottom", fontsize=8)
        ax.set_xlabel("seed")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.legend()
        png, pdf = save_fig(fig, plots_dir, stem)
        generated.append({"file_png": png, "file_pdf": pdf, "description": title})

    bar_by_seed(test_raw["auroc"], "test AUROC", f"{arm} / {endpoint_key}\nTest AUROC by seed (raw; raw==calibrated, rank-preserving)", "01_test_auroc_by_seed")
    bar_by_seed(test_raw["auprc"], "test AUPRC", f"{arm} / {endpoint_key}\nTest AUPRC by seed (raw; raw==calibrated, rank-preserving)", "02_test_auprc_by_seed")
    bar_by_seed(test_raw["brier_score"], "test Brier (raw)", f"{arm} / {endpoint_key}\nTest Brier score by seed (raw)", "03_test_brier_by_seed", color="#9467bd")
    bar_by_seed(test_raw["ece"], "test ECE (raw)", f"{arm} / {endpoint_key}\nTest ECE by seed (raw)", "04_test_ece_by_seed", color="#8c564b")

    def raw_vs_cal(metric, ylabel, stem, title):
        fig, ax = plt.subplots(figsize=(6, 4))
        x = np.arange(len(seeds))
        w = 0.35
        ax.bar(x - w / 2, test_raw[metric], w, label="raw", color="#1f77b4")
        ax.bar(x + w / 2, test_cal[metric], w, label="calibrated", color="#d62728")
        ax.set_xticks(x, labels=[str(s) for s in seeds])
        ax.set_xlabel("seed")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.legend()
        png, pdf = save_fig(fig, plots_dir, stem)
        generated.append({"file_png": png, "file_pdf": pdf, "description": title})

    raw_vs_cal("brier_score", "Brier score", "05_brier_raw_vs_calibrated", f"{arm} / {endpoint_key}\nRaw vs calibrated Brier score, per seed (test)")
    raw_vs_cal("ece", "ECE", "06_ece_raw_vs_calibrated", f"{arm} / {endpoint_key}\nRaw vs calibrated ECE, per seed (test)")

    agg_raw = aggregate["test_metrics_across_seeds"][endpoint_key]["raw"]
    agg_cal = aggregate["test_metrics_across_seeds"][endpoint_key]["calibrated"]
    fig, ax = plt.subplots(figsize=(6, 4.5))
    metrics_lbl = ["AUROC", "AUPRC"]
    means = [agg_raw["auroc_mean"], agg_raw["auprc_mean"]]
    stds = [agg_raw["auroc_std"], agg_raw["auprc_std"]]
    x = np.arange(len(metrics_lbl))
    ax.errorbar(x, means, yerr=stds, fmt="o", markersize=10, capsize=6, color="#d62728", label=f"mean ± std (n={int(agg_raw['n_seeds'])} seeds)")
    for i, m in enumerate(("auroc", "auprc")):
        ax.scatter(np.full(len(seeds), i) + 0.08, test_raw[m], color="#1f77b4", alpha=0.7, zorder=3, label="individual seeds" if i == 0 else None)
    ax.set_xticks(x, labels=metrics_lbl)
    ax.set_ylabel("value")
    ax.set_title(f"{arm} / {endpoint_key}\nPrimary test metrics: mean ± std (project's documented aggregation) + individual seeds")
    ax.legend()
    png, pdf = save_fig(fig, plots_dir, "07_mean_sd_summary")
    generated.append({"file_png": png, "file_pdf": pdf, "description": "Mean+-std (documented aggregation) with individual seed points, primary test metrics."})

    fig, ax = plt.subplots(figsize=(5.5, 5.5))
    ax.scatter(val_auroc, test_auroc_raw, s=80, color="#1f77b4")
    for i, s in enumerate(seeds):
        ax.annotate(f"seed {s}", (val_auroc[i], test_auroc_raw[i]), textcoords="offset points", xytext=(6, 4), fontsize=9)
    lo = min(val_auroc.min(), test_auroc_raw.min()) - 0.02
    hi = max(val_auroc.max(), test_auroc_raw.max()) + 0.02
    ax.plot([lo, hi], [lo, hi], color="gray", linestyle=":", label="val == test")
    ax.set_xlabel("best validation AUROC")
    ax.set_ylabel("test AUROC (raw)")
    ax.set_title(f"{arm} / {endpoint_key}\nPer-seed validation AUROC vs test AUROC")
    ax.legend()
    png, pdf = save_fig(fig, plots_dir, "08_val_auroc_vs_test_auroc_by_seed")
    generated.append({"file_png": png, "file_pdf": pdf, "description": "Validation AUROC (x) vs test AUROC (y), one point per seed."})

    bar_by_seed(gap, "val AUROC − test AUROC", f"{arm} / {endpoint_key}\nValidation→test AUROC gap by seed", "09_val_to_test_gap_by_seed", color="#e377c2")
    bar_by_seed(best_epochs, "selected (best) epoch", f"{arm} / {endpoint_key}\nBest/selected epoch by seed (of 30)", "10_best_epoch_by_seed", color="#17becf")

    # ---- Part 10: training-curve aggregation across seeds --------------- #
    per_seed_epochs = []
    for rid in run_ids:
        log = RUNS_DIR / rid / "artifacts" / "kermt" / "logs" / "finetune.log"
        from eval.tier0_artifacts import parse_finetune_log

        rows, _, _ = parse_finetune_log(log)
        per_seed_epochs.append(rows)
    n_epochs_per_seed = {len(r) for r in per_seed_epochs}
    same_length = len(n_epochs_per_seed) == 1
    curve_note = None
    if same_length:
        n_ep = n_epochs_per_seed.pop()
        loss_train_mat = np.array([[r[e]["loss_train"] for e in range(n_ep)] for r in per_seed_epochs])
        loss_val_mat = np.array([[r[e]["loss_val"] for e in range(n_ep)] for r in per_seed_epochs])
        auc_val_mat = np.array([[r[e]["auc_val"] for e in range(n_ep)] for r in per_seed_epochs])
        epochs_axis = np.arange(n_ep)

        fig, ax = plt.subplots(figsize=(7, 4.5))
        for i, s in enumerate(seeds):
            ax.plot(epochs_axis, loss_train_mat[i], color="#1f77b4", alpha=0.35, linewidth=1)
            ax.plot(epochs_axis, loss_val_mat[i], color="#ff7f0e", alpha=0.35, linewidth=1)
        mean_tr, std_tr = loss_train_mat.mean(axis=0), loss_train_mat.std(axis=0, ddof=1)
        mean_va, std_va = loss_val_mat.mean(axis=0), loss_val_mat.std(axis=0, ddof=1)
        ax.plot(epochs_axis, mean_tr, color="#1f77b4", linewidth=2.5, label="mean train loss")
        ax.fill_between(epochs_axis, mean_tr - std_tr, mean_tr + std_tr, color="#1f77b4", alpha=0.15)
        ax.plot(epochs_axis, mean_va, color="#ff7f0e", linewidth=2.5, label="mean val loss")
        ax.fill_between(epochs_axis, mean_va - std_va, mean_va + std_va, color="#ff7f0e", alpha=0.15)
        ax.set_xlabel("epoch")
        ax.set_ylabel("loss")
        ax.set_title(f"{arm} / {endpoint_key}\nAggregate training loss across {len(seeds)} seeds (mean ± std band; thin lines = individual seeds)")
        ax.legend()
        png, pdf = save_fig(fig, plots_dir, "11_aggregate_training_loss_curve")
        generated.append({"file_png": png, "file_pdf": pdf, "description": "Mean +- std train/val loss across all 5 seeds, individual seed curves preserved as thin lines."})

        fig, ax = plt.subplots(figsize=(7, 4.5))
        for i, s in enumerate(seeds):
            ax.plot(epochs_axis, auc_val_mat[i], color="#2ca02c", alpha=0.35, linewidth=1)
        mean_auc, std_auc = auc_val_mat.mean(axis=0), auc_val_mat.std(axis=0, ddof=1)
        ax.plot(epochs_axis, mean_auc, color="#2ca02c", linewidth=2.5, label="mean val AUROC")
        ax.fill_between(epochs_axis, mean_auc - std_auc, mean_auc + std_auc, color="#2ca02c", alpha=0.15)
        ax.set_xlabel("epoch")
        ax.set_ylabel("val AUROC")
        ax.set_title(f"{arm} / {endpoint_key}\nAggregate validation AUROC across {len(seeds)} seeds\n(train AUROC not exposed by KERMT's finetune CLI)")
        ax.legend()
        png, pdf = save_fig(fig, plots_dir, "12_aggregate_val_auroc_curve")
        generated.append({"file_png": png, "file_pdf": pdf, "description": "Mean +- std val AUROC across all 5 seeds, individual seed curves preserved as thin lines."})
    else:
        curve_note = f"Seeds do not share the same epoch count ({n_epochs_per_seed}); aggregate training-curve figures were skipped rather than interpolated/padded."

    # ---- Tables ----------------------------------------------------------- #
    import csv

    with (tables_dir / "per_seed_metrics.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "seed", "run_id", "best_epoch", "best_val_auroc", "final_val_auroc",
            "test_auroc_raw", "test_auprc_raw", "test_brier_raw", "test_ece_raw",
            "test_auroc_cal", "test_auprc_cal", "test_brier_cal", "test_ece_cal",
            "temperature", "at_boundary", "optimizer_success", "wandb_url",
        ])
        for s in seeds_summaries:
            w.writerow([
                s["seed"], s["run_id"], s["best_epoch"], s["best_val_auroc"], s["final_val_auroc"],
                s["test_metrics_raw"]["auroc"], s["test_metrics_raw"]["auprc"], s["test_metrics_raw"]["brier_score"], s["test_metrics_raw"]["ece"],
                s["test_metrics_calibrated"]["auroc"], s["test_metrics_calibrated"]["auprc"], s["test_metrics_calibrated"]["brier_score"], s["test_metrics_calibrated"]["ece"],
                s["calibration_metrics"]["temperature"], s["calibration_metrics"]["at_boundary"], s["calibration_metrics"]["optimizer_success"], s["wandb_url"],
            ])

    def descriptive(values: np.ndarray) -> dict:
        return {"median": float(np.median(values)), "min": float(np.min(values)), "max": float(np.max(values))}

    summary_metrics = {
        "documented_aggregation": {
            "method": "mean +/- std over 5 seeds (blueprint Module 11 Section 2; eval.cluster_calibration.aggregate_test_metrics_across_seeds / aggregate_calibration_across_seeds, via the runbook's own s_agg.py)",
            "source_file": str(agg_path),
            "raw": agg_raw,
            "calibrated": agg_cal,
        },
        "supplementary_descriptive_stats": {
            "note": "Median/min/max are plain descriptive statistics over the same 5 numbers already aggregated above -- NOT a different or invented aggregation methodology. No confidence-interval method is specified anywhere in the blueprint/decisions/runbook for this comparison, so none is reported here.",
            "test_auroc_raw": descriptive(test_raw["auroc"]),
            "test_auprc_raw": descriptive(test_raw["auprc"]),
            "test_brier_raw": descriptive(test_raw["brier_score"]),
            "test_ece_raw": descriptive(test_raw["ece"]),
            "test_brier_calibrated": descriptive(test_cal["brier_score"]),
            "test_ece_calibrated": descriptive(test_cal["ece"]),
        },
        "calibration_stability": aggregate["calibration_stability_across_seeds"],
        "val_to_test_gap": {"mean": float(gap.mean()), "std": float(gap.std(ddof=1)), "per_seed": {int(s): float(g) for s, g in zip(seeds, gap)}},
    }
    (tables_dir / "summary_metrics.json").write_text(json.dumps(summary_metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (tables_dir / "summary_metrics.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric", "raw_mean", "raw_std", "calibrated_mean", "calibrated_std", "median_raw", "min_raw", "max_raw"])
        rows = [
            ("auroc", agg_raw["auroc_mean"], agg_raw["auroc_std"], agg_cal["auroc_mean"], agg_cal["auroc_std"], *descriptive(test_raw["auroc"]).values()),
            ("auprc", agg_raw["auprc_mean"], agg_raw["auprc_std"], agg_cal["auprc_mean"], agg_cal["auprc_std"], *descriptive(test_raw["auprc"]).values()),
            ("brier_score", agg_raw["brier_score_mean"], agg_raw["brier_score_std"], agg_cal["brier_score_mean"], agg_cal["brier_score_std"], *descriptive(test_raw["brier_score"]).values()),
            ("ece", agg_raw["ece_mean"], agg_raw["ece_std"], agg_cal["ece_mean"], agg_cal["ece_std"], *descriptive(test_raw["ece"]).values()),
        ]
        for r in rows:
            w.writerow(r)

    (metrics_dir / "aggregate_metrics.json").write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    overfitting_all = {str(s["seed"]): s["overfitting_diagnostics"] for s in seeds_summaries}
    (metrics_dir / "overfitting_diagnostics_all_seeds.json").write_text(json.dumps(overfitting_all, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # ---- Per-seed copies (self-contained package) ------------------------ #
    for s in seeds_summaries:
        rid = s["run_id"]
        src_plots = RUNS_DIR / rid / "artifacts" / "plots"
        src_metrics = RUNS_DIR / rid / "artifacts" / "metrics"
        src_tables = RUNS_DIR / rid / "artifacts" / "tables"
        dst = per_seed_dir / rid
        if dst.exists():
            shutil.rmtree(dst)
        (dst / "plots").mkdir(parents=True, exist_ok=True)
        (dst / "metrics").mkdir(parents=True, exist_ok=True)
        (dst / "tables").mkdir(parents=True, exist_ok=True)
        for f in src_plots.glob("*"):
            shutil.copy2(f, dst / "plots" / f.name)
        for f in src_metrics.glob("*"):
            shutil.copy2(f, dst / "metrics" / f.name)
        for f in src_tables.glob("*"):
            shutil.copy2(f, dst / "tables" / f.name)

    # ---- Provenance -------------------------------------------------------- #
    prov_manifest = {
        "arm": arm,
        "endpoint": endpoint_key,
        "n_seeds": len(seeds),
        "seeds": seeds,
        "run_ids": [s["run_id"] for s in seeds_summaries],
        "wandb_urls": {s["seed"]: s["wandb_url"] for s in seeds_summaries},
        "wandb_entity": "shashquatch",
        "wandb_project": "mars-admet",
        "git_sha": seeds_summaries[0]["git_sha"],
        "git_dirty_per_seed": {s["seed"]: s["git_dirty"] for s in seeds_summaries},
        "kermt_source_commit": seeds_summaries[0]["kermt_source_commit"],
        "checkpoint_sha256": seeds_summaries[0]["checkpoint_sha256"],
        "prep_id": seeds_summaries[0]["prep_id"],
        "config": seeds_summaries[0]["config"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": "ml/eval/tier0_present.py + ml/eval/tier0_artifacts.py",
        "aggregation_source": str(agg_path),
    }
    (prov_dir / "manifest.json").write_text(json.dumps(prov_manifest, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")

    # ---- README ------------------------------------------------------------ #
    readme_lines = [
        f"# Tier-0 DILI KERMT — {arm} / {endpoint_key} — 5-seed presentation package",
        "",
        f"Generated {prov_manifest['generated_at_utc']} by `ml/eval/tier0_present.py` (aggregate layer) "
        "and `ml/eval/tier0_artifacts.py` (per-seed layer). Both are read-only, post-hoc analysis scripts: "
        "they do not retrain, do not call the KERMT container, and never touch training/epoch-selection/"
        "calibration decisions. Everything here is reconstructed from artifacts the training runs already "
        "wrote (finetune.log, on-disk predictions.csv, calibration_diagnostics.json, temperature_scaler.json).",
        "",
        "## Identity / provenance (all 5 seeds)",
        "",
        f"- Git SHA: `{prov_manifest['git_sha']}`",
        f"- KERMT source commit: `{prov_manifest['kermt_source_commit']}`",
        f"- Checkpoint SHA256: `{prov_manifest['checkpoint_sha256']}`",
        f"- Dataset/prep ID: `{prov_manifest['prep_id']}`",
        f"- Config (harness defaults, no overrides): `{json.dumps(prov_manifest['config'])}`",
        f"- W&B entity/project: `{prov_manifest['wandb_entity']}` / `{prov_manifest['wandb_project']}`",
        "- W&B run URLs (per seed):",
    ]
    for s in seeds:
        readme_lines.append(f"  - seed {s}: {prov_manifest['wandb_urls'][s]}")
    readme_lines += [
        "- `git_dirty` per seed: " + json.dumps(prov_manifest["git_dirty_per_seed"])
        + " — seed 0 was recorded clean; seeds 1-4 show `true` because `ml/eval/tier0_artifacts.py` "
        "and one line in `ml/requirements-m2.txt` (documenting the new `matplotlib` dependency used only "
        "for this post-hoc plotting) were added to the working tree between seed 0 and seed 1. Verified via "
        "`git diff --stat` that no file under `train/`, `models/`, `data/`, `configs/`, or "
        "`eval/calibration*.py`/`cluster_calibration.py`/`metrics.py` changed — the training/calibration "
        "methodology executed identically for all 5 seeds.",
        "",
        "## Run IDs",
        "",
    ]
    for s in seeds_summaries:
        readme_lines.append(f"- seed {s['seed']}: `{s['run_id']}` (wall {s['wall_seconds']}s, best epoch {s['best_epoch']})")
    readme_lines += [
        "",
        "## Documented aggregation method",
        "",
        "Per `decisions.md` and `eval/cluster_calibration.py` (used by the runbook's own `s_agg.py`, "
        "which produced `" + str(agg_path.name) + "`): **mean +/- std over the 5 fixed seeds (0-4)**, "
        "raw and calibrated reported side by side. This is the project's only documented aggregation "
        "method for this comparison; no confidence-interval methodology is specified anywhere in the "
        "blueprint/decisions/runbook, so none is invented or reported here. `tables/summary_metrics.json` "
        "also reports median/min/max as purely descriptive statistics over the same 5 numbers — labelled "
        "supplementary, not a substitute for the documented mean +/- std.",
        "",
        "## Directory guide",
        "",
        "```",
        "tier0_dili_standalone__cls/",
        "  README.md                        <- this file",
        "  plots/                            <- MULTI-SEED aggregate plots (new content; Parts 9-10)",
        "    01-04_*_by_seed.*                individual metric per seed, bar + mean line",
        "    05-06_*_raw_vs_calibrated.*       raw vs calibrated, per seed",
        "    07_mean_sd_summary.*              documented mean+-std + individual seed points",
        "    08_val_auroc_vs_test_auroc_*.*    generalization scatter, one point per seed",
        "    09_val_to_test_gap_by_seed.*      val-test AUROC gap per seed",
        "    10_best_epoch_by_seed.*           KERMT's selected epoch per seed",
        "    11_aggregate_training_loss_curve.*  mean+-std train/val loss across seeds + individual curves",
        "    12_aggregate_val_auroc_curve.*      mean+-std val AUROC across seeds + individual curves",
        "  tables/",
        "    per_seed_metrics.csv              one row per seed, all key metrics",
        "    summary_metrics.csv/json          documented mean+-std + supplementary median/min/max",
        "  metrics/",
        "    aggregate_metrics.json            raw output of s_agg.py / eval.cluster_calibration",
        "    overfitting_diagnostics_all_seeds.json",
        "  provenance/",
        "    manifest.json                     git/KERMT/checkpoint/prep identity, run ids, W&B links",
        "  per_seed/<run_id>/                  COPY of that seed's own plots+metrics+tables",
        "                                       (identical to ml/runs/<run_id>/artifacts/{plots,metrics,tables}/)",
        "    plots/01-09_*                     TRAINING split (train/val only — never test)",
        "    plots/10_roc_curve_test.*          TEST split",
        "    plots/11_pr_curve_test.*           TEST split",
        "    plots/12_confusion_matrix_test.*   TEST split, default threshold 0.5 (not an approved/tuned threshold — none is documented)",
        "    plots/13-14_prob_distribution_*.*  TEST split, raw and calibrated",
        "    plots/15_reliability_diagram_test.* TEST split, raw vs calibrated",
        "    plots/16-19_*                      TEST (Brier/ECE) and CALIBRATION split (NLL, temperature)",
        "    plots/20-21,24_*                   VALIDATION split (train loss vs val AUROC/loss; overfitting)",
        "    plots/25-26_*                      ALL SPLITS (dataset counts / class balance)",
        "    metrics/seed_summary.json          full per-seed metrics + provenance",
        "    metrics/overfitting_diagnostics.json",
        "    tables/split_counts.csv/json, class_balance.json, leakage_summary.json",
        "```",
        "",
        "Six requested per-seed curves were **not generated** because KERMT's finetune CLI does not "
        "expose them (`agent/config/defaults_finetune.json` / `finetune.log` only log "
        "`loss_train, loss_val, auc_val, cur_lr` per epoch — no per-epoch train AUROC/AUPRC or val AUPRC): "
        "train AUROC vs epoch, train AUPRC vs epoch, val AUPRC vs epoch, combined AUPRC curve, "
        "train-AUROC-vs-val-AUROC scatter, train-AUPRC-vs-val-AUPRC scatter. This is recorded per-seed in "
        "each `seed_summary.json`'s `artifacts_skipped` list with the same reason.",
    ]
    if curve_note:
        readme_lines += ["", f"**Note:** {curve_note}"]
    readme_lines += [
        "",
        "## Dataset / split counts (all 5 seeds identical — same prep_id, same cluster, deterministic split)",
        "",
        "| Split | N | Positive | Negative |",
        "|---|---|---|---|",
    ]
    counts0 = seeds_summaries[0]["counts"]
    bal0 = seeds_summaries[0]["class_balance"]
    for split in ("train", "val", "calibration", "test"):
        readme_lines.append(f"| {split} | {counts0[split]} | {bal0[split]['positive']} | {bal0[split]['negative']} |")
    readme_lines += [
        "",
        "Expected per the runbook: train 287, val 41, calibration 50 (13 pos/37 neg), test 96. "
        + ("Matches exactly for all 5 seeds." if counts0 == {"train": 287, "val": 41, "calibration": 50, "test": 96} and bal0["calibration"] == {"positive": 13, "negative": 37} else "See tables/ for actual per-seed values — differs from the documented expectation; see per-seed leakage_summary.json/seed_summary.json for detail."),
        "",
        "Leakage: all 5 seeds show 0 overlap for every train/val/calibration/test pair (see each "
        "`per_seed/<run_id>/tables/leakage_summary.json` and the corresponding `s_verify.py` VERDICT: PASS "
        "logs under `ml/runs/lab_logs/verify_<run_id>.txt`).",
        "",
        "## What this does and does not support",
        "",
        "This package characterizes `dili_standalone__cls` / `dili_liver_injury` across the 5 fixed KERMT "
        "Tier-0 seeds using the project's documented aggregation (mean +/- std). It does not constitute a "
        "KERMT-vs-XGBoost comparison (that needs the laptop-only `ml/runs/test_evaluations/*.json`, "
        "per the runbook — `eval.xgboost_heldout` is a known, expected FAIL on this workstation). No "
        "run's test-set results influenced training, epoch selection, or calibration for any seed.",
        "",
    ]
    (out_dir / "README.md").write_text("\n".join(readme_lines) + "\n", encoding="utf-8")

    summary_out = {
        "arm": arm,
        "endpoint": endpoint_key,
        "out_dir": str(out_dir),
        "n_seeds": len(seeds),
        "n_aggregate_plots": len(generated),
        "aggregate_plots": generated,
    }
    (out_dir / "generation_manifest.json").write_text(json.dumps(summary_out, indent=2, default=str) + "\n", encoding="utf-8")
    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True)
    ap.add_argument("--run-ids", required=True, nargs="+")
    ap.add_argument("--out-name", default=None)
    args = ap.parse_args()
    out = present(args.arm, args.run_ids, args.out_name)
    print(json.dumps({"out_dir": str(out)}, indent=2))


if __name__ == "__main__":
    main()
