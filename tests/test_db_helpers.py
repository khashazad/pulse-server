"""Unit tests for the pure helpers and guard rails in :mod:`pulse_server.db`.

Covers URL driver coercion (``to_sqlalchemy_url``), dollar-quote-aware
statement splitting (``_split_sql_statements``), IPv4 pinning
(``_force_ipv4``), and the "pool not initialized" guards on ``get_session``
/ ``bootstrap_schema``. Engine construction and live SQL are exercised by
the integration suite, not here.
"""

from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

from pulse_server import db


# ---- to_sqlalchemy_url --------------------------------------------------------


def test_to_sqlalchemy_url_passthrough_for_explicit_driver() -> None:
    """A URL that already names a driver is returned unchanged."""
    url = "postgresql+psycopg://u:p@h/db"
    assert db.to_sqlalchemy_url(url) == url


def test_to_sqlalchemy_url_coerces_postgres_scheme() -> None:
    """A bare ``postgres://`` scheme is upgraded to the psycopg async driver."""
    assert db.to_sqlalchemy_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"


def test_to_sqlalchemy_url_coerces_postgresql_scheme() -> None:
    """A bare ``postgresql://`` scheme is upgraded to the psycopg async driver."""
    assert db.to_sqlalchemy_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"


def test_to_sqlalchemy_url_unknown_scheme_unchanged() -> None:
    """An unsupported scheme is returned verbatim for caller-level validation."""
    assert db.to_sqlalchemy_url("sqlite:///x.db") == "sqlite:///x.db"


# ---- _split_sql_statements ----------------------------------------------------


def test_split_simple_statements() -> None:
    """Top-level semicolons split a script into trimmed statements."""
    out = db._split_sql_statements("SELECT 1; SELECT 2;")
    assert out == ["SELECT 1", "SELECT 2"]


def test_split_preserves_dollar_quoted_body() -> None:
    """Semicolons inside a ``$$ ... $$`` block stay within one statement."""
    script = (
        "CREATE FUNCTION f() RETURNS void AS $$ BEGIN PERFORM 1; PERFORM 2; END; $$ LANGUAGE plpgsql;"
        " SELECT 1;"
    )
    out = db._split_sql_statements(script)
    assert len(out) == 2
    assert "PERFORM 1; PERFORM 2;" in out[0]
    assert out[1] == "SELECT 1"


def test_split_trailing_statement_without_semicolon() -> None:
    """A trailing statement with no terminating semicolon is still captured."""
    assert db._split_sql_statements("SELECT 1") == ["SELECT 1"]


def test_split_ignores_blank_statements() -> None:
    """Empty fragments between semicolons are dropped."""
    assert db._split_sql_statements(";;SELECT 1;;") == ["SELECT 1"]


# ---- _force_ipv4 --------------------------------------------------------------


def test_force_ipv4_appends_hostaddr() -> None:
    """A resolvable host gets a ``hostaddr`` query param appended."""
    fake = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("203.0.113.7", 5432))]
    with patch("pulse_server.db.socket.getaddrinfo", return_value=fake):
        out = db._force_ipv4("postgresql://u:p@example.com/db")
    assert "hostaddr=203.0.113.7" in out


def test_force_ipv4_returns_unchanged_when_already_present() -> None:
    """A URL that already carries ``hostaddr`` is left untouched."""
    fake = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("203.0.113.7", 5432))]
    url = "postgresql://u:p@example.com/db?hostaddr=1.2.3.4"
    with patch("pulse_server.db.socket.getaddrinfo", return_value=fake):
        assert db._force_ipv4(url) == url


def test_force_ipv4_returns_unchanged_on_resolution_failure() -> None:
    """A resolution failure leaves the URL unchanged for libpq to report."""
    with patch("pulse_server.db.socket.getaddrinfo", side_effect=socket.gaierror):
        url = "postgresql://u:p@example.com/db"
        assert db._force_ipv4(url) == url


