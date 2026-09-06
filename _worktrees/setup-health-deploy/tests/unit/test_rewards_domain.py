"""The rewards domain: the fold, the listing rule, and the redemption machine.

No database and no network: every function under test in
``smartmatch_domain.rewards`` is a computation over plain values, which is what
makes this a unit test rather than an addition to
``tests/integration/test_rewards_repository.py``. That file proves PostgreSQL
holds up its end; this one proves the rules hold on a machine with no
PostgreSQL at all.

Three things are being defended here.

**Fix #9 — the balance is a fold.** The legacy computed it in the browser from
two summary counters. The tests below prove the balance is a pure function of
the entries, order-independent, and that a correction moves it by appending a
compensating entry rather than by editing anything.

**Fix #15 — the catalog named nobody.** ``is_listable`` requires both halves of
D6, and every listing-shaped function in the module goes through it: an
unfunded or unowned item is absent from the listing, is never called
affordable, cannot be redeemed, and has no progress number at all.

**ADR-0013's approval step.** ``requested -> fulfilled`` is not a shortcut; it
is the approval step deleted, and the transition table refuses it.

The D7 numbers used below are read from the module's own constants, which are
transcribed from ``docs/decisions/pilot-decisions.md`` §D7. No test here
invents an economy: ``test_d7_numbers_match_the_recorded_decision`` pins the
transcription, and ``test_earn_policy_is_not_claimed_ratified`` keeps the
tentative status honest.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from smartmatch_domain.rewards import (
    CALIBRATION_N_TENTATIVE,
    D7_TENTATIVE_POINT_BANDS,
    EARN_POLICY_RATIFIED,
    POINTS_PER_VERIFIED_ATTENDANCE,
    REDEMPTION_TRANSITIONS,
    TERMINAL_REDEMPTION_STATES,
    InvalidRedemptionTransition,
    LedgerEntry,
    LedgerEntryKind,
    RedemptionState,
    RewardItem,
    UnlistableRewardError,
    affordable_items,
    attendance_credit,
    cheapest_listable_cost,
    events_still_needed,
    fold_balance,
    is_listable,
    listable_items,
    redemption_debit_amount,
    replay_states,
    request_redemption,
    reversal_entry_amount,
    satisfies_calibration,
)

_TENANT = uuid.uuid4()
_OWNER = uuid.uuid4()
_SUBJECT = uuid.uuid4()
_EPOCH = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def _entry(amount: int, *, minutes: int = 0, source: uuid.UUID | None = None) -> LedgerEntry:
    """An attendance-sourced ledger entry with a synthetic id and a fixed clock.

    The kind follows the sign, which is exactly the derivation migration
    ``0019``'s backfill states for rows written before ``kind`` existed: a
    positive attendance-sourced entry is the credit, a negative one is the
    reversal that withdraws it. :func:`_debit` builds the third kind, which has
    no attendance at all.
    """
    return LedgerEntry(
        entry_id=uuid.uuid4(),
        tenant_id=_TENANT,
        kind=(LedgerEntryKind.ATTENDANCE_CREDIT if amount > 0 else LedgerEntryKind.REVERSAL),
        amount=amount,
        source_attendance_id=source or uuid.uuid4(),
        reason="synthetic fixture",
        occurred_at=_EPOCH + timedelta(minutes=minutes),
    )


def _debit(amount: int, *, minutes: int = 0, redemption: uuid.UUID | None = None) -> LedgerEntry:
    """A redemption debit: no attendance, a redemption, and a negative amount.

    The row shape that did not exist before migration ``0019`` — see
    ``test_a_redemption_is_durable_and_its_debit_is_representable``.
    """
    return LedgerEntry(
        entry_id=uuid.uuid4(),
        tenant_id=_TENANT,
        kind=LedgerEntryKind.REDEMPTION_DEBIT,
        amount=amount,
        source_redemption_id=redemption or uuid.uuid4(),
        reason="synthetic fixture",
        occurred_at=_EPOCH + timedelta(minutes=minutes),
    )


def _item(
    *,
    points_cost: int,
    funded: bool = True,
    owner: uuid.UUID | None = _OWNER,
    name: str = "synthetic reward",
) -> RewardItem:
    """A reward item. Defaults to the listable case; tests vary one half at a time."""
    return RewardItem(
        item_id=uuid.uuid4(),
        tenant_id=_TENANT,
        name=name,
        points_cost=points_cost,
        budget_owner_id=owner,
        funded=funded,
    )


# ---------------------------------------------------------------------------
# The recorded D7 numbers
# ---------------------------------------------------------------------------


def test_d7_numbers_match_the_recorded_decision():
    """The constants are D7's figures, transcribed — not an economy invented here.

    ``docs/decisions/pilot-decisions.md`` §D7: 100 points per verified
    attendance, bands 300 / 600 / 1,000, calibration N = 3. Pinned so a later
    edit that quietly retunes the economy has to change this test and say so.
    """
    assert POINTS_PER_VERIFIED_ATTENDANCE == 100
    assert D7_TENTATIVE_POINT_BANDS == (300, 600, 1000)
    assert CALIBRATION_N_TENTATIVE == 3


def test_earn_policy_is_not_claimed_ratified():
    """D7 is tentative, and the module says so in a value rather than a comment."""
    assert EARN_POLICY_RATIFIED is False


def test_the_d7_bands_satisfy_d7_calibration_by_construction():
    """3 x 100 = 300, which is the cheapest recorded band exactly.

    Asserted against the *tentative* numbers, named explicitly at the call site
    — this is a property of the recorded proposal, not an approval of it.
    """
    catalog = [_item(points_cost=cost) for cost in D7_TENTATIVE_POINT_BANDS]
    assert satisfies_calibration(
        catalog,
        points_per_event=POINTS_PER_VERIFIED_ATTENDANCE,
        events=CALIBRATION_N_TENTATIVE,
    )
    assert min(D7_TENTATIVE_POINT_BANDS) == CALIBRATION_N_TENTATIVE * POINTS_PER_VERIFIED_ATTENDANCE


# ---------------------------------------------------------------------------
# The fold
# ---------------------------------------------------------------------------


def test_balance_folds_the_entries():
    assert fold_balance([_entry(100), _entry(100, minutes=1), _entry(100, minutes=2)]) == 300


def test_fold_is_order_independent():
    """Two readers of the same rows in different orders cannot disagree."""
    entries = [_entry(100), _entry(-100, minutes=1), _entry(300, minutes=2)]
    assert fold_balance(entries) == fold_balance(list(reversed(entries)))


def test_empty_ledger_folds_to_zero():
    """Zero known entries is a known zero — not the ADR-0011 unknown-as-zero defect.

    The unknown case is a subject whose rows were never read, which this
    function is never asked about: it folds exactly what it is handed.
    """
    assert fold_balance([]) == 0


def test_a_reversal_moves_the_balance_by_appending():
    """The compensating entry is a new value in the sequence, not an edit of one.

    ADR-0013: "a reversal is a compensating entry, never a delete". The earned
    entry is still present in the folded sequence afterwards, and still says
    what it said.
    """
    source = uuid.uuid4()
    earned = _entry(100, source=source)
    ledger = [earned]
    assert fold_balance(ledger) == 100

    ledger.append(_entry(reversal_entry_amount(earned.amount), minutes=5, source=source))
    assert fold_balance(ledger) == 0
    assert ledger[0] is earned
    assert ledger[0].amount == 100


def test_ledger_entries_are_immutable():
    """Append-only in the type, not only in the table."""
    entry = _entry(100)
    with pytest.raises(Exception):  # noqa: B017 - FrozenInstanceError is a dataclasses detail
        entry.amount = 999  # type: ignore[misc]


def test_attendance_credit_is_the_d7_rate_by_default():
    assert attendance_credit() == POINTS_PER_VERIFIED_ATTENDANCE
    assert attendance_credit(250) == 250


@pytest.mark.parametrize("rate", [0, -1, -100])
def test_a_non_positive_earning_rate_is_refused(rate: int):
    """A zero credit is a row ``ck_point_ledger_entry_amount_nonzero`` refuses."""
    with pytest.raises(ValueError, match="must be positive"):
        attendance_credit(rate)


def test_reversing_a_zero_entry_is_refused():
    with pytest.raises(ValueError, match="nonzero"):
        reversal_entry_amount(0)


def test_reversal_of_a_negative_entry_is_positive():
    """The arithmetic is a negation, not an ``abs`` — the sign carries meaning."""
    assert reversal_entry_amount(-100) == 100
    assert reversal_entry_amount(100) == -100


# ---------------------------------------------------------------------------
# Listability — Fix #15
# ---------------------------------------------------------------------------


def test_a_funded_owned_item_is_listable():
    assert is_listable(_item(points_cost=300)) is True


def test_an_unfunded_item_is_not_listable():
    """``funded``'s server default is false, and a default is not a permission."""
    assert is_listable(_item(points_cost=300, funded=False)) is False


