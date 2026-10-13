"""ExactTime orders instants, not wall clocks, across a DST fall-back (#280)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from smartmatch_domain.events import ExactTime

LA = ZoneInfo("America/Los_Angeles")
TZ = "America/Los_Angeles"


def _at(hour: int, minute: int, fold: int) -> datetime:
    # 2026-11-01 01:00-02:00 happens twice in Los Angeles.
    return datetime(2026, 11, 1, hour, minute, tzinfo=LA, fold=fold)


def test_fall_back_interval_with_earlier_wall_clock_end_is_accepted() -> None:
    ExactTime(starts_at=_at(1, 30, 0), ends_at=_at(1, 10, 1), time_zone=TZ)


def test_fall_back_interval_with_later_wall_clock_end_but_earlier_instant_is_rejected() -> None:
    with pytest.raises(ValueError, match="strictly after"):
        ExactTime(starts_at=_at(1, 10, 1), ends_at=_at(1, 30, 0), time_zone=TZ)


def test_same_instant_is_rejected() -> None:
    with pytest.raises(ValueError, match="strictly after"):
        ExactTime(starts_at=_at(1, 30, 1), ends_at=_at(1, 30, 1), time_zone=TZ)


def test_ordinary_interval_still_accepted() -> None:
    ExactTime(starts_at=_at(1, 10, 0), ends_at=_at(1, 30, 0), time_zone=TZ)
