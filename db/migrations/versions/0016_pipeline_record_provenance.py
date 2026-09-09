"""``pipeline_record.matched_provenance`` — a match asserts where it came from.

Revision ID: 0016_pipeline_provenance
Revises: 0015_remove_ledger_reversal
Create Date: 2026-09-03

``pipeline_record.matched_at`` (migration ``0011``) is ``NOT NULL`` with the
comment "a record exists because a match does": the row's whole reason for
existing is the claim that a match happened. Until this migration, that claim
carried no source. `docs/plans/2026-09-03-pipeline-synthetic-caller-plan.md`
authorizes a coordinator's synthetic review-accept to write a
``pipeline_record`` row for a stakeholder demo — the same table, the same
``matched_at`` claim, but with no matching engine anywhere in the path that
produced it. Once a real matching engine lands beside this table
(``pilot/match-engine-m2-m7``, PR #12, M8) and writes rows of its own, nothing
would tell the two apart: both would carry a ``matched_at`` timestamp, both
would satisfy every constraint ``0011`` added, and both would be retained for
one year under the D5 retention table. A synthetic row that asserts a match
occurred with nothing recording that the "match" was a coordinator accepting a
seed row is exactly the fabricated-field shape (Fix #15, H21) this schema
refuses everywhere else — a value with nothing behind it, indistinguishable
from one a real event produced. And it cannot be discharged by a log line: a
log rotates away, while this table is the year-long evidence itself.
``matched_provenance`` is the column that makes the claim answerable instead of
assumed.

The vocabulary is closed, and these are its only two members
----------------------------------------------------------------
``ck_pipeline_record_matched_provenance`` admits exactly two values:

* ``'synthetic / coordinator-accepted'`` — a coordinator accepted a synthetic,
  in-list opportunity row in the pilot appliance. No matching engine ran;
  ``matched_at`` is the moment of that acceptance and asserts nothing about
  fit.
* ``'match-engine'`` — the row was produced by the real matching engine (G1 /
  M1-M10). This is a **reserved slot**: nothing in this repository writes it
  today, and this migration does not wire anything to write it. It exists now
  so the engine branch needs no migration of its own to become storable, and
  reserving the slot is not the same as depending on that branch.

Why the first value is spelled with a space and a slash, not a tidy
``snake_case`` token: it is the one string the program owner directed, the one
string ``smartmatch_persistence.pipeline.MATCH_PROVENANCE_SYNTHETIC_COORDINATOR``
carries, and the one string the provisioning service's structured log line
emits. A second, tidier spelling for the database would be a second source of
truth for the same fact — the defect ADR-0011 rule 4 already names, one column
over.

**Adding a member later is a new revision, never an edit to this file.** A
CHECK constraint edited in place changes, retroactively, what every row already
stored under it was validated against — a reader of migration history would no
longer be able to tell which rule a given row actually satisfied at write time.
Whichever revision needs a third value creates its own ``ALTER TABLE ... DROP
CONSTRAINT`` / ``ADD CONSTRAINT`` pair, exactly as this file does to ``0011``'s
table.

No server default, and why that is what makes the guarantee real
--------------------------------------------------------------------
``matched_provenance`` is ``NOT NULL`` with **no** ``server_default``, at any
point in this migration or afterwards. A default would let a future caller
insert a row and simply never mention provenance, and the column would then
mean nothing more than "a value happened to be here" — silently defeating the
one guarantee this migration exists to add. Instead, every path is closed by
construction: ``smartmatch_persistence.pipeline.PipelineRepository.record_matched``
takes ``matched_provenance`` as a required keyword argument with no default,
so no Python caller can omit it; and the database itself refuses any insert
that tries, so no caller reaching around the repository can omit it either.
There is no third path by which a row could exist without one.

Can a row already exist with no provenance to backfill? In principle, no:
``pipeline_record`` has never had a production caller (that absence is this
whole plan's premise — see ``smartmatch_persistence.pipeline``'s own module
docstring, "No production caller wires this module yet"), CI always builds a
fresh database, ``docker compose down -v`` discards the dev volume, and every
integration test that writes this table cleans its own rows up in an autouse
fixture. But "in principle no rows" is not a fact this migration is entitled to
assume about a developer's laptop that has been running longer than that
premise has been true, so ``upgrade()`` below is written as three statements
rather than one: add the column nullable, backfill any row already present to
``'synthetic / coordinator-accepted'``, then make it ``NOT NULL``. The backfill
is expected to touch **zero rows in every environment that matters** — and a
stray pre-existing row, if one is ever found, was by construction not
engine-produced, because no engine-writing code exists anywhere in this
repository yet, so backfilling it to the synthetic value is not a guess, it is
the only value that could possibly be true of it.

What this migration does not touch
-------------------------------------
One column and one CHECK constraint, nothing else on the table. Every
constraint ``0011`` added is untouched by this revision:
``ck_pipeline_record_stage_prefix``, ``ck_pipeline_record_stage_order``,
``ck_pipeline_record_attendance_evidence``, ``uq_pipeline_record_subject_opportunity``,
``pipeline_record_pkey``, and the three foreign keys to ``org_unit``,
``user_account`` and ``attendance_record``. None of them is weakened,
recreated, or renamed here — this migration only adds to the table, and
verifying that the other nine still hold after ``0016`` is part of this card's
own test suite (``tests/integration/test_pipeline_provenance_migration.py``).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_pipeline_provenance"
down_revision = "0015_remove_ledger_reversal"
branch_labels = None
depends_on = None

#: The one value any pre-existing row is backfilled to. Matches
#: ``smartmatch_persistence.pipeline.MATCH_PROVENANCE_SYNTHETIC_COORDINATOR``
#: character for character — see this module's docstring for why that string
#: is spelled with a space and a slash rather than as a tidier token.
_SYNTHETIC_PROVENANCE = "synthetic / coordinator-accepted"


def upgrade() -> None:
    """Add ``matched_provenance``, backfill it, then close both NOT NULL and the CHECK.

    Three statements plus the CHECK, in this order and no other, because each
    one depends on the state the one before it left behind: the column must
    exist before it can be backfilled, and it must be backfilled before it can
    be made ``NOT NULL``.
    """
    op.add_column(
        "pipeline_record",
        sa.Column("matched_provenance", sa.Text(), nullable=True),
    )
    # Expected to affect zero rows in every environment that matters: no
    # production caller has ever written this table (see this module's own
    # docstring), CI builds a fresh database, and `docker compose down -v`
    # discards the dev volume. A stray developer-laptop row, if one exists,
    # was by construction not engine-produced — no code path that writes
    # 'match-engine' exists anywhere in this repository yet — so this is the
    # only value that could truthfully describe it.
    op.execute(
        "UPDATE pipeline_record SET matched_provenance = "
        f"'{_SYNTHETIC_PROVENANCE}' WHERE matched_provenance IS NULL"
    )
    op.alter_column("pipeline_record", "matched_provenance", nullable=False)
    op.create_check_constraint(
        "ck_pipeline_record_matched_provenance",
        "pipeline_record",
        "matched_provenance IN ('synthetic / coordinator-accepted', 'match-engine')",
    )


def downgrade() -> None:
    """Drop the CHECK, then the column.

    A development tool, not a production rollback path (v1.1 §4.2). The CHECK
    is dropped first because it references the column; the column takes
    whatever provenance values were stored with it.
    """
    op.drop_constraint("ck_pipeline_record_matched_provenance", "pipeline_record", type_="check")
    op.drop_column("pipeline_record", "matched_provenance")
