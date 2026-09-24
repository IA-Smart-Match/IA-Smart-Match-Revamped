"""B26 T4: an availability verdict becomes a compose / dispatch skip reason.

Plan ``docs/plans/b26-tracks/T4-plan.md`` §4.3-§4.4, §8 test 11.
"""

from __future__ import annotations

from datetime import date

import pytest
from smartmatch_domain.availability_verdict import StoredVerdict
from smartmatch_domain.cba_invitations import SkipReason, skip_reason_for_availability
from smartmatch_domain.eligibility import (
    AvailabilityReason,
    AvailabilityState,
    EligibilityOutcome,
)

_AS_OF = date(2026, 10, 1)


@pytest.mark.parametrize(
    ("verdict", "state", "reason", "paused_until", "expected"),
    [
        (
            EligibilityOutcome.EXCLUDED,
            AvailabilityState.BLACKED_OUT,
            AvailabilityReason.WINDOW,
            None,
            SkipReason.SPEAKER_UNAVAILABLE_ON_DATE,
        ),
        (
            EligibilityOutcome.EXCLUDED,
            AvailabilityState.BLACKED_OUT,
            AvailabilityReason.PAUSED,
            date(2027, 1, 10),
            SkipReason.SPEAKER_INVITATIONS_PAUSED,
        ),
        (
            EligibilityOutcome.UNDETERMINED,
            AvailabilityState.UNKNOWN,
            AvailabilityReason.NOT_STATED,
            None,
            None,
        ),
        (
            EligibilityOutcome.UNDETERMINED,
            AvailabilityState.UNKNOWN,
            AvailabilityReason.EVENT_UNRESOLVED,
            None,
            None,
        ),
        (
            EligibilityOutcome.ELIGIBLE,
            AvailabilityState.AVAILABLE,
            AvailabilityReason.CLEAR,
            None,
            None,
        ),
    ],
    ids=["window", "paused", "not_stated", "event_unresolved", "clear"],
)
def test_availability_skip_reasons_map_from_excluded_only(
    verdict, state, reason, paused_until, expected
) -> None:
    stored = StoredVerdict(
        subject_id="prof-a",
        verdict=verdict,
        state=state,
        reason=reason,
        as_of=_AS_OF,
        paused_until=paused_until,
    )

    assert skip_reason_for_availability(stored) is expected


def test_the_two_tokens_are_the_api_vocabulary() -> None:
    assert SkipReason.SPEAKER_UNAVAILABLE_ON_DATE.value == "speaker_unavailable_on_date"
    assert SkipReason.SPEAKER_INVITATIONS_PAUSED.value == "speaker_invitations_paused"
