"""Event registration, against real PostgreSQL — the file that used to pin its absence.

Customer §15 asks that a student be able to *register* for an event. Card
``CBA-STUDENT-EVENTS`` could not ship it and this file is what it left behind: a
set of **absence controls** asserting that no registration table, column or
route had quietly appeared, together with ``REQUIRED_REGISTRATION_COLUMNS`` — the
shape such a table would need — so that the card closing **OQ-CBA-018** would
inherit a column list rather than a paragraph.

Migration ``0026`` is that card. This file is therefore the diff its predecessor
asked for: rewritten by the card that answered the question, in the same branch
as the migration that made the old assertions wrong.

## What was kept, and why keeping it matters more than the rest

The controls that were about **not confusing a registration with an
attendance** are still here, unchanged in force and wider in reach.
:class:`TestAttendanceStaysAttendance` still reads
``ck_attendance_record_method`` out of the database and still requires its three
values to describe somebody who was *there*; it still requires
``ck_point_ledger_entry_kind`` to derive every ``attendance_credit`` from a
``source_attendance_id``. Those never depended on registration being absent.
They depended on registration not being *smuggled into attendance*, which is a
hazard that grew rather than shrank the moment a Register button became real.

:class:`TestRegistrationHasNoPathToPoints` is new and is the same idea aimed at
the new table: no foreign key between ``event_registration`` and
``point_ledger_entry`` in either direction, and no ``(tenant_id, id)``
uniqueness for one to be built on later. ADR-0013 says points derive from
attendance and nothing else; this is that sentence as a query against
``pg_constraint``.

## What replaced the absence controls

``REQUIRED_REGISTRATION_COLUMNS`` survives with its meaning inverted. It was a
checklist of what would have to exist; it is now checked against the migrated
database column by column, so the shape the blocked card specified is the shape
the unblocking card actually built — and a later revision dropping one of them
fails here rather than in whatever read went quiet.

The behavioural half — that registering twice is one registration, that
cancelling is a transition rather than a delete, and that a re-registration
reuses the row — is asserted through
:class:`~smartmatch_persistence.event_registration.EventRegistrationRepository`
against the tables, **never against an HTTP response**. ``get_session`` rolls
back unconditionally, so a route that forgets to commit returns a clean ``201``
and stores nothing; a test that believed the status code would pass on exactly
that defect. Every assertion below reads the row back.

Requires a live migrated PostgreSQL and skips when none is reachable.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")

from conftest import ensure_event, ensure_owning_unit, unique_subject
from smartmatch_domain.event_registration import (
    REGISTRATION_STATUSES,
    STATUS_CANCELLED,
    STATUS_REGISTERED,
)
from smartmatch_persistence import schema
from smartmatch_persistence.event_registration import EventRegistrationRepository
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration

#: Repository root, from ``tests/integration/``.
_REPO_ROOT = Path(__file__).resolve().parents[2]

#: The revision that ends the absence, and the one it follows. Revision **ids**,
#: not filenames: ``0025``'s id happens to match its file, but ``0024``'s does
#: not, and a ``down_revision`` naming a filename resolves to nothing.
_THIS_REVISION = "0026_event_registration"
_PARENT_REVISION = "0025_cba_contact_identity"

#: The table this card adds.
_TABLE = "event_registration"

#: The columns ``event_registration`` has, and the reason each one is not
#: optional. This dictionary is the *survivor* of the version of this file that
#: pinned the absence, where it was a specification for a table that did not
#: exist. It is now checked against the migrated database, so the shape the
#: blocked card asked for is the shape the unblocking card built.
#:
#: Note what is still **not** on it: nothing that would let a registration
#: become an attendance. The two are separate rows in separate tables, so that
#: "registered but did not attend" is a query rather than an archaeology
#: exercise.
REQUIRED_REGISTRATION_COLUMNS: dict[str, str] = {
    "id": "surrogate primary key, as every table in this schema has",
    "tenant_id": "tenant isolation is structural here, never a filter applied afterwards",
    "owning_unit_id": (
        "A5-shaped, matching attendance_record and job: authorization is unit-scoped and a "
        "row with no unit cannot be scoped to a subtree"
    ),
    "event_id": (
        "composite foreign key on (tenant_id, event_id), RESTRICT, so an event cannot be "
        "deleted out from under a student holding a place at it"
    ),
    "subject_id": (
        "composite foreign key on (tenant_id, subject_id) into user_account; the student, "
        "and the column a self-scoped read filters on"
    ),
    "status": (
        "registered / cancelled, with a CHECK. A cancellation must be a state on the row "
        "rather than a DELETE, or 'they cancelled' and 'they never registered' become the "
        "same absence"
    ),
    "registered_at": "when the place was taken, which never moves once it is set",
    "updated_at": "when the status last moved, so a cancellation has a time",
}

#: The uniqueness that makes the write idempotent without an ``Idempotency-Key``
#: — the reasoning ``routers/speaker_requests.py`` gives for deriving idempotency
#: from the data's own identity.
REQUIRED_REGISTRATION_UNIQUENESS = ("tenant_id", "subject_id", "event_id")

#: The status vocabulary ``ck_event_registration_status`` admits.
#:
#: Two values. ``waitlisted`` was named in this file's predecessor as a plausible
#: third and migration ``0026`` deliberately left it out: a waitlist is overflow
#: from a capacity and no capacity exists anywhere in this schema, so the value
#: would be one no writer could produce — a vocabulary invented by DDL ahead of
#: the decision that gives it meaning. Recorded as OQ-CBA-029, and asserted below
#: as an absence rather than merely unmentioned.
_STATUSES = (STATUS_REGISTERED, STATUS_CANCELLED)

#: Values that must never appear in ``ck_attendance_record_method``. The same
#: list the absence-control version of this file scanned every table and column
#: name for, kept pointed at the one constraint where it still means something.
_REGISTRATION_MARKERS = ("registration", "register", "rsvp", "signup", "sign_up")


def _script_directory():
    """The Alembic script directory, loaded from ``db/alembic.ini``.

    Imported inside the function rather than at module scope so the revision
    tests skip cleanly where Alembic is absent instead of failing collection for
    the whole module — ``test_cba_contact_schema.py``'s arrangement.
    """
    alembic_config = pytest.importorskip("alembic.config")
    alembic_script = pytest.importorskip("alembic.script")

    config = alembic_config.Config(str(_REPO_ROOT / "db" / "alembic.ini"))
    config.set_main_option("script_location", str(_REPO_ROOT / "db" / "migrations"))
    return alembic_script.ScriptDirectory.from_config(config)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_registrations(engine: Engine, tenant_id):
    """Delete this file's rows before ``tenant_id`` tears its own down.

    Belt to ``conftest._TENANT_SCOPED_TABLES``' braces. ``event_registration``
    holds ``ON DELETE RESTRICT`` references to ``event``, ``user_account`` *and*
    ``org_unit``, so a row left behind would fail the tenant teardown on three
    different deletes — the hazard ``test_cba_contact_schema.py``'s own cleanup
    fixture exists for, with one more parent.
    """
    yield
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM event_registration WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )


@pytest.fixture
def student_id(engine: Engine, tenant_id: uuid.UUID) -> uuid.UUID:
    """One ``user_account`` to be the student.

    ``external_subject`` goes through :func:`conftest.unique_subject` because
    ``uq_user_account_external_subject`` is **global** — migration ``0007``
    dropped the tenant-scoped constraint that used to stand beside it, so two
    tenants cannot both hold the literal string a test would otherwise reach for.
    """
    subject_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                "VALUES (:id, :tid, :sub, :email)"
            ),
            {
                "id": subject_id,
                "tid": tenant_id,
                "sub": unique_subject(f"registration-{subject_id.hex[:8]}"),
                "email": f"{subject_id.hex[:8]}@example.edu",
            },
        )
    return subject_id


@pytest.fixture
def unit_id(engine: Engine, tenant_id: uuid.UUID) -> uuid.UUID:
    with engine.begin() as conn:
        return ensure_owning_unit(conn, tenant_id)


@pytest.fixture
def event_id(engine: Engine, tenant_id: uuid.UUID) -> uuid.UUID:
    with engine.begin() as conn:
        return ensure_event(conn, tenant_id, slug="registration")


@pytest.fixture
def other_event_id(engine: Engine, tenant_id: uuid.UUID) -> uuid.UUID:
    """A second event, for the assertions that are about two of them."""
    with engine.begin() as conn:
        return ensure_event(conn, tenant_id, slug="registration-other")


@pytest.fixture
def session(session_factory: sessionmaker[Session]):
    """A session the tests drive the repository through, committed explicitly.

    The repository commits nothing — transaction boundaries belong to its
    caller — so every test here commits for itself and then reads back. That is
    not ceremony: it is the same sequence the route performs, and it is what
    makes "the row is actually there" an assertion about storage rather than
    about a return value.
    """
    with session_factory() as db:
        yield db
        db.rollback()


@pytest.fixture
def registrations() -> EventRegistrationRepository:
    return EventRegistrationRepository()


def _stored_status(session: Session, *, tenant_id, subject_id, event_id) -> str | None:
    """Read ``status`` straight out of the table.

    Deliberately not routed through the repository. A test that asked the writer
    what it wrote would prove the writer self-consistent; this asks PostgreSQL.
    """
    return session.execute(
        text(
            "SELECT status FROM event_registration "
            "WHERE tenant_id = :tid AND subject_id = :sid AND event_id = :eid"
        ),
        {"tid": tenant_id, "sid": subject_id, "eid": event_id},
    ).scalar_one_or_none()


def _row_count(session: Session, *, tenant_id, subject_id, event_id) -> int:
    return session.execute(
        text(
            "SELECT count(*) FROM event_registration "
            "WHERE tenant_id = :tid AND subject_id = :sid AND event_id = :eid"
        ),
        {"tid": tenant_id, "sid": subject_id, "eid": event_id},
    ).scalar_one()


# ---------------------------------------------------------------------------
# The revision graph. No database.
# ---------------------------------------------------------------------------


class TestTheMigrationIsTheHeadAndFollowsItsParent:
    """``0026`` extends the chain rather than branching beside it.

    Two heads is the quiet failure of parallel migration work: Alembic refuses
    ``upgrade head`` with an ambiguity error only at deploy time, on a branch
    that has already merged. Several CBA cards write migrations at once, which is
    exactly the condition that produces one.
    """

    def test_the_registration_revision_is_the_single_head(self) -> None:
        heads = _script_directory().get_heads()

        assert heads == [_THIS_REVISION], (
            f"expected {_THIS_REVISION} to be the single Alembic head, got {heads}"
        )

    def test_it_chains_to_the_contact_identity_revision(self) -> None:
        """``down_revision`` names ``0025``'s revision id, not its filename."""
        script = _script_directory().get_revision(_THIS_REVISION)

        assert script.down_revision == _PARENT_REVISION


