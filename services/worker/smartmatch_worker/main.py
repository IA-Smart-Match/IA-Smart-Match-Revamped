"""Worker HTTP boundary.

Architecture v1.1 §3.1: a private Cloud Run service with two legitimate callers
and four endpoints — a health probe, the one that executes a command Cloud Tasks
delivered, the one Cloud Scheduler drives to run a dispatcher pass, and a read of
that pass's heartbeat.

The two callers are kept apart all the way down: separate audiences, separate
service-account allowlists, separate verifiers. Cloud Tasks may deliver work and
may not drive dispatch; Cloud Scheduler may drive dispatch and may not deliver
work. Neither needs the other's permission, so neither is given it.

## Order of operations, which is the security property

``/tasks/execute`` does exactly three things, in this order, and the order is
the control:

1. **Verify the caller's OIDC task identity.** Before the body is read, before
   it is parsed, before anything is looked up. That is why the body arrives as a
   raw :class:`~starlette.requests.Request` rather than as a declared model:
   FastAPI resolves a declared body *before* the handler runs, so an
   unauthenticated caller sending a malformed body would be answered ``422`` —
   a validation error, telling them something about this service, on a request
   that should never have been read at all.
2. **Parse the delivery.** Identifiers only: a tenant and a job.
3. **Execute**, which re-reads the authoritative job from PostgreSQL.

## Status codes are part of the contract with Cloud Tasks

The queue retries on failure, so every status here is a decision about whether
the delivery should come back:

* ``200`` — the delivery was handled. Includes a **duplicate** delivery whose
  job another delivery already claimed: at-least-once delivery makes that the
  normal case, and answering anything else would ask the queue to retry a task
  that is already running.
* ``503`` — the delivery arrived before the dispatcher recorded the job as
  dispatched, so the job still reads ``queued`` and the claim could not match.
  The one case where retrying genuinely helps: the race window is a single
  transaction wide. Acknowledging it instead would delete the task and strand
  the job, since nothing else re-delivers it and ``queued`` has no route to
  ``redrive_pending``.
* ``401`` — no credential presented.
* ``403`` — a credential that did not verify. Undifferentiated on purpose;
  which check failed is in the log, not in the response.
* ``501`` — task-identity verification is not configured in this deployment, so
  nothing can be verified and everything is refused. Distinguished from ``403``
  because the caller cannot fix it by presenting a better token, and because an
  operator seeing ``501`` should look at the deployment rather than the queue.
* ``500`` — PostgreSQL could not be reached or written. The only failure the
  worker genuinely cannot record, and the only one worth a retry.

``/operations/dispatch`` answers with the same vocabulary, aimed at Cloud
Scheduler rather than Cloud Tasks. It adds one meaning to ``501``: no task queue
is configured, so the dispatcher has nothing to create tasks *in*. That is a
deployment fact rather than a caller's mistake, and it fails closed for the
reason the identity path does — the alternative, defaulting to
``FixtureTaskQueue``, would answer ``200`` while every dispatched task went into
a dictionary in process memory and vanished with the container. A ``501`` that
says "not configured" is the only honest answer a build with no Cloud Tasks
client can give.

Its ``500`` means the claim itself failed, and the non-2xx is the point: it moves
Cloud Scheduler's own attempt-failure metric, which is where a pass that ran and
broke belongs — as distinct from a pass that never ran, which is what the
heartbeat's absence is for.

This resolves security finding S-001. The scaffold's stub rejected everything
unconditionally and was safe for exactly that reason; what replaces it must
therefore be measured against the same standard, and it is: with nothing
configured, :func:`~smartmatch_worker.identity.build_task_verifier` returns a
verifier that refuses every request, so the default posture is unchanged.

## The scheduled pass, and why the loop is not in this repository (J8)

``POST /operations/dispatch`` runs one
:class:`~smartmatch_worker.dispatcher.ScheduledPass`: the J9 stalled-job sweep,
then the outbox dispatcher's ``run_once`` — which itself begins with J12's
reclaim — then a lag measurement. Cloud Scheduler is what calls it.

An in-process poll loop was the obvious alternative and it is the wrong shape
for the platform this targets. A Cloud Run service has no process between
requests; a loop needs ``min-instances >= 1`` to exist at all, and even then it
is a thread inside one container whose death is **silent** — nothing outside
that container can tell a loop that stopped from a loop with nothing to do. A
scheduler firing an HTTP request is the opposite: every tick is an external
event with a status code, recorded by something that is not the thing being
watched. Given that this pass is the only thing that recovers stranded outbox
rows and stalled jobs, being able to observe that it *ran* matters more than the
few seconds of latency a timer would save.

**The endpoint calls ``run_once`` and there is deliberately no narrower entry
point to call.** J8's first constraint: ``run_once`` is where
``reclaim_stranded`` lives, so whatever schedules dispatch necessarily schedules
the reclaim. No configuration here can separate them, because there is no
setting that could.

## What to alert on — and why the obvious alert is not enough

Nothing here can create an alert policy; there is no monitoring stack and
nothing is deployed. What this service owes is the *signal* an alert can be
built on, and the argument for which alerts are the right ones. Both are below.
The signal is the log line
:data:`~smartmatch_worker.dispatcher.HEARTBEAT_MESSAGE`, written once per
completed pass with every number on it, plus the same numbers in this
endpoint's response body and on ``GET /operations/dispatch``.

**1. The schedule stopped firing.** This is the alert J8 says the design must
support, and it must fire on *silence*, not on lag being high. The reason is
sharper than "a stalled dispatcher reports lag zero": a stalled dispatcher
reports **nothing at all**, because ``lag()`` is taken *by the pass*, so no pass
means no sample. And a lag metric sampled independently would still not save it,
because ``pending_count`` shares ``_claimable_predicate`` with the claim — so
the rows a dead dispatcher stranded are precisely the rows it does not count.
The measurement that should notice a dispatcher's absence is blind to the damage
that absence does.

That doubles back on itself, which is why this alert matters more than any other
here: a dispatcher that is not running is what strands outbox rows, and is then
also what stops anything reclaiming them. The failure is silent, self-concealing,
and compounding.

*Shape:* a log-based counter matching ``HEARTBEAT_MESSAGE``, with an **absence**
condition — no data for some small multiple of the schedule interval. It has to
be evaluated by something outside this service, since the condition being tested
is that this service is not running. Cloud Scheduler's own attempt-failure
metric belongs beside it and is not a substitute: it catches a job that fired and
got an error, not one that stopped firing.

**2. ``reclaimed > 0``, on its own.** J8's second constraint. A reclaimed row
sits outside the ``claimed == dispatched + already_existed + failed`` identity
and should always be zero. Non-zero says a dispatcher died, or the database
refused a write, at the one moment in a row's life when that cannot be retried
away. It is a statement about the dispatcher's health, not the queue's depth, so
it does not belong in a lag threshold — any non-zero value is the condition.

**3. ``timed_out > 0``, beside it and for the same reason.** J9's half of the
same surface: a worker claimed a job and never came back.
:attr:`~smartmatch_worker.dispatcher.ScheduledPassOutcome.rescued` is the sum,
and it is the number to page on; the two fields tell an operator which table to
open.

**4. ``unexplained_failures``, never ``failed``.** A benign lease race between
two dispatcher instances lands in ``failed`` and is reported apart from it in
``contended``. Alerting on ``failed`` would page someone for a race that
resolves itself, and would do so *more* the more instances they run.

**5. Lag, last.** ``pending`` and ``oldest_age``, through
:meth:`~smartmatch_worker.dispatcher.DispatcherLag.exceeds`. It is the alert
this platform already had a placeholder for, and it is listed last on purpose:
it is the only one of the five that a dispatcher which is not running cannot
trip.

**6. ``sweep_failed`` on consecutive passes.** One is a deadlock; a run of them
is J9 not working, with ``timed_out`` reading zero for the wrong reason.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ValidationError
from smartmatch_persistence.engine import create_session_factory
from smartmatch_persistence.jobs import DEFAULT_JOB_LEASE
from smartmatch_providers.tasks import TaskQueue
from sqlalchemy.orm import Session, sessionmaker

from smartmatch_worker.config import WorkerSettings, get_settings
from smartmatch_worker.dispatcher import (
    OutboxDispatcher,
    ScheduledPass,
    ScheduledPassOutcome,
)
from smartmatch_worker.execution import StalledJobSweeper, TaskExecutor
from smartmatch_worker.handlers import CommandRegistry, default_registry
from smartmatch_worker.identity import (
    TaskIdentity,
    TaskIdentityError,
    TaskIdentityUnconfigured,
    TaskIdentityVerifier,
    build_task_verifier,
)

__all__ = ["app", "create_app"]

logger = logging.getLogger(__name__)


class TaskDelivery(BaseModel):
    """The body Cloud Tasks delivers.

    Identifiers only, matching what the dispatcher enqueues. Anything else in
    the body is ignored rather than trusted: a task can sit in the queue while
    consent, budget, or approval change, so the delivery is a notification that
    work exists, never a description of it.
    """

    tenant_id: uuid.UUID
    job_id: uuid.UUID


class TaskExecutionResponse(BaseModel):
    """What the worker tells the queue about a delivery it handled.

    Attributes:
        job_id: The job the delivery named.
        status: ``executed``, ``duplicate``, or ``unknown``.
        state: The job's state afterwards, when there is a job.
    """

    job_id: uuid.UUID
    status: str
    state: str | None = None


class DispatchPassResponse(BaseModel):
    """What one scheduled pass did.

    Every field an operator alerts on, in the response as well as in the
    heartbeat log line. The response is the convenient copy and the log line is
    the durable one: a response requires something to have been listening, and
    the alert that matters most here is the one that has to work when nothing
    was.

    Attributes:
        unexplained_failures: ``failed`` minus ``contended``. **This is the
            failure number to alert on**, not ``failed`` — see the module
            docstring.
        rescued: ``reclaimed + timed_out``. Work that had to be recovered
            because something died holding it. Should be zero.
        sweep_failed: When true, ``timed_out`` is zero because the sweep did not
            run, not because there was nothing to sweep.
        pending: ``null`` when the lag measurement itself failed, which is a
            different fact from a lag of zero.
    """

    ran_at: datetime
    finished_at: datetime
    duration_ms: int
    claimed: int
    dispatched: int
    already_existed: int
    failed: int
    unexplained_failures: int
    contended: int
    reclaimed: int
    timed_out: int
    rescued: int
    sweep_failed: bool
    pending: int | None = None
    oldest_age_seconds: float | None = None


class DispatcherHeartbeatResponse(BaseModel):
    """Whether this instance can run a pass, and when it last did.

    Attributes:
        configured: Whether a task queue and a database are wired up here. A
            ``false`` with a ``null`` ``last_completed`` is a deployment that
            cannot dispatch at all, which is a different problem from one that
            can and has not.
        last_completed: The last pass **this process** completed, or ``null``.
            Process-local by construction, and on Cloud Run with scale-to-zero
            the instance answering this read is routinely not the one that ran
            the pass. It answers "has this container done a pass"; it cannot
            answer "is the schedule firing", and nothing held in a process's
            memory could. That question is what the heartbeat log line and an
            absence alert are for.
    """

    configured: bool
    last_completed: DispatchPassResponse | None = None


def create_app(
    *,
    settings: WorkerSettings | None = None,
    session_factory: sessionmaker[Session] | None = None,
    task_verifier: TaskIdentityVerifier | None = None,
    scheduler_verifier: TaskIdentityVerifier | None = None,
    registry: CommandRegistry | None = None,
    task_queue: TaskQueue | None = None,
) -> FastAPI:
    """Build the worker application.

    Every collaborator is injectable, which is what makes the identity control
    testable without a network: a test supplies its own verifier — a real one,
    with its own keys and clock — rather than patching verification away. A test
    that removed the verifier would prove nothing about the verifier, and this
    is the one control where that distinction decides whether the endpoint is
    safe.

    Args:
        settings: Configuration. Read from the environment when omitted, and
            only then — so constructing an app in a test never depends on the
            environment it runs in.
        session_factory: Database sessions. Built from ``settings`` at startup
            when omitted.
        task_verifier: Verifies the Cloud Tasks OIDC identity. Built from
            ``settings`` at startup when omitted, which — absent configuration —
            means a verifier that refuses everything.
        scheduler_verifier: Verifies the Cloud Scheduler OIDC identity for
            ``/operations/dispatch``. Built from its own settings, against its
            own audience and its own allowlist — never derived from
            ``task_verifier``, because sharing one would mean the queue's
            credentials also drove dispatch.
        registry: Command handlers. The shipped registry when omitted.
        task_queue: Where the dispatcher creates tasks. **No default**, and the
            absence is not an oversight: this repository ships only
            ``FixtureTaskQueue``, an in-memory double, and defaulting to it
            would give a deployment a dispatcher that reported success while
            every task it "created" lived in a dictionary until the container
            went away. Without one, ``/operations/dispatch`` answers ``501``.

    Returns:
        A configured :class:`~fastapi.FastAPI` application.
    """
    registry = registry or default_registry()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Build shared resources once per process.

        The session factory and the verifier are built here rather than per
        request: a connection pool created per request is not a pool, and a
        verifier rebuilt per request would discard the key cache a JWKS source
        needs.

        Anything the caller injected is left alone, so this runs the environment
        path only for a real deployment.
        """
        resolved = settings or get_settings()
        app.state.settings = resolved

        if app.state.session_factory is None:
            app.state.session_factory = create_session_factory(resolved.database_url)
            app.state.owns_session_factory = True

        if app.state.task_verifier is None:
            # No JWKS source and no signature backend are passed, so this
            # returns a verifier that refuses everything. Supplying them is a
            # deliberate deployment act; see ``identity`` for what is missing
            # and why it is not faked.
            app.state.task_verifier = build_task_verifier(
                expected_audience=resolved.task_audience,
                allowed_service_accounts=resolved.allowed_service_accounts,
            )

        if app.state.scheduler_verifier is None:
            # Built from the scheduler's own settings and nothing else. A
            # fallback to the task audience or the task allowlist would quietly
            # let a deployment that configured only the queue accept
            # queue-minted tokens on the endpoint that drives dispatch.
            app.state.scheduler_verifier = build_task_verifier(
                expected_audience=resolved.scheduler_audience,
                allowed_service_accounts=resolved.allowed_scheduler_accounts,
            )

        # Built once per process, because `ScheduledPass` holds this instance's
        # heartbeat and one rebuilt per request would have nothing to remember.
        _scheduled_pass(app)

        yield

        if app.state.owns_session_factory and app.state.session_factory is not None:
            app.state.session_factory.kw["bind"].dispose()

    app = FastAPI(
        title="SmartMatch Worker",
        version="0.1.0",
        description=(
            "Private Cloud Tasks target. Not internet-facing: ingress is internal, "
            "and every request must carry a verified OIDC service identity."
        ),
        lifespan=lifespan,
    )

    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.task_verifier = task_verifier
    app.state.scheduler_verifier = scheduler_verifier
    app.state.registry = registry
    app.state.task_queue = task_queue
    app.state.scheduled_pass = None
    app.state.owns_session_factory = False

    @app.get("/health", tags=["operations"])
    def health() -> dict[str, str]:
        """Liveness probe for the worker service.

        Answers regardless of whether task identity is configured. A worker that
        refused to start without an audience would make a misconfiguration look
        like an outage, and would take the probe down with it — the endpoint
        that tells an operator the process is alive is the last thing that
        should depend on the endpoint they misconfigured.
        """
        return {"status": "ok"}

    @app.post(
        "/tasks/execute",
        tags=["tasks"],
        response_model=TaskExecutionResponse,
    )
    async def execute_task(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> TaskExecutionResponse:
        """Execute one durable command delivered by Cloud Tasks.

        Raises:
            HTTPException: ``401`` with no credential, ``403`` with one that did
                not verify, ``501`` when verification is not configured here,
                ``400`` for a body that is not a task delivery, and ``500`` when
                the outcome could not be recorded in PostgreSQL.
        """
        identity = _verify_task_identity(request.app.state.task_verifier, authorization)

        delivery = await _parse_delivery(request)

        logger.info(
            "task delivery accepted from %s: tenant=%s job=%s",
            identity.email,
            delivery.tenant_id,
            delivery.job_id,
        )

        executor = TaskExecutor(
            request.app.state.session_factory,
            request.app.state.registry,
            # The lease this delivery's claim will carry. Read from settings
            # when the lifespan resolved them, and otherwise the repository's
            # own default — an app constructed directly with its collaborators
            # injected never runs the lifespan, and a claim with no lease would
            # write a `running` row the sweep is required to skip forever.
            lease=_job_lease(request.app),
        )
        try:
            # Off the event loop. Execution is synchronous, blocking, and
            # potentially slow — it talks to PostgreSQL several times and runs a
            # handler of unknown duration. Running that inline would stall every
            # other in-flight delivery on this instance, which for a worker
            # whose whole job is concurrent deliveries is not a small cost.
            outcome = await run_in_threadpool(
                executor.execute, tenant_id=delivery.tenant_id, job_id=delivery.job_id
            )
        except Exception as exc:
            # The job may now be stuck in ``running``: the claim committed and
            # the outcome did not. Nothing here can fix that — recording the
            # failure needs the same database that just refused — so it is
            # surfaced as a 5xx and logged with a traceback. See
            # ``execution`` for the sweeper this is waiting on.
            logger.exception("job %s: execution could not be recorded", delivery.job_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="the command outcome could not be recorded",
            ) from exc

        if outcome.status == "early":
            # The delivery raced the dispatcher's second transaction: the task is
            # live in the queue and the job still reads ``queued``. Unlike every
            # other outcome, this one *is* improved by asking again — the window
            # is one transaction wide — and acknowledging it would strand the job
            # with nothing left to re-deliver it.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="dispatch is not yet recorded for this job; retry shortly",
                headers={"Retry-After": "1"},
            )

        return TaskExecutionResponse(
            job_id=outcome.job_id,
            status=outcome.status,
            state=outcome.state.value if outcome.state is not None else None,
        )

    @app.post(
        "/operations/dispatch",
        tags=["operations"],
        response_model=DispatchPassResponse,
    )
    async def run_dispatch_pass(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> DispatchPassResponse:
        """Run one scheduled dispatcher pass. Cloud Scheduler is the caller.

        Sweeps stalled jobs (J9), reclaims stranded outbox rows and dispatches
        whatever is claimable (J12, J1), and measures lag — see
        :class:`~smartmatch_worker.dispatcher.ScheduledPass` for the order and
        why the sweep is first.

        **Verified against the scheduler's own identity**, before anything is
        read or run, in the order and for the reasons ``/tasks/execute``
        establishes. A caller holding only Cloud Tasks credentials is refused
        here as firmly as an anonymous one.

        Not idempotent, and it does not need to be. Two passes are not a double
        dispatch: the second claims what the first left, and every row the first
        took is either finished or leased and therefore unclaimable. So a
        scheduler that retries a timed-out request costs a little work and
        nothing else, which is why there is no request body, no idempotency key,
        and nothing to replay.

        Raises:
            HTTPException: ``401`` with no credential, ``403`` with one that did
                not verify, ``501`` when scheduler verification is not
                configured here **or** when no task queue is, and ``500`` when
                the outbox claim itself failed.
        """
        _verify_task_identity(request.app.state.scheduler_verifier, authorization)

        scheduled = _scheduled_pass(request.app)
        if scheduled is None:
            # No queue, so there is nothing to create tasks in. Refused rather
            # than run: a pass that claimed rows and could not enqueue them
            # would burn an attempt off every one of them for a reason that is
            # not going to change until someone redeploys.
            logger.warning("dispatch pass refused: no task queue is configured")
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=(
                    "no task queue is configured in this deployment; the dispatcher "
                    "has nothing to create tasks in and refuses to claim rows it "
                    "could not dispatch"
                ),
            )

        try:
            # Off the event loop, for the reason ``/tasks/execute`` gives: the
            # pass is synchronous, talks to PostgreSQL repeatedly, and makes one
            # network call per claimed row.
            outcome = await run_in_threadpool(scheduled.run)
        except Exception as exc:
            # Only a failed claim reaches here — the sweep and the lag read are
            # guarded inside the pass. The 500 is deliberate and is not merely a
            # report of an error: it is what moves Cloud Scheduler's own
            # attempt-failure metric, which is the signal for "a pass ran and
            # broke", as distinct from the heartbeat's absence, which is the
            # signal for "no pass ran".
            logger.exception("the scheduled dispatch pass failed")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="the dispatcher could not claim a batch",
            ) from exc

        return _pass_response(outcome)

    @app.get(
        "/operations/dispatch",
        tags=["operations"],
        response_model=DispatcherHeartbeatResponse,
    )
    def dispatch_heartbeat(request: Request) -> DispatcherHeartbeatResponse:
        """Report the last pass **this instance** completed.

        Unauthenticated, like ``/health`` and on the same reasoning: the worker
        is a private service whose ingress is the control, and this answers with
        counters and timestamps only — no tenant, no job, no identifier of any
        kind. Requiring a minted OIDC identity would make it unreadable by the
        monitoring that is its only audience, which would leave a signal nothing
        could collect.

        **It is not the "is the schedule firing" signal**, and must not be
        mistaken for one. See
        :class:`DispatcherHeartbeatResponse.last_completed` and the module
        docstring: that question is answered by an absence alert on the
        heartbeat *log line*, evaluated somewhere other than here.
        """
        scheduled = _scheduled_pass(request.app)
        if scheduled is None:
            return DispatcherHeartbeatResponse(configured=False)

        last = scheduled.last_completed
        return DispatcherHeartbeatResponse(
            configured=True,
            last_completed=None if last is None else _pass_response(last),
        )

    return app


