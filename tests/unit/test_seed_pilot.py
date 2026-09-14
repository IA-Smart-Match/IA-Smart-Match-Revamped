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


# ---------------------------------------------------------------------------
# One account, several roles: the connector persona's membership set
# ---------------------------------------------------------------------------
#
# `_ensure_membership_set` replaced a check that refused *any* second
# membership row. That refusal is why the dual-role connector seed could write
# `coordinator` + `admin` to a fresh database and then fail on every re-run
# against the database it had just written — so the fresh path and the
# already-seeded path are both exercised below, not just the first.


def _inserted_roles(connection: _Connection) -> list[str]:
    """The `role` of every INSERT the fake connection was handed, in order."""
    return [
        statement.compile().params["role"]
        for statement, _params in connection.calls
        if statement.__visit_name__ == "insert"
    ]


def test_a_fresh_account_gets_every_requested_role():
    connection = _Connection([_Result(all_rows=[]), _Result(), _Result()])

    seed_pilot._ensure_membership_set(
        connection,  # type: ignore[arg-type]
        tenant_id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        path="pilot",
        roles=("coordinator", "admin"),
    )

    # Sorted, so two runs of the same seed write the same rows in the same
    # order rather than whichever the table happened to list first.
    assert _inserted_roles(connection) == ["admin", "coordinator"]


def test_reseeding_an_account_that_already_holds_every_role_writes_nothing():
    """The path that used to fail: the seed re-run against its own output."""
    connection = _Connection(
        [
            _Result(
                all_rows=[
                    SimpleNamespace(
                        granted_path="pilot", role=role, valid_from=None, valid_until=None
                    )
                    for role in ("coordinator", "admin")
                ]
            )
        ]
    )

    seed_pilot._ensure_membership_set(
        connection,  # type: ignore[arg-type]
        tenant_id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        path="pilot",
        roles=("coordinator", "admin"),
    )

    assert _inserted_roles(connection) == []


def test_an_account_seeded_before_the_pivot_gains_only_the_missing_role():
    """A live database holds one row; the upgrade adds the other and no more.

    This is the migration path for the pilot logins, which exist already with
    a single membership each. Nothing is recreated and nothing is rewritten.
    """
    connection = _Connection(
        [
            _Result(
                all_rows=[
                    SimpleNamespace(
                        granted_path="pilot",
                        role="coordinator",
                        valid_from=None,
                        valid_until=None,
                    )
                ]
            ),
            _Result(),
        ]
    )

    seed_pilot._ensure_membership_set(
        connection,  # type: ignore[arg-type]
        tenant_id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        path="pilot",
        roles=("coordinator", "admin"),
    )

    assert _inserted_roles(connection) == ["admin"]


def test_a_role_nobody_asked_for_is_still_a_conflict():
    """Widening the set must not widen what the seed will tolerate.

    The account holds everything requested *and* a role this seed never names.
    Somebody else granted that, and an operator tool that silently accepted it
    would be an operator tool that could be used to hide one.
    """
    connection = _Connection(
        [
            _Result(
                all_rows=[
                    SimpleNamespace(
                        granted_path="pilot", role=role, valid_from=None, valid_until=None
                    )
                    for role in ("coordinator", "admin", "student")
                ]
            )
        ]
    )

    with pytest.raises(seed_pilot.SeedConflictError, match="different membership"):
        seed_pilot._ensure_membership_set(
            connection,  # type: ignore[arg-type]
            tenant_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            path="pilot",
            roles=("coordinator", "admin"),
        )


def test_the_right_role_over_the_wrong_path_is_a_conflict():
    """A grant is a role *over a subtree*; half of it matching is not a match."""
    connection = _Connection(
        [
            _Result(
                all_rows=[
                    SimpleNamespace(
                        granted_path="pilot.elsewhere",
                        role="admin",
                        valid_from=None,
                        valid_until=None,
                    )
                ]
            )
        ]
    )

    with pytest.raises(seed_pilot.SeedConflictError, match="different membership"):
        seed_pilot._ensure_membership_set(
            connection,  # type: ignore[arg-type]
            tenant_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            path="pilot",
            roles=("coordinator", "admin"),
        )


def test_a_validity_window_this_seed_did_not_write_is_a_conflict():
    """An expiring grant is somebody's decision; re-seeding must not erase it."""
    connection = _Connection(
        [
            _Result(
                all_rows=[
                    SimpleNamespace(
                        granted_path="pilot",
                        role="admin",
                        valid_from=None,
                        valid_until="2030-01-01T00:00:00Z",
                    )
                ]
            )
        ]
    )

    with pytest.raises(seed_pilot.SeedConflictError, match="different membership"):
        seed_pilot._ensure_membership_set(
            connection,  # type: ignore[arg-type]
            tenant_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            path="pilot",
            roles=("admin",),
        )
