"""Drop the tenant-scoped subject constraint the global one made redundant.

Revision ID: 0007_drop_tenant_subject
Revises: 0006_job_owning_unit
Create Date: 2026-08-26

``user_account`` has carried two uniqueness constraints on ``external_subject``
since ``0003``:

* ``uq_user_account_tenant_subject`` — ``(tenant_id, external_subject)``, from
  ``0001``. One account per subject *per tenant*, which says nothing about two
  tenants.
* ``uq_user_account_external_subject`` — ``(external_subject)``, from ``0003``.
  Globally unique, which is what makes ``PrincipalRepository.load_by_subject``'s
  ``.one_or_none()`` sound rather than merely defended (ADR-0008).

The second **strictly implies** the first. If a subject appears at most once in
the whole table, it appears at most once per tenant; there is no state the older
constraint forbids that the newer one permits. So it enforces nothing, and costs
a unique index maintained on every ``user_account`` insert and update.

``0003`` said all of that and kept it anyway, in a section headed
"``uq_user_account_tenant_subject`` is kept": dropping it is a **contract-phase**
action under v1.1 §4.2, and ``0003`` was itself the expand phase. A release
rolled back after ``0003`` ran must still find the schema it was built against,
and nothing in the old release breaks because a redundant constraint is present
while something could break because it is suddenly absent. This revision is that
contract phase, tracked as backlog **F12**, and it runs now for the reason
``0003`` named as the precondition: nothing is deployed, no release is
mid-promotion, and no code path anywhere inserts a ``user_account``.

What this does *not* do, stated because it is the whole risk
-------------------------------------------------------------
It does not touch ``uq_user_account_external_subject``. That constraint is the
one carrying a guarantee, and "drop the redundant constraint" and "drop the
constraint that matters" are one identifier apart in a file like this one.

Dropping the wrong one would restore, silently and with a green schema, the
defect ``0003`` exists to fix: one identity-provider subject with accounts in two
tenants, ``load_by_subject`` matching two rows, ``MultipleResultsFound``, and an
unhandled 500 on *every* authenticated request by that person — not a denial, not
a wrong-tenant answer. The catalog would look busier afterwards, not emptier,
because the constraint left standing would be the one whose name mentions
tenants.

Nothing in a migration can protect against that, so the protection is in the
tests and is behavioural rather than structural.
``test_principal_identity.py::test_one_subject_cannot_hold_accounts_in_two_tenants``
attempts the forbidden insert and requires the refusal to name
``uq_user_account_external_subject``;
``::test_one_subject_cannot_be_reused_inside_a_tenant`` does the same for the
within-tenant duplicate, which is the case that used to be answered by the
constraint this revision removes and must now be answered by the survivor. A swap
fails both. ``::test_the_migration_drops_exactly_one_constraint`` runs this
revision against a scratch database and asserts the set difference, so a revision
that dropped this constraint *and* something else fails too.

The lock, and why there is no guard
------------------------------------
``ALTER TABLE ... DROP CONSTRAINT`` takes ``ACCESS EXCLUSIVE`` on
``user_account`` and drops the backing index. Unlike ``0003``'s ``ADD
CONSTRAINT`` there is no index to build, so the lock is held for a catalog update
and not for a scan — microseconds at any table size. Per ADR-0009 and
``transaction_per_migration=True`` in ``db/migrations/env.py`` it is held until
*this revision* commits, which with one statement is the statement's own
duration.

``0003`` opened with an explicit ``LOCK TABLE`` ahead of a duplicate check, to
close the window between reading the table and constraining it. There is no
equivalent here and none is needed: this revision asks the table no questions.
Removing a constraint cannot fail on data, so there is no precondition to verify
and nothing a concurrent insert could slip past. It runs identically in offline
(``--sql``) mode for the same reason.
"""

from __future__ import annotations

from alembic import op

revision = "0007_drop_tenant_subject"
down_revision = "0006_job_owning_unit"
branch_labels = None
depends_on = None

#: The redundant constraint this revision removes. A constant so that the
#: ``upgrade`` and the ``downgrade`` cannot come to name different constraints.
_REDUNDANT = "uq_user_account_tenant_subject"


def upgrade() -> None:
    """Drop the redundant constraint. Nothing else."""
    op.drop_constraint(_REDUNDANT, "user_account", type_="unique")


def downgrade() -> None:
    """Recreate the constraint, restoring the schema ``0006`` produced.

    Usable on a development database, and on this revision the reversal is
    genuinely total: the constraint is implied by
    ``uq_user_account_external_subject``, which was never touched, so no row can
    exist that would refuse to be reconstrained. That is unusual — ``0003``'s and
    ``0006``'s downgrades both return the schema without returning the
    correctness — and it is a consequence of this revision removing something
    that enforced nothing.

    Restoring it takes ``ACCESS EXCLUSIVE`` and builds the unique index that was
    dropped, so unlike the upgrade this one *does* scan. The remarks in ``0003``
    about ``CREATE UNIQUE INDEX CONCURRENTLY`` and the ``autocommit_block`` it
    requires apply here in full, should this ever be reversed against a large
    ``user_account``.
    """
    op.create_unique_constraint(_REDUNDANT, "user_account", ["tenant_id", "external_subject"])