# ---------------------------------------------------------------------------
# The shape, against the migrated database and against schema.py
# ---------------------------------------------------------------------------


class TestTheTableHasTheShapeTheBlockedCardSpecified:
    """``REQUIRED_REGISTRATION_COLUMNS``, held against what actually shipped.

    Both the database and ``schema.py`` are checked. The database is the one that
    decides — a table could exist in Python and never have been migrated — and
    ``schema.py`` is checked too because the reverse failure, a migration nobody
    mirrored, is the one with no column to notice.
    """

    def test_every_specified_column_exists_in_the_migrated_database(self, engine: Engine) -> None:
        columns = {column["name"] for column in inspect(engine).get_columns(_TABLE)}

        missing = sorted(set(REQUIRED_REGISTRATION_COLUMNS) - columns)
        assert missing == [], (
            f"{_TABLE} is missing {missing}. Each of those columns was specified "
            "with a reason before the table existed; dropping one now is a "
            "decision that has to be argued, not a refactor."
        )

    def test_the_declared_schema_mirrors_the_same_columns(self) -> None:
        declared = set(schema.event_registration.columns.keys())

        assert set(REQUIRED_REGISTRATION_COLUMNS) <= declared

    def test_every_specified_column_still_carries_the_reason_it_is_required(self) -> None:
        assert REQUIRED_REGISTRATION_COLUMNS
        for column, reason in REQUIRED_REGISTRATION_COLUMNS.items():
            assert reason.strip(), f"{column} is listed with no reason"

    def test_the_natural_key_is_unique_in_the_database(self, engine: Engine) -> None:
        """``uq_event_registration_subject_event``, read out of PostgreSQL.

        The constraint *is* the idempotency, so it is asserted on the database
        rather than inferred from a repository that happens not to insert twice.
        """
        constraints = inspect(engine).get_unique_constraints(_TABLE)
        by_name = {constraint["name"]: constraint for constraint in constraints}

        assert "uq_event_registration_subject_event" in by_name
        assert (
            tuple(by_name["uq_event_registration_subject_event"]["column_names"])
            == REQUIRED_REGISTRATION_UNIQUENESS
        )

    def test_the_status_vocabulary_is_exactly_two_values(self, engine: Engine) -> None:
        """``ck_event_registration_status``, and the absence of ``waitlisted``.

        The absence is asserted rather than left unmentioned: a third value added
        without a capacity to justify it should fail here, which is the whole of
        what OQ-CBA-029 is holding open.
        """
        with engine.connect() as conn:
            definition = conn.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conname = 'ck_event_registration_status'"
                )
            ).scalar_one()

        for status in _STATUSES:
            assert f"'{status}'" in definition
        assert "waitlist" not in definition.lower(), (
            "a waitlist status appeared in the CHECK. No capacity column exists "
            "for it to overflow from — see OQ-CBA-029."
        )

    def test_the_domain_vocabulary_agrees_with_the_constraint(self) -> None:
        """``smartmatch_domain`` and the CHECK say the same two words.

        The domain module is where the transitions live, so a vocabulary that
        drifted from the constraint would produce a status the database refuses
        at exactly the moment a student clicked something.
        """
        assert frozenset(_STATUSES) == REGISTRATION_STATUSES

    def test_all_three_foreign_keys_are_composite_on_tenant(self, engine: Engine) -> None:
        """Tenant isolation held by the key rather than by a remembered predicate.

        Architecture v1.1 §2.2. A registration must not be able to name an event,
        a student, or a unit belonging to another tenant, and a single-column
        foreign key would permit exactly that.
        """
        keys = inspect(engine).get_foreign_keys(_TABLE)
        targets = {key["referred_table"]: key for key in keys}

        assert set(targets) == {"event", "user_account", "org_unit"}
        for table, key in targets.items():
            assert "tenant_id" in key["constrained_columns"], (
                f"the foreign key to {table} is not composite on tenant_id"
            )


