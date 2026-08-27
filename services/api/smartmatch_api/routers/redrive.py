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

  **A key names accepted work. A refused command consumes quota and no key.**
  That now holds for every refusal this route can produce, which it did not
  before ADR-0015: the limiter ran *after* the job load, the authorization and
  the header and body validators, so a ``403``, ``404`` or ``400`` cost the
  caller nothing — measured at 25 consecutive refusals of each kind moving the
  counter by zero (backlog **J16**). Those are the refusals cheapest to produce
  in bulk, which made the free ones exactly the traffic a limiter exists to
  bound. The charge is now the first statement of each handler and commits in
  its own transaction, and what that decides — an authenticated caller pays for
  requests they were never allowed to make, and for ids that do not exist — is
  ADR-0015's, recorded there rather than settled in a comment.
  So a retry after a ``409`` re-runs the attempt and is refused again — it does
  not replay the refusal, and it does not replay a success that never happened.
  That is not a nicety: the states this route refuses are not permanent. A
  ``running`` job later fails and becomes re-drivable, and the same key must
  then produce a real re-drive rather than a stale answer in either direction.
  Holding the reservation past a refusal made every retry of a refused command
  answer ``202 accepted`` — or ``200 abandoned`` — for work that was never
  authorized and never ran, permanently, because nothing expires a reservation.

  This is why both handlers wrap everything the command writes in a
  ``SAVEPOINT``, opened after the quota has been charged and committed. A
  refusal rolls the savepoint back — reservation, parking, state change, audit
  record, outbox row, all of it — and commits the outer transaction, so the
  command leaves nothing and the quota, already durable, stays. A targeted
  delete of the reservation would read as simpler and would be wrong: the
  parking step can insert a ``redrive_record`` before a compare-and-set loses,
  and a delete aimed at the reservation would commit that stray record.
  The savepoint expresses the actual rule — *the command did not happen; only
  the quota did* — instead of enumerating the rows that must be removed, so it
  keeps holding when someone adds a write inside the block.
* **Two people pressing the button.** Two coordinators looking at the same
  failed job generate two *different* keys, so idempotency cannot see them as
  related. Guarded instead by the job's own state: the
  ``redrive_pending -> queued`` move is a compare-and-set, so exactly one of
  them can win and the other is refused.
* **A job that should never be re-driven at all.** A succeeded job, a cancelled
  one, one still running. Guarded by the domain state machine — re-driving
  something that already succeeded would re-run effects nobody asked to repeat.

## What a 500 costs, and what is still free

The savepoint also carries a broad ``except`` that rolls it back, commits the
outer transaction, and re-raises — so an *unexpected* error costs quota too. The
caller still gets their 500; the capacity they spent provoking it still counts
against them. Before that (backlog **J15**) any exception outside the three
refusal types left the savepoint open and skipped the commit, and
``get_session``'s unconditional ``finally: session.rollback()`` discarded the
rate-limit increment along with the half-written command — measured at quota
``0`` before and ``0`` after. A caller who could reliably provoke a 500 paid
nothing for it, on the most tightly rate-limited route in the API.

**Those blocks are no longer what keeps the quota, and they are kept anyway.**
ADR-0015 moved the charge to the front of the handler and gave it its own
transaction, so by the time a savepoint is opened the increment is already
committed and no later failure — handled, unhandled, or a process dying — can
take it back. What the ``except`` blocks still do is state the other half: the
command did not happen. Removing them would make the quota's survival depend on
reading ``charge_quota`` rather than on reading this file, and would leave the
outer transaction to the dependency teardown on paths that deliberately commit.
The J15 hole in :mod:`smartmatch_api.commands`, which no savepoint covered,
closes by the same move rather than by copying these blocks into it.

**What is still free, named rather than implied.** A request rejected by
FastAPI's own validation — a body that is not an object, a ``job_id`` that is
not a UUID — never enters these handlers, so nothing charges it and the ``422``
costs the caller nothing. Charging it would mean making the quota a route
*dependency* rather than a statement, which is a different shape with its own
ordering questions, and it is left open deliberately: a ``422`` is answered
before the request touches the database at all, which is the one refusal here
that is genuinely cheap to *serve* as well as cheap to produce.

## The authorization

Authorization runs **after** the job is loaded, and the load is tenant-scoped in
the query, so a job in another tenant is a 404 rather than a 403 — a denial that
distinguished them would be an existence oracle for other tenants' work.

