"""Monetary spend reservation state machine (ADR-0015 Amendment A1).

These tests are the specification for `smartmatch_domain.spend`. A1's rule is
reserve-the-maximum-before-the-paid-call, reconcile-after; the load-bearing
claims tested here are that `released` has exactly one legal entry path, that a
timeout or a sweep always reclaims at the reserved maximum flagged as
*estimated*, and that an overage is recorded rather than truncated.

Nothing here touches a database, a provider, or the network — several tests
exist specifically to prove those paths are absent.
"""

from __future__ import annotations

import dataclasses
import inspect
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from smartmatch_domain import spend
from smartmatch_domain.spend import (
    BUCKET_LOCK_ORDER,
    TERMINAL_STATES,
    TRANSITIONS,
    AbandonedReservationSnapshot,
    AlreadyReconciledOutcome,
    BucketType,
    ExpiredOutcome,
    InvalidSpendTransitionError,
    ReconciledOutcome,
    RefusalReason,
    Refused,
    ReleasedOutcome,
    ReservationSnapshot,
    ReviewFindingCategory,
    SpendReservationReceipt,
    SpendReservationState,
    assert_transition,
    can_transition,
    derive_work_key,
    dispatch,
    expire_abandoned,
    expire_on_timeout,
    is_terminal,
    job_bucket_key,
    reconcile,
    release_before_dispatch,
    tenant_day_bucket_key,
    tenant_month_bucket_key,
)

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
TENANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
JOB_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
RESERVATION_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
LEASE_TOKEN = uuid.UUID("44444444-4444-4444-4444-444444444444")
ESTIMATE = Decimal("1.5000")


def _snapshot(
    *,
    state: SpendReservationState = SpendReservationState.RESERVED,
    actual_cost: Decimal | None = None,
    lease_token: uuid.UUID | None = LEASE_TOKEN,
    lease_expires_at: datetime = NOW + timedelta(minutes=5),
) -> ReservationSnapshot:
    return ReservationSnapshot(
        id=RESERVATION_ID,
        tenant_id=TENANT_ID,
        work_key="spend-abc",
        state=state,
        estimate=ESTIMATE,
        actual_cost=actual_cost,
        lease_token=lease_token,
        lease_expires_at=lease_expires_at,
    )


def _abandoned(
    *,
    state: SpendReservationState = SpendReservationState.RESERVED,
    lease_expires_at: datetime = NOW - timedelta(minutes=1),
) -> AbandonedReservationSnapshot:
    return AbandonedReservationSnapshot(
        id=RESERVATION_ID,
        tenant_id=TENANT_ID,
        work_key="spend-abc",
        state=state,
        estimate=ESTIMATE,
        lease_expires_at=lease_expires_at,
    )


def _receipt(
    *, reservation_id: uuid.UUID = RESERVATION_ID, lease_token: uuid.UUID = LEASE_TOKEN
) -> SpendReservationReceipt:
    return SpendReservationReceipt(
        reservation_id=reservation_id,
        tenant_id=TENANT_ID,
        work_key="spend-abc",
        lease_token=lease_token,
        estimate=ESTIMATE,
    )


TERMINAL = (
    SpendReservationState.RECONCILED,
    SpendReservationState.EXPIRED_SPENT,
    SpendReservationState.RELEASED,
)


# ---------------------------------------------------------------------------
# The state machine — only `reserved` is non-terminal.
# ---------------------------------------------------------------------------