def test_force_ipv4_returns_unchanged_when_no_host() -> None:
    """A URL without a host short-circuits without resolution."""
    assert db._force_ipv4("postgresql:///db") == "postgresql:///db"


def test_force_ipv4_returns_unchanged_when_no_addrinfo() -> None:
    """An empty ``getaddrinfo`` result leaves the URL unchanged."""
    with patch("pulse_server.db.socket.getaddrinfo", return_value=[]):
        url = "postgresql://u:p@example.com/db"
        assert db._force_ipv4(url) == url


def test_force_ipv4_merges_with_existing_query() -> None:
    """An existing query string is preserved and the hostaddr appended with ``&``."""
    fake = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("203.0.113.7", 5432))]
    with patch("pulse_server.db.socket.getaddrinfo", return_value=fake):
        out = db._force_ipv4("postgresql://u:p@example.com/db?sslmode=require")
    assert "sslmode=require" in out
    assert "hostaddr=203.0.113.7" in out


# ---- pool-not-initialized guards ----------------------------------------------


@pytest.mark.asyncio
async def test_get_session_requires_initialized_pool() -> None:
    """``get_session`` raises when the session factory is unset."""
    with patch.object(db, "_session_factory", None):
        with pytest.raises(RuntimeError):
            async with db.get_session():
                pass


@pytest.mark.asyncio
async def test_bootstrap_schema_requires_engine() -> None:
    """``bootstrap_schema`` raises when the engine is unset."""
    with patch.object(db, "_engine", None):
        with pytest.raises(RuntimeError):
            await db.bootstrap_schema()


@pytest.mark.asyncio
async def test_init_pool_runs_connectivity_check() -> None:
    """``init_pool`` builds the engine/factory and runs a ``SELECT 1`` probe."""
    from unittest.mock import AsyncMock, MagicMock

    conn = AsyncMock()
    conn_cm = MagicMock()
    conn_cm.__aenter__ = AsyncMock(return_value=conn)
    conn_cm.__aexit__ = AsyncMock(return_value=False)
    engine = MagicMock()
    engine.connect = MagicMock(return_value=conn_cm)

    with patch("pulse_server.db.create_async_engine", return_value=engine) as make_engine, patch(
        "pulse_server.db.async_sessionmaker"
    ), patch("pulse_server.db.socket.getaddrinfo", side_effect=socket.gaierror):
        try:
            await db.init_pool("postgresql://u:p@localhost/db")
            make_engine.assert_called_once()
            conn.execute.assert_awaited_once()
        finally:
            with patch.object(db, "_engine", None), patch.object(db, "_session_factory", None):
                pass
    # Reset module globals set by init_pool so other tests start clean.
    db._engine = None
    db._session_factory = None


@pytest.mark.asyncio
async def test_bootstrap_schema_executes_statements() -> None:
    """``bootstrap_schema`` reads ``schema.sql`` and executes each statement."""
    from unittest.mock import AsyncMock, MagicMock

    conn = AsyncMock()
    begin_cm = MagicMock()
    begin_cm.__aenter__ = AsyncMock(return_value=conn)
    begin_cm.__aexit__ = AsyncMock(return_value=False)
    engine = MagicMock()
    engine.begin = MagicMock(return_value=begin_cm)

    with patch.object(db, "_engine", engine):
        await db.bootstrap_schema()
    assert conn.execute.await_count > 0


@pytest.mark.asyncio
async def test_get_session_yields_from_factory() -> None:
    """``get_session`` / ``get_session_dependency`` yield a session from the factory."""
    from unittest.mock import AsyncMock, MagicMock

    sentinel = object()
    sess_cm = MagicMock()
    sess_cm.__aenter__ = AsyncMock(return_value=sentinel)
    sess_cm.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=sess_cm)

    with patch.object(db, "_session_factory", factory):
        async with db.get_session() as session:
            assert session is sentinel
        # The dependency wrapper delegates to get_session with the same lifecycle.
        agen = db.get_session_dependency()
        assert await agen.__anext__() is sentinel
        with pytest.raises(StopAsyncIteration):
            await agen.__anext__()
