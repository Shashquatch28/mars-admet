"""
Post-hoc artifact/plot generation for one completed Tier-0 KERMT run.

Strictly read-only with respect to the run: everything here is reconstructed
from artifacts the harness already wrote (``finetune.log``, the
``predict_*/out/predictions.csv`` files, ``calibration_diagnostics.json``,
``temperature_scaler.json``, the processed-data cluster splits). No
retraining, no additional container/GPU inference calls, no test-set
influence on training/epoch-selection/calibration — this module only reads
and plots what the training run already produced.

Handles both single-endpoint arms (e.g. ``dili_standalone__cls``) and
multi-task subgroup arms (e.g. ``toxicity__cls`` = herg + ames): every
per-endpoint artifact (ROC/PR/confusion matrix/probability distributions/
reliability/Brier/ECE/NLL/temperature diagnostic/split counts/class balance)
is generated once per member endpoint. For a single-endpoint arm, filenames
are unprefixed (matches the original DILI convention exactly); for a
multi-endpoint arm, filenames are prefixed ``<endpoint>__``. Training-curve
plots (loss/AUROC vs epoch) are inherently whole-model, not per-endpoint —
KERMT's own ``finetune.log`` logs one joint ``auc_val`` across all targets in
a multi-task run, not a per-endpoint breakdown — and are labelled as such.

Calibrated test-set probabilities are recomputed on the host by applying the
run's own saved ``TemperatureScaler`` (eval/calibration.py) to
``logit(raw_prob)`` for the test-set raw predictions already on disk. This is
algebraically identical to what ``eval/cluster_calibration.py`` computed
during the run (see its ``test_metrics_calibrated``, which this script's
recomputed AUROC/AUPRC/Brier/ECE should reproduce as a self-check).

Usage:
    PYTHONPATH=. ../.venv/bin/python eval/tier0_artifacts.py --run-id <RUN_ID>
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import precision_recall_curve, roc_curve

from configs.clusters import all_subgroups
from data.cluster_loaders import SMILES_COL, load_cluster
from eval.calibration import TemperatureScaler
from eval.metrics import compute_metrics
from mars_contracts.endpoints import TaskType

RUNS_DIR = Path("runs")
DEFAULT_THRESHOLD = 0.5  # no project-specific operating threshold is documented anywhere in the
# repo (blueprint/decisions/runbook) or in eval/metrics.py; this is the conventional default for a
# calibrated binary probability, NOT a tuned or approved operating point. Labelled as such on every
# plot that uses it, per the explicit instruction not to invent an approved threshold.
EPS = 1e-6

EPOCH_LINE = re.compile(
    r"Epoch:\s*(\d+)\s+loss_train:\s*([\d.eE+-]+)\s+loss_val:\s*([\d.eE+-]+)\s+"
    r"auc_val:\s*([\d.eE+-]+)\s+cur_lr:\s*([\d.eE+-]+)\s+t_time:\s*([\d.eE+-]+)s\s+v_time:\s*([\d.eE+-]+)s"
)
BEST_EPOCH_LINE = re.compile(r"best validation auc\s*=\s*([\d.eE+-]+)\s+on epoch\s+(\d+)", re.IGNORECASE)


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), EPS, 1.0 - EPS)
    return np.log(p / (1.0 - p))


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", "..", *args], capture_output=True, text=True).stdout.strip()


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #


def parse_finetune_log(path: Path) -> tuple[list[dict], int | None, float | None]:
    """Per-epoch rows plus KERMT's own reported best epoch, if logged."""
    text = path.read_text(encoding="utf-8", errors="replace")
    rows = []
    for line in text.splitlines():
        m = EPOCH_LINE.search(line)
        if m:
            rows.append(
                {
                    "epoch": int(m.group(1)),
                    "loss_train": float(m.group(2)),
                    "loss_val": float(m.group(3)),
                    "auc_val": float(m.group(4)),
                    "lr": float(m.group(5)),
                    "t_time": float(m.group(6)),
                    "v_time": float(m.group(7)),
                }
            )
    best_epoch = None
    best_auc = None
    bm = BEST_EPOCH_LINE.search(text)
    if bm:
        best_auc = float(bm.group(1))
        best_epoch = int(bm.group(2))
    return rows, best_epoch, best_auc


def find_predict_dir(run_dir: Path, target_smiles: set[str]) -> Path:
    kermt_dir = run_dir / "artifacts" / "kermt"
    matches = []
    for c in sorted(kermt_dir.glob("predict_*")):
        smiles_csv = c / "input" / "smiles.csv"
        if not smiles_csv.exists():
            continue
        with smiles_csv.open(encoding="utf-8") as f:
            s = {row["smiles"] for row in csv.DictReader(f)}
        if s == target_smiles:
            matches.append(c)
    if not matches:
        raise RuntimeError(f"No predict_* dir under {kermt_dir} matches the requested {len(target_smiles)}-molecule split")
    if len(matches) > 1:
        raise RuntimeError(f"Ambiguous: {len(matches)} predict_* dirs match the same {len(target_smiles)}-molecule split")
    return matches[0]