Both routes call :func:`smartmatch_api.job_authz.authorize_job_command`, which is
the same module the status and event routes go to. This file used to carry its
own ``_authorize_redrive``, restating the policy's four rules in Python because
``job`` had no owning org unit for an inherited grant to match against and
supplying a made-up path would have been fabricating authorization data. That
column exists as of migration ``0006``, so the restatement is gone and the policy
is called. The consequence the old docstring reported plainly — *a coordinator in
one department may re-drive another department's job* — is closed: authorization
is now scoped to the unit the job was submitted into.

What has not changed, and is the reason these two routes take the *command*
entry point rather than the read one: **there is no actor exception here.**
Having submitted a job is not authority to re-run it or to close it permanently.
Re-drive and abandon are oversight, not ownership, and the person who pressed the
button the first time is precisely the person most likely to press it again.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Header, Path, status
from pydantic import BaseModel, Field
from smartmatch_domain.jobs import InvalidTransitionError, JobState
from smartmatch_persistence.idempotency import (
    IdempotencyConflictError,
    IdempotencyRepository,
    IdempotencyResult,
    fingerprint_request,
)
from smartmatch_persistence.jobs import JobRecord, JobRepository
from smartmatch_persistence.principals import ResolvedPrincipal
from smartmatch_persistence.rate_limit import RateLimit
from smartmatch_persistence.redrive import RedriveConflictError, RedriveRepository
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal, DbSession, charge_quota
from smartmatch_api.errors import ApiError
from smartmatch_api.job_authz import authorize_job_command
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/jobs", tags=["redrive"])

logger = logging.getLogger(__name__)

_jobs = JobRepository()
_redrive = RedriveRepository()
_idempotency = IdempotencyRepository()

