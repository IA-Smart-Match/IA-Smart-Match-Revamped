"""The owning organizational unit, so a job can be scoped to a subtree.

Revision ID: 0006_job_owning_unit
Revises: 0005_command_payload
Create Date: 2026-08-26

Four routes act on a job — status, the SSE event stream, re-drive and abandon —
and none of them could be scoped to a part of the organization, because ``job``
had no owning unit to scope to. Authorization was therefore
actor-or-oversight-role *within the tenant*: a coordinator in one department
could read, re-drive and abandon another department's work, and the two routers
said so in their own docstrings rather than papering over it. That is backlog
**A5**.

The hole was missing data, not a missing rule, and
``tests/authz/test_policy_matrix.py`` measured that rather than asserting it: the
same sibling-department coordinator, evaluated by ``smartmatch_authz.evaluate``
against a resource that *does* carry an owning unit, is refused. So this revision
adds the column, and the routers stop reimplementing a role check the policy
already performs.

The composite reference is the point
------------------------------------
::

    FOREIGN KEY (tenant_id, owning_unit_id) REFERENCES org_unit (tenant_id, id)

**not** ``owning_unit_id REFERENCES org_unit (id)``. The two look identical in a
schema diagram and differ in exactly the guarantee this column exists to
provide: the single-column form would accept a job in one tenant naming a unit in
another, after which every authorization decision about that job would be made
against a path in a tree the caller has no relationship to — a cross-tenant
disclosure produced by the fix for a cross-department one.

``org_unit`` already carries ``uq_org_unit_tenant_id`` on ``(tenant_id, id)``,
added by ``0001`` for precisely this: a composite foreign key needs a unique
constraint on the columns it references, and a primary key on ``id`` alone will
not serve. Every other tenant-owned reference in this schema is built the same
way (``membership``, ``resource_grant``, ``job_event``, ``outbox_record``), and
``test_schema_matches_migration.py::test_every_tenant_scoped_table_is_anchored_by_a_composite_key``
enumerates them **from the database** so a simplification here fails even if the
mirror is simplified to match.

``ON DELETE RESTRICT``, not ``CASCADE``
---------------------------------------
The same intent ``tenant`` uses, for a stronger reason. A unit is reorganized —
merged, renamed, moved — far more often than a tenant is deleted, and ``CASCADE``
would make one such reorganization silently delete the audit trail of every
command ever submitted into that unit, including the ``redrive_record`` rows that
say who decided to re-run failed work and why. ``RESTRICT`` makes the
reorganization refuse until someone has decided where the jobs go, which is a
decision a person should take rather than a delete should imply.

Single-phase, and why that is correct *here*
--------------------------------------------
This revision adds the column, backfills it, and makes it ``NOT NULL`` in one
transaction. That is not the expand/migrate/contract shape ``0003`` and ``0005``
follow, and the difference is deliberate rather than an oversight.

Expand/migrate/contract exists to keep two releases running against one database
during a rolling deploy. **There is no production data and no rolling
deployment**: nothing is deployed, no instance is serving traffic against this
database, and no account provisioning path exists. Splitting this into an expand
revision now and a contract revision later would therefore buy nothing and cost
something real — a window in which ``job.owning_unit_id`` is nullable, during
which :mod:`smartmatch_api.job_authz` has to answer "what does an unscoped job
mean" for rows that will never exist. A nullable authorization input is a
fail-open shape waiting to be written, and the column being ``NOT NULL`` from the
moment it exists is what lets the authorizer treat a missing path as a defect
rather than as a case.

The rollout ordering is the one ``0004`` and ``0005`` recorded and is unchanged:
``schema.py`` is a whole-table mirror and ``JobRepository.get`` names every column
it declares, so **this migration must be applied before the new release starts**.
Old-code-on-new-schema is *not* safe here, and that is what single-phase costs,
stated rather than implied: the old release inserts jobs without this column, and
the ``NOT NULL`` refuses them. With nothing deployed that population is empty;
the day it is not, a change of this shape has to be split.

Whoever first runs this against a live system should also reconsider the lock.
``ALTER TABLE ... ADD COLUMN`` with no default is a catalog change PostgreSQL 16
does not rewrite the table for, but ``SET NOT NULL`` scans the whole table and the
``ADD CONSTRAINT`` validates it, both under ``ACCESS EXCLUSIVE`` held until this
revision commits (ADR-0009, ``transaction_per_migration=True``). At pilot size
that is milliseconds. Against a large ``job`` table the form to use is
``ADD CONSTRAINT ... NOT VALID`` followed by ``VALIDATE CONSTRAINT`` in a separate
transaction, and a ``CHECK (owning_unit_id IS NOT NULL) NOT VALID`` promoted the
same way — both of which need ``op.get_context().autocommit_block()`` and bring
the obligations ``0003`` enumerates.

The backfill refuses rather than repairs
----------------------------------------
``import.create`` is the only command wired end to end, and ``0005`` gave it a
``payload`` carrying the ``unit_id`` the route authorized. That is the only place
a pre-existing job's owning unit can come from, so the backfill resolves
``payload->>'unit_id'`` against ``org_unit`` **joined on both ``tenant_id`` and
``id``** — the same tenant-safe join the new constraint enforces, so the backfill
cannot write a value the constraint would then reject with a less useful message.

Any row the backfill cannot resolve stops the migration, with the count and the
rows named. It deliberately does not default, drop, or guess, and the reasons are
the ones ``0003`` gives for refusing duplicate subjects rather than merging them:

* **There is no defensible default.** "The tenant's root unit" would grant every
  coordinator in the tenant access to work they previously reached only through
  the hole this migration closes — the fix would preserve the defect in the data
  while claiming to have fixed it in the schema.
* **Deleting the rows destroys an audit trail** to make a constraint apply, at
  deploy time, with nobody watching.
* **Letting the ``SET NOT NULL`` raise on its own** reports one row and leaves an
  operator unable to tell whether the fix is one job or nine hundred — the same
  smaller reason ``0003`` gives for checking before the ``ALTER``.

The three ways a row fails to resolve are different problems and the message says
which: a payload naming a unit that does not exist *in that job's tenant*, a job
written before ``0005`` whose parameters are unrecoverable, and a command type
that never carried a unit. The last is what every future command resource looks
like on the day it first ships, which is why the error names the command type
rather than only the id.

The check needs a live connection, so it cannot run in Alembic's offline
(``--sql``) mode; the generated script carries the backfill and the constraints
but not the guard, exactly as ``0003``'s does. The ``NOT NULL`` still refuses the
bad state — what is lost is the readable message, not the protection.

No index, deliberately
----------------------
Nothing queries jobs *by* owning unit yet. The authorizer reaches a job by primary
key and joins the unit in to read its path, which uses ``org_unit``'s own primary
key. A per-unit job listing would want an index on ``(tenant_id,
owning_unit_id)``; it does not exist, so neither does the index. Adding one to
serve a query nobody issues would cost every command submission a write.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision = "0006_job_owning_unit"
down_revision = "0005_command_payload"
branch_labels = None
depends_on = None

#: The command whose payload records the unit the route authorized. The only
#: source a pre-existing job's owning unit can come from; every other command
#: type is reported as unresolvable rather than guessed at.
_BACKFILL_COMMAND_TYPE = "import.create"

#: How many unresolved rows the error names before it stops. A table that has been
#: accumulating jobs could have thousands, and an error that prints all of them is
#: one an operator scrolls past rather than reads. The total is always reported,
#: so the cap hides detail and never hides scale — the same rule ``0003`` applies
#: to duplicate subjects.
_MAX_REPORTED_ROWS = 20

#: Matches a canonical UUID rendering, applied *before* the cast so a payload
#: carrying ``"unit_id": "not-a-uuid"`` is reported as one unresolved row rather
#: than aborting the whole statement with an unreadable ``invalid input syntax``
#: from the cast. Both cases are accepted because nothing normalizes what a
#: payload was written with.
_UUID_TEXT = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"

#: Resolve each import job's owning unit and write it.
#:
#: The CTE is ``MATERIALIZED`` on purpose. Inlined, PostgreSQL is free to push the
#: cast in the select list past the ``WHERE`` that guards it, and a single
#: malformed ``unit_id`` anywhere in the table would then fail the whole statement
#: with a cast error instead of being reported as one unresolved row.
#: ``MATERIALIZED`` evaluates the CTE to completion first, and within it a row's
#: qualifiers are applied before its target list is computed.
#:
#: The join carries ``tenant_id`` as well as ``id``, which is the same rule the
#: constraint below enforces. Without it the backfill would happily resolve a
#: payload naming another tenant's unit, and the ``ADD CONSTRAINT`` would then
#: reject the row it had just written — reporting a foreign-key violation instead
#: of the specific "this unit is not in this job's tenant" the guard reports.
_BACKFILL = sa.text(
    """
    WITH candidate AS MATERIALIZED (
        SELECT j.id AS job_id,
               j.tenant_id AS tenant_id,
               CAST(j.payload ->> 'unit_id' AS uuid) AS unit_id
        FROM job j
        WHERE j.command_type = :command_type
          AND jsonb_typeof(j.payload) = 'object'
          AND j.payload ->> 'unit_id' ~ :uuid_pattern
    )
    UPDATE job
    SET owning_unit_id = u.id
    FROM candidate c
    JOIN org_unit u
      ON u.tenant_id = c.tenant_id
     AND u.id = c.unit_id
    WHERE job.id = c.job_id
    """
)

#: Everything the backfill could not resolve, with enough context to act on.
#: ``payload ->> 'unit_id'`` is reported as-is — including ``NULL`` — because "the
#: payload named a unit that is not in this tenant" and "the payload named
#: nothing" are different problems with different fixes.
_UNRESOLVED = sa.text(
    """
    SELECT id, command_type, payload ->> 'unit_id' AS payload_unit_id
    FROM job
    WHERE owning_unit_id IS NULL
    ORDER BY command_type, id
    """
)


def _refuse_unresolved_jobs(bind: sa.Connection) -> None:
    """Raise if any job row still has no owning unit after the backfill.

    Separated from :func:`upgrade` so it reads as what it is — a precondition with
    an explanation attached — and so a test can run the real check against a
    database holding real unresolvable rows instead of asserting against a copy of
    the query.

    Raises:
        RuntimeError: naming the total and the rows. ``RuntimeError`` rather than
            a database exception because nothing here should be caught and
            retried: the migration is stopping to ask a question that only a human
            who knows what those jobs were for can answer.
    """
    unresolved = bind.execute(_UNRESOLVED).all()
    if not unresolved:
        return

    shown = unresolved[:_MAX_REPORTED_ROWS]
    listing = "\n".join(
        f"  {row.id}  command_type={row.command_type}  payload.unit_id={row.payload_unit_id!r}"
        for row in shown
    )
    elided = len(unresolved) - len(shown)
    if elided:
        listing += f"\n  ... and {elided} more row(s) not listed"

    raise RuntimeError(
        f"Cannot make job.owning_unit_id NOT NULL: {len(unresolved)} job row(s) "
        f"have no resolvable owning organizational unit.\n"
        f"{listing}\n"
        f"Each row is one of three situations, and the fix differs. Its "
        f"payload.unit_id names a unit that does not exist **in that job's "
        f"tenant** — a cross-tenant reference, which is exactly what the new "
        f"composite foreign key forbids, and which must be corrected rather than "
        f"imported. Or the job predates migration 0005 and carries no payload at "
        f"all, so its parameters are unrecoverable (the idempotency fingerprint is "
        f"a one-way hash) and the row can only be assigned a unit by someone who "
        f"knows what it was for. Or its command_type is not "
        f"{_BACKFILL_COMMAND_TYPE!r} and therefore never recorded a unit, which "
        f"means a command resource shipped without one and its submission path has "
        f"to start persisting the unit it authorizes against before this migration "
        f"can run.\n"
        f"This migration will not default, drop, or guess: assigning these rows a "
        f"root unit would grant every coordinator in the tenant access to work "
        f"they could previously reach only through the very hole this migration "
        f"closes. Resolve every row listed above, then run it again."
    )


def upgrade() -> None:
    """Add the column, backfill it, constrain it, and require it — in one transaction."""
    op.add_column(
        "job",
        sa.Column("owning_unit_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    if context.is_offline_mode():
        # The unresolved-row check reads the table, which offline mode has no
        # connection to. Say so in the emitted script rather than silently
        # generating SQL that looks like it carries the same guard.
        op.execute(
            "-- 0006: the unresolved-job check requires a live connection and was "
            "not run.\n"
            "-- After the backfill below, and before the SET NOT NULL, run:\n"
            "--   SELECT id, command_type, payload ->> 'unit_id'\n"
            "--   FROM job WHERE owning_unit_id IS NULL;\n"
            "-- and resolve every row it returns. The SET NOT NULL will otherwise\n"
            "-- fail with a message naming one row and not the scale."
        )
        op.execute(
            _BACKFILL.bindparams(command_type=_BACKFILL_COMMAND_TYPE, uuid_pattern=_UUID_TEXT)
        )
    else:
        bind = op.get_bind()
        bind.execute(
            _BACKFILL,
            {"command_type": _BACKFILL_COMMAND_TYPE, "uuid_pattern": _UUID_TEXT},
        )
        _refuse_unresolved_jobs(bind)

    # After the backfill and its guard: a constraint added first would refuse the
    # UPDATE's own rows one at a time and report a foreign-key violation instead
    # of the specific diagnosis above.
    op.create_foreign_key(
        "fk_job_owning_unit",
        "job",
        "org_unit",
        ["tenant_id", "owning_unit_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.alter_column("job", "owning_unit_id", nullable=False)


def downgrade() -> None:
    """Drop the column, and the constraint with it.

    A development tool. Production rollback never depends on it (v1.1 §4.2): the
    destructive step of expand → migrate → contract runs only after a release is
    fully promoted.

    Reversing this **reopens A5**. Every job becomes unscopeable again, and the
    authorizer that reads ``owning_unit_path`` finds nothing to read — which it
    treats as a denial rather than as permission, so the failure direction is
    closed rather than open. It also discards which unit each job belonged to; the
    payload of an ``import.create`` job still names it and a re-upgrade re-derives
    it, but a job of any other command type loses the association for good.

    The foreign key is dropped explicitly rather than left to fall with the
    column. ``DROP COLUMN`` does remove a constraint that depends on it, but this
    one names two columns and reading ``op.drop_column`` alone would leave a
    reasonable person wondering what happens to ``tenant_id``.
    """
    op.drop_constraint("fk_job_owning_unit", "job", type_="foreignkey")
    op.drop_column("job", "owning_unit_id")
