"""The CBA speaker handoff: accepted invitation -> confirmed, attendance -> attended.

Track CBA-HANDOFF-PIPELINE. What this file proves, against real storage rather
than against the HTTP response body:

* An **accepted** ``cba_invitation`` (track 20, migration ``0029``) is what makes
  a journey's ``confirmed_at`` true, and a real ``attendance_record`` is what
  makes ``attended_at`` true. Neither stage is ever written without the row that
  evidences it.
* Every stage is written with the **evidencing row's own timestamp** -- the
  invitation's ``created_at``, ``dispatched_at`` and ``response_recorded_at``,
  and the attendance's ``created_at`` -- never a server clock reading standing in
  for a moment nobody recorded.
* Re-applying the identical evidence is a no-op: one row, unchanged timestamps.
* The stages are ordered: an unanswered or declined invitation cannot reach
  ``confirmed``, and nothing reaches ``attended`` without it.
* **No CBA ``member_inquiry`` is ever written.** The stage, its column and its
  history are preserved (``tests/integration/test_pipeline_record_constraints.py``
  still writes one over raw SQL); what is proven here is that no CBA write path
  produces one and no CBA surface offers one.
* The aggregate equals the drill-down, and both equal the Host's confirmed
  speaker list -- ADR-0011 rule 3, proven by comparing three numbers rather than
  by reading three code paths.

Every assertion about what was stored is made through a **separate connection**
to the same database, not through the response body. ``get_session`` rolls back
unconditionally, so a write route that forgot ``session.commit()`` returns a
clean 2xx and stores nothing; only a read on another connection can tell the
two apart.

Requires a live database, and is skipped when none is reachable.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

pytest.importorskip("sqlalchemy")

import httpx
from conftest import JOB_OWNING_UNIT_PATH, ensure_event, ensure_owning_unit, unique_subject
from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_domain.pipeline import (
    CBA_EXCLUDED_STAGES,
    CBA_STAGE_SEQUENCE,
    CbaStageEvidenceKind,
    MemberInquiryExcludedError,
    PipelineStage,
    plan_cba_stages,
)
from smartmatch_persistence.engine import create_session_factory
from smartmatch_persistence.pipeline import (
    CbaAttendanceMismatchError,
    CbaHandoffRepository,
    CbaInvitationNotConfirmedError,
    UnknownOpportunityEventError,
)
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_handoff_tables(engine: Engine, tenant_id: uuid.UUID) -> Iterator[None]:
    """Delete this file's rows, children before parents.

    Same arrangement, and the same reason, as
    ``test_pipeline_record_writers.py``'s own cleanup fixture: every one of
    these tables carries ``ON DELETE RESTRICT`` foreign keys back to
    ``org_unit``, ``user_account`` or ``event``, so a row left behind would make
    the ``tenant_id`` fixture's own teardown fail.
    """
    yield
    with engine.begin() as conn:
        for table in (
            "pipeline_record",
            "attendance_record",
            "cba_invitation",
            "cba_invitation_batch",
            "speaker_profile",
        ):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})


@pytest.fixture(scope="module")
def repo() -> CbaHandoffRepository:
    return CbaHandoffRepository()


@pytest.fixture
def db_session_factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine.url.render_as_string(hide_password=False))


@dataclass(frozen=True, slots=True)
class _Handoff:
    """One prepared journey's ingredients: a speaker, an event, an invitation."""

    tenant_id: uuid.UUID
    unit_id: uuid.UUID
    event_id: uuid.UUID
    professional_id: uuid.UUID
    invitation_id: uuid.UUID
    created_at: datetime
    dispatched_at: datetime | None
    responded_at: datetime | None


def _make_user(conn: Any, tenant_id: uuid.UUID) -> uuid.UUID:
    user_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :tid, :sub, :email)"
        ),
        {
            "id": user_id,
            "tid": tenant_id,
            "sub": unique_subject(f"cba-handoff-{user_id.hex[:8]}"),
            "email": f"{user_id.hex[:8]}@example.edu",
        },
    )
    return user_id


