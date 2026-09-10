"""What migration ``0034`` refuses, asserted against a real database.

``0034`` creates ``cba_meeting`` (the coordinator portal's Meetings record). The
part of the revision that matters is not what it stores but **what it will not
let anybody store**: a meeting with no resolved time.

The invariant this file exists for
====================================
``scheduled_at`` is ``NOT NULL`` and carries **no server default**. Those two
facts together are the invariant — either one alone is not it:

* ``NOT NULL`` with a ``server_default = now()`` would accept an insert naming no
  instant and silently answer "the meeting is happening right now", which is
  migration finding **F-003** with a shorter offset. F-003 is the legacy defect
  where an unparsed date became "thirty days from now" and produced a confident
  slot **nobody chose**; ``smartmatch_domain.ics`` was ported to end that class,
  and ADR-0010 rule 2 is the rule it enforces.
* Nullable with no default would store the meeting and leave the *reading*
  surface to invent a time, which moves the fabrication one layer out.

So :func:`test_a_meeting_with_no_time_is_refused_by_the_database` inserts a row
naming every other column and omitting only ``scheduled_at``, and asserts the
database refuses it. It is written as a raw ``INSERT`` rather than through
``MeetingRepository`` on purpose: the repository and the route both refuse first,
with worded errors, and this file is about the guarantee that holds when a
*second* writer is added by somebody who did not read either.

:func:`test_the_column_carries_no_default` asserts the same thing from the other
side, out of the catalog. Without it this file would pass against a migration
that had quietly acquired a default, because a default makes the omitting insert
succeed — and a test that only checks "the insert failed" cannot tell the
difference between a refusal and a fabrication.

Requires a live database and the privilege to create one; skipped otherwise.
"""

from __future__ import annotations

import uuid

import pytest

pytest.importorskip("sqlalchemy")

from migration_harness import alembic, applied_revision, connected, scratch_database
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.integration

#: The revision immediately before the one under test.
#:
#: Read off the ``revision =`` line of ``0033_event_filed_by.py``, not off a
#: filename: Alembic revision ids are not filenames, and this repository carries
#: the standing proof — ``0024_cba_classification_schema.py`` declares
#: ``revision = "0024_cba_classification"``.
REVISION_BEFORE = "0033_event_filed_by"

#: The revision under test.
REVISION = "0034_cba_meeting"

#: A plausible IANA zone. The column stores the zone the people in the room
#: agreed the time *in*, which a ``timestamptz`` cannot recover on its own.
ZONE = "America/Los_Angeles"

#: The one meeting instant every row below is written at. A literal with an
#: explicit offset, so the assertion is about the column and not about whatever
#: the test host's clock or ``TimeZone`` setting happens to be.
INSTANT = "TIMESTAMPTZ '2026-09-15 17:00:00+00'"


def _insert_tenant(conn, tenant_id: uuid.UUID) -> None:
    conn.execute(
        text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
        {"id": tenant_id, "slug": f"scratch-{tenant_id.hex[:12]}"},
    )


def _insert_unit(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    unit_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
            "VALUES (:id, :tid, CAST(:path AS ltree), 'department', 'Scratch')"
        ),
        {"id": unit_id, "tid": tenant_id, "path": f"scratch{tenant_id.hex[:8]}"},
    )
    return unit_id


def _insert_user(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    """An account that could have recorded a meeting.

    ``external_subject`` is globally unique (migration 0003), so it is keyed on
    the generated id rather than on the tenant — two scratch tenants in one test
    would otherwise collide.
    """
    user_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :tid, :sub, :email)"
        ),
        {
            "id": user_id,
            "tid": tenant_id,
            "sub": f"scratch-{user_id.hex}",
            "email": f"scratch-{user_id.hex[:12]}@example.invalid",
        },
    )
    return user_id


def _scaffold(scratch) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """A tenant, a unit in it, and an account that could record a meeting."""
    tenant_id = uuid.uuid4()
    with scratch.begin() as conn:
        _insert_tenant(conn, tenant_id)
        unit_id = _insert_unit(conn, tenant_id)
        user_id = _insert_user(conn, tenant_id)
    return tenant_id, unit_id, user_id