#: v1.1 §3.4 pilot defaults are hypotheses to tune with recorded evidence. Tight
#: here on purpose: re-drive is a deliberate human decision, so a caller issuing
#: more than a handful a minute is looping, not deciding.
#: Both routes share this one bucket, including ``/abandon``: they are the same
#: privileged decision at the same tightness. Worth knowing before debugging a
#: 429 on ``/abandon`` by looking for a ``job.abandon`` counter that never
#: existed.
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
) -> IdempotencyResult:
    """Reserve the key for this decision, and report what it already holds.

    Returns the whole :class:`IdempotencyResult` rather than just
    ``is_replay``. The replay branch needs ``result_generation`` off the same
    row, and fetching it in a second query would be a second chance for the
    answer to change.

    Bound to the *existing* job rather than to a new one — the whole point of
    re-drive is that the job keeps its identity, so a replay returns the same job
    id the first call did.

    A key reused with a *different* reason is a conflict, not a replay: answering
    with the earlier decision would silently discard the new one.

    **Writes nothing that outlives a refusal.** This used to commit the
    transaction itself before letting :class:`IdempotencyConflictError`
    propagate, so that the rate-limit consumption stuck. That commit is gone: the
    callers now run this inside a ``SAVEPOINT`` with the quota taken outside it,
    which keeps the quota and discards the reservation without this function
    needing to know either rule. Committing here would have been worse than
    redundant — ``Session.commit()`` with an open savepoint commits the
    savepoint's work too, so the reservation it was meant to be indifferent about
    would have been made permanent.
    """
    return _idempotency.reserve(
        session,
        tenant_id=principal.tenant_id,
        command_type=command_type,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint_request(payload),
        job_id=job_id,
    )


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

    Everything the *command* writes commits at once — the idempotency
    reservation, the parking, the state change, the audit stamp, and the new
    outbox row. A re-drive recorded without its outbox row would be an audit
    trail describing work that never ran; an outbox row without the audit record
    would be work nobody authorized. The quota is not in that set and commits
    ahead of all of it (ADR-0015): it is what the request cost, not part of what
    the command did.
    """
    # Quota first, and first means first: ahead of the job load, the
    # authorization, and both validators. Charging after them made a 403, 404 or
    # 400 free — 25 consecutive refusals of each kind moved the counter by zero
    # (J16) — which is the same S-008 shape the savepoint closes on the 409
    # paths, reached by the three refusals cheapest to produce in bulk.
    #
    # ``charge_quota`` commits, so the increment is durable before anything
    # below can raise. That is not an optimization of the ordering; without it
    # the reordering alone would fix nothing, because every one of those
    # refusals leaves through ``get_session``'s unconditional
    # ``finally: session.rollback()``.
    #
    # What it decides is in ADR-0015 and is not a detail: an authenticated
    # caller now pays for requests they were never allowed to make, and for job
    # ids that do not exist.
    charge_quota(session, principal, REDRIVE_RATE_LIMIT)

    job = _load_job_or_404(session, principal.tenant_id, job_id)
    authorize_job_command(principal, job, at=utc_now())

    reason = _require_reason(body.reason)
    key = _require_idempotency_key(idempotency_key)

    # Everything the command writes goes inside a SAVEPOINT so a refusal can
    # discard all of it and keep the quota. See the module docstring for why
    # this is a savepoint rather than a targeted delete of the reservation.
    command = session.begin_nested()
    try:
        reservation = _reserve(
            session,
            principal,
            command_type="job.redrive",
            job_id=job_id,
            idempotency_key=key,
            payload={"job_id": str(job_id), "reason": reason},
        )
        if reservation.is_replay:
            # The decision was already recorded and the work already re-queued.
            # A replay is an *accepted* command, so it commits normally: its
            # reservation must stay, and the retry still costs quota.
            #
            # "Identically" has to include the generation, and the generation
            # has to be *this key's* — which is why it is read off the
            # reservation rather than recomputed.
            #
            # ``current_generation`` returns the job's **latest** dispatch, not
            # the one this key created, and that is J14: K1 re-drives
            # (generation 1); the job fails again; K2 re-drives (generation 2);
            # a retry of K1 then answered ``{"replayed": true, "generation":
            # 2}`` — wrong in the one field that exists to disambiguate
            # dispatches, and wrong silently.
            replayed_generation = reservation.result_generation
            if replayed_generation is None:
                # Exactly two causes: the reservation predates migration
                # ``0004``, or an instance running pre-J14 code reserved the key
                # and recorded no result.
                #
                # A third looks plausible and is not reachable — "the command
                # reserved the key and never completed". The reservation is
                # written inside this savepoint, so a command that fails takes
                # its reservation down with it and leaves no row at all.
                # Verified by making ``redrive`` raise after ``_reserve``
                # succeeded: no ``idempotency_record`` survives.
                #
                # **This is a permanent condition on those keys, not a window
                # that closes when a deploy finishes.** Nothing repairs a legacy
                # row and nothing expires one — there is no retention job on
                # ``idempotency_record`` — so a replay of such a key keeps
                # answering with the job's latest dispatch for as long as the row
                # exists. Repairing it here is not possible either: the true
                # value is exactly what was never recorded, and
                # ``current_generation`` is the same guess that is already wrong.
                # The warning therefore identifies a legacy key, and a steady
                # trickle of it long after a rollout is expected rather than
                # alarming.
                #
                # The fallback is the old, wrong answer. That is deliberate:
                # refusing would turn a deploy into 500s on the replay path,
                # which is a worse failure than the one being fixed, and this
                # route is the privileged one. The warning is what makes the
                # window visible — if it is still firing after a deploy has
                # settled, something is writing reservations without results.
                logger.warning(
                    "idempotency key %r for job %s has no recorded generation "
                    "(reserved before migration 0004 or by pre-J14 code); "
                    "falling back to the job's latest dispatch, which may not be "
                    "the one this key created (J14). This key will answer this "
                    "way permanently.",
                    key,
                    job_id,
                )
                replayed_generation = _redrive.current_generation(
                    session, principal.tenant_id, job_id
                )
            command.commit()
            session.commit()
            return RedriveAcceptedResponse(
                job_id=job_id,
                generation=replayed_generation,
                events_url=f"/v1/jobs/{job_id}/events",
                replayed=True,
            )

        outcome = _redrive.redrive(
            session,
            tenant_id=principal.tenant_id,
            job_id=job_id,
            actor_id=principal.user_id,
            reason=reason,
            now=utc_now(),
        )
    except (IdempotencyConflictError, RedriveConflictError, InvalidTransitionError) as exc:
        # The command did not happen; only the quota did. ROLLBACK TO SAVEPOINT
        # discards the reservation and anything the attempt wrote — including a
        # ``redrive_record`` backfilled by the parking step before the
        # compare-and-set lost — and releases the row locks taken since the
        # savepoint. The outer commit closes the transaction on a session that
        # has nothing left to persist: since ADR-0015 the increment is committed
        # before this handler loads anything, so it is no longer riding out on
        # this commit.
        command.rollback()
        session.commit()
        if isinstance(exc, RedriveConflictError):
            raise _conflict(exc) from exc
        # Both remaining cases are rendered as 409 by the application-wide
        # handlers, which already name the states or the reused key.
        raise
    except Exception:
        # J15: a 500 must not refund the quota that produced it.
        #
        # Any exception outside the tuple above used to leave this savepoint
        # open and skip every commit below, so ``get_session``'s unconditional
        # ``finally: session.rollback()`` discarded the rate-limit increment
        # together with the half-written command. Measured by making
        # ``_redrive.redrive`` raise ``RuntimeError``: quota 0 before, 0 after.
        # A caller who can provoke a 500 reliably therefore paid nothing for it,
        # on the most tightly rate-limited route in the API — which is precisely
        # the traffic the limiter exists to bound (S-008).
        #
        # The two statements are the refusal path's, in the same order and for
        # the same reason: the command did not happen; only the quota did. They
        # carry more weight here, because the failure may have come from
        # PostgreSQL rather than from Python — an error inside the savepoint
        # aborts the whole transaction, and ROLLBACK TO SAVEPOINT is what leaves
        # the outer one committable.
        #
        # ``is_active`` because the replay branch commits inside this ``try``:
        # if its own ``session.commit()`` is what failed, there is no savepoint
        # left to roll back and nothing a second commit could rescue.
        #
        # The boundary used to be exact and slightly narrower than it looked:
        # the ``record_result`` call and the two commits below sit *after* this
        # block, so a failure in one of them took the quota with it. ADR-0015
        # closes that residue by construction rather than by widening the block
        # — the increment is committed before the handler starts, so there is no
        # longer any point in the request at which a failure can refund it.
        if command.is_active:
            command.rollback()
        session.commit()
        # Re-raised unchanged, deliberately. This fixes what persists, not what
        # the caller is told: the 500 is still a 500, still unhandled, and still
        # a defect to be fixed on its own terms.
        raise

    # Inside the savepoint, so a command that is discarded leaves no result
    # behind claiming it happened. This cannot move into ``_reserve``: the
    # generation is ``redrive``'s result and does not exist until it returns.
    _idempotency.record_result(
        session,
        tenant_id=principal.tenant_id,
        command_type="job.redrive",
        idempotency_key=key,
        result_generation=outcome.generation,
    )

    command.commit()
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
    # First statement, committed on the spot, for the reason ``redrive_job``
    # gives at length: every refusal this route can produce costs quota, and
    # both routes spend from the same ``job.redrive`` bucket — so a caller
    # hammering ``/abandon`` with ids that do not exist exhausts the quota they
    # would need to re-drive a real one.
    charge_quota(session, principal, REDRIVE_RATE_LIMIT)

    job = _load_job_or_404(session, principal.tenant_id, job_id)
    authorize_job_command(principal, job, at=utc_now())

    reason = _require_reason(body.reason)
    key = _require_idempotency_key(idempotency_key)

    command = session.begin_nested()
    try:
        if _reserve(
            session,
            principal,
            command_type="job.abandon",
            job_id=job_id,
            idempotency_key=key,
            payload={"job_id": str(job_id), "reason": reason},
        ).is_replay:
            # An accepted command being retried. Commits normally.
            #
            # No ``record_result`` on this path, and no generation read from
            # the reservation: an abandon has no generation to report —
            # ``AbandonedResponse`` carries only the job id and the status — so
            # its ``result_generation`` stays ``NULL`` permanently and correctly.
            command.commit()
            session.commit()
            return AbandonedResponse(job_id=job_id)

        _redrive.abandon(
            session,
            tenant_id=principal.tenant_id,
            job_id=job_id,
            actor_id=principal.user_id,
            reason=reason,
            now=utc_now(),
        )
    except (IdempotencyConflictError, RedriveConflictError, InvalidTransitionError) as exc:
        # Identical to ``redrive_job``: discard everything the command wrote,
        # keep the quota. Deliberately not factored into a shared helper — the
        # two differ in response type and in the replay branch, and the shape is
        # short enough that a reader can check each one against the other.
        command.rollback()
        session.commit()
        if isinstance(exc, RedriveConflictError):
            raise _conflict(exc) from exc
        raise
    except Exception:
        # J15, identical in shape to ``redrive_job`` and identical in reasoning:
        # an unexpected error is a 500, and a 500 keeps the quota it spent
        # rather than refunding it. Measured the same way, by making
        # ``_redrive.abandon`` raise ``RuntimeError``: quota 0 before, 0 after.
        # Not factored into a shared helper, for the reason the refusal path
        # above gives — these two handlers are meant to be read against each
        # other.
        if command.is_active:
            command.rollback()
        session.commit()
        raise

    command.commit()
    session.commit()
    return AbandonedResponse(job_id=job_id)
