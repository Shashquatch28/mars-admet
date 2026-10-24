"""
Module 11 section 4: MARS beside the TDC ADMET leaderboard, on the twelve endpoints where it is possible.

Inputs, all on disk
-------------------
* ``documentation/status/tdc_leaderboard_reference.json`` - leaderboard values read from the public
  TDC pages on a stated date (``tdc_comparison.py`` explains why values are recorded, never hard-coded
  or fetched live). It holds the top entry of each page and the entries the blueprint names
  (CaliciBoost, MapLight, MapLight + GNN).
* ``documentation/status/evaluation_results.json`` - MARS XGBoost, five seeds, test split.
* the KERMT Tier-0 records in git, for the endpoints the routing table sends to KERMT.

What the comparison does and does not mean
------------------------------------------
Only the twelve datasets whose MARS split adopted TDC's benchmark split are shown
(``split_method == "adopt_benchmark"``). hERG and PPB are listed as not comparable, with the reason.
Even for these twelve:

* MARS removes duplicates and re-standardizes, so its test set can be a few molecules smaller than
  TDC's; the table shows the sizes.
* MARS ran no hyperparameter search (``self_audit.md``); leaderboard entries range from stock to heavily
  tuned and some use extra data or pretraining.
* DILI was trained on the DILIst-augmented pool (979 molecules against TDC's 475): not like-for-like.
* The leaderboard std is seed-to-seed training noise on one fixed test set, as MARS's is.
* A leaderboard page has no audit status. Only the entries the blueprint names are treated as
  audited, and that audit could not be located (see the reference file).
* No row says MARS is above or below the leaderboard. The table gives values; there is no rank,
  no "beats" and no shaded cell.

Usage (from ``ml/``)
    PYTHONPATH=. python eval/tdc_leaderboard_table.py --prep-root <.../processed> --artifacts-root <.../artifacts> \\
        --cache-root <.../cache>
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import numpy as np

ML_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_ROOT.parent
STATUS = REPO_ROOT / "documentation" / "status"
DEFAULT_PREP_ID = "20260830T200000Z"


def _fmt(pair, digits: int = 3) -> str:
    mean, std = pair
    if std is None or not np.isfinite(std):
        return f"{mean:.{digits}f}"
    return f"{mean:.{digits}f} ± {std:.{digits}f}"


def mars_value(metric: str, ev: dict) -> tuple[float, float] | None:
    """MARS XGBoost (mean, std over seeds) in the leaderboard's metric, from evaluation_results.json."""
    if metric in ("MAE", "AUROC") and ev["metric"] == metric:
        return ev["seed_mean"], ev["seed_std"]
    if metric == "AUPRC" and "AUPRC" in ev.get("secondary", {}):
        m, s = ev["secondary"]["AUPRC"]
        return m, s
    return None


def kermt_auprc(results_dir: Path) -> dict[str, tuple[float, float | None]]:
    """endpoint -> (AUPRC mean, std) from the KERMT Tier-0 classification records in git."""
    from eval import tier0_classification

    out: dict[str, tuple[float, float | None]] = {}
    for arm in sorted(p.name for p in results_dir.iterdir() if p.is_dir() and p.name.endswith("__cls")):
        try:
            for endpoint, _n, raw in tier0_classification.load_arm(results_dir, arm):
                out[endpoint] = (raw["auprc_mean"], raw.get("auprc_std"))
        except (ValueError, KeyError, FileNotFoundError):
            continue
    return out


def spearman_per_seed(endpoint: str, prep_dir: Path, artifacts_root: Path, cache_root: Path) -> tuple[float, float]:
    from configs.experiment_config import FIXED_SEEDS
    from data.loaders import load_endpoint
    from featurize.cache import FeatureCache
    from models.xgboost_model import XGBoostModel
    from scipy.stats import spearmanr

    data = load_endpoint(prep_dir, endpoint)
    smiles = data.test["standardized_smiles"].tolist()
    y = data.test["label"].astype(float).to_numpy()
    cache = FeatureCache(cache_root)
    values = []
    for seed in FIXED_SEEDS:
        model = XGBoostModel.load_with_cache(artifacts_root / endpoint / f"seed_{seed}", cache)
        pred = np.asarray(model.predict(smiles), dtype=float)
        ok = ~np.isnan(pred)
        values.append(float(spearmanr(y[ok], pred[ok]).statistic))
    arr = np.array(values)
    return float(arr.mean()), float(arr.std(ddof=1))


