"""``MeetingRepository`` against real PostgreSQL (migration ``0034``).

Every assertion here reads the row back out of the table. ``get_session`` rolls
back unconditionally, so a writer that looks successful and stores nothing is a
live failure mode in this codebase — the argument
``test_event_registration.py``'s docstring makes — and a test that trusted a
return value would pass on exactly that defect.

Two things this file is about, and one it deliberately is not
==============================================================
**The refusal.** :class:`TestAnUnresolvedTimeIsRefused` is the reason the module
exists. A meeting with no instant, and a meeting whose instant is a naive
``datetime``, are both refused *before a statement is built* — and the second is
the arm that cannot be delegated to the column, because ``NOT NULL`` accepts a
naive datetime and lets PostgreSQL resolve it against the session's ``TimeZone``.
An instant that depends on which connection wrote it is finding **F-003**'s
shape: a time nobody chose, arrived at by a default nobody stated.

**The read.** A listing is bounded, ordered, tenant-scoped and unit-scoped, and
returns cancelled rows rather than hiding them.

**Not authorization.** No principal appears in this file. Who may call these
methods is the router's question and is asserted over HTTP in
``tests/contract/test_meetings_api.py`` and in the policy matrix.

Requires a live migrated PostgreSQL and skips when none is reachable.
"""

from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("sqlalchemy")

import sqlalchemy as sa
from conftest import ensure_owning_unit, unique_subject
from smartmatch_persistence import schema
from smartmatch_persistence.meetings import (
    MEETING_STATUS_CANCELLED,
    MEETING_STATUS_SCHEDULED,
    MeetingRepository,
    UnresolvedMeetingTimeError,
)
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration

#: The zone every meeting below is agreed in. A real IANA name, because the
#: column stores the zone the people in the room used and a placeholder would
#: make the assertions say less than they appear to.
ZONE = "America/Los_Angeles"

#: The instant the single-meeting tests use. Aware, and fixed rather than derived
#: from the clock: a test that scheduled a meeting "in an hour" would assert
#: about a value it computed the same way the code under test might have.
INSTANT = datetime(2026, 9, 15, 17, 0, tzinfo=UTC)


@pytest.fixture
def meetings() -> MeetingRepository:
    return MeetingRepository()


@pytest.fixture
def session(session_factory: sessionmaker[Session]):
    with session_factory() as opened:
        yield opened
        opened.rollback()


@pytest.fixture
def recorder(session: Session, tenant_id: uuid.UUID) -> uuid.UUID:
    """An account that could have recorded a meeting.

    Committed rather than left pending, because the composite foreign key on
    every write below has to be able to see it.
    """
    user_id = uuid.uuid4()
    session.execute(
        sa.insert(schema.user_account).values(
            id=user_id,
            tenant_id=tenant_id,
            external_subject=unique_subject(f"meeting-recorder-{user_id.hex[:8]}"),
            email=f"recorder-{user_id.hex[:8]}@example.invalid",
        )
    )
    session.commit()
    return user_id


@pytest.fixture
def unit_id(session: Session, tenant_id: uuid.UUID) -> uuid.UUID:
    unit = ensure_owning_unit(session, tenant_id)
    session.commit()
    return unit


class TestAnUnresolvedTimeIsRefused:
    """The invariant: a meeting with no resolved time is refused, never defaulted.

    ADR-0010 rule 2, migration finding F-003. The legacy turned an unparsed date
    into "thirty days from now"; ``smartmatch_domain.ics`` was ported to end that
    class of defect, and these are the two ways it could re-enter through this
    table.
    """

    def test_a_meeting_with_no_instant_is_refused_and_nothing_is_written(
        self,
        meetings: MeetingRepository,
        session: Session,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        recorder: uuid.UUID,
    ) -> None:
        """``None`` raises, and the table is untouched.

        The second half is the one worth having. A version that raised *after*
        inserting — or that inserted a placeholder and then complained — would
        pass an exception-only assertion while leaving exactly the fabricated row
        this rule exists to prevent.
        """
        with pytest.raises(UnresolvedMeetingTimeError):
            meetings.create(
                session,
                tenant_id=tenant_id,
                owning_unit_id=unit_id,
                title="CBA team sync",
                scheduled_at=None,
                time_zone=ZONE,
                location_or_link=None,
                created_by_user_id=recorder,
            )

        assert meetings.count_for_unit(session, tenant_id=tenant_id, owning_unit_id=unit_id) == 0

    def test_a_naive_datetime_is_refused_rather_than_assigned_a_zone(
        self,
        meetings: MeetingRepository,
        session: Session,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        recorder: uuid.UUID,
    ) -> None:
        """The arm the column cannot cover.

        ``scheduled_at`` is ``NOT NULL``, and a naive datetime is not null — the
        database would take it and resolve it against the session's ``TimeZone``,
        so the stored instant would depend on which connection wrote the row.
        This is the check that has to live in the repository, and it is why the
        duplication with the column is not redundant.
        """
        with pytest.raises(UnresolvedMeetingTimeError) as raised:
            meetings.create(
                session,
                tenant_id=tenant_id,
                owning_unit_id=unit_id,
                title="CBA team sync",
                # No tzinfo. A wall-clock reading, not an instant.
                scheduled_at=datetime(2026, 9, 15, 17, 0),
                time_zone=ZONE,
                location_or_link=None,
                created_by_user_id=recorder,
            )

        assert "timezone-aware" in str(raised.value)
        assert meetings.count_for_unit(session, tenant_id=tenant_id, owning_unit_id=unit_id) == 0

    def test_the_repository_offers_no_way_to_omit_the_time(self) -> None:
        """``scheduled_at`` has no default in the signature, and must not acquire one.

        Read off the callable rather than argued in prose, so a later edit adding
        ``scheduled_at: datetime | None = None`` — which would make every caller
        that forgot a time silently mean "no time", one keystroke from meaning
        "now" — fails here.
        """
        parameter = inspect.signature(MeetingRepository.create).parameters["scheduled_at"]
        assert parameter.default is inspect.Parameter.empty


