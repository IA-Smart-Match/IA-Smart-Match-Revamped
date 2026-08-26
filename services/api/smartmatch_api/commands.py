"""The shared command-submission path.

Architecture v1.1 §1.11 replaces the v1.0 generic ``POST /jobs`` with explicit
command resources — ``/discovery-jobs``, ``/imports``, ``/match-runs``, send
commands — each with its own authorization, quota, and payload contract. What
they share is *how* a command is accepted, and that is here rather than copied
into each router.

## The one transaction

Everything a submission writes commits together (v1.1 §1.6):

    idempotency reservation · job row (**with its payload**) · outbox row

If any part fails, none of it happened: a rolled-back command must not burn an
idempotency key, and a committed job must never exist without the outbox row
that will dispatch it.

**Quota is deliberately not in that list, as of ADR-0015.** It used to be — the
increment shared this transaction, so a submission that was refused or that
failed gave the caller their capacity back. The charge now happens in the router,
before the resource is loaded and before it is authorized, and commits in a
transaction of its own; :func:`submit_command` takes the resulting
:class:`~smartmatch_api.dependencies.QuotaCharge` as evidence rather than
charging for itself. The two are separate on purpose and in one direction only:
a command that does not happen still costs the caller, and quota already spent
is never handed back by a later failure.

The payload is part of that list as of J10, and it is inside the boundary by
construction rather than by care: ``JobRepository.create`` writes it as a column
of the job's own INSERT, so there is no separate statement anyone could later
move out of the transaction. Until then the body was hashed into an idempotency
fingerprint and dropped, and the worker — handed a job id, a tenant and a command
type — failed every import it was given because nothing recorded what to import.
An accepted command that cannot be executed is not an accepted command.

Note what is deliberately **absent**: no provider call, no Cloud Tasks call, no
work. The request path only records intent. The dispatcher moves it, and the
worker performs it — so a browser request can never trigger a paid or
consequential action directly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import status
from smartmatch_persistence.idempotency import (
    IdempotencyConflictError,
    IdempotencyRepository,
    fingerprint_request,
)
from smartmatch_persistence.jobs import JobRepository
from smartmatch_persistence.outbox import OutboxRepository
from smartmatch_persistence.principals import ResolvedPrincipal
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import QuotaCharge
from smartmatch_api.errors import ApiError

__all__ = ["CommandAccepted", "submit_command"]

_jobs = JobRepository()
_outbox = OutboxRepository()
_idempotency = IdempotencyRepository()


@dataclass(frozen=True, slots=True)
class CommandAccepted:
    """The result of accepting a command.

    Attributes:
        job_id: The job now recorded. Follow it via ``/v1/jobs/{id}`` and
            ``/v1/jobs/{id}/events``.
        is_replay: ``True`` when this exact request had already been accepted
            under the same idempotency key. The response is identical either
            way — that is the point of idempotency — but the flag lets a caller
            distinguish a retry from a fresh submission in its own logs.
    """

    job_id: uuid.UUID
    is_replay: bool


def submit_command(
    session: Session,
    principal: ResolvedPrincipal,
    *,
    command_type: str,
    payload: dict[str, Any],
    idempotency_key: str | None,
    charge: QuotaCharge,
) -> CommandAccepted:
    """Accept a command: validate, reserve, record, and commit.

    Args:
        session: The request session. Committed here on success.
        principal: The authenticated caller. Tenant and actor come from this,
            never from ``payload``.
        command_type: Stable command identifier, e.g. ``"match-run.create"``.
        payload: The command's parameters, as the router assembled them from the
            validated request body plus the identifiers it resolved. Persisted on
            the job row for the worker to execute, and hashed for the idempotency
            fingerprint. It must contain everything the handler needs and nothing
            the caller may not dictate: tenant and actor come from ``principal``
            and are never read out of here.
        idempotency_key: The caller's ``Idempotency-Key`` header. Required —
            see below.
        charge: The receipt from
            :func:`~smartmatch_api.dependencies.charge_quota`, which the router
            called as its first statement. Required rather than a
            ``RateLimit`` this function would apply itself: charging here would
            put the quota back behind the router's load, authorization and
            validation, which is the ordering ADR-0015 exists to reverse. Asking
            for the receipt instead means a route cannot submit a command it
            never charged for, and a type checker says so.

    Returns:
        A :class:`CommandAccepted`. Callers respond ``202`` with the job id.

    Raises:
        ApiError: 400 when the idempotency key is missing or unusable.
        IdempotencyConflictError: 409 when the key was reused with a different
            body.
    """
    # ``charge`` is deliberately never read. It is a precondition made
    # structural: the guarantee is that the caller already spent quota on this
    # request, and a value this function could only re-check would not add one.
    if not idempotency_key or not idempotency_key.strip():
        # Required rather than optional. A command that creates durable,
        # possibly paid work must be safely retryable, and a caller cannot retry
        # safely without a key. Generating one server-side would defeat the
        # purpose: every retry would look like a new request.
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="idempotency_key_required",
            message=(
                "An Idempotency-Key header is required for command submission so "
                "that retries cannot duplicate work."
            ),
        )

    if len(idempotency_key) > 255:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="idempotency_key_too_long",
            message="Idempotency-Key must be at most 255 characters.",
        )

    job_id = uuid.uuid4()
    try:
        reservation = _idempotency.reserve(
            session,
            tenant_id=principal.tenant_id,
            command_type=command_type,
            idempotency_key=idempotency_key.strip(),
            # Unchanged by J10, deliberately. The fingerprint covers exactly the
            # dictionary that is about to be persisted as `job.payload`, so the
            # rule it enforces — same key, same body, same job — is now a
            # statement about the work that will actually run rather than about
            # a body nothing kept. Persisting the payload narrows nothing and
            # widens nothing; it makes the existing check meaningful.
            #
            # Two things it still does not cover, both pre-existing and both
            # left alone here. The actor: a key is scoped to
            # (tenant, command_type, key), so a second caller in the same tenant
            # replaying an identical body gets the first caller's job. And the
            # persisted form: this hashes the request dictionary in-process,
            # never the stored jsonb, because jsonb normalizes key order and
            # duplicate keys — a fingerprint recomputed from the column could
            # differ from the one taken from the body and turn a legitimate
            # retry into a 409.
            request_fingerprint=fingerprint_request(payload),
            job_id=job_id,
        )
    except IdempotencyConflictError:
        # No commit here any more, and its absence is the point. This used to
        # commit before letting the 409 propagate, purely so the rate-limit
        # increment survived the request-scoped rollback — the one place
        # ADR-0006 records as inverting its own "the caller commits, alongside
        # the request's own work" rule. ADR-0015 makes that inversion the
        # general rule and moves it to the front of the request, so the quota
        # is already durable by the time this key was even looked at. A
        # conflicting ``reserve`` is ``ON CONFLICT DO NOTHING`` followed by a
        # read, so there is nothing else on this path to keep.
        raise

    if reservation.is_replay:
        # The work already exists, and a replay writes no rows, so this commit
        # has nothing of its own to persist — the retry's quota was charged and
        # committed before this function was called. It stays as the explicit
        # end of the transaction this path opened, matching the success path
        # below rather than leaving the session for the dependency teardown to
        # roll back.
        session.commit()
        assert reservation.job_id is not None
        return CommandAccepted(job_id=reservation.job_id, is_replay=True)

    _jobs.create(
        session,
        tenant_id=principal.tenant_id,
        command_type=command_type,
        actor_id=principal.user_id,
        job_id=job_id,
        # Inside the boundary because it is a column of this INSERT, not a
        # follow-up write that happens to sit before the commit.
        payload=payload,
    )
    _outbox.enqueue(
        session,
        tenant_id=principal.tenant_id,
        job_id=job_id,
        command_type=command_type,
    )

    # One commit for the reservation, the job with its payload, and the outbox
    # row. Not for the quota: that is already committed, in front of this whole
    # function, and is not part of what a failure here should undo (ADR-0015).
    session.commit()

    return CommandAccepted(job_id=job_id, is_replay=False)
