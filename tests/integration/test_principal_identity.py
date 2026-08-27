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

import uuid
from collections.abc import Iterator

import pytest

pytest.importorskip("sqlalchemy")

import sqlalchemy as sa
from conftest import _TENANT_SCOPED_TABLES, unique_subject
from migration_harness import alembic, scratch_database
from smartmatch_authz import OrgPath
from smartmatch_persistence.principals import PrincipalRepository
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration

#: The revision immediately before the one under test. The scratch database is
#: brought to here, filled with the data the constraint forbids, and only then
#: asked to go to head.
_REVISION_BEFORE = "0002_rate_limit"

#: The revision that drops the redundant tenant-scoped subject constraint (F12),
#: and the one before it. The scratch database is brought to the latter so the
#: constraint is present to be removed.
_REVISION_0007 = "0007_drop_tenant_subject"
_REVISION_BEFORE_0007 = "0006_job_owning_unit"

#: The constraint F12 removes, and the one it must leave standing. Named because
#: both appear in assertions on *both* sides of the change, and a typo in one of
#: them would otherwise read as a passing test.
_REDUNDANT_SUBJECT_CONSTRAINT = "uq_user_account_tenant_subject"
_GLOBAL_SUBJECT_CONSTRAINT = "uq_user_account_external_subject"


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
    """The narrower rule outlives the constraint that used to state it.

    ``uq_user_account_tenant_subject`` said this directly and was dropped by
    ``0007`` (F12) as redundant: a subject appearing at most once in the whole
    table appears at most once per tenant. That implication is the entire
    argument for removing it, so the refusal is asserted here **and** attributed
    to the surviving constraint by name — a test that only required "some
    IntegrityError" would pass just as well if F12 had dropped the wrong one.
    """
    subject = unique_subject("sub-reused")

    with engine.begin() as conn:
        _insert_account(conn, tenant_id, subject)

    with pytest.raises(IntegrityError) as raised, engine.begin() as conn:
        _insert_account(conn, tenant_id, subject)

    assert _GLOBAL_SUBJECT_CONSTRAINT in str(raised.value), (
        f"the within-tenant duplicate was refused by something other than "
        f"{_GLOBAL_SUBJECT_CONSTRAINT}, which is the only subject constraint left; "
        f"got {raised.value}"
    )


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

    The scratch database itself comes from ``migration_harness``, which is where
    the create/drop/sweep and the one legitimate skip now live — ``0006`` needs
    the same machinery, and a second copy of a ``DROP DATABASE`` sweep is not a
    thing to have. The skip is still narrow: only a role that cannot create a
    database, which is a gap in the environment rather than a defect in the
    migration.
    """
    with scratch_database(engine) as scratch_url:
        _run_the_refusal(scratch_url)


def _run_the_refusal(scratch_url: sa.engine.URL) -> None:
    """Fill the scratch database with duplicates and require ``0003`` to refuse."""
    alembic(scratch_url, _REVISION_BEFORE, expect_success=True)

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

        completed = alembic(scratch_url, "head", expect_success=False)
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


# ---------------------------------------------------------------------------
# F12 — dropping the redundant constraint without weakening the real one
# ---------------------------------------------------------------------------
#
# ``0003`` added the global constraint and deliberately kept
# ``uq_user_account_tenant_subject``, because dropping it is a contract-phase
# action and ``0003`` was the expand phase (ADR-0008). ``0007`` is that contract
# phase.
#
# The risk is the obvious one, and it is why the guarantee is asserted as
# behaviour above rather than only as a catalog lookup here: "drop the redundant
# constraint" and "drop the constraint that matters" are one identifier apart in
# a migration, and produce identical green suites if nothing attempts the write.
# ``test_one_subject_cannot_hold_accounts_in_two_tenants`` and
# ``test_one_subject_cannot_be_reused_inside_a_tenant`` both name the surviving
# constraint, so a swap fails there. What is added here is *which* constraint
# moved, so a failure locates the change instead of leaving it to be inferred
# from a duplicate-insert error in another module.


def _unique_constraints(conn: sa.Connection, table: str) -> set[str]:
    return set(
        conn.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = CAST(:table AS regclass) AND contype = 'u'"
            ),
            {"table": table},
        ).scalars()
    )


def test_the_redundant_subject_constraint_is_gone_and_the_global_one_is_not(engine: Engine):
    """The state F12 leaves behind, on the database the rest of the suite uses."""
    with engine.connect() as conn:
        constraints = _unique_constraints(conn, "user_account")

    assert _REDUNDANT_SUBJECT_CONSTRAINT not in constraints, (
        f"{_REDUNDANT_SUBJECT_CONSTRAINT} is still present; F12 removes it as contract-phase work"
    )
    assert _GLOBAL_SUBJECT_CONSTRAINT in constraints, (
        f"{_GLOBAL_SUBJECT_CONSTRAINT} is missing — ADR-0008's global subject "
        f"uniqueness has been dropped, and load_by_subject's .one_or_none() is "
        f"unsound again"
    )


def test_the_migration_drops_exactly_one_constraint(engine: Engine):
    """Run ``0007`` against a scratch database and compare before with after.

    Asserted as a set difference rather than as two membership checks, so a
    revision that dropped the redundant constraint *and* something else fails
    here — which two independent assertions about two named constraints would
    not.
    """
    with scratch_database(engine) as scratch_url:
        alembic(scratch_url, _REVISION_BEFORE_0007, expect_success=True)

        scratch_engine = create_engine(scratch_url, future=True)
        try:
            with scratch_engine.connect() as conn:
                before = _unique_constraints(conn, "user_account")

            alembic(scratch_url, _REVISION_0007, expect_success=True)

            with scratch_engine.connect() as conn:
                after = _unique_constraints(conn, "user_account")
        finally:
            scratch_engine.dispose()

    assert _REDUNDANT_SUBJECT_CONSTRAINT in before, (
        f"{_REDUNDANT_SUBJECT_CONSTRAINT} was already absent at "
        f"{_REVISION_BEFORE_0007}; this test proves nothing"
    )
    assert before - after == {_REDUNDANT_SUBJECT_CONSTRAINT}, (
        f"0007 removed {sorted(before - after)}, not exactly "
        f"{sorted({_REDUNDANT_SUBJECT_CONSTRAINT})}"
    )
    assert not after - before, f"0007 added constraints it does not declare: {after - before}"


def test_the_0007_downgrade_restores_the_removed_constraint(engine: Engine):
    """A reversed ``0007`` must leave the schema an older release was built against.

    Restoring it is the only thing the downgrade owes: the global constraint was
    never touched, so a downgraded database is exactly the schema ``0006``
    produced.
    """
    with scratch_database(engine) as scratch_url:
        alembic(scratch_url, "head", expect_success=True)

        scratch_engine = create_engine(scratch_url, future=True)
        try:
            with scratch_engine.connect() as conn:
                assert _REDUNDANT_SUBJECT_CONSTRAINT not in _unique_constraints(
                    conn, "user_account"
                )

            alembic(scratch_url, _REVISION_BEFORE_0007, expect_success=True, command="downgrade")

            with scratch_engine.connect() as conn:
                restored = _unique_constraints(conn, "user_account")
                revision = conn.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
        finally:
            scratch_engine.dispose()

    assert _REDUNDANT_SUBJECT_CONSTRAINT in restored
    assert _GLOBAL_SUBJECT_CONSTRAINT in restored
    assert revision == _REVISION_BEFORE_0007
