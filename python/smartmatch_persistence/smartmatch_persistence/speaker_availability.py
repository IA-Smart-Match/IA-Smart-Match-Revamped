"""The ``speaker_availability`` read/write path (migration ``0038``, B26 T2).

A speaker's stated availability is one row plus its unavailable windows. This
module reads and writes the pair and returns it as the T1 domain type,
:class:`~smartmatch_domain.speaker_availability.AvailabilityStatement`, wrapped
with the version and provenance the API needs.

## No row is an answer

:meth:`SpeakerAvailabilityRepository.get` returns ``None`` for a speaker who
has said nothing (``UNKNOWN`` downstream). A row with zero windows is a real
answer — "nothing blocked" (``AVAILABLE``). The two are kept apart.

## A read is one statement

The engine runs READ COMMITTED, so two queries can straddle a writer's commit
and pair the row at version *n* with the windows at *n+1*. Both reads are one
``LEFT JOIN`` statement, grouped in Python; ``get`` is ``get_many`` with one id.

## The version is always checked

Two writers share a row: the speaker and a Speaker Connector. So
``expected_version`` is never a blind write: ``None`` means "I believe there
is no row". A mismatch in either direction, and a concurrent first write that
won the insert race, raise :class:`StaleSpeakerAvailabilityError` (T3 maps it
to ``409 speaker_availability_stale``).

## Transaction boundaries belong to the caller

A :class:`~sqlalchemy.orm.Session` per call; this module **never commits**.

## What this module never does

It never validates. The caller runs
:func:`~smartmatch_domain.speaker_availability.validate_availability_statement`
first (limits, horizons, duplicates -> 422). A duplicate range that still
reaches the database raises ``IntegrityError`` on
``uq_speaker_availability_window_range``: a caller bug, reported loudly. An
unknown or other-tenant ``professional_id`` is a foreign-key ``IntegrityError``;
T3 checks the profile's unit first and returns 404.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

import sqlalchemy as sa
from smartmatch_domain.speaker_availability import AvailabilityStatement, UnavailableWindow
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = [
    "AvailabilitySource",
    "SpeakerAvailabilityRepository",
    "StaleSpeakerAvailabilityError",
    "StoredSpeakerAvailability",
    "StoredWindow",
]


class AvailabilitySource(StrEnum):
    """Which surface wrote a statement or a window (T2 plan C7: persistence-owned)."""

    SPEAKER = "speaker"
    CONNECTOR = "connector"


class StaleSpeakerAvailabilityError(RuntimeError):
    """The caller's ``expected_version`` is not what is stored, or a first write lost a race."""


@dataclass(frozen=True, slots=True)
class StoredWindow:
    """One stored unavailable window and who wrote it."""

    starts_on: date
    ends_on: date
    created_source: AvailabilitySource
    created_by_user_id: uuid.UUID
    created_at: datetime


@dataclass(frozen=True, slots=True)
class StoredSpeakerAvailability:
    """A speaker's statement as stored, with version and provenance.

    ``statement.unavailable`` and ``windows`` hold the same ranges in the same
    order, ``(starts_on, ends_on)``; ``windows`` adds each range's provenance.
    """

    tenant_id: uuid.UUID
    professional_id: uuid.UUID
    statement: AvailabilityStatement
    windows: tuple[StoredWindow, ...]
    version: int
    updated_source: AvailabilitySource
    updated_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


def _assemble(rows: Sequence[Any]) -> StoredSpeakerAvailability:
    """One speaker's joined rows (same statement, zero or more windows) as a record."""
    head = rows[0]
    windows = tuple(
        StoredWindow(
            starts_on=row.w_starts_on,
            ends_on=row.w_ends_on,
            created_source=AvailabilitySource(row.w_created_source),
            created_by_user_id=row.w_created_by_user_id,
            created_at=row.w_created_at,
        )
        for row in rows
        if row.w_starts_on is not None
    )
    return StoredSpeakerAvailability(
        tenant_id=head.tenant_id,
        professional_id=head.professional_id,
        statement=AvailabilityStatement(
            invitations_paused_until=head.invitations_paused_until,
            declared_capacity_hours_per_90_days=head.declared_capacity_hours_per_90_days,
            unavailable=tuple(UnavailableWindow(w.starts_on, w.ends_on) for w in windows),
        ),
        windows=windows,
        version=int(head.version),
        updated_source=AvailabilitySource(head.updated_source),
        updated_by_user_id=head.updated_by_user_id,
        created_at=head.created_at,
        updated_at=head.updated_at,
    )


