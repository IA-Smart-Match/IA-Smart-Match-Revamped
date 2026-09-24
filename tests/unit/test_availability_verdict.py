"""B26 T4: the stored Stage A availability verdict (``availability_verdict``).

Plan ``docs/plans/b26-tracks/T4-plan.md`` §2, §3, §5 and §8 tests 1–10. Pure
domain: no database, no clock.
"""

from __future__ import annotations

import dataclasses
import uuid
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from smartmatch_domain.availability_verdict import (
    StoredVerdict,
    as_of_utc,
    changed_since,
    event_time_from_columns,
    filed_this_request,
    from_payload,
    to_payload,
    verdicts_for_pool,
)
from smartmatch_domain.eligibility import (
    AvailabilityReason,
    AvailabilityState,
    EligibilityOutcome,
)
from smartmatch_domain.events import DateOnlyTime, ExactTime, UnresolvedTime
from smartmatch_domain.speaker_availability import (
    AvailabilityStatement,
    UnavailableWindow,
    event_local_span,
)

LA = "America/Los_Angeles"
AS_OF = date(2026, 10, 1)
EVENT_DAY = date(2026, 10, 5)
SPAN = (EVENT_DAY, EVENT_DAY)


def _stmt(
    *, paused: date | None = None, windows: tuple[tuple[date, date], ...] = ()
) -> AvailabilityStatement:
    return AvailabilityStatement(
        invitations_paused_until=paused,
        declared_capacity_hours_per_90_days=None,
        unavailable=tuple(UnavailableWindow(a, b) for a, b in windows),
    )


def _verdict(**overrides: object) -> StoredVerdict:
    fields: dict[str, object] = {
        "subject_id": "prof-a",
        "verdict": EligibilityOutcome.ELIGIBLE,
        "state": AvailabilityState.AVAILABLE,
        "reason": AvailabilityReason.CLEAR,
        "as_of": AS_OF,
        "paused_until": None,
    }
    fields.update(overrides)
    return StoredVerdict(**fields)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 1-2: the verdicts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("statement", "span", "verdict", "state", "reason", "paused_until"),
    [
        (
            _stmt(windows=((date(2026, 10, 4), date(2026, 10, 6)),)),
            SPAN,
            EligibilityOutcome.EXCLUDED,
            AvailabilityState.BLACKED_OUT,
            AvailabilityReason.WINDOW,
            None,
        ),
        (
            _stmt(paused=date(2027, 1, 10)),
            SPAN,
            EligibilityOutcome.EXCLUDED,
            AvailabilityState.BLACKED_OUT,
            AvailabilityReason.PAUSED,
            date(2027, 1, 10),
        ),
        (
            None,
            SPAN,
            EligibilityOutcome.UNDETERMINED,
            AvailabilityState.UNKNOWN,
            AvailabilityReason.NOT_STATED,
            None,
        ),
        (
            _stmt(),
            None,
            EligibilityOutcome.UNDETERMINED,
            AvailabilityState.UNKNOWN,
            AvailabilityReason.EVENT_UNRESOLVED,
            None,
        ),
        (
            _stmt(windows=((date(2026, 11, 1), date(2026, 11, 2)),)),
            SPAN,
            EligibilityOutcome.ELIGIBLE,
            AvailabilityState.AVAILABLE,
            AvailabilityReason.CLEAR,
            None,
        ),
    ],
    ids=["window", "paused", "not_stated", "event_unresolved", "clear"],
)
def test_each_parent_5_1_row_maps_to_its_verdict(
    statement, span, verdict, state, reason, paused_until
) -> None:
    statements = {} if statement is None else {"prof-a": statement}
    (only,) = verdicts_for_pool(("prof-a",), statements, span, AS_OF)

    assert only == StoredVerdict(
        subject_id="prof-a",
        verdict=verdict,
        state=state,
        reason=reason,
        as_of=AS_OF,
        paused_until=paused_until,
    )


def test_verdicts_cover_every_subject_in_pool_order() -> None:
    pool = ("prof-z", "prof-a", "prof-m")
    statements = {"prof-a": _stmt(paused=date(2026, 12, 1)), "prof-m": _stmt()}

    verdicts = verdicts_for_pool(pool, statements, SPAN, AS_OF)

    assert [v.subject_id for v in verdicts] == list(pool)
    assert [v.verdict for v in verdicts] == [
        EligibilityOutcome.UNDETERMINED,
        EligibilityOutcome.EXCLUDED,
        EligibilityOutcome.ELIGIBLE,
    ]
    # A statement for somebody outside the pool is ignored, not reported.
    extra = verdicts_for_pool(pool, {**statements, "prof-q": _stmt()}, SPAN, AS_OF)
    assert extra == verdicts


# ---------------------------------------------------------------------------
# 3-4: the payload
# ---------------------------------------------------------------------------


