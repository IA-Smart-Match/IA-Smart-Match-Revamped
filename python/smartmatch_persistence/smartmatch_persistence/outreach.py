"""The outreach write and read paths (migration ``0021``, plan card L4).

Drafts, sends, the append-only delivery stream, and the suppression list. Like
every other repository here (``jobs.py``, ``outbox.py``, ``match_runs.py``), this
takes a :class:`~sqlalchemy.orm.Session` per call and **never commits**: the
transaction boundary belongs to whoever owns the unit of work, which on the send
path is the worker's executor, so a delivery record cannot become durable for a
job whose success the state machine refused.

## The one method worth reading first

:meth:`OutreachRepository.load_recipient` is where suppression is applied, and it
is a ``LEFT JOIN`` rather than a column read. Migration ``0021`` explains why
there is no ``suppressed`` flag on ``contact_channel``; this is the other half of
that decision. Every caller that asks "may we write to this person" gets the
answer computed from ``suppression_record`` at the moment they ask, so there is
no cached value to go stale between the unsubscribe and the send.

The join is on **address**, not on contact id, because a suppression is a
statement about a person rather than about a row. If the same address were later
re-added as a contact under a different unit, a channel-scoped suppression would
silently fail to cover it — which is the failure mode where somebody who
unsubscribed starts receiving mail again, and nothing in the system looks wrong.

## Re-drive must not send twice

:meth:`reserve_send` is ``ON CONFLICT ON CONSTRAINT uq_outreach_send_job DO
NOTHING`` followed by a read of whatever row now holds that key —
``MatchRunRepository.record``'s pattern, and here it is load-bearing rather than
merely tidy. A handler can execute more than once for one job: a worker can die
after committing its business write and before the executor's terminal
transition commits, and the operator's fix is a re-drive of the identical
payload. Without the constraint, that re-drive would put a second copy of the
same message in someone's inbox.

:attr:`SendReservation.was_already_reserved` is what tells the handler which
attempt it is on, so a re-drive can skip the provider call entirely rather than
discover the duplicate afterwards.

## Nothing here decides whether a send is allowed

There is no consent logic in this module. :meth:`load_recipient` reports the
facts — lifecycle state, consent source, whether a suppression exists — and
``smartmatch_domain.outreach.assert_send_allowed`` decides what they mean. A
repository that refused to return an ineligible recipient would be a second
place the policy lives, and the one place it would be invisible: a caller
holding an empty result cannot tell "no such contact" from "not allowed", and
those two need different job outcomes.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = [
    "DEFAULT_DRAFT_PAGE_SIZE",
    "MAX_DRAFT_PAGE_SIZE",
    "DraftRow",
    "OutreachRepository",
    "RecipientFacts",
    "SendReservation",
    "SendRow",
    "SuppressionOutcome",
]

#: How many drafts a coordinator listing returns when it does not say. Small
#: enough that a page is a screen rather than an export.
DEFAULT_DRAFT_PAGE_SIZE: Final[int] = 25

#: The ceiling a caller may request. A bound applied in SQL rather than after
#: the fetch, so a caller asking for everything gets a shorter answer from a
#: route that says how many it returned — never a silently truncated one, which
#: is the shape ``units_in_subtree`` refuses for the same reason.
MAX_DRAFT_PAGE_SIZE: Final[int] = 200


@dataclass(frozen=True, slots=True)
class RecipientFacts:
    """Everything the send gate needs to know about one addressee.

    Deliberately facts and not a verdict. See the module docstring: the decision
    is ``smartmatch_domain.outreach.assert_send_allowed``'s, and it needs each
    of these separately in order to say *which* condition failed — a caller
    handed a boolean could only report that something did.

    Attributes:
        contact_channel_id: The row these facts came from.
        address: The address as stored now. The send record snapshots its own
            copy, so a later correction does not rewrite history.
        contact_state: The contact-confidence lifecycle state, as text. Coerced
            to :class:`~smartmatch_domain.consent.ContactState` by the caller,
            which is the layer that owns that vocabulary.
        consent_source: As text, or ``None`` when no consent is recorded.
        suppressed: Whether a ``suppression_record`` covers this address, right
            now. Computed by a join on every read — never cached.
    """

    contact_channel_id: uuid.UUID
    professional_id: uuid.UUID
    owning_unit_id: uuid.UUID
    address: str
    contact_state: str
    consent_source: str | None
    suppressed: bool


@dataclass(frozen=True, slots=True)
class DraftRow:
    """One stored draft, as a coordinator surface reads it."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    owning_unit_id: uuid.UUID
    contact_channel_id: uuid.UUID
    template_id: str
    content_status: str
    subject: str
    body: str
    status: str
    created_by: uuid.UUID
    created_at: datetime
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    superseded_by_draft_id: uuid.UUID | None


