"""`POST /depict` (frontend ADR-039) - a plain black-line 2D drawing of a molecule as `image/svg+xml`, no account needed.

The drawing says what the molecule looks like and nothing else: one ink, no element colours, no highlighted atoms, no
labels. POST rather than GET so a user's SMILES is never written into a URL (access logs, history, referrers). The cache is
keyed on the RDKit canonical SMILES and the drawing version, so every way of writing one molecule shares one entry, and a
change to the drawing options (`DEPICTION_VERSION`) makes older entries unreachable instead of serving them as the new look.
"""

from __future__ import annotations

import hashlib
import warnings

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException
from mars_contracts import DepictRequest
from starlette.responses import Response

from app.core.config import get_settings
from app.services import depiction_service
from app.services.rate_limit import enforce_depict_rate_limit
from app.services.redis_client import get_redis

router = APIRouter()

_CACHE_PREFIX = "depict_cache:"
# The body is generated from the input by RDKit and holds no script, but a drawing is never a document: if it were opened
# on its own, nothing in it may run or load.
_SVG_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
    "X-Content-Type-Options": "nosniff",
}


def _cache_key(canonical: str) -> str:
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{_CACHE_PREFIX}{depiction_service.DEPICTION_VERSION}:{digest}"


def _svg(body: str, cache: str) -> Response:
    return Response(content=body, media_type="image/svg+xml", headers={**_SVG_HEADERS, "X-Depiction-Cache": cache})


@router.post("", response_class=Response, responses={200: {"content": {"image/svg+xml": {}}}})
async def depict(
    req: DepictRequest,
    r: redis.Redis = Depends(get_redis),
    _rate_limit: None = Depends(enforce_depict_rate_limit),
) -> Response:
    if not depiction_service.depiction_available:
        raise HTTPException(status_code=501, detail="Structure drawing needs rdkit, which is not installed in this environment")
    try:
        canonical = depiction_service.canonical_smiles(req.smiles)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    key = _cache_key(canonical)
    try:
        cached = await r.get(key)
        if cached is not None:
            return _svg(cached.decode("utf-8") if isinstance(cached, bytes) else str(cached), "hit")
    except redis.RedisError as exc:
        warnings.warn(f"Depiction cache unavailable, treating as a miss: {exc}", stacklevel=2)

    try:
        svg = depiction_service.draw_svg(canonical)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        await r.set(key, svg, ex=get_settings().depiction_cache_ttl_seconds)
    except redis.RedisError as exc:
        warnings.warn(f"Could not cache a depiction: {exc}", stacklevel=2)
    return _svg(svg, "miss")
