"""The class exercise stores what Ann's final data file carries.

Revision ID: 0042_exercise_ann_dataset
Revises: 0041_batch_speaker_request
Create Date: 2026-09-24

Ann's data file arrived on 2026-09-24 and closed OQ-CE-01 (column names and
vocabularies) and OQ-CE-05 (the upload is her ``.xlsx``). It carries two values
``exercise_profile`` has no column for:

``hidden_true_career_goal``
    Ann's second pink column: "HIDDEN. The profile's real career goal. Same
    rules as hidden_true_interests." Withheld under ADR-0025 D6 exactly as
    ``hidden_true_interests`` is — named in ``EXERCISE_WITHHELD_FIELDS``, so
    ``exercise_profile_public_columns()`` never selects it. Read by the
    simulated-results rule and by the refresh, which copies it onto a new card
    (OQ-CE-13, answered by the same Read Me). Nullable: a dataset stored
    before this revision has none, and the file may leave the cell blank.
    Such a dataset's simulated results earn no career-goal fit (the rule now
    reads the hidden goal, not the public one); only placeholder-CSV uploads
    are affected, and re-uploading Ann's file restores it.

``tiebreak_order``
    "Fixed random order 1–300 for the last step of the tie-break. Never
    changes between runs." (owner ruling 3). Positive and unique within a
    dataset. Nullable, because a dataset stored before this revision has none
    and keeps the checksum-seeded order; PostgreSQL's unique constraint admits
    any number of ``NULL``\\ s, so those datasets remain valid.

Nothing is added to ``exercise_event``. ``event_type`` and ``event_date`` are
in Ann's file but nothing in the exercise shows or reads them; ``seats`` is
checked at ingest against the simulation's fixed 60 rather than stored, so a
file that disagrees is refused rather than half-honoured.

No ``CHECK`` closes a vocabulary: the owner ruled the vocabularies closed *in
code* (``smartmatch_domain.exercise.vocabulary``), where changing one is an
edit rather than a migration. The revision 0037 comments that say OQ-CE-01 is
open are history and are left as written.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0042_exercise_ann_dataset"
down_revision = "0041_batch_speaker_request"
branch_labels = None
depends_on = None

_TABLE = "exercise_profile"


def upgrade() -> None:
    """Add the two columns and the fixed order's two constraints."""
    op.add_column(_TABLE, sa.Column("tiebreak_order", sa.Integer, nullable=True))
    op.add_column(_TABLE, sa.Column("hidden_true_career_goal", sa.Text, nullable=True))
    op.create_check_constraint(
        "ck_exercise_profile_tiebreak_order", _TABLE, "tiebreak_order >= 1"
    )
    op.create_unique_constraint(
        "uq_exercise_profile_tiebreak_order", _TABLE, ["dataset_id", "tiebreak_order"]
    )


def downgrade() -> None:
    """Drop them again. Both columns' values are lost; re-upload the file."""
    op.drop_constraint("uq_exercise_profile_tiebreak_order", _TABLE, type_="unique")
    op.drop_constraint("ck_exercise_profile_tiebreak_order", _TABLE, type_="check")
    op.drop_column(_TABLE, "hidden_true_career_goal")
    op.drop_column(_TABLE, "tiebreak_order")