def test_an_unowned_item_is_not_listable():
    """D6: a named human budget owner, or the item is not shippable."""
    assert is_listable(_item(points_cost=300, owner=None)) is False


def test_an_unowned_unfunded_item_is_not_listable():
    assert is_listable(_item(points_cost=300, owner=None, funded=False)) is False


def test_listing_drops_unfunded_and_unowned_rows_and_keeps_order():
    listable_a = _item(points_cost=300, name="a")
    listable_b = _item(points_cost=600, name="b")
    catalog = [
        _item(points_cost=1, funded=False, name="unfunded"),
        listable_a,
        _item(points_cost=1, owner=None, name="unowned"),
        listable_b,
    ]
    assert listable_items(catalog) == (listable_a, listable_b)


def test_cheapest_listable_cost_ignores_a_cheap_unfunded_row():
    """The trap this function exists to avoid: a 1-point row nobody funds."""
    catalog = [_item(points_cost=1, funded=False), _item(points_cost=600)]
    assert cheapest_listable_cost(catalog) == 600


def test_cheapest_listable_cost_of_an_empty_catalog_is_none():
    """``None``, not ``0`` — ``0`` would read as a free reward."""
    assert cheapest_listable_cost([]) is None
    assert cheapest_listable_cost([_item(points_cost=300, funded=False)]) is None