def _job_lease(app: FastAPI) -> timedelta:
    """This deployment's job lease, or the repository's default.

    The default arm is reached only by an application constructed directly with
    its collaborators injected, which never runs the lifespan and so never
    resolves settings. It is a real lease rather than ``None`` on purpose: a
    claim carrying no deadline writes a ``running`` row that
    ``sweep_expired_leases`` is required to skip, which is the exact row shape
    J9 exists to eliminate.
    """
    settings: WorkerSettings | None = app.state.settings
    return DEFAULT_JOB_LEASE if settings is None else settings.job_lease


def _scheduled_pass(app: FastAPI) -> ScheduledPass | None:
    """Return this process's scheduled pass, building it once.

    Memoized on ``app.state`` because :class:`ScheduledPass` carries this
    instance's heartbeat: one built per request would have nothing to remember
    and ``GET /operations/dispatch`` would always answer "never ran".

    Returns ``None`` when the pass cannot be assembled — no task queue, or no
    session factory. Both are deployment facts and both become a ``501``.

    The lifespan calls this at startup so the ordinary path builds it once,
    before any request. The lazy arm covers an app constructed directly in a
    test, where there is no lifespan to have done it; two threads racing that
    arm would build two passes and lose one heartbeat, which is a cost only a
    test can pay and not one worth a lock.
    """
    existing: ScheduledPass | None = app.state.scheduled_pass
    if existing is not None:
        return existing

    queue: TaskQueue | None = app.state.task_queue
    session_factory: sessionmaker[Session] | None = app.state.session_factory
    if queue is None or session_factory is None:
        return None

    settings: WorkerSettings | None = app.state.settings
    dispatch_batch = 20 if settings is None else settings.dispatch_batch_size
    sweep_batch = 100 if settings is None else settings.sweep_batch_size

    built = ScheduledPass(
        OutboxDispatcher(session_factory, queue),
        StalledJobSweeper(session_factory, limit=sweep_batch),
        batch_size=dispatch_batch,
    )
    app.state.scheduled_pass = built
    return built


