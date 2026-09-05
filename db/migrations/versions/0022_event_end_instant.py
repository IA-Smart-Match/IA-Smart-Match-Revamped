"""Event end instant — the column an .ics download needs and could not invent.

Revision ID: 0022_event_end_instant
Revises: 0021_outreach_schema
Create Date: 2026-09-04

Migration ``0017`` gave ``event`` ADR-0010's temporal triple — ``starts_at``,
``on_date``, ``time_zone`` — and a ``time_precision`` discriminator over them.
It gave the row no end, because nothing then needed one: the catalog route
renders when an event *begins*, and identity keys on the resolved date.

An RFC 5545 ``VEVENT`` needs both ends. ``smartmatch_domain.ics.generate_ics``
will supply a missing ``DTEND`` as one hour after ``DTSTART``, preserved from
the legacy so that port stayed a port, and
``smartmatch_domain.calendar_invite`` exists precisely to refuse that fallback:
"a guessed duration is still a guess". Finding F-003 is the legacy generator
turning an unparsed recurrence string into a confident invite thirty days out,
and a fabricated *duration* is the same defect on the other endpoint.

So there were two ways to serve a calendar artifact from these rows, and only
one of them is honest. Either the API guesses an hour on the way out — putting
the fabrication one layer further from the database than the legacy had it —
or the end instant becomes something a row can actually state. This revision
is the second. The column is where a coordinator's "3–4:30pm" is kept, and its
absence is what an ICS request is refused for.

``ends_at``
-----------
Nullable, and nullable permanently. The pilot's fixture events state no end,
and backfilling them with ``starts_at + 1 hour`` would write the exact value
this change exists to avoid — into storage, where it would then look like
something the source said. ``NULL`` here means "the source did not state an
end", which is a fact worth keeping, and it is the fact
``GET .../invite.ics`` turns into a 409 rather than into a guess.

``ck_event_end_after_start``
----------------------------
Three clauses, one rule: an end may exist only where a start does, and must
come after it.

* ``ends_at IS NULL`` — always legal, the ordinary case.
* ``time_precision = 'exact'`` — an end instant on a ``date_only`` row would
  pair a clock time with a date that has none, and on an ``unresolved`` row it
  would be an end for an event with no beginning. ``ck_event_temporal_shape``
  already keeps ``starts_at`` NULL in both, so without this clause a row could
  hold an end and no start and satisfy every other constraint.
* ``ends_at > starts_at`` — strictly. A zero-length event is not something a
  source states; it is what an adapter writes when it copies ``starts_at``
  across for want of a better value, and a calendar would render it as a real
  entry. :class:`smartmatch_domain.events.ExactTime` refuses the same value in
  Python — the same rule stated at both ends, as ``0020`` puts it.

Expand only, one transaction
----------------------------
One added nullable column and one added CHECK that every existing row already
satisfies (they all have ``ends_at IS NULL``). Nothing is dropped, renamed, or
narrowed, so every reader written before this revision is unaffected by it
(v1.1 §4.2, ADR-0009). ``transaction_per_migration=True``
(``db/migrations/env.py``) holds both statements in one transaction.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022_event_end_instant"
down_revision = "0021_outreach_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "event",
        sa.Column("ends_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_event_end_after_start",
        "event",
        "ends_at IS NULL OR (time_precision = 'exact' AND ends_at > starts_at)",
    )


def downgrade() -> None:
    # The constraint first: dropping the column would take it along, but naming
    # both makes the reverse an exact mirror of the forward rather than
    # something a reader has to know PostgreSQL's cascade rules to check.
    op.drop_constraint("ck_event_end_after_start", "event", type_="check")
    op.drop_column("event", "ends_at")
