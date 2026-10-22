"""The Cloud Tasks worker endpoint: `POST /api/internal/batch/run` runs one slice of a batch job.

Cloud Tasks calls it once per slice (see `services/task_queue.py`). It is not for browsers, so it is
left out of the OpenAPI schema, and because the Cloud Run service is public it protects itself:

* it does not exist (404) unless `BATCH_QUEUE_BACKEND=cloud_tasks`;
* it refuses everything (503) while `BATCH_WORKER_SECRET` is unset, rather than running open;
* it compares the `X-MARS-Worker-Secret` header in constant time.

Status codes are the queue's retry protocol: a 2xx finishes the task, anything else is retried with
Cloud Tasks' backoff. After the last attempt the job is marked failed and the task is answered 200, so
the client sees "failed" instead of a job stuck at "running".
"""

from __future__ import annotations

import hmac
import uuid

import redis.asyncio as redis
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.services.batch_runner import fail_job, get_task_queue, run_slice
from app.services.blob_store import get_blob_store
from app.services.redis_client import get_redis

router = APIRouter(include_in_schema=False)


class RunSliceRequest(BaseModel):
    job_id: str
    index: int = Field(ge=0)


@router.post("/run")
async def run(
    req: RunSliceRequest,
    r: redis.Redis = Depends(get_redis),
    x_mars_worker_secret: str | None = Header(default=None),
    x_cloudtasks_taskretrycount: int = Header(default=0),
) -> dict:
    settings = get_settings()
    if settings.batch_queue_backend != "cloud_tasks":
        raise HTTPException(status_code=404, detail="Not found")
    if not settings.batch_worker_secret:
        raise HTTPException(status_code=503, detail="Worker endpoint is not configured")
    if not hmac.compare_digest((x_mars_worker_secret or "").encode(), settings.batch_worker_secret.encode()):
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        uuid.UUID(req.job_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="job_id must be a UUID") from None

    try:
        next_index = await run_slice(r, get_blob_store(r), req.job_id, req.index)
        if next_index is not None:
            await get_task_queue().enqueue(req.job_id, next_index)
    except Exception:
        if x_cloudtasks_taskretrycount + 1 >= settings.batch_task_max_attempts:
            await fail_job(r, req.job_id)
            return {"next": None, "failed": True}
        raise  # 500: Cloud Tasks retries this slice; the part that already succeeded is not redone
    return {"next": next_index}
