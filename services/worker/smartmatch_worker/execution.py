"""Executing one delivered command.

Architecture v1.1 §1.6 and §1.7, component ``E`` in the dispatch sequence. The
dispatcher creates a Cloud Tasks entry; this is what consumes it.

## The claim is the whole safety argument

Cloud Tasks delivers **at least once**. A duplicate delivery is not a fault to
be defended against occasionally — it is a routine event, produced by a slow
response, a retried acknowledgement, or a worker that was killed mid-request.

:meth:`smartmatch_persistence.jobs.JobRepository.claim` moves
``dispatched -> running`` with a conditional UPDATE, so exactly one delivery can
win. Everything else this module does hangs off that single fact:

* A losing delivery is **acknowledged**, not failed. Returning an error would
  make Cloud Tasks retry a task whose work is already running or already done,
  which is the exact multiplication the claim exists to prevent.
* A losing delivery **executes nothing**. It does not re-read, re-emit, or
  re-transition; it reports the job's current state and stops.

## Nothing may leave a job in ``running``

A job in ``running`` with no worker behind it is invisible work: the SSE stream
shows progress that will never arrive, no operations view lists it as needing
attention, and the only evidence anything went wrong is an absence. So every
path out of a claimed job — handler success, declared failure, unknown command
type, or an exception nobody predicted — ends in a terminal transition.

The one case that could not be closed by any of those paths is a worker that
dies *after* claiming and before recording an outcome — a killed process, an
evicted pod, an OOM, a drained node, or the ``500`` ``main`` returns when
PostgreSQL itself refuses the write. No code in this module runs at that moment,
so no amount of care inside it could have helped: the job simply stayed
``running`` until a human noticed.

**J9 closes it, and the mechanism is a deadline rather than liveness
detection.** Nothing tries to discover whether a worker is alive; there is only
a promise with an expiry on it, exactly as the outbox already recovers a crashed
dispatcher. Four writes, all of them in
:class:`~smartmatch_persistence.jobs.JobRepository`:

1. :meth:`~smartmatch_persistence.jobs.JobRepository.claim` sets
   ``job.lease_expires_at`` in the same conditional UPDATE that takes
   ``dispatched -> running``, so there is no window in which a job is claimed
   and undated.
2. :meth:`_emit` renews it with every progress event, so a job that is still
   saying something is never swept.
3. Every terminal transition clears it — :meth:`_finish` goes through
   ``transition``, which writes ``NULL`` unless a lease is given.
4. :class:`StalledJobSweeper` takes ``running -> timed_out`` for whatever is
   left, from the dispatcher's scheduled pass (J8).

What that does **not** close is a handler that hangs while its process stays
healthy for longer than the lease with nothing to report. It is swept, its work
may still be running, and its eventual outcome is discarded by :meth:`_finish`'s
``expected_from='running'`` guard — recorded as ``job.outcome_discarded`` rather
than lost. That is the deliberate trade: the lease bounds *silence*, and a
handler that intends to work for longer than one must emit progress. See
``smartmatch_persistence.jobs`` for the argument against renewing on a timer
instead.

## The delivery is identifiers, and only identifiers

The delivery names a tenant and a job. Everything else is re-read from
PostgreSQL, because a task can sit in the queue for minutes while consent,
budget, or approval change — and because a delivery the worker trusts is one an
attacker who reaches the queue can dictate.

That includes the command's own parameters, which is worth saying plainly now
that there are some: ``job.payload`` (migration ``0005``) is read off the job row
by the same ``_read_job`` that reads the status, and reaches the handler on
:class:`~smartmatch_worker.handlers.CommandContext`. Nothing here copies a
parameter out of the request body. The two are different senses of the word
"payload" and only one of them is authoritative — the delivery still carries a
tenant id and a job id and nothing else, and widening it would hand the queue
the ability to say what a job is for.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Final, Literal

from smartmatch_domain.jobs import JobState
from smartmatch_persistence.jobs import (
    DEFAULT_JOB_LEASE,
    JobRecord,
    JobRepository,
    TimedOutJobRecord,
)
from sqlalchemy.orm import Session, sessionmaker

from smartmatch_worker.handlers import (
    BudgetFailure,
    CommandContext,
    CommandRegistry,
    HandlerFailure,
    HandlerResult,
    PolicyFailure,
    ProviderFailure,
)

__all__ = ["ExecutionOutcome", "StalledJobSweeper", "TaskExecutor"]

logger = logging.getLogger(__name__)

#: How a declared handler failure becomes a job state. Resolved along the
#: exception's MRO by :func:`_state_for`, so a more specific failure defined
#: later inherits its parent's meaning rather than silently falling through to
#: the unexpected arm.
_FAILURE_STATES: Final[dict[type[HandlerFailure], JobState]] = {
    PolicyFailure: JobState.FAILED_POLICY,
    BudgetFailure: JobState.FAILED_BUDGET,
    ProviderFailure: JobState.FAILED_PROVIDER,
}

#: Where an unclassified exception lands. ``failed_provider`` rather than
#: ``failed_policy`` because it is one of the two states with a transition back
#: to ``queued``: an unexpected error is, by definition, one nobody has decided
#: is permanent, and parking it beyond recovery decides that for them.
_UNEXPECTED_FAILURE_STATE: Final[JobState] = JobState.FAILED_PROVIDER


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    """What one delivery amounted to.

    Attributes:
        job_id: The job the delivery named.
        status: ``executed`` when this delivery ran the handler, ``duplicate``
            when another delivery had already claimed the job (or the job had
            moved on), ``early`` when the delivery arrived before the dispatcher
            recorded the job as dispatched, and ``unknown`` when no such job
            exists for that tenant.
        state: The job's state afterwards, or ``None`` for an unknown job.

    ``executed``, ``duplicate``, and ``unknown`` are reported to Cloud Tasks with
    ``200``: none can be improved by asking again, since a duplicate is expected
    and an unknown job cannot become known on retry.

    ``early`` is the exception and is reported ``503``. It means the delivery
    raced the dispatcher's second transaction and the job is still ``queued``,
    which *is* fixed by asking again a moment later. Acknowledging it instead
    would strand the job permanently — see :meth:`TaskExecutor.execute`.
    """

    job_id: uuid.UUID
    status: Literal["executed", "duplicate", "early", "unknown"]
    state: JobState | None


class TaskExecutor:
    """Runs one delivered command to a terminal state.

    Args:
        session_factory: Produces sessions. The executor owns its transaction
            boundaries — the claim commits on its own so it is visible to a
            racing delivery immediately, progress events commit as they happen
            so a client can see them, and the terminal transition commits with
            the event that describes it so a job can never be terminal with no
            record of why.
        registry: The command types this worker can execute.
        lease: How long this worker's claim on a job stays good without the
            handler saying anything. It bounds silence, not duration — see the
            module docstring, and :class:`StalledJobSweeper` for what happens
            when it runs out.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        registry: CommandRegistry,
        *,
        lease: timedelta = DEFAULT_JOB_LEASE,
    ) -> None:
        self._session_factory = session_factory
        self._registry = registry
        self._lease = lease
        self._jobs = JobRepository()

    def execute(self, *, tenant_id: uuid.UUID, job_id: uuid.UUID) -> ExecutionOutcome:
        """Claim and execute one job.

        Returns:
            An :class:`ExecutionOutcome`. Every return value is an
            acknowledgement — the caller answers ``200`` for all of them.

        Raises:
            Exception: only if PostgreSQL itself could not be reached or written.
                That is worth surfacing as a ``5xx``: it is the one failure the
                worker genuinely cannot record, and the queue's retry is the
                only thing left that might.
        """
        job = self._read_job(tenant_id, job_id)
        if job is None:
            # Nothing to run and nothing to record against. Retrying cannot make
            # the job appear, so this is acknowledged rather than failed — but it
            # is logged loudly, because a task naming a job that does not exist
            # means either a deleted job or a delivery nobody's dispatcher made.
            logger.warning("task delivery names no job: tenant=%s job=%s", tenant_id, job_id)
            return ExecutionOutcome(job_id=job_id, status="unknown", state=None)

        if not self._claim(tenant_id, job_id):
            # The claim failed, and *why* decides whether the queue should try
            # again. Treating every failure as a duplicate loses work.
            current = self._read_job(tenant_id, job_id)
            state = current.status if current is not None else None

            if state is JobState.QUEUED:
                # This delivery beat the dispatcher. The dispatcher enqueues the
                # task and records ``queued -> dispatched`` in a *separate*
                # transaction afterwards, so the task can be live in the queue
                # while the job still reads ``queued`` — and ``claim`` requires
                # ``dispatched``.
                #
                # Acknowledging here would be silent loss: Cloud Tasks deletes an
                # acknowledged task, the outbox row is already marked dispatched
                # so no dispatcher revisits it, and ``queued`` has no route to
                # ``redrive_pending``, so re-drive cannot rescue it either. The
                # work would simply never run, with nothing anywhere saying so.
                #
                # Asking the queue to redeliver is exactly right: the window is
                # one transaction wide, and the retry finds the job dispatched.
                logger.info(
                    "job %s delivered before dispatch was recorded; asking the queue to retry",
                    job_id,
                )
                return ExecutionOutcome(job_id=job_id, status="early", state=state)

            # Another delivery won, or the job was cancelled between dispatch and
            # delivery. Either way this delivery must not execute, and must not
            # ask the queue to try again — the job has moved on, and it will not
            # move back.
            logger.info(
                "task delivery did not claim job %s (state=%s); acknowledging without executing",
                job_id,
                state.value if state is not None else "gone",
            )
            return ExecutionOutcome(job_id=job_id, status="duplicate", state=state)

        # Re-read after the claim so the handler sees the row as it is now,
        # including the ``running`` status it was just moved to.
        claimed = self._read_job(tenant_id, job_id)
        if claimed is None:  # pragma: no cover - a job deleted mid-claim
            logger.warning("job %s disappeared immediately after being claimed", job_id)
            return ExecutionOutcome(job_id=job_id, status="unknown", state=None)

        return self._run_claimed_job(claimed)

    # -- internals ---------------------------------------------------------

    def _run_claimed_job(self, job: JobRecord) -> ExecutionOutcome:
        """Execute a job this delivery owns, and record how it ended."""
        self._emit(job, {"type": "job.started", "command_type": job.command_type})

        handler = self._registry.handler_for(job.command_type)
        if handler is None:
            # The worst available outcome would be to acknowledge this silently:
            # the job would report success and nothing would have happened. It is
            # ``failed_provider`` — re-drivable — because the usual cause is
            # version skew during a rolling deploy, which a human fixes by
            # finishing the deploy and re-driving, not by abandoning the work.
            return self._finish(
                job,
                _UNEXPECTED_FAILURE_STATE,
                {
                    "type": "job.failed",
                    "reason": "unknown_command_type",
                    "detail": (
                        f"this worker has no handler for command type "
                        f"{job.command_type!r}; it can execute "
                        f"{sorted(self._registry.command_types)}"
                    ),
                },
            )

        context = CommandContext(
            job=job,
            emit=lambda payload: self._emit(job, payload),
        )

        try:
            result = handler(context)
        except HandlerFailure as exc:
            state = _state_for(exc)
            logger.info("job %s failed (%s): %s", job.id, state.value, exc)
            return self._finish(
                job,
                state,
                {
                    "type": "job.failed",
                    "reason": exc.reason,
                    "detail": str(exc),
                },
            )
        except Exception as exc:
            # Nobody predicted this one, which is exactly why it is logged with a
            # traceback and why the job must still reach a terminal state. A
            # handler bug that left jobs in ``running`` would be discovered only
            # by someone noticing work that never finished.
            logger.exception("job %s: handler raised an unexpected exception", job.id)
            return self._finish(
                job,
                _UNEXPECTED_FAILURE_STATE,
                {
                    "type": "job.failed",
                    "reason": "unhandled_error",
                    "detail": f"{type(exc).__name__}: {exc}",
                },
            )

        return self._complete(job, result)

    def _complete(self, job: JobRecord, result: HandlerResult) -> ExecutionOutcome:
        """Record a handler's successful (or partial) completion."""
        return self._finish(
            job,
            result.state,
            {
                "type": "job.completed",
                "state": result.state.value,
                "summary": result.summary,
            },
        )

    def _finish(self, job: JobRecord, state: JobState, event: dict[str, Any]) -> ExecutionOutcome:
        """Move the job to its terminal state and record why, in one transaction.

        A terminal state with no event explaining it, or an event describing an
        outcome the job never reached, would each be worse than neither. They
        commit together.

        The transition is conditional on the job still being ``running``. If it
        is not — a cancellation landed while the handler worked, which
        ``running -> cancelled`` permits — the job's own state is left alone and
        the discarded outcome is recorded instead, so the stream shows what
        happened rather than falling silent.
        """
        with self._session_factory() as session:
            applied = self._jobs.transition(
                session,
                tenant_id=job.tenant_id,
                job_id=job.id,
                to_state=state,
                expected_from=JobState.RUNNING,
            )
            if not applied:
                logger.warning(
                    "job %s left 'running' before its outcome was recorded; "
                    "the %s outcome is being discarded",
                    job.id,
                    state.value,
                )
                event = {
                    "type": "job.outcome_discarded",
                    "state": state.value,
                    "detail": "the job left 'running' before this outcome could be applied",
                }
            self._jobs.append_event(session, tenant_id=job.tenant_id, job_id=job.id, payload=event)
            session.commit()

        final = self._read_job(job.tenant_id, job.id)
        return ExecutionOutcome(
            job_id=job.id,
            status="executed",
            state=final.status if final is not None else None,
        )

    def _emit(self, job: JobRecord, payload: dict[str, Any]) -> int:
        """Append one job event, renew the lease, and commit both immediately.

        Its own transaction, so a client following the SSE stream sees progress
        while the work is still running. Batching these until the end would make
        the stream a summary delivered after the fact, which is not what a
        stream is for.

        **The renewal rides the event, and that is the whole of J9's step 2.**
        An emitted event is the only evidence this process has that the *work*
        is progressing rather than merely that the process is up, so it is what
        the lease is extended on. The two writes share the transaction because a
        renewal without its event would extend a deadline on the strength of
        nothing, and an event without its renewal would let a job the client can
        watch making progress be swept out from under it.

        A renewal that finds the job no longer ``running`` is reported rather
        than ignored. It means the handler is working a job that has already
        been cancelled or already been swept, and the second is the visible
        symptom of a lease configured shorter than the work — the one thing an
        operator can act on. The event is still appended: the job's stream
        should show what the handler was doing when it lost the job, and
        ``job_event`` has no state precondition to violate.
        """
        with self._session_factory() as session:
            record = self._jobs.append_event(
                session, tenant_id=job.tenant_id, job_id=job.id, payload=payload
            )
            renewed = self._jobs.renew_lease(
                session, tenant_id=job.tenant_id, job_id=job.id, lease=self._lease
            )
            session.commit()

        if not renewed:
            logger.warning(
                "job %s: progress was recorded but its lease could not be renewed; "
                "the job is no longer 'running'. It was cancelled, or its lease "
                "expired and the sweep timed it out while this handler was still "
                "working — in which case this worker's outcome will be discarded",
                job.id,
            )

        return record.sequence

    def _claim(self, tenant_id: uuid.UUID, job_id: uuid.UUID) -> bool:
        """Take ``dispatched -> running`` for this delivery, committing at once.

        Committed on its own rather than as part of a longer transaction: the
        claim has to be visible to a racing delivery *before* the work starts,
        or both deliveries can be inside their own transactions believing they
        won.

        The lease goes on in the same statement, not afterwards. A follow-up
        write would leave a window — narrow, and exactly the width of the defect
        J9 exists to close — in which the job is ``running`` with no deadline on
        it, and a worker that died inside that window would leave behind the one
        row shape the sweep is required to skip.
        """
        with self._session_factory() as session:
            claimed = self._jobs.claim(
                session, tenant_id=tenant_id, job_id=job_id, lease=self._lease
            )
            session.commit()
        return claimed

    def _read_job(self, tenant_id: uuid.UUID, job_id: uuid.UUID) -> JobRecord | None:
        """Read the authoritative job row.

        Scoped by ``(tenant_id, id)``, so a delivery naming the wrong tenant
        finds nothing rather than another tenant's job. That is a property of
        the composite key, not of a filter this method remembered to apply.
        """
        with self._session_factory() as session:
            return self._jobs.get(session, tenant_id=tenant_id, job_id=job_id)


