"""Event registration is **not** shipped, and this file is why that is safe.

Customer §15 asks that a student be able to *register* for an event. Card
``CBA-STUDENT-EVENTS`` did not ship it, and the reason is a schema fact rather
than a scheduling one: there is no registration table, this card's migration
queue is closed, and every table that could have been pressed into service means
something else.

## The one that would have worked, and what it would have cost

``attendance_record`` is the obvious candidate. It ties a ``subject_id`` to an
``event_id`` inside a tenant, it is already unique on that pair, and a
``POST .../register`` writing one would have made the button work today.

It would also have been a fabrication with a paper trail. ADR-0013 makes
attendance the **only** input to points; ``point_ledger_entry``'s
``attendance_credit`` shape derives from ``source_attendance_id``; and
``uq_attendance_record_subject_event`` means the row a registration wrote is
indistinguishable from the row a check-in writes. A student who registered for
an event and never went would be credited for attending it, and no later code
could tell the two apart, because by then the evidence would say they were the
same thing.

So the tests below are **absence controls**, in the shape
``tests/unit/test_calendar_invite_wiring.py`` used before its facade was wired:
they assert that nothing has quietly appeared, and they name what would have to
exist for the absence to end. They are the sort of test meant to be *deleted* by
the card that closes **OQ-CBA-018** — deliberately, in a diff, alongside the
migration that makes them wrong.

## What OQ-CBA-018 needs

:data:`REQUIRED_REGISTRATION_COLUMNS` is the shape, stated once so the open
question has an engineering answer attached rather than only a paragraph. It is
not a migration and this file writes none; it is the checklist a reviewer holds
the eventual ``event_registration`` table against.
"""

from __future__ import annotations

import os

import pytest
from smartmatch_persistence import schema
from sqlalchemy import Engine, create_engine, inspect, text

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)

#: Substrings that would betray a registration surface arriving — in a table
#: name, a column name, or an HTTP path. Deliberately broader than one exact
#: name: the failure this file exists to catch is somebody shipping the concept,
#: not somebody shipping a particular spelling of it.
_REGISTRATION_MARKERS = ("registration", "register", "rsvp", "signup", "sign_up")

#: The columns an ``event_registration`` table would need, and the reason each
#: one is not optional. Written down here because "the queue is closed, record
#: the missing column" is the instruction this card was given, and a sentence in
#: an open-questions row is not a column list.
#:
#: Note what is **not** on it: nothing that would let a registration become an
#: attendance. The two must stay separate rows in separate tables, so that the
#: day somebody asks for "registered but did not attend" the answer is a query
#: rather than an archaeology exercise.
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
        "registered / cancelled / waitlisted, with a CHECK. A cancellation must be a state "
        "on the row rather than a DELETE, or 'they cancelled' and 'they never registered' "
        "become the same absence"
    ),
    "registered_at": "when the place was taken, which a waitlist would order on",
    "updated_at": "when the status last moved, so a cancellation has a time",
}

#: The uniqueness the write would need to be idempotent without an
#: ``Idempotency-Key`` — the reasoning ``routers/speaker_requests.py`` gives for
#: deriving idempotency from the data's own identity.
REQUIRED_REGISTRATION_UNIQUENESS = ("tenant_id", "subject_id", "event_id")


@pytest.fixture(scope="module")
def engine() -> Engine:
    """A live migrated PostgreSQL engine, or skip.

    These assertions are about what the *migrated database* holds, not only about
    what ``schema.py`` declares. Both are checked, and the database is the one
    that decides: a table could exist in Python and never have been migrated, or
    — the failure that would actually matter here — be added by a migration
    nobody reflected into ``schema.py``.
    """
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1 FROM attendance_record LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}")
    return eng


class TestTheSchemaHoldsNoRegistration:
    """The absence, asserted against the migrated database and against ``schema.py``."""

    def test_no_migrated_table_names_a_registration(self, engine: Engine) -> None:
        """The card's blocked half, stated executably.

        When this fails, one of two things has happened: the open question was
        answered and a migration landed — in which case this file is what the
        answering card rewrites — or somebody added the table without answering
        it, which is exactly the arrival this control exists to make loud.
        """
        tables = inspect(engine).get_table_names()

        offenders = sorted(
            table for table in tables for marker in _REGISTRATION_MARKERS if marker in table.lower()
        )

        assert offenders == [], (
            f"a registration table has appeared: {offenders}. OQ-CBA-018 is the "
            "decision that admits one; if it has been answered, this file should be "
            "rewritten by the card that answered it rather than amended around."
        )

    def test_no_column_on_any_table_smuggles_one_in(self, engine: Engine) -> None:
        """A column is as much a surface as a table.

        ``attendance_record.method`` is the one that would have been reached for
        — adding ``'registration'`` to its CHECK would have needed no new table
        at all, and would have put registrations into the only input points are
        computed from.
        """
        inspector = inspect(engine)
        offenders = sorted(
            f"{table}.{column['name']}"
            for table in inspector.get_table_names()
            for column in inspector.get_columns(table)
            for marker in _REGISTRATION_MARKERS
            if marker in column["name"].lower()
        )

        assert offenders == [], f"these columns describe a registration: {offenders}"

    def test_the_declared_schema_agrees_that_there_is_none(self) -> None:
        """The Python half, so a table added to ``schema.py`` alone also fails here."""
        offenders = sorted(
            name
            for name in schema.METADATA.tables
            for marker in _REGISTRATION_MARKERS
            if marker in name.lower()
        )

        assert offenders == [], f"schema.py declares a registration table: {offenders}"