# ---------------------------------------------------------------------------
# The separation from points. The controls this file has always carried.
# ---------------------------------------------------------------------------


class TestAttendanceStaysAttendance:
    """The misuse ``CBA-STUDENT-EVENTS`` refused, still refused now that it is reachable.

    These assertions never depended on registration being absent. They depend on
    registration never being written *into attendance*, which became a live
    hazard rather than a hypothetical one the moment a Register control existed.
    """

    def test_attendance_admits_only_the_three_ways_somebody_actually_attended(
        self, engine: Engine
    ) -> None:
        """``ck_attendance_record_method``, read out of the database.

        Each of the three describes a person who was *there*: a code scanned in
        the room, a coordinator recording who came, or a roster imported after
        the fact. A fourth value meaning "signed up" would make the table answer
        two questions with one row shape, and ADR-0013 would credit points for
        both — which is precisely the shortcut migration ``0026`` exists to make
        unnecessary.
        """
        with engine.connect() as conn:
            definition = conn.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conname = 'ck_attendance_record_method'"
                )
            ).scalar_one()

        for attended in ("qr_scan", "coordinator_entry", "import"):
            assert attended in definition
        for not_attended in _REGISTRATION_MARKERS:
            assert not_attended not in definition.lower()

    def test_points_still_derive_from_attendance_and_from_nothing_else(
        self, engine: Engine
    ) -> None:
        """ADR-0013, and why a registration row could not have been an attendance row."""
        with engine.connect() as conn:
            definition = conn.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conname = 'ck_point_ledger_entry_kind'"
                )
            ).scalar_one()

        assert "attendance_credit" in definition
        assert "source_attendance_id IS NOT NULL" in definition


