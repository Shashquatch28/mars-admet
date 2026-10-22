"""Computed molecule properties on the /predict response (frontend ADR-034 item 3).

The RDKit calculations are tested in ml/tests/test_serve_properties.py (the root env has no RDKit). Here: how the API
attaches them, that nothing breaks when they are missing, and that the cache key follows the response shape."""

from types import SimpleNamespace

from app.services import prediction_cache
from app.services import prediction_service as ps
from app.services.stub_predictor import predict_stub
from mars_contracts import ALL_ENDPOINTS, Endpoint, PredictionResponse

FAKE = SimpleNamespace(
    mol_weight=381.4,
    crippen_logp=3.5,
    h_bond_donors=1,
    h_bond_acceptors=3,
    tpsa=78.0,
    rotatable_bonds=3,
    qed=0.75,
    lipinski_criteria_exceeded=0,
    alerts=(("PAINS", "ene_rhod_A(235)"), ("Brenk", "nitro group")),
)


def _response() -> PredictionResponse:
    return predict_stub("CCO", ALL_ENDPOINTS)


def test_properties_are_attached_with_their_alerts(monkeypatch):
    monkeypatch.setattr(ps, "_ml_available", True)
    monkeypatch.setattr(ps, "compute_properties", lambda smiles: FAKE, raising=False)
    r = ps._add_properties(_response())
    assert r.properties is not None
    assert r.properties.mol_weight == 381.4
    assert r.properties.qed == 0.75
    assert [(a.catalog, a.name) for a in r.properties.alerts] == [("PAINS", "ene_rhod_A(235)"), ("Brenk", "nitro group")]


def test_properties_do_not_depend_on_which_endpoints_were_asked_for(monkeypatch):
    monkeypatch.setattr(ps, "_ml_available", True)
    monkeypatch.setattr(ps, "compute_properties", lambda smiles: FAKE, raising=False)
    one = predict_stub("CCO", [Endpoint.SOLUBILITY])
    assert ps._add_properties(one).properties is not None


def test_a_missing_qed_stays_null(monkeypatch):
    monkeypatch.setattr(ps, "_ml_available", True)
    monkeypatch.setattr(ps, "compute_properties", lambda smiles: SimpleNamespace(**{**FAKE.__dict__, "qed": None}), raising=False)
    assert ps._add_properties(_response()).properties.qed is None


def test_without_the_ml_stack_properties_stay_null(monkeypatch):
    monkeypatch.setattr(ps, "_ml_available", False)
    assert ps._add_properties(_response()).properties is None


def test_an_unparseable_molecule_or_a_failure_leaves_them_null_and_never_raises(monkeypatch):
    monkeypatch.setattr(ps, "_ml_available", True)
    monkeypatch.setattr(ps, "compute_properties", lambda smiles: None, raising=False)
    assert ps._add_properties(_response()).properties is None

    def boom(smiles):
        raise RuntimeError("descriptor failure")

    monkeypatch.setattr(ps, "compute_properties", boom, raising=False)
    assert ps._add_properties(_response()).properties is None  # a prediction is never turned into a 500


def test_a_response_cached_before_properties_existed_still_loads():
    raw = _response().model_dump_json(exclude={"properties"})
    assert PredictionResponse.model_validate_json(raw).properties is None


def test_the_cache_key_carries_the_response_shape(monkeypatch):
    monkeypatch.setattr(ps, "_ml_available", False)
    key = prediction_cache.build_cache_key("CCO", None)
    assert key.endswith(f":{prediction_cache.RESPONSE_SHAPE}")
    assert prediction_cache.RESPONSE_SHAPE != "r1"  # entries written before `properties` existed are unreachable
