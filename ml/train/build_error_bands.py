"""
Build the held-out-error band (frontend ADR-024) for each regression endpoint and write it next to the
promoted artifacts as ``<artifacts>/<endpoint>/error_band.json``.

Reads the promoted seed models and the processed train_val pool. For each seed it regenerates the same
scaffold partition the seed trained on (``five_seed_train_val_folds``), scores that seed on its own
validation fold, pools the five folds' absolute residuals and takes the ceil((n+1)*level)-th smallest.
No model is fit or modified. The test set is used only to REPORT how often the band held (never to
choose the half-width), and the report says so.

Usage
-----
    cd ml && PYTHONPATH=. python train/build_error_bands.py
    cd ml && PYTHONPATH=. python train/build_error_bands.py --level 0.8 --endpoints caco2_permeability
    cd ml && PYTHONPATH=. python train/build_error_bands.py --report ../documentation/status/heldout_error_bands.md
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
from data.loaders import load_endpoint
from data.split import five_seed_train_val_folds
from eval.applicability_domain import query_ad
from eval.error_band import DEFAULT_LEVEL, ERROR_BAND_FILENAME, ErrorBand, build_error_band
from featurize.cache import FeatureCache
from mars_contracts.endpoints import ENDPOINT_METADATA, ML_ENDPOINTS, TaskType
from serve.registry import ModelRegistry

DEFAULT_PREP_ID = "20260830T200000Z"  # the snapshot all 70 sweep runs trained under


def regression_endpoints() -> list[str]:
    return [e.value for e in ML_ENDPOINTS if ENDPOINT_METADATA[e]["task_type"] == TaskType.REGRESSION]


def test_coverage(registry: ModelRegistry, key: str, data, band: ErrorBand) -> dict:
    """How often the band held on the held-out TEST molecules (reporting only)."""
    smiles = data.test["standardized_smiles"].tolist()
    y = data.test["label"].to_numpy(dtype=float)
    models = registry.load_models(key)
    preds = np.array([m.predict(smiles) for m in models])
    ok = ~np.isnan(preds).any(axis=0)
    err = np.abs(y[ok] - preds[:, ok].mean(axis=0))
    held = err <= band.halfwidth
    out = {"n_test": int(ok.sum()), "cover": float(held.mean()), "cover_in_domain": None, "cover_out_domain": None, "n_out_domain": 0}
    index = registry.load_ad_index(key)
    if index is not None:
        in_dom = np.array([r.in_domain for r in query_ad(index, [s for s, o in zip(smiles, ok, strict=True) if o])])
        if in_dom.any():
            out["cover_in_domain"] = float(held[in_dom].mean())
        if (~in_dom).any():
            out["cover_out_domain"] = float(held[~in_dom].mean())
        out["n_out_domain"] = int((~in_dom).sum())
    return out


def render_report(rows: list[tuple[ErrorBand, dict]], level: float) -> str:
    lines = [
        "# Held-out-error band, regression endpoints",
        "",
        f"Level {level:.0%}. The half-width is fixed from the pooled out-of-fold residuals only; the test columns",
        "report how often it held on the held-out test molecules and played no part in choosing it.",
        "The band is one constant per endpoint (marginal, not per-molecule) and it under-covers",
        "out-of-domain molecules, which is why the applicability-domain flag stays beside it.",
        "",
        "| Endpoint | half-width | pooled residuals | test n | test cover | in-domain | out-of-domain (n) |",
        "|---|---|---|---|---|---|---|",
    ]
    for band, t in rows:
        fmt = lambda v: "n/a" if v is None else f"{v:.2f}"  # noqa: E731
        lines.append(
            f"| {band.endpoint} | {band.halfwidth:.4g} | {band.n_residuals} | {t['n_test']} | {t['cover']:.2f} "
            f"| {fmt(t['cover_in_domain'])} | {fmt(t['cover_out_domain'])} ({t['n_out_domain']}) |"
        )
    lines += ["", "Regenerate: `cd ml && PYTHONPATH=. python train/build_error_bands.py --report <path>`.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ml_root = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prep-id", default=DEFAULT_PREP_ID)
    p.add_argument("--artifacts-root", default=str(ml_root / "artifacts"))
    p.add_argument("--cache-root", default=str(ml_root / "data" / "cache"))
    p.add_argument("--level", type=float, default=DEFAULT_LEVEL)
    p.add_argument("--endpoints", nargs="*", default=None, help="Subset of regression endpoint keys.")
    p.add_argument("--report", default=None, help="Write a markdown summary here.")
    args = p.parse_args(argv)

    prep_dir = ml_root / "data" / "processed" / args.prep_id
    if not prep_dir.exists():
        print(f"Processed snapshot not found: {prep_dir}", file=sys.stderr)
        return 2

    keys = args.endpoints or regression_endpoints()
    bad = [k for k in keys if k not in regression_endpoints()]
    if bad:
        print(f"Not regression endpoints (a held-out absolute-error band is defined for these only): {bad}", file=sys.stderr)
        return 2

    registry = ModelRegistry(FeatureCache(Path(args.cache_root)), artifacts_root=args.artifacts_root)
    rows: list[tuple[ErrorBand, dict]] = []
    for key in keys:
        t0 = time.time()
        cov = registry.coverage(key)
        if cov.seeds != [0, 1, 2, 3, 4]:
            print(f"BLOCKED {key}: promoted seeds are {cov.seeds}, the band needs 0-4", flush=True)
            continue
        data = load_endpoint(prep_dir, key)
        smiles = data.train_val["standardized_smiles"].tolist()  # as trained: the folds depend on this exact list
        labels = dict(zip(smiles, data.train_val["label"].astype(float), strict=True))
        folds = five_seed_train_val_folds(smiles)
        models = dict(zip(cov.seeds, registry.load_models(key), strict=True))
        band = build_error_band(key, models, folds, labels, level=args.level)
        band.save(Path(args.artifacts_root) / key / ERROR_BAND_FILENAME)
        cover = test_coverage(registry, key, data, band)
        rows.append((band, cover))
        print(
            f"OK {key:24s} halfwidth={band.halfwidth:.4g} n={band.n_residuals:5d} test cover={cover['cover']:.2f} ({time.time() - t0:.0f}s)",
            flush=True,
        )

    if args.report and rows:
        Path(args.report).write_text(render_report(rows, args.level), encoding="utf-8")
        print(f"Wrote {args.report}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
