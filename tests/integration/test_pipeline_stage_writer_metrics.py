"""The funnel's last three metrics go non-zero because of the stage-advance routes.

``docs/plans/2026-09-05-pipeline-stage-writers-plan.md`` §4. This is the claim
the slice actually makes, and no other test in this repository makes it:
``pipeline_confirmed``, ``pipeline_attended`` and ``pipeline_member_inquiry``
can be **non-zero from a deployed HTTP path** that a coordinator can reach.

``test_pipeline_funnel_end_to_end.py`` proves the same three stages can move,
but it moves them with ``tools.seed_demo_pipeline`` — a developer entry point
that walks synthetic journeys in bulk. That leaves the operator question open:
can a coordinator, with a token and a browser, record that one journey reached
Confirmed? Until this branch the answer was no, and the three metrics were
measuring an unreachable stage rather than an unattained one.

**Why the numbers are read back through the metrics route and nowhere else.**
Asserting on ``PipelineRepository.get(...)`` after driving the advance would
prove the repository agrees with itself: the metrics binding could be broken,
unreachable, or never wired to this data and such a test would still pass. That
is ADR-0011 rule 4's reasoning, and it is why the assertions below go through
``GET /v1/units/{unit_id}/metrics`` — the same read a stakeholder gets.

**What is seeded rather than driven, and why.** Matched and Contacted are
inserted directly. Neither is writable by the routes under test, deliberately:
Matched is opened by ``record_matched`` when a journey is created, and Contacted
is the outreach worker's own consequence of a provider accepting custody of a
message. Seeding them is the honest way to start a journey at the point this
slice picks it up; reaching them through the new route would be testing a rule
``routers/pipeline.py`` exists to refuse.

Requires a live database, and is skipped when none is reachable (the ``engine``
fixture in ``tests/integration/conftest.py``).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

pytest.importorskip("sqlalchemy")

from conftest import JOB_OWNING_UNIT_PATH, ensure_owning_unit, unique_subject
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from test_review_accept_opens_pipeline import _get, _make_client, _register_coordinator

pytestmark = pytest.mark.integration

#: ``MATCH_PROVENANCE_SYNTHETIC_COORDINATOR``. Spelled rather than imported so a
#: seeded row is visibly synthetic in the SQL that creates it.
SYNTHETIC_PROVENANCE = "synthetic / coordinator-accepted"

BASE = datetime(2026, 6, 12, 15, 0, tzinfo=UTC)
MATCHED_AT = BASE
CONTACTED_AT = BASE + timedelta(hours=1)
CONFIRMED_AT = BASE + timedelta(hours=2)
ATTENDED_AT = BASE + timedelta(hours=3)
INQUIRY_AT = BASE + timedelta(hours=4)

#: The three stages this slice made reachable, paired with the metric each one
#: is supposed to move. Restated as a local literal rather than derived from
#: `PIPELINE_STAGE_SEQUENCE`, so a reordering upstream shows up here as a
#: failing assertion rather than silently reordering this file's own checks —
#: the same reasoning `test_pipeline_funnel_end_to_end.py` gives.
WRITABLE_STAGES: tuple[tuple[str, str], ...] = (
    ("confirmed", "pipeline_confirmed"),
    ("attended", "pipeline_attended"),
    ("member_inquiry", "pipeline_member_inquiry"),
)


def _delete_this_files_rows(engine: Engine, tenant_id: uuid.UUID) -> None:
    """Child-first: `pipeline_record` cites `attendance_record`, which cites `event`.

    None of the three is in `conftest.py`'s `_TENANT_SCOPED_TABLES`, and all
    carry `ON DELETE RESTRICT` back to `org_unit` / `user_account` — the same
    arrangement `test_pipeline_funnel_end_to_end.py` cleans up for the same
    reason.
    """
    with engine.begin() as conn:
        for table in ("pipeline_record", "attendance_record", "event"):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})


@pytest.fixture(autouse=True)
def _clean_rows(engine: Engine, tenant_id: uuid.UUID) -> Iterator[None]:
    """Delete before and after, so a run killed mid-test cannot corrupt a re-run's counts."""
    _delete_this_files_rows(engine, tenant_id)
    yield
    _delete_this_files_rows(engine, tenant_id)


@dataclass(frozen=True, slots=True)
class _Context:
    client: TestClient
    engine: Engine
    tenant_id: uuid.UUID
    unit_id: uuid.UUID
    token: str
    record_id: uuid.UUID
    attendance_id: uuid.UUID


