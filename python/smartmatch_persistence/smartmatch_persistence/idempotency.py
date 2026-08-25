"""Idempotency-key repository.

Architecture v1.1 §1.11 requires a defined idempotency-key scope. Here it is
``(tenant_id, command_type, idempotency_key)``: the same key under a different
command type is a different operation, not a replay, and keys are never shared
across tenants.

The rule that makes this safe is the **request fingerprint**. A replayed key with
the *same* request body returns the original job — that is a retry, and returning
the original result is exactly right. A replayed key with a *different* body is a
client bug, and returning the original job would silently discard the new
request. That case raises instead.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = [
    "IdempotencyConflictError",
    "IdempotencyRepository",
    "IdempotencyResult",
    "fingerprint_request",
]


class IdempotencyConflictError(ValueError):
    """Raised when a key is reused with a different request body.

    Maps to HTTP 409. Never 200 with the original job: the caller asked for
    something new, and silently answering a different question is worse than
    failing.
    """


@dataclass(frozen=True, slots=True)
class IdempotencyResult:
    """The outcome of reserving an idempotency key.

    Attributes:
        is_replay: ``True`` when this key was already used with an identical
            request. The caller should return the existing job rather than
            starting new work.
        job_id: The job this key is bound to, when known.
        result_generation: What :meth:`IdempotencyRepository.record_result`
            stored for this key, and ``None`` when nothing did. Only meaningful
            on a replay — on a fresh reservation the command has not run yet, so
            there is no result to carry.

            ``None`` on a replay is several situations at once and the caller
            has to decide what to do about all of them: the row predates
            migration ``0004``; the command type has no generation at all, which
            is true of ``job.abandon``; or the caller reserved the key,
            committed, and never recorded a result.

            That last one is caller-dependent rather than universal. A caller
            that reserves inside a savepoint it rolls back on failure — which is
            what ``redrive.py`` does — cannot produce it, because a failed
            command discards its own reservation and leaves no row. A caller that
            commits the reservation separately can. Nothing here distinguishes
            any of them, because nothing here can.
    """

    is_replay: bool
    job_id: uuid.UUID | None
    result_generation: int | None = None


def fingerprint_request(payload: dict[str, Any]) -> str:
    """Hash a request body for replay comparison.

    Keys are sorted so that two logically identical bodies with different key
    order produce the same fingerprint — otherwise a client that serializes
    unordered dicts would see spurious conflicts on legitimate retries.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class IdempotencyRepository:
    """Reserves and resolves idempotency keys."""

    def reserve(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        command_type: str,
        idempotency_key: str,
        request_fingerprint: str,
        job_id: uuid.UUID,
    ) -> IdempotencyResult:
        """Reserve a key for a new job, or detect a replay.

        Implemented as ``INSERT ... ON CONFLICT DO NOTHING`` followed by a read
        of the conflicting row. Doing it the other way round — read, then insert
        if absent — races: two concurrent requests with the same key would both
        find nothing and both insert, and one would fail on the unique
        constraint anyway. Letting the constraint arbitrate is correct by
        construction.

        Must run in the same transaction as the job and outbox inserts, so a
        reservation is never left behind by a rolled-back command.

        Returns:
            ``is_replay=False`` when the key was fresh and now belongs to
            ``job_id``; ``is_replay=True`` with the original job id otherwise.

        Raises:
            IdempotencyConflictError: if the key exists with a different
                request fingerprint.
        """
        inserted = session.execute(
            sa.dialects.postgresql.insert(schema.idempotency_record)
            .values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                command_type=command_type,
                request_fingerprint=request_fingerprint,
                job_id=job_id,
            )
            .on_conflict_do_nothing(constraint="uq_idempotency_scope")
            .returning(schema.idempotency_record.c.job_id)
        ).one_or_none()

        if inserted is not None:
            return IdempotencyResult(is_replay=False, job_id=job_id)

        existing = session.execute(
            sa.select(
                schema.idempotency_record.c.job_id,
                schema.idempotency_record.c.request_fingerprint,
                schema.idempotency_record.c.result_generation,
            ).where(
                schema.idempotency_record.c.tenant_id == tenant_id,
                schema.idempotency_record.c.command_type == command_type,
                schema.idempotency_record.c.idempotency_key == idempotency_key,
            )
        ).one()

        if existing.request_fingerprint != request_fingerprint:
            raise IdempotencyConflictError(
                f"idempotency key {idempotency_key!r} was already used for "
                f"{command_type!r} with a different request body. Reusing a key for "
                "a different request is a client error; use a new key."
            )

        return IdempotencyResult(
            is_replay=True,
            job_id=existing.job_id,
            result_generation=existing.result_generation,
        )

    def record_result(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        command_type: str,
        idempotency_key: str,
        result_generation: int,
    ) -> None:
        """Record what this key's command produced, so a replay can repeat it.

        **Separate from :meth:`reserve`, and it has to be.** The obvious design
        stores the generation when the key is reserved, and it cannot work: the
        generation *is* the command's result, and the command has not run when
        the key is reserved. Reserving first and recording afterwards is the
        only order the data allows.

        Called after the command succeeds and in the same transaction, so a
        command that is rolled back leaves no result behind claiming it
        happened. The caller's savepoint discipline does the rest: if the
        command is discarded, so is this.

        Idempotent by construction — it writes the same value a replay would
        compute — but not expected to run twice, because the path that calls it
        runs once per key by definition.
        """
        session.execute(
            sa.update(schema.idempotency_record)
            .where(
                schema.idempotency_record.c.tenant_id == tenant_id,
                schema.idempotency_record.c.command_type == command_type,
                schema.idempotency_record.c.idempotency_key == idempotency_key,
            )
            .values(result_generation=result_generation)
        )
