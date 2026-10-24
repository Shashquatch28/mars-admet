"""
Module 11 section 6, last bullet: calibration method on the XGBoost classifiers.

Question
--------
The served scores are raw ensemble means (C0). The Platt calibrators fitted earlier were worse than
raw on Brier for 9 of 9 endpoints and on ECE for 8 of 9 (``xgboost_c0_raw_vs_calibrated.md``). That
used one method. Module 11 asks for the three common ones side by side: Platt scaling, temperature
scaling and isotonic regression.

What is compared
----------------
For each of the nine classification endpoints and each of the five promoted seed models:

* ``raw``         the model's probability as it comes out.
* ``Platt``       ``fit_platt_calibrator`` (the MARS definition: a logistic fit on the *probability*).
* ``temperature`` ``fit_temperature_scaler`` on the logit of the probability (clipped to [1e-6, 1-1e-6]).
* ``isotonic``    ``sklearn.isotonic.IsotonicRegression`` fitted on the calibration split, clipped to [0, 1].

Each calibrator is fitted on that seed's predictions for the calibration split only, then scored on
the untouched test split. The same three are also fitted on the five-seed *mean* of the calibration
split and scored on the five-seed mean of the test split, because the mean is what is served.
Brier score, ECE (10 equal-width bins) and AUROC are reported; AUROC is unchanged by a monotone map
(Platt, temperature) and can change under isotonic regression, which makes ties.

What it does and does not show
------------------------------
* The calibration split is small and not label-representative (the known C1 caveat): AMES 580, but
  HIA 47 with one negative, DILI 112. Isotonic regression with a few dozen points is a step function
  that memorises them; the table prints the size and the number of positives so the reader can see it.
* An endpoint whose calibration split has one class cannot be fitted by Platt or temperature; it is
  marked and skipped, never filled in.
* Nothing here is tuned on the test split. A lower Brier or ECE than raw is a number on this one test
  set; it is not a ranking of methods and not a claim that any of them makes the score a probability.

Usage (from ``ml/``)
    PYTHONPATH=. python eval/calibration_ablation.py --prep-root <.../processed> \\
        --artifacts-root <.../artifacts> --cache-root <scratch>
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np

from eval.calibration import fit_platt_calibrator, fit_temperature_scaler
from eval.metrics import compute_classification_metrics

DEFAULT_PREP_ID = "20260830T200000Z"
ML_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_ROOT.parent
METHODS = ("raw", "Platt", "temperature", "isotonic")
EPS = 1e-6


@dataclass
class Scores:
    """Brier, ECE and AUROC on the test split for each method; None where the method could not be fitted."""

    brier: dict[str, float | None] = field(default_factory=dict)
    ece: dict[str, float | None] = field(default_factory=dict)
    auroc: dict[str, float | None] = field(default_factory=dict)
    skipped: str | None = None


@dataclass
class EndpointAblation:
    endpoint: str
    n_cal: int
    n_cal_pos: int
    n_test: int
    per_seed: list[Scores]
    ensemble: Scores


def logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def calibrated_scores(p_cal: np.ndarray, y_cal: np.ndarray, p_test: np.ndarray) -> tuple[dict[str, np.ndarray], str | None]:
    """Fit each calibrator on (p_cal, y_cal) and return the test-split scores each method gives.

    Returns the methods that could be fitted and, if the calibration split has a single class, the reason
    nothing but ``raw`` is available.
    """
    from sklearn.isotonic import IsotonicRegression

    out: dict[str, np.ndarray] = {"raw": np.asarray(p_test, dtype=float)}
    y_cal = np.asarray(y_cal, dtype=int)
    if len(np.unique(y_cal)) < 2:
        return out, "calibration split has one class"
    out["Platt"] = fit_platt_calibrator(p_cal, y_cal).transform(p_test)
    scaler = fit_temperature_scaler(logit(p_cal), y_cal)
    out["temperature"] = scaler.transform_logits(logit(p_test))
    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(np.asarray(p_cal, dtype=float), y_cal)
    out["isotonic"] = np.clip(iso.predict(np.asarray(p_test, dtype=float)), 0.0, 1.0)
    return out, None


def score_methods(p_cal: np.ndarray, y_cal: np.ndarray, p_test: np.ndarray, y_test: np.ndarray) -> Scores:
    probs, skipped = calibrated_scores(p_cal, y_cal, p_test)
    s = Scores(skipped=skipped)
    for name in METHODS:
        if name not in probs:
            s.brier[name] = s.ece[name] = s.auroc[name] = None
            continue
        m = compute_classification_metrics(y_test, np.clip(probs[name], 0.0, 1.0))
        s.brier[name], s.ece[name], s.auroc[name] = m.brier_score, m.ece, m.auroc
    return s


def summarise(per_seed: list[Scores], key: str, method: str) -> tuple[float, float] | None:
    values = [getattr(s, key)[method] for s in per_seed if getattr(s, key).get(method) is not None]
    if len(values) < len(per_seed):
        return None
    arr = np.array(values, dtype=float)
    return float(arr.mean()), float(arr.std(ddof=1)) if len(arr) > 1 else float("nan")


def _cell(pair: tuple[float, float] | None, digits: int = 3) -> str:
    if pair is None:
        return "not fitted"
    return f"{pair[0]:.{digits}f} ± {pair[1]:.{digits}f}"


def render_markdown(results: list[EndpointAblation], *, today: str, prep_id: str) -> str:
    lines = [
        "# Calibration method on the XGBoost classifiers (Module 11 section 6)",
        "",
        f"Generated {today} by `ml/eval/calibration_ablation.py` on snapshot `{prep_id}`. Each calibrator is fitted "
        "on a seed model's predictions for the calibration split and scored on the untouched test split; mean ± "
        "sample std over the five seeds. Lower Brier and lower ECE are the metrics' own convention. **This is a "
        "table of numbers on one test set, not a ranking of methods**, and no method turns a score into a "
        "validated probability.",
        "",
    ]
    for key, title in (("brier", "Brier score"), ("ece", "ECE (10 equal-width bins)"), ("auroc", "AUROC")):
        lines += [
            f"## {title}, per-seed models",
            "",
            "| endpoint | calibration n (positives) | raw | Platt | temperature | isotonic |",
            "|---|---|---|---|---|---|",
        ]
        for r in results:
            cells = " | ".join(_cell(summarise(r.per_seed, key, m)) for m in METHODS)
            lines.append(f"| {r.endpoint} | {r.n_cal} ({r.n_cal_pos}) | {cells} |")
        lines.append("")
    lines += [
        "## The served score: five-seed mean, calibrator fitted on the mean",
        "",
        "| endpoint | Brier raw | Platt | temperature | isotonic | ECE raw | Platt | temperature | isotonic |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    def one(v: float | None) -> str:
        return "not fitted" if v is None else f"{v:.3f}"

    for r in results:
        b, e = r.ensemble.brier, r.ensemble.ece
        lines.append(f"| {r.endpoint} | " + " | ".join(one(b[m]) for m in METHODS) + " | " + " | ".join(one(e[m]) for m in METHODS) + " |")
    n = len(results)
    lines += ["", "Counts on the served-score table (how many of the " + str(n) + " endpoints show a value lower than raw):", ""]
    for metric, label in (("brier", "Brier"), ("ece", "ECE")):
        parts = []
        for m in METHODS[1:]:
            lower = sum(1 for r in results if getattr(r.ensemble, metric)[m] is not None
                        and getattr(r.ensemble, metric)[m] < getattr(r.ensemble, metric)["raw"])
            parts.append(f"{m} {lower}")
        lines.append(f"- {label}: " + ", ".join(parts) + ".")
    lines += [
        "",
        "## Reading it, and what it does not show",
        "",
        "- **Calibration sets are small.** The counts in the first column are the whole calibration split. Isotonic "
        "regression on a few dozen molecules is a step function that follows them, so a low calibration-split "
        "error there says nothing about the test split. Where a calibration split has very few molecules of one "
        "class (HIA's has a single negative), every method is fitted on almost no information about that class.",
        "- **Platt here is a fit on the probability, not the logit.** That is the MARS definition "
        "(`eval/calibration.py`); the usual textbook form is a fit on the score before the sigmoid. Temperature "
        "scaling is the logit form.",
        "- **The calibration split is not label-representative** (the C1 caveat in `SHIP_CHECKLIST.md` D2 and "
        "`xgboost_c0_raw_vs_calibrated.md`): its positive rate can differ from the test set's, and any monotone "
        "map learned there inherits that shift.",
        "- **One test set.** Differences of a few thousandths are inside the noise of 96 to 2,600 test molecules; "
        "see the bootstrap intervals in `evaluation_results.md` for how wide that is.",
        "- **Not covered:** KERMT (it has its own temperature scalers, `kermt_tier0_results`, and no per-molecule "
        "test predictions in git), and regression endpoints (nothing to calibrate).",
        "",
    ]
    return "\n".join(lines)


def load_results(path: Path) -> tuple[list[EndpointAblation], str]:
    """Rebuild the results from the JSON this module writes, so wording can change without a re-run."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    def scores(d: dict) -> Scores:
        return Scores(brier=d["brier"], ece=d["ece"], auroc=d["auroc"], skipped=d.get("skipped"))

    out = [
        EndpointAblation(
            ep, v["n_cal"], v["n_cal_pos"], v["n_test"], [scores(s) for s in v["per_seed"]], scores(v["ensemble"])
        )
        for ep, v in data["endpoints"].items()
    ]
    return out, data["prep_id"]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--render-only", action="store_true", help="Re-render the report from --out-json without re-running.")
    p.add_argument("--prep-id", default=DEFAULT_PREP_ID)
    p.add_argument("--prep-root", default=str(ML_ROOT / "data" / "processed"))
    p.add_argument("--artifacts-root", default=str(ML_ROOT / "artifacts"))
    p.add_argument("--cache-root", default=str(ML_ROOT / "data" / "cache"))
    p.add_argument("--out-md", default=str(REPO_ROOT / "documentation" / "status" / "calibration_ablation.md"))
    p.add_argument("--out-json", default=str(REPO_ROOT / "documentation" / "status" / "calibration_ablation.json"))
    args = p.parse_args(argv)

    if args.render_only:
        results, prep_id = load_results(Path(args.out_json))
        Path(args.out_md).write_text(
            render_markdown(results, today=date.today().isoformat(), prep_id=prep_id), encoding="utf-8", newline="\n"
        )
        print(f"re-rendered {args.out_md}")
        return 0

    from configs.experiment_config import FIXED_SEEDS
    from data.loaders import load_endpoint
    from featurize.cache import FeatureCache
    from mars_contracts.endpoints import ML_ENDPOINTS
    from models.xgboost_model import XGBoostModel

    prep_dir = Path(args.prep_root) / args.prep_id
    cache = FeatureCache(Path(args.cache_root))
    results: list[EndpointAblation] = []
    for ep in ML_ENDPOINTS:
        key = ep.value
        data = load_endpoint(prep_dir, key, use_augmented_dili=(key == "dili_liver_injury"))
        if data.task_type.value != "classification":
            continue
        cal_s = data.calibration["standardized_smiles"].tolist()
        y_cal = data.calibration["label"].astype(float).to_numpy()
        te_s = data.test["standardized_smiles"].tolist()
        y_te = data.test["label"].astype(float).to_numpy()
        cal_preds, te_preds = [], []
        for seed in FIXED_SEEDS:
            model = XGBoostModel.load_with_cache(Path(args.artifacts_root) / key / f"seed_{seed}", cache)
            cal_preds.append(np.asarray(model.predict(cal_s), dtype=float))
            te_preds.append(np.asarray(model.predict(te_s), dtype=float))
        ok_cal = ~np.isnan(np.vstack(cal_preds)).any(axis=0)
        ok_te = ~np.isnan(np.vstack(te_preds)).any(axis=0)
        yc, yt = y_cal[ok_cal], y_te[ok_te]
        per_seed = [score_methods(c[ok_cal], yc, t[ok_te], yt) for c, t in zip(cal_preds, te_preds, strict=True)]
        ens = score_methods(np.mean(cal_preds, axis=0)[ok_cal], yc, np.mean(te_preds, axis=0)[ok_te], yt)
        results.append(EndpointAblation(key, int(ok_cal.sum()), int(yc.sum()), int(ok_te.sum()), per_seed, ens))
        b = ens.brier
        print(f"{key:22s} n_cal={int(ok_cal.sum()):4d}({int(yc.sum())}) ens Brier "
              + " ".join(f"{m}={'-' if b[m] is None else format(b[m], '.3f')}" for m in METHODS), flush=True)

    text = render_markdown(results, today=date.today().isoformat(), prep_id=args.prep_id)
    Path(args.out_md).write_text(text, encoding="utf-8", newline="\n")
    Path(args.out_json).write_text(
        json.dumps(
            {
                "prep_id": args.prep_id,
                "endpoints": {
                    r.endpoint: {
                        "n_cal": r.n_cal,
                        "n_cal_pos": r.n_cal_pos,
                        "n_test": r.n_test,
                        "per_seed": [
                            {"brier": s.brier, "ece": s.ece, "auroc": s.auroc, "skipped": s.skipped} for s in r.per_seed
                        ],
                        "ensemble": {
                            "brier": r.ensemble.brier,
                            "ece": r.ensemble.ece,
                            "auroc": r.ensemble.auroc,
                            "skipped": r.ensemble.skipped,
                        },
                    }
                    for r in results
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {args.out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
