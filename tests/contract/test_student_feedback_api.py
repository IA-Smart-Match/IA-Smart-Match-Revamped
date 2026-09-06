"""HTTP contracts for student-to-speaker feedback (OQ-CBA-003).

The persistence suite owns the table and eligibility constraints.  These tests
hold the guarantees that exist only at the HTTP boundary: the student's id is
always taken from the verified principal, responses never expose that id, and
the Connector receives an aggregate rather than individual ratings or comments.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.dependencies import get_current_principal, get_session
from smartmatch_api.main import app
from smartmatch_api.routers import student_speaker_feedback as routes
from smartmatch_authz import Principal
from smartmatch_domain.student_speaker_feedback import EditWindow, EditWindowState
from smartmatch_persistence.principals import ResolvedPrincipal
from smartmatch_persistence.student_speaker_feedback import (
    FeedbackRow,
    FeedbackWriteResult,
)


class _Session:
    """The only session behaviour these route contracts need to observe."""

    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


class _FeedbackRepository:
    def __init__(self, row: FeedbackRow) -> None:
        self.row = row
        self.submission: dict[str, Any] | None = None
        self.ratings: list[int] = []

    def submit(self, _session: object, **values: Any) -> FeedbackWriteResult:
        self.submission = values
        return FeedbackWriteResult(row=self.row, created=True, changed=True)

    def submitted_ratings(self, _session: object, **_values: Any) -> list[int]:
        return self.ratings

    def speaker_on_roster(self, _session: object, **_values: Any) -> bool:
        return True


@pytest.fixture
def http(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, _FeedbackRepository, _Session, ResolvedPrincipal]]:
    tenant_id = uuid.uuid4()
    student_id = uuid.uuid4()
    speaker_id = uuid.uuid4()
    now = datetime(2026, 9, 6, 12, tzinfo=UTC)
    principal = ResolvedPrincipal(
        principal=Principal(user_id=str(student_id), tenant_id=str(tenant_id)),
        user_id=student_id,
        tenant_id=tenant_id,
        email="student@example.invalid",
    )
    session = _Session()
    repository = _FeedbackRepository(
        FeedbackRow(
            id=uuid.uuid4(),
            event_id=uuid.uuid4(),
            student_id=student_id,
            speaker_professional_id=speaker_id,
            status="submitted",
            rating=5,
            comment="Clear and useful",
            submitted_at=now,
            updated_at=now,
        )
    )

    def _session_override() -> Iterator[_Session]:
        yield session

    app.dependency_overrides[get_current_principal] = lambda: principal
    app.dependency_overrides[get_session] = _session_override
    monkeypatch.setattr(routes, "_feedback", repository)
    monkeypatch.setattr(routes, "charge_quota", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(routes, "_authorize_student_feedback_write", lambda *_args: None)
    monkeypatch.setattr(routes, "_authorize_speaker_feedback_summary_read", lambda *_args: None)
    monkeypatch.setattr(
        routes,
        "_require_eligible_and_open",
        lambda *_args, **_kwargs: EditWindow(
            state=EditWindowState.OPEN,
            closes_at=datetime(2026, 9, 13, 12, tzinfo=UTC),
        ),
    )

    try:
        with TestClient(app) as client:
            yield client, repository, session, principal
    finally:
        app.dependency_overrides.clear()


def test_submission_uses_verified_student_and_returns_no_student_id(http) -> None:
    client, repository, session, principal = http
    unit_id = uuid.uuid4()
    event_id = repository.row.event_id
    speaker_id = repository.row.speaker_professional_id
    attacker_chosen_id = uuid.uuid4()

    response = client.post(
        f"/v1/units/{unit_id}/student/events/{event_id}/speakers/{speaker_id}/feedback",
        json={
            "rating": 5,
            "comment": " Clear and useful ",
            "student_id": str(attacker_chosen_id),
        },
    )

    assert response.status_code == 201
    assert repository.submission is not None
    assert repository.submission["student_id"] == principal.user_id
    assert repository.submission["student_id"] != attacker_chosen_id
    assert session.commits == 1
    body = response.json()
    assert "student_id" not in body
    assert "student_id" not in body["feedback"]
    assert body["feedback"]["rating"] == 5
    assert body["changed"] is True


@pytest.mark.parametrize("rating", [0, 6])
def test_submission_rejects_values_outside_the_approved_scale(http, rating: int) -> None:
    client, repository, session, _principal = http
    response = client.post(
        "/v1/units/"
        f"{uuid.uuid4()}/student/events/{repository.row.event_id}/speakers/"
        f"{repository.row.speaker_professional_id}/feedback",
        json={"rating": rating},
    )

    assert response.status_code == 422
    assert repository.submission is None
    assert session.commits == 0


@pytest.mark.parametrize(
    ("ratings", "suppressed", "count", "mean"),
    [
        ([], True, None, None),
        ([1, 5], True, None, None),
        ([3, 4, 5], False, 3, 4.0),
    ],
)
def test_connector_gets_only_the_thresholded_aggregate(
    http,
    ratings: list[int],
    suppressed: bool,
    count: int | None,
    mean: float | None,
) -> None:
    client, repository, _session, _principal = http
    repository.ratings = ratings
    response = client.get(
        f"/v1/units/{uuid.uuid4()}/speakers/"
        f"{repository.row.speaker_professional_id}/feedback-summary"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["suppressed"] is suppressed
    assert body["response_count"] == count
    assert body["mean_rating"] == mean
    assert body["minimum_responses"] == 3
    assert "student_id" not in body
    assert "comment" not in body
    assert "feedback" not in body