class TestStateMachine:
    @pytest.mark.parametrize("target", TERMINAL)
    def test_reserved_may_reach_every_terminal_state(self, target: SpendReservationState) -> None:
        assert can_transition(SpendReservationState.RESERVED, target)

    @pytest.mark.parametrize("state", TERMINAL)
    @pytest.mark.parametrize("target", SpendReservationState)
    def test_no_transition_leaves_a_terminal_state(
        self, state: SpendReservationState, target: SpendReservationState
    ) -> None:
        assert not can_transition(state, target)

    def test_terminal_states_are_exactly_the_three(self) -> None:
        assert frozenset(TERMINAL) == TERMINAL_STATES
        assert not is_terminal(SpendReservationState.RESERVED)

    def test_every_state_has_a_transition_entry(self) -> None:
        assert set(TRANSITIONS) == set(SpendReservationState)

    def test_assert_transition_raises_on_an_illegal_move(self) -> None:
        with pytest.raises(InvalidSpendTransitionError) as excinfo:
            assert_transition(SpendReservationState.EXPIRED_SPENT, SpendReservationState.RECONCILED)
        assert excinfo.value.current is SpendReservationState.EXPIRED_SPENT
        assert excinfo.value.requested is SpendReservationState.RECONCILED

    def test_assert_transition_is_silent_on_a_legal_move(self) -> None:
        assert_transition(SpendReservationState.RESERVED, SpendReservationState.RECONCILED)


# ---------------------------------------------------------------------------
# Deterministic keys — a retry re-reserves under the same key, never a new one.
# ---------------------------------------------------------------------------


class TestKeyDerivation:
    def test_identical_inputs_derive_an_identical_work_key(self) -> None:
        first = derive_work_key(
            tenant_id=TENANT_ID, job_id=JOB_ID, provider="geocoder", unit_of_work="page-1"
        )
        second = derive_work_key(
            tenant_id=TENANT_ID, job_id=JOB_ID, provider="geocoder", unit_of_work="page-1"
        )
        assert first == second

    def test_any_changed_input_derives_a_different_work_key(self) -> None:
        other_tenant = uuid.UUID("99999999-9999-9999-9999-999999999999")
        other_job = uuid.UUID("88888888-8888-8888-8888-888888888888")
        baseline = derive_work_key(
            tenant_id=TENANT_ID, job_id=JOB_ID, provider="geocoder", unit_of_work="page-1"
        )
        varied = {
            derive_work_key(
                tenant_id=other_tenant,
                job_id=JOB_ID,
                provider="geocoder",
                unit_of_work="page-1",
            ),
            derive_work_key(
                tenant_id=TENANT_ID,
                job_id=other_job,
                provider="geocoder",
                unit_of_work="page-1",
            ),
            derive_work_key(
                tenant_id=TENANT_ID, job_id=JOB_ID, provider="other", unit_of_work="page-1"
            ),
            derive_work_key(
                tenant_id=TENANT_ID, job_id=JOB_ID, provider="geocoder", unit_of_work="page-2"
            ),
        }
        assert baseline not in varied
        # Each varied input is also distinct from every other, not merely from
        # the baseline — a key that collapsed two different units of work would
        # let one reservation cover both.
        assert len(varied) == 4

    def test_a_delimiter_inside_a_component_cannot_forge_a_collision(self) -> None:
        """Length-prefixed encoding: no two distinct inputs share a key."""
        shifted_left = derive_work_key(
            tenant_id=TENANT_ID, job_id=JOB_ID, provider="a|b", unit_of_work="c"
        )
        shifted_right = derive_work_key(
            tenant_id=TENANT_ID, job_id=JOB_ID, provider="a", unit_of_work="b|c"
        )
        assert shifted_left != shifted_right

    def test_an_empty_component_does_not_collide_with_a_shifted_one(self) -> None:
        assert derive_work_key(
            tenant_id=TENANT_ID, job_id=JOB_ID, provider="", unit_of_work="ab"
        ) != derive_work_key(tenant_id=TENANT_ID, job_id=JOB_ID, provider="a", unit_of_work="b")

    def test_bucket_keys_carry_their_type_prefix(self) -> None:
        assert job_bucket_key(JOB_ID) == f"job:{JOB_ID}"
        assert (
            tenant_day_bucket_key(TENANT_ID, date(2026, 9, 1))
            == f"tenant-day:{TENANT_ID}:2026-09-01"
        )
        assert tenant_month_bucket_key(TENANT_ID, 2026, 9) == f"tenant-month:{TENANT_ID}:2026-09"

    def test_month_bucket_key_is_zero_padded(self) -> None:
        assert tenant_month_bucket_key(TENANT_ID, 2026, 3).endswith("2026-03")

    def test_lock_order_is_fixed_and_covers_every_bucket(self) -> None:
        assert BUCKET_LOCK_ORDER == (
            BucketType.JOB,
            BucketType.TENANT_DAY,
            BucketType.TENANT_MONTH,
        )
        assert set(BUCKET_LOCK_ORDER) == set(BucketType)


