"""HTTP contract for the two student event reads (customer §15).

``tests/authz/test_policy_matrix.py`` owns the authorization rectangle for
``student_event.browse`` and ``student_agenda.list``, and runs it without a
database. What it structurally cannot state is the half of each rule that is a
fact about a **row** rather than about a principal, and that half is the whole
of what this card had to get right:

* the agenda is scoped to the caller's own ``attendance_record`` rows, so one
  student never sees another's — a self-scope ``evaluate`` has no concept of;
* browse shows published events only, and *counts* the rest rather than dropping
  them (ADR-0011);
* the ``calendar`` object on each item agrees with what
  ``GET .../invite.ics`` would actually do, so a client never learns a refusal
  by attempting a download.

The last of those is the one worth stating twice. The .ics route already refuses
an unresolved start, an unstated end, and an event a student was not at, each
with its own code. A listing that advertised a download for any of those three
would be ``docs/plans/frontend-broken-buttons.md`` B07 again with a real URL
attached — worse than the original toast, because the toast at least did not
hand anybody a link that 404s. So
:class:`TestTheCalendarLinkAgreesWithTheIcsRoute` does not assert the field's
value in isolation: it asserts the field, then *calls the .ics route* and
requires the two to agree.

## Why these rows are inserted rather than ingested

The same reason ``tests/contract/test_calendar_ics.py`` gives: no parser reads
``DTEND`` yet (``docs/plans/open-questions/calendar-deferred.md`` OQ-003), so
every ingested event has ``ends_at IS NULL`` and the "download is available"
path would be unreachable. Rows are written directly and each names the exact
combination of ``publication_status``, ``time_precision`` and ``ends_at`` whose
response is under assertion.

## Registration is not tested here because it is not shipped

§15 also asks for registration. There is no registration table and this card
adds no DDL, so no route claims to register anybody — see
``tests/integration/test_event_registration.py``, which pins that absence
against the database, and OQ-CBA-018.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import Engine, create_engine, text

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)

UNIT_PATH = "iawest.studentevents"
#: A second department in the same tenant containing none of :data:`UNIT_PATH`.
SIBLING_UNIT_PATH = "iawest.studenteventssibling"

#: A resolved slot, ninety minutes long. Not an hour, for the reason
#: ``test_calendar_ics.py`` gives: an hour is what a guessed duration looks like,
#: so a document that fell back to ``generate_ics``'s default would agree with a
#: fixture that had chosen one.
STARTS_AT = datetime(2026, 10, 6, 17, 0, tzinfo=UTC)
EVENT_DURATION = timedelta(minutes=90)


@pytest.fixture(scope="module")
def engine() -> Engine:
    """A live migrated PostgreSQL engine, or skip this contract.

    The probe selects ``ends_at`` specifically: a database migrated only as far
    as ``0021`` would pass a bare connection check and then fail every test here
    with an opaque error about a missing column.
    """
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT ends_at FROM event LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}")
    return eng


class _World:
    """The ids and writers one test needs, so a test reads as a question.

    Deliberately the same shape as ``test_calendar_ics.py::_World``, because the
    two files exercise two halves of one surface and a reader moving between
    them should not have to learn a second vocabulary.
    """

    def __init__(
        self,
        client: TestClient,
        engine: Engine,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        sibling_unit_id: uuid.UUID,
    ) -> None:
        self.client = client
        self.engine = engine
        self.tenant_id = tenant_id
        self.unit_id = unit_id
        self.sibling_unit_id = sibling_unit_id

    def add_event(
        self,
        *,
        title: str,
        publication_status: str = "published",
        time_precision: str = "exact",
        has_end: bool = True,
        starts_at: datetime = STARTS_AT,
        quarantined_tag_count: int = 0,
        unit_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Insert one event row and return its id.

        The temporal columns and ``resolved_date`` are derived from
        ``time_precision`` rather than passed independently, because
        ``ck_event_temporal_shape`` and ``ck_event_identity_iff_resolved`` tie
        them together: a helper that let a test set them separately would let it
        try to write a row the database will not hold, and the failure would look
        like a bug in the route.

        ``has_end`` rather than an ``ends_at`` instant, for the same reason:
        ``ck_event_end_after_start`` ties the end to *this row's* start, so a test
        that moved ``starts_at`` and left a fixed end behind would be refused by
        the database rather than by the route it meant to exercise.
        """
        event_id = uuid.uuid4()
        exact = time_precision == "exact"
        resolved = time_precision != "unresolved"
        ends_at = starts_at + EVENT_DURATION if has_end else None
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO event (id, tenant_id, host_org_unit_id, title, "
                    "normalized_title, starts_at, ends_at, on_date, time_zone, "
                    "time_precision, resolved_date, publication_status, "
                    "quarantined_tag_count, origin) VALUES (:id, :tid, :unit, :title, "
                    ":norm, :starts_at, :ends_at, :on_date, :zone, :precision, "
                    ":resolved, :status, :quarantined, 'coordinator_entry')"
                ),
                {
                    "id": event_id,
                    "tid": self.tenant_id,
                    "unit": unit_id or self.unit_id,
                    "title": title,
                    "norm": title.lower(),
                    "starts_at": starts_at if exact else None,
                    "ends_at": ends_at if exact else None,
                    "on_date": starts_at.date() if (resolved and not exact) else None,
                    "zone": "UTC" if resolved else None,
                    "precision": time_precision,
                    "resolved": starts_at.date() if resolved else None,
                    "status": publication_status,
                    "quarantined": quarantined_tag_count,
                },
            )
        return event_id

    def add_principal(self, *, role: str, path: str = UNIT_PATH) -> tuple[str, uuid.UUID]:
        """Create one account with one membership, and return its token and user id."""
        user_id = uuid.uuid4()
        subject = f"sub-se-{uuid.uuid4().hex}"
        token = f"tok-se-{uuid.uuid4().hex}"
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                    "VALUES (:id, :tid, :subject, :email)"
                ),
                {
                    "id": user_id,
                    "tid": self.tenant_id,
                    "subject": subject,
                    "email": f"{subject}@example.edu",
                },
            )
            conn.execute(
                text(
                    "INSERT INTO membership (id, tenant_id, user_id, granted_path, role) "
                    "VALUES (:id, :tid, :uid, CAST(:path AS ltree), :role)"
                ),
                {
                    "id": uuid.uuid4(),
                    "tid": self.tenant_id,
                    "uid": user_id,
                    "path": path,
                    "role": role,
                },
            )
        self.client.app.state.token_verifier.register(token, subject)
        return token, user_id

    def record_attendance(self, *, subject_id: uuid.UUID, event_id: uuid.UUID) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO attendance_record (id, tenant_id, owning_unit_id, "
                    "subject_id, event_id, method) VALUES (:id, :tid, :unit, :sid, "
                    ":eid, 'coordinator_entry')"
                ),
                {
                    "id": uuid.uuid4(),
                    "tid": self.tenant_id,
                    "unit": self.unit_id,
                    "sid": subject_id,
                    "eid": event_id,
                },
            )

    def browse(self, token: str, unit_id: uuid.UUID | None = None):
        return self.client.get(
            f"/v1/units/{unit_id or self.unit_id}/student/events",
            headers={"Authorization": f"Bearer {token}"},
        )

    def agenda(self, token: str, unit_id: uuid.UUID | None = None):
        return self.client.get(
            f"/v1/units/{unit_id or self.unit_id}/student/agenda",
            headers={"Authorization": f"Bearer {token}"},
        )

    def download(self, event_id: uuid.UUID, token: str):
        return self.client.get(
            f"/v1/units/{self.unit_id}/events/{event_id}/invite.ics",
            headers={"Authorization": f"Bearer {token}"},
        )