class TestARecordedMeetingIsStored:
    """The complement: the refusals above are refusals, not a broken writer."""

    def test_a_meeting_is_written_and_read_back(
        self,
        meetings: MeetingRepository,
        session: Session,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        recorder: uuid.UUID,
    ) -> None:
        """Every field round-trips, and the row starts ``scheduled``."""
        stored = meetings.create(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            title="CBA team sync",
            scheduled_at=INSTANT,
            time_zone=ZONE,
            location_or_link="Bldg 9-241",
            created_by_user_id=recorder,
        )
        session.commit()

        assert stored.title == "CBA team sync"
        assert stored.scheduled_at == INSTANT
        assert stored.time_zone == ZONE
        assert stored.location_or_link == "Bldg 9-241"
        assert stored.status == MEETING_STATUS_SCHEDULED
        assert stored.created_by_user_id == recorder
        assert stored.owning_unit_id == unit_id

        read_back = meetings.get(session, tenant_id=tenant_id, meeting_id=stored.id)
        assert read_back == stored

    def test_a_meeting_with_no_location_keeps_none_rather_than_a_blank(
        self,
        meetings: MeetingRepository,
        session: Session,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        recorder: uuid.UUID,
    ) -> None:
        """A room still being settled is a real state, and ``None`` is how it reads.

        The pair to ``ck_cba_meeting_location_shape``'s refusal of ``''``: the
        constraint stops a blank string becoming a second way to say "unknown",
        and this asserts the honest way still works.
        """
        stored = meetings.create(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            title="Room to be confirmed",
            scheduled_at=INSTANT,
            time_zone=ZONE,
            location_or_link=None,
            created_by_user_id=recorder,
        )
        session.commit()

        assert stored.location_or_link is None

    def test_created_and_updated_are_server_written_not_guessed(
        self,
        meetings: MeetingRepository,
        session: Session,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        recorder: uuid.UUID,
    ) -> None:
        """The two provenance instants come back from the database, aware and equal.

        They are server defaults, so the repository reads the row back rather than
        constructing the value — otherwise the returned row would carry this
        module's guess at what PostgreSQL wrote.
        """
        stored = meetings.create(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            title="CBA team sync",
            scheduled_at=INSTANT,
            time_zone=ZONE,
            location_or_link=None,
            created_by_user_id=recorder,
        )
        session.commit()

        assert stored.created_at.tzinfo is not None
        assert stored.updated_at == stored.created_at
        # And it is not the meeting time — three distinct instants live on this
        # row, and collapsing any two would lose a question somebody asks.
        assert stored.created_at != stored.scheduled_at


