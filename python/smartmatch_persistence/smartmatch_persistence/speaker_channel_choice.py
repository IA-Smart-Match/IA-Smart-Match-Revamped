"""The Speaker's opt-in / opt-out log per contact channel (B26 T6b-3 plan §4.2).

``contact_channel_speaker_choice`` (migration ``0039``) is append-only (a
``BEFORE UPDATE`` trigger refuses edits) and ordered by ``sequence``, not by
``decided_at``: two requests' clocks can disagree with their lock order. The
writer computes ``max(sequence) + 1`` while the caller holds the channel's
``FOR UPDATE`` lock, and ``uq_contact_channel_speaker_choice_sequence`` catches
a writer that skipped the lock.

The log decides the Speaker-wins 409s on Connector surfaces only. No send path
reads it: suppression stays the one send gate.

Nothing here commits.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from smartmatch_domain.speaker_channel_consent import SpeakerChoice
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = ["SpeakerChoiceRepository", "SpeakerChoiceRow"]

_LOG = schema.contact_channel_speaker_choice


@dataclass(frozen=True, slots=True)
class SpeakerChoiceRow:
    """One entry of the log."""

    id: uuid.UUID
    contact_channel_id: uuid.UUID
    professional_id: uuid.UUID
    sequence: int
    choice: SpeakerChoice
    decided_at: datetime
    actor_user_id: uuid.UUID
    lifted_source: str | None
    lifted_suppressed_at: datetime | None


def _row(row: sa.Row[Any]) -> SpeakerChoiceRow:
    return SpeakerChoiceRow(
        id=row.id,
        contact_channel_id=row.contact_channel_id,
        professional_id=row.professional_id,
        sequence=row.sequence,
        choice=SpeakerChoice(row.choice),
        decided_at=row.decided_at,
        actor_user_id=row.actor_user_id,
        lifted_source=row.lifted_source,
        lifted_suppressed_at=row.lifted_suppressed_at,
    )


class SpeakerChoiceRepository:
    """Appends to and reads the choice log. Stateless; never commits."""

    def append(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        contact_channel_id: uuid.UUID,
        choice: SpeakerChoice,
        decided_at: datetime,
        actor_user_id: uuid.UUID,
        lifted_source: str | None = None,
        lifted_suppressed_at: datetime | None = None,
    ) -> SpeakerChoiceRow:
        """Append one choice. The caller holds the channel's ``FOR UPDATE`` lock.

        ``professional_id`` is copied from the channel row in the same
        statement, so it always equals ``contact_channel.professional_id``
        (no foreign key can say so).
        """
        channel = schema.contact_channel
        next_sequence = (
            sa.select(sa.func.coalesce(sa.func.max(_LOG.c.sequence), 0) + 1)
            .where(_LOG.c.tenant_id == tenant_id, _LOG.c.contact_channel_id == contact_channel_id)
            .scalar_subquery()
        )
        source = sa.select(
            sa.literal(uuid.uuid4(), sa.Uuid).label("id"),
            channel.c.tenant_id,
            channel.c.professional_id,
            channel.c.id.label("contact_channel_id"),
            next_sequence.label("sequence"),
            sa.literal(choice.value, sa.Text).label("choice"),
            sa.literal(decided_at, sa.DateTime(timezone=True)).label("decided_at"),
            sa.literal(actor_user_id, sa.Uuid).label("actor_user_id"),
            sa.literal(lifted_source, sa.Text).label("lifted_source"),
            sa.literal(lifted_suppressed_at, sa.DateTime(timezone=True)).label(
                "lifted_suppressed_at"
            ),
        ).where(channel.c.tenant_id == tenant_id, channel.c.id == contact_channel_id)
        written = session.execute(
            sa.insert(_LOG)
            .from_select(
                [
                    "id",
                    "tenant_id",
                    "professional_id",
                    "contact_channel_id",
                    "sequence",
                    "choice",
                    "decided_at",
                    "actor_user_id",
                    "lifted_source",
                    "lifted_suppressed_at",
                ],
                source,
            )
            .returning(*_LOG.c)
        ).one_or_none()
        if written is None:
            raise LookupError("no such contact channel in this tenant")
        return _row(written)

    def latest_for_channel(
        self, session: Session, *, tenant_id: uuid.UUID, contact_channel_id: uuid.UUID
    ) -> SpeakerChoiceRow | None:
        """The channel's latest choice by ``sequence``, or ``None``."""
        row = session.execute(
            sa.select(_LOG)
            .where(_LOG.c.tenant_id == tenant_id, _LOG.c.contact_channel_id == contact_channel_id)
            .order_by(_LOG.c.sequence.desc())
            .limit(1)
        ).one_or_none()
        return None if row is None else _row(row)

    def latest_for_channels(
        self, session: Session, *, tenant_id: uuid.UUID, contact_channel_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, SpeakerChoiceRow]:
        """Each channel's latest choice, in one ``DISTINCT ON`` query."""
        wanted = sorted(set(contact_channel_ids))
        if not wanted:
            return {}
        rows = session.execute(
            sa.select(_LOG)
            .distinct(_LOG.c.contact_channel_id)
            .where(_LOG.c.tenant_id == tenant_id, _LOG.c.contact_channel_id.in_(wanted))
            .order_by(_LOG.c.contact_channel_id, _LOG.c.sequence.desc())
        ).all()
        return {row.contact_channel_id: _row(row) for row in rows}

    def last_transition_at_for_channels(
        self, session: Session, *, tenant_id: uuid.UUID, contact_channel_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, datetime]:
        """Each channel's latest ``contact_channel_transition.occurred_at``."""
        wanted = sorted(set(contact_channel_ids))
        if not wanted:
            return {}
        trail = schema.contact_channel_transition
        rows = session.execute(
            sa.select(trail.c.contact_channel_id, sa.func.max(trail.c.occurred_at).label("at"))
            .where(trail.c.tenant_id == tenant_id, trail.c.contact_channel_id.in_(wanted))
            .group_by(trail.c.contact_channel_id)
        ).all()
        return {row.contact_channel_id: row.at for row in rows}
