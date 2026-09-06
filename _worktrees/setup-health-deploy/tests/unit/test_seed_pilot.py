"""Unit coverage for the development-only pilot database seeder."""

from __future__ import annotations

import uuid
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from smartmatch_api.config import Settings
from smartmatch_providers import Edition

from tools import seed_pilot


class _Result:
    def __init__(self, *, one: object | None = None, all_rows: list[object] | None = None) -> None:
        self._one = one
        self._all_rows = all_rows or []

    def one_or_none(self) -> object | None:
        return self._one

    def all(self) -> list[object]:
        return self._all_rows


class _Connection:
    def __init__(self, results: list[_Result]) -> None:
        self.results = results
        self.calls: list[tuple[object, object | None]] = []

    def execute(self, statement: object, params: object | None = None) -> _Result:
        self.calls.append((statement, params))
        return self.results.pop(0)


def test_seed_requires_validated_dev_fixture_settings():
    settings = Settings(edition=Edition.DEV, use_fixture_providers=True)
    assert seed_pilot.require_development_fixture_settings(settings) is settings

    with pytest.raises(seed_pilot.SeedConfigurationError):
        seed_pilot.require_development_fixture_settings(Settings(edition=Edition.STAGING))

    with pytest.raises(seed_pilot.SeedConfigurationError):
        seed_pilot.require_development_fixture_settings(
            Settings(edition=Edition.DEV, use_fixture_providers=False)
        )


def test_seed_lock_uses_a_postgresql_transaction_scoped_advisory_lock():
    connection = _Connection([_Result()])

    seed_pilot.acquire_seed_lock(connection)  # type: ignore[arg-type]

    statement, params = connection.calls[0]
    assert "pg_advisory_xact_lock" in str(statement)
    assert params == {"lock_key": seed_pilot.SEED_PILOT_ADVISORY_LOCK_KEY}


def test_main_uses_validated_settings_url_and_acquires_lock_before_seeding(
    monkeypatch: pytest.MonkeyPatch,
):
    settings = SimpleNamespace(
        edition=Edition.DEV,
        use_fixture_providers=True,
        database_url="postgresql+psycopg://configured.example.test/pilot",
    )
    events: list[object] = []
    connection = object()
    engine = SimpleNamespace(begin=lambda: nullcontext(connection), dispose=lambda: None)

    monkeypatch.setattr(seed_pilot, "Settings", lambda: settings)
    monkeypatch.setattr(seed_pilot, "create_db_engine", lambda url: events.append(url) or engine)
    monkeypatch.setattr(seed_pilot, "acquire_seed_lock", lambda conn: events.append("lock"))
    monkeypatch.setattr(seed_pilot, "seed_pilot", lambda conn, **kwargs: events.append("seed"))

    assert (
        seed_pilot.main(["--subject", "sub", "--email", "a@example.test", "--role", "viewer"]) == 0
    )
    assert events == [settings.database_url, "lock", "seed"]


def test_seed_rejects_an_arbitrary_database_url_argument():
    with pytest.raises(SystemExit):
        seed_pilot.parse_args(
            [
                "--subject",
                "sub",
                "--email",
                "a@example.test",
                "--role",
                "viewer",
                "--database-url",
                "postgresql://other",
            ]
        )


def test_existing_tenant_with_identical_attributes_is_an_idempotent_repeat():
    tenant_id = "e2f99577-b1d6-45f3-95d5-827b47b69ffc"
    connection = _Connection([_Result(one=SimpleNamespace(id=tenant_id, display_name="Pilot"))])

    assert seed_pilot._existing_or_insert_tenant(
        connection,
        slug="pilot",
        display_name="Pilot",  # type: ignore[arg-type]
    ) == uuid.UUID(tenant_id)
    assert len(connection.calls) == 1


def test_existing_membership_with_different_role_is_a_conflict():
    connection = _Connection(
        [
            _Result(
                all_rows=[
                    SimpleNamespace(
                        granted_path="pilot",
                        role="viewer",
                        valid_from=None,
                        valid_until=None,
                    )
                ]
            )
        ]
    )

    with pytest.raises(seed_pilot.SeedConflictError, match="different membership"):
        seed_pilot._existing_or_insert_membership(
            connection,  # type: ignore[arg-type]
            tenant_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            path="pilot",
            role="coordinator",
        )