def test_payload_round_trip_is_exact() -> None:
    verdicts = verdicts_for_pool(
        ("prof-a", "prof-b", "prof-c", "prof-d"),
        {
            "prof-a": _stmt(windows=((EVENT_DAY, EVENT_DAY),)),
            "prof-b": _stmt(paused=date(2027, 1, 10)),
            "prof-d": _stmt(),
        },
        SPAN,
        AS_OF,
    )

    payload = to_payload(verdicts)

    assert payload[1] == {
        "subject_id": "prof-b",
        "verdict": "excluded",
        "state": "blacked_out",
        "reason": "paused",
        "as_of": "2026-10-01",
        "paused_until": "2027-01-10",
    }
    assert from_payload(payload) == verdicts


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda e: e.update(verdict="maybe"), "verdict"),
        (lambda e: e.pop("reason"), "reason"),
        (lambda e: e.pop("as_of"), "as_of"),
        (lambda e: e.update(reason="clear"), "reason"),
        (lambda e: e.update(verdict="eligible"), "verdict"),
        (lambda e: e.update(paused_until=None), "paused_until"),
        (lambda e: e.update(as_of="1 October"), "as_of"),
        (lambda e: e.update(subject_id=""), "subject_id"),
    ],
    ids=[
        "unknown_verdict",
        "missing_reason",
        "missing_as_of",
        "reason_of_another_state",
        "verdict_contradicts_state",
        "paused_without_date",
        "unparseable_date",
        "blank_subject",
    ],
)
def test_payload_reader_refuses_unknown_verdict_missing_field_and_mismatched_reason(
    mutate, message
) -> None:
    payload = to_payload(
        verdicts_for_pool(("prof-a",), {"prof-a": _stmt(paused=date(2027, 1, 10))}, SPAN, AS_OF)
    )
    mutate(payload[0])

    with pytest.raises(ValueError, match=message):
        from_payload(payload)


def test_payload_reader_refuses_a_non_list_and_a_duplicate_subject() -> None:
    with pytest.raises(ValueError, match="availability"):
        from_payload({"subject_id": "prof-a"})
    entry = to_payload((_verdict(),))[0]
    with pytest.raises(ValueError, match="duplicate"):
        from_payload([entry, dict(entry)])


# ---------------------------------------------------------------------------
# 5-6: changed since this run
# ---------------------------------------------------------------------------


def test_unchanged_verdict_reason_and_pause_is_not_changed() -> None:
    stored = _verdict(as_of=date(2026, 9, 1))
    current = _verdict(as_of=date(2026, 10, 1))

    assert changed_since(stored, current) is False
    assert (
        changed_since(
            stored,
            _verdict(
                verdict=EligibilityOutcome.EXCLUDED,
                state=AvailabilityState.BLACKED_OUT,
                reason=AvailabilityReason.WINDOW,
            ),
        )
        is True
    )


def test_moved_pause_date_is_changed() -> None:
    paused = {
        "verdict": EligibilityOutcome.EXCLUDED,
        "state": AvailabilityState.BLACKED_OUT,
        "reason": AvailabilityReason.PAUSED,
    }
    stored = _verdict(**paused, paused_until=date(2027, 1, 10))
    moved = _verdict(**paused, paused_until=date(2027, 2, 10))

    assert changed_since(stored, moved) is True
    assert changed_since(stored, dataclasses.replace(stored, as_of=date(2026, 12, 1))) is False


# ---------------------------------------------------------------------------
# 7-9: dates and event times
# ---------------------------------------------------------------------------


def test_as_of_is_the_utc_date() -> None:
    late_evening_pacific = datetime(2026, 10, 5, 23, 30, tzinfo=ZoneInfo(LA))

    assert as_of_utc(late_evening_pacific) == date(2026, 10, 6)
    assert as_of_utc(datetime(2026, 10, 6, 0, 0, tzinfo=UTC)) == date(2026, 10, 6)
    with pytest.raises(ValueError, match="aware"):
        as_of_utc(datetime(2026, 10, 5, 23, 30))


def test_window_overlap_uses_the_event_local_dates_not_as_of() -> None:
    starts = datetime(2026, 10, 5, 23, 30, tzinfo=ZoneInfo(LA))
    event = ExactTime(starts_at=starts, time_zone=LA)
    as_of = as_of_utc(starts)
    assert as_of == date(2026, 10, 6)

    (only,) = verdicts_for_pool(
        ("prof-a",),
        {"prof-a": _stmt(windows=((date(2026, 10, 5), date(2026, 10, 5)),))},
        event_local_span(event),
        as_of,
    )

    assert only.verdict is EligibilityOutcome.EXCLUDED
    assert only.reason is AvailabilityReason.WINDOW
    assert only.as_of == date(2026, 10, 6)


def test_event_time_from_columns_for_each_precision() -> None:
    starts = datetime(2026, 10, 5, 17, 0, tzinfo=UTC)
    ends = datetime(2026, 10, 5, 19, 0, tzinfo=UTC)

    assert event_time_from_columns(
        time_precision="exact", starts_at=starts, ends_at=ends, on_date=None, time_zone=LA
    ) == ExactTime(starts_at=starts, time_zone=LA, ends_at=ends)
    assert event_time_from_columns(
        time_precision="date_only",
        starts_at=None,
        ends_at=None,
        on_date=EVENT_DAY,
        time_zone=LA,
    ) == DateOnlyTime(on_date=EVENT_DAY, time_zone=LA)
    assert (
        event_time_from_columns(
            time_precision="unresolved", starts_at=None, ends_at=None, on_date=None, time_zone=None
        )
        == UnresolvedTime()
    )

    with pytest.raises(ValueError, match="time_precision"):
        event_time_from_columns(
            time_precision="fuzzy", starts_at=None, ends_at=None, on_date=None, time_zone=LA
        )
    with pytest.raises(ValueError, match="starts_at"):
        event_time_from_columns(
            time_precision="exact", starts_at=None, ends_at=None, on_date=None, time_zone=LA
        )
    with pytest.raises(ValueError, match="on_date"):
        event_time_from_columns(
            time_precision="date_only", starts_at=None, ends_at=None, on_date=None, time_zone=LA
        )


# ---------------------------------------------------------------------------
# 10: Q8
# ---------------------------------------------------------------------------


def test_filed_this_request_rule() -> None:
    host = uuid.uuid4()
    other = uuid.uuid4()

    assert filed_this_request(host, host) is True
    assert filed_this_request(host, other) is False
    assert filed_this_request(None, host) is False
    assert filed_this_request(host, None) is False
    assert filed_this_request(None, None) is False