def _make_speaker(conn: Any, tenant_id: uuid.UUID, unit_id: uuid.UUID, name: str) -> uuid.UUID:
    """A ``user_account`` plus the ``speaker_profile`` that names the person.

    The speaker is referenced by **id** everywhere below and never by name:
    ``speaker_profile.professional_id`` is an opaque identifier this test does
    not derive from anything.
    """
    professional_id = _make_user(conn, tenant_id)
    conn.execute(
        text(
            "INSERT INTO speaker_profile "
            "(tenant_id, professional_id, owning_unit_id, full_name, company, title) "
            "VALUES (:tid, :pid, :unit, :name, 'Acme Analytics', 'Director of Insights')"
        ),
        {"tid": tenant_id, "pid": professional_id, "unit": unit_id, "name": name},
    )
    return professional_id


def _make_batch(
    conn: Any, tenant_id: uuid.UUID, unit_id: uuid.UUID, actor_id: uuid.UUID
) -> uuid.UUID:
    batch_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO cba_invitation_batch (id, tenant_id, owning_unit_id, idempotency_key, "
            "template_id, event_name, event_date, created_by_user_id) "
            "VALUES (:id, :tid, :unit, :key, 'speaker_invite_v1', 'CBA Career Panel', "
            "'14 September 2026', :actor)"
        ),
        {
            "id": batch_id,
            "tid": tenant_id,
            "unit": unit_id,
            "key": f"handoff-{batch_id.hex}",
            "actor": actor_id,
        },
    )
    return batch_id


def _make_send_job(
    conn: Any, tenant_id: uuid.UUID, unit_id: uuid.UUID, actor_id: uuid.UUID
) -> uuid.UUID:
    job_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO job (id, tenant_id, owning_unit_id, command_type, status, "
            "actor_id, payload) "
            "VALUES (:id, :tid, :unit, 'outreach.send', 'succeeded', :actor, "
            "CAST('{}' AS jsonb))"
        ),
        {"id": job_id, "tid": tenant_id, "unit": unit_id, "actor": actor_id},
    )
    return job_id


def _make_invitation(
    conn: Any,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    batch_id: uuid.UUID,
    professional_id: uuid.UUID,
    *,
    status: str,
    response_status: str,
    created_at: datetime,
    dispatched_at: datetime | None,
    responded_at: datetime | None,
    send_job_id: uuid.UUID | None,
) -> uuid.UUID:
    """One ``cba_invitation`` row, written so every ``0029`` CHECK is satisfied.

    Raw SQL rather than ``InvitationRepository``: the repository's own write path
    is track 20's to prove, and this file needs rows in states (dispatched,
    declined, skipped) that the repository only reaches through several calls.
    What matters here is that the row is one the database itself accepts, which
    ``ck_cba_invitation_dispatched``, ``ck_cba_invitation_addressed`` and
    ``ck_cba_invitation_response_dated`` decide either way.
    """
    invitation_id = uuid.uuid4()
    skipped = status == "skipped"
    conn.execute(
        text(
            "INSERT INTO cba_invitation (id, tenant_id, owning_unit_id, batch_id, "
            "professional_id, status, skip_reason, recipient_address, "
            "outreach_send_job_id, dispatched_at, response_status, response_recorded_at, "
            "response_channel, created_at, updated_at) "
            "VALUES (:id, :tid, :unit, :batch, :pid, :status, :skip, :addr, "
            ":job, :dispatched, :response_status, :responded, :channel, :created, :created)"
        ),
        {
            "id": invitation_id,
            "tid": tenant_id,
            "unit": unit_id,
            "batch": batch_id,
            "pid": professional_id,
            "status": status,
            "skip": "not_on_roster" if skipped else None,
            "addr": None if skipped else "speaker@example.com",
            "job": send_job_id,
            "dispatched": dispatched_at,
            "response_status": response_status,
            "responded": responded_at,
            "channel": None if responded_at is None else "speaker_link",
            "created": created_at,
        },
    )
    return invitation_id