@pytest.fixture
def world(engine: Engine) -> Iterator[_World]:
    """One tenant with two departments, and a client wired to a fixture verifier."""
    tenant_id = uuid.uuid4()
    unit_id = uuid.uuid4()
    sibling_unit_id = uuid.uuid4()

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"test-se-{tenant_id.hex[:12]}"},
        )
        for new_unit_id, path, name in (
            (unit_id, UNIT_PATH, "Student Events"),
            (sibling_unit_id, SIBLING_UNIT_PATH, "Sibling"),
        ):
            conn.execute(
                text(
                    "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                    "VALUES (:id, :tid, CAST(:path AS ltree), 'department', :name)"
                ),
                {"id": new_unit_id, "tid": tenant_id, "path": path, "name": name},
            )

    client = TestClient(app)
    client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    client.app.state.token_verifier = FixtureTokenVerifier()

    yield _World(client, engine, tenant_id, unit_id, sibling_unit_id)

    with engine.begin() as conn:
        for table in (
            "attendance_record",
            "event_tag",
            "discovery_review_item",
            "event",
            "membership",
            "resource_grant",
            "user_account",
            "org_unit",
            "rate_limit_counter",
        ):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tenant_id})


# ---------------------------------------------------------------------------
# Browse: what a student may see, and what is counted instead
# ---------------------------------------------------------------------------