class SpeakerAvailabilityRepository:
    """Reads and writes ``speaker_availability`` and its windows. Never commits."""

    def get(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        professional_id: uuid.UUID,
    ) -> StoredSpeakerAvailability | None:
        """The speaker's statement, or ``None`` when they have said nothing. One query."""
        found = self.get_many(session, tenant_id=tenant_id, professional_ids=[professional_id])
        return found.get(professional_id)

    def get_many(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        professional_ids: Collection[uuid.UUID],
    ) -> Mapping[uuid.UUID, StoredSpeakerAvailability]:
        """Statements for the given speakers, keyed by ``professional_id``.

        An absent key means no row. Empty input issues no query. Otherwise one
        ``LEFT JOIN`` statement, so the result is one committed state.
        """
        ids = list(dict.fromkeys(professional_ids))
        if not ids:
            return {}

        a = schema.speaker_availability
        w = schema.speaker_availability_window
        query = (
            sa.select(
                a,
                w.c.starts_on.label("w_starts_on"),
                w.c.ends_on.label("w_ends_on"),
                w.c.created_source.label("w_created_source"),
                w.c.created_by_user_id.label("w_created_by_user_id"),
                w.c.created_at.label("w_created_at"),
            )
            .select_from(
                a.outerjoin(
                    w,
                    sa.and_(
                        w.c.tenant_id == a.c.tenant_id,
                        w.c.professional_id == a.c.professional_id,
                    ),
                )
            )
            .where(a.c.tenant_id == tenant_id, a.c.professional_id.in_(ids))
            .order_by(a.c.professional_id, w.c.starts_on, w.c.ends_on)
        )

        grouped: dict[uuid.UUID, list[Any]] = {}
        for row in session.execute(query):
            grouped.setdefault(row.professional_id, []).append(row)
        return {pid: _assemble(rows) for pid, rows in grouped.items()}

    def upsert(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        professional_id: uuid.UUID,
        statement: AvailabilityStatement,
        source: AvailabilitySource,
        actor_user_id: uuid.UUID,
        expected_version: int | None,
        now: datetime | None = None,
    ) -> StoredSpeakerAvailability:
        """Write an **already validated** statement; return it as stored.

        Args:
            expected_version: The version the caller read, or ``None`` for "I
                believe there is no row". Always checked.
            now: The write's timestamp, injected so a test can pin it.

        Raises:
            StaleSpeakerAvailabilityError: the stored version differs from
                ``expected_version``, or a concurrent first write won.
        """
        table = schema.speaker_availability
        key = sa.and_(table.c.tenant_id == tenant_id, table.c.professional_id == professional_id)

        stored_version = session.execute(
            sa.select(table.c.version).where(key).with_for_update()
        ).scalar_one_or_none()
        if expected_version != stored_version:
            raise StaleSpeakerAvailabilityError(
                f"expected version {expected_version}, but the stored version is "
                f"{stored_version}. Someone else changed this availability first; "
                "re-read it before writing."
            )

        moment = now or datetime.now(tz=UTC)
        values = {
            "invitations_paused_until": statement.invitations_paused_until,
            "declared_capacity_hours_per_90_days": statement.declared_capacity_hours_per_90_days,
            "updated_source": source.value,
            "updated_by_user_id": actor_user_id,
            "updated_at": moment,
        }

        if stored_version is None:
            inserted = session.execute(
                pg_insert(table)
                .values(
                    tenant_id=tenant_id,
                    professional_id=professional_id,
                    version=1,
                    created_at=moment,
                    **values,
                )
                .on_conflict_do_nothing(index_elements=["tenant_id", "professional_id"])
                .returning(table.c.version)
            ).scalar_one_or_none()
            if inserted is None:
                raise StaleSpeakerAvailabilityError(
                    "expected no stored availability, but a concurrent first write "
                    "created one. Re-read it before writing."
                )
        else:
            session.execute(
                sa.update(table).where(key).values(version=table.c.version + 1, **values)
            )

        self._replace_windows(
            session,
            tenant_id=tenant_id,
            professional_id=professional_id,
            wanted=statement.unavailable,
            source=source,
            actor_user_id=actor_user_id,
            moment=moment,
        )

        stored = self.get(session, tenant_id=tenant_id, professional_id=professional_id)
        if stored is None:  # pragma: no cover - the row was written or locked above
            raise RuntimeError("speaker_availability row vanished inside its own transaction")
        return stored

    @staticmethod
    def _replace_windows(
        session: Session,
        *,
        tenant_id: uuid.UUID,
        professional_id: uuid.UUID,
        wanted: Sequence[UnavailableWindow],
        source: AvailabilitySource,
        actor_user_id: uuid.UUID,
        moment: datetime,
    ) -> None:
        """Delete ranges no longer wanted, insert new ones, keep the rest untouched.

        Keyed by ``(starts_on, ends_on)``: an unchanged range keeps its original
        ``created_source``, ``created_by_user_id`` and ``created_at``.
        """
        w = schema.speaker_availability_window
        owner = sa.and_(w.c.tenant_id == tenant_id, w.c.professional_id == professional_id)

        existing = {
            (row.starts_on, row.ends_on)
            for row in session.execute(sa.select(w.c.starts_on, w.c.ends_on).where(owner))
        }
        wanted_ranges = [(window.starts_on, window.ends_on) for window in wanted]

        for starts_on, ends_on in existing - set(wanted_ranges):
            session.execute(
                sa.delete(w).where(owner, w.c.starts_on == starts_on, w.c.ends_on == ends_on)
            )

        new_rows = [
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "professional_id": professional_id,
                "starts_on": starts_on,
                "ends_on": ends_on,
                "created_source": source.value,
                "created_by_user_id": actor_user_id,
                "created_at": moment,
            }
            for starts_on, ends_on in wanted_ranges
            if (starts_on, ends_on) not in existing
        ]
        if new_rows:
            session.execute(sa.insert(w), new_rows)
