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

__all__ = ["ImportBatchRecord", "ReviewRepository"]

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