def test_calibration_is_not_satisfied_by_an_unfunded_bargain():
    """The legacy defect in a new costume, refused.

    A 1-point unfunded row would satisfy ``min(cost) <= N * rate`` on paper
    while being unreachable in fact. The property is evaluated over listable
    items only, so the 1,200-point listed item is what it is measured against.
    """
    catalog = [_item(points_cost=1, funded=False), _item(points_cost=1200)]
    assert not satisfies_calibration(catalog, points_per_event=100, events=3)


def test_an_empty_catalog_does_not_satisfy_calibration():
    """A catalog with no cheapest reward does not satisfy "reachable in N events"."""
    assert not satisfies_calibration([], points_per_event=100, events=3)


@pytest.mark.parametrize(("rate", "events"), [(0, 3), (100, 0), (-100, 3), (100, -1)])
def test_calibration_refuses_non_positive_inputs(rate: int, events: int):
    with pytest.raises(ValueError, match="positive"):
        satisfies_calibration([_item(points_cost=300)], points_per_event=rate, events=events)


def test_affordable_items_never_include_an_unlistable_one():
    """Even a cheap unfunded row is never described as affordable."""
    reachable = _item(points_cost=300)
    catalog = [reachable, _item(points_cost=100, funded=False), _item(points_cost=1000)]
    assert affordable_items(catalog, balance=300) == (reachable,)


# ---------------------------------------------------------------------------
# Progress — engagement-model §4
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cost", "balance", "expected"),
    [
        (300, 0, 3),
        (300, 100, 2),
        (300, 250, 1),
        (300, 300, 0),
        (300, 400, 0),
        (1000, 0, 10),
        (1000, 50, 10),
    ],
)
def test_events_still_needed_rounds_up(cost: int, balance: int, expected: int):
    """A partial event does not count: 950 points short is still 10 more events.

    Ceiling division, because attending nine and a half events is not a thing a
    student can do — rounding down would show an item as reachable one event
    sooner than it is.
    """
    assert events_still_needed(_item(points_cost=cost), balance=balance) == expected


