import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException
from mars_contracts import PredictionRequest, PredictionResponse

from app.services.molecule_lookup import register_molecule
from app.services.prediction_cache import (
    build_cache_key,
    get_cached_prediction,
    set_cached_prediction,
)
from app.services.prediction_service import predict as predict_service
from app.services.rate_limit import enforce_predict_rate_limit
from app.services.redis_client import get_redis

router = APIRouter()


@router.post("", response_model=PredictionResponse)
async def predict(
    req: PredictionRequest,
    r: redis.Redis = Depends(get_redis),
    _rate_limit: None = Depends(enforce_predict_rate_limit),
) -> PredictionResponse:
    if not req.smiles or not req.smiles.strip():
        raise HTTPException(status_code=422, detail="smiles must be a non-empty string")

    key = build_cache_key(req.smiles, req.endpoints)
    cached = await get_cached_prediction(r, key)
    if cached is not None:
        # Still (re-)register on a cache hit: an entry cached before this
        # molecule_id -> smiles mapping existed (or one whose mapping already
        # expired independently of the prediction cache) would otherwise
        # leave GET /molecule/{id}/3d permanently 404ing for it.
        await register_molecule(r, cached.molecule_id, cached.smiles_standardized)
        return cached

    try:
        response = predict_service(req.smiles, req.endpoints)
    except ValueError as exc:
        # Module 3 Stage 1 validation (real RDKit standardization) rejects
        # invalid SMILES with a clear error — only enforced when the real ml
        # stack is present (see prediction_service.py's module docstring).
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await set_cached_prediction(r, key, response)
    # Registers molecule_id -> smiles so GET /molecule/{id}/3d can look it up
    # later (Module 8) — same cache window as the prediction itself.
    await register_molecule(r, response.molecule_id, response.smiles_standardized)
    return response
