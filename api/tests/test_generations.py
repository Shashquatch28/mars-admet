"""GET /generations (ADR-026): the deployed generation, anonymous, and no choice that is not real."""

from app.core.config import get_settings
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_generations_reports_only_the_deployed_generation_without_a_session():
    active = get_settings().model_version
    r = client.get("/generations")  # no cookie: anonymous like /predict
    assert r.status_code == 200
    assert r.json() == {"active": active, "available": [active]}
