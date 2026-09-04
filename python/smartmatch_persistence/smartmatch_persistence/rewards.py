"""Ledger reads and writes, and the funded-only catalog query.

The persistence half of :mod:`smartmatch_domain.rewards`. Three things, and
nothing else: credit a verified attendance to the append-only ledger, read a
subject's entries back so the domain can fold them into a balance, and list the
reward items a student may actually be shown.

Session per call, no commit — the convention every repository in this package
already holds (``jobs.py``, ``review.py``, ``redrive.py``, ``pipeline.py``,
``attendance.py``): transaction boundaries belong to the caller.

Append-only in practice, not just in principle
------------------------------------------------
This module issues ``INSERT`` and ``SELECT`` against ``point_ledger_entry`` and
nothing else. There is no ``UPDATE`` and no ``DELETE`` here, and no method that
could become one without visibly adding a statement of a kind this file
otherwise never uses. A correction is
:meth:`RewardsRepository.record_reversal`, which appends. Note what that does
*not* amount to: a database-level append-only guard on ``point_ledger_entry``
is still absent (card **L2**, and the gap reported in
``docs/decisions/d6-rewards-budget-decision-record.md`` §7 check 2). Nothing in
this module closes it, and this module adds no migration.

What this module deliberately does not have
--------------------------------------------
**No ``reward_item`` writer.** D6 gates a shipped catalog, and a convenient
``create_reward_item`` here would be the mechanism for shipping one. Integration
tests insert their own synthetic rows directly, the way
``tests/integration/test_engagement_schema_constraints.py`` already does.

**No redemption persistence.** There is no ``redemption`` table: migration
``0009`` deliberately deferred it, and this change adds no migration. The
redemption state machine therefore lives entirely in
:mod:`smartmatch_domain.rewards`, and a redemption is not durable yet.
:func:`redemption_debit_is_representable` states the second half of why in code
— ``point_ledger_entry.source_attendance_id`` is ``NOT NULL``, so a debit
deriving from a redemption rather than from an attendance has no row shape to
be written as. Both gaps are reported, not worked around; nothing here writes a
redemption debit against an unrelated attendance record to make one fit.

**No money.** ``fulfilment_cost`` is never read, spent, reserved, or disclosed
by this module.
"""

from __future__ import annotations

import uuid
from typing import Final

import sqlalchemy as sa
from smartmatch_domain.rewards import (
    POINTS_PER_VERIFIED_ATTENDANCE,
    LedgerEntry,
    RewardItem,
    attendance_credit,
    fold_balance,
    reversal_entry_amount,
)
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = [
    "ATTENDANCE_EARN_REASON",
    "REVERSAL_REASON_PREFIX",
    "AlreadyCreditedError",
    "NothingToReverseError",
    "RewardsRepository",
    "UnknownAttendanceError",
    "redemption_debit_is_representable",
]

#: ``point_ledger_entry.reason`` for the ordinary earning entry. A single
#: spelling, held here rather than at each call site, for the reason
#: ``SYNTHETIC_MATCH_PROVENANCE`` is held in
#: :mod:`smartmatch_domain.synthetic_pilot`: an entry whose reason a reader
#: cannot match against the rule that produced it is an entry that cannot
#: explain itself, which is most of what ADR-0013 wanted the ledger for.
ATTENDANCE_EARN_REASON: Final[str] = "verified attendance"

#: ``point_ledger_entry.reason`` prefix for a compensating entry. The suffix is
#: the caller's own explanation, required rather than defaulted — a reversal
#: with no stated cause is D7's "no silent balance editing" rule evaded by
#: leaving the reason blank instead of by issuing an ``UPDATE``.
REVERSAL_REASON_PREFIX: Final[str] = "reversal of verified attendance credit: "


class UnknownAttendanceError(ValueError):
    """No ``attendance_record`` row exists for the id a credit was asked for.

    Refused before any insert. The composite foreign key would refuse it too,
    but as an ``IntegrityError`` naming a constraint rather than the missing
    evidence — and ADR-0013's "points derive from recorded attendance and
    nothing else" is exactly the rule a caller has broken here, so it is worth
    saying so.
    """


