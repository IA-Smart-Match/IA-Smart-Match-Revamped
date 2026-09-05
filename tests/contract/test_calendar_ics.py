"""HTTP contract for the .ics download (gate G5's one permitted calendar artifact).

``tests/authz/test_policy_matrix.py`` owns the authorization rectangle for
``calendar.invite.download`` and needs no database to run it. What it cannot
state is the half of the rule that is a fact about a *row* rather than about a
principal: a student who clears the role check still has to have an
``attendance_record`` for the specific event, and an event with no such row is a
404 rather than a 403. That is what this file adds, along with the three
refusals and the bytes themselves.

## Why these rows are inserted rather than ingested

``tests/contract/test_events_api.py`` deliberately builds its rows by running
the real ingest over ``tests/fixtures/pilot_events/``, so that the listing
agrees with a shape the pipeline actually produces. This file cannot do that,
and the reason is itself one of the things under test: neither ``ical_parser``
nor ``jsonld_parser`` reads ``DTEND`` yet
(``docs/plans/open-questions/calendar-deferred.md`` OQ-003), so *every* ingested
event has ``ends_at IS NULL`` and the success path would be unreachable. Rows
are therefore written directly, and each one names the exact combination of
``time_precision``, ``ends_at`` and ``quarantined_tag_count`` whose response is
being asserted — which is the property this file is actually about.

The ``ends_at IS NULL`` case is the one an ingested row would have produced
anyway, and it is asserted here too, so the refusal that every event in the
pilot currently receives is covered by name rather than only by implication.
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

UNIT_PATH = "iawest.calendar"
#: A second department in the same tenant containing none of :data:`UNIT_PATH`.
SIBLING_UNIT_PATH = "iawest.calendarsibling"

#: A resolved slot: both instants stated, ninety minutes apart. Deliberately not
#: an hour, so a document that silently fell back to ``generate_ics``'s default
#: duration would produce a different ``DTEND`` and fail rather than agree.
STARTS_AT = datetime(2026, 9, 15, 17, 0, tzinfo=UTC)
ENDS_AT = STARTS_AT + timedelta(minutes=90)

TITLE = "Careers Panel"


@pytest.fixture(scope="module")
def engine() -> Engine:
    """A live migrated PostgreSQL engine, or skip this contract.

    The probe selects ``ends_at`` specifically: a database migrated only as far
    as ``0021`` would otherwise pass the connection check and then fail every
    test here with an opaque error about a missing column.
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

    A small object rather than six fixtures: every test here varies exactly one
    thing about a row or a principal, and the setup that does not vary should
    not be restated in each of them.
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
        time_precision: str = "exact",
        ends_at: datetime | None = ENDS_AT,
        quarantined_tag_count: int = 0,
        title: str = TITLE,
        description: str | None = None,
        unit_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Insert one event row and return its id.

        ``resolved_date`` and the temporal columns are derived from
        ``time_precision`` rather than passed independently, because
        ``ck_event_identity_iff_resolved`` and ``ck_event_temporal_shape`` tie
        them together — a helper that let a test set them separately would let
        it try to write a row the database will not hold, and the failure would
        look like a bug in the route.
        """
        event_id = uuid.uuid4()
        exact = time_precision == "exact"
        # `unresolved` carries no date and no zone at all; `date_only` carries
        # both but no instant. Derived here rather than passed so a test cannot
        # ask for a combination `ck_event_temporal_shape` forbids.
        resolved = time_precision != "unresolved"
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO event (id, tenant_id, host_org_unit_id, title, "
                    "normalized_title, description, starts_at, ends_at, on_date, "
                    "time_zone, time_precision, resolved_date, quarantined_tag_count, "
                    "origin) VALUES (:id, :tid, :unit, :title, :norm, :description, "
                    ":starts_at, :ends_at, :on_date, :zone, :precision, :resolved, "
                    ":quarantined, 'coordinator_entry')"
                ),
                {
                    "id": event_id,
                    "tid": self.tenant_id,
                    "unit": unit_id or self.unit_id,
                    "title": title,
                    "norm": title.lower(),
                    "description": description,
                    "starts_at": STARTS_AT if exact else None,
                    "ends_at": ends_at if exact else None,
                    "on_date": STARTS_AT.date() if (resolved and not exact) else None,
                    "zone": "UTC" if resolved else None,
                    "precision": time_precision,
                    "resolved": STARTS_AT.date() if resolved else None,
                    "quarantined": quarantined_tag_count,
                },
            )
        return event_id

    def add_principal(self, *, role: str, path: str = UNIT_PATH) -> tuple[str, uuid.UUID]:
        """Create one account with one membership, and return its token and user id."""
        user_id = uuid.uuid4()
        subject = f"sub-cal-{uuid.uuid4().hex}"
        token = f"tok-cal-{uuid.uuid4().hex}"
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

    def get(self, event_id: uuid.UUID, token: str, unit_id: uuid.UUID | None = None):
        return self.client.get(
            f"/v1/units/{unit_id or self.unit_id}/events/{event_id}/invite.ics",
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
            {"id": tenant_id, "slug": f"test-cal-{tenant_id.hex[:12]}"},
        )
        for new_unit_id, path, name in (
            (unit_id, UNIT_PATH, "Calendar"),
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
# The bytes
# ---------------------------------------------------------------------------


def test_a_coordinator_downloads_a_resolved_event_as_a_calendar_document(world: _World):
    """The success path, asserted on the document rather than on the status alone."""
    token, _ = world.add_principal(role="coordinator")
    event_id = world.add_event(description="Bring questions")

    response = world.get(event_id, token)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    body = response.text
    assert "BEGIN:VCALENDAR" in body
    assert "DTSTART:20260915T170000Z" in body
    # Ninety minutes, which is what the row says. An hour here would mean the
    # facade's refusal to guess a duration had been routed around somewhere.
    assert "DTEND:20260915T183000Z" in body
    assert f"SUMMARY:{TITLE}" in body
    assert "DESCRIPTION:Bring questions" in body
    # RFC 5546 §3.2.2 would then require ORGANIZER and ATTENDEE, which SmartMatch
    # has no identity to fill in — see the ics module and OQ-005.
    assert "METHOD" not in body


def test_the_uid_is_keyed_on_the_row_so_a_retitled_event_updates_rather_than_duplicates(
    world: _World,
):
    """Correcting a title must not issue a second entry beside the first (OQ-006)."""
    token, _ = world.add_principal(role="coordinator")
    event_id = world.add_event()

    before = world.get(event_id, token).text
    with world.engine.begin() as conn:
        conn.execute(
            text("UPDATE event SET title = :title WHERE id = :id"),
            {"title": "Careers Panel (corrected)", "id": event_id},
        )
    after = world.get(event_id, token).text

    assert f"UID:{event_id}@events.smartmatch.invalid" in before
    assert f"UID:{event_id}@events.smartmatch.invalid" in after


def test_the_response_offers_the_file_as_a_download_named_by_the_row(world: _World):
    """The filename carries no user-supplied text — see the route's header comment."""
    token, _ = world.add_principal(role="coordinator")
    event_id = world.add_event(title='Panel "quoted"; and \\ escaped')

    response = world.get(event_id, token)

    assert response.headers["content-disposition"] == (
        f'attachment; filename="smartmatch-event-{event_id}.ics"'
    )
    assert response.headers["cache-control"] == "no-store"


