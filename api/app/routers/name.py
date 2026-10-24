"""`POST /name` (frontend ADR-043) - the name of a molecule as a name source gives it, no account needed.

The SMILES stays out of the URL (POST) and out of the source: the service computes the molecule's InChIKey with RDKit and asks
the source about the key only. The answer is `found` (a name, with its source and record id), `not_found` (the source has no
record: an answer, kept for a day) or `unavailable` (the source failed, with the reason in words: never kept, so the next ask
tries again). All three are HTTP 200 for a molecule that could be parsed; 422 is a SMILES that could not be.
"""

from __future__ import annotations

import hashlib
import warnings

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, Response
from mars_contracts import NameRequest, NameResponse, NameStatus

from app.core.config import get_settings
from app.services import name_service
from app.services.rate_limit import enforce_name_rate_limit
from app.services.redis_client import get_redis

router = APIRouter()

_CACHE_PREFIX = "name_cache:"


def _cache_key(inchikey: str) -> str:
    digest = hashlib.sha256(inchikey.encode("utf-8")).hexdigest()
    return f"{_CACHE_PREFIX}{name_service.NAME_VERSION}:{digest}"


@router.post("", response_model=NameResponse)
async def name(
    req: NameRequest,
    response: Response,
    r: redis.Redis = Depends(get_redis),
    _rate_limit: None = Depends(enforce_name_rate_limit),
) -> NameResponse:
    if not name_service.name_available:
        raise HTTPException(status_code=501, detail="Naming a structure needs rdkit, which is not installed in this environment")
    try:
        key = name_service.inchikey(req.smiles)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    cache_key = _cache_key(key)
    try:
        cached = await r.get(cache_key)
        if cached is not None:
            response.headers["X-Name-Cache"] = "hit"
            return NameResponse.model_validate_json(cached)
    except (redis.RedisError, ValueError) as exc:
        warnings.warn(f"Name cache unavailable, treating as a miss: {exc}", stacklevel=2)

    result = await name_service.lookup(key)
    response.headers["X-Name-Cache"] = "miss"
    if result.cacheable:
        settings = get_settings()
        ttl = settings.name_cache_ttl_seconds if result.response.status == NameStatus.FOUND else settings.name_not_found_ttl_seconds
        try:
            await r.set(cache_key, result.response.model_dump_json(), ex=ttl)
        except redis.RedisError as exc:
            warnings.warn(f"Could not cache a name: {exc}", stacklevel=2)
    return result.response
