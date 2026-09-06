"""Unit-testable pieces of `smartmatch_persistence.spend_sweeper` (A1 T-08).

`SpendReservationSweeper.sweep` issues real SQL and resolves real races, so
its guarded write and its predicate belong to `tests/integration` (Task 5).
What is provable without a database is the piece the sweep's whole
"never releases" guarantee rests on: `_snapshot_from_row` builds an
`AbandonedReservationSnapshot`, which carries no `lease_token`, so nothing
read by a sweep can satisfy `release_before_dispatch`. These tests pin that
absence directly, and pin that the snapshot feeds `expire_abandoned` to the
conservative outcome A1 requires.
"""

from __future__ import annotations

import uuid
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from smartmatch_domain.spend import (
    AbandonedReservationSnapshot,
    ExpiredOutcome,
    RefusalReason,
    Refused,
    ReviewFindingCategory,
    SpendReservationState,
    expire_abandoned,
)
from smartmatch_persistence.spend_sweeper import DEFAULT_SWEEP_LIMIT, _snapshot_from_row

TENANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
RESERVATION_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
EXPIRED_AT = NOW - timedelta(minutes=5)


def _row(**overrides: object) -> SimpleNamespace:
    """A stand-in for the row `_select_abandoned` returns.

    Deliberately carries no `lease_token` attribute, matching the columns
    `_select_abandoned` actually selects: a mapping that reached for one
    would raise here rather than pass against a too-generous fake.
    """
    defaults: dict[str, object] = {
        "id": RESERVATION_ID,
        "tenant_id": TENANT_ID,
        "work_key": "spend-abc123",
        "state": SpendReservationState.RESERVED.value,
        "estimate": Decimal("2.5000"),
        "lease_expires_at": EXPIRED_AT,
    }
    return SimpleNamespace(**{**defaults, **overrides})


class TestSnapshotFromRow:
    def test_maps_every_column_the_domain_type_declares(self):
        snapshot = _snapshot_from_row(_row())

        assert snapshot == AbandonedReservationSnapshot(
            id=RESERVATION_ID,
            tenant_id=TENANT_ID,
            work_key="spend-abc123",
            state=SpendReservationState.RESERVED,
            estimate=Decimal("2.5000"),
            lease_expires_at=EXPIRED_AT,
        )

    def test_carries_no_lease_token(self):
        """The absence is the enforcement, not an oversight.

        Without a token on this type, nothing built from a sweep's read can
        satisfy `release_before_dispatch`'s signature — which is how A1's
        "the sweep never releases" rule is enforced by the type system rather
        than by this module remembering to obey it.
        """
        assert "lease_token" not in {f.name for f in fields(AbandonedReservationSnapshot)}
        assert not hasattr(_snapshot_from_row(_row()), "lease_token")

    def test_state_is_widened_to_the_domain_enum(self):
        snapshot = _snapshot_from_row(_row())

        assert isinstance(snapshot.state, SpendReservationState)

    def test_estimate_stays_decimal(self):
        """A1 Global Constraint 5: money is never a float."""
        assert isinstance(_snapshot_from_row(_row()).estimate, Decimal)


class TestSnapshotDrivesTheConservativeOutcome:
    def test_an_expired_reserved_row_is_reclaimed_at_the_full_estimate(self):
        outcome = expire_abandoned(_snapshot_from_row(_row()), now=NOW)

        assert isinstance(outcome, ExpiredOutcome)
        assert outcome.spent_amount == Decimal("2.5000")
        assert outcome.is_estimated is True
        assert outcome.review_finding is not None
        assert outcome.review_finding.category is ReviewFindingCategory.ABANDONED_EXPIRY
        assert outcome.review_finding.reservation_id == RESERVATION_ID

    def test_a_lease_that_has_not_expired_is_refused(self):
        row = _row(lease_expires_at=NOW + timedelta(minutes=1))

        outcome = expire_abandoned(_snapshot_from_row(row), now=NOW)

        assert isinstance(outcome, Refused)
        assert outcome.reason is RefusalReason.NOT_EXPIRED

    def test_an_already_settled_row_is_refused(self):
        row = _row(state=SpendReservationState.RECONCILED.value)

        outcome = expire_abandoned(_snapshot_from_row(row), now=NOW)

        assert isinstance(outcome, Refused)
        assert outcome.reason is RefusalReason.ALREADY_TERMINAL


class TestSweepLimit:
    def test_the_default_bound_is_positive_and_modest(self):
        """A bound, not a throttle — see the constant's own docstring."""
        assert 0 < DEFAULT_SWEEP_LIMIT <= 1000
