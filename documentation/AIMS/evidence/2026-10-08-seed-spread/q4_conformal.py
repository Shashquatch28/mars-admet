import sys, os, json, math
src = open(os.path.expanduser("~/scratch/q4_eval.py")).read().split("if __name__")[0]
exec(src)
from data.split import five_seed_train_val_folds

def regression_conformal(ep):
    data = load_endpoint(prep_dir_for(ep), ep)
    tv, te = data.train_val, data.test
    lab = dict(zip(tv["standardized_smiles"], tv["label"].astype(float)))
    smi = tv["standardized_smiles"].tolist()
    models = reg.load_models(ep)
    folds = five_seed_train_val_folds(smi)
    resid, val_mae = [], []
    for (s, train, valid), m in zip(folds, models):
        p = m.predict(valid); ok = ~np.isnan(p)
        y = np.array([lab[v] for v in valid])
        r = np.abs(y[ok] - p[ok]); resid += r.tolist(); val_mae.append(r.mean())
    resid = np.sort(np.array(resid)); n = len(resid)
    # test: ensemble mean, as served
    tsm = te["standardized_smiles"].tolist(); ty = te["label"].to_numpy(dtype=float)
    P = np.array([m.predict(tsm) for m in models]); ok = ~np.isnan(P).any(0)
    P, ty = P[:, ok], ty[ok]
    mean, std = P.mean(0), P.std(0); err = np.abs(ty - mean)
    adi = reg.load_ad_index(ep)
    ind = np.array([a.in_domain for a in query_ad(adi, [s for s, o in zip(tsm, ok) if o])]) if adi else None
    out = dict(endpoint=ep, n_resid=n, val_mae=float(np.mean(val_mae)), test_mae=float(err.mean()), std_median=float(np.median(std)))
    for alpha in (0.2, 0.1):
        k = min(n, math.ceil((n + 1) * (1 - alpha)))
        q = float(resid[k - 1])
        cov = float(np.mean(err <= q))
        d = dict(halfwidth=q, cover=cov)
        if ind is not None and (~ind).any():
            d["cover_in_domain"] = float(np.mean(err[ind] <= q)); d["cover_out_domain"] = float(np.mean(err[~ind] <= q))
        out[f"conf_{int((1-alpha)*100)}"] = d
    return out

def classification_redundancy(ep):
    data = load_endpoint(prep_dir_for(ep), ep)
    te = data.test; tsm = te["standardized_smiles"].tolist(); y = te["label"].to_numpy(dtype=float)
    models = reg.load_models(ep); cal = reg.load_calibrator(ep)
    P = np.array([m.predict(tsm) for m in models]); ok = ~np.isnan(P).any(0); P, y = P[:, ok], y[ok]
    res = dict(endpoint=ep)
    for name, Q in (("raw", P), ("served", np.array([cal.transform(p) for p in P]) if cal else P)):
        mean, std = Q.mean(0), Q.std(0); margin = np.abs(mean - 0.5)
        wrong = ((mean >= 0.5).astype(float) != y)
        res[name] = dict(
            rho_std_margin=float(spearmanr(std, margin).correlation),
            auroc_std=float(roc_auc_score(wrong, std)), auroc_neg_margin=float(roc_auc_score(wrong, -margin)),
            auroc_both=float(roc_auc_score(wrong, -margin - 0.0 * std)),
        )
        # does spread add anything beyond the score? residualise std on margin (rank-based) and test
        from scipy.stats import rankdata
        rs, rm = rankdata(std), rankdata(margin)
        beta = np.polyfit(rm, rs, 1); resid_std = rs - np.polyval(beta, rm)
        res[name]["auroc_std_given_margin"] = float(roc_auc_score(wrong, resid_std))
    return res

if __name__ == "__main__":
    mode, eps = sys.argv[1], sys.argv[2:]
    outs = []
    for ep in eps:
        outs.append(regression_conformal(ep) if mode == "reg" else classification_redundancy(ep))
        print("DONE", ep, flush=True)
    json.dump(outs, open(os.path.expanduser(f"~/scratch/out2_{mode}_{eps[0]}.json"), "w"), indent=1)
