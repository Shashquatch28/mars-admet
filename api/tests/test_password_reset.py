"""Password reset (frontend ADR-043): single-use, short-lived, hashed tokens; the same answer whether or not an address has an
account; rate limits; every session ended on success; the email behind an interface with a log backend and a Resend backend.

The infra tests need the live Postgres and Redis (and the `password_reset_tokens` table: `alembic upgrade head`). The email
backends are unit-tested with a mock transport, so no key is needed and nothing is ever really sent.
"""

import asyncio
import logging
import re
import uuid
from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest
from app.core.config import Settings, get_settings
from app.db.models import PasswordResetToken
from app.db.session import SessionLocal
from app.main import _warn_on_insecure_config
from app.services import password_reset
from app.services.batch_runner import now_naive_utc
from app.services.email_sender import (
    RESEND_URL,
    EmailMessage,
    LogEmailSender,
    ResendEmailSender,
    email_config_problem,
    get_email_sender,
)
from app.services.redis_client import get_redis
from sqlalchemy import select, update
from tests.conftest import requires_infra


class Outbox:
    """Stands in for the email provider: records what would have been sent."""

    def __init__(self):
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> bool:
        self.sent.append(message)
        return True


@pytest.fixture
def outbox(monkeypatch):
    box = Outbox()
    monkeypatch.setattr(password_reset, "get_email_sender", lambda: box)
    return box


@pytest.fixture(autouse=True)
def fresh_limits():
    """The limiter counts per hour in the shared Redis; start each test from zero."""

    async def clear():
        r = get_redis()
        async for key in r.scan_iter(match="ratelimit:pwreset-*"):
            await r.delete(key)

    try:
        asyncio.run(clear())
    except Exception:  # no Redis: the infra tests are skipped, the unit tests do not need it
        pass


def _token_from(message: EmailMessage) -> str:
    m = re.search(r"/reset-password#token=([A-Za-z0-9_-]+)", message.text)
    assert m, message.text
    return m.group(1)


def _rows(email_user_id: str) -> list[PasswordResetToken]:
    async def go():
        async with SessionLocal() as db:
            q = select(PasswordResetToken).where(PasswordResetToken.user_id == uuid.UUID(email_user_id))
            return list((await db.execute(q)).scalars())

    return asyncio.run(go())


def _set(user_id: str, **values) -> None:
    async def go():
        async with SessionLocal() as db:
            await db.execute(update(PasswordResetToken).where(PasswordResetToken.user_id == uuid.UUID(user_id)).values(**values))
            await db.commit()

    asyncio.run(go())


def _ask(client, email):
    return client.post("/auth/password-reset/request", json={"email": email})


# --- the request route -------------------------------------------------------------------------------------------------


@requires_infra
def test_an_unknown_and_a_known_address_get_the_same_answer(client, registered_user, outbox):
    unknown = _ask(client, f"nobody-{uuid.uuid4().hex[:8]}@example.com")
    known = _ask(client, registered_user["email"])
    assert (unknown.status_code, unknown.content, unknown.headers.get("content-type")) == (
        known.status_code,
        known.content,
        known.headers.get("content-type"),
    )
    assert known.status_code == 202
    # ...and only the known one produced an email
    assert [m.to for m in outbox.sent] == [registered_user["email"]]


@requires_infra
def test_the_email_links_to_the_app_with_the_token_in_the_fragment(client, registered_user, outbox):
    _ask(client, registered_user["email"])
    (msg,) = outbox.sent
    base = get_settings().app_base_url.rstrip("/")
    assert f"{base}/reset-password#token=" in msg.text  # a fragment: never sent to a server, so not in logs or Referer
    assert "?token=" not in msg.text
    assert str(get_settings().password_reset_ttl_minutes) in msg.text
    assert "ignore this email" in msg.text


@requires_infra
def test_only_a_hash_of_the_token_is_stored(client, registered_user, outbox):
    _ask(client, registered_user["email"])
    raw = _token_from(outbox.sent[0])
    (row,) = _rows(registered_user["user_id"])
    assert row.token_hash == password_reset.hash_token(raw)
    assert raw not in row.token_hash and row.token_hash != raw
    assert len(raw) >= 43  # 32 random bytes, url-safe
    assert row.used_at is None
    ttl = row.expires_at - row.created_at.replace(tzinfo=None)
    assert timedelta(minutes=get_settings().password_reset_ttl_minutes - 1) < ttl <= timedelta(minutes=get_settings().password_reset_ttl_minutes + 1)