class TestAttendanceStaysAttendance:
    """The specific misuse this card refused, pinned so a later card cannot drift into it."""

    def test_attendance_admits_only_the_three_ways_somebody_actually_attended(
        self, engine: Engine
    ) -> None:
        """``ck_attendance_record_method``, read out of the database.

        Every one of the three describes a person who was *there*: a code scanned
        in the room, a coordinator recording who came, or a roster imported after
        the fact. A fourth value meaning "signed up" would make the table answer
        two different questions with one row shape, and ADR-0013 would credit
        points for both.
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
        """ADR-0013, and why a registration row could not have been an attendance row.

        ``ck_point_ledger_entry_kind`` makes an ``attendance_credit`` require a
        ``source_attendance_id``. So anything written into ``attendance_record``
        is, by construction, a thing points can be computed from — which is what
        makes writing one at registration time a fabrication rather than a
        shortcut.
        """
        with engine.connect() as conn:
            definition = conn.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conname = 'ck_point_ledger_entry_kind'"
                )
            ).scalar_one()

        assert "attendance_credit" in definition
        assert "source_attendance_id IS NOT NULL" in definition


class TestNoRouteClaimsToRegisterAnybody:
    """A page must not be able to call something that looks like registration.

    The API half of the same absence. A route is the thing a UI actually binds a
    button to, so a contract with no registration path is what keeps B06's "until
    then relabel" honest — there is nothing for a mislabelled button to call.
    """

    def test_the_served_route_set_contains_no_registration_path(self) -> None:
        from smartmatch_api.main import app

        offenders = sorted(
            path
            for path in app.openapi()["paths"]
            for marker in _REGISTRATION_MARKERS
            if marker in str(path).lower()
        )

        assert offenders == [], f"these routes claim to register somebody: {offenders}"

    def test_the_student_surface_is_read_only(self) -> None:
        """Both student routes are ``GET``, and neither writes.

        Stated as an equality on the method set rather than as "no POST": a
        ``PUT``, ``PATCH`` or ``DELETE`` arriving on these paths would be as much
        a write as a ``POST``, and would face the same missing table.
        """
        from smartmatch_api.main import app

        paths = app.openapi()["paths"]
        for path in (
            "/v1/units/{unit_id}/student/events",
            "/v1/units/{unit_id}/student/agenda",
        ):
            assert path in paths, f"{path} is not served"
            assert set(paths[path]) == {"get"}, (
                f"{path} serves {sorted(paths[path])}; the student surface reads and "
                "does not write, because the table a write would need does not exist "
                "(OQ-CBA-018)"
            )


class TestTheMissingShapeIsRecordedRatherThanGuessedAt:
    """The checklist, held to itself.

    Not a test of the product — a test that the *record* of what is missing is
    complete, so the card that closes OQ-CBA-018 inherits a column list rather
    than a paragraph. The same practice ``test_policy_matrix.py::GAPS`` keeps
    after being emptied: the mechanism is the part worth keeping.
    """

    def test_every_required_column_carries_the_reason_it_is_required(self) -> None:
        assert REQUIRED_REGISTRATION_COLUMNS
        for column, reason in REQUIRED_REGISTRATION_COLUMNS.items():
            assert reason.strip(), f"{column} is listed with no reason"

    def test_the_shape_names_the_scoping_columns_authorization_would_need(self) -> None:
        """A registration with no tenant and no unit could not be authorized at all.

        Every authorizer in this codebase resolves an ``org_unit`` and compares
        paths; a table without ``owning_unit_id`` would force a registration route
        to authorize against something else, which is how a surface ends up scoped
        differently from every other surface beside it.
        """
        for scoping in ("tenant_id", "owning_unit_id", "subject_id", "event_id"):
            assert scoping in REQUIRED_REGISTRATION_COLUMNS

    def test_the_shape_makes_a_resubmission_idempotent(self) -> None:
        """Customer-facing idempotency comes from the data's own identity.

        ``routers/speaker_requests.py`` states the rule this follows: a header key
        only recognises a repeat of the identical body, while uniqueness on the
        triple makes a second click the same registration however the request was
        phrased.
        """
        assert set(REQUIRED_REGISTRATION_UNIQUENESS) <= set(REQUIRED_REGISTRATION_COLUMNS)

    def test_the_shape_keeps_a_cancellation_visible(self) -> None:
        """A DELETE would make "cancelled" and "never registered" the same absence."""
        assert "status" in REQUIRED_REGISTRATION_COLUMNS
