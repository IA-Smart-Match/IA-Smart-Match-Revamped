"""Import batch and review item repository (migration ``0008``).

Architecture v1.1 §1.5: a validated import produces review items, not verified
records. This is the write path for both tables that path needs —
``import_batch`` (one row per import) and ``review_item`` (one row per
submitted record, quarantined ``pending`` until a coordinator accepts or
rejects it) — and nothing else touches them. ``handle_import_create``
(``smartmatch_worker.handlers``) decides *whether* a submission is usable, by
calling ``smartmatch_domain.ingest.validate_columns``; this module only ever
writes what that decision already reached. It performs no validation of its
own and holds no opinion about column contracts.

## Re-drive must not double-insert

A command handler can be executed more than once for the *same* job: a worker
can die after committing this module's write and before the executor's
terminal transition commits (the gap J9's lease exists to recover from), and
the operator's fix is a re-drive — the identical persisted ``job.payload``,
handed to this handler again. A second execution that inserted a second batch
and a second set of review items would double a coordinator's queue for every
row in the import, silently, and there is no UI affordance that would make that
obvious.

The fix is that both writes are **idempotent under exact replay**, and neither
half depends on the caller noticing anything:

* ``import_batch.id`` is not a fresh random id. It is ``uuid5`` of a fixed
  namespace and this job's own id (:func:`_batch_id_for_job`), which is stable
  across every execution of the same job — ``job.payload`` is immutable once
  persisted (migration ``0005``), so a re-driven job computes the identical
  batch id, dataset, and rows every time. The insert is
  ``ON CONFLICT (import_batch_pkey) DO NOTHING``, so a second execution's
  insert is a no-op rather than a duplicate row or a raised error.
* ``review_item`` rows key their identity, for this purpose, off
  ``uq_review_item_batch_row`` — ``(import_batch_id, row_index)`` — not off
  their own random ``id``. A second execution proposes fresh random ids for
  every row, and every one of them collides with the row a first execution
  already wrote at the same ``(batch, index)``, so
  ``ON CONFLICT (uq_review_item_batch_row) DO NOTHING`` skips all of them.

Neither statement needs to know whether it is the first attempt or the second;
both are correct either way, which is what makes this safe to call from a
handler that cannot itself tell the difference.

## A coordinator's decision is the other write this module makes

``import.create`` is not the only thing that writes ``review_item``.
Migration ``0013`` adds ``decided_at``/``decided_by`` to the table and
:meth:`ReviewRepository.decide` is what a coordinator's accept-or-reject
eventually calls, through ``POST /v1/review-items/{id}/decision``
(``services/api/smartmatch_api/routers/review.py``). It is a genuinely
different write from the two above — a single-row ``UPDATE`` guarded by
``status = 'pending'`` rather than an idempotent bulk insert — but it belongs
in this module rather than a new one for the same reason ``import_batch`` and
``review_item`` share this file to begin with: both tables, and every write to
either of them, are one path (v1.1 §1.5), and a second repository file would
only be a second place to look for "what may write ``review_item``".

## The queue a coordinator decides *from*

:meth:`ReviewRepository.decide` gave the API a way to move one row out of
``pending`` while nothing gave it a way to find out which rows were pending in
the first place. The coordinator dashboard counted them —
``pending_review_items`` (``smartmatch_domain.metrics``, served through
``GET /v1/units/{unit_id}/metrics``) — and no route listed them, so the screen
showed a number it could not itself explain. :meth:`list_for_unit` is the
missing read, and it is deliberately the *same query shape* the count is
derived from.

That sameness is the whole point, not an implementation convenience.
``review_item`` carries **no owning unit column**: the unit a row belongs to is
derived by joining ``import_batch.owning_unit_id``, and there are now three
places that make that derivation — ``routers/metrics.py``'s
``_pending_review_item_rows_v1`` (the count and its drill-down),
``routers/review.py``'s ``_load_review_item_context_or_404`` (the decision's
authorization), and this method. Any two of them disagreeing about the join
would put a row in one unit's queue and another unit's count, which is
precisely the defect this method exists to close. So the join is written the
same way in all three: composite on ``tenant_id`` at every hop, scoped to the
caller's tenant *in the query* rather than by a filter applied afterwards, and
inner because both ``review_item.import_batch_id`` and
``import_batch.owning_unit_id`` are ``NOT NULL`` under composite foreign keys
(migration ``0008``) — a row that fails to join cannot exist while those
constraints hold.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = [
    "ImportBatchRecord",
    "ReviewDecisionOutcome",
    "ReviewItemRow",
    "ReviewRepository",
]

#: Fixed, not random: this is a *namespace* for deriving a stable id, and a
#: value that changed on every process start would make every batch id change
#: with it, which defeats the whole point of :func:`_batch_id_for_job`. Any
#: fixed UUID works as a namespace; this one is itself derived deterministically
#: (``uuid5`` of a URL namespace and a fixed name) purely so nobody has to trust
#: that a hand-typed literal was transcribed correctly — computing it is as
#: reproducible as hard-coding it, and self-documents what it is for.
_BATCH_ID_NAMESPACE: uuid.UUID = uuid.uuid5(
    uuid.NAMESPACE_URL, "https://smartmatch.invalid/import_batch"
)


def _batch_id_for_job(job_id: uuid.UUID) -> uuid.UUID:
    """The ``import_batch.id`` a given job's execution always derives.

    A pure function of ``job_id`` alone, which is what makes it safe across a
    re-drive: the job id is stable for the life of the job (a re-drive keeps
    the same job row and only adds a new outbox generation — see
    ``smartmatch_persistence.redrive``), so every execution of the same job
    computes the same batch id without coordinating with any earlier attempt.
    """
    return uuid.uuid5(_BATCH_ID_NAMESPACE, str(job_id))


@dataclass(frozen=True, slots=True)
class ImportBatchRecord:
    """One import batch, as it stands after a write.

    Attributes:
        review_item_count: How many ``review_item`` rows this batch has *right
            now*, read back with a fresh ``COUNT`` after the insert rather than
            assumed from how many rows this call proposed. On a first execution
            the two agree; on a re-driven replay this call proposes the same
            rows again and none of them land, so trusting the proposal would
            silently overstate what changed. The count is always the honest
            answer to "how many review items does this batch have".
    """

    id: uuid.UUID
    tenant_id: uuid.UUID
    owning_unit_id: uuid.UUID
    job_id: uuid.UUID
    dataset: str
    row_count: int
    dry_run: bool
    created_at: datetime
    review_item_count: int


@dataclass(frozen=True, slots=True)
class ReviewDecisionOutcome:
    """What happened when :meth:`ReviewRepository.decide` was asked to record one.

    A router needs to answer three different ways depending on what this
    carries — 404 (:attr:`exists` is ``False``), 409
    (:attr:`exists` is ``True`` and :attr:`transitioned` is ``False``), or 200
    (:attr:`transitioned` is ``True``) — and none of those three is derivable
    from a bare boolean. See :meth:`ReviewRepository.decide`'s docstring for
    why a blind ``rowcount`` cannot distinguish the first two on its own.

    Attributes:
        exists: Whether a ``review_item`` row was found at this
            ``(tenant_id, id)``. ``False`` makes the other two fields
            meaningless, and they are left at their defaults rather than
            populated with values that would look like they mean something.
        transitioned: Whether *this call* is the one that moved the row out of
            ``pending``. ``False`` with ``exists=True`` means some earlier
            call already decided it — never this one, because a second
            decision on the same row can never itself be the transitioning
            call by construction (the conditional ``UPDATE`` cannot match a
            row twice).
        status: The row's status after this call — ``decision`` on a fresh
            transition, or whatever an earlier decision already set. ``None``
            only when ``exists`` is ``False``.
        decided_at: When the recorded decision was made — this call's own
            ``decided_at`` on a fresh transition, or the earlier decision's
            timestamp otherwise. ``None`` only when ``exists`` is ``False``.
    """

    exists: bool
    transitioned: bool
    status: str | None = None
    decided_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ReviewItemRow:
    """One ``review_item`` as a queue reader sees it.

    Carries exactly the columns a coordinator needs to decide the row and no
    more. In particular it does **not** carry ``decided_by``. That column holds
    a ``user_account`` id, and no surface in this API discloses one today —
    ``ReviewDecisionResponse`` (``routers/review.py``) answers a decision with
    ``id``, ``status`` and ``decided_at`` and stops there. A list is the widest
    possible place to be the first surface to publish who acted: it returns
    many rows at once, to anyone holding the unit's role, rather than one row to
    the caller who just acted on it. Widening disclosure is a product decision
    with its own justification to write down, not something a new read should
    acquire as a side effect of selecting one more column, so this omits it. If
    a queue is later asked to show "decided by whom", that is a deliberate
    change to this dataclass and to the decision surface together.

    ``decided_at`` *is* carried, because it is already disclosed by the decision
    response and because a queue filtered to ``accepted``/``rejected`` is
    meaningless without it — the column is ``NULL`` exactly for ``pending``
    rows (``ck_review_item_decision_evidence``), so it reads as "not yet
    decided" rather than as a missing fact.
    """

    id: uuid.UUID
    import_batch_id: uuid.UUID
    row_index: int
    status: str
    row_data: Mapping[str, Any]
    created_at: datetime
    decided_at: datetime | None


class ReviewRepository:
    """Writes ``import_batch`` and ``review_item`` rows.

    Takes a session per call, like every other repository here
    (``jobs.py``, ``outbox.py``, ``redrive.py``): transaction boundaries belong
    to the caller. :meth:`create_batch_with_items` does not commit — the caller
    commits once, after both inserts, so a crash between them can never leave a
    batch with no items or items with no batch.
    """

    def create_batch_with_items(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        job_id: uuid.UUID,
        dataset: str,
        rows: Sequence[Mapping[str, Any]],
    ) -> ImportBatchRecord:
        """Write one import batch and one review item per row.

        Args:
            owning_unit_id: The unit the job itself is scoped against
                (``job.owning_unit_id``, A5) — not re-derived from anything in
                the command payload, for the same reason ``JobRepository.create``
                takes it as a required argument rather than reading it back out
                of ``payload``: it must be the value the router already
                authorized against.
            rows: Already-normalized rows — the shape
                ``review_item.row_data`` is documented (``schema.py``) to hold.
                Normalizing is this module's caller's job
                (``smartmatch_worker.handlers``), not this one's: a repository
                that silently transformed what it was handed would make the
                stored ``row_data`` depend on a decision made two files away
                from where a reader would look for it.

        Returns:
            The batch as it stands after this call, including every row
            written by *any* execution of this job, not just this one — see
            :attr:`ImportBatchRecord.review_item_count`.
        """
        batch_id = _batch_id_for_job(job_id)

        session.execute(
            postgresql.insert(schema.import_batch)
            .values(
                id=batch_id,
                tenant_id=tenant_id,
                owning_unit_id=owning_unit_id,
                job_id=job_id,
                dataset=dataset,
                row_count=len(rows),
                # Always False: this method is only ever called once a live
                # import has already decided to write review items (dry runs
                # never reach here — see handle_import_create). The column
                # still exists for a batch that could one day be recorded from
                # a dry run too; nothing here does that yet.
                dry_run=False,
            )
            .on_conflict_do_nothing(constraint="import_batch_pkey")
        )

        if rows:
            items = [
                {
                    # Deliberately a fresh random id on every execution,
                    # including a replay. It is never the conflict target —
                    # uq_review_item_batch_row is — so a replay's fresh ids are
                    # simply the ones that lose the race against the rows
                    # already there. See the module docstring.
                    "id": uuid.uuid4(),
                    "tenant_id": tenant_id,
                    "import_batch_id": batch_id,
                    "row_index": index,
                    "row_data": row,
                }
                for index, row in enumerate(rows)
            ]
            session.execute(
                postgresql.insert(schema.review_item)
                .values(items)
                .on_conflict_do_nothing(constraint="uq_review_item_batch_row")
            )

        return self._read_batch(session, tenant_id=tenant_id, batch_id=batch_id)

    # -- internals -----------------------------------------------------------

    def _read_batch(
        self, session: Session, *, tenant_id: uuid.UUID, batch_id: uuid.UUID
    ) -> ImportBatchRecord:
        """Read a batch back, scoped by ``(tenant_id, id)`` like every lookup here."""
        row = session.execute(
            sa.select(schema.import_batch).where(
                schema.import_batch.c.tenant_id == tenant_id,
                schema.import_batch.c.id == batch_id,
            )
        ).one()

        item_count = session.execute(
            sa.select(sa.func.count())
            .select_from(schema.review_item)
            .where(
                schema.review_item.c.tenant_id == tenant_id,
                schema.review_item.c.import_batch_id == batch_id,
            )
        ).scalar_one()

        return ImportBatchRecord(
            id=row.id,
            tenant_id=row.tenant_id,
            owning_unit_id=row.owning_unit_id,
            job_id=row.job_id,
            dataset=row.dataset,
            row_count=row.row_count,
            dry_run=row.dry_run,
            created_at=row.created_at,
            review_item_count=item_count,
        )

    def list_for_unit(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        status: str,
        limit: int,
    ) -> tuple[ReviewItemRow, ...]:
        """The review items one unit owns at one ``status``, oldest first.

        The unit is **derived, never stored**. ``review_item`` has no owning
        unit column, so this joins ``import_batch`` and filters on
        ``import_batch.owning_unit_id`` — byte for byte the derivation
        ``routers/metrics.py::_pending_review_item_rows_v1`` makes for the
        ``pending_review_items`` count and its drill-down, including the
        ``ORDER BY created_at, id``. The module docstring says why that
        agreement is load-bearing rather than cosmetic: a list and a count that
        derived ownership differently would disagree about which unit a row
        belongs to, and a coordinator dashboard whose queue length contradicted
        its own badge is the defect this method closes.

        The join is composite on ``tenant_id`` at both ends and the tenant
        predicate is in the query itself, not applied to the result. A join on
        the surrogate id alone would return the same rows today only because
        the composite foreign keys already forbid a cross-tenant pairing, and a
        read behind an authorization boundary should not depend on a constraint
        defined elsewhere staying intact in order to stay safe — the same
        discipline ``JobRepository.get`` and
        ``routers/review.py::_load_review_item_context_or_404`` both state at
        length for their own joins.

        Ordered by ``created_at`` then ``id``. ``created_at`` is the order a
        queue should be worked in — oldest submission first — and ``id`` breaks
        ties so a batch inserted inside one transaction, whose rows share a
        ``now()``, never swaps places between two identical reads. A stable
        total order is also what makes a truncation cut at a stable point
        instead of at an arbitrary one.

        Args:
            owning_unit_id: The unit the caller was **already authorized
                against**, passed in rather than derived here. This method
                performs no authorization and holds no opinion about who may
                read the unit; the router authorizes, then names the unit it
                authorized. Nothing else in the request may select which rows
                come back.
            status: An exact equality predicate — ``pending``, ``accepted`` or
                ``rejected``. Not validated here, the same discipline
                :meth:`decide` states for its own ``decision`` argument: the
                router parsed and refused an out-of-vocabulary value before
                this call, and ``ck_review_item_status`` is the schema's
                backstop should that lapse. There is no "all statuses" arm and
                no ``NULL``/empty fallback that would widen the predicate into
                the whole table — an unrecognised status matches nothing, which
                is the fail-closed answer.
            limit: The maximum number of rows to return. The caller passes it
                and decides what a full page means; this method returns at most
                that many and says nothing about whether more exist, because a
                repository inventing a ``truncated`` flag would be a second
                opinion beside the route's own cap (the same split
                ``SpeakerRequestRepository.list_for_unit`` documents).

        Returns:
            At most ``limit`` :class:`ReviewItemRow` values, oldest first.
        """
        result = session.execute(
            sa.select(
                schema.review_item.c.id,
                schema.review_item.c.import_batch_id,
                schema.review_item.c.row_index,
                schema.review_item.c.status,
                schema.review_item.c.row_data,
                schema.review_item.c.created_at,
                schema.review_item.c.decided_at,
            )
            .join(
                schema.import_batch,
                sa.and_(
                    schema.import_batch.c.tenant_id == schema.review_item.c.tenant_id,
                    schema.import_batch.c.id == schema.review_item.c.import_batch_id,
                ),
            )
            .where(
                schema.review_item.c.tenant_id == tenant_id,
                schema.import_batch.c.owning_unit_id == owning_unit_id,
                schema.review_item.c.status == status,
            )
            .order_by(schema.review_item.c.created_at, schema.review_item.c.id)
            .limit(limit)
        )
        return tuple(
            ReviewItemRow(
                id=row.id,
                import_batch_id=row.import_batch_id,
                row_index=row.row_index,
                status=row.status,
                row_data=row.row_data,
                created_at=row.created_at,
                decided_at=row.decided_at,
            )
            for row in result
        )

    def decide(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        review_item_id: uuid.UUID,
        decision: str,
        decided_by: uuid.UUID,
        decided_at: datetime,
    ) -> ReviewDecisionOutcome:
        """Transition one ``pending`` review item to ``accepted`` or ``rejected``.

        One statement, ``WHERE tenant_id = ... AND id = ... AND status =
        'pending'`` — the conditional ``UPDATE`` ``0008``'s own module docstring
        proposed for this column under "no version column", the same shape
        ``JobRepository.claim`` already uses against ``job.status``. A second
        call against the same row, whatever decision it names, matches nothing:
        the row is no longer ``pending``, so there is no window in which two
        concurrent decisions could both believe they were first.

        Does not commit — the caller commits, per this module's own convention
        (see the class docstring).

        Why a blind zero-row match cannot tell the router what to answer
        ---------------------------------------------------------------------
        An ``UPDATE`` whose ``WHERE`` clause matches zero rows is silent about
        *which* clause failed to match — whether that "zero" is read off
        ``rowcount`` or, as here, off an empty ``RETURNING`` (``RETURNING`` is
        used rather than ``rowcount`` for the same typing reason
        ``OutboxRepository.mark_dispatched`` and ``JobRepository._transition``
        already give: ``rowcount`` lives on the driver's ``CursorResult``,
        which ``Session.execute`` is not statically known to return). Either
        way, a zero-row match is consistent with two entirely different facts
        on the ground — no ``review_item`` row exists at this
        ``(tenant_id, id)`` at all (a 404: the caller named something that was
        never real, or was never real *in this tenant*), or the row exists and
        is simply no longer ``pending`` (a 409: a decision already landed,
        possibly the caller's own retried request). Those are different HTTP
        statuses, so this method does not leave the router to guess between
        them from one boolean. It reads the row back — only on the path where
        the ``UPDATE`` matched nothing, so the common case pays for one
        statement, not two — and returns which of the two the caller is
        looking at as an explicit field on :class:`ReviewDecisionOutcome`,
        rather than an outcome the router has to re-derive from a count.

        Args:
            decision: ``"accepted"`` or ``"rejected"``. Not validated here —
                the same discipline ``create_batch_with_items`` states for
                ``row_data``: this module writes what its caller already
                decided, and the router is where the request body was parsed
                and where an invalid value must already have been refused.
                ``ck_review_item_status`` is the schema's own backstop should
                that discipline ever lapse.
            decided_by: The authorizing principal's own verified user id — the
                same "server derives it, the caller never names it" discipline
                ``import.create`` applies to ``owning_unit_id``. This module
                trusts what it is handed; the router is where that value is
                the caller's *own* identity and not one they supplied.

        Returns:
            A :class:`ReviewDecisionOutcome` reporting one of: the row does not
            exist in this tenant, the row exists but was already decided (this
            call's ``UPDATE`` matched nothing), or the row was just
            transitioned by this call.
        """
        transitioned_id = session.execute(
            sa.update(schema.review_item)
            .where(
                schema.review_item.c.tenant_id == tenant_id,
                schema.review_item.c.id == review_item_id,
                schema.review_item.c.status == "pending",
            )
            .values(status=decision, decided_at=decided_at, decided_by=decided_by)
            .returning(schema.review_item.c.id)
        ).one_or_none()

        if transitioned_id is not None:
            # The common case: this call's own UPDATE is the decision, so its
            # own arguments are the record of what just happened. No read-back
            # needed — every field the caller could want was already supplied.
            return ReviewDecisionOutcome(
                exists=True,
                transitioned=True,
                status=decision,
                decided_at=decided_at,
            )

        # The UPDATE matched nothing. Read the row back, scoped the same way
        # every lookup in this codebase is, to learn which of the two
        # zero-match cases this is.
        row = session.execute(
            sa.select(
                schema.review_item.c.status,
                schema.review_item.c.decided_at,
            ).where(
                schema.review_item.c.tenant_id == tenant_id,
                schema.review_item.c.id == review_item_id,
            )
        ).one_or_none()

        if row is None:
            return ReviewDecisionOutcome(exists=False, transitioned=False)

        return ReviewDecisionOutcome(
            exists=True,
            transitioned=False,
            status=row.status,
            decided_at=row.decided_at,
        )
