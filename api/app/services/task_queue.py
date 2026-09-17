"""Module 8 batch queue abstraction.

Blueprint-locked architecture: `POST /batch/predict` enqueues a Cloud Task per
job; Cloud Tasks delivers it to a dedicated Cloud Run worker endpoint
(retry/backoff handled by Cloud Tasks); the worker writes progress to Redis;
the backend streams it via SSE. No Celery, no RQ, no always-on worker process
— see `documentation/mars-blueprint_v4.md` Module 8/10.

`CloudTasksQueue` is the real target and is NOT wired up (needs
`GCP_SA_KEY_JSON` + a deployed Cloud Run worker endpoint, neither of which
exist yet — this is explicitly M3/M10 deployment work, tracked in
`next_steps.md`, not fabricated here). `LocalTaskQueue` is a same-process
asyncio stand-in that implements the identical job-lifecycle contract
(enqueue -> progress updates in Redis -> SSE-readable status) so the API
routes, DB rows, and SSE endpoint are all real and testable today; swapping
in `CloudTasksQueue` later changes only which class `get_task_queue()`
returns.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Protocol

import redis.asyncio as redis

_PROGRESS_TTL_SECONDS = 86_400  # matches the 24h batch-upload retention window


def _progress_key(job_id: str) -> str:
    return f"batch_progress:{job_id}"


class TaskQueue(Protocol):
    async def enqueue(self, job_id: str, coro_factory: Callable[[], Awaitable[None]]) -> None: ...


class LocalTaskQueue:
    """In-process asyncio background task. Single-instance only — correct
    for local dev/tests, NOT a substitute for Cloud Tasks in a multi-instance
    Cloud Run deployment (a task started here dies if this process dies)."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}

    async def enqueue(self, job_id: str, coro_factory: Callable[[], Awaitable[None]]) -> None:
        self._tasks[job_id] = asyncio.create_task(coro_factory())


class CloudTasksQueue:
    """Real target for M3/M10 — NOT wired up. Requires `GCP_SA_KEY_JSON`,
    `GCP_PROJECT_ID`, `CLOUD_TASKS_QUEUE`, and a deployed Cloud Run worker
    endpoint to deliver to. Implementing this without those in place would
    either silently no-op or fabricate a working queue that isn't — so it
    raises instead of pretending."""

    async def enqueue(self, job_id: str, coro_factory: Callable[[], Awaitable[None]]) -> None:
        raise NotImplementedError(
            "CloudTasksQueue is not wired up yet — requires a deployed Cloud Run worker "
            "endpoint + GCP_SA_KEY_JSON (M3/M10 deployment work, not yet done). "
            "Use LocalTaskQueue for local dev."
        )


async def set_job_progress(r: redis.Redis, job_id: str, *, status: str, total: int, completed: int) -> None:
    payload = json.dumps({"job_id": job_id, "status": status, "total": total, "completed": completed})
    await r.set(_progress_key(job_id), payload, ex=_PROGRESS_TTL_SECONDS)


async def get_job_progress(r: redis.Redis, job_id: str) -> dict | None:
    raw = await r.get(_progress_key(job_id))
    return json.loads(raw) if raw else None
