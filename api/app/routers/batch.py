"""Module 8 batch prediction. Two-tier design (blueprint Module 12): up to
`batch_interactive_threshold` molecules (default 100) run inline (interactive tier); more are
enqueued (async tier) — see `services/task_queue.py` for what's real vs. a documented
stub in that path. CSV always works (no rdkit needed); SDF needs rdkit,
which is only installed in the production container
(`ml/requirements-serving.txt`) — `sdf_parser.sdf_available` distinguishes
that at request time and returns 501 (not a fabricated empty result) in an
environment that can't parse it, rather than always claiming 415."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import uuid

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from mars_contracts import BatchPredictResponse, Endpoint
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from app.core.config import get_settings
from app.db.models import BatchJob, User
from app.db.session import get_db
from app.deps import get_current_user
from app.services.batch_runner import (
    fail_job,
    get_task_queue,
    now_naive_utc,
    predict_row,
    store_job_input,
)
from app.services.blob_store import get_blob_store, results_key
from app.services.prediction_pool import run_prediction
from app.services.redis_client import get_redis
from app.services.sdf_parser import parse_sdf, sdf_available
from app.services.task_queue import get_job_progress, set_job_progress

router = APIRouter()

_MAX_CONCURRENT_JOBS_PER_ACCOUNT = 5


def _parse_csv(content: bytes, smiles_column: str | None) -> list[str]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return []
    column = smiles_column or next(
        (c for c in reader.fieldnames if c.lower() == "smiles"), reader.fieldnames[0]
    )
    return [row.get(column, "") for row in reader]


@router.post("/predict", response_model=BatchPredictResponse)
async def batch_predict(
    file: UploadFile,
    smiles_column: str | None = None,
    endpoints: list[Endpoint] | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
) -> BatchPredictResponse:
    settings = get_settings()

    content = await file.read()
    is_sdf = bool(file.filename and file.filename.lower().endswith(".sdf"))
    if is_sdf:
        if not sdf_available:
            raise HTTPException(
                status_code=501,
                detail="SDF parsing needs rdkit, which is not installed in this environment — use CSV",
            )
        smiles_list = parse_sdf(content)
    else:
        smiles_list = _parse_csv(content, smiles_column)
    total = len(smiles_list)
    if total == 0:
        raise HTTPException(status_code=422, detail="No rows found (empty file or missing SMILES column)")
    if total > settings.batch_size_cap:
        raise HTTPException(status_code=422, detail=f"Batch exceeds cap of {settings.batch_size_cap} molecules")

    active_count = await db.scalar(
        select(func.count()).where(
            BatchJob.user_id == user.id, BatchJob.status.in_(["queued", "running"])
        )
    )
    if active_count is not None and active_count >= _MAX_CONCURRENT_JOBS_PER_ACCOUNT:
        raise HTTPException(
            status_code=429, detail=f"Max {_MAX_CONCURRENT_JOBS_PER_ACCOUNT} concurrent batch jobs per account"
        )

    job = BatchJob(user_id=user.id, status="queued", molecule_count=total)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    job_id = str(job.id)

    if total <= settings.batch_interactive_threshold:
        results = await run_prediction(
            lambda: [predict_row(i, s, endpoints) for i, s in enumerate(smiles_list)]
        )
        job.status = "done"
        job.completed_at = now_naive_utc()
        await db.commit()
        return BatchPredictResponse(job_id=None, status="done", total=total, completed=total, results=results)

    await store_job_input(get_blob_store(r), job_id, smiles_list, endpoints)
    await set_job_progress(r, job_id, status="queued", total=total, completed=0)
    try:
        await get_task_queue().enqueue(job_id, 0)
    except Exception:
        await fail_job(r, job_id, total)
        raise HTTPException(status_code=503, detail="Could not queue the batch job; try again shortly") from None
    return BatchPredictResponse(job_id=job_id, status="queued", total=total, completed=0, results=None)


async def _owned_job_or_404(job_id: str, user: User, db: AsyncSession) -> BatchJob:
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found") from None
    job = await db.get(BatchJob, job_uuid)
    if job is None or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    return job


@router.get("/progress/{job_id}")
async def batch_progress(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
) -> StreamingResponse:
    await _owned_job_or_404(job_id, user, db)

    async def event_stream():
        while True:
            progress = await get_job_progress(r, job_id)
            if progress is None:
                yield f"data: {json.dumps({'job_id': job_id, 'status': 'unknown'})}\n\n"
                return
            yield f"data: {json.dumps(progress)}\n\n"
            if progress["status"] in ("done", "failed"):
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/results/{job_id}", response_model=BatchPredictResponse)
async def batch_results(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    r: redis.Redis = Depends(get_redis),
) -> BatchPredictResponse:
    job = await _owned_job_or_404(job_id, user, db)
    if job.status not in ("done", "failed"):
        raise HTTPException(status_code=409, detail=f"Job is still {job.status}")

    raw = await get_blob_store(r).get(results_key(job_id))
    if raw is None:
        raise HTTPException(
            status_code=410, detail="Results have expired and are no longer available (24h retention)"
        )
    return BatchPredictResponse.model_validate_json(raw)
