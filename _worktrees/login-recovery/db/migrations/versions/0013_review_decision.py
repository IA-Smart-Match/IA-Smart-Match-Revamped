"""A decision on ``review_item`` cites who made it and when.

Revision ID: 0013_review_decision
Revises: 0012_professional_unit_rel
Create Date: 2026-09-02

``review_item.status`` (migration ``0008``) has carried ``pending`` /
``accepted`` / ``rejected`` since it was created, and until this migration
nothing in the API ever wrote the second or third value: an import produces
``pending`` rows and the metric built on them, ``pending_review_items``, could
only ever climb. This migration is the storage half of closing that — the API
half is the new ``POST /v1/review-items/{id}/decision`` route
(``services/api/smartmatch_api/routers/review.py``), which this migration's two
new columns exist to be written by.

Why a decision needs a citation, not just a new status value
--------------------------------------------------------------
A ``status`` column that moves from ``pending`` to ``accepted`` records *that*
something changed. It does not record *who* changed it or *when* — and a
coordinator's decision is exactly the kind of claim this codebase has already
decided must never stand unaccompanied. ``pipeline_record``'s
``attended_attendance_id`` (migration ``0011``) makes the same argument for a
different claim: "attendance is cited, never asserted", because a claim citing
nothing is the fabricated-field defect Fix #15 / H21 names — a value in a
column with nothing behind it, indistinguishable from one a human actually
attests to. A review decision is that same shape one table over: ``accepted``
with no ``decided_by`` and no ``decided_at`` is a status a reviewer minute-book
cannot corroborate, so the same biconditional evidence idiom applies again
here, on the same two axes redrive already uses for its own authorship
(``ck_redrive_authorship_complete``, migration ``0001``) and spend uses for its
lease (``ck_spend_reservation_lease_token_iff_reserved``, migration ``0010``).

The columns
-----------
``decided_at timestamptz NULL`` — when the decision was made. ``NULL`` while
``pending``, set once and never again: nothing in this codebase re-decides a
review item, and ``ReviewRepository``'s conditional ``UPDATE ... WHERE status
= 'pending'`` (the same idiom ``0008``'s own docstring already proposed for
this column, under "no version column") is what makes a second decision
structurally unable to overwrite the first rather than merely unlikely to.

``decided_by uuid NULL``, composite FK ``(tenant_id, decided_by) ->
user_account (tenant_id, id)``, ``ON DELETE RESTRICT`` — who decided. Composite
rather than a bare id, for the reason every tenant-scoped reference in this
schema is composite (ADR-0004, v1.1 §2.2): a bare ``user_account.id`` foreign
key would accept a decision naming an account row that belongs to a *different*
tenant, and every audit query that trusts ``decided_by`` to mean "a coordinator
in this tenant decided this" would be trusting a fact the schema never actually
enforced. ``RESTRICT``, not ``CASCADE`` and not ``SET NULL``: deleting the
``user_account`` row behind a recorded decision must not silently turn a cited
decision back into an uncited one — that would be manufacturing exactly the
fabricated-field state the CHECK below exists to make unstorable. Nothing in
this codebase deletes a ``user_account`` row today (no route exists), so this
is a guarantee for whenever one does, not a constraint anything currently
exercises.

``ck_review_item_decision_evidence``
-------------------------------------
Two biconditionals, ANDed rather than chained as one three-way comparison:

* ``(status = 'pending') = (decided_at IS NULL)`` — a row is pending exactly
  when it carries no decision timestamp. This is what stops a coordinator's
  ``UPDATE ... SET status = 'accepted'`` from ever landing without also
  setting ``decided_at`` in the same statement, and equally stops a stray
  ``UPDATE ... SET decided_at = now()`` against a still-``pending`` row.
* ``(decided_at IS NULL) = (decided_by IS NULL)`` — the same biconditional
  ``ck_redrive_authorship_complete`` already states for ``redriven_at`` /
  ``redriven_by``: a timestamp with no author, or an author with no timestamp,
  is a half-written fact.

A chained ``(status = 'pending') = (decided_at IS NULL) = (decided_by IS
NULL)`` would parse, but would not say what it looks like it says: SQL's ``=``
is left-associative and boolean-typed, so the middle comparison's *result* — a
boolean — would be compared against ``(decided_by IS NULL)`` rather than every
pair being checked against every other pair. Writing the two independent
biconditionals and ``AND``-ing them, as
``ck_spend_reservation_lease_token_iff_reserved`` already does for its own
two-column version of this idiom, says exactly what is meant: both facts must
agree with each other, not that a chain of comparisons happens to reduce to
``TRUE``.

No backfill needed
-------------------
Every existing ``review_item`` row is ``pending`` (migration ``0008``'s
``server_default``, and nothing before this migration ever wrote a different
value), and a ``pending`` row satisfies the CHECK with both new columns left at
their default ``NULL`` — so the constraint is satisfiable the moment the
columns exist, with no ``UPDATE`` pass over existing data and no window where
the table is briefly inconsistent. This is ``0011``'s shape, not ``0006``'s:
one transaction, no expand/contract split, because there is nothing to migrate
forward.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013_review_decision"
down_revision = "0012_professional_unit_rel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add ``decided_at``, ``decided_by`` and their evidence CHECK to ``review_item``."""
    op.add_column(
        "review_item",
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "review_item",
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_review_item_decided_by",
        "review_item",
        "user_account",
        ["tenant_id", "decided_by"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_review_item_decision_evidence",
        "review_item",
        "(status = 'pending') = (decided_at IS NULL) "
        "AND (decided_at IS NULL) = (decided_by IS NULL)",
    )


def downgrade() -> None:
    """Drop the CHECK, the foreign key, and the two columns.

    A development tool, not a production rollback path (v1.1 §4.2). The CHECK
    is dropped first because it references both new columns; the foreign key
    by the explicit name ``upgrade`` gave it; the columns last, taking
    whatever remains on them with them.
    """
    op.drop_constraint("ck_review_item_decision_evidence", "review_item", type_="check")
    op.drop_constraint("fk_review_item_decided_by", "review_item", type_="foreignkey")
    op.drop_column("review_item", "decided_by")
    op.drop_column("review_item", "decided_at")