class AlreadyCreditedError(ValueError):
    """This attendance record already has a positive entry deriving from it.

    ``uq_attendance_record_subject_event`` stops the same attendance being
    *recorded* twice; nothing in the schema stops it being *credited* twice,
    because there is no unique constraint on
    ``point_ledger_entry.source_attendance_id`` — and there deliberately is not
    one in general, since ADR-0013 anticipates several entries per attendance as
    the earn policy is revised.
    :meth:`RewardsRepository.credit_attendance` closes the double-credit case
    under a row lock; this is what it raises when the caller asked for a second
    credit rather than an idempotent repeat.
    """


class NothingToReverseError(ValueError):
    """A reversal was asked for against an attendance with no outstanding credit.

    Either nothing was ever credited from it, or an earlier reversal already
    withdrew the credit. Refused rather than appending a second negative entry,
    which would take the ledger below what was ever earned.
    """


def redemption_debit_is_representable() -> bool:
    """Whether a redemption debit can be written to ``point_ledger_entry`` today.

    ``False``, and that is a fact about the schema rather than about this
    module: ``source_attendance_id`` is ``NOT NULL`` (migration ``0009``), so
    every ledger row must name an attendance record it derives from. A debit
    taken when a student redeems a reward derives from a *redemption*, not from
    an attendance, and there is no column for that and no ``redemption`` table
    for it to point at.

    Expressed as a function reading the live column definition so a test can
    assert on the limitation and fail the moment it stops being true — at which
    point the redemption debit path can be written honestly, rather than by
    borrowing an unrelated attendance id to satisfy a ``NOT NULL``.
    """
    return bool(schema.point_ledger_entry.c.source_attendance_id.nullable)


