"""Tuning-trial runner for the pre-registered Tier-1 protocol (``train.kermt_mixed.tuning``).

Supplies the *procedure* only: no search space, trial count, seed, objective or threshold lives here. All of them come from a registered
protocol file (``tuning.preregister``); this module refuses to run unless that file's hash matches.

    python -m train.run_tuning plan     --registration documentation/AIMS/tuning/<name>.json [--hours-per-run 1.1]
    python -m train.run_tuning run      --registration ... --results runs/tuning/<name> --checkpoint <ckpt> --prep-dir <dir> [--max-runs N]
    python -m train.run_tuning finalize --registration ... --results runs/tuning/<name>

Ledger rules (same discipline as the Tier-0 launches):
* ``<results>/trial<T>_seed<S>.started`` is written before a run and ``….done.json`` after it. A ``.started`` without ``.done.json`` is a
  crashed run: the runner stops and never re-runs over it; the maintainer decides (move the files aside and say so in the session note).
* Trials run with ``calibrate=False`` (the test split is never read) and ``hyperparameter_source = source_tag(protocol, trial)``.
* ``finalize`` refuses partial results (``tuning.select``) and writes ``selection.json``.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from train.kermt_mixed.tuning import (
    Axis,
    Protocol,
    ProtocolError,
    enumerate_trials,
    select,
    source_tag,
    split_trial_params,
    verify_registration,
)

#: ``(trial, seed, source_tag, kermt_config_kwargs, mixed_kwargs) -> {"objective": float, ...}``
Runner = Callable[[int, int, str, dict[str, Any], dict[str, Any]], dict[str, Any]]


def load_protocol(registration: Path | str) -> Protocol:
    """Rebuild the protocol from its registration file and verify hash and trial list."""
    doc = json.loads(Path(registration).read_text(encoding="utf-8"))
    p = doc["protocol"]
    space = tuple(
        Axis(a["name"], a["kind"], tuple(a.get("values") or ()), a.get("low"), a.get("high")) for a in p["space"]
    )
    proto = Protocol(
        name=p["name"], cluster=p["cluster"], arm=p["arm"], space=space, reference=dict(p["reference"]),
        n_trials=p["n_trials"], sampling_seed=p["sampling_seed"], tuning_seeds=tuple(p["tuning_seeds"]),
        objective=p["objective"], lower_is_better=p["lower_is_better"],
        min_improvement_in_stds=p["min_improvement_in_stds"], notes=p["notes"],
    )
    verify_registration(proto, registration)
    return proto


def plan(proto: Protocol, hours_per_run: float) -> dict[str, Any]:
    n_runs = proto.n_trials * len(proto.tuning_seeds)
    return {
        "protocol": proto.name, "sha256": proto.sha256(), "cluster": proto.cluster, "arm": proto.arm,
        "n_trials": proto.n_trials, "tuning_seeds": list(proto.tuning_seeds), "runs": n_runs,
        "gpu_hours_estimate": round(n_runs * hours_per_run, 2),
        "note": "estimate = runs x --hours-per-run; the per-run cost of a mixed run with tuned epochs/batch size has never been measured",
    }


def _paths(results: Path, trial: int, seed: int) -> tuple[Path, Path]:
    return results / f"trial{trial}_seed{seed}.started", results / f"trial{trial}_seed{seed}.done.json"


def run_all(proto: Protocol, results: Path, runner: Runner, *, max_runs: int | None = None) -> int:
    """Run every outstanding (trial, seed) in registered order. Returns the number of runs executed."""
    results.mkdir(parents=True, exist_ok=True)
    trials = enumerate_trials(proto)
    todo = []
    for t in trials:
        for s in proto.tuning_seeds:
            started, done = _paths(results, t.trial_id, s)
            if done.exists():
                continue
            if started.exists():
                raise ProtocolError(
                    f"trial {t.trial_id} seed {s} has a .started marker and no result: a crashed run. Not re-run over; "
                    "the maintainer decides how to proceed"
                )
            todo.append((t, s))
    executed = 0
    for t, s in todo:
        if max_runs is not None and executed >= max_runs:
            break
        started, done = _paths(results, t.trial_id, s)
        tag = source_tag(proto, t.trial_id)
        cfg_kwargs, mixed_kwargs = split_trial_params(t.params)
        started.write_text(json.dumps({"trial": t.trial_id, "seed": s, "source": tag}) + "\n", encoding="utf-8")
        out = runner(t.trial_id, s, tag, cfg_kwargs, mixed_kwargs)
        if "objective" not in out:
            raise ProtocolError(f"runner returned no 'objective' for trial {t.trial_id} seed {s}")
        done.write_text(
            json.dumps({"trial": t.trial_id, "seed": s, "source": tag, "params": dict(t.params), **out}, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        executed += 1
    return executed


def finalize(proto: Protocol, results: Path) -> dict[str, Any]:
    objective: dict[int, list[float]] = {}
    for t in enumerate_trials(proto):
        vals = []
        for s in proto.tuning_seeds:
            _, done = _paths(results, t.trial_id, s)
            if not done.exists():
                raise ProtocolError(f"missing result for trial {t.trial_id} seed {s}; select() refuses partial results")
            vals.append(float(json.loads(done.read_text(encoding="utf-8"))["objective"]))
        objective[t.trial_id] = vals
    sel = select(proto, objective)
    doc = {
        "protocol": proto.name, "sha256": proto.sha256(), "objective": proto.objective, "lower_is_better": proto.lower_is_better,
        "chosen_trial": sel.chosen_trial, "moved_off_reference": sel.moved_off_reference, "reason": sel.reason, "table": sel.table,
        "chosen_params": dict(enumerate_trials(proto)[sel.chosen_trial].params),
    }
    (results / "selection.json").write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return doc


def real_runner(proto: Protocol, *, prep_dir: Path, checkpoint: Path, runs_dir: Path, use_wandb: bool) -> Runner:
    """The GPU runner: ``train_one_seed_mixed(calibrate=False)``. Imports are lazy (needs the KERMT container to actually fit).

    The objective is the run's ``best_selection_loss`` (summed per-task validation loss on scaled targets) when the protocol's
    ``objective`` is ``"val_selection_loss"``; any other objective name is refused here rather than guessed.
    """
    if proto.objective != "val_selection_loss":
        raise ProtocolError(
            f"objective {proto.objective!r} is not implemented by the runner; add it (computed from logs/val_views.npz) "
            "before registering a protocol that uses it"
        )
    from configs.clusters import cluster_members
    from configs.experiment_config import ExperimentConfig
    from data.cluster_loaders import load_cluster
    from models.kermt_model import KermtConfig
    from train.train_kermt_mixed import train_one_seed_mixed

    keys = cluster_members(proto.cluster)
    cd = load_cluster(prep_dir, keys, cluster_key=proto.cluster)
    cfg = ExperimentConfig(proto.cluster, "kermt_mixed", 0, cd.prep_id, notes=f"tuning {proto.name}")

    def run(trial: int, seed: int, tag: str, cfg_kwargs: dict[str, Any], mixed_kwargs: dict[str, Any]) -> dict[str, Any]:
        res = train_one_seed_mixed(
            cd, cfg, seed, checkpoint=checkpoint, loss_mode=proto.arm, hyperparameter_source=tag,
            kermt_config=KermtConfig(**cfg_kwargs), runs_dir=runs_dir, use_wandb=use_wandb, calibrate=False,
            **{"min_per_task": 0, **mixed_kwargs},
        )
        fit = json.loads((Path(res.model_path).parent / "fit_summary.json").read_text(encoding="utf-8"))
        # min_per_task absent from the protocol means 0 (stock shuffling, the registered reference value in decisions.md 2026-10-14)
        return {
            "objective": float(fit["best_selection_loss"]), "best_epoch": fit.get("best_epoch"), "run_id": res.run_id,
            "min_per_task_used": mixed_kwargs.get("min_per_task", 0),
        }

    return run


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run", "finalize"):
        p = sub.add_parser(name)
        p.add_argument("--registration", required=True, type=Path)
        if name == "plan":
            p.add_argument("--hours-per-run", type=float, required=True)
        else:
            p.add_argument("--results", required=True, type=Path)
        if name == "run":
            p.add_argument("--checkpoint", required=True, type=Path)
            p.add_argument("--prep-dir", required=True, type=Path)
            p.add_argument("--runs-dir", type=Path, default=Path("runs"))
            p.add_argument("--max-runs", type=int, default=None)
            p.add_argument("--wandb", action="store_true")
    a = ap.parse_args(argv)
    proto = load_protocol(a.registration)
    if a.cmd == "plan":
        print(json.dumps(plan(proto, a.hours_per_run), indent=2))
    elif a.cmd == "run":
        runner = real_runner(proto, prep_dir=a.prep_dir, checkpoint=a.checkpoint, runs_dir=a.runs_dir, use_wandb=a.wandb)
        print(f"executed {run_all(proto, a.results, runner, max_runs=a.max_runs)} run(s)")
    else:
        print(json.dumps(finalize(proto, a.results), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
