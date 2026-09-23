"""Tests for the B26 T1 speaker availability verdict and statement limits."""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from smartmatch_domain.eligibility import (
    AvailabilityEvidence,
    AvailabilityState,
    EligibilityOutcome,
    apply_availability_filter,
)
from smartmatch_domain.events import DateOnlyTime, ExactTime, UnresolvedTime
from smartmatch_domain.speaker_availability import (
    AvailabilityAssessment,
    AvailabilityErrorCode,
    AvailabilityReason,
    AvailabilityStatement,
    AvailabilityStatementInvalid,
    UnavailableWindow,
    availability_state_for_event,
    event_local_span,
    validate_availability_statement,
)

AS_OF = date(2026, 9, 22)
EVENT_DAY = date(2026, 10, 15)
SPAN = (EVENT_DAY, EVENT_DAY)
LA = "America/Los_Angeles"


def _stmt(
    *,
    paused: date | None = None,
    capacity: Decimal | None = None,
    windows: tuple[UnavailableWindow, ...] = (),
) -> AvailabilityStatement:
    return AvailabilityStatement(
        invitations_paused_until=paused,
        declared_capacity_hours_per_90_days=capacity,
        unavailable=windows,
    )


def _w(starts: date, ends: date) -> UnavailableWindow:
    return UnavailableWindow(starts_on=starts, ends_on=ends)


def _verdict(assessment: AvailabilityAssessment) -> tuple[AvailabilityState, AvailabilityReason]:
    return (assessment.state, assessment.reason)


AVAILABLE_CLEAR = (AvailabilityState.AVAILABLE, AvailabilityReason.CLEAR)
PAUSED = (AvailabilityState.BLACKED_OUT, AvailabilityReason.PAUSED)
WINDOW = (AvailabilityState.BLACKED_OUT, AvailabilityReason.WINDOW)
NOT_STATED = (AvailabilityState.UNKNOWN, AvailabilityReason.NOT_STATED)
EVENT_UNRESOLVED = (AvailabilityState.UNKNOWN, AvailabilityReason.EVENT_UNRESOLVED)


# ---------------------------------------------------------------------------
# Verdict (§5.1 rows)
# ---------------------------------------------------------------------------


def test_no_row_is_unknown_not_stated():
    assert _verdict(availability_state_for_event(None, SPAN, AS_OF)) == NOT_STATED


def test_no_row_with_unresolved_event_is_still_not_stated():
    assert _verdict(availability_state_for_event(None, None, AS_OF)) == NOT_STATED


def test_unresolved_event_is_unknown_event_unresolved():
    assert _verdict(availability_state_for_event(_stmt(), None, AS_OF)) == EVENT_UNRESOLVED


def test_pause_until_after_as_of_is_blacked_out_paused():
    stmt = _stmt(paused=AS_OF + timedelta(days=5))
    assert _verdict(availability_state_for_event(stmt, SPAN, AS_OF)) == PAUSED


def test_pause_until_equal_as_of_is_blacked_out_paused():
    stmt = _stmt(paused=AS_OF)
    assert _verdict(availability_state_for_event(stmt, SPAN, AS_OF)) == PAUSED


def test_pause_until_day_before_as_of_is_not_paused():
    stmt = _stmt(paused=AS_OF - timedelta(days=1))
    assert _verdict(availability_state_for_event(stmt, SPAN, AS_OF)) == AVAILABLE_CLEAR


def test_unresolved_event_wins_over_active_pause():
    stmt = _stmt(paused=AS_OF + timedelta(days=30))
    assert _verdict(availability_state_for_event(stmt, None, AS_OF)) == EVENT_UNRESOLVED


def test_pause_wins_over_window_reason():
    stmt = _stmt(paused=AS_OF + timedelta(days=30), windows=(_w(EVENT_DAY, EVENT_DAY),))
    assert _verdict(availability_state_for_event(stmt, SPAN, AS_OF)) == PAUSED


def test_window_overlapping_event_date_is_blacked_out_window():
    stmt = _stmt(windows=(_w(EVENT_DAY - timedelta(days=2), EVENT_DAY + timedelta(days=2)),))
    assert _verdict(availability_state_for_event(stmt, SPAN, AS_OF)) == WINDOW


