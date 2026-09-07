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

The backfill, and why it disables a trigger
=============================================
``0018`` installed ``match_run_is_immutable``, a ``BEFORE UPDATE`` trigger that
raises on every UPDATE. A backfill is an UPDATE, so it would be refused —
correctly, because that trigger is what makes "a correction is a new run" true
of a psql session and not only of the repository. The backfill therefore
disables the trigger for the duration of one statement and re-enables it in the
same transaction, which is narrower than every alternative:

* ``session_replication_role = replica`` needs superuser and silences every
  trigger *and* every foreign key in the session, so a mistake in this
  statement would be uncheckable rather than merely wrong.
* Dropping and recreating the trigger would leave a window in which the table is
  mutable if this migration failed between the two statements.
* Leaving the historical rows unlabelled and backfilling from application code
  later would mean the column's meaning depended on whether that code had run.

Immutability is not being relaxed. The row's *recorded facts* do not change: the
backfill writes into two columns that did not exist a moment ago, copying a mode
the run already recorded elsewhere into the place it should always have been.
Nothing a coordinator was shown moves.

Where the backfill reads from, and when it declines
=====================================================
The stored explanation payload on the run's own job — ``job.payload ->
'explanations'``, the array ``explanation_to_payload`` produced for the pool that
was actually scored. It is used **only when the run's mode is unambiguous**:
exactly one distinct ``scoring_mode`` across the array, non-null, non-blank, and
a member of the closed vocabulary, with exactly one distinct
``scoring_mode_version`` beside it. Anything else leaves both columns NULL.

Every way that can fail leaves NULL rather than a guess, and each is a real
shape rather than a hypothetical:

* **no job payload, or no ``explanations`` key, or one that is not an array** —
  the payload is durable but a release that predates the explanation layer wrote
  it, so there is nothing to read;
* **every entry's mode is null** — a genuine pre-ADR-0016 run, and NULL is the
  correct and final answer for it, not a failure;
* **entries disagree** — a payload assembled from two scoring passes. A run
  whose candidates were not all scored under one model has no single mode, and
  picking the majority would invent one;
* **a mode outside the vocabulary** — a typo, or a value from a release this
  database does not know. Refusing it here is the same judgement
  ``_read_match_run_command`` makes at the front door, where an unrecognised
  mode is a failure rather than a fall-through to the default.

``registry_hash`` is deliberately **not** a backfill source, even though it does
distinguish the two modes. It distinguishes them only by being different from
each other, and mapping a digest back to the mode that produced it means
recomputing today's weight sets and hoping the unit had no overrides — a
reconstruction that would be silently wrong for any unit that did (migration
``0027``). A payload that says ``"cba-virtual-1"`` says it; a hash merely differs.

Expand only
=============
Two nullable columns, one partial CHECK over one of them, one partial index, and
an UPDATE that touches only rows whose mode is already recorded elsewhere.
Nothing is dropped, renamed or narrowed, and no existing constraint is widened,
so the previous release runs unchanged against this schema (v1.1 §4.2,
ADR-0009): it neither writes these columns nor reads them.
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

#: The vocabulary as a SQL list, spelled once so the CHECK below and the
#: backfill's own filter cannot disagree about what a mode is.
_SCORING_MODES_SQL = "'" + "','".join(_SCORING_MODES) + "'"

#: Partial by construction: it says what a recorded mode may be, and nothing
#: about a run that recorded none. Widening ``ck_match_run_pins_present`` to
#: cover this column instead would have put every stored row in violation, which
#: is why that constraint is untouched.
_SCORING_MODE_IS_KNOWN = f"scoring_mode IS NULL OR scoring_mode IN ({_SCORING_MODES_SQL})"