def _pass_response(outcome: ScheduledPassOutcome) -> DispatchPassResponse:
    """Render a pass outcome for the wire.

    ``pending`` and ``oldest_age_seconds`` are ``None`` when the lag read
    failed, which the pass reports as a ``None`` lag rather than as zeros. The
    distinction is kept all the way to the response because "nothing is
    pending" and "nobody could tell" are different answers and an operator acts
    differently on each.
    """
    lag = outcome.lag
    dispatch = outcome.dispatch
    return DispatchPassResponse(
        ran_at=outcome.ran_at,
        finished_at=outcome.finished_at,
        duration_ms=round(outcome.duration.total_seconds() * 1000),
        claimed=dispatch.claimed,
        dispatched=dispatch.dispatched,
        already_existed=dispatch.already_existed,
        failed=dispatch.failed,
        unexplained_failures=dispatch.unexplained_failures,
        contended=dispatch.contended,
        reclaimed=dispatch.reclaimed,
        timed_out=outcome.timed_out,
        rescued=outcome.rescued,
        sweep_failed=outcome.sweep_failed,
        pending=None if lag is None else lag.pending,
        oldest_age_seconds=(
            None if lag is None or lag.oldest_age is None else lag.oldest_age.total_seconds()
        ),
    )


def _verify_task_identity(
    verifier: TaskIdentityVerifier | None, authorization: str | None
) -> TaskIdentity:
    """Verify the Cloud Tasks OIDC token, or refuse.

    Fails closed in every direction. A worker with no verifier at all — which
    can only happen if the lifespan never ran — refuses just as firmly as one
    whose verifier rejected the token, because "the control is missing" and "the
    control said no" must produce the same outcome for the caller.

    Raises:
        HTTPException: ``401`` when no credential was presented, ``501`` when
            verification is not configured in this deployment, and ``403`` when
            the credential did not verify.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing task credentials",
        )

    if verifier is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "OIDC task-identity verification is not configured; this endpoint "
                "fails closed until it is"
            ),
        )

    try:
        return verifier.verify(authorization)
    except TaskIdentityUnconfigured as exc:
        logger.warning("task delivery refused: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                f"OIDC task-identity verification is not configured; this endpoint "
                f"fails closed until it is ({exc})"
            ),
        ) from exc
    except TaskIdentityError as exc:
        # The reason goes to the log and not to the caller: telling an attacker
        # which check rejected their token tells them which forgery to refine.
        logger.warning("task delivery rejected: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="task identity could not be verified",
        ) from exc


async def _parse_delivery(request: Request) -> TaskDelivery:
    """Read the delivery body, after the caller has been verified.

    Raises:
        HTTPException: ``400`` if the body is not a task delivery. Not ``422``:
            the caller is Cloud Tasks replaying what the dispatcher enqueued, so
            a body that does not parse is this platform's own defect, and the
            queue retrying it will not help.
    """
    try:
        return TaskDelivery.model_validate(await request.json())
    except (ValidationError, ValueError, TypeError) as exc:
        logger.warning("task delivery body is not a task delivery: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="task delivery must carry a tenant_id and a job_id",
        ) from exc


#: The application uvicorn serves. Built from the environment, which — with
#: nothing configured — is a worker that answers ``/health`` and refuses every
#: task delivery.
app = create_app()
