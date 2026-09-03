"""``reward_item`` catalog reads and the append-only ``point_ledger_entry`` write path.

Migration ``0009`` (ADR-0013, backlog S6/S7/S8) created ``attendance_record``,
``point_ledger_entry``, and ``reward_item`` and left them with no application
code at all. This module is the catalog read half (S8) and the ledger write
half (S7's storage) that ``docs/plans/2026-08-28-d6-rewards-s8-s9-plan.md``
cards L3 and L1 describe, built against D6's now-closed budget-ownership
decision.

## No HTTP route ships with this module, and that is deliberate

``services/api/smartmatch_api/routers/engagement.py`` is a declared-empty stub
and stays one. Three separate committed statements keep it that way, none of
which this module is entitled to overturn:

1. ``tests/unit/test_matching_fail_closed.py`` asserts
   ``engagement.router.routes == []`` and scans the published OpenAPI document
   for the path segments ``reward``, ``rewards``, ``redemption``, ``balance``,
   and ``catalog``. That scan is a gate, and
   ``docs/plans/2026-08-28-d6-rewards-s8-s9-plan.md`` card R3 names flipping it
   as R3's own deliberate, reviewed commit.
2. ``docs/decisions/d6-rewards-budget-decision-record.md`` §5 lists
   "Read/redemption roles" among the fields D6 explicitly does **not** resolve,
   and that plan's stop-gate item 3 says "If roles are missing, cards R3+ stop
   before route work." A route whose authorized roles nobody has decided is a
   route gated on nothing.
3. That plan's card R3 additionally requires card **L2** — a database-level
   append-only guard on ``point_ledger_entry`` — to be merged and CI-proven
   first, "otherwise an ordering race exposes routes over a mutable ledger".
   No such guard exists yet (see the next section).

So this module has the same posture ``smartmatch_persistence.pipeline`` already
holds and for a comparable reason: the storage-layer work is real, tested, and
ready for the caller its gate authorizes, and it has no caller today.

## Append-only is enforced here by construction, and *only* here

This module exposes no ``update``, no ``delete``, and no method that issues
either statement against ``point_ledger_entry``. ADR-0013: "A reversal is a
compensating entry, never a delete." :meth:`PointLedgerRepository.append_reversal`
is that compensating entry — a second ``INSERT`` carrying the negated amount,
the same ``source_attendance_id``, a reason naming what it corrects, and
``reverses_entry_id`` naming the entry itself. The row it reverses is read and
never written.

``reverses_entry_id`` (migration ``0014``) exists because carrying the shared
``source_attendance_id`` forward was not enough to satisfy ADR-0013's "names
what it reverses": it identifies the *attendance*, and once two entries derive
from one attendance — which nothing prevents, and which a revised earn policy
invites — a negative row citing that source leaves an auditor unable to say
which credit was withdrawn. The composite foreign key is tenant-safe, so a
reversal cannot reach an entry in another tenant, and
``smartmatch_domain.rewards.assert_reversal_target`` refuses both a reversal
that names nothing and an earning entry that names something. ADR-0013 is
**silent** on whether a reversal may itself be reversed; nothing here invents a
prohibition it does not state.

**The database does not enforce this.**
``docs/decisions/d6-rewards-budget-decision-record.md`` §7 check 2 records the
gap in those words: append-only is "enforced only by convention (absent mutable
columns) and by an application/test contract, not by any database trigger or
rule. No ``UPDATE``/``DELETE`` guard exists on the live table." Migration
``0009``'s design does make the convention unusually load-bearing — the table
has no ``status``, ``updated_at``, or ``version`` column, so there is nothing an
application could legitimately ``UPDATE`` — but "nothing worth updating" is not
"updating is refused". Closing that gap is plan card L2 and needs a migration
this module deliberately does not write.

## Budget ownership is established, never defaulted

D6 §1: "Danny Tran (@dangt) is named the **institutional budget owner** for the
rewards program, effective 2026-09-02." The schema's form of that requirement
is ``reward_item.budget_owner_id NOT NULL`` with a *composite* foreign key to
``user_account (tenant_id, id)`` — composite so an owner from another tenant is
refused, because (migration ``0009``) "D6's 'named human budget owner' reads
emptily if the name can belong to someone with no standing in this tenant at
all."

:meth:`RewardCatalogRepository.create_item` establishes the owner in two steps
before it writes anything: ``smartmatch_domain.rewards.assert_budget_owner_named``
refuses the absent case, and a tenant-scoped ``SELECT`` against
``user_account`` refuses an id that names nobody in this tenant
(:class:`UnknownBudgetOwnerError`). Neither step has a fallback branch. There
is no "default owner", no environment-supplied owner, and no coordinator-role
substitute — the plan's standing constraints say "A coordinator role is not a
budget owner; an arbitrary UUID is not ownership."

:meth:`RewardCatalogRepository.list_listable_items` enforces the same rule on
the read side, and re-derives it rather than trusting the write side to have
held: the listing is an ``INNER JOIN`` to ``user_account`` on the composite
key, filtered to ``funded IS TRUE``. An item whose owner was somehow written
without standing in this tenant, or an item that is merely unfunded, does not
appear — it is not returned with a flag for a caller to remember to check.

## Nothing here seeds a catalog

There is no module-level catalog constant, no bootstrap function, and no insert
this module performs on import. Every row comes from an explicit
:meth:`~RewardCatalogRepository.create_item` call by a caller that supplied its
own values. The plan's standing constraints require it ("Seed no production
catalog data in migrations"), D7 has ratified no item name or point cost
(``docs/decisions/d6-rewards-budget-decision-record.md`` §4), and the legacy
costs are a documented defect (Fix #15) rather than content to carry forward.
The only reward rows this repository creates are synthetic ones built inside
``tests/integration/test_rewards_repositories.py``.

## No redemption, and no earn policy

``redemption`` is one of the three tables migration ``0009`` explicitly defers
(``0009_engagement_schema.py``'s module docstring), so there is no table to
write and no fulfilment path here — S9 is plan card L4 and remains gated.
Neither is there any derivation of ledger entries *from* attendance: how many
points a verified attendance earns is D7, still tentative, so a caller supplies
``amount`` and this module records it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from smartmatch_domain.rewards import (
    assert_budget_owner_named,
    assert_ledger_entry_well_formed,
    assert_reversal_target,
    fold_balance,
    reversal_amount,
)
from sqlalchemy.orm import Session

from smartmatch_persistence import schema

__all__ = [
    "PointLedgerEntryRow",
    "PointLedgerRepository",
    "RewardCatalogRepository",
    "RewardItemRow",
    "UnknownAttendanceSourceError",
    "UnknownBudgetOwnerError",
    "UnknownLedgerEntryError",
]


class UnknownBudgetOwnerError(ValueError):
    """``budget_owner_id`` names nobody with standing in this tenant.

    Checked with a tenant-scoped ``SELECT`` before
    :meth:`RewardCatalogRepository.create_item` issues its ``INSERT``, rather
    than left to the composite foreign key
    (``reward_item_tenant_id_budget_owner_id_fkey``), for the reason
    :class:`~smartmatch_persistence.pipeline.UnknownAttendanceEvidenceError`
    gives for the same choice: a bogus or cross-tenant id would otherwise abort
    the whole transaction with an ``IntegrityError`` naming a constraint the
    caller may not recognize, when the caller's actual mistake — D6's one
    requirement — deserves to be said in those terms.

    This is emphatically not a softening of the database constraint. The
    foreign key still holds; this refusal happens first and says why.
    """


class UnknownAttendanceSourceError(ValueError):
    """``source_attendance_id`` does not name an ``attendance_record`` in this tenant.

    ADR-0013: "Points derive from recorded attendance and nothing else. …
    There is no discretionary grant, no client-submitted event, and no formula
    over summary counters." A ledger entry whose cited source does not exist is
    exactly the discretionary grant that rule forbids, so it is refused before
    the ``INSERT``, on the same reasoning as :class:`UnknownBudgetOwnerError`.
    """


class UnknownLedgerEntryError(ValueError):
    """The entry a reversal names does not exist in this tenant.

    :meth:`PointLedgerRepository.append_reversal` must read the original to
    negate its amount and to carry its ``source_attendance_id`` forward; there
    is nothing to compensate for if it is not there.
    """


@dataclass(frozen=True, slots=True)
class RewardItemRow:
    """One ``reward_item`` row.

    Frozen: a listing is a read, and a row a caller could mutate in place is a
    row a caller could quietly "fix" the funded flag on. ``fulfilment_cost`` is
    a :class:`~decimal.Decimal`, matching the column's ``NUMERIC(12, 4)`` —
    money read back as a float would round, which is the class of defect
    ADR-0011 (accountable numbers) is about.
    """

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    points_cost: int
    fulfilment_cost: Decimal
    budget_owner_id: uuid.UUID
    funded: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PointLedgerEntryRow:
    """One ``point_ledger_entry`` row, as appended.

    Frozen for a stronger reason than :class:`RewardItemRow`'s: the ledger is
    append-only, and a mutable row object is the first thing a caller reaches
    for when it wants to change one. There is no ``updated_at`` field here
    because there is no such column — see this module's docstring.
    """

    id: uuid.UUID
    tenant_id: uuid.UUID
    amount: int
    source_attendance_id: uuid.UUID
    reason: str
    actor_id: uuid.UUID | None
    reverses_entry_id: uuid.UUID | None
    occurred_at: datetime

    def is_reversal(self) -> bool:
        """Whether this row compensates for another entry.

        Derived from ``reverses_entry_id`` rather than from the sign of
        ``amount``: a negative amount is how a reversal *offsets*, but nothing
        stops a future earn policy from writing a negative earning entry, and
        ADR-0013's definition of a compensating entry is that it names what it
        reverses — not that it happens to be negative.
        """
        return self.reverses_entry_id is not None


def _reward_item_row(row: sa.Row[Any]) -> RewardItemRow:
    """Build a :class:`RewardItemRow` from a result row."""
    return RewardItemRow(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        points_cost=row.points_cost,
        fulfilment_cost=row.fulfilment_cost,
        budget_owner_id=row.budget_owner_id,
        funded=row.funded,
        created_at=row.created_at,
    )


def _ledger_entry_row(row: sa.Row[Any]) -> PointLedgerEntryRow:
    """Build a :class:`PointLedgerEntryRow` from a result row."""
    return PointLedgerEntryRow(
        id=row.id,
        tenant_id=row.tenant_id,
        amount=row.amount,
        source_attendance_id=row.source_attendance_id,
        reason=row.reason,
        actor_id=row.actor_id,
        reverses_entry_id=row.reverses_entry_id,
        occurred_at=row.occurred_at,
    )


class RewardCatalogRepository:
    """Reads and creates ``reward_item`` rows under D6's ownership rule.

    Takes a session per call, like every other repository in this package
    (``jobs.py``, ``review.py``, ``pipeline.py``): transaction boundaries
    belong to the caller, and no method here commits.
    """

    def list_listable_items(
        self, session: Session, *, tenant_id: uuid.UUID
    ) -> tuple[RewardItemRow, ...]:
        """Every item in ``tenant_id`` that may actually be shown to a student.

        "Listable" is ADR-0013's pair and nothing looser: ``funded IS TRUE``,
        and a ``budget_owner_id`` that resolves — through the same composite
        ``(tenant_id, id)`` key the foreign key uses — to a real
        ``user_account`` in this tenant. The owner check is an ``INNER JOIN``
        rather than a trusted column read: the point of re-deriving it on the
        read side is that a listing cannot be made to include an unowned item
        by any write that got past, or around, :meth:`create_item`.

        Unfunded and unowned rows are **omitted**, not returned with a flag. A
        flag is a check a caller can forget, which is the shape of the legacy
        defect (Fix #15) this whole surface exists to close.

        Ordered by ``points_cost`` ascending, then ``id``. The ascending sort
        is the one property ADR-0013 keeps from the legacy ``getSortedCatalog``
        ("free-to-give items sort first by construction rather than
        editorially"); ``id`` is the tiebreak that makes the order total, so
        two items at the same cost do not swap places between calls.

        Returns:
            A tuple — immutable, so a caller cannot append to what it was told
            is the listable set. Empty when nothing is listable, which is the
            honest answer for a tenant with no funded, owned items, and is the
            answer every tenant gets today (nothing seeds this table).
        """
        item = schema.reward_item
        account = schema.user_account
        rows = session.execute(
            sa.select(
                item.c.id,
                item.c.tenant_id,
                item.c.name,
                item.c.points_cost,
                item.c.fulfilment_cost,
                item.c.budget_owner_id,
                item.c.funded,
                item.c.created_at,
            )
            .join(
                account,
                sa.and_(
                    account.c.tenant_id == item.c.tenant_id,
                    account.c.id == item.c.budget_owner_id,
                ),
            )
            .where(item.c.tenant_id == tenant_id, item.c.funded.is_(True))
            .order_by(item.c.points_cost.asc(), item.c.id.asc())
        ).all()
        return tuple(_reward_item_row(row) for row in rows)

    def get_item(
        self, session: Session, *, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> RewardItemRow | None:
        """Read one item by id, scoped by tenant — or ``None``.

        Unfiltered by ``funded`` and by owner standing, unlike
        :meth:`list_listable_items`, and that difference is the point: an
        administrator inspecting why an item does not appear needs to see the
        row that does not qualify. This is a by-id read, never a listing, so it
        cannot become the path an unowned item reaches a student through.
        """
        item = schema.reward_item
        row = session.execute(
            sa.select(
                item.c.id,
                item.c.tenant_id,
                item.c.name,
                item.c.points_cost,
                item.c.fulfilment_cost,
                item.c.budget_owner_id,
                item.c.funded,
                item.c.created_at,
            ).where(item.c.tenant_id == tenant_id, item.c.id == item_id)
        ).one_or_none()
        return None if row is None else _reward_item_row(row)

    def create_item(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        name: str,
        points_cost: int,
        fulfilment_cost: Decimal,
        budget_owner_id: uuid.UUID | None,
        funded: bool,
    ) -> RewardItemRow:
        """Create one reward item, refusing any write whose owner cannot be established.

        The ownership check is two refusals in sequence, neither with a
        fallback:

        1. ``smartmatch_domain.rewards.assert_budget_owner_named`` raises
           :class:`~smartmatch_domain.rewards.MissingBudgetOwnerError` when no
           owner was supplied. ``budget_owner_id`` is typed optional here **so
           that this refusal has something to refuse** — a caller threading a
           ``uuid.UUID | None`` through from its own input reaches a named
           error rather than a type-checker complaint at one call site and a
           ``NOT NULL`` violation at another.
        2. A tenant-scoped ``SELECT`` against ``user_account`` raises
           :class:`UnknownBudgetOwnerError` when the id names nobody in this
           tenant — including the case where it names a real account belonging
           to a *different* tenant, which is what the composite key exists to
           refuse.

        Only then is the ``INSERT`` issued, and it names ``funded`` explicitly
        rather than relying on the column's ``server_default``: the default is
        a fail-closed floor for a statement that says nothing, not a way for
        this method to avoid deciding.

        ``fulfilment_cost`` is a :class:`~decimal.Decimal` and not a float, for
        the reason :class:`RewardItemRow` gives.

        No caller in this repository creates a reward item. See this module's
        docstring: nothing seeds a catalog, and D7 has ratified no item.

        Raises:
            MissingBudgetOwnerError: ``budget_owner_id`` is ``None``.
            UnknownBudgetOwnerError: it names nobody in this tenant.
            ValueError: ``name`` is blank.
        """
        owner_id = assert_budget_owner_named(budget_owner_id)
        if not name.strip():
            raise ValueError("a reward item requires a name")

        account = schema.user_account
        owner_exists = session.execute(
            sa.select(account.c.id).where(
                account.c.tenant_id == tenant_id, account.c.id == owner_id
            )
        ).one_or_none()
        if owner_exists is None:
            raise UnknownBudgetOwnerError(
                f"budget_owner_id {owner_id} names no user_account in tenant {tenant_id} — "
                "D6 requires a named owner with standing in this tenant, and there is "
                "no default owner to fall back to"
            )

        item = schema.reward_item
        row = session.execute(
            sa.insert(item)
            .values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                name=name,
                points_cost=points_cost,
                fulfilment_cost=fulfilment_cost,
                budget_owner_id=owner_id,
                funded=funded,
            )
            .returning(
                item.c.id,
                item.c.tenant_id,
                item.c.name,
                item.c.points_cost,
                item.c.fulfilment_cost,
                item.c.budget_owner_id,
                item.c.funded,
                item.c.created_at,
            )
        ).one()
        return _reward_item_row(row)


class PointLedgerRepository:
    """Appends ``point_ledger_entry`` rows, and folds them into a balance.

    Every method here either ``INSERT``s or ``SELECT``s. There is no
    ``update``, no ``delete``, and no method that issues either statement
    against this table — see the module docstring for why that application
    guarantee is currently the only one there is.

    Takes a session per call and commits nothing, like every other repository
    in this package.
    """

    def append_entry(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        source_attendance_id: uuid.UUID,
        amount: int,
        reason: str,
        occurred_at: datetime,
        actor_id: uuid.UUID | None = None,
    ) -> PointLedgerEntryRow:
        """Append one entry deriving from a recorded attendance.

        ``source_attendance_id`` is checked against a real, tenant-scoped
        ``attendance_record`` row before the ``INSERT``
        (:class:`UnknownAttendanceSourceError`), which is ADR-0013's "Points
        derive from recorded attendance and nothing else" stated as a
        precondition rather than left to the composite foreign key alone.

        ``amount`` is supplied by the caller and **not derived** from anything
        here: the points a verified attendance earns is D7, recorded as still
        tentative by ``docs/decisions/d6-rewards-budget-decision-record.md``
        §4, so this module records the number a caller decided rather than
        adopting a tentative one as if it were approved.

        ``actor_id`` defaults to ``None`` — the ordinary case, per migration
        ``0009``: an entry produced by automatic derivation from an attendance
        record has no human actor to name, and forcing one would misstate the
        row's origin.

        ``occurred_at`` is required and must be timezone-aware, matching
        :meth:`~smartmatch_persistence.pipeline.PipelineRepository.record_matched`'s
        discipline against a ``timestamptz`` column: a naive datetime is
        interpreted using the session's local offset rather than UTC, which
        silently records the wrong moment.

        Raises:
            ZeroLedgerAmountError: ``amount`` is zero.
            EmptyLedgerReasonError: ``reason`` is blank.
            ValueError: ``occurred_at`` is naive.
            UnknownAttendanceSourceError: no such attendance row in this tenant.
        """
        assert_ledger_entry_well_formed(amount=amount, reason=reason)
        if occurred_at.tzinfo is None:
            raise ValueError(
                "occurred_at must be timezone-aware — a naive datetime is read against "
                "a timestamptz column using the session's local offset, not UTC"
            )

        attendance = schema.attendance_record
        source_exists = session.execute(
            sa.select(attendance.c.id).where(
                attendance.c.tenant_id == tenant_id,
                attendance.c.id == source_attendance_id,
            )
        ).one_or_none()
        if source_exists is None:
            raise UnknownAttendanceSourceError(
                f"source_attendance_id {source_attendance_id} names no attendance_record "
                f"in tenant {tenant_id} — points derive from recorded attendance and "
                "nothing else (ADR-0013)"
            )

        return self._insert(
            session,
            tenant_id=tenant_id,
            source_attendance_id=source_attendance_id,
            amount=amount,
            reason=reason,
            actor_id=actor_id,
            # An earning entry names no reversed entry, and the domain rule
            # refuses one that tries to — this is not merely "left null".
            reverses_entry_id=assert_reversal_target(is_reversal=False, reverses_entry_id=None),
            occurred_at=occurred_at,
        )

    def append_reversal(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        entry_id: uuid.UUID,
        reason: str,
        occurred_at: datetime,
        actor_id: uuid.UUID | None = None,
    ) -> PointLedgerEntryRow:
        """Append the compensating entry that offsets ``entry_id``.

        ADR-0013: "Attendance recorded in error is corrected by an offsetting
        ledger entry that names what it reverses. The ledger is append-only."
        This method is that correction, and it is an ``INSERT``: the row named
        by ``entry_id`` is read to negate its amount and to carry its
        ``source_attendance_id`` forward — the compensating entry cites the
        same source, which is what makes the pair reconcilable — and is never
        written to.

        Reversing an entry twice is **not** prevented here, and that is not an
        oversight: two compensating entries against one credit are two more
        rows and a balance now negative by one credit's worth, which is visible
        and correctable by a third entry. Refusing it would require either a
        status column on the ledger (which migration ``0009`` deliberately
        omits, because "a column invites exactly the mutation its absence
        forecloses") or a uniqueness rule the schema does not carry. A caller
        that must not double-reverse should read the ledger first.

        ``reason`` is required rather than generated: it is where "what this
        reverses, and why" is recorded, and a generated string would say only
        what the amount already says.

        Raises:
            UnknownLedgerEntryError: ``entry_id`` names no row in this tenant.
            EmptyLedgerReasonError: ``reason`` is blank.
            ValueError: ``occurred_at`` is naive.
        """
        if occurred_at.tzinfo is None:
            raise ValueError(
                "occurred_at must be timezone-aware — a naive datetime is read against "
                "a timestamptz column using the session's local offset, not UTC"
            )

        original = self.get_entry(session, tenant_id=tenant_id, entry_id=entry_id)
        if original is None:
            raise UnknownLedgerEntryError(
                f"point_ledger_entry {entry_id} does not exist in tenant {tenant_id}; "
                "there is nothing to compensate for"
            )

        amount = reversal_amount(original.amount)
        assert_ledger_entry_well_formed(amount=amount, reason=reason)
        return self._insert(
            session,
            tenant_id=tenant_id,
            source_attendance_id=original.source_attendance_id,
            amount=amount,
            reason=reason,
            actor_id=actor_id,
            # ADR-0013's "names what it reverses". The shared
            # source_attendance_id above is carried forward so the pair
            # reconciles against the same evidence, but it is this column that
            # identifies *which entry* was withdrawn — the two are not
            # interchangeable once more than one entry derives from one
            # attendance.
            reverses_entry_id=assert_reversal_target(
                is_reversal=True, reverses_entry_id=original.id
            ),
            occurred_at=occurred_at,
        )

    def get_entry(
        self, session: Session, *, tenant_id: uuid.UUID, entry_id: uuid.UUID
    ) -> PointLedgerEntryRow | None:
        """Read one entry back by id, scoped by tenant — or ``None``."""
        entry = schema.point_ledger_entry
        row = session.execute(
            sa.select(
                entry.c.id,
                entry.c.tenant_id,
                entry.c.amount,
                entry.c.source_attendance_id,
                entry.c.reason,
                entry.c.actor_id,
                entry.c.reverses_entry_id,
                entry.c.occurred_at,
            ).where(entry.c.tenant_id == tenant_id, entry.c.id == entry_id)
        ).one_or_none()
        return None if row is None else _ledger_entry_row(row)

    def entries_for_subject(
        self, session: Session, *, tenant_id: uuid.UUID, subject_id: uuid.UUID
    ) -> tuple[PointLedgerEntryRow, ...]:
        """Every entry credited to ``subject_id``, oldest first.

        The ledger has no ``subject_id`` of its own — an entry names the
        attendance it derives from, and the attendance names the student — so
        this joins through ``attendance_record``. That indirection is the
        derivation rule made structural: there is no way to write an entry for
        a student without an attendance row for that student to hang it on.

        This is the "why is my balance this" read ADR-0013's case for a ledger
        over a counter rests on. Ordered by ``occurred_at`` then ``id``, so the
        order is total and stable across calls.
        """
        entry = schema.point_ledger_entry
        attendance = schema.attendance_record
        rows = session.execute(
            sa.select(
                entry.c.id,
                entry.c.tenant_id,
                entry.c.amount,
                entry.c.source_attendance_id,
                entry.c.reason,
                entry.c.actor_id,
                entry.c.reverses_entry_id,
                entry.c.occurred_at,
            )
            .join(
                attendance,
                sa.and_(
                    attendance.c.tenant_id == entry.c.tenant_id,
                    attendance.c.id == entry.c.source_attendance_id,
                ),
            )
            .where(entry.c.tenant_id == tenant_id, attendance.c.subject_id == subject_id)
            .order_by(entry.c.occurred_at.asc(), entry.c.id.asc())
        ).all()
        return tuple(_ledger_entry_row(row) for row in rows)

    def balance_for_subject(
        self, session: Session, *, tenant_id: uuid.UUID, subject_id: uuid.UUID
    ) -> int:
        """Fold ``subject_id``'s entries into a balance.

        ADR-0013: "A balance is a fold over that ledger. It is never stored as
        a counter and never computed by a client." No column anywhere in this
        schema stores this number; it is recomputed on every call from the rows
        that justify it.

        The fold itself is ``smartmatch_domain.rewards.fold_balance`` rather
        than a ``SUM`` pushed into SQL, so the rule that defines a balance
        lives in one place and is unit-testable without a database. A student
        with no attendance folds to ``0`` — the correct balance, not an unknown
        one, which matters because ADR-0011 otherwise requires unknown to
        render as unknown.
        """
        entries = self.entries_for_subject(session, tenant_id=tenant_id, subject_id=subject_id)
        return fold_balance(entry.amount for entry in entries)

    def _insert(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        source_attendance_id: uuid.UUID,
        amount: int,
        reason: str,
        actor_id: uuid.UUID | None,
        reverses_entry_id: uuid.UUID | None,
        occurred_at: datetime,
    ) -> PointLedgerEntryRow:
        """The one statement that writes this table, shared by both append paths.

        Private and singular on purpose: every write to ``point_ledger_entry``
        in this package goes through here, so "is anything in this module
        capable of mutating a ledger row" is answered by reading one method.

        ``reverses_entry_id`` is a required argument with no default, even
        though the column is nullable. Both callers have already run it through
        ``smartmatch_domain.rewards.assert_reversal_target``, and a default here
        would let a third caller added later write an unnamed reversal by simply
        not mentioning the parameter — which is the defect migration ``0014``
        exists to close.
        """
        entry = schema.point_ledger_entry
        row = session.execute(
            sa.insert(entry)
            .values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                amount=amount,
                source_attendance_id=source_attendance_id,
                reason=reason,
                actor_id=actor_id,
                reverses_entry_id=reverses_entry_id,
                occurred_at=occurred_at,
            )
            .returning(
                entry.c.id,
                entry.c.tenant_id,
                entry.c.amount,
                entry.c.source_attendance_id,
                entry.c.reason,
                entry.c.actor_id,
                entry.c.reverses_entry_id,
                entry.c.occurred_at,
            )
        ).one()
        return _ledger_entry_row(row)