def _insert_attendance(
    conn: Any,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    subject_id: uuid.UUID,
    event_id: uuid.UUID,
) -> uuid.UUID:
    record_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO attendance_record "
            "(id, tenant_id, owning_unit_id, subject_id, event_id, method) "
            "VALUES (:id, :tid, :unit, :subject, :event, 'coordinator_entry')"
        ),
        {
            "id": record_id,
            "tid": tenant_id,
            "unit": unit_id,
            "subject": subject_id,
            "event": event_id,
        },
    )
    return record_id


def _stored_record(engine: Engine, tenant_id: uuid.UUID, subject_id: uuid.UUID) -> Any:
    """Read the journey back on a **separate connection**.

    The point of the separate connection: a route that never committed leaves
    nothing here, however cheerful its response body was.
    """
    with engine.begin() as conn:
        return conn.execute(
            text(
                "SELECT id, matched_at, matched_provenance, contacted_at, confirmed_at, "
                "attended_at, member_inquiry_at, attended_attendance_id, opportunity_event_id "
                "FROM pipeline_record WHERE tenant_id = :tid AND subject_id = :sid"
            ),
            {"tid": tenant_id, "sid": subject_id},
        ).one_or_none()


# ---------------------------------------------------------------------------
# HTTP client and an authorized coordinator
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Context:
    client: TestClient
    tenant_id: uuid.UUID
    unit_id: uuid.UUID
    event_id: uuid.UUID
    token: str
    actor_id: uuid.UUID
    session_factory: sessionmaker[Session]


def _register_coordinator(
    engine: Engine, client: TestClient, tenant_id: uuid.UUID, unit_path: str
) -> tuple[str, uuid.UUID]:
    user_id = uuid.uuid4()
    subject = unique_subject(f"cba-handoff-actor-{user_id.hex[:8]}")
    token = f"tok-cba-handoff-{uuid.uuid4().hex}"
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                "VALUES (:id, :tid, :sub, :email)"
            ),
            {
                "id": user_id,
                "tid": tenant_id,
                "sub": subject,
                "email": f"{user_id.hex[:8]}@example.edu",
            },
        )
        conn.execute(
            text(
                "INSERT INTO membership (id, tenant_id, user_id, granted_path, role) "
                "VALUES (:id, :tid, :uid, CAST(:path AS ltree), 'coordinator')"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "uid": user_id, "path": unit_path},
        )
    client.app.state.token_verifier.register(token, subject)
    return token, user_id


@pytest.fixture
def context(
    engine: Engine, tenant_id: uuid.UUID, db_session_factory: sessionmaker[Session]
) -> Iterator[_Context]:
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
        event_id = ensure_event(conn, tenant_id, "cba-handoff")
    client = TestClient(app)
    client.app.state.session_factory = db_session_factory
    client.app.state.token_verifier = FixtureTokenVerifier()
    token, actor_id = _register_coordinator(engine, client, tenant_id, JOB_OWNING_UNIT_PATH)
    yield _Context(
        client=client,
        tenant_id=tenant_id,
        unit_id=unit_id,
        event_id=event_id,
        token=token,
        actor_id=actor_id,
        session_factory=db_session_factory,
    )


def _dispatched_invitation(
    engine: Engine,
    ctx: _Context,
    *,
    name: str,
    response_status: str,
    responded: bool,
) -> _Handoff:
    """A speaker who was written to, with whatever answer the test needs."""
    created_at = datetime.now(UTC) - timedelta(days=3)
    dispatched_at = created_at + timedelta(hours=1)
    responded_at = dispatched_at + timedelta(days=1) if responded else None
    with engine.begin() as conn:
        professional_id = _make_speaker(conn, ctx.tenant_id, ctx.unit_id, name)
        batch_id = _make_batch(conn, ctx.tenant_id, ctx.unit_id, ctx.actor_id)
        job_id = _make_send_job(conn, ctx.tenant_id, ctx.unit_id, ctx.actor_id)
        invitation_id = _make_invitation(
            conn,
            ctx.tenant_id,
            ctx.unit_id,
            batch_id,
            professional_id,
            status="dispatched",
            response_status=response_status,
            created_at=created_at,
            dispatched_at=dispatched_at,
            responded_at=responded_at,
            send_job_id=job_id,
        )
    return _Handoff(
        tenant_id=ctx.tenant_id,
        unit_id=ctx.unit_id,
        event_id=ctx.event_id,
        professional_id=professional_id,
        invitation_id=invitation_id,
        created_at=created_at,
        dispatched_at=dispatched_at,
        responded_at=responded_at,
    )


