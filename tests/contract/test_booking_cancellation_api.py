"""HTTP contract for ``POST …/pipeline-records/{id}/cancellation`` (B26 T8a).

A Speaker booking is a ``pipeline_record`` that reached Confirmed. Cancelling it
is a transition on that row (migration ``0040``): who and when are recorded, the
row is kept, and a repeat is a ``200`` that changes nothing. The three refusals
are ``409`` because the request is valid and the row's state refuses it.

Fixtures come from ``test_pipeline_stages.py`` (one tenant, one coordinator, a
journey at Contacted in the unit and one in a sibling unit). Requires a migrated
PostgreSQL; skipped otherwise.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import test_pipeline_stages as stages
from sqlalchemy import text
from test_pipeline_stages import ATTENDED_AT, CONFIRMED_AT, _Context

#: The fixtures, re-exported so pytest finds them in this module.
engine = stages.engine
ctx = stages.ctx

pytestmark = pytest.mark.integration


def _cancel(ctx: _Context, *, unit_id: uuid.UUID | None = None, record_id=None, auth=True):
    unit = ctx.unit_id if unit_id is None else unit_id
    record = ctx.record_id if record_id is None else record_id
    return ctx.client.post(
        f"/v1/units/{unit}/pipeline-records/{record}/cancellation",
        headers=ctx.headers() if auth else {},
    )


def _coordinator_id(ctx: _Context) -> uuid.UUID:
    with ctx.engine.begin() as conn:
        return conn.execute(
            text("SELECT user_id FROM membership WHERE tenant_id = :tid"),
            {"tid": ctx.tenant_id},
        ).scalar_one()


def _stored(ctx: _Context, record_id: uuid.UUID | None = None):
    with ctx.engine.begin() as conn:
        return conn.execute(
            text(
                "SELECT cancelled_at, cancelled_by_user_id, attended_at "
                "FROM pipeline_record WHERE id = :id"
            ),
            {"id": ctx.record_id if record_id is None else record_id},
        ).one()


def _confirm(ctx: _Context, at: datetime = CONFIRMED_AT) -> None:
    response = ctx.advance("confirmed", at)
    assert response.status_code == 200, response.text


def _quota_count(ctx: _Context) -> int:
    with ctx.engine.begin() as conn:
        return conn.execute(
            text(
                "SELECT coalesce(sum(count), 0) FROM rate_limit_counter "
                "WHERE tenant_id = :tid AND operation = 'pipeline.booking_cancel'"
            ),
            {"tid": ctx.tenant_id},
        ).scalar_one()


def test_cancelling_a_confirmed_booking_returns_who_and_when(ctx: _Context) -> None:
    _confirm(ctx)
    before = datetime.now(UTC)

    response = _cancel(ctx)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["transitioned"] is True
    assert body["already_cancelled"] is False
    coordinator = _coordinator_id(ctx)
    assert body["record"]["cancelled_by_user_id"] == str(coordinator)
    stored = _stored(ctx)
    assert stored.cancelled_by_user_id == coordinator
    assert before - timedelta(seconds=5) <= stored.cancelled_at <= datetime.now(UTC)
    assert datetime.fromisoformat(body["record"]["cancelled_at"]) == stored.cancelled_at
    assert body["record"]["current_stage"] == "confirmed"


def test_repeating_a_cancellation_is_200_and_changes_nothing(ctx: _Context) -> None:
    _confirm(ctx)
    assert _cancel(ctx).status_code == 200
    first = _stored(ctx)

    again = _cancel(ctx)

    assert again.status_code == 200
    assert again.json()["transitioned"] is False
    assert again.json()["already_cancelled"] is True
    assert _stored(ctx) == first


def test_cancelling_an_unconfirmed_journey_is_409(ctx: _Context) -> None:
    response = _cancel(ctx)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "pipeline_booking_not_confirmed"
    assert _stored(ctx).cancelled_at is None


def test_cancelling_an_attended_booking_is_409(ctx: _Context) -> None:
    _confirm(ctx)
    attended = ctx.advance("attended", ATTENDED_AT, attendance_id=str(ctx.attendance_id))
    assert attended.status_code == 200, attended.text

    response = _cancel(ctx)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "pipeline_booking_already_attended"
    assert _stored(ctx).cancelled_at is None


def test_cancelling_a_future_confirmed_booking_is_409(ctx: _Context) -> None:
    _confirm(ctx, datetime.now(UTC) + timedelta(days=2))

    response = _cancel(ctx)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "pipeline_booking_confirmed_in_future"
    assert _stored(ctx).cancelled_at is None


def test_a_record_in_a_sibling_unit_is_a_404_not_a_403(ctx: _Context) -> None:
    response = _cancel(ctx, record_id=ctx.sibling_record_id)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "pipeline_record_not_found"


def test_an_unknown_record_is_the_same_404(ctx: _Context) -> None:
    response = _cancel(ctx, record_id=uuid.uuid4())
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "pipeline_record_not_found"


def test_a_coordinator_without_the_unit_is_refused(ctx: _Context) -> None:
    response = _cancel(ctx, unit_id=ctx.sibling_unit_id, record_id=ctx.sibling_record_id)
    assert response.status_code == 403
    assert _stored(ctx, ctx.sibling_record_id).cancelled_at is None


def test_an_unauthenticated_caller_writes_nothing(ctx: _Context) -> None:
    _confirm(ctx)
    response = _cancel(ctx, auth=False)
    assert response.status_code == 401
    assert _stored(ctx).cancelled_at is None


def test_quota_is_charged_before_the_404(ctx: _Context) -> None:
    """ADR-0015: ``charge_quota`` runs first, so a refusal still costs a request."""
    assert _quota_count(ctx) == 0
    assert _cancel(ctx, record_id=uuid.uuid4()).status_code == 404
    assert _quota_count(ctx) == 1


def test_attended_on_a_cancelled_booking_is_409_on_the_stages_route(ctx: _Context) -> None:
    _confirm(ctx)
    assert _cancel(ctx).status_code == 200

    response = ctx.advance("attended", ATTENDED_AT, attendance_id=str(ctx.attendance_id))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "pipeline_record_cancelled"
    assert _stored(ctx).attended_at is None


def test_the_read_route_carries_cancelled_fields(ctx: _Context) -> None:
    live = ctx.read().json()
    assert live["cancelled_at"] is None
    assert live["cancelled_by_user_id"] is None

    _confirm(ctx)
    assert _cancel(ctx).status_code == 200

    body = ctx.read().json()
    assert body["cancelled_at"] is not None
    assert body["cancelled_by_user_id"] == str(_coordinator_id(ctx))
