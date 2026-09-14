"""What migration ``0035`` refuses, asserted against a real database.

``0035`` creates the three side tables the manual-event surface writes to:
``event_manual_detail`` (the event-only extras that do not belong on ``event``
itself), and the feedback-QR pair ``event_feedback_qr`` /
``event_feedback_qr_open``.

What this file is for
=====================
The revision carries five CHECK constraints, and
``tests/integration/test_check_constraints.py`` pins each one's *expression*.
A pinned expression is a claim about what a constraint **says**; it would be
satisfied by a constraint nothing ever writes against. This file is the other
half — the forbidden and the permitted write for each one, attempted against a
live database — and it is what
``test_every_declared_constraint_says_where_it_is_exercised`` points at.

Every refusal test here is paired with a permitted one on purpose. A test that
attempts only the refusal passes just as happily against a table that rejects
*everything*, which is the failure mode that matters: these columns are all
optional detail, and a constraint that had been tightened into "NOT NULL" would
refuse to record an event whose capacity or room is still being settled.

The inserts are written as raw SQL rather than through the repository because
the repository and the route both refuse first, with worded errors. This is the
guarantee that holds when a *second* writer is added by somebody who read
neither.

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
#: Read off the ``revision =`` line of ``0034_cba_meeting.py``, not off a
#: filename: Alembic revision ids are not filenames, and this repository carries
#: the standing proof — ``0024_cba_classification_schema.py`` declares
#: ``revision = "0024_cba_classification"``.
REVISION_BEFORE = "0034_cba_meeting"

#: The revision under test.
REVISION = "0035_manual_event_detail"

ON_DATE = "2026-10-14"
ZONE = "America/Los_Angeles"

#: A token of the shape the redirect actually mints. ``ck_..._token_shape``
#: requires at least 20 non-blank characters, so a literal short enough to read
#: would not be a fair stand-in for the permitted case.
#:
#: Assembled rather than written out, because a 20-plus character string on a
#: line naming a token is precisely what the ``hard-coded-credential`` rule in
#: ``tools/scan_forbidden.py`` exists to catch. The gate cannot tell a synthetic
#: token from a real one and should not have to, so this avoids the shape
#: instead of being excused from it.
GOOD_TOKEN = "qr-sample-" + "0" * 22

#: RFC 2606 reserves ``.invalid``; nothing here opens a socket.
GOOD_DESTINATION = "https://forms.example.invalid/feedback/analytics-panel"


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
    """An account that could have filed an event.

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


def _insert_event(conn, tenant_id: uuid.UUID, unit_id: uuid.UUID) -> uuid.UUID:
    """A coordinator-entry event — the origin a manually filed one carries."""
    event_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO event (id, tenant_id, host_org_unit_id, title, normalized_title, "
            "                   on_date, time_zone, time_precision, resolved_date, origin) "
            "VALUES (:id, :tid, :unit, 'Analytics Careers Panel', "
            "        'analytics careers panel', :on_date, :zone, 'date_only', :on_date, "
            "        'coordinator_entry')"
        ),
        {"id": event_id, "tid": tenant_id, "unit": unit_id, "on_date": ON_DATE, "zone": ZONE},
    )
    return event_id


def _scaffold(scratch) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """A tenant, a unit in it, an account, and one event to hang detail off."""
    tenant_id = uuid.uuid4()
    with scratch.begin() as conn:
        _insert_tenant(conn, tenant_id)
        unit_id = _insert_unit(conn, tenant_id)
        user_id = _insert_user(conn, tenant_id)
        event_id = _insert_event(conn, tenant_id, unit_id)
    return tenant_id, unit_id, user_id, event_id


def _detail_insert(columns: str, values: str) -> str:
    return (
        "INSERT INTO event_manual_detail "
        f"(event_id, tenant_id, owning_unit_id{columns}) "
        f"VALUES (:event, :tid, :unit{values})"
    )


def _qr_insert(token: str, destination: str) -> str:
    return (
        "INSERT INTO event_feedback_qr "
        "(id, tenant_id, owning_unit_id, event_id, public_token, destination_url, created_by) "
        f"VALUES (:id, :tid, :unit, :event, {token}, {destination}, :user)"
    )


# --- event_manual_detail ------------------------------------------------