# ---------------------------------------------------------------------------
# The three refusals (finding F-003)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("precision", ["unresolved", "date_only"])
def test_an_event_without_a_resolved_instant_is_refused(world: _World, precision: str):
    """F-003: no invite is issued for a time the source never stated.

    ``date_only`` is refused alongside ``unresolved`` because turning a date
    into an instant means choosing midnight, in some zone, on the event's
    behalf — the same fabrication with a smaller error bar.
    """
    token, _ = world.add_principal(role="coordinator")
    event_id = world.add_event(time_precision=precision)

    response = world.get(event_id, token)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "event_time_unresolved"
    assert response.headers["content-type"].startswith("application/json")


def test_an_event_whose_source_stated_no_end_is_refused(world: _World):
    """The refusal every ingested event currently gets (OQ-002, OQ-003).

    ``generate_ics`` would supply an hour here. That it does not is the whole
    reason ``calendar_invite`` exists, and this is where that shows up over
    HTTP.
    """
    token, _ = world.add_principal(role="coordinator")
    event_id = world.add_event(ends_at=None)

    response = world.get(event_id, token)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "event_end_unknown"


def test_an_event_carrying_a_quarantined_tag_is_refused(world: _World):
    """ADR-0012: an event still awaiting review is not handed to anybody.

    The catalog withholds it (``routers/events.py``) and
    ``ck_event_publishable`` refuses to publish it; a file a person imports is
    the same act under a different name.
    """
    token, _ = world.add_principal(role="coordinator")
    event_id = world.add_event(quarantined_tag_count=1)

    response = world.get(event_id, token)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "event_not_presentable"


