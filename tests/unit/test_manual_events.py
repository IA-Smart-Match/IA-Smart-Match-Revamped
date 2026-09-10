"""No-database contracts for manual events and the feedback QR redirect.

Mirrors the validation and repository-logic tests PR #125 shipped for its own
``managed_event`` design (``git show origin/frontend-dev:tests/unit/test_manual_events.py``),
adapted to this port's design: manual events are rows in the canonical
``event`` table, and the side tables are ``event_manual_detail`` /
``event_feedback_qr`` / ``event_feedback_qr_open``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError
from smartmatch_api.errors import ApiError
from smartmatch_api.routers import manual_events
from smartmatch_persistence import schema
from smartmatch_persistence.manual_events import ManualEventDetailRepository
from sqlalchemy.dialects import postgresql


@pytest.mark.parametrize(
    "destination",
    [
        "https://forms.office.com/r/example?origin=QRCode#feedback",
        "https://docs.google.com/forms/d/e/example/viewform?usp=sharing",
        "https://feedback.example.edu:8443/event?id=42",
    ],
)
def test_feedback_destination_accepts_external_https_urls(destination: str) -> None:
    assert (
        manual_events.FeedbackQrRequest(destination_url=destination).destination_url == destination
    )


@pytest.mark.parametrize(
    "destination",
    [
        "http://forms.example.edu/feedback",
        "https://localhost/feedback",
        "https://127.0.0.1/feedback",
        "https://[::1]/feedback",
        "https://user:password@forms.example.edu/feedback",
        "https://intranet/feedback",
        "https://bad..example.edu/feedback",
        "https://forms.example.edu/feedback\nsecond-line",
    ],
)
def test_feedback_destination_rejects_unsafe_urls(destination: str) -> None:
    with pytest.raises(ValidationError):
        manual_events.FeedbackQrRequest(destination_url=destination)


def test_event_schedule_requires_named_zone_and_aware_instant() -> None:
    with pytest.raises(ValidationError):
        manual_events.EventWrite(
            title="Volunteer fair",
            time_precision="exact",
            starts_at=datetime(2026, 10, 2, 9, 0),
            time_zone="America/Los_Angeles",
        )

    result = manual_events.EventWrite(
        title="Volunteer fair",
        time_precision="exact",
        starts_at=datetime(2026, 10, 2, 16, 0, tzinfo=UTC),
        time_zone="America/Los_Angeles",
    )
    assert result.title == "Volunteer fair"


def test_date_only_event_rejects_a_clock_time() -> None:
    with pytest.raises(ValidationError):
        manual_events.EventWrite(
            title="Hackathon",
            time_precision="date_only",
            starts_at=datetime(2026, 10, 2, 9, 0, tzinfo=UTC),
            time_zone="America/Los_Angeles",
        )


def test_unresolved_event_rejects_a_date() -> None:
    with pytest.raises(ValidationError):
        manual_events.EventWrite(
            title="Hackathon", time_precision="unresolved", on_date=date(2026, 10, 2)
        )


def test_volunteer_openings_cannot_exceed_capacity() -> None:
    with pytest.raises(ValidationError):
        manual_events.EventWrite(title="Fair", capacity=5, volunteer_openings=6)


def test_category_must_be_approved() -> None:
    with pytest.raises(ValidationError):
        manual_events.EventWrite(title="Fair", category="not a real category")

    assert manual_events.EventWrite(title="Fair", category="Hackathon").category == "hackathon"


def test_manual_event_side_tables_are_unit_scoped_and_qr_opens_store_no_visitor_data() -> None:
    assert {"tenant_id", "owning_unit_id", "event_id"} <= set(schema.event_manual_detail.c.keys())
    assert {"id", "tenant_id", "qr_id", "opened_at"} == set(schema.event_feedback_qr_open.c.keys())
    assert {"ip", "user_agent", "referrer", "cookie"}.isdisjoint(
        schema.event_feedback_qr_open.c.keys()
    )


def test_manual_events_reuse_the_existing_coordinator_entry_origin() -> None:
    """There is no new ``event.origin`` value: ``coordinator_entry`` already
    means "a person typed this event in" (migration 0017), which is exactly
    what a manually filed event is."""
    from smartmatch_persistence.events import ORIGIN_COORDINATOR_ENTRY

    assert ORIGIN_COORDINATOR_ENTRY == "coordinator_entry" == manual_events.ORIGIN_COORDINATOR_ENTRY


def test_no_managed_event_table_exists() -> None:
    assert not hasattr(schema, "managed_event")


def test_qr_destination_update_does_not_rotate_the_public_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements = []

    class Session:
        def execute(self, statement):
            statements.append(statement)

    repository = ManualEventDetailRepository()
    monkeypatch.setattr(
        repository,
        "get_qr",
        lambda _session, *, tenant_id, event_id: {
            "tenant_id": tenant_id,
            "event_id": event_id,
        },
    )
    repository.upsert_qr(
        Session(),
        tenant_id=uuid4(),
        unit_id=uuid4(),
        event_id=uuid4(),
        actor_id=uuid4(),
        destination_url="https://forms.example.edu/new-destination",
    )
    sql = str(statements[0].compile(dialect=postgresql.dialect()))
    update_clause = sql.split("DO UPDATE SET", 1)[1]
    assert "destination_url" in update_clause
    assert "public_token" not in update_clause


def test_feedback_qr_constraint_name_matches_the_repository() -> None:
    from pathlib import Path

    migration = (
        Path(__file__).resolve().parents[2]
        / "db"
        / "migrations"
        / "versions"
        / "0035_manual_event_detail.py"
    ).read_text(encoding="utf-8")
    repository = (
        Path(__file__).resolve().parents[2]
        / "python"
        / "smartmatch_persistence"
        / "smartmatch_persistence"
        / "manual_events.py"
    ).read_text(encoding="utf-8")
    assert 'name="uq_event_feedback_qr_event"' in migration
    assert 'constraint="uq_event_feedback_qr_event"' in repository


def test_manual_event_detail_migration_revises_the_cba_meeting_head() -> None:
    from pathlib import Path

    migration = (
        Path(__file__).resolve().parents[2]
        / "db"
        / "migrations"
        / "versions"
        / "0035_manual_event_detail.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision = "0034_cba_meeting"' in migration
    assert '"managed_event"' not in migration


def test_inactive_public_qr_is_not_disclosed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        manual_events._details, "record_open", lambda _session, *, public_token: None
    )
    with pytest.raises(ApiError) as captured:
        manual_events.open_feedback_qr(object(), "opaque-token-that-does-not-exist-000")
    assert captured.value.status_code == 404


def test_published_qr_redirect_has_privacy_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    class Session:
        committed = False

        def commit(self) -> None:
            self.committed = True

    session = Session()
    destination = "https://forms.example.edu/feedback?event=42#questions"
    monkeypatch.setattr(
        manual_events._details,
        "record_open",
        lambda _session, *, public_token: destination,
    )
    response = manual_events.open_feedback_qr(session, "opaque-published-feedback-token-000")
    assert response.status_code == 302
    assert response.headers["location"] == destination
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert session.committed is True


def test_short_public_token_is_refused_before_any_query(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def _fail(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(manual_events._details, "record_open", _fail)
    with pytest.raises(ApiError) as captured:
        manual_events.open_feedback_qr(object(), "short")
    assert captured.value.status_code == 404
    assert called is False
