"""Unit-testable pieces of `smartmatch_persistence.spend` (ADR-0015 A1).

`SpendReservationService.reserve`, and its settle counterparts `reconcile`,
`expire_on_timeout`, and `release_before_dispatch`, all need a live
PostgreSQL instance to exercise their guarded SQL and the races those guards
resolve — that is `tests/integration`'s job (Task 5). What is provable here,
without a database, is every piece of *pure* logic those methods are built
from: the `released` re-reservation numbering scheme (the module docstring's
*failure mode* section; `family_attempt_number`/`next_family_work_key`), the
row-to-snapshot mapping every settle path shares (`_snapshot_from_row`), and
the two settle-outcome-to-bucket-delta rules A1 is strictest about —
overage-posts-in-full and release-moves-only-reserved — pinned directly via
`_bucket_deltas_for_settle`. `SpendCeilings` and `ReservationRequest`'s
validation is likewise pure.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from smartmatch_domain.spend import (
    AlreadyReconciledOutcome,
    ExpiredOutcome,
    ReconciledOutcome,
    RefusalReason,
    Refused,
    ReleasedOutcome,
    ReservationSnapshot,
    SpendReservationReceipt,
    SpendReservationState,
)
from smartmatch_persistence.spend import (
    ReservationRequest,
    SpendCeilings,
    SpendReservationService,
    _bucket_deltas_for_settle,
    _snapshot_from_row,
    family_attempt_number,
    next_family_work_key,
)

TENANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
JOB_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
RESERVATION_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
LEASE_TOKEN = uuid.UUID("44444444-4444-4444-4444-444444444444")
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


def _fake_row(**overrides):
    """A `SimpleNamespace` standing in for the `sa.Row` `_snapshot_from_row` reads.

    `sa.Row` cannot be constructed directly outside SQLAlchemy's own
    machinery; `_snapshot_from_row` only ever reads attributes off its
    argument, so a duck-typed stand-in exercises the same code path a real
    row would, matching `tests/unit/test_seed_pilot.py`'s existing use of
    `SimpleNamespace` for the same purpose.
    """
    defaults = dict(
        id=RESERVATION_ID,
        tenant_id=TENANT_ID,
        work_key=BASE,
        job_bucket_key=f"job:{JOB_ID}",
        tenant_day_bucket_key=f"tenant-day:{TENANT_ID}:2026-09-01",
        tenant_month_bucket_key=f"tenant-month:{TENANT_ID}:2026-09",
        state="reserved",
        estimate=Decimal("2.0000"),
        actual_cost=None,
        lease_token=LEASE_TOKEN,
        lease_expires_at=NOW,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _redelivery_row(**overrides):
    defaults = dict(
        id=RESERVATION_ID,
        tenant_id=TENANT_ID,
        work_key=BASE,
        state="reserved",
        estimate=Decimal("2.0000"),
        actual_cost=None,
        lease_token=LEASE_TOKEN,
        lease_expires_at=NOW,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestRedeliveryRule:
    def test_an_expired_reserved_row_is_refused_without_becoming_reusable(self):
        row = _redelivery_row(lease_expires_at=NOW - timedelta(microseconds=1))

        outcome = SpendReservationService._apply_redelivery_rule(row, now=NOW)

        assert isinstance(outcome, Refused)
        assert outcome.reason is RefusalReason.EXPIRED_NO_RETRY

    def test_a_reserved_row_expiring_exactly_now_reuses_the_original_receipt(self):
        row = _redelivery_row(lease_expires_at=NOW)

        outcome = SpendReservationService._apply_redelivery_rule(row, now=NOW)

        assert outcome == SpendReservationReceipt(
            reservation_id=RESERVATION_ID,
            tenant_id=TENANT_ID,
            work_key=BASE,
            lease_token=LEASE_TOKEN,
            estimate=Decimal("2.0000"),
        )

    def test_a_reconciled_row_returns_its_durable_actual_cost(self):
        row = _redelivery_row(
            state="reconciled",
            actual_cost=Decimal("1.2500"),
            lease_token=None,
        )

        outcome = SpendReservationService._apply_redelivery_rule(row, now=NOW)

        assert outcome == AlreadyReconciledOutcome(actual_cost=Decimal("1.2500"))


class TestSnapshotFromRow:
    def test_every_field_maps_across(self):
        row = _fake_row()
        snapshot = _snapshot_from_row(row)
        assert snapshot == ReservationSnapshot(
            id=RESERVATION_ID,
            tenant_id=TENANT_ID,
            work_key=BASE,
            state=SpendReservationState.RESERVED,
            estimate=Decimal("2.0000"),
            actual_cost=None,
            lease_token=LEASE_TOKEN,
            lease_expires_at=NOW,
        )

    def test_state_is_converted_from_the_stored_string(self):
        """The row's `state` column is a plain string; the snapshot's is the enum."""
        row = _fake_row(state="reconciled", lease_token=None, actual_cost=Decimal("1.5000"))
        snapshot = _snapshot_from_row(row)
        assert snapshot.state is SpendReservationState.RECONCILED
        assert snapshot.actual_cost == Decimal("1.5000")
        assert snapshot.lease_token is None


class TestBucketDeltasForSettle:
    """Pins the two rules A1 is strictest about — see the module docstring's
    *Settling a reservation* section. `reserved_delta` is always `-estimate`;
    only `spent_delta` differs by outcome.
    """

    ESTIMATE = Decimal("2.0000")

    def test_reconciled_at_or_under_estimate_posts_the_actual_cost(self):
        outcome = ReconciledOutcome(
            actual_cost=Decimal("1.5000"), overage=None, review_finding=None
        )
        reserved_delta, spent_delta = _bucket_deltas_for_settle(outcome, estimate=self.ESTIMATE)
        assert reserved_delta == -self.ESTIMATE
        assert spent_delta == Decimal("1.5000")

    def test_an_overage_posts_in_full_never_clamped_to_the_estimate(self):
        """A1: "record the overage as actual spend, never silently truncate it
        to the reservation." `spent_delta` must be the real, larger figure —
        not `min(actual_cost, estimate)` and not the estimate.
        """
        actual = Decimal("5.7500")
        outcome = ReconciledOutcome(
            actual_cost=actual, overage=actual - self.ESTIMATE, review_finding=None
        )
        reserved_delta, spent_delta = _bucket_deltas_for_settle(outcome, estimate=self.ESTIMATE)
        assert reserved_delta == -self.ESTIMATE
        assert spent_delta == actual
        assert spent_delta > self.ESTIMATE

    def test_expired_on_timeout_posts_the_full_estimate_as_spent(self):
        outcome = ExpiredOutcome(spent_amount=self.ESTIMATE, is_estimated=True, review_finding=None)
        reserved_delta, spent_delta = _bucket_deltas_for_settle(outcome, estimate=self.ESTIMATE)
        assert reserved_delta == -self.ESTIMATE
        assert spent_delta == self.ESTIMATE

    def test_released_moves_reserved_only_never_spent(self):
        """A1: a release before dispatch returns capacity; the call this
        reservation covered never happened, so `spent` must not move at all.
        """
        outcome = ReleasedOutcome(reason="caller declined the match")
        reserved_delta, spent_delta = _bucket_deltas_for_settle(outcome, estimate=self.ESTIMATE)
        assert reserved_delta == -self.ESTIMATE
        assert spent_delta == Decimal("0")

    def test_reserved_delta_is_always_the_negative_estimate(self):
        for outcome in (
            ReconciledOutcome(actual_cost=Decimal("0"), overage=None, review_finding=None),
            ExpiredOutcome(spent_amount=self.ESTIMATE, is_estimated=True, review_finding=None),
            ReleasedOutcome(reason="x"),
        ):
            reserved_delta, _ = _bucket_deltas_for_settle(outcome, estimate=self.ESTIMATE)
            assert reserved_delta == -self.ESTIMATE
