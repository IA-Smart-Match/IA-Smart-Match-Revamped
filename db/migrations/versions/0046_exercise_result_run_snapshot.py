"""A result run keeps the names it invited and the weights it was built with.

Revision ID: 0046_exercise_run_snapshot
Revises: 0045_exercise_unlock_closed_at
Create Date: 2026-10-06

Two defects, one cause (issues #271 and #319). ``exercise_result_run`` stored
profile *numbers* and a ``setting_name`` label, and every screen that wanted a
name asked the team's saved setting for it. A saved setting is mutable: delete
it and the names turned into "Profile 17"; re-save it under the same name and
the names shown were no longer the names the run invited. The instructor's
page could show no names for a run at all.

A run is a record, so it now carries its own:

``exercise_result_run.invited_profiles``
    ``JSONB NULL``. The invited list as the team's screen showed it at the
    moment of the run, in rank order: one object per name with ``rank``,
    ``profile_no``, ``display_name``, ``major``, ``class_year``, ``marker``
    and ``reason``. Only fields a team already sees on its ranked list; never
    a withheld column, never a score.

``exercise_result_run.setting_weights``
    ``JSONB NULL``. The four stated weights the list was built with.

Both are nullable because rows stored before this revision exist — the pilot
VM carries real runs — and ``NULL`` is the honest value for "not recorded".

The backfill, and what it deliberately does not write
=====================================================
Existing rows are backfilled **in SQL**, with no domain code imported:

* ``invited_profiles`` is rebuilt from ``invited_profile_nos`` joined to
  ``exercise_profile`` on ``(dataset_id, profile_no)``, in the stored order,
  with ``profile_no``, ``display_name``, ``major`` and ``class_year`` only.
  **No ``rank``, ``marker`` or ``reason`` key is written.** Those three
  depended on the weights and on the team's own view of the profiles at the
  moment of the run — a view a later refresh has since changed — so they
  cannot be reconstructed, and inventing them would put a fabricated rank on a
  record. The stored order is the order of ``invited_profile_nos``, which is by
  profile number, not by rank. Readers treat the three as absent.
* ``setting_weights`` is copied from ``exercise_saved_setting.weights`` where a
  setting of the run's ``setting_name`` still exists for that team and event.
  That is the setting **as it stands today**: one re-saved under the same name
  since the run shows its newer numbers. Where the setting was deleted the
  column stays ``NULL``.

The downgrade drops both columns; the names then come from the live ranked
list again, as before.

The revision id is shorter than this file's name on purpose:
``alembic_version.version_num`` is ``VARCHAR(32)``, and the file's name is
longer than that. ``0040_speaker_booking_cancellation.py`` carries
``0040_booking_cancellation`` for the same reason.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0046_exercise_run_snapshot"
down_revision = "0045_exercise_unlock_closed_at"
branch_labels = None
depends_on = None

_TABLE = "exercise_result_run"

#: Names and the two public facts beside them, in the stored order. No rank,
#: marker or reason: see the module docstring.
_BACKFILL_INVITED = """
UPDATE exercise_result_run AS run
SET invited_profiles = rebuilt.snapshot
FROM (
    SELECT
        stored.id,
        jsonb_agg(
            jsonb_build_object(
                'profile_no', profile.profile_no,
                'display_name', profile.display_name,
                'major', profile.major,
                'class_year', profile.class_year
            )
            ORDER BY invited.position
        ) AS snapshot
    FROM exercise_result_run AS stored
    CROSS JOIN LATERAL unnest(stored.invited_profile_nos)
        WITH ORDINALITY AS invited(profile_no, position)
    JOIN exercise_profile AS profile
        ON profile.dataset_id = stored.dataset_id
        AND profile.profile_no = invited.profile_no
    GROUP BY stored.id
) AS rebuilt
WHERE run.id = rebuilt.id
  AND run.invited_profiles IS NULL
"""

#: The saved setting as it stands now, where it still exists.
_BACKFILL_WEIGHTS = """
UPDATE exercise_result_run AS run
SET setting_weights = setting.weights
FROM exercise_saved_setting AS setting
WHERE setting.workspace_id = run.workspace_id
  AND setting.event_key = run.event_key
  AND setting.name = run.setting_name
  AND run.setting_weights IS NULL
"""


def upgrade() -> None:
    """Add the two columns, then give existing runs what can honestly be rebuilt."""
    op.add_column(_TABLE, sa.Column("invited_profiles", postgresql.JSONB, nullable=True))
    op.add_column(_TABLE, sa.Column("setting_weights", postgresql.JSONB, nullable=True))
    op.execute(_BACKFILL_INVITED)
    op.execute(_BACKFILL_WEIGHTS)


def downgrade() -> None:
    """Drop both. A run's names come from the live ranked list again."""
    op.drop_column(_TABLE, "setting_weights")
    op.drop_column(_TABLE, "invited_profiles")
