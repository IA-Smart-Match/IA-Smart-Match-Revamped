"""Storage operations for manually managed events and feedback QR redirects."""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Mapping
from typing import Any

import sqlalchemy as sa
from smartmatch_domain.events import DateOnlyTime, ExactTime, normalize_title, resolved_date
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from smartmatch_persistence import schema
from smartmatch_persistence.events import EventRepository, ORIGIN_COORDINATOR_ENTRY

__all__ = ["ManualEventRepository"]


class ManualEventRepository:
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
            sa.select(schema.managed_event).where(
                schema.managed_event.c.tenant_id == tenant_id,
                schema.managed_event.c.owning_unit_id == unit_id,
                schema.managed_event.c.idempotency_key == idempotency_key,
            )
        ).mappings().one_or_none()
        if existing is not None:
            if existing["request_fingerprint"] != request_fingerprint:
                raise ValueError("idempotency_conflict")
            return existing, True

        event_id = uuid.uuid4()
        row = session.execute(
            sa.insert(schema.managed_event)
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
            .returning(*schema.managed_event.c)
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
        query = sa.select(schema.managed_event).where(
            schema.managed_event.c.tenant_id == tenant_id,
            schema.managed_event.c.owning_unit_id == unit_id,
        )
        if event_status != "all":
            query = query.where(schema.managed_event.c.status == event_status)
        query = query.order_by(
            schema.managed_event.c.starts_at.asc().nullslast(),
            schema.managed_event.c.on_date.asc().nullslast(),
            schema.managed_event.c.title,
        )
        return list(session.execute(query).mappings().all())

    def get_event(
        self, session: Session, *, tenant_id: uuid.UUID, unit_id: uuid.UUID, event_id: uuid.UUID
    ) -> RowMapping | None:
        return session.execute(
            sa.select(schema.managed_event).where(
                schema.managed_event.c.tenant_id == tenant_id,
                schema.managed_event.c.owning_unit_id == unit_id,
                schema.managed_event.c.id == event_id,
            )
        ).mappings().one_or_none()

    def update_event(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        event_id: uuid.UUID,
        expected_version: int,
        values: Mapping[str, Any],
    ) -> RowMapping | None:
        return session.execute(
            sa.update(schema.managed_event)
            .where(
                schema.managed_event.c.tenant_id == tenant_id,
                schema.managed_event.c.owning_unit_id == unit_id,
                schema.managed_event.c.id == event_id,
                schema.managed_event.c.version == expected_version,
            )
            .values(**values, version=expected_version + 1, updated_at=sa.func.now())
            .returning(*schema.managed_event.c)
        ).mappings().one_or_none()

    def sync_student_catalog(self, session: Session, *, row: Mapping[str, Any]) -> RowMapping:
        """Project one published managed event into the existing Student catalog."""
        precision = str(row["time_precision"])
        if precision == "exact":
            event_time = ExactTime(
                starts_at=row["starts_at"], time_zone=row["time_zone"], ends_at=row["ends_at"]
            )
        elif precision == "date_only":
            event_time = DateOnlyTime(on_date=row["on_date"], time_zone=row["time_zone"])
        else:
            raise ValueError("event_not_publishable")

        catalog_id = row.get("catalog_event_id")
        if catalog_id is None:
            outcome = EventRepository().upsert_returning_outcome(
                session,
                tenant_id=row["tenant_id"],
                host_org_unit_id=row["owning_unit_id"],
                title=row["title"],
                event_time=event_time,
                origin=ORIGIN_COORDINATOR_ENTRY,
                description=row["description"],
                filed_by_user_id=row["created_by"],
            )
            linked = session.execute(
                sa.select(schema.managed_event.c.id).where(
                    schema.managed_event.c.tenant_id == row["tenant_id"],
                    schema.managed_event.c.catalog_event_id == outcome.event_id,
                    schema.managed_event.c.id != row["id"],
                )
            ).first()
            if linked is not None:
                raise ValueError("catalog_event_conflict")
            catalog_id = outcome.event_id
            session.execute(
                sa.update(schema.managed_event)
                .where(
                    schema.managed_event.c.tenant_id == row["tenant_id"],
                    schema.managed_event.c.id == row["id"],
                )
                .values(catalog_event_id=catalog_id)
            )
        else:
            values: dict[str, Any] = {
                "title": row["title"],
                "normalized_title": normalize_title(row["title"]),
                "description": row["description"],
                "resolved_date": resolved_date(event_time),
                "starts_at": getattr(event_time, "starts_at", None),
                "ends_at": getattr(event_time, "ends_at", None),
                "on_date": getattr(event_time, "on_date", None),
                "time_zone": row["time_zone"],
                "time_precision": precision,
                "updated_at": sa.func.now(),
            }
            updated = session.execute(
                sa.update(schema.event)
                .where(
                    schema.event.c.tenant_id == row["tenant_id"],
                    schema.event.c.id == catalog_id,
                    schema.event.c.host_org_unit_id == row["owning_unit_id"],
                )
                .values(**values)
            )
            if updated.rowcount != 1:
                raise ValueError("catalog_event_conflict")

        EventRepository().publish(
            session, tenant_id=row["tenant_id"], event_id=catalog_id
        )
        refreshed = self.get_event(
            session,
            tenant_id=row["tenant_id"],
            unit_id=row["owning_unit_id"],
            event_id=row["id"],
        )
        assert refreshed is not None
        return refreshed

    def unpublish_student_catalog(self, session: Session, *, row: Mapping[str, Any]) -> None:
        catalog_id = row.get("catalog_event_id")
        if catalog_id is None:
            return
        session.execute(
            sa.update(schema.event)
            .where(
                schema.event.c.tenant_id == row["tenant_id"],
                schema.event.c.id == catalog_id,
            )
            .values(publication_status="unpublished", updated_at=sa.func.now())
        )

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
        event = schema.managed_event
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