class TestTheListingIsBoundedScopedAndOrdered:
    """What ``for_unit`` promises, asserted one property at a time."""

    def _record(
        self,
        meetings: MeetingRepository,
        session: Session,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        recorder: uuid.UUID,
        *,
        title: str,
        offset_hours: int,
    ) -> uuid.UUID:
        row = meetings.create(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            title=title,
            scheduled_at=INSTANT + timedelta(hours=offset_hours),
            time_zone=ZONE,
            location_or_link=None,
            created_by_user_id=recorder,
        )
        return row.id

    def test_meetings_come_back_soonest_first(
        self,
        meetings: MeetingRepository,
        session: Session,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        recorder: uuid.UUID,
    ) -> None:
        """Written out of order, so the ordering is the query's and not the insert's."""
        self._record(
            meetings, session, tenant_id, unit_id, recorder, title="Third", offset_hours=48
        )
        self._record(meetings, session, tenant_id, unit_id, recorder, title="First", offset_hours=0)
        self._record(
            meetings, session, tenant_id, unit_id, recorder, title="Second", offset_hours=24
        )
        session.commit()

        listed = meetings.for_unit(session, tenant_id=tenant_id, owning_unit_id=unit_id, limit=10)
        assert [row.title for row in listed] == ["First", "Second", "Third"]

    def test_the_limit_is_honoured_and_the_count_reports_the_rest(
        self,
        meetings: MeetingRepository,
        session: Session,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        recorder: uuid.UUID,
    ) -> None:
        """A bounded page plus a measured total, which is what lets a caller say so.

        Without the count, a surface rendering ``limit`` rows cannot tell a unit
        with exactly that many meetings from one with more — so it would have to
        either claim a total it did not measure or say nothing at all.
        """
        for index in range(5):
            self._record(
                meetings,
                session,
                tenant_id,
                unit_id,
                recorder,
                title=f"Meeting {index}",
                offset_hours=index,
            )
        session.commit()

        listed = meetings.for_unit(session, tenant_id=tenant_id, owning_unit_id=unit_id, limit=2)
        assert [row.title for row in listed] == ["Meeting 0", "Meeting 1"]
        assert meetings.count_for_unit(session, tenant_id=tenant_id, owning_unit_id=unit_id) == 5

    def test_a_non_positive_limit_is_refused_rather_than_answered_with_an_empty_list(
        self,
        meetings: MeetingRepository,
        session: Session,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
    ) -> None:
        """An empty list would be a false statement, not a small answer.

        ``limit=0`` returning ``[]`` is indistinguishable from "this unit has no
        meetings", and the two are different facts.
        """
        with pytest.raises(ValueError, match="limit must be positive"):
            meetings.for_unit(session, tenant_id=tenant_id, owning_unit_id=unit_id, limit=0)

    def test_a_cancelled_meeting_is_listed_rather_than_hidden(
        self,
        meetings: MeetingRepository,
        session: Session,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        recorder: uuid.UUID,
    ) -> None:
        """ "Called off" and "never arranged" are different facts, and the read keeps both.

        The status is moved with a direct UPDATE because there is no cancel method
        yet — the write half of the transition is not part of this track, and
        asserting the *read* does not require inventing one.
        """
        meeting_id = self._record(
            meetings, session, tenant_id, unit_id, recorder, title="Called off", offset_hours=0
        )
        session.execute(
            sa.update(schema.cba_meeting)
            .where(
                schema.cba_meeting.c.tenant_id == tenant_id,
                schema.cba_meeting.c.id == meeting_id,
            )
            .values(status=MEETING_STATUS_CANCELLED)
        )
        session.commit()

        listed = meetings.for_unit(session, tenant_id=tenant_id, owning_unit_id=unit_id, limit=10)
        assert [(row.title, row.status) for row in listed] == [
            ("Called off", MEETING_STATUS_CANCELLED)
        ]

    def test_a_sibling_units_meetings_are_not_in_this_units_list(
        self,
        meetings: MeetingRepository,
        session: Session,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        recorder: uuid.UUID,
    ) -> None:
        """Unit scoping is in the WHERE clause, not applied by a caller afterwards."""
        sibling_id = uuid.uuid4()
        session.execute(
            sa.insert(schema.org_unit).values(
                id=sibling_id,
                tenant_id=tenant_id,
                path=sa.cast(f"iawest.sibling{sibling_id.hex[:8]}", schema.LTree()),
                unit_type="department",
                display_name="Sibling",
            )
        )
        session.commit()

        self._record(meetings, session, tenant_id, unit_id, recorder, title="Ours", offset_hours=0)
        meetings.create(
            session,
            tenant_id=tenant_id,
            owning_unit_id=sibling_id,
            title="Theirs",
            scheduled_at=INSTANT,
            time_zone=ZONE,
            location_or_link=None,
            created_by_user_id=recorder,
        )
        session.commit()

        ours = meetings.for_unit(session, tenant_id=tenant_id, owning_unit_id=unit_id, limit=10)
        assert [row.title for row in ours] == ["Ours"]

        # The sibling unit is this test's own, so it cleans it up rather than
        # leaving a row the tenant fixture's ordered teardown would trip on.
        session.execute(
            sa.delete(schema.cba_meeting).where(
                schema.cba_meeting.c.tenant_id == tenant_id,
                schema.cba_meeting.c.owning_unit_id == sibling_id,
            )
        )
        session.execute(sa.delete(schema.org_unit).where(schema.org_unit.c.id == sibling_id))
        session.commit()

    def test_a_meeting_in_another_tenant_is_absent_rather_than_filtered_later(
        self,
        meetings: MeetingRepository,
        session: Session,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        recorder: uuid.UUID,
    ) -> None:
        """``get`` scopes by tenant in the query, so a foreign row is never fetched at all."""
        stored = meetings.create(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            title="CBA team sync",
            scheduled_at=INSTANT,
            time_zone=ZONE,
            location_or_link=None,
            created_by_user_id=recorder,
        )
        session.commit()

        assert meetings.get(session, tenant_id=uuid.uuid4(), meeting_id=stored.id) is None