class TestRegistrationHasNoPathToPoints:
    """The new table's half of the same guarantee, asserted structurally.

    ADR-0013: points derive from recorded attendance and nothing else. That is a
    sentence in a decision record, and these are the queries that keep it true of
    the schema — so a later card cannot grow a path from an intention to a credit
    one plausible column at a time.
    """

    def test_the_ledger_holds_no_foreign_key_to_a_registration(self, engine: Engine) -> None:
        referred = {
            key["referred_table"] for key in inspect(engine).get_foreign_keys("point_ledger_entry")
        }

        assert _TABLE not in referred, (
            "point_ledger_entry references event_registration. Points derive from "
            "attendance and nothing else (ADR-0013); a registration is a claim "
            "about the future and crediting it pays for an event nobody attended."
        )

    def test_no_ledger_column_names_a_registration(self, engine: Engine) -> None:
        columns = {column["name"] for column in inspect(engine).get_columns("point_ledger_entry")}

        offenders = sorted(
            name for name in columns for marker in _REGISTRATION_MARKERS if marker in name.lower()
        )
        assert offenders == [], f"these ledger columns describe a registration: {offenders}"

    def test_the_registration_table_references_nothing_that_carries_points(
        self, engine: Engine
    ) -> None:
        """The reverse direction, which is the one a well-meaning card would add."""
        referred = {key["referred_table"] for key in inspect(engine).get_foreign_keys(_TABLE)}

        assert "point_ledger_entry" not in referred
        assert "attendance_record" not in referred, (
            "event_registration references attendance_record. The two tables "
            "answer two questions, and a key between them would make a "
            "registration derivable from evidence it is not."
        )

    def test_no_uniqueness_exists_for_a_ledger_reference_to_be_built_on(
        self, engine: Engine
    ) -> None:
        """No ``(tenant_id, id)`` constraint, which is what such a key would need.

        ``uq_attendance_record_tenant_id`` exists precisely because
        ``point_ledger_entry.source_attendance_id`` references it. Migration
        ``0026`` deliberately declines the equivalent, following ``0008``'s rule
        that the constraint is added by whichever revision first needs it — and
        the one revision that must never need it is the ledger's.
        """
        constrained = {
            tuple(constraint["column_names"])
            for constraint in inspect(engine).get_unique_constraints(_TABLE)
        }

        assert ("tenant_id", "id") not in constrained


