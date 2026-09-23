"""Tests for the Engagement Load Index, formula 2.0.0 (B26 T8b).

Centered 90-day window (``[as_of - 45, as_of)`` completed, ``[as_of, as_of + 44]``
confirmed), Q7 load bands, Unknown on missing hours or capacity, no default
capacity, no modifiers.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from smartmatch_domain import eli
from smartmatch_domain.eli import (
    COMPLETED_WINDOW_DAYS,
    CONFIRMED_WINDOW_DAYS,
    ELI_FORMULA_VERSION,
    Q7_LOAD_BAND_TABLE,
    Engagement,
    LoadAssessment,
    LoadBand,
    LoadBandTable,
    LoadInputs,
    LoadReason,
    compute_eli,
)
from smartmatch_domain.events import DateOnlyTime, ExactTime, UnresolvedTime
from smartmatch_domain.factor_registry import PROHIBITED_INPUTS

AS_OF = date(2026, 8, 17)
_US_PER_HOUR = 3_600_000_000

_counter = iter(range(1_000_000))


def _eng(
    offset_days: int | None,
    hours: Decimal | str | int | None,
    *,
    confirmed: bool = True,
    attended: bool = False,
    cancelled: bool = False,
    ref: str | None = None,
) -> Engagement:
    """Build an engagement dated ``AS_OF + offset_days`` (``None`` = unresolved)."""
    duration: timedelta | None
    if hours is None:
        duration = None
    else:
        us = Decimal(hours) * _US_PER_HOUR
        assert us == us.to_integral_value(), f"fixture hours {hours} round"
        duration = timedelta(microseconds=int(us))
    return Engagement(
        ref=ref if ref is not None else f"pr-{next(_counter)}",
        event_date=None if offset_days is None else AS_OF + timedelta(days=offset_days),
        duration=duration,
        confirmed=confirmed,
        attended=attended,
        cancelled=cancelled,
    )


def _run(
    *engagements: Engagement,
    capacity: Decimal | str | None = "100.0",
    table: LoadBandTable = Q7_LOAD_BAND_TABLE,
) -> LoadAssessment:
    cap = None if capacity is None else Decimal(capacity)
    return compute_eli(
        LoadInputs(as_of=AS_OF, engagements=tuple(engagements), declared_capacity_hours=cap),
        table,
    )


# 1 ------------------------------------------------------------------------


def test_formula_version_is_2_0_0():
    assert ELI_FORMULA_VERSION == "2.0.0"
    assert _run().formula_version == "2.0.0"


# 2, 3 ---------------------------------------------------------------------


def test_capacity_has_no_default():
    with pytest.raises(TypeError):
        LoadInputs(as_of=AS_OF, engagements=())  # type: ignore[call-arg]


@pytest.mark.parametrize("bad", [40.0, 40, True])
def test_capacity_rejects_float_int_bool(bad: object):
    with pytest.raises(TypeError):
        LoadInputs(as_of=AS_OF, engagements=(), declared_capacity_hours=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["0", "0.0", "-1.0", "NaN", "sNaN", "Infinity", "-Infinity"])
def test_capacity_rejects_zero_negative_nan_infinity(bad: str):
    with pytest.raises(ValueError):
        LoadInputs(as_of=AS_OF, engagements=(), declared_capacity_hours=Decimal(bad))


# 4, 5 ---------------------------------------------------------------------


def test_capacity_none_is_unknown():
    empty = _run(capacity=None)
    heavy = _run(_eng(-1, 500, attended=True), capacity=None)
    unknown_ref = _eng(3, None, ref="pr-missing")
    gap = _run(unknown_ref, capacity=None)
    for result in (empty, heavy, gap):
        assert result.band is LoadBand.UNKNOWN
        assert result.reason is LoadReason.CAPACITY_NOT_STATED
        assert result.utilization is None
        assert result.capacity_hours is None
        assert result.measurable is False
    assert heavy.completed_hours == Decimal(500)
    assert gap.unknown_hours_refs == ("pr-missing",)


def test_no_engagements_is_light_measured_zero():
    result = _run()
    assert result.band is LoadBand.LIGHT
    assert result.reason is LoadReason.MEASURED
    assert result.measurable is True
    assert result.utilization == 0
    assert result.completed_hours == 0
    assert result.confirmed_hours == 0
    assert result.capacity_hours == Decimal("100.0")
    assert result.unknown_hours_refs == ()


# 6 completed window edges -------------------------------------------------


def test_window_constants():
    assert COMPLETED_WINDOW_DAYS == 45
    assert CONFIRMED_WINDOW_DAYS == 45


def test_completed_day_minus_46_ignored():
    result = _run(_eng(-46, 10, attended=True))
    assert result.completed_hours == 0
    assert result.confirmed_hours == 0


def test_completed_day_minus_45_counts():
    assert _run(_eng(-45, 10, attended=True)).completed_hours == Decimal(10)


def test_completed_day_minus_1_counts():
    result = _run(_eng(-1, 10, attended=True))
    assert result.completed_hours == Decimal(10)
    assert result.confirmed_hours == 0


# 7 upcoming rule (R1) -----------------------------------------------------


def test_day_0_confirmed_counts_as_confirmed():
    result = _run(_eng(0, 10))
    assert result.confirmed_hours == Decimal(10)
    assert result.completed_hours == 0


def test_day_0_attended_counts_as_confirmed_not_completed():
    result = _run(_eng(0, 10, attended=True))
    assert result.confirmed_hours == Decimal(10)
    assert result.completed_hours == 0


def test_attended_future_booking_counts_as_confirmed():
    result = _run(_eng(5, 10, attended=True))
    assert result.confirmed_hours == Decimal(10)
    assert result.completed_hours == 0


# 8 confirmed window edges -------------------------------------------------


def test_confirmed_day_plus_44_counts():
    assert _run(_eng(44, 10)).confirmed_hours == Decimal(10)


def test_confirmed_day_plus_45_ignored():
    result = _run(_eng(45, 10))
    assert result.confirmed_hours == 0
    assert result.completed_hours == 0


# 9 -------------------------------------------------------------------------


def test_window_spans_exactly_90_days():
    engagements = [_eng(d, 1, attended=d < 0) for d in range(-46, 46)]
    result = _run(*engagements, capacity="90.0")
    assert result.completed_hours == Decimal(45)
    assert result.confirmed_hours == Decimal(45)
    assert result.utilization == 1
    assert result.band is LoadBand.HEAVY
    assert result.reason is LoadReason.MEASURED


# 10 counted in neither ----------------------------------------------------


def _assert_nothing_counted(result: LoadAssessment) -> None:
    assert result.completed_hours == 0
    assert result.confirmed_hours == 0
    assert result.unknown_hours_refs == ()
    assert result.band is LoadBand.LIGHT
    assert result.reason is LoadReason.MEASURED


def test_confirmed_not_attended_in_past_counts_in_neither():
    _assert_nothing_counted(_run(_eng(-5, 60)))


def test_cancelled_confirmed_future_counts_in_neither():
    _assert_nothing_counted(_run(_eng(5, 60, cancelled=True)))


def test_cancelled_attended_past_counts_in_neither():
    _assert_nothing_counted(_run(_eng(-5, 60, attended=True, cancelled=True)))


def test_cancelled_attended_day_0_counts_in_neither():
    _assert_nothing_counted(_run(_eng(0, 60, attended=True, cancelled=True)))


def test_cancelled_unknown_hours_does_not_make_unknown():
    _assert_nothing_counted(
        _run(_eng(5, None, cancelled=True), _eng(-5, None, attended=True, cancelled=True))
    )


def test_unconfirmed_future_counts_in_neither():
    _assert_nothing_counted(_run(_eng(5, 60, confirmed=False)))


# 11, 12 unknown hours -----------------------------------------------------


def test_unknown_hours_in_window_is_unknown():
    result = _run(
        _eng(-10, 30, attended=True),
        _eng(3, None, ref="pr-b"),
        _eng(-2, None, attended=True, ref="pr-a"),
    )
    assert result.band is LoadBand.UNKNOWN
    assert result.reason is LoadReason.HOURS_UNKNOWN
    assert result.measurable is False
    assert result.unknown_hours_refs == ("pr-a", "pr-b")
    assert result.utilization == Decimal("0.3")
    assert result.completed_hours == Decimal(30)


def test_unknown_hours_outside_window_stays_measurable():
    result = _run(_eng(-46, None, attended=True), _eng(45, None))
    assert result.band is LoadBand.LIGHT
    assert result.reason is LoadReason.MEASURED
    assert result.unknown_hours_refs == ()


def test_confirmed_not_attended_past_unknown_hours_stays_measurable():
    result = _run(_eng(-5, None), _eng(-10, 30, attended=True))
    assert result.reason is LoadReason.MEASURED
    assert result.band is LoadBand.LIGHT
    assert result.unknown_hours_refs == ()
    assert result.completed_hours == Decimal(30)


# 13, 14 lower-bound Full (R4) ---------------------------------------------


def test_lower_bound_full():
    result = _run(_eng(-3, "10.5", attended=True), _eng(2, None, ref="pr-x"), capacity="10.0")
    assert result.band is LoadBand.FULL
    assert result.reason is LoadReason.FULL_BY_KNOWN_HOURS
    assert result.measurable is False
    assert result.unknown_hours_refs == ("pr-x",)


def test_measured_full_has_measured_reason():
    result = _run(_eng(2, "10.5"), capacity="10.0")
    assert result.band is LoadBand.FULL
    assert result.reason is LoadReason.MEASURED
    assert result.measurable is True


def test_known_exactly_at_capacity_plus_unknown_is_unknown():
    result = _run(_eng(-3, 10, attended=True), _eng(2, None), capacity="10.0")
    assert result.band is LoadBand.UNKNOWN
    assert result.reason is LoadReason.HOURS_UNKNOWN
    assert result.utilization == 1


# 15, 16, 17 band edges and exactness --------------------------------------


@pytest.mark.parametrize(
    ("hours", "band"),
    [
        ("49.99", LoadBand.LIGHT),
        ("50.00", LoadBand.MODERATE),
        ("79.99", LoadBand.MODERATE),
        ("80.00", LoadBand.HEAVY),
        ("100.00", LoadBand.HEAVY),
        ("100.01", LoadBand.FULL),
    ],
)
def test_band_edges(hours: str, band: LoadBand):
    result = _run(_eng(1, hours), capacity="100.0")
    assert result.band is band
    assert result.reason is LoadReason.MEASURED


def test_band_edges_are_exact_not_float():
    # Float `+=` of eight 0.1 h gives 0.7999999999999999 -> Moderate.
    acc = 0.0
    for _ in range(8):
        acc += 0.1
    assert acc < 0.8
    result = _run(*(_eng(1, "0.1") for _ in range(8)), capacity="1.0")
    assert result.band is LoadBand.HEAVY
    assert result.confirmed_hours == Decimal("0.8")


def test_inexact_quotients_do_not_raise():
    third = _run(_eng(1, 1), capacity="3.0")
    assert third.band is LoadBand.LIGHT
    assert third.utilization == Decimal(1) / Decimal(3)

    minutes = Engagement(
        ref="pr-7m",
        event_date=AS_OF,
        duration=timedelta(minutes=7),
        confirmed=True,
        attended=False,
        cancelled=False,
    )
    result = _run(minutes, capacity="3.0")
    assert result.confirmed_hours == Decimal(420_000_000) / Decimal(3_600_000_000)
    assert result.band is LoadBand.LIGHT


# 18, 19 from_event_time ----------------------------------------------------


def test_from_event_time():
    start = datetime(2026, 8, 20, 16, 0, tzinfo=UTC)
    exact = Engagement.from_event_time(
        "pr-1",
        ExactTime(
            starts_at=start, time_zone="America/Los_Angeles", ends_at=start + timedelta(hours=2)
        ),
        confirmed=True,
        attended=False,
        cancelled=False,
    )
    assert exact.duration == timedelta(hours=2)
    assert exact.event_date == date(2026, 8, 20)

    open_ended = Engagement.from_event_time(
        "pr-2",
        ExactTime(starts_at=start, time_zone="America/Los_Angeles"),
        confirmed=True,
        attended=False,
        cancelled=False,
    )
    assert open_ended.duration is None
    assert open_ended.event_date == date(2026, 8, 20)

    date_only = Engagement.from_event_time(
        "pr-3",
        DateOnlyTime(on_date=date(2026, 8, 21), time_zone="America/Los_Angeles"),
        confirmed=True,
        attended=True,
        cancelled=False,
    )
    assert date_only.duration is None
    assert date_only.event_date == date(2026, 8, 21)
    assert date_only.attended is True

    unresolved = Engagement.from_event_time(
        "pr-4", UnresolvedTime(), confirmed=True, attended=False, cancelled=True
    )
    assert unresolved.event_date is None
    assert unresolved.duration is None
    assert unresolved.cancelled is True


def test_event_date_is_first_local_date():
    # 23:30 on 20 Aug in Los Angeles is 06:30 UTC on 21 Aug; the event runs 2 days.
    start = datetime(2026, 8, 21, 6, 30, tzinfo=UTC)
    engagement = Engagement.from_event_time(
        "pr-la",
        ExactTime(
            starts_at=start, time_zone="America/Los_Angeles", ends_at=start + timedelta(days=2)
        ),
        confirmed=True,
        attended=False,
        cancelled=False,
    )
    assert engagement.event_date == date(2026, 8, 20)
    assert engagement.duration == timedelta(days=2)


# 20 unresolved dates (R4) -------------------------------------------------


def test_unresolved_confirmed_engagement_is_unknown():
    result = _run(_eng(None, 5, ref="pr-u"), _eng(-3, 10, attended=True))
    assert result.band is LoadBand.UNKNOWN
    assert result.reason is LoadReason.HOURS_UNKNOWN
    assert result.unknown_hours_refs == ("pr-u",)
    assert result.completed_hours == Decimal(10)
    assert result.confirmed_hours == 0


def test_unresolved_with_known_hours_over_capacity_is_full():
    result = _run(_eng(None, None, ref="pr-u"), _eng(2, 11), capacity="10.0")
    assert result.band is LoadBand.FULL
    assert result.reason is LoadReason.FULL_BY_KNOWN_HOURS
    assert result.unknown_hours_refs == ("pr-u",)


def test_unresolved_unconfirmed_or_cancelled_is_ignored():
    result = _run(_eng(None, None, confirmed=False), _eng(None, None, cancelled=True))
    assert result.band is LoadBand.LIGHT
    assert result.reason is LoadReason.MEASURED
    assert result.unknown_hours_refs == ()


# 21 validation -------------------------------------------------------------


def _raw(**overrides: object) -> Engagement:
    base: dict[str, object] = {
        "ref": "pr-v",
        "event_date": AS_OF,
        "duration": timedelta(hours=1),
        "confirmed": True,
        "attended": False,
        "cancelled": False,
    }
    base.update(overrides)
    return Engagement(**base)  # type: ignore[arg-type]


def test_engagement_rejects_attended_without_confirmed():
    with pytest.raises(ValueError):
        _raw(confirmed=False, attended=True)


def test_engagement_rejects_cancelled_without_confirmed():
    with pytest.raises(ValueError):
        _raw(confirmed=False, cancelled=True)


@pytest.mark.parametrize("bad", [timedelta(0), timedelta(hours=-1)])
def test_engagement_rejects_zero_or_negative_duration(bad: timedelta):
    with pytest.raises(ValueError):
        _raw(duration=bad)


@pytest.mark.parametrize("bad", ["", "   "])
def test_engagement_rejects_blank_ref(bad: str):
    with pytest.raises(ValueError):
        _raw(ref=bad)


def test_inputs_reject_duplicate_refs():
    with pytest.raises(ValueError):
        LoadInputs(
            as_of=AS_OF,
            engagements=(_raw(ref="pr-d"), _raw(ref="pr-d")),
            declared_capacity_hours=Decimal("10.0"),
        )


# 22 band table -------------------------------------------------------------


def test_q7_table_values():
    table = Q7_LOAD_BAND_TABLE
    assert table.moderate_from == Decimal("0.50")
    assert table.heavy_from == Decimal("0.80")
    assert table.full_above == Decimal("1.00")
    assert dict(table.multipliers) == {
        LoadBand.LIGHT: Decimal("1.00"),
        LoadBand.MODERATE: Decimal("0.90"),
        LoadBand.HEAVY: Decimal("0.70"),
        LoadBand.UNKNOWN: Decimal("1.00"),
    }
    assert LoadBand.FULL not in table.multipliers


def _table(**overrides: object) -> LoadBandTable:
    base: dict[str, object] = {
        "moderate_from": Decimal("0.50"),
        "heavy_from": Decimal("0.80"),
        "full_above": Decimal("1.00"),
        "multipliers": dict(Q7_LOAD_BAND_TABLE.multipliers),
    }
    base.update(overrides)
    return LoadBandTable(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "overrides",
    [
        {"moderate_from": Decimal("0.80")},  # moderate == heavy
        {"heavy_from": Decimal("1.10")},  # heavy > full
        {"moderate_from": Decimal("0")},
        {"moderate_from": Decimal("NaN")},
        {"moderate_from": 0.5},
        {
            "multipliers": {
                LoadBand.LIGHT: Decimal(1),
                LoadBand.MODERATE: Decimal("0.9"),
                LoadBand.HEAVY: Decimal("0.7"),
            }
        },
        {"multipliers": {**dict(Q7_LOAD_BAND_TABLE.multipliers), LoadBand.FULL: Decimal("0.1")}},
        {"multipliers": {**dict(Q7_LOAD_BAND_TABLE.multipliers), LoadBand.HEAVY: Decimal("0")}},
        {"multipliers": {**dict(Q7_LOAD_BAND_TABLE.multipliers), LoadBand.HEAVY: Decimal("1.1")}},
    ],
)
def test_band_table_rejects_bad_order_and_missing_keys(overrides: dict[str, object]):
    with pytest.raises((TypeError, ValueError)):
        _table(**overrides)


def test_band_table_allows_heavy_equal_to_full():
    table = _table(heavy_from=Decimal("1.00"))
    assert table.heavy_from == table.full_above


def test_band_table_multipliers_are_read_only():
    with pytest.raises(TypeError):
        Q7_LOAD_BAND_TABLE.multipliers[LoadBand.LIGHT] = Decimal("0.5")  # type: ignore[index]


def test_custom_table_moves_cut_points_not_edge_semantics():
    table = _table(
        moderate_from=Decimal("0.40"), heavy_from=Decimal("0.60"), full_above=Decimal("0.90")
    )
    assert _run(_eng(1, "39.99"), table=table).band is LoadBand.LIGHT
    assert _run(_eng(1, "40.00"), table=table).band is LoadBand.MODERATE
    assert _run(_eng(1, "60.00"), table=table).band is LoadBand.HEAVY
    assert _run(_eng(1, "90.00"), table=table).band is LoadBand.HEAVY
    assert _run(_eng(1, "90.01"), table=table).band is LoadBand.FULL


def test_band_table_is_hashable_and_compares_multipliers():
    a = _table()
    b = _table(multipliers={**dict(Q7_LOAD_BAND_TABLE.multipliers), LoadBand.HEAVY: Decimal("0.6")})
    assert isinstance(hash(a), int)
    assert isinstance(hash(b), int)
    assert a == _table()
    assert a != b


# 23 LoadModifier gone (R3) -------------------------------------------------


def test_load_modifier_is_gone():
    assert not hasattr(eli, "LoadModifier")
    assert "modifiers" not in {f.name for f in fields(LoadInputs)}
    for removed in ("EngagementRecord", "EliSnapshot", "CapDecision", "evaluate_cap"):
        assert not hasattr(eli, removed)
    assert not hasattr(eli, "load_penalty")


# 24 prohibited inputs ------------------------------------------------------


def test_prohibited_inputs_cannot_reach_the_computation():
    """The enforcement ``eli.py``'s module docstring claims, actually performed.

    The docstring says the prohibited-input list is enforced "by the registry
    schema and by ``tests/unit/test_eli.py``, not by convention". Documentation
    is not a control; this is.
    """
    permitted = {f.name for f in fields(LoadInputs)} | {f.name for f in fields(Engagement)}
    assert not permitted & PROHIBITED_INPUTS

    for prohibited in sorted(PROHIBITED_INPUTS):
        with pytest.raises(TypeError):
            LoadInputs(
                as_of=AS_OF,
                engagements=(),
                declared_capacity_hours=Decimal("10.0"),
                **{prohibited: "x"},  # type: ignore[arg-type]
            )
        with pytest.raises(TypeError):
            _raw(**{prohibited: "x"})

    # Nor can one be attached after construction: ``slots=True`` leaves no
    # ``__dict__`` for a stray attribute to land in, and ``frozen=True`` refuses
    # the assignment outright.
    inputs = LoadInputs(as_of=AS_OF, engagements=(), declared_capacity_hours=Decimal("10.0"))
    engagement = _raw()
    assert not hasattr(inputs, "__dict__")
    assert not hasattr(engagement, "__dict__")
    for prohibited in sorted(PROHIBITED_INPUTS):
        with pytest.raises((AttributeError, TypeError)):
            setattr(inputs, prohibited, "x")
        with pytest.raises((AttributeError, TypeError)):
            setattr(engagement, prohibited, "x")