def test_progress_toward_an_unlistable_item_is_refused_not_zeroed():
    """ADR-0011: no honest number exists, so none is returned.

    Returning ``0`` would render as "you can have it now", and returning the
    full distance would render a progress bar toward a reward nobody will
    honour. Both are the defect; the refusal is the fix.
    """
    for unlistable in (
        _item(points_cost=300, funded=False),
        _item(points_cost=300, owner=None),
    ):
        with pytest.raises(UnlistableRewardError, match="not listable"):
            events_still_needed(unlistable, balance=0)


def test_events_still_needed_refuses_a_non_positive_rate():
    with pytest.raises(ValueError, match="must be positive"):
        events_still_needed(_item(points_cost=300), balance=0, points_per_event=0)


# ---------------------------------------------------------------------------
# The redemption state machine
# ---------------------------------------------------------------------------


def test_the_vocabulary_is_adr_0013s():
    assert {state.value for state in RedemptionState} == {
        "requested",
        "approved",
        "fulfilled",
        "denied",
        "expired",
    }


def test_terminal_states_are_the_three_outcomes():
    assert {
        RedemptionState.FULFILLED,
        RedemptionState.DENIED,
        RedemptionState.EXPIRED,
    } == TERMINAL_REDEMPTION_STATES


def test_every_state_has_a_transition_row():
    """A state missing from the table would raise ``KeyError`` at transition time."""
    assert set(REDEMPTION_TRANSITIONS) == set(RedemptionState)


def test_the_happy_path_is_requested_approved_fulfilled():
    assert (
        replay_states(
            RedemptionState.REQUESTED,
            [RedemptionState.APPROVED, RedemptionState.FULFILLED],
        )
        is RedemptionState.FULFILLED
    )


@pytest.mark.parametrize("outcome", [RedemptionState.DENIED, RedemptionState.EXPIRED])
def test_a_request_can_be_denied_or_expire(outcome: RedemptionState):
    assert replay_states(RedemptionState.REQUESTED, [outcome]) is outcome


def test_an_approved_redemption_can_still_expire():
    """Approved but never handed over is a real outcome, not a stuck state."""
    moves = [RedemptionState.APPROVED, RedemptionState.EXPIRED]
    assert replay_states(RedemptionState.REQUESTED, moves) is RedemptionState.EXPIRED


def test_fulfilment_cannot_skip_approval():
    """ADR-0013 calls redemption "a command with an approval step".

    A ``requested -> fulfilled`` edge would not be a shortcut through that step;
    it would be that step deleted.
    """
    with pytest.raises(InvalidRedemptionTransition):
        replay_states(RedemptionState.REQUESTED, [RedemptionState.FULFILLED])


def test_a_denied_redemption_cannot_be_approved_later():
    with pytest.raises(InvalidRedemptionTransition):
        replay_states(RedemptionState.DENIED, [RedemptionState.APPROVED])


@pytest.mark.parametrize("terminal", sorted(TERMINAL_REDEMPTION_STATES))
@pytest.mark.parametrize("target", sorted(RedemptionState))
def test_no_move_leaves_a_terminal_state(terminal: RedemptionState, target: RedemptionState):
    """Including re-entering itself: a fulfilment that can repeat is a double payout."""
    with pytest.raises(InvalidRedemptionTransition):
        replay_states(terminal, [target])


@pytest.mark.parametrize("state", sorted(RedemptionState))
def test_no_state_transitions_to_itself(state: RedemptionState):
    assert state not in REDEMPTION_TRANSITIONS[state]


def test_the_error_names_the_state_it_was_actually_in():
    """A caller debugging a refused move needs the current state, not just the move."""
    error = InvalidRedemptionTransition(RedemptionState.DENIED, RedemptionState.FULFILLED)
    assert "denied" in str(error)
    assert "fulfilled" in str(error)
    assert error.current is RedemptionState.DENIED
    assert error.requested is RedemptionState.FULFILLED


def test_replay_refuses_the_first_illegal_move_rather_than_skipping_it():
    with pytest.raises(InvalidRedemptionTransition) as caught:
        replay_states(
            RedemptionState.REQUESTED,
            [RedemptionState.DENIED, RedemptionState.APPROVED, RedemptionState.FULFILLED],
        )
    assert caught.value.current is RedemptionState.DENIED


# ---------------------------------------------------------------------------
# Opening a redemption
# ---------------------------------------------------------------------------


