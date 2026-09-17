"""Module 13 auth integration tests — real Postgres + Redis."""

import uuid

from tests.conftest import requires_infra


@requires_infra
def test_register_login_logout_flow(client):
    email = f"test-{uuid.uuid4().hex[:12]}@example.com"
    password = "correct-horse-battery"

    r = client.post("/auth/register", json={"email": email, "password": password, "turnstile_token": "t"})
    assert r.status_code == 201
    user_id = r.json()["user_id"]

    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    assert r.json()["user_id"] == user_id
    assert "mars_session" in r.cookies

    r = client.get("/molecules")  # any session-gated route proves the cookie works
    assert r.status_code == 200
    assert r.json() == []

    r = client.post("/auth/logout")
    assert r.status_code == 204

    r = client.get("/molecules")
    assert r.status_code == 401

    # cleanup: log back in to delete the account
    client.post("/auth/login", json={"email": email, "password": password})
    client.request("DELETE", "/account", json={"password": password})


@requires_infra
def test_register_duplicate_email_rejected(registered_user):
    client = registered_user["client"]
    r = client.post(
        "/auth/register",
        json={"email": registered_user["email"], "password": "whatever123", "turnstile_token": "t"},
    )
    assert r.status_code == 409


@requires_infra
def test_login_wrong_password_rejected(registered_user):
    client = registered_user["client"]
    r = client.post("/auth/login", json={"email": registered_user["email"], "password": "wrong-password"})
    assert r.status_code == 401


@requires_infra
def test_unauthenticated_request_rejected(client):
    r = client.get("/molecules")
    assert r.status_code == 401


@requires_infra
def test_password_reset_request_always_202_no_enumeration(client):
    r1 = client.post("/auth/password-reset/request", json={"email": "nonexistent@example.com"})
    r2 = client.post("/auth/password-reset/request", json={"email": "also-nonexistent@example.com"})
    assert r1.status_code == 202
    assert r2.status_code == 202


@requires_infra
def test_password_reset_confirm_rejects_bad_token(client):
    r = client.post("/auth/password-reset/confirm", json={"token": "not-a-real-token", "new_password": "newpass123"})
    assert r.status_code == 400