def test_window_starting_on_event_date_blocks():
    stmt = _stmt(windows=(_w(EVENT_DAY, EVENT_DAY + timedelta(days=3)),))
    assert _verdict(availability_state_for_event(stmt, SPAN, AS_OF)) == WINDOW


def test_window_ending_on_event_date_blocks():
    stmt = _stmt(windows=(_w(EVENT_DAY - timedelta(days=3), EVENT_DAY),))
    assert _verdict(availability_state_for_event(stmt, SPAN, AS_OF)) == WINDOW


def test_window_ending_day_before_event_does_not_block():
    stmt = _stmt(windows=(_w(EVENT_DAY - timedelta(days=3), EVENT_DAY - timedelta(days=1)),))
    assert _verdict(availability_state_for_event(stmt, SPAN, AS_OF)) == AVAILABLE_CLEAR


def test_window_starting_day_after_event_does_not_block():
    stmt = _stmt(windows=(_w(EVENT_DAY + timedelta(days=1), EVENT_DAY + timedelta(days=3)),))
    assert _verdict(availability_state_for_event(stmt, SPAN, AS_OF)) == AVAILABLE_CLEAR


def test_row_with_no_windows_and_no_pause_is_available_clear():
    assert _verdict(availability_state_for_event(_stmt(), SPAN, AS_OF)) == AVAILABLE_CLEAR


def test_non_overlapping_windows_only_is_available_clear():
    stmt = _stmt(
        windows=(
            _w(date(2026, 10, 1), date(2026, 10, 10)),
            _w(date(2026, 10, 20), date(2026, 10, 25)),
        )
    )
    assert _verdict(availability_state_for_event(stmt, SPAN, AS_OF)) == AVAILABLE_CLEAR


INVERTED = (EVENT_DAY, EVENT_DAY - timedelta(days=1))


def test_inverted_span_with_no_statement_raises_value_error():
    with pytest.raises(ValueError):
        availability_state_for_event(None, INVERTED, AS_OF)


def test_inverted_span_with_active_pause_raises_value_error():
    with pytest.raises(ValueError):
        availability_state_for_event(_stmt(paused=AS_OF), INVERTED, AS_OF)


def test_inverted_span_with_ordinary_statement_raises_value_error():
    with pytest.raises(ValueError):
        availability_state_for_event(_stmt(), INVERTED, AS_OF)


@pytest.mark.parametrize(
    "span",
    [
        (),
        (EVENT_DAY,),
        (EVENT_DAY, EVENT_DAY, EVENT_DAY),
        (datetime(2026, 10, 15, 9, 0), datetime(2026, 10, 15, 10, 0)),
    ],
    ids=["empty", "one-tuple", "three-tuple", "datetime-pair"],
)
def test_malformed_span_raises_value_error(span):
    with pytest.raises(ValueError):
        availability_state_for_event(None, span, AS_OF)


def test_verdict_maps_through_apply_availability_filter():
    cases = {
        "SYNTH-PRO-0001": (_stmt(), SPAN),
        "SYNTH-PRO-0002": (_stmt(paused=AS_OF), SPAN),
        "SYNTH-PRO-0003": (None, SPAN),
    }
    evidence = {
        sid: availability_state_for_event(stmt, span, AS_OF).to_evidence(sid)
        for sid, (stmt, span) in cases.items()
    }
    decisions = apply_availability_filter(tuple(cases), evidence)
    assert [d.outcome for d in decisions] == [
        EligibilityOutcome.ELIGIBLE,
        EligibilityOutcome.EXCLUDED,
        EligibilityOutcome.UNDETERMINED,
    ]


def test_capacity_does_not_affect_verdict():
    low = _stmt(capacity=Decimal("0.1"))
    high = _stmt(capacity=Decimal("720"))
    none = _stmt()
    verdicts = {_verdict(availability_state_for_event(s, SPAN, AS_OF)) for s in (low, high, none)}
    assert verdicts == {AVAILABLE_CLEAR}


# ---------------------------------------------------------------------------
# Event span / multi-day / DST
# ---------------------------------------------------------------------------


def test_date_only_event_yields_on_date():
    assert event_local_span(DateOnlyTime(date(2026, 9, 14), LA)) == (
        date(2026, 9, 14),
        date(2026, 9, 14),
    )


