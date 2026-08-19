"""Worker HTTP boundary.

Architecture v1.1 §3.1: a private Cloud Run service whose only legitimate caller
is Cloud Tasks. Two endpoints — a health probe, and the one that executes a
delivered command.

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

This resolves security finding S-001. The scaffold's stub rejected everything
unconditionally and was safe for exactly that reason; what replaces it must
therefore be measured against the same standard, and it is: with nothing
configured, :func:`~smartmatch_worker.identity.build_task_verifier` returns a
verifier that refuses every request, so the default posture is unchanged.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ValidationError
from smartmatch_persistence.engine import create_session_factory
from sqlalchemy.orm import Session, sessionmaker

from smartmatch_worker.config import WorkerSettings, get_settings
from smartmatch_worker.execution import TaskExecutor
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


def create_app(
    *,
    settings: WorkerSettings | None = None,
    session_factory: sessionmaker[Session] | None = None,
    task_verifier: TaskIdentityVerifier | None = None,
    registry: CommandRegistry | None = None,
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
        registry: Command handlers. The shipped registry when omitted.

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
    app.state.registry = registry
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

        executor = TaskExecutor(request.app.state.session_factory, request.app.state.registry)
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

    return app


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
