"""Module 8 `GET /molecule/{id}/3d` integration tests — real Redis (no
account needed, matches the blueprint's route table). Conformer generation
itself needs rdkit, not installed in this test environment (root `.venv`,
see mars-aims-and-envs.md) — so the real-generation path is asserted via the
501 branch here and separately container-verified (see context.md)."""

from app.services.conformer_service import conformer_available
from tests.conftest import requires_infra


@requires_infra
def test_unknown_molecule_id_404(client):
    r = client.get("/molecule/0000000000000000/3d")
    assert r.status_code == 404


@requires_infra
def test_known_molecule_without_rdkit_returns_501(client):
    if conformer_available:
        import pytest

        pytest.skip("rdkit is installed in this environment — this test only covers the without-rdkit path")

    predicted = client.post("/predict", json={"smiles": "CCO"}).json()
    molecule_id = predicted["molecule_id"]

    # Redis is a real, shared instance (docker-compose) — a prior run of the
    # BUILT container (which does have rdkit) may have already cached a real
    # conformer for this same content-addressed molecule_id. Clear it first
    # so this test genuinely exercises the without-rdkit path rather than
    # incidentally serving a stale real cache entry.
    import asyncio

    from app.services.redis_client import get_redis

    asyncio.run(get_redis().delete(f"conformer_cache:{molecule_id}"))

    r = client.get(f"/molecule/{molecule_id}/3d")
    assert r.status_code == 501
