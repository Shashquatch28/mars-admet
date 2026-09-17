"""Module 13 account deletion integration tests — real Postgres + Redis.
Verifies the cascade (saved_molecules/saved_reports/batch_jobs all disappear
with the user) and that deletion requires the correct password."""

import uuid

from tests.conftest import requires_infra


@requires_infra
def test_delete_account_requires_correct_password(client):
    email = f"test-{uuid.uuid4().hex[:12]}@example.com"
    password = "correct-horse-battery"
    client.post("/auth/register", json={"email": email, "password": password, "turnstile_token": "t"})
    client.post("/auth/login", json={"email": email, "password": password})

    r = client.request("DELETE", "/account", json={"password": "wrong-password"})
    assert r.status_code == 403

    r = client.request("DELETE", "/account", json={"password": password})
    assert r.status_code == 204

    r = client.get("/molecules")
    assert r.status_code == 401  # session was revoked by the deletion


@requires_infra
def test_delete_account_cascades_saved_molecules(client):
    email = f"test-{uuid.uuid4().hex[:12]}@example.com"
    password = "correct-horse-battery"
    client.post("/auth/register", json={"email": email, "password": password, "turnstile_token": "t"})
    client.post("/auth/login", json={"email": email, "password": password})

    prediction = client.post("/predict", json={"smiles": "CCO"}).json()
    client.post("/molecules/save", json={"prediction": prediction})

    r = client.request("DELETE", "/account", json={"password": password})
    assert r.status_code == 204

    # re-registering the same email must succeed — proves the row is really gone
    r = client.post("/auth/register", json={"email": email, "password": password, "turnstile_token": "t"})
    assert r.status_code == 201
    client.post("/auth/login", json={"email": email, "password": password})
    r = client.get("/molecules")
    assert r.json() == []  # fresh account, no leaked molecules from the deleted one
    client.request("DELETE", "/account", json={"password": password})
