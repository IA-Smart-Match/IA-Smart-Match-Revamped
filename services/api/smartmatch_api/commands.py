"""The shared command-submission path.

Architecture v1.1 §1.11 replaces the v1.0 generic ``POST /jobs`` with explicit
command resources — ``/discovery-jobs``, ``/imports``, ``/match-runs``, send
commands — each with its own authorization, quota, and payload contract. What
they share is *how* a command is accepted, and that is here rather than copied
into each router.

## The one transaction

Everything a submission writes commits together (v1.1 §1.6):

    idempotency reservation · rate-limit consumption · job row (**with its
    payload**) · outbox row

If any part fails, none of it happened. That matters in both directions: a
rolled-back command must not consume quota or burn an idempotency key, and a
committed job must never exist without the outbox row that will dispatch it.

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
from smartmatch_persistence.rate_limit import RateLimit
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import enforce_rate_limit
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
    rate_limit: RateLimit,
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
        rate_limit: The limit for this operation.

    Returns:
        A :class:`CommandAccepted`. Callers respond ``202`` with the job id.

    Raises:
        ApiError: 400 when the idempotency key is missing or unusable,
            429 when the rate limit is exhausted.
        IdempotencyConflictError: 409 when the key was reused with a different
            body.
    """
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

    # Quota first, so an exhausted caller cannot burn idempotency keys or job
    # ids by hammering. Consumed inside the transaction, so a request that later
    # fails does not count against them.
    enforce_rate_limit(session, principal, rate_limit)

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
        # Commit the quota consumption before the 409 propagates. Without this,
        # the request-scoped session is rolled back on the way out and the
        # increment goes with it — making an unbounded stream of conflicting
        # requests free, which is precisely the traffic a limiter exists to
        # bound. A rejected request still costs the caller quota.
        session.commit()
        raise

    if reservation.is_replay:
        # The work already exists. Commit so the rate-limit consumption sticks —
        # a retry still costs quota, or a client could poll a command endpoint
        # for free — then return the original job.
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

    # One commit for the reservation, the quota, the job with its payload, and
    # the outbox row.
    session.commit()

    return CommandAccepted(job_id=job_id, is_replay=False)
