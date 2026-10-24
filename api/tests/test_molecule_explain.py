"""`/molecule/{id}/explain` (Module 6, ADR-031 and ADR-040): status codes, caching, background jobs, and that a failure
is never cached or replaced by another model's explanation. No Redis, RDKit or KERMT service needed: the explainers,
the job calls and the cache are replaced with small stand-ins, so this runs in the fast tier."""

from __future__ import annotations

from types import SimpleNamespace

import app.main as app_main
import pytest
import redis.asyncio as aioredis
from app.main import app
from app.routers import molecule as molecule_router
from app.services import rate_limit
from app.services.redis_client import get_redis
from fastapi import HTTPException
from fastapi.testclient import TestClient
from mars_contracts import ExplainJobStatus, ExplainMethod, ExplainOutputSpace, ExplainResponse

MOLECULE_ID = "0123456789abcdef"
# Main mounts every route under /api (ADR-025); this branch predates that. Work with either.
PREFIX = getattr(app_main, "API_PREFIX", "")
URL = f"{PREFIX}/molecule/{MOLECULE_ID}/explain"
XGB, KERMT, KERMT2 = "solubility_logs", "herg_cardiotoxicity", "bbb_permeability"


class _Redis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.broken = False

    def _check(self):
        if self.broken:
            raise aioredis.RedisError("down")

    async def get(self, key):
        self._check()
        return self.store.get(key)

    async def set(self, key, value, ex=None, nx=False):
        self._check()
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def delete(self, key):
        self._check()
        self.store.pop(key, None)


def _response(endpoint, method=ExplainMethod.TREE_SHAP) -> ExplainResponse:
    return ExplainResponse(
        molecule_id=MOLECULE_ID,
        endpoint=endpoint,
        method=method,
        model_id="mars-xgboost-ecfp-desc-v1",
        output_space=ExplainOutputSpace.LOG_ODDS,
        unit=None,
        n_seeds=5,
        base_value=0.0,
        output_value=0.5,
        baseline="test",
        atom_attributions=[0.1, 0.2],
        fragment_attributions=[],
        whole_molecule_attributions=[],
        whole_molecule_rest=0.2,
        structure_total=0.3,
        whole_molecule_total=0.2,
        unmapped_total=0.0,
        completeness_error=0.0,
        n_steps=None,
        model_version="v-test",
    )


def _snap(job_id, state="queued", **kw):
    base = {
        "job_id": job_id, "state": state, "queue_position": 1 if state == "queued" else None, "seeds_done": 0,
        "seeds_total": 3, "stage": None, "elapsed_seconds": 1.5, "error": None, "error_kind": None, "result": None,
    }
    return SimpleNamespace(**{**base, **kw})


class _Service:
    """What the KERMT service would say: one job per endpoint of the one test molecule."""

    def __init__(self):
        self.snaps: dict[str, SimpleNamespace] = {}
        self.submits: list[tuple] = []
        self.cancels: list[str] = []
        self.busy = False

    def submit(self, smiles, endpoint):
        if self.busy:
            raise molecule_router.ExplainUnavailable("the explanation queue is full (8 waiting)")
        self.submits.append((smiles, endpoint.value))
        return self.snaps.setdefault(endpoint.value, _snap(f"job-{endpoint.value}"))

    def status(self, job_id):
        for snap in self.snaps.values():
            if snap.job_id == job_id:
                return snap
        raise molecule_router.ExplainJobLost(job_id)

    def cancel(self, job_id):
        self.cancels.append(job_id)
        snap = self.status(job_id)
        snap.state, snap.queue_position = "cancelled", None
        return snap


@pytest.fixture
def env(monkeypatch):
    fake = _Redis()
    calls: list[tuple] = []
    svc = _Service()

    async def lookup(_r, molecule_id):
        return "CCO" if molecule_id == MOLECULE_ID else None

    def explain(molecule_id, smiles, endpoint):
        calls.append((molecule_id, smiles, endpoint))
        return _response(endpoint)

    monkeypatch.setattr(molecule_router, "lookup_molecule_smiles", lookup)
    monkeypatch.setattr(molecule_router, "explain", explain)
    monkeypatch.setattr(molecule_router, "explain_available", True)
    monkeypatch.setattr(molecule_router, "serving_version", lambda: "v-test")
    monkeypatch.setattr(molecule_router, "kermt_serves", lambda endpoint: endpoint.value in (KERMT, KERMT2))
    monkeypatch.setattr(molecule_router, "kermt_digest", lambda: "dig1")
    monkeypatch.setattr(molecule_router, "kermt_submit", svc.submit)
    monkeypatch.setattr(molecule_router, "kermt_status", svc.status)
    monkeypatch.setattr(molecule_router, "kermt_cancel", svc.cancel)
    monkeypatch.setattr(
        molecule_router, "kermt_finish", lambda mid, smiles, endpoint, snap: _response(endpoint, ExplainMethod.INTEGRATED_GRADIENTS)
    )
    app.dependency_overrides[get_redis] = lambda: fake
    app.dependency_overrides[rate_limit.enforce_predict_rate_limit] = lambda: None
    try:
        yield SimpleNamespace(client=TestClient(app), redis=fake, calls=calls, svc=svc)
    finally:
        app.dependency_overrides.pop(get_redis, None)
        app.dependency_overrides.pop(rate_limit.enforce_predict_rate_limit, None)


