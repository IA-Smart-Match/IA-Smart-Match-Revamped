"""Job and job-event repository.

Architecture v1.1 §1.6 and §1.7. Two properties matter here and are tested
against a real database:

* **State transitions are validated against the domain state machine** before
  they are written, and the database's own CHECK constraint is the backstop.
* **Claiming a job is atomic.** ``claim`` moves ``dispatched -> running`` with a
  conditional UPDATE, so a duplicate Cloud Tasks delivery finds zero rows
  matching and does not double-execute. Cloud Tasks guarantees at-least-once
  delivery, which makes this the load-bearing check, not a nicety.
* **A job carries what it is for.** ``create`` writes the command's parameters
  into ``job.payload`` as part of the job's own INSERT (migration ``0005``), so
  the parameters commit with the intent to dispatch and with the outbox row that
  will dispatch it. Before that column existed the request body was hashed for
  idempotency and then discarded, and every import reaching the worker failed
  because nothing could say what to import (J10).
* **A ``running`` job carries a deadline, and only a ``running`` job does.**
  ``claim`` writes ``job.lease_expires_at`` in the same conditional UPDATE that
  takes ``dispatched -> running``; ``renew_lease`` pushes it out while the work
  reports progress; every :meth:`JobRepository.transition` clears it; and
  ``sweep_expired_leases`` takes ``running -> timed_out`` for the rows that
  outlived theirs. Before that, a worker killed after the claim committed and
  before its outcome did left the job ``running`` with nothing behind it, until
  a human noticed (J9, migration ``0004``).

## The lease is a bound on *silence*, not on duration

This is the one thing a handler author has to know. The lease says how long a
claimed job may go without saying anything before the sweep is entitled to
conclude nobody is behind it. It does not say how long work may take. A handler
that runs for an hour and emits progress every minute is never swept; a handler
that runs for eleven minutes in silence under a ten-minute lease is, and its
outcome is then discarded by the ``expected_from='running'`` guard in the
worker's own terminal transition.

Renewal is deliberately tied to progress events rather than to a background
timer. A timer would renew the lease of a handler that had hung, which is
precisely the job the sweep exists to find — the renewal would prove the
*process* was alive and assert that the *work* was, and those are different
claims. An emitted event is evidence of the second.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import sqlalchemy as sa
from smartmatch_domain.jobs import JobState, assert_transition
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = [
    "DEFAULT_JOB_LEASE",
    "JobEventRecord",
    "JobRecord",
    "JobRepository",
    "TimedOutJobRecord",
]

#: How long a claimed job may stay silent before the sweep may conclude that
#: nothing is behind it.
#:
#: Generous on purpose, and much longer than ``outbox.DEFAULT_LEASE``. The two
#: leases bound different things and the asymmetry is deliberate: the outbox
#: lease bounds how long a dispatcher may hold a row across one enqueue call,
#: which is a network round trip; this one bounds how long a *command handler*
#: may work without reporting progress, and a handler is arbitrary code doing
#: arbitrary work. Setting it low would make the sweep terminate live jobs,
#: which is a worse failure than the one it exists to fix — a stuck job is
#: visible-once-swept, whereas a job killed mid-flight has already half-run.
DEFAULT_JOB_LEASE: Final[timedelta] = timedelta(minutes=10)


@dataclass(frozen=True, slots=True)
class JobRecord:
    """A durable job.

    Attributes:
        payload: The command's parameters as they were submitted, or ``None``
            when the row carries none. The two are different facts and a reader
            must treat them as such: ``{}`` is a command that genuinely carried
            no parameters, while ``None`` is a row written before ``job.payload``
            existed (migration ``0005``) or by a release that did not write it.
            Nothing can recover the parameters of such a row — the idempotency
            fingerprint is a one-way hash — so a handler that finds ``None``
            must fail the job rather than guess, and must not treat it as an
            empty command.
        lease_expires_at: When the worker holding this job is expected to have
            reported an outcome, or ``None`` when no worker holds it. Only a
            ``running`` job carries one. ``None`` on a ``running`` row means the
            job was claimed by a release that predates J9 — such a row is never
            swept, which is the fail-safe direction: a missing deadline is not
            grounds for terminating work that may still be in flight.
        owning_unit_id: The organizational unit this job belongs to (A5,
            migration ``0006``). ``NOT NULL`` in the database, and referenced
            through the composite ``(tenant_id, owning_unit_id)`` so it can never
            name a unit in another tenant.
        owning_unit_path: That unit's ``ltree`` path as text, which is the form
            :mod:`smartmatch_api.job_authz` needs — the policy matches an
            inherited grant against a path, not against an id.

            ``None`` means **this record was not read from the database**:
            :meth:`JobRepository.create` returns a write receipt and does not
            re-read the row to resolve a path for the id it was just handed.
            Every read path populates it. The two are deliberately
            distinguishable rather than papered over by having ``create`` accept
            the path as an argument: a path supplied alongside an id is a second
            source of truth for one fact, and the authorizer must never be handed
            one — it treats ``None`` as a denial, which a *wrong* path would not
            be.
    """

    id: uuid.UUID
    tenant_id: uuid.UUID
    command_type: str
    status: JobState
    actor_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    owning_unit_id: uuid.UUID
    payload: dict[str, Any] | None = None
    lease_expires_at: datetime | None = None
    owning_unit_path: str | None = None


@dataclass(frozen=True, slots=True)
class JobEventRecord:
    """One entry in a job's event stream."""

    job_id: uuid.UUID
    sequence: int
    payload: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TimedOutJobRecord:
    """A job the sweep moved from ``running`` to ``timed_out``.

    Carries only what the caller needs to explain the sweep afterwards: which
    job, whose, what it was, and how long ago the deadline it missed had passed.

    Attributes:
        lease_expired_at: The deadline the row carried, read back from the row
            *before* the sweep cleared it. It is the only evidence of how long
            the job had been unattended, and it is gone from the row the instant
            this write commits.
    """

    id: uuid.UUID
    tenant_id: uuid.UUID
    command_type: str
    lease_expired_at: datetime


