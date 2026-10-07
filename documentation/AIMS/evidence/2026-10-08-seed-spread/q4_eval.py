import sys, os, json, warnings, tempfile
import datetime as _dt, enum as _en
if not hasattr(_dt, "UTC"): _dt.UTC = _dt.timezone.utc
if not hasattr(_en, "StrEnum"):
    class _StrEnum(str, _en.Enum):
        def __str__(self): return str(self.value)
    _en.StrEnum = _StrEnum
import typing as _t
if not hasattr(_t, "Self"):
    _t.Self = object
warnings.filterwarnings("ignore")
REPO = os.path.expanduser("~/mnt/mars-admet")
sys.path[:0] = [f"{REPO}/ml", f"{REPO}/contracts"]
os.chdir(f"{REPO}/ml")
import numpy as np
from pathlib import Path
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score
from data.loaders import load_endpoint
from featurize.cache import FeatureCache
from serve.registry import ModelRegistry
from eval.applicability_domain import query_ad
from mars_contracts import TaskType

OUT = os.path.expanduser("~/scratch/out")
cache = FeatureCache(os.path.expanduser("~/scratch/featcache"))
reg = ModelRegistry(cache, artifacts_root=f"{REPO}/ml/artifacts")

def prep_dir_for(ep):
    j = json.load(open(f"{REPO}/ml/runs/test_evaluations/{ep}.json"))
    return Path(f"{REPO}/ml/data/processed/{j['prep_id']}")

def quartile_table(spread, err, k=4):
    qs = np.quantile(spread, np.linspace(0, 1, k + 1))
    rows = []
    for i in range(k):
        lo, hi = qs[i], qs[i + 1]
        m = (spread >= lo) & ((spread <= hi) if i == k - 1 else (spread < hi))
        rows.append(dict(q=i + 1, n=int(m.sum()), spread_med=float(np.median(spread[m])) if m.any() else None,
                         err_mean=float(np.mean(err[m])) if m.any() else None))
    return rows

def run(ep):
    data = load_endpoint(prep_dir_for(ep), ep)
    test = data.test
    smiles = test["standardized_smiles"].tolist()
    y = test["label"].to_numpy(dtype=float)
    models = reg.load_models(ep)
    P = np.array([m.predict(smiles) for m in models])  # seeds x n
    ok = ~np.isnan(P).any(axis=0)
    P, y, smiles = P[:, ok], y[ok], [s for s, o in zip(smiles, ok) if o]
    task = data.task_type
    res = dict(endpoint=ep, task=str(task), n_test=int(len(y)), n_seeds=int(P.shape[0]), dropped=int((~ok).sum()))
    # applicability domain
    adi = reg.load_ad_index(ep)
    ad = query_ad(adi, smiles) if adi is not None else None
    in_dom = np.array([a.in_domain for a in ad]) if ad else None
    res["frac_in_domain"] = float(in_dom.mean()) if in_dom is not None else None

    if task == TaskType.CLASSIFICATION:
        cal = reg.load_calibrator(ep)
        variants = {"raw": P}
        if cal is not None:
            variants["served(calibrated)"] = np.array([cal.transform(p) for p in P])
        res["variants"] = {}
        for name, Q in variants.items():
            mean, std = Q.mean(0), Q.std(0)
            wrong = ((mean >= 0.5).astype(float) != y).astype(float)
            absbrier = np.abs(mean - y)
            v = dict(
                auroc=float(roc_auc_score(y, mean)) if len(set(y)) > 1 else None,
                err_rate=float(wrong.mean()),
                std_median=float(np.median(std)), std_p90=float(np.quantile(std, .9)),
                spearman_std_vs_abserr=float(spearmanr(std, absbrier).correlation),
                auroc_std_predicts_misclass=(float(roc_auc_score(wrong, std)) if 0 < wrong.sum() < len(wrong) else None),
                frac_interval_outside_01=float(((mean - std < 0) | (mean + std > 1)).mean()),
                quartiles_abserr=quartile_table(std, absbrier),
                quartiles_misclass=quartile_table(std, wrong),
            )
            if in_dom is not None and (~in_dom).any() and in_dom.any():
                v["std_median_in_domain"] = float(np.median(std[in_dom]))
                v["std_median_out_domain"] = float(np.median(std[~in_dom]))
                v["abserr_in_domain"] = float(absbrier[in_dom].mean())
                v["abserr_out_domain"] = float(absbrier[~in_dom].mean())
            res["variants"][name] = v
    else:
        mean, std = P.mean(0), P.std(0)
        err = np.abs(y - mean)
        z = err / np.maximum(std, 1e-12)
        res.update(
            rmse=float(np.sqrt(np.mean((y - mean) ** 2))), mae=float(err.mean()),
            std_median=float(np.median(std)), std_p90=float(np.quantile(std, .9)),
            cover_1sigma=float(np.mean(err <= std)),          # what the UI draws/prints
            cover_196sigma=float(np.mean(err <= 1.96 * std)), # what a "95% CI" would claim
            median_abs_err_over_median_std=float(np.median(err) / np.median(std)),
            spearman_std_vs_abserr=float(spearmanr(std, err).correlation),
            quartiles_abserr=quartile_table(std, err),
        )
        if in_dom is not None and (~in_dom).any() and in_dom.any():
            res["std_median_in_domain"] = float(np.median(std[in_dom]))
            res["std_median_out_domain"] = float(np.median(std[~in_dom]))
            res["abserr_in_domain"] = float(err[in_dom].mean())
            res["abserr_out_domain"] = float(err[~in_dom].mean())
            res["cover_1sigma_in_domain"] = float(np.mean(err[in_dom] <= std[in_dom]))
            res["cover_1sigma_out_domain"] = float(np.mean(err[~in_dom] <= std[~in_dom]))
    json.dump(res, open(f"{OUT}/{ep}.json", "w"), indent=1)
    return res

if __name__ == "__main__":
    for ep in sys.argv[1:]:
        r = run(ep)
        print("DONE", ep, "n_test", r["n_test"], "in_domain", r["frac_in_domain"])

def per_seed_check(ep):
    """Recompute per-seed test metrics to compare against runs/test_evaluations (reproduction check)."""
    data = load_endpoint(prep_dir_for(ep), ep)
    smiles = data.test["standardized_smiles"].tolist(); y = data.test["label"].to_numpy(dtype=float)
    out = []
    for m in reg.load_models(ep):
        p = m.predict(smiles); ok = ~np.isnan(p)
        if data.task_type == TaskType.CLASSIFICATION:
            out.append(roc_auc_score(y[ok], p[ok]))
        else:
            out.append(float(np.mean(np.abs(y[ok]-p[ok]))))
    return float(np.mean(out))
