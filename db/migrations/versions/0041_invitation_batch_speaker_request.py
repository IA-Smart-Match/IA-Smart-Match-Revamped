"""An invitation batch names the Speaker Request it invites for.

Revision ID: 0041_batch_speaker_request
Revises: 0040_booking_cancellation
Create Date: 2026-09-23

The revision id is shorter than the filename on purpose: ``alembic_version`` is
``varchar(32)``, and ``0041_invitation_batch_speaker_request`` is 37 characters.
The precedents are ``0024_cba_classification`` and ``0040_booking_cancellation``.

B26 T4 (parent plan ``docs/plans/2026-09-22-b26-self-service-availability-plan.md``
§3.5; track plan ``docs/plans/b26-tracks/T4-plan.md`` §4.1; owner ruling C1 (b)).

Why
===
Before this revision a batch had no event: ``event_name`` / ``event_date`` are
display strings, and ``match_run_id`` is optional. Compose and dispatch re-check
a Speaker's stated availability against the event's date, so the batch must say
which Speaker Request (an ``event`` row with ``origin = 'coordinator_entry'``) it
invites for — with or without a run.

The column
==========
``speaker_request_id`` — nullable ``uuid``, no default. Legacy hand-picked
batches and batches from pre-OQ-CBA-031 runs have no request to name, so the
column stays nullable; "every new batch names one" is an API rule (C12 = R1).

The backfill
============
One ``UPDATE`` of ``cba_invitation_batch`` from ``match_run`` → ``event``. Since
OQ-CBA-031 a run's ``event_need_id`` is written from the request id, and the
batch recorded the run: the join reads two recorded facts, it reconstructs
nothing (ADR-0011 rule 1). It matches by **text** (``e.id::text =
r.event_need_id``), never ``::uuid``, because a pre-031 need is free text and a
cast would abort the revision. The run and the request must both belong to the
batch's own unit; anything else stays NULL. ``match_run`` is only read, so its
immutability trigger is not involved.

The key
=======
``fk_cba_invitation_batch_speaker_request`` is composite, ``(tenant_id,
speaker_request_id)`` → ``event (tenant_id, id)``, so a batch can never name
another tenant's request. ``ON DELETE RESTRICT``: a batch's record of what it
invited for must neither vanish nor be silently unstamped. No index: nothing
filters batches by request and nothing deletes ``event`` rows.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0041_batch_speaker_request"
down_revision = "0040_booking_cancellation"
branch_labels = None
depends_on = None

_TABLE = "cba_invitation_batch"
_FK = "fk_cba_invitation_batch_speaker_request"

_BACKFILL = """
UPDATE cba_invitation_batch AS b
SET speaker_request_id = e.id
FROM match_run AS r
JOIN event AS e
  ON e.tenant_id = r.tenant_id
 AND e.id::text = r.event_need_id
WHERE r.tenant_id = b.tenant_id
  AND r.id = b.match_run_id
  AND r.owning_unit_id = b.owning_unit_id
  AND e.host_org_unit_id = b.owning_unit_id
  AND e.origin = 'coordinator_entry'
"""


def upgrade() -> None:
    """Add the column, backfill it from the batch's run, then add the key."""
    op.add_column(
        _TABLE,
        sa.Column("speaker_request_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(sa.text(_BACKFILL))
    op.create_foreign_key(
        _FK,
        _TABLE,
        "event",
        ["tenant_id", "speaker_request_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """Drop the key, then the column. The backfilled values are derivable again."""
    op.drop_constraint(_FK, _TABLE, type_="foreignkey")
    op.drop_column(_TABLE, "speaker_request_id")