def _accepted_invitation(engine: Engine, ctx: _Context, *, name: str = "Dana Reyes") -> _Handoff:
    return _dispatched_invitation(
        engine, ctx, name=name, response_status="accepted_invitation", responded=True
    )


def _unanswered_invitation(engine: Engine, ctx: _Context, *, name: str) -> _Handoff:
    return _dispatched_invitation(
        engine, ctx, name=name, response_status="awaiting_response", responded=False
    )


def _post_handoff(ctx: _Context, handoff: _Handoff, **body: object) -> httpx.Response:
    return ctx.client.post(
        f"/v1/units/{ctx.unit_id}/cba/events/{handoff.event_id}/speaker-handoff",
        json={"invitation_id": str(handoff.invitation_id), **body},
        headers={"Authorization": f"Bearer {ctx.token}"},
    )


def _get(ctx: _Context, path: str) -> httpx.Response:
    return ctx.client.get(path, headers={"Authorization": f"Bearer {ctx.token}"})


# ---------------------------------------------------------------------------
# An accepted invitation supplies the Confirmed stage's evidence
# ---------------------------------------------------------------------------


def test_an_accepted_invitation_confirms_the_speaker_with_the_invitations_own_timestamps(
    engine: Engine, context: _Context
) -> None:
    handoff = _accepted_invitation(engine, context)

    response = _post_handoff(context, handoff)

    assert response.status_code == 200, response.text
    stored = _stored_record(engine, context.tenant_id, handoff.professional_id)
    assert stored is not None, "the route returned 200 but stored nothing -- missing commit?"
    assert stored.matched_at == handoff.created_at
    assert stored.contacted_at == handoff.dispatched_at
    assert stored.confirmed_at == handoff.responded_at
    assert stored.opportunity_event_id == handoff.event_id
    assert stored.attended_at is None, "attendance is a different table's fact"
    assert stored.member_inquiry_at is None


def test_the_response_carries_the_stage_to_evidence_map(engine: Engine, context: _Context) -> None:
    handoff = _accepted_invitation(engine, context)

    body = _post_handoff(context, handoff).json()

    assert body["speaker"]["current_stage"] == PipelineStage.CONFIRMED.value
    evidenced = {entry["stage"]: entry["evidence"] for entry in body["speaker"]["stages"]}
    assert evidenced == {
        PipelineStage.MATCHED.value: CbaStageEvidenceKind.INVITATION_COMPOSED.value,
        PipelineStage.CONTACTED.value: CbaStageEvidenceKind.INVITATION_DISPATCHED.value,
        PipelineStage.CONFIRMED.value: CbaStageEvidenceKind.INVITATION_ACCEPTED.value,
    }


def test_reapplying_the_same_evidence_is_idempotent(engine: Engine, context: _Context) -> None:
    handoff = _accepted_invitation(engine, context)

    first = _post_handoff(context, handoff)
    second = _post_handoff(context, handoff)

    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["speaker"]["record_id"] == second.json()["speaker"]["record_id"]
    assert first.json()["applied"] == [
        PipelineStage.MATCHED.value,
        PipelineStage.CONTACTED.value,
        PipelineStage.CONFIRMED.value,
    ]
    assert second.json()["applied"] == [], "a replay writes nothing"

    with engine.begin() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM pipeline_record WHERE tenant_id = :tid"),
            {"tid": context.tenant_id},
        ).scalar_one()
    assert count == 1
    stored = _stored_record(engine, context.tenant_id, handoff.professional_id)
    assert stored is not None
    assert stored.confirmed_at == handoff.responded_at, "the replay must not move the timestamp"


# ---------------------------------------------------------------------------
# No stage without evidence, and the stages stay ordered
# ---------------------------------------------------------------------------


def test_an_unanswered_invitation_never_reaches_confirmed(
    engine: Engine, context: _Context
) -> None:
    handoff = _unanswered_invitation(engine, context, name="Sam Okafor")

    response = _post_handoff(context, handoff)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "cba_invitation_not_accepted"
    assert _stored_record(engine, context.tenant_id, handoff.professional_id) is None, (
        "a refused handoff writes no journey at all"
    )