# ---------------------------------------------------------------------------
# The row-level half of authorization, which the policy matrix cannot state
# ---------------------------------------------------------------------------


def test_a_student_downloads_an_event_they_attended(world: _World):
    """The permit the matrix records, plus the attendance row that completes it."""
    token, user_id = world.add_principal(role="student")
    event_id = world.add_event()
    world.record_attendance(subject_id=user_id, event_id=event_id)

    response = world.get(event_id, token)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")


def test_a_student_without_an_attendance_row_gets_a_404_not_a_403(world: _World):
    """A denial distinguishable from an absence is an existence oracle.

    The student holds an active ``student`` membership at exactly this unit, so
    policy permits them; what refuses them is the missing row. Reporting that as
    403 would confirm the event exists to somebody with no claim on it, which is
    the reasoning ``load_unit_or_404`` gives for a cross-tenant unit.
    """
    token, _ = world.add_principal(role="student")
    event_id = world.add_event()

    response = world.get(event_id, token)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "event_not_found"


def test_a_student_attending_one_event_cannot_download_another(world: _World):
    """Attendance is checked per event, not treated as a licence for the unit."""
    token, user_id = world.add_principal(role="student")
    attended = world.add_event()
    other = world.add_event(title="Some Other Panel")
    world.record_attendance(subject_id=user_id, event_id=attended)

    assert world.get(attended, token).status_code == 200
    assert world.get(other, token).status_code == 404


def test_an_attendance_row_does_not_help_a_student_in_a_sibling_department(world: _World):
    """Policy runs first: the role check is scoped to the unit in the path.

    A student whose membership covers only a sibling department is refused
    before the attendance question is asked at all, so the row cannot be used to
    reach across the org tree.
    """
    token, user_id = world.add_principal(role="student", path=SIBLING_UNIT_PATH)
    event_id = world.add_event()
    world.record_attendance(subject_id=user_id, event_id=event_id)

    response = world.get(event_id, token)

    assert response.status_code == 403


def test_a_coordinator_needs_no_attendance_row(world: _World):
    """The unit-wide branch: coordinators read the whole catalog and its invites."""
    token, _ = world.add_principal(role="coordinator")
    event_id = world.add_event()

    assert world.get(event_id, token).status_code == 200


def test_an_event_hosted_by_another_unit_is_not_reachable_through_this_one(world: _World):
    """The unit in the path must be the unit that hosts the event.

    Otherwise a coordinator could name their own unit and any event id in the
    tenant, and the role check would pass against a unit that has nothing to do
    with the row being read.
    """
    token, _ = world.add_principal(role="coordinator")
    event_id = world.add_event(unit_id=world.sibling_unit_id)

    response = world.get(event_id, token)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "event_not_found"


def test_a_volunteer_is_refused_before_any_row_is_read(world: _World):
    """The role set is closed: ``admin``, ``coordinator``, ``student``, nobody else."""
    token, _ = world.add_principal(role="volunteer")
    event_id = world.add_event()

    assert world.get(event_id, token).status_code == 403


def test_an_unauthenticated_caller_is_refused(world: _World):
    """No anonymous calendar surface — an .ics is not a public link."""
    event_id = world.add_event()

    response = world.client.get(f"/v1/units/{world.unit_id}/events/{event_id}/invite.ics")

    assert response.status_code == 401
