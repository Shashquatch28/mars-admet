"""Module 8 `GET /molecule/{id}/3d` — lazy, cached, no account required
(per `contracts/API_ROUTES.md`'s route table). `{id}` only makes sense if
`/predict` has already been called for that molecule in this cache window
(that's how the id -> SMILES mapping gets registered — see
`services/molecule_lookup.py`); a cold/unknown id is a clear 404, not a
guess."""

from __future__ import annotations

import warnings

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException
from mars_contracts import ConformerResponse

from app.core.config import get_settings
from app.services.conformer_service import conformer_available, get_conformer
from app.services.molecule_lookup import lookup_molecule_smiles
from app.services.redis_client import get_redis

router = APIRouter()

_CACHE_PREFIX = "conformer_cache:"


@router.get("/{molecule_id}/3d", response_model=ConformerResponse)
async def get_molecule_3d(
    molecule_id: str,
    r: redis.Redis = Depends(get_redis),
) -> ConformerResponse:
    cache_key = f"{_CACHE_PREFIX}{molecule_id}"
    try:
        cached = await r.get(cache_key)
        if cached is not None:
            return ConformerResponse.model_validate_json(cached)
    except redis.RedisError as exc:
        warnings.warn(f"Conformer cache unavailable, treating as a miss: {exc}", stacklevel=2)

    smiles = await lookup_molecule_smiles(r, molecule_id)
    if smiles is None:
        raise HTTPException(
            status_code=404,
            detail="Unknown molecule_id — call /predict for this molecule first (or its cache entry expired)",
        )

    if not conformer_available:
        raise HTTPException(
            status_code=501, detail="Conformer generation needs rdkit, which is not installed in this environment"
        )

    try:
        response = get_conformer(molecule_id, smiles)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        await r.set(cache_key, response.model_dump_json(), ex=get_settings().prediction_cache_ttl_seconds)
    except redis.RedisError as exc:
        warnings.warn(f"Could not cache conformer: {exc}", stacklevel=2)

    return response
