from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from mars_contracts import SavedMoleculeResponse, SaveMoleculeRequest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SavedMolecule, User
from app.db.session import get_db
from app.deps import get_current_user

router = APIRouter()


def _to_response(row: SavedMolecule) -> SavedMoleculeResponse:
    return SavedMoleculeResponse(
        id=str(row.id),
        smiles=row.smiles,
        label=row.label,
        notes=row.notes,
        tags=row.tags,
        predictions_snapshot=row.predictions_snapshot,
        model_version=row.model_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/save", status_code=201, response_model=SavedMoleculeResponse)
async def save_molecule(
    req: SaveMoleculeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SavedMoleculeResponse:
    row = SavedMolecule(
        user_id=user.id,
        smiles=req.prediction.smiles_standardized,
        label=req.label,
        notes=req.notes,
        tags=req.tags,
        predictions_snapshot=req.prediction.model_dump(mode="json"),
        model_version=req.prediction.model_version,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _to_response(row)


@router.get("", response_model=list[SavedMoleculeResponse])
async def list_saved_molecules(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SavedMoleculeResponse]:
    result = await db.execute(
        select(SavedMolecule).where(SavedMolecule.user_id == user.id).order_by(SavedMolecule.created_at.desc())
    )
    return [_to_response(row) for row in result.scalars().all()]


@router.delete("/{molecule_id}", status_code=204)
async def delete_saved_molecule(
    molecule_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        mol_uuid = uuid.UUID(molecule_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found") from None

    result = await db.execute(
        select(SavedMolecule).where(SavedMolecule.id == mol_uuid, SavedMolecule.user_id == user.id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Not found")

    await db.execute(delete(SavedMolecule).where(SavedMolecule.id == mol_uuid))
    await db.commit()