# ---------------------------------------------------------------------------
# Behaviour, asserted against the tables
# ---------------------------------------------------------------------------


class TestRegisteringIsIdempotent:
    """A second click is the same registration, and the table is what says so."""

    def test_a_first_registration_stores_a_registered_row(
        self, session, registrations, tenant_id, unit_id, event_id, student_id
    ) -> None:
        result = registrations.register(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=student_id,
            event_id=event_id,
        )
        session.commit()

        assert result.created is True
        assert result.changed is True
        assert (
            _stored_status(session, tenant_id=tenant_id, subject_id=student_id, event_id=event_id)
            == STATUS_REGISTERED
        )

    def test_registering_twice_leaves_exactly_one_row(
        self, session, registrations, tenant_id, unit_id, event_id, student_id
    ) -> None:
        """The card's central requirement, counted rather than inferred.

        A count against the table, not an HTTP status and not the repository's
        own report: ``get_session`` rolls back unconditionally, so a route that
        never committed would satisfy any assertion made about its response.
        """
        for _ in range(2):
            registrations.register(
                session,
                tenant_id=tenant_id,
                owning_unit_id=unit_id,
                subject_id=student_id,
                event_id=event_id,
            )
            session.commit()

        assert (
            _row_count(session, tenant_id=tenant_id, subject_id=student_id, event_id=event_id) == 1
        )

    def test_the_second_registration_reports_that_it_created_nothing(
        self, session, registrations, tenant_id, unit_id, event_id, student_id
    ) -> None:
        """``created`` is what a route turns into ``201`` versus ``200``."""
        registrations.register(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=student_id,
            event_id=event_id,
        )
        session.commit()

        second = registrations.register(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=student_id,
            event_id=event_id,
        )
        session.commit()

        assert second.created is False
        assert second.changed is False

    def test_a_repeated_registration_does_not_move_updated_at(
        self, session, registrations, tenant_id, unit_id, event_id, student_id
    ) -> None:
        """Migration ``0026`` defines ``updated_at`` as "when the status last moved".

        So a no-op must not touch it. An unconditional upsert setting
        ``updated_at = now()`` would pass every other test in this class and make
        this column claim a transition that never happened.
        """
        first = registrations.register(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=student_id,
            event_id=event_id,
        )
        session.commit()

        second = registrations.register(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=student_id,
            event_id=event_id,
        )
        session.commit()

        assert second.row is not None and first.row is not None
        assert second.row.updated_at == first.row.updated_at
        assert second.row.id == first.row.id

    def test_the_database_refuses_a_duplicate_written_around_the_repository(
        self, session, registrations, tenant_id, unit_id, event_id, student_id
    ) -> None:
        """The constraint, not the writer, is what makes the triple unique.

        Written straight through ``INSERT`` so the guarantee is shown to survive
        a caller that does not use the repository at all — the discipline
        ``test_cba_classification_schema.py`` states for its own constraints.
        """
        registrations.register(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=student_id,
            event_id=event_id,
        )
        session.commit()

        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO event_registration "
                    "(id, tenant_id, owning_unit_id, event_id, subject_id, status) "
                    "VALUES (:id, :tid, :unit, :eid, :sid, 'registered')"
                ),
                {
                    "id": uuid.uuid4(),
                    "tid": tenant_id,
                    "unit": unit_id,
                    "eid": event_id,
                    "sid": student_id,
                },
            )
        session.rollback()

    def test_one_student_may_register_for_two_different_events(
        self, session, registrations, tenant_id, unit_id, event_id, other_event_id, student_id
    ) -> None:
        """The uniqueness is per event, not per student.

        Stated because the constraint that makes a *repeat* idempotent would, if
        it were narrower by one column, make a second registration impossible.
        """
        for target in (event_id, other_event_id):
            registrations.register(
                session,
                tenant_id=tenant_id,
                owning_unit_id=unit_id,
                subject_id=student_id,
                event_id=target,
            )
        session.commit()

        stored = session.execute(
            text(
                "SELECT count(*) FROM event_registration "
                "WHERE tenant_id = :tid AND subject_id = :sid"
            ),
            {"tid": tenant_id, "sid": student_id},
        ).scalar_one()
        assert stored == 2


