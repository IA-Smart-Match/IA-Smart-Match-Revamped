"""Spend reservation integration tests (ADR-0015 Amendment A1, Task 5).

``tests/unit/test_spend_persistence.py`` pins every piece of
``smartmatch_persistence.spend`` that is pure — the ``released`` attempt
numbering, the row-to-snapshot mapping, the settle deltas. None of that
touches the part A1 is actually strict about: the *guards*. A guard is a
property of one SQL statement executing against a real PostgreSQL under real
concurrency, and it cannot be proven by a fake. Every claim in this file is
one that a passing unit suite would leave completely unverified:

* that the debit's ``INSERT`` is guarded and not only its ``DO UPDATE`` —
  A1's named hole, and the defect an implementer copying ADR-0006 verbatim
  reintroduces every time;
* that a refusal on the *second* ceiling leaves the *first* ceiling untouched,
  which only a transaction can deliver;
* that N racing sessions against a ceiling admitting K get exactly K
  reservations — the whole point of the single conditional write;
* that the fixed ``BUCKET_LOCK_ORDER`` keeps interleaved reservations off
  each other's deadlock;
* that redelivery does what A1's four states say, including that a second
  delivery of a ``reserved`` row debits nothing a second time;
* that a reconcile is idempotent across two real transactions;
* that the sweep expires rather than releases, and reports each reservation
  once;
* that an overage posts in full past the ceiling and then closes the bucket.

**Concurrency here is real.** The racing tests open one
:class:`~sqlalchemy.orm.Session` per thread from the session factory — one
connection, one transaction each — and release them onto the same statement
through a :class:`threading.Barrier`. Nothing is simulated by calling the
service twice in sequence; a sequential test of a guarded write proves only
that the arithmetic is right, which is what the unit suite already proves.

Skipped in full when no PostgreSQL is reachable, via ``conftest.engine``.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from smartmatch_domain.spend import (
    AlreadyReconciledOutcome,
    BucketType,
    ExpiredOutcome,
    ReconciledOutcome,
    RefusalReason,
    Refused,
    ReleasedOutcome,
    SpendReservationReceipt,
    SpendReservationState,
    derive_work_key,
    job_bucket_key,
    tenant_day_bucket_key,
    tenant_month_bucket_key,
)
from smartmatch_persistence.spend import (
    ReservationRequest,
    SpendCeilings,
    SpendReservationService,
)
from smartmatch_persistence.spend_sweeper import SpendReservationSweeper
from sqlalchemy import Engine, Row, text
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration

#: Injected rather than read from the clock, the same discipline
#: ``RateLimiter.check`` follows: the day and month bucket keys are derived
#: from this instant, so a test that ran at midnight would otherwise land its
#: two reservations in different buckets and fail for the calendar's reasons
#: rather than the code's.
NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)

#: Long enough that no test's lease expires by accident. The sweeper tests
#: move ``now`` past it instead of waiting.
LEASE = timedelta(minutes=30)

#: Generous enough never to be the ceiling under test. A test that means to
#: exercise the job, day, or month ceiling sets that one explicitly.
UNCAPPED = Decimal("1000.0000")


def _ceilings(
    *,
    job: Decimal = UNCAPPED,
    tenant_day: Decimal = UNCAPPED,
    tenant_month: Decimal = UNCAPPED,
) -> SpendCeilings:
    """Ceilings with only the one under test constrained."""
    return SpendCeilings(job=job, tenant_day=tenant_day, tenant_month=tenant_month)


def _request(
    tenant_id: uuid.UUID,
    job_id: uuid.UUID,
    *,
    unit_of_work: str,
    estimate: Decimal,
    now: datetime = NOW,
    lease: timedelta = LEASE,
) -> ReservationRequest:
    """One reservation request. ``estimate`` is a ``Decimal``, never a float."""
    return ReservationRequest(
        tenant_id=tenant_id,
        job_id=job_id,
        provider="synthetic",
        unit_of_work=unit_of_work,
        estimate=estimate,
        now=now,
        lease=lease,
    )


def _bucket(
    engine: Engine, tenant_id: uuid.UUID, bucket_type: BucketType, bucket_key: str
) -> Row[tuple[Decimal, Decimal, Decimal]] | None:
    """Read one ``spend_ceiling_bucket`` row, or ``None`` if it does not exist.

    Read through a *separate* connection from the service's session on
    purpose: these assertions are about what committed, not about what one
    session can see of its own uncommitted work.
    """
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT ceiling, reserved, spent FROM spend_ceiling_bucket "
                "WHERE tenant_id = :tid AND bucket_type = :btype AND bucket_key = :bkey"
            ),
            {"tid": tenant_id, "btype": bucket_type.value, "bkey": bucket_key},
        ).one_or_none()
    return row


def _reservation(engine: Engine, reservation_id: uuid.UUID) -> Row[tuple[object, ...]] | None:
    """Read one committed ``spend_reservation`` row, or ``None``."""
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT state, estimate, actual_cost, actual_is_estimated, lease_token, "
                "settled_at, review_flagged_at, work_key FROM spend_reservation WHERE id = :id"
            ),
            {"id": reservation_id},
        ).one_or_none()
    return row


def _reservation_count(engine: Engine, tenant_id: uuid.UUID) -> int:
    """How many reservation rows this tenant owns, committed."""
    with engine.begin() as conn:
        return int(
            conn.execute(
                text("SELECT count(*) FROM spend_reservation WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            ).scalar_one()
        )


def _reserve(
    session_factory: sessionmaker[Session],
    request: ReservationRequest,
    ceilings: SpendCeilings,
) -> SpendReservationReceipt | Refused:
    """Take one reservation in its own session, as a caller would.

    ``reserve`` commits its own transaction (Global Constraint 4), so a fresh
    session per call is the honest shape: nothing here leaks an open
    transaction into the next assertion.
    """
    with session_factory() as session:
        return SpendReservationService(session).reserve(request, ceilings)


def _run_concurrently(
    session_factory: sessionmaker[Session],
    tasks: list[Callable[[Session], object]],
    *,
    timeout: float = 60.0,
) -> list[object]:
    """Run ``tasks`` on real, separate sessions released at the same instant.

    Each task gets its own thread, its own :class:`~sqlalchemy.orm.Session`,
    and therefore its own pooled connection and its own database transaction.
    A :class:`threading.Barrier` holds every thread until the last one has its
    session open, so the contended statement is the first thing each of them
    executes — without it the threads would trickle through in start order and
    the test would pass against a guard that does not exist.

    Args:
        timeout: A generous bound that is nonetheless a bound. PostgreSQL
            detects a genuine deadlock and raises, so this is the backstop for
            a hang deadlock detection does *not* resolve, which would
            otherwise stall CI rather than fail it.

    Returns:
        Each task's return value, in the order the tasks were given. An
        exception inside a task propagates out of this call rather than being
        recorded as a result: a deadlock reported by the driver is a test
        failure, not a datum.
    """
    barrier = threading.Barrier(len(tasks))

    def _run(task: Callable[[Session], object]) -> object:
        with session_factory() as session:
            barrier.wait(timeout=timeout)
            return task(session)

    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        futures = [pool.submit(_run, task) for task in tasks]
        return [future.result(timeout=timeout) for future in futures]


# ---------------------------------------------------------------------------
# 1. The guarded insert — A1's named hole
# ---------------------------------------------------------------------------


def test_first_reservation_over_ceiling_with_no_bucket_row_is_refused(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id: uuid.UUID
) -> None:
    """The very first reservation against a key with no row must still be guarded.

    This is the test A1 names, and the one defect this whole file exists to
    catch. ADR-0006's upsert shape guards only the ``DO UPDATE`` branch: when
    the bucket row already exists, ``reserved + spent + estimate <= ceiling``
    is checked and an over-ceiling reservation is refused. When the row does
    *not* exist yet that branch never runs — the ``INSERT`` simply lands, and a
    first reservation for an estimate already larger than the entire ceiling
    sails through unguarded, creating a bucket that is over its own limit
    before it has served a single request.

    Every ceiling starts with no row, so this is not an edge case; it is what
    every tenant's first paid call hits. Hence three assertions: the call is
    refused, no bucket row was created at all (the guard rejects the insert's
    *source row*, so there is nothing left to insert), and no reservation row
    exists for the tenant.
    """
    job_id = uuid.uuid4()
    key = job_bucket_key(job_id)
    assert _bucket(engine, tenant_id, BucketType.JOB, key) is None, (
        "the bucket must not exist before the call, or this test proves the DO UPDATE branch"
    )

    result = _reserve(
        session_factory,
        _request(tenant_id, job_id, unit_of_work="page-1", estimate=Decimal("5.0000")),
        _ceilings(job=Decimal("2.0000")),
    )

    assert isinstance(result, Refused), (
        "an estimate larger than the ceiling was admitted against a key with no bucket row: "
        "the INSERT's source row is unguarded (ADR-0015 A1, Global Constraint 3)"
    )
    assert result.reason is RefusalReason.CEILING_EXCEEDED
    assert "job" in result.detail
    assert _bucket(engine, tenant_id, BucketType.JOB, key) is None
    assert _reservation_count(engine, tenant_id) == 0


def test_first_reservation_at_exactly_the_ceiling_is_admitted(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id: uuid.UUID
) -> None:
    """The guard is ``<=``, not ``<``.

    The companion to the test above, and the reason it cannot be satisfied by
    refusing every insert: a guard written one comparison too strict would make
    a first reservation for exactly the ceiling impossible, and the
    over-ceiling test above would still pass. Both directions have to be
    pinned or neither is.
    """
    job_id = uuid.uuid4()
    ceiling = Decimal("2.0000")

    result = _reserve(
        session_factory,
        _request(tenant_id, job_id, unit_of_work="page-1", estimate=ceiling),
        _ceilings(job=ceiling),
    )

    assert isinstance(result, SpendReservationReceipt)
    bucket = _bucket(engine, tenant_id, BucketType.JOB, job_bucket_key(job_id))
    assert bucket is not None
    assert bucket.reserved == ceiling
    assert bucket.spent == Decimal("0")


# ---------------------------------------------------------------------------
# 2. All or nothing across the three ceilings
# ---------------------------------------------------------------------------


def test_a_day_ceiling_refusal_leaves_the_job_bucket_untouched(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id: uuid.UUID
) -> None:
    """A refusal on the second ceiling must roll back the first ceiling's debit.

    The debits run one guarded statement per bucket in ``BUCKET_LOCK_ORDER``,
    so by the time the ``tenant_day`` bucket refuses, the ``job`` bucket has
    *already* been debited inside the same transaction. A1's obligation 1 is
    all-or-nothing: a caller refused for the day ceiling must not have quietly
    consumed its job budget on the way there. The failure this catches is a
    ``reserve`` that returns the refusal without rolling back — the tenant's
    per-job budget then drains a little on every refused call, and nothing
    anywhere reports it, because no reservation row was ever written to account
    for it.

    An existing job bucket is established first, so the assertion is on a
    concrete unchanged number rather than on an absent row; an absent row would
    also be produced by a debit that never happened at all.
    """
    job_id = uuid.uuid4()
    admitted = Decimal("1.0000")
    first = _reserve(
        session_factory,
        _request(tenant_id, job_id, unit_of_work="page-1", estimate=admitted),
        _ceilings(job=Decimal("10.0000"), tenant_day=Decimal("10.0000")),
    )
    assert isinstance(first, SpendReservationReceipt)

    # The job ceiling admits this comfortably; the day ceiling cannot, because
    # the first reservation already consumed all but 0.50 of it.
    refused = _reserve(
        session_factory,
        _request(tenant_id, job_id, unit_of_work="page-2", estimate=Decimal("3.0000")),
        _ceilings(job=Decimal("10.0000"), tenant_day=Decimal("1.5000")),
    )

    assert isinstance(refused, Refused)
    assert refused.reason is RefusalReason.CEILING_EXCEEDED
    assert "tenant_day" in refused.detail

    job_bucket = _bucket(engine, tenant_id, BucketType.JOB, job_bucket_key(job_id))
    assert job_bucket is not None
    assert job_bucket.reserved == admitted, (
        "the job bucket kept the refused estimate: the transaction was not rolled back, "
        "so a refusal silently consumed per-job budget (ADR-0015 A1 obligation 1)"
    )
    month_bucket = _bucket(
        engine,
        tenant_id,
        BucketType.TENANT_MONTH,
        tenant_month_bucket_key(tenant_id, NOW.year, NOW.month),
    )
    assert month_bucket is not None
    assert month_bucket.reserved == admitted
    assert _reservation_count(engine, tenant_id) == 1


# ---------------------------------------------------------------------------
# 3. N sessions racing one ceiling that admits K
# ---------------------------------------------------------------------------


def test_concurrent_reservations_admit_exactly_the_ceiling_and_no_more(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id: uuid.UUID
) -> None:
    """Eight real sessions race a ceiling with room for four. Four win.

    This is the property the whole single-conditional-write rule exists for,
    and the only one a sequential test cannot reach. A
    ``SELECT``-then-compare-then-``UPDATE`` passes every test in the unit suite
    and fails here: all eight sessions read ``reserved = 0``, all eight
    conclude there is room, and all eight write — the bucket ends at double its
    ceiling and the tenant is billed for calls no ceiling admitted. A1: *"a
    reservation that is not a single conditional write is not a reservation."*

    Each thread reserves a distinct ``unit_of_work``, so every one derives its
    own work key and the redelivery path — which would also produce "only one
    debit" — cannot be what makes this pass.
    """
    job_id = uuid.uuid4()
    estimate = Decimal("1.0000")
    ceiling = Decimal("4.0000")
    racers = 8
    ceilings = _ceilings(job=ceiling)

    def _task(index: int) -> Callable[[Session], object]:
        def _run(session: Session) -> object:
            return SpendReservationService(session).reserve(
                _request(tenant_id, job_id, unit_of_work=f"page-{index}", estimate=estimate),
                ceilings,
            )

        return _run

    results = _run_concurrently(session_factory, [_task(i) for i in range(racers)])

    receipts = [r for r in results if isinstance(r, SpendReservationReceipt)]
    refusals = [r for r in results if isinstance(r, Refused)]
    assert len(receipts) == 4, (
        f"{len(receipts)} of {racers} racing sessions were admitted against a ceiling with "
        "room for 4: the ceiling debit is not a single conditional write"
    )
    assert len(refusals) == racers - 4
    assert all(r.reason is RefusalReason.CEILING_EXCEEDED for r in refusals)

    bucket = _bucket(engine, tenant_id, BucketType.JOB, job_bucket_key(job_id))
    assert bucket is not None
    assert bucket.reserved + bucket.spent <= bucket.ceiling
    assert bucket.reserved == ceiling
    assert _reservation_count(engine, tenant_id) == 4


# ---------------------------------------------------------------------------
# 4. The fixed lock order under interleaving
# ---------------------------------------------------------------------------


def test_interleaved_reservations_over_shared_buckets_do_not_deadlock(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id: uuid.UUID
) -> None:
    """Reservations and settles across the same three buckets must not deadlock.

    ``BUCKET_LOCK_ORDER`` is fixed in the domain layer — ``job``, then
    ``tenant_day``, then ``tenant_month`` — and both ``reserve`` and
    ``_settle`` iterate it, never a caller-chosen or dict-insertion order. The
    defect that costs is subtle: a future edit that lets one path walk the
    buckets in a different sequence deadlocks only under contention, only
    sometimes, and in production rather than in review.

    The interleaving here is built to find exactly that. Two job buckets share
    one tenant-day and one tenant-month bucket, so every transaction contends
    with every other on the two shared rows while holding a lock on a row the
    others may not want. Half the threads reserve; half reserve and then
    settle, which takes the same three rows a second time in a second
    transaction. If any path walked them in a different order, PostgreSQL's
    deadlock detector would abort one of these transactions and the raised
    error would surface here as a failure rather than as a wrong number.
    """
    job_a, job_b = uuid.uuid4(), uuid.uuid4()
    estimate = Decimal("0.5000")
    settled_actual = Decimal("0.2500")
    ceilings = _ceilings()

    def _reserve_only(index: int, job_id: uuid.UUID) -> Callable[[Session], object]:
        def _run(session: Session) -> object:
            return SpendReservationService(session).reserve(
                _request(tenant_id, job_id, unit_of_work=f"reserve-{index}", estimate=estimate),
                ceilings,
            )

        return _run

    def _reserve_then_reconcile(index: int, job_id: uuid.UUID) -> Callable[[Session], object]:
        def _run(session: Session) -> object:
            service = SpendReservationService(session)
            receipt = service.reserve(
                _request(tenant_id, job_id, unit_of_work=f"settle-{index}", estimate=estimate),
                ceilings,
            )
            assert isinstance(receipt, SpendReservationReceipt)
            return service.reconcile(receipt, actual_cost=settled_actual, now=NOW)

        return _run

    tasks: list[Callable[[Session], object]] = []
    for index in range(4):
        # Alternating jobs, so the two job buckets are contended by different
        # threads while the day and month buckets are contended by all of them.
        reserving_job = job_a if index % 2 == 0 else job_b
        settling_job = job_b if index % 2 == 0 else job_a
        tasks.append(_reserve_only(index, reserving_job))
        tasks.append(_reserve_then_reconcile(index, settling_job))

    results = _run_concurrently(session_factory, tasks)

    assert all(isinstance(r, (SpendReservationReceipt, ReconciledOutcome)) for r in results), (
        f"a transaction failed under interleaving rather than completing: {results}"
    )
    assert _reservation_count(engine, tenant_id) == len(tasks)

    month = _bucket(
        engine,
        tenant_id,
        BucketType.TENANT_MONTH,
        tenant_month_bucket_key(tenant_id, NOW.year, NOW.month),
    )
    assert month is not None
    # Four reservations still held, four settled at `settled_actual` each.
    assert month.reserved == estimate * 4
    assert month.spent == settled_actual * 4


# ---------------------------------------------------------------------------
# 5. Redelivery, one test per state (Global Constraint 8)
# ---------------------------------------------------------------------------


def test_redelivery_of_a_reserved_row_reuses_it_and_debits_nothing_twice(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id: uuid.UUID
) -> None:
    """A redelivered ``reserved`` unit of work is recognised, not charged again.

    At-least-once delivery means the same message arrives twice as a matter of
    routine, not of failure. If the second delivery took a fresh debit, every
    duplicate would consume the ceiling a second time for a call that will be
    made once — the ceiling would refuse legitimate work while the ledger
    quietly disagreed with reality. The receipt must name the *same* row with
    the same lease token, or the second worker holds a token the first one's
    reconcile will not match.
    """
    job_id = uuid.uuid4()
    estimate = Decimal("1.0000")
    request = _request(tenant_id, job_id, unit_of_work="page-1", estimate=estimate)

    first = _reserve(session_factory, request, _ceilings())
    second = _reserve(session_factory, request, _ceilings())

    assert isinstance(first, SpendReservationReceipt)
    assert isinstance(second, SpendReservationReceipt)
    assert second.reservation_id == first.reservation_id
    assert second.lease_token == first.lease_token
    assert second.work_key == first.work_key

    bucket = _bucket(engine, tenant_id, BucketType.JOB, job_bucket_key(job_id))
    assert bucket is not None
    assert bucket.reserved == estimate, "the redelivery took a second debit"
    assert _reservation_count(engine, tenant_id) == 1


def test_redelivery_of_a_reconciled_row_is_refused_as_terminal(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id: uuid.UUID
) -> None:
    """A redelivery after the call was made and paid for is a no-op refusal.

    The work already happened and its real cost is on the row. Re-reserving
    would charge the ceiling twice for one paid call; returning a receipt would
    invite the caller to make the call a second time. The only correct answer
    is to refuse, and the refusal must say *why*: ``ALREADY_TERMINAL`` is a
    different operational situation from a ceiling refusal, and a caller that
    cannot tell them apart will retry the one it must not.
    """
    job_id = uuid.uuid4()
    request = _request(tenant_id, job_id, unit_of_work="page-1", estimate=Decimal("1.0000"))
    receipt = _reserve(session_factory, request, _ceilings())
    assert isinstance(receipt, SpendReservationReceipt)

    with session_factory() as session:
        outcome = SpendReservationService(session).reconcile(
            receipt, actual_cost=Decimal("0.7500"), now=NOW
        )
    assert isinstance(outcome, ReconciledOutcome)

    redelivered = _reserve(session_factory, request, _ceilings())

    assert isinstance(redelivered, Refused)
    assert redelivered.reason is RefusalReason.ALREADY_TERMINAL
    assert _reservation_count(engine, tenant_id) == 1
    bucket = _bucket(engine, tenant_id, BucketType.JOB, job_bucket_key(job_id))
    assert bucket is not None
    assert bucket.reserved == Decimal("0")
    assert bucket.spent == Decimal("0.7500")


def test_redelivery_of_an_expired_row_is_refused_with_expired_no_retry(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id: uuid.UUID
) -> None:
    """An expired reservation may not be silently retried under its old key.

    A1 is explicit that the retry *does not call*: the money may already have
    been spent on the call nobody reported back from, so a redelivery must not
    quietly take a fresh debit and go again. The distinct reason code is the
    deliverable — a caller reading ``EXPIRED_NO_RETRY`` knows it must derive a
    genuinely new unit of work and be re-admitted under the ceiling as it now
    stands, which is not the same instruction as ``CEILING_EXCEEDED`` or
    ``ALREADY_TERMINAL``.
    """
    job_id = uuid.uuid4()
    estimate = Decimal("1.0000")
    request = _request(tenant_id, job_id, unit_of_work="page-1", estimate=estimate)
    receipt = _reserve(session_factory, request, _ceilings())
    assert isinstance(receipt, SpendReservationReceipt)

    with session_factory() as session:
        outcome = SpendReservationService(session).expire_on_timeout(receipt, now=NOW)
    assert isinstance(outcome, ExpiredOutcome)

    redelivered = _reserve(session_factory, request, _ceilings())

    assert isinstance(redelivered, Refused)
    assert redelivered.reason is RefusalReason.EXPIRED_NO_RETRY
    assert _reservation_count(engine, tenant_id) == 1
    bucket = _bucket(engine, tenant_id, BucketType.JOB, job_bucket_key(job_id))
    assert bucket is not None
    assert bucket.spent == estimate, "an expired reservation must be held as spent, not released"


def test_redelivery_after_release_re_reserves_under_the_next_attempt_key(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id: uuid.UUID
) -> None:
    """A released unit of work is never-charged, and re-reserving must work.

    ``released`` is terminal and ``work_key`` is globally unique, so the two
    obvious implementations both fail: reusing the row violates the state
    machine, and reusing the key violates ``uq_spend_reservation_work_key``.
    The persistence layer's answer is the ``base#n`` attempt family documented
    in its module docstring, and this is the only test that proves the scheme
    survives contact with the real constraint — a unit test can compute
    ``base#2`` all day without ever asking PostgreSQL whether it will accept
    it.

    The bucket assertions are the other half: a release credits ``reserved``
    back and moves no ``spent``, so a ceiling exactly one estimate wide must
    admit the re-reservation. If the release had posted spend, this second
    reservation would be refused instead.
    """
    job_id = uuid.uuid4()
    estimate = Decimal("1.0000")
    request = _request(tenant_id, job_id, unit_of_work="page-1", estimate=estimate)
    base_key = derive_work_key(
        tenant_id=tenant_id, job_id=job_id, provider="synthetic", unit_of_work="page-1"
    )

    first = _reserve(session_factory, request, _ceilings(job=estimate))
    assert isinstance(first, SpendReservationReceipt)
    assert first.work_key == base_key

    with session_factory() as session:
        released = SpendReservationService(session).release_before_dispatch(
            first, reason="input vanished before dispatch", now=NOW
        )
    assert isinstance(released, ReleasedOutcome)

    bucket = _bucket(engine, tenant_id, BucketType.JOB, job_bucket_key(job_id))
    assert bucket is not None
    assert bucket.reserved == Decimal("0")
    assert bucket.spent == Decimal("0"), "a release must move no spent"

    second = _reserve(session_factory, request, _ceilings(job=estimate))

    assert isinstance(second, SpendReservationReceipt)
    assert second.reservation_id != first.reservation_id
    assert second.work_key == f"{base_key}#2"
    assert second.lease_token != first.lease_token
    assert _reservation_count(engine, tenant_id) == 2
    reopened = _bucket(engine, tenant_id, BucketType.JOB, job_bucket_key(job_id))
    assert reopened is not None
    assert reopened.reserved == estimate


# ---------------------------------------------------------------------------
# 6. Reconcile idempotency (Global Constraint 9)
# ---------------------------------------------------------------------------


def test_two_reconciles_record_one_actual(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id: uuid.UUID
) -> None:
    """A second reconcile must not post the cost a second time.

    A1 names the case: a late worker and the sweep can reach the same row, and
    so can two deliveries of the same completion message. The guard is the
    ``WHERE ... state = 'reserved'`` on the settle update, and what it protects
    is the bucket, not the row — a second unguarded credit would add
    ``actual_cost`` to ``spent`` again and subtract ``estimate`` from
    ``reserved`` again, driving ``reserved`` negative and inflating recorded
    spend for a single call. The two reconciles run in *separate sessions* so
    the second genuinely re-reads committed state rather than reusing the
    first's identity map.
    """
    job_id = uuid.uuid4()
    estimate = Decimal("1.0000")
    actual = Decimal("0.6000")
    receipt = _reserve(
        session_factory,
        _request(tenant_id, job_id, unit_of_work="page-1", estimate=estimate),
        _ceilings(),
    )
    assert isinstance(receipt, SpendReservationReceipt)

    with session_factory() as session:
        first = SpendReservationService(session).reconcile(receipt, actual_cost=actual, now=NOW)
    with session_factory() as session:
        second = SpendReservationService(session).reconcile(receipt, actual_cost=actual, now=NOW)

    assert isinstance(first, ReconciledOutcome)
    assert first.actual_cost == actual
    assert isinstance(second, AlreadyReconciledOutcome), (
        "the second reconcile was not recognised as already settled"
    )
    assert second.actual_cost == actual

    for bucket_type, key in (
        (BucketType.JOB, job_bucket_key(job_id)),
        (BucketType.TENANT_DAY, tenant_day_bucket_key(tenant_id, NOW.date())),
        (BucketType.TENANT_MONTH, tenant_month_bucket_key(tenant_id, NOW.year, NOW.month)),
    ):
        bucket = _bucket(engine, tenant_id, bucket_type, key)
        assert bucket is not None, f"{bucket_type.value} bucket missing"
        assert bucket.reserved == Decimal("0"), f"{bucket_type.value} was credited twice"
        assert bucket.spent == actual, f"{bucket_type.value} recorded the actual twice"

    row = _reservation(engine, receipt.reservation_id)
    assert row is not None
    assert row.state == SpendReservationState.RECONCILED.value
    assert row.actual_cost == actual
    assert row.actual_is_estimated is False
    assert row.lease_token is None


# ---------------------------------------------------------------------------
# 7. The sweep expires, never releases, and reports once
# ---------------------------------------------------------------------------


def test_the_sweep_expires_an_abandoned_reservation_at_the_reserved_maximum(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id: uuid.UUID
) -> None:
    """An abandoned reservation is held as spent at its maximum, flagged estimated.

    The reservation this models is the expensive one: a worker that committed
    its debit, made the paid call, and died before reporting the cost. A1
    refuses to release it — releasing would hand back budget a provider has
    already billed for, precisely in the case where the system knows least. So
    the sweep writes the full estimate to ``spent`` and sets
    ``actual_is_estimated`` so that figure can never be reported as a real cost
    (Global Constraint 6).

    A second sweep over the same instant must find nothing: the settled row is
    no longer ``reserved``, so it is not selected, and ``review_flagged_at``
    guards the finding behind that. A duplicated finding is not a cosmetic
    problem — each one is a human review of a tenant charged on a guess, and a
    sweep that re-reports on every pass trains its reader to ignore it.
    """
    job_id = uuid.uuid4()
    estimate = Decimal("1.0000")
    receipt = _reserve(
        session_factory,
        _request(tenant_id, job_id, unit_of_work="page-1", estimate=estimate),
        _ceilings(),
    )
    assert isinstance(receipt, SpendReservationReceipt)

    after_lease = NOW + LEASE + timedelta(seconds=1)
    with session_factory() as session:
        findings = [
            finding
            for finding in SpendReservationSweeper(session).sweep(now=after_lease, limit=10)
            # Scoped to this test's tenant: the sweep is deliberately global,
            # and a row left behind by an interrupted earlier run would
            # otherwise be counted as this test's finding.
            if finding.tenant_id == tenant_id
        ]
    with session_factory() as session:
        second_pass = [
            finding
            for finding in SpendReservationSweeper(session).sweep(now=after_lease, limit=10)
            if finding.tenant_id == tenant_id
        ]

    assert len(findings) == 1
    assert findings[0].reservation_id == receipt.reservation_id
    assert second_pass == [], "the second sweep re-reported a reservation it had already settled"

    row = _reservation(engine, receipt.reservation_id)
    assert row is not None
    assert row.state == SpendReservationState.EXPIRED_SPENT.value, (
        "the sweep must never release; A1 admits no exception"
    )
    assert row.actual_cost == estimate
    assert row.actual_is_estimated is True
    assert row.lease_token is None
    assert row.settled_at is not None
    assert row.review_flagged_at is not None

    bucket = _bucket(engine, tenant_id, BucketType.JOB, job_bucket_key(job_id))
    assert bucket is not None
    assert bucket.reserved == Decimal("0")
    assert bucket.spent == estimate


def test_the_sweep_leaves_a_live_reservation_alone(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id: uuid.UUID
) -> None:
    """A reservation whose lease is still in force is not the sweep's to take.

    The bound on the previous test. A sweep whose predicate lost its
    ``lease_expires_at < now`` clause would satisfy every assertion there while
    expiring every live reservation in the system — turning each one into an
    unretryable ``expired_spent`` row underneath a worker that is still
    running.
    """
    job_id = uuid.uuid4()
    receipt = _reserve(
        session_factory,
        _request(tenant_id, job_id, unit_of_work="page-1", estimate=Decimal("1.0000")),
        _ceilings(),
    )
    assert isinstance(receipt, SpendReservationReceipt)

    with session_factory() as session:
        findings = [
            finding
            for finding in SpendReservationSweeper(session).sweep(
                now=NOW + timedelta(minutes=1), limit=10
            )
            if finding.tenant_id == tenant_id
        ]

    assert findings == []
    row = _reservation(engine, receipt.reservation_id)
    assert row is not None
    assert row.state == SpendReservationState.RESERVED.value
    assert row.lease_token is not None


# ---------------------------------------------------------------------------
# 8. An overage posts in full, and closes the bucket
# ---------------------------------------------------------------------------


def test_an_overage_posts_in_full_and_the_next_reservation_is_refused(
    engine: Engine, session_factory: sessionmaker[Session], tenant_id: uuid.UUID
) -> None:
    """A provider that charged more than the estimate is recorded honestly.

    Two rules meet here, and the tempting implementation breaks both. Clamping
    ``spent`` to ``min(actual_cost, estimate)`` would keep the bucket tidily
    under its ceiling and make money the tenant was actually billed disappear
    from the ledger — the one place anyone would look for it. So migration
    ``0010`` carries no ``reserved + spent <= ceiling`` CHECK, on purpose, and
    this test asserts the bucket really does end up over its own ceiling.

    The second half is the consequence: a bucket over its ceiling is closed.
    The next reservation against it — for any amount, however small — must be
    refused by the ``DO UPDATE`` guard, because the overage is recorded rather
    than forgiven. Without that follow-up reservation this test would pass
    against an implementation that posted the overage and then went on serving
    calls out of a budget that no longer exists.
    """
    job_id = uuid.uuid4()
    estimate = Decimal("1.0000")
    ceiling = Decimal("2.0000")
    overage_actual = Decimal("3.0000")

    receipt = _reserve(
        session_factory,
        _request(tenant_id, job_id, unit_of_work="page-1", estimate=estimate),
        _ceilings(job=ceiling),
    )
    assert isinstance(receipt, SpendReservationReceipt)

    with session_factory() as session:
        outcome = SpendReservationService(session).reconcile(
            receipt, actual_cost=overage_actual, now=NOW
        )

    assert isinstance(outcome, ReconciledOutcome)
    assert outcome.actual_cost == overage_actual
    assert outcome.overage == overage_actual - estimate
    assert outcome.review_finding is not None

    bucket = _bucket(engine, tenant_id, BucketType.JOB, job_bucket_key(job_id))
    assert bucket is not None
    assert bucket.spent == overage_actual, "the overage was truncated instead of posted in full"
    assert bucket.spent > bucket.ceiling
    assert bucket.reserved == Decimal("0")

    refused = _reserve(
        session_factory,
        _request(tenant_id, job_id, unit_of_work="page-2", estimate=Decimal("0.0100")),
        _ceilings(job=ceiling),
    )

    assert isinstance(refused, Refused), (
        "a bucket already over its ceiling admitted another reservation: the overage was "
        "posted but not enforced"
    )
    assert refused.reason is RefusalReason.CEILING_EXCEEDED
    assert "job" in refused.detail

    row = _reservation(engine, receipt.reservation_id)
    assert row is not None
    assert row.actual_is_estimated is False, "a reported actual must never be marked estimated"
    assert row.review_flagged_at is not None