def post(env, endpoint=KERMT, mol=MOLECULE_ID):
    return env.client.post(f"{PREFIX}/molecule/{mol}/explain", params={"endpoint": endpoint})


def get(env, endpoint=KERMT, mol=MOLECULE_ID):
    return env.client.get(f"{PREFIX}/molecule/{mol}/explain", params={"endpoint": endpoint})


def delete(env, endpoint=KERMT):
    return env.client.delete(URL, params={"endpoint": endpoint})


# ---- XGBoost-served: instant ----


def test_explains_and_caches_per_version_molecule_and_endpoint(env):
    first = post(env, XGB)
    assert first.status_code == 200
    body = ExplainResponse.model_validate(first.json())
    assert body.method is ExplainMethod.TREE_SHAP and body.model_id == "mars-xgboost-ecfp-desc-v1"
    second = post(env, XGB)
    assert second.status_code == 200 and second.json() == first.json()
    assert len(env.calls) == 1  # the second answer came from the cache
    assert list(env.redis.store) == [f"explain_cache:v-test:{MOLECULE_ID}:{XGB}"]
    assert post(env, "ames_mutagenicity").status_code == 200 and len(env.calls) == 2  # another endpoint is another entry


def test_get_has_no_side_effect_it_reads_the_cache_or_says_nothing_started(env):
    assert get(env, XGB).status_code == 204 and not env.calls  # GET never computes
    post(env, XGB)
    assert get(env, XGB).status_code == 200


def test_unknown_or_expired_molecule_is_404(env):
    assert post(env, XGB, "ffffffffffffffff").status_code == 404
    assert get(env, XGB, "ffffffffffffffff").status_code == 404
    assert post(env, KERMT, "ffffffffffffffff").status_code == 404
    assert not env.calls and not env.svc.submits


def test_unknown_endpoint_is_422(env):
    assert env.client.post(URL, params={"endpoint": "not_an_endpoint"}).status_code == 422
    assert env.client.post(URL).status_code == 422


def test_rule_based_score_has_nothing_to_explain(env):
    for call in (post, get, delete):
        r = call(env, "synthetic_accessibility")
        assert r.status_code == 409 and "nothing to explain" in r.json()["detail"]
    assert not env.calls


def test_without_the_ml_stack_it_is_501_not_a_made_up_answer(env, monkeypatch):
    monkeypatch.setattr(molecule_router, "explain_available", False)
    assert post(env, XGB).status_code == 501 and post(env, KERMT).status_code == 501 and not env.calls


@pytest.mark.parametrize(
    ("exc_name", "status"),
    [("NothingToExplain", 409), ("ExplainUnavailable", 503), ("ValueError", 422)],
)
def test_failures_map_to_status_codes_and_are_never_cached(env, monkeypatch, exc_name, status):
    exc = {
        "NothingToExplain": molecule_router.NothingToExplain,
        "ExplainUnavailable": molecule_router.ExplainUnavailable,
        "ValueError": ValueError,
    }[exc_name]

    def boom(*_a):
        raise exc("because")

    monkeypatch.setattr(molecule_router, "explain", boom)
    r = post(env, "ames_mutagenicity")
    assert r.status_code == status and r.json()["detail"] == "because"
    assert env.redis.store == {}


# ---- KERMT-served: background jobs ----


def test_a_kermt_explanation_is_started_polled_finished_and_cached(env):
    started = post(env)
    assert started.status_code == 202 and started.headers["retry-after"] == "3"
    status = ExplainJobStatus.model_validate(started.json())
    assert status.state.value == "queued" and status.queue_position == 1 and status.seeds_total == 3
    assert f"explain_job:v-test:dig1:{MOLECULE_ID}:{KERMT}" in env.redis.store

    snap = env.svc.snaps[KERMT]
    snap.state, snap.queue_position, snap.seeds_done, snap.stage = "running", None, 1, "seed 2 of 3, 128 steps"
    running = get(env)
    assert running.status_code == 202
    body = ExplainJobStatus.model_validate(running.json())
    assert body.state.value == "running" and body.seeds_done == 1 and body.stage == "seed 2 of 3, 128 steps"

    snap.state = "done"
    done = get(env)
    assert done.status_code == 200
    assert ExplainResponse.model_validate(done.json()).method is ExplainMethod.INTEGRATED_GRADIENTS
    # cached under the digest; the job record and the address's slot are gone
    assert list(env.redis.store) == [f"explain_cache:v-test:dig1:{MOLECULE_ID}:{KERMT}"]
    assert get(env).status_code == 200 and post(env).status_code == 200
    assert len(env.svc.submits) == 1


