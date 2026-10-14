"""
Pre-registered hyperparameter search for the Tier-1 arms.

Why this module exists
----------------------
Every setting that changes a Tier-1 number — epochs (which also stretches the Noam
learning-rate schedule, so it is not just early stopping), learning rates, the
stratified-batch floor, GradNorm's ``alpha`` and weight learning rate — is an
empirical question for MARS's data, not a constant to be asserted. The values in
the literature come from other problems: GradNorm's own paper reports an optimum
near ``alpha = 1.5`` on NYUv2 and used ``0.12`` on its synthetic regression task.
KERMT's stock defaults are explicitly a "faster default" (``epochs = 30``, the file
says to raise it for a real run). Nothing here, nor in the stock config, was tuned
on ADMET data.

This module makes the decision procedure explicit and tamper-evident:

1. a :class:`Protocol` states the search space, the always-included reference
   configuration, the budget, the tuning seeds, the objective and the selection
   rule — **before any trial runs**;
2. :func:`preregister` writes it to disk with its sha256 and refuses to overwrite
   it with anything different;
3. :func:`select` picks a configuration from validation numbers only, and moves
   off the reference **only if** the evidence beats seed noise.

What it deliberately does not do
--------------------------------
* It has no default for any field. The person registering a protocol states every
  number; the numbers are a maintainer decision (``decisions.md``), and a module
  that supplied them would be making that decision silently.
* It never sees a test or calibration metric. Trials are run with
  ``calibrate=False`` (the test split is then not read at all) and the objective is
  a validation quantity.
* It does not decide the *objective itself*. ``val_selection_loss`` (the sum of
  per-task validation losses on scaled targets) is unweighted by the training arm,
  so it is comparable across hyperparameters *within* an arm; whether it is the
  right thing to optimize is the open question the per-epoch validation views
  (``posthoc.py``) exist to answer without retraining.

Fairness across arms (``assert_equal_budget``)
-----------------------------------------------
An arm with extra hyperparameters (GradNorm) must not receive more tuning trials
than one without. Each arm gets the same number of trials over *its own* space.
Comparing a tuned Tier-1 arm to the untuned stock Tier-0 number would credit tuning
to mixed-type training; report Tier 1 at the reference configuration beside the
tuned result.

Stdlib + numpy only; host-side (never staged into the container).
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

KINDS = ("choice", "int", "uniform", "loguniform")

#: Parameter names a trial may set, and where each one goes.
KERMT_CONFIG_PARAMS = (
    "epochs", "batch_size", "init_lr", "max_lr", "final_lr", "dropout",
    "bond_drop_rate", "dist_coff", "ffn_hidden_size", "ffn_num_layers",
)
MIXED_PARAMS = ("min_per_task", "gradnorm_alpha", "gradnorm_lr")


class ProtocolError(ValueError):
    """The protocol, its registration, or the results offered to it are invalid."""


@dataclass(frozen=True)
class Axis:
    """One searched parameter. ``choice`` takes ``values``; the rest take ``low``/``high``."""

    name: str
    kind: str
    values: tuple[Any, ...] = ()
    low: float | None = None
    high: float | None = None

    def __post_init__(self) -> None:
        if self.name not in KERMT_CONFIG_PARAMS + MIXED_PARAMS:
            raise ProtocolError(f"unknown parameter {self.name!r}")
        if self.kind not in KINDS:
            raise ProtocolError(f"axis {self.name!r}: kind must be one of {KINDS}")
        if self.kind == "choice":
            if len(self.values) < 2:
                raise ProtocolError(f"axis {self.name!r}: a choice axis needs >= 2 values")
        else:
            if self.low is None or self.high is None or not self.low < self.high:
                raise ProtocolError(f"axis {self.name!r}: needs low < high")
            if self.kind == "loguniform" and self.low <= 0:
                raise ProtocolError(f"axis {self.name!r}: loguniform needs low > 0")

    def sample(self, rng: np.random.Generator) -> Any:
        if self.kind == "choice":
            return self.values[int(rng.integers(len(self.values)))]
        assert self.low is not None and self.high is not None
        if self.kind == "int":
            return int(rng.integers(int(self.low), int(self.high) + 1))
        if self.kind == "uniform":
            return float(rng.uniform(self.low, self.high))
        return float(math.exp(rng.uniform(math.log(self.low), math.log(self.high))))


@dataclass(frozen=True)
class Protocol:
    """A complete, pre-registered search. Every field is required."""

    name: str
    cluster: str
    arm: str  # loss mode this protocol tunes
    space: tuple[Axis, ...]
    reference: Mapping[str, Any]  # trial 0: the "do not move" configuration
    n_trials: int  # total, including the reference
    sampling_seed: int
    tuning_seeds: tuple[int, ...]
    objective: str  # name of the validation quantity (recorded, not interpreted)
    lower_is_better: bool
    min_improvement_in_stds: float  # evidence required to leave the reference
    notes: str

    def __post_init__(self) -> None:
        if self.n_trials < 2:
            raise ProtocolError("n_trials must be >= 2 (the reference plus >= 1 candidate)")
        if len(self.tuning_seeds) < 2:
            raise ProtocolError(
                "tuning needs >= 2 seeds: with one seed there is no noise estimate and "
                "a 'better' configuration cannot be told from luck"
            )
        if len(set(self.tuning_seeds)) != len(self.tuning_seeds):
            raise ProtocolError("tuning_seeds must be distinct")
        if self.min_improvement_in_stds < 0:
            raise ProtocolError("min_improvement_in_stds must be >= 0")
        names = [a.name for a in self.space]
        if len(set(names)) != len(names):
            raise ProtocolError("duplicate axis names")
        extra = set(self.reference) - set(names)
        missing = set(names) - set(self.reference)
        if extra or missing:
            raise ProtocolError(
                f"reference must give exactly the searched parameters; "
                f"missing {sorted(missing)}, extra {sorted(extra)}"
            )

    def canonical(self) -> dict[str, Any]:
        d = asdict(self)
        d["space"] = [asdict(a) for a in self.space]
        d["reference"] = dict(self.reference)
        d["tuning_seeds"] = list(self.tuning_seeds)
        return json.loads(json.dumps(d, sort_keys=True, default=str))

    def sha256(self) -> str:
        blob = json.dumps(self.canonical(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Trial:
    trial_id: int
    params: Mapping[str, Any]
    is_reference: bool


def enumerate_trials(protocol: Protocol) -> list[Trial]:
    """Trial 0 is the reference; the rest are reproducible random draws."""
    trials = [Trial(0, dict(protocol.reference), True)]
    seen = {json.dumps(trials[0].params, sort_keys=True, default=str)}
    rng = np.random.default_rng(protocol.sampling_seed)
    attempts = 0
    while len(trials) < protocol.n_trials:
        attempts += 1
        if attempts > 200 * protocol.n_trials:
            raise ProtocolError(
                f"search space too small for n_trials={protocol.n_trials}: found only "
                f"{len(trials)} distinct configurations. Enlarge the space or lower n_trials; "
                "a silently shorter budget would break the equal-budget rule."
            )
        params = {a.name: a.sample(rng) for a in protocol.space}
        key = json.dumps(params, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        trials.append(Trial(len(trials), params, False))
    return trials


def source_tag(protocol: Protocol, trial_id: int) -> str:
    """The ``hyperparameter_source`` string a run record carries."""
    return f"tuning:{protocol.sha256()[:12]}:{trial_id}"


def split_trial_params(params: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """``(KermtConfig kwargs, mixed-trainer kwargs)`` for a trial's parameters."""
    cfg = {k: v for k, v in params.items() if k in KERMT_CONFIG_PARAMS}
    mixed = {k: v for k, v in params.items() if k in MIXED_PARAMS}
    unknown = set(params) - set(cfg) - set(mixed)
    if unknown:
        raise ProtocolError(f"unknown trial parameters: {sorted(unknown)}")
    return cfg, mixed


