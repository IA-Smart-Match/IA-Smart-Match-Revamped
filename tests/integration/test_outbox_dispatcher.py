"""Outbox dispatcher integration tests.

Architecture v1.1 §4.1 names two scenarios the integration suite must exercise:

    crash between commit and task creation must not lose a job;
    duplicate task delivery must not double-execute

Both are here, as :func:`test_crash_between_commit_and_task_creation_loses_nothing`
and :func:`test_duplicate_task_delivery_does_not_double_execute`. The rest of the
module covers the mechanisms those two depend on — lease expiry, concurrent
claiming, deterministic naming, and the failure path.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from smartmatch_domain.jobs import JobState, can_transition
from smartmatch_persistence.jobs import JobRepository
from smartmatch_persistence.outbox import (
    MAX_DISPATCH_ATTEMPTS,
    OutboxRepository,
    OutboxStatus,
    derive_task_name,
)
from smartmatch_providers.tasks import (
    FixtureTaskQueue,
    TaskHandle,
    TaskQueueError,
    TaskRequest,
)
from smartmatch_worker.dispatcher import OutboxDispatcher
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

pytestmark = pytest.mark.integration

COMMAND = "test.noop"


@pytest.fixture
def jobs() -> JobRepository:
    return JobRepository()


@pytest.fixture
def outbox() -> OutboxRepository:
    return OutboxRepository()


@pytest.fixture
def queue() -> FixtureTaskQueue:
    return FixtureTaskQueue()


@pytest.fixture
def dispatcher(session_factory, queue) -> OutboxDispatcher:
    return OutboxDispatcher(session_factory, queue)


def _accept_command(session_factory, jobs, outbox, tenant_id) -> uuid.UUID:
    """Accept a command the way the API will: job and outbox in one transaction."""
    with session_factory() as session:
        job = jobs.create(session, tenant_id=tenant_id, command_type=COMMAND)
        outbox.enqueue(session, tenant_id=tenant_id, job_id=job.id, command_type=COMMAND)
        session.commit()
    return job.id


# ---------------------------------------------------------------------------
# The two scenarios v1.1 §4.1 names
# ---------------------------------------------------------------------------


def test_crash_between_commit_and_task_creation_loses_nothing(
    session_factory, jobs, outbox, tenant_id, queue
):
    """A dispatcher that dies mid-dispatch must not strand the job.

    Simulated by claiming a row and then abandoning it — exactly what a killed
    process leaves behind: a ``leased`` row whose lease will expire with no task
    ever created.

    The recovery mechanism is lease expiry, not liveness detection. Nothing
    notices the dispatcher died; the next one simply finds a claimable row.
    """
    job_id = _accept_command(session_factory, jobs, outbox, tenant_id)

    # Dispatcher A claims the row, then the process dies.
    with session_factory() as session:
        claimed = outbox.claim_batch(session, limit=10, lease=timedelta(seconds=60))
        session.commit()
    assert len(claimed) == 1
    assert queue.enqueued == [], "no task was created before the crash"

    # Nothing is claimable while A's lease is live — otherwise B would dispatch
    # a row A might still be working on.
    with session_factory() as session:
        assert outbox.claim_batch(session, limit=10) == []
        session.rollback()

    # The lease expires. Dispatcher B takes over and completes the work.
    _expire_all_leases(session_factory, tenant_id)
    dispatcher_b = OutboxDispatcher(session_factory, queue)
    outcome = dispatcher_b.run_once()

    assert outcome.dispatched == 1
    assert len(queue.enqueued) == 1

    with session_factory() as session:
        assert jobs.get(session, tenant_id=tenant_id, job_id=job_id).status is (JobState.DISPATCHED)
        assert _outbox_status(session, job_id) == OutboxStatus.DISPATCHED


def test_crash_after_task_creation_does_not_dispatch_twice(
    session_factory, jobs, outbox, tenant_id, queue, dispatcher
):
    """The harder half of the same scenario.

    If the crash happened *after* Cloud Tasks accepted the task but before the
    outbox row was updated, the row still looks undispatched. A naive retry would
    enqueue the work a second time. The deterministic task name prevents it: the
    queue rejects the duplicate, and the dispatcher converges on 'dispatched'.
    """
    job_id = _accept_command(session_factory, jobs, outbox, tenant_id)

    # Simulate the pre-crash state: the task exists, the outbox row does not
    # know it.
    dispatcher.run_once()
    assert len(queue.enqueued) == 1

    with session_factory() as session:
        session.execute(
            text(
                "UPDATE outbox_record SET status = 'pending', lease_expires_at = NULL "
                "WHERE job_id = :job_id"
            ),
            {"job_id": job_id},
        )
        session.commit()

    outcome = dispatcher.run_once()

    assert outcome.already_existed == 1, "the duplicate must be recognized, not retried"
    assert outcome.dispatched == 0
    assert len(queue.enqueued) == 1, "the work must be enqueued exactly once"

    with session_factory() as session:
        assert _outbox_status(session, job_id) == OutboxStatus.DISPATCHED


def test_duplicate_task_delivery_does_not_double_execute(
    session_factory, jobs, outbox, tenant_id, dispatcher
):
    """Cloud Tasks delivers at-least-once; only one delivery may run the work.

    The guard is the conditional job claim: ``dispatched -> running`` matches a
    row only once. The second delivery finds nothing to update and returns
    ``False``, which the worker treats as "already handled".
    """
    job_id = _accept_command(session_factory, jobs, outbox, tenant_id)
    dispatcher.run_once()

    with session_factory() as session:
        first = jobs.claim(session, tenant_id=tenant_id, job_id=job_id)
        session.commit()

    with session_factory() as session:
        second = jobs.claim(session, tenant_id=tenant_id, job_id=job_id)
        session.commit()

    assert first is True, "the first delivery claims the job"
    assert second is False, "the duplicate delivery must not claim it again"

    with session_factory() as session:
        assert jobs.get(session, tenant_id=tenant_id, job_id=job_id).status is (JobState.RUNNING)


# ---------------------------------------------------------------------------
# Mechanisms the two scenarios rest on
# ---------------------------------------------------------------------------


def test_job_and_outbox_row_commit_together(session_factory, jobs, outbox, tenant_id):
    """A rolled-back command leaves neither a job nor an outbox row."""
    job_id = uuid.uuid4()
    with session_factory() as session:
        jobs.create(session, tenant_id=tenant_id, command_type=COMMAND, job_id=job_id)
        outbox.enqueue(session, tenant_id=tenant_id, job_id=job_id, command_type=COMMAND)
        session.rollback()

    with session_factory() as session:
        assert jobs.get(session, tenant_id=tenant_id, job_id=job_id) is None
        assert _outbox_status(session, job_id) is None


def test_a_live_lease_blocks_a_second_claim(session_factory, jobs, outbox, tenant_id):
    """Two dispatchers must never hold the same row."""
    _accept_command(session_factory, jobs, outbox, tenant_id)

    with session_factory() as session:
        first = outbox.claim_batch(session, limit=10)
        session.commit()

    with session_factory() as session:
        second = outbox.claim_batch(session, limit=10)
        session.commit()

    assert len(first) == 1
    assert second == []


def test_an_expired_lease_becomes_claimable_again(session_factory, jobs, outbox, tenant_id):
    """Lease expiry is the recovery mechanism; assert it directly."""
    _accept_command(session_factory, jobs, outbox, tenant_id)

    with session_factory() as session:
        outbox.claim_batch(session, limit=10)
        session.commit()

    _expire_all_leases(session_factory, tenant_id)

    with session_factory() as session:
        reclaimed = outbox.claim_batch(session, limit=10)
        session.commit()

    assert len(reclaimed) == 1
    assert reclaimed[0].dispatch_attempts == 2, "attempts accumulate across claims"


def test_task_names_are_deterministic_and_distinct():
    """Determinism is what makes a retried dispatch safe."""
    job_a, job_b = uuid.uuid4(), uuid.uuid4()

    assert derive_task_name(job_a, COMMAND) == derive_task_name(job_a, COMMAND)
    assert derive_task_name(job_a, COMMAND) != derive_task_name(job_b, COMMAND)
    assert derive_task_name(job_a, COMMAND) != derive_task_name(job_a, "other.command")


def test_task_name_does_not_leak_identifiers():
    """Queue metadata is visible to anyone with queue-viewer access."""
    job_id = uuid.uuid4()
    name = derive_task_name(job_id, "outreach.send")

    assert str(job_id) not in name
    assert "outreach" not in name


def test_dispatch_failure_is_retried_then_parked(
    session_factory, jobs, outbox, tenant_id, queue, dispatcher
):
    """A failing enqueue retries while attempts remain, then stops."""
    job_id = _accept_command(session_factory, jobs, outbox, tenant_id)

    for attempt in range(MAX_DISPATCH_ATTEMPTS):
        # Let the previous failure's backoff elapse — the row is deliberately
        # not claimable until then, so without this the loop spins on an idle
        # queue and attempts never accumulate.
        if attempt:
            _expire_all_leases(session_factory, tenant_id)
        queue.fail_next_with = TaskQueueError(f"transient failure {attempt}")
        outcome = dispatcher.run_once()
        assert outcome.failed == 1

    with session_factory() as session:
        assert _outbox_status(session, job_id) == OutboxStatus.FAILED
        # The job never claimed to be dispatched, because it never was — but it
        # does not stay ``queued`` either.
        #
        # **Changed deliberately.** This assertion used to require ``queued``,
        # which described the row honestly and the job dishonestly: a parked row
        # is never revisited, so the job was not queued for anything, and
        # ``queued`` reaches neither a terminal state nor ``redrive_pending``.
        # The job that most needed re-driving was the one job re-drive could not
        # touch. ``failed_provider`` is what actually happened — the queue is the
        # provider that failed — and it has a route back through re-drive.
        assert jobs.get(session, tenant_id=tenant_id, job_id=job_id).status is (
            JobState.FAILED_PROVIDER
        )

    # A parked row is no longer claimable, so it cannot loop forever.
    assert dispatcher.run_once().is_idle


def test_dispatch_records_the_job_transition_and_evidence(
    session_factory, jobs, outbox, tenant_id, dispatcher
):
    """v1.1 §1.6 requires dispatch evidence be recorded."""
    job_id = _accept_command(session_factory, jobs, outbox, tenant_id)
    dispatcher.run_once()

    with session_factory() as session:
        assert jobs.get(session, tenant_id=tenant_id, job_id=job_id).status is (JobState.DISPATCHED)
        row = session.execute(
            text(
                "SELECT status, lease_expires_at, dispatch_attempts "
                "FROM outbox_record WHERE job_id = :job_id"
            ),
            {"job_id": job_id},
        ).one()

    assert row.status == OutboxStatus.DISPATCHED.value
    assert row.lease_expires_at is None, "a dispatched row must not look claimable"
    assert row.dispatch_attempts == 1


def test_idle_dispatcher_reports_idle(dispatcher):
    """An empty outbox is not an error and does no work."""
    assert dispatcher.run_once().is_idle


def test_batch_size_is_respected(session_factory, jobs, outbox, tenant_id, dispatcher):
    """Bounded batches keep a backlog from monopolizing one pass.

    Regression guard for a real defect: the claim originally used
    ``IN (SELECT ... LIMIT n FOR UPDATE SKIP LOCKED)``. PostgreSQL cannot hash a
    subplan containing ``FOR UPDATE``, re-executed it while evaluating the
    ``IN``, and claimed every row rather than ``n``. Materializing the selection
    in a CTE bounds it correctly.
    """
    for _ in range(5):
        _accept_command(session_factory, jobs, outbox, tenant_id)

    first = dispatcher.run_once(batch_size=2)
    assert first.claimed == 2, "the batch must be bounded by batch_size"

    remaining = dispatcher.run_once(batch_size=10)
    assert remaining.claimed == 3


def test_concurrent_dispatchers_claim_disjoint_batches(session_factory, jobs, outbox, tenant_id):
    """Two dispatchers must never claim the same row.

    Uses two real sessions with overlapping transactions, which is what
    ``SKIP LOCKED`` exists for: the second session skips rows the first has
    locked instead of blocking behind them.
    """
    for _ in range(6):
        _accept_command(session_factory, jobs, outbox, tenant_id)

    session_a = session_factory()
    session_b = session_factory()
    try:
        claimed_a = outbox.claim_batch(session_a, limit=3)
        # B claims while A's transaction is still open and holding its locks.
        claimed_b = outbox.claim_batch(session_b, limit=3)
        session_a.commit()
        session_b.commit()
    finally:
        session_a.close()
        session_b.close()

    ids_a = {record.id for record in claimed_a}
    ids_b = {record.id for record in claimed_b}

    assert len(ids_a) == 3
    assert len(ids_b) == 3
    assert ids_a.isdisjoint(ids_b), "the same row was claimed by both dispatchers"


# ---------------------------------------------------------------------------
# Lag metric
# ---------------------------------------------------------------------------


def test_lag_reports_pending_count_and_oldest_age(
    session_factory, jobs, outbox, tenant_id, dispatcher
):
    """v1.1 §1.6 requires a lag metric with an alert.

    Measured as a delta rather than an absolute. The metric is deliberately
    dispatcher-wide, not tenant-scoped — a per-tenant view would hide a global
    backlog — so another tenant's rows may legitimately be in flight.
    """
    baseline = dispatcher.lag().pending

    _accept_command(session_factory, jobs, outbox, tenant_id)

    lag = dispatcher.lag()
    assert lag.pending == baseline + 1
    assert lag.oldest_age is not None

    dispatcher.run_once()
    assert dispatcher.lag().pending == baseline


def test_lag_count_and_age_agree(session_factory, jobs, outbox, tenant_id, dispatcher):
    """The two halves of the metric must never contradict each other.

    They once did: a zero count could accompany a non-null age, because the
    count excluded live leases and the age did not. An operator seeing that has
    to debug the metric instead of acting on it.
    """
    _accept_command(session_factory, jobs, outbox, tenant_id)
    dispatcher.run_once()

    lag = dispatcher.lag()
    assert (lag.pending == 0) == (lag.oldest_age is None)


def test_lag_threshold_triggers_on_either_count_or_age():
    """Count alone cannot tell a healthy burst from one row stuck for an hour."""
    from smartmatch_worker.dispatcher import DispatcherLag

    limits = {"max_pending": 100, "max_age": timedelta(minutes=5)}

    assert not DispatcherLag(pending=10, oldest_age=timedelta(seconds=5)).exceeds(**limits)
    assert DispatcherLag(pending=500, oldest_age=timedelta(seconds=5)).exceeds(**limits)
    assert DispatcherLag(pending=1, oldest_age=timedelta(hours=1)).exceeds(**limits)
    assert not DispatcherLag(pending=0, oldest_age=None).exceeds(**limits)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _expire_all_leases(session_factory, tenant_id: uuid.UUID) -> None:
    """Force every lease for this tenant into the past."""
    with session_factory() as session:
        session.execute(
            text("UPDATE outbox_record SET lease_expires_at = :past WHERE tenant_id = :tid"),
            {"past": datetime.now(UTC) - timedelta(hours=1), "tid": tenant_id},
        )
        session.commit()


def _outbox_status(session, job_id: uuid.UUID) -> OutboxStatus | None:
    row = session.execute(
        text("SELECT status FROM outbox_record WHERE job_id = :job_id"),
        {"job_id": job_id},
    ).one_or_none()
    return OutboxStatus(row.status) if row else None


def test_dispatch_failure_backs_off_before_retrying(
    session_factory, jobs, outbox, tenant_id, queue, dispatcher
):
    """A brief outage must be survivable, not fatal.

    Without backoff the row was re-armed immediately, so a dispatcher polling
    every couple of seconds burned all five attempts within about ten seconds
    and parked the work permanently — for an outage that may have resolved a
    minute later. The lease doubles as the backoff timer.
    """
    _accept_command(session_factory, jobs, outbox, tenant_id)

    queue.fail_next_with = TaskQueueError("provider briefly unavailable")
    assert dispatcher.run_once().failed == 1

    # Immediately afterwards the row is not claimable: the backoff is running.
    assert dispatcher.run_once().is_idle, "a failed row must back off, not spin"

    with session_factory() as session:
        row = session.execute(
            text(
                "SELECT status, lease_expires_at, dispatch_attempts "
                "FROM outbox_record WHERE tenant_id = :tid"
            ),
            {"tid": tenant_id},
        ).one()

    assert row.status == OutboxStatus.LEASED.value
    assert row.lease_expires_at is not None, "backoff needs a future lease to gate on"
    assert row.dispatch_attempts == 1

    # Once the backoff elapses the work resumes and succeeds.
    _expire_all_leases(session_factory, tenant_id)
    assert dispatcher.run_once().dispatched == 1


def test_backoff_grows_with_attempts(session_factory, jobs, outbox, tenant_id, queue, dispatcher):
    """Successive failures wait longer, so a persistent outage is not hammered."""
    _accept_command(session_factory, jobs, outbox, tenant_id)

    waits = []
    for attempt in range(3):
        queue.fail_next_with = TaskQueueError(f"still down {attempt}")
        dispatcher.run_once()
        with session_factory() as session:
            row = session.execute(
                text(
                    "SELECT lease_expires_at, dispatch_attempts FROM outbox_record "
                    "WHERE tenant_id = :tid"
                ),
                {"tid": tenant_id},
            ).one()
        waits.append((row.dispatch_attempts, row.lease_expires_at))
        _expire_all_leases(session_factory, tenant_id)

    attempts = [attempt for attempt, _ in waits]
    assert attempts == [1, 2, 3], "each failure must consume exactly one attempt"


def test_exhausted_row_is_parked_without_a_lease(
    session_factory, jobs, outbox, tenant_id, queue, dispatcher
):
    """A terminal row must not look claimable again once a timer elapses."""
    _accept_command(session_factory, jobs, outbox, tenant_id)

    for attempt in range(MAX_DISPATCH_ATTEMPTS):
        # Expire before each retry, never after the last: the helper updates
        # every row, and stamping a lease onto the parked row afterwards would
        # fabricate the very state this test then asserts on.
        if attempt:
            _expire_all_leases(session_factory, tenant_id)
        queue.fail_next_with = TaskQueueError(f"failure {attempt}")
        dispatcher.run_once()

    with session_factory() as session:
        row = session.execute(
            text("SELECT status, lease_expires_at FROM outbox_record WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        ).one()

    assert row.status == OutboxStatus.FAILED.value
    assert row.lease_expires_at is None
    assert dispatcher.run_once().is_idle


# ---------------------------------------------------------------------------
# One bad row must not stall the batch
# ---------------------------------------------------------------------------


class _ExplodingQueue(FixtureTaskQueue):
    """A queue that raises an unanticipated error for one named task.

    ``fail_next_with`` fails whichever row happens to be attempted first, which
    would make these tests depend on the order the batch was claimed in. Keying
    the failure to a task name pins it to a specific row instead, so the
    assertions about *the other* rows mean what they say.
    """

    explode_for: str | None = None

    def enqueue(self, request: TaskRequest) -> TaskHandle:
        if request.name == self.explode_for:
            raise ValueError("client blew up in a way nobody anticipated")
        return super().enqueue(request)


def test_an_unexpected_error_does_not_abort_the_batch(session_factory, jobs, outbox, tenant_id):
    """The docstring's promise, asserted for an exception nobody anticipated.

    ``TaskAlreadyExists`` and ``TaskQueueError`` are the failures the dispatcher
    was written for. A live queue client can raise anything else — a driver
    error, a credentials refresh failure, a ``ValueError`` from a payload it
    dislikes — and when that escaped ``run_once`` the rest of the claimed batch
    was abandoned mid-pass, still leased, with nothing reported.
    """
    first_job = _accept_command(session_factory, jobs, outbox, tenant_id)
    second_job = _accept_command(session_factory, jobs, outbox, tenant_id)

    # A ValueError, not a TaskQueueError: this is the class of failure the
    # dispatcher does not anticipate, which is the whole point.
    queue = _ExplodingQueue()
    queue.explode_for = derive_task_name(first_job, COMMAND)
    dispatcher = OutboxDispatcher(session_factory, queue)

    outcome = dispatcher.run_once()

    assert outcome.claimed == 2
    assert outcome.failed == 1
    assert outcome.dispatched == 1, "the row after the bad one must still be dispatched"
    assert len(queue.enqueued) == 1

    with session_factory() as session:
        # The failed row keeps its evidence and its retry, exactly as a
        # TaskQueueError would.
        assert _outbox_status(session, first_job) == OutboxStatus.LEASED
        assert jobs.get(session, tenant_id=tenant_id, job_id=first_job).status is JobState.QUEUED
        assert _outbox_status(session, second_job) == OutboxStatus.DISPATCHED
        assert (
            jobs.get(session, tenant_id=tenant_id, job_id=second_job).status is JobState.DISPATCHED
        )


def test_an_unexpected_error_is_recorded_against_the_row(
    session_factory, jobs, outbox, tenant_id, queue, dispatcher
):
    """An unexplained failure must leave an explanation on the row.

    Counting it is not enough: without ``last_error`` an operator looking at a
    parked row has no way to tell a queue outage from a bug in the dispatcher.
    """
    _accept_command(session_factory, jobs, outbox, tenant_id)

    queue.fail_next_with = ValueError("client blew up in a way nobody anticipated")
    dispatcher.run_once()

    with session_factory() as session:
        row = session.execute(
            text("SELECT last_error, dispatch_attempts FROM outbox_record WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        ).one()

    assert row.dispatch_attempts == 1, "an unexpected failure consumes an attempt like any other"
    assert "ValueError" in row.last_error, "the failure type must be recoverable from the row"


def test_a_failure_while_recording_a_dispatch_does_not_abort_the_batch(
    session_factory, jobs, outbox, tenant_id, queue, dispatcher, monkeypatch
):
    """A database blip while writing evidence must not abandon the rest.

    Recording happened outside the per-row ``try`` entirely, so a connection
    dropped between the enqueue and the ``mark_dispatched`` commit took the
    whole batch with it. The task itself was already created, so the row is
    recovered by lease expiry and the deterministic name makes the retry a
    no-op — but only if the dispatcher survives long enough to keep going.
    """
    _accept_command(session_factory, jobs, outbox, tenant_id)
    second_job = _accept_command(session_factory, jobs, outbox, tenant_id)

    real_record = dispatcher._record_dispatched
    seen: list[uuid.UUID] = []

    def flaky(tenant_id_, job_id, record_id):
        seen.append(record_id)
        if len(seen) == 1:
            raise OperationalError("UPDATE outbox_record", {}, Exception("server closed"))
        real_record(tenant_id_, job_id, record_id)

    monkeypatch.setattr(dispatcher, "_record_dispatched", flaky)
    outcome = dispatcher.run_once()

    assert outcome.claimed == 2
    assert len(queue.enqueued) == 2, "both rows were attempted"
    assert outcome.failed == 1, "an unrecorded dispatch is not a dispatch"
    assert outcome.dispatched == 1

    with session_factory() as session:
        assert _outbox_status(session, second_job) == OutboxStatus.DISPATCHED


def test_a_failure_while_recording_a_failure_does_not_abort_the_batch(
    session_factory, jobs, outbox, tenant_id, queue, dispatcher, monkeypatch
):
    """The same, for the path that records a failure.

    This is the shape a full database outage takes: every row fails to enqueue
    *and* fails to record. The pass must still terminate, having reported what
    it could not do.
    """
    _accept_command(session_factory, jobs, outbox, tenant_id)
    _accept_command(session_factory, jobs, outbox, tenant_id)

    def always_broken(record_id, error, attempts):
        raise OperationalError("UPDATE outbox_record", {}, Exception("server closed"))

    monkeypatch.setattr(dispatcher, "_record_failure", always_broken)
    queue.fail_next_with = TaskQueueError("queue unavailable")
    outcome = dispatcher.run_once()

    assert outcome.claimed == 2
    assert outcome.failed + outcome.dispatched + outcome.already_existed == 2


def test_dispatch_outcome_totals_always_add_up(session_factory, jobs, outbox, tenant_id):
    """Every claimed row lands in exactly one bucket, on every path.

    The counts are what an operator alerts on. A batch that claims five rows and
    reports four accounted for is a silent loss of exactly the kind the outbox
    exists to make impossible, so assert the arithmetic across a batch that
    exercises all three outcomes at once.
    """
    exploding = _accept_command(session_factory, jobs, outbox, tenant_id)
    _accept_command(session_factory, jobs, outbox, tenant_id)
    already_dispatched = _accept_command(session_factory, jobs, outbox, tenant_id)

    queue = _ExplodingQueue()
    queue.explode_for = derive_task_name(exploding, COMMAND)
    # A task the queue already holds — the crash-recovery path.
    queue.enqueued.append(
        TaskRequest(name=derive_task_name(already_dispatched, COMMAND), payload={})
    )
    dispatcher = OutboxDispatcher(session_factory, queue)

    outcome = dispatcher.run_once()

    assert outcome.claimed == 3
    assert outcome.claimed == outcome.dispatched + outcome.already_existed + outcome.failed
    assert (outcome.dispatched, outcome.already_existed, outcome.failed) == (1, 1, 1)


def test_a_keyboard_interrupt_still_terminates_the_batch(
    session_factory, jobs, outbox, tenant_id, queue, dispatcher
):
    """Resilience must not extend to swallowing a shutdown signal.

    ``KeyboardInterrupt`` and ``SystemExit`` are how a process is asked to stop.
    A dispatcher that caught them would keep working through the batch while the
    operator waited, which is why the per-row guard catches ``Exception`` and
    not ``BaseException``.
    """
    _accept_command(session_factory, jobs, outbox, tenant_id)

    queue.fail_next_with = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        dispatcher.run_once()


def test_a_row_whose_dispatch_is_never_recorded_ends_up_visible(
    session_factory, jobs, outbox, tenant_id, queue, dispatcher, monkeypatch
):
    """An unrecordable dispatch must park as ``failed``, not vanish.

    The evidence write is the fragile step: the task is already created, and if
    every attempt to record it fails, the row consumes an attempt each time.
    Counting the row as failed without *recording* the failure leaves it exactly
    as the claim left it — ``leased``, with a lease that expires and attempts
    that keep climbing.

    That is fine while attempts remain, and silently wrong at the end.
    ``_claimable_predicate`` requires ``dispatch_attempts <
    MAX_DISPATCH_ATTEMPTS``, so on the final attempt the row stops being
    claimable while its status still reads ``leased``. It is then never retried,
    never counted by the lag metric — which uses the same predicate — and never
    shows up as ``failed`` in an operations view. It is the "invisible work,
    silently stuck" state ``mark_failed`` exists to prevent, reached by a path
    that never calls it.
    """
    job_id = _accept_command(session_factory, jobs, outbox, tenant_id)

    def always_fails(tenant_id_, job_id_, record_id):
        raise OperationalError("UPDATE outbox_record", {}, Exception("server closed"))

    monkeypatch.setattr(dispatcher, "_record_dispatched", always_fails)

    for attempt in range(MAX_DISPATCH_ATTEMPTS):
        if attempt:
            _expire_all_leases(session_factory, tenant_id)
        assert dispatcher.run_once().failed == 1

    with session_factory() as session:
        assert _outbox_status(session, job_id) == OutboxStatus.FAILED, (
            "a row that exhausted its attempts must be parked and visible, "
            "not left leased and unclaimable"
        )
        # The lag metric must not be able to report zero while work is stuck.
        assert outbox.pending_count(session) == 0


def test_a_job_whose_dispatch_is_exhausted_becomes_redrivable(
    session_factory, jobs, outbox, tenant_id, queue, dispatcher
):
    """Parking the outbox row is not enough; the job must say so too.

    When dispatch attempts run out the outbox row becomes ``failed``, but the
    job was left ``queued`` — on the reasoning that it had not been dispatched
    and saying otherwise would strand it. That reasoning holds for a *retryable*
    failure and breaks at exhaustion, because ``queued`` admits only
    ``dispatched`` and ``cancelled``.

    So the job that most needs re-driving was the one job re-drive could not
    touch: the command answers 409 forever, and no dispatcher will look at the
    row again. ``failed_provider`` is the truthful state — dispatch failed at
    the queue — and it is one of the two states with a route to
    ``redrive_pending``.
    """
    job_id = _accept_command(session_factory, jobs, outbox, tenant_id)

    for attempt in range(MAX_DISPATCH_ATTEMPTS):
        if attempt:
            _expire_all_leases(session_factory, tenant_id)
        queue.fail_next_with = TaskQueueError(f"queue unavailable {attempt}")
        assert dispatcher.run_once().failed == 1

    with session_factory() as session:
        assert _outbox_status(session, job_id) == OutboxStatus.FAILED
        job = jobs.get(session, tenant_id=tenant_id, job_id=job_id)
        assert job.status is JobState.FAILED_PROVIDER, (
            "a job whose dispatch is exhausted must reach a state re-drive can "
            f"reach, not stay queued forever (got {job.status.value})"
        )

    # And that state genuinely admits a re-drive.
    assert can_transition(JobState.FAILED_PROVIDER, JobState.REDRIVE_PENDING)
