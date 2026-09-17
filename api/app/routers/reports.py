"""Module 13 saved reports.

Snapshot-on-save: the client POSTs back the `PredictionResponse` /
`BatchPredictResponse` it already holds (from a prior `/predict` or
`/batch/results` call) and this endpoint freezes it into `results_snapshot`
verbatim. This sidesteps the blueprint's "save-vs-purge race condition"
(Module 13) by construction rather than by re-fetching from R2 at save time:
there is no server-side re-fetch step here to race against the 24h purge,
because the full result set the client already has in hand IS the snapshot.
`source_batch_job_id` remains purely a provenance pointer (job-history
display), never re-read to build the snapshot.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from mars_contracts import SavedReportResponse, SaveReportRequest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SavedReport, User
from app.db.session import get_db
from app.deps import get_current_user

router = APIRouter()


def _to_response(row: SavedReport) -> SavedReportResponse:
    return SavedReportResponse(
        id=str(row.id),
        type=row.type,
        source_batch_job_id=str(row.source_batch_job_id) if row.source_batch_job_id else None,
        results_snapshot=row.results_snapshot,
        molecule_ids=[str(m) for m in row.molecule_ids],
        notes=row.notes,
        tags=row.tags,
        created_at=row.created_at,
    )


@router.post("/save", status_code=201, response_model=SavedReportResponse)
async def save_report(
    req: SaveReportRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SavedReportResponse:
    if req.type not in ("single", "batch"):
        raise HTTPException(status_code=422, detail='type must be "single" or "batch"')

    molecule_uuids: list[uuid.UUID] = []
    for mid in req.molecule_ids:
        try:
            molecule_uuids.append(uuid.UUID(mid))
        except ValueError:
            # molecule_ids here are FK refs into saved_molecules (uuid), not
            # the content-hash molecule_id from PredictionResponse — reject
            # clearly rather than silently dropping a malformed reference.
            raise HTTPException(status_code=422, detail=f"Invalid molecule_id: {mid!r}") from None

    source_job_uuid: uuid.UUID | None = None
    if req.source_batch_job_id:
        try:
            source_job_uuid = uuid.UUID(req.source_batch_job_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid source_batch_job_id") from None

    row = SavedReport(
        user_id=user.id,
        type=req.type,
        source_batch_job_id=source_job_uuid,
        results_snapshot=req.results.model_dump(mode="json"),
        molecule_ids=molecule_uuids,
        notes=req.notes,
        tags=req.tags,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _to_response(row)


@router.get("", response_model=list[SavedReportResponse])
async def list_saved_reports(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SavedReportResponse]:
    result = await db.execute(
        select(SavedReport).where(SavedReport.user_id == user.id).order_by(SavedReport.created_at.desc())
    )
    return [_to_response(row) for row in result.scalars().all()]


@router.delete("/{report_id}", status_code=204)
async def delete_saved_report(
    report_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        report_uuid = uuid.UUID(report_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found") from None

    result = await db.execute(
        select(SavedReport).where(SavedReport.id == report_uuid, SavedReport.user_id == user.id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Not found")

    await db.execute(delete(SavedReport).where(SavedReport.id == report_uuid))
    await db.commit()
