"""The command payload, so an accepted command can actually be executed.

Revision ID: 0005_command_payload
Revises: 0004_lease_and_generation
Create Date: 2026-08-25

``import.create`` is the only command wired end to end and it has never once
executed. ``POST /v1/units/{unit_id}/imports`` accepts ``source_reference``,
``dataset`` and ``dry_run``; ``submit_command`` feeds the body to
``fingerprint_request`` — a one-way hash — and then drops it. Neither ``job``
nor ``outbox_record`` has anywhere to put it. By the time the worker claims the
job the only facts left are the tenant, the job id and the command type, so the
handler fails every import as ``failed_policy`` with the reason
``command_not_executable``. The command that the API's whole accept path exists
to serve is refused at the last step, every time (backlog J10).

This revision adds the missing column. ``job.payload`` is written by
``submit_command`` **in the same INSERT as the job row**, which is inside the
one transaction that already carries the idempotency reservation, the rate-limit
consumption, the job and the outbox row (v1.1 §1.6, ADR-0005). The intent to
dispatch and the parameters being dispatched are then exactly as durable as each
other: there is no commit at which a job exists carrying work nobody can
describe.

``jsonb``, not ``json`` and not ``text``
----------------------------------------
``jsonb`` for three reasons, in the order they matter here.

* **The database validates it.** A malformed payload is rejected at the insert,
  by the writer, rather than discovered minutes later by a worker that has
  already claimed the job and now has to invent a failure state for it.
* **It is queryable.** A5 (``job.owning_unit_id``) plans to backfill from
  ``payload->>'unit_id'``, and an operator triaging a stuck import will want
  ``WHERE payload->>'dataset' = …``. ``json`` supports the operators but reparses
  the document on every access; ``text`` supports nothing and would make the
  column an opaque blob the database cannot check, index or search.
* **It matches the two JSON columns already here** — ``job_event.payload`` and
  ``redrive_record.attempt_history`` are both ``jsonb``, and a third JSON column
  of a different type would be a difference readers have to explain.

What ``jsonb`` costs is normalization: it does not preserve key order, insertion
whitespace, or duplicate keys. **That cost is zero here and must stay zero.**
``fingerprint_request`` hashes the request dictionary in the API process, before
this column is written, so the fingerprint never depends on the stored form.
Anything that later recomputed a fingerprint *from this column* would be
comparing a normalized document against a hash of the original body and could
report a spurious conflict on a legitimate retry. The fingerprint is computed
from the request; this column is what the worker executes.

**No CHECK constraint, and that is a decision rather than an omission.** The
tempting one is ``jsonb_typeof(payload) = 'object'``: ``'"gs://bucket"'::jsonb``
and ``'[1,2]'::jsonb`` are valid ``jsonb`` and are not command payloads. It is
not added, for two reasons that point the same way. It would guarantee only
*not a scalar or an array*, while the guarantee a handler actually needs is
about **fields** — and those differ per command type, so a CHECK that knew
``import.create``'s field names would have to be altered by every new command,
making a schema change the price of shipping a handler. Since the handler must
validate the fields anyway, and does (``_read_import_command`` fails the job as
``invalid_command_payload`` and names every problem it found), a constraint
covering the narrow half adds a second place to state the rule and removes
nothing from the first. The second reason is the repository's own discipline:
every CHECK here has its rendered expression pinned and its forbidden and
permitted writes exercised in ``tests/integration/test_check_constraints.py``,
and adding one is that work too — worth doing deliberately, not as a side effect
of adding a column.

Nullable, no default, no backfill
----------------------------------
Expand phase, under v1.1 §4.2 and ADR-0004. The column is nullable with no
server default, so the release running **before** this migration is unaffected —
it never names the column — and the release running **after** it must tolerate
``NULL``.

**A ``NULL`` payload means the row was written by code that did not persist
one.** It does not mean "no parameters": that is ``'{}'::jsonb``, which is a
command that genuinely carried nothing, and the two are different facts that the
worker answers differently. Keeping them distinguishable is the whole reason
there is no ``DEFAULT '{}'::jsonb`` here. A default would make every pre-J10 job
— whose parameters are gone and unrecoverable — indistinguishable from a
legitimately empty command, and the handler's honest "there is nothing to
import" refusal would become a claim about the caller's request rather than
about our own missing data.

So ``handle_import_create`` treats ``NULL`` as terminal ``failed_policy`` with
the reason ``command_payload_missing``. That is the fail-closed direction and
the only honest one: no retry, no re-drive and no backfill can recover
parameters that were never written down, and reporting anything other than a
failure would claim an import that did not happen.

The rollout constraint, which is a hard ordering and not a preference
---------------------------------------------------------------------
**This migration must be applied before the new release starts.** The rule is
the one ``0004`` recorded and reproduced: ``schema.py`` is a whole-table mirror
and ``JobRepository.get`` issues ``sa.select(schema.job)``, which names every
column the mirror declares. New code against ``0004`` raises
``psycopg.errors.UndefinedColumn`` on an ordinary job read. Old-code-on-new-
schema is safe; new-code-on-old-schema is not.

What a mixed fleet does during the rolling deploy, stated because "expand phase"
alone does not say: an import accepted by an **old** API instance carries a
``NULL`` payload, and a **new** worker fails it terminally as
``command_payload_missing``; an import accepted by a new API instance and
delivered to an **old** worker fails as ``command_not_executable``, exactly as
every import does today. Both are honest terminal failures the submitter can see
and resubmit against; neither reports a success that did not happen, and neither
is silent. There is no combination in which a payload is written and then
ignored without saying so.

``NOT NULL`` is contract-phase work for a later revision, after the release is
fully promoted and the pre-J10 rows have aged out or been backfilled — the same
rule under which ``0001`` drops nothing and ``0003`` keeps a constraint it made
redundant. It cannot be done here: rows written by the current release exist with
``NULL`` and would fail the constraint at ``ALTER``.

No index, and no ``CONCURRENTLY``
----------------------------------
No index on ``payload``. Nothing queries by it: the worker fetches a job by
primary key and reads the column off the row. A GIN index would cost every
insert on the command path to serve a query nobody issues yet. A5's backfill is a
one-off full scan and does not want one either.

``ADD COLUMN`` with no default and no ``NOT NULL`` rewrites nothing — it is a
catalog change, and PostgreSQL 16 does not rebuild the table for it. It still
takes ``ACCESS EXCLUSIVE`` and, per ADR-0009, holds it until *this revision*
commits; with one statement in the revision that is the statement's own duration,
which on any table is microseconds. This revision has nothing that could extend
the lock — no index build, no constraint validation — so ``CONCURRENTLY`` and the
``autocommit_block`` it would require (see ``0004``, and the guard in
``tests/unit/test_migration_transactions.py``) have nothing to buy here.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_command_payload"
down_revision = "0004_lease_and_generation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add ``job.payload``: nullable ``jsonb``, no default, no backfill."""
    op.add_column(
        "job",
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Drop the column.

    A development tool. Production rollback never depends on it (v1.1 §4.2):
    the destructive step of expand → migrate → contract runs only after a
    release is fully promoted.

    Reversing this **destroys the parameters of every command accepted since it
    was applied** — they exist nowhere else, the fingerprint being a one-way hash
    — and returns ``import.create`` to failing every job it is given.
    """
    op.drop_column("job", "payload")
