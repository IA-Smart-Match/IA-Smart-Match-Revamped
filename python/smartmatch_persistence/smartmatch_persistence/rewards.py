"""Ledger reads and writes, and the funded-only catalog query.

The persistence half of :mod:`smartmatch_domain.rewards`. Three things, and
nothing else: credit a verified attendance to the append-only ledger, read a
subject's entries back so the domain can fold them into a balance, and list the
reward items a student may actually be shown.

Session per call, no commit — the convention every repository in this package
already holds (``jobs.py``, ``review.py``, ``redrive.py``, ``pipeline.py``,
``attendance.py``): transaction boundaries belong to the caller.

Append-only, and now enforced rather than merely observed
-----------------------------------------------------------
This module issues ``INSERT`` and ``SELECT`` against ``point_ledger_entry`` and
nothing else. There is no ``UPDATE`` and no ``DELETE`` here, and no method that
could become one without visibly adding a statement of a kind this file
otherwise never uses. A correction is
:meth:`RewardsRepository.record_reversal`, which appends.

That used to be the whole guarantee, and it held only for callers who came
through this file. Migration ``0019`` closes card **L2** — the gap reported at
``docs/decisions/d6-rewards-budget-decision-record.md`` §7 check 2 — with a
``BEFORE UPDATE`` trigger that raises ``restrict_violation``, following the
pattern ``0018`` established for ``match_run``. A ``psql`` session cannot amend
an amount now, and neither can a future method that forgot. ``DELETE`` remains
permitted, deliberately and narrowly; ``0019``'s docstring says why.

The ``redemption`` table is mutable, and that is the intended difference: a
redemption's whole purpose is to move through its states, so
:meth:`RewardsRepository.transition_redemption` does issue an ``UPDATE`` — of
that table, never of the ledger.

What this module deliberately does not have
--------------------------------------------
**No ``reward_item`` writer.** D6 gates a shipped catalog, and a convenient
``create_reward_item`` here would be the mechanism for shipping one. Integration
tests insert their own synthetic rows directly, the way
``tests/integration/test_engagement_schema_constraints.py`` already does.

**No route.** D6 records "read/redemption roles" among the fields it does not
resolve, so nothing here decides who may call any of it. Card R3 owns the
routes, their policy-matrix rows, and the OpenAPI regeneration.

**No ``reverses_entry_id``.** Migration ``0015`` removed it and ``0019`` did
not bring it back (that migration's docstring says why). So a compensating
entry still names the *attendance* it corrects rather than the *entry* it
withdraws, and where two entries share a source it is ambiguous which credit
was withdrawn. Reported, not worked around.

**No money.** ``fulfilment_cost`` is never read, spent, reserved, or disclosed
by this module.

Redemption, and where the debit happens
-----------------------------------------
Migration ``0019`` created ``redemption``, so the
``requested -> approved -> fulfilled | denied | expired`` machine in
:mod:`smartmatch_domain.rewards` is now durable rather than in-memory. The
legality of every move is still decided there —
:meth:`RewardsRepository.transition_redemption` builds the domain value from
the row and asks it — so there is exactly one statement of the state machine
and the database's CHECK constraints are its structural echo, not a second
copy with its own opinions.

**The debit is taken at fulfilment, not at request.** That is a decision worth
naming, because the alternative is defensible too: debiting at request would
reserve the points, and would then need a *refund* entry whenever a redemption
is denied or expires. That fourth kind of ledger row is exactly what
``ck_point_ledger_entry_kind`` does not admit, and admitting it would mean a
student's balance could move for a reward they never received — twice, in
opposite directions, for nothing. Debiting when the reward is actually handed
over means a balance only ever falls for something the student got.

The cost of that choice, stated: two redemptions can each be affordable when
requested and not both affordable when fulfilled. The second fulfilment is
refused (:class:`InsufficientBalanceError`) rather than allowed to drive the
balance negative, and the redemption stays ``approved`` — a coordinator can
still deny or expire it. Fail-closed, and visible.
"""

from __future__ import annotations