@requires_infra
def test_a_new_request_retires_the_earlier_link(client, registered_user, outbox):
    _ask(client, registered_user["email"])
    _ask(client, registered_user["email"])
    first, second = (_token_from(m) for m in outbox.sent)
    body = {"token": first, "new_password": "brand-new-password"}
    assert client.post("/auth/password-reset/confirm", json=body).status_code == 400
    assert client.post("/auth/password-reset/confirm", json={**body, "token": second}).status_code == 204


@requires_infra
def test_rate_limit_per_address_is_silent(client, registered_user, outbox, monkeypatch):
    monkeypatch.setattr(get_settings(), "password_reset_per_email_per_hour", 2)
    answers = [_ask(client, registered_user["email"]) for _ in range(4)]
    assert {a.status_code for a in answers} == {202}  # a limit looks like any other answer
    assert len({a.content for a in answers}) == 1
    assert len(outbox.sent) == 2  # but nothing is sent past it


@requires_infra
def test_rate_limit_per_ip_is_silent(client, registered_user, outbox, monkeypatch):
    monkeypatch.setattr(get_settings(), "password_reset_per_ip_per_hour", 2)
    for _ in range(4):
        assert _ask(client, f"x-{uuid.uuid4().hex[:8]}@example.com").status_code == 202
    assert _ask(client, registered_user["email"]).status_code == 202
    assert outbox.sent == []  # the IP is over its limit, so even a real account gets nothing from here


@requires_infra
def test_a_malformed_address_is_a_422_not_a_probe(client):
    assert client.post("/auth/password-reset/request", json={"email": "not-an-email"}).status_code == 422


@requires_infra
def test_an_email_failure_never_changes_the_answer(client, registered_user, monkeypatch):
    class Boom:
        async def send(self, message):
            raise RuntimeError("provider down")

    monkeypatch.setattr(password_reset, "get_email_sender", lambda: Boom())
    assert _ask(client, registered_user["email"]).status_code == 202


# --- confirm --------------------------------------------------------------------------------------------------------------


@requires_infra
def test_a_reset_sets_the_password_ends_every_session_and_signs_nobody_in(client, registered_user, outbox):
    email, old = registered_user["email"], registered_user["password"]
    assert client.get("/auth/me").status_code == 200  # signed in by the fixture
    _ask(client, email)
    token = _token_from(outbox.sent[0])

    r = client.post("/auth/password-reset/confirm", json={"token": token, "new_password": "a-different-password"})
    assert r.status_code == 204
    assert "set-cookie" not in {k.lower() for k in r.headers}  # not signed in by a reset
    assert client.get("/auth/me").status_code == 401  # the session that existed is gone
    assert client.post("/auth/login", json={"email": email, "password": old}).status_code == 401
    assert client.post("/auth/login", json={"email": email, "password": "a-different-password"}).status_code == 200


@requires_infra
def test_a_link_works_once(client, registered_user, outbox):
    _ask(client, registered_user["email"])
    token = _token_from(outbox.sent[0])
    ok = client.post("/auth/password-reset/confirm", json={"token": token, "new_password": "first-new-password"})
    again = client.post("/auth/password-reset/confirm", json={"token": token, "new_password": "second-new-password"})
    assert (ok.status_code, again.status_code) == (204, 400)
    assert client.post("/auth/login", json={"email": registered_user["email"], "password": "first-new-password"}).status_code == 200


@requires_infra
def test_an_expired_link_fails_with_the_same_answer_as_an_unknown_one(client, registered_user, outbox):
    _ask(client, registered_user["email"])
    token = _token_from(outbox.sent[0])
    _set(registered_user["user_id"], expires_at=now_naive_utc() - timedelta(seconds=1))
    expired = client.post("/auth/password-reset/confirm", json={"token": token, "new_password": "a-valid-password"})
    unknown = client.post("/auth/password-reset/confirm", json={"token": "x" * 43, "new_password": "a-valid-password"})
    assert (expired.status_code, expired.json()) == (unknown.status_code, unknown.json()) == (400, {"detail": "Invalid or expired reset token"})


@requires_infra
def test_a_password_that_cannot_be_stored_does_not_burn_the_link(client, registered_user, outbox):
    _ask(client, registered_user["email"])
    token = _token_from(outbox.sent[0])
    too_long = client.post("/auth/password-reset/confirm", json={"token": token, "new_password": "p" * 80})
    assert too_long.status_code == 422
    too_short = client.post("/auth/password-reset/confirm", json={"token": token, "new_password": "short"})
    assert too_short.status_code == 422
    assert client.post("/auth/password-reset/confirm", json={"token": token, "new_password": "a-valid-password"}).status_code == 204


@requires_infra
def test_confirm_attempts_are_limited_per_ip(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "password_reset_confirm_per_ip_per_hour", 2)
    codes = [client.post("/auth/password-reset/confirm", json={"token": "y" * 43, "new_password": "a-valid-password"}).status_code for _ in range(3)]
    assert codes == [400, 400, 429]