def test_exact_event_without_end_yields_local_start_date():
    t = ExactTime(datetime(2026, 9, 15, 6, 30, tzinfo=timezone.utc), LA)
    assert event_local_span(t) == (date(2026, 9, 14), date(2026, 9, 14))


def test_exact_event_across_local_midnight_yields_two_dates():
    tz = ZoneInfo(LA)
    t = ExactTime(
        datetime(2026, 9, 14, 22, 0, tzinfo=tz),
        LA,
        ends_at=datetime(2026, 9, 15, 1, 0, tzinfo=tz),
    )
    assert event_local_span(t) == (date(2026, 9, 14), date(2026, 9, 15))


def test_exact_event_ending_at_local_midnight_excludes_next_day():
    tz = ZoneInfo(LA)
    t = ExactTime(
        datetime(2026, 9, 14, 20, 0, tzinfo=tz),
        LA,
        ends_at=datetime(2026, 9, 15, 0, 0, tzinfo=tz),
    )
    assert event_local_span(t) == (date(2026, 9, 14), date(2026, 9, 14))


def test_exact_event_ending_at_skipped_midnight_excludes_next_day():
    t = ExactTime(
        datetime(2026, 9, 5, 23, 0, tzinfo=timezone(timedelta(hours=-4))),
        "America/Santiago",
        ends_at=datetime(2026, 9, 6, 4, 0, tzinfo=timezone.utc),
    )
    assert event_local_span(t) == (date(2026, 9, 5), date(2026, 9, 5))


def test_exact_event_across_fall_back_yields_two_dates():
    t = ExactTime(
        datetime(2026, 10, 31, 22, 0, tzinfo=timezone(timedelta(hours=-7))),
        LA,
        ends_at=datetime(2026, 11, 1, 2, 0, tzinfo=timezone(timedelta(hours=-8))),
    )
    assert event_local_span(t) == (date(2026, 10, 31), date(2026, 11, 1))


def test_exact_event_across_spring_forward_yields_local_dates():
    t = ExactTime(
        datetime(2026, 3, 7, 22, 0, tzinfo=timezone(timedelta(hours=-8))),
        LA,
        ends_at=datetime(2026, 3, 8, 3, 30, tzinfo=timezone(timedelta(hours=-7))),
    )
    assert event_local_span(t) == (date(2026, 3, 7), date(2026, 3, 8))


def test_three_day_event_blocked_by_window_on_middle_day_only():
    span = (date(2026, 10, 14), date(2026, 10, 16))
    stmt = _stmt(windows=(_w(date(2026, 10, 15), date(2026, 10, 15)),))
    assert _verdict(availability_state_for_event(stmt, span, AS_OF)) == WINDOW


def test_long_exact_event_overlap_is_interval_based():
    tz = ZoneInfo(LA)
    t = ExactTime(
        datetime(2027, 1, 1, 9, 0, tzinfo=tz),
        LA,
        ends_at=datetime(2032, 1, 1, 9, 0, tzinfo=tz),
    )
    span = event_local_span(t)
    assert span == (date(2027, 1, 1), date(2032, 1, 1))
    stmt = _stmt(windows=(_w(date(2029, 6, 1), date(2029, 6, 3)),))
    assert _verdict(availability_state_for_event(stmt, span, AS_OF)) == WINDOW


def test_multi_day_event_uses_event_zone_not_utc():
    tokyo = "Asia/Tokyo"
    # 2026-10-14T16:00Z is 2026-10-15 01:00 in Tokyo; ends 2026-10-16 10:00 Tokyo.
    t = ExactTime(
        datetime(2026, 10, 14, 16, 0, tzinfo=timezone.utc),
        tokyo,
        ends_at=datetime(2026, 10, 16, 1, 0, tzinfo=timezone.utc),
    )
    assert event_local_span(t) == (date(2026, 10, 15), date(2026, 10, 16))


def test_unresolved_event_yields_none():
    assert event_local_span(UnresolvedTime()) is None


# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------

TODAY = date(2026, 9, 22)


def _invalid(stmt: AvailabilityStatement, today: date = TODAY) -> AvailabilityStatementInvalid:
    with pytest.raises(AvailabilityStatementInvalid) as exc_info:
        validate_availability_statement(stmt, today)
    return exc_info.value


