"""Unit coverage for ``smartmatch_domain.rewards`` and the append-only surface.

Two things are pinned here, and only one of them needs a database.

**The rules** (``smartmatch_domain.rewards``) are pure, so every refusal D6 and
ADR-0013 require can be asserted without infrastructure: an absent budget owner
is refused rather than defaulted, an unfunded item is not listable, a zero
amount and a blank reason are refused, a reversal is the negation, and a
balance is a fold that is total over the empty ledger.

**The absence of a mutation path** is asserted structurally, against
``smartmatch_persistence.rewards``. ADR-0013 says the ledger is append-only and
``docs/decisions/d6-rewards-budget-decision-record.md`` §7 check 2 records that
today *nothing in the database enforces that* — so the application-side
guarantee carries the whole weight, which makes it worth a test that fails if
someone later adds an ``update_entry`` or a ``delete_entry``. The scan below is
deliberately structural (public attribute names, and the source of the module)
rather than behavioural: a behavioural test can only prove the methods that
exist behave, and the property at issue is that a whole *class* of method does
not exist.

``tests/integration/test_rewards_repositories.py`` is the behavioural half and
needs PostgreSQL.
"""

from __future__ import annotations

import inspect
import re
import uuid

import pytest
from smartmatch_domain.rewards import (
    EmptyLedgerReasonError,
    MisdeclaredReversalTargetError,
    MissingBudgetOwnerError,
    UnfundedRewardItemError,
    ZeroLedgerAmountError,
    assert_budget_owner_named,
    assert_ledger_entry_well_formed,
    assert_listable,
    assert_reversal_target,
    fold_balance,
    is_listable,
    reversal_amount,
)

#: A placeholder owner id. Synthetic and structureless — this file never
#: reaches a database, so it names nobody, which is exactly what the pure
#: rules can and cannot check (see ``assert_listable``'s docstring).
OWNER = uuid.UUID("11111111-1111-4111-8111-111111111111")


# ---------------------------------------------------------------------------
# D6 — the budget owner is established or the write is refused.
# ---------------------------------------------------------------------------


def test_assert_budget_owner_named_returns_the_owner_it_was_given():
    """The check is a pass-through, not a transformation."""
    assert assert_budget_owner_named(OWNER) == OWNER


def test_assert_budget_owner_named_refuses_an_absent_owner():
    """D6's requirement is a *named* human; the absent case has no default."""
    with pytest.raises(MissingBudgetOwnerError, match="named budget owner"):
        assert_budget_owner_named(None)


def test_assert_budget_owner_named_never_substitutes_a_placeholder():
    """A refusal, not a fallback — the error says so and no value escapes.

    Pinned explicitly because "reject, do not default" is the entire point of
    D6, and a future edit that returned some sentinel owner would still satisfy
    the previous test's *name* while destroying its meaning.
    """
    with pytest.raises(MissingBudgetOwnerError) as caught:
        assert_budget_owner_named(None)
    assert "no default owner" in str(caught.value)


# ---------------------------------------------------------------------------
# ADR-0013 — listable means owned AND funded.
# ---------------------------------------------------------------------------


def test_an_owned_and_funded_item_is_listable():
    assert is_listable(budget_owner_id=OWNER, funded=True) is True
    assert assert_listable(budget_owner_id=OWNER, funded=True) == OWNER


def test_an_unowned_item_is_not_listable_however_funded():
    assert is_listable(budget_owner_id=None, funded=True) is False
    with pytest.raises(MissingBudgetOwnerError):
        assert_listable(budget_owner_id=None, funded=True)


def test_an_unfunded_item_is_not_listable_however_owned():
    """Naming an owner does not fund the item — ADR-0013 requires both."""
    assert is_listable(budget_owner_id=OWNER, funded=False) is False
    with pytest.raises(UnfundedRewardItemError, match="no funded balance"):
        assert_listable(budget_owner_id=OWNER, funded=False)


def test_an_unowned_unfunded_item_reports_the_ownership_failure_first():
    """The legacy defect (Fix #15) was an unowned promise; that is the headline."""
    with pytest.raises(MissingBudgetOwnerError):
        assert_listable(budget_owner_id=None, funded=False)


# ---------------------------------------------------------------------------
# Ledger entry well-formedness.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("amount", [1, -1, 100, -100, 300])
def test_a_nonzero_amount_with_a_reason_is_well_formed(amount):
    """Negative amounts are well-formed: a reversal is a negative entry."""
    assert assert_ledger_entry_well_formed(amount=amount, reason="attendance") is None


def test_a_zero_amount_is_refused():
    """``ck_point_ledger_entry_amount_nonzero``, stated in application code."""
    with pytest.raises(ZeroLedgerAmountError, match="non-zero"):
        assert_ledger_entry_well_formed(amount=0, reason="attendance")


@pytest.mark.parametrize("reason", ["", "   ", "\t\n"])
def test_a_blank_reason_is_refused(reason):
    """``NOT NULL`` accepts whitespace; a ledger that cannot say why does not."""
    with pytest.raises(EmptyLedgerReasonError, match="must carry a reason"):
        assert_ledger_entry_well_formed(amount=100, reason=reason)


# ---------------------------------------------------------------------------
# Reversal is a compensating entry, and the fold reconciles it.
# ---------------------------------------------------------------------------


TARGET = uuid.UUID("22222222-2222-4222-8222-222222222222")


def test_a_reversal_must_name_its_target():
    """ADR-0013:69 — the compensating entry "names what it reverses"."""
    assert assert_reversal_target(is_reversal=True, reverses_entry_id=TARGET) == TARGET


