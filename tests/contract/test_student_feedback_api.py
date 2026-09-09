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
from smartmatch_api.units import OrgUnitRow
from smartmatch_authz import Membership, OrgPath, Principal
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
        self.ratings_by_speaker: dict[uuid.UUID, list[int]] = {}

    def submit(self, _session: object, **values: Any) -> FeedbackWriteResult:
        self.submission = values
        return FeedbackWriteResult(row=self.row, created=True, changed=True)

    def submitted_ratings(self, _session: object, **_values: Any) -> list[int]:
        return self.ratings

    def submitted_ratings_by_speaker(
        self, _session: object, **_values: Any
    ) -> dict[uuid.UUID, list[int]]:
        return self.ratings_by_speaker

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
    monkeypatch.setattr(routes, "_authorize_unit_feedback_summary_read", lambda *_args: None)
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


# ---------------------------------------------------------------------------
# The unit-level aggregate
# ---------------------------------------------------------------------------


def test_the_unit_summary_is_suppressed_below_the_threshold(http) -> None:
    """Two ratings across the whole unit publish nothing, and not a zero.

    ADR-0011 rule 1: a unit nobody has rated and a unit rated 0.0 are different
    claims, and only one of them is true.
    """
    client, repository, _session, _principal = http
    repository.ratings_by_speaker = {uuid.uuid4(): [4, 5]}

    response = client.get(f"/v1/units/{uuid.uuid4()}/speaker-feedback-summary")

    assert response.status_code == 200
    body = response.json()
    assert body["suppressed"] is True
    assert body["response_count"] is None
    assert body["mean_rating"] is None
    assert body["display_text"] == "not enough responses yet"
    assert body["minimum_responses"] == 3


def test_the_unit_summary_is_suppressed_when_it_would_difference_a_speaker(http) -> None:
    """The differencing case, over HTTP.

    Speaker A is rated by three students and the per-speaker route publishes A's
    count and mean. Speaker B is rated by two and is suppressed. Pooled ``n = 5``
    clears the threshold, and a route that stopped there would let the reader
    compute ``5 - 3 = 2`` and recover a mean over B's two students by
    subtracting what the per-speaker route already told them.
    """
    client, repository, _session, _principal = http
    speaker_a, speaker_b = uuid.uuid4(), uuid.uuid4()
    repository.ratings = [5, 5, 5]
    repository.ratings_by_speaker = {speaker_a: [5, 5, 5], speaker_b: [1, 2]}
    unit_id = uuid.uuid4()

    per_speaker = client.get(f"/v1/units/{unit_id}/speakers/{speaker_a}/feedback-summary").json()
    unit = client.get(f"/v1/units/{unit_id}/speaker-feedback-summary").json()

    assert per_speaker["suppressed"] is False
    assert per_speaker["response_count"] == 3
    assert unit["suppressed"] is True
    assert unit["response_count"] is None
    assert unit["mean_rating"] is None


def test_the_unit_summary_publishes_when_nothing_can_be_differenced(http) -> None:
    """The permitted half: two speakers no aggregate is published for.

    Neither speaker clears the threshold alone, so there is no published total to
    subtract, and pooling the four ratings exposes no individual.
    """
    client, repository, _session, _principal = http
    repository.ratings_by_speaker = {uuid.uuid4(): [4, 4], uuid.uuid4(): [5, 5]}

    body = client.get(f"/v1/units/{uuid.uuid4()}/speaker-feedback-summary").json()

    assert body["suppressed"] is False
    assert body["response_count"] == 4
    assert body["mean_rating"] == 4.5


def test_the_unit_summary_names_no_student_and_no_speaker(http) -> None:
    """Aggregate-only (OQ-CBA-003 part 1), and no per-speaker handle either.

    A ``speakers: [...]`` breakdown would be the per-speaker route again with the
    suppression decided once for all of them, and every extra number is something
    the next number can be differenced against.
    """
    client, repository, _session, _principal = http
    repository.ratings_by_speaker = {uuid.uuid4(): [4, 4], uuid.uuid4(): [5, 5]}
    unit_id = uuid.uuid4()

    body = client.get(f"/v1/units/{unit_id}/speaker-feedback-summary").json()

    assert set(body) == {
        "unit_id",
        "suppressed",
        "response_count",
        "mean_rating",
        "display_text",
        "minimum_responses",
    }
    assert body["unit_id"] == str(unit_id)
    for forbidden in ("student_id", "speaker_professional_id", "speakers", "comment", "feedback"):
        assert forbidden not in body


