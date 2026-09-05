"""Contact channels and their consent history (migrations ``0021`` and ``0022``).

``outreach.py`` owns the send path — drafts, sends, the delivery stream, the
suppression list — and reads ``contact_channel`` only through
:meth:`~smartmatch_persistence.outreach.OutreachRepository.load_recipient`, the
one question the send path asks: *may we write to this person*. This module owns
the other side of the same table: **how a contact comes to exist, and how it
moves through the lifecycle**, which is a coordinator's work rather than the
worker's.

They are separate modules rather than one because they are separate audiences
with separate transaction owners, and keeping the send path's read surface small
is what makes it reviewable. Nothing here is on the send path.

## Every state change writes two rows, in one transaction

:meth:`ContactChannelRepository.apply_transition` updates ``contact_channel``
and appends to ``contact_channel_transition``. The pair is not optional and not
best-effort: a lifecycle move whose audit row failed to write is a consent
decision with no record of who made it, which is the thing migration ``0022``
exists to prevent. Both statements run in the caller's transaction, so either
both become durable or neither does.

Registration writes the pair too, with ``from_state`` NULL. A trail that starts
at the first *edit* cannot say where a contact started.

## The update is guarded by the state it expected to find

``UPDATE ... WHERE contact_state = :expected`` and ``RETURNING``, the shape
``OutreachRepository.conclude_send`` uses. Two coordinators moving the same
contact at once is not hypothetical — the lifecycle is exactly the kind of
shared worklist two people work from — and without the guard the second write
would silently overwrite a decision it never saw, then record an audit row
claiming a transition out of a state the contact had already left.

A ``None`` return therefore means "the contact was not in the state you read",
and the caller must report a conflict rather than retrying blind.

## Nothing here decides whether a transition is legal

There is no lifecycle graph in this module, deliberately, and migration
``0022``'s docstring gives the reason: the legal edges live in
``smartmatch_domain.consent.STATE_TRANSITIONS`` and a second copy in SQL or in a
repository would be free to disagree with them. What the database enforces is
the narrower rule that must hold against a hand-written INSERT as well —
arriving at ``consented`` names an approved source — and what this module does
is record what happened.
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
    "DEFAULT_CONTACT_PAGE_SIZE",
    "MAX_CONTACT_PAGE_SIZE",
    "ContactChannelRepository",
    "ContactChannelRow",
    "TransitionRow",
]

#: How many contacts a coordinator listing returns when it does not say, and
#: the ceiling it may ask for. The same numbers and the same argument as
#: ``outreach.DEFAULT_DRAFT_PAGE_SIZE``: a page is a screen, not an export, and
#: the bound is applied in SQL rather than after the fetch.
DEFAULT_CONTACT_PAGE_SIZE: Final[int] = 25
MAX_CONTACT_PAGE_SIZE: Final[int] = 200


@dataclass(frozen=True, slots=True)
class ContactChannelRow:
    """One contact channel as a coordinator surface reads it.

    :attr:`suppressed` is computed by a join against ``suppression_record`` on
    every read rather than stored, for the reason migration ``0021`` gives for
    there being no such column: two places to look would be two places to
    disagree, and the disagreement always resolves toward sending.
    """

    id: uuid.UUID
    tenant_id: uuid.UUID
    owning_unit_id: uuid.UUID
    professional_id: uuid.UUID
    channel_kind: str
    address: str
    contact_state: str
    consent_source: str | None
    consent_recorded_at: datetime | None
    consent_evidence: str | None
    suppressed: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class TransitionRow:
    """One recorded lifecycle move.

    :attr:`from_state` is ``None`` for the registration row, which is a real
    entry rather than an absent one: the contact moved from not existing to its
    initial state, and somebody did that.
    """

    id: uuid.UUID
    contact_channel_id: uuid.UUID
    from_state: str | None
    to_state: str
    consent_source: str | None
    consent_evidence: str | None
    reason: str | None
    actor_user_id: uuid.UUID
    occurred_at: datetime


def _selectable() -> sa.Select[Any]:
    """The contact columns plus a live suppression check.

    A ``LEFT JOIN`` on ``(tenant_id, address)``, matching
    ``OutreachRepository.load_recipient`` exactly — on address rather than on
    contact id, because a suppression is a statement about a person and not
    about a row.
    """
    channel = schema.contact_channel
    suppression = schema.suppression_record
    return sa.select(
        channel.c.id,
        channel.c.tenant_id,
        channel.c.owning_unit_id,
        channel.c.professional_id,
        channel.c.channel_kind,
        channel.c.address,
        channel.c.contact_state,
        channel.c.consent_source,
        channel.c.consent_recorded_at,
        channel.c.consent_evidence,
        channel.c.created_at,
        channel.c.updated_at,
        (suppression.c.id.isnot(None)).label("suppressed"),
    ).select_from(
        channel.outerjoin(
            suppression,
            sa.and_(
                suppression.c.tenant_id == channel.c.tenant_id,
                suppression.c.address == channel.c.address,
            ),
        )
    )


def _to_contact(row: sa.Row[Any]) -> ContactChannelRow:
    """Narrow a joined ``contact_channel`` row to the record callers read."""
    return ContactChannelRow(
        id=row.id,
        tenant_id=row.tenant_id,
        owning_unit_id=row.owning_unit_id,
        professional_id=row.professional_id,
        channel_kind=row.channel_kind,
        address=row.address,
        contact_state=row.contact_state,
        consent_source=row.consent_source,
        consent_recorded_at=row.consent_recorded_at,
        consent_evidence=row.consent_evidence,
        suppressed=bool(row.suppressed),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class ContactChannelRepository:
    """Registers contacts and moves them through the lifecycle. Stateless."""

    def register(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        professional_id: uuid.UUID,
        address: str,
        contact_state: str,
        actor_user_id: uuid.UUID,
        occurred_at: datetime,
        consent_source: str | None = None,
        consent_recorded_at: datetime | None = None,
        consent_evidence: str | None = None,
        reason: str | None = None,
        channel_kind: str = "email",
        contact_channel_id: uuid.UUID | None = None,
    ) -> uuid.UUID | None:
        """Store one contact and the registration entry of its trail.

        ``ON CONFLICT ON CONSTRAINT uq_contact_channel_address DO NOTHING``, by
        constraint name for ``reserve_send``'s reason: the name is what
        ``schema.py`` mirrors and what the migration declares, and an inferred
        target would be a second spelling of the same key that nothing checks.

        Reported as a ``None`` return rather than raised, because the caller has
        a better answer for it than an exception does — a second registration of
        an address this tenant already holds is a coordinator looking at a stale
        list, not an integrity failure. Letting the constraint raise would also
        abort the transaction, taking any other work in it along.

        Returns:
            The new contact's id, or ``None`` when this tenant already holds a
            channel of this kind for this address.
        """
        new_id = contact_channel_id or uuid.uuid4()
        written = session.execute(
            postgresql.insert(schema.contact_channel)
            .values(
                id=new_id,
                tenant_id=tenant_id,
                owning_unit_id=owning_unit_id,
                professional_id=professional_id,
                channel_kind=channel_kind,
                address=address,
                contact_state=contact_state,
                consent_source=consent_source,
                consent_recorded_at=consent_recorded_at,
                consent_evidence=consent_evidence,
                created_at=occurred_at,
                updated_at=occurred_at,
            )
            .on_conflict_do_nothing(constraint="uq_contact_channel_address")
            .returning(schema.contact_channel.c.id)
        ).one_or_none()

        if written is None:
            return None

        self.record_transition(
            session,
            tenant_id=tenant_id,
            contact_channel_id=new_id,
            from_state=None,
            to_state=contact_state,
            consent_source=consent_source,
            consent_evidence=consent_evidence,
            reason=reason,
            actor_user_id=actor_user_id,
            occurred_at=occurred_at,
        )
        return new_id

    def get(
        self, session: Session, *, tenant_id: uuid.UUID, contact_channel_id: uuid.UUID
    ) -> ContactChannelRow | None:
        """Read one contact plus a live suppression check, or ``None``.

        ``tenant_id`` is part of the lookup rather than a filter applied after
        it, so a caller cannot read another tenant's contact by id.
        """
        row = session.execute(
            _selectable().where(
                schema.contact_channel.c.tenant_id == tenant_id,
                schema.contact_channel.c.id == contact_channel_id,
            )
        ).one_or_none()
        return None if row is None else _to_contact(row)

    def list_for_unit(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        limit: int = DEFAULT_CONTACT_PAGE_SIZE,
        offset: int = 0,
    ) -> list[ContactChannelRow]:
        """One unit's contacts, ordered by address so the page is stable.

        By address rather than by ``created_at``: a coordinator looking for a
        person scans for the address, and an ordering that moves as rows are
        touched makes paging through a worklist skip entries.

        ``limit`` is clamped here as well as at the route, for ``list_drafts``'s
        reason: a bound that exists only in a route stops applying the moment a
        second caller appears.
        """
        bounded = max(1, min(limit, MAX_CONTACT_PAGE_SIZE))
        rows = session.execute(
            _selectable()
            .where(
                schema.contact_channel.c.tenant_id == tenant_id,
                schema.contact_channel.c.owning_unit_id == owning_unit_id,
            )
            .order_by(schema.contact_channel.c.address, schema.contact_channel.c.id)
            .limit(bounded)
            .offset(max(0, offset))
        ).all()
        return [_to_contact(row) for row in rows]

    def update_evidence(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        contact_channel_id: uuid.UUID,
        consent_evidence: str,
        updated_at: datetime,
    ) -> bool:
        """Record or correct *how* this contact's consent was captured.

        The evidence, and nothing else. Neither the address nor the lifecycle
        state is writable here: changing an address would move a recorded
        consent onto a different person, and changing a state without an audit
        row is the whole failure ``0022`` exists to prevent — that move is
        :meth:`apply_transition`'s, which writes the trail with it.

        Returns:
            ``True`` when a row was updated, ``False`` when no such contact
            exists in this tenant.
        """
        written = session.execute(
            sa.update(schema.contact_channel)
            .where(
                schema.contact_channel.c.tenant_id == tenant_id,
                schema.contact_channel.c.id == contact_channel_id,
            )
            .values(consent_evidence=consent_evidence, updated_at=updated_at)
            .returning(schema.contact_channel.c.id)
        ).one_or_none()
        return written is not None

    def apply_transition(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        contact_channel_id: uuid.UUID,
        expected_state: str,
        to_state: str,
        actor_user_id: uuid.UUID,
        occurred_at: datetime,
        consent_source: str | None = None,
        consent_evidence: str | None = None,
        reason: str | None = None,
    ) -> ContactChannelRow | None:
        """Move a contact to ``to_state`` and record who moved it.

        Guarded by ``contact_state = :expected_state``, so a move made against
        state a caller read a moment ago fails rather than overwriting a
        decision it never saw. See the module docstring: two coordinators
        working one lifecycle is the ordinary case, not the exotic one.

        ``consent_source`` and ``consent_evidence`` are written only when given.
        A move to ``active_candidate`` carries neither — the source that
        authorizes it was recorded when the contact reached ``consented``, and
        rewriting it here would redate a permission granted earlier.

        The audit row is written from the values the ``UPDATE`` returned rather
        than from the arguments, so what the trail records is what the database
        actually holds — the difference between an audit trail and a log of
        intentions.

        Returns:
            The contact as it now stands, or ``None`` when no contact in this
            tenant is in ``expected_state``. ``None`` is a conflict, never a
            "not found": the caller must not retry it blind.
        """
        values: dict[str, Any] = {"contact_state": to_state, "updated_at": occurred_at}
        if consent_source is not None:
            values["consent_source"] = consent_source
            # Together or not at all — ck_contact_channel_consent_dated. A
            # source with no date is a consent record nobody can date.
            values["consent_recorded_at"] = occurred_at
        if consent_evidence is not None:
            values["consent_evidence"] = consent_evidence

        updated = session.execute(
            sa.update(schema.contact_channel)
            .where(
                schema.contact_channel.c.tenant_id == tenant_id,
                schema.contact_channel.c.id == contact_channel_id,
                schema.contact_channel.c.contact_state == expected_state,
            )
            .values(**values)
            .returning(
                schema.contact_channel.c.contact_state,
                schema.contact_channel.c.consent_source,
                schema.contact_channel.c.consent_evidence,
            )
        ).one_or_none()

        if updated is None:
            return None

        self.record_transition(
            session,
            tenant_id=tenant_id,
            contact_channel_id=contact_channel_id,
            from_state=expected_state,
            to_state=updated.contact_state,
            consent_source=updated.consent_source,
            consent_evidence=updated.consent_evidence,
            reason=reason,
            actor_user_id=actor_user_id,
            occurred_at=occurred_at,
        )

        return self.get(session, tenant_id=tenant_id, contact_channel_id=contact_channel_id)

    def record_transition(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        contact_channel_id: uuid.UUID,
        from_state: str | None,
        to_state: str,
        consent_source: str | None,
        consent_evidence: str | None,
        reason: str | None,
        actor_user_id: uuid.UUID,
        occurred_at: datetime,
        transition_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Append one entry to a contact's trail.

        There is no update method, and the absence is the API: migration
        ``0022``'s trigger refuses an ``UPDATE`` outright, and a correction to a
        contact's lifecycle is a *new* transition.
        """
        new_id = transition_id or uuid.uuid4()
        session.execute(
            sa.insert(schema.contact_channel_transition).values(
                id=new_id,
                tenant_id=tenant_id,
                contact_channel_id=contact_channel_id,
                from_state=from_state,
                to_state=to_state,
                consent_source=consent_source,
                consent_evidence=consent_evidence,
                reason=reason,
                actor_user_id=actor_user_id,
                occurred_at=occurred_at,
            )
        )
        return new_id

    def list_transitions(
        self, session: Session, *, tenant_id: uuid.UUID, contact_channel_id: uuid.UUID
    ) -> list[TransitionRow]:
        """One contact's history, oldest first.

        Ordered by ``occurred_at`` with ``recorded_at`` and ``id`` breaking
        ties, so the order is total and a reader rendering it gets the same
        sequence every time — the rule ``list_delivery_events`` follows.
        """
        table = schema.contact_channel_transition
        rows = session.execute(
            sa.select(table)
            .where(
                table.c.tenant_id == tenant_id,
                table.c.contact_channel_id == contact_channel_id,
            )
            .order_by(table.c.occurred_at, table.c.recorded_at, table.c.id)
        ).all()
        return [
            TransitionRow(
                id=row.id,
                contact_channel_id=row.contact_channel_id,
                from_state=row.from_state,
                to_state=row.to_state,
                consent_source=row.consent_source,
                consent_evidence=row.consent_evidence,
                reason=row.reason,
                actor_user_id=row.actor_user_id,
                occurred_at=row.occurred_at,
            )
            for row in rows
        ]
