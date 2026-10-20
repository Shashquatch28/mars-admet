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
from mars_contracts import ConformerResponse, Endpoint, ExplainResponse

from app.core.config import get_settings
from app.services.conformer_service import conformer_available, get_conformer
from app.services.explanation_service import (
    ExplainUnavailable,
    NothingToExplain,
    explain,
    explain_available,
)
from app.services.molecule_lookup import lookup_molecule_smiles
from app.services.prediction_pool import run_explanation
from app.services.prediction_service import serving_version
from app.services.rate_limit import enforce_predict_rate_limit
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


_EXPLAIN_PREFIX = "explain_cache:"


@router.get("/{molecule_id}/explain", response_model=ExplainResponse)
async def get_molecule_explanation(
    molecule_id: str,
    endpoint: Endpoint,
    r: redis.Redis = Depends(get_redis),
    _rate_limit: None = Depends(enforce_predict_rate_limit),
) -> ExplainResponse:
    """Module 6 / ADR-031: explain the value the serving model gave this endpoint, computed on request.

    404 unknown or expired molecule; 409 nothing to explain (stub-served, or the rule-based SA score);
    422 the molecule cannot be explained; 501 no ml stack here; 503 the serving model cannot explain
    right now (never swapped for a different model's explanation, and never cached).
    """
    if endpoint == Endpoint.SA_SCORE:
        raise HTTPException(status_code=409, detail="synthetic_accessibility is a computed rule, not a model: there is nothing to explain")
    if not explain_available:
        raise HTTPException(status_code=501, detail="Explanations need the ml stack (rdkit, xgboost), which is not installed in this environment")

    cache_key = f"{_EXPLAIN_PREFIX}{serving_version()}:{molecule_id}:{endpoint.value}"
    try:
        cached = await r.get(cache_key)
        if cached is not None:
            return ExplainResponse.model_validate_json(cached)
    except redis.RedisError as exc:
        warnings.warn(f"Explanation cache unavailable, treating as a miss: {exc}", stacklevel=2)

    smiles = await lookup_molecule_smiles(r, molecule_id)
    if smiles is None:
        raise HTTPException(
            status_code=404,
            detail="Unknown molecule_id — call /predict for this molecule first (or its cache entry expired)",
        )

    try:
        response = await run_explanation(explain, molecule_id, smiles, endpoint)
    except NothingToExplain as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ExplainUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        await r.set(cache_key, response.model_dump_json(), ex=get_settings().prediction_cache_ttl_seconds)
    except redis.RedisError as exc:
        warnings.warn(f"Could not cache explanation: {exc}", stacklevel=2)
    return response