def test_a_meeting_with_no_time_is_refused_by_the_database(engine: Engine):
    """The invariant. An insert naming every column but ``scheduled_at`` fails.

    ADR-0010 rule 2 and finding F-003. The route refuses first with a worded
    ``422``; this is the refusal that holds when a later writer skips the route.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)

        with connected(url) as scratch:
            tenant_id, unit_id, user_id = _scaffold(scratch)

            with pytest.raises(DBAPIError) as raised, scratch.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO cba_meeting (id, tenant_id, owning_unit_id, title, "
                        "time_zone, location_or_link, status, created_by_user_id) "
                        "VALUES (:id, :tid, :unit, 'CBA team sync', :zone, "
                        "'Bldg 9-241', 'scheduled', :user)"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "tid": tenant_id,
                        "unit": unit_id,
                        "zone": ZONE,
                        "user": user_id,
                    },
                )

        assert applied_revision(url) == REVISION

    message = str(raised.value).lower()
    assert "scheduled_at" in message and "null" in message, (
        "an insert naming no meeting time was not refused for the reason this "
        f"migration exists to refuse it: {raised.value}"
    )


def test_the_column_carries_no_default(engine: Engine):
    """Read out of the catalog, because a default would make the test above pass.

    A migration that acquired ``server_default=now()`` would accept the omitting
    insert and answer "the meeting is now" — the fabrication, not the refusal.
    The two tests together are what distinguish them.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)

        with connected(url) as scratch, scratch.connect() as conn:
            default, nullable = conn.execute(
                text(
                    "SELECT column_default, is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'cba_meeting' AND column_name = 'scheduled_at'"
                )
            ).one()

    assert default is None, (
        f"scheduled_at acquired a server default ({default!r}). A default turns "
        "'nobody named a time' into a fabricated slot — finding F-003."
    )
    assert nullable == "NO"


def test_a_meeting_with_a_time_is_stored(engine: Engine):
    """The complement: the refusal above is a refusal, not a broken table.

    Without this, every assertion in this file would pass against a migration
    whose table rejected everything.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)

        with connected(url) as scratch:
            tenant_id, unit_id, user_id = _scaffold(scratch)

            with scratch.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO cba_meeting (id, tenant_id, owning_unit_id, title, "
                        "scheduled_at, time_zone, location_or_link, status, "
                        f"created_by_user_id) VALUES (:id, :tid, :unit, 'CBA team sync', "
                        f"{INSTANT}, :zone, 'Bldg 9-241', 'scheduled', :user)"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "tid": tenant_id,
                        "unit": unit_id,
                        "zone": ZONE,
                        "user": user_id,
                    },
                )

            with scratch.connect() as conn:
                stored = conn.execute(
                    text("SELECT count(*) FROM cba_meeting WHERE status = 'scheduled'")
                ).scalar_one()

    assert stored == 1


def test_an_unknown_status_is_refused(engine: Engine):
    """``ck_cba_meeting_status`` is the vocabulary, and there is no third word.

    A cancellation is a transition, never a ``DELETE`` (OQ-CBA-018's shape), so
    the two states have to stay exactly two: a row reading ``'postponed'`` would
    be a state no surface renders and no rule governs.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)

        with connected(url) as scratch:
            tenant_id, unit_id, user_id = _scaffold(scratch)

            with pytest.raises(DBAPIError) as raised, scratch.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO cba_meeting (id, tenant_id, owning_unit_id, title, "
                        "scheduled_at, time_zone, status, created_by_user_id) "
                        f"VALUES (:id, :tid, :unit, 'CBA team sync', {INSTANT}, "
                        ":zone, 'postponed', :user)"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "tid": tenant_id,
                        "unit": unit_id,
                        "zone": ZONE,
                        "user": user_id,
                    },
                )

    assert "ck_cba_meeting_status" in str(raised.value)


