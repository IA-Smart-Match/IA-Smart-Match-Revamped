"""Attendance-derived points, funded-only listing, and the redemption state machine.

The pure half of ADR-0013's engagement surface: the fold that turns
``point_ledger_entry`` rows into a balance, the listability rule that keeps an
unowned or unfunded ``reward_item`` out of every catalog, and the
``requested -> approved -> fulfilled | denied | expired`` state machine.
Everything here is a deterministic computation over plain values. This module
imports no ``sqlalchemy``, no ``os``/``pathlib``/``socket``, and makes no
network call — the same fence :mod:`smartmatch_domain.spend` and
:mod:`smartmatch_domain.jobs` hold.

Why a fold and not a counter
----------------------------
ADR-0013's case against a stored balance is that a counter "cannot answer 'why
is my balance this'". Migration ``0009`` therefore gives no table a balance
column, and ``tests/unit/test_engagement_schema.py`` keeps it that way.
:func:`fold_balance` is the other half of that decision: the balance is
recomputed from the entries on every request, and a correction is an appended
compensating entry — never an ``UPDATE``, never a ``DELETE``, and never a
number this module remembers between calls. Nothing in this module holds
mutable state; every public type is a frozen dataclass and every constant is
immutable.

The earn policy, and what is tentative about it
-----------------------------------------------
``docs/decisions/pilot-decisions.md`` §D7 records **100 points per verified
attendance**, initial bands of **300 / 600 / 1,000**, and calibration
**N = 3**, and records all of them as *tentative* — D7 is not ratified. The
constants below therefore carry the D7 values verbatim rather than inventing an
economy of their own, and :data:`EARN_POLICY_RATIFIED` states in code that they
are not ratified. The calibration property from
``docs/architecture/engagement-model.md`` §3 —
``min(points_cost over listed items) <= N * points_per_event`` — is exposed as
:func:`satisfies_calibration` so a catalog can be *checked* against N rather
than assumed to satisfy it.

Unknown is not zero (ADR-0011)
-------------------------------
A fold over an empty sequence of entries is genuinely ``0`` — zero *known*
entries is a known balance of zero, not a missing one. What this module refuses
to do is answer a question it has no evidence for: :func:`events_still_needed`
raises rather than returning ``0`` for an item that is not listable, because
"how many more events until you can afford a reward nobody will honour" has no
honest number. The same reasoning is why :func:`listable_items` filters rather
than defaulting a missing ``budget_owner_id`` to anything.

What this module deliberately does not do
------------------------------------------
No HTTP, no route, no OpenAPI operation, no authorization decision: the read
and redemption roles are still TBD (D6, "fields this direction does not
resolve"), so nothing here decides who may call it. No catalog content and no
seeded item: :data:`D7_TENTATIVE_POINT_BANDS` is the recorded band list, not a
shipped catalog. No money moves; ``fulfilment_cost`` is a recorded figure this
module never spends, reserves, or discloses.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final

__all__ = [
    "CALIBRATION_N_TENTATIVE",
    "D7_TENTATIVE_POINT_BANDS",
    "EARN_POLICY_RATIFIED",
    "POINTS_PER_VERIFIED_ATTENDANCE",
    "REDEMPTION_TRANSITIONS",
    "TERMINAL_REDEMPTION_STATES",
    "InvalidRedemptionTransition",
    "LedgerEntry",
    "LedgerEntryKind",
    "Redemption",
    "RedemptionState",
    "RewardItem",
    "UnlistableRewardError",
    "affordable_items",
    "attendance_credit",
    "cheapest_listable_cost",
    "events_still_needed",
    "fold_balance",
    "is_listable",
    "listable_items",
    "redemption_debit_amount",
    "replay_states",
    "request_redemption",
    "reversal_entry_amount",
    "satisfies_calibration",
]

#: D7's tentative earning rate: 100 points per *verified* attendance. One
#: ``attendance_record`` row is one verified attendance — ADR-0013's "points
#: derive from recorded attendance and nothing else" — so this constant is the
#: whole earn policy. Streaks, logins, and referrals earn nothing, deliberately:
#: D7 says the basis is "attendance alone" so the calibration property can be
#: evaluated identically for every student.
POINTS_PER_VERIFIED_ATTENDANCE: Final[int] = 100

#: D7's tentative calibration N: the cheapest listed reward should be reachable
#: within three verified attendances. ADR-0013 calls 3 "a proposal, not
#: approval"; D7 records it as tentative. Used by
#: :func:`satisfies_calibration`, which takes N as an argument so a caller must
#: name the number it is asserting against rather than inherit one silently.
CALIBRATION_N_TENTATIVE: Final[int] = 3

#: D7's recorded initial bands, in ascending order. This is the decision
#: record's list, transcribed — not a catalog. No ``reward_item`` row is created
#: from it anywhere in this repository, and D6 blocks a shipped catalog
#: regardless. Present so a test can cite the recorded figures instead of
#: hard-coding invented ones.
D7_TENTATIVE_POINT_BANDS: Final[tuple[int, ...]] = (300, 600, 1000)

#: D7 is **tentative**, not ratified — ``docs/decisions/pilot-decisions.md``
#: §D7's own heading. Stated as a value so a caller (or a test) can assert on
#: the ratification status rather than on a comment about it, and so promoting
#: the numbers later is a visible one-line change rather than a silent one.
EARN_POLICY_RATIFIED: Final[bool] = False


# ---------------------------------------------------------------------------
# The ledger and its fold
# ---------------------------------------------------------------------------


class LedgerEntryKind(StrEnum):
    """What a ``point_ledger_entry`` row *is*, as migration ``0019`` records it.

    A ``StrEnum`` for the reason :class:`RedemptionState` is one: the member
    compares equal to the text ``ck_point_ledger_entry_kind`` pins, so one
    spelling serves the domain, the repository, and the column.

    Three kinds and no more. The vocabulary is closed on purpose: every way a
    balance can change is one of these, and a fourth would be a way to move
    points that no rule in ADR-0013 describes.
    """

    #: One verified attendance, credited once. Positive, names an attendance.
    ATTENDANCE_CREDIT = "attendance_credit"
    #: The compensating entry that withdraws a credit. Negative, names the same
    #: attendance — ADR-0013's "a reversal is a compensating entry, never a
    #: delete".
    REVERSAL = "reversal"
    #: The debit taken when a redemption is fulfilled. Negative, names a
    #: ``redemption`` and **no** attendance: it does not derive from evidence
    #: of attending anything.
    REDEMPTION_DEBIT = "redemption_debit"


@dataclass(frozen=True)
class LedgerEntry:
    """One ``point_ledger_entry`` row, as the fold sees it.

    Frozen, because the table is append-only: there is no legitimate mutation
    of an entry either in the database — migration ``0009`` gives the table no
    ``status``, ``version``, or ``updated_at`` column, and ``0019`` adds a
    ``BEFORE UPDATE`` trigger that refuses one outright — or in this
    representation of one.

    ``amount`` is signed. A correction is a negative entry citing the same
    ``source_attendance_id`` with a ``reason`` that says what it corrects —
    ADR-0013's "a reversal is a compensating entry, never a delete".

    Both source columns are optional **as types** and exactly one of them is
    populated **as a rule**, which :meth:`__post_init__` enforces. That is the
    application twin of ``ck_point_ledger_entry_kind`` (migration ``0019``):
    the nullability exists so a redemption debit — which derives from a
    redemption, not from an attendance — has a row shape at all, and the rule
    exists so the nullability is not a hole through which an entry deriving
    from nothing could arrive.
    """

    entry_id: uuid.UUID
    tenant_id: uuid.UUID
    kind: LedgerEntryKind
    amount: int
    reason: str
    occurred_at: datetime
    source_attendance_id: uuid.UUID | None = None
    source_redemption_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        """Refuse a shape ``ck_point_ledger_entry_kind`` would refuse.

        Checked here as well as in the database because this type is also
        built from values that never came from a row — a test, or a caller
        assembling an entry it is about to insert — and a shape the database
        would reject should fail where it was constructed rather than three
        frames later inside an ``INSERT``.

        Raises:
            ValueError: the kind and the fields disagree.
        """
        expected_attendance = self.kind is not LedgerEntryKind.REDEMPTION_DEBIT
        if (self.source_attendance_id is not None) != expected_attendance:
            raise ValueError(
                f"a {self.kind.value} entry must "
                f"{'name' if expected_attendance else 'not name'} an attendance record"
            )
        if (self.source_redemption_id is not None) != (not expected_attendance):
            raise ValueError(
                f"a {self.kind.value} entry must "
                f"{'not name' if expected_attendance else 'name'} a redemption"
            )
        positive = self.kind is LedgerEntryKind.ATTENDANCE_CREDIT
        if positive and self.amount <= 0:
            raise ValueError(f"an attendance credit must be positive, not {self.amount}")
        if not positive and self.amount >= 0:
            raise ValueError(f"a {self.kind.value} must be negative, not {self.amount}")


def fold_balance(entries: Iterable[LedgerEntry]) -> int:
    """Sum an append-only ledger into a balance.

    Deterministic and order-independent: addition over the signed ``amount``
    column commutes, so a caller need not order its query and two callers
    reading the same rows in different orders cannot disagree.

    An empty ledger folds to ``0``. That is not the ADR-0011 "unknown rendered
    as zero" defect: zero *known* entries is a known balance of zero. The
    unknown case is a subject whose entries were never read at all, which is a
    question this function is never asked — it folds what it is given.
    """
    return sum(entry.amount for entry in entries)


def attendance_credit(points_per_event: int = POINTS_PER_VERIFIED_ATTENDANCE) -> int:
    """The credit one verified attendance earns under the D7 earn policy.

    A function rather than a bare constant read, so the rate is named at every
    call site and so a future rule *version* (D7: "points are earned under the
    rule version in effect at the time of the attendance") has an obvious seam
    to enter through.

    Raises:
        ValueError: ``points_per_event`` is not positive. A zero or negative
            earning rate would make attendance evidence produce a row
            ``ck_point_ledger_entry_amount_nonzero`` refuses, or a debit.
    """
    if points_per_event <= 0:
        raise ValueError(f"points per verified attendance must be positive, not {points_per_event}")
    return points_per_event


def reversal_entry_amount(credited: int) -> int:
    """The signed amount of the compensating entry that withdraws ``credited``.

    The reversal is a *new row*, which is why this returns an amount to insert
    rather than mutating anything. Refuses a zero, which
    ``ck_point_ledger_entry_amount_nonzero`` would refuse anyway — named here so
    the caller gets a catchable ``ValueError`` before a statement is issued, the
    same application-code-twin idiom
    ``smartmatch_persistence.attendance.ATTENDANCE_METHODS`` uses.

    Note the schema limit this repository still carries: after migration
    ``0015`` there is no ``reverses_entry_id`` column, so a compensating entry
    can name only the *attendance* it corrects, not the specific entry it
    withdraws. See this module's persistence counterpart for how that is
    handled today.
    """
    if credited == 0:
        raise ValueError(
            "a zero ledger entry cannot be reversed "
            "(ck_point_ledger_entry_amount_nonzero refuses a zero amount)"
        )
    return -credited


def redemption_debit_amount(points_cost: int) -> int:
    """The signed amount of the debit that pays for a redemption.

    Symmetric with :func:`reversal_entry_amount`, and separate from it because
    the two are different facts: a reversal withdraws a credit that should not
    have been given, and a debit spends points that were properly earned. The
    ledger tells them apart by ``kind`` rather than by sign alone
    (:class:`LedgerEntryKind`), which is why a caller must choose.

    Takes the redemption's **snapshot** cost, not the item's current
    ``points_cost``: D7 says "existing redemptions retain their point-cost
    snapshot", so a reward repriced between the request and the fulfilment is
    paid for at the price the student was shown.

    Raises:
        ValueError: ``points_cost`` is not positive. Zero would produce a row
            ``ck_point_ledger_entry_amount_nonzero`` refuses, and a negative
            cost would make redeeming a reward *earn* points.
    """
    if points_cost <= 0:
        raise ValueError(f"a redemption debit needs a positive cost, not {points_cost}")
    return -points_cost


# ---------------------------------------------------------------------------
# Reward items and listability
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RewardItem:
    """A ``reward_item`` row as the listing rule sees it.

    ``budget_owner_id`` is typed ``uuid.UUID | None`` even though the column is
    ``NOT NULL``. That is not a softening of the constraint: it is what lets
    :func:`is_listable` be *tested* against the unowned case, which the database
    will not let anyone write. A row read back from PostgreSQL always has an
    owner; a row constructed in a test may not, and the rule must refuse it.
    """

    item_id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    points_cost: int
    budget_owner_id: uuid.UUID | None
    funded: bool


class UnlistableRewardError(ValueError):
    """An operation was asked for about an item that may not be listed.

    Raised rather than answered with a zero or a ``False``: "how far is this
    student from a reward nobody owns" has no honest answer, and returning one
    is the ADR-0011 defect of rendering an unknown as a number.
    """


def is_listable(item: RewardItem) -> bool:
    """Whether ``item`` may appear in a catalog at all.

    Both halves of D6, and nothing else: a named budget owner **and** a funded
    balance. Migration ``0009`` makes both columns ``NOT NULL`` so the database
    refuses an unowned or unfunded *row*; this function is why an unfunded row
    that nevertheless exists (``funded`` defaults to ``false``, which is an
    insert-time default and not a listing permission) never reaches a student.

    Deliberately not a check of anything else. ``points_cost > 0`` is a database
    CHECK, and re-asserting it here would suggest that constraint is optional.
    """
    return item.budget_owner_id is not None and item.funded


def listable_items(items: Iterable[RewardItem]) -> tuple[RewardItem, ...]:
    """The subset of ``items`` that :func:`is_listable` accepts, order preserved.

    Filters rather than raising: a catalog containing one unfunded row is a
    catalog with one fewer listable item, not an error. The refusal is that the
    row is absent from the result, which is what the caller renders.
    """
    return tuple(item for item in items if is_listable(item))


def cheapest_listable_cost(items: Iterable[RewardItem]) -> int | None:
    """The lowest ``points_cost`` among listable items, or ``None`` if there are none.

    ``None``, not ``0``: a catalog with nothing listable has no cheapest item,
    and ``0`` would read as a free reward.
    """
    costs = [item.points_cost for item in listable_items(items)]
    return min(costs) if costs else None


def satisfies_calibration(
    items: Iterable[RewardItem],
    *,
    points_per_event: int,
    events: int,
) -> bool:
    """The engagement-model §3 property, evaluated over the **listable** items.

    ``min(points_cost over listed items) <= events * points_per_event``.

    Evaluated over listable items only, deliberately: an unfunded one-point row
    would otherwise satisfy the calibration on paper while being unreachable in
    fact, which is precisely the legacy defect — a catalog making a promise the
    program could not keep — in a new costume.

    Returns ``False`` for a catalog with nothing listable. A catalog that lists
    nothing does not satisfy "the cheapest reward is reachable in N events"; it
    has no cheapest reward, and returning ``True`` would let an empty catalog
    pass the calibration check.

    Both ``points_per_event`` and ``events`` are keyword-only and required: D7 is
    tentative, so every assertion about calibration must name the numbers it is
    asserting against rather than silently inherit a figure nobody ratified.

    Raises:
        ValueError: either argument is not positive.
    """
    if points_per_event <= 0 or events <= 0:
        raise ValueError(
            "calibration needs a positive earning rate and a positive event count, not "
            f"points_per_event={points_per_event}, events={events}"
        )
    cheapest = cheapest_listable_cost(items)
    if cheapest is None:
        return False
    return cheapest <= events * points_per_event


def affordable_items(items: Iterable[RewardItem], *, balance: int) -> tuple[RewardItem, ...]:
    """Listable items whose cost the folded ``balance`` already covers.

    Unlistable items are excluded before affordability is considered, so an
    unfunded item is never described as affordable.
    """
    return tuple(item for item in listable_items(items) if item.points_cost <= balance)


def events_still_needed(
    item: RewardItem,
    *,
    balance: int,
    points_per_event: int = POINTS_PER_VERIFIED_ATTENDANCE,
) -> int:
    """Verified attendances remaining before ``balance`` reaches ``item``'s cost.

    ``0`` when the item is already affordable. This is the "progress only toward
    reachable items" rule from ``docs/architecture/engagement-model.md`` §4: the
    number is meaningful only for an item the student could actually receive.

    Raises:
        UnlistableRewardError: ``item`` is unowned or unfunded. There is no
            honest distance to a reward nobody will honour, so this refuses
            rather than returning a number a progress bar would render.
        ValueError: ``points_per_event`` is not positive — otherwise the
            remaining-events arithmetic has no answer.
    """
    if not is_listable(item):
        raise UnlistableRewardError(
            f"reward_item {item.item_id} is not listable "
            f"(budget_owner_id={item.budget_owner_id!r}, funded={item.funded}); "
            "progress toward an unowned or unfunded reward has no honest value (D6, ADR-0011)"
        )
    if points_per_event <= 0:
        raise ValueError(f"points per verified attendance must be positive, not {points_per_event}")
    shortfall = item.points_cost - balance
    if shortfall <= 0:
        return 0
    return -(-shortfall // points_per_event)


# ---------------------------------------------------------------------------
# The redemption state machine
# ---------------------------------------------------------------------------


class RedemptionState(StrEnum):
    """ADR-0013's redemption vocabulary, verbatim.

    ``requested -> approved -> fulfilled | denied | expired``. A ``StrEnum`` for
    the reason :class:`smartmatch_domain.jobs.JobState` is one: the member
    compares equal to the text a database CHECK constraint would pin, so a
    single spelling serves the state machine and the eventual column.
    """

    REQUESTED = "requested"
    APPROVED = "approved"
    FULFILLED = "fulfilled"
    DENIED = "denied"
    EXPIRED = "expired"


#: The only legal moves. ``denied`` and ``expired`` are reachable from
#: ``requested`` (a coordinator refuses it, or it ages out before anyone acts),
#: and ``expired`` also from ``approved`` (approved but never handed over).
#: ``fulfilled`` is reachable **only** from ``approved``: ADR-0013 says
#: redemption "is a command with an approval step", so a request that skips
#: approval and lands fulfilled would be that step deleted rather than passed.
#: The three terminal states have no outgoing moves, mirroring
#: :data:`smartmatch_domain.jobs.TRANSITIONS` — a terminal state that can be
#: re-entered is a fulfilment that can be repeated.
REDEMPTION_TRANSITIONS: Final[Mapping[RedemptionState, frozenset[RedemptionState]]] = (
    MappingProxyType(
        {
            RedemptionState.REQUESTED: frozenset(
                {RedemptionState.APPROVED, RedemptionState.DENIED, RedemptionState.EXPIRED}
            ),
            RedemptionState.APPROVED: frozenset(
                {RedemptionState.FULFILLED, RedemptionState.EXPIRED}
            ),
            RedemptionState.FULFILLED: frozenset(),
            RedemptionState.DENIED: frozenset(),
            RedemptionState.EXPIRED: frozenset(),
        }
    )
)

#: Derived from :data:`REDEMPTION_TRANSITIONS` rather than listed separately, so
#: the two cannot drift — the idiom ``smartmatch_domain.jobs`` already uses.
TERMINAL_REDEMPTION_STATES: Final[frozenset[RedemptionState]] = frozenset(
    state for state, allowed in REDEMPTION_TRANSITIONS.items() if not allowed
)


class InvalidRedemptionTransition(ValueError):
    """A move the redemption state machine does not allow."""

    def __init__(self, current: RedemptionState, requested: RedemptionState) -> None:
        allowed = sorted(state.value for state in REDEMPTION_TRANSITIONS[current])
        super().__init__(
            f"redemption cannot move from {current.value} to {requested.value}; "
            f"allowed from {current.value}: {allowed or ['(terminal)']}"
        )
        self.current = current
        self.requested = requested


@dataclass(frozen=True)
class Redemption:
    """One redemption, with the point cost it was requested against.

    ``points_cost_snapshot`` is D7's "existing redemptions retain their
    point-cost snapshot": repricing a reward must not reprice a request already
    made against the old price. It is a field on the redemption rather than a
    lookup through ``reward_item`` for exactly that reason — a lookup would
    return today's price, which is the defect.

    ``item_name_snapshot`` is the second of D7's two "consequences that must
    survive into any implementation": "a deactivated reward blocks new requests
    but stays visible on existing tickets". An in-flight ticket that has to join
    back to a row someone may deactivate cannot say what it is for.

    Frozen: :meth:`transition` returns a new value rather than mutating this
    one, so a caller cannot half-apply a move and no in-flight redemption
    changes under a concurrent reader.
    """

    redemption_id: uuid.UUID
    tenant_id: uuid.UUID
    subject_id: uuid.UUID
    item_id: uuid.UUID
    item_name_snapshot: str
    points_cost_snapshot: int
    state: RedemptionState

    def transition(self, requested: RedemptionState) -> Redemption:
        """Return a copy of this redemption in ``requested``.

        Raises:
            InvalidRedemptionTransition: the move is not in
                :data:`REDEMPTION_TRANSITIONS` — including every move out of a
                terminal state, and every self-transition.
        """
        if requested not in REDEMPTION_TRANSITIONS[self.state]:
            raise InvalidRedemptionTransition(self.state, requested)
        return Redemption(
            redemption_id=self.redemption_id,
            tenant_id=self.tenant_id,
            subject_id=self.subject_id,
            item_id=self.item_id,
            item_name_snapshot=self.item_name_snapshot,
            points_cost_snapshot=self.points_cost_snapshot,
            state=requested,
        )

    @property
    def is_terminal(self) -> bool:
        """Whether no further move is legal from this redemption's state."""
        return self.state in TERMINAL_REDEMPTION_STATES


def request_redemption(
    *,
    redemption_id: uuid.UUID,
    subject_id: uuid.UUID,
    item: RewardItem,
    balance: int,
) -> Redemption:
    """Open a redemption for ``item`` at the caller's folded ``balance``.

    Both refusals are checked before any redemption value exists, so an
    unaffordable or unlistable request cannot be represented at all rather than
    being represented and rejected later:

    * An unlistable item is refused (D6) — a request against a reward nobody
      owns or funds is a promise the program cannot keep.
    * A balance below the item's cost is refused. The balance passed in must be
      a server-side fold (:func:`fold_balance`); ADR-0013 forbids a browser
      computing one, and this function has no way to obtain one itself, which is
      deliberate — it is pure.

    The returned redemption is ``requested``, never ``approved``: the approval
    step is ADR-0013's, and a function that could return an already-approved
    redemption would be that step's deletion.

    Raises:
        UnlistableRewardError: ``item`` is unowned or unfunded.
        ValueError: ``balance`` does not cover ``item.points_cost``.
    """
    if not is_listable(item):
        raise UnlistableRewardError(
            f"reward_item {item.item_id} is not listable "
            f"(budget_owner_id={item.budget_owner_id!r}, funded={item.funded}); "
            "an unowned or unfunded reward cannot be redeemed (D6)"
        )
    if balance < item.points_cost:
        raise ValueError(
            f"balance {balance} does not cover reward_item {item.item_id} at "
            f"{item.points_cost} points"
        )
    return Redemption(
        redemption_id=redemption_id,
        tenant_id=item.tenant_id,
        subject_id=subject_id,
        item_id=item.item_id,
        item_name_snapshot=item.name,
        points_cost_snapshot=item.points_cost,
        state=RedemptionState.REQUESTED,
    )


def replay_states(initial: RedemptionState, moves: Sequence[RedemptionState]) -> RedemptionState:
    """Apply ``moves`` in order from ``initial``, refusing the first illegal one.

    For a caller reconstructing a redemption's current state from an audited
    sequence of transitions. Raises :class:`InvalidRedemptionTransition` on the
    first move the machine refuses, naming the state it was actually in — never
    silently skipping it.
    """
    state = initial
    for move in moves:
        if move not in REDEMPTION_TRANSITIONS[state]:
            raise InvalidRedemptionTransition(state, move)
        state = move
    return state
