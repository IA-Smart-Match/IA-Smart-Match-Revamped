"""Storage operations for manually managed events and feedback QR redirects."""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Mapping
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = ["EventRepository"]


class EventRepository:
    """Keep event and QR persistence behind one tenant-scoped boundary."""

    def create_draft(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        actor_id: uuid.UUID,
        idempotency_key: str,
        request_fingerprint: str,
        values: Mapping[str, Any],
    ) -> tuple[RowMapping, bool]:
        existing = session.execute(
            sa.select(schema.event).where(
                schema.event.c.tenant_id == tenant_id,
                schema.event.c.owning_unit_id == unit_id,
                schema.event.c.idempotency_key == idempotency_key,
            )
        ).mappings().one_or_none()
        if existing is not None:
            if existing["request_fingerprint"] != request_fingerprint:
                raise ValueError("idempotency_conflict")
            return existing, True

        event_id = uuid.uuid4()
        row = session.execute(
            sa.insert(schema.event)
            .values(
                id=event_id,
                tenant_id=tenant_id,
                owning_unit_id=unit_id,
                created_by=actor_id,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
                status="draft",
                source_kind="manual",
                **values,
            )
            .returning(*schema.event.c)
        ).mappings().one()
        return row, False

    def list_events(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        event_status: str,
    ) -> list[RowMapping]:
        query = sa.select(schema.event).where(
            schema.event.c.tenant_id == tenant_id,
            schema.event.c.owning_unit_id == unit_id,
        )
        if event_status != "all":
            query = query.where(schema.event.c.status == event_status)
        query = query.order_by(
            schema.event.c.starts_at.asc().nullslast(),
            schema.event.c.on_date.asc().nullslast(),
            schema.event.c.title,
        )
        return list(session.execute(query).mappings().all())

    def get_event(
        self, session: Session, *, tenant_id: uuid.UUID, unit_id: uuid.UUID, event_id: uuid.UUID
    ) -> RowMapping | None:
        return session.execute(
            sa.select(schema.event).where(
                schema.event.c.tenant_id == tenant_id,
                schema.event.c.owning_unit_id == unit_id,
                schema.event.c.id == event_id,
            )
        ).mappings().one_or_none()

    def update_event(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        event_id: uuid.UUID,
        values: Mapping[str, Any],
    ) -> RowMapping | None:
        return session.execute(
            sa.update(schema.event)
            .where(
                schema.event.c.tenant_id == tenant_id,
                schema.event.c.owning_unit_id == unit_id,
                schema.event.c.id == event_id,
            )
            .values(**values, updated_at=sa.func.now())
            .returning(*schema.event.c)
        ).mappings().one_or_none()

    def get_qr(
        self, session: Session, *, tenant_id: uuid.UUID, event_id: uuid.UUID
    ) -> RowMapping | None:
        qr = schema.event_feedback_qr
        opens = schema.event_feedback_qr_open
        return session.execute(
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
        ).mappings().one_or_none()

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
        qr = schema.event_feedback_qr
        session.execute(
            sa.dialects.postgresql.insert(qr)
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
        qr = schema.event_feedback_qr
        event = schema.event
        row = session.execute(
            sa.select(qr.c.id, qr.c.tenant_id, qr.c.destination_url)
            .join(
                event,
                sa.and_(event.c.tenant_id == qr.c.tenant_id, event.c.id == qr.c.event_id),
            )
            .where(qr.c.public_token == public_token, event.c.status == "published")
        ).one_or_none()
        if row is None:
            return None
        session.execute(
            sa.insert(schema.event_feedback_qr_open).values(
                id=uuid.uuid4(), tenant_id=row.tenant_id, qr_id=row.id
            )
        )
        return str(row.destination_url)
