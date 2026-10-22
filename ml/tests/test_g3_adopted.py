import pytest

from eval.g3_adopted import g3_adopted, inside


def _par(ames, herg):
    mk = lambda ci: {"n_scored": 10, "pooled": {"delta": sum(ci) / 2, "ci90": ci}}
    return {"endpoints": {"ames_mutagenicity": mk(ames), "herg_cardiotoxicity": mk(herg)}}


def test_inside_is_inclusive():
    assert inside([-0.02, 0.02], 0.02)
    assert not inside([-0.0201, 0.0], 0.02)


def test_ames_gates_and_herg_does_not():
    r = g3_adopted(_par([-0.0076, 0.0100], [-0.029, -0.0098]))
    assert r["verdict"] == "PASS" and r["endpoints"]["herg_cardiotoxicity"]["status"] == "WATCH"


def test_ames_outside_fails():
    r = g3_adopted(_par([-0.03, 0.0], [-0.001, 0.001]))
    assert r["verdict"] == "FAIL" and r["endpoints"]["herg_cardiotoxicity"]["status"] == "reported"


def test_missing_gating_endpoint_raises():
    with pytest.raises(ValueError):
        g3_adopted({"endpoints": {}})