def test_a_new_redemption_starts_requested_and_snapshots_the_price():
    """D7: "existing redemptions retain their point-cost snapshot"."""
    item = _item(points_cost=300, name="cheapest band")
    redemption = request_redemption(
        redemption_id=uuid.uuid4(), subject_id=_SUBJECT, item=item, balance=300
    )
    assert redemption.state is RedemptionState.REQUESTED
    assert redemption.points_cost_snapshot == 300
    assert redemption.item_name_snapshot == "cheapest band"
    assert redemption.item_id == item.item_id
    assert redemption.tenant_id == item.tenant_id
    assert redemption.is_terminal is False


def test_repricing_the_item_does_not_reprice_an_open_redemption():
    """The snapshot is a field, not a lookup — a lookup would return today's price."""
    item = _item(points_cost=300)
    redemption = request_redemption(
        redemption_id=uuid.uuid4(), subject_id=_SUBJECT, item=item, balance=300
    )
    repriced = RewardItem(
        item_id=item.item_id,
        tenant_id=item.tenant_id,
        name=item.name,
        points_cost=900,
        budget_owner_id=item.budget_owner_id,
        funded=item.funded,
    )
    assert repriced.points_cost == 900
    assert redemption.points_cost_snapshot == 300


def test_a_deactivated_item_leaves_the_ticket_able_to_say_what_it_is_for():
    """D7's second consequence: deactivation is not deletion.

    The redemption carries the item's name, so an in-flight ticket does not have
    to join back to a row a coordinator may since have unfunded.
    """
    item = _item(points_cost=300, name="campus bookstore voucher")
    redemption = request_redemption(
        redemption_id=uuid.uuid4(), subject_id=_SUBJECT, item=item, balance=300
    )
    assert redemption.item_name_snapshot == "campus bookstore voucher"


def test_an_unlistable_item_cannot_be_redeemed():
    for unlistable in (
        _item(points_cost=300, funded=False),
        _item(points_cost=300, owner=None),
    ):
        with pytest.raises(UnlistableRewardError, match="not listable"):
            request_redemption(
                redemption_id=uuid.uuid4(), subject_id=_SUBJECT, item=unlistable, balance=100_000
            )


def test_an_insufficient_balance_is_refused():
    with pytest.raises(ValueError, match="does not cover"):
        request_redemption(
            redemption_id=uuid.uuid4(),
            subject_id=_SUBJECT,
            item=_item(points_cost=300),
            balance=299,
        )


def test_a_redemption_is_durable_and_its_debit_is_representable():
    """The two schema gaps migration ``0019`` closed, asserted as the new reality.

    This test used to say the opposite, and was written to fail the moment
    either gap was closed — "a reminder to write the durable path honestly, not
    a preference for the current shape". This is that rewrite rather than a
    deletion, so the same two facts stay under test with their truth value
    flipped:

    1. There *is* a ``redemption`` table, so the state machine above is durable
       rather than an in-memory value that dies with the process.
    2. ``point_ledger_entry.source_attendance_id`` is nullable and
       ``source_redemption_id`` exists, so a debit deriving from a redemption
       rather than from an attendance has a row shape of its own. Nothing
       borrows an unrelated attendance id to make one fit — before ``0019``
       that was the only way to write one at all.

    Still deliberately in the unit suite: both are properties of the schema
    *definition*, so they hold on a machine with no PostgreSQL. The integration
    lane proves the database agrees
    (``tests/integration/test_redemption_durability.py``).
    """
    from smartmatch_persistence import schema
    from smartmatch_persistence.rewards import redemption_debit_is_representable

    assert "redemption" in schema.METADATA.tables
    assert redemption_debit_is_representable() is True