class TestCancellingIsATransitionAndNotADelete:
    """The decision migration ``0026`` argues, asserted on the row that survives."""

    def test_cancelling_keeps_the_row_and_moves_its_status(
        self, session, registrations, tenant_id, unit_id, event_id, student_id
    ) -> None:
        registrations.register(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=student_id,
            event_id=event_id,
        )
        session.commit()

        registrations.cancel(session, tenant_id=tenant_id, subject_id=student_id, event_id=event_id)
        session.commit()

        assert (
            _row_count(session, tenant_id=tenant_id, subject_id=student_id, event_id=event_id) == 1
        ), (
            "cancelling deleted the row. 'They cancelled' and 'they never "
            "registered' must not be the same absence."
        )
        assert (
            _stored_status(session, tenant_id=tenant_id, subject_id=student_id, event_id=event_id)
            == STATUS_CANCELLED
        )

    def test_a_cancellation_has_a_time_and_the_original_one_is_kept(
        self, session, registrations, tenant_id, unit_id, event_id, student_id
    ) -> None:
        """``registered_at`` does not move; ``updated_at`` does.

        Which is the pair that lets a coordinator ask how late a cancellation
        was — the question a ``DELETE`` would have discarded the evidence for.
        """
        first = registrations.register(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=student_id,
            event_id=event_id,
        )
        session.commit()
        assert first.row is not None

        cancelled = registrations.cancel(
            session, tenant_id=tenant_id, subject_id=student_id, event_id=event_id
        )
        session.commit()

        assert cancelled.row is not None
        assert cancelled.row.registered_at == first.row.registered_at
        assert cancelled.row.updated_at >= first.row.updated_at

    def test_cancelling_twice_is_not_an_error_and_changes_nothing(
        self, session, registrations, tenant_id, unit_id, event_id, student_id
    ) -> None:
        registrations.register(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=student_id,
            event_id=event_id,
        )
        session.commit()
        registrations.cancel(session, tenant_id=tenant_id, subject_id=student_id, event_id=event_id)
        session.commit()

        second = registrations.cancel(
            session, tenant_id=tenant_id, subject_id=student_id, event_id=event_id
        )
        session.commit()

        assert second.changed is False
        assert (
            _stored_status(session, tenant_id=tenant_id, subject_id=student_id, event_id=event_id)
            == STATUS_CANCELLED
        )

    def test_cancelling_something_never_registered_writes_no_row(
        self, session, registrations, tenant_id, event_id, student_id
    ) -> None:
        """A student who never registered has no registration to cancel.

        Manufacturing a pre-cancelled row would put one in the table for every
        stray click, and would make "cancelled" stop meaning "they had a place
        and gave it up".
        """
        result = registrations.cancel(
            session, tenant_id=tenant_id, subject_id=student_id, event_id=event_id
        )
        session.commit()

        assert result.row is None
        assert result.changed is False
        assert (
            _row_count(session, tenant_id=tenant_id, subject_id=student_id, event_id=event_id) == 0
        )

    def test_registering_again_after_cancelling_reuses_the_same_row(
        self, session, registrations, tenant_id, unit_id, event_id, student_id
    ) -> None:
        """One row per student per event, whatever the status.

        ``created`` is ``False`` on the return: the uniqueness holds across a
        cancellation, so a student who comes back moves the row they already had
        rather than acquiring a second one — and ``registered_at`` still says
        when they first took the place.
        """
        first = registrations.register(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=student_id,
            event_id=event_id,
        )
        session.commit()
        registrations.cancel(session, tenant_id=tenant_id, subject_id=student_id, event_id=event_id)
        session.commit()

        again = registrations.register(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=student_id,
            event_id=event_id,
        )
        session.commit()

        assert first.row is not None and again.row is not None
        assert again.created is False
        assert again.changed is True
        assert again.row.id == first.row.id
        assert again.row.registered_at == first.row.registered_at
        assert (
            _row_count(session, tenant_id=tenant_id, subject_id=student_id, event_id=event_id) == 1
        )