@pytest.fixture
def ctx(engine: Engine, tenant_id: uuid.UUID) -> _Context:
    """One coordinator and one journey sitting where the outreach worker leaves it."""
    client = _make_client(engine)
    token, _ = _register_coordinator(engine, client, tenant_id, JOB_OWNING_UNIT_PATH)

    student_id = uuid.uuid4()
    event_id = uuid.uuid4()
    attendance_id = uuid.uuid4()
    record_id = uuid.uuid4()

    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
        subject = unique_subject("sub-pipeline-stage-student")
        conn.execute(
            text(
                "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                "VALUES (:id, :tid, :subject, :email)"
            ),
            {
                "id": student_id,
                "tid": tenant_id,
                "subject": subject,
                "email": f"{subject}@example.edu",
            },
        )
        conn.execute(
            text(
                "INSERT INTO event (id, tenant_id, host_org_unit_id, title, "
                "normalized_title, time_precision, origin) "
                "VALUES (:id, :tid, :unit, :title, :normalized, 'unresolved', "
                "'coordinator_entry')"
            ),
            {
                "id": event_id,
                "tid": tenant_id,
                "unit": unit_id,
                "title": f"Synthetic Showcase {event_id}",
                "normalized": f"synthetic showcase {event_id}",
            },
        )
        # The evidence the Attended stage will cite. Written here because
        # nothing in this slice writes attendance — see OQ-102.
        conn.execute(
            text(
                "INSERT INTO attendance_record "
                "(id, tenant_id, owning_unit_id, subject_id, event_id, method) "
                "VALUES (:id, :tid, :unit, :subject, :event, 'qr_scan')"
            ),
            {
                "id": attendance_id,
                "tid": tenant_id,
                "unit": unit_id,
                "subject": student_id,
                "event": event_id,
            },
        )
        conn.execute(
            text(
                "INSERT INTO pipeline_record (id, tenant_id, owning_unit_id, subject_id, "
                "opportunity_event_id, matched_at, matched_provenance, contacted_at) "
                "VALUES (:id, :tid, :unit, :subject, :event, :matched, :prov, :contacted)"
            ),
            {
                "id": record_id,
                "tid": tenant_id,
                "unit": unit_id,
                "subject": student_id,
                "event": event_id,
                "matched": MATCHED_AT,
                "prov": SYNTHETIC_PROVENANCE,
                "contacted": CONTACTED_AT,
            },
        )

    return _Context(
        client=client,
        engine=engine,
        tenant_id=tenant_id,
        unit_id=unit_id,
        token=token,
        record_id=record_id,
        attendance_id=attendance_id,
    )


def _metrics_by_name(ctx: _Context) -> dict[str, dict[str, Any]]:
    response = _get(ctx.client, f"/v1/units/{ctx.unit_id}/metrics", ctx.token)
    assert response.status_code == 200, response.text
    return {item["name"]: item for item in response.json()["metrics"]}


def _advance(ctx: _Context, stage: str, reached_at: datetime, **extra: object):
    body: dict[str, object] = {"stage": stage, "reached_at": reached_at.isoformat()}
    body.update(extra)
    return ctx.client.post(
        f"/v1/units/{ctx.unit_id}/pipeline-records/{ctx.record_id}/stages",
        json=body,
        headers={"Authorization": f"Bearer {ctx.token}"},
    )


def test_the_stage_routes_move_the_last_three_funnel_metrics(ctx: _Context) -> None:
    """The whole claim, walked once: seeded journey in, non-zero metrics out."""
    # ---- Before: a measured zero, not an unknown ---------------------------
    before = _metrics_by_name(ctx)
    assert before["pipeline_matched"]["value"] == 1
    assert before["pipeline_contacted"]["value"] == 1
    for _stage, metric in WRITABLE_STAGES:
        assert before[metric]["value"] == 0, metric
        # ADR-0011: the table was read and it held nothing. That is a
        # measurement, and it is the state this slice is here to change.
        assert before[metric]["unknown_reason"] is None, metric

    # ---- The three advances, over HTTP, as a coordinator would --------------
    assert _advance(ctx, "confirmed", CONFIRMED_AT).status_code == 200
    attended = _advance(ctx, "attended", ATTENDED_AT, attendance_id=str(ctx.attendance_id))
    assert attended.status_code == 200, attended.text
    assert _advance(ctx, "member_inquiry", INQUIRY_AT).status_code == 200

    # ---- After: read back through the metrics route, never the repository --
    after = _metrics_by_name(ctx)
    for _stage, metric in WRITABLE_STAGES:
        assert after[metric]["value"] == 1, metric
        assert after[metric]["unknown_reason"] is None, metric

    # The stages before the ones this slice writes are untouched: advancing a
    # journey does not re-count it at an earlier stage, and the funnel stays
    # the shape a coordinator expects (1/1/1/1/1 for one completed journey).
    assert after["pipeline_matched"]["value"] == 1
    assert after["pipeline_contacted"]["value"] == 1


def test_a_journey_that_stops_partway_leaves_the_later_metrics_at_zero(ctx: _Context) -> None:
    """A funnel that only ever goes up is not a funnel.

    Advancing to Confirmed and stopping must move exactly one metric. If
    Attended moved too, the number would be counting journeys that had reached
    *some* stage rather than the stage it names.
    """
    assert _advance(ctx, "confirmed", CONFIRMED_AT).status_code == 200

    metrics = _metrics_by_name(ctx)
    assert metrics["pipeline_confirmed"]["value"] == 1
    assert metrics["pipeline_attended"]["value"] == 0
    assert metrics["pipeline_member_inquiry"]["value"] == 0


def test_a_refused_advance_moves_no_metric(ctx: _Context) -> None:
    """The 409 paths are not partial writes.

    Skipping Confirmed is refused, and the funnel afterwards is exactly the
    funnel before — the failure mode that would matter most here is a route
    that refuses the caller and writes the row anyway.
    """
    refused = _advance(ctx, "attended", ATTENDED_AT, attendance_id=str(ctx.attendance_id))
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "pipeline_stage_prerequisite_unmet"

    metrics = _metrics_by_name(ctx)
    for _stage, metric in WRITABLE_STAGES:
        assert metrics[metric]["value"] == 0, metric


def test_repeating_the_advance_does_not_double_count(ctx: _Context) -> None:
    """One journey is one row, however many times a coordinator asserts the stage.

    The route has no ``Idempotency-Key`` — this is what stands in for one, and
    the metric is where a double write would actually show up.
    """
    assert _advance(ctx, "confirmed", CONFIRMED_AT).status_code == 200
    repeat = _advance(ctx, "confirmed", CONFIRMED_AT)
    assert repeat.status_code == 200
    assert repeat.json()["transitioned"] is False
    assert repeat.json()["already_reached"] is True

    assert _metrics_by_name(ctx)["pipeline_confirmed"]["value"] == 1