def test_a_reversal_with_no_target_is_refused():
    """The defect migration 0014 closed: a correction that names nothing."""
    with pytest.raises(MisdeclaredReversalTargetError, match="must name the entry it reverses"):
        assert_reversal_target(is_reversal=True, reverses_entry_id=None)


def test_a_reversal_with_no_target_is_not_quietly_defaulted():
    """No fallback target is invented — the error says why one cannot be."""
    with pytest.raises(MisdeclaredReversalTargetError) as caught:
        assert_reversal_target(is_reversal=True, reverses_entry_id=None)
    assert "source_attendance_id is not specific enough" in str(caught.value)


def test_an_earning_entry_leaves_the_target_null():
    assert assert_reversal_target(is_reversal=False, reverses_entry_id=None) is None


def test_an_earning_entry_that_names_a_target_is_refused():
    """The column is what distinguishes the two kinds of row; it cannot be both."""
    with pytest.raises(MisdeclaredReversalTargetError, match="must not name a reversed entry"):
        assert_reversal_target(is_reversal=False, reverses_entry_id=TARGET)


def test_reversal_amount_is_the_negation():
    assert reversal_amount(300) == -300
    assert reversal_amount(-300) == 300


def test_reversing_a_reversal_restores_the_original_amount():
    assert reversal_amount(reversal_amount(300)) == 300


def test_reversal_of_zero_is_refused():
    """No zero entry can exist, so nothing can be reversed to one either."""
    with pytest.raises(ZeroLedgerAmountError):
        reversal_amount(0)


def test_fold_balance_sums_signed_amounts():
    assert fold_balance([100, 100, 100]) == 300


def test_fold_balance_of_an_entry_and_its_reversal_is_zero():
    """The property that makes a compensating entry a correction, not noise."""
    assert fold_balance([300, reversal_amount(300)]) == 0


def test_fold_balance_of_an_empty_ledger_is_zero_not_unknown():
    """A student with no attendance has a balance of zero, and it is known."""
    assert fold_balance([]) == 0


# ---------------------------------------------------------------------------
# Append-only: no mutation path exists to find.
# ---------------------------------------------------------------------------

#: Method-name fragments that would indicate a ledger mutation path. Matched
#: against *public* attribute names on the repository, so ``_insert`` (the one
#: private writer) is out of scope by construction, while ``update_entry``,
#: ``delete``, ``remove_entry``, ``amend``, or ``void`` would all be caught.
_MUTATION_NAME_FRAGMENTS = ("update", "delete", "remove", "amend", "void", "edit", "overwrite")


def test_point_ledger_repository_exposes_no_mutation_method():
    """The application-side append-only guarantee, asserted by absence.

    Worth asserting rather than assuming precisely because the database does
    not enforce append-only today (D6 record §7 check 2) — this is currently
    the only guard there is, so it should fail loudly if it is removed.
    """
    pytest.importorskip("sqlalchemy")
    from smartmatch_persistence.rewards import PointLedgerRepository

    public_names = [name for name in dir(PointLedgerRepository) if not name.startswith("_")]
    offenders = [
        name
        for name in public_names
        if any(fragment in name.lower() for fragment in _MUTATION_NAME_FRAGMENTS)
    ]
    assert offenders == [], (
        f"PointLedgerRepository exposes {offenders}; the ledger is append-only "
        "(ADR-0013) and no database guard backs that up yet"
    )


def test_rewards_persistence_module_issues_no_update_or_delete_statement():
    """No ``sa.update``/``sa.delete`` anywhere in the module's own source.

    The name scan above catches a mutation method that announces itself. This
    catches one that does not — an innocuously named helper that nonetheless
    issues an ``UPDATE`` or a ``DELETE`` against any table in this module.
    """
    pytest.importorskip("sqlalchemy")
    from smartmatch_persistence import rewards

    source = inspect.getsource(rewards)
    # Strip the module docstring: it discusses UPDATE and DELETE at length,
    # which is prose about the guarantee rather than a statement violating it.
    body = source.replace(rewards.__doc__ or "", "", 1)
    offenders = re.findall(r"\bsa\.(update|delete)\b", body)
    assert offenders == [], (
        f"smartmatch_persistence.rewards issues {offenders} — the ledger and the "
        "catalog reads in this module are append-only and read-only respectively"
    )


def test_rewards_persistence_module_declares_no_seed_catalog():
    """Nothing seeds a catalog: no module-level reward rows, no bootstrap call.

    The D6 plan's standing constraints say "Seed no production catalog data",
    and D7 has ratified no item name or point cost. The check is that the
    module's only insert path is a method taking caller-supplied values — there
    is no importable constant or function that would create rows on its own.
    """
    pytest.importorskip("sqlalchemy")
    from smartmatch_persistence import rewards

    seed_like = [
        name
        for name in dir(rewards)
        if not name.startswith("_") and any(word in name.lower() for word in ("seed", "bootstrap"))
    ]
    assert seed_like == [], f"smartmatch_persistence.rewards exposes seeding helpers: {seed_like}"


def test_engagement_router_still_declares_no_handlers():
    """This task added no route, and the D6 route gate is still closed.

    ``tests/unit/test_matching_fail_closed.py`` owns that assertion as a gate;
    this restates it from the rewards side so the reason the repositories above
    have no HTTP caller is visible in the rewards tests themselves rather than
    only in a file about matching.
    """
    pytest.importorskip("fastapi")
    from smartmatch_api.routers import engagement

    assert engagement.router.routes == [], (
        "a reward route landed without D6/D7 read roles and without the card L2 "
        "database append-only guard — see smartmatch_persistence.rewards' docstring"
    )
