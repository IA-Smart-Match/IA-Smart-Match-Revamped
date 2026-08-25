"""The identity lookup, and the constraint that makes it correct.

``PrincipalRepository.load_by_subject`` finds an account by ``external_subject``
and by nothing else — the token proves who you are, the database decides which
tenant you are in — and then calls ``.one_or_none()``. That call is only sound
if a subject can match at most one row, which is a property of the schema and
not of the query. Migration ``0003`` added
``uq_user_account_external_subject`` to make it true.

These tests hold both halves to account. The first asserts the rule the database
now enforces, by attempting the write it must refuse: the same subject in two
different tenants, which is exactly the shape that returned two rows,
raised ``MultipleResultsFound``, and turned every authenticated request by that
person into a 500. The second asserts the lookup resolves the account, its
tenant, and its memberships when the subject exists once. The third runs the
migration itself against a scratch database holding duplicates and requires it
to stop and name them.

Requires a live database. Skipped automatically when one is not configured.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")

import sqlalchemy as sa
from conftest import _TENANT_SCOPED_TABLES, unique_subject
from smartmatch_authz import OrgPath
from smartmatch_persistence.principals import PrincipalRepository
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: The revision immediately before the one under test. The scratch database is
#: brought to here, filled with the data the constraint forbids, and only then
#: asked to go to head.
_REVISION_BEFORE = "0002_rate_limit"

#: PostgreSQL's ``insufficient_privilege``. The *only* condition under which this
#: module declines to exercise the migration guard, checked as a SQLSTATE rather
#: than by catching the exception class it arrives as: SQLAlchemy wraps it as
#: ``ProgrammingError``, psycopg raises it as ``InsufficientPrivilege``, and
#: neither name is the thing being tested for. Verified against a role created
#: ``NOCREATEDB``: ``exc.orig.sqlstate == "42501"``, message "permission denied
#: to create database".
_INSUFFICIENT_PRIVILEGE = "42501"

#: PostgreSQL's ``object_in_use``: the database is connected to. The sweep below
#: treats it as "not mine to remove" rather than as a failure.
_OBJECT_IN_USE = "55006"

#: Name prefix for the throwaway database the migration is run against. Used
#: both to build the name and to recognise a leaked one, so the two cannot
#: disagree about what this test owns.
_SCRATCH_PREFIX = "smartmatch_dupcheck_"

#: The exact shape this module creates. The sweep drops only names matching it,
#: which keeps the sweep to databases this test made — and, because the pattern
#: admits nothing but the prefix and twelve hex digits, means the name can be
#: interpolated into ``DROP DATABASE`` without any question of what a catalog
#: entry might contain.
_SCRATCH_NAME = re.compile(rf"^{re.escape(_SCRATCH_PREFIX)}[0-9a-f]{{12}}$")


def _insert_account(
    conn: sa.Connection, tenant_id: uuid.UUID, subject: str, *, suspended: bool = False
) -> uuid.UUID:
    user_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO user_account (id, tenant_id, external_subject, email, suspended) "
            "VALUES (:id, :tid, :sub, :email, :susp)"
        ),
        {
            "id": user_id,
            "tid": tenant_id,
            "sub": subject,
            "email": f"{subject}@example.edu",
            "susp": suspended,
        },
    )
    return user_id


@pytest.fixture
def second_tenant(engine: Engine) -> Iterator[uuid.UUID]:
    """A second tenant, so cross-tenant claims can be made about real rows.

    The shared ``tenant_id`` fixture creates one tenant. Everything here is about
    what happens when *two* tenants are involved, so the second is created the
    same way and torn down in the same dependency order.
    """
    tid = uuid.uuid4()
    slug = f"second-{tid.hex[:12]}"
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tid, "slug": slug},
        )

    yield tid

    with engine.begin() as conn:
        # The conftest list, imported rather than copied. A local list of the
        # three tables this module happens to write today would be correct until
        # the first test here creates a job or an org_unit, and would then fail
        # in *teardown* — ``tenant`` is ON DELETE RESTRICT, so an unremoved child
        # makes the tenant undeletable, and the resulting error names the tenant
        # rather than the row that is actually holding it. Crossing the leading
        # underscore is the lesser evil: one list that cannot drift beats two
        # that can.
        for table in _TENANT_SCOPED_TABLES:
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tid})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tid})


def test_one_subject_cannot_hold_accounts_in_two_tenants(
    engine: Engine, tenant_id: uuid.UUID, second_tenant: uuid.UUID
):
    """The defect, asserted as the write the database now refuses.

    Before ``uq_user_account_external_subject`` both inserts succeeded, because
    ``uq_user_account_tenant_subject`` only promises one account per subject *per
    tenant*. The two rows then made ``load_by_subject`` raise
    ``MultipleResultsFound`` on every request that person made.

    This is a behavioural check and not a check that the constraint is listed
    somewhere: it proves the constraint does its job, which existence does not.
    """
    subject = unique_subject("sub-shared")

    with engine.begin() as conn:
        _insert_account(conn, tenant_id, subject)

    with pytest.raises(IntegrityError) as raised, engine.begin() as conn:
        _insert_account(conn, second_tenant, subject)

    assert "uq_user_account_external_subject" in str(raised.value), (
        "the insert was refused by something other than the global subject constraint; "
        f"got {raised.value}"
    )


def test_one_subject_cannot_be_reused_inside_a_tenant(engine: Engine, tenant_id: uuid.UUID):
    """The narrower rule still holds, which is the point of keeping both.

    ``uq_user_account_tenant_subject`` is now implied by the global constraint
    and is retained only because dropping it is a contract-phase action (v1.1
    §4.2). Whichever of the two refuses this insert, the guarantee callers depend
    on is unchanged, so the assertion is on the refusal and not on which
    constraint produced it.
    """
    subject = unique_subject("sub-reused")

    with engine.begin() as conn:
        _insert_account(conn, tenant_id, subject)

    with pytest.raises(IntegrityError), engine.begin() as conn:
        _insert_account(conn, tenant_id, subject)


def test_load_by_subject_resolves_the_one_account_that_holds_it(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id: uuid.UUID
):
    """A subject that exists exactly once resolves to its account and its tenant.

    The tenant is an *output* of this lookup. Asserting it is what distinguishes
    resolving an identity from confirming one the caller already supplied — the
    latter being caller-selected identity, which is what the token deliberately
    does not carry.
    """
    subject = unique_subject("sub-resolved")
    with engine.begin() as conn:
        user_id = _insert_account(conn, tenant_id, subject)
        conn.execute(
            text(
                "INSERT INTO membership (id, tenant_id, user_id, granted_path, role) "
                "VALUES (:id, :tid, :uid, CAST(:path AS ltree), 'coordinator')"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "uid": user_id, "path": "iawest"},
        )

    with session_factory() as session:
        resolved = PrincipalRepository().load_by_subject(session, external_subject=subject)

    assert resolved is not None
    assert resolved.user_id == user_id
    assert resolved.tenant_id == tenant_id
    assert resolved.email == f"{subject}@example.edu"
    assert resolved.principal.suspended is False
    assert [m.role for m in resolved.principal.memberships] == ["coordinator"]
    assert resolved.principal.memberships[0].granted_path == OrgPath.parse("iawest")


def test_load_by_subject_returns_none_when_nothing_holds_the_subject(
    session_factory: sessionmaker[Session],
):
    """An authenticated stranger is ``None``, not an error and not an empty principal."""
    with session_factory() as session:
        resolved = PrincipalRepository().load_by_subject(
            session, external_subject=unique_subject(f"sub-absent-{uuid.uuid4().hex}")
        )

    assert resolved is None


def test_load_by_subject_returns_a_suspended_account_rather_than_none(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id: uuid.UUID
):
    """Suspended is a *state of a known account*, not an absence of one.

    ``load_by_subject`` documents this deliberately: a suspended account is
    returned carrying ``suspended=True`` so that policy can deny it on its own
    terms (v1.1 Appendix A, diagram 23). Returning ``None`` instead would be
    easier and would collapse "this person is suspended" into "we have never
    heard of this person" — and the audit log would then record the same thing
    for a revoked employee and for a stranger, which are not the same event and
    should not be investigated the same way.

    The promise is in a docstring and was checked by nothing in this module. It
    is checked here.
    """
    subject = unique_subject("sub-suspended-principal")
    with engine.begin() as conn:
        user_id = _insert_account(conn, tenant_id, subject, suspended=True)

    with session_factory() as session:
        resolved = PrincipalRepository().load_by_subject(session, external_subject=subject)

    assert resolved is not None, "a suspended account resolved to None, which is 'unknown'"
    assert resolved.user_id == user_id
    assert resolved.principal.suspended is True


# ---------------------------------------------------------------------------
# The migration's own refusal
# ---------------------------------------------------------------------------


def test_the_migration_refuses_to_run_against_duplicate_subjects(engine: Engine):
    """Run ``0003`` for real, against a database that already holds duplicates.

    The check cannot be exercised against the dev database, because the
    constraint it protects is already there — so this builds a scratch database,
    stops it one revision short, inserts the rows the constraint forbids, and
    asks Alembic to continue. Nothing about the migration is stubbed or
    re-implemented here: the assertions are on the process's exit status and on
    the text an operator would actually read.

    What is asserted is the *refusal*, not the wording. Named subjects and a
    total are required because they are the reason this check exists rather than
    letting PostgreSQL raise its own ``IntegrityError``, which reports one
    conflicting key and leaves the scale of the problem unknown. That the
    migration does not quietly deduplicate is asserted the only way it can be —
    the duplicate rows are still there afterwards, and the revision did not move.

    Skipped, not failed, in exactly one case: the test role lacks the privilege
    to create a database, which is a gap in the environment rather than a defect
    in the migration. Every other database failure — a server restart, ``too many
    clients already``, the ``postgres`` maintenance database briefly unreachable —
    fails loudly and deliberately. This is the only test that exercises the
    duplicate guard at all, so a skip a flake can produce would leave the guard
    unverified while CI stayed green, which is the failure mode this whole
    module exists to avoid.
    """
    scratch = f"{_SCRATCH_PREFIX}{uuid.uuid4().hex[:12]}"
    admin_url = engine.url.set(database="postgres")
    scratch_url = engine.url.set(database=scratch)

    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", future=True)
    try:
        try:
            with admin.connect() as conn:
                _drop_leaked_scratch_databases(conn)
                conn.execute(text(f'CREATE DATABASE "{scratch}"'))
        except DBAPIError as exc:  # pragma: no cover - environment dependent
            if getattr(exc.orig, "sqlstate", None) != _INSUFFICIENT_PRIVILEGE:
                raise
            pytest.skip(
                f"{engine.url.username} lacks the privilege to create a database, so the "
                f"migration's duplicate guard cannot be exercised here: {exc.orig}"
            )

        try:
            _run_the_refusal(scratch_url)
        finally:
            with admin.connect() as conn:
                conn.execute(text(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)'))
    finally:
        # Outermost, so the AUTOCOMMIT connection to ``postgres`` is returned
        # even when the create above skips the test — ``pytest.skip`` raises a
        # ``BaseException``, which an ``except`` clause alone does not survive.
        admin.dispose()


def _drop_leaked_scratch_databases(admin: sa.Connection) -> None:
    """Remove scratch databases an earlier run was killed before dropping.

    The drop below lives in a ``finally``, which covers a failing assertion and
    does not cover the process being killed — and on this project being killed
    mid-run is routine rather than exceptional, which is the same premise
    :func:`conftest.unique_subject` is built on. Each leak carries a fresh random
    name, so leaks accumulate quietly instead of colliding and announcing
    themselves.

    Scoped by :data:`_SCRATCH_NAME` to databases this test created, in the same
    spirit as ``_clean_dispatch_state``: clean up what an interrupted run left
    behind, and nothing that belongs to somebody else.

    ``DROP DATABASE`` is issued **without** ``FORCE``. A database still connected
    to is one a concurrently running suite is using, and terminating its backends
    to tidy up would be a worse bug than the leak. PostgreSQL refuses with
    ``object_in_use`` (``55006``) in that case and the name is left alone; any
    other failure is re-raised.
    """
    leaked = [
        name
        for name in admin.execute(text("SELECT datname FROM pg_database")).scalars()
        if _SCRATCH_NAME.match(name)
    ]
    for name in leaked:
        try:
            admin.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) != _OBJECT_IN_USE:
                raise


def _run_the_refusal(scratch_url: sa.engine.URL) -> None:
    """Fill the scratch database with duplicates and require ``0003`` to refuse."""
    _alembic(scratch_url, _REVISION_BEFORE, expect_success=True)

    scratch_engine = create_engine(scratch_url, future=True)
    try:
        # Fixed literals, unlike everywhere else in this suite: this database was
        # created seconds ago and is dropped by the caller, so nothing else can
        # be holding these subjects. They are also load-bearing — the assertions
        # below require the migration to name them back.
        subjects = ("sub-collision-one", "sub-collision-two")
        with scratch_engine.begin() as conn:
            for index, subject in enumerate(subjects):
                for _ in range(2 + index):
                    tid = uuid.uuid4()
                    conn.execute(
                        text(
                            "INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"
                        ),
                        {"id": tid, "slug": f"t-{tid.hex[:12]}"},
                    )
                    _insert_account(conn, tid, subject)

        completed = _alembic(scratch_url, "head", expect_success=False)
        message = completed.stderr

        assert "2 subject(s), across 5 accounts" in message, message
        for subject in subjects:
            assert subject in message, f"{subject} is not named in the failure: {message}"
        assert "not something this migration will resolve on your behalf" in message, message

        with scratch_engine.connect() as conn:
            revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            surviving = conn.execute(
                text("SELECT count(*) FROM user_account WHERE external_subject = ANY(:subs)"),
                {"subs": list(subjects)},
            ).scalar_one()
            constraints = set(
                conn.execute(
                    text(
                        "SELECT conname FROM pg_constraint "
                        "WHERE conrelid = 'user_account'::regclass AND contype = 'u'"
                    )
                ).scalars()
            )

        assert revision == _REVISION_BEFORE, "the failed migration recorded itself as applied"
        assert surviving == 5, "the migration deleted rows instead of refusing to run"
        assert "uq_user_account_external_subject" not in constraints
    finally:
        scratch_engine.dispose()


def _alembic(
    url: sa.engine.URL, revision: str, *, expect_success: bool
) -> subprocess.CompletedProcess[str]:
    """Run ``alembic upgrade`` against ``url`` the way an operator would.

    ``sys.executable -m alembic`` rather than a path to the console script, so
    the interpreter running the tests is the one running the migration and there
    is no virtualenv layout to guess. ``render_as_string(hide_password=False)``
    because the default masks the password as ``***``, which the subprocess
    would then try to authenticate with.
    """
    env = dict(os.environ, SMARTMATCH_DATABASE_URL=url.render_as_string(hide_password=False))
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=_REPO_ROOT / "db",
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if expect_success:
        assert completed.returncode == 0, f"upgrade to {revision} failed: {completed.stderr}"
    else:
        assert completed.returncode != 0, (
            f"upgrade to {revision} succeeded and should not have: {completed.stdout}"
        )
    return completed
