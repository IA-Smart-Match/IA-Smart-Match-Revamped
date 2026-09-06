"""The invitation write and read paths (migration ``0029``, card CBA-INVITATIONS).

Batches, the invitations in them, and the answers Speakers gave. Like every other
repository here this takes a :class:`~sqlalchemy.orm.Session` per call and
**never commits**: the transaction boundary belongs to whoever owns the unit of
work. ``get_session`` rolls back unconditionally, so a route that forgets to
commit returns a clean ``2xx`` and stores nothing — which is why the tests that
matter here assert against the tables rather than against a status code.

## Delivery and response are read from two places, and that is on purpose

:meth:`InvitationRepository.list_invitations` returns
:class:`InvitationWithDelivery`: an invitation, and *separately* the
:class:`DeliveryFacts` of the send its job produced, or ``None`` when no send
exists yet. Two nested records rather than one flattened row, because the
flattening is the bug this whole card exists to prevent — a provider saying
``accepted`` is a mail system taking custody, and
``response_status='accepted_invitation'`` is a human being agreeing to come and
talk to students, and a reader who can reach both through one field will
eventually read one as the other.

``DeliveryFacts`` is ``None`` for an invitation that has not been dispatched, and
its ``disposition`` is ``None`` for one that has been dispatched and not yet
concluded. Those are two different unknowns and neither is a failure: the first
means nothing was submitted, the second means an attempt is in flight, and
collapsing either into "not delivered" is the ADR-0011 shape.

## Nothing here decides anything

There is no eligibility logic in this module and no state machine. Whether a
recipient may be invited is
``smartmatch_domain.cba_invitations.classify_recipient``'s, and whether an answer
may replace an existing one is ``record_response``'s — both in the domain layer,
which is the layer that owns those vocabularies. What this module guarantees is
only that the database's own rules apply: ``ck_cba_invitation_response_status``
refuses a response word no Speaker could have said, and
``uq_cba_invitation_batch_recipient`` refuses a second invitation for one person
in one batch regardless of what any caller intended.

## Two guarded updates, for ``conclude_send``'s reason

:meth:`InvitationRepository.mark_dispatched` and
:meth:`InvitationRepository.record_response` both carry their precondition in the
``WHERE`` clause and report whether they wrote. A dispatch that re-submitted an
already-dispatched invitation would put a second copy of an invitation in
somebody's inbox; a response that overwrote an existing one would erase a fact an
Event Host may already have acted on. Both return ``False`` rather than raising,
because "somebody got there first" is an outcome the caller has to describe, not
an error.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = [
    "DEFAULT_BATCH_PAGE_SIZE",
    "MAX_BATCH_PAGE_SIZE",
    "BatchReservation",
    "BatchRow",
    "DeliveryFacts",
    "InvitationRepository",
    "InvitationRow",
    "InvitationWithDelivery",
]

#: How many batches a Connector's listing returns when it does not say, and the
#: ceiling it may ask for. The same two numbers as the outreach draft and send
#: listings, deliberately: all three are a coordinator's screen over the same
#: unit's outreach, and a reader of one page size should not have to wonder why
#: another differs.
DEFAULT_BATCH_PAGE_SIZE: Final[int] = 25
MAX_BATCH_PAGE_SIZE: Final[int] = 200


@dataclass(frozen=True, slots=True)
class BatchRow:
    """One batch of invitations, as a Connector reads it back."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    owning_unit_id: uuid.UUID
    idempotency_key: str
    match_run_id: uuid.UUID | None
    template_id: str
    event_name: str
    event_date: str
    created_by_user_id: uuid.UUID
    created_at: datetime


@dataclass(frozen=True, slots=True)
class BatchReservation:
    """The result of claiming an idempotency key for one unit.

    Attributes:
        batch: The row that now holds the key — on a replay, the *first*
            submission's, never the one this call proposed.
        was_replayed: ``True`` when this call found the batch rather than wrote
            it. A caller seeing ``True`` must not compose or invite anybody: the
            first submission already decided who was invited and who was skipped,
            and re-deciding would produce a second set of messages under a key
            whose whole purpose is to prevent exactly that.
    """

    batch: BatchRow
    was_replayed: bool