def test_the_unit_summary_does_not_claim_to_feed_matching(http) -> None:
    """OQ-CBA-053 is open, and this response must not pre-empt it.

    Nothing here is a score, a weight or a factor, and no field name may imply
    that a student's rating changes who gets invited next.
    """
    client, repository, _session, _principal = http
    repository.ratings_by_speaker = {uuid.uuid4(): [4, 4, 4]}

    body = client.get(f"/v1/units/{uuid.uuid4()}/speaker-feedback-summary").json()

    for forbidden in ("score", "weight", "factor", "match_score", "rank"):
        assert forbidden not in body


# ---------------------------------------------------------------------------
# Authorization, with the real authorizer running
# ---------------------------------------------------------------------------


_OWNING_UNIT = "iawest.cpp.engineering.ie"
_SIBLING_UNIT = "iawest.cpp.engineering.cs"


@pytest.fixture
def authorized_http(monkeypatch: pytest.MonkeyPatch):
    """A client whose unit-summary authorizer is the real one.

    The ``http`` fixture stubs the authorizer out so the aggregate's shape can be
    asserted without a database. These refusals are the other half, and stubbing
    the thing under test would make them assert nothing: the unit row is faked,
    the policy call is not.
    """
    tenant_id = uuid.uuid4()

    monkeypatch.setattr(
        routes,
        "load_unit_or_404",
        lambda _session, **_kwargs: OrgUnitRow(
            id=uuid.uuid4(),
            path=_OWNING_UNIT,
            unit_type="department",
            display_name="Industrial Engineering",
        ),
    )
    repository = _FeedbackRepository(
        FeedbackRow(
            id=uuid.uuid4(),
            event_id=uuid.uuid4(),
            student_id=uuid.uuid4(),
            speaker_professional_id=uuid.uuid4(),
            status="submitted",
            rating=5,
            comment=None,
            submitted_at=datetime(2026, 9, 6, 12, tzinfo=UTC),
            updated_at=datetime(2026, 9, 6, 12, tzinfo=UTC),
        )
    )
    repository.ratings_by_speaker = {uuid.uuid4(): [4, 4, 4]}
    monkeypatch.setattr(routes, "_feedback", repository)

    def _session_override() -> Iterator[_Session]:
        yield _Session()

    app.dependency_overrides[get_session] = _session_override

    def _as(role: str, path: str) -> TestClient:
        user_id = uuid.uuid4()
        app.dependency_overrides[get_current_principal] = lambda: ResolvedPrincipal(
            principal=Principal(
                user_id=str(user_id),
                tenant_id=str(tenant_id),
                memberships=(Membership(granted_path=OrgPath.parse(path), role=role),),
            ),
            user_id=user_id,
            tenant_id=tenant_id,
            email=f"{role}@example.invalid",
        )
        return TestClient(app)

    try:
        yield _as
    finally:
        app.dependency_overrides.clear()


def test_a_student_is_refused_the_unit_summary(authorized_http) -> None:
    """A student reads their own rows, never the class's average.

    A student who could read this could watch it move as their classmates
    answered, which is the re-identification the threshold exists to prevent
    aimed at a reader who knows who has not answered yet.
    """
    with authorized_http("student", _OWNING_UNIT) as client:
        response = client.get(f"/v1/units/{uuid.uuid4()}/speaker-feedback-summary")
    assert response.status_code == 403


def test_a_sibling_coordinator_is_refused_the_unit_summary(authorized_http) -> None:
    """Right role, wrong path -- and no ``tenant_wide_roles`` on this authorizer.

    Reading another department's pooled ratings from one's own department is a
    reach nothing has ratified.
    """
    with authorized_http("coordinator", _SIBLING_UNIT) as client:
        response = client.get(f"/v1/units/{uuid.uuid4()}/speaker-feedback-summary")
    assert response.status_code == 403


def test_the_owning_coordinator_is_allowed_the_unit_summary(authorized_http) -> None:
    """The permitted half. A route that refused everyone would pass both above."""
    with authorized_http("coordinator", _OWNING_UNIT) as client:
        response = client.get(f"/v1/units/{uuid.uuid4()}/speaker-feedback-summary")
    assert response.status_code == 200
    assert response.json()["suppressed"] is False
