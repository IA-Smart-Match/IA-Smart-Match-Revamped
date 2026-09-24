"""The Speaker's own views: pure builders, no database (B26 T6b-2 plan §7.1).

What is pinned, each for a leak or a lie it would otherwise allow:

* ``state`` reads cancelled before attended before confirmed, so a cancelled
  booking never shows as a live one.
* ``recorded_by`` names a *kind* of recorder, never a user id: a Speaker's own
  answer (link or portal) is ``speaker``; a Connector's entry is
  ``speaker_connector``.
* The rendered field sets are exact, so a batch, canceller, unit or
  other-person field cannot appear by accident.
* The request body forbids every extra key, so no body can name a subject.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError
from smartmatch_api.routers.speaker_availability_models import SpeakerAvailabilityUpdateRequest
from smartmatch_api.routers.speaker_self import (
    SpeakerOwnResponseRequest,
    engagement_state,
    engagement_view,
    invitation_view,
)
from smartmatch_persistence.cba_invitations import SpeakerInvitationRow
from smartmatch_persistence.pipeline import SpeakerEngagementRow

CONFIRMED = datetime(2026, 9, 20, 16, 2, tzinfo=UTC)
LATER = datetime(2026, 9, 22, 21, 40, tzinfo=UTC)
DISPATCHED = datetime(2026, 10, 1, 17, 0, tzinfo=UTC)
ANSWERED = datetime(2026, 10, 2, 9, 14, tzinfo=UTC)


def _invitation(
    *,
    response_status: str = "awaiting_response",
    channel: str | None = None,
    recorded_at: datetime | None = None,
) -> SpeakerInvitationRow:
    return SpeakerInvitationRow(
        id=uuid.uuid4(),
        event_name="Accounting Society Spring Mixer",
        event_date="Thursday 12 March 2027",
        event_local_date=None,
        event_time_zone=None,
        dispatched_at=DISPATCHED,
        response_status=response_status,
        response_recorded_at=recorded_at,
        response_channel=channel,
    )


def _engagement(
    *,
    attended_at: datetime | None = None,
    cancelled_at: datetime | None = None,
    with_event: bool = True,
) -> SpeakerEngagementRow:
    return SpeakerEngagementRow(
        id=uuid.uuid4(),
        confirmed_at=CONFIRMED,
        attended_at=attended_at,
        cancelled_at=cancelled_at,
        event_title="ACCT 4100 guest lecture" if with_event else None,
        event_local_date=date(2026, 10, 14) if with_event else None,
        event_time_zone="America/Los_Angeles" if with_event else None,
        event_time_precision="exact" if with_event else None,
        event_starts_at=datetime(2026, 10, 14, 17, 0, tzinfo=UTC) if with_event else None,
        event_ends_at=datetime(2026, 10, 14, 18, 15, tzinfo=UTC) if with_event else None,
    )


def test_engagement_state_is_cancelled_then_attended_then_confirmed() -> None:
    assert engagement_state(_engagement()) == "confirmed"
    assert engagement_state(_engagement(attended_at=LATER)) == "attended"
    assert engagement_state(_engagement(cancelled_at=LATER)) == "cancelled"
    # The database refuses both at once; the view still reads cancelled first.
    both = _engagement(attended_at=LATER, cancelled_at=LATER)
    assert engagement_state(both) == "cancelled"


@pytest.mark.parametrize(
    ("channel", "expected"),
    [
        ("speaker_link", "speaker"),
        ("speaker_portal", "speaker"),
        ("connector_recorded", "speaker_connector"),
    ],
)
def test_recorded_by_maps_each_channel(channel: str, expected: str) -> None:
    view = invitation_view(
        _invitation(response_status="accepted_invitation", channel=channel, recorded_at=ANSWERED)
    )
    assert view.response is not None
    assert view.response.recorded_by == expected
    assert view.response.recorded_at == ANSWERED


def test_recorded_by_is_absent_while_awaiting() -> None:
    assert invitation_view(_invitation()).response is None


def test_answerable_only_while_awaiting() -> None:
    assert invitation_view(_invitation()).answerable is True
    for status, channel in (
        ("accepted_invitation", "speaker_link"),
        ("declined_invitation", "connector_recorded"),
    ):
        answered = _invitation(response_status=status, channel=channel, recorded_at=ANSWERED)
        assert invitation_view(answered).answerable is False


def test_invitation_view_field_set_is_exact() -> None:
    dumped = invitation_view(
        _invitation(
            response_status="accepted_invitation", channel="speaker_portal", recorded_at=ANSWERED
        )
    ).model_dump(mode="json")
    assert set(dumped) == {
        "invitation_id",
        "event",
        "dispatched_at",
        "status",
        "response",
        "answerable",
    }
    assert set(dumped["event"]) == {"title", "date_text", "local_date", "time_zone"}
    assert set(dumped["response"]) == {"recorded_at", "recorded_by"}
    assert dumped["event"]["date_text"] == "Thursday 12 March 2027"
    assert dumped["status"] == "accepted_invitation"


def test_engagement_view_field_set_is_exact() -> None:
    dumped = engagement_view(_engagement(cancelled_at=LATER)).model_dump(mode="json")
    assert set(dumped) == {
        "engagement_id",
        "event",
        "state",
        "confirmed_at",
        "attended_at",
        "cancelled_at",
    }
    assert set(dumped["event"]) == {
        "title",
        "local_date",
        "time_zone",
        "time_precision",
        "starts_at",
        "ends_at",
    }
    assert dumped["state"] == "cancelled"
    assert dumped["event"]["local_date"] == "2026-10-14"


def test_engagement_without_an_event_row_has_no_event() -> None:
    assert engagement_view(_engagement(with_event=False)).event is None


@pytest.mark.parametrize("extra", ["professional_id", "user_id", "unit_id", "channel"])
def test_request_models_forbid_extra_keys(extra: str) -> None:
    with pytest.raises(ValidationError):
        SpeakerOwnResponseRequest.model_validate({"response": "accept", extra: "x"})
    with pytest.raises(ValidationError):
        SpeakerAvailabilityUpdateRequest.model_validate(
            {
                "expected_version": None,
                "invitations_paused_until": None,
                "declared_capacity_hours_per_90_days": None,
                "unavailable": [],
                extra: "x",
            }
        )


@pytest.mark.parametrize("value", ["maybe", "accepted_invitation", "", None])
def test_response_accepts_only_accept_or_decline(value: object) -> None:
    with pytest.raises(ValidationError):
        SpeakerOwnResponseRequest.model_validate({"response": value})
    assert SpeakerOwnResponseRequest.model_validate({"response": "decline"}).response == "decline"