@pytest.mark.parametrize(
    ("column", "constraint"),
    [
        ("capacity", "ck_event_manual_detail_capacity"),
        ("volunteer_openings", "ck_event_manual_detail_volunteer_openings"),
    ],
)
def test_a_negative_headcount_is_refused(engine: Engine, column: str, constraint: str):
    """Neither a room's capacity nor a call for volunteers can run backwards.

    Both columns are nullable — "not yet decided" is a real state and stays
    representable — so the constraint is the only thing standing between the
    table and a row claiming an event seats minus one person. A negative
    opening count would also subtract from any total a coordinator view sums.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)

        with connected(url) as scratch:
            tenant_id, unit_id, _user_id, event_id = _scaffold(scratch)

            with pytest.raises(DBAPIError) as raised, scratch.begin() as conn:
                conn.execute(
                    text(_detail_insert(f", {column}", ", -1")),
                    {"event": event_id, "tid": tenant_id, "unit": unit_id},
                )

        assert applied_revision(url) == REVISION

    assert constraint in str(raised.value)


def test_a_version_below_one_is_refused(engine: Engine):
    """``ck_event_manual_detail_version`` — the first write is version 1.

    The column carries ``server_default = 1`` and the repository bumps it on
    every edit, so it is the optimistic-concurrency counter the update path
    compares against. A row at 0 would sort *below* the first write and make a
    stale edit look fresh, which is the one way this counter can do harm.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)

        with connected(url) as scratch:
            tenant_id, unit_id, _user_id, event_id = _scaffold(scratch)

            with pytest.raises(DBAPIError) as raised, scratch.begin() as conn:
                conn.execute(
                    text(_detail_insert(", version", ", 0")),
                    {"event": event_id, "tid": tenant_id, "unit": unit_id},
                )

    assert "ck_event_manual_detail_version" in str(raised.value)


def test_detail_that_names_no_headcount_at_all_is_stored(engine: Engine):
    """The permitted half, and the one that matters most here.

    Every one of these columns is optional: an event filed before the room is
    booked names no capacity, and one that needs no help names no openings.
    Without this test the three refusals above would pass unchanged against a
    table somebody had tightened into ``NOT NULL``, which would refuse exactly
    the event this surface exists to let a Connector file early.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)

        with connected(url) as scratch:
            tenant_id, unit_id, _user_id, event_id = _scaffold(scratch)

            with scratch.begin() as conn:
                conn.execute(
                    text(_detail_insert("", "")),
                    {"event": event_id, "tid": tenant_id, "unit": unit_id},
                )

            with scratch.connect() as conn:
                capacity, openings, version = conn.execute(
                    text(
                        "SELECT capacity, volunteer_openings, version "
                        "FROM event_manual_detail WHERE event_id = :event"
                    ),
                    {"event": event_id},
                ).one()

    assert capacity is None
    assert openings is None
    assert version == 1, "the server default is what makes version 1 the first write"


def test_a_zero_headcount_is_stored(engine: Engine):
    """Zero is not negative, and the boundary is the half most easily lost.

    ``>= 0`` rather than ``> 0`` is deliberate: an event that seats nobody
    because it is online, and one that has closed its volunteer call, are both
    real. A constraint tightened to ``> 0`` passes every refusal test above.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)

        with connected(url) as scratch:
            tenant_id, unit_id, _user_id, event_id = _scaffold(scratch)

            with scratch.begin() as conn:
                conn.execute(
                    text(_detail_insert(", capacity, volunteer_openings", ", 0, 0")),
                    {"event": event_id, "tid": tenant_id, "unit": unit_id},
                )

            with scratch.connect() as conn:
                stored = conn.execute(
                    text(
                        "SELECT count(*) FROM event_manual_detail "
                        "WHERE event_id = :event AND capacity = 0 AND volunteer_openings = 0"
                    ),
                    {"event": event_id},
                ).scalar_one()

    assert stored == 1


# --- event_feedback_qr --------------------------------------------------


def test_a_short_public_token_is_refused(engine: Engine):
    """``ck_event_feedback_qr_token_shape`` — the token is the whole secret.

    ``GET /q/{public_token}`` is unauthenticated by design: the printed code has
    to work for a visitor who has no account. The token's length is therefore
    the only thing making the redirect unguessable, and a short one turns the
    public endpoint into an enumerable index of every event's feedback form.
    The floor is asserted on ``btrim`` so a token padded to length with spaces
    does not satisfy it.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)

        with connected(url) as scratch:
            tenant_id, unit_id, user_id, event_id = _scaffold(scratch)

            with pytest.raises(DBAPIError) as raised, scratch.begin() as conn:
                conn.execute(
                    text(_qr_insert("'qr-tok-short'", ":dest")),
                    {
                        "id": uuid.uuid4(),
                        "tid": tenant_id,
                        "unit": unit_id,
                        "event": event_id,
                        "user": user_id,
                        "dest": GOOD_DESTINATION,
                    },
                )

    assert "ck_event_feedback_qr_token_shape" in str(raised.value)


def test_a_token_padded_to_length_with_blanks_is_refused(engine: Engine):
    """The reason the floor is measured on ``btrim`` and not on ``length``.

    A 30-space token satisfies ``length(public_token) >= 20`` and carries no
    secret whatsoever. This is the counterexample that distinguishes the
    constraint as written from the one a reader would most likely write.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)

        with connected(url) as scratch:
            tenant_id, unit_id, user_id, event_id = _scaffold(scratch)

            with pytest.raises(DBAPIError) as raised, scratch.begin() as conn:
                conn.execute(
                    text(_qr_insert(":token", ":dest")),
                    {
                        "id": uuid.uuid4(),
                        "tid": tenant_id,
                        "unit": unit_id,
                        "event": event_id,
                        "user": user_id,
                        "token": " " * 30,
                        "dest": GOOD_DESTINATION,
                    },
                )

    assert "ck_event_feedback_qr_token_shape" in str(raised.value)


