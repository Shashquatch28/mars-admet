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

    def ready(self) -> bool:
        try:
            return self._http.get("/health").status_code == 200
        except httpx.HTTPError:
            return False
