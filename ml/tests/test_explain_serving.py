"""Routing an explanation to the model that serves the endpoint (ADR-031), with the KERMT service replaced
by an in-process HTTP stand-in. No torch, no checkpoints."""

from __future__ import annotations

import httpx
import pytest
from rdkit import Chem
from serve import explainer
from serve.explain_errors import ExplainUnavailable, NothingToExplain
from serve.kermt_client import KermtClient, KermtUnavailable
from serve.kermt_router import KermtRouter
from serve.routing import Route, RoutingTable

SMILES = "CC(=O)Oc1ccccc1C(=O)O"
N_ATOMS = Chem.MolFromSmiles(SMILES).GetNumAtoms()


def _reply(**over):
    body = {
        "arm": "toxicity__cls",
        "model_id": "mars-kermt-toxicity-cls-v1",
        "output_space": "score",
        "n_seeds": 3,
        "n_steps": 64,
        "base_value": 0.4,
        "output_value": 0.7,
        "baseline": "empty graph",
        "atom_scores": [0.01 * (i + 1) for i in range(N_ATOMS)],
        "descriptor_names": ["MolLogP", "TPSA"],
        "descriptor_values": [1.2, None],
        "descriptor_scores": [0.05, -0.02],
        "unmapped_total": 0.0,
    }
    body.update(over)
    return body


def _router(handler) -> KermtRouter:
    client = KermtClient("http://kermt.test", transport=httpx.MockTransport(handler))
    routing = RoutingTable(
        {
            "herg_cardiotoxicity": Route("herg_cardiotoxicity", "kermt", "toxicity__cls", ""),
            "ames_mutagenicity": Route("ames_mutagenicity", "xgboost", "toxicity__cls", ""),
        }
    )
    return KermtRouter(routing, client, registry=None)


def test_kermt_routed_endpoint_is_explained_by_the_service():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = request.content
        return httpx.Response(200, json=_reply())

    router = _router(handler)
    res = explainer.explain_endpoint(None, "herg_cardiotoxicity", SMILES, kermt=router)
    assert seen["path"] == "/explain"
    assert b'"arm":"toxicity__cls"' in seen["body"].replace(b" ", b"")
    assert res.method == "integrated_gradients" and res.model_id == "mars-kermt-toxicity-cls-v1"
    assert res.output_space == "score" and res.n_steps == 64 and res.n_seeds == 3
    assert len(res.atom_attributions) == N_ATOMS
    assert res.structure_total == pytest.approx(sum(0.01 * (i + 1) for i in range(N_ATOMS)))
    assert res.whole_molecule_total == pytest.approx(0.03)
    assert [d.name for d in res.descriptors] == ["MolLogP", "TPSA"]
    assert res.descriptors[1].value is None  # a non-finite descriptor is null, not 0
    assert res.completeness_error == pytest.approx(abs(0.4 + res.structure_total + 0.03 - 0.7))
    assert any(f.name == "ring system" for f in res.fragments)


def test_xgboost_routed_endpoint_never_goes_to_the_kermt_service(monkeypatch):
    def handler(_request):
        raise AssertionError("the KERMT service must not be called for an XGBoost-routed endpoint")

    sentinel = object()
    monkeypatch.setattr(explainer, "explain_xgboost", lambda reg, ep, smi: sentinel)
    assert explainer.explain_endpoint("registry", "ames_mutagenicity", SMILES, kermt=_router(handler)) is sentinel


def test_kermt_off_means_xgboost_explains(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(explainer, "explain_xgboost", lambda reg, ep, smi: sentinel)
    assert explainer.explain_endpoint("registry", "herg_cardiotoxicity", SMILES, kermt=None) is sentinel


def test_stub_served_endpoint_has_nothing_to_explain(monkeypatch):
    monkeypatch.setattr(explainer, "explain_xgboost", lambda reg, ep, smi: None)
    with pytest.raises(NothingToExplain):
        explainer.explain_endpoint("registry", "solubility_logs", SMILES, kermt=None)


@pytest.mark.parametrize(
    "handler",
    [
        lambda r: httpx.Response(500, text="boom"),
        lambda r: httpx.Response(200, json={"arm": "toxicity__cls"}),  # malformed
        lambda r: httpx.Response(200, json=_reply(atom_scores=[0.1, 0.2])),  # wrong atom count
        lambda r: httpx.Response(200, json=_reply(descriptor_scores=[0.1])),  # inconsistent lengths
    ],
)
def test_a_kermt_failure_is_unavailable_never_another_models_explanation(handler, monkeypatch):
    monkeypatch.setattr(explainer, "explain_xgboost", lambda *a: pytest.fail("must not fall back to XGBoost"))
    with pytest.raises(ExplainUnavailable):
        explainer.explain_endpoint(None, "herg_cardiotoxicity", SMILES, kermt=_router(handler))


def test_a_failed_explanation_does_not_open_the_prediction_breaker():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(500, text="boom") if request.url.path == "/explain" else httpx.Response(200, json={"arms": {}})

    router = _router(handler)
    with pytest.raises(KermtUnavailable):
        router.explain(SMILES, "herg_cardiotoxicity")
    with pytest.raises(KermtUnavailable):
        router.explain(SMILES, "herg_cardiotoxicity")
    assert calls == ["/explain", "/explain"]  # the second call still reached the service


def test_open_prediction_breaker_gates_explanations():
    router = _router(lambda r: httpx.Response(200, json=_reply()))
    router.client._down_until = float("inf")
    with pytest.raises(KermtUnavailable):
        router.explain(SMILES, "herg_cardiotoxicity")


def test_explaining_an_endpoint_not_routed_to_kermt_is_a_programming_error():
    with pytest.raises(ValueError):
        _router(lambda r: httpx.Response(200, json=_reply())).explain(SMILES, "ames_mutagenicity")