# ---------------------------------------------------------------------------
# reconcile — an overage is recorded, never truncated; already-settled is a no-op.
# ---------------------------------------------------------------------------


class TestReconcile:
    def test_cost_under_the_estimate_records_no_overage(self) -> None:
        outcome = reconcile(_snapshot(), actual_cost=Decimal("0.7500"), now=NOW)
        assert isinstance(outcome, ReconciledOutcome)
        assert outcome.actual_cost == Decimal("0.7500")
        assert outcome.overage is None
        assert outcome.review_finding is None

    def test_cost_exactly_at_the_estimate_records_no_overage(self) -> None:
        outcome = reconcile(_snapshot(), actual_cost=ESTIMATE, now=NOW)
        assert isinstance(outcome, ReconciledOutcome)
        assert outcome.overage is None

    def test_cost_over_the_estimate_records_the_overage_in_full(self) -> None:
        outcome = reconcile(_snapshot(), actual_cost=Decimal("2.0000"), now=NOW)
        assert isinstance(outcome, ReconciledOutcome)
        assert outcome.actual_cost == Decimal("2.0000")
        assert outcome.overage == Decimal("0.5000")
        assert outcome.review_finding is not None
        assert outcome.review_finding.category is ReviewFindingCategory.OVERAGE
        assert outcome.review_finding.reservation_id == RESERVATION_ID

    def test_a_second_reconcile_is_an_idempotent_no_op(self) -> None:
        settled = _snapshot(
            state=SpendReservationState.RECONCILED,
            actual_cost=Decimal("0.7500"),
            lease_token=None,
        )
        outcome = reconcile(settled, actual_cost=Decimal("2.0000"), now=NOW)
        assert isinstance(outcome, AlreadyReconciledOutcome)
        # The recorded cost, not the one the late caller presented.
        assert outcome.actual_cost == Decimal("0.7500")

    def test_a_negative_actual_cost_is_refused(self) -> None:
        """A credit is not a negative call cost; the domain refuses before the DB does."""
        outcome = reconcile(_snapshot(), actual_cost=Decimal("-3.0000"), now=NOW)
        assert isinstance(outcome, Refused)
        assert outcome.reason is RefusalReason.NEGATIVE_ACTUAL_COST

    def test_a_zero_actual_cost_is_accepted(self) -> None:
        outcome = reconcile(_snapshot(), actual_cost=Decimal("0"), now=NOW)
        assert isinstance(outcome, ReconciledOutcome)
        assert outcome.actual_cost == Decimal("0")

    @pytest.mark.parametrize(
        "state", [SpendReservationState.EXPIRED_SPENT, SpendReservationState.RELEASED]
    )
    def test_a_late_worker_cannot_reopen_an_expired_or_released_row(
        self, state: SpendReservationState
    ) -> None:
        outcome = reconcile(
            _snapshot(state=state, lease_token=None), actual_cost=Decimal("2.0000"), now=NOW
        )
        assert isinstance(outcome, Refused)
        assert outcome.reason is RefusalReason.ALREADY_TERMINAL


# ---------------------------------------------------------------------------
# The sweep — reclaims at the reserved maximum, and can never release.
# ---------------------------------------------------------------------------


