"""The Speaker Request write and read path (migration ``0024``).

Card ``CBA-EVENT-REQUEST``. A Speaker Request is not a new entity: customer §4
renames "Volunteer opportunity" to **Speaker Request**, and migration ``0024``
persists one as an ``event`` row plus its ``speaker_request_classification``
children. This module is the only writer of that child table, and it composes
:class:`~smartmatch_persistence.events.EventRepository` rather than reaching
into ``event`` itself, so ADR-0012's identity key keeps exactly one
implementation.

Idempotency is the identity key, not a header
===============================================

``submit_command`` requires an ``Idempotency-Key`` because a command creates
durable, possibly *paid* work whose only handle is a job id — two accepted
submissions are two jobs, and nothing about the payload can tell them apart
afterwards. A Speaker Request is the other shape: it has a deterministic natural
key already, from ADR-0012 — host org unit, folded title, resolved date — and
"two extractions producing the same key are the same event, and the second
updates the first rather than inserting" is a rule this repository committed to
before this card existed. ADR-0012 is explicit that manual entry is not exempt
from it.

So a re-filed request is the *same* request. :meth:`SpeakerRequestRepository.file`
returns :class:`SpeakerRequestWriteResult` with ``created`` read out of the
upsert itself, so an API layer can answer ``201`` for a new request and ``200``
for a resubmission without asking a second question whose answer could have
changed between the two. A header-based key on top of this would add a second,
weaker notion of sameness — same key, same body — beside a stronger one that is
already true of the data, and the two would disagree the first time a host fixed
a typo in a description and resubmitted.

Classifications are replaced, not accumulated
===============================================

A resubmission states the whole request. So :meth:`file` writes the draft's
targets and **deletes the ones the draft no longer names**, in the same
transaction. Accumulating instead would make a host removing "Finance" from
their request a no-op they could not see: the row would stay, the matcher would
keep weighting it, and nothing on screen would say why. The delete is scoped by
``(tenant_id, event_id)`` and by the exact ``(kind, code)`` pairs to keep, so it
can only ever touch this request's own rows.

The inserts are ``ON CONFLICT DO NOTHING`` on
``uq_speaker_request_classification`` — the natural key ``0024`` declares — so
re-filing an unchanged request is a no-op rather than a constraint violation,
the same discipline ``events.record_tags`` applies to ``event_tag``.

What this module does not do
==============================

No commit — transaction boundaries belong to the caller, like every other
repository here. No publication: ``ck_event_publishable`` and
``EventRepository.publish`` own that, and a filed request is ``unpublished`` /
``pending`` exactly as an extracted event is. No network, no URL, no fetch: a
Speaker Request is typed by a person, and :data:`ORIGIN_COORDINATOR_ENTRY` with
no ``EventProvenance`` is what ``ck_event_provenance_evidence`` requires of one.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime

import sqlalchemy as sa
from smartmatch_domain.speaker_requests import (
    SpeakerRequestClassification,
    SpeakerRequestDraft,
    classifications_of,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from smartmatch_persistence import schema
from smartmatch_persistence.events import ORIGIN_COORDINATOR_ENTRY, EventRepository

__all__ = [
    "SpeakerRequestRepository",
    "SpeakerRequestRow",
    "SpeakerRequestWriteResult",
]


@dataclass(frozen=True, slots=True)
class SpeakerRequestWriteResult:
    """What filing one Speaker Request did.

    Attributes:
        event_id: The ``event`` row holding the request.
        created: ``True`` when this call inserted the request, ``False`` when
            ADR-0012's identity key resolved it onto one already filed and this
            call updated it. See the module docstring on idempotency.
        classifications: The targets now stored, in ``(kind, code)`` order —
            what the request says after this call, not what this call changed.
    """

    event_id: uuid.UUID
    created: bool
    classifications: tuple[SpeakerRequestClassification, ...]


@dataclass(frozen=True, slots=True)
class SpeakerRequestRow:
    """One filed Speaker Request, as a Speaker Connector reads it (customer §13).

    Deliberately not an ``event`` row with extra fields. It carries no
    ``source_url``, ``fetched_at`` or ``extractor_version``, because a Speaker
    Request has none by construction — ``ck_event_provenance_evidence`` keeps
    all three NULL on a ``coordinator_entry`` row — and a read model with three
    permanently-null provenance fields invites a reader to wonder which
    extraction produced a request a person typed.

    Attributes:
        event_id: The request.
        title: What the host called it. Never carries its source (ADR-0012).
        description: §12's topic/description, or ``None``.
        time_precision: ADR-0010's discriminator — ``exact`` or ``date_only``.
            Never ``unresolved``: the domain refuses to build such a draft.
        starts_at: Present only at ``exact`` precision.
        ends_at: Present only when the host stated an end.
        on_date: Present only at ``date_only`` precision.
        time_zone: The IANA zone the event happens in (ADR-0010 rule 1).
        is_virtual: §12's physical/virtual switch.
        location_city: §10's city, or ``None`` — always ``None`` when virtual.
        location_postal_code: §10's ZIP, or ``None`` — same.
        publication_status: The event's own status, unchanged by filing.
        review_status: Likewise.
        created_at: When the request was first filed.
        updated_at: When it was last re-filed or otherwise written.
        classifications: Its targets, in ``(kind, code)`` order.
    """

    event_id: uuid.UUID
    title: str
    description: str | None
    time_precision: str
    starts_at: datetime | None
    ends_at: datetime | None
    on_date: date | None
    time_zone: str | None
    is_virtual: bool
    location_city: str | None
    location_postal_code: str | None
    publication_status: str
    review_status: str
    created_at: datetime
    updated_at: datetime
    classifications: tuple[SpeakerRequestClassification, ...]


class SpeakerRequestRepository:
    """Writes and reads Speaker Requests over ``event`` and its classifications.

    Takes a session per call and commits nothing, like every other repository in
    this package.
    """

    def __init__(self, events: EventRepository | None = None) -> None:
        """Compose the event writer rather than duplicating it.

        Injectable so a test can pass a repository it is watching, and defaulted
        so ordinary callers need not know this class writes ``event`` through
        another one.
        """
        self._events = events if events is not None else EventRepository()

    def file(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        host_org_unit_id: uuid.UUID,
        draft: SpeakerRequestDraft,
    ) -> SpeakerRequestWriteResult:
        """Store this Speaker Request, or update the one its key already names.

        ``origin`` is :data:`~smartmatch_persistence.events.ORIGIN_COORDINATOR_ENTRY`
        and ``provenance`` is ``None``, unconditionally and with no parameter
        that could change either. ADR-0012: "Manual event entry uses the same key
        and the same vocabulary. A coordinator typing an event is not exempt, or
        the duplicate class reopens through a second door" — and a request a
        person filed has no page anybody fetched, so a source URL on it would
        attribute their entry to a fetch that never happened.

        Args:
            session: The caller's session. Not committed here.
            tenant_id: From the authenticated principal, never from a body.
            host_org_unit_id: The unit the router already authorized against —
                ADR-0012's host component, and the scope every later
                authorization decision about this request is made in.
            draft: The validated request. Every rule it enforces is stated in
                ``smartmatch_domain.speaker_requests``; nothing is re-checked
                here, so a rule has one place to be read from.

        Returns:
            A :class:`SpeakerRequestWriteResult`.
        """
        outcome = self._events.upsert_returning_outcome(
            session,
            tenant_id=tenant_id,
            host_org_unit_id=host_org_unit_id,
            title=draft.title,
            event_time=draft.event_time,
            origin=ORIGIN_COORDINATOR_ENTRY,
            provenance=None,
            description=draft.description,
            is_virtual=draft.is_virtual,
            location_city=draft.location_city,
            location_postal_code=draft.location_postal_code,
        )

        classifications = classifications_of(draft)
        self._replace_classifications(
            session,
            tenant_id=tenant_id,
            event_id=outcome.event_id,
            classifications=classifications,
        )
        return SpeakerRequestWriteResult(
            event_id=outcome.event_id,
            created=outcome.created,
            classifications=classifications,
        )

    def get(
        self, session: Session, *, tenant_id: uuid.UUID, event_id: uuid.UUID
    ) -> SpeakerRequestRow | None:
        """One filed Speaker Request, or ``None`` when this tenant has no such row.

        Scoped by ``tenant_id`` in the query rather than filtered afterwards, and
        restricted to ``origin = 'coordinator_entry'``: an extracted event is not
        a Speaker Request, and returning one here would let a discovery row —
        provenance and all — reach a surface that promises a host typed it.
        """
        rows = self._rows(
            session,
            tenant_id=tenant_id,
            extra=(schema.event.c.id == event_id,),
            limit=1,
        )
        return rows[0] if rows else None

    def list_for_unit(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        host_org_unit_id: uuid.UUID,
        limit: int,
    ) -> tuple[SpeakerRequestRow, ...]:
        """This unit's filed Speaker Requests, soonest first, capped at ``limit``.

        Ordered by ``resolved_date`` then ``id``: a Speaker Connector working a
        queue wants the requests whose events happen next, and ``id`` breaks ties
        so two requests on one day never swap places between two identical reads
        — which is also what makes a truncation cut at a stable point.

        The caller passes ``limit`` and decides what to do about a full page;
        this method returns at most that many rows and says nothing about whether
        more exist, because a repository inventing a "truncated" flag would be a
        second opinion beside the route's own cap.
        """
        return self._rows(
            session,
            tenant_id=tenant_id,
            extra=(schema.event.c.host_org_unit_id == host_org_unit_id,),
            limit=limit,
        )

    # -----------------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------------

    def _replace_classifications(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        event_id: uuid.UUID,
        classifications: tuple[SpeakerRequestClassification, ...],
    ) -> None:
        """Make the stored targets equal to ``classifications``, exactly.

        Delete-then-insert rather than insert-only. See the module docstring: a
        request is restated in full on every filing, so a target the new draft
        does not name is a target the host removed, and leaving it behind would
        keep weighting a factor nobody asked for with nothing on screen to
        explain it.
        """
        keep = [(row.kind, row.code) for row in classifications]
        session.execute(
            sa.delete(schema.speaker_request_classification).where(
                schema.speaker_request_classification.c.tenant_id == tenant_id,
                schema.speaker_request_classification.c.event_id == event_id,
                # `not_in` over the composite: a target survives only if this
                # draft still names that exact (kind, code) pair. One predicate
                # rather than two so an industry code that happened to equal a
                # role code could not save the wrong row — impossible under the
                # two released vocabularies today, and not something a delete
                # should depend on staying impossible.
                sa.tuple_(
                    schema.speaker_request_classification.c.kind,
                    schema.speaker_request_classification.c.code,
                ).not_in(keep),
            )
        )
        for row in classifications:
            session.execute(
                postgresql.insert(schema.speaker_request_classification)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    event_id=event_id,
                    kind=row.kind,
                    code=row.code,
                    taxonomy_version=row.taxonomy_version,
                )
                .on_conflict_do_nothing(constraint="uq_speaker_request_classification")
            )

    def _rows(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        extra: tuple[sa.ColumnElement[bool], ...],
        limit: int,
    ) -> tuple[SpeakerRequestRow, ...]:
        """Read requests matching ``extra``, then their targets, in two queries.

        Two queries rather than one join: a join would multiply each request by
        its target count and leave the caller to fold the duplicates back, which
        is the shape that silently reports "three requests" when there are one
        request and three industries.
        """
        events = session.execute(
            sa.select(
                schema.event.c.id,
                schema.event.c.title,
                schema.event.c.description,
                schema.event.c.time_precision,
                schema.event.c.starts_at,
                schema.event.c.ends_at,
                schema.event.c.on_date,
                schema.event.c.time_zone,
                schema.event.c.is_virtual,
                schema.event.c.location_city,
                schema.event.c.location_postal_code,
                schema.event.c.publication_status,
                schema.event.c.review_status,
                schema.event.c.created_at,
                schema.event.c.updated_at,
            )
            .where(
                schema.event.c.tenant_id == tenant_id,
                schema.event.c.origin == ORIGIN_COORDINATOR_ENTRY,
                *extra,
            )
            .order_by(schema.event.c.resolved_date, schema.event.c.id)
            .limit(limit)
        ).all()
        if not events:
            return ()

        targets = self._classifications(
            session, tenant_id=tenant_id, event_ids=[row.id for row in events]
        )
        return tuple(
            SpeakerRequestRow(
                event_id=row.id,
                title=row.title,
                description=row.description,
                time_precision=row.time_precision,
                starts_at=row.starts_at,
                ends_at=row.ends_at,
                on_date=row.on_date,
                time_zone=row.time_zone,
                is_virtual=row.is_virtual,
                location_city=row.location_city,
                location_postal_code=row.location_postal_code,
                publication_status=row.publication_status,
                review_status=row.review_status,
                created_at=row.created_at,
                updated_at=row.updated_at,
                classifications=targets.get(row.id, ()),
            )
            for row in events
        )

    def _classifications(
        self, session: Session, *, tenant_id: uuid.UUID, event_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[SpeakerRequestClassification, ...]]:
        """Every listed request's targets, in one query, keyed by request."""
        rows = session.execute(
            sa.select(
                schema.speaker_request_classification.c.event_id,
                schema.speaker_request_classification.c.kind,
                schema.speaker_request_classification.c.code,
                schema.speaker_request_classification.c.taxonomy_version,
            )
            .where(
                schema.speaker_request_classification.c.tenant_id == tenant_id,
                schema.speaker_request_classification.c.event_id.in_(event_ids),
            )
            .order_by(
                schema.speaker_request_classification.c.event_id,
                schema.speaker_request_classification.c.kind,
                schema.speaker_request_classification.c.code,
            )
        ).all()
        grouped: dict[uuid.UUID, list[SpeakerRequestClassification]] = {}
        for row in rows:
            grouped.setdefault(row.event_id, []).append(
                SpeakerRequestClassification(
                    kind=str(row.kind),
                    code=str(row.code),
                    taxonomy_version=str(row.taxonomy_version),
                )
            )
        return {event_id: tuple(items) for event_id, items in grouped.items()}