class TestBrowseShowsPublishedEventsAndCountsTheRest:
    def test_a_student_reads_the_units_published_events(self, world: _World):
        token, _ = world.add_principal(role="student")
        world.add_event(title="Careers Panel")

        response = world.browse(token)

        assert response.status_code == 200
        body = response.json()
        assert [event["title"] for event in body["events"]] == ["Careers Panel"]
        assert body["truncated"] is False

    def test_an_unpublished_event_is_withheld_and_counted_rather_than_dropped(self, world: _World):
        """ADR-0011's corollary: an omission is never rendered as an absence.

        Without the count, "this unit has no events for me" and "this unit has
        three events it has not published" are the same empty list, and a student
        staring at an empty page cannot tell which.
        """
        token, _ = world.add_principal(role="student")
        world.add_event(title="Draft Workshop", publication_status="unpublished")

        body = world.browse(token).json()

        assert body["events"] == []
        assert body["withheld_unpublished"] == 1

    def test_the_response_carries_no_extraction_provenance_or_review_state(self, world: _World):
        """The reason this is a second route rather than a wider role set.

        ``routers/events.py``'s response carries ``review_status``,
        ``source_url``, ``fetched_at`` and ``extractor_version``. If admitting a
        student had been done by adding a role to ``_EVENT_ROLES``, all four
        would have gone with it.
        """
        token, _ = world.add_principal(role="student")
        world.add_event(title="Careers Panel")

        item = world.browse(token).json()["events"][0]

        for coordinator_only in ("review_status", "provenance", "publication_status"):
            assert coordinator_only not in item

    def test_a_sibling_departments_events_are_not_this_units_events(self, world: _World):
        """Unit scoping, asserted on the rows rather than only on the authorizer."""
        token, _ = world.add_principal(role="student")
        world.add_event(title="Ours")
        world.add_event(title="Theirs", unit_id=world.sibling_unit_id)

        body = world.browse(token).json()

        assert [event["title"] for event in body["events"]] == ["Ours"]

    def test_a_coordinator_is_refused_this_surface(self, world: _World):
        """``{student}`` is the whole role set — see the matrix rows.

        Not a leak in either direction: the coordinator reads the same events
        through ``GET /v1/units/{unit_id}/events``, which shows them more.
        """
        token, _ = world.add_principal(role="coordinator")
        world.add_event(title="Careers Panel")

        assert world.browse(token).status_code == 403
        assert world.agenda(token).status_code == 403

    def test_a_unit_in_another_tenant_is_a_404_and_not_a_403(self, world: _World):
        """A denial distinguished from an absence is an existence oracle."""
        token, _ = world.add_principal(role="student")

        assert world.browse(token, unit_id=uuid.uuid4()).status_code == 404


