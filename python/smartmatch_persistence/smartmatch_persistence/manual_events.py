"""Storage for manually filed events and their per-event feedback QR redirect.

A manual event is a row in the canonical ``event`` table
(``origin='coordinator_entry'``, ``filed_by_user_id`` set), written through
``smartmatch_persistence.events.EventRepository`` — this module does not
duplicate that write path. What it owns is:

* ``event_manual_detail`` — the event-only extras ``event`` has no column
  for (category, free-text location, capacity, volunteer openings/needs,
  audience, contact, speaker topics, region), one row per manual event, plus
  the idempotency-replay and optimistic-locking bookkeeping the write route
  needs.
* ``event_feedback_qr`` / ``event_feedback_qr_open`` — the per-event
  feedback QR and its data-minimised open counter.

No ``managed_event`` table exists here; see the migration ``0035`` docstring
for why.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Mapping
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = ["ManualEventDetailRepository"]


class ManualEventDetailRepository:
    """Reads and writes ``event_manual_detail`` and the feedback QR tables.

    Every method takes a session per call and commits nothing — transaction
    boundaries belong to the caller, the discipline every repository in this
    package holds to.
    """

    # -- manual event detail -------------------------------------------------

    def find_by_idempotency_key(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        idempotency_key: str,
    ) -> RowMapping | None:
        """The detail row already stored under this idempotency key, if any."""
        return (
            session.execute(
                sa.select(schema.event_manual_detail).where(
                    schema.event_manual_detail.c.tenant_id == tenant_id,
                    schema.event_manual_detail.c.owning_unit_id == unit_id,
                    schema.event_manual_detail.c.idempotency_key == idempotency_key,
                )
            )
            .mappings()
            .one_or_none()
        )

    def create_detail(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        event_id: uuid.UUID,
        idempotency_key: str,
        request_fingerprint: str,
        values: Mapping[str, Any],
    ) -> RowMapping:
        """Insert the side-table row for a freshly created manual event."""
        row = (
            session.execute(
                sa.insert(schema.event_manual_detail)
                .values(
                    event_id=event_id,
                    tenant_id=tenant_id,
                    owning_unit_id=unit_id,
                    idempotency_key=idempotency_key,
                    request_fingerprint=request_fingerprint,
                    **values,
                )
                .returning(*schema.event_manual_detail.c)
            )
            .mappings()
            .one()
        )
        return row

    def get_detail(
        self, session: Session, *, tenant_id: uuid.UUID, event_id: uuid.UUID
    ) -> RowMapping | None:
        return (
            session.execute(
                sa.select(schema.event_manual_detail).where(
                    schema.event_manual_detail.c.tenant_id == tenant_id,
                    schema.event_manual_detail.c.event_id == event_id,
                )
            )
            .mappings()
            .one_or_none()
        )

    def update_detail(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        event_id: uuid.UUID,
        expected_version: int,
        values: Mapping[str, Any],
    ) -> RowMapping | None:
        """Update the detail row, or return ``None`` on a version mismatch."""
        return (
            session.execute(
                sa.update(schema.event_manual_detail)
                .where(
                    schema.event_manual_detail.c.tenant_id == tenant_id,
                    schema.event_manual_detail.c.event_id == event_id,
                    schema.event_manual_detail.c.version == expected_version,
                )
                .values(**values, version=expected_version + 1, updated_at=sa.func.now())
                .returning(*schema.event_manual_detail.c)
            )
            .mappings()
            .one_or_none()
        )

    # -- feedback QR ----------------------------------------------------------

    def get_qr(
        self, session: Session, *, tenant_id: uuid.UUID, event_id: uuid.UUID
    ) -> RowMapping | None:
        qr = schema.event_feedback_qr
        opens = schema.event_feedback_qr_open
        return (
            session.execute(
                sa.select(
                    *qr.c,
                    sa.func.count(opens.c.id).label("open_count"),
                    sa.func.max(opens.c.opened_at).label("last_opened_at"),
                )
                .outerjoin(
                    opens,
                    sa.and_(opens.c.tenant_id == qr.c.tenant_id, opens.c.qr_id == qr.c.id),
                )
                .where(qr.c.tenant_id == tenant_id, qr.c.event_id == event_id)
                .group_by(*qr.c)
            )
            .mappings()
            .one_or_none()
        )

    def upsert_qr(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        event_id: uuid.UUID,
        actor_id: uuid.UUID,
        destination_url: str,
    ) -> RowMapping:
        """Create the event's feedback QR, or repoint its destination.

        The public token is generated only on first insert
        (``secrets.token_urlsafe(24)``) and is never part of the
        ``ON CONFLICT DO UPDATE`` set — see
        ``tests/unit/test_manual_events.py``'s token-stability assertion —
        so a destination change never rotates a printed code (decision doc).
        """
        qr = schema.event_feedback_qr
        session.execute(
            postgresql.insert(qr)
            .values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                owning_unit_id=unit_id,
                event_id=event_id,
                public_token=secrets.token_urlsafe(24),
                destination_url=destination_url,
                created_by=actor_id,
            )
            .on_conflict_do_update(
                constraint="uq_event_feedback_qr_event",
                set_={"destination_url": destination_url, "updated_at": sa.func.now()},
            )
        )
        row = self.get_qr(session, tenant_id=tenant_id, event_id=event_id)
        assert row is not None
        return row

    def record_open(self, session: Session, *, public_token: str) -> str | None:
        """Record a data-minimised open and return the destination, if active.

        Active means: the token exists, and the event it belongs to has
        ``publication_status = 'published'``. Returns ``None`` otherwise —
        the caller must not disclose which of "no such token" and "not
        published" applies (decision doc: "The redirect is active only for a
        published event.").
        """
        qr = schema.event_feedback_qr
        event = schema.event
        row = session.execute(
            sa.select(qr.c.id, qr.c.tenant_id, qr.c.destination_url)
            .join(
                event,
                sa.and_(event.c.tenant_id == qr.c.tenant_id, event.c.id == qr.c.event_id),
            )
            .where(
                qr.c.public_token == public_token,
                event.c.publication_status == "published",
            )
        ).one_or_none()
        if row is None:
            return None
        session.execute(
            sa.insert(schema.event_feedback_qr_open).values(
                id=uuid.uuid4(), tenant_id=row.tenant_id, qr_id=row.id
            )
        )
        return str(row.destination_url)