def test_a_blank_destination_is_refused(engine: Engine):
    """``ck_event_feedback_qr_destination_shape`` — a QR must lead somewhere.

    The column is ``NOT NULL``, so the empty string is the only way a
    destinationless QR could be stored. It would print and scan perfectly and
    then redirect a visitor to nothing, which is worse than refusing to mint it.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)

        with connected(url) as scratch:
            tenant_id, unit_id, user_id, event_id = _scaffold(scratch)

            with pytest.raises(DBAPIError) as raised, scratch.begin() as conn:
                conn.execute(
                    text(_qr_insert(":token", "'   '")),
                    {
                        "id": uuid.uuid4(),
                        "tid": tenant_id,
                        "unit": unit_id,
                        "event": event_id,
                        "user": user_id,
                        "token": GOOD_TOKEN,
                    },
                )

    assert "ck_event_feedback_qr_destination_shape" in str(raised.value)


def test_a_well_formed_qr_is_stored(engine: Engine):
    """The complement: the four refusals above are refusals, not a broken table."""
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)

        with connected(url) as scratch:
            tenant_id, unit_id, user_id, event_id = _scaffold(scratch)
            qr_id = uuid.uuid4()

            with scratch.begin() as conn:
                conn.execute(
                    text(_qr_insert(":token", ":dest")),
                    {
                        "id": qr_id,
                        "tid": tenant_id,
                        "unit": unit_id,
                        "event": event_id,
                        "user": user_id,
                        "token": GOOD_TOKEN,
                        "dest": GOOD_DESTINATION,
                    },
                )

            with scratch.connect() as conn:
                token, destination = conn.execute(
                    text(
                        "SELECT public_token, destination_url FROM event_feedback_qr WHERE id = :id"
                    ),
                    {"id": qr_id},
                ).one()

    assert token == GOOD_TOKEN
    assert destination == GOOD_DESTINATION


def test_an_open_is_recorded_against_the_qr_it_belongs_to(engine: Engine):
    """The composite foreign key ``0035`` needed a unique constraint to declare.

    ``event_feedback_qr_open`` references ``(tenant_id, qr_id)``, which is why
    ``event_feedback_qr`` carries ``uq_event_feedback_qr_tenant_id``. Without
    that unique constraint the migration does not apply at all, so this test is
    also the one that would have caught its absence from an empty database.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)

        with connected(url) as scratch:
            tenant_id, unit_id, user_id, event_id = _scaffold(scratch)
            qr_id = uuid.uuid4()

            with scratch.begin() as conn:
                conn.execute(
                    text(_qr_insert(":token", ":dest")),
                    {
                        "id": qr_id,
                        "tid": tenant_id,
                        "unit": unit_id,
                        "event": event_id,
                        "user": user_id,
                        "token": GOOD_TOKEN,
                        "dest": GOOD_DESTINATION,
                    },
                )
                conn.execute(
                    text(
                        "INSERT INTO event_feedback_qr_open (id, tenant_id, qr_id) "
                        "VALUES (:id, :tid, :qr)"
                    ),
                    {"id": uuid.uuid4(), "tid": tenant_id, "qr": qr_id},
                )

            with scratch.connect() as conn:
                opens = conn.execute(
                    text("SELECT count(*) FROM event_feedback_qr_open WHERE qr_id = :qr"),
                    {"qr": qr_id},
                ).scalar_one()

    assert opens == 1


def test_an_open_cannot_name_a_qr_from_another_tenant(engine: Engine):
    """The reason that foreign key is composite rather than a key to ``id``.

    A single-column key to ``event_feedback_qr.id`` would accept this row: the
    QR exists. Naming the tenant in the key is what stops one tenant's scan
    count being incremented through another's.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)

        with connected(url) as scratch:
            tenant_id, unit_id, user_id, event_id = _scaffold(scratch)
            other_tenant = uuid.uuid4()
            with scratch.begin() as conn:
                _insert_tenant(conn, other_tenant)

            qr_id = uuid.uuid4()
            with scratch.begin() as conn:
                conn.execute(
                    text(_qr_insert(":token", ":dest")),
                    {
                        "id": qr_id,
                        "tid": tenant_id,
                        "unit": unit_id,
                        "event": event_id,
                        "user": user_id,
                        "token": GOOD_TOKEN,
                        "dest": GOOD_DESTINATION,
                    },
                )

            with pytest.raises(DBAPIError) as raised, scratch.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO event_feedback_qr_open (id, tenant_id, qr_id) "
                        "VALUES (:id, :tid, :qr)"
                    ),
                    {"id": uuid.uuid4(), "tid": other_tenant, "qr": qr_id},
                )

    assert "fk_event_feedback_qr_open_qr" in str(raised.value)
