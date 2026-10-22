"""Module 8 batch queue abstraction.

Blueprint-locked architecture: `POST /batch/predict` enqueues a Cloud Task per job; Cloud Tasks
delivers it to a Cloud Run worker endpoint (retry and backoff are Cloud Tasks'); the worker writes
progress to Redis; the API streams it as SSE. No Celery, no RQ, no always-on worker process.

A job is a chain of slices (see `batch_runner.py`), so the queue's contract is small: `enqueue(job_id,
index)` arranges for slice `index` of that job to run. Two implementations, chosen by
`BATCH_QUEUE_BACKEND`:

* `LocalTaskQueue` (default): runs the whole chain as one in-process asyncio task. Single-instance
  only. Correct for development and tests; a job dies with its process.
* `CloudTasksQueue`: creates one Cloud Task per slice, aimed at this service's own worker endpoint
  (`routers/worker.py`). Written against the documented Cloud Tasks API and unit-tested against a fake
  client; it has NOT been run against a real project, which needs GCP credentials and a deployed
  service (ship checklist C6-C8).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Protocol

import redis.asyncio as redis

from app.core.config import Settings

_PROGRESS_TTL_SECONDS = 86_400  # matches the 24h batch-upload retention window


def _progress_key(job_id: str) -> str:
    return f"batch_progress:{job_id}"


class TaskQueue(Protocol):
    async def enqueue(self, job_id: str, index: int = 0) -> None: ...


class LocalTaskQueue:
    """In-process asyncio background task that runs a job's whole slice chain. Single-instance only:
    NOT a substitute for Cloud Tasks across several Cloud Run instances (a task started here dies if
    this process dies)."""

    def __init__(self, run_job: Callable[[str], Awaitable[None]]) -> None:
        self._run_job = run_job
        self._tasks: dict[str, asyncio.Task] = {}

    async def enqueue(self, job_id: str, index: int = 0) -> None:
        self._tasks[job_id] = asyncio.create_task(self._run_job(job_id))


class CloudTasksQueue:
    """One Cloud Task per slice, delivered by HTTP to this service's worker endpoint.

    The task body is only `{job_id, index}`: Cloud Tasks caps a task at 100 KB, so the molecules
    themselves stay in the blob store. The worker secret travels as a header, because the Cloud Run
    service is public (it serves the site) and the endpoint must protect itself. The task is named
    `<job>-s<index>`, so enqueueing the same slice twice is a no-op rather than a duplicate."""

    def __init__(self, settings: Settings, client=None) -> None:
        self._settings = settings
        self._client = client

    def _get_client(self):
        if self._client is None:
            # Imported here: development and the test suite never need the library.
            from google.cloud import tasks_v2

            self._client = tasks_v2.CloudTasksAsyncClient()
        return self._client

    async def enqueue(self, job_id: str, index: int = 0) -> None:
        s = self._settings
        missing = [
            name
            for name, value in (
                ("GCP_PROJECT_ID", s.gcp_project_id),
                ("WORKER_BASE_URL", s.worker_base_url),
                ("BATCH_WORKER_SECRET", s.batch_worker_secret),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(f"Cloud Tasks queue is not configured: set {', '.join(missing)}")
        client = self._get_client()
        parent = client.queue_path(s.gcp_project_id, s.gcp_region, s.cloud_tasks_queue)
        task = {
            "name": f"{parent}/tasks/{job_id}-s{index}",
            "http_request": {
                "http_method": "POST",
                "url": f"{s.worker_base_url.rstrip('/')}/api/internal/batch/run",
                "headers": {"Content-Type": "application/json", "X-MARS-Worker-Secret": s.batch_worker_secret},
                "body": json.dumps({"job_id": job_id, "index": index}).encode("utf-8"),
            },
            # Longest an HTTP target may take is 30 minutes; a slice is a few minutes of work.
            "dispatch_deadline": {"seconds": s.batch_task_deadline_seconds},
        }
        try:
            await client.create_task(request={"parent": parent, "task": task})
        except Exception as exc:
            # The same slice enqueued twice (a retried worker call) is the dedup working, not an error.
            if type(exc).__name__ != "AlreadyExists":
                raise


async def set_job_progress(r: redis.Redis, job_id: str, *, status: str, total: int, completed: int) -> None:
    payload = json.dumps({"job_id": job_id, "status": status, "total": total, "completed": completed})
    await r.set(_progress_key(job_id), payload, ex=_PROGRESS_TTL_SECONDS)


async def get_job_progress(r: redis.Redis, job_id: str) -> dict | None:
    raw = await r.get(_progress_key(job_id))
    return json.loads(raw) if raw else None