class TestExpireAbandoned:
    def test_expired_lease_is_reclaimed_at_the_reserved_maximum_as_estimated(self) -> None:
        outcome = expire_abandoned(_abandoned(), now=NOW)
        assert isinstance(outcome, ExpiredOutcome)
        assert outcome.spent_amount == ESTIMATE
        assert outcome.is_estimated is True
        assert outcome.review_finding is not None
        assert outcome.review_finding.category is ReviewFindingCategory.ABANDONED_EXPIRY

    def test_a_lease_still_in_force_is_refused(self) -> None:
        outcome = expire_abandoned(_abandoned(lease_expires_at=NOW + timedelta(minutes=1)), now=NOW)
        assert isinstance(outcome, Refused)
        assert outcome.reason is RefusalReason.NOT_EXPIRED

    def test_a_lease_expiring_exactly_now_is_not_yet_expired(self) -> None:
        outcome = expire_abandoned(_abandoned(lease_expires_at=NOW), now=NOW)
        assert isinstance(outcome, Refused)
        assert outcome.reason is RefusalReason.NOT_EXPIRED

    @pytest.mark.parametrize("state", TERMINAL)
    def test_an_already_settled_row_is_refused(self, state: SpendReservationState) -> None:
        outcome = expire_abandoned(_abandoned(state=state), now=NOW)
        assert isinstance(outcome, Refused)
        assert outcome.reason is RefusalReason.ALREADY_TERMINAL

    def test_the_sweeps_snapshot_type_carries_no_lease_token(self) -> None:
        """The structural reason a sweep can never mint a receipt (A1)."""
        fields = {f.name for f in dataclasses.fields(AbandonedReservationSnapshot)}
        assert "lease_token" not in fields


# ---------------------------------------------------------------------------
# In-worker timeout — reserved maximum, flagged estimated, never `released`.
# ---------------------------------------------------------------------------


class TestExpireOnTimeout:
    def test_timeout_holds_the_reserved_maximum_flagged_as_estimated(self) -> None:
        outcome = expire_on_timeout(_snapshot(), _receipt(), now=NOW)
        assert isinstance(outcome, ExpiredOutcome)
        assert outcome.spent_amount == ESTIMATE
        assert outcome.is_estimated is True

    def test_timeout_never_records_zero_and_never_reconciles(self) -> None:
        outcome = expire_on_timeout(_snapshot(), _receipt(), now=NOW)
        assert not isinstance(outcome, ReconciledOutcome)
        assert isinstance(outcome, ExpiredOutcome)
        assert outcome.spent_amount != Decimal("0")

    def test_a_receipt_for_another_reservation_is_refused(self) -> None:
        other = uuid.UUID("55555555-5555-5555-5555-555555555555")
        outcome = expire_on_timeout(_snapshot(), _receipt(reservation_id=other), now=NOW)
        assert isinstance(outcome, Refused)
        assert outcome.reason is RefusalReason.RECEIPT_MISMATCH

    def test_a_stale_lease_token_is_refused(self) -> None:
        stale = uuid.UUID("66666666-6666-6666-6666-666666666666")
        outcome = expire_on_timeout(_snapshot(), _receipt(lease_token=stale), now=NOW)
        assert isinstance(outcome, Refused)
        assert outcome.reason is RefusalReason.RECEIPT_MISMATCH

    def test_state_is_checked_before_the_receipt(self) -> None:
        """A settled row reports 'already settled', not a misleading mismatch."""
        outcome = expire_on_timeout(
            _snapshot(state=SpendReservationState.EXPIRED_SPENT, lease_token=None),
            _receipt(),
            now=NOW,
        )
        assert isinstance(outcome, Refused)
        assert outcome.reason is RefusalReason.ALREADY_TERMINAL


# ---------------------------------------------------------------------------
# release_before_dispatch — the single legal entry to `released`.
# ---------------------------------------------------------------------------


