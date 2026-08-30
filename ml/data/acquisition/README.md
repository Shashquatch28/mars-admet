# TDC acquisition — isolated environment

`ml/data/acquire.py` pulls the blueprint-required datasets through PyTDC and
writes the data-versioning lockfile (`ml/data/metadata/datasets.lock.json`).
It runs in a **dedicated, isolated environment**, separate from `ml/.venv`.

## Why isolated

Modern PyTDC (0.4.17 – 1.1.15) hard-pins `numpy<2.0.0` and `rdkit<2024.3.1` and
declares `tiledbsoma`, which has **no Windows wheel**. Installing it into the M1
working environment would drag `ml/.venv` back to NumPy 1.x / RDKit 2023.09 and
pull a large multi-omics stack that the ADMET dataset code path never imports.
So acquisition gets its own throwaway environment and `ml/.venv` stays on
NumPy 2.x / RDKit 2026.3 (decision 2026-08-30, `documentation/AIMS/decisions.md`).

## The environment used for the recorded snapshot (2026-08-30)

- **WSL Ubuntu 24.04**, Python 3.12.3
- `python3 -m venv --without-pip ~/mars-acq-venv`; pip bootstrapped via `get-pip.py`
- `pip install "PyTDC==1.1.15" --no-deps` + the minimal ADMET runtime deps
- Exact resolved versions: **`ml/data/requirements-acquire.lock.txt`** (its sha256
  is recorded in the lockfile under `acquisition.acq_env_lockfile`)

`--no-deps` is deliberate: the omitted packages (`tiledbsoma`, `cellxgene-census`,
`gget`, `biopython`, `transformers`, `accelerate`, `datasets`, `seaborn`) are only
imported by TDC's multi-omics / model-server modules, not by `tdc.single_pred`
or `tdc.benchmark_group`. The packages that ARE installed are all pinned.

## Reproduce the environment

```bash
wsl -d Ubuntu -- bash -s <<'SH'
python3 -m venv --without-pip ~/mars-acq-venv
curl -sSL https://bootstrap.pypa.io/get-pip.py | ~/mars-acq-venv/bin/python
~/mars-acq-venv/bin/pip install "setuptools<81"
~/mars-acq-venv/bin/pip install --no-deps "PyTDC==1.1.15"
~/mars-acq-venv/bin/pip install -r "/mnt/c/Users/Shashwat Kumar/Desktop/Labs/mars-admet/ml/data/requirements-acquire.lock.txt"
SH
```

(A Linux Docker container with the same pins works identically; WSL was used
because Docker Desktop's daemon was not running on this machine.)

## Run acquisition

```bash
wsl -d Ubuntu -- bash -s <<'SH'
REPO="/mnt/c/Users/Shashwat Kumar/Desktop/Labs/mars-admet"
cd "$REPO/ml/data"
export TQDM_DISABLE=1
~/mars-acq-venv/bin/python acquire.py \
  --repo-root "$REPO" \
  --repo-git-sha "$(git -C "$REPO" rev-parse HEAD)" \
  --acq-env-lockfile "$REPO/ml/data/requirements-acquire.lock.txt"
SH
```

Notes:
- Pipe the script via `bash -s` (stdin). Passing a space-containing repo path as a
  `bash -lc '...'` argument through `wsl.exe` mangles the quoting — stdin does not.
- `--repo-root` must be the repo root (the script rejects anything else).
- Output: `ml/data/raw/<TDC_name>/<acq_id>/…` (immutable; git-ignored, ~22 MB),
  `ml/data/metadata/datasets.lock.json`, `ml/data/metadata/acquisition_report.md`.
- A second run with a new `acq_id` keeps the old raw dirs and archives the old
  lockfile to `ml/data/metadata/history/`. It never overwrites a prior snapshot.

## Verify

From `ml/`, with `ml/.venv`:

```bash
../ml/.venv/Scripts/python.exe -m pytest tests/test_acquisition_lockfile.py -q
```

Re-derives every recorded hash from the raw files on disk. Skips cleanly if no
acquisition has been run on this machine.
