"""Bounded worker pool for predictions.

A prediction is CPU-bound and single-threaded (RDKit plus 70 XGBoost calls, each pinned to
one thread). `asyncio.to_thread` runs it on the loop's default executor, which allows about
40 threads, so a burst of requests would put 40 predictions on a container with 1-2 CPUs and
make every one of them slow. This pool runs at most one prediction per CPU and lets the rest
wait their turn; the event loop stays free either way.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from app.core.config import get_settings

T = TypeVar("T")

_executor: ThreadPoolExecutor | None = None


def prediction_concurrency() -> int:
    """`MAX_CONCURRENT_PREDICTIONS` if set, else the CPUs this process may use."""
    configured = get_settings().max_concurrent_predictions
    if configured > 0:
        return configured
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except AttributeError:  # not available on Windows or macOS
        return max(1, os.cpu_count() or 1)


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=prediction_concurrency(), thread_name_prefix="predict")
    return _executor


async def run_prediction(fn: Callable[..., T], *args: object) -> T:
    """Run blocking prediction work `fn(*args)` on the bounded pool."""
    return await asyncio.get_running_loop().run_in_executor(_get_executor(), fn, *args)


# Explanations get their own small pool (ADR-029): a KERMT Integrated Gradients request waits
# seconds on the inference service, and must neither occupy the per-CPU prediction workers nor let
# a burst of explanations starve `/predict`. Two at a time; the rest queue.
EXPLANATION_WORKERS = 2
_explain_executor: ThreadPoolExecutor | None = None


def _get_explain_executor() -> ThreadPoolExecutor:
    global _explain_executor
    if _explain_executor is None:
        _explain_executor = ThreadPoolExecutor(max_workers=EXPLANATION_WORKERS, thread_name_prefix="explain")
    return _explain_executor


async def run_explanation(fn: Callable[..., T], *args: object) -> T:
    """Run blocking explanation work `fn(*args)` on the explanation pool."""
    return await asyncio.get_running_loop().run_in_executor(_get_explain_executor(), fn, *args)
