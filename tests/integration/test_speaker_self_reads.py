"""The Speaker's own reads, at the repository (B26 T6b-2 plan §7.2).

* ``find_bound_profile`` resolves a login to the profile bound to it, in the
  caller's tenant only.
* Invitations: the professional's own ``dispatched`` rows, newest first. Never
  ``pending`` (never sent) or ``skipped`` (a Connector's internal reason).
* Engagements: own confirmed journeys, cancelled and attended included,
  bucketed on the event's local date against a supplied "today". An unknown or
  missing date is never "past".
* Rows are keyed by ``professional_id``, never by the login id: after T6b-5's
  merged login the two differ.

Requires a live database; skipped otherwise. A local skip is not proof — CI is.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

pytest.importorskip("sqlalchemy")

from conftest import _TENANT_SCOPED_TABLES, ensure_owning_unit, unique_subject
from smartmatch_persistence.cba_invitations import InvitationRepository
from smartmatch_persistence.pipeline import PipelineRepository
from smartmatch_persistence.speaker_portal import BoundSpeakerProfile, SpeakerPortalRepository
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration

PORTAL = SpeakerPortalRepository()
INVITES = InvitationRepository()
PIPELINE = PipelineRepository()

AS_OF = date(2026, 10, 14)
T0 = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _user(conn: Any, tenant_id: uuid.UUID) -> uuid.UUID:
    user_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :tid, :sub, :email)"
        ),
        {
            "id": user_id,
            "tid": tenant_id,
            "sub": unique_subject(f"speaker-self-{user_id.hex[:8]}"),
            "email": f"{user_id.hex[:8]}@example.edu",
        },
    )
    return user_id


def _profile(conn: Any, tenant_id: uuid.UUID, *, bound_to: uuid.UUID | None = None) -> uuid.UUID:
    """A roster profile; ``bound_to`` binds it to that login."""
    professional_id = _user(conn, tenant_id)
    conn.execute(
        text(
            "INSERT INTO speaker_profile (tenant_id, professional_id, owning_unit_id, full_name, "
            "account_user_id, account_bound_at) VALUES (:tid, :pid, :unit, 'Dana Reyes', "
            ":acct, CASE WHEN CAST(:acct AS uuid) IS NULL THEN NULL ELSE now() END)"
        ),
        {
            "tid": tenant_id,
            "pid": professional_id,
            "unit": ensure_owning_unit(conn, tenant_id),
            "acct": bound_to,
        },
    )
    return professional_id


def _bind(conn: Any, tenant_id: uuid.UUID, professional_id: uuid.UUID, login: uuid.UUID) -> None:
    conn.execute(
        text(
            "UPDATE speaker_profile SET account_user_id = :acct, account_bound_at = now() "
            "WHERE tenant_id = :tid AND professional_id = :pid"
        ),
        {"acct": login, "tid": tenant_id, "pid": professional_id},
    )


def _batch(
    conn: Any, tenant_id: uuid.UUID, actor: uuid.UUID, name: str = "Spring Mixer"
) -> uuid.UUID:
    batch_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO cba_invitation_batch (id, tenant_id, owning_unit_id, idempotency_key, "
            "template_id, event_name, event_date, created_by_user_id) "
            "VALUES (:id, :tid, :unit, :key, 'speaker_invite_v1', :name, "
            "'Thursday 12 March 2027', :actor)"
        ),
        {
            "id": batch_id,
            "tid": tenant_id,
            "unit": ensure_owning_unit(conn, tenant_id),
            "key": f"self-{batch_id.hex}",
            "name": name,
            "actor": actor,
        },
    )
    return batch_id


def _invitation(
    conn: Any,
    tenant_id: uuid.UUID,
    batch_id: uuid.UUID,
    professional_id: uuid.UUID,
    actor: uuid.UUID,
    *,
    status: str = "dispatched",
    dispatched_at: datetime = T0,
) -> uuid.UUID:
    """One ``cba_invitation`` row the ``0029`` CHECKs accept."""
    invitation_id = uuid.uuid4()
    unit = ensure_owning_unit(conn, tenant_id)
    job_id = None
    if status == "dispatched":
        job_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO job (id, tenant_id, owning_unit_id, command_type, status, "
                "actor_id, payload) VALUES (:id, :tid, :unit, 'outreach.send', 'succeeded', "
                ":actor, CAST('{}' AS jsonb))"
            ),
            {"id": job_id, "tid": tenant_id, "unit": unit, "actor": actor},
        )
    skipped = status == "skipped"
    conn.execute(
        text(
            "INSERT INTO cba_invitation (id, tenant_id, owning_unit_id, batch_id, "
            "professional_id, status, skip_reason, recipient_address, outreach_send_job_id, "
            "dispatched_at, response_status) VALUES (:id, :tid, :unit, :batch, :pid, :status, "
            ":skip, :addr, :job, :dispatched, 'awaiting_response')"
        ),
        {
            "id": invitation_id,
            "tid": tenant_id,
            "unit": unit,
            "batch": batch_id,
            "pid": professional_id,
            "status": status,
            "skip": "not_on_roster" if skipped else None,
            "addr": None if skipped else "speaker@example.invalid",
            "job": job_id,
            "dispatched": dispatched_at if status == "dispatched" else None,
        },
    )
    return invitation_id


def _event(
    conn: Any,
    tenant_id: uuid.UUID,
    *,
    on: date | None,
    title: str | None = None,
) -> uuid.UUID:
    event_id = uuid.uuid4()
    title = title or f"Guest lecture {event_id.hex[:8]}"
    conn.execute(
        text(
            "INSERT INTO event (id, tenant_id, host_org_unit_id, title, normalized_title, "
            "on_date, time_zone, time_precision, resolved_date, origin) VALUES (:id, :tid, "
            ":unit, :title, :norm, :on, CASE WHEN CAST(:on AS date) IS NULL THEN NULL "
            "ELSE 'America/Los_Angeles' END, :prec, :on, 'coordinator_entry')"
        ),
        {
            "id": event_id,
            "tid": tenant_id,
            "unit": ensure_owning_unit(conn, tenant_id),
            "title": title,
            "norm": title.lower(),
            "on": on,
            "prec": "unresolved" if on is None else "date_only",
        },
    )
    return event_id


def _journey(
    conn: Any,
    tenant_id: uuid.UUID,
    professional_id: uuid.UUID,
    event_id: uuid.UUID,
    *,
    confirmed: bool = True,
    cancelled_by: uuid.UUID | None = None,
    attended: bool = False,
) -> uuid.UUID:
    record_id = uuid.uuid4()
    unit = ensure_owning_unit(conn, tenant_id)
    attendance_id = None
    if attended:
        attendance_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO attendance_record (id, tenant_id, owning_unit_id, subject_id, "
                "event_id, method) VALUES (:id, :tid, :unit, :sub, :ev, 'coordinator_entry')"
            ),
            {
                "id": attendance_id,
                "tid": tenant_id,
                "unit": unit,
                "sub": professional_id,
                "ev": event_id,
            },
        )
    conn.execute(
        text(
            "INSERT INTO pipeline_record (id, tenant_id, owning_unit_id, subject_id, "
            "opportunity_event_id, matched_at, matched_provenance, contacted_at, confirmed_at, "
            "attended_at, attended_attendance_id, cancelled_at, cancelled_by_user_id) "
            "VALUES (:id, :tid, :unit, :sub, :ev, :m, 'synthetic / coordinator-accepted', :c, "
            ":conf, :att, :att_id, :canc, :canc_by)"
        ),
        {
            "id": record_id,
            "tid": tenant_id,
            "unit": unit,
            "sub": professional_id,
            "ev": event_id,
            "m": T0,
            "c": T0 + timedelta(hours=1),
            "conf": T0 + timedelta(hours=2) if confirmed else None,
            "att": T0 + timedelta(hours=3) if attended else None,
            "att_id": attendance_id,
            "canc": T0 + timedelta(hours=4) if cancelled_by else None,
            "canc_by": cancelled_by,
        },
    )
    return record_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(engine: Engine, tenant_id: uuid.UUID) -> Iterator[Any]:
    """A connection-per-call helper; removes the journeys the shared teardown skips."""

    class _Db:
        def run(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
            with engine.begin() as conn:
                return fn(conn, *args, **kwargs)

    yield _Db()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM pipeline_record WHERE tenant_id = :t"), {"t": tenant_id})
        conn.execute(text("DELETE FROM attendance_record WHERE tenant_id = :t"), {"t": tenant_id})


@pytest.fixture
def other_tenant_id(engine: Engine) -> Iterator[uuid.UUID]:
    tid = uuid.uuid4()
    slug = f"test-other-{tid.hex[:12]}"
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :name)"),
            {"id": tid, "slug": slug, "name": slug},
        )
    yield tid
    with engine.begin() as conn:
        for table in _TENANT_SCOPED_TABLES:
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tid})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tid})


def _read(factory: sessionmaker[Session], fn: Any, **kwargs: Any) -> Any:
    with factory() as session:
        return fn(session, **kwargs)


# ---------------------------------------------------------------------------
# Bound profile
# ---------------------------------------------------------------------------


def test_find_bound_profile_returns_profile_and_unit_path(
    db: Any, tenant_id: uuid.UUID, session_factory: sessionmaker[Session]
) -> None:
    pid = db.run(_profile, tenant_id)
    db.run(_bind, tenant_id, pid, pid)
    bound = _read(
        session_factory, PORTAL.find_bound_profile, tenant_id=tenant_id, account_user_id=pid
    )
    assert isinstance(bound, BoundSpeakerProfile)
    assert bound.professional_id == pid
    assert bound.owning_unit_id == db.run(ensure_owning_unit, tenant_id)
    assert bound.owning_unit_path == "iawest.jobs"


def test_find_bound_profile_is_tenant_scoped(
    db: Any,
    tenant_id: uuid.UUID,
    other_tenant_id: uuid.UUID,
    session_factory: sessionmaker[Session],
) -> None:
    pid = db.run(_profile, tenant_id)
    db.run(_bind, tenant_id, pid, pid)
    assert (
        _read(
            session_factory,
            PORTAL.find_bound_profile,
            tenant_id=other_tenant_id,
            account_user_id=pid,
        )
        is None
    )


def test_unbound_login_finds_nothing(
    db: Any, tenant_id: uuid.UUID, session_factory: sessionmaker[Session]
) -> None:
    pid = db.run(_profile, tenant_id)
    assert (
        _read(session_factory, PORTAL.find_bound_profile, tenant_id=tenant_id, account_user_id=pid)
        is None
    )


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------


def test_invitations_are_own_dispatched_rows_only(
    db: Any,
    tenant_id: uuid.UUID,
    other_tenant_id: uuid.UUID,
    session_factory: sessionmaker[Session],
) -> None:
    actor = db.run(_user, tenant_id)
    me = db.run(_profile, tenant_id)
    other = db.run(_profile, tenant_id)
    b1 = db.run(_batch, tenant_id, actor)
    b2 = db.run(_batch, tenant_id, actor)
    b3 = db.run(_batch, tenant_id, actor)
    mine = db.run(_invitation, tenant_id, b1, me, actor)
    db.run(_invitation, tenant_id, b2, me, actor, status="pending")
    db.run(_invitation, tenant_id, b3, me, actor, status="skipped")
    db.run(_invitation, tenant_id, b1, other, actor)
    # Another tenant's row carrying the same professional id.
    o_actor = db.run(_user, other_tenant_id)
    o_batch = db.run(_batch, other_tenant_id, o_actor)
    db.run(_invitation, other_tenant_id, o_batch, me, o_actor)

    rows = _read(
        session_factory,
        INVITES.list_for_professional,
        tenant_id=tenant_id,
        professional_id=me,
        limit=50,
    )
    assert [row.id for row in rows] == [mine]
    row = rows[0]
    assert row.event_name == "Spring Mixer"
    assert row.event_date == "Thursday 12 March 2027"
    assert row.event_local_date is None
    assert row.event_time_zone is None
    assert row.response_status == "awaiting_response"


def test_invitations_order_newest_first_and_honour_limit(
    db: Any, tenant_id: uuid.UUID, session_factory: sessionmaker[Session]
) -> None:
    actor = db.run(_user, tenant_id)
    me = db.run(_profile, tenant_id)
    ids = []
    for hours in (0, 2, 1):
        batch = db.run(_batch, tenant_id, actor)
        ids.append(
            db.run(
                _invitation, tenant_id, batch, me, actor, dispatched_at=T0 + timedelta(hours=hours)
            )
        )
    rows = _read(
        session_factory,
        INVITES.list_for_professional,
        tenant_id=tenant_id,
        professional_id=me,
        limit=2,
    )
    assert [row.id for row in rows] == [ids[1], ids[2]]


def test_get_for_professional_refuses_another_professionals_invitation(
    db: Any, tenant_id: uuid.UUID, session_factory: sessionmaker[Session]
) -> None:
    actor = db.run(_user, tenant_id)
    me = db.run(_profile, tenant_id)
    other = db.run(_profile, tenant_id)
    batch = db.run(_batch, tenant_id, actor)
    theirs = db.run(_invitation, tenant_id, batch, other, actor)
    mine = db.run(_invitation, tenant_id, batch, me, actor)
    pending_batch = db.run(_batch, tenant_id, actor)
    pending = db.run(_invitation, tenant_id, pending_batch, me, actor, status="pending")

    def get(invitation_id: uuid.UUID) -> Any:
        return _read(
            session_factory,
            INVITES.get_for_professional,
            tenant_id=tenant_id,
            professional_id=me,
            invitation_id=invitation_id,
        )

    assert get(theirs) is None
    assert get(pending) is None
    assert get(uuid.uuid4()) is None
    assert get(mine).id == mine


# ---------------------------------------------------------------------------
# Engagements
# ---------------------------------------------------------------------------


def _engagements(
    factory: sessionmaker[Session], tenant_id: uuid.UUID, pid: uuid.UUID, when: str
) -> list[Any]:
    return list(
        _read(
            factory,
            PIPELINE.list_engagements_for_speaker,
            tenant_id=tenant_id,
            professional_id=pid,
            today=AS_OF,
            when=when,
            limit=50,
        )
    )


def test_engagements_include_cancelled_and_attended_exclude_unconfirmed(
    db: Any, tenant_id: uuid.UUID, session_factory: sessionmaker[Session]
) -> None:
    actor = db.run(_user, tenant_id)
    me = db.run(_profile, tenant_id)
    later = AS_OF + timedelta(days=5)
    confirmed = db.run(_journey, tenant_id, me, db.run(_event, tenant_id, on=later))
    cancelled = db.run(
        _journey, tenant_id, me, db.run(_event, tenant_id, on=later), cancelled_by=actor
    )
    attended = db.run(_journey, tenant_id, me, db.run(_event, tenant_id, on=later), attended=True)
    db.run(_journey, tenant_id, me, db.run(_event, tenant_id, on=later), confirmed=False)

    rows = _engagements(session_factory, tenant_id, me, "upcoming")
    by_id = {row.id: row for row in rows}
    assert set(by_id) == {confirmed, cancelled, attended}
    assert by_id[cancelled].cancelled_at is not None
    assert by_id[attended].attended_at is not None


def test_engagement_buckets_by_event_local_date(
    db: Any, tenant_id: uuid.UUID, session_factory: sessionmaker[Session]
) -> None:
    me = db.run(_profile, tenant_id)
    yesterday = db.run(
        _journey, tenant_id, me, db.run(_event, tenant_id, on=AS_OF - timedelta(days=1))
    )
    today = db.run(_journey, tenant_id, me, db.run(_event, tenant_id, on=AS_OF))
    unresolved = db.run(_journey, tenant_id, me, db.run(_event, tenant_id, on=None))
    missing = db.run(_journey, tenant_id, me, uuid.uuid4())

    upcoming = _engagements(session_factory, tenant_id, me, "upcoming")
    past = _engagements(session_factory, tenant_id, me, "past")
    assert [row.id for row in past] == [yesterday]
    assert upcoming[0].id == today
    assert {row.id for row in upcoming} == {today, unresolved, missing}
    no_event = next(row for row in upcoming if row.id == missing)
    assert no_event.event_title is None
    assert past[0].event_local_date == AS_OF - timedelta(days=1)
    assert past[0].event_time_zone == "America/Los_Angeles"


def test_rows_are_keyed_by_professional_not_login(
    db: Any, tenant_id: uuid.UUID, session_factory: sessionmaker[Session]
) -> None:
    actor = db.run(_user, tenant_id)
    login = db.run(_profile, tenant_id)  # a login that also has rows keyed to it
    me = db.run(_profile, tenant_id)
    db.run(_bind, tenant_id, me, login)
    batch = db.run(_batch, tenant_id, actor)
    mine = db.run(_invitation, tenant_id, batch, me, actor)
    db.run(_invitation, tenant_id, batch, login, actor)
    my_journey = db.run(_journey, tenant_id, me, db.run(_event, tenant_id, on=AS_OF))
    db.run(_journey, tenant_id, login, db.run(_event, tenant_id, on=AS_OF))

    bound = _read(
        session_factory, PORTAL.find_bound_profile, tenant_id=tenant_id, account_user_id=login
    )
    assert bound.professional_id == me
    invitations = _read(
        session_factory,
        INVITES.list_for_professional,
        tenant_id=tenant_id,
        professional_id=bound.professional_id,
        limit=50,
    )
    assert [row.id for row in invitations] == [mine]
    journeys = _engagements(session_factory, tenant_id, bound.professional_id, "upcoming")
    assert [row.id for row in journeys] == [my_journey]