def _day_windows(n: int) -> tuple[UnavailableWindow, ...]:
    return tuple(_w(TODAY + timedelta(days=i), TODAY + timedelta(days=i)) for i in range(n))


def test_twenty_windows_valid():
    validate_availability_statement(_stmt(windows=_day_windows(20)), TODAY)


def test_twenty_one_windows_too_many():
    err = _invalid(_stmt(windows=_day_windows(21)))
    assert err.code is AvailabilityErrorCode.TOO_MANY_WINDOWS
    assert err.field == "unavailable"
    assert err.index is None


def test_window_end_before_start_invalid():
    err = _invalid(_stmt(windows=(_w(date(2026, 10, 5), date(2026, 10, 4)),)))
    assert err.code is AvailabilityErrorCode.WINDOW_INVALID
    assert err.field == "unavailable"
    assert err.index == 0


def test_single_day_window_valid():
    validate_availability_statement(_stmt(windows=(_w(EVENT_DAY, EVENT_DAY),)), TODAY)


def test_window_span_366_valid():
    start = date(2026, 10, 1)
    validate_availability_statement(
        _stmt(windows=(_w(start, start + timedelta(days=366)),)), TODAY
    )


def test_window_span_367_invalid():
    start = date(2026, 10, 1)
    err = _invalid(_stmt(windows=(_w(start, start + timedelta(days=367)),)))
    assert err.code is AvailabilityErrorCode.WINDOW_INVALID
    assert err.index == 0


def test_window_end_at_18_months_valid():
    horizon = date(2028, 3, 22)
    validate_availability_statement(_stmt(windows=(_w(horizon, horizon),)), TODAY)


def test_window_end_day_after_18_months_invalid():
    beyond = date(2028, 3, 23)
    err = _invalid(_stmt(windows=(_w(beyond, beyond),)))
    assert err.code is AvailabilityErrorCode.WINDOW_INVALID
    assert err.index == 0


@pytest.mark.parametrize(
    ("today", "horizon"),
    [
        (date(2026, 8, 31), date(2028, 2, 29)),
        (date(2027, 8, 31), date(2029, 2, 28)),
    ],
)
def test_18_month_horizon_clamps_month_end(today, horizon):
    validate_availability_statement(_stmt(windows=(_w(horizon, horizon),)), today)
    beyond = horizon + timedelta(days=1)
    err = _invalid(_stmt(windows=(_w(beyond, beyond),)), today)
    assert err.code is AvailabilityErrorCode.WINDOW_INVALID


def test_12_month_pause_horizon_clamps_leap_day():
    today = date(2028, 2, 29)
    validate_availability_statement(_stmt(paused=date(2029, 2, 28)), today)
    err = _invalid(_stmt(paused=date(2029, 3, 1)), today)
    assert err.code is AvailabilityErrorCode.PAUSE_INVALID


def test_duplicate_window_invalid_reports_later_index():
    dup = _w(date(2026, 10, 1), date(2026, 10, 3))
    windows = (
        dup,
        _w(date(2026, 11, 1), date(2026, 11, 2)),
        _w(date(2026, 12, 1), date(2026, 12, 2)),
        _w(date(2026, 10, 1), date(2026, 10, 3)),
    )
    err = _invalid(_stmt(windows=windows))
    assert err.code is AvailabilityErrorCode.WINDOW_INVALID
    assert err.index == 3


def test_past_window_valid():
    validate_availability_statement(
        _stmt(windows=(_w(date(2025, 1, 1), date(2025, 1, 5)),)), TODAY
    )


def test_pause_today_valid():
    validate_availability_statement(_stmt(paused=TODAY), TODAY)


def test_pause_yesterday_invalid():
    err = _invalid(_stmt(paused=TODAY - timedelta(days=1)))
    assert err.code is AvailabilityErrorCode.PAUSE_INVALID
    assert err.field == "invitations_paused_until"
    assert err.index is None


def test_pause_at_12_months_valid():
    validate_availability_statement(_stmt(paused=date(2027, 9, 22)), TODAY)


def test_pause_day_after_12_months_invalid():
    err = _invalid(_stmt(paused=date(2027, 9, 23)))
    assert err.code is AvailabilityErrorCode.PAUSE_INVALID