class TestTheReadsNarrowToActiveRegistrations:
    """What "on my agenda" is allowed to be built from."""

    def test_an_active_registration_is_reported_as_registered(
        self, session, registrations, tenant_id, unit_id, event_id, student_id
    ) -> None:
        registrations.register(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=student_id,
            event_id=event_id,
        )
        session.commit()

        assert registrations.is_registered(
            session, tenant_id=tenant_id, subject_id=student_id, event_id=event_id
        )
        assert registrations.active_event_ids(
            session, tenant_id=tenant_id, subject_id=student_id, event_ids=[event_id]
        ) == {event_id}

    def test_a_cancelled_registration_is_not_an_active_one(
        self, session, registrations, tenant_id, unit_id, event_id, student_id
    ) -> None:
        """Cancelling actually removes the event from the agenda.

        And therefore withdraws the ``.ics`` link with it, which is what makes
        cancelling mean something rather than annotate something.
        """
        registrations.register(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=student_id,
            event_id=event_id,
        )
        session.commit()
        registrations.cancel(session, tenant_id=tenant_id, subject_id=student_id, event_id=event_id)
        session.commit()

        assert not registrations.is_registered(
            session, tenant_id=tenant_id, subject_id=student_id, event_id=event_id
        )
        assert (
            registrations.active_event_ids(
                session, tenant_id=tenant_id, subject_id=student_id, event_ids=[event_id]
            )
            == set()
        )

    def test_a_cancelled_registration_is_still_readable_as_a_row(
        self, session, registrations, tenant_id, unit_id, event_id, student_id
    ) -> None:
        """The distinction the whole design turns on, at the reader.

        ``rows_for_events`` returns every status so a listing can render "you
        cancelled this" differently from "you never registered". A reader that
        filtered cancelled rows away would make the two indistinguishable again
        one layer above the table that kept them apart.
        """
        registrations.register(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=student_id,
            event_id=event_id,
        )
        session.commit()
        registrations.cancel(session, tenant_id=tenant_id, subject_id=student_id, event_id=event_id)
        session.commit()

        rows = registrations.rows_for_events(
            session, tenant_id=tenant_id, subject_id=student_id, event_ids=[event_id]
        )

        assert event_id in rows
        assert rows[event_id].status == STATUS_CANCELLED

    def test_a_student_who_never_registered_has_no_row_at_all(
        self, session, registrations, tenant_id, event_id, student_id
    ) -> None:
        assert (
            registrations.get(
                session, tenant_id=tenant_id, subject_id=student_id, event_id=event_id
            )
            is None
        )


