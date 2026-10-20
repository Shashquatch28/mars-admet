"""Torch-free client for the KERMT inference service (`serve/kermt_service/app.py`).

The API image does not contain torch, KERMT or the 30 checkpoints; it asks the service for the
per-seed values of the arms it needs and does the ensembling itself. Anything that stops the
service from answering (down, loading, slow, a malformed reply) becomes `KermtUnavailable`, and
the caller serves those endpoints from XGBoost instead. It never returns a partial or invented
value.

A small circuit breaker keeps a dead service from adding its timeout to every request: after a
failure the client refuses calls for `cooldown_seconds` and raises at once.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger("mars.kermt_client")


class KermtUnavailable(RuntimeError):
    """The KERMT service could not provide predictions right now."""


@dataclass(frozen=True)
class RawExplanation:
    """What the service computes for one (molecule, endpoint): Integrated Gradients, seed-averaged.

    Raw on purpose: fragments and totals are derived API-side by `explain.result.assemble`, so both
    explainers share one definition of them. Atom order is RDKit's for the SMILES that was sent.
    """

    arm: str
    model_id: str
    output_space: str
    n_seeds: int
    n_steps: int
    base_value: float
    output_value: float
    baseline: str
    atom_scores: list[float]
    descriptor_names: list[str]
    descriptor_values: list[float | None]
    descriptor_scores: list[float]
    unmapped_total: float


@dataclass(frozen=True)
class ArmValues:
    arm: str
    model_id: str
    task_type: str
    seeds: list[int]
    # target -> per-seed values for the ONE molecule asked about (None where a seed gave no value)
    values: dict[str, list[float | None]]


class KermtClient:
    def __init__(
        self,
        base_url: str,
        *,
        token: str = "",
        timeout_seconds: float = 30.0,
        cooldown_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = {"X-Kermt-Token": token} if token else {}
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"), headers=headers,
            # fail fast when the service is not there at all; only a slow answer may use the full budget
            timeout=httpx.Timeout(timeout_seconds, connect=min(3.0, timeout_seconds)), transport=transport,
        )
        self._cooldown = cooldown_seconds
        self._down_until = 0.0
        self._lock = threading.Lock()

    def close(self) -> None:
        self._http.close()

    def _trip(self, why: str) -> KermtUnavailable:
        with self._lock:
            self._down_until = time.monotonic() + self._cooldown
        logger.warning("KERMT service unavailable (%s); serving KERMT-routed endpoints from XGBoost for %.0fs", why, self._cooldown)
        return KermtUnavailable(why)

    def predict(self, smiles: str, arms: list[str]) -> dict[str, ArmValues]:
        """Per-seed values for one standardized SMILES across `arms` (one HTTP call)."""
        if not arms:
            return {}
        with self._lock:
            blocked = time.monotonic() < self._down_until
        if blocked:
            raise KermtUnavailable("circuit open after a recent failure")
        try:
            resp = self._http.post("/predict", json={"smiles": [smiles], "arms": arms})
        except httpx.HTTPError as exc:
            raise self._trip(f"{type(exc).__name__}: {exc}") from exc
        if resp.status_code != 200:
            raise self._trip(f"HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            body = resp.json()["arms"]
            out: dict[str, ArmValues] = {}
            for arm in arms:
                a = body[arm]
                out[arm] = ArmValues(
                    arm=arm,
                    model_id=a["model_id"],
                    task_type=a["task_type"],
                    seeds=[int(s) for s in a["seeds"]],
                    values={t: [None if v is None else float(v) for v in rows[0]] for t, rows in a["values"].items()},
                )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise self._trip(f"malformed reply: {exc!r}") from exc
        return out

    def explain(self, smiles: str, arm: str, endpoint: str, *, timeout_seconds: float = 120.0) -> RawExplanation:
        """Integrated Gradients for one endpoint of one arm (ADR-031). Slow: seconds, not milliseconds.

        Shares the prediction breaker as a gate (a dead service is dead for both) but a slow or
        failed explanation never opens it: explanations are optional and must not stop predictions.
        """
        with self._lock:
            blocked = time.monotonic() < self._down_until
        if blocked:
            raise KermtUnavailable("circuit open after a recent failure")
        try:
            resp = self._http.post(
                "/explain", json={"smiles": smiles, "arm": arm, "endpoint": endpoint}, timeout=timeout_seconds
            )
        except httpx.HTTPError as exc:
            raise KermtUnavailable(f"{type(exc).__name__}: {exc}") from exc
        if resp.status_code != 200:
            raise KermtUnavailable(f"HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            b = resp.json()
            n_atoms = len(b["atom_scores"])
            names = [str(n) for n in b["descriptor_names"]]
            out = RawExplanation(
                arm=str(b["arm"]),
                model_id=str(b["model_id"]),
                output_space=str(b["output_space"]),
                n_seeds=int(b["n_seeds"]),
                n_steps=int(b["n_steps"]),
                base_value=float(b["base_value"]),
                output_value=float(b["output_value"]),
                baseline=str(b["baseline"]),
                atom_scores=[float(v) for v in b["atom_scores"]],
                descriptor_names=names,
                descriptor_values=[None if v is None else float(v) for v in b["descriptor_values"]],
                descriptor_scores=[float(v) for v in b["descriptor_scores"]],
                unmapped_total=float(b["unmapped_total"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise KermtUnavailable(f"malformed explain reply: {exc!r}") from exc
        if not (len(out.descriptor_values) == len(out.descriptor_scores) == len(names)) or n_atoms == 0:
            raise KermtUnavailable("malformed explain reply: inconsistent lengths")
        return out

    def ready(self) -> bool:
        try:
            return self._http.get("/health").status_code == 200
        except httpx.HTTPError:
            return False
