"""Run a queued batch job one slice at a time.

A real prediction costs 0.2-0.5 s, so a 50,000-molecule job is hours of work. No single request can
carry that: Cloud Tasks gives an HTTP target at most 30 minutes, and a dead instance would lose all of
it. So a job is a chain of short invocations. Each one predicts `batch_slice_rows` molecules, stores
them, and hands back the index of the next slice, or finishes the job. Every step is safe to repeat:

* a slice already stored is not predicted again, so a retried invocation costs nothing;
* a job already `done` or `failed` is left alone, so a duplicate delivery is a no-op.

`LocalTaskQueue` runs the chain in-process; `CloudTasksQueue` enqueues each next slice as its own task
(see `task_queue.py` and `routers/worker.py`). This module is the one piece of job logic both share.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import redis.asyncio as redis
from mars_contracts import BatchPredictResponse, BatchRowResult, Endpoint

from app.core.config import get_settings
from app.db.models import BatchJob
from app.db.session import SessionLocal
from app.services.blob_store import BlobStore, get_blob_store, input_key, results_key, slice_key
from app.services.prediction_pool import run_prediction
from app.services.prediction_service import predict as predict_one
from app.services.redis_client import get_redis
from app.services.task_queue import (
    CloudTasksQueue,
    LocalTaskQueue,
    TaskQueue,
    get_job_progress,
    set_job_progress,
)


def predict_row(row_index: int, smiles: str, endpoints: list[Endpoint] | None) -> BatchRowResult:
    """One molecule -> one row. A bad molecule is a failed row, never a dropped one (ADR-008)."""
    if not smiles or not smiles.strip():
        return BatchRowResult(row_index=row_index, smiles_input=smiles, ok=False, error="empty SMILES")
    try:
        prediction = predict_one(smiles, endpoints)
    except ValueError as exc:
        return BatchRowResult(row_index=row_index, smiles_input=smiles, ok=False, error=str(exc))
    return BatchRowResult(row_index=row_index, smiles_input=smiles, ok=True, prediction=prediction)


def now_naive_utc() -> datetime:
    """`batch_jobs.completed_at` is a naive `TIMESTAMP WITHOUT TIME ZONE` column; asyncpg rejects a
    tz-aware value against it. Store naive UTC consistently."""
    return datetime.now(UTC).replace(tzinfo=None)


async def store_job_input(blobs: BlobStore, job_id: str, smiles: list[str], endpoints: list[Endpoint] | None) -> None:
    payload = {"smiles": smiles, "endpoints": [e.value for e in endpoints] if endpoints else None}
    await blobs.put(input_key(job_id), json.dumps(payload))


async def _mark_job(job_id: str, status: str) -> None:
    async with SessionLocal() as session:
        job = await session.get(BatchJob, uuid.UUID(job_id))
        if job is not None:
            job.status = status
            job.completed_at = now_naive_utc()
            await session.commit()


async def fail_job(r: redis.Redis, job_id: str, total: int = 0) -> None:
    """Record a job as failed in both places clients read it from."""
    await set_job_progress(r, job_id, status="failed", total=total, completed=0)
    await _mark_job(job_id, "failed")


async def run_slice(r: redis.Redis, blobs: BlobStore, job_id: str, index: int) -> int | None:
    """Run slice `index` of `job_id`. Returns the next slice's index, or None when the job is over
    (finished, failed, or already finished by an earlier delivery)."""
    progress = await get_job_progress(r, job_id)
    if progress is not None and progress["status"] in ("done", "failed"):
        return None

    raw = await blobs.get(input_key(job_id))
    if raw is None:
        await fail_job(r, job_id)
        return None
    payload = json.loads(raw)
    smiles_list: list[str] = payload["smiles"]
    endpoints = [Endpoint(e) for e in payload["endpoints"]] if payload["endpoints"] else None
    total = len(smiles_list)
    size = get_settings().batch_slice_rows
    start = index * size
    stop = min(start + size, total)

    if await blobs.get(slice_key(job_id, index)) is None:
        rows: list[BatchRowResult] = []
        for i in range(start, stop):
            rows.append(await run_prediction(predict_row, i, smiles_list[i], endpoints))
            await set_job_progress(r, job_id, status="running", total=total, completed=i + 1)
        await blobs.put(slice_key(job_id, index), json.dumps([row.model_dump(mode="json") for row in rows]))
    await set_job_progress(r, job_id, status="running", total=total, completed=stop)

    if stop < total:
        return index + 1

    slices = -(-total // size)
    results: list[BatchRowResult] = []
    for k in range(slices):
        part = await blobs.get(slice_key(job_id, k))
        if part is None:
            await fail_job(r, job_id, total)
            return None
        results.extend(BatchRowResult.model_validate(row) for row in json.loads(part))
    response = BatchPredictResponse(job_id=job_id, status="done", total=total, completed=total, results=results)
    await blobs.put(results_key(job_id), response.model_dump_json())
    await set_job_progress(r, job_id, status="done", total=total, completed=total)
    await _mark_job(job_id, "done")
    await blobs.delete(input_key(job_id), *(slice_key(job_id, k) for k in range(slices)))
    return None


async def run_job(r: redis.Redis, blobs: BlobStore, job_id: str) -> None:
    """Run every slice in this process. Used by `LocalTaskQueue`. Failures are written back as
    `failed` rather than left to vanish inside a background task, which would strand the job at
    "queued" or "running" forever."""
    try:
        index: int | None = 0
        while index is not None:
            index = await run_slice(r, blobs, job_id, index)
    except Exception:
        await fail_job(r, job_id)


async def _run_local(job_id: str) -> None:
    # The request that enqueued the job has returned, so this task needs its own Redis client.
    r = get_redis()
    try:
        await run_job(r, get_blob_store(r), job_id)
    finally:
        await r.aclose()


_local_queue: LocalTaskQueue | None = None


def get_task_queue() -> TaskQueue:
    global _local_queue
    settings = get_settings()
    if settings.batch_queue_backend == "cloud_tasks":
        return CloudTasksQueue(settings)
    if _local_queue is None:
        _local_queue = LocalTaskQueue(_run_local)
    return _local_queue