def load_predictions(predict_dir: Path, target_name: str) -> dict[str, float]:
    """Map each INPUT smiles.csv molecule to its predicted value, joined by row
    POSITION rather than by matching the SMILES string in predictions.csv.

    KERMT's inference pipeline re-canonicalizes SMILES internally (verified:
    a cis/trans double-bond molecule came back with an equivalent but
    textually different \\/ representation), so the output CSV's own SMILES
    column is not always byte-identical to what was submitted. Row order is
    preserved (verified positionally against the input), so the input file's
    SMILES — the same strings MARS's own label dictionaries use — is the
    correct join key.
    """
    with (predict_dir / "input" / "smiles.csv").open(encoding="utf-8") as f:
        input_smiles = [row["smiles"] for row in csv.DictReader(f)]
    with (predict_dir / "out" / "predictions.csv").open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        output_rows = list(reader)
    if len(input_smiles) != len(output_rows):
        raise RuntimeError(
            f"{predict_dir}: input smiles.csv has {len(input_smiles)} rows but "
            f"predictions.csv has {len(output_rows)} — cannot safely join positionally"
        )
    return {s: float(row[target_name]) for s, row in zip(input_smiles, output_rows)}


def _read_multi_input_csv(path: Path, endpoints: list[str]) -> tuple[list[str], dict[str, dict[str, int]]]:
    """One shared multi-target CSV -> (all smiles in the split, {endpoint: {smiles: label}}).

    Missing labels are empty cells (KERMT's masked-multi-task convention); a
    single-endpoint arm's CSV has exactly one target column and every row
    labelled, so this degrades to the same behaviour as before.
    """
    all_smiles: list[str] = []
    per_ep: dict[str, dict[str, int]] = {ep: {} for ep in endpoints}
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            s = row["smiles"]
            all_smiles.append(s)
            for ep in endpoints:
                v = row.get(ep, "")
                if v not in ("", None):
                    per_ep[ep][s] = int(float(v))
    return all_smiles, per_ep