def test_a_declined_invitation_never_reaches_confirmed(engine: Engine, context: _Context) -> None:
    handoff = _dispatched_invitation(
        engine, context, name="Lee Brandt", response_status="declined_invitation", responded=True
    )

    assert _post_handoff(context, handoff).status_code == 409
    assert _stored_record(engine, context.tenant_id, handoff.professional_id) is None


def test_a_skipped_invitation_plans_no_stage_at_all() -> None:
    """A pure-domain check: a skipped recipient is not a paired speaker.

    ``ck_cba_invitation_addressed`` means a skipped row names no channel and no
    draft, so it records somebody the Connector was told not to write to.
    """

    @dataclass(frozen=True, slots=True)
    class _Skipped:
        created_at: datetime
        status: str = "skipped"
        response_status: str = "awaiting_response"
        dispatched_at: datetime | None = None
        response_recorded_at: datetime | None = None

    assert plan_cba_stages(_Skipped(created_at=datetime.now(UTC))) == ()


def test_the_handoff_refuses_an_event_this_tenant_does_not_have(
    engine: Engine, context: _Context, repo: CbaHandoffRepository
) -> None:
    handoff = _accepted_invitation(engine, context)
    with context.session_factory() as session, pytest.raises(UnknownOpportunityEventError):
        repo.reconcile_invitation(
            session,
            tenant_id=context.tenant_id,
            owning_unit_id=context.unit_id,
            opportunity_event_id=uuid.uuid4(),
            invitation_id=handoff.invitation_id,
        )


# ---------------------------------------------------------------------------
# Attendance supplies the Attended stage's evidence
# ---------------------------------------------------------------------------


def test_attendance_supplies_the_attended_stage_and_the_row_cites_it(
    engine: Engine, context: _Context
) -> None:
    handoff = _accepted_invitation(engine, context)
    assert _post_handoff(context, handoff).status_code == 200
    with engine.begin() as conn:
        attendance_id = _insert_attendance(
            conn, context.tenant_id, context.unit_id, handoff.professional_id, context.event_id
        )

    response = _post_handoff(context, handoff, attendance_id=str(attendance_id))

    assert response.status_code == 200, response.text
    stored = _stored_record(engine, context.tenant_id, handoff.professional_id)
    assert stored is not None
    assert stored.attended_at is not None
    assert stored.attended_attendance_id == attendance_id
    assert stored.member_inquiry_at is None
    assert stored.confirmed_at <= stored.attended_at


def test_attendance_at_another_event_cannot_evidence_this_journey(
    engine: Engine, context: _Context, repo: CbaHandoffRepository
) -> None:
    """``ck_pipeline_record_attendance_evidence`` does not check *which* event.

    The constraint makes the citation biconditional -- an Attended row names an
    attendance and an attendance-naming row is Attended -- but nothing in the
    schema requires that attendance to be at the journey's own opportunity. This
    writer checks it, because an Attended stage evidenced by a different event is
    a number no drill-down can reconcile.
    """
    handoff = _accepted_invitation(engine, context)
    assert _post_handoff(context, handoff).status_code == 200
    with engine.begin() as conn:
        other_event = ensure_event(conn, context.tenant_id, "cba-handoff-other")
        wrong = _insert_attendance(
            conn, context.tenant_id, context.unit_id, handoff.professional_id, other_event
        )

    with context.session_factory() as session, pytest.raises(CbaAttendanceMismatchError):
        repo.reconcile_invitation(
            session,
            tenant_id=context.tenant_id,
            owning_unit_id=context.unit_id,
            opportunity_event_id=context.event_id,
            invitation_id=handoff.invitation_id,
            attendance_id=wrong,
        )

    stored = _stored_record(engine, context.tenant_id, handoff.professional_id)
    assert stored is not None and stored.attended_at is None