@requires_infra
def test_deleting_an_account_removes_its_tokens(client, registered_user, outbox):
    _ask(client, registered_user["email"])
    assert len(_rows(registered_user["user_id"])) == 1
    client.request("DELETE", "/account", json={"password": registered_user["password"]})
    assert _rows(registered_user["user_id"]) == []


# --- tokens, as units -----------------------------------------------------------------------------------------------------


def test_tokens_are_random_and_only_their_hash_is_for_storing():
    raw1, h1 = password_reset.new_token()
    raw2, h2 = password_reset.new_token()
    assert raw1 != raw2 and h1 != h2
    assert h1 == password_reset.hash_token(raw1) and h1 != raw1
    assert len(h1) == 64


# --- the email backends ----------------------------------------------------------------------------------------------------

KEY = "re_test_key_that_must_never_be_printed"
FROM = "MARS <no-reply@example.test>"
MSG = EmailMessage(to="person@example.test", subject="Reset", text="link")


def _resend(handler):
    return ResendEmailSender(KEY, FROM, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_the_resend_backend_posts_the_message_with_the_key_from_its_settings():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["auth"], seen["json"] = str(request.url), request.headers["authorization"], request.read()
        return httpx.Response(200, json={"id": "x"})

    assert asyncio.run(_resend(handler).send(MSG)) is True
    assert seen["url"] == RESEND_URL and seen["auth"] == f"Bearer {KEY}"
    assert b"person@example.test" in seen["json"] and FROM.encode() in seen["json"]


@pytest.mark.parametrize("response", [httpx.Response(422, json={"message": "bad person@example.test"}), httpx.Response(500)])
def test_a_refusal_is_a_false_and_the_log_holds_neither_key_nor_address(caplog, response):
    with caplog.at_level(logging.DEBUG):
        assert asyncio.run(_resend(lambda request: response).send(MSG)) is False
    text = caplog.text
    assert KEY not in text and "person@example.test" not in text
    assert str(response.status_code) in text


def test_a_network_failure_is_a_false_and_the_log_holds_neither_key_nor_address(caplog):
    def handler(request):
        raise httpx.ConnectError(f"cannot reach {request.url} with {request.headers['authorization']} for person@example.test")

    with caplog.at_level(logging.DEBUG):
        assert asyncio.run(_resend(handler).send(MSG)) is False
    assert KEY not in caplog.text and "person@example.test" not in caplog.text and "ConnectError" in caplog.text


def test_the_log_backend_writes_the_message_where_a_developer_will_see_it(caplog):
    with caplog.at_level(logging.WARNING):
        assert asyncio.run(LogEmailSender().send(EmailMessage(to="dev@example.test", subject="S", text="http://localhost:5173/x"))) is True
    assert "not sent" in caplog.text and "http://localhost:5173/x" in caplog.text


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_the_resend_backend_needs_both_the_key_and_the_from_address_and_names_what_is_missing_not_its_value():
    assert email_config_problem(_settings(email_backend="log")) is None
    assert email_config_problem(_settings(email_backend="resend", resend_api_key=KEY, resend_from_email=FROM)) is None
    p = email_config_problem(_settings(email_backend="resend", resend_api_key=KEY, resend_from_email=""))
    assert p == "EMAIL_BACKEND=resend needs RESEND_FROM_EMAIL" and KEY not in p
    both = email_config_problem(_settings(email_backend="resend"))
    assert "RESEND_API_KEY" in both and "RESEND_FROM_EMAIL" in both


def test_the_service_refuses_to_start_with_resend_selected_and_no_key(monkeypatch):
    broken = _settings(email_backend="resend", resend_from_email=FROM)
    import app.main as main_module

    monkeypatch.setattr(main_module, "get_settings", lambda: broken)
    with pytest.raises(RuntimeError, match="RESEND_API_KEY"):
        _warn_on_insecure_config()


def test_the_sender_is_chosen_from_settings(monkeypatch):
    from app.services import email_sender

    monkeypatch.setattr(email_sender, "get_settings", lambda: _settings(email_backend="log"))
    assert isinstance(get_email_sender(), LogEmailSender)
    monkeypatch.setattr(email_sender, "get_settings", lambda: _settings(email_backend="resend", resend_api_key=KEY, resend_from_email=FROM))
    assert isinstance(get_email_sender(), ResendEmailSender)
    monkeypatch.setattr(email_sender, "get_settings", lambda: SimpleNamespace(**{**_settings(email_backend="resend").model_dump()}))
    with pytest.raises(RuntimeError):
        get_email_sender()