class RunBundle:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.run_dir = RUNS_DIR / run_id
        if not self.run_dir.exists():
            raise FileNotFoundError(self.run_dir)
        self.config = json.loads((self.run_dir / "config.json").read_text(encoding="utf-8"))
        self.run_meta = json.loads((self.run_dir / "run.json").read_text(encoding="utf-8"))
        self.provenance = json.loads((self.run_dir / "provenance.json").read_text(encoding="utf-8"))
        self.lab_summary = json.loads((self.run_dir / "lab_summary.json").read_text(encoding="utf-8"))
        self.lock = json.loads(Path("data/metadata/kermt_checkpoint.lock.json").read_text(encoding="utf-8"))

        self.subgroup_key = self.config["endpoint"]
        self.spec = all_subgroups()[self.subgroup_key]
        self.endpoint_keys = list(self.spec.endpoints)
        self.multi = len(self.endpoint_keys) > 1
        self.seed = self.config["seed"]
        self.prep_id = self.config["prep_id"]

        self.cd = load_cluster(Path("data/processed") / self.prep_id, self.endpoint_keys, cluster_key=self.subgroup_key)

        cal_rec_list = [
            json.loads(line)["metrics"]
            for line in (self.run_dir / "metrics.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.cal_record = {
            ep: next(r for r in cal_rec_list if r.get("split") == "calibration+test" and r["endpoint_key"] == ep)
            for ep in self.endpoint_keys
        }
        self.val_record = {
            ep: next(r for r in cal_rec_list if r.get("split") == "val" and r["endpoint"] == ep)
            for ep in self.endpoint_keys
        }

        self.calibration_diag: dict[str, dict] = {}
        self.temp_scaler: dict[str, TemperatureScaler] = {}
        for ep in self.endpoint_keys:
            diag_path = self.run_dir / "artifacts" / "calibration" / ep / "calibration_diagnostics.json"
            self.calibration_diag[ep] = json.loads(diag_path.read_text(encoding="utf-8"))
            self.temp_scaler[ep] = TemperatureScaler.load(
                self.run_dir / "artifacts" / "calibration" / ep / "temperature_scaler.json"
            )

        finetune_log = self.run_dir / "artifacts" / "kermt" / "logs" / "finetune.log"
        self.epoch_rows, self.kermt_best_epoch, self.kermt_best_auc = parse_finetune_log(finetune_log)

        # Splits (labels), from the same source s_verify.py trusts. One shared
        # train.csv/val.csv for the whole (possibly multi-task) model.
        train_path = self.run_dir / "artifacts" / "kermt" / "input" / "train.csv"
        val_path = self.run_dir / "artifacts" / "kermt" / "input" / "val.csv"
        self.train_all_smiles, self.train_labels = _read_multi_input_csv(train_path, self.endpoint_keys)
        self.val_all_smiles, self.val_labels = _read_multi_input_csv(val_path, self.endpoint_keys)

        self.test_labels: dict[str, dict[str, int]] = {}
        self.cal_labels: dict[str, dict[str, int]] = {}
        for ep in self.endpoint_keys:
            test_df = self.cd.endpoint_test_frame(ep)
            self.test_labels[ep] = dict(zip(test_df[SMILES_COL], test_df[ep].astype(int)))
            cal_df = self.cd.calibration[[SMILES_COL, ep]].dropna()
            self.cal_labels[ep] = dict(zip(cal_df[SMILES_COL], cal_df[ep].astype(int)))

        # Raw probabilities from the model's own on-disk predictions (no re-inference).
        # One predict_* dir covers the whole cluster test set (all endpoints' columns).
        test_predict_dir = find_predict_dir(self.run_dir, set(self.cd.smiles("test")))
        self.test_p_raw: dict[str, np.ndarray] = {}
        self.test_p_cal: dict[str, np.ndarray] = {}
        self.test_y: dict[str, np.ndarray] = {}
        self.test_smiles_sorted: dict[str, list[str]] = {}
        for ep in self.endpoint_keys:
            raw_by_smiles = load_predictions(test_predict_dir, ep)
            smiles_sorted = sorted(self.test_labels[ep])
            self.test_smiles_sorted[ep] = smiles_sorted
            y = np.array([self.test_labels[ep][s] for s in smiles_sorted], dtype=int)
            p_raw = np.array([raw_by_smiles[s] for s in smiles_sorted], dtype=float)
            self.test_y[ep] = y
            self.test_p_raw[ep] = p_raw
            self.test_p_cal[ep] = self.temp_scaler[ep].transform_logits(_logit(p_raw))

    def prefix(self, ep: str) -> str:
        return f"{ep}__" if self.multi else ""


# --------------------------------------------------------------------------- #
# Plot helpers
# --------------------------------------------------------------------------- #


def save_fig(fig: plt.Figure, out_dir: Path, stem: str, generated: list[dict], description: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / f"{stem}.png"
    pdf = out_dir / f"{stem}.pdf"
    fig.savefig(png, dpi=150, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")
    plt.close(fig)
    generated.append({"file_png": str(png), "file_pdf": str(pdf), "description": description})


def skip(reason: str, name: str, skipped: list[dict]) -> None:
    skipped.append({"artifact": name, "reason": reason})


def _reliability(probs: np.ndarray, y_true: np.ndarray, n_bins: int = 10):
    bins = np.linspace(0, 1, n_bins + 1)
    idx = np.clip(np.digitize(probs, bins) - 1, 0, n_bins - 1)
    conf, acc = [], []
    for b in range(n_bins):
        mask = idx == b
        if mask.sum() == 0:
            continue
        conf.append(float(probs[mask].mean()))
        acc.append(float(y_true[mask].mean()))
    return np.array(conf), np.array(acc)


# --------------------------------------------------------------------------- #
# Per-seed artifact generation
# --------------------------------------------------------------------------- #


def generate(run_id: str) -> dict:
    rb = RunBundle(run_id)
    plots_dir = rb.run_dir / "artifacts" / "plots"
    tables_dir = rb.run_dir / "artifacts" / "tables"
    metrics_dir = rb.run_dir / "artifacts" / "metrics"
    prov_dir = rb.run_dir / "artifacts" / "provenance"
    for d in (plots_dir, tables_dir, metrics_dir, prov_dir):
        d.mkdir(parents=True, exist_ok=True)

    generated: list[dict] = []
    skipped: list[dict] = []

    epochs = [r["epoch"] for r in rb.epoch_rows]
    loss_train = [r["loss_train"] for r in rb.epoch_rows]
    loss_val = [r["loss_val"] for r in rb.epoch_rows]
    auc_val = [r["auc_val"] for r in rb.epoch_rows]
    best_epoch = rb.kermt_best_epoch
    final_epoch = epochs[-1] if epochs else None
    joint_note = (
        f" (JOINT across all {len(rb.endpoint_keys)} targets: {', '.join(rb.endpoint_keys)} — "
        "KERMT's finetune CLI logs one auc_val per epoch for the whole multi-task model, not per-endpoint)"
        if rb.multi
        else ""
    )

    # ---- Part 4: training curves (whole-model; only ever joint in a multi-task run) ---- #

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(epochs, loss_train, color="#1f77b4")
    ax.set_xlabel("epoch")
    ax.set_ylabel("train loss")
    ax.set_title(f"{run_id}\nTraining loss vs epoch (train split, N={len(rb.train_all_smiles)}){joint_note}")
    if best_epoch is not None:
        ax.axvline(best_epoch, color="#d62728", linestyle="--", label=f"selected epoch ({best_epoch})")
        ax.legend()
    save_fig(fig, plots_dir, "01_train_loss_vs_epoch", generated, "Training loss per epoch (train split, whole model).")

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(epochs, loss_val, color="#ff7f0e")
    ax.set_xlabel("epoch")
    ax.set_ylabel("val loss")
    ax.set_title(f"{run_id}\nValidation loss vs epoch (val split, N={len(rb.val_all_smiles)}){joint_note}")
    if best_epoch is not None:
        ax.axvline(best_epoch, color="#d62728", linestyle="--", label=f"selected epoch ({best_epoch})")
        ax.legend()
    save_fig(fig, plots_dir, "02_val_loss_vs_epoch", generated, "Validation loss per epoch (val split, whole model).")

    skip("KERMT's finetune CLI logs only loss_train/loss_val/auc_val/cur_lr per epoch; no per-epoch train AUROC is exposed.", "03_train_auroc_vs_epoch", skipped)

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(epochs, auc_val, color="#2ca02c")
    ax.set_xlabel("epoch")
    ax.set_ylabel("val AUROC")
    ax.set_title(f"{run_id}\nValidation AUROC vs epoch (val split, N={len(rb.val_all_smiles)}){joint_note}")
    if best_epoch is not None:
        ax.axvline(best_epoch, color="#d62728", linestyle="--", label=f"selected epoch ({best_epoch}, AUROC={rb.kermt_best_auc:.4f})")
        ax.legend()
    save_fig(fig, plots_dir, "04_val_auroc_vs_epoch", generated, "Validation AUROC per epoch (val split, whole model). Best/selected epoch marked (from KERMT's own log line).")

    skip("No per-epoch train AUROC is exposed by KERMT's finetune CLI.", "05_train_auprc_vs_epoch", skipped)
    skip("No per-epoch AUPRC (train or val) is exposed by KERMT's finetune CLI; only auc_val is logged.", "06_val_auprc_vs_epoch", skipped)

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(epochs, loss_train, label="train loss", color="#1f77b4")
    ax.plot(epochs, loss_val, label="val loss", color="#ff7f0e")
    if best_epoch is not None:
        ax.axvline(best_epoch, color="#d62728", linestyle="--", label=f"selected epoch ({best_epoch})")
    ax.set_xlabel("epoch")
    ax.set_ylabel("loss")
    ax.set_title(f"{run_id}\nCombined loss curve (train vs val){joint_note}")
    ax.legend()
    save_fig(fig, plots_dir, "07_combined_loss_curve", generated, "Train and validation loss together, selected epoch marked.")

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(epochs, auc_val, label="val AUROC (only series KERMT exposes per epoch)", color="#2ca02c")
    if best_epoch is not None:
        ax.axvline(best_epoch, color="#d62728", linestyle="--", label=f"selected epoch ({best_epoch})")
    ax.set_xlabel("epoch")
    ax.set_ylabel("AUROC")
    ax.set_title(f"{run_id}\nCombined AUROC curve{joint_note}\n(train AUROC not exposed by KERMT's finetune CLI — val only)")
    ax.legend()
    save_fig(fig, plots_dir, "08_combined_auroc_curve", generated, "Val AUROC per epoch; train AUROC not available from KERMT's finetune log, so this is val-only.")

    skip("Neither train nor val per-epoch AUPRC is exposed by KERMT's finetune CLI.", "09_combined_auprc_curve", skipped)

    # ---- Part 5 + 6: per-endpoint final performance + overfitting diagnostics ---- #

    best_idx = epochs.index(best_epoch) if best_epoch in epochs else None
    final_val_auroc = auc_val[-1] if auc_val else None
    best_val_auroc = rb.kermt_best_auc
    final_train_loss = loss_train[-1] if loss_train else None
    best_train_loss = loss_train[best_idx] if best_idx is not None else None

    per_endpoint_summary: dict[str, dict] = {}

    for ep in rb.endpoint_keys:
        pfx = rb.prefix(ep)
        y, p_raw, p_cal = rb.test_y[ep], rb.test_p_raw[ep], rb.test_p_cal[ep]
        cal_record = rb.cal_record[ep]
        calibration_diag = rb.calibration_diag[ep]
        ep_label = f" — endpoint: {ep}" if rb.multi else ""

        fpr_r, tpr_r, _ = roc_curve(y, p_raw)
        fpr_c, tpr_c, _ = roc_curve(y, p_cal)
        auroc_raw = cal_record["test_metrics_raw"]["auroc"]
        auroc_cal = cal_record["test_metrics_calibrated"]["auroc"]
        fig, ax = plt.subplots(figsize=(5.5, 5.5))
        ax.plot(fpr_r, tpr_r, label=f"raw (AUROC={auroc_raw:.4f})", color="#1f77b4")
        ax.plot(fpr_c, tpr_c, label=f"calibrated (AUROC={auroc_cal:.4f})", color="#d62728", linestyle="--")
        ax.plot([0, 1], [0, 1], color="gray", linestyle=":", label="chance")
        ax.set_xlabel("False Positive Rate")
        ax.set_ylabel("True Positive Rate")
        ax.set_title(f"{run_id}{ep_label}\nROC curve — HELD-OUT TEST (N={len(y)})\nraw and calibrated curves coincide: temperature scaling is rank-preserving")
        ax.legend(loc="lower right")
        save_fig(fig, plots_dir, f"{pfx}10_roc_curve_test", generated, f"ROC curve on held-out test set for {ep}, raw vs temperature-calibrated (curves are identical by construction).")

        prec_r, rec_r, _ = precision_recall_curve(y, p_raw)
        prec_c, rec_c, _ = precision_recall_curve(y, p_cal)
        auprc_raw = cal_record["test_metrics_raw"]["auprc"]
        auprc_cal = cal_record["test_metrics_calibrated"]["auprc"]
        fig, ax = plt.subplots(figsize=(5.5, 5.5))
        ax.plot(rec_r, prec_r, label=f"raw (AUPRC={auprc_raw:.4f})", color="#1f77b4")
        ax.plot(rec_c, prec_c, label=f"calibrated (AUPRC={auprc_cal:.4f})", color="#d62728", linestyle="--")
        ax.axhline(float(y.mean()), color="gray", linestyle=":", label=f"prevalence baseline ({y.mean():.3f})")
        ax.set_xlabel("Recall")
        ax.set_ylabel("Precision")
        ax.set_title(f"{run_id}{ep_label}\nPrecision-Recall curve — HELD-OUT TEST (N={len(y)})\nraw and calibrated curves coincide: temperature scaling is rank-preserving")
        ax.legend(loc="lower left")
        save_fig(fig, plots_dir, f"{pfx}11_pr_curve_test", generated, f"Precision-recall curve on held-out test set for {ep}, raw vs calibrated (identical by construction).")

        pred_label = (p_raw >= DEFAULT_THRESHOLD).astype(int)
        tp = int(((pred_label == 1) & (y == 1)).sum())
        tn = int(((pred_label == 0) & (y == 0)).sum())
        fp = int(((pred_label == 1) & (y == 0)).sum())
        fn = int(((pred_label == 0) & (y == 1)).sum())
        cm = np.array([[tn, fp], [fn, tp]])
        fig, ax = plt.subplots(figsize=(5, 4.5))
        im = ax.imshow(cm, cmap="Blues")
        ax.set_xticks([0, 1], labels=["pred negative", "pred positive"])
        ax.set_yticks([0, 1], labels=["true negative", "true positive"])
        for i in range(2):
            for j in range(2):
                ax.text(j, i, str(cm[i, j]), ha="center", va="center", color="black", fontsize=14)
        ax.set_title(
            f"{run_id}{ep_label}\nConfusion matrix — HELD-OUT TEST (raw probabilities, N={len(y)})\n"
            f"threshold={DEFAULT_THRESHOLD} (default; no project-specific operating threshold is documented)"
        )
        fig.colorbar(im, ax=ax, fraction=0.046)
        save_fig(fig, plots_dir, f"{pfx}12_confusion_matrix_test", generated, f"Confusion matrix at default threshold {DEFAULT_THRESHOLD} (not a tuned/approved threshold) on held-out test for {ep}, raw probabilities.")

        fig, ax = plt.subplots(figsize=(6, 4))
        ax.hist(p_raw[y == 0], bins=15, alpha=0.6, label="true negative", color="#1f77b4", range=(0, 1))
        ax.hist(p_raw[y == 1], bins=15, alpha=0.6, label="true positive", color="#d62728", range=(0, 1))
        ax.set_xlabel("raw predicted probability")
        ax.set_ylabel("count")
        ax.set_title(f"{run_id}{ep_label}\nRaw predicted-probability distribution — HELD-OUT TEST (N={len(y)})")
        ax.legend()
        save_fig(fig, plots_dir, f"{pfx}13_prob_distribution_raw_test", generated, f"Raw predicted-probability histogram for {ep}, positive vs negative test molecules.")

        fig, ax = plt.subplots(figsize=(6, 4))
        ax.hist(p_cal[y == 0], bins=15, alpha=0.6, label="true negative", color="#1f77b4", range=(0, 1))
        ax.hist(p_cal[y == 1], bins=15, alpha=0.6, label="true positive", color="#d62728", range=(0, 1))
        ax.set_xlabel("calibrated predicted probability")
        ax.set_ylabel("count")
        ax.set_title(f"{run_id}{ep_label}\nCalibrated predicted-probability distribution — HELD-OUT TEST (N={len(y)})")
        ax.legend()
        save_fig(fig, plots_dir, f"{pfx}14_prob_distribution_calibrated_test", generated, f"Temperature-calibrated predicted-probability histogram for {ep}, positive vs negative test molecules.")

        conf_r, acc_r = _reliability(p_raw, y)
        conf_c, acc_c = _reliability(p_cal, y)
        ece_raw = cal_record["test_metrics_raw"]["ece"]
        ece_cal = cal_record["test_metrics_calibrated"]["ece"]
        fig, ax = plt.subplots(figsize=(5.5, 5.5))
        ax.plot([0, 1], [0, 1], color="gray", linestyle=":", label="perfect calibration")
        ax.plot(conf_r, acc_r, "o-", color="#1f77b4", label=f"raw (ECE={ece_raw:.4f})")
        ax.plot(conf_c, acc_c, "s-", color="#d62728", label=f"calibrated (ECE={ece_cal:.4f})")
        ax.set_xlabel("mean predicted probability (bin)")
        ax.set_ylabel("observed positive fraction (bin)")
        ax.set_title(f"{run_id}{ep_label}\nReliability diagram — HELD-OUT TEST (N={len(y)})")
        ax.legend(loc="upper left")
        save_fig(fig, plots_dir, f"{pfx}15_reliability_diagram_test", generated, f"Reliability diagram for {ep}, raw vs calibrated, held-out test set.")

        brier_raw = cal_record["test_metrics_raw"]["brier_score"]
        brier_cal = cal_record["test_metrics_calibrated"]["brier_score"]
        fig, ax = plt.subplots(figsize=(4, 4))
        ax.bar(["raw", "calibrated"], [brier_raw, brier_cal], color=["#1f77b4", "#d62728"])
        ax.set_ylabel("Brier score (lower is better)")
        ax.set_title(f"{run_id}{ep_label}\nBrier score — HELD-OUT TEST")
        for i, v in enumerate([brier_raw, brier_cal]):
            ax.text(i, v, f"{v:.4f}", ha="center", va="bottom")
        save_fig(fig, plots_dir, f"{pfx}16_brier_comparison_test", generated, f"Raw vs calibrated Brier score for {ep}, held-out test set.")

        fig, ax = plt.subplots(figsize=(4, 4))
        ax.bar(["raw", "calibrated"], [ece_raw, ece_cal], color=["#1f77b4", "#d62728"])
        ax.set_ylabel("ECE (lower is better)")
        ax.set_title(f"{run_id}{ep_label}\nECE — HELD-OUT TEST")
        for i, v in enumerate([ece_raw, ece_cal]):
            ax.text(i, v, f"{v:.4f}", ha="center", va="bottom")
        save_fig(fig, plots_dir, f"{pfx}17_ece_comparison_test", generated, f"Raw vs calibrated ECE for {ep}, held-out test set.")

        nll_before = calibration_diag["nll_before"]
        nll_after = calibration_diag["nll_after"]
        fig, ax = plt.subplots(figsize=(4, 4))
        ax.bar(["before scaling", "after scaling"], [nll_before, nll_after], color=["#1f77b4", "#d62728"])
        ax.set_ylabel("NLL (lower is better)")
        ax.set_title(f"{run_id}{ep_label}\nNLL before/after temperature scaling\nCALIBRATION split (N={calibration_diag['n_fit_samples']}) — NOT test")
        for i, v in enumerate([nll_before, nll_after]):
            ax.text(i, v, f"{v:.4f}", ha="center", va="bottom")
        save_fig(fig, plots_dir, f"{pfx}18_nll_comparison_calibration_split", generated, f"NLL before/after temperature fitting for {ep}, on the CALIBRATION split.")

        fig, ax = plt.subplots(figsize=(6, 4))
        ax.axis("off")
        lines = [
            f"Temperature (T): {calibration_diag['temperature']:.4f}",
            f"At search boundary: {calibration_diag['at_boundary']}",
            f"Optimizer success: {calibration_diag['optimizer_success']}",
            f"NLL before -> after (calibration split): {nll_before:.4f} -> {nll_after:.4f}  (improved={calibration_diag['nll_improved']})",
            f"ECE before -> after (calibration split): {calibration_diag['ece_before']:.4f} -> {calibration_diag['ece_after']:.4f}  (improved={calibration_diag['ece_improved']})",
            f"Calibration split: n={calibration_diag['n_fit_samples']}, positive={calibration_diag['n_positive']}, negative={calibration_diag['n_negative']}",
        ]
        ax.text(0.02, 0.9, f"{run_id}{ep_label}\nTemperature-scaling diagnostic", fontsize=11, fontweight="bold", va="top")
        ax.text(0.02, 0.72, "\n".join(lines), fontsize=10, va="top", family="monospace")
        save_fig(fig, plots_dir, f"{pfx}19_temperature_scaling_diagnostic", generated, f"Text panel for {ep}: temperature, boundary/optimizer status, NLL/ECE before-after on the calibration split.")

        val_metrics_ep = rb.val_record[ep]
        val_auroc_ep = val_metrics_ep.get("auroc")
        overfitting_diag = {
            "endpoint": ep,
            "best_epoch": best_epoch,
            "best_val_auroc_joint_whole_model": best_val_auroc,
            "final_val_auroc_joint_whole_model": final_val_auroc,
            "val_auroc_this_endpoint_at_selected_epoch": val_auroc_ep,
            "val_n_samples_this_endpoint": val_metrics_ep.get("n_samples"),
            "test_auroc_raw": auroc_raw,
            "val_to_test_auroc_gap_this_endpoint": (val_auroc_ep - auroc_raw) if val_auroc_ep is not None else None,
            "train_loss_at_best_epoch_whole_model": best_train_loss,
            "train_loss_at_final_epoch_whole_model": final_train_loss,
            "note": (
                "best_val_auroc/final_val_auroc are the WHOLE-MODEL joint AUROC KERMT logs per epoch "
                "(across all targets in this arm), not this endpoint's own AUROC -- KERMT's finetune "
                "CLI does not expose a per-target per-epoch curve in a multi-task run. "
                "val_auroc_this_endpoint_at_selected_epoch is this endpoint's own AUROC on its own "
                "validation subset, computed once after training (not per-epoch). This script does not "
                "auto-label the run 'overfit' or 'not overfit'."
                if rb.multi
                else "These are measured indicators only; this script does not auto-label the run "
                "'overfit' or 'not overfit'. KERMT does not expose per-epoch train AUROC/AUPRC or "
                "val AUPRC, so the corresponding train-vs-val comparisons are not available."
            ),
        }
        (metrics_dir / f"{pfx}overfitting_diagnostics.json").write_text(
            json.dumps(overfitting_diag, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        recomputed_raw = compute_metrics(y, p_raw, TaskType.CLASSIFICATION)
        recomputed_cal = compute_metrics(y, p_cal, TaskType.CLASSIFICATION)
        self_check = {
            "recomputed_test_metrics_raw": asdict(recomputed_raw),
            "recomputed_test_metrics_calibrated": asdict(recomputed_cal),
            "matches_run_own_test_metrics_raw": abs(recomputed_raw.auroc - auroc_raw) < 1e-6,
            "matches_run_own_test_metrics_calibrated": abs(recomputed_cal.auroc - auroc_cal) < 1e-6,
        }

        train_ep = rb.train_labels[ep]
        val_ep = rb.val_labels[ep]
        cal_ep = rb.cal_labels[ep]
        test_ep = rb.test_labels[ep]
        counts_ep = {"train": len(train_ep), "val": len(val_ep), "calibration": len(cal_ep), "test": len(test_ep)}
        balance_ep = {
            split: {
                "positive": int(sum(v for v in d.values() if v == 1)),
                "negative": int(sum(1 for v in d.values() if v == 0)),
            }
            for split, d in (("train", train_ep), ("val", val_ep), ("calibration", cal_ep), ("test", test_ep))
        }
        train_s, val_s, cal_s, test_s = set(train_ep), set(val_ep), set(cal_ep), set(test_ep)
        leakage_ep = {
            "train_test_overlap": len(train_s & test_s),
            "val_test_overlap": len(val_s & test_s),
            "train_calibration_overlap": len(train_s & cal_s),
            "val_calibration_overlap": len(val_s & cal_s),
            "train_val_overlap": len(train_s & val_s),
        }

        fig, ax = plt.subplots(figsize=(5.5, 4))
        ax.bar(list(counts_ep.keys()), list(counts_ep.values()), color="#1f77b4")
        for i, (k, v) in enumerate(counts_ep.items()):
            ax.text(i, v, str(v), ha="center", va="bottom")
        ax.set_ylabel("n molecules")
        ax.set_title(f"{run_id}{ep_label}\nSplit sizes (labelled rows for this endpoint)")
        save_fig(fig, plots_dir, f"{pfx}25_split_counts", generated, f"Train/validation/calibration/test labelled sample counts for {ep}.")

        fig, ax = plt.subplots(figsize=(6, 4))
        splits = list(balance_ep.keys())
        pos = [balance_ep[s]["positive"] for s in splits]
        neg = [balance_ep[s]["negative"] for s in splits]
        ax.bar(splits, neg, label="negative", color="#1f77b4")
        ax.bar(splits, pos, bottom=neg, label="positive", color="#d62728")
        for i, s in enumerate(splits):
            ax.text(i, neg[i] + pos[i], f"{pos[i]}/{neg[i]+pos[i]} pos", ha="center", va="bottom", fontsize=8)
        ax.set_ylabel("n molecules")
        ax.set_title(f"{run_id}{ep_label}\nClass balance per split")
        ax.legend()
        save_fig(fig, plots_dir, f"{pfx}26_class_balance", generated, f"Positive/negative class balance per split for {ep}.")

        (tables_dir / f"{pfx}split_counts.json").write_text(json.dumps(counts_ep, indent=2) + "\n", encoding="utf-8")
        (tables_dir / f"{pfx}class_balance.json").write_text(json.dumps(balance_ep, indent=2) + "\n", encoding="utf-8")
        (tables_dir / f"{pfx}leakage_summary.json").write_text(json.dumps(leakage_ep, indent=2) + "\n", encoding="utf-8")
        with (tables_dir / f"{pfx}split_counts.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["split", "n", "positive", "negative"])
            for s in ("train", "val", "calibration", "test"):
                w.writerow([s, counts_ep[s], balance_ep[s]["positive"], balance_ep[s]["negative"]])

        per_endpoint_summary[ep] = {
            "counts": counts_ep,
            "class_balance": balance_ep,
            "leakage": leakage_ep,
            "val_metrics": {k: val_metrics_ep[k] for k in ("auroc", "auprc", "brier_score", "ece", "n_samples", "n_positive") if k in val_metrics_ep},
            "calibration_metrics": calibration_diag,
            "test_metrics_raw": cal_record["test_metrics_raw"],
            "test_metrics_calibrated": cal_record["test_metrics_calibrated"],
            "overfitting_diagnostics": overfitting_diag,
            "self_check": self_check,
            "confusion_matrix_test_at_default_threshold": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        }

    # ---- Whole-model final-vs-best (joint AUROC, not per-endpoint) ---- #

    fig, ax = plt.subplots(figsize=(5, 4))
    labels = ["val AUROC\n(best epoch)", "val AUROC\n(final epoch)"]
    vals = [best_val_auroc, final_val_auroc]
    ax.bar(labels, vals, color=["#2ca02c", "#7f7f7f"])
    for i, v in enumerate(vals):
        ax.text(i, v, f"{v:.4f}", ha="center", va="bottom")
    ax.set_ylabel("AUROC")
    ax.set_title(f"{run_id}\nFinal-vs-best validation AUROC{joint_note}")
    save_fig(fig, plots_dir, "24_final_vs_best_val_metric", generated, "Comparison of the whole-model joint val AUROC at the selected (best) epoch vs the final epoch.")

    fig, ax = plt.subplots(figsize=(6, 4.5))
    sc = ax.scatter(loss_train, auc_val, c=epochs, cmap="viridis", s=25)
    if best_idx is not None:
        ax.scatter([loss_train[best_idx]], [auc_val[best_idx]], marker="*", s=250, color="#d62728", label=f"selected epoch ({best_epoch})", zorder=5)
    ax.set_xlabel("train loss")
    ax.set_ylabel("val AUROC (joint)")
    ax.set_title(f"{run_id}\nTrain loss vs validation AUROC, per epoch{joint_note}")
    fig.colorbar(sc, ax=ax, label="epoch")
    ax.legend()
    save_fig(fig, plots_dir, "20_train_loss_vs_val_auroc", generated, "Scatter of whole-model train loss vs joint val AUROC across epochs, selected epoch marked.")

    fig, ax = plt.subplots(figsize=(6, 4.5))
    sc = ax.scatter(loss_train, loss_val, c=epochs, cmap="viridis", s=25)
    if best_idx is not None:
        ax.scatter([loss_train[best_idx]], [loss_val[best_idx]], marker="*", s=250, color="#d62728", label=f"selected epoch ({best_epoch})", zorder=5)
    ax.set_xlabel("train loss")
    ax.set_ylabel("val loss")
    ax.set_title(f"{run_id}\nTrain loss vs validation loss, per epoch{joint_note}")
    fig.colorbar(sc, ax=ax, label="epoch")
    ax.legend()
    save_fig(fig, plots_dir, "21_train_loss_vs_val_loss", generated, "Scatter of whole-model train loss vs val loss across epochs, selected epoch marked.")

    skip("No per-epoch train AUROC is exposed by KERMT's finetune CLI.", "22_train_auroc_vs_val_auroc", skipped)
    skip("No per-epoch train or val AUPRC is exposed by KERMT's finetune CLI.", "23_train_auprc_vs_val_auprc", skipped)

    # ---- Consolidated per-seed manifest ---------------------------------- #

    seed_summary = {
        "run_id": rb.run_id,
        "seed": rb.seed,
        "endpoints": rb.endpoint_keys,
        "subgroup": rb.subgroup_key,
        "multi_task": rb.multi,
        "git_sha": rb.provenance.get("git", {}).get("commit"),
        "git_dirty": rb.provenance.get("git", {}).get("dirty"),
        "kermt_source_commit": rb.lock["model"]["source_code_commit"],
        "checkpoint_sha256": rb.lock["files"]["kermt_contrastive_v2.0.pt"]["sha256"],
        "prep_id": rb.prep_id,
        "config": rb.config,
        "wandb_url": rb.lab_summary.get("wandb_url"),
        "wandb_entity": "shashquatch",
        "wandb_project": "mars-admet",
        "wall_seconds": rb.lab_summary.get("wall_seconds"),
        "n_epochs": len(epochs),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "best_epoch": best_epoch,
        "best_val_auroc_joint_whole_model": best_val_auroc,
        "final_val_auroc_joint_whole_model": final_val_auroc,
        "per_endpoint": per_endpoint_summary,
        "default_threshold_used_for_confusion_matrix": DEFAULT_THRESHOLD,
        "artifacts_generated": generated,
        "artifacts_skipped": skipped,
    }
    if not rb.multi:
        ep = rb.endpoint_keys[0]
        seed_summary["endpoint"] = ep
        seed_summary["counts"] = per_endpoint_summary[ep]["counts"]
        seed_summary["class_balance"] = per_endpoint_summary[ep]["class_balance"]
        seed_summary["leakage"] = per_endpoint_summary[ep]["leakage"]
        seed_summary["val_metrics"] = per_endpoint_summary[ep]["val_metrics"]
        seed_summary["calibration_metrics"] = per_endpoint_summary[ep]["calibration_metrics"]
        seed_summary["test_metrics_raw"] = per_endpoint_summary[ep]["test_metrics_raw"]
        seed_summary["test_metrics_calibrated"] = per_endpoint_summary[ep]["test_metrics_calibrated"]
        seed_summary["overfitting_diagnostics"] = per_endpoint_summary[ep]["overfitting_diagnostics"]
        seed_summary["self_check"] = per_endpoint_summary[ep]["self_check"]
        seed_summary["confusion_matrix_test_at_default_threshold"] = per_endpoint_summary[ep]["confusion_matrix_test_at_default_threshold"]
        seed_summary["best_val_auroc"] = best_val_auroc
        seed_summary["final_val_auroc"] = final_val_auroc

    (metrics_dir / "seed_summary.json").write_text(json.dumps(seed_summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")

    prov_manifest = {
        "run_id": rb.run_id,
        "seed": rb.seed,
        "endpoints": rb.endpoint_keys,
        "git_sha": seed_summary["git_sha"],
        "git_dirty": seed_summary["git_dirty"],
        "kermt_source_commit": seed_summary["kermt_source_commit"],
        "checkpoint_sha256": seed_summary["checkpoint_sha256"],
        "prep_id": rb.prep_id,
        "config": rb.config,
        "wandb_url": seed_summary["wandb_url"],
        "generated_at_utc": seed_summary["generated_at_utc"],
        "generator": "ml/eval/tier0_artifacts.py",
    }
    (prov_dir / "manifest.json").write_text(json.dumps(prov_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return seed_summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args()
    summary = generate(args.run_id)
    print(json.dumps({"run_id": summary["run_id"], "n_plots": len(summary["artifacts_generated"]), "n_skipped": len(summary["artifacts_skipped"])}, indent=2))


if __name__ == "__main__":
    main()
