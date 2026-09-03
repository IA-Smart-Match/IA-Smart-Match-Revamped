"""Rewards rules — D6 budget ownership and the append-only ledger, as pure logic.

ADR-0013 (``docs/architecture/decisions/ADR-0013-attendance-derived-engagement.md``)
makes two structural claims this module states once, as data, so a persistence
writer can refuse a bad write *before* issuing a statement the database would
reject anyway — the same split ``smartmatch_domain.pipeline`` and
``smartmatch_domain.jobs`` already make against their own tables.

**A listable reward has a named owner and a funded balance.** ADR-0013:
"A catalog item with a real fulfilment cost needs a named budget owner and a
funded balance … An item whose fulfilment costs the program money **cannot be
listed** without both." D6 (``docs/decisions/d6-rewards-budget-decision-record.md``
§1) closed the ownership question for pilot scope by naming a human, and the
schema (migration ``0009``) makes ``budget_owner_id`` ``NOT NULL`` with a
composite tenant foreign key. :func:`assert_budget_owner_named` is the
application-side half of that pair: it refuses an *absent* owner rather than
substituting one. There is deliberately no default, no fallback, and no
"system" owner constant in this module — migration ``0009``'s own rationale for
why the column carries no server default ("there is no safe value to fall back
to for who owns a budget") applies identically here.

**The ledger is append-only, and a reversal is a compensating entry.**
ADR-0013: "A reversal is a compensating entry, never a delete." So the only
rule this module needs about changing what the ledger says is how to compute
the *entry that offsets another one* (:func:`reversal_amount`) — there is no
update rule to express, because there is no legitimate update.

**A reversal names what it reverses.** ADR-0013 §"A reversal is a compensating
entry, never a delete" (line 69) requires "an offsetting ledger entry that
names what it reverses", and ``docs/architecture/engagement-model.md``:99 says
the same. :func:`assert_reversal_target` is that requirement, paired with
``point_ledger_entry.reverses_entry_id`` (migration ``0014``).

**On reversing a reversal, ADR-0013 is silent.** Neither it nor
``docs/architecture/engagement-model.md`` says whether a compensating entry may
itself be compensated for. Nothing here invents a prohibition it does not
state: a chain is permitted, each link names its own distinct target, and the
fold reconciles it — :func:`reversal_amount` applied twice returns the original
amount by construction. What *is* refused is the case ADR-0013 does speak to: a
compensating entry that names nothing.

**A balance is a fold, never a stored counter.** :func:`fold_balance` is that
fold and nothing more: it sums signed amounts. It deliberately encodes **no
earn rate** — how many points a verified attendance is worth is D7, which
``docs/decisions/d6-rewards-budget-decision-record.md`` §4 records as still
tentative and explicitly not promoted by D6's closure. Deriving entries from
attendance is therefore not implemented anywhere in this module or its
persistence counterpart; summing entries that already exist needs no such
number.

Nothing in this repository ships a reward HTTP route yet, and this module does
not change that. See ``smartmatch_persistence.rewards``'s docstring for which
gate is still open and why.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

__all__ = [
    "EmptyLedgerReasonError",
    "MisdeclaredReversalTargetError",
    "MissingBudgetOwnerError",
    "UnfundedRewardItemError",
    "ZeroLedgerAmountError",
    "assert_budget_owner_named",
    "assert_ledger_entry_well_formed",
    "assert_listable",
    "assert_reversal_target",
    "fold_balance",
    "is_listable",
    "reversal_amount",
]


class MissingBudgetOwnerError(ValueError):
    """No budget owner was supplied for a reward item.

    D6's requirement is a *named* human, so the absent case is a refusal and
    never a default. ``reward_item.budget_owner_id`` is ``NOT NULL`` with no
    server default (migration ``0009``), which refuses this at the database
    too; this is the identical refusal raised in application code, with a type
    a caller can catch, before any statement is issued.
    """


class UnfundedRewardItemError(ValueError):
    """A reward item without a funded balance was offered for listing.

    ADR-0013 pairs ``funded`` with ``budget_owner_id``: an item whose
    fulfilment costs the program money cannot be *listed* without both. Note
    the asymmetry with the schema — ``funded`` is ``NOT NULL`` but carries
    ``server_default 'false'``, so the database refuses an item that says
    nothing about funding while happily storing one that says "not funded".
    Refusing to *list* the latter is this rule's job, not the column's.
    """


class ZeroLedgerAmountError(ValueError):
    """A ledger entry carrying no points.

    ``ck_point_ledger_entry_amount_nonzero`` (migration ``0009``) refuses this
    at the database. An entry of zero records that nothing happened, which the
    absence of a row already records more cheaply.
    """


class EmptyLedgerReasonError(ValueError):
    """A ledger entry with no reason.

    ``reason`` is ``NOT NULL`` in the schema, which refuses only ``NULL`` — a
    whitespace-only string satisfies the column and defeats the point of it.
    ADR-0013's case for a ledger over a counter is that it can answer "why is
    my balance this"; an entry with a blank reason cannot.
    """


def assert_budget_owner_named(budget_owner_id: uuid.UUID | None) -> uuid.UUID:
    """Return ``budget_owner_id``, or raise if it is absent.

    Returns the id rather than ``None`` so a caller writes
    ``owner = assert_budget_owner_named(candidate)`` and cannot accidentally
    carry the optional type forward past the check.

    Raises:
        MissingBudgetOwnerError: ``budget_owner_id`` is ``None``.
    """
    if budget_owner_id is None:
        raise MissingBudgetOwnerError(
            "a reward item requires a named budget owner (D6, ADR-0013); "
            "there is no default owner to fall back to"
        )
    return budget_owner_id


def is_listable(*, budget_owner_id: uuid.UUID | None, funded: bool) -> bool:
    """Whether an item may appear in a catalog listing.

    Both halves of ADR-0013's pair, and nothing else — point cost and
    fulfilment cost are already bounded by their own CHECK constraints, and
    whether an owner id names a *real same-tenant account* is a question only
    storage can answer (``smartmatch_persistence.rewards``).
    """
    return budget_owner_id is not None and funded


def assert_listable(*, budget_owner_id: uuid.UUID | None, funded: bool) -> uuid.UUID:
    """Return the owner id if the item may be listed, else raise.

    Raises:
        MissingBudgetOwnerError: no owner is named.
        UnfundedRewardItemError: the owner is named but the item is unfunded.
    """
    owner = assert_budget_owner_named(budget_owner_id)
    if not funded:
        raise UnfundedRewardItemError(
            "a reward item with no funded balance cannot be listed (ADR-0013); "
            "naming an owner does not by itself fund the item"
        )
    return owner


def assert_ledger_entry_well_formed(*, amount: int, reason: str) -> None:
    """Refuse a ledger entry the ledger could not later explain.

    Raises:
        ZeroLedgerAmountError: ``amount`` is zero.
        EmptyLedgerReasonError: ``reason`` is empty or whitespace only.
    """
    if amount == 0:
        raise ZeroLedgerAmountError(
            "a point ledger entry must carry a non-zero amount "
            "(ck_point_ledger_entry_amount_nonzero)"
        )
    if not reason.strip():
        raise EmptyLedgerReasonError(
            "a point ledger entry must carry a reason — a ledger that cannot "
            "say why is the counter ADR-0013 replaced"
        )


class MisdeclaredReversalTargetError(ValueError):
    """A ledger entry disagrees with itself about whether it is a reversal.

    Two mistakes, one type: a compensating entry that names no target, and an
    ordinary earning entry that names one. ``point_ledger_entry.reverses_entry_id``
    (migration ``0014``) is nullable precisely because *which* of the two a row
    is is what that column records — so neither case has a default, and both
    are refused rather than resolved.
    """


def assert_reversal_target(
    *, is_reversal: bool, reverses_entry_id: uuid.UUID | None
) -> uuid.UUID | None:
    """Check that a row's reversal target agrees with what kind of entry it is.

    ADR-0013: "Attendance recorded in error is corrected by an offsetting
    ledger entry that **names what it reverses**." Before migration ``0014``
    the only link between a compensating entry and its original was the
    ``source_attendance_id`` they shared, which names the *attendance* and not
    the *entry* — ambiguous the moment two entries derive from one attendance,
    which nothing prevents and which a change of earn policy positively
    invites. This rule is the application-side half of the column that closed
    that gap.

    Returns the target unchanged (``None`` for an earning entry), so a caller
    can write ``target = assert_reversal_target(...)`` and pass the result
    straight to its insert rather than re-deriving which branch it is in.

    Raises:
        MisdeclaredReversalTargetError: a reversal with no target, or an
            earning entry that names one.
    """
    if is_reversal and reverses_entry_id is None:
        raise MisdeclaredReversalTargetError(
            "a compensating entry must name the entry it reverses (ADR-0013); "
            "there is no default target and the shared source_attendance_id is "
            "not specific enough to identify one"
        )
    if not is_reversal and reverses_entry_id is not None:
        raise MisdeclaredReversalTargetError(
            "an earning entry must not name a reversed entry — reverses_entry_id "
            "is what distinguishes a compensating entry from an ordinary one"
        )
    return reverses_entry_id


def reversal_amount(original_amount: int) -> int:
    """The amount of the compensating entry that offsets ``original_amount``.

    The negation, which is the whole of the rule: ``amount`` is a signed
    integer precisely so a reversal is a negative entry naming the same source
    rather than a sign flag alongside a magnitude (migration ``0009``
    docstring). Reversing a reversal is therefore the original amount again,
    and the fold over all three entries is the single remaining credit.

    Raises:
        ZeroLedgerAmountError: ``original_amount`` is zero, so the compensating
            entry would be zero too and would violate the same constraint.
    """
    if original_amount == 0:
        raise ZeroLedgerAmountError(
            "cannot reverse a zero-amount entry — no such entry can exist "
            "(ck_point_ledger_entry_amount_nonzero)"
        )
    return -original_amount


def fold_balance(amounts: Iterable[int]) -> int:
    """Sum signed ledger amounts into a balance.

    ADR-0013: "A balance is a fold over that ledger. It is never stored as a
    counter and never computed by a client." This function is that fold. It
    takes amounts rather than rows so the rule stays free of any storage
    shape, and it is total: an empty ledger folds to ``0``, which is the
    correct balance for a student with no attendance, not an unknown one.
    """
    return sum(amounts)
