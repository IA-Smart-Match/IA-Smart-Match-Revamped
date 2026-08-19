"""Re-drive and abandon: the authorized commands over parked work.

Architecture v1.1 §1.6. Cloud Tasks has no dead-letter queue, so terminally
failed work parks in PostgreSQL and restarting it is a command, not a retry —
one that names an actor, records a reason, and cannot be issued by everybody who
happens to be in the tenant.

Both routes here are ``POST`` and both mutate. A re-drive re-runs work that
already failed *and may already have had effects*: an import that wrote review
items, a send that reached a mailbox. That is why the authorization is
role-gated rather than actor-based, why the reason is mandatory rather than
optional, and why the whole thing is idempotent.

## What guards what

Three different failures are possible, and they need three different guards —
using one for all of them leaves the other two open:

* **A retried request.** The caller's own network hiccup, or a client library
  retrying a ``POST``. Guarded by ``Idempotency-Key``, exactly as
  :mod:`smartmatch_api.commands` guards command submission: the same key with
  the same body replays and returns the original job.
* **Two people pressing the button.** Two coordinators looking at the same
  failed job generate two *different* keys, so idempotency cannot see them as
  related. Guarded instead by the job's own state: the
  ``redrive_pending -> queued`` move is a compare-and-set, so exactly one of
  them can win and the other is refused.
* **A job that should never be re-driven at all.** A succeeded job, a cancelled
  one, one still running. Guarded by the domain state machine — re-driving
  something that already succeeded would re-run effects nobody asked to repeat.

## The authorization, and the one thing it cannot do

Authorization runs **after** the job is loaded, and the load is tenant-scoped in
the query, so a job in another tenant is a 404 rather than a 403 — a denial that
distinguished them would be an existence oracle for other tenants' work.

It does not call :func:`smartmatch_authz.assert_allowed`, and that is a
deliberate limitation rather than a shortcut. ``assert_allowed`` matches an
inherited grant against the resource's ``owning_unit_path``, and the ``job``
table has no owning org unit — the same gap
:mod:`smartmatch_api.routers.jobs` documents for job reads. Supplying a made-up
path to satisfy the signature would be fabricating authorization data rather
than enforcing it. So :func:`_authorize_redrive` applies the policy's rules in
the policy's own order, over the policy's own types, and raises the policy's own
:class:`~smartmatch_authz.AuthorizationError` — so denials carry the same stable
reason codes and render through the same handler as everywhere else. The
consequence, stated plainly: a coordinator in one department may re-drive
another department's job. Closing that needs a ``job.owning_unit_id`` column and
an expand-phase migration, and is reported rather than papered over.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Annotated, Any, Final

from fastapi import APIRouter, Header, Path, status
from pydantic import BaseModel, Field
from smartmatch_authz import AccessDecision, AuthorizationError, Effect
from smartmatch_domain.jobs import InvalidTransitionError, JobState
from smartmatch_persistence.idempotency import (
    IdempotencyConflictError,
    IdempotencyRepository,
    fingerprint_request,
)
from smartmatch_persistence.jobs import JobRecord, JobRepository
from smartmatch_persistence.principals import ResolvedPrincipal
from smartmatch_persistence.rate_limit import RateLimit
from smartmatch_persistence.redrive import RedriveConflictError, RedriveRepository
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal, DbSession, enforce_rate_limit
from smartmatch_api.errors import ApiError
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/jobs", tags=["redrive"])

_jobs = JobRepository()
_redrive = RedriveRepository()
_idempotency = IdempotencyRepository()

#: The resource type explicit grants use for a job, matching what an
#: administrator writes into ``resource_grant.resource_type``.
_JOB_RESOURCE: Final[str] = "job"

#: Roles that may re-drive or abandon parked work. An explicit set, not "any
#: active membership": re-running failed work can repeat side effects that
#: already reached people outside the system, and closing it permanently removes
#: it from everyone else's view.
_REDRIVE_ROLES: Final[frozenset[str]] = frozenset({"admin", "coordinator"})

#: v1.1 §3.4 pilot defaults are hypotheses to tune with recorded evidence. Tight
#: here on purpose: re-drive is a deliberate human decision, so a caller issuing
#: more than a handful a minute is looping, not deciding.
REDRIVE_RATE_LIMIT = RateLimit(
    operation="job.redrive",
    max_requests=10,
    window=timedelta(minutes=1),
)


class RedriveRequest(BaseModel):
    """A re-drive decision.

    ``reason`` is required and has no default. An optional reason becomes an
    absent reason, and a parked-work table full of blank reasons answers none of
    the questions it exists to answer — who decided this was worth re-running,
    and on what basis.
    """

    reason: str = Field(
        min_length=1,
        max_length=1000,
        description="Why this work is being re-run. Recorded in the audit trail.",
    )


class RedriveAcceptedResponse(BaseModel):
    """Acknowledgement that a re-drive was recorded and will be dispatched."""

    job_id: uuid.UUID
    status: str = Field(default="accepted")
    #: Which dispatch of this job the re-drive created. ``1`` is the first
    #: re-drive; ``0`` was the original submission.
    generation: int = Field(default=0, description="Dispatch generation this re-drive created")
    #: Where to follow the work.
    events_url: str
    #: True when an identical request under the same key was already accepted.
    replayed: bool = False


class AbandonedResponse(BaseModel):
    """Acknowledgement that a parked job was closed permanently."""

    job_id: uuid.UUID
    status: str = Field(default=JobState.ABANDONED.value)


def _load_job_or_404(session: Session, tenant_id: uuid.UUID, job_id: uuid.UUID) -> JobRecord:
    """Fetch a job within the caller's tenant, or raise 404.

    Tenant scoping is part of the lookup, not a filter applied to the result. A
    job belonging to another tenant is indistinguishable from one that does not
    exist, which is what stops this route becoming an existence oracle.
    """
    job = _jobs.get(session, tenant_id=tenant_id, job_id=job_id)
    if job is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="job_not_found",
            message="No such job.",
        )
    return job


def _authorize_redrive(principal: ResolvedPrincipal, job_id: uuid.UUID, *, at: datetime) -> None:
    """Authorize a re-drive or an abandonment, in the policy's own order.

    The four rules are :mod:`smartmatch_authz.policy`'s, applied to a resource
    that has no org path for the inherited-grant path to match (see the module
    docstring):

    1. **Suspension is checked first and unconditionally.** An administrator who
       suspends an account must not have to wait for the identity provider to
       revoke a token before the account stops being able to re-run work.
    2. **Tenant mismatch is structural.** Already impossible here, because the
       job was loaded scoped to the caller's tenant — asserted anyway, since the
       cost is a comparison and the failure mode is cross-tenant execution.
    3. **An explicit deny on the job beats the role.** This is how an
       administrator carves one job out of a broad grant, and it must win.
    4. **A role is required, and a bare resource grant cannot supply it.** A
       grant conveys access to a resource, not authority to re-run it; the
       policy makes the same call for the same reason, with the same distinct
       reason code so the open policy-matrix gap stays visible in the audit
       trail instead of being silently allowed or silently denied.

    Raises:
        AuthorizationError: on any denial. Rendered as 403 with the decision's
            stable reason code by the application's existing handler.
    """
    actor = principal.principal

    if actor.suspended:
        raise AuthorizationError(AccessDecision(allowed=False, reason="principal_suspended"))

    if actor.tenant_id != str(principal.tenant_id):
        raise AuthorizationError(AccessDecision(allowed=False, reason="tenant_mismatch"))

    grants = [
        grant
        for grant in actor.resource_grants
        if grant.resource_type == _JOB_RESOURCE and grant.resource_id == str(job_id)
    ]
    if any(grant.effect is Effect.DENY for grant in grants):
        raise AuthorizationError(AccessDecision(allowed=False, reason="explicit_resource_deny"))

    holds_role = any(
        membership.is_active_at(at) and membership.role in _REDRIVE_ROLES
        for membership in actor.memberships
    )
    if holds_role:
        return

    if any(grant.effect is Effect.ALLOW for grant in grants):
        raise AuthorizationError(
            AccessDecision(allowed=False, reason="resource_grant_lacks_required_role")
        )

    raise AuthorizationError(AccessDecision(allowed=False, reason="no_grant"))


def _require_idempotency_key(idempotency_key: str | None) -> str:
    """Return a usable key, or refuse the command.

    Required rather than optional, for the same reason
    :func:`smartmatch_api.commands.submit_command` requires one: a command that
    re-runs durable, possibly paid work must be safely retryable, and a caller
    cannot retry safely without a key. Generating one server-side would defeat
    the purpose — every retry would look like a fresh decision to re-run.
    """
    if not idempotency_key or not idempotency_key.strip():
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="idempotency_key_required",
            message=(
                "An Idempotency-Key header is required so that a retried re-drive "
                "cannot start the work twice."
            ),
        )
    if len(idempotency_key) > 255:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="idempotency_key_too_long",
            message="Idempotency-Key must be at most 255 characters.",
        )
    return idempotency_key.strip()


def _require_reason(reason: str) -> str:
    """Return the trimmed reason, or refuse.

    ``min_length`` on the model rejects ``""`` but not ``"   "``, and a
    whitespace reason is an absent reason wearing a disguise.
    """
    trimmed = reason.strip()
    if not trimmed:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="redrive_reason_required",
            message="A re-drive must record why the work is being re-run.",
        )
    return trimmed


def _reserve(
    session: Session,
    principal: ResolvedPrincipal,
    *,
    command_type: str,
    job_id: uuid.UUID,
    idempotency_key: str,
    payload: dict[str, Any],
) -> bool:
    """Reserve the key for this decision. Returns whether this is a replay.

    Bound to the *existing* job rather than to a new one — the whole point of
    re-drive is that the job keeps its identity, so a replay returns the same job
    id the first call did.

    A key reused with a *different* reason is a conflict, not a replay: answering
    with the earlier decision would silently discard the new one. The transaction
    is committed before that 409 propagates so the rate-limit consumption sticks
    — without it, an unbounded stream of conflicting requests would be free,
    which is precisely the traffic a limiter exists to bound. Only this one
    exception is caught: committing on an arbitrary failure would persist half a
    command.
    """
    try:
        reservation = _idempotency.reserve(
            session,
            tenant_id=principal.tenant_id,
            command_type=command_type,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint_request(payload),
            job_id=job_id,
        )
    except IdempotencyConflictError:
        session.commit()
        raise
    return reservation.is_replay


def _conflict(exc: RedriveConflictError) -> ApiError:
    """Render a lost race as 409.

    Distinct from ``invalid_state_transition``: the request was legal when it was
    checked and another actor got there first, so retrying may well succeed.
    """
    return ApiError(
        status_code=status.HTTP_409_CONFLICT,
        code="redrive_conflict",
        message=str(exc),
    )


@router.post(
    "/{job_id}/redrive",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RedriveAcceptedResponse,
    summary="Re-drive a parked job",
)
def redrive_job(
    principal: CurrentPrincipal,
    session: DbSession,
    body: RedriveRequest,
    job_id: Annotated[uuid.UUID, Path()],
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", description="Required. Makes retries safe."),
    ] = None,
) -> RedriveAcceptedResponse:
    """Re-queue work that failed terminally, under audit.

    Returns ``202``, not ``200``: nothing has re-run when this returns. The job
    is queued again and a fresh outbox row exists; the dispatcher moves it and
    the worker performs it. Reporting ``200`` would be claiming success for work
    that has not started (v1.1 §3.6 N2) — the same mistake the ``partial`` state
    exists to correct.

    A job still sitting in ``failed_provider`` or ``timed_out`` is parked as part
    of this call rather than requiring a separate step. Both moves are declared
    transitions; a job in any other state is refused with ``409``.

    Everything commits at once — the idempotency reservation, the quota, the
    parking, the state change, the audit stamp, and the new outbox row. A
    re-drive recorded without its outbox row would be an audit trail describing
    work that never ran; an outbox row without the audit record would be work
    nobody authorized.
    """
    job = _load_job_or_404(session, principal.tenant_id, job_id)
    _authorize_redrive(principal, job.id, at=utc_now())

    reason = _require_reason(body.reason)
    key = _require_idempotency_key(idempotency_key)

    # Quota first, so an exhausted caller cannot burn idempotency keys by
    # hammering. Consumed inside the transaction, so a request that later fails
    # does not count against them.
    enforce_rate_limit(session, principal, REDRIVE_RATE_LIMIT)

    if _reserve(
        session,
        principal,
        command_type="job.redrive",
        job_id=job_id,
        idempotency_key=key,
        payload={"job_id": str(job_id), "reason": reason},
    ):
        # The decision was already recorded and the work already re-queued.
        # Commit so the retry still costs quota, then answer identically.
        #
        # "Identically" has to include the generation. Omitting it fell back to
        # the field default of ``0``, which the schema documents as the original
        # submission — so a replayed re-drive reported itself as the thing it
        # demonstrably was not, and a client reconciling generations against the
        # event stream would read it as a different dispatch.
        replayed_generation = _redrive.current_generation(session, principal.tenant_id, job_id)
        session.commit()
        return RedriveAcceptedResponse(
            job_id=job_id,
            generation=replayed_generation,
            events_url=f"/v1/jobs/{job_id}/events",
            replayed=True,
        )

    try:
        outcome = _redrive.redrive(
            session,
            tenant_id=principal.tenant_id,
            job_id=job_id,
            actor_id=principal.user_id,
            reason=reason,
            now=utc_now(),
        )
    except (RedriveConflictError, InvalidTransitionError) as exc:
        # Commit before the 409 propagates. The rate-limit increment is still
        # uncommitted at this point, and the request-scoped session rolls it
        # back — so a caller hammering a job that cannot be re-driven would pay
        # no quota at all. This is the same hole ``_reserve`` deliberately
        # commits to close for idempotency conflicts (security finding S-008);
        # a rejected command still consumed the capacity used to reject it.
        session.commit()
        if isinstance(exc, InvalidTransitionError):
            # Rendered by the application-wide handler, which already maps an
            # illegal transition to 409 with the states named.
            raise
        raise _conflict(exc) from exc

    session.commit()

    return RedriveAcceptedResponse(
        job_id=job_id,
        generation=outcome.generation,
        events_url=f"/v1/jobs/{job_id}/events",
        replayed=False,
    )


@router.post(
    "/{job_id}/abandon",
    status_code=status.HTTP_200_OK,
    response_model=AbandonedResponse,
    summary="Abandon a parked job",
)
def abandon_job(
    principal: CurrentPrincipal,
    session: DbSession,
    body: RedriveRequest,
    job_id: Annotated[uuid.UUID, Path()],
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", description="Required. Makes retries safe."),
    ] = None,
) -> AbandonedResponse:
    """Close a parked job permanently: this will never work, stop showing it.

    ``200``, not ``202``: unlike a re-drive this starts nothing. The state change
    is complete when the response is written, and there is no job to follow.

    Exists because ``redrive_pending -> abandoned`` is declared, and because a
    parked-work view whose items cannot be dismissed is a view people stop
    reading — which costs attention on the items that *are* actionable.

    The reason is required here too. "Why did nobody re-run this?" is a question
    asked months later, usually by someone who was not in the room.
    """
    job = _load_job_or_404(session, principal.tenant_id, job_id)
    _authorize_redrive(principal, job.id, at=utc_now())

    reason = _require_reason(body.reason)
    key = _require_idempotency_key(idempotency_key)

    enforce_rate_limit(session, principal, REDRIVE_RATE_LIMIT)

    if _reserve(
        session,
        principal,
        command_type="job.abandon",
        job_id=job_id,
        idempotency_key=key,
        payload={"job_id": str(job_id), "reason": reason},
    ):
        session.commit()
        return AbandonedResponse(job_id=job_id)

    try:
        _redrive.abandon(
            session,
            tenant_id=principal.tenant_id,
            job_id=job_id,
            actor_id=principal.user_id,
            reason=reason,
            now=utc_now(),
        )
    except (RedriveConflictError, InvalidTransitionError) as exc:
        # Commit before the 409 propagates. The rate-limit increment is still
        # uncommitted at this point, and the request-scoped session rolls it
        # back — so a caller hammering a job that cannot be re-driven would pay
        # no quota at all. This is the same hole ``_reserve`` deliberately
        # commits to close for idempotency conflicts (security finding S-008);
        # a rejected command still consumed the capacity used to reject it.
        session.commit()
        if isinstance(exc, InvalidTransitionError):
            # Rendered by the application-wide handler, which already maps an
            # illegal transition to 409 with the states named.
            raise
        raise _conflict(exc) from exc

    session.commit()
    return AbandonedResponse(job_id=job_id)