@dataclass(frozen=True, slots=True)
class SendRow:
    """One send attempt and its outcome, if it has reached one yet.

    :attr:`disposition` is ``None`` for an attempt in flight. That is a third
    state, not a missing value, and a reader must render it as "in progress"
    rather than as any kind of failure — an attempt whose outcome is unknown is
    exactly the case ADR-0011 forbids collapsing into a default.
    """

    id: uuid.UUID
    tenant_id: uuid.UUID
    owning_unit_id: uuid.UUID
    draft_id: uuid.UUID
    job_id: uuid.UUID
    idempotency_key: str
    recipient_address: str
    from_address: str
    disposition: str | None
    provider: str | None
    provider_message_id: str | None
    failure_reason: str | None
    created_at: datetime
    concluded_at: datetime | None


@dataclass(frozen=True, slots=True)
class SendReservation:
    """The result of claiming the right to send one message.

    Attributes:
        send_id: The row that now holds this job's key — on a re-drive, the
            *first* execution's id, not the one this call proposed.
        was_already_reserved: ``True`` when this call found the reservation
            rather than wrote it, which is exactly the re-drive case. A handler
            that sees ``True`` must not call the provider again: the first
            execution either already did, or already recorded why it would not.
        recipient_address: The address snapshotted on the stored row, read back
            rather than assumed, so a re-drive reports what was actually sent to.
    """

    send_id: uuid.UUID
    was_already_reserved: bool
    recipient_address: str
    disposition: str | None


@dataclass(frozen=True, slots=True)
class SuppressionOutcome:
    """What happened when an unsubscribe was recorded.

    Attributes:
        address: The address now suppressed.
        was_already_suppressed: ``True`` when a suppression already covered this
            address. Reported rather than swallowed, and both cases are
            successes — a person clicking unsubscribe twice has not made an
            error, and showing them one would be alarming for no reason.
    """

    address: str
    was_already_suppressed: bool


