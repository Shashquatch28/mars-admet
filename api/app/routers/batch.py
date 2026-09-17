"""Module 8 batch prediction. Two-tier design (blueprint Module 12): <=1000
molecules run synchronously inline (interactive tier); >1000 are enqueued
(async tier) — see `services/task_queue.py` for what's real vs. a documented
stub in that path. CSV always works (no rdkit needed); SDF needs rdkit,
which is only installed in the production container
(`ml/requirements-serving.txt`) — `sdf_parser.sdf_available` distinguishes
that at request time and returns 501 (not a fabricated empty result) in an
environment that can't parse it, rather than always claiming 415."""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import UTC, datetime

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from mars_contracts import BatchPredictResponse, BatchRowResult, Endpoint
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from app.core.config import get_settings
from app.db.models import BatchJob, User
from app.db.session import SessionLocal, get_db
from app.deps import get_current_user
from app.services.batch_results import load_batch_results, store_batch_results
from app.services.prediction_service import predict as predict_one
from app.services.redis_client import get_redis
from app.services.sdf_parser import parse_sdf, sdf_available
from app.services.task_queue import LocalTaskQueue, get_job_progress, set_job_progress

router = APIRouter()
_queue = LocalTaskQueue()

_MAX_CONCURRENT_JOBS_PER_ACCOUNT = 5


def _now_naive_utc() -> datetime:
    """`batch_jobs.completed_at` is a naive `TIMESTAMP WITHOUT TIME ZONE`
    column — asyncpg rejects a tz-aware value against it ("can't subtract
    offset-naive and offset-aware datetimes"). Store naive UTC consistently
    rather than adding `timezone=True` to one column and not others."""
    return datetime.now(UTC).replace(tzinfo=None)


def _predict_row(row_index: int, smiles: str, endpoints: list[Endpoint] | None) -> BatchRowResult:
    if not smiles or not smiles.strip():
        return BatchRowResult(row_index=row_index, smiles_input=smiles, ok=False, error="empty SMILES")
    try:
        prediction = predict_one(smiles, endpoints)
    except ValueError as exc:
        return BatchRowResult(row_index=row_index, smiles_input=smiles, ok=False, error=str(exc))
    return BatchRowResult(row_index=row_index, smiles_input=smiles, ok=True, prediction=prediction)


def _parse_csv(content: bytes, smiles_column: str | None) -> list[str]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return []
    column = smiles_column or next(
        (c for c in reader.fieldnames if c.lower() == "smiles"), reader.fieldnames[0]
    )
    return [row.get(column, "") for row in reader]


async def _run_async_job(job_id: str, smiles_list: list[str], endpoints: list[Endpoint] | None) -> None:
    """Background job body — its own Redis client and DB session, since the
    request that enqueued it has already returned. This is a fire-and-forget
    `asyncio.create_task` (see `LocalTaskQueue`) — an uncaught exception here
    would otherwise vanish into the event loop's default exception handler
    and leave the job stuck at "queued"/"running" forever, so failures are
    caught explicitly and written back as `status="failed"`."""
    from app.services.redis_client import get_redis as _get_redis

    r = _get_redis()
    total = len(smiles_list)
    try:
        await set_job_progress(r, job_id, status="running", total=total, completed=0)

        results: list[BatchRowResult] = []
        for i, smiles in enumerate(smiles_list):
            results.append(_predict_row(i, smiles, endpoints))
            await set_job_progress(r, job_id, status="running", total=total, completed=i + 1)

        response = BatchPredictResponse(job_id=job_id, status="done", total=total, completed=total, results=results)
        await store_batch_results(r, job_id, response.model_dump_json())
        await set_job_progress(r, job_id, status="done", total=total, completed=total)
        final_status = "done"
    except Exception:
        await set_job_progress(r, job_id, status="failed", total=total, completed=0)
        final_status = "failed"

    async with SessionLocal() as session:
        job = await session.get(BatchJob, uuid.UUID(job_id))
        if job is not None:
            job.status = final_status
            job.completed_at = _now_naive_utc()
            await session.commit()


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
        results = [_predict_row(i, s, endpoints) for i, s in enumerate(smiles_list)]
        job.status = "done"
        job.completed_at = _now_naive_utc()
        await db.commit()
        return BatchPredictResponse(job_id=None, status="done", total=total, completed=total, results=results)

    await set_job_progress(r, job_id, status="queued", total=total, completed=0)
    await _queue.enqueue(job_id, lambda: _run_async_job(job_id, smiles_list, endpoints))
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
        import asyncio

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

    raw = await load_batch_results(r, job_id)
    if raw is None:
        raise HTTPException(
            status_code=410, detail="Results have expired and are no longer available (24h retention)"
        )
    return BatchPredictResponse.model_validate_json(raw)