def test_attendance_by_somebody_else_cannot_evidence_this_journey(
    engine: Engine, context: _Context, repo: CbaHandoffRepository
) -> None:
    handoff = _accepted_invitation(engine, context)
    assert _post_handoff(context, handoff).status_code == 200
    with engine.begin() as conn:
        stranger = _make_user(conn, context.tenant_id)
        wrong = _insert_attendance(
            conn, context.tenant_id, context.unit_id, stranger, context.event_id
        )

    with context.session_factory() as session, pytest.raises(CbaAttendanceMismatchError):
        repo.reconcile_invitation(
            session,
            tenant_id=context.tenant_id,
            owning_unit_id=context.unit_id,
            opportunity_event_id=context.event_id,
            invitation_id=handoff.invitation_id,
            attendance_id=wrong,
        )


def test_attendance_cannot_be_recorded_before_the_speaker_is_confirmed(
    engine: Engine, context: _Context, repo: CbaHandoffRepository
) -> None:
    """The stages are ordered, and the order is not this writer's to skip."""
    handoff = _unanswered_invitation(engine, context, name="Ari Blum")
    with engine.begin() as conn:
        attendance_id = _insert_attendance(
            conn, context.tenant_id, context.unit_id, handoff.professional_id, context.event_id
        )

    with context.session_factory() as session, pytest.raises(CbaInvitationNotConfirmedError):
        repo.reconcile_invitation(
            session,
            tenant_id=context.tenant_id,
            owning_unit_id=context.unit_id,
            opportunity_event_id=context.event_id,
            invitation_id=handoff.invitation_id,
            attendance_id=attendance_id,
        )

    assert _stored_record(engine, context.tenant_id, handoff.professional_id) is None


# ---------------------------------------------------------------------------
# No CBA member_inquiry is ever written, and none is displayed
# ---------------------------------------------------------------------------


def test_member_inquiry_is_excluded_from_the_cba_funnel() -> None:
    assert frozenset({PipelineStage.MEMBER_INQUIRY}) == CBA_EXCLUDED_STAGES
    assert PipelineStage.MEMBER_INQUIRY not in CBA_STAGE_SEQUENCE
    assert CBA_STAGE_SEQUENCE == (
        PipelineStage.MATCHED,
        PipelineStage.CONTACTED,
        PipelineStage.CONFIRMED,
        PipelineStage.ATTENDED,
    )
    # The stage itself is preserved: still a member of the whole funnel.
    assert PipelineStage("member_inquiry") is PipelineStage.MEMBER_INQUIRY


def test_the_cba_writer_refuses_member_inquiry_outright(
    engine: Engine, context: _Context, repo: CbaHandoffRepository
) -> None:
    handoff = _accepted_invitation(engine, context)
    record_id = uuid.UUID(_post_handoff(context, handoff).json()["speaker"]["record_id"])

    with context.session_factory() as session, pytest.raises(MemberInquiryExcludedError):
        repo.advance_cba_stage(
            session,
            tenant_id=context.tenant_id,
            record_id=record_id,
            stage=PipelineStage.MEMBER_INQUIRY,
            reached_at=datetime.now(UTC),
        )


def test_a_fully_attended_cba_journey_still_has_no_member_inquiry(
    engine: Engine, context: _Context
) -> None:
    handoff = _accepted_invitation(engine, context)
    assert _post_handoff(context, handoff).status_code == 200
    with engine.begin() as conn:
        attendance_id = _insert_attendance(
            conn, context.tenant_id, context.unit_id, handoff.professional_id, context.event_id
        )
    assert _post_handoff(context, handoff, attendance_id=str(attendance_id)).status_code == 200

    with engine.begin() as conn:
        member_inquiries = conn.execute(
            text(
                "SELECT count(*) FROM pipeline_record "
                "WHERE tenant_id = :tid AND member_inquiry_at IS NOT NULL"
            ),
            {"tid": context.tenant_id},
        ).scalar_one()
    assert member_inquiries == 0


