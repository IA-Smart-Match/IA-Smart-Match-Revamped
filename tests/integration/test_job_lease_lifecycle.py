"""The job lease, end to end, against a real PostgreSQL instance (J9).

Backlog J9 is the recovery path for a worker that dies after its claim commits
and before the terminal transition does. Migration ``0004`` gave it a column;
``jobs.py``, ``execution.py`` and the scheduled pass gave it a lifecycle. What
the handoff (``docs/plans/pr1-blockers-handoff.md`` §2.2) established is that
**none of it was tested** — the 27 lease assertions in
``test_outbox_dispatcher.py`` are every one of them about
``outbox_record.lease_expires_at``, the dispatcher's lease, which predates J9
and bounds a different thing.

So this module asserts the four writes and the one read that make up the job
lease, and it asserts them against the database rather than a double, because
every one of them is a property of a single conditional UPDATE:

* **written** by ``claim``, in the statement that takes ``dispatched ->
  running`` — never by a follow-up, because a worker that died between the two
  is precisely the failure being fixed;
* **renewed** by ``TaskExecutor._emit``, on the strength of a handler's
  progress event and in the same transaction as it;
* **cleared** by the terminal transition, so a finished job does not sit in
  ``ix_job_running_lease`` looking attended;
* **read** by ``sweep_expired_leases``, which takes ``running -> timed_out``
  for an expired deadline and skips a ``NULL`` one — the row shape a release
  predating J9 wrote, and terminating live work on the strength of a column
  that release never set would be a defect introduced by the fix.

The last test is the one that says the sweep is safe to run: a job that keeps
reporting progress inside its lease is never swept, however long it runs.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from conftest import ensure_owning_unit
from smartmatch_domain.jobs import JobState
from smartmatch_persistence.jobs import JobRepository
from smartmatch_worker.config import WorkerSettings
from smartmatch_worker.execution import StalledJobSweeper, TaskExecutor
from smartmatch_worker.handlers import CommandContext, CommandRegistry, HandlerResult
from sqlalchemy import text

pytestmark = pytest.mark.integration

COMMAND = "test.leased"


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def jobs() -> JobRepository:
    return JobRepository()


@pytest.fixture
def sweeper(session_factory) -> StalledJobSweeper:
    return StalledJobSweeper(session_factory)


def dispatched_job(session_factory, jobs, tenant_id, *, command_type: str = COMMAND) -> uuid.UUID:
    """A job in ``dispatched`` — the only state ``claim`` will admit."""
    with session_factory() as session:
        job = jobs.create(
            session,
            tenant_id=tenant_id,
            command_type=command_type,
            owning_unit_id=ensure_owning_unit(session, tenant_id),
        )
        jobs.transition(
            session,
            tenant_id=tenant_id,
            job_id=job.id,
            to_state=JobState.DISPATCHED,
            expected_from=JobState.QUEUED,
        )
        session.commit()
    return job.id


def job_row(session_factory, job_id: uuid.UUID):
    """The columns this module is about, read straight from the table."""
    with session_factory() as session:
        return session.execute(
            text("SELECT status, lease_expires_at, version FROM job WHERE id = :job_id"),
            {"job_id": job_id},
        ).one()


def expire_lease(session_factory, job_id: uuid.UUID) -> datetime:
    """Force one job's deadline into the past, and say when it now is.

    A worker that died holding the job, seen from the database's side: the row
    is ``running``, its deadline has passed, and nothing is coming back. No
    fault is injected into the executor, because process death is not a raised
    exception — it is the absence of one.
    """
    past = datetime.now(UTC) - timedelta(hours=1)
    with session_factory() as session:
        session.execute(
            text("UPDATE job SET lease_expires_at = :past WHERE id = :job_id"),
            {"past": past, "job_id": job_id},
        )
        session.commit()
    return past


def registry_of(handler) -> CommandRegistry:
    return CommandRegistry(handlers={COMMAND: handler})


def job_events(session_factory, jobs, tenant_id, job_id) -> list[dict[str, Any]]:
    with session_factory() as session:
        return [
            event.payload
            for event in jobs.events_since(session, tenant_id=tenant_id, job_id=job_id)
        ]


# ---------------------------------------------------------------------------
# Written: the claim and the lease are one statement
# ---------------------------------------------------------------------------


def test_the_claim_takes_the_lease_in_the_statement_that_starts_the_job(
    session_factory, jobs, tenant_id
):
    """``dispatched -> running`` and the deadline commit together, or not at all.

    The window a follow-up UPDATE would open is one statement wide, and it is
    the exact window J9 exists to close: a worker that claimed the job and died
    before writing a deadline leaves a ``running`` row that
    ``sweep_expired_leases`` is required to skip forever.

    Asserted from the row rather than from the return value, because the return
    value is what the code believes and the row is what the sweep will read.
    """
    job_id = dispatched_job(session_factory, jobs, tenant_id)

    before = job_row(session_factory, job_id)
    assert before.status == JobState.DISPATCHED.value
    assert before.lease_expires_at is None, "nothing before the claim may set a deadline"

    lease = timedelta(minutes=7)
    claimed_at = datetime.now(UTC)
    with session_factory() as session:
        assert jobs.claim(session, tenant_id=tenant_id, job_id=job_id, lease=lease) is True
        session.commit()

    after = job_row(session_factory, job_id)
    assert after.status == JobState.RUNNING.value
    assert after.lease_expires_at is not None, (
        "a running job with no deadline is the row shape J9 exists to eliminate"
    )
    assert after.lease_expires_at > claimed_at, "the deadline must be in the future"
    assert after.lease_expires_at <= datetime.now(UTC) + lease, (
        "the deadline must be the lease that was asked for, not a longer one"
    )


def test_a_claim_that_loses_the_race_writes_no_lease(session_factory, jobs, tenant_id):
    """The second delivery neither runs the job nor touches its deadline.

    The compare-and-set is what makes at-least-once delivery survivable, and the
    lease rides it: a losing claim that still wrote a deadline would push the
    winner's out by its own lease length, on the strength of nothing having
    happened.
    """
    job_id = dispatched_job(session_factory, jobs, tenant_id)

    with session_factory() as session:
        assert jobs.claim(session, tenant_id=tenant_id, job_id=job_id, lease=timedelta(minutes=1))
        session.commit()
    won = job_row(session_factory, job_id)

    with session_factory() as session:
        assert (
            jobs.claim(session, tenant_id=tenant_id, job_id=job_id, lease=timedelta(hours=9))
            is False
        ), "a job that is already running is not claimable"
        session.commit()

    lost = job_row(session_factory, job_id)
    assert lost.lease_expires_at == won.lease_expires_at, (
        "a losing claim must not extend the winner's deadline"
    )
    assert lost.version == won.version, "and must not count as a state change"


# ---------------------------------------------------------------------------
# Renewed: progress is what the deadline moves on
# ---------------------------------------------------------------------------


def test_renewing_a_lease_moves_the_deadline_without_changing_the_state(
    session_factory, jobs, tenant_id
):
    """``renew_lease`` is a deadline write, not a transition.

    ``version`` counts state changes. A handler emitting progress every second
    would churn it for a job that never changed state, so the renewal leaves it
    alone and moves ``updated_at`` instead, because the row did change.
    """
    job_id = dispatched_job(session_factory, jobs, tenant_id)
    with session_factory() as session:
        jobs.claim(session, tenant_id=tenant_id, job_id=job_id, lease=timedelta(seconds=30))
        session.commit()
    claimed = job_row(session_factory, job_id)

    with session_factory() as session:
        assert (
            jobs.renew_lease(
                session, tenant_id=tenant_id, job_id=job_id, lease=timedelta(minutes=20)
            )
            is True
        )
        session.commit()

    renewed = job_row(session_factory, job_id)
    assert renewed.lease_expires_at > claimed.lease_expires_at, "the deadline must move out"
    assert renewed.status == JobState.RUNNING.value
    assert renewed.version == claimed.version, "a renewal is not a state change"


def test_a_handler_reporting_progress_renews_its_own_lease(session_factory, jobs, tenant_id):
    """``TaskExecutor._emit`` renews the lease, and that is the whole of J9 step 2.

    An emitted event is the only evidence this process has that the *work* is
    progressing rather than merely that the process is up, so it is what the
    deadline is extended on — never a background timer, which would renew the
    lease of a handler that had hung.

    The handler pushes its own deadline into the past first, which models the
    passage of real time without spending any: a lease that has all but run out
    while the work legitimately continued. What the emission must then do is put
    it back in the future.
    """
    observed: dict[str, datetime | None] = {}

    def report_progress(context: CommandContext) -> HandlerResult:
        observed["before"] = expire_lease(session_factory, context.job.id)
        context.emit({"type": "progress", "detail": "still working"})
        observed["after"] = job_row(session_factory, context.job.id).lease_expires_at
        return HandlerResult(state=JobState.SUCCEEDED, summary={"performed": "nothing"})

    job_id = dispatched_job(session_factory, jobs, tenant_id)
    executor = TaskExecutor(
        session_factory, registry_of(report_progress), lease=timedelta(minutes=10)
    )
    executor.execute(tenant_id=tenant_id, job_id=job_id)

    assert observed["after"] is not None, "the renewal must not clear the deadline"
    assert observed["after"] > observed["before"], "progress must push the deadline out"
    assert observed["after"] > datetime.now(UTC) - timedelta(seconds=5), (
        "an expired lease that was renewed must land in the future, not merely later"
    )


# ---------------------------------------------------------------------------
# Cleared: a terminal job is not an attended one
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "state",
    [JobState.SUCCEEDED, JobState.FAILED_PROVIDER, JobState.CANCELLED],
    ids=lambda state: state.value,
)
def test_leaving_running_clears_the_deadline(session_factory, jobs, tenant_id, state):
    """Every way out of ``running`` drops the lease, not merely the happy one.

    A terminal job keeping a stale deadline sits in ``ix_job_running_lease``
    forever and reads to anyone inspecting the row as though a worker were still
    on it. Parametrized over three exits rather than asserted once, because
    ``transition``'s default is what guarantees this and a default is only as
    good as the paths that take it.
    """
    job_id = dispatched_job(session_factory, jobs, tenant_id)
    with session_factory() as session:
        jobs.claim(session, tenant_id=tenant_id, job_id=job_id, lease=timedelta(minutes=10))
        session.commit()
    assert job_row(session_factory, job_id).lease_expires_at is not None

    with session_factory() as session:
        assert jobs.transition(
            session,
            tenant_id=tenant_id,
            job_id=job_id,
            to_state=state,
            expected_from=JobState.RUNNING,
        )
        session.commit()

    row = job_row(session_factory, job_id)
    assert row.status == state.value
    assert row.lease_expires_at is None, "a terminal job must not look attended"


def test_a_job_the_executor_finished_carries_no_deadline(session_factory, jobs, tenant_id):
    """The same property through the executor, which is what actually runs.

    The parametrized test above proves ``transition`` clears the column. This
    one proves the production path reaches that transition — including after a
    handler that renewed the lease on its way, which is the arrangement in which
    a stale deadline would survive.
    """

    def works_then_finishes(context: CommandContext) -> HandlerResult:
        context.emit({"type": "progress", "detail": "halfway"})
        return HandlerResult(state=JobState.SUCCEEDED, summary={"rows": 1})

    job_id = dispatched_job(session_factory, jobs, tenant_id)
    TaskExecutor(session_factory, registry_of(works_then_finishes)).execute(
        tenant_id=tenant_id, job_id=job_id
    )

    row = job_row(session_factory, job_id)
    assert row.status == JobState.SUCCEEDED.value
    assert row.lease_expires_at is None


# ---------------------------------------------------------------------------
# Read: the sweep, and what it must not touch
# ---------------------------------------------------------------------------


def test_the_sweep_times_out_a_job_whose_lease_ran_out(session_factory, jobs, sweeper, tenant_id):
    """The recovery J9 exists for: a claim with nothing behind it.

    The job is claimed and then abandoned — no exception, no outcome, nothing.
    That is what a killed worker leaves, and until the sweep existed the row
    stayed ``running`` until a human noticed.
    """
    job_id = dispatched_job(session_factory, jobs, tenant_id)
    with session_factory() as session:
        jobs.claim(session, tenant_id=tenant_id, job_id=job_id, lease=timedelta(minutes=10))
        session.commit()
    missed = expire_lease(session_factory, job_id)

    assert sweeper.sweep() == 1, "the count is the metric an operator alerts on"

    row = job_row(session_factory, job_id)
    assert row.status == JobState.TIMED_OUT.value
    assert row.lease_expires_at is None, "a swept job must not be swept again"

    events = job_events(session_factory, jobs, tenant_id, job_id)
    timed_out = [event for event in events if event.get("type") == "job.timed_out"]
    assert len(timed_out) == 1, (
        "a job that goes terminal with nothing saying why is the failure this "
        "whole module is organised against"
    )
    assert timed_out[0]["reason"] == "lease_expired"
    assert missed.isoformat() in timed_out[0]["detail"], (
        "the event carries the missed deadline because the row stops carrying it"
    )


def test_the_sweep_skips_a_running_job_that_has_no_deadline(
    session_factory, jobs, sweeper, tenant_id
):
    """A ``NULL`` lease is not an expired one, and the difference is a live job.

    Such a row is what a release predating J9 wrote: it claimed against this
    schema and never set the column. Terminating live work on the strength of a
    column that release never wrote would be a defect introduced by the fix, so
    the sweep's predicate tests ``lease_expires_at < now`` — which ``NULL``
    fails — rather than "no deadline in the future".
    """
    job_id = dispatched_job(session_factory, jobs, tenant_id)
    with session_factory() as session:
        # Straight to ``running`` with no lease: ``transition``'s default writes
        # NULL, which is exactly the pre-J9 row.
        assert jobs.transition(
            session,
            tenant_id=tenant_id,
            job_id=job_id,
            to_state=JobState.RUNNING,
            expected_from=JobState.DISPATCHED,
        )
        session.commit()
    assert job_row(session_factory, job_id).lease_expires_at is None

    assert sweeper.sweep() == 0, "a job with no deadline has not missed one"
    assert job_row(session_factory, job_id).status == JobState.RUNNING.value
    assert job_events(session_factory, jobs, tenant_id, job_id) == []


def test_the_sweep_leaves_a_live_lease_alone(session_factory, jobs, sweeper, tenant_id):
    """A deadline in the future is a worker that is still within its budget."""
    job_id = dispatched_job(session_factory, jobs, tenant_id)
    with session_factory() as session:
        jobs.claim(session, tenant_id=tenant_id, job_id=job_id, lease=timedelta(hours=1))
        session.commit()

    assert sweeper.sweep() == 0
    assert job_row(session_factory, job_id).status == JobState.RUNNING.value


def test_a_job_that_keeps_reporting_progress_is_never_swept(
    session_factory, jobs, sweeper, tenant_id
):
    """The property that makes the sweep safe to schedule at all.

    The lease bounds *silence*, not duration. A handler that runs for longer
    than ``job_lease_seconds`` while reporting progress must survive a sweep
    that runs in the middle of it; only one that goes quiet for longer than the
    lease may be timed out. Get this wrong and the sweep becomes the thing that
    kills long imports.

    Real time, real sleeps, and a deliberately tiny lease taken from
    :class:`WorkerSettings` rather than invented here — the configured value is
    what a deployment tunes, so it is what the guarantee has to be stated in
    terms of. The handler sweeps from inside itself, which is the awkward-looking
    part and the point: the sweep runs *while the job is running*, at a moment
    when more than one whole lease has passed since the claim.
    """
    lease = WorkerSettings(job_lease_seconds=1).job_lease
    swept_during: list[int] = []

    def works_longer_than_its_lease(context: CommandContext) -> HandlerResult:
        for step in range(3):
            time.sleep(0.6)
            context.emit({"type": "progress", "detail": f"step {step}"})
            swept_during.append(sweeper.sweep())
        return HandlerResult(state=JobState.SUCCEEDED, summary={"steps": 3})

    job_id = dispatched_job(session_factory, jobs, tenant_id)
    started = datetime.now(UTC)
    TaskExecutor(session_factory, registry_of(works_longer_than_its_lease), lease=lease).execute(
        tenant_id=tenant_id, job_id=job_id
    )

    assert datetime.now(UTC) - started > lease, (
        "the test proves nothing unless the job outlived a whole lease"
    )
    assert swept_during == [0, 0, 0], (
        "a job reporting progress inside its lease must never be swept; the "
        "lease bounds silence, not duration"
    )
    assert job_row(session_factory, job_id).status == JobState.SUCCEEDED.value


def test_a_job_that_goes_quiet_for_longer_than_its_lease_is_swept(
    session_factory, jobs, sweeper, tenant_id
):
    """The other side of the same line, so the pair is not vacuous.

    Without this, the test above would pass just as well against a sweep that
    never times anything out. Same tiny lease, same elapsed time, one difference
    — the handler says nothing — and the outcome inverts.
    """
    lease = WorkerSettings(job_lease_seconds=1).job_lease
    job_id = dispatched_job(session_factory, jobs, tenant_id)
    with session_factory() as session:
        jobs.claim(session, tenant_id=tenant_id, job_id=job_id, lease=lease)
        session.commit()

    time.sleep(1.2)

    assert sweeper.sweep() == 1
    assert job_row(session_factory, job_id).status == JobState.TIMED_OUT.value
