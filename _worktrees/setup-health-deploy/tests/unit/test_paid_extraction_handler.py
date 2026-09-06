"""The worker's reserve -> dispatch -> settle path, without a database.

ADR-0015 Amendment A1, Task 4. What the guarded SQL does is Task 5's business;
what this file pins is the **ordering and the branching** the handler is
responsible for, which is where A1 says the defect lives:

* nothing reaches the provider before a reservation commits;
* a refused reservation raises `BudgetFailure` (terminal, `failed_budget`) and
  makes no call at all;
* a returned call reconciles to its **actual**;
* a timed-out call settles through `expire_on_timeout` — the reserved maximum,
  flagged estimated — and never through `reconcile`, and never through a
  release;
* the handler never uses the executor's transaction for the reservation.

`SpendReservationService` is replaced with a recording double. That is a
deliberate seam, not a shortcut: the real service's behavior is proven against
PostgreSQL in `tests/integration`, and what is under test here is the order in
which this handler calls it — a fact no database can make more true.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
import smartmatch_worker.paid_extraction as paid_extraction
from smartmatch_domain.jobs import JobState
from smartmatch_domain.spend import (
    AlreadyReconciledOutcome,
    ExpiredOutcome,
    ReconciledOutcome,
    RefusalReason,
    Refused,
    ReleasedOutcome,
    SpendReservationReceipt,
)
from smartmatch_persistence.jobs import JobRecord
from smartmatch_persistence.spend import ReservationRequest, SpendCeilings
from smartmatch_providers.paid import SyntheticPaidProvider, estimate_max_cost
from smartmatch_worker.handlers import (
    BudgetFailure,
    CommandContext,
    PolicyFailure,
    ProviderFailure,
    default_registry,
)
from smartmatch_worker.paid_extraction import (
    PAID_EXTRACTION_COMMAND_TYPE,
    build_paid_extraction_handler,
    with_paid_extraction,
)

TENANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
JOB_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
RESERVATION_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
LEASE_TOKEN = uuid.UUID("44444444-4444-4444-4444-444444444444")
UNIT_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")
NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)

CEILINGS = SpendCeilings(
    job=Decimal("2.0000"), tenant_day=Decimal("25.0000"), tenant_month=Decimal("250.0000")
)


class _FakeSession:
    """A session that can be opened and closed and does nothing else.

    The handler is required to take its own session for the reservation, so the
    test needs something the factory can hand back. It is never asked to
    execute anything, because every statement in this path belongs to the
    service double below.
    """

    def __init__(self) -> None:
        self.closed = False

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.closed = True


class _RecordingService:
    """Records the calls the handler makes, in order, and returns canned results.

    Attributes:
        calls: One entry per service method reached, so a test can assert
            *"reconcile, and never expire_on_timeout"* rather than only
            asserting the outcome — the branch is the thing A1 cares about.
    """

    def __init__(
        self,
        *,
        reserve_result: SpendReservationReceipt | AlreadyReconciledOutcome | Refused,
        reconcile_result: object = None,
        timeout_result: object = None,
    ) -> None:
        self._reserve_result = reserve_result
        self._reconcile_result = reconcile_result
        self._timeout_result = timeout_result
        self.calls: list[str] = []
        self.reserve_requests: list[ReservationRequest] = []
        self.reconciled_costs: list[Decimal] = []

    def reserve(
        self, request: ReservationRequest, ceilings: SpendCeilings
    ) -> SpendReservationReceipt | AlreadyReconciledOutcome | Refused:
        self.calls.append("reserve")
        self.reserve_requests.append(request)
        assert ceilings is CEILINGS
        return self._reserve_result

    def reconcile(
        self, receipt: SpendReservationReceipt, *, actual_cost: Decimal, now: datetime
    ) -> object:
        self.calls.append("reconcile")
        self.reconciled_costs.append(actual_cost)
        assert now.tzinfo is not None
        assert receipt.reservation_id == RESERVATION_ID
        return self._reconcile_result

    def expire_on_timeout(self, receipt: SpendReservationReceipt, *, now: datetime) -> object:
        self.calls.append("expire_on_timeout")
        assert receipt.reservation_id == RESERVATION_ID
        assert now.tzinfo is not None
        return self._timeout_result

    def release_before_dispatch(
        self, receipt: SpendReservationReceipt, *, reason: str, now: datetime
    ) -> ReleasedOutcome:
        # A1: "the sweep never releases", and neither does anything past
        # dispatch. Reaching this is a test failure, not a behavior.
        self.calls.append("release_before_dispatch")
        raise AssertionError("the paid handler must never release a reservation")


def _receipt(estimate: Decimal) -> SpendReservationReceipt:
    return SpendReservationReceipt(
        reservation_id=RESERVATION_ID,
        tenant_id=TENANT_ID,
        work_key="spend-abc",
        lease_token=LEASE_TOKEN,
        estimate=estimate,
    )


def _job(payload: dict[str, Any] | None) -> JobRecord:
    return JobRecord(
        id=JOB_ID,
        tenant_id=TENANT_ID,
        command_type=PAID_EXTRACTION_COMMAND_TYPE,
        status=JobState.RUNNING,
        actor_id=None,
        created_at=NOW,
        updated_at=NOW,
        owning_unit_id=UNIT_ID,
        payload=payload,
    )


class _Context:
    """A `CommandContext` whose `emit` records instead of writing."""

    def __init__(self, payload: dict[str, Any] | None) -> None:
        self.events: list[dict[str, Any]] = []
        self.executor_session = _FakeSession()
        self.context = CommandContext(
            job=_job(payload),
            emit=self._emit,
            session=self.executor_session,  # type: ignore[arg-type]
        )

    def _emit(self, event: dict[str, Any]) -> int:
        self.events.append(event)
        return len(self.events)


def _build(
    monkeypatch: pytest.MonkeyPatch,
    service: _RecordingService,
    provider: Any,
) -> tuple[Any, list[_FakeSession]]:
    """Wire the handler against the double, and report the sessions it opened."""
    opened: list[_FakeSession] = []

    def factory() -> _FakeSession:
        session = _FakeSession()
        opened.append(session)
        return session

    monkeypatch.setattr(
        paid_extraction, "SpendReservationService", lambda session: service, raising=True
    )
    handler = build_paid_extraction_handler(
        session_factory=factory,  # type: ignore[arg-type]
        provider=provider,
        ceilings=CEILINGS,
        lease=timedelta(minutes=5),
        clock=lambda: NOW,
    )
    return handler, opened


# ---------------------------------------------------------------------------
# The payload is read, never guessed
# ---------------------------------------------------------------------------


def test_a_job_with_no_payload_is_terminal(monkeypatch: pytest.MonkeyPatch):
    service = _RecordingService(reserve_result=_receipt(Decimal("0.3500")))
    handler, _ = _build(monkeypatch, service, SyntheticPaidProvider())

    with pytest.raises(PolicyFailure) as raised:
        handler(_Context(None).context)

    assert raised.value.reason == "command_payload_missing"
    assert service.calls == [], "nothing may be reserved for a command nobody can read"


@pytest.mark.parametrize(
    "payload",
    [
        {"pages": 10},
        {"unit_of_work": "  ", "pages": 10},
        {"unit_of_work": "page:1"},
        {"unit_of_work": "page:1", "pages": "10"},
        {"unit_of_work": "page:1", "pages": 10.0},
        {"unit_of_work": "page:1", "pages": True},
        {"unit_of_work": "page:1", "pages": 0},
    ],
)
def test_an_unreadable_payload_reserves_nothing(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
):
    """A dollar figure must never come from a value nobody validated."""
    service = _RecordingService(reserve_result=_receipt(Decimal("0.3500")))
    handler, _ = _build(monkeypatch, service, SyntheticPaidProvider())

    with pytest.raises(PolicyFailure) as raised:
        handler(_Context(payload).context)

    assert raised.value.reason == "invalid_command_payload"
    assert service.calls == []


# ---------------------------------------------------------------------------
# A refused reservation is a BudgetFailure, and no call is made
# ---------------------------------------------------------------------------


def test_a_refused_reservation_raises_budget_failure_and_calls_nothing(
    monkeypatch: pytest.MonkeyPatch,
):
    provider = SyntheticPaidProvider()
    service = _RecordingService(
        reserve_result=Refused(RefusalReason.CEILING_EXCEEDED, "job ceiling refused 0.3500")
    )
    handler, _ = _build(monkeypatch, service, provider)
    ctx = _Context({"unit_of_work": "page:1", "pages": 10})

    with pytest.raises(BudgetFailure) as raised:
        handler(ctx.context)

    assert raised.value.reason == RefusalReason.CEILING_EXCEEDED.value
    assert provider.calls == [], "the ceiling must stop the call, not report it afterwards"
    assert service.calls == ["reserve"]
    assert any(event.get("reservation_refused") for event in ctx.events)


def test_a_redelivery_of_an_expired_unit_is_refused_not_re_debited(
    monkeypatch: pytest.MonkeyPatch,
):
    """A1: `expired_spent` requires a new reservation under the ceiling as it
    now stands — the handler surfaces that refusal rather than retrying past it.
    """
    provider = SyntheticPaidProvider()
    service = _RecordingService(
        reserve_result=Refused(RefusalReason.EXPIRED_NO_RETRY, "already reclaimed as spent")
    )
    handler, _ = _build(monkeypatch, service, provider)

    with pytest.raises(BudgetFailure) as raised:
        handler(_Context({"unit_of_work": "page:1", "pages": 10}).context)

    assert raised.value.reason == RefusalReason.EXPIRED_NO_RETRY.value
    assert provider.calls == []


def test_a_reconciled_redelivery_succeeds_without_calling_or_settling(
    monkeypatch: pytest.MonkeyPatch,
):
    provider = SyntheticPaidProvider()
    service = _RecordingService(
        reserve_result=AlreadyReconciledOutcome(actual_cost=Decimal("0.1200"))
    )
    handler, _ = _build(monkeypatch, service, provider)

    result = handler(_Context({"unit_of_work": "page:1", "pages": 10}).context)

    assert result.state is JobState.SUCCEEDED
    assert result.summary["actual_cost"] == "0.1200"
    assert result.summary["actual_is_estimated"] is False
    assert result.summary["already_reconciled"] is True
    assert "estimate" not in result.summary
    assert provider.calls == []
    assert service.calls == ["reserve"]


def test_a_reconciled_redelivery_missing_its_actual_cost_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
):
    provider = SyntheticPaidProvider()
    service = _RecordingService(reserve_result=AlreadyReconciledOutcome(actual_cost=None))
    handler, _ = _build(monkeypatch, service, provider)

    with pytest.raises(RuntimeError, match=r"reconciled.*actual_cost"):
        handler(_Context({"unit_of_work": "page:1", "pages": 10}).context)

    assert provider.calls == []
    assert service.calls == ["reserve"]


# ---------------------------------------------------------------------------
# The happy path: reserve the maximum, call, reconcile the actual
# ---------------------------------------------------------------------------


def test_the_reservation_is_the_estimated_maximum_and_precedes_the_call(
    monkeypatch: pytest.MonkeyPatch,
):
    estimate = estimate_max_cost(10)
    provider = SyntheticPaidProvider()
    service = _RecordingService(
        reserve_result=_receipt(estimate),
        reconcile_result=ReconciledOutcome(
            actual_cost=Decimal("0.1200"), overage=None, review_finding=None
        ),
    )
    handler, opened = _build(monkeypatch, service, provider)
    ctx = _Context({"unit_of_work": "page:1", "pages": 10})

    result = handler(ctx.context)

    assert service.calls == ["reserve", "reconcile"]
    request = service.reserve_requests[0]
    assert request.estimate == estimate == Decimal("0.3500")
    assert request.tenant_id == TENANT_ID
    assert request.job_id == JOB_ID
    assert request.unit_of_work == "page:1"
    assert request.provider == provider.name
    assert provider.calls == [_receipt(estimate)]
    assert service.reconciled_costs == [Decimal("0.1200")]
    assert result.state is JobState.SUCCEEDED
    assert result.summary["actual_cost"] == "0.1200"
    assert result.summary["actual_is_estimated"] is False
    assert result.summary["overage"] is None
    assert opened, "the reservation must run on a session of its own"
    assert ctx.executor_session.closed is False, (
        "the executor's transaction is not the handler's to open, close, or commit"
    )


def test_an_overage_is_reported_in_full(monkeypatch: pytest.MonkeyPatch):
    """A1: "record the overage as actual spend, never silently truncate it"."""
    estimate = estimate_max_cost(2)
    provider = SyntheticPaidProvider(cost_per_page=Decimal("0.5"))
    service = _RecordingService(
        reserve_result=_receipt(estimate),
        reconcile_result=ReconciledOutcome(
            actual_cost=Decimal("1.0000"),
            overage=Decimal("0.9300"),
            review_finding=None,
        ),
    )
    handler, _ = _build(monkeypatch, service, provider)

    result = handler(_Context({"unit_of_work": "page:1", "pages": 2}).context)

    assert service.reconciled_costs == [Decimal("1.0000")]
    assert result.summary["overage"] == "0.9300"
    assert result.summary["actual_cost"] == "1.0000"
    assert Decimal(result.summary["actual_cost"]) > Decimal(result.summary["estimate"])


def test_a_lost_reconcile_race_completes_as_partial(monkeypatch: pytest.MonkeyPatch):
    """The work happened; the ledger holds an estimate. Neither claim is a lie.

    Reporting `succeeded` would hide the fact that the recorded figure is not
    this call's actual — an estimate reported as an actual is exactly what A1
    forbids.
    """
    provider = SyntheticPaidProvider()
    service = _RecordingService(
        reserve_result=_receipt(estimate_max_cost(10)),
        reconcile_result=Refused(RefusalReason.ALREADY_TERMINAL, "the sweep settled it first"),
    )
    handler, _ = _build(monkeypatch, service, provider)

    result = handler(_Context({"unit_of_work": "page:1", "pages": 10}).context)

    assert result.state is JobState.PARTIAL
    assert result.summary["actual_is_estimated"] is True
    assert result.summary["ledger_records"] == "0.3500"
    assert result.summary["reconcile_refused"] == RefusalReason.ALREADY_TERMINAL.value


# ---------------------------------------------------------------------------
# The timeout branch
# ---------------------------------------------------------------------------


def test_a_timeout_settles_through_expire_on_timeout_never_reconcile(
    monkeypatch: pytest.MonkeyPatch,
):
    """A1: the reserved maximum, held as spent, flagged estimated.

    Not zero (which fails open), not the estimate written into `actual_cost`
    with `actual_is_estimated=False` (which fabricates a value), and never a
    release.
    """
    estimate = estimate_max_cost(10)
    provider = SyntheticPaidProvider(times_out=True)
    service = _RecordingService(
        reserve_result=_receipt(estimate),
        timeout_result=ExpiredOutcome(
            spent_amount=estimate, is_estimated=True, review_finding=None
        ),
    )
    handler, _ = _build(monkeypatch, service, provider)
    ctx = _Context({"unit_of_work": "page:1", "pages": 10})

    with pytest.raises(ProviderFailure) as raised:
        handler(ctx.context)

    assert raised.value.reason == "paid_call_timed_out"
    assert service.calls == ["reserve", "expire_on_timeout"]
    assert "reconcile" not in service.calls
    settle_event = ctx.events[-1]
    assert settle_event["spent"] == str(estimate)
    assert settle_event["estimated"] is True


def test_an_unexpected_provider_error_also_settles_conservatively(
    monkeypatch: pytest.MonkeyPatch,
):
    """A failure this side of the wire cannot prove the provider was not billed."""

    class _Exploding:
        name = "synthetic-paid-exploding"

        def extract(self, receipt: SpendReservationReceipt, *, pages: int) -> Any:
            raise RuntimeError("connection reset")

    estimate = estimate_max_cost(3)
    service = _RecordingService(
        reserve_result=_receipt(estimate),
        timeout_result=ExpiredOutcome(
            spent_amount=estimate, is_estimated=True, review_finding=None
        ),
    )
    handler, _ = _build(monkeypatch, service, _Exploding())

    with pytest.raises(ProviderFailure) as raised:
        handler(_Context({"unit_of_work": "page:1", "pages": 3}).context)

    assert raised.value.reason == "paid_call_failed"
    assert service.calls == ["reserve", "expire_on_timeout"]


def test_a_timeout_that_loses_the_settle_race_still_fails_the_job(
    monkeypatch: pytest.MonkeyPatch,
):
    """The sweep got there first and recorded the same figure by the same rule."""
    provider = SyntheticPaidProvider(times_out=True)
    service = _RecordingService(
        reserve_result=_receipt(estimate_max_cost(10)),
        timeout_result=Refused(RefusalReason.ALREADY_TERMINAL, "the sweep expired it"),
    )
    handler, _ = _build(monkeypatch, service, provider)
    ctx = _Context({"unit_of_work": "page:1", "pages": 10})

    with pytest.raises(ProviderFailure):
        handler(ctx.context)

    assert service.calls == ["reserve", "expire_on_timeout"]
    assert ctx.events[-1]["timeout_settle_refused"] == RefusalReason.ALREADY_TERMINAL.value


# ---------------------------------------------------------------------------
# Registration is a deliberate act
# ---------------------------------------------------------------------------


def test_the_shipped_registry_has_no_spending_command():
    assert PAID_EXTRACTION_COMMAND_TYPE not in default_registry().command_types


def test_with_paid_extraction_composes_a_new_registry(monkeypatch: pytest.MonkeyPatch):
    service = _RecordingService(reserve_result=_receipt(Decimal("0.3500")))
    handler, _ = _build(monkeypatch, service, SyntheticPaidProvider())
    base = default_registry()

    composed = with_paid_extraction(base, handler)

    assert composed.handler_for(PAID_EXTRACTION_COMMAND_TYPE) is handler
    assert base.command_types < composed.command_types
    assert PAID_EXTRACTION_COMMAND_TYPE not in base.command_types, (
        "the base registry must not be mutated"
    )


def test_registering_a_second_spending_handler_is_refused(monkeypatch: pytest.MonkeyPatch):
    service = _RecordingService(reserve_result=_receipt(Decimal("0.3500")))
    handler, _ = _build(monkeypatch, service, SyntheticPaidProvider())
    composed = with_paid_extraction(default_registry(), handler)

    with pytest.raises(ValueError, match="already registered"):
        with_paid_extraction(composed, handler)