# ---- registration ------------------------------------------------------------


def preregister(protocol: Protocol, path: Path | str) -> str:
    """Write the protocol (and its trial list) before any trial runs; return the hash.

    Idempotent for an identical protocol; raises if ``path`` already holds a
    different one. That refusal is the point: a search space cannot be edited after
    results are seen without it being visible as a different hash.
    """
    p = Path(path)
    digest = protocol.sha256()
    if p.exists():
        existing = json.loads(p.read_text(encoding="utf-8"))
        if existing.get("sha256") != digest:
            raise ProtocolError(
                f"{p} already holds protocol {existing.get('sha256', '?')[:12]}; this one is "
                f"{digest[:12]}. A registered protocol is not edited — register a new name."
            )
        return digest
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "sha256": digest,
        "protocol": protocol.canonical(),
        "trials": [
            {"trial_id": t.trial_id, "params": dict(t.params), "is_reference": t.is_reference}
            for t in enumerate_trials(protocol)
        ],
    }
    p.write_text(json.dumps(doc, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return digest


def verify_registration(protocol: Protocol, path: Path | str) -> None:
    """Raise unless ``path`` holds exactly this protocol (hash and trial list)."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if doc.get("sha256") != protocol.sha256():
        raise ProtocolError("registered protocol hash does not match the protocol in use")
    registered = [t["params"] for t in doc["trials"]]
    now = [dict(t.params) for t in enumerate_trials(protocol)]
    if json.loads(json.dumps(registered, default=str)) != json.loads(json.dumps(now, default=str)):
        raise ProtocolError("registered trial list differs from the regenerated one")


# ---- selection -----------------------------------------------------------------


@dataclass(frozen=True)
class Selection:
    chosen_trial: int
    moved_off_reference: bool
    reason: str
    table: list[dict[str, Any]]


def select(
    protocol: Protocol, objective_by_trial: Mapping[int, Sequence[float]]
) -> Selection:
    """Choose a trial from validation objectives (one value per tuning seed).

    Refuses partial results: a selection made after only some trials ran is a
    different, smaller experiment than the one registered. Moves off the reference
    only if the best candidate's mean beats it by more than
    ``min_improvement_in_stds`` times the seed noise, where noise is the larger of
    the reference's std and the median std over all trials (so a lucky
    zero-variance reference cannot make any difference look significant).
    """
    expected = {t.trial_id for t in enumerate_trials(protocol)}
    got = set(objective_by_trial)
    if got != expected:
        raise ProtocolError(
            f"results must cover exactly the registered trials; missing {sorted(expected - got)}, "
            f"unexpected {sorted(got - expected)}"
        )
    n_seeds = len(protocol.tuning_seeds)
    table = []
    for tid in sorted(expected):
        vals = np.asarray(objective_by_trial[tid], dtype=float)
        if vals.shape != (n_seeds,):
            raise ProtocolError(f"trial {tid}: need {n_seeds} values (one per tuning seed)")
        if not np.isfinite(vals).all():
            raise ProtocolError(f"trial {tid}: non-finite objective; the run is invalid, not 'bad'")
        table.append({"trial_id": tid, "mean": float(vals.mean()), "std": float(vals.std()),
                      "values": [float(v) for v in vals]})
    ref = table[0]
    sign = 1.0 if protocol.lower_is_better else -1.0
    best = min(table, key=lambda r: sign * r["mean"])
    noise = max(ref["std"], float(np.median([r["std"] for r in table])), 1e-12)
    gain = sign * (ref["mean"] - best["mean"])  # positive = better than reference
    needed = protocol.min_improvement_in_stds * noise
    if best["trial_id"] == 0 or gain <= needed:
        why = (
            f"best candidate improves the reference by {gain:.6g}; required more than "
            f"{needed:.6g} ({protocol.min_improvement_in_stds} x noise {noise:.6g}). "
            "No evidence to leave the reference."
        )
        return Selection(0, False, why, table)
    why = (
        f"trial {best['trial_id']} improves the reference by {gain:.6g} (> {needed:.6g}, "
        f"{protocol.min_improvement_in_stds} x noise {noise:.6g})"
    )
    return Selection(best["trial_id"], True, why, table)


def assert_equal_budget(protocols: Sequence[Protocol]) -> None:
    """Every arm must get the same number of trials, seeds and objective."""
    if not protocols:
        return
    first = protocols[0]
    for p in protocols[1:]:
        problems = []
        if p.n_trials != first.n_trials:
            problems.append(f"n_trials {p.n_trials} != {first.n_trials}")
        if len(p.tuning_seeds) != len(first.tuning_seeds):
            problems.append("different number of tuning seeds")
        if p.objective != first.objective or p.lower_is_better != first.lower_is_better:
            problems.append("different objective")
        if p.min_improvement_in_stds != first.min_improvement_in_stds:
            problems.append("different selection threshold")
        if problems:
            raise ProtocolError(
                f"unequal tuning budget between {first.arm!r} and {p.arm!r}: " + "; ".join(problems)
            )
