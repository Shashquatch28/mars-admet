"""Module 13 saved-reports integration tests — real Postgres + Redis."""

from tests.conftest import requires_infra


@requires_infra
def test_save_list_delete_single_report(registered_user):
    client = registered_user["client"]
    prediction = client.post("/predict", json={"smiles": "CCO"}).json()

    r = client.post(
        "/reports/save",
        json={"type": "single", "results": prediction, "molecule_ids": [], "tags": ["batch1"]},
    )
    assert r.status_code == 201, r.text
    saved = r.json()
    assert saved["type"] == "single"
    assert saved["results_snapshot"]["molecule_id"] == prediction["molecule_id"]

    r = client.get("/reports")
    assert saved["id"] in [rep["id"] for rep in r.json()]

    r = client.delete(f"/reports/{saved['id']}")
    assert r.status_code == 204
    r = client.get("/reports")
    assert saved["id"] not in [rep["id"] for rep in r.json()]


@requires_infra
def test_save_report_rejects_bad_type(registered_user):
    client = registered_user["client"]
    prediction = client.post("/predict", json={"smiles": "CCO"}).json()
    r = client.post("/reports/save", json={"type": "not-a-real-type", "results": prediction})
    assert r.status_code == 422