# ---------------------------------------------------------------------------
# The agenda, and the self-scope the policy engine cannot express
# ---------------------------------------------------------------------------


class TestTheAgendaIsScopedToTheCallerAlone:
    def test_it_returns_the_events_this_student_is_recorded_at(self, world: _World):
        token, user_id = world.add_principal(role="student")
        mine = world.add_event(title="Careers Panel")
        world.add_event(title="Someone Else's Seminar")
        world.record_attendance(subject_id=user_id, event_id=mine)

        body = world.agenda(token).json()

        assert [event["title"] for event in body["events"]] == ["Careers Panel"]
        assert body["events"][0]["on_my_agenda"] is True

    def test_one_students_agenda_never_contains_another_students_attendance(self, world: _World):
        """The assertion the authorization matrix structurally cannot make.

        Both principals hold the identical role at the identical unit, so
        ``evaluate`` returns the identical decision for both. Everything that
        separates them is the ``subject_id`` predicate in the query.
        """
        mine_token, mine_id = world.add_principal(role="student")
        theirs_token, theirs_id = world.add_principal(role="student")
        my_event = world.add_event(title="Mine")
        their_event = world.add_event(title="Theirs")
        world.record_attendance(subject_id=mine_id, event_id=my_event)
        world.record_attendance(subject_id=theirs_id, event_id=their_event)

        assert [e["title"] for e in world.agenda(mine_token).json()["events"]] == ["Mine"]
        assert [e["title"] for e in world.agenda(theirs_token).json()["events"]] == ["Theirs"]

    def test_an_attended_event_stays_on_the_agenda_after_it_is_unpublished(self, world: _World):
        """Deliberate asymmetry with browse, and the docstring says why.

        An event a student actually attended is theirs to see whether or not the
        unit still publishes it. Filtering it out would make their own history
        disagree with itself.
        """
        token, user_id = world.add_principal(role="student")
        event_id = world.add_event(title="Last Term's Panel", publication_status="unpublished")
        world.record_attendance(subject_id=user_id, event_id=event_id)

        assert [e["title"] for e in world.agenda(token).json()["events"]] == ["Last Term's Panel"]

    def test_an_unresolved_date_is_excluded_from_the_time_ordering_and_counted(self, world: _World):
        """ADR-0010 rule 2: a dateless event has no position on a time-ordered list."""
        token, user_id = world.add_principal(role="student")
        undated = world.add_event(
            title="Sometime", publication_status="unpublished", time_precision="unresolved"
        )
        world.record_attendance(subject_id=user_id, event_id=undated)

        body = world.agenda(token).json()

        assert body["events"] == []
        assert body["withheld_unresolved_date"] == 1

    def test_the_agenda_is_ordered_soonest_first(self, world: _World):
        token, user_id = world.add_principal(role="student")
        later = world.add_event(title="Later", starts_at=STARTS_AT + timedelta(days=7))
        sooner = world.add_event(title="Sooner", starts_at=STARTS_AT)
        for event_id in (later, sooner):
            world.record_attendance(subject_id=user_id, event_id=event_id)

        body = world.agenda(token).json()

        assert [event["title"] for event in body["events"]] == ["Sooner", "Later"]


# ---------------------------------------------------------------------------
# The calendar link, checked against the route it points at
# ---------------------------------------------------------------------------


