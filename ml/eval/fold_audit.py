"""CPU-only audit of the per-task validation folds every multitask subgroup trains/selects on.

Uses the training code path: ``cd.train_pool(holdout_calibration=True)`` then ``five_seed_train_val_folds``.
Per task and seed: validation n, positives, negatives, pairs, smallest AUROC step (classification) or n (regression).
Also the cross-seed Jaccard of the validation sets. Flags classification tasks with < 70 positives or < 70 negatives
in ANY seed's validation fold (Hanley-McNeil rule of thumb at AUROC 0.88: SE <= 0.03 needs ~70 of each class).
Reads labels of train_val only; the test split is never touched.

    PREP_ID=<id> python -m eval.fold_audit --out <json>
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
from pathlib import Path

from configs.clusters import multitask_subgroups
from data.cluster_loaders import SMILES_COL, load_cluster
from data.split import five_seed_train_val_folds
from mars_contracts.endpoints import TaskType

MIN_PER_CLASS = 70
SEEDS = (0, 1, 2, 3, 4)


def audit_subgroup(prep: Path, key: str, spec) -> dict:
    cd = load_cluster(prep, list(spec.endpoints), cluster_key=key)
    pool, lost = cd.train_pool(holdout_calibration=True)
    smiles = pool[SMILES_COL].tolist()
    folds = five_seed_train_val_folds(smiles, seeds=SEEDS)
    val_sets = {s: set(v) for s, _, v in folds}
    idx = pool.set_index(SMILES_COL)
    out = {"pool_size": len(pool), "val_size": {s: len(v) for s, v in val_sets.items()},
           "labels_lost_to_calibration_holdout": lost, "tasks": {}, "flags": []}
    for ep in spec.endpoints:
        is_cls = cd.task_types[ep] is TaskType.CLASSIFICATION
        per_seed = {}
        for s, _, val in folds:
            y = idx.loc[val, ep].dropna()
            n = int(len(y))
            if is_cls:
                pos = int((y == 1).sum()); neg = n - pos
                pairs = pos * neg
                per_seed[s] = {"n": n, "pos": pos, "neg": neg, "pairs": pairs,
                               "smallest_auroc_step": (1.0 / pairs) if pairs else None}
                if pos < MIN_PER_CLASS or neg < MIN_PER_CLASS:
                    out["flags"].append(f"{ep} seed{s}: pos={pos} neg={neg} (< {MIN_PER_CLASS})")
            else:
                per_seed[s] = {"n": n}
        out["tasks"][ep] = {"type": "classification" if is_cls else "regression", "per_seed": per_seed,
                            "train_labelled_seed0": int(idx.loc[folds[0][1], ep].notna().sum())}
    jac = {f"{a}-{b}": len(val_sets[a] & val_sets[b]) / len(val_sets[a] | val_sets[b])
           for a, b in itertools.combinations(SEEDS, 2)}
    out["val_jaccard"] = {"min": min(jac.values()), "max": max(jac.values()), "pairs": jac,
                          "in_all_five": len(set.intersection(*val_sets.values()))}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    prep = Path("data/processed") / os.environ["PREP_ID"]
    res = {"prep_id": os.environ["PREP_ID"], "min_per_class": MIN_PER_CLASS, "subgroups": {}}
    for key, spec in multitask_subgroups().items():
        res["subgroups"][key] = audit_subgroup(prep, key, spec)
        r = res["subgroups"][key]
        print(f"{key}: pool={r['pool_size']} val={sorted(set(r['val_size'].values()))} "
              f"jaccard={r['val_jaccard']['min']:.3f}-{r['val_jaccard']['max']:.3f} flags={len(r['flags'])}", flush=True)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