def test_the_ledger_kind_vocabulary_is_the_one_the_column_admits():
    """The domain enum and the CHECK constraint are one vocabulary, not two.

    :class:`LedgerEntryKind` exists so the domain, the repository, and the
    column all spell a kind the same way. A member added here and not to
    ``ck_point_ledger_entry_kind`` would be a kind no row could hold, and a
    value admitted by the constraint and absent here would be a row the fold
    could not classify — both of which are silent until something writes one.
    """
    from smartmatch_persistence import schema

    check = next(
        constraint
        for constraint in schema.point_ledger_entry.constraints
        if getattr(constraint, "name", None) == "ck_point_ledger_entry_kind"
    )
    expression = str(check.sqltext)
    for kind in LedgerEntryKind:
        assert f"'{kind.value}'" in expression, (
            f"{kind.value} is a LedgerEntryKind the ledger column does not admit"
        )
    assert expression.count("kind = ") == len(LedgerEntryKind), (
        "ck_point_ledger_entry_kind names a number of kinds LedgerEntryKind does not"
    )


def test_a_ledger_entry_must_carry_the_fields_its_kind_requires():
    """The application twin of ``ck_point_ledger_entry_kind``.

    The nullability that makes a redemption debit writable is only safe because
    exactly one source is populated. These are the shapes the database refuses,
    refused here too — at construction, where the caller can still see what it
    was building, rather than three frames later inside an ``INSERT``.
    """
    common = {
        "entry_id": uuid.uuid4(),
        "tenant_id": _TENANT,
        "reason": "synthetic fixture",
        "occurred_at": _EPOCH,
    }
    with pytest.raises(ValueError, match="must not name an attendance"):
        LedgerEntry(
            kind=LedgerEntryKind.REDEMPTION_DEBIT,
            amount=-300,
            source_attendance_id=uuid.uuid4(),
            source_redemption_id=uuid.uuid4(),
            **common,
        )
    with pytest.raises(ValueError, match="must name an attendance"):
        LedgerEntry(kind=LedgerEntryKind.ATTENDANCE_CREDIT, amount=100, **common)
    with pytest.raises(ValueError, match="must name a redemption"):
        LedgerEntry(kind=LedgerEntryKind.REDEMPTION_DEBIT, amount=-300, **common)
    with pytest.raises(ValueError, match="must not name a redemption"):
        LedgerEntry(
            kind=LedgerEntryKind.REVERSAL,
            amount=-100,
            source_attendance_id=uuid.uuid4(),
            source_redemption_id=uuid.uuid4(),
            **common,
        )
    with pytest.raises(ValueError, match="must be positive"):
        LedgerEntry(
            kind=LedgerEntryKind.ATTENDANCE_CREDIT,
            amount=-100,
            source_attendance_id=uuid.uuid4(),
            **common,
        )
    with pytest.raises(ValueError, match="must be negative"):
        LedgerEntry(
            kind=LedgerEntryKind.REDEMPTION_DEBIT,
            amount=300,
            source_redemption_id=uuid.uuid4(),
            **common,
        )


def test_a_debit_lowers_the_balance_by_the_snapshot_cost():
    """Redeeming spends points, and the fold is what says so.

    The debit is an appended entry like every other movement — there is no
    stored balance to decrement — so the balance after a redemption is the
    credits and the debit folded together.
    """
    ledger = [_entry(100), _entry(100, minutes=1), _entry(100, minutes=2)]
    assert fold_balance(ledger) == 300

    ledger.append(_debit(redemption_debit_amount(300), minutes=3))
    assert fold_balance(ledger) == 0
    assert all(entry.amount == 100 for entry in ledger[:3]), "the credits are untouched"


def test_a_redemption_debit_needs_a_positive_cost():
    """Zero would be a row the ledger refuses; negative would make redeeming *earn*."""
    with pytest.raises(ValueError, match="positive cost"):
        redemption_debit_amount(0)
    with pytest.raises(ValueError, match="positive cost"):
        redemption_debit_amount(-300)


def test_transition_returns_a_new_value_and_leaves_the_original_alone():
    """Frozen: a caller cannot half-apply a move, and no reader sees a torn state."""
    opened = request_redemption(
        redemption_id=uuid.uuid4(), subject_id=_SUBJECT, item=_item(points_cost=300), balance=300
    )
    approved = opened.transition(RedemptionState.APPROVED)
    assert approved is not opened
    assert opened.state is RedemptionState.REQUESTED
    assert approved.state is RedemptionState.APPROVED
    assert approved.redemption_id == opened.redemption_id
    assert approved.points_cost_snapshot == opened.points_cost_snapshot
    assert approved.transition(RedemptionState.FULFILLED).is_terminal is True
