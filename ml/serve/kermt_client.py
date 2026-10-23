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


class KermtBusy(KermtUnavailable):
    """The service is up but its explanation queue is full."""


class KermtJobNotFound(Exception):
    """The service has no such explanation job: it never had it, or it restarted and lost it."""


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
    completeness_error: float
    converged: bool
    seed_agreement: float | None


@dataclass(frozen=True)
class JobSnapshot:
    """One explanation job as the service reports it (ADR-035)."""

    job_id: str
    state: str  # queued | running | done | failed | cancelled
    queue_position: int | None
    seeds_done: int
    seeds_total: int
    stage: str | None
    elapsed_seconds: float
    error: str | None
    error_kind: str | None  # unexplainable | internal | None
    result: RawExplanation | None


def parse_raw_explanation(b: dict) -> RawExplanation:
    """A service explain body -> RawExplanation. Raises KeyError / TypeError / ValueError when malformed."""
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
        completeness_error=float(b["completeness_error"]),
        converged=bool(b["converged"]),
        seed_agreement=None if b.get("seed_agreement") is None else float(b["seed_agreement"]),
    )
    if not (len(out.descriptor_values) == len(out.descriptor_scores) == len(names)) or not out.atom_scores:
        raise ValueError("inconsistent lengths")
    return out


def _snapshot(b: dict) -> JobSnapshot:
    result = b.get("result")
    return JobSnapshot(
        job_id=str(b["job_id"]),
        state=str(b["state"]),
        queue_position=None if b.get("queue_position") is None else int(b["queue_position"]),
        seeds_done=int(b["seeds_done"]),
        seeds_total=int(b["seeds_total"]),
        stage=b.get("stage"),
        elapsed_seconds=float(b["elapsed_seconds"]),
        error=b.get("error"),
        error_kind=b.get("error_kind"),
        result=parse_raw_explanation(result) if result else None,
    )


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
            out = parse_raw_explanation(resp.json())
        except (KeyError, TypeError, ValueError) as exc:
            raise KermtUnavailable(f"malformed explain reply: {exc!r}") from exc
        return out

    # ---- background explanation jobs (ADR-035). Short calls: the work happens in the service. ----

    _SHORT_TIMEOUT = 15.0

    def _gate(self) -> None:
        with self._lock:
            blocked = time.monotonic() < self._down_until
        if blocked:
            raise KermtUnavailable("circuit open after a recent failure")

    def _job_call(self, method: str, path: str, **kw) -> httpx.Response:
        self._gate()
        try:
            return self._http.request(method, path, timeout=self._SHORT_TIMEOUT, **kw)
        except httpx.HTTPError as exc:
            raise KermtUnavailable(f"{type(exc).__name__}: {exc}") from exc

    def submit_explain_job(self, smiles: str, arm: str, endpoint: str) -> JobSnapshot:
        """Start (or join) the job for this molecule and endpoint. KermtBusy when the queue is full."""
        resp = self._job_call("POST", "/explain/jobs", json={"smiles": smiles, "arm": arm, "endpoint": endpoint})
        if resp.status_code == 429:
            raise KermtBusy(resp.json().get("detail", "the explanation queue is full") if resp.content else "the explanation queue is full")
        if resp.status_code == 422:
            raise ValueError(resp.json().get("detail", "KERMT cannot explain this molecule"))
        return self._read_snapshot(resp)

    def explain_job(self, job_id: str) -> JobSnapshot:
        resp = self._job_call("GET", f"/explain/jobs/{job_id}")
        if resp.status_code == 404:
            raise KermtJobNotFound(job_id)
        return self._read_snapshot(resp)

    def cancel_explain_job(self, job_id: str) -> JobSnapshot:
        resp = self._job_call("DELETE", f"/explain/jobs/{job_id}")
        if resp.status_code == 404:
            raise KermtJobNotFound(job_id)
        return self._read_snapshot(resp)

    def _read_snapshot(self, resp: httpx.Response) -> JobSnapshot:
        if resp.status_code != 200:
            raise KermtUnavailable(f"HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            return _snapshot(resp.json())
        except (KeyError, TypeError, ValueError) as exc:
            raise KermtUnavailable(f"malformed job reply: {exc!r}") from exc

    def explain_config(self) -> dict:
        """The service's explanation parameters and a digest of them (cache-key material), cached for 60 s."""
        now = time.monotonic()
        with self._lock:
            hit = getattr(self, "_config_cache", None)
            if hit is not None and now - hit[0] < 60.0:
                return hit[1]
        resp = self._job_call("GET", "/explain/config")
        if resp.status_code != 200:
            raise KermtUnavailable(f"HTTP {resp.status_code} from /explain/config")
        try:
            cfg = dict(resp.json())
            str(cfg["digest"])
        except (KeyError, TypeError, ValueError) as exc:
            raise KermtUnavailable(f"malformed config reply: {exc!r}") from exc
        with self._lock:
            self._config_cache = (now, cfg)
        return cfg

    def ready(self) -> bool:
        try:
            return self._http.get("/health").status_code == 200
        except httpx.HTTPError:
            return False
