"""
MARS Milestone 1 — TDC data acquisition (blueprint Module 1 §1, §5).

Pulls every blueprint-required dataset through PyTDC (programmatic, versioned,
reproducible by construction), preserves the raw bytes TDC delivered without
destructive modification, records per-dataset metadata, and writes a
deterministic data-versioning lockfile.

The lockfile (``ml/data/metadata/datasets.lock.json``) answers:
  * Which PyTDC version was used?          -> acquisition.pytdc_version
  * Which dataset identifiers were used?   -> datasets[*].tdc_name / benchmark_group_name
  * When was the dataset acquired?         -> acquisition.acquired_at_utc (+ per-dataset)
  * What raw files were used?              -> datasets[*].raw_files[*].path / sha256
  * What hash identifies the snapshot?     -> datasets[*].snapshot_sha256 (order-independent)

Design:
  * RUNS IN THE ISOLATED ACQUISITION ENVIRONMENT ONLY (WSL Ubuntu venv with a
    pinned PyTDC — see ml/data/acquisition/README.md). It imports ``tdc`` and
    pandas; it does NOT import torch / rdkit / mars_contracts.
  * Non-destructive: each run writes a fresh ``<acq_id>`` directory under
    ``raw/<dataset>/`` and refuses to overwrite an existing one. The previous
    lockfile is archived under ``metadata/history/`` before a new one is written.
  * Standardization, dedup, splitting and augmentation are OUT OF SCOPE here —
    they consume these raw snapshots in later runs.

Usage (from the repo root, inside the acquisition venv):
    python ml/data/acquire.py --repo-root . --acq-env-lockfile ml/data/requirements-acquire.lock.txt
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from importlib.metadata import version as _pkg_version
from pathlib import Path

from dataset_registry import DATASET_SPECS, DatasetSpec
from snapshot import canonical_csv_digest, sha256_file

LOCKFILE_SCHEMA_VERSION = 1
SMILES_COL = "Drug"
LABEL_COL = "Y"
ID_COL = "Drug_ID"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _new_acq_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _git_sha(repo_root: Path) -> tuple[str | None, bool | None]:
    try:
        sha = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return sha, bool(status)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None, None


def _pytdc_version() -> str:
    for name in ("PyTDC", "pytdc"):
        try:
            return _pkg_version(name)
        except Exception:  # noqa: BLE001
            continue
    return "unknown"


def _load_full(spec: DatasetSpec, tdc_download_dir: Path):
    """Load a dataset via PyTDC single_pred; return (df, list_of_delivered_files)."""
    from tdc.single_pred import ADME, Tox

    loader_cls = {"ADME": ADME, "Tox": Tox}[spec.tdc_loader]
    tdc_download_dir.mkdir(parents=True, exist_ok=True)
    data = loader_cls(name=spec.tdc_name, path=str(tdc_download_dir))
    df = data.get_data()
    # every file TDC wrote into the download dir is preserved + hashed as the
    # authentic delivered artifact
    delivered = sorted(p for p in tdc_download_dir.iterdir() if p.is_file())
    return df, delivered


def _write_csv(df, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def _file_record(path: Path, raw_root: Path, role: str, n_rows: int | None) -> dict:
    return {
        "role": role,
        "path": str(path.relative_to(raw_root.parent).as_posix()),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "n_rows": n_rows,
    }


# --------------------------------------------------------------------------- #
# per-dataset acquisition
# --------------------------------------------------------------------------- #
def acquire_one(
    spec: DatasetSpec,
    raw_root: Path,
    acq_id: str,
    bench_group,
    *,
    force: bool,
) -> dict:
    ds_dir = raw_root / spec.tdc_name / acq_id
    if ds_dir.exists() and any(ds_dir.iterdir()) and not force:
        raise FileExistsError(
            f"{ds_dir} already exists and is non-empty. "
            f"Refusing to overwrite a prior snapshot (use --force only if you mean it)."
        )
    ds_dir.mkdir(parents=True, exist_ok=True)

    print(f"  [{spec.dataset_key}] TDC={spec.tdc_name} loader={spec.tdc_loader} ...", flush=True)
    df, delivered = _load_full(spec, ds_dir / "tdc_download")

    n = len(df)
    cols = list(df.columns)
    if not {SMILES_COL, LABEL_COL}.issubset(cols):
        raise RuntimeError(f"{spec.tdc_name}: unexpected columns {cols}")

    full_csv = ds_dir / f"{spec.tdc_name}.full.csv"
    _write_csv(df, full_csv)

    raw_files = [
        _file_record(full_csv, raw_root, "full_normalized_csv", n),
    ]
    for f in delivered:
        raw_files.append(_file_record(f, raw_root, f"tdc_delivered:{f.name}", None))

    entry: dict = {
        "dataset_key": spec.dataset_key,
        "endpoint_key": spec.endpoint_key,
        "variant": spec.variant,
        "tdc_name": spec.tdc_name,
        "tdc_loader": spec.tdc_loader,
        "task": spec.task,
        "license": spec.license,
        "license_ref": spec.license_ref,
        "in_admet_benchmark_group": spec.in_admet_benchmark_group,
        "benchmark_group_name": None,
        "acquired_at_utc": _utc_now(),
        "n_rows": n,
        "columns": cols,
        "id_column": ID_COL if ID_COL in cols else None,
        "smiles_column": SMILES_COL,
        "label_column": LABEL_COL,
        "approx_n_blueprint": spec.approx_n,
        "n_matches_blueprint_within_5pct": (
            spec.approx_n is not None
            and abs(n - spec.approx_n) <= max(1, round(0.05 * spec.approx_n))
        ),
        "raw_files": raw_files,
        "snapshot_sha256": canonical_csv_digest(full_csv, SMILES_COL, LABEL_COL),
        "benchmark_split": None,
        "notes": spec.notes,
    }

    if spec.in_admet_benchmark_group and bench_group is not None:
        try:
            bench = bench_group.get(spec.tdc_name)
            tv, te = bench["train_val"], bench["test"]
            bdir = ds_dir / "benchmark_split"
            tv_csv, te_csv = bdir / "train_val.csv", bdir / "test.csv"
            _write_csv(tv, tv_csv)
            _write_csv(te, te_csv)
            entry["benchmark_group_name"] = bench.get("name")
            entry["benchmark_split"] = {
                "source": "tdc.benchmark_group.admet_group",
                "protocol": "official fixed 80/20 scaffold split (Murcko); "
                "5-seed train/valid CV is applied within train_val downstream",
                "train_val": {
                    **_file_record(tv_csv, raw_root, "benchmark_train_val", len(tv)),
                    "snapshot_sha256": canonical_csv_digest(tv_csv, SMILES_COL, LABEL_COL),
                },
                "test": {
                    **_file_record(te_csv, raw_root, "benchmark_test", len(te)),
                    "snapshot_sha256": canonical_csv_digest(te_csv, SMILES_COL, LABEL_COL),
                },
            }
            print(
                f"      benchmark split: train_val={len(tv)} test={len(te)} "
                f"(resolved name={bench.get('name')!r})",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            entry["benchmark_split"] = {"error": f"{type(exc).__name__}: {exc}"}
            print(f"      !! benchmark split failed: {exc}", flush=True)

    # per-dataset source_meta.json alongside the raw files
    (ds_dir / "source_meta.json").write_text(
        json.dumps(entry, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return entry


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", default=".", type=Path)
    ap.add_argument("--acq-id", default=None, help="default: UTC timestamp")
    ap.add_argument(
        "--acq-env-lockfile",
        default=None,
        type=Path,
        help="path to the pinned pip-freeze of this acquisition env (hashed into the lockfile)",
    )
    ap.add_argument("--repo-git-sha", default=None, help="override if git is unavailable here")
    ap.add_argument("--only", nargs="*", default=None, help="subset of dataset_keys (debug)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    repo_root: Path = args.repo_root.resolve()
    if not (repo_root / "ml" / "data" / "acquire.py").exists():
        print(
            f"--repo-root {repo_root} does not look like the MARS repo root "
            f"(expected ml/data/acquire.py under it). Pass an explicit absolute path.",
            file=sys.stderr,
        )
        return 2
    data_root = repo_root / "ml" / "data"
    raw_root = data_root / "raw"
    meta_root = data_root / "metadata"
    raw_root.mkdir(parents=True, exist_ok=True)
    meta_root.mkdir(parents=True, exist_ok=True)

    acq_id = args.acq_id or _new_acq_id()
    git_sha, git_dirty = (args.repo_git_sha, None)
    if git_sha is None:
        git_sha, git_dirty = _git_sha(repo_root)

    specs = list(DATASET_SPECS.values())
    if args.only:
        specs = [s for s in specs if s.dataset_key in set(args.only)]
        if not specs:
            print(f"no dataset_keys match {args.only}", file=sys.stderr)
            return 2

    print(f"MARS acquisition  acq_id={acq_id}  pytdc={_pytdc_version()}  datasets={len(specs)}")

    # benchmark group object (downloads the official split archive once)
    bench_group = None
    bench_names: list[str] = []
    if any(s.in_admet_benchmark_group for s in specs):
        from tdc.benchmark_group import admet_group

        bg_cache = raw_root / "_tdc_benchmark_cache" / acq_id
        bg_cache.mkdir(parents=True, exist_ok=True)
        bench_group = admet_group(path=str(bg_cache))
        bench_names = sorted(getattr(bench_group, "dataset_names", []) or [])

    entries: dict[str, dict] = {}
    for spec in specs:
        entries[spec.dataset_key] = acquire_one(
            spec, raw_root, acq_id, bench_group, force=args.force
        )

    acq_env_lock = None
    if args.acq_env_lockfile and args.acq_env_lockfile.exists():
        acq_env_lock = {
            "path": str(args.acq_env_lockfile.resolve().relative_to(repo_root).as_posix()),
            "sha256": sha256_file(args.acq_env_lockfile),
        }

    lock = {
        "schema_version": LOCKFILE_SCHEMA_VERSION,
        "generator": "ml/data/acquire.py",
        "acquisition": {
            "acq_id": acq_id,
            "acquired_at_utc": _utc_now(),
            "pytdc_version": _pytdc_version(),
            "python_version": sys.version,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "repo_git_sha": git_sha,
            "repo_git_dirty": git_dirty,
            "acq_env_lockfile": acq_env_lock,
            "tdc_source": (
                "TDC single_pred (ADME/Tox) + benchmark_group.admet_group; "
                "downloads are Harvard Dataverse-backed"
            ),
            "tdc_benchmark_group_dataset_names": bench_names,
        },
        "conventions": {
            "smiles_column": SMILES_COL,
            "label_column": LABEL_COL,
            "id_column": ID_COL,
            "snapshot_digest_scheme": "mars-canonical-rows-v1 (order-independent; see ml/data/snapshot.py)",
            "raw_is_immutable": True,
            "standardization": "NOT applied here — raw SMILES/labels exactly as TDC delivered",
        },
        "datasets": entries,
        "notes": {
            "herg": (
                "Two hERG datasets acquired: 'hERG_Karim' (primary, ~13445, blueprint "
                "Module 2) and 'hERG' (benchmark_alt, ~655, TDC ADMET Benchmark Group). "
                "endpoint->dataset choice for herg_cardiotoxicity is deferred to Run 2 "
                "EDA (decision 2026-08-30). See documentation/FUTURE_SCOPE.md."
            ),
            "dilist": (
                "DILIst augmentation source (Module 1 §6) is not a TDC dataset; its "
                "acquisition + provenance is deferred to Run 2."
            ),
            "hERG_Karim_not_leaderboard_comparable": (
                "hERG_Karim is absent from TDC's ADMET Benchmark Group; the published "
                "TDC hERG leaderboard is computed on the 655-compound 'hERG'. Results on "
                "hERG_Karim are not directly leaderboard-comparable (blueprint Module 1 "
                "§4 wording flagged for the maintainer)."
            ),
        },
    }

    lockfile = meta_root / "datasets.lock.json"
    if lockfile.exists():
        prev = json.loads(lockfile.read_text(encoding="utf-8"))
        prev_id = prev.get("acquisition", {}).get("acq_id", "unknown")
        if prev_id != acq_id:
            hist = meta_root / "history"
            hist.mkdir(exist_ok=True)
            archived = hist / f"datasets.lock.{prev_id}.json"
            archived.write_text(json.dumps(prev, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(f"archived previous lockfile ({prev_id}) -> {archived.relative_to(repo_root)}")

    lockfile.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {lockfile.relative_to(repo_root)}")

    _write_report(meta_root / "acquisition_report.md", lock, repo_root)
    print(f"wrote {(meta_root / 'acquisition_report.md').relative_to(repo_root)}")
    return 0


def _write_report(path: Path, lock: dict, repo_root: Path) -> None:
    acq = lock["acquisition"]
    lines = [
        "# MARS — TDC acquisition report",
        "",
        f"- **acq_id:** `{acq['acq_id']}`",
        f"- **acquired (UTC):** {acq['acquired_at_utc']}",
        f"- **PyTDC version:** `{acq['pytdc_version']}`",
        f"- **Python:** `{acq['python_version'].splitlines()[0]}`",
        f"- **Platform:** `{acq['platform']}`",
        f"- **Repo git SHA:** `{acq['repo_git_sha']}` (dirty={acq['repo_git_dirty']})",
        "- **Acq env lockfile:** "
        + (f"`{acq['acq_env_lockfile']['path']}` "
           f"(sha256 `{acq['acq_env_lockfile']['sha256'][:16]}…`)"
           if acq.get("acq_env_lockfile") else "_not recorded_"),
        "",
        "Raw data under `ml/data/raw/<TDC_name>/<acq_id>/` is immutable. Snapshot "
        "hashes are order-independent content digests over `(Drug, Y)`.",
        "",
        "| endpoint | dataset_key | TDC name | variant | task | N | ~N (blueprint) | in TDC benchmark | bench train_val/test | snapshot_sha256 (12) |",
        "|---|---|---|---|---|--:|--:|:--:|--:|---|",
    ]
    for key, e in lock["datasets"].items():
        bs = e.get("benchmark_split") or {}
        if "train_val" in bs:
            bcounts = f"{bs['train_val']['n_rows']}/{bs['test']['n_rows']}"
        elif "error" in bs:
            bcounts = "ERROR"
        else:
            bcounts = "—"
        lines.append(
            f"| {e['endpoint_key']} | `{key}` | {e['tdc_name']} | {e['variant']} | "
            f"{e['task']} | {e['n_rows']} | {e['approx_n_blueprint'] or '—'} | "
            f"{'yes' if e['in_admet_benchmark_group'] else 'no'} | {bcounts} | "
            f"`{e['snapshot_sha256'][:12]}` |"
        )
    lines += ["", "## Notes", ""]
    for k, v in lock["notes"].items():
        lines.append(f"- **{k}:** {v}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
