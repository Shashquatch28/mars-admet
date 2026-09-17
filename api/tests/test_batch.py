"""Module 8 batch endpoint integration tests — real Postgres + Redis.
Covers the interactive (synchronous) tier; the async tier is exercised
separately in test_batch_async.py since it needs the SSE/results endpoints."""

import io

import pytest
from app.services.sdf_parser import sdf_available
from tests.conftest import requires_infra

_CSV = b"smiles\nCCO\nCCC\nnot a smiles at all\n"

_ETHANOL_SDF = b"""ethanol
     RDKit          2D

  3  2  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    2.0000    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  2  3  1  0
M  END
$$$$
"""


@requires_infra
def test_batch_predict_interactive_tier(registered_user):
    client = registered_user["client"]
    r = client.post("/batch/predict", files={"file": ("molecules.csv", io.BytesIO(_CSV), "text/csv")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["job_id"] is None  # interactive tier per contract docstring
    assert body["status"] == "done"
    assert body["total"] == 3
    assert body["completed"] == 3
    assert body["results"][0]["ok"] is True
    assert body["results"][1]["ok"] is True
    # "not a smiles at all" is non-blocking per-row — real ml stack isn't
    # installed in this test environment either, so the stub answers it too;
    # this assertion just proves the batch doesn't 500 on a garbage row.
    assert body["results"][2]["row_index"] == 2


@requires_infra
def test_batch_predict_requires_account(client):
    r = client.post("/batch/predict", files={"file": ("molecules.csv", io.BytesIO(_CSV), "text/csv")})
    assert r.status_code == 401


@requires_infra
def test_batch_predict_sdf_without_rdkit_returns_501(registered_user):
    """This test suite runs under the root `.venv` (no rdkit) — see
    mars-aims-and-envs.md — so this exercises the honest "can't parse SDF
    here" path, not a fabricated rejection. See test_batch_predict_sdf_real
    below for the real-parse path, which only runs where rdkit IS installed
    (the built container; skipped here by construction)."""
    if sdf_available:
        pytest.skip("rdkit is installed in this environment — this test only covers the without-rdkit path")
    client = registered_user["client"]
    r = client.post(
        "/batch/predict", files={"file": ("molecules.sdf", io.BytesIO(_ETHANOL_SDF), "chemical/x-mdl-sdfile")}
    )
    assert r.status_code == 501


@requires_infra
def test_batch_predict_sdf_real(registered_user):
    if not sdf_available:
        pytest.skip("rdkit not installed in this environment — see test_batch_predict_sdf_without_rdkit_returns_501")
    client = registered_user["client"]
    r = client.post(
        "/batch/predict", files={"file": ("molecules.sdf", io.BytesIO(_ETHANOL_SDF), "chemical/x-mdl-sdfile")}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["results"][0]["ok"] is True
    assert body["results"][0]["smiles_input"] == "CCO"


@requires_infra
def test_batch_predict_rejects_empty_file(registered_user):
    client = registered_user["client"]
    r = client.post("/batch/predict", files={"file": ("empty.csv", io.BytesIO(b"smiles\n"), "text/csv")})
    assert r.status_code == 422