@dataclass(frozen=True, slots=True)
class InvitationRow:
    """One named recipient's outcome, and the answer they gave if they gave one.

    Carries **no delivery field**. Whether a message reached anybody is
    :class:`DeliveryFacts`, read through ``outreach_send_job_id``, and the
    separation is structural rather than stylistic — see the module docstring.

    Attributes:
        status: ``pending``, ``dispatched`` or ``skipped``. Says what this
            platform did, never what the recipient did.
        skip_reason: Present exactly when ``status`` is ``skipped``.
        response_status: What the *Speaker* said — ``awaiting_response``,
            ``accepted_invitation`` or ``declined_invitation``. Never a
            provider's word.
        response_channel: ``speaker_link`` when the Speaker followed the link in
            their own invitation, ``connector_recorded`` when a coordinator
            entered what they were told. Kept apart because the second is a
            weaker evidentiary claim and a surface that showed them alike would
            assert a directness nobody has.
    """

    id: uuid.UUID
    tenant_id: uuid.UUID
    owning_unit_id: uuid.UUID
    batch_id: uuid.UUID
    professional_id: uuid.UUID
    status: str
    skip_reason: str | None
    contact_channel_id: uuid.UUID | None
    recipient_address: str | None
    outreach_draft_id: uuid.UUID | None
    outreach_send_job_id: uuid.UUID | None
    dispatched_at: datetime | None
    response_status: str
    response_recorded_at: datetime | None
    response_channel: str | None
    response_recorded_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class DeliveryFacts:
    """What happened to the *message*, as ``outreach_send`` records it.

    A separate record from :class:`InvitationRow` so that no single object offers
    a caller one field that could mean either fact. ``disposition`` is ``None``
    while an attempt is in flight — a third state, rendered as in-progress and
    never as a failure — and this whole record is ``None`` when no send exists at
    all, which is a different unknown again.
    """

    send_id: uuid.UUID
    disposition: str | None
    provider: str | None
    failure_reason: str | None
    concluded_at: datetime | None


@dataclass(frozen=True, slots=True)
class InvitationWithDelivery:
    """One invitation and, separately, what became of the message it sent."""

    invitation: InvitationRow
    delivery: DeliveryFacts | None


