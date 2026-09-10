"""Pool sizing in `smartmatch_persistence.engine`.

The pilot VM exhausted its pool under a burst of concurrent authenticated
requests — every request holds its connection for its whole lifetime, so the
old hard-coded `pool_size=5, max_overflow=5` capped the API at ten in-flight
requests and the eleventh waited `pool_timeout` seconds and then raised.

Two things are pinned here, both without a database, because `create_engine`
does not connect until first use:

1. The **defaults** are the numbers the single-VM appliance is sized for. A
   change to them is a change to how many backends the API and the worker
   together ask of a `postgres:16` running at the image default
   `max_connections = 100`, so it should have to edit a test that says so.
2. The **environment override** exists and is total — every pool knob is
   settable — because the Cloud Run deployment's ceiling is
   `instances x pool_size` and cannot be the VM's number. A malformed value
   raises rather than falling back, so a deployment that meant to cap its pool
   and typed the number wrong fails to boot instead of quietly running with the
   wrong ceiling.
"""

from __future__ import annotations

import pytest
from smartmatch_persistence.engine import (
    DEFAULT_MAX_OVERFLOW,
    DEFAULT_POOL_RECYCLE,
    DEFAULT_POOL_SIZE,
    DEFAULT_POOL_TIMEOUT,
    create_db_engine,
    resolve_pool_settings,
)

# Never connected to; `create_engine` is lazy.
_URL = "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch"

_ENV_VARS = (
    "SMARTMATCH_DB_POOL_SIZE",
    "SMARTMATCH_DB_MAX_OVERFLOW",
    "SMARTMATCH_DB_POOL_TIMEOUT",
    "SMARTMATCH_DB_POOL_RECYCLE",
)


@pytest.fixture(autouse=True)
def _clean_pool_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run every case against a machine that configures nothing.

    Without this a developer's own `SMARTMATCH_DB_*` export would decide
    whether the defaults case passes.
    """
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults_are_the_appliance_numbers() -> None:
    """The compose appliance's budget, stated as an assertion.

    `(20 + 10) API + (20 + 10) worker = 60`, against `max_connections = 100`
    less three superuser-reserved, leaves 37 for migrate/seed one-shots, an
    operator's psql, and host-side pytest.
    """
    assert DEFAULT_POOL_SIZE == 20
    assert DEFAULT_MAX_OVERFLOW == 10
    assert 2 * (DEFAULT_POOL_SIZE + DEFAULT_MAX_OVERFLOW) <= 100 - 3

    assert resolve_pool_settings() == {
        "pool_size": DEFAULT_POOL_SIZE,
        "max_overflow": DEFAULT_MAX_OVERFLOW,
        "pool_timeout": DEFAULT_POOL_TIMEOUT,
        "pool_recycle": DEFAULT_POOL_RECYCLE,
    }


def test_engine_is_built_with_the_resolved_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """The resolved numbers reach the pool, not just the helper."""
    monkeypatch.setenv("SMARTMATCH_DB_POOL_SIZE", "7")
    monkeypatch.setenv("SMARTMATCH_DB_MAX_OVERFLOW", "3")
    monkeypatch.setenv("SMARTMATCH_DB_POOL_TIMEOUT", "11")

    engine = create_db_engine(_URL)
    try:
        pool = engine.pool
        assert pool.size() == 7
        assert pool._max_overflow == 3  # noqa: SLF001 - no public accessor
        assert pool._timeout == 11  # noqa: SLF001 - no public accessor
    finally:
        engine.dispose()


@pytest.mark.parametrize("name", _ENV_VARS)
def test_every_knob_is_overridable(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """No knob is settable-looking but ignored."""
    monkeypatch.setenv(name, "42")

    key = name.removeprefix("SMARTMATCH_DB_").lower()
    assert resolve_pool_settings()[key] == 42


def test_blank_value_takes_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Compose passes `${VAR:-}`, which arrives as an empty string, not as unset."""
    monkeypatch.setenv("SMARTMATCH_DB_POOL_SIZE", "")

    assert resolve_pool_settings()["pool_size"] == DEFAULT_POOL_SIZE


@pytest.mark.parametrize("value", ["five", "5.5", "-1"])
def test_malformed_value_refuses_rather_than_defaulting(
    value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A typo'd ceiling must fail loudly, not silently become the default."""
    monkeypatch.setenv("SMARTMATCH_DB_POOL_SIZE", value)

    with pytest.raises(ValueError, match="SMARTMATCH_DB_POOL_SIZE"):
        resolve_pool_settings()
