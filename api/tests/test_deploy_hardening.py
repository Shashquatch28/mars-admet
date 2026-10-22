"""Deploy-hardening guards (ship checklist C2, C3, C4).

C2: which address the anonymous rate limiter counts against behind a proxy.
C3: predictions run on a pool capped to the CPUs, not on the 40-thread default.
C4: the interactive Batch tier is small enough to answer inside one request.
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest
from app.core.config import Settings, get_settings
from app.services import prediction_pool
from app.services.rate_limit import client_ip
from starlette.requests import Request


def _request(peer: str | None, forwarded: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded is not None else []
    scope = {"type": "http", "headers": headers, "client": (peer, 1234) if peer else None}
    return Request(scope)


@pytest.fixture
def hops(monkeypatch):
    def _set(n: int) -> None:
        monkeypatch.setenv("TRUSTED_PROXY_HOPS", str(n))
        get_settings.cache_clear()

    yield _set
    get_settings.cache_clear()


def test_peer_is_the_client_by_default(hops):
    hops(0)
    # An unconfigured API must not believe a header any caller can write.
    assert client_ip(_request("10.0.0.5", "1.2.3.4")) == "10.0.0.5"


def test_one_hop_reads_the_entry_the_proxy_appended(hops):
    hops(1)
    # The client sent "6.6.6.6"; our proxy appended the real address after it.
    assert client_ip(_request("169.254.1.1", "6.6.6.6, 203.0.113.9")) == "203.0.113.9"


def test_two_hops_skip_the_inner_proxy(hops):
    hops(2)
    assert client_ip(_request("169.254.1.1", "6.6.6.6, 203.0.113.9, 35.1.1.1")) == "203.0.113.9"


def test_a_spoofed_leftmost_entry_is_never_read(hops):
    hops(1)
    assert client_ip(_request("169.254.1.1", "1.1.1.1, 2.2.2.2, 203.0.113.9")) == "203.0.113.9"


def test_header_shorter_than_hops_falls_back_to_the_peer(hops):
    hops(2)
    assert client_ip(_request("10.0.0.5", "203.0.113.9")) == "10.0.0.5"
    assert client_ip(_request("10.0.0.5")) == "10.0.0.5"


def test_no_peer_and_no_header_is_unknown(hops):
    hops(0)
    assert client_ip(_request(None)) == "unknown"


def test_interactive_batch_threshold_default_is_small():
    # A real prediction costs 0.2-0.5 s; 1,000 rows held one request open for minutes.
    # The field default, not Settings(): a developer's local .env may still carry the old value.
    assert Settings.model_fields["batch_interactive_threshold"].default <= 100


def test_concurrency_defaults_to_available_cpus(monkeypatch):
    monkeypatch.delenv("MAX_CONCURRENT_PREDICTIONS", raising=False)
    get_settings.cache_clear()
    assert prediction_pool.prediction_concurrency() >= 1


def test_concurrency_setting_overrides_cpu_count(monkeypatch):
    monkeypatch.setenv("MAX_CONCURRENT_PREDICTIONS", "3")
    get_settings.cache_clear()
    try:
        assert prediction_pool.prediction_concurrency() == 3
    finally:
        get_settings.cache_clear()


def test_pool_never_runs_more_predictions_than_the_cap(monkeypatch):
    monkeypatch.setenv("MAX_CONCURRENT_PREDICTIONS", "2")
    get_settings.cache_clear()
    monkeypatch.setattr(prediction_pool, "_executor", None)

    lock = threading.Lock()
    running = 0
    peak = 0

    def work(_n):
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        time.sleep(0.05)
        with lock:
            running -= 1

    async def burst():
        await asyncio.gather(*(prediction_pool.run_prediction(work, i) for i in range(10)))

    try:
        asyncio.run(burst())
    finally:
        pool, prediction_pool._executor = prediction_pool._executor, None
        if pool is not None:
            pool.shutdown(wait=True)
        get_settings.cache_clear()

    assert peak == 2