def test_the_cba_metric_surface_offers_no_member_inquiry_tile(
    engine: Engine, context: _Context
) -> None:
    """The display half of the exclusion, on the server rather than the browser."""
    handoff = _accepted_invitation(engine, context)
    assert _post_handoff(context, handoff).status_code == 200

    cba = _get(context, f"/v1/units/{context.unit_id}/metrics?surface=cba").json()
    names = [metric["name"] for metric in cba["metrics"]]
    assert "pipeline_member_inquiry" not in names
    assert "pipeline_confirmed" in names

    # The whole register is still there for a caller that asks for it -- the
    # stage's history is preserved, not deleted.
    every = _get(context, f"/v1/units/{context.unit_id}/metrics").json()
    assert "pipeline_member_inquiry" in [metric["name"] for metric in every["metrics"]]


def test_the_cba_surface_refuses_to_drill_into_member_inquiry(context: _Context) -> None:
    drill_down = f"/v1/units/{context.unit_id}/metrics/pipeline_member_inquiry/drill-down"

    assert _get(context, f"{drill_down}?surface=cba").status_code == 404
    assert _get(context, drill_down).status_code == 200


# ---------------------------------------------------------------------------
# The Event Host handoff: reading the confirmed speaker back
# ---------------------------------------------------------------------------


def test_the_host_reads_the_confirmed_speaker_for_their_event(
    engine: Engine, context: _Context
) -> None:
    handoff = _accepted_invitation(engine, context, name="Dana Reyes")
    assert _post_handoff(context, handoff).status_code == 200

    body = _get(
        context, f"/v1/units/{context.unit_id}/cba/confirmed-speakers?event_id={context.event_id}"
    ).json()

    assert [speaker["professional_id"] for speaker in body["speakers"]] == [
        str(handoff.professional_id)
    ]
    speaker = body["speakers"][0]
    assert speaker["full_name"] == "Dana Reyes"
    assert speaker["confirmed_at"] is not None
    assert speaker["event_id"] == str(context.event_id)
    assert "member_inquiry_at" not in speaker


def test_the_host_list_omits_a_speaker_who_has_not_confirmed(
    engine: Engine, context: _Context
) -> None:
    confirmed = _accepted_invitation(engine, context, name="Dana Reyes")
    assert _post_handoff(context, confirmed).status_code == 200
    _unanswered_invitation(engine, context, name="Not Yet")

    body = _get(context, f"/v1/units/{context.unit_id}/cba/confirmed-speakers").json()

    assert [speaker["professional_id"] for speaker in body["speakers"]] == [
        str(confirmed.professional_id)
    ]


# ---------------------------------------------------------------------------
# ADR-0011 rule 3: aggregate == drill-down == the Host list
# ---------------------------------------------------------------------------


def test_the_confirmed_aggregate_equals_its_drill_down_and_the_host_list(
    engine: Engine, context: _Context
) -> None:
    """Three numbers, compared, not three code paths read.

    The aggregate the dashboard shows, the rows a coordinator drills into, and
    the speakers the Event Host is handed must be the same set. This writes three
    confirmed journeys and one that stops short of Confirmed, so a filter that
    quietly widened would show up as a mismatch rather than as a plausible
    number.
    """
    confirmed_ids = []
    for index in range(3):
        handoff = _accepted_invitation(engine, context, name=f"Speaker {index}")
        assert _post_handoff(context, handoff).status_code == 200
        confirmed_ids.append(handoff.professional_id)
    _unanswered_invitation(engine, context, name="Unanswered")

    aggregate = _get(context, f"/v1/units/{context.unit_id}/metrics?surface=cba").json()
    confirmed = next(m for m in aggregate["metrics"] if m["name"] == "pipeline_confirmed")
    drill_down = _get(
        context, f"/v1/units/{context.unit_id}/metrics/pipeline_confirmed/drill-down?surface=cba"
    ).json()
    host_list = _get(context, f"/v1/units/{context.unit_id}/cba/confirmed-speakers").json()

    assert confirmed["value"] == 3
    assert confirmed["value"] == len(drill_down["rows"]) == len(host_list["speakers"])
    assert drill_down["aggregate_value"] == confirmed["value"]
    # The same three journeys, not merely the same count.
    assert {row["subject_id"] for row in drill_down["rows"]} == {str(pid) for pid in confirmed_ids}
    assert {speaker["professional_id"] for speaker in host_list["speakers"]} == {
        str(pid) for pid in confirmed_ids
    }