class JobRepository:
    """Reads and writes jobs and their event streams.

    The repository takes a :class:`~sqlalchemy.orm.Session` per call rather than
    holding one. Transaction boundaries belong to the caller: the API needs the
    idempotency check, the job row, and the outbox row in *one* transaction
    (v1.1 §1.6), and a repository that opened its own could not provide that.
    """

    def create(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        command_type: str,
        owning_unit_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        deadline: datetime | None = None,
        job_id: uuid.UUID | None = None,
        payload: dict[str, Any] | None = None,
    ) -> JobRecord:
        """Insert a job in ``queued``.

        Does not commit. The caller commits once, with the outbox row, so a
        crash can never leave a job with no outbox entry to dispatch it.

        Args:
            owning_unit_id: The organizational unit this job belongs to, and the
                thing every later authorization decision about it is scoped
                against (A5, migration ``0006``).

                **Required, and positioned among the required arguments rather
                than given a default**, which is the same choice ``claim`` makes
                about its lease and for the same reason: a default here would be
                a value invented by this module for a fact only the caller knows,
                and every job that took it would be authorized against the wrong
                subtree. There is no safe default — the tenant's root unit would
                grant every coordinator in the tenant access to work they should
                not reach, which is the hole ``0006`` closes.

                It must be a unit the caller has already **authorized against**,
                never one read out of ``payload``. ``routers/imports.py``
                resolves it with ``load_unit_or_404`` from the path parameter and
                passes ``assert_allowed`` the same unit, so the id stored here is
                by construction the one the request was permitted for.
            payload: The command's parameters. Written as a column of **this
                INSERT**, which is the strongest available form of "in the same
                transaction": there is no second statement that could be moved,
                reordered, or committed separately, and no arrangement of the
                caller's code in which a job exists carrying work nobody can
                describe. That property is what backlog J10 is about — see
                migration ``0005``.

                Omit it only for a command that genuinely has no parameters. The
                resulting ``NULL`` is indistinguishable from a row written before
                ``0005``, and a worker reading one is entitled to fail the job.

        Returns:
            A write receipt. Its ``owning_unit_path`` is ``None``: this method
            writes an id and does not read the unit back to resolve a path for
            it. Anything that needs the path — which in practice means anything
            authorizing — must go through :meth:`get`.
        """
        job_id = job_id or uuid.uuid4()
        now = datetime.now(UTC)

        session.execute(
            sa.insert(schema.job).values(
                id=job_id,
                tenant_id=tenant_id,
                command_type=command_type,
                status=JobState.QUEUED.value,
                actor_id=actor_id,
                deadline=deadline,
                payload=payload,
                owning_unit_id=owning_unit_id,
                created_at=now,
                updated_at=now,
                version=1,
            )
        )

        return JobRecord(
            id=job_id,
            tenant_id=tenant_id,
            command_type=command_type,
            status=JobState.QUEUED,
            actor_id=actor_id,
            created_at=now,
            updated_at=now,
            owning_unit_id=owning_unit_id,
            payload=payload,
        )

    def get(self, session: Session, *, tenant_id: uuid.UUID, job_id: uuid.UUID) -> JobRecord | None:
        """Fetch one job and the path of the unit that owns it, scoped to its tenant.

        ``tenant_id`` is part of the lookup, not a filter applied afterwards, so
        a caller cannot accidentally read another tenant's job by id.

        ## The join is on both columns, and that is not belt and braces

        ``org_unit`` is joined on ``tenant_id`` **and** ``id``, matching the
        composite foreign key ``0006`` added. The key already makes a
        cross-tenant pairing unstorable, so a join on ``id`` alone would return
        the same rows today — and would be the half of the pair that silently
        stopped being safe if the constraint were ever simplified. The read that
        feeds an authorization decision should not depend on a constraint
        elsewhere being intact; it should state the same rule itself.

        An **inner** join, deliberately. ``owning_unit_id`` is ``NOT NULL`` and
        the foreign key guarantees the unit exists, so a job that fails to match
        is a job whose owning unit vanished — which cannot happen through
        ``RESTRICT``. Returning ``None`` for such a row means the four job routes
        answer ``404`` rather than authorizing against a path they could not
        resolve, which is the fail-closed direction. An outer join would produce
        a record carrying ``owning_unit_path=None``, and while
        :mod:`smartmatch_api.job_authz` denies on that too, one refusal is better
        than two ways to reach it.

        The path is cast to ``Text`` because ``ltree`` has no SQLAlchemy type
        (see ``schema.LTree``) and the policy parses a string —
        ``units.py::load_unit_or_404`` casts the same column the same way for the
        same reason.
        """
        row = session.execute(
            sa.select(
                schema.job,
                sa.cast(schema.org_unit.c.path, sa.Text).label("owning_unit_path"),
            )
            .join(
                schema.org_unit,
                sa.and_(
                    schema.org_unit.c.tenant_id == schema.job.c.tenant_id,
                    schema.org_unit.c.id == schema.job.c.owning_unit_id,
                ),
            )
            .where(schema.job.c.tenant_id == tenant_id, schema.job.c.id == job_id)
        ).one_or_none()

        if row is None:
            return None
        return _to_job_record(row)

    def transition(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        job_id: uuid.UUID,
        to_state: JobState,
        expected_from: JobState | None = None,
        lease: timedelta | None = None,
    ) -> bool:
        """Move a job to ``to_state``, validating the transition first.

        Args:
            expected_from: When given, the UPDATE additionally requires the row
                to still be in this state. That makes the move a compare-and-set
                and is how concurrent workers are prevented from both advancing
                the same job.
            lease: How long the job's new state may go unattended. Given only by
                :meth:`claim`, which is the only transition *into* ``running``.

        Returns:
            ``True`` if a row was updated. ``False`` means another actor moved
            the job first — a normal race outcome, not an error.

        Raises:
            InvalidTransitionError: if the transition is illegal per the domain
                state machine. Validated before touching the database so an
                illegal move is a programming error surfaced in the caller's
                stack, not a constraint violation surfaced in the driver's.

        ## Every transition writes the lease, and almost every one clears it

        ``lease_expires_at`` is set here rather than by a separate statement,
        for the same reason ``payload`` is a column of ``create``'s INSERT:
        there is then no arrangement of a caller's code in which the two
        disagree. A job that is ``running`` and a job that has a deadline are
        meant to be the same set of rows, and the way to keep them the same set
        is to write both facts with one statement.

        So the default is ``NULL``: *leaving* ``running`` — succeeded, failed,
        cancelled, timed out — must drop the deadline, or a terminal job keeps a
        stale one, sits in ``ix_job_running_lease`` forever, and reads to anyone
        inspecting the row as though a worker were still on it. Transitions that
        never involve ``running`` at all (``queued -> dispatched``, the
        dispatcher's parking write, re-drive) clear a column that was already
        ``NULL``, which costs nothing and means no future transition has to
        remember to.
        """
        if expected_from is not None:
            assert_transition(expected_from, to_state)

        conditions = [
            schema.job.c.tenant_id == tenant_id,
            schema.job.c.id == job_id,
        ]
        if expected_from is not None:
            conditions.append(schema.job.c.status == expected_from.value)

        now = datetime.now(UTC)

        # Returning the id rather than reading ``rowcount`` keeps this typed and
        # portable: ``rowcount`` lives on CursorResult, which ``Session.execute``
        # is not statically known to produce.
        updated = session.execute(
            sa.update(schema.job)
            .where(*conditions)
            .values(
                status=to_state.value,
                lease_expires_at=now + lease if lease is not None else None,
                updated_at=now,
                version=schema.job.c.version + 1,
            )
            .returning(schema.job.c.id)
        ).one_or_none()

        return updated is not None

    def claim(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        job_id: uuid.UUID,
        lease: timedelta = DEFAULT_JOB_LEASE,
    ) -> bool:
        """Claim a dispatched job for execution, taking a lease on it.

        This is the guard against double execution. Cloud Tasks delivers
        at-least-once, so the same task can arrive twice; only the delivery whose
        conditional UPDATE matches a ``dispatched`` row proceeds. The second
        finds zero rows and returns ``False``, and the worker acknowledges it
        without re-running the work.

        **The lease is taken by the same UPDATE, never by a follow-up** (J9).
        The window this closes is one statement wide and it is the exact window
        the defect lives in: a worker that claimed the job and died before
        writing a deadline would leave a ``running`` row nothing would ever
        sweep, which is the state the whole item exists to make impossible.

        ``lease`` defaults rather than being required, and that direction is
        chosen deliberately. A forgotten argument would produce a ``NULL``
        deadline — a row the sweep skips forever — so the default has to be a
        real lease, not ``None``.
        """
        return self.transition(
            session,
            tenant_id=tenant_id,
            job_id=job_id,
            to_state=JobState.RUNNING,
            expected_from=JobState.DISPATCHED,
            lease=lease,
        )

    def renew_lease(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        job_id: uuid.UUID,
        lease: timedelta = DEFAULT_JOB_LEASE,
    ) -> bool:
        """Push a running job's deadline out, on the strength of progress.

        Conditional on the job still being ``running``, which makes a ``False``
        return meaningful rather than merely unsuccessful: the job left
        ``running`` while the worker believed it held it. The two ways that
        happens are a cancellation and this lease having already expired and
        been swept — and the caller is entitled to say so, because a worker
        reporting progress on a job that has been timed out is the visible
        symptom of a lease set shorter than the work.

        **Not a transition, and deliberately not routed through one.** The
        state does not change, so ``assert_transition`` has nothing to check and
        ``running -> running`` is not in the state machine. ``version`` is left
        alone for the same reason: it counts state changes, and a handler
        emitting progress every second would otherwise churn it without any
        state having changed. ``updated_at`` *does* move, because the row did.

        Returns:
            ``True`` if the lease was extended.
        """
        now = datetime.now(UTC)

        renewed = session.execute(
            sa.update(schema.job)
            .where(
                schema.job.c.tenant_id == tenant_id,
                schema.job.c.id == job_id,
                schema.job.c.status == JobState.RUNNING.value,
            )
            .values(lease_expires_at=now + lease, updated_at=now)
            .returning(schema.job.c.id)
        ).one_or_none()

        return renewed is not None

    def sweep_expired_leases(
        self,
        session: Session,
        *,
        now: datetime | None = None,
        limit: int = 100,
    ) -> list[TimedOutJobRecord]:
        """Take ``running -> timed_out`` for jobs whose lease has run out (J9).

        The recovery path for a worker that died after its claim committed and
        before its outcome did. Nothing else finds such a job: the task it came
        from was acknowledged or has exhausted its own retries, the outbox row
        is ``dispatched`` and no dispatcher revisits it, and ``running`` reaches
        neither ``redrive_pending`` nor any terminal state on its own. It stays
        ``running`` until a human looks — which is what ``execution.py`` named
        and could not close.

        ``timed_out`` rather than ``failed_provider``, and the distinction is
        not cosmetic. Both are re-drivable (``TRANSITIONS[TIMED_OUT]`` is
        ``{queued, redrive_pending}``, identically to ``failed_provider``), so
        recovery is the same either way — but only one of them is true. Nothing
        here knows the provider failed; what is known is that a deadline passed
        with nobody reporting. ``failed_provider`` would put that guess in the
        operator's audit trail.

        ## The predicate, and why it is written in this order

        ``lease_expires_at < now`` first, ``status = 'running'`` second, and
        that is the whole reason ``ix_job_running_lease`` is partial on
        ``lease_expires_at IS NOT NULL`` rather than on the status. Migration
        ``0004`` measured it: a partial index predicated on ``status`` is
        unusable by a query that binds the status as a parameter, because the
        planner cannot prove ``$1`` is always ``'running'``, and every query in
        this repository binds its values. Written this way the range condition
        drives an index scan — ``<`` is strict, so it implies ``IS NOT NULL``
        and the planner can discharge the index's predicate — and the status is
        applied as a filter on the few rows that survive.

        **A ``NULL`` deadline is not expired.** It fails the ``<`` comparison
        and the row is skipped, exactly as ``_stranded_predicate`` skips a
        ``leased`` outbox row carrying no lease, and for a stronger version of
        the same reason: a ``running`` job with no deadline was claimed by a
        release that predates J9, and terminating live work on the strength of a
        column that release never wrote would be a defect introduced by the fix.

        ## Shape

        The CTE + ``FOR UPDATE SKIP LOCKED`` form is the one
        ``OutboxRepository.claim_batch`` uses and it is here for the reasons
        ADR-0005 gives there, both of which apply unchanged: PostgreSQL cannot
        hash a subplan containing ``FOR UPDATE``, so an ``IN (SELECT ... LIMIT
        n)`` may re-execute and sweep far more rows than asked; and ``SKIP
        LOCKED`` makes two concurrent sweeps take disjoint sets rather than
        serialize.

        Oldest deadline first, so a sweep that hits ``limit`` rescues the work
        that has been unattended longest rather than an arbitrary subset. The
        ``ORDER BY`` in the CTE decides *which* rows are taken under ``LIMIT``;
        the results are re-sorted in Python because ``UPDATE ... RETURNING`` has
        no defined output order, which is the defect J13 found in ``claim_batch``
        and is not worth rediscovering here.

        Args:
            now: Injected for tests, so lease expiry is exercised without
                waiting out a real deadline.
            limit: Most rows to sweep in one call.

        Returns:
            The jobs moved to ``timed_out``, oldest deadline first. **Does not
            commit** — the caller owns the transaction, because the event that
            explains each sweep has to commit with it.
        """
        # Asked of the domain rather than assumed, so this method cannot outlive
        # a state machine that stopped permitting the move. `transition` makes
        # the same call for the same reason.
        assert_transition(JobState.RUNNING, JobState.TIMED_OUT)

        now = now or datetime.now(UTC)

        expired = (
            sa.select(
                schema.job.c.id,
                # Selected as well as filtered on, because the UPDATE below
                # overwrites it: `RETURNING` on an UPDATE yields the *new* row,
                # so reading `job.lease_expires_at` there would report the NULL
                # this sweep just wrote. The deadline the row missed exists
                # nowhere else once this commits, and it is the only measure of
                # how long the job went unattended.
                schema.job.c.lease_expires_at.label("lease_expired_at"),
            )
            .where(
                schema.job.c.lease_expires_at < now,
                schema.job.c.status == JobState.RUNNING.value,
            )
            .order_by(schema.job.c.lease_expires_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
            .cte("expired_leases")
        )

        rows = session.execute(
            sa.update(schema.job)
            .where(schema.job.c.id == expired.c.id)
            .values(
                status=JobState.TIMED_OUT.value,
                # Cleared with the same write that ends the job, for the reason
                # `transition` gives: a terminal row holding a deadline reads as
                # though a worker were still on it, and would sit in the partial
                # index forever.
                lease_expires_at=None,
                updated_at=now,
                version=schema.job.c.version + 1,
            )
            .returning(
                schema.job.c.id,
                schema.job.c.tenant_id,
                schema.job.c.command_type,
                expired.c.lease_expired_at,
            )
        ).all()

        ordered = sorted(rows, key=lambda row: (row.lease_expired_at, row.id))

        return [
            TimedOutJobRecord(
                id=row.id,
                tenant_id=row.tenant_id,
                command_type=row.command_type,
                lease_expired_at=row.lease_expired_at,
            )
            for row in ordered
        ]

    def append_event(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        job_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> JobEventRecord:
        """Append an event, assigning the next sequence number for this job.

        The sequence is computed inside the statement
        (``SELECT coalesce(max(sequence), 0) + 1``) rather than read and then
        written, so two concurrent appends cannot both compute the same number.
        If they race, the ``(job_id, sequence)`` unique constraint rejects the
        loser and the caller retries — which is correct, and cheaper than
        serializing every append behind a lock.
        """
        next_sequence = (
            sa.select(sa.func.coalesce(sa.func.max(schema.job_event.c.sequence), 0) + 1)
            .where(schema.job_event.c.job_id == job_id)
            .scalar_subquery()
        )

        row = session.execute(
            sa.insert(schema.job_event)
            .values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                job_id=job_id,
                sequence=next_sequence,
                payload=payload,
            )
            .returning(
                schema.job_event.c.sequence,
                schema.job_event.c.created_at,
            )
        ).one()

        return JobEventRecord(
            job_id=job_id,
            sequence=row.sequence,
            payload=payload,
            created_at=row.created_at,
        )

    def latest_sequence(self, session: Session, *, tenant_id: uuid.UUID, job_id: uuid.UUID) -> int:
        """Return the highest event sequence for a job, or 0 when it has none.

        Lets a status response tell a client where to resume from without
        shipping the whole event history alongside it.
        """
        highest: int | None = session.execute(
            sa.select(sa.func.max(schema.job_event.c.sequence)).where(
                schema.job_event.c.tenant_id == tenant_id,
                schema.job_event.c.job_id == job_id,
            )
        ).scalar_one_or_none()
        return highest or 0

    def events_since(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        job_id: uuid.UUID,
        after_sequence: int = 0,
        limit: int = 500,
    ) -> list[JobEventRecord]:
        """Read events after ``after_sequence``, oldest first.

        This is the single source for both SSE and polling (v1.1 §1.6): an SSE
        reconnect passes ``Last-Event-ID`` as ``after_sequence`` and a polling
        client reads the same rows, so the two cannot disagree.
        """
        rows = session.execute(
            sa.select(schema.job_event)
            .where(
                schema.job_event.c.tenant_id == tenant_id,
                schema.job_event.c.job_id == job_id,
                schema.job_event.c.sequence > after_sequence,
            )
            .order_by(schema.job_event.c.sequence)
            .limit(limit)
        ).all()

        return [
            JobEventRecord(
                job_id=row.job_id,
                sequence=row.sequence,
                payload=row.payload,
                created_at=row.created_at,
            )
            for row in rows
        ]


def _to_job_record(row: sa.Row[Any]) -> JobRecord:
    # `payload` is read back as the dict PostgreSQL parsed, not as the text that
    # was sent: jsonb does not preserve key order, insertion whitespace, or
    # duplicate keys. Nothing may recompute an idempotency fingerprint from this
    # value for exactly that reason — the fingerprint is taken from the request
    # body in the API process, before the row is written. See migration 0005.
    payload: dict[str, Any] | None = row.payload
    return JobRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        command_type=row.command_type,
        status=JobState(row.status),
        actor_id=row.actor_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        owning_unit_id=row.owning_unit_id,
        payload=payload,
        lease_expires_at=row.lease_expires_at,
        # Present because `get` joins it in. This is the only place a record
        # acquires a path, which is what makes "read from the database" and "has
        # an owning unit path" the same condition for the authorizer.
        owning_unit_path=row.owning_unit_path,
    )
