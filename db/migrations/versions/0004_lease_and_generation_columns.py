"""Three columns that let a writer prove which attempt it is finishing.

Revision ID: 0004_lease_and_generation
Revises: 0003_global_subject
Create Date: 2026-08-24

Three defects found by the J11 and J12 audits share one shape: a writer knows
*that* something is in progress and cannot tell **which** thing, or **whose**.
Each needs somewhere to record an identity that is currently thrown away, and
none of them can be fixed at the call site because the column does not exist.
They are in one revision because they are one schema change, and splitting them
would make three expand-phase migrations where one does.

``idempotency_record.result_generation`` — J14
----------------------------------------------
The re-drive replay branch answers a repeated request with
``current_generation(...)``, which returns the job's *latest* dispatch rather
than the one the replayed key created. K1 re-drives (generation 1), the job
fails again, K2 re-drives (generation 2), and a retry of **K1** answers
``{"replayed": true, "generation": 2}``. It is wrong in the one field that
exists to disambiguate dispatches, and it is wrong silently.

The generation is not known when the key is reserved: ``_reserve`` runs before
``RedriveRepository.redrive``, and the generation is that call's result. So the
column is written *after* the command succeeds, on the row the reservation just
created, inside the same savepoint — and read back on replay instead of being
recomputed.

Nullable, with no backfill. A row reserved before this revision has ``NULL``,
and so does a reservation whose command never completed.

``outbox_record.lease_token`` — J17
------------------------------------
``mark_dispatched`` and ``mark_failed`` guard on ``status = 'leased'``, which
proves *someone* holds the row and not that the caller does. That is enough
against the reclaim — a reclaimed row is ``failed`` and fails the check — and
not enough against a peer dispatcher that re-claimed the row after this caller's
lease expired, because the peer's own claim satisfies ``leased``. Measured: a
stale ``mark_failed`` carrying the older attempt count overwrites the peer's
fresh lease with the older count's much shorter backoff, cutting 56 seconds off
it, and replaces the peer's ``last_error``. The row becomes claimable while the
peer is still working it, and the extra claim burns an attempt the row should
not have spent.

A token minted per claim turns "someone holds this" into "*you* hold this".
``claim_batch`` writes a fresh one per row and returns it; both writers require
it. A peer that re-claimed holds a different token, so the stale writer matches
zero rows and learns it lost instead of corrupting the winner's state.

``job.lease_expires_at`` — J9
------------------------------
``execution.py`` names this and does not close it: a worker that dies after
``dispatched -> running`` commits and before the terminal transition does leaves
the job ``running`` with nothing behind it. Today such a job stays ``running``
until someone looks. Recovering it needs a deadline on the row and something
that sweeps past it.

The index is partial on ``lease_expires_at IS NOT NULL``, which is not the
predicate it first had. ``WHERE status = 'running'`` is the obvious choice and
it is the wrong one: **PostgreSQL cannot use a partial index whose predicate
names a column the query supplies as a bound parameter**, because the planner
cannot prove ``$1`` is always ``'running'``. Every query in this repository
binds its values. Measured against 50,000 jobs of which 200 are ``running``: with
the ``status`` predicate, a literal query index-scans and the same query under a
**generic** plan — which is what a prepared statement settles into — falls back
to a sequential scan of the whole table. With ``lease_expires_at IS NOT NULL``
the generic plan index-scans and applies ``status = $1`` as a filter. The index
stays just as small, because only a ``running`` job carries a lease: 16 kB
against a 5.3 MB table in that measurement.

Why every column is nullable, and why nothing is backfilled
-----------------------------------------------------------
This is expand-phase, under v1.1 §4.2 and ADR-0004's expand/migrate/contract
section. Each column is nullable with no default and no backfill, so:

* the release running **before** this migration ignores all three and is
  unaffected — it never names them, and nothing it writes becomes invalid;
* the release running **after** it must tolerate ``NULL`` on rows that predate
  it, which during a rolling deploy includes rows written seconds ago by an
  instance that has not restarted yet.

**This migration must be applied before the new release starts, and that is a
hard ordering, not a preference.** Expand-phase is often read as "both
directions are safe". Only one is. ``schema.py`` is a table mirror and
``JobRepository.get`` issues ``sa.select(schema.job)``, which compiles to a
``SELECT`` naming every column the mirror declares — including
``lease_expires_at``. Reproduced: against ``0003``, the new code raises
``psycopg.errors.UndefinedColumn: column job.lease_expires_at does not exist``
on an ordinary job read, before any of J9's code exists. Old-code-on-new-schema
is safe; new-code-on-old-schema is not, and no amount of nullability changes
that while the mirror selects whole tables.

Making any of them ``NOT NULL`` is contract-phase work, and belongs in a later
revision that runs after the release is fully promoted — the same rule under
which ``0001`` drops nothing and ``0003`` keeps a constraint it made redundant.

What each ``NULL`` means to the code, stated because "nullable" alone does not
say:

* ``result_generation`` falls back to the old — and wrong — computed answer with
  a warning. Refusing would turn a rolling deploy into 500s on the replay path,
  which is a worse failure than the one being fixed.
* ``lease_expires_at`` being ``NULL`` means the row is not swept. That is the
  fail-safe direction: a job is left alone rather than terminated on the
  strength of a missing deadline.
* ``lease_token`` is the one whose ``NULL`` carries a **rollout constraint
  rather than a meaning**, and saying otherwise would be wrong. It is tempting
  to write "a ``NULL`` token is a row no current dispatcher holds". That is
  false in a mixed-version fleet: a dispatcher still running the old code claims
  rows against this schema without writing a token, so it *actively holds* a
  ``NULL``-token row — and its ``mark_dispatched`` and ``mark_failed`` still
  guard on ``status = 'leased'`` alone, so it can overwrite a new dispatcher's
  tokenized lease exactly as J17 describes. **J17's ownership guarantee holds
  only once every dispatcher runs the new code.** The column makes the fix
  possible; draining the old dispatchers is what makes it true.

No ``CONCURRENTLY``, deliberately
----------------------------------
``ADD COLUMN`` with no default and no ``NOT NULL`` rewrites nothing — it is a
catalog change, and PostgreSQL 16 does not rebuild the table for it.

**It does not follow that the lock is brief, and an earlier draft of this
docstring said it was.** ``ADD COLUMN`` takes ``ACCESS EXCLUSIVE``, and
PostgreSQL holds locks until the transaction ends rather than until the
statement does. That transaction is this revision (ADR-0009), so the
``ACCESS EXCLUSIVE`` on ``job`` is taken by the ``ADD COLUMN`` and held
**across the index build** until ``0004`` commits — blocking reads as well as
writes for that whole span, not just for the catalog update. Verified against
PostgreSQL 16.15 by reading ``pg_locks`` from a second session mid-transaction:
the ``AccessExclusiveLock`` is still granted while ``CREATE INDEX`` runs.

Against an empty ``job`` that span is microseconds either way, which is why the
simple form is still the right trade here.

``CREATE INDEX CONCURRENTLY`` would shorten it — though note it avoids blocking
DML, not all locking — and it is not used. It
cannot run inside a transaction at all, so it would need
``with op.get_context().autocommit_block():`` — which ``transaction_per_migration
= True`` does **not** provide and is not a substitute for (ADR-0009) — and a
build that fails partway leaves an ``INVALID`` index for someone to find and
drop by hand. Those obligations buy an availability benefit nothing can
currently collect: nothing is deployed. Whoever first runs this against a live
system with a large ``job`` table should switch, and take the obligations with
it. ``0003`` records the same trade for the same reason.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_lease_and_generation"
down_revision = "0003_global_subject"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add three nullable columns and one partial index.

    Order is not significant — the three tables are independent, and each
    statement is a catalog change that cannot fail on data because none of the
    columns constrains any.
    """
    op.add_column(
        "idempotency_record",
        sa.Column("result_generation", sa.Integer(), nullable=True),
    )
    op.add_column(
        "outbox_record",
        sa.Column("lease_token", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "job",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Partial on `lease_expires_at IS NOT NULL`, **not** on `status = 'running'`.
    # See the docstring: a predicate naming `status` is unusable by a query that
    # binds the status as a parameter, which is how every query in this
    # repository is written.
    op.create_index(
        "ix_job_running_lease",
        "job",
        ["lease_expires_at"],
        postgresql_where=sa.text("lease_expires_at IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop all three, and the index.

    Usable on a development database. Production rollback never depends on it:
    migrations follow expand → migrate → contract, and the destructive step runs
    only after a release is fully promoted (v1.1 §4.2).

    Reversing this restores the three defects it exists to make fixable — a
    replay reporting the latest generation rather than its own, a stale
    dispatcher overwriting a peer's lease, and a job stuck in ``running`` with
    nothing to find it. That is the point of a downgrade being a development
    tool: it returns the schema, not the correctness.
    """
    op.drop_index("ix_job_running_lease", table_name="job")
    op.drop_column("job", "lease_expires_at")
    op.drop_column("outbox_record", "lease_token")
    op.drop_column("idempotency_record", "result_generation")