class TestReleaseBeforeDispatch:
    def test_the_holding_worker_may_release_before_dispatch(self) -> None:
        outcome = release_before_dispatch(
            _snapshot(), _receipt(), reason="worker declined the work", now=NOW
        )
        assert isinstance(outcome, ReleasedOutcome)
        assert outcome.reason == "worker declined the work"

    def test_a_worker_whose_lease_ran_out_cannot_release(self) -> None:
        """A1 admits no exception: an expired reservation is spent, never released."""
        outcome = release_before_dispatch(
            _snapshot(lease_expires_at=NOW - timedelta(seconds=1)),
            _receipt(),
            reason="stalled worker changed its mind",
            now=NOW,
        )
        assert isinstance(outcome, Refused)
        assert outcome.reason is RefusalReason.LEASE_EXPIRED

    def test_a_lease_expiring_exactly_now_cannot_release(self) -> None:
        outcome = release_before_dispatch(
            _snapshot(lease_expires_at=NOW), _receipt(), reason="too late", now=NOW
        )
        assert isinstance(outcome, Refused)
        assert outcome.reason is RefusalReason.LEASE_EXPIRED

    def test_a_mismatched_receipt_cannot_release(self) -> None:
        stale = uuid.UUID("66666666-6666-6666-6666-666666666666")
        outcome = release_before_dispatch(
            _snapshot(), _receipt(lease_token=stale), reason="whatever", now=NOW
        )
        assert isinstance(outcome, Refused)
        assert outcome.reason is RefusalReason.RECEIPT_MISMATCH

    @pytest.mark.parametrize("state", TERMINAL)
    def test_a_settled_row_cannot_be_released(self, state: SpendReservationState) -> None:
        outcome = release_before_dispatch(
            _snapshot(state=state, lease_token=None),
            _receipt(),
            reason="too late",
            now=NOW,
        )
        assert isinstance(outcome, Refused)
        assert outcome.reason is RefusalReason.ALREADY_TERMINAL

    def test_no_other_public_function_can_return_a_released_outcome(self) -> None:
        """A1: 'The sweep never releases.' Enforced by return type, not convention."""
        returns_released = {
            name
            for name, obj in vars(spend).items()
            if inspect.isfunction(obj)
            and not name.startswith("_")
            and "ReleasedOutcome" in str(inspect.signature(obj).return_annotation)
        }
        assert returns_released == {"release_before_dispatch"}


# ---------------------------------------------------------------------------
# The dispatch seam — no receipt, no paid call.
# ---------------------------------------------------------------------------


class TestDispatchSeam:
    def test_a_receipt_reaches_the_provider_callable_unchanged(self) -> None:
        receipt = _receipt()
        assert dispatch(receipt, lambda r: r) is receipt

    @pytest.mark.parametrize("impostor", [None, {"reservation_id": RESERVATION_ID}, "receipt"])
    def test_anything_that_is_not_a_receipt_is_refused_at_runtime(self, impostor: object) -> None:
        def _must_not_run(_: SpendReservationReceipt) -> None:  # pragma: no cover
            raise AssertionError("the paid call was reached without a reservation")

        with pytest.raises(TypeError):
            dispatch(impostor, _must_not_run)  # type: ignore[arg-type]

    def test_the_receipt_parameter_has_no_default(self) -> None:
        parameter = inspect.signature(dispatch).parameters["receipt"]
        assert parameter.default is inspect.Parameter.empty


# ---------------------------------------------------------------------------
# Purity — this module is the half that touches nothing.
# ---------------------------------------------------------------------------


class TestPurity:
    @pytest.mark.parametrize(
        "forbidden", ["sqlalchemy", "socket", "os", "pathlib", "requests", "httpx"]
    )
    def test_the_module_imports_no_io_dependency(self, forbidden: str) -> None:
        source = inspect.getsource(spend)
        assert f"import {forbidden}" not in source
