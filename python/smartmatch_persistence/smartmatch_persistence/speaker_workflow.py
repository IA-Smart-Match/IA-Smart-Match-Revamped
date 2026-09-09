"""Tenant-safe persistence for speaker rosters and invitation tracking."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from smartmatch_persistence import schema


class SpeakerWorkflowRepository:
    def create_speaker(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        actor_id: uuid.UUID,
        values: Mapping[str, Any],
    ) -> RowMapping:
        return (
            session.execute(
                sa.insert(schema.speaker)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    owning_unit_id=unit_id,
                    created_by=actor_id,
                    **values,
                )
                .returning(*schema.speaker.c)
            )
            .mappings()
            .one()
        )

    def list_speakers(
        self, session: Session, *, tenant_id: uuid.UUID, unit_id: uuid.UUID, published: bool
    ) -> list[RowMapping]:
        table = schema.speaker_roster_entry if published else schema.speaker
        return list(
            session.execute(
                sa.select(table)
                .where(table.c.tenant_id == tenant_id, table.c.owning_unit_id == unit_id)
                .order_by(table.c.name)
            ).mappings()
        )

    def get_speaker(
        self, session: Session, *, tenant_id: uuid.UUID, unit_id: uuid.UUID, speaker_id: uuid.UUID
    ) -> RowMapping | None:
        return (
            session.execute(
                sa.select(schema.speaker).where(
                    schema.speaker.c.tenant_id == tenant_id,
                    schema.speaker.c.owning_unit_id == unit_id,
                    schema.speaker.c.id == speaker_id,
                )
            )
            .mappings()
            .one_or_none()
        )

    def update_speaker(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        speaker_id: uuid.UUID,
        version: int,
        values: Mapping[str, Any],
    ) -> RowMapping | None:
        return (
            session.execute(
                sa.update(schema.speaker)
                .where(
                    schema.speaker.c.tenant_id == tenant_id,
                    schema.speaker.c.owning_unit_id == unit_id,
                    schema.speaker.c.id == speaker_id,
                    schema.speaker.c.version == version,
                )
                .values(**values, version=version + 1, updated_at=sa.func.now())
                .returning(*schema.speaker.c)
            )
            .mappings()
            .one_or_none()
        )

    def publish_roster(
        self, session: Session, *, tenant_id: uuid.UUID, unit_id: uuid.UUID, actor_id: uuid.UUID
    ) -> tuple[int, Any]:
        roster = schema.speaker_roster
        row = session.execute(
            insert(roster)
            .values(
                tenant_id=tenant_id,
                owning_unit_id=unit_id,
                version=1,
                published_by=actor_id,
                published_at=sa.func.now(),
            )
            .on_conflict_do_update(
                constraint="speaker_roster_pkey",
                set_={
                    "version": roster.c.version + 1,
                    "published_by": actor_id,
                    "published_at": sa.func.now(),
                },
            )
            .returning(roster.c.version, roster.c.published_at)
        ).one()
        session.execute(
            sa.delete(schema.speaker_roster_entry).where(
                schema.speaker_roster_entry.c.tenant_id == tenant_id,
                schema.speaker_roster_entry.c.owning_unit_id == unit_id,
            )
        )
        source = sa.select(
            schema.speaker.c.tenant_id,
            schema.speaker.c.owning_unit_id,
            schema.speaker.c.id,
            sa.literal(row.version),
            schema.speaker.c.name,
            schema.speaker.c.title,
            schema.speaker.c.company,
            schema.speaker.c.board_role,
            schema.speaker.c.expertise_topics,
            schema.speaker.c.home_region,
            schema.speaker.c.service_regions,
        ).where(
            schema.speaker.c.tenant_id == tenant_id,
            schema.speaker.c.owning_unit_id == unit_id,
            schema.speaker.c.active.is_(True),
            schema.speaker.c.available.is_(True),
        )
        session.execute(
            sa.insert(schema.speaker_roster_entry).from_select(
                [
                    "tenant_id",
                    "owning_unit_id",
                    "speaker_id",
                    "roster_version",
                    "name",
                    "title",
                    "company",
                    "board_role",
                    "expertise_topics",
                    "home_region",
                    "service_regions",
                ],
                source,
            )
        )
        return int(row.version), row.published_at

    def roster_version(
        self, session: Session, *, tenant_id: uuid.UUID, unit_id: uuid.UUID
    ) -> int | None:
        return session.scalar(
            sa.select(schema.speaker_roster.c.version).where(
                schema.speaker_roster.c.tenant_id == tenant_id,
                schema.speaker_roster.c.owning_unit_id == unit_id,
            )
        )

    def create_match_run(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        event_id: uuid.UUID,
        actor_id: uuid.UUID,
        idempotency_key: str,
        fingerprint: str,
        results: Sequence[Any],
    ) -> tuple[RowMapping, bool]:
        run = schema.speaker_match_run
        existing = (
            session.execute(
                sa.select(run).where(
                    run.c.tenant_id == tenant_id,
                    run.c.owning_unit_id == unit_id,
                    run.c.idempotency_key == idempotency_key,
                )
            )
            .mappings()
            .one_or_none()
        )
        if existing:
            if existing["request_fingerprint"] != fingerprint:
                raise ValueError("idempotency_conflict")
            return existing, True
        version = self.roster_version(session, tenant_id=tenant_id, unit_id=unit_id)
        if version is None:
            raise ValueError("roster_not_published")
        row = (
            session.execute(
                sa.insert(run)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    owning_unit_id=unit_id,
                    event_id=event_id,
                    requested_by=actor_id,
                    idempotency_key=idempotency_key,
                    request_fingerprint=fingerprint,
                    roster_version=version,
                )
                .returning(*run.c)
            )
            .mappings()
            .one()
        )
        for position, result in enumerate(results, 1):
            profile = (
                session.execute(
                    sa.select(schema.speaker_roster_entry).where(
                        schema.speaker_roster_entry.c.tenant_id == tenant_id,
                        schema.speaker_roster_entry.c.owning_unit_id == unit_id,
                        schema.speaker_roster_entry.c.speaker_id == result.speaker_id,
                        schema.speaker_roster_entry.c.roster_version == version,
                    )
                )
                .mappings()
                .one()
            )
            session.execute(
                sa.insert(schema.speaker_match_result).values(
                    tenant_id=tenant_id,
                    owning_unit_id=unit_id,
                    match_run_id=row["id"],
                    speaker_id=result.speaker_id,
                    position=position,
                    speaker_name=profile["name"],
                    speaker_title=profile["title"],
                    speaker_company=profile["company"],
                    speaker_board_role=profile["board_role"],
                    expertise_topics=profile["expertise_topics"],
                    home_region=profile["home_region"],
                    service_regions=profile["service_regions"],
                    topic_score=result.topic_score,
                    proximity_score=result.proximity_score,
                    total_score=result.total_score,
                    explanations=list(result.explanations),
                )
            )
        return row, False

    def match_results(
        self, session: Session, *, tenant_id: uuid.UUID, unit_id: uuid.UUID, run_id: uuid.UUID
    ) -> list[RowMapping]:
        result = schema.speaker_match_result
        return list(
            session.execute(
                sa.select(
                    result.c.speaker_id,
                    result.c.speaker_name.label("name"),
                    result.c.speaker_title.label("title"),
                    result.c.speaker_company.label("company"),
                    result.c.speaker_board_role.label("board_role"),
                    result.c.expertise_topics,
                    result.c.home_region,
                    result.c.service_regions,
                    result.c.explanations,
                )
                .where(
                    result.c.tenant_id == tenant_id,
                    result.c.owning_unit_id == unit_id,
                    result.c.match_run_id == run_id,
                )
                .order_by(result.c.position)
            ).mappings()
        )

    def get_run(
        self, session: Session, *, tenant_id: uuid.UUID, unit_id: uuid.UUID, run_id: uuid.UUID
    ) -> RowMapping | None:
        return (
            session.execute(
                sa.select(schema.speaker_match_run).where(
                    schema.speaker_match_run.c.tenant_id == tenant_id,
                    schema.speaker_match_run.c.owning_unit_id == unit_id,
                    schema.speaker_match_run.c.id == run_id,
                )
            )
            .mappings()
            .one_or_none()
        )

    def submit_shortlist(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        run: Mapping[str, Any],
        speaker_ids: Sequence[uuid.UUID],
        actor_id: uuid.UUID,
        idempotency_key: str,
    ) -> list[RowMapping]:
        fingerprint = hashlib.sha256(
            json.dumps(sorted(str(value) for value in speaker_ids)).encode()
        ).hexdigest()
        submission = schema.speaker_shortlist_submission
        existing = (
            session.execute(
                sa.select(submission).where(
                    submission.c.tenant_id == tenant_id,
                    submission.c.owning_unit_id == unit_id,
                    submission.c.idempotency_key == idempotency_key,
                )
            )
            .mappings()
            .one_or_none()
        )
        if existing:
            if existing["request_fingerprint"] != fingerprint:
                raise ValueError("idempotency_conflict")
            return self.list_records(
                session, tenant_id=tenant_id, unit_id=unit_id, event_id=run["event_id"]
            )
        allowed = set(
            session.scalars(
                sa.select(schema.speaker_match_result.c.speaker_id).where(
                    schema.speaker_match_result.c.tenant_id == tenant_id,
                    schema.speaker_match_result.c.owning_unit_id == unit_id,
                    schema.speaker_match_result.c.match_run_id == run["id"],
                )
            )
        )
        if not set(speaker_ids) <= allowed:
            raise ValueError("invalid_shortlist")
        session.execute(
            sa.insert(submission).values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                owning_unit_id=unit_id,
                match_run_id=run["id"],
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
            )
        )
        for speaker_id in speaker_ids:
            record_id = uuid.uuid4()
            created = session.execute(
                insert(schema.speaker_event)
                .values(
                    id=record_id,
                    tenant_id=tenant_id,
                    owning_unit_id=unit_id,
                    event_id=run["event_id"],
                    speaker_id=speaker_id,
                    assigned_host_id=actor_id,
                )
                .on_conflict_do_nothing(constraint="uq_speaker_event_pair")
                .returning(schema.speaker_event.c.id)
            ).scalar_one_or_none()
            if created:
                session.execute(
                    sa.insert(schema.speaker_event_history).values(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        owning_unit_id=unit_id,
                        speaker_event_id=created,
                        from_status=None,
                        to_status="not_emailed_yet",
                        action_kind="created",
                        actor_id=actor_id,
                        idempotency_key=f"{idempotency_key}:{speaker_id}",
                    )
                )
        return self.list_records(
            session, tenant_id=tenant_id, unit_id=unit_id, event_id=run["event_id"]
        )

    def list_records(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        event_id: uuid.UUID | None = None,
    ) -> list[RowMapping]:
        se, sp, ev = schema.speaker_event, schema.speaker, schema.managed_event
        query = (
            sa.select(
                *se.c,
                sp.c.name.label("speaker_name"),
                sp.c.title.label("speaker_title"),
                sp.c.company.label("speaker_company"),
                ev.c.title.label("event_title"),
            )
            .join(sp, sa.and_(sp.c.tenant_id == se.c.tenant_id, sp.c.id == se.c.speaker_id))
            .join(ev, sa.and_(ev.c.tenant_id == se.c.tenant_id, ev.c.id == se.c.event_id))
            .where(se.c.tenant_id == tenant_id, se.c.owning_unit_id == unit_id)
        )
        if event_id:
            query = query.where(se.c.event_id == event_id)
        return list(session.execute(query.order_by(se.c.updated_at.desc())).mappings())

    def get_record(
        self, session: Session, *, tenant_id: uuid.UUID, unit_id: uuid.UUID, record_id: uuid.UUID
    ) -> RowMapping | None:
        return next(iter(self._record_query(session, tenant_id, unit_id, record_id)), None)

    def _record_query(
        self, session: Session, tenant_id: uuid.UUID, unit_id: uuid.UUID, record_id: uuid.UUID
    ):
        se, sp, ev = schema.speaker_event, schema.speaker, schema.managed_event
        return session.execute(
            sa.select(
                *se.c,
                sp.c.name.label("speaker_name"),
                sp.c.title.label("speaker_title"),
                sp.c.company.label("speaker_company"),
                ev.c.title.label("event_title"),
            )
            .join(sp, sa.and_(sp.c.tenant_id == se.c.tenant_id, sp.c.id == se.c.speaker_id))
            .join(ev, sa.and_(ev.c.tenant_id == se.c.tenant_id, ev.c.id == se.c.event_id))
            .where(
                se.c.tenant_id == tenant_id, se.c.owning_unit_id == unit_id, se.c.id == record_id
            )
        ).mappings()

    def history(
        self, session: Session, *, tenant_id: uuid.UUID, unit_id: uuid.UUID, record_id: uuid.UUID
    ) -> list[RowMapping]:
        return list(
            session.execute(
                sa.select(schema.speaker_event_history)
                .where(
                    schema.speaker_event_history.c.tenant_id == tenant_id,
                    schema.speaker_event_history.c.owning_unit_id == unit_id,
                    schema.speaker_event_history.c.speaker_event_id == record_id,
                )
                .order_by(schema.speaker_event_history.c.created_at)
            ).mappings()
        )

    def notes(
        self, session: Session, *, tenant_id: uuid.UUID, unit_id: uuid.UUID, record_id: uuid.UUID
    ) -> list[RowMapping]:
        return list(
            session.execute(
                sa.select(schema.speaker_event_note)
                .where(
                    schema.speaker_event_note.c.tenant_id == tenant_id,
                    schema.speaker_event_note.c.owning_unit_id == unit_id,
                    schema.speaker_event_note.c.speaker_event_id == record_id,
                )
                .order_by(schema.speaker_event_note.c.created_at)
            ).mappings()
        )

    def change_status(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        record_id: uuid.UUID,
        expected_version: int,
        to_status: str,
        actor_id: uuid.UUID,
        action_kind: str,
        idempotency_key: str | None,
        note: str | None = None,
        correction_reason: str | None = None,
    ) -> RowMapping | None:
        current = self.get_record(
            session, tenant_id=tenant_id, unit_id=unit_id, record_id=record_id
        )
        if not current:
            return None
        if idempotency_key:
            replay = session.scalar(
                sa.select(schema.speaker_event_history.c.id).where(
                    schema.speaker_event_history.c.tenant_id == tenant_id,
                    schema.speaker_event_history.c.owning_unit_id == unit_id,
                    schema.speaker_event_history.c.idempotency_key == idempotency_key,
                )
            )
            if replay:
                return current
        updated = (
            session.execute(
                sa.update(schema.speaker_event)
                .where(
                    schema.speaker_event.c.tenant_id == tenant_id,
                    schema.speaker_event.c.owning_unit_id == unit_id,
                    schema.speaker_event.c.id == record_id,
                    schema.speaker_event.c.version == expected_version,
                )
                .values(status=to_status, version=expected_version + 1, updated_at=sa.func.now())
                .returning(*schema.speaker_event.c)
            )
            .mappings()
            .one_or_none()
        )
        if not updated:
            raise RuntimeError("stale_version")
        session.execute(
            sa.insert(schema.speaker_event_history).values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                owning_unit_id=unit_id,
                speaker_event_id=record_id,
                from_status=current["status"],
                to_status=to_status,
                action_kind=action_kind,
                actor_id=actor_id,
                note=note,
                correction_reason=correction_reason,
                idempotency_key=idempotency_key,
            )
        )
        return self.get_record(session, tenant_id=tenant_id, unit_id=unit_id, record_id=record_id)

    def add_note(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        record_id: uuid.UUID,
        actor_id: uuid.UUID,
        body: str,
    ) -> RowMapping:
        return (
            session.execute(
                sa.insert(schema.speaker_event_note)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    owning_unit_id=unit_id,
                    speaker_event_id=record_id,
                    actor_id=actor_id,
                    body=body,
                )
                .returning(*schema.speaker_event_note.c)
            )
            .mappings()
            .one()
        )
