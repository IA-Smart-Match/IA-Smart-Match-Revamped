"""``match_run.scoring_mode`` — the mode a run was scored under, in a column.

Revision ID: 0032_match_run_scoring_mode
Revises: 0031_student_speaker_feedback
Create Date: 2026-09-06

**OQ-CBA-028**, closed 6 September 2026 by Danny Tran, program owner of record.
This revision is that decision and nothing beyond it.

ADR-0016 Proposal 9 requires a run to record which of the registry's models
produced it, and ``MatchRunPins`` has carried ``scoring_mode`` since
``CBA-MATCH-REGISTRY``. That card added no DDL, so the mode reached durable
storage three ways and none of them was a column: the job summary event, the
stored explanation payload (``explanation_to_payload`` writes ``scoring_mode``
and ``scoring_mode_version`` on every candidate), and ``registry_hash``, which
differs between the two modes by construction because they apply different
weight sets.

That is enough to make every run **recoverable**. It was never enough to make
one **queryable**: "how many virtual runs did we score in March" is a JSON walk
across a second table's payload, and a mode-based filter, aggregate or index is
not writable at all. This revision moves the mode onto the row so it is both.

NULL is a fact, not a gap
==========================
Both columns are **nullable**, and a pre-ADR-0016 run stays NULL. That is the
true statement about such a run: it predates the mode vocabulary and was scored
under ``SUPERSEDED_G1_MODEL``, whose ``scoring_mode`` is ``None`` in the domain
for exactly this reason. ``MatchRunPins``' docstring says it in the sharpest
form available — reading such a run as ``cba-physical-1`` "would claim a
proximity factor was scored under a rulebook that had no modes at all".

The rejected alternative was a ``NOT NULL`` column carrying a sentinel such as
``legacy-pre-adr-0016`` on the historical rows. It was rejected on the ground
that settles it: **ADR-0016 Proposal 5 closes the mode vocabulary**, minting a
third value here would reopen it in DDL rather than in the ADR, and every
reader of ``scoring_mode`` — ``resolve_scoring_model`` first among them — would
then have to know about a mode that names no model. ADR-0011's "unknown is not
zero" is the same argument one level up: an absent measurement is recorded as
absent, never as a plausible-looking value nobody chose.

``ck_match_run_pins_present`` is deliberately not widened
===========================================================
That constraint requires eight fields to be non-blank, and adding
``scoring_mode`` to it would put **every row already stored** into violation the
moment this revision ran — an expand-only migration that cannot be applied to a
populated database. The new ``ck_match_run_scoring_mode`` is therefore
**partial**: it constrains the value only when there is one, and says nothing at
all about a run that has none. The two constraints are about different things
and stay apart: the old one is "a pin that was required was recorded", the new
one is "a mode that was recorded is a real mode".

The pairing rule — a mode and its version are set together or neither is — is
**not** a CHECK here. It is enforced in
:meth:`smartmatch_domain.match_run.MatchRunPins.__post_init__`, at the point a
caller assembles the pins, which is where a caller can be told which half it
left out. Duplicating it in DDL is outside what OQ-CBA-028 approved, and the
column that would carry the risk — a stored mode with no version — is
unreachable from the one writer this table has.

Why the vocabulary is transcribed rather than imported
=======================================================
``smartmatch_domain.factors.proximity.CBA_SCORING_MODES`` is the single copy
application code reads. The two literals below are a second copy, for the reason
``0023``, ``0024`` and ``0028`` each gave for theirs: a CHECK cannot import
Python, and a migration describes the database as of the moment it ran, so an
import would let a later edit to the domain silently change what this historical
revision meant. The divergence that risks is caught behaviourally rather than by
discipline — ``tests/integration/test_match_run_snapshot.py`` parametrizes over
``CBA_SCORING_MODES`` *from the domain module* and requires every released mode
to be storable, so a third mode added in Python without a migration fails there
rather than in a report.

There is no backfill, and that is the decision
===============================================
Every ``match_run`` row that existed before this revision keeps ``scoring_mode``
NULL. **A backfill was written, reviewed, and rejected on 6 September 2026 by
Danny Tran, program owner of record.** This section is the record of that, so a
later reader finds the decision rather than a silence where one would have been.

The backfill was possible. The mode of a pre-``0032`` run is recoverable from the
stored explanation payload — ``job.payload -> 'explanations'``, the array
``explanation_to_payload`` produced for the pool that was actually scored — and a
statement that copied it across where every entry agreed would have been correct
for the rows it touched.

What made it unaffordable was the one thing it required. ``0018`` installed
``match_run_is_immutable``, a ``BEFORE UPDATE`` trigger that raises on every
UPDATE, and a backfill is an UPDATE. Reaching those rows means switching that
trigger off — by name, by ``session_replication_role``, or by dropping and
recreating it — and all three have the same shape: a migration that turns off the
guarantee ``0018`` exists to provide.

That trigger is load-bearing. ``0018``'s docstring makes it a deliberate
exception to this codebase's argument against triggers, precisely because it is
what makes "a correction is a new run, never an UPDATE" true of a hand-written
statement in a psql session and not merely of a repository that declines to offer
an update method. A migration that switches it off, however briefly and however
well-argued in its own docstring, is a **permanent precedent**: the next revision
that wants to "just fix these few rows" would cite this one, and it would be
citing it correctly. The cost is paid once here and collected forever after.

Against that, the gain is small, and it is small because **nothing is lost**. The
mode of a pre-``0032`` run stays exactly as recoverable as it is today, through
the same three routes OQ-CBA-028 catalogued: the job summary event, the stored
explanation payload, and ``registry_hash``, which differs between the two modes
by construction. The explanation payload remains the system of record for those
runs. What this revision buys is that **every run from now on is queryable**, and
that is the whole of what the card asked for; retrofitting the runs that came
before it was never the requirement.

And NULL on those rows is not a gap to be filled — it is the honest reading. A
run recorded before ADR-0016 has no mode, so a NULL is the true statement about
it whether or not anyone ever looks the mode up elsewhere. A backfilled value
would have been a *reconstruction* presented in the same column, and
indistinguishable from a mode the run itself recorded.

If a report one day genuinely needs the historical rows labelled, the honest
instrument is a read-side view or a report-time join against the payload — not a
rewrite of immutable rows, and not this migration.

``registry_hash`` would not have been an acceptable source in any case, even
though it does distinguish the two modes. It distinguishes them only by being
different from each other, and mapping a digest back to the mode that produced it
means recomputing today's weight sets and hoping the unit had no overrides — a
reconstruction that is silently wrong for any unit that did (migration ``0027``).

Expand only
=============
Two nullable columns, one partial CHECK over one of them, and one partial index.
**No UPDATE, no DML of any kind, and no trigger is created, dropped, disabled or
enabled.** Nothing is dropped, renamed or narrowed, and no existing constraint is
widened, so the previous release runs unchanged against this schema (v1.1 §4.2,
ADR-0009): it neither writes these columns nor reads them. On a populated
database this revision is three catalog changes and touches no row.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032_match_run_scoring_mode"
down_revision = "0031_student_speaker_feedback"
branch_labels = None
depends_on = None


#: ADR-0016 Proposal 5's closed vocabulary, transcribed. See the module
#: docstring for why these are literals here and not an import, and for what
#: catches the two copies drifting apart.
_SCORING_MODES = ("cba-physical-1", "cba-virtual-1")

#: Partial by construction: it says what a recorded mode may be, and nothing
#: about a run that recorded none. That ``IS NULL`` arm is what lets this
#: constraint be added to a populated table at all — every row stored before this
#: revision satisfies it, and none is rewritten to make that true. Widening
#: ``ck_match_run_pins_present`` to cover this column instead would have put every
#: one of them in violation, which is why that constraint is untouched.
#:
#: The one place the vocabulary is rendered into SQL. It had a second consumer
#: while this revision carried a backfill; the backfill was rejected (see the
#: module docstring) and the constant went with it, so there is now exactly one
#: statement in this file that can disagree with ``CBA_SCORING_MODES``.
_SCORING_MODE_IS_KNOWN = (
    "scoring_mode IS NULL OR scoring_mode IN ('" + "','".join(_SCORING_MODES) + "')"
)


def upgrade() -> None:
    """Add the two mode columns and constrain them. No row is written.

    Adding a nullable column with no default is a catalog change in PostgreSQL,
    so this does not rewrite the table and does not fire ``match_run``'s
    ``BEFORE UPDATE`` trigger. That is not a happy accident — it is why this
    revision can leave the trigger completely alone. See the module docstring on
    why the backfill that would have needed it was rejected.
    """
    # Nullable, no server default. A default would put every existing row into a
    # mode nobody chose, which is the whole of what OQ-CBA-028 rejected. Every
    # row that exists when this runs keeps NULL, permanently and on purpose.
    op.add_column("match_run", sa.Column("scoring_mode", sa.Text, nullable=True))
    op.add_column("match_run", sa.Column("scoring_mode_version", sa.Text, nullable=True))

    # Adding this to a populated table is safe *because* nothing was backfilled:
    # the constraint's `scoring_mode IS NULL` arm is satisfied by every existing
    # row without PostgreSQL having to read one, and a value it could refuse can
    # only arrive from a writer after this point.
    op.create_check_constraint(
        "ck_match_run_scoring_mode",
        "match_run",
        _SCORING_MODE_IS_KNOWN,
    )

    # The access path this card exists for: one unit's runs of one mode, newest
    # first. Partial on ``scoring_mode IS NOT NULL`` because the query the OQ
    # names — "how many virtual runs in March" — never asks for the unlabelled
    # rows, and an index that carried them would be larger for no reader.
    # Declared with the columns rather than left to whoever writes the first
    # report, for ``0018``'s stated reason about ``ix_match_run_unit_created``.
    op.create_index(
        "ix_match_run_scoring_mode",
        "match_run",
        ["tenant_id", "owning_unit_id", "scoring_mode", sa.text("created_at DESC")],
        postgresql_where=sa.text("scoring_mode IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop the index, the constraint, then the two columns.

    In reverse creation order. A development tool, not a production rollback
    path (v1.1 §4.2): running this discards every run's recorded mode from the
    row. It is not, however, a loss of the fact — the job summary event and the
    stored explanation payload still say what each run was scored under, which
    is precisely the state OQ-CBA-028 described before this revision.

    Symmetric with ``upgrade`` in the way that matters here: dropping a column
    writes no row either, so a rollback does not touch ``match_run_is_immutable``
    any more than the upgrade did.
    """
    op.drop_index("ix_match_run_scoring_mode", table_name="match_run")
    op.drop_constraint("ck_match_run_scoring_mode", "match_run", type_="check")
    op.drop_column("match_run", "scoring_mode_version")
    op.drop_column("match_run", "scoring_mode")