def render_markdown(rows: list[dict], reference: dict, *, today: str) -> str:
    lines = [
        "# MARS beside the TDC ADMET leaderboard (Module 11 section 4)",
        "",
        f"Generated {today} by `ml/eval/tdc_leaderboard_table.py`. Leaderboard values were read from the public "
        f"TDC pages on {reference['accessed']} (`tdc_leaderboard_reference.json`). MARS values are the "
        "production XGBoost, five seeds, test split, raw scores, no hyperparameter search.",
        "",
        "**This table gives values. It does not say MARS is above or below the leaderboard**, and it should not be "
        "quoted that way: read the caveats below first.",
        "",
        "| endpoint | TDC dataset | metric | MARS XGBoost | MARS served (KERMT-routed only) | MapLight | MapLight + GNN | CaliciBoost | top entry on the page (unaudited) | MARS n_test / TDC size |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        named = r["ref"]["named"]
        top = r["ref"]["top"]
        cali = _fmt(named["CaliciBoost"][:2]) if "CaliciBoost" in named else "not listed"
        ml = _fmt(named["MapLight"][:2]) if "MapLight" in named else "not listed"
        mg = _fmt(named["MapLight + GNN"][:2]) if "MapLight + GNN" in named else "not listed"
        lines.append(
            f"| {r['endpoint']} | {r['ref']['tdc_dataset']} | {r['ref']['metric']} | {_fmt(r['mars'])} | "
            f"{r['served']} | {ml} | {mg} | {cali} | {top[0]} {_fmt(top[1:3])} | {r['n_test']} / {r['ref']['tdc_size']} |"
        )
    lines += [
        "",
        "Not compared:",
        "",
    ]
    for k, why in reference["not_comparable"].items():
        lines.append(f"- `{k}`: {why}")
    lines += [
        "",
        "## Caveats that apply to every row",
        "",
        "- **Audit status.** " + reference["audit_status"],
        "- **Page notes.** " + reference["page_notes"],
        "- **Test sets.** MARS adopts TDC's benchmark split, then removes duplicates and re-standardizes, so its "
        "test set can differ from TDC's by a few molecules; the last column shows MARS's `n_test` and the size TDC "
        "prints for the whole dataset (not its test set).",
        "- **Tuning.** MARS ran no hyperparameter search (`self_audit.md`). Leaderboard entries range from stock "
        "settings to heavy tuning, pretraining and external data.",
        "- **DILI.** MARS trained on the DILIst-augmented pool (979 molecules, against TDC's 475). The number is not "
        "like-for-like.",
        "- **Metric for clearance.** TDC scores `Clearance_Microsome_AZ` by Spearman; MARS reports MAE everywhere else. "
        "The Spearman here is computed from the same five XGBoost seed models. The KERMT clearance arm has MAE only "
        "in the records in git, so no KERMT value appears in that row.",
        "- **Spread.** Both stds are seed-to-seed training noise on one fixed test set; neither includes test-set "
        "sampling noise (`evaluation_results.md` has bootstrap intervals for that).",
        "- **Routing selection.** The served KERMT numbers belong to endpoints the routing rule chose because KERMT "
        "scored higher on these same test records.",
        "- **Leaderboards move.** The pages show no date. Re-read them before quoting any value.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--prep-id", default=DEFAULT_PREP_ID)
    p.add_argument("--prep-root", default=str(ML_ROOT / "data" / "processed"))
    p.add_argument("--artifacts-root", default=str(ML_ROOT / "artifacts"))
    p.add_argument("--cache-root", default=str(ML_ROOT / "data" / "cache"))
    p.add_argument("--reference", default=str(STATUS / "tdc_leaderboard_reference.json"))
    p.add_argument("--results", default=str(STATUS / "evaluation_results.json"))
    p.add_argument("--results-dir", default=str(STATUS / "kermt_tier0_results"))
    p.add_argument("--out", default=str(STATUS / "tdc_leaderboard_comparison.md"))
    args = p.parse_args(argv)

    from eval.evaluation_results import ROUTING, _kermt_primary

    reference = json.loads(Path(args.reference).read_text(encoding="utf-8"))
    results = json.loads(Path(args.results).read_text(encoding="utf-8"))["endpoints"]
    routing = json.loads(ROUTING.read_text(encoding="utf-8"))
    kermt = _kermt_primary(Path(args.results_dir))
    kermt_pr = kermt_auprc(Path(args.results_dir))
    prep_dir = Path(args.prep_root) / args.prep_id

    rows = []
    for endpoint, ref in reference["endpoints"].items():
        ev = results[endpoint]
        metric = ref["metric"]
        if metric == "Spearman":
            mars = spearman_per_seed(endpoint, prep_dir, Path(args.artifacts_root), Path(args.cache_root))
        else:
            mars = mars_value(metric, ev)
            if mars is None:
                raise SystemExit(f"{endpoint}: no MARS value for metric {metric}")
        served = "-"
        if routing["endpoints"].get(endpoint, {}).get("model") == "kermt" and endpoint in kermt:
            k_metric, k_mean, k_std, _ = kermt[endpoint]
            if k_metric == metric:
                served = _fmt((k_mean, k_std))
            elif metric == "AUPRC" and endpoint in kermt_pr:
                served = _fmt(kermt_pr[endpoint])
            else:
                served = f"KERMT-routed; {k_metric} only in the records"
        rows.append({"endpoint": endpoint, "ref": ref, "mars": mars, "served": served, "n_test": ev["n_test"]})

    text = render_markdown(rows, reference, today=date.today().isoformat())
    Path(args.out).write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {args.out} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