class TestRegistrationIsScopedToItsTenantAndItsStudent:
    """The two scopes that are structural rather than remembered."""

    def test_another_students_registration_is_not_this_students(
        self, engine, session, registrations, tenant_id, unit_id, event_id, student_id
    ) -> None:
        """Self-scoping, at the layer that does the filtering.

        The route never accepts a subject id, so the only way a student could see
        somebody else's registration is a reader that forgot its predicate. This
        is that predicate, asserted.
        """
        other = uuid.uuid4()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                    "VALUES (:id, :tid, :sub, :email)"
                ),
                {
                    "id": other,
                    "tid": tenant_id,
                    "sub": unique_subject(f"registration-other-{other.hex[:8]}"),
                    "email": f"{other.hex[:8]}@example.edu",
                },
            )

        registrations.register(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=other,
            event_id=event_id,
        )
        session.commit()

        assert (
            registrations.get(
                session, tenant_id=tenant_id, subject_id=student_id, event_id=event_id
            )
            is None
        )
        assert not registrations.is_registered(
            session, tenant_id=tenant_id, subject_id=student_id, event_id=event_id
        )

    def test_a_registration_cannot_name_an_event_this_tenant_does_not_have(
        self, session, tenant_id, unit_id, student_id
    ) -> None:
        """The composite foreign key, not a predicate somebody has to write.

        Architecture v1.1 §2.2. A single-column key to ``event`` would still
        refuse an id that exists nowhere, but would accept one belonging to
        another tenant — and tenant isolation would then rest on every future
        query remembering to filter.
        """
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO event_registration "
                    "(id, tenant_id, owning_unit_id, event_id, subject_id, status) "
                    "VALUES (:id, :tid, :unit, :eid, :sid, 'registered')"
                ),
                {
                    "id": uuid.uuid4(),
                    "tid": tenant_id,
                    "unit": unit_id,
                    "eid": uuid.uuid4(),
                    "sid": student_id,
                },
            )
        session.rollback()

    def test_an_unknown_status_is_refused_by_the_database(
        self, session, tenant_id, unit_id, event_id, student_id
    ) -> None:
        """``ck_event_registration_status``, attempted rather than read.

        Including the value this file's predecessor expected to exist: a
        ``waitlisted`` row is refused, because no capacity exists for it to
        overflow from (OQ-CBA-029).
        """
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO event_registration "
                    "(id, tenant_id, owning_unit_id, event_id, subject_id, status) "
                    "VALUES (:id, :tid, :unit, :eid, :sid, 'waitlisted')"
                ),
                {
                    "id": uuid.uuid4(),
                    "tid": tenant_id,
                    "unit": unit_id,
                    "eid": event_id,
                    "sid": student_id,
                },
            )
        session.rollback()


class TestRegisteringWritesNothingElse:
    """The absence that used to be this whole file, aimed where it still bites.

    Registering must not produce an attendance row and must not produce a ledger
    entry. Asserted as counts around a real write rather than as a claim about
    the code, because the failure this guards against is a *future* card adding a
    convenience — "while we are here, credit the student" — that no amount of
    docstring prevents.
    """

    def test_registering_creates_no_attendance_record(
        self, session, registrations, tenant_id, unit_id, event_id, student_id
    ) -> None:
        registrations.register(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=student_id,
            event_id=event_id,
        )
        session.commit()

        attendance = session.execute(
            text(
                "SELECT count(*) FROM attendance_record "
                "WHERE tenant_id = :tid AND subject_id = :sid AND event_id = :eid"
            ),
            {"tid": tenant_id, "sid": student_id, "eid": event_id},
        ).scalar_one()

        assert attendance == 0, (
            "registering wrote an attendance_record. ADR-0013 makes attendance "
            "the only input to points, so this credits a student for an event "
            "they have not been to."
        )

    def test_registering_creates_no_ledger_entry(
        self, session, registrations, tenant_id, unit_id, event_id, student_id
    ) -> None:
        before = session.execute(
            text("SELECT count(*) FROM point_ledger_entry WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        ).scalar_one()

        registrations.register(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=student_id,
            event_id=event_id,
        )
        session.commit()

        after = session.execute(
            text("SELECT count(*) FROM point_ledger_entry WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        ).scalar_one()

        assert after == before