class InvitationRepository:
    """Reads and writes the two ``0029`` tables. Stateless; one instance serves all."""

    # -----------------------------------------------------------------------
    # Batches
    # -----------------------------------------------------------------------

    def reserve_batch(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        idempotency_key: str,
        template_id: str,
        event_name: str,
        event_date: str,
        created_by_user_id: uuid.UUID,
        match_run_id: uuid.UUID | None = None,
        batch_id: uuid.UUID | None = None,
    ) -> BatchReservation:
        """Claim this unit's idempotency key for one batch, and say who got it.

        ``ON CONFLICT ON CONSTRAINT uq_cba_invitation_batch_key DO NOTHING``
        followed by a read of whatever row now holds the key —
        ``OutreachRepository.reserve_send``'s pattern, and load-bearing here for
        the same reason it is there. Without it, a Connector who double-clicked
        Send would compose a second set of drafts and a second set of
        invitations, and the second set would go to the same inboxes.

        The read-back is not a formality: on a replay the durable row is the
        first submission's, with its id, its template and its event text.
        Reporting this call's proposed id would attribute the batch to the retry
        and orphan every invitation already filed under the original.

        Returns:
            A :class:`BatchReservation`. A caller seeing ``was_replayed=True``
            must invite nobody and must report the *stored* outcomes.
        """
        proposed_id = batch_id or uuid.uuid4()

        session.execute(
            postgresql.insert(schema.cba_invitation_batch)
            .values(
                id=proposed_id,
                tenant_id=tenant_id,
                owning_unit_id=owning_unit_id,
                idempotency_key=idempotency_key,
                match_run_id=match_run_id,
                template_id=template_id,
                event_name=event_name,
                event_date=event_date,
                created_by_user_id=created_by_user_id,
            )
            .on_conflict_do_nothing(constraint="uq_cba_invitation_batch_key")
        )

        row = session.execute(
            sa.select(schema.cba_invitation_batch).where(
                schema.cba_invitation_batch.c.tenant_id == tenant_id,
                schema.cba_invitation_batch.c.owning_unit_id == owning_unit_id,
                schema.cba_invitation_batch.c.idempotency_key == idempotency_key,
            )
        ).one()

        return BatchReservation(batch=_to_batch(row), was_replayed=row.id != proposed_id)

    def get_batch(
        self, session: Session, *, tenant_id: uuid.UUID, batch_id: uuid.UUID
    ) -> BatchRow | None:
        """Read one batch, scoped to its tenant, or ``None``.

        ``tenant_id`` is part of the lookup rather than a filter applied
        afterwards, so a caller cannot read another tenant's batch by id.
        """
        row = session.execute(
            sa.select(schema.cba_invitation_batch).where(
                schema.cba_invitation_batch.c.tenant_id == tenant_id,
                schema.cba_invitation_batch.c.id == batch_id,
            )
        ).one_or_none()
        return None if row is None else _to_batch(row)

    def list_batches(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        limit: int = DEFAULT_BATCH_PAGE_SIZE,
        offset: int = 0,
    ) -> list[BatchRow]:
        """One unit's batches, newest first.

        ``limit`` is clamped here as well as at the route, for ``list_drafts``'s
        reason: a bound that lives only in a route stops applying the moment a
        second caller appears.
        """
        bounded = max(1, min(limit, MAX_BATCH_PAGE_SIZE))
        rows = session.execute(
            sa.select(schema.cba_invitation_batch)
            .where(
                schema.cba_invitation_batch.c.tenant_id == tenant_id,
                schema.cba_invitation_batch.c.owning_unit_id == owning_unit_id,
            )
            .order_by(
                schema.cba_invitation_batch.c.created_at.desc(),
                schema.cba_invitation_batch.c.id,
            )
            .limit(bounded)
            .offset(max(0, offset))
        ).all()
        return [_to_batch(row) for row in rows]

    # -----------------------------------------------------------------------
    # Invitations
    # -----------------------------------------------------------------------

    def add_invitation(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        batch_id: uuid.UUID,
        professional_id: uuid.UUID,
        status: str,
        response_status: str,
        skip_reason: str | None = None,
        contact_channel_id: uuid.UUID | None = None,
        recipient_address: str | None = None,
        outreach_draft_id: uuid.UUID | None = None,
        response_token_hash: str | None = None,
        invitation_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Record one named recipient's outcome and return its id.

        ``status`` and ``skip_reason`` are the caller's, because *why* somebody
        was skipped is a policy question the domain answers and this module does
        not second-guess. What is guaranteed here is that the database's own
        consistency rules apply: ``ck_cba_invitation_addressed`` refuses a
        skipped row carrying an address, and
        ``ck_cba_invitation_skipped_unanswered`` refuses one carrying an answer —
        so a recipient nobody wrote to cannot be recorded as having accepted.

        ``response_status`` has no default. An invitation's initial state is a
        value somebody wrote, not one the database supplied, which is what keeps
        "who decided this was awaiting a response" answerable.
        """
        new_id = invitation_id or uuid.uuid4()
        session.execute(
            sa.insert(schema.cba_invitation).values(
                id=new_id,
                tenant_id=tenant_id,
                owning_unit_id=owning_unit_id,
                batch_id=batch_id,
                professional_id=professional_id,
                status=status,
                skip_reason=skip_reason,
                contact_channel_id=contact_channel_id,
                recipient_address=recipient_address,
                outreach_draft_id=outreach_draft_id,
                response_status=response_status,
                response_token_hash=response_token_hash,
            )
        )
        return new_id

    def get_invitation(
        self, session: Session, *, tenant_id: uuid.UUID, invitation_id: uuid.UUID
    ) -> InvitationRow | None:
        """Read one invitation, scoped to its tenant, or ``None``."""
        row = session.execute(
            sa.select(schema.cba_invitation).where(
                schema.cba_invitation.c.tenant_id == tenant_id,
                schema.cba_invitation.c.id == invitation_id,
            )
        ).one_or_none()
        return None if row is None else _to_invitation(row)

    def list_invitations(
        self, session: Session, *, tenant_id: uuid.UUID, batch_id: uuid.UUID
    ) -> list[InvitationWithDelivery]:
        """Every outcome in one batch, with each message's delivery beside it.

        Not paged, and bounded instead by ``MAX_BATCH_RECIPIENTS`` at the point a
        batch is created: an outcome list delivered in pieces is one a Connector
        can accidentally read half of, and half of it is the half without the
        skips.

        The join to ``outreach_send`` is on the *job*, which is the only link an
        invitation keeps to the delivery side. It is a ``LEFT JOIN`` because a
        pending invitation has no job and a just-dispatched one has a job whose
        handler has not yet written a send — two different absences, both
        reported as ``delivery is None``, and neither a failure.
        """
        invitation = schema.cba_invitation
        send = schema.outreach_send

        rows = session.execute(
            sa.select(
                invitation,
                send.c.id.label("send_id"),
                send.c.disposition,
                send.c.provider,
                send.c.failure_reason,
                send.c.concluded_at,
            )
            .select_from(
                invitation.outerjoin(
                    send,
                    sa.and_(
                        send.c.tenant_id == invitation.c.tenant_id,
                        send.c.job_id == invitation.c.outreach_send_job_id,
                    ),
                )
            )
            .where(
                invitation.c.tenant_id == tenant_id,
                invitation.c.batch_id == batch_id,
            )
            .order_by(invitation.c.created_at, invitation.c.id)
        ).all()

        return [
            InvitationWithDelivery(
                invitation=_to_invitation(row),
                delivery=(
                    None
                    if row.send_id is None
                    else DeliveryFacts(
                        send_id=row.send_id,
                        disposition=row.disposition,
                        provider=row.provider,
                        failure_reason=row.failure_reason,
                        concluded_at=row.concluded_at,
                    )
                ),
            )
            for row in rows
        ]

    def list_pending(
        self, session: Session, *, tenant_id: uuid.UUID, batch_id: uuid.UUID
    ) -> list[InvitationRow]:
        """The invitations in one batch that no send has been submitted for.

        What a dispatch iterates. Filtering in SQL rather than in the caller is
        what makes a second dispatch of the same batch a no-op by construction:
        an already-dispatched invitation is not in this list, so it cannot be
        submitted twice even before :meth:`mark_dispatched`'s guard is reached.
        """
        rows = session.execute(
            sa.select(schema.cba_invitation)
            .where(
                schema.cba_invitation.c.tenant_id == tenant_id,
                schema.cba_invitation.c.batch_id == batch_id,
                schema.cba_invitation.c.status == "pending",
            )
            .order_by(schema.cba_invitation.c.created_at, schema.cba_invitation.c.id)
        ).all()
        return [_to_invitation(row) for row in rows]

    def mark_dispatched(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        invitation_id: uuid.UUID,
        outreach_send_job_id: uuid.UUID,
        dispatched_at: datetime,
    ) -> bool:
        """Record that a send command was submitted. Returns whether this wrote it.

        Guarded by ``status = 'pending'`` in the ``WHERE`` clause, so a dispatch
        is recorded exactly once. The guard is the same shape ``conclude_send``
        uses and exists for a sharper version of its reason: overwriting one job
        id with another would lose the send that is already in flight, and leave
        two commands pointing at one person.

        ``RETURNING`` rather than ``rowcount``, the shape ``jobs.py`` uses and
        for its reason: ``rowcount`` lives on ``CursorResult``, which
        ``Session.execute`` is not typed as returning.
        """
        written = session.execute(
            sa.update(schema.cba_invitation)
            .where(
                schema.cba_invitation.c.tenant_id == tenant_id,
                schema.cba_invitation.c.id == invitation_id,
                schema.cba_invitation.c.status == "pending",
            )
            .values(
                status="dispatched",
                outreach_send_job_id=outreach_send_job_id,
                dispatched_at=dispatched_at,
                updated_at=dispatched_at,
            )
            .returning(schema.cba_invitation.c.id)
        ).one_or_none()
        return written is not None

    # -----------------------------------------------------------------------
    # Responses
    # -----------------------------------------------------------------------

    def resolve_response_token(self, session: Session, *, token_hash: str) -> sa.Row[Any] | None:
        """Find the invitation a response token belongs to, across every tenant.

        Deliberately **not** tenant-scoped, the one place in this module that
        departs from the rule every other method keeps — and
        ``resolve_unsubscribe_token``'s departure, for its reason. The public
        respond route is unauthenticated because a Speaker on a §13 roster is a
        contact rather than an account, so there is no tenant to scope by and the
        token is the entire authorization. Migration ``0029`` makes that safe by
        requiring the hash to be globally unique and never storing the token.

        Returns:
            The invitation id, its tenant, its status and its current response,
            or ``None`` for a token that matches nothing. A caller must answer
            identically either way: telling a stranger whether a token is real is
            telling them whether a given person was invited.
        """
        return session.execute(
            sa.select(
                schema.cba_invitation.c.id,
                schema.cba_invitation.c.tenant_id,
                schema.cba_invitation.c.status,
                schema.cba_invitation.c.response_status,
            ).where(schema.cba_invitation.c.response_token_hash == token_hash)
        ).one_or_none()

    def record_response(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        invitation_id: uuid.UUID,
        response_status: str,
        response_channel: str,
        recorded_at: datetime,
        recorded_by_user_id: uuid.UUID | None = None,
    ) -> bool:
        """Write what the Speaker said. Returns whether this call recorded it.

        Guarded by ``response_status = 'awaiting_response'``, so the first answer
        stands and a second one changes nothing. Whether a Speaker *may* change
        their mind is OQ-CBA-044 and is the domain's question, not this module's;
        what this guard guarantees is that no code path can silently overwrite an
        acceptance an Event Host may already have acted on.

        The update also refuses to reach an invitation nobody was written to,
        because ``status = 'dispatched'`` is in the ``WHERE`` clause: an answer to
        a message that was never submitted is an answer to nothing, and
        ``ck_cba_invitation_skipped_unanswered`` would refuse the row anyway.

        Returns:
            ``True`` when this call recorded the answer; ``False`` when the
            invitation had already been answered, was never dispatched, or does
            not exist. All three are outcomes a caller describes rather than
            errors it raises.
        """
        written = session.execute(
            sa.update(schema.cba_invitation)
            .where(
                schema.cba_invitation.c.tenant_id == tenant_id,
                schema.cba_invitation.c.id == invitation_id,
                schema.cba_invitation.c.status == "dispatched",
                schema.cba_invitation.c.response_status == "awaiting_response",
            )
            .values(
                response_status=response_status,
                response_channel=response_channel,
                response_recorded_at=recorded_at,
                response_recorded_by_user_id=recorded_by_user_id,
                updated_at=recorded_at,
            )
            .returning(schema.cba_invitation.c.id)
        ).one_or_none()
        return written is not None


def _to_batch(row: sa.Row[Any]) -> BatchRow:
    """Narrow a ``cba_invitation_batch`` row to the record callers read."""
    return BatchRow(
        id=row.id,
        tenant_id=row.tenant_id,
        owning_unit_id=row.owning_unit_id,
        idempotency_key=row.idempotency_key,
        match_run_id=row.match_run_id,
        template_id=row.template_id,
        event_name=row.event_name,
        event_date=row.event_date,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
    )


def _to_invitation(row: sa.Row[Any]) -> InvitationRow:
    """Narrow a ``cba_invitation`` row to the record callers read.

    ``response_token_hash`` is deliberately not carried onto
    :class:`InvitationRow`. Nothing above this layer needs it —
    :meth:`InvitationRepository.resolve_response_token` is the only reader — and
    a field that appears on the record a route renders is a field a route can
    render.
    """
    return InvitationRow(
        id=row.id,
        tenant_id=row.tenant_id,
        owning_unit_id=row.owning_unit_id,
        batch_id=row.batch_id,
        professional_id=row.professional_id,
        status=row.status,
        skip_reason=row.skip_reason,
        contact_channel_id=row.contact_channel_id,
        recipient_address=row.recipient_address,
        outreach_draft_id=row.outreach_draft_id,
        outreach_send_job_id=row.outreach_send_job_id,
        dispatched_at=row.dispatched_at,
        response_status=row.response_status,
        response_recorded_at=row.response_recorded_at,
        response_channel=row.response_channel,
        response_recorded_by_user_id=row.response_recorded_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
