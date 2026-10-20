"""Module 8 routing table: the packaged table is valid, and bad tables are rejected, not guessed at."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mars_contracts.endpoints import ML_ENDPOINTS
from serve.routing import DEFAULT_ROUTING_PATH, KERMT_ARMS, RoutingTable


def _write(tmp_path: Path, doc: dict) -> Path:
    p = tmp_path / "routing.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def _doc(model="xgboost", **over) -> dict:
    arm_of = {e: a for a, eps in KERMT_ARMS.items() for e in eps}
    eps = {ep.value: {"model": model, "kermt_arm": arm_of[ep.value]} for ep in ML_ENDPOINTS}
    eps.update(over)
    return {"version": 1, "default": "xgboost", "endpoints": eps}


def test_packaged_table_loads_and_covers_all_ml_endpoints():
    table = RoutingTable.load(DEFAULT_ROUTING_PATH)
    assert set(table.as_dict()) == {e.value for e in ML_ENDPOINTS}
    assert set(table.as_dict().values()) <= {"xgboost", "kermt"}


def test_packaged_table_is_the_one_the_evidence_script_generates():
    # eval/kermt_routing_evidence.py --check is the full staleness test; this is the cheap invariant:
    # every route names an arm that really predicts that endpoint (load() enforces it).
    table = RoutingTable.load(DEFAULT_ROUTING_PATH)
    for endpoint in table.as_dict():
        assert endpoint in KERMT_ARMS[table.route(endpoint).kermt_arm]


def test_arms_for_groups_endpoints_into_one_call_per_arm(tmp_path):
    table = RoutingTable.load(_write(tmp_path, _doc("kermt")))
    asked = ["cyp3a4_inhibition", "cyp2d6_inhibition", "herg_cardiotoxicity"]
    assert table.arms_for(asked) == ["metabolism__cls", "toxicity__cls"]


def test_only_kermt_routed_endpoints_are_returned(tmp_path):
    doc = _doc("xgboost")
    doc["endpoints"]["bbb_permeability"]["model"] = "kermt"
    table = RoutingTable.load(_write(tmp_path, doc))
    assert table.kermt_endpoints(["bbb_permeability", "hia_absorption"]) == ["bbb_permeability"]
    assert table.arms_for(["hia_absorption"]) == []


def test_all_xgboost_table_routes_nothing_to_kermt():
    table = RoutingTable.all_xgboost()
    assert table.kermt_endpoint_set() == frozenset()


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda d: d.update(version=2), "unsupported routing version"),
        (lambda d: d["endpoints"].pop("ppb_binding"), "exactly the 14 ML endpoints"),
        (lambda d: d["endpoints"].update(not_an_endpoint={"model": "xgboost"}), "exactly the 14 ML endpoints"),
        (lambda d: d["endpoints"]["ppb_binding"].update(model="lightgbm"), "unknown model"),
        (lambda d: d["endpoints"]["ppb_binding"].update(kermt_arm="toxicity__cls"), "not a KERMT arm that predicts it"),
    ],
)
def test_bad_tables_are_rejected(tmp_path, mutate, message):
    doc = _doc()
    mutate(doc)
    with pytest.raises(ValueError, match=message):
        RoutingTable.load(_write(tmp_path, doc))