def test_get_says_204_when_no_job_was_started(env):
    assert get(env).status_code == 204 and not env.svc.submits


def test_starting_again_joins_the_running_job_instead_of_queueing_another(env):
    assert post(env).status_code == 202 and post(env).status_code == 202
    assert len(env.svc.submits) == 1


def test_a_second_explanation_from_the_same_address_waits_until_the_first_ends(env):
    assert post(env, KERMT).status_code == 202
    blocked = post(env, KERMT2)
    assert blocked.status_code == 429 and "already have an explanation running" in blocked.json()["detail"]
    env.svc.snaps[KERMT].state = "done"
    assert get(env, KERMT).status_code == 200
    assert post(env, KERMT2).status_code == 202  # the slot was freed when the first finished


def test_a_slot_held_by_a_job_that_ended_unseen_does_not_block(env):
    post(env, KERMT)
    env.svc.snaps[KERMT].state = "done"  # finished while nobody polled
    assert post(env, KERMT2).status_code == 202


def test_a_molecule_the_model_cannot_take_fails_with_its_reason_and_can_be_started_again(env):
    post(env)
    snap = env.svc.snaps[KERMT]
    snap.state, snap.error, snap.error_kind = "failed", "its descriptor vector has non-finite values", "unexplainable"
    r = get(env)
    assert r.status_code == 422 and "non-finite" in r.json()["detail"]
    assert get(env).status_code == 422  # remembered for a while, not recomputed
    assert not any(k.startswith("explain_cache:") for k in env.redis.store)  # a failure is never cached
    env.svc.snaps.clear()
    assert post(env).status_code == 202 and len(env.svc.submits) == 2  # Start again replaces it


def test_an_internal_failure_is_503_not_422(env):
    post(env)
    snap = env.svc.snaps[KERMT]
    snap.state, snap.error, snap.error_kind = "failed", "The service failed while explaining this molecule.", "internal"
    assert get(env).status_code == 503


def test_a_job_lost_to_a_service_restart_is_said_so_and_starts_again_on_post(env):
    post(env)
    env.svc.snaps.clear()  # the service restarted: it no longer knows the job
    lost = get(env)
    assert lost.status_code == 503 and "lost" in lost.json()["detail"]
    assert get(env).status_code == 204  # forgotten
    assert post(env).status_code == 202 and len(env.svc.submits) == 2


def test_post_over_a_lost_job_resubmits_without_an_error(env):
    post(env)
    env.svc.snaps.clear()
    assert post(env).status_code == 202 and len(env.svc.submits) == 2


def test_a_full_queue_is_503_and_leaves_nothing_behind(env):
    env.svc.busy = True
    r = post(env)
    assert r.status_code == 503 and "queue is full" in r.json()["detail"]
    assert env.redis.store == {}  # no record, no slot held
    env.svc.busy = False
    assert post(env).status_code == 202


def test_the_service_being_down_is_503_never_another_models_answer(env, monkeypatch):
    def down():
        raise molecule_router.ExplainUnavailable("The KERMT service could not answer: down")

    monkeypatch.setattr(molecule_router, "kermt_digest", down)
    for call in (post, get, delete):
        assert call(env).status_code == 503
    assert env.redis.store == {}


def test_cancel_stops_the_job_and_forgets_it(env):
    post(env)
    cancelled = delete(env)
    assert cancelled.status_code == 200 and cancelled.json()["state"] == "cancelled"
    assert env.svc.cancels == ["job-" + KERMT]
    assert env.redis.store == {}
    assert get(env).status_code == 204
    assert delete(env).status_code == 204  # nothing left to cancel


def test_only_the_address_that_started_a_job_can_cancel_it(env, monkeypatch):
    post(env)
    monkeypatch.setattr(molecule_router, "client_ip", lambda request: "203.0.113.9")
    assert delete(env).status_code == 403 and not env.svc.cancels
    assert get(env).status_code == 202  # other people can still watch it


def test_a_cancel_the_service_has_not_finished_yet_is_reported_as_it_is(env, monkeypatch):
    post(env)
    env.svc.snaps[KERMT].state = "running"
    monkeypatch.setattr(molecule_router, "kermt_cancel", lambda job_id: env.svc.snaps[KERMT])  # asked to stop, still running
    r = delete(env)
    assert r.status_code == 202 and r.json()["state"] == "running"
    assert any(k.startswith("explain_job:") for k in env.redis.store)  # still tracked until it reports cancelled


def test_the_job_state_needs_redis_and_says_so(env):
    env.redis.broken = True
    r = post(env)
    assert r.status_code == 503 and "cache" in r.json()["detail"]


def test_only_starting_a_job_is_rate_limited_polling_and_cancelling_are_not(env):
    def limited():
        raise HTTPException(status_code=429, detail="Rate limit exceeded: 60/minute per IP")

    app.dependency_overrides[rate_limit.enforce_predict_rate_limit] = limited
    assert post(env).status_code == 429
    assert get(env).status_code == 204 and delete(env).status_code == 204