class TestTheCalendarLinkAgreesWithTheIcsRoute:
    """Each item's ``calendar`` object is asserted *and then exercised*.

    Asserting the field alone would only prove the listing is internally
    consistent. What matters is that it is consistent with a different module —
    ``routers/calendar.py`` — whose refusal rules it restates. So every test here
    calls the download too, and requires the two to agree.
    """

    def test_an_event_the_student_attends_offers_a_link_that_works(self, world: _World):
        token, user_id = world.add_principal(role="student")
        event_id = world.add_event(title="Careers Panel")
        world.record_attendance(subject_id=user_id, event_id=event_id)

        item = world.browse(token).json()["events"][0]

        assert item["calendar"]["available"] is True
        assert item["calendar"]["unavailable_reason"] is None
        assert item["calendar"]["download_path"] == (
            f"/v1/units/{world.unit_id}/events/{event_id}/invite.ics"
        )

        followed = world.client.get(
            item["calendar"]["download_path"], headers={"Authorization": f"Bearer {token}"}
        )
        assert followed.status_code == 200
        assert followed.headers["content-type"].startswith("text/calendar")

    def test_an_event_the_student_is_not_recorded_at_offers_no_link(self, world: _World):
        """The reason is about the caller, so the .ics route answers 404, not 409.

        That asymmetry is deliberate and documented: the download cannot
        distinguish "not yours" from "no such event" without becoming an
        existence oracle, while a listing that already showed the event has no
        such secret left to keep.
        """
        token, _ = world.add_principal(role="student")
        event_id = world.add_event(title="Careers Panel")

        item = world.browse(token).json()["events"][0]

        assert item["on_my_agenda"] is False
        assert item["calendar"] == {
            "available": False,
            "download_path": None,
            "unavailable_reason": "event_not_on_your_agenda",
        }
        assert world.download(event_id, token).status_code == 404

    def test_a_date_only_event_offers_no_link_and_names_the_missing_instant(self, world: _World):
        """Finding F-003.

        A date with no clock time becomes an instant only by somebody choosing
        midnight, in some zone, on the event's behalf.
        """
        token, user_id = world.add_principal(role="student")
        event_id = world.add_event(title="Autumn Fair", time_precision="date_only")
        world.record_attendance(subject_id=user_id, event_id=event_id)

        item = world.browse(token).json()["events"][0]

        assert item["time"]["precision"] == "date_only"
        assert item["time"]["starts_at"] is None
        assert item["calendar"]["available"] is False
        assert item["calendar"]["unavailable_reason"] == "event_time_unresolved"

        refused = world.download(event_id, token)
        assert refused.status_code == 409
        assert refused.json()["error"]["code"] == "event_time_unresolved"

    def test_an_event_with_no_stated_end_offers_no_link_and_says_so(self, world: _World):
        """The case every ingested event is in today (OQ-003).

        ``generate_ics`` would supply an hour; ``build_invite_ics`` refuses to let
        it, because a guessed duration is still a guess. The listing reports that
        refusal instead of letting a student discover it by clicking.
        """
        token, user_id = world.add_principal(role="student")
        event_id = world.add_event(title="Open House", has_end=False)
        world.record_attendance(subject_id=user_id, event_id=event_id)

        item = world.browse(token).json()["events"][0]

        assert item["time"]["ends_at"] is None
        assert item["calendar"]["available"] is False
        assert item["calendar"]["unavailable_reason"] == "event_end_unknown"

        refused = world.download(event_id, token)
        assert refused.status_code == 409
        assert refused.json()["error"]["code"] == "event_end_unknown"

    def test_exactly_one_of_the_path_and_the_reason_is_ever_set(self, world: _World):
        """The invariant that makes the field usable as a render condition.

        A client shows the link when there is a path and the reason when there is
        not; there is no third state in which it has to decide for itself.
        """
        token, user_id = world.add_principal(role="student")
        attending = world.add_event(title="Careers Panel")
        world.record_attendance(subject_id=user_id, event_id=attending)
        world.add_event(title="Open House", has_end=False)
        world.add_event(title="Autumn Fair", time_precision="date_only")

        for item in world.browse(token).json()["events"]:
            calendar = item["calendar"]
            assert calendar["available"] is (calendar["download_path"] is not None)
            assert calendar["available"] is (calendar["unavailable_reason"] is None)