class StalledJobSweeper:
    """Times out jobs whose worker never came back (J9).

    The counterpart to ``OutboxDispatcher.reclaim_stranded``, one table over,
    and deliberately **not** the same code. ``transaction-boundary-defects.md``
    §3.3 argued that case and the argument holds: the predicates differ, the
    recovery writes differ, and the two tables have no relationship a shared
    "expired lease reaper" could exploit. What they share is a place — the
    dispatcher's scheduled pass — and a purpose, which is to be the one surface
    an operator reads for *work that had to be rescued*.

    Args:
        session_factory: Produces sessions. The sweep owns its transaction,
            because each job's state change and the event explaining it commit
            together for the reason :meth:`TaskExecutor._finish` gives.
        limit: Most jobs to time out in one pass. A bound rather than a
            throttle: a sweep that found ten thousand expired leases has found
            an incident, and taking them a hundred at a time keeps one pass's
            transaction short instead of holding row locks across the whole
            table while the dispatcher waits behind it.

    ## Every sweep writes an event, and the event is the point

    A job that goes terminal with nothing saying why is the failure this whole
    module is organised against. It is worse here than anywhere else: the client
    watching the SSE stream saw ``job.started`` and then silence, and without an
    event the state change is silence too — the job simply *is* ``timed_out``
    one day, with no record of when the deadline was, how long it had passed, or
    that a sweep rather than a worker decided it. So the transition and its
    ``job.timed_out`` event share a transaction, exactly as
    :meth:`TaskExecutor._finish` does, and the event carries the missed deadline
    because the row stops carrying it the instant the sweep commits.

    ## Logged after the commit, and only about what committed

    The same rule ``OutboxDispatcher.reclaim_stranded`` learned. A batch that
    raises part-way through would otherwise have announced jobs as timed out
    while the transaction rolled every one of them back, leaving an operator
    reconciling a log against a metric that disagreed with it — with the log the
    one that was wrong.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        limit: int = 100,
    ) -> None:
        self._session_factory = session_factory
        self._limit = limit
        self._jobs = JobRepository()

    def sweep(self) -> int:
        """Time out every job whose lease has expired.

        Returns:
            How many jobs were moved ``running -> timed_out``. Normally zero. A
            non-zero count is not a queue-depth reading to be smoothed over
            time: it says a worker died holding work, or a handler went silent
            for longer than its lease, and either deserves an operator's
            attention on its own.

        Raises:
            Exception: whatever the database raised. The caller guards this —
            the sweep is janitorial, and the rule ``run_once`` established is
            that tidying up yesterday's wreckage must never cost today's
            dispatch. It is not swallowed *here* because a sweeper that reported
            zero when it had failed would be indistinguishable from a healthy
            one, and the count is the metric.
        """
        with self._session_factory() as session:
            swept: list[TimedOutJobRecord] = self._jobs.sweep_expired_leases(
                session, limit=self._limit
            )
            for record in swept:
                self._jobs.append_event(
                    session,
                    tenant_id=record.tenant_id,
                    job_id=record.id,
                    payload={
                        "type": "job.timed_out",
                        "reason": "lease_expired",
                        "detail": (
                            "no worker reported on this job before its lease expired at "
                            f"{record.lease_expired_at.isoformat()}; it was timed out by "
                            "the scheduled sweep"
                        ),
                    },
                )
            session.commit()

        for record in swept:
            # WARNING, never INFO. Reaching here means a delivery claimed this
            # job and no code ever came back to say how it ended — the failure
            # this module's whole design is arranged to make impossible from the
            # inside, arrived at from the outside.
            logger.warning(
                "job %s (%s) held a lease that expired at %s with no outcome recorded; "
                "timed out by the sweep. Re-drive it to re-run the work",
                record.id,
                record.command_type,
                record.lease_expired_at.isoformat(),
            )

        return len(swept)


def _state_for(failure: HandlerFailure) -> JobState:
    """Map a declared failure to its job state, following the exception's MRO.

    Matching on the exact class would mean that a future ``ConsentWithdrawn``
    subclassing :class:`~smartmatch_worker.handlers.PolicyFailure` landed in
    ``failed_provider`` and became re-drivable — the opposite of what its parent
    means. Walking the MRO makes the mapping inheritable, which is how the
    exception hierarchy already reads.

    A failure that inherits from :class:`HandlerFailure` and nothing more
    specific still falls through to ``failed_provider``: an unclassified failure
    is one nobody has decided is permanent, and the re-drivable state is the one
    that does not decide it for them.
    """
    for klass in type(failure).__mro__:
        state = _FAILURE_STATES.get(klass)
        if state is not None:
            return state
    return _UNEXPECTED_FAILURE_STATE