class RewardsRepository:
    """Reads and appends ``point_ledger_entry``; reads the listable catalog."""

    # -- earning -----------------------------------------------------------

    def credit_attendance(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        attendance_id: uuid.UUID,
        points_per_event: int = POINTS_PER_VERIFIED_ATTENDANCE,
        actor_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Append the earning entry for one verified attendance, once.

        ``SELECT ... FOR UPDATE`` on the ``attendance_record`` row first. The
        lock target is deliberate: there is no unique constraint to hang an
        ``ON CONFLICT`` on (see :class:`AlreadyCreditedError`), but every
        concurrent call crediting *this* attendance must take *this* row's lock
        before it can look for an existing credit, so the check-then-insert
        below is serialized against the only writers that could race it. A
        second caller blocks, then finds the first caller's entry and raises
        rather than writing a duplicate credit. This is an application-level
        guard standing in for a database constraint that does not exist, and it
        holds only for callers that come through this method.

        ``actor_id`` stays ``None`` for the ordinary derived credit — ADR-0013's
        "no discretionary grant" means the row usually has no human author, and
        naming one would misstate its origin. It is accepted for the case where
        a coordinator's action is what caused the derivation to be run.

        Returns:
            The new ``point_ledger_entry.id``.

        Raises:
            UnknownAttendanceError: no such attendance record in this tenant.
            AlreadyCreditedError: a positive entry already derives from it.
            ValueError: ``points_per_event`` is not positive
                (:func:`smartmatch_domain.rewards.attendance_credit`).
        """
        amount = attendance_credit(points_per_event)

        locked = session.execute(
            sa.select(schema.attendance_record.c.id)
            .where(
                schema.attendance_record.c.tenant_id == tenant_id,
                schema.attendance_record.c.id == attendance_id,
            )
            .with_for_update()
        ).one_or_none()
        if locked is None:
            raise UnknownAttendanceError(
                f"no attendance_record {attendance_id} in tenant {tenant_id}; points derive "
                "from recorded attendance and nothing else (ADR-0013)"
            )

        existing = session.execute(
            sa.select(schema.point_ledger_entry.c.id).where(
                schema.point_ledger_entry.c.tenant_id == tenant_id,
                schema.point_ledger_entry.c.source_attendance_id == attendance_id,
                schema.point_ledger_entry.c.amount > 0,
            )
        ).first()
        if existing is not None:
            raise AlreadyCreditedError(
                f"attendance_record {attendance_id} is already credited by point_ledger_entry "
                f"{existing.id}; crediting it again would be an unearned second credit"
            )

        entry_id = uuid.uuid4()
        session.execute(
            sa.insert(schema.point_ledger_entry).values(
                id=entry_id,
                tenant_id=tenant_id,
                amount=amount,
                source_attendance_id=attendance_id,
                reason=ATTENDANCE_EARN_REASON,
                actor_id=actor_id,
            )
        )
        return entry_id

    def record_reversal(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        attendance_id: uuid.UUID,
        reason: str,
        actor_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Append a compensating entry withdrawing this attendance's net credit.

        ADR-0013: "a reversal is a compensating entry, never a delete". This
        method issues an ``INSERT``; it does not touch the entry it corrects.

        The amount is the *net* of the entries already deriving from this
        attendance, so a second reversal has nothing left to withdraw and is
        refused rather than driving the balance below what was earned.

        ``reason`` is required and non-blank. D7's "no silent balance editing"
        rule is that a correction is "an appended entry with a reason, visible
        to the student"; a reversal with an empty reason satisfies the letter
        and defeats the point.

        A limitation, stated rather than worked around: the entry names the
        *attendance* it corrects, not the *entry* it withdraws.
        ``reverses_entry_id`` was added by migration ``0014`` and removed again
        by ``0015``, and this change adds no migration. Where two entries share
        a source, this reversal is ambiguous about which credit it withdraws —
        recorded as a follow-up, not papered over here.

        Returns:
            The new ``point_ledger_entry.id``.

        Raises:
            UnknownAttendanceError: no such attendance record in this tenant.
            NothingToReverseError: the entries for this attendance net to zero
                or below.
            ValueError: ``reason`` is blank.
        """
        if not reason.strip():
            raise ValueError(
                "a reversal must state its reason (D7: corrections are audited ledger "
                "adjustments with a stated reason, visible to the student)"
            )

        locked = session.execute(
            sa.select(schema.attendance_record.c.id)
            .where(
                schema.attendance_record.c.tenant_id == tenant_id,
                schema.attendance_record.c.id == attendance_id,
            )
            .with_for_update()
        ).one_or_none()
        if locked is None:
            raise UnknownAttendanceError(
                f"no attendance_record {attendance_id} in tenant {tenant_id}"
            )

        net = session.execute(
            sa.select(sa.func.coalesce(sa.func.sum(schema.point_ledger_entry.c.amount), 0)).where(
                schema.point_ledger_entry.c.tenant_id == tenant_id,
                schema.point_ledger_entry.c.source_attendance_id == attendance_id,
            )
        ).scalar_one()
        if net <= 0:
            raise NothingToReverseError(
                f"entries deriving from attendance_record {attendance_id} net to {net}; there "
                "is no outstanding credit to withdraw"
            )

        entry_id = uuid.uuid4()
        session.execute(
            sa.insert(schema.point_ledger_entry).values(
                id=entry_id,
                tenant_id=tenant_id,
                amount=reversal_entry_amount(int(net)),
                source_attendance_id=attendance_id,
                reason=f"{REVERSAL_REASON_PREFIX}{reason.strip()}",
                actor_id=actor_id,
            )
        )
        return entry_id

    # -- reading -----------------------------------------------------------

    def ledger_entries_for_subject(
        self, session: Session, *, tenant_id: uuid.UUID, subject_id: uuid.UUID
    ) -> tuple[LedgerEntry, ...]:
        """Every ledger entry deriving from ``subject_id``'s attendance, oldest first.

        The join through ``attendance_record`` is what makes an entry belong to
        a student: ``point_ledger_entry`` has no subject column, deliberately,
        because the subject is a property of the evidence and duplicating it on
        the entry would let the two disagree.

        Ordered for readability, not for correctness —
        :func:`smartmatch_domain.rewards.fold_balance` is order-independent by
        construction.
        """
        rows = session.execute(
            sa.select(
                schema.point_ledger_entry.c.id,
                schema.point_ledger_entry.c.tenant_id,
                schema.point_ledger_entry.c.amount,
                schema.point_ledger_entry.c.source_attendance_id,
                schema.point_ledger_entry.c.reason,
                schema.point_ledger_entry.c.occurred_at,
            )
            .join(
                schema.attendance_record,
                sa.and_(
                    schema.attendance_record.c.tenant_id == schema.point_ledger_entry.c.tenant_id,
                    schema.attendance_record.c.id
                    == schema.point_ledger_entry.c.source_attendance_id,
                ),
            )
            .where(
                schema.point_ledger_entry.c.tenant_id == tenant_id,
                schema.attendance_record.c.subject_id == subject_id,
            )
            .order_by(schema.point_ledger_entry.c.occurred_at, schema.point_ledger_entry.c.id)
        ).all()
        return tuple(
            LedgerEntry(
                entry_id=row.id,
                tenant_id=row.tenant_id,
                amount=row.amount,
                source_attendance_id=row.source_attendance_id,
                reason=row.reason,
                occurred_at=row.occurred_at,
            )
            for row in rows
        )

    def balance_for_subject(
        self, session: Session, *, tenant_id: uuid.UUID, subject_id: uuid.UUID
    ) -> int:
        """``subject_id``'s balance: a fold over the entries, computed on request.

        The fold is :func:`smartmatch_domain.rewards.fold_balance`, in the
        domain, over rows this method read — not a ``SUM()`` this method
        remembers and not a column anything stores. ADR-0013's whole objection
        to the legacy was a balance with no history behind it; folding the
        history in a pure function keeps the number and its explanation the same
        object.
        """
        return fold_balance(
            self.ledger_entries_for_subject(session, tenant_id=tenant_id, subject_id=subject_id)
        )

    # -- the catalog -------------------------------------------------------

    def listable_items(self, session: Session, *, tenant_id: uuid.UUID) -> tuple[RewardItem, ...]:
        """Reward items a student may be shown: funded, and owned in this tenant.

        Both of D6's halves, in SQL:

        * ``funded IS TRUE`` — the column's ``server_default 'false'`` is an
          insert-time default, not a listing permission, so an item nobody has
          confirmed funding for is simply not selected.
        * an inner join to ``user_account`` on the composite
          ``(tenant_id, budget_owner_id)`` — the named human budget owner,
          resolved rather than assumed. The composite foreign key already
          guarantees the row exists in this tenant; the join is written anyway so
          the *query* states the rule, and so this method still refuses an
          unowned item if that constraint is ever relaxed.

        Ordered by cost then id: ascending cost is how a catalog reads, and the
        id breaks ties so two calls against unchanged data return the same order.

        Returns domain :class:`~smartmatch_domain.rewards.RewardItem` values with
        ``budget_owner_id`` populated. There is deliberately no method here
        returning unlistable items to a caller that could render them; a test
        that needs to prove an unfunded row exists reads it with its own SQL.
        """
        rows = session.execute(
            sa.select(
                schema.reward_item.c.id,
                schema.reward_item.c.tenant_id,
                schema.reward_item.c.name,
                schema.reward_item.c.points_cost,
                schema.reward_item.c.budget_owner_id,
                schema.reward_item.c.funded,
            )
            .join(
                schema.user_account,
                sa.and_(
                    schema.user_account.c.tenant_id == schema.reward_item.c.tenant_id,
                    schema.user_account.c.id == schema.reward_item.c.budget_owner_id,
                ),
            )
            .where(
                schema.reward_item.c.tenant_id == tenant_id,
                schema.reward_item.c.funded.is_(True),
            )
            .order_by(schema.reward_item.c.points_cost, schema.reward_item.c.id)
        ).all()
        return tuple(
            RewardItem(
                item_id=row.id,
                tenant_id=row.tenant_id,
                name=row.name,
                points_cost=row.points_cost,
                budget_owner_id=row.budget_owner_id,
                funded=row.funded,
            )
            for row in rows
        )
