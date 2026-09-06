"""The ``match_run`` write path (migration ``0018``, plan card M8a).

One table, one writer, and one method that writes it. Plan card M8a: "Immutable
``match_run`` snapshot rows ... Executed through the existing durable-command
path (transactional outbox per ADR-0005)." The caller is
``smartmatch_worker.handlers.handle_match_run_create``, which reaches this
module holding the executor-owned session, and there is deliberately no other
one: a route inserting here directly would produce a run with no job behind it,
and ``match_run.job_id``'s foreign key makes that unstorable anyway.

## There is no update method, and that is the API

:meth:`MatchRunRepository.record` inserts. Nothing here updates a run, and
nothing here should: a correction is a new row whose ``supersedes_run_id``
names the one it replaces, so the record of what a coordinator was actually
shown survives the correction. That rule is enforced in three places on
purpose, and none of them is redundant:

* **here**, by the absence of a method — the cheapest kind of enforcement,
  because code that does not exist cannot be called by accident;
* **in the database**, by ``0018``'s ``match_run_is_immutable`` trigger, which
  is what survives a hand-written ``UPDATE`` in a psql session;
* **in the tests**, by ``test_match_run_snapshot.py``, which attempts that
  UPDATE and requires the refusal — because a guarantee nothing exercises is a
  guarantee nobody knows is still there.

## Re-drive must not double-insert

A command handler can execute more than once for the same job: a worker can die
after committing its business write and before the executor's terminal
transition commits, and the operator's fix is a re-drive of the identical
persisted payload. ``review.py``'s docstring makes this argument at length and
it applies here unchanged, with one simplification — this write is a single row
whose natural key is already the job. So the insert is
``ON CONFLICT ON CONSTRAINT uq_match_run_job DO NOTHING`` followed by a read of
whatever row now holds that key, and
:attr:`MatchRunRecord.was_already_recorded` says which attempt this was.

The second execution therefore returns the **first** execution's run id rather
than a new one, which is the honest answer: the run happened once, and a
re-drive is a second delivery of the same command, not a second run. A fresh id
per attempt would have made a re-drive look like a correction, and corrections
are meant to be deliberate.

## Transaction boundaries belong to the caller

Like every other repository here (``jobs.py``, ``outbox.py``, ``review.py``),
this takes a :class:`~sqlalchemy.orm.Session` per call and never commits. The
executor commits it only alongside an applied terminal transition, so a run
snapshot cannot become durable for a job whose success the state machine
refused — the property ``smartmatch_worker.handlers``' module docstring calls
"business work is atomic with the terminal outcome".
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from smartmatch_domain.match_run import MatchRunPins
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = ["MatchRunRecord", "MatchRunRepository"]


@dataclass(frozen=True, slots=True)
class MatchRunRecord:
    """One stored run, as it stands after :meth:`MatchRunRepository.record`.

    Attributes:
        id: The run's identifier — the one a first execution wrote, which on a
            re-driven second execution is *not* the id that call proposed. See
            the module docstring.
        was_already_recorded: ``True`` when this call found the row rather than
            wrote it, which is exactly the re-drive case. Reported rather than
            swallowed so a handler's summary can say what happened: a run that
            was already recorded and a run recorded just now are both
            successes, and a coordinator reading the job's event stream is
            entitled to know which one they are looking at.
        created_at: When the run was recorded — the *stored* value, read back
            from the row, so a re-drive reports the first execution's timestamp
            and not the moment of the retry.
    """

    id: uuid.UUID
    tenant_id: uuid.UUID
    owning_unit_id: uuid.UUID
    job_id: uuid.UUID
    inputs_hash: str
    created_at: datetime
    was_already_recorded: bool


class MatchRunRepository:
    """Writes and reads ``match_run`` rows. Insert-only by construction."""

    def record(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        job_id: uuid.UUID,
        event_need_id: str,
        inputs_hash: str,
        portfolio_size: int,
        random_seed: int,
        weights: Mapping[str, float],
        pins: MatchRunPins,
        portfolio_status: str,
        supersedes_run_id: uuid.UUID | None = None,
        run_id: uuid.UUID | None = None,
    ) -> MatchRunRecord:
        """Insert one snapshot, or return the one this job already wrote.

        Does not commit; see the module docstring.

        Args:
            tenant_id: From the authenticated principal, by way of the job row.
                Never read out of a command payload — the rule
                ``submit_command`` states about ``owning_unit_id`` applies to
                every authorization input, and the worker honours it by taking
                both from :class:`~smartmatch_persistence.jobs.JobRecord`.
            owning_unit_id: The unit the job belongs to, and therefore the unit
                every later authorization decision about this run is scoped
                against (A5). Taken from the job row for the same reason.
            job_id: The durable command that produced this run. Also the
                natural key that makes the write idempotent under re-drive.
            event_need_id: ``PortfolioRequest.event_need_id``.
            inputs_hash: :func:`smartmatch_domain.match_run.inputs_fingerprint`
                over the pool, the size, the seed, and the weights.
            weights: The factor weights in force, stored readable alongside
                ``pins.registry_hash``, which fingerprints them. Rendered to a
                plain ``dict`` for the JSONB column — a ``Mapping`` that is not
                a ``dict`` (a ``MappingProxyType``, which is what
                ``factor_registry.active_weights`` returns) is not something
                the driver will serialize.
            pins: Every version this run is pinned to. Validated by
                :class:`~smartmatch_domain.match_run.MatchRunPins` before it
                arrives, so this method never has to decide what a blank
                version means.
            portfolio_status: The solver's verdict, as
                :class:`smartmatch_domain.optimizer.PortfolioStatus`'s value.
                Passed through rather than narrowed here — ``0018``'s CHECK
                constraint holds the vocabulary, and duplicating it in Python
                would create a second place for it to fall out of date.
            supersedes_run_id: The run this one corrects, when it corrects one.
                ``None`` is the ordinary case and means "not a correction",
                which is a different fact from "corrects nothing in particular".
            run_id: Supplied only by a caller that needs to know the id before
                the write; no production caller does. Defaults to a fresh UUID.

        Returns:
            A :class:`MatchRunRecord` describing the row that now holds this
            job's key, whether or not this call is what put it there.
        """
        proposed_id = run_id or uuid.uuid4()

        insert = (
            postgresql.insert(schema.match_run)
            .values(
                id=proposed_id,
                tenant_id=tenant_id,
                owning_unit_id=owning_unit_id,
                job_id=job_id,
                event_need_id=event_need_id,
                inputs_hash=inputs_hash,
                portfolio_size=portfolio_size,
                random_seed=random_seed,
                registry_version=pins.registry_version,
                registry_hash=pins.registry_hash,
                weights={name: float(weight) for name, weight in weights.items()},
                optimizer_model_version=pins.optimizer_model_version,
                solver_name=pins.solver_name,
                solver_version=pins.solver_version,
                route_estimate_source=pins.route_estimate_source,
                route_estimate_version=pins.route_estimate_version,
                portfolio_status=portfolio_status,
                supersedes_run_id=supersedes_run_id,
            )
            # By constraint name rather than by column list, because the name is
            # what `schema.py` mirrors and what the migration declares; an
            # inferred conflict target would be a second spelling of the same
            # key that nothing checks.
            .on_conflict_do_nothing(constraint="uq_match_run_job")
        )
        session.execute(insert)

        # Read back rather than trust the insert. `rowcount` would say whether a
        # row landed, but not what is stored: on a re-drive the durable row is
        # the *first* execution's, with its id and its created_at, and reporting
        # this call's proposed id would attribute the run to the retry.
        row = session.execute(
            sa.select(
                schema.match_run.c.id,
                schema.match_run.c.owning_unit_id,
                schema.match_run.c.inputs_hash,
                schema.match_run.c.created_at,
            ).where(
                schema.match_run.c.tenant_id == tenant_id,
                schema.match_run.c.job_id == job_id,
            )
        ).one()

        return MatchRunRecord(
            id=row.id,
            tenant_id=tenant_id,
            owning_unit_id=row.owning_unit_id,
            job_id=job_id,
            inputs_hash=row.inputs_hash,
            created_at=row.created_at,
            was_already_recorded=row.id != proposed_id,
        )

    def get(
        self, session: Session, *, tenant_id: uuid.UUID, run_id: uuid.UUID
    ) -> sa.Row[Any] | None:
        """Fetch one run, scoped to its tenant.

        ``tenant_id`` is part of the lookup rather than a filter applied
        afterwards, so a caller cannot read another tenant's run by id — the
        same rule :meth:`smartmatch_persistence.jobs.JobRepository.get` states.

        Returns the row as read, not a narrowed record type. Card M8b's routes
        decide what a run looks like on the wire, and inventing a response shape
        here — before any operation is authorized or any policy-matrix row
        exists — would be guessing at a contract this card does not own.
        """
        return session.execute(
            sa.select(schema.match_run).where(
                schema.match_run.c.tenant_id == tenant_id,
                schema.match_run.c.id == run_id,
            )
        ).one_or_none()
