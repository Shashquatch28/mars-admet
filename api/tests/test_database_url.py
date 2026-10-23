"""A Postgres URL copied from Neon's console must work with the asyncpg driver as pasted (ship checklist C7)."""

from __future__ import annotations

import pytest
from app.core.config import Settings, normalize_database_url
from sqlalchemy.engine import make_url

NEON = "postgresql://mars_owner:pw%40word@ep-cool-123.us-east-2.aws.neon.tech/mars?sslmode=require&channel_binding=require"


def test_neon_console_url_becomes_an_asyncpg_url():
    url = make_url(normalize_database_url(NEON))
    assert url.drivername == "postgresql+asyncpg"
    assert url.query == {"ssl": "require"}  # no sslmode (asyncpg rejects it), no channel_binding
    assert url.host == "ep-cool-123.us-east-2.aws.neon.tech" and url.password == "pw@word"


@pytest.mark.parametrize("scheme", ["postgres", "postgresql"])
def test_bare_schemes_get_the_driver(scheme):
    assert normalize_database_url(f"{scheme}://u:p@h/db").startswith("postgresql+asyncpg://")


def test_an_already_correct_url_is_unchanged():
    url = "postgresql+asyncpg://mars:mars_dev_password@localhost:55432/mars_dev"
    assert normalize_database_url(url) == url


def test_surrounding_whitespace_from_a_pasted_secret_is_dropped():
    assert normalize_database_url("  postgresql+asyncpg://u:p@h/db\n") == "postgresql+asyncpg://u:p@h/db"


def test_settings_apply_it():
    assert Settings(database_url=NEON, _env_file=None).database_url.startswith("postgresql+asyncpg://")