def test_a_unit_from_another_tenant_is_refused(engine: Engine):
    """The composite foreign key, which is the reason it is composite.

    A single-column key to ``org_unit.id`` would accept this row: the unit exists,
    it is simply somebody else's. The pair ``(tenant_id, owning_unit_id)`` is what
    makes tenant isolation structural rather than remembered (v1.1 §2.2).
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)

        with connected(url) as scratch:
            tenant_id, _unit_id, user_id = _scaffold(scratch)
            _other_tenant, other_unit_id, _other_user = _scaffold(scratch)

            with pytest.raises(DBAPIError) as raised, scratch.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO cba_meeting (id, tenant_id, owning_unit_id, title, "
                        "scheduled_at, time_zone, status, created_by_user_id) "
                        f"VALUES (:id, :tid, :unit, 'CBA team sync', {INSTANT}, "
                        ":zone, 'scheduled', :user)"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "tid": tenant_id,
                        # A real unit, in the wrong tenant.
                        "unit": other_unit_id,
                        "zone": ZONE,
                        "user": user_id,
                    },
                )

    assert "foreign key" in str(raised.value).lower()


def test_a_blank_title_is_refused(engine: Engine):
    """``''`` is a third state nobody defined, and the CHECK refuses it.

    NULL means "no title", and the column is NOT NULL, so the only way to store a
    titleless meeting would be the empty string — which every surface would render
    as a blank row rather than as the absence it is.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)

        with connected(url) as scratch:
            tenant_id, unit_id, user_id = _scaffold(scratch)

            with pytest.raises(DBAPIError) as raised, scratch.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO cba_meeting (id, tenant_id, owning_unit_id, title, "
                        "scheduled_at, time_zone, status, created_by_user_id) "
                        f"VALUES (:id, :tid, :unit, '   ', {INSTANT}, "
                        ":zone, 'scheduled', :user)"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "tid": tenant_id,
                        "unit": unit_id,
                        "zone": ZONE,
                        "user": user_id,
                    },
                )

    assert "ck_cba_meeting_title_shape" in str(raised.value)


def test_a_blank_time_zone_is_refused(engine: Engine):
    """The zone is the half a ``timestamptz`` cannot recover, so it must be named.

    A blank zone would leave every rendering to pick one on the unit's behalf,
    which is ``scheduled_at``'s fabrication moved into a neighbouring column: the
    instant would be right and the wall-clock time shown beside it would be
    whatever the reader's browser guessed.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)

        with connected(url) as scratch:
            tenant_id, unit_id, user_id = _scaffold(scratch)

            with pytest.raises(DBAPIError) as raised, scratch.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO cba_meeting (id, tenant_id, owning_unit_id, title, "
                        "scheduled_at, time_zone, status, created_by_user_id) "
                        f"VALUES (:id, :tid, :unit, 'CBA team sync', {INSTANT}, "
                        "'  ', 'scheduled', :user)"
                    ),
                    {"id": uuid.uuid4(), "tid": tenant_id, "unit": unit_id, "user": user_id},
                )

    assert "ck_cba_meeting_time_zone" in str(raised.value)


def test_a_blank_location_is_refused_but_an_absent_one_is_not(engine: Engine):
    """Both halves, because this is the constraint whose *permitted* side carries meaning.

    ``location_or_link`` is genuinely optional: a meeting whose room is still
    being settled is a real thing to have recorded, and NULL is how the row says
    so. ``''`` is refused because it would be a second way of saying the same
    thing that every surface renders differently — a blank cell rather than an
    absence. A test attempting only the refusal would pass against a column that
    had been made ``NOT NULL``, which is a different and wrong decision.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)

        with connected(url) as scratch:
            tenant_id, unit_id, user_id = _scaffold(scratch)

            with pytest.raises(DBAPIError) as raised, scratch.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO cba_meeting (id, tenant_id, owning_unit_id, title, "
                        "scheduled_at, time_zone, location_or_link, status, "
                        f"created_by_user_id) VALUES (:id, :tid, :unit, 'CBA team sync', "
                        f"{INSTANT}, :zone, '', 'scheduled', :user)"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "tid": tenant_id,
                        "unit": unit_id,
                        "zone": ZONE,
                        "user": user_id,
                    },
                )

            # The permitted half: no location at all.
            with scratch.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO cba_meeting (id, tenant_id, owning_unit_id, title, "
                        "scheduled_at, time_zone, status, created_by_user_id) "
                        f"VALUES (:id, :tid, :unit, 'Room to be confirmed', {INSTANT}, "
                        ":zone, 'scheduled', :user)"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "tid": tenant_id,
                        "unit": unit_id,
                        "zone": ZONE,
                        "user": user_id,
                    },
                )

            with scratch.connect() as conn:
                unplaced = conn.execute(
                    text("SELECT count(*) FROM cba_meeting WHERE location_or_link IS NULL")
                ).scalar_one()

    assert "ck_cba_meeting_location_shape" in str(raised.value)
    assert unplaced == 1
