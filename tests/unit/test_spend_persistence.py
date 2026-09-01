"""Unit-testable pieces of `smartmatch_persistence.spend` (ADR-0015 A1).

`SpendReservationService.reserve` itself needs a live PostgreSQL instance —
its guarded `INSERT ... ON CONFLICT` writes and the `uq_spend_reservation_work_key`
race are exercised by `tests/integration` — but the `released` re-reservation
numbering scheme (the module docstring's *failure mode* section) is pure
arithmetic over strings, deliberately factored out as
`family_attempt_number`/`next_family_work_key` so it can be pinned here without
a database. `SpendCeilings` and `ReservationRequest`'s validation is likewise
pure.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from smartmatch_persistence.spend import (
    ReservationRequest,
    SpendCeilings,
    family_attempt_number,
    next_family_work_key,
)

TENANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
JOB_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
BASE = "spend-abc123"


class TestFamilyAttemptNumber:
    def test_the_base_key_itself_is_attempt_one(self):
        assert family_attempt_number(BASE, BASE) == 1

    def test_a_suffixed_key_reports_its_number(self):
        assert family_attempt_number(BASE, f"{BASE}#2") == 2
        assert family_attempt_number(BASE, f"{BASE}#7") == 7

    def test_a_key_outside_the_family_is_rejected(self):
        with pytest.raises(ValueError, match="does not belong"):
            family_attempt_number(BASE, "spend-somethingelse")

    def test_a_non_numeric_suffix_is_rejected(self):
        with pytest.raises(ValueError, match="non-numeric"):
            family_attempt_number(BASE, f"{BASE}#not-a-number")


class TestNextFamilyWorkKey:
    def test_the_first_re_reservation_skips_to_attempt_two(self):
        """The unsuffixed base row is implicitly attempt 1.

        A family holding only the original (now `released`) row has one
        member, so the next attempt is 2 — never `base#1`, which would
        collide with nothing but would also misrepresent the base row as
        something other than the first attempt.
        """
        assert next_family_work_key(BASE, [BASE]) == f"{BASE}#2"

    def test_numbering_advances_with_each_release(self):
        assert next_family_work_key(BASE, [BASE, f"{BASE}#2"]) == f"{BASE}#3"
        assert next_family_work_key(BASE, [BASE, f"{BASE}#2", f"{BASE}#3"]) == f"{BASE}#4"

    def test_an_empty_family_still_yields_attempt_two(self):
        """Defensive: `reserve` never calls this with an empty family (a fresh
        key uses the base key directly), but the function's own contract does
        not depend on that — an empty iterable simply has family_size 0.
        """
        assert next_family_work_key(BASE, []) == f"{BASE}#1"

    def test_unrelated_keys_are_not_counted(self):
        """A key that merely shares a prefix without the `#` separator, or
        that belongs to a different base entirely, is not part of this
        family and must not inflate the attempt number.
        """
        other = "spend-def456"
        assert next_family_work_key(BASE, [BASE, other, f"{other}#2"]) == f"{BASE}#2"
        assert next_family_work_key(BASE, [f"{BASE}extra"]) == f"{BASE}#1"


class TestSpendCeilings:
    def test_valid_ceilings_construct(self):
        ceilings = SpendCeilings(
            job=Decimal("2.0000"), tenant_day=Decimal("25.0000"), tenant_month=Decimal("250.0000")
        )
        assert ceilings.job == Decimal("2.0000")

    @pytest.mark.parametrize("field", ["job", "tenant_day", "tenant_month"])
    def test_a_negative_ceiling_is_rejected(self, field):
        values = {"job": Decimal("1"), "tenant_day": Decimal("1"), "tenant_month": Decimal("1")}
        values[field] = Decimal("-0.0001")
        with pytest.raises(ValueError, match="non-negative"):
            SpendCeilings(**values)


class TestReservationRequest:
    def _request(self, **overrides):
        defaults = dict(
            tenant_id=TENANT_ID,
            job_id=JOB_ID,
            provider="openai",
            unit_of_work="page-1",
            estimate=Decimal("0.5000"),
            now=NOW,
            lease=timedelta(minutes=5),
        )
        defaults.update(overrides)
        return ReservationRequest(**defaults)

    def test_a_valid_request_constructs(self):
        request = self._request()
        assert request.estimate == Decimal("0.5000")

    def test_a_negative_estimate_is_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            self._request(estimate=Decimal("-0.0001"))

    def test_a_naive_datetime_is_rejected(self):
        with pytest.raises(ValueError, match="timezone-aware"):
            self._request(now=datetime(2026, 9, 1, 12, 0))

    def test_a_zero_lease_is_rejected(self):
        with pytest.raises(ValueError, match="positive"):
            self._request(lease=timedelta(0))

    def test_a_negative_lease_is_rejected(self):
        with pytest.raises(ValueError, match="positive"):
            self._request(lease=timedelta(seconds=-1))
