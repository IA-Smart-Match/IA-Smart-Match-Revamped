"""Focused no-database contracts for manual events and feedback QR redirects."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from smartmatch_api.errors import ApiError
from smartmatch_api.routers import events
from smartmatch_persistence import schema
from smartmatch_persistence.events import EventRepository
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
    assert events.FeedbackQrRequest(destination_url=destination).destination_url == destination


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
        events.FeedbackQrRequest(destination_url=destination)


def test_event_schedule_requires_named_zone_and_aware_instant() -> None:
    with pytest.raises(ValidationError):
        events.EventWrite(
            title="Volunteer fair",
            time_precision="exact",
            starts_at=datetime(2026, 10, 2, 9, 0),
            time_zone="America/Los_Angeles",
        )

    result = events.EventWrite(
        title="Volunteer fair",
        time_precision="exact",
        starts_at=datetime(2026, 10, 2, 16, 0, tzinfo=UTC),
        time_zone="America/Los_Angeles",
    )
    assert result.title == "Volunteer fair"


def test_manual_event_schema_is_unit_scoped_and_qr_opens_store_no_visitor_data() -> None:
    assert {"tenant_id", "owning_unit_id", "created_by"} <= set(schema.event.c.keys())
    assert {"id", "tenant_id", "qr_id", "opened_at"} == set(
        schema.event_feedback_qr_open.c.keys()
    )
    assert {"ip", "user_agent", "referrer", "cookie"}.isdisjoint(
        schema.event_feedback_qr_open.c.keys()
    )


def test_legacy_event_foreign_keys_are_added_without_validating_orphans() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "db"
        / "migrations"
        / "versions"
        / "0016_manual_events.py"
    ).read_text(encoding="utf-8")
    assert migration.count("NOT VALID") >= 2
    assert "fk_attendance_record_event" in migration
    assert "fk_pipeline_record_event" in migration


def test_qr_destination_update_does_not_rotate_the_public_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements = []

    class Session:
        def execute(self, statement):
            statements.append(statement)

    repository = EventRepository()
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


def test_inactive_public_qr_is_not_disclosed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(events._events, "record_open", lambda _session, *, public_token: None)
    with pytest.raises(ApiError) as captured:
        events.open_feedback_qr(object(), "opaque-token-that-does-not-exist")
    assert captured.value.status_code == 404


def test_published_qr_redirect_has_privacy_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    class Session:
        committed = False

        def commit(self) -> None:
            self.committed = True

    session = Session()
    destination = "https://forms.example.edu/feedback?event=42#questions"
    monkeypatch.setattr(
        events._events,
        "record_open",
        lambda _session, *, public_token: destination,
    )
    response = events.open_feedback_qr(session, "opaque-published-feedback-token")
    assert response.status_code == 302
    assert response.headers["location"] == destination
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert session.committed is True
