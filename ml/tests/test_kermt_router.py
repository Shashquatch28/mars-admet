"""KermtRouter + predictor integration, with fake client and registry (no service, no artifacts)."""

from __future__ import annotations

import numpy as np
import pytest
from serve.kermt_client import ArmValues, KermtUnavailable
from serve.kermt_router import KermtRouter
from serve.predictor import predict_endpoints
from serve.registry import KERMT_ERROR_BAND_FILENAME
from serve.routing import KERMT_ARMS, RoutingTable

CLS_ARM, CLS_EP = "toxicity__cls", "herg_cardiotoxicity"
REG_ARM, REG_EP = "metabolism__reg", "clearance_microsomal"


class _Band:
    halfwidth, level, n_residuals = 12.5, 0.9, 321


class _Registry:
    """What predict_endpoint (XGBoost path) and the router read."""

    def __init__(self):
        self.band_requests: list[tuple[str, str]] = []

    def load_models(self, endpoint_key):
        class M:
            model_id = "xgb-fake"

            def predict(self, smiles):
                return np.array([0.25])

        return [M()]

    def load_calibrator(self, endpoint_key):
        return None

    def load_ad_index(self, endpoint_key):
        return None

    def load_error_band(self, endpoint_key, filename="error_band.json"):
        self.band_requests.append((endpoint_key, filename))
        return _Band() if filename == KERMT_ERROR_BAND_FILENAME and endpoint_key == REG_EP else None


class _Client:
    def __init__(self, replies=None, raises=False):
        self.replies, self.raises, self.calls = replies or {}, raises, []

    def predict(self, smiles, arms):
        self.calls.append((smiles, list(arms)))
        if self.raises:
            raise KermtUnavailable("down")
        return {a: self.replies[a] for a in arms}


def _routing(*kermt_endpoints: str) -> RoutingTable:
    arm_of = {e: a for a, eps in KERMT_ARMS.items() for e in eps}
    from mars_contracts.endpoints import ML_ENDPOINTS
    from serve.routing import Route

    return RoutingTable({
        ep.value: Route(ep.value, "kermt" if ep.value in kermt_endpoints else "xgboost", arm_of[ep.value], "t")
        for ep in ML_ENDPOINTS
    })


def _arm(arm, task, values, seeds=(0, 1, 2)):
    return ArmValues(arm=arm, model_id="mars-kermt-multitask-v1", task_type=task, seeds=list(seeds), values=values)


def test_ensembles_seeds_like_the_xgboost_path():
    client = _Client({CLS_ARM: _arm(CLS_ARM, "classification", {CLS_EP: [0.2, 0.4, 0.6], "ames_mutagenicity": [0.1, 0.1, 0.1]})})
    router = KermtRouter(_routing(CLS_EP), client, _Registry())
    pred = router.predict("CCO", [CLS_EP])[CLS_EP]
    assert pred.value == pytest.approx(0.4)
    assert pred.confidence_low == pytest.approx(0.4 - np.std([0.2, 0.4, 0.6]))
    assert pred.confidence_high == pytest.approx(0.4 + np.std([0.2, 0.4, 0.6]))
    assert pred.n_seeds == 3
    assert pred.model_id == "mars-kermt-multitask-v1"
    assert pred.heldout_error_halfwidth is None  # classification never carries a band


def test_only_kermt_routed_endpoints_are_asked_and_one_call_per_arm():
    client = _Client({CLS_ARM: _arm(CLS_ARM, "classification", {CLS_EP: [0.5], "ames_mutagenicity": [0.5]})})
    router = KermtRouter(_routing(CLS_EP), client, _Registry())
    out = router.predict("CCO", [CLS_EP, "ames_mutagenicity", "hia_absorption"])
    assert set(out) == {CLS_EP}  # ames and hia are routed to XGBoost
    assert client.calls == [("CCO", [CLS_ARM])]


def test_nothing_routed_to_kermt_means_no_service_call():
    client = _Client()
    assert KermtRouter(_routing(), client, _Registry()).predict("CCO", [CLS_EP]) == {}
    assert client.calls == []


def test_regression_row_carries_the_kermt_band_not_the_xgboost_band():
    reg = _Registry()
    client = _Client({REG_ARM: _arm(REG_ARM, "regression", {REG_EP: [20.0, 22.0]}, seeds=(0, 1))})
    pred = KermtRouter(_routing(REG_EP), client, reg).predict("CCO", [REG_EP])[REG_EP]
    assert (pred.heldout_error_halfwidth, pred.heldout_error_level, pred.heldout_error_n) == (12.5, 0.9, 321)
    assert reg.band_requests == [(REG_EP, KERMT_ERROR_BAND_FILENAME)]


def test_service_down_returns_nothing_so_the_caller_falls_back():
    router = KermtRouter(_routing(CLS_EP), _Client(raises=True), _Registry())
    assert router.predict("CCO", [CLS_EP]) == {}


def test_seed_without_value_is_dropped_and_all_missing_is_not_answered():
    client = _Client({CLS_ARM: _arm(CLS_ARM, "classification", {CLS_EP: [0.2, None, 0.6], "ames_mutagenicity": [None, None, None]})})
    router = KermtRouter(_routing(CLS_EP, "ames_mutagenicity"), client, _Registry())
    out = router.predict("CCO", [CLS_EP, "ames_mutagenicity"])
    assert out[CLS_EP].n_seeds == 2 and out[CLS_EP].value == pytest.approx(0.4)
    assert "ames_mutagenicity" not in out


def test_task_type_disagreeing_with_the_contract_is_refused():
    client = _Client({CLS_ARM: _arm(CLS_ARM, "regression", {CLS_EP: [3.0]})})
    assert KermtRouter(_routing(CLS_EP), client, _Registry()).predict("CCO", [CLS_EP]) == {}


def test_predict_endpoints_mixes_kermt_and_xgboost_and_falls_back(monkeypatch):
    monkeypatch.setattr("serve.predictor.standardize_or_raise", lambda s: s)
    client = _Client({CLS_ARM: _arm(CLS_ARM, "classification", {CLS_EP: [0.9], "ames_mutagenicity": [0.9]})})
    registry = _Registry()
    router = KermtRouter(_routing(CLS_EP), client, registry)

    mixed = predict_endpoints(registry, "CCO", [CLS_EP, "ames_mutagenicity"], kermt=router)
    assert mixed[CLS_EP].model_id == "mars-kermt-multitask-v1" and mixed[CLS_EP].value == pytest.approx(0.9)
    assert mixed["ames_mutagenicity"].model_id == "xgb-fake"

    client.raises = True  # service goes down: the KERMT-routed endpoint is still answered, by XGBoost
    degraded = predict_endpoints(registry, "CCO", [CLS_EP], kermt=router)
    assert degraded[CLS_EP].model_id == "xgb-fake"

    plain = predict_endpoints(registry, "CCO", [CLS_EP])  # no router at all: the pre-KERMT behaviour
    assert plain[CLS_EP].model_id == "xgb-fake"


def test_unexpected_kermt_error_costs_only_the_kermt_rows(monkeypatch):
    monkeypatch.setattr("serve.predictor.standardize_or_raise", lambda s: s)

    class _Boom:
        def served_by_kermt(self):
            return frozenset({CLS_EP})

        def predict(self, smiles, endpoint_keys):
            raise RuntimeError("bug in the router")

    out = predict_endpoints(_Registry(), "CCO", [CLS_EP, "ames_mutagenicity"], kermt=_Boom())
    assert out[CLS_EP].model_id == "xgb-fake" and out["ames_mutagenicity"].model_id == "xgb-fake"