class OutreachRepository:
    """Reads and writes the five ``0021`` tables. Stateless; one instance serves all."""

    # -----------------------------------------------------------------------
    # Contacts
    # -----------------------------------------------------------------------

    def load_recipient(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        contact_channel_id: uuid.UUID,
    ) -> RecipientFacts | None:
        """Read one contact plus a live suppression check, or ``None``.

        ``tenant_id`` is part of the lookup rather than a filter applied
        afterwards, so a caller cannot read another tenant's contact by id —
        the rule ``JobRepository.get`` states and every repository here keeps.

        The suppression is a ``LEFT JOIN`` on address evaluated at read time.
        See the module docstring for why it is on address and why it is not a
        column.

        Returns:
            The facts, or ``None`` when no such contact exists in this tenant.
            ``None`` means "no such contact" and never "not allowed" — the
            second is a decision this module does not make.
        """
        suppression = schema.suppression_record
        channel = schema.contact_channel

        row = session.execute(
            sa.select(
                channel.c.id,
                channel.c.professional_id,
                channel.c.owning_unit_id,
                channel.c.address,
                channel.c.contact_state,
                channel.c.consent_source,
                (suppression.c.id.isnot(None)).label("suppressed"),
            )
            .select_from(
                channel.outerjoin(
                    suppression,
                    sa.and_(
                        suppression.c.tenant_id == channel.c.tenant_id,
                        suppression.c.address == channel.c.address,
                    ),
                )
            )
            .where(
                channel.c.tenant_id == tenant_id,
                channel.c.id == contact_channel_id,
            )
        ).one_or_none()

        if row is None:
            return None

        return RecipientFacts(
            contact_channel_id=row.id,
            professional_id=row.professional_id,
            owning_unit_id=row.owning_unit_id,
            address=row.address,
            contact_state=row.contact_state,
            consent_source=row.consent_source,
            suppressed=bool(row.suppressed),
        )

    # -----------------------------------------------------------------------
    # Drafts
    # -----------------------------------------------------------------------

    def create_draft(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        contact_channel_id: uuid.UUID,
        template_id: str,
        content_status: str,
        subject: str,
        body: str,
        created_by: uuid.UUID,
        status: str,
        approved_by: uuid.UUID | None = None,
        approved_at: datetime | None = None,
        draft_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Insert one draft and return its id.

        The rendered ``subject`` and ``body`` are stored as given. This module
        does not render, and could not: the template registry is
        ``smartmatch_domain``'s and the persistence layer may not reach into it
        (the "Layering" import contract runs one way). Storing text the domain
        composed, rather than the ingredients to recompose it, is also what makes
        an approval binding — see migration ``0021``'s column comment.

        ``status`` and the approval columns are the caller's, because who may
        approve is an authorization question the router answers. What this
        method guarantees is only that the database's own consistency rules
        apply: ``ck_outreach_draft_approved_has_approver`` refuses an approved
        draft with no approver regardless of what any caller intended.
        """
        new_id = draft_id or uuid.uuid4()
        session.execute(
            sa.insert(schema.outreach_draft).values(
                id=new_id,
                tenant_id=tenant_id,
                owning_unit_id=owning_unit_id,
                contact_channel_id=contact_channel_id,
                template_id=template_id,
                content_status=content_status,
                subject=subject,
                body=body,
                status=status,
                created_by=created_by,
                approved_by=approved_by,
                approved_at=approved_at,
            )
        )
        return new_id

    def get_draft(
        self, session: Session, *, tenant_id: uuid.UUID, draft_id: uuid.UUID
    ) -> DraftRow | None:
        """Read one draft, scoped to its tenant, or ``None``."""
        row = session.execute(
            sa.select(schema.outreach_draft).where(
                schema.outreach_draft.c.tenant_id == tenant_id,
                schema.outreach_draft.c.id == draft_id,
            )
        ).one_or_none()
        return None if row is None else _to_draft(row)

    def list_drafts(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        limit: int = DEFAULT_DRAFT_PAGE_SIZE,
        offset: int = 0,
    ) -> list[DraftRow]:
        """One unit's drafts, newest first.

        ``limit`` is clamped to :data:`MAX_DRAFT_PAGE_SIZE` here rather than
        trusted, so a route that forgets to validate it cannot turn a listing
        into a table scan.
        """
        bounded = max(1, min(limit, MAX_DRAFT_PAGE_SIZE))
        rows = session.execute(
            sa.select(schema.outreach_draft)
            .where(
                schema.outreach_draft.c.tenant_id == tenant_id,
                schema.outreach_draft.c.owning_unit_id == owning_unit_id,
            )
            .order_by(schema.outreach_draft.c.created_at.desc(), schema.outreach_draft.c.id)
            .limit(bounded)
            .offset(max(0, offset))
        ).all()
        return [_to_draft(row) for row in rows]

    # -----------------------------------------------------------------------
    # Sends
    # -----------------------------------------------------------------------

    def reserve_send(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        draft_id: uuid.UUID,
        job_id: uuid.UUID,
        idempotency_key: str,
        recipient_address: str,
        from_address: str,
        unsubscribe_token_hash: str,
        send_id: uuid.UUID | None = None,
    ) -> SendReservation:
        """Claim the right to send this draft once, and report whether we got it.

        ``ON CONFLICT ON CONSTRAINT uq_outreach_send_job DO NOTHING``, then read
        back whatever row holds the key. By constraint *name* rather than by
        column list, because the name is what ``schema.py`` mirrors and what the
        migration declares; an inferred conflict target would be a second
        spelling of the same key that nothing checks.

        The read-back is not a formality. ``rowcount`` would say whether a row
        landed but not what is stored, and on a re-drive the durable row is the
        first execution's — with its id, its snapshotted address, and possibly
        an outcome already recorded. Reporting this call's proposed id would
        attribute the send to the retry.

        Returns:
            A :class:`SendReservation`. A caller seeing
            ``was_already_reserved=True`` must not call the provider.
        """
        proposed_id = send_id or uuid.uuid4()

        session.execute(
            postgresql.insert(schema.outreach_send)
            .values(
                id=proposed_id,
                tenant_id=tenant_id,
                owning_unit_id=owning_unit_id,
                draft_id=draft_id,
                job_id=job_id,
                idempotency_key=idempotency_key,
                recipient_address=recipient_address,
                from_address=from_address,
                unsubscribe_token_hash=unsubscribe_token_hash,
            )
            .on_conflict_do_nothing(constraint="uq_outreach_send_job")
        )

        row = session.execute(
            sa.select(
                schema.outreach_send.c.id,
                schema.outreach_send.c.recipient_address,
                schema.outreach_send.c.disposition,
            ).where(
                schema.outreach_send.c.tenant_id == tenant_id,
                schema.outreach_send.c.job_id == job_id,
            )
        ).one()

        return SendReservation(
            send_id=row.id,
            was_already_reserved=row.id != proposed_id,
            recipient_address=row.recipient_address,
            disposition=row.disposition,
        )

    def conclude_send(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        send_id: uuid.UUID,
        disposition: str,
        concluded_at: datetime,
        provider: str | None = None,
        provider_message_id: str | None = None,
        failure_reason: str | None = None,
    ) -> bool:
        """Record how a send attempt ended. Returns whether this call wrote it.

        Guarded by ``disposition IS NULL`` in the ``WHERE`` clause, so a
        conclusion is written exactly once and a second attempt to conclude an
        already-concluded send changes nothing and says so. That guard is the
        same shape ``ReviewRepository.decide`` uses, and it exists here for a
        sharper reason: overwriting an ``accepted`` disposition with a later
        ``failed`` would erase the record of a message that is already in
        somebody's inbox.

        The database enforces the rest — a ``provider_message_id`` is only
        storable alongside ``accepted``, an acceptance must name its provider,
        and a refusal must carry a reason — so a caller cannot record a
        half-described outcome even by trying.

        Returns:
            ``True`` when this call recorded the conclusion; ``False`` when the
            send had already concluded or does not exist.
        """
        # ``RETURNING`` rather than ``rowcount``, the shape ``jobs.py`` and
        # ``outbox.py`` both use and for their reason: ``rowcount`` lives on
        # ``CursorResult``, which ``Session.execute`` is not typed as returning,
        # so reading it costs a cast that says nothing about the query.
        written = session.execute(
            sa.update(schema.outreach_send)
            .where(
                schema.outreach_send.c.tenant_id == tenant_id,
                schema.outreach_send.c.id == send_id,
                schema.outreach_send.c.disposition.is_(None),
            )
            .values(
                disposition=disposition,
                concluded_at=concluded_at,
                provider=provider,
                provider_message_id=provider_message_id,
                failure_reason=failure_reason,
            )
            .returning(schema.outreach_send.c.id)
        ).one_or_none()
        return written is not None

    def get_send(
        self, session: Session, *, tenant_id: uuid.UUID, send_id: uuid.UUID
    ) -> SendRow | None:
        """Read one send, scoped to its tenant, or ``None``."""
        row = session.execute(
            sa.select(schema.outreach_send).where(
                schema.outreach_send.c.tenant_id == tenant_id,
                schema.outreach_send.c.id == send_id,
            )
        ).one_or_none()
        return None if row is None else _to_send(row)

    def get_send_for_job(
        self, session: Session, *, tenant_id: uuid.UUID, job_id: uuid.UUID
    ) -> SendRow | None:
        """Read the send a given command produced, or ``None`` if it produced none.

        ``None`` is a real answer and a common one: a job that has been accepted
        but not yet executed has no send row, because the row is written by the
        handler rather than by the route. A caller must not read that absence as
        a failure.
        """
        row = session.execute(
            sa.select(schema.outreach_send).where(
                schema.outreach_send.c.tenant_id == tenant_id,
                schema.outreach_send.c.job_id == job_id,
            )
        ).one_or_none()
        return None if row is None else _to_send(row)

    def resolve_unsubscribe_token(self, session: Session, *, token_hash: str) -> sa.Row[Any] | None:
        """Find the send a token belongs to, across every tenant.

        Deliberately **not** tenant-scoped, which is the one place in this module
        that departs from the rule every other method keeps. The unsubscribe POST
        is unauthenticated by design — RFC 8058 one-click arrives with no session
        at all — so there is no tenant to scope by, and the token itself is the
        entire authorization. Migration ``0021`` makes that safe by requiring the
        hash to be globally unique and by never storing the token, so possession
        of a database row does not confer the ability to unsubscribe anyone.

        Returns:
            The tenant, address, and send id, or ``None`` for a token that
            matches nothing. A caller must answer identically either way: telling
            a stranger whether a token is real is telling them whether an address
            is on our list.
        """
        return session.execute(
            sa.select(
                schema.outreach_send.c.id,
                schema.outreach_send.c.tenant_id,
                schema.outreach_send.c.recipient_address,
            ).where(schema.outreach_send.c.unsubscribe_token_hash == token_hash)
        ).one_or_none()

    # -----------------------------------------------------------------------
    # Delivery events
    # -----------------------------------------------------------------------

    def append_delivery_event(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        send_id: uuid.UUID,
        event_type: str,
        occurred_at: datetime,
        provider_event_id: str | None = None,
        detail: Mapping[str, Any] | None = None,
        event_id: uuid.UUID | None = None,
    ) -> uuid.UUID | None:
        """Append one event to a send's stream, or report a duplicate.

        ``ON CONFLICT DO NOTHING`` against
        ``uq_delivery_event_provider_event``, so a provider webhook delivered
        twice becomes one event rather than two bounces. Events this platform
        writes itself pass ``provider_event_id=None`` and never collide, because
        PostgreSQL treats NULLs as distinct in a unique index — which is why the
        constraint can cover both cases without a partial index.

        There is no update method, and that absence is the API: migration
        ``0021``'s trigger refuses an ``UPDATE`` outright, and a later fact about
        a message is a new event.

        Returns:
            The event's id, or ``None`` when an event with this provider id was
            already recorded for this send.
        """
        new_id = event_id or uuid.uuid4()
        result = session.execute(
            postgresql.insert(schema.delivery_event)
            .values(
                id=new_id,
                tenant_id=tenant_id,
                send_id=send_id,
                event_type=event_type,
                occurred_at=occurred_at,
                provider_event_id=provider_event_id,
                # ``sa.null()`` rather than ``None``. SQLAlchemy maps a Python
                # ``None`` bound to a JSONB column to the JSON value ``null``,
                # not to SQL NULL — so "this event carries no detail" would be
                # stored as a JSON document that says nothing, which is a
                # different fact and one ``ck_delivery_event_detail_object``
                # correctly refuses. The same ADR-0011 rule as everywhere else
                # here: absent is not a value.
                detail=dict(detail) if detail is not None else sa.null(),
            )
            .on_conflict_do_nothing(constraint="uq_delivery_event_provider_event")
            .returning(schema.delivery_event.c.id)
        ).one_or_none()
        return None if result is None else result.id

    def list_delivery_events(
        self, session: Session, *, tenant_id: uuid.UUID, send_id: uuid.UUID
    ) -> Sequence[sa.Row[Any]]:
        """One send's events, oldest first by when they happened.

        Ordered by ``occurred_at`` rather than by ``recorded_at``: the stream
        describes what happened to a message, and a bounce that arrived late is
        still a bounce that happened when it happened. Ties break on
        ``recorded_at`` so the order is total and a projection over it is
        deterministic.
        """
        return session.execute(
            sa.select(schema.delivery_event)
            .where(
                schema.delivery_event.c.tenant_id == tenant_id,
                schema.delivery_event.c.send_id == send_id,
            )
            .order_by(
                schema.delivery_event.c.occurred_at,
                schema.delivery_event.c.recorded_at,
                schema.delivery_event.c.id,
            )
        ).all()

    # -----------------------------------------------------------------------
    # Suppression
    # -----------------------------------------------------------------------

    def suppress(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        address: str,
        source: str,
        suppressed_at: datetime,
        origin_send_id: uuid.UUID | None = None,
        record_id: uuid.UUID | None = None,
    ) -> SuppressionOutcome:
        """Record that an address must not be written to again.

        ``ON CONFLICT ON CONSTRAINT uq_suppression_record_address DO NOTHING``:
        a repeated unsubscribe is the same instruction, not a second one, and
        turning it into an integrity error would surface a database constraint
        to somebody who did nothing wrong.

        The **first** suppression is the one that stands. A second call does not
        move ``suppressed_at`` forward, because "when did they ask us to stop" is
        the question that matters and the answer is the first time they asked.
        """
        session.execute(
            postgresql.insert(schema.suppression_record)
            .values(
                id=record_id or uuid.uuid4(),
                tenant_id=tenant_id,
                address=address,
                source=source,
                suppressed_at=suppressed_at,
                origin_send_id=origin_send_id,
            )
            .on_conflict_do_nothing(constraint="uq_suppression_record_address")
        )

        existing = session.execute(
            sa.select(schema.suppression_record.c.suppressed_at).where(
                schema.suppression_record.c.tenant_id == tenant_id,
                schema.suppression_record.c.address == address,
            )
        ).one()

        return SuppressionOutcome(
            address=address,
            was_already_suppressed=existing.suppressed_at != suppressed_at,
        )

    def is_suppressed(self, session: Session, *, tenant_id: uuid.UUID, address: str) -> bool:
        """Whether a suppression currently covers this address in this tenant."""
        return (
            session.execute(
                sa.select(sa.literal(1)).where(
                    schema.suppression_record.c.tenant_id == tenant_id,
                    schema.suppression_record.c.address == address,
                )
            ).first()
            is not None
        )


def _to_draft(row: sa.Row[Any]) -> DraftRow:
    """Narrow a ``outreach_draft`` row to the record callers read."""
    return DraftRow(
        id=row.id,
        tenant_id=row.tenant_id,
        owning_unit_id=row.owning_unit_id,
        contact_channel_id=row.contact_channel_id,
        template_id=row.template_id,
        content_status=row.content_status,
        subject=row.subject,
        body=row.body,
        status=row.status,
        created_by=row.created_by,
        created_at=row.created_at,
        approved_by=row.approved_by,
        approved_at=row.approved_at,
        superseded_by_draft_id=row.superseded_by_draft_id,
    )


def _to_send(row: sa.Row[Any]) -> SendRow:
    """Narrow an ``outreach_send`` row to the record callers read."""
    return SendRow(
        id=row.id,
        tenant_id=row.tenant_id,
        owning_unit_id=row.owning_unit_id,
        draft_id=row.draft_id,
        job_id=row.job_id,
        idempotency_key=row.idempotency_key,
        recipient_address=row.recipient_address,
        from_address=row.from_address,
        disposition=row.disposition,
        provider=row.provider,
        provider_message_id=row.provider_message_id,
        failure_reason=row.failure_reason,
        created_at=row.created_at,
        concluded_at=row.concluded_at,
    )