import uuid
from typing import Any, Final

import sqlalchemy as sa
from smartmatch_domain.rewards import (
    POINTS_PER_VERIFIED_ATTENDANCE,
    TERMINAL_REDEMPTION_STATES,
    LedgerEntry,
    LedgerEntryKind,
    Redemption,
    RedemptionState,
    RewardItem,
    attendance_credit,
    fold_balance,
    redemption_debit_amount,
    request_redemption,
    reversal_entry_amount,
)
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = [
    "ATTENDANCE_EARN_REASON",
    "REDEMPTION_DEBIT_REASON_PREFIX",
    "REVERSAL_REASON_PREFIX",
    "AlreadyCreditedError",
    "InsufficientBalanceError",
    "NothingToReverseError",
    "RewardsRepository",
    "UnknownAttendanceError",
    "UnknownRedemptionError",
    "UnknownRewardItemError",
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

#: ``point_ledger_entry.reason`` prefix for a redemption debit. The suffix is
#: the redemption's ``item_name_snapshot`` — the name the student was shown,
#: not the reward item's current name, which D7 says may have changed or been
#: deactivated since. A debit a student cannot recognise on their own ledger is
#: a balance movement they have to take on trust, which is the legacy defect.
REDEMPTION_DEBIT_REASON_PREFIX: Final[str] = "redemption of "


class UnknownAttendanceError(ValueError):
    """No ``attendance_record`` row exists for the id a credit was asked for.

    Refused before any insert. The composite foreign key would refuse it too,
    but as an ``IntegrityError`` naming a constraint rather than the missing
    evidence — and ADR-0013's "points derive from recorded attendance and
    nothing else" is exactly the rule a caller has broken here, so it is worth
    saying so.
    """


class AlreadyCreditedError(ValueError):
    """This attendance record already has a credit deriving from it.

    ``uq_attendance_record_subject_event`` stops the same attendance being
    *recorded* twice. Being *credited* twice is refused by a different
    constraint, and one that did not exist until migration ``0019``:
    ``uq_point_ledger_entry_attendance_credit``, a **partial** unique index
    over ``(tenant_id, source_attendance_id) WHERE kind = 'attendance_credit'``.
    Partial because the general constraint would be wrong — ADR-0013
    anticipates several entries deriving from one attendance as the earn policy
    is revised, and a reversal is one of them. What must not happen twice is
    the credit.

    This is what :meth:`RewardsRepository.credit_attendance` raises when the
    index refused a second credit, rather than the ``IntegrityError`` naming an
    index that a caller would have to decode.
    """


class UnknownRewardItemError(ValueError):
    """No ``reward_item`` row exists for the id a redemption was asked for.

    Distinct from :class:`smartmatch_domain.rewards.UnlistableRewardError`,
    which is about an item that exists and may not be shown. Conflating "there
    is no such reward" with "this reward is unfunded" would tell a coordinator
    to go and fund something that was never there.
    """


class UnknownRedemptionError(ValueError):
    """No ``redemption`` row exists for the id a transition was asked for."""


class InsufficientBalanceError(ValueError):
    """The folded balance no longer covers a redemption's snapshot cost.

    Raised at *fulfilment*, which is where the debit is taken. A student can
    hold two approved redemptions that were each affordable when requested, and
    the second one is refused here rather than allowed to drive the balance
    below zero. See this module's docstring for why the debit happens at
    fulfilment rather than at request.
    """


class NothingToReverseError(ValueError):
    """A reversal was asked for against an attendance with no outstanding credit.

    Either nothing was ever credited from it, or an earlier reversal already
    withdrew the credit. Refused rather than appending a second negative entry,
    which would take the ledger below what was ever earned.
    """


def redemption_debit_is_representable() -> bool:
    """Whether a redemption debit can be written to ``point_ledger_entry``.

    ``True`` since migration ``0019``, and it stayed a function reading the
    live schema rather than becoming a constant for the same reason it was one
    when it answered ``False``: the answer is a fact about the schema, and a
    hard-coded ``True`` would go on claiming a capability a later migration
    could take away.

    All three conditions are checked, because any one of them failing brings
    back the state this function was written to report:

    * ``source_attendance_id`` is nullable — a debit derives from a redemption,
      not from an attendance, and must not have to borrow an unrelated
      attendance id to satisfy a ``NOT NULL``;
    * ``source_redemption_id`` exists — there is somewhere to record what the
      debit was actually for;
    * ``redemption`` exists — there is a row for that column to point at.

    What it deliberately does **not** claim is that any *particular* write is
    correct. ``ck_point_ledger_entry_kind`` is what refuses an entry naming
    neither source, or both.
    """
    ledger = schema.point_ledger_entry
    return (
        bool(ledger.c.source_attendance_id.nullable)
        and "source_redemption_id" in ledger.c
        and "redemption" in schema.METADATA.tables
    )


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

        Idempotency is the database's now, not this method's. Migration
        ``0019`` added ``uq_point_ledger_entry_attendance_credit``, so the
        insert below is ``ON CONFLICT DO NOTHING`` against that index: a second
        caller writes nothing, reads the first caller's entry back, and raises
        :class:`AlreadyCreditedError`. The ``SELECT ... FOR UPDATE`` this
        method used to take on ``attendance_record`` is gone with it — a lock
        held by one method is a guard every other writer walks straight past.

        ``actor_id`` stays ``None`` for the ordinary derived credit — ADR-0013's
        "no discretionary grant" means the row usually has no human author, and
        naming one would misstate its origin. It is accepted for the case where
        a coordinator's action is what caused the derivation to be run.

        Returns:
            The new ``point_ledger_entry.id``.

        Raises:
            UnknownAttendanceError: no such attendance record in this tenant.
            AlreadyCreditedError: a credit already derives from it.
            ValueError: ``points_per_event`` is not positive
                (:func:`smartmatch_domain.rewards.attendance_credit`).
        """
        amount = attendance_credit(points_per_event)

        # The foreign key would refuse a missing attendance too, but as an
        # IntegrityError naming a constraint rather than the missing evidence.
        known = session.execute(
            sa.select(schema.attendance_record.c.id).where(
                schema.attendance_record.c.tenant_id == tenant_id,
                schema.attendance_record.c.id == attendance_id,
            )
        ).one_or_none()
        if known is None:
            raise UnknownAttendanceError(
                f"no attendance_record {attendance_id} in tenant {tenant_id}; points derive "
                "from recorded attendance and nothing else (ADR-0013)"
            )

        ledger = schema.point_ledger_entry
        entry_id = uuid.uuid4()
        inserted = session.execute(
            sa.dialects.postgresql.insert(ledger)
            .values(
                id=entry_id,
                tenant_id=tenant_id,
                kind=LedgerEntryKind.ATTENDANCE_CREDIT.value,
                amount=amount,
                source_attendance_id=attendance_id,
                source_redemption_id=None,
                reason=ATTENDANCE_EARN_REASON,
                actor_id=actor_id,
            )
            # Inferred against the partial index rather than named as a
            # constraint: PostgreSQL has no constraint object for a partial
            # unique index, so the predicate is part of the inference.
            #
            # `literal_execute=True` is load-bearing, and was not discovered to
            # be until the rewards API exercised this method more than ten times
            # over one pooled connection. Without it SQLAlchemy renders the
            # predicate as a bind parameter, which PostgreSQL accepts while the
            # statement is planned per execution and *rejects* the moment
            # psycopg server-prepares it (`prepare_threshold`, reached around the
            # eleventh call on a connection): "there is no unique or exclusion
            # constraint matching the ON CONFLICT specification", because a
            # prepared plan cannot prove a parameterized predicate matches the
            # index's own. The failure therefore never appeared in a short test
            # and would have appeared in production under an ordinary pool.
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "source_attendance_id"],
                index_where=ledger.c.kind
                == sa.literal(LedgerEntryKind.ATTENDANCE_CREDIT.value, literal_execute=True),
            )
            .returning(ledger.c.id)
        ).scalar_one_or_none()

        if inserted is None:
            existing = session.execute(
                sa.select(ledger.c.id).where(
                    ledger.c.tenant_id == tenant_id,
                    ledger.c.source_attendance_id == attendance_id,
                    ledger.c.kind == LedgerEntryKind.ATTENDANCE_CREDIT.value,
                )
            ).one()
            raise AlreadyCreditedError(
                f"attendance_record {attendance_id} is already credited by point_ledger_entry "
                f"{existing.id}; crediting it again would be an unearned second credit"
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
        by ``0015``, and ``0019`` deliberately did not restore it — see that
        migration's docstring. Where two entries share a source, this reversal
        is ambiguous about which credit it withdraws — recorded as a follow-up,
        not papered over here.

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
                kind=LedgerEntryKind.REVERSAL.value,
                amount=reversal_entry_amount(int(net)),
                source_attendance_id=attendance_id,
                source_redemption_id=None,
                reason=f"{REVERSAL_REASON_PREFIX}{reason.strip()}",
                actor_id=actor_id,
            )
        )
        return entry_id

    # -- reading -----------------------------------------------------------

    def ledger_entries_for_subject(
        self, session: Session, *, tenant_id: uuid.UUID, subject_id: uuid.UUID
    ) -> tuple[LedgerEntry, ...]:
        """Every ledger entry belonging to ``subject_id``, oldest first.

        ``point_ledger_entry`` has no subject column, deliberately, because the
        subject is a property of what the entry derives from and duplicating it
        on the entry would let the two disagree. So an entry belongs to a
        student by way of its source — and since migration ``0019`` there are
        two kinds of source, which is why both joins are **outer** ones and the
        subject is ``coalesce(attendance.subject_id, redemption.subject_id)``.

        An inner join through ``attendance_record`` alone, which is what this
        method used to do, would silently drop every redemption debit — and a
        balance folded from credits with the debits missing is a number that is
        too high, reported as though it were exact. That is worse than an
        error, so the query shape is the fix rather than a filter added later.

        ``ck_point_ledger_entry_kind`` guarantees exactly one of the two joins
        matches for any row, so the ``coalesce`` is a selection, not a
        precedence rule that could quietly prefer the wrong one.

        Ordered for readability, not for correctness —
        :func:`smartmatch_domain.rewards.fold_balance` is order-independent by
        construction.
        """
        ledger = schema.point_ledger_entry
        attendance = schema.attendance_record
        redemption = schema.redemption
        rows = session.execute(
            sa.select(
                ledger.c.id,
                ledger.c.tenant_id,
                ledger.c.kind,
                ledger.c.amount,
                ledger.c.source_attendance_id,
                ledger.c.source_redemption_id,
                ledger.c.reason,
                ledger.c.occurred_at,
            )
            .select_from(
                ledger.outerjoin(
                    attendance,
                    sa.and_(
                        attendance.c.tenant_id == ledger.c.tenant_id,
                        attendance.c.id == ledger.c.source_attendance_id,
                    ),
                ).outerjoin(
                    redemption,
                    sa.and_(
                        redemption.c.tenant_id == ledger.c.tenant_id,
                        redemption.c.id == ledger.c.source_redemption_id,
                    ),
                )
            )
            .where(
                ledger.c.tenant_id == tenant_id,
                sa.func.coalesce(attendance.c.subject_id, redemption.c.subject_id) == subject_id,
            )
            .order_by(ledger.c.occurred_at, ledger.c.id)
        ).all()
        return tuple(
            LedgerEntry(
                entry_id=row.id,
                tenant_id=row.tenant_id,
                kind=LedgerEntryKind(row.kind),
                amount=row.amount,
                source_attendance_id=row.source_attendance_id,
                source_redemption_id=row.source_redemption_id,
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

    def _load_item(
        self, session: Session, *, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> RewardItem:
        """One ``reward_item`` row as a domain value, listable or not.

        Private, and unlike :meth:`listable_items` it does **not** filter: the
        listability rule belongs to
        :func:`smartmatch_domain.rewards.request_redemption`, which refuses an
        unowned or unfunded item with a message naming which half failed. A
        query that had already excluded the row could only report that the
        reward did not exist, which is a different and less true statement.
        """
        row = session.execute(
            sa.select(
                schema.reward_item.c.id,
                schema.reward_item.c.tenant_id,
                schema.reward_item.c.name,
                schema.reward_item.c.points_cost,
                schema.reward_item.c.budget_owner_id,
                schema.reward_item.c.funded,
            ).where(
                schema.reward_item.c.tenant_id == tenant_id,
                schema.reward_item.c.id == item_id,
            )
        ).one_or_none()
        if row is None:
            raise UnknownRewardItemError(f"no reward_item {item_id} in tenant {tenant_id}")
        return RewardItem(
            item_id=row.id,
            tenant_id=row.tenant_id,
            name=row.name,
            points_cost=row.points_cost,
            budget_owner_id=row.budget_owner_id,
            funded=row.funded,
        )

    # -- redemption --------------------------------------------------------

    def open_redemption(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        subject_id: uuid.UUID,
        item_id: uuid.UUID,
    ) -> Redemption:
        """Open a ``requested`` redemption, or return the one already open.

        The refusals are the domain's
        (:func:`smartmatch_domain.rewards.request_redemption`) rather than this
        method's: an unlistable item and an insufficient balance are both
        decided there, over a balance this method folds server-side. ADR-0013
        forbids a client computing one, and the domain function is pure and
        cannot obtain one itself, which is what keeps the two halves honest.

        Idempotent by way of ``uq_redemption_open_per_item``. A second request
        for an item this student already has in flight writes nothing and reads
        the in-flight redemption back, which is card L4's "concurrent duplicate
        requests resolve to one redemption" — and it resolves that way for
        every writer, not only for two calls that happened to reach this
        method. A *terminal* redemption never blocks a new one; the index is
        partial for exactly that reason.

        Returns:
            The redemption, in state ``requested``.

        Raises:
            UnknownRewardItemError: no such reward item in this tenant.
            smartmatch_domain.rewards.UnlistableRewardError: the item is
                unowned or unfunded (D6).
            ValueError: the folded balance does not cover the item's cost.
        """
        item = self._load_item(session, tenant_id=tenant_id, item_id=item_id)
        balance = self.balance_for_subject(session, tenant_id=tenant_id, subject_id=subject_id)
        opened = request_redemption(
            redemption_id=uuid.uuid4(),
            subject_id=subject_id,
            item=item,
            balance=balance,
        )

        table = schema.redemption
        inserted = session.execute(
            sa.dialects.postgresql.insert(table)
            .values(
                id=opened.redemption_id,
                tenant_id=opened.tenant_id,
                subject_id=opened.subject_id,
                item_id=opened.item_id,
                item_name_snapshot=opened.item_name_snapshot,
                points_cost_snapshot=opened.points_cost_snapshot,
                state=opened.state.value,
            )
            # `literal_execute=True` for the reason `credit_attendance` gives at
            # length: a bind parameter here is accepted until psycopg
            # server-prepares the statement and refused from then on, which on
            # this method is the eleventh redemption request a running API
            # process handles rather than anything a short test would reach.
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "subject_id", "item_id"],
                index_where=table.c.state.in_(
                    [
                        sa.literal(RedemptionState.REQUESTED.value, literal_execute=True),
                        sa.literal(RedemptionState.APPROVED.value, literal_execute=True),
                    ]
                ),
            )
            .returning(table.c.id)
        ).scalar_one_or_none()
        if inserted is not None:
            return opened

        existing = self._open_redemption_for(
            session, tenant_id=tenant_id, subject_id=subject_id, item_id=item_id
        )
        if existing is None:  # pragma: no cover - only reachable under a lost race
            raise UnknownRedemptionError(
                f"the open redemption for subject {subject_id} and reward_item {item_id} "
                "conflicted on insert and then could not be read back"
            )
        return existing

    def _open_redemption_for(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        subject_id: uuid.UUID,
        item_id: uuid.UUID,
    ) -> Redemption | None:
        """The in-flight redemption for this student and item, if there is one."""
        table = schema.redemption
        row = session.execute(
            sa.select(table).where(
                table.c.tenant_id == tenant_id,
                table.c.subject_id == subject_id,
                table.c.item_id == item_id,
                table.c.state.in_(
                    [RedemptionState.REQUESTED.value, RedemptionState.APPROVED.value]
                ),
            )
        ).one_or_none()
        return None if row is None else _redemption_from(row)

    def load_redemption(
        self, session: Session, *, tenant_id: uuid.UUID, redemption_id: uuid.UUID
    ) -> Redemption | None:
        """Read one redemption back, or ``None`` if this tenant has no such row."""
        table = schema.redemption
        row = session.execute(
            sa.select(table).where(
                table.c.tenant_id == tenant_id,
                table.c.id == redemption_id,
            )
        ).one_or_none()
        return None if row is None else _redemption_from(row)

    def redemptions_for_subject(
        self, session: Session, *, tenant_id: uuid.UUID, subject_id: uuid.UUID
    ) -> tuple[Redemption, ...]:
        """A student's redemptions, newest request first.

        The order ``ix_redemption_subject_requested`` exists for, and the order
        a ticket list reads in. The id breaks ties so two calls against
        unchanged data return the same order.
        """
        table = schema.redemption
        rows = session.execute(
            sa.select(table)
            .where(table.c.tenant_id == tenant_id, table.c.subject_id == subject_id)
            .order_by(table.c.requested_at.desc(), table.c.id)
        ).all()
        return tuple(_redemption_from(row) for row in rows)

    def transition_redemption(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        redemption_id: uuid.UUID,
        to_state: RedemptionState,
        actor_id: uuid.UUID | None = None,
    ) -> Redemption:
        """Move a redemption, and take the ledger debit if the move is ``fulfilled``.

        The legality of the move is decided by
        :meth:`smartmatch_domain.rewards.Redemption.transition` — this method
        reads the row, builds the domain value, and asks it. There is therefore
        one statement of the state machine and not two, and the database's
        ``ck_redemption_approval_evidence`` is its structural echo rather than
        a second opinion: even a hand-written ``UPDATE`` cannot land a row in
        ``fulfilled`` with no approval behind it.

        The row is taken ``FOR UPDATE`` first. That lock is doing something a
        constraint cannot: two concurrent fulfilments of *different*
        redemptions for the same student would each fold a balance that did not
        yet include the other's debit, and the second must see the first.
        Serializing on the redemption row is not enough for that on its own —
        the balance check below re-folds *after* taking the lock, and the two
        fulfilments contend on their shared subject only through the entries
        they insert, so a caller wanting strict serialization across two
        different redemptions should use a serializable transaction. What this
        method guarantees is that one redemption is fulfilled once.

        ``actor_id`` is **required** for ``approved``, ``fulfilled``, and
        ``denied`` — all three are things a person does, and
        ``ck_redemption_approval_evidence`` refuses an approval with no author
        in any case. It must be **absent** for ``expired``: an expiry is
        something time does, and naming a human for it would be a fabricated
        field.

        Returns:
            The redemption in its new state.

        Raises:
            UnknownRedemptionError: no such redemption in this tenant.
            smartmatch_domain.rewards.InvalidRedemptionTransition: the move is
                not one the state machine allows.
            InsufficientBalanceError: fulfilment was asked for and the folded
                balance no longer covers the snapshot cost.
            ValueError: ``actor_id`` is missing where it is required, or
                present on an expiry.
        """
        table = schema.redemption
        row = session.execute(
            sa.select(table)
            .where(table.c.tenant_id == tenant_id, table.c.id == redemption_id)
            .with_for_update()
        ).one_or_none()
        if row is None:
            raise UnknownRedemptionError(f"no redemption {redemption_id} in tenant {tenant_id}")

        current = _redemption_from(row)
        moved = current.transition(to_state)

        if to_state is RedemptionState.EXPIRED:
            if actor_id is not None:
                raise ValueError(
                    "an expiry has no author: it is something time does, and naming a "
                    "person for it would record a decision nobody made"
                )
        elif actor_id is None:
            raise ValueError(
                f"moving a redemption to {to_state.value} is an act, and the acting "
                "account must be named"
            )

        values: dict[str, object] = {"state": to_state.value}
        if to_state is RedemptionState.APPROVED:
            values["approved_at"] = sa.func.now()
            values["approved_by"] = actor_id
        if to_state in _TERMINAL_STATE_VALUES:
            values["closed_at"] = sa.func.now()
            values["closed_by"] = actor_id

        if to_state is RedemptionState.FULFILLED:
            self._debit_for(session, redemption=moved, actor_id=actor_id)

        session.execute(
            sa.update(table)
            .where(table.c.tenant_id == tenant_id, table.c.id == redemption_id)
            .values(**values)
        )
        return moved

    def _debit_for(
        self,
        session: Session,
        *,
        redemption: Redemption,
        actor_id: uuid.UUID | None,
    ) -> uuid.UUID:
        """Append the debit that pays for ``redemption``, refusing an overdraw.

        The balance is re-folded here rather than trusted from the request: a
        redemption can sit ``approved`` for as long as a coordinator takes, and
        the points behind it may have been reversed in the meantime. Card L4
        asks that "balance check and ledger debit are atomic server-side",
        which is what this is — one statement's worth apart, inside the
        caller's transaction, with the redemption row already locked.

        The debit names the redemption and **no** attendance. That row was not
        writable at all before migration ``0019``; nothing here borrows an
        unrelated attendance id to make one fit.
        """
        balance = self.balance_for_subject(
            session, tenant_id=redemption.tenant_id, subject_id=redemption.subject_id
        )
        if balance < redemption.points_cost_snapshot:
            raise InsufficientBalanceError(
                f"balance {balance} no longer covers redemption {redemption.redemption_id} "
                f"at its snapshot cost of {redemption.points_cost_snapshot} points"
            )

        entry_id = uuid.uuid4()
        session.execute(
            sa.insert(schema.point_ledger_entry).values(
                id=entry_id,
                tenant_id=redemption.tenant_id,
                kind=LedgerEntryKind.REDEMPTION_DEBIT.value,
                amount=redemption_debit_amount(redemption.points_cost_snapshot),
                source_attendance_id=None,
                source_redemption_id=redemption.redemption_id,
                # The name the student was shown, not today's — see
                # REDEMPTION_DEBIT_REASON_PREFIX.
                reason=f"{REDEMPTION_DEBIT_REASON_PREFIX}{redemption.item_name_snapshot}",
                actor_id=actor_id,
            )
        )
        return entry_id


#: The states a ``closed_at`` belongs to, derived from the domain's own terminal
#: set rather than listed again here — the two cannot drift, and
#: ``ck_redemption_closure_evidence`` is the database's copy of the same fact.
_TERMINAL_STATE_VALUES: Final[frozenset[RedemptionState]] = TERMINAL_REDEMPTION_STATES


def _redemption_from(row: sa.Row[Any]) -> Redemption:
    """Build the domain value from a ``redemption`` row.

    The audit columns (``requested_at``, the two evidence pairs) are
    deliberately **not** carried into
    :class:`smartmatch_domain.rewards.Redemption`: that type is the state
    machine's value, and the timestamps are how the row proves what happened to
    it. A domain type carrying them would invite a caller to compute a
    transition from a timestamp rather than from ``state``, which is the sort
    of second source of truth ADR-0013 spends its length arguing against.
    """
    return Redemption(
        redemption_id=row.id,
        tenant_id=row.tenant_id,
        subject_id=row.subject_id,
        item_id=row.item_id,
        item_name_snapshot=row.item_name_snapshot,
        points_cost_snapshot=row.points_cost_snapshot,
        state=RedemptionState(row.state),
    )
