"""Module 8 Redis cache for `/predict`: key = (standardized SMILES, sorted
endpoint set, model_version), TTL 48h. Model version is part of the key (not
just the response) — deploying a new model produces new keys rather than
silently serving stale predictions under the new version label.

Cache-key SMILES normalization: when the real ml/serve/ path is available
(see `prediction_service.py`), the key uses true RDKit-canonical SMILES. When
it isn't (local dev/tests without the ml stack), it falls back to a bare
`.strip()` — cheap, consistent, but NOT chemically canonical (e.g. "CCO" and
"OCC" would miss each other). This degraded mode only affects environments
that don't have real inference either, so it doesn't cost a correctness
regression on the path that matters (the deployed container, which always
has the ml stack per `api/Dockerfile`).
"""

from __future__ import annotations

import warnings

import redis.asyncio as redis
from mars_contracts import Endpoint, PredictionResponse

from app.core.config import get_settings
from app.services import prediction_service


def _cache_key_smiles(smiles: str) -> str:
    if prediction_service._ml_available:
        try:
            return prediction_service.standardize_or_raise(smiles)
        except ValueError:
            pass
    return smiles.strip()


def build_cache_key(smiles: str, endpoints: list[Endpoint] | None) -> str:
    """Computable before running inference — `model_version` here is the
    deployed serving generation (`settings.model_version`), not any one
    endpoint's per-prediction `model_id`. Deploying a new model bumps
    `MODEL_VERSION` and every key changes, so old cache entries are never
    served under a new version (they simply become unreachable, not
    invalidated in place — no explicit flush step needed)."""
    ep_part = ",".join(sorted(e.value for e in endpoints)) if endpoints else "ALL"
    return f"predict_cache:{_cache_key_smiles(smiles)}:{ep_part}:{get_settings().model_version}"


async def get_cached_prediction(r: redis.Redis, key: str) -> PredictionResponse | None:
    """Fails OPEN (returns None = cache miss) if Redis is unreachable —
    see `rate_limit.py`'s docstring for the same fail-open rationale."""
    try:
        raw = await r.get(key)
    except redis.RedisError as exc:
        warnings.warn(f"Prediction cache unavailable, treating as a miss: {exc}", stacklevel=2)
        return None
    if raw is None:
        return None
    response = PredictionResponse.model_validate_json(raw)
    response.cache_hit = True
    return response


async def set_cached_prediction(r: redis.Redis, key: str, response: PredictionResponse) -> None:
    ttl = get_settings().prediction_cache_ttl_seconds
    try:
        await r.set(key, response.model_dump_json(), ex=ttl)
    except redis.RedisError as exc:
        warnings.warn(f"Prediction cache unavailable, skipping write: {exc}", stacklevel=2)
