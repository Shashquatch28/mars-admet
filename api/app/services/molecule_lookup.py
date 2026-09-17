"""Module 8 `GET /molecule/{id}/3d` needs to go from `molecule_id` (a hash of
the standardized SMILES, per `PredictionResponse.molecule_id`) back to the
SMILES itself. `/predict` registers this mapping in Redis (same TTL as the
prediction cache — both represent "how long we still know about this
molecule") every time it serves a response; `/molecule/{id}/3d` reads it.

Fails open the same way prediction_cache.py does: if Redis is down, lookups
just report "unknown molecule" rather than 500ing.
"""

from __future__ import annotations

import warnings

import redis.asyncio as redis

from app.core.config import get_settings

_KEY_PREFIX = "molecule_smiles:"


async def register_molecule(r: redis.Redis, molecule_id: str, smiles_standardized: str) -> None:
    try:
        await r.set(f"{_KEY_PREFIX}{molecule_id}", smiles_standardized, ex=get_settings().prediction_cache_ttl_seconds)
    except redis.RedisError as exc:
        warnings.warn(f"Could not register molecule_id for 3D lookup: {exc}", stacklevel=2)


async def lookup_molecule_smiles(r: redis.Redis, molecule_id: str) -> str | None:
    try:
        return await r.get(f"{_KEY_PREFIX}{molecule_id}")
    except redis.RedisError as exc:
        warnings.warn(f"Molecule lookup unavailable: {exc}", stacklevel=2)
        return None
