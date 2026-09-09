"""``event.filed_by_user_id`` — who typed this request, in a column.

Revision ID: 0033_event_filed_by
Revises: 0032_match_run_scoring_mode
Create Date: 2026-09-07

**OQ-CBA-014**, closed 7 September 2026 by Danny Tran, program owner of record.
This revision is that decision's storage half and nothing beyond it.

Why a column was unavoidable
=============================
OQ-CBA-014 asked whether an Event Host may list back the Speaker Requests *they*
filed, and it named the schema question in the same breath: whether "filed by"
needs "a stored actor column the ``event`` table does not have today". It does
not have one. ``event`` carries ``host_org_unit_id``, ``origin``, the three
provenance columns and ADR-0010's temporal set, and no column naming an account;
``created_by``-shaped columns exist on ``job``, ``point_ledger_entry``,
``redemption``, ``review_item``, ``discovery_review_item``, ``outreach_draft``
and ``match_weight_setting_revision`` — never on ``event``.

So a host-scoped read could not be written before this revision, for the plain
reason that there was no stored fact to filter on. The alternative the register
pre-refused was to widen ``_SPEAKER_REQUEST_READ_ROLES`` instead: "do not widen
the list role set as a shortcut; a host-scoped read is a different query, not a
wider permit". That queue holds every host's request text for the unit, so
widening it would have handed one host the others' filings — which is why the
answer is a column and a second route rather than one more role in a set.

NULL is *unknown filer*, never *no filer*
==========================================
The column is **nullable**, every row that exists when this runs keeps NULL, and
**nothing is backfilled**. A Speaker Request filed before this revision has no
recorded filer, and NULL is the true statement about it.

The backfill that was available and rejected: write the unit's coordinator, or —
where a unit has exactly one ``volunteer`` — write that account. Both are
*reconstructions*, and once stored they are indistinguishable from a filer the
system actually recorded. ADR-0011 rule 1 is the same argument one level up, and
its subject here is an identity rather than a number: an unobserved fact is
recorded as absent, never as the plausible-looking value nobody chose. The
consequence is stated rather than smoothed over — **a host cannot list a request
they filed before this migration** — and it is asserted, on the row that could
have gone either way, in ``tests/integration/test_event_filed_by_migration.py``.

The read side must never soften that. A ``WHERE filed_by_user_id IS NULL OR ...``
clause, or a fallback to ``host_org_unit_id`` when the filer is unknown, would
republish the whole queue through the narrow route and undo the decision this
revision implements.

The two constraints
====================
``ck_event_filed_by_manual_origin`` — a filer may exist only on a
``coordinator_entry`` row. An extracted event has no author, and a filer on a
crawled row would attribute a fetch to a person. It is the mirror of
``ck_event_provenance_evidence``, which enforces the other direction: a source
URL may exist only on an ``extraction`` row. Partial by construction, so every
row already stored satisfies it without PostgreSQL reading one.

The **composite** foreign key ``(tenant_id, filed_by_user_id)`` referencing
``user_account (tenant_id, id)`` — the shape every account reference in this
schema uses (``attendance_record.subject_id`` is the standing example). A
single-column key would accept an account from another tenant: the row would
exist, it would simply be somebody else's. ``ON DELETE RESTRICT``, matching every
other account reference here, and with a cost worth naming: deleting an account
that has filed a request is now an error rather than a silent orphaning. That is
the same trade ``attendance_record`` already makes.

``ix_event_filed_by`` is the access path the new read issues and nothing else:
``(tenant_id, host_org_unit_id, filed_by_user_id)``, partial on
``filed_by_user_id IS NOT NULL`` because the query never asks for the
unattributed rows and an index carrying them would be larger for no reader.

Expand only
============
One nullable column, one partial CHECK, one composite foreign key over it, one
partial index. **No UPDATE and no DML of any kind.** Nothing is dropped, renamed
or narrowed, and no existing constraint is widened, so the previous release runs
unchanged against this schema (v1.1 §4.2, ADR-0009): it neither writes this
column nor reads it. Adding a nullable column with no default is a catalog change
in PostgreSQL, so on a populated database this revision rewrites no table and
touches no row.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0033_event_filed_by"
down_revision = "0032_match_run_scoring_mode"
branch_labels = None
depends_on = None


#: Partial by construction: it says where a filer may be recorded, and nothing
#: about a row that records none. The ``IS NULL`` arm is what lets this be added
#: to a populated table at all — every pre-``0033`` row satisfies it, and none is
#: rewritten to make that true. The origin vocabulary is transcribed rather than
#: imported for the reason ``0023``, ``0024``, ``0028`` and ``0032`` each gave for
#: theirs: a CHECK cannot import Python, and a migration describes the database as
#: of the moment it ran.
_FILER_ONLY_ON_A_TYPED_ROW = "filed_by_user_id IS NULL OR origin = 'coordinator_entry'"


def upgrade() -> None:
    """Add the column, constrain it, key it, and index it. No row is written."""
    # Nullable, no server default. A default would attribute every existing
    # request to somebody nobody chose, which is the whole of what this decision
    # rejects. Every row that exists when this runs keeps NULL, permanently.
    op.add_column(
        "event",
        sa.Column("filed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    op.create_check_constraint(
        "ck_event_filed_by_manual_origin",
        "event",
        _FILER_ONLY_ON_A_TYPED_ROW,
    )

    # Composite, against `uq_user_account_tenant_id`. A single-column key would
    # accept an account from another tenant — the account exists, it is simply
    # somebody else's — and tenant isolation in this schema is structural rather
    # than a predicate every reader has to remember.
    op.create_foreign_key(
        "fk_event_filed_by_user",
        "event",
        "user_account",
        ["tenant_id", "filed_by_user_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )

    # The exact predicate the host-scoped read issues: one unit, one filer,
    # inside one tenant. Declared with the column rather than left to whoever
    # writes the first slow query, for ``0018``'s stated reason about
    # ``ix_match_run_unit_created``.
    op.create_index(
        "ix_event_filed_by",
        "event",
        ["tenant_id", "host_org_unit_id", "filed_by_user_id"],
        postgresql_where=sa.text("filed_by_user_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop the index, the key, the constraint, then the column, in that order.

    A development tool, not a production rollback path (v1.1 §4.2): running this
    discards every recorded filer, and unlike ``0032``'s columns there is no
    second copy of the fact anywhere — no job payload, no explanation blob, no
    hash that distinguishes one filer from another. The state it returns to is
    exactly the one OQ-CBA-014 described before this revision: a host who can
    file and cannot list, because nothing says which requests are theirs.

    Symmetric with ``upgrade`` in the way that matters: dropping a column writes
    no row either.
    """
    op.drop_index("ix_event_filed_by", table_name="event")
    op.drop_constraint("fk_event_filed_by_user", "event", type_="foreignkey")
    op.drop_constraint("ck_event_filed_by_manual_origin", "event", type_="check")
    op.drop_column("event", "filed_by_user_id")