def upgrade() -> None:
    """Add the two mode columns, backfill the unambiguous rows, then constrain."""
    # Nullable, no server default. A default would put every existing row into a
    # mode nobody chose, which is the whole of what OQ-CBA-028 rejected.
    op.add_column("match_run", sa.Column("scoring_mode", sa.Text, nullable=True))
    op.add_column("match_run", sa.Column("scoring_mode_version", sa.Text, nullable=True))

    # Backfill before constraining. The order does not matter for correctness
    # here — the statement below writes only vocabulary members — but it matters
    # for the failure mode: if that read ever produced something outside the
    # vocabulary, the constraint should refuse to be created rather than the
    # backfill silently succeeding.
    _backfill_from_explanation_payloads()

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


def _backfill_from_explanation_payloads() -> None:
    """Copy each run's already-recorded mode onto its row, where it is unambiguous.

    One statement, wrapped in the trigger disable/enable pair the module
    docstring explains. The trigger is named rather than switched off wholesale
    with ``DISABLE TRIGGER USER``, so a trigger some later revision adds to this
    table is not silently disabled by this one.
    """
    op.execute("ALTER TABLE match_run DISABLE TRIGGER match_run_is_immutable")
    op.execute(
        f"""
        WITH recorded AS (
            SELECT
                run.id                                           AS run_id,
                run.tenant_id                                    AS tenant_id,
                -- COUNT(DISTINCT ...) ignores NULLs, so these counts read
                -- together are what "unambiguous" means: exactly one mode was
                -- named, and it was named on every candidate. A payload mixing
                -- a labelled entry with an unlabelled one makes `entries`
                -- exceed `labelled_entries` and is declined below.
                COUNT(DISTINCT entry ->> 'scoring_mode')         AS distinct_modes,
                COUNT(DISTINCT entry ->> 'scoring_mode_version') AS distinct_versions,
                COUNT(*)                                         AS entries,
                COUNT(entry ->> 'scoring_mode')                  AS labelled_entries,
                MIN(entry ->> 'scoring_mode')                    AS mode,
                MIN(entry ->> 'scoring_mode_version')            AS mode_version
              FROM match_run AS run
              JOIN job
                ON job.tenant_id = run.tenant_id
               AND job.id = run.job_id
              CROSS JOIN LATERAL
                   jsonb_array_elements(job.payload -> 'explanations') AS entry
             WHERE run.scoring_mode IS NULL
               AND job.payload IS NOT NULL
               -- Guards the LATERAL: jsonb_array_elements raises on a scalar or
               -- an object, and a migration that failed on one malformed
               -- payload would be a migration nobody can run.
               AND jsonb_typeof(job.payload -> 'explanations') = 'array'
             GROUP BY run.id, run.tenant_id
        )
        UPDATE match_run AS target
           SET scoring_mode = recorded.mode,
               scoring_mode_version = recorded.mode_version
          FROM recorded
         WHERE target.id = recorded.run_id
           AND target.tenant_id = recorded.tenant_id
           AND recorded.entries > 0
           -- Exactly one mode, on every entry, with exactly one version beside
           -- it. See the module docstring for each way this declines.
           AND recorded.distinct_modes = 1
           AND recorded.distinct_versions = 1
           AND recorded.labelled_entries = recorded.entries
           AND length(btrim(recorded.mode)) > 0
           AND length(btrim(recorded.mode_version)) > 0
           AND recorded.mode IN ({_SCORING_MODES_SQL})
        """
    )
    op.execute("ALTER TABLE match_run ENABLE TRIGGER match_run_is_immutable")


def downgrade() -> None:
    """Drop the index, the constraint, then the two columns.

    In reverse creation order. A development tool, not a production rollback
    path (v1.1 §4.2): running this discards every run's recorded mode from the
    row. It is not, however, a loss of the fact — the job summary event and the
    stored explanation payload still say what each run was scored under, which
    is precisely the state OQ-CBA-028 described before this revision, and the
    reason the backfill above was possible at all.
    """
    op.drop_index("ix_match_run_scoring_mode", table_name="match_run")
    op.drop_constraint("ck_match_run_scoring_mode", "match_run", type_="check")
    op.drop_column("match_run", "scoring_mode_version")
    op.drop_column("match_run", "scoring_mode")