def _capacity_invalid(value: Decimal) -> None:
    err = _invalid(_stmt(capacity=value))
    assert err.code is AvailabilityErrorCode.CAPACITY_INVALID
    assert err.field == "declared_capacity_hours_per_90_days"
    assert err.index is None


def test_capacity_zero_invalid():
    _capacity_invalid(Decimal("0"))


def test_capacity_negative_invalid():
    _capacity_invalid(Decimal("-1"))


def test_capacity_0_1_valid():
    validate_availability_statement(_stmt(capacity=Decimal("0.1")), TODAY)


def test_capacity_720_valid():
    validate_availability_statement(_stmt(capacity=Decimal("720")), TODAY)


def test_capacity_720_1_invalid():
    _capacity_invalid(Decimal("720.1"))


def test_capacity_trailing_zero_decimals_valid():
    validate_availability_statement(_stmt(capacity=Decimal("24.00")), TODAY)


def test_capacity_two_significant_decimals_invalid():
    _capacity_invalid(Decimal("24.05"))


@pytest.mark.parametrize("raw", ["NaN", "sNaN", "Infinity", "-Infinity"])
def test_capacity_not_finite_invalid(raw):
    _capacity_invalid(Decimal(raw))


@pytest.mark.parametrize("value", [24, 24.0, True], ids=["int", "float", "bool"])
def test_capacity_non_decimal_raises_type_error(value):
    with pytest.raises(TypeError):
        AvailabilityStatement(
            invitations_paused_until=None,
            declared_capacity_hours_per_90_days=value,
        )


def test_capacity_none_and_pause_none_valid():
    validate_availability_statement(_stmt(), TODAY)


def test_first_failure_order_capacity_before_pause_before_windows():
    bad_windows = _day_windows(21)
    bad_pause = TODAY - timedelta(days=1)
    bad_capacity = Decimal("0")
    all_bad = _stmt(capacity=bad_capacity, paused=bad_pause, windows=bad_windows)
    assert _invalid(all_bad).code is AvailabilityErrorCode.CAPACITY_INVALID
    pause_and_windows = _stmt(paused=bad_pause, windows=bad_windows)
    assert _invalid(pause_and_windows).code is AvailabilityErrorCode.PAUSE_INVALID
    too_many_and_bad_window = _stmt(
        windows=(_w(date(2026, 10, 5), date(2026, 10, 4)),) + _day_windows(20)
    )
    assert _invalid(too_many_and_bad_window).code is AvailabilityErrorCode.TOO_MANY_WINDOWS


def test_error_code_values_match_api_codes():
    assert AvailabilityErrorCode.CAPACITY_INVALID.value == "speaker_availability_capacity_invalid"
    assert AvailabilityErrorCode.PAUSE_INVALID.value == "speaker_availability_pause_invalid"
    assert (
        AvailabilityErrorCode.TOO_MANY_WINDOWS.value == "speaker_availability_too_many_windows"
    )
    assert AvailabilityErrorCode.WINDOW_INVALID.value == "speaker_availability_window_invalid"
    assert len(AvailabilityErrorCode) == 4


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


def test_types_are_frozen():
    window = _w(EVENT_DAY, EVENT_DAY)
    stmt = _stmt(windows=(window,))
    assessment = AvailabilityAssessment(AvailabilityState.AVAILABLE, AvailabilityReason.CLEAR)
    with pytest.raises(dataclasses.FrozenInstanceError):
        window.starts_on = TODAY  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        stmt.invitations_paused_until = TODAY  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        assessment.state = AvailabilityState.UNKNOWN  # type: ignore[misc]


@pytest.mark.parametrize(
    ("state", "reason"),
    [AVAILABLE_CLEAR, PAUSED, WINDOW, NOT_STATED, EVENT_UNRESOLVED],
)
def test_to_evidence_carries_state_and_reason(state, reason):
    evidence = AvailabilityAssessment(state, reason).to_evidence("SYNTH-PRO-0001")
    assert evidence == AvailabilityEvidence("SYNTH-PRO-0001", state, reason)


@pytest.mark.parametrize("subject_id", ["", "   "])
def test_to_evidence_rejects_blank_subject(subject_id):
    assessment = AvailabilityAssessment(AvailabilityState.AVAILABLE, AvailabilityReason.CLEAR)
    with pytest.raises(ValueError):
        assessment.to_evidence(subject_id)
