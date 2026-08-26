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

import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from smartmatch_domain.jobs import JobState, can_transition
from smartmatch_persistence.jobs import JobRepository
from smartmatch_persistence.outbox import (
    MAX_DISPATCH_ATTEMPTS,
    OutboxRepository,
    OutboxStatus,
    backoff_for,
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


def test_a_claimed_batch_arrives_oldest_first(session_factory, jobs, outbox, tenant_id):
    """The FIFO order :meth:`claim_batch` documents must be real, not incidental.

    The claim selects the oldest rows inside a CTE that sorts by ``created_at``,
    but hands them back through ``UPDATE ... RETURNING``, whose output order SQL
    does not define. PostgreSQL plans the update as a hash join whose outer side
    is a sequential scan of ``outbox_record``, so unsorted results arrive in
    *heap* order — and heap order stops matching ``created_at`` order the moment
    an update rewrites an older row's tuple behind a newer one, which is the
    ordinary life of an outbox row that has been claimed, failed and re-armed.

    So the setup deliberately drives the two orders apart: every row is created,
    then the older half is rewritten in place, moving its live tuples to the end
    of the heap. Before the sort in :meth:`claim_batch` this returned newest
    first (J13).
    """
    job_ids = [_accept_command(session_factory, jobs, outbox, tenant_id) for _ in range(8)]
    older_half = job_ids[:4]

    # Rewrite the older rows so their live tuples land physically after the
    # newer ones. Any update does this; PostgreSQL never updates a tuple in
    # place. ``last_error`` is not read by the claim predicate, so this changes
    # heap layout and nothing else.
    with session_factory() as session:
        session.execute(
            text("UPDATE outbox_record SET last_error = 'heap churn' WHERE job_id = ANY(:ids)"),
            {"ids": older_half},
        )
        session.commit()

    with session_factory() as session:
        heap_order = [
            row[0]
            for row in session.execute(text("SELECT job_id FROM outbox_record ORDER BY ctid"))
        ]
        claimed = outbox.claim_batch(session, limit=10)
        session.commit()

    assert heap_order != job_ids, "setup failed: heap order still matches creation order"
    assert [record.job_id for record in claimed] == job_ids, "claims must arrive oldest first"


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

    The failure is injected against a *named* job rather than against whichever
    call happens to come first. Keying on the call ordinal quietly turned this
    into an assertion about claim order, which is not what it is here to check,
    and it failed roughly one module run in thirty whenever the batch came back
    in the other order (J13). Naming the job keeps the test about the thing it
    describes; the ordering guarantee is asserted on its own in
    :func:`test_a_claimed_batch_arrives_oldest_first`.
    """
    broken_job = _accept_command(session_factory, jobs, outbox, tenant_id)
    second_job = _accept_command(session_factory, jobs, outbox, tenant_id)

    real_record = dispatcher._record_dispatched

    def flaky(tenant_id_, job_id, record_id, *, lease_token):
        if job_id == broken_job:
            raise OperationalError("UPDATE outbox_record", {}, Exception("server closed"))
        # Returned, not discarded: ``_record_dispatched`` answers whether this
        # dispatcher still owned the row, and a stand-in that swallowed that
        # would make every delegated call look like a lost race. The lease token
        # is forwarded for the same reason — dropping it would make the real
        # call lose its own compare-and-set (J17).
        return real_record(tenant_id_, job_id, record_id, lease_token=lease_token)

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
    ``dispatched``, ``cancelled`` and ``failed_provider`` — but not
    ``redrive_pending``, so re-drive is refused too.

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


def _outbox_row(session_factory, job_id: uuid.UUID):
    with session_factory() as session:
        return session.execute(
            text(
                "SELECT status, dispatch_attempts, lease_expires_at, lease_token, "
                "last_error FROM outbox_record WHERE job_id = :job_id"
            ),
            {"job_id": job_id},
        ).one()


def _claim_and_walk_away(session_factory, outbox, tenant_id) -> None:
    """Claim every claimable row, commit the lease, and record no outcome.

    Exactly what a dispatcher killed between the claim's commit and the outcome
    write leaves behind — a SIGKILL, an evicted pod, an OOM, a drained node.
    :func:`test_crash_between_commit_and_task_creation_loses_nothing` already
    uses this technique for a single crash; the stranding tests repeat it to
    exhaustion, because that is the attempt on which it stops being survivable.
    """
    _expire_all_leases(session_factory, tenant_id)
    with session_factory() as session:
        outbox.claim_batch(session, limit=10)
        session.commit()


def test_a_row_stranded_on_its_last_attempt_is_reclaimed(
    session_factory, jobs, outbox, tenant_id, dispatcher
):
    """Attempts exhausted while ``leased`` is a dead end, and must not be.

    **No fault injection.** The dispatcher is never made to fail; it is simply
    never given the chance to record anything, which is what process death looks
    like from the database's side. That matters because the swallowed
    failure-write is the route that is easy to test and process death is the
    route that is likely — a deployment, an autoscale event, an OOM — and a fix
    that only closed the testable one would leave the likely one open.

    On the fifth claim ``dispatch_attempts`` reaches ``MAX_DISPATCH_ATTEMPTS``,
    and ``_claimable_predicate`` requires strictly fewer. The row is then
    ``leased`` forever: never re-claimed, never counted by the lag metric that
    shares that predicate, never visible as ``failed``, and its job stuck
    ``queued`` — which ``TRANSITIONS`` routes only to ``dispatched`` and
    ``cancelled``, so re-drive answers 409 on it forever. Invisible work whose
    only symptom is a job that never finishes.
    """
    job_id = _accept_command(session_factory, jobs, outbox, tenant_id)

    for _ in range(MAX_DISPATCH_ATTEMPTS):
        _claim_and_walk_away(session_factory, outbox, tenant_id)

    # The hole, asserted before it is closed. Every one of these passes today.
    stranded = _outbox_row(session_factory, job_id)
    assert stranded.status == OutboxStatus.LEASED.value
    assert stranded.dispatch_attempts == MAX_DISPATCH_ATTEMPTS
    with session_factory() as session:
        assert outbox.claim_batch(session, limit=10) == [], "no dispatcher will claim it again"
        assert outbox.pending_count(session) == 0, "and the lag metric cannot see it"
        assert jobs.get(session, tenant_id=tenant_id, job_id=job_id).status == JobState.QUEUED

    _expire_all_leases(session_factory, tenant_id)
    outcome = dispatcher.run_once()

    assert outcome.reclaimed == 1, "a stranded row is a real signal and must be countable"

    reclaimed = _outbox_row(session_factory, job_id)
    assert reclaimed.status == OutboxStatus.FAILED.value, (
        "a row nothing will ever claim again must be visible as failed"
    )
    assert reclaimed.lease_expires_at is None, "a terminal row must not look claimable later"
    assert "no outcome" in (reclaimed.last_error or ""), (
        "the text must say the final attempt recorded nothing, not repeat the "
        "previous attempt's error as though the queue had rejected it"
    )

    with session_factory() as session:
        job = jobs.get(session, tenant_id=tenant_id, job_id=job_id)
    assert job.status == JobState.FAILED_PROVIDER
    assert can_transition(job.status, JobState.REDRIVE_PENDING), (
        "reclaiming is worth nothing if the operator still cannot act on it"
    )


def test_a_row_whose_failure_is_never_recorded_ends_up_visible(
    session_factory, jobs, outbox, tenant_id, queue, dispatcher, monkeypatch
):
    """The other route in: the failure-write itself never lands.

    The sibling of :func:`test_a_row_whose_dispatch_is_never_recorded_ends_up_visible`,
    which covers the case where only ``_record_dispatched`` fails and
    ``_record_failure`` still parks the row. Here the parking write is the one
    that fails, on every attempt including the last — a database unreachable for
    the whole of a queue outage — so nothing ever writes the row's outcome.

    ``_record_failure_safely`` swallowing the error is correct and stays: one
    row's failure must not cost the rest of the batch their attempt. What was
    missing is the thing that makes swallowing safe on the final attempt.
    """
    job_id = _accept_command(session_factory, jobs, outbox, tenant_id)

    def always_fails(record, error, attempts):
        raise OperationalError("UPDATE outbox_record", {}, Exception("server closed"))

    monkeypatch.setattr(dispatcher, "_record_failure", always_fails)

    for attempt in range(MAX_DISPATCH_ATTEMPTS):
        if attempt:
            _expire_all_leases(session_factory, tenant_id)
        queue.fail_next_with = TaskQueueError("queue unavailable")
        assert dispatcher.run_once().failed == 1

    assert _outbox_row(session_factory, job_id).status == OutboxStatus.LEASED.value

    monkeypatch.undo()
    _expire_all_leases(session_factory, tenant_id)
    outcome = dispatcher.run_once()

    assert outcome.reclaimed == 1
    assert _outbox_row(session_factory, job_id).status == OutboxStatus.FAILED.value
    with session_factory() as session:
        assert jobs.get(session, tenant_id=tenant_id, job_id=job_id).status == (
            JobState.FAILED_PROVIDER
        )


def test_a_live_lease_blocks_a_reclaim(session_factory, jobs, outbox, tenant_id, dispatcher):
    """The reclaim must never touch a row a dispatcher is still working on.

    This is the worst thing the reclaim could do: mark a row ``failed`` and park
    its job while a live dispatcher is mid-enqueue, producing exactly the
    "failed job beside a live row" that ``_record_failure`` shares a transaction
    to prevent. The guard is the same one the ordinary recovery path relies on —
    ``lease_expires_at < now`` — and it deserves its own assertion rather than
    being inferred from the claim path's.
    """
    job_id = _accept_command(session_factory, jobs, outbox, tenant_id)

    for _ in range(MAX_DISPATCH_ATTEMPTS):
        _claim_and_walk_away(session_factory, outbox, tenant_id)

    # Attempts are exhausted, but the last claim's lease is still running.
    with session_factory() as session:
        session.execute(
            text("UPDATE outbox_record SET lease_expires_at = :future WHERE tenant_id = :tid"),
            {"future": datetime.now(UTC) + timedelta(hours=1), "tid": tenant_id},
        )
        session.commit()

    assert dispatcher.run_once().reclaimed == 0, "a live lease is not stranded work"
    assert _outbox_row(session_factory, job_id).status == OutboxStatus.LEASED.value
    with session_factory() as session:
        assert jobs.get(session, tenant_id=tenant_id, job_id=job_id).status == JobState.QUEUED


def test_a_leased_row_with_no_lease_is_left_alone(
    session_factory, jobs, outbox, tenant_id, dispatcher
):
    """A row whose state is not understood is not something to write off.

    ADR-0005's invariant says a ``leased`` row always carries a lease, so this
    row should not exist. If one ever does, the reclaim's ``lease_expires_at <
    now`` skips it, because NULL never satisfies a comparison. That is the right
    conservative behaviour — do not park work whose state nothing can explain —
    but it falls out of SQL's NULL semantics rather than from anything a reader
    can see, so it is asserted here rather than left to be rediscovered.
    """
    job_id = _accept_command(session_factory, jobs, outbox, tenant_id)

    for _ in range(MAX_DISPATCH_ATTEMPTS):
        _claim_and_walk_away(session_factory, outbox, tenant_id)

    with session_factory() as session:
        session.execute(
            text("UPDATE outbox_record SET lease_expires_at = NULL WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )
        session.commit()

    assert dispatcher.run_once().reclaimed == 0
    assert _outbox_row(session_factory, job_id).status == OutboxStatus.LEASED.value


def test_a_reclaimed_row_is_not_resurrected_by_a_late_dispatch(
    session_factory, jobs, outbox, tenant_id, dispatcher
):
    """An expired lease is not proof the dispatcher holding it is dead.

    The reclaim treats it as proof, and mostly it is. But the lease bounds how
    long a dispatcher may *hold* a row, not how long Cloud Tasks may take to
    answer, so with two instances and a slow batch dispatcher A can still be
    mid-enqueue on a row that dispatcher B has just written off. A then records
    its dispatch over the top.

    Without a guard the write lands, because ``mark_dispatched`` filtered on the
    row id alone: the row goes back to ``dispatched`` while the job stays
    ``failed_provider``, since A's conditional ``queued -> dispatched``
    transition no-ops against a job B has already parked. That is exactly the
    "failed job beside a live row" that ``_record_failure`` shares a transaction
    to prevent, produced by the very mechanism added to prevent it.

    **Exactly-once is not at risk here and this test says so explicitly.** The
    task may well exist in the queue, but a job in ``failed_provider`` cannot be
    claimed — :meth:`JobRepository.claim` requires ``dispatched`` — so the
    delivery is acknowledged and executes nothing. The defect is the inconsistent
    state and the work made invisible by it, not double execution.
    """
    job_id = _accept_command(session_factory, jobs, outbox, tenant_id)

    for _ in range(MAX_DISPATCH_ATTEMPTS - 1):
        _claim_and_walk_away(session_factory, outbox, tenant_id)

    # Dispatcher A claims the final attempt and begins a slow enqueue.
    _expire_all_leases(session_factory, tenant_id)
    with session_factory() as session:
        claimed = outbox.claim_batch(session, limit=10)
        session.commit()
    assert len(claimed) == 1
    record = claimed[0]
    assert record.dispatch_attempts == MAX_DISPATCH_ATTEMPTS

    # The enqueue outlives the lease. Nothing exotic: a slow provider call, a
    # paused container, a long GC.
    _expire_all_leases(session_factory, tenant_id)

    # Dispatcher B sweeps and writes the row off.
    other = OutboxDispatcher(session_factory, FixtureTaskQueue())
    assert other.run_once().reclaimed == 1
    assert _outbox_row(session_factory, job_id).status == OutboxStatus.FAILED.value

    # A's enqueue returns, and A records the dispatch it genuinely performed.
    dispatcher._record_dispatched(
        record.tenant_id, record.job_id, record.id, lease_token=record.lease_token
    )

    row = _outbox_row(session_factory, job_id)
    assert row.status == OutboxStatus.FAILED.value, (
        "a row already written off must not be resurrected by the dispatcher "
        "that lost the race; a dispatched row beside a parked job is the state "
        "nothing reconciles"
    )
    assert row.lease_expires_at is None

    with session_factory() as session:
        assert jobs.get(session, tenant_id=tenant_id, job_id=job_id).status == (
            JobState.FAILED_PROVIDER
        )
        # The half that was never in danger, asserted so it stays that way.
        assert not jobs.claim(session, tenant_id=tenant_id, job_id=job_id), (
            "a parked job cannot be claimed, so a still-live task executes nothing"
        )


def test_a_reclaimed_rows_explanation_survives_a_late_failure_write(
    session_factory, jobs, outbox, tenant_id, dispatcher
):
    """The other late writer must not overwrite why the row was written off.

    ``mark_failed`` cannot resurrect a reclaimed row the way ``mark_dispatched``
    could — at exhaustion it writes the *same* terminal state, ``failed`` with
    the lease cleared, so the status converges. What it would take with it is the
    reason: ``last_error`` would be replaced by this attempt's queue error, which
    is precisely the misleading text the reclaim exists to replace. An operator
    would read "queue unavailable" and investigate the queue, when what actually
    happened is that nothing ever recorded the final attempt.
    """
    job_id = _accept_command(session_factory, jobs, outbox, tenant_id)

    for _ in range(MAX_DISPATCH_ATTEMPTS - 1):
        _claim_and_walk_away(session_factory, outbox, tenant_id)

    _expire_all_leases(session_factory, tenant_id)
    with session_factory() as session:
        record = outbox.claim_batch(session, limit=10)[0]
        session.commit()

    _expire_all_leases(session_factory, tenant_id)
    OutboxDispatcher(session_factory, FixtureTaskQueue()).run_once()

    reclaimed_text = _outbox_row(session_factory, job_id).last_error
    assert "no outcome" in reclaimed_text

    dispatcher._record_failure(record, "queue unavailable", record.dispatch_attempts)

    row = _outbox_row(session_factory, job_id)
    assert row.status == OutboxStatus.FAILED.value
    assert row.last_error == reclaimed_text, (
        "the reclaim's explanation must survive; the late writer's error belongs "
        "to an attempt whose outcome was already decided"
    )


def test_a_failing_reclaim_does_not_stop_the_pass(
    session_factory, jobs, outbox, tenant_id, queue, dispatcher, monkeypatch
):
    """The sweep is janitorial and must never cost a healthy row its dispatch.

    ``run_once``'s contract is that only a failed *claim* aborts a pass — a batch
    that never started has nothing to summarize. The reclaim is not the claim. It
    runs first, it touches rows this pass has no other interest in, and it takes
    job-row locks in an order other paths also take, so a deadlock or a lock
    timeout there is entirely possible. Letting that abort the pass would mean a
    problem with yesterday's wreckage stops today's work — the same reasoning
    that makes ``_record_failure_safely`` swallow rather than raise.
    """
    job_id = _accept_command(session_factory, jobs, outbox, tenant_id)

    def broken_sweep(*args, **kwargs):
        raise OperationalError("UPDATE outbox_record", {}, Exception("deadlock detected"))

    monkeypatch.setattr(dispatcher, "reclaim_stranded", broken_sweep)

    outcome = dispatcher.run_once()

    assert outcome.dispatched == 1, "a healthy row must still be dispatched"
    assert outcome.reclaimed == 0, "a sweep that failed must not report work it did not do"
    with session_factory() as session:
        assert _outbox_status(session, job_id) == OutboxStatus.DISPATCHED


def test_a_peer_that_finalised_the_row_first_is_not_reported_as_a_failure(
    session_factory, jobs, outbox, tenant_id, queue, dispatcher, caplog
):
    """A lost race against a *healthy* peer is convergence, not a failure.

    ``mark_dispatched``'s compare-and-set returns ``False`` for two entirely
    different situations, and only one of them is a problem. The reclaim wrote
    the row off — that is the dangerous one. Or a peer dispatcher claimed the row
    after this one's lease expired and finalised it correctly, which is the
    ordinary recovery path the deterministic task name exists to make safe.

    Treating the second as the first is worse than a miscount. The row is
    ``dispatched``, the job is ``dispatched``, and a worker is on its way to run
    it — so telling an operator to re-drive would duplicate live work, which is
    the single outcome ADR-0007's whole argument is built to prevent. So this
    test asserts the counter *and* the log: no failure, and no advice to re-run
    something that is already running.
    """
    job_id = _accept_command(session_factory, jobs, outbox, tenant_id)

    # This dispatcher claims the row and begins a slow enqueue.
    with session_factory() as session:
        record = outbox.claim_batch(session, limit=10)[0]
        session.commit()

    # The enqueue outlives the lease, and a healthy peer picks the row up and
    # finishes it properly. The peer shares the queue, as two instances would.
    _expire_all_leases(session_factory, tenant_id)
    peer = OutboxDispatcher(session_factory, queue)
    assert peer.run_once().dispatched == 1

    with session_factory() as session:
        assert _outbox_status(session, job_id) == OutboxStatus.DISPATCHED
        assert jobs.get(session, tenant_id=tenant_id, job_id=job_id).status == JobState.DISPATCHED

    # Now the slow dispatcher's enqueue returns and it tries to record.
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="smartmatch_worker.dispatcher"):
        outcome = dispatcher._dispatch_row(record)

    assert outcome == "already_existed", (
        "a peer finalising the row is the expected recovery path, not a failure; "
        "counting it failed would make a healthy convergence look like an incident"
    )
    assert "re-drive" not in caplog.text.lower(), (
        "the job is dispatched and running — advising a re-drive here would "
        "duplicate live work, which is what deterministic task names exist to prevent"
    )

    with session_factory() as session:
        assert _outbox_status(session, job_id) == OutboxStatus.DISPATCHED
        assert jobs.get(session, tenant_id=tenant_id, job_id=job_id).status == JobState.DISPATCHED


def test_a_reclaimed_row_still_tells_the_operator_to_re_drive(
    session_factory, jobs, outbox, tenant_id, queue, dispatcher, caplog
):
    """The other half: when the row *was* written off, say so and say what to do.

    The sibling of the test above, asserted together with it so the two branches
    cannot silently collapse into one. Here the job really is parked, no worker
    will pick it up, and a re-drive is exactly what an operator should do — so
    the advice that would be dangerous in the peer case is the correct advice
    here.
    """
    job_id = _accept_command(session_factory, jobs, outbox, tenant_id)

    for _ in range(MAX_DISPATCH_ATTEMPTS - 1):
        _claim_and_walk_away(session_factory, outbox, tenant_id)

    _expire_all_leases(session_factory, tenant_id)
    with session_factory() as session:
        record = outbox.claim_batch(session, limit=10)[0]
        session.commit()

    _expire_all_leases(session_factory, tenant_id)
    assert OutboxDispatcher(session_factory, FixtureTaskQueue()).run_once().reclaimed == 1

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="smartmatch_worker.dispatcher"):
        outcome = dispatcher._dispatch_row(record)

    assert outcome == "failed"
    assert "re-drive" in caplog.text.lower(), (
        "a parked job needs a human to restart it, and the log is the only place "
        "this dispatcher can say so"
    )

    with session_factory() as session:
        assert _outbox_status(session, job_id) == OutboxStatus.FAILED
        assert jobs.get(session, tenant_id=tenant_id, job_id=job_id).status == (
            JobState.FAILED_PROVIDER
        )


def test_a_peer_that_finalised_the_row_is_not_reported_as_a_failure_on_the_failure_path(
    session_factory, jobs, outbox, tenant_id, queue, dispatcher, caplog
):
    """The failure path must tell the two losing cases apart too.

    ``mark_failed``'s compare-and-set loses to a healthy peer's ``dispatched``
    write exactly as readily as it loses to the sweep, so ``_record_failure``
    faces the identical ambiguity ``_record_dispatched`` does. Reporting a peer's
    success as "already reclaimed" would count a dispatched row as a failure and
    tell an operator to re-drive a job that is running — the same dangerous
    reading, reached down the other branch.

    Here this dispatcher's own enqueue fails *after* a peer has already
    dispatched the row, which is what a partial queue outage across two
    instances looks like.
    """
    job_id = _accept_command(session_factory, jobs, outbox, tenant_id)

    with session_factory() as session:
        record = outbox.claim_batch(session, limit=10)[0]
        session.commit()

    # A peer picks the row up once the lease expires and dispatches it properly.
    _expire_all_leases(session_factory, tenant_id)
    assert OutboxDispatcher(session_factory, queue).run_once().dispatched == 1

    # This dispatcher's enqueue then fails, routing it to the failure path.
    queue.fail_next_with = TaskQueueError("queue unavailable")
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="smartmatch_worker.dispatcher"):
        outcome = dispatcher._dispatch_row(record)

    assert outcome == "already_existed", (
        "a peer finalising the row is convergence, not this pass's failure"
    )
    assert "re-drive" not in caplog.text.lower(), (
        "the job is dispatched and running; advising a re-drive would duplicate live work"
    )

    with session_factory() as session:
        assert _outbox_status(session, job_id) == OutboxStatus.DISPATCHED
        assert jobs.get(session, tenant_id=tenant_id, job_id=job_id).status == JobState.DISPATCHED


def test_a_reclaim_that_never_commits_logs_nothing(
    session_factory, jobs, outbox, tenant_id, dispatcher, monkeypatch, caplog
):
    """A reclaim is only real once it commits, and the log must say only real things.

    The per-row lines were emitted inside the loop, before ``session.commit()``.
    A commit that failed — or anything raising part-way through the batch — left
    up to ``batch_size`` WARNING lines announcing rows as reclaimed and jobs as
    parked, while ``run_once`` correctly reported ``reclaimed = 0`` and the
    database still held every one of those rows ``leased``. An operator
    reconciling the log against the metric finds them contradicting each other,
    and the log is the one that is wrong.
    """
    first = _accept_command(session_factory, jobs, outbox, tenant_id)
    second = _accept_command(session_factory, jobs, outbox, tenant_id)
    for _ in range(MAX_DISPATCH_ATTEMPTS):
        _claim_and_walk_away(session_factory, outbox, tenant_id)
    _expire_all_leases(session_factory, tenant_id)

    real_transition = dispatcher._jobs.transition
    seen: list[uuid.UUID] = []

    def fails_on_the_second_row(session, **kwargs):
        seen.append(kwargs["job_id"])
        if len(seen) == 2:
            raise OperationalError("UPDATE job", {}, Exception("deadlock detected"))
        return real_transition(session, **kwargs)

    monkeypatch.setattr(dispatcher._jobs, "transition", fails_on_the_second_row)

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="smartmatch_worker.dispatcher"):
        outcome = dispatcher.run_once()

    assert outcome.reclaimed == 0, "nothing committed, so nothing was reclaimed"
    assert "reclaimed as failed" not in caplog.text, (
        "no row may be announced as reclaimed when the transaction that would "
        "have reclaimed it never committed"
    )

    for job_id in (first, second):
        assert _outbox_row(session_factory, job_id).status == OutboxStatus.LEASED.value
        with session_factory() as session:
            assert jobs.get(session, tenant_id=tenant_id, job_id=job_id).status == JobState.QUEUED


def test_a_reclaimed_job_that_was_not_queued_is_not_logged_as_parked(
    session_factory, jobs, outbox, tenant_id, dispatcher, caplog
):
    """The job transition's result decides what the line may claim.

    The transition is conditional on the job still being ``queued`` and its
    return was discarded, so every reclaimed row was announced as "its job
    parked" whether or not any job moved. A cancelled job is the reachable case:
    ``queued -> cancelled`` is declared, the row is still stranded and still
    worth writing off, and the job is emphatically not parked.
    """
    job_id = _accept_command(session_factory, jobs, outbox, tenant_id)
    for _ in range(MAX_DISPATCH_ATTEMPTS):
        _claim_and_walk_away(session_factory, outbox, tenant_id)

    with session_factory() as session:
        assert jobs.transition(
            session,
            tenant_id=tenant_id,
            job_id=job_id,
            to_state=JobState.CANCELLED,
            expected_from=JobState.QUEUED,
        )
        session.commit()

    _expire_all_leases(session_factory, tenant_id)
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="smartmatch_worker.dispatcher"):
        assert dispatcher.run_once().reclaimed == 1

    assert "its job parked" not in caplog.text, (
        "the job was cancelled, not parked; the line must report what happened"
    )
    assert _outbox_row(session_factory, job_id).status == OutboxStatus.FAILED.value
    with session_factory() as session:
        assert jobs.get(session, tenant_id=tenant_id, job_id=job_id).status == JobState.CANCELLED


def test_a_committed_reclaim_survives_a_claim_that_then_fails(
    session_factory, jobs, outbox, tenant_id, dispatcher, monkeypatch, caplog
):
    """A reclaim that committed is a fact, and a later failure must not erase it.

    The sweep commits, then ``claim_batch`` raises and the exception leaves
    ``run_once`` before any ``DispatchOutcome`` is built — so the ``reclaimed``
    signal vanishes. That is exactly backwards: the conditions that make the
    claim fail, a database under strain, are the conditions that strand rows in
    the first place, so the signal disappears precisely when it is most
    informative.

    ``run_once`` still raises, deliberately — a batch that could not be claimed
    must reach the caller's poll loop rather than being reported as a quiet pass.
    What must not happen is the reclaim going unreported.
    """
    job_id = _accept_command(session_factory, jobs, outbox, tenant_id)
    for _ in range(MAX_DISPATCH_ATTEMPTS):
        _claim_and_walk_away(session_factory, outbox, tenant_id)
    _expire_all_leases(session_factory, tenant_id)

    def broken_claim(*args, **kwargs):
        raise OperationalError("SELECT outbox_record", {}, Exception("server closed"))

    monkeypatch.setattr(dispatcher._outbox, "claim_batch", broken_claim)

    caplog.clear()
    with (
        caplog.at_level(logging.INFO, logger="smartmatch_worker.dispatcher"),
        pytest.raises(OperationalError) as raised,
    ):
        dispatcher.run_once()

    # The reclaim really did happen and is committed.
    assert _outbox_row(session_factory, job_id).status == OutboxStatus.FAILED.value

    carried = " ".join(getattr(raised.value, "__notes__", []))
    assert "1" in carried and "reclaim" in carried.lower(), (
        "the committed reclaim must travel with the failure that followed it, "
        f"not be discarded; notes were {getattr(raised.value, '__notes__', [])!r}"
    )


# ---------------------------------------------------------------------------
# J17 — a row must record *which* dispatcher claimed it
# ---------------------------------------------------------------------------


def _claim_one(session_factory, outbox, *, lease: timedelta = timedelta(seconds=60)):
    """Claim exactly one row and commit the lease, as a dispatcher pass would."""
    with session_factory() as session:
        claimed = outbox.claim_batch(session, limit=10, lease=lease)
        session.commit()
    assert len(claimed) == 1
    return claimed[0]


def test_a_stale_failure_write_cannot_overwrite_a_peers_lease(
    session_factory, jobs, outbox, tenant_id, dispatcher
):
    """The measured J17 scenario: ``leased`` proves liveness, not ownership.

    Two dispatchers and one slow dispatch. A claims the row; A's enqueue outlives
    its own lease — nothing exotic, a slow provider call or a long GC — and peer
    B legitimately re-claims it with a fresh 60-second lease. A's enqueue then
    fails, and A records the failure it believes belongs to it.

    With the guard on ``status = 'leased'`` alone, A wins: B's own claim
    satisfies ``leased``. Measured before the fix, and the numbers this test
    pins are those numbers. A carries the *older* attempt count, so its backoff
    is ``backoff_for(2)`` — four seconds — and it writes that over B's
    sixty-second lease, cutting **56 seconds** off it. It replaces B's
    ``last_error`` with an error from an attempt B never made. And the row
    becomes claimable again while B is still working it, so a third pass claims
    it and burns an attempt the row should not have spent — repeat that near the
    limit and the row is parked as exhausted having had fewer real attempts than
    ``MAX_DISPATCH_ATTEMPTS`` promises.

    Nothing is lost or double-executed here and the test does not claim
    otherwise: ``JobRepository.claim`` still admits only a ``dispatched`` job.
    What is wrong is that the row's attempt budget, its lease, and its
    explanation all come to describe an attempt that is not the one in progress.
    """
    job_id = _accept_command(session_factory, jobs, outbox, tenant_id)

    # One earlier attempt, so A's claim is attempt 2 and its backoff is the
    # four seconds the measurement used.
    _claim_and_walk_away(session_factory, outbox, tenant_id)

    # Dispatcher A claims and begins a slow enqueue.
    _expire_all_leases(session_factory, tenant_id)
    stale = _claim_one(session_factory, outbox)
    assert stale.dispatch_attempts == 2

    # The enqueue outlives A's lease, and peer B re-claims the row.
    _expire_all_leases(session_factory, tenant_id)
    peer = _claim_one(session_factory, outbox)
    assert peer.id == stale.id, "the two dispatchers are working the same row"
    assert peer.lease_token != stale.lease_token, (
        "a re-claim is a new claim and must mint a new token, or ownership is "
        "indistinguishable from liveness"
    )
    assert peer.dispatch_attempts == 3

    held_by_peer = _outbox_row(session_factory, job_id)

    # A's enqueue finally fails, and A records the failure against a row it no
    # longer owns.
    recorded = dispatcher._record_failure(stale, "queue unavailable", stale.dispatch_attempts)

    assert recorded == "contended", (
        "a row a peer is still working is neither a reclaim nor a completed "
        "dispatch; the dispatcher must say nothing about it rather than guess. "
        "J17 landed this as 'unresolved'; J8 gave it a name of its own so the "
        "benign race stops looking like an incident — see DispatchOutcome"
    )

    row = _outbox_row(session_factory, job_id)
    assert row.lease_token == peer.lease_token, "the peer must still own the row"
    assert row.status == OutboxStatus.LEASED.value
    assert row.lease_expires_at == held_by_peer.lease_expires_at, (
        "the peer's 60-second lease must survive; the stale writer's backoff is "
        f"{backoff_for(stale.dispatch_attempts).total_seconds():.0f}s, which "
        "would have cut 56 seconds off it and handed the row to a third pass "
        "while the peer was still enqueuing"
    )
    assert row.last_error is None, (
        "the error belongs to an attempt that is not the one in progress; "
        "writing it over the peer's row describes the wrong attempt"
    )
    assert row.dispatch_attempts == 3

    # The consequence that costs the row its attempt budget, asserted directly:
    # halfway through the peer's lease nothing may claim this row.
    midway = datetime.now(UTC) + timedelta(seconds=30)
    with session_factory() as session:
        assert outbox.claim_batch(session, limit=10, now=midway) == [], (
            "a row whose peer holds a live lease must not become claimable "
            "because a stale writer shortened it"
        )
        session.rollback()

    with session_factory() as session:
        assert jobs.get(session, tenant_id=tenant_id, job_id=job_id).status == JobState.QUEUED


def test_a_stale_dispatch_write_cannot_overwrite_a_peers_lease(
    session_factory, jobs, outbox, tenant_id, dispatcher
):
    """The same race down the other writer, closed for consistency's sake.

    ``mark_dispatched`` was affected in form rather than in substance: a stale
    write there asserts the row is ``dispatched``, and it is, because that path
    is only reached having enqueued the task or found it already present. So the
    old behaviour converged on a true statement — by writing over a row a peer
    was holding, and finishing a claim that was not its own.

    It is closed anyway. A rule about who may finish a row that one of its two
    writers is exempt from is a rule nothing can rely on, and the exemption's
    safety rests on a chain of reasoning about the enqueue that a later change
    could quietly break. Here the peer keeps its lease and its token, the job
    stays ``queued`` until whoever *does* own the row says otherwise, and the
    stale dispatcher reports a row it could not complete rather than one it did.
    """
    job_id = _accept_command(session_factory, jobs, outbox, tenant_id)

    stale = _claim_one(session_factory, outbox)

    _expire_all_leases(session_factory, tenant_id)
    peer = _claim_one(session_factory, outbox)
    assert peer.lease_token != stale.lease_token

    held_by_peer = _outbox_row(session_factory, job_id)

    recorded = dispatcher._record_dispatched(
        stale.tenant_id, stale.job_id, stale.id, lease_token=stale.lease_token
    )

    assert recorded == "contended", (
        "the row is neither reclaimed nor finalised — it is held by a peer "
        "mid-pass, and this dispatcher cannot say how that pass ends. Named "
        "apart from 'unresolved' by J8: this dispatcher knows exactly what "
        "happened, it simply is not the one finishing the row"
    )

    row = _outbox_row(session_factory, job_id)
    assert row.status == OutboxStatus.LEASED.value, (
        "a row a peer holds must not be finalised by the dispatcher that lost it"
    )
    assert row.lease_token == peer.lease_token
    assert row.lease_expires_at == held_by_peer.lease_expires_at

    with session_factory() as session:
        assert jobs.get(session, tenant_id=tenant_id, job_id=job_id).status == JobState.QUEUED, (
            "the job advances when its row's owner records the dispatch, not "
            "when a dispatcher that lost the row does"
        )

    # And the owner finishes it, which is the point: nothing is stuck, the work
    # is simply completed by the pass that holds the claim.
    assert (
        dispatcher._record_dispatched(
            peer.tenant_id, peer.job_id, peer.id, lease_token=peer.lease_token
        )
        == "recorded"
    )
    with session_factory() as session:
        assert _outbox_status(session, job_id) == OutboxStatus.DISPATCHED
        assert jobs.get(session, tenant_id=tenant_id, job_id=job_id).status == JobState.DISPATCHED


def test_a_lease_with_no_token_is_not_treated_as_unheld(
    session_factory, jobs, outbox, tenant_id, dispatcher
):
    """A ``NULL`` token is a rollout constraint, not a free row.

    ``outbox_record.lease_token`` is expand-phase and nullable (migration
    ``0004``), so during a rolling deploy a dispatcher still running pre-J17 code
    claims rows against this schema **without writing a token** — and holds them.
    Reading ``lease_token IS NULL`` as "nobody holds this row" would therefore
    hand a live claim to whichever writer arrived, which is the defect J17 exists
    to close, reached through the fix for it.

    So both writers fail closed: ``lease_token = :token`` is never true against a
    ``NULL`` column, so a tokenless row matches nothing and the caller takes the
    ordinary lost-the-race path. That costs this code nothing, because a caller
    on this code always has a token — ``claim_batch`` mints one in the same
    UPDATE that takes the lease.

    What it does **not** buy is symmetry, and this test cannot assert what it
    does not buy: the old dispatcher's own writers still guard on ``status =
    'leased'`` alone, so it can overwrite a new dispatcher's tokenized lease
    exactly as J17 describes. J17's guarantee holds only once every dispatcher
    runs this code. Draining the old ones is what makes it true; see ``0004``.
    """
    job_id = _accept_command(session_factory, jobs, outbox, tenant_id)

    record = _claim_one(session_factory, outbox)

    # What a pre-J17 dispatcher's claim leaves on the row: a live lease, an
    # incremented attempt count, and no token at all.
    with session_factory() as session:
        session.execute(
            text("UPDATE outbox_record SET lease_token = NULL WHERE id = :id"),
            {"id": record.id},
        )
        session.commit()

    with session_factory() as session:
        assert not outbox.mark_failed(
            session,
            record_id=record.id,
            lease_token=record.lease_token,
            error="queue unavailable",
            attempts=record.dispatch_attempts,
        ), "a tokenless lease is held by a dispatcher this code cannot identify"
        assert not outbox.mark_dispatched(
            session, record_id=record.id, lease_token=record.lease_token
        ), "and the dispatch writer must refuse it for the same reason"
        session.commit()

    row = _outbox_row(session_factory, job_id)
    assert row.status == OutboxStatus.LEASED.value
    assert row.lease_token is None, "nothing may adopt a row it cannot prove it holds"
    assert row.last_error is None
    assert row.lease_expires_at is not None, (
        "the old dispatcher's lease must survive; clearing it would make the "
        "row claimable while that dispatcher is still working it"
    )

    with session_factory() as session:
        assert jobs.get(session, tenant_id=tenant_id, job_id=job_id).status == JobState.QUEUED
