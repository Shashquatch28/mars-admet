"""Module 13 saved-molecules integration tests — real Postgres + Redis."""

from tests.conftest import requires_infra


def _get_prediction(client, smiles="CCO"):
    r = client.post("/predict", json={"smiles": smiles})
    assert r.status_code == 200
    return r.json()


@requires_infra
def test_save_list_delete_molecule(registered_user):
    client = registered_user["client"]
    prediction = _get_prediction(client)

    r = client.post(
        "/molecules/save",
        json={"prediction": prediction, "label": "my ethanol", "tags": ["favorite"]},
    )
    assert r.status_code == 201, r.text
    saved = r.json()
    assert saved["label"] == "my ethanol"
    assert saved["tags"] == ["favorite"]
    assert saved["smiles"] == prediction["smiles_standardized"]
    assert saved["predictions_snapshot"]["molecule_id"] == prediction["molecule_id"]

    r = client.get("/molecules")
    assert r.status_code == 200
    ids = [m["id"] for m in r.json()]
    assert saved["id"] in ids

    r = client.delete(f"/molecules/{saved['id']}")
    assert r.status_code == 204

    r = client.get("/molecules")
    assert saved["id"] not in [m["id"] for m in r.json()]


@requires_infra
def test_delete_nonexistent_molecule_404(registered_user):
    client = registered_user["client"]
    r = client.delete("/molecules/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


@requires_infra
def test_cannot_delete_another_users_molecule(client):
    """Account isolation: user A's molecule must be invisible/undeletable by user B."""
    import uuid

    def _register_and_login(email_prefix):
        email = f"{email_prefix}-{uuid.uuid4().hex[:8]}@example.com"
        password = "correct-horse-battery"
        client.post("/auth/register", json={"email": email, "password": password, "turnstile_token": "t"})
        client.post("/auth/login", json={"email": email, "password": password})
        return email, password

    email_a, password_a = _register_and_login("user-a")
    prediction = _get_prediction(client)
    saved = client.post("/molecules/save", json={"prediction": prediction}).json()
    client.post("/auth/logout")

    email_b, password_b = _register_and_login("user-b")
    r = client.delete(f"/molecules/{saved['id']}")
    assert r.status_code == 404  # not found FOR THIS USER, not a permission leak that confirms existence

    r = client.get("/molecules")
    assert saved["id"] not in [m["id"] for m in r.json()]
    client.request("DELETE", "/account", json={"password": password_b})

    client.post("/auth/login", json={"email": email_a, "password": password_a})
    client.request("DELETE", "/account", json={"password": password_a})
