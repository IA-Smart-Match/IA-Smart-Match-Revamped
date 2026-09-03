"""Behavioural coverage for ``smartmatch_persistence.rewards`` against real PostgreSQL.

``tests/integration/test_engagement_schema_constraints.py`` already proves what
migration ``0009``'s *constraints* refuse, in raw SQL. This file asks the
different question: what the repositories built on those tables actually do —
that a catalog listing omits every item ADR-0013 says is not listable, that a
write with no establishable budget owner is refused rather than defaulted, and
that correcting the ledger appends a row instead of changing one.

Every fixture row here is synthetic and lives only inside a test's own
throwaway tenant. **Nothing in this file, and nothing it exercises, seeds a
catalog** — the D6 plan's standing constraints forbid seeded catalog data, D7
has ratified no item name or point cost, and the legacy costs are a documented
defect (Fix #15). The names and numbers below are deliberately obvious
placeholders ("Synthetic funded item", 100/300/600 points) so that no reader
can mistake one for a ratified value.

Requires a live database, and is skipped when none is reachable (``engine``
fixture, ``tests/integration/conftest.py``).

Teardown mirrors ``test_engagement_schema_constraints.py``'s: every foreign key
migration ``0009`` adds is ``RESTRICT``, so this file must delete its own rows
before ``conftest.py``'s ``tenant_id`` fixture tries to delete the
``user_account`` and ``org_unit`` rows they reference.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

pytest.importorskip("sqlalchemy")

from conftest import ensure_owning_unit, unique_subject
from smartmatch_domain.rewards import MissingBudgetOwnerError
from smartmatch_persistence.rewards import (
    PointLedgerRepository,
    RewardCatalogRepository,
    UnknownAttendanceSourceError,
    UnknownBudgetOwnerError,
    UnknownLedgerEntryError,
)
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration

#: A fixed moment for entries that need one. Timezone-aware, because
#: ``occurred_at`` is ``timestamptz`` and the repository refuses naive values.
WHEN = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clean_engagement_tables(engine: Engine, tenant_id):
    """Delete this file's rows before ``tenant_id`` tears down its own.

    Same ordering argument as ``test_engagement_schema_constraints.py``'s
    fixture of this name: depending on ``tenant_id`` makes pytest tear this
    down *first*, so ``conftest.py`` can then delete ``user_account`` and
    ``org_unit`` without tripping the ``RESTRICT`` foreign keys
    ``point_ledger_entry``, ``attendance_record``, and ``reward_item`` hold.
    """
    yield
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM point_ledger_entry WHERE tenant_id = :tid"), {"tid": tenant_id}
        )
        conn.execute(
            text("DELETE FROM attendance_record WHERE tenant_id = :tid"), {"tid": tenant_id}
        )
        conn.execute(text("DELETE FROM reward_item WHERE tenant_id = :tid"), {"tid": tenant_id})


@pytest.fixture
def session(session_factory: sessionmaker[Session]):
    """One session per test, rolled back at the end.

    The repositories take a session per call and commit nothing (their own
    docstrings), so the transaction boundary belongs here — which also means a
    failing test leaves no rows behind for the teardown above to find.
    """
    with session_factory() as sess:
        yield sess
        sess.rollback()


# ---------------------------------------------------------------------------
# Synthetic row builders. Not fixtures: most tests need several accounts or
# several attendance rows, with different properties each.
# ---------------------------------------------------------------------------


def _make_account(session: Session, tenant_id: uuid.UUID) -> uuid.UUID:
    """One ``user_account`` in ``tenant_id`` — a candidate budget owner or student."""
    account_id = uuid.uuid4()
    session.execute(
        text(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :tenant_id, :sub, :email)"
        ),
        {
            "id": account_id,
            "tenant_id": tenant_id,
            "sub": unique_subject(f"rewards-{account_id.hex[:8]}"),
            "email": f"{account_id.hex[:8]}@example.edu",
        },
    )
    return account_id


def _make_attendance(session: Session, tenant_id: uuid.UUID, *, subject_id: uuid.UUID) -> uuid.UUID:
    """One ``attendance_record`` — the only legitimate source of a ledger entry."""
    record_id = uuid.uuid4()
    session.execute(
        text(
            "INSERT INTO attendance_record "
            "(id, tenant_id, owning_unit_id, subject_id, event_id, method) "
            "VALUES (:id, :tenant_id, :unit_id, :subject_id, :event_id, 'qr_scan')"
        ),
        {
            "id": record_id,
            "tenant_id": tenant_id,
            "unit_id": ensure_owning_unit(session, tenant_id),
            "subject_id": subject_id,
            "event_id": uuid.uuid4(),
        },
    )
    return record_id


def _create_item(
    session: Session,
    tenant_id: uuid.UUID,
    *,
    owner_id: uuid.UUID | None,
    funded: bool = True,
    name: str = "Synthetic funded item",
    points_cost: int = 300,
):
    """Create a reward item through the repository under test."""
    return RewardCatalogRepository().create_item(
        session,
        tenant_id=tenant_id,
        name=name,
        points_cost=points_cost,
        fulfilment_cost=Decimal("0.0000"),
        budget_owner_id=owner_id,
        funded=funded,
    )


def _make_other_tenant(engine: Engine, label: str) -> uuid.UUID:
    """A second tenant, for the cross-tenant tests.

    ``conftest.py``'s ``tenant_id`` fixture yields exactly one tenant, and the
    property under test is precisely that a second one's rows are invisible —
    so these tests create and tear down their own.
    """
    other = uuid.uuid4()
    slug = f"test-{label}-{other.hex[:12]}"
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :name)"),
            {"id": other, "slug": slug, "name": slug},
        )
    return other


def _drop_other_tenant(engine: Engine, other: uuid.UUID) -> None:
    """Remove a tenant made by :func:`_make_other_tenant`, children first."""
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM reward_item WHERE tenant_id = :tid"), {"tid": other})
        conn.execute(text("DELETE FROM user_account WHERE tenant_id = :tid"), {"tid": other})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": other})


# ---------------------------------------------------------------------------
# D6 — a write that cannot establish the budget owner is refused, not defaulted.
# ---------------------------------------------------------------------------


def test_create_item_refuses_an_absent_budget_owner(session: Session, tenant_id) -> None:
    """No owner supplied is a refusal with no row written — never a default."""
    with pytest.raises(MissingBudgetOwnerError):
        _create_item(session, tenant_id, owner_id=None)

    remaining = session.execute(
        text("SELECT count(*) FROM reward_item WHERE tenant_id = :tid"), {"tid": tenant_id}
    ).scalar_one()
    assert remaining == 0, "a refused create must leave no reward_item row behind"


def test_create_item_refuses_an_owner_id_that_names_nobody(session: Session, tenant_id) -> None:
    """An arbitrary UUID is not ownership (D6 plan, standing constraints)."""
    with pytest.raises(UnknownBudgetOwnerError, match="no user_account"):
        _create_item(session, tenant_id, owner_id=uuid.uuid4())


def test_create_item_refuses_an_owner_from_another_tenant(
    session: Session, session_factory: sessionmaker[Session], engine: Engine, tenant_id
) -> None:
    """The composite key's whole point: a name with no standing in *this* tenant."""
    other_tenant = _make_other_tenant(engine, "owner")
    try:
        with session_factory() as other_session:
            foreign_owner = _make_account(other_session, other_tenant)
            other_session.commit()

        with pytest.raises(UnknownBudgetOwnerError, match="standing in this tenant"):
            _create_item(session, tenant_id, owner_id=foreign_owner)
    finally:
        _drop_other_tenant(engine, other_tenant)


def test_create_item_writes_the_owner_it_was_given(session: Session, tenant_id) -> None:
    """The happy path stores the named owner verbatim, and funded as supplied."""
    owner_id = _make_account(session, tenant_id)
    item = _create_item(session, tenant_id, owner_id=owner_id, funded=True)

    assert item.budget_owner_id == owner_id
    assert item.funded is True
    assert item.fulfilment_cost == Decimal("0.0000")


def test_create_item_honours_an_explicit_unfunded_flag(session: Session, tenant_id) -> None:
    """``funded`` is passed explicitly, so ``False`` is stored, not defaulted over."""
    owner_id = _make_account(session, tenant_id)
    item = _create_item(session, tenant_id, owner_id=owner_id, funded=False)
    assert item.funded is False


def test_create_item_refuses_a_blank_name(session: Session, tenant_id) -> None:
    owner_id = _make_account(session, tenant_id)
    with pytest.raises(ValueError, match="requires a name"):
        _create_item(session, tenant_id, owner_id=owner_id, name="   ")


# ---------------------------------------------------------------------------
# S8 listing — an unowned or unfunded item never appears.
# ---------------------------------------------------------------------------


def test_listing_is_empty_for_a_tenant_with_no_items(session: Session, tenant_id) -> None:
    """Nothing seeds this table, so this is every tenant's state today."""
    assert RewardCatalogRepository().list_listable_items(session, tenant_id=tenant_id) == ()


def test_listing_includes_an_owned_funded_item(session: Session, tenant_id) -> None:
    owner_id = _make_account(session, tenant_id)
    item = _create_item(session, tenant_id, owner_id=owner_id)

    listed = RewardCatalogRepository().list_listable_items(session, tenant_id=tenant_id)
    assert [row.id for row in listed] == [item.id]


def test_listing_omits_an_unfunded_item(session: Session, tenant_id) -> None:
    """ADR-0013 requires both halves; an owner alone does not make it listable."""
    owner_id = _make_account(session, tenant_id)
    _create_item(session, tenant_id, owner_id=owner_id, funded=False)

    assert RewardCatalogRepository().list_listable_items(session, tenant_id=tenant_id) == ()


def test_listing_omits_an_item_whose_owner_has_no_standing(session: Session, tenant_id) -> None:
    """The read-side join re-derives ownership rather than trusting the column.

    Set up by writing a legitimate row through the repository, then dropping the
    composite foreign key so the owner can be pointed at an account that does
    not exist. This is a test of what the *listing* does with a row it should
    never see — not a suggestion such a row is reachable in production, where
    the constraint refuses it.

    The schema surgery is confined to a **SAVEPOINT** (``begin_nested``) rather
    than left to the outer transaction's rollback. DDL is transactional in
    PostgreSQL either way, but a savepoint releases the ``ACCESS EXCLUSIVE``
    lock the ``ALTER TABLE`` takes as soon as this test is done with it instead
    of holding it for the rest of the session, and it makes the restoration a
    step this test performs rather than a side effect it relies on. The
    post-condition below then asserts the constraint is actually back, so a
    future edit that breaks the isolation fails here rather than somewhere
    downstream.
    """
    owner_id = _make_account(session, tenant_id)
    item = _create_item(session, tenant_id, owner_id=owner_id)
    session.flush()

    savepoint = session.begin_nested()
    try:
        session.execute(
            text(
                "ALTER TABLE reward_item DROP CONSTRAINT reward_item_tenant_id_budget_owner_id_fkey"
            )
        )
        session.execute(
            text("UPDATE reward_item SET budget_owner_id = :ghost WHERE id = :id"),
            {"ghost": uuid.uuid4(), "id": item.id},
        )
        listed = RewardCatalogRepository().list_listable_items(session, tenant_id=tenant_id)
        assert listed == (), "an item whose owner has no standing must not be listed"
    finally:
        savepoint.rollback()

    still_there = session.execute(
        text(
            "SELECT count(*) FROM pg_constraint "
            "WHERE conname = 'reward_item_tenant_id_budget_owner_id_fkey'"
        )
    ).scalar_one()
    assert still_there == 1, "the savepoint must have restored the foreign key"


def test_listing_is_scoped_to_its_tenant(
    session: Session, session_factory: sessionmaker[Session], engine: Engine, tenant_id
) -> None:
    """A listable item in another tenant is not this tenant's catalog."""
    other_tenant = _make_other_tenant(engine, "scope")
    try:
        with session_factory() as other_session:
            other_owner = _make_account(other_session, other_tenant)
            _create_item(other_session, other_tenant, owner_id=other_owner)
            other_session.commit()

        assert RewardCatalogRepository().list_listable_items(session, tenant_id=tenant_id) == ()
    finally:
        _drop_other_tenant(engine, other_tenant)


def test_listing_sorts_ascending_by_points_cost(session: Session, tenant_id) -> None:
    """The one property ADR-0013 keeps from the legacy ``getSortedCatalog``."""
    owner_id = _make_account(session, tenant_id)
    for cost in (600, 100, 300):
        _create_item(session, tenant_id, owner_id=owner_id, points_cost=cost, name=f"Item {cost}")

    listed = RewardCatalogRepository().list_listable_items(session, tenant_id=tenant_id)
    assert [row.points_cost for row in listed] == [100, 300, 600]


def test_get_item_shows_an_unlistable_row_that_the_listing_hides(
    session: Session, tenant_id
) -> None:
    """The by-id read is for diagnosing why an item does not appear."""
    owner_id = _make_account(session, tenant_id)
    item = _create_item(session, tenant_id, owner_id=owner_id, funded=False)

    found = RewardCatalogRepository().get_item(session, tenant_id=tenant_id, item_id=item.id)
    assert found is not None
    assert found.funded is False
    assert RewardCatalogRepository().list_listable_items(session, tenant_id=tenant_id) == ()


# ---------------------------------------------------------------------------
# S7 ledger — append-only, sourced from attendance, folded into a balance.
# ---------------------------------------------------------------------------


def test_append_entry_records_the_amount_and_source_it_was_given(
    session: Session, tenant_id
) -> None:
    subject_id = _make_account(session, tenant_id)
    attendance_id = _make_attendance(session, tenant_id, subject_id=subject_id)

    entry = PointLedgerRepository().append_entry(
        session,
        tenant_id=tenant_id,
        source_attendance_id=attendance_id,
        amount=100,
        reason="verified attendance",
        occurred_at=WHEN,
    )
    assert entry.amount == 100
    assert entry.source_attendance_id == attendance_id
    assert entry.actor_id is None, "automatic derivation names no human actor"


def test_append_entry_refuses_a_source_that_is_not_recorded_attendance(
    session: Session, tenant_id
) -> None:
    """ADR-0013: points derive from recorded attendance and nothing else."""
    with pytest.raises(UnknownAttendanceSourceError, match="nothing else"):
        PointLedgerRepository().append_entry(
            session,
            tenant_id=tenant_id,
            source_attendance_id=uuid.uuid4(),
            amount=100,
            reason="a grant with no evidence",
            occurred_at=WHEN,
        )


def test_append_entry_refuses_a_naive_occurred_at(session: Session, tenant_id) -> None:
    subject_id = _make_account(session, tenant_id)
    attendance_id = _make_attendance(session, tenant_id, subject_id=subject_id)

    with pytest.raises(ValueError, match="timezone-aware"):
        PointLedgerRepository().append_entry(
            session,
            tenant_id=tenant_id,
            source_attendance_id=attendance_id,
            amount=100,
            reason="verified attendance",
            occurred_at=datetime(2026, 9, 3, 12, 0),  # naive on purpose
        )


def test_a_reversal_appends_and_leaves_the_original_untouched(session: Session, tenant_id) -> None:
    """ADR-0013: "A reversal is a compensating entry, never a delete."

    The single most important assertion in this file: after the correction, the
    original row is exactly what it was, and the table holds two rows rather
    than one amended one.
    """
    subject_id = _make_account(session, tenant_id)
    attendance_id = _make_attendance(session, tenant_id, subject_id=subject_id)
    ledger = PointLedgerRepository()

    original = ledger.append_entry(
        session,
        tenant_id=tenant_id,
        source_attendance_id=attendance_id,
        amount=100,
        reason="verified attendance",
        occurred_at=WHEN,
    )
    reversal = ledger.append_reversal(
        session,
        tenant_id=tenant_id,
        entry_id=original.id,
        reason="attendance recorded in error",
        occurred_at=WHEN + timedelta(hours=1),
    )

    assert reversal.id != original.id
    assert reversal.amount == -original.amount
    assert reversal.source_attendance_id == original.source_attendance_id

    reread = ledger.get_entry(session, tenant_id=tenant_id, entry_id=original.id)
    assert reread == original, "the reversed entry must be unchanged"

    row_count = session.execute(
        text("SELECT count(*) FROM point_ledger_entry WHERE tenant_id = :tid"),
        {"tid": tenant_id},
    ).scalar_one()
    assert row_count == 2, "a correction appends; it does not replace"


def test_append_reversal_refuses_an_entry_that_does_not_exist(session: Session, tenant_id) -> None:
    with pytest.raises(UnknownLedgerEntryError, match="nothing to compensate"):
        PointLedgerRepository().append_reversal(
            session,
            tenant_id=tenant_id,
            entry_id=uuid.uuid4(),
            reason="correcting nothing",
            occurred_at=WHEN,
        )


def test_balance_is_a_fold_over_the_ledger(session: Session, tenant_id) -> None:
    """Three credits from three separate attendances fold to their sum."""
    subject_id = _make_account(session, tenant_id)
    ledger = PointLedgerRepository()
    for _ in range(3):
        attendance_id = _make_attendance(session, tenant_id, subject_id=subject_id)
        ledger.append_entry(
            session,
            tenant_id=tenant_id,
            source_attendance_id=attendance_id,
            amount=100,
            reason="verified attendance",
            occurred_at=WHEN,
        )

    assert ledger.balance_for_subject(session, tenant_id=tenant_id, subject_id=subject_id) == 300


def test_a_reversal_moves_the_balance_without_removing_its_history(
    session: Session, tenant_id
) -> None:
    """The property a counter cannot offer: the balance is back to zero and both
    rows explaining why are still there."""
    subject_id = _make_account(session, tenant_id)
    attendance_id = _make_attendance(session, tenant_id, subject_id=subject_id)
    ledger = PointLedgerRepository()

    original = ledger.append_entry(
        session,
        tenant_id=tenant_id,
        source_attendance_id=attendance_id,
        amount=100,
        reason="verified attendance",
        occurred_at=WHEN,
    )
    ledger.append_reversal(
        session,
        tenant_id=tenant_id,
        entry_id=original.id,
        reason="attendance recorded in error",
        occurred_at=WHEN + timedelta(hours=1),
    )

    assert ledger.balance_for_subject(session, tenant_id=tenant_id, subject_id=subject_id) == 0
    entries = ledger.entries_for_subject(session, tenant_id=tenant_id, subject_id=subject_id)
    assert len(entries) == 2
    assert [entry.reason for entry in entries] == [
        "verified attendance",
        "attendance recorded in error",
    ]


# ---------------------------------------------------------------------------
# ADR-0013:69 — "an offsetting ledger entry that names what it reverses".
# Migration 0014's reverses_entry_id, and the ambiguity it closed.
# ---------------------------------------------------------------------------


def test_an_earning_entry_names_no_reversed_entry(session: Session, tenant_id) -> None:
    """``reverses_entry_id`` is NULL on an ordinary credit — that is what makes it
    distinguishable from a compensating one."""
    subject_id = _make_account(session, tenant_id)
    attendance_id = _make_attendance(session, tenant_id, subject_id=subject_id)

    entry = PointLedgerRepository().append_entry(
        session,
        tenant_id=tenant_id,
        source_attendance_id=attendance_id,
        amount=100,
        reason="verified attendance",
        occurred_at=WHEN,
    )
    assert entry.reverses_entry_id is None
    assert entry.is_reversal() is False


def test_a_reversal_names_the_entry_it_reverses(session: Session, tenant_id) -> None:
    """The direct statement of ADR-0013:69."""
    subject_id = _make_account(session, tenant_id)
    attendance_id = _make_attendance(session, tenant_id, subject_id=subject_id)
    ledger = PointLedgerRepository()

    original = ledger.append_entry(
        session,
        tenant_id=tenant_id,
        source_attendance_id=attendance_id,
        amount=100,
        reason="verified attendance",
        occurred_at=WHEN,
    )
    reversal = ledger.append_reversal(
        session,
        tenant_id=tenant_id,
        entry_id=original.id,
        reason="attendance recorded in error",
        occurred_at=WHEN + timedelta(hours=1),
    )

    assert reversal.reverses_entry_id == original.id
    assert reversal.is_reversal() is True


def test_a_reversal_is_unambiguous_when_entries_share_an_attendance_source(
    session: Session, tenant_id
) -> None:
    """**The exact defect migration 0014 closed.**

    Three credits derive from one attendance — which nothing prevents, and
    which a revised earn policy invites. Before ``reverses_entry_id``, the
    compensating row carried only the shared ``source_attendance_id``, so all
    three were equally plausible targets and an auditor could not say which
    credit was withdrawn. Asserted directly here: the reversal names exactly
    one of the three, the other two are untouched, and the ledger identifies
    the pair without reference to the amounts.
    """
    subject_id = _make_account(session, tenant_id)
    attendance_id = _make_attendance(session, tenant_id, subject_id=subject_id)
    ledger = PointLedgerRepository()

    # Three entries, one shared source. Equal amounts on two of them, so the
    # target cannot be inferred from the amount either.
    first = ledger.append_entry(
        session,
        tenant_id=tenant_id,
        source_attendance_id=attendance_id,
        amount=100,
        reason="verified attendance",
        occurred_at=WHEN,
    )
    second = ledger.append_entry(
        session,
        tenant_id=tenant_id,
        source_attendance_id=attendance_id,
        amount=100,
        reason="verified attendance, re-credited under revised policy",
        occurred_at=WHEN + timedelta(minutes=1),
    )
    third = ledger.append_entry(
        session,
        tenant_id=tenant_id,
        source_attendance_id=attendance_id,
        amount=50,
        reason="verified attendance, partial adjustment",
        occurred_at=WHEN + timedelta(minutes=2),
    )
    assert first.source_attendance_id == second.source_attendance_id == third.source_attendance_id

    reversal = ledger.append_reversal(
        session,
        tenant_id=tenant_id,
        entry_id=second.id,
        reason="the re-credit was applied twice",
        occurred_at=WHEN + timedelta(hours=1),
    )

    # The whole point: exactly one of the three is named, and it is the right one.
    assert reversal.reverses_entry_id == second.id
    assert reversal.reverses_entry_id not in (first.id, third.id)

    # The other two are untouched, and the ledger can still be read as pairs.
    entries = ledger.entries_for_subject(session, tenant_id=tenant_id, subject_id=subject_id)
    reversed_targets = {e.reverses_entry_id for e in entries if e.is_reversal()}
    assert reversed_targets == {second.id}
    unreversed = {e.id for e in entries if not e.is_reversal()} - reversed_targets
    assert unreversed == {first.id, third.id}

    # 100 + 100 + 50 - 100
    assert ledger.balance_for_subject(session, tenant_id=tenant_id, subject_id=subject_id) == 150


def test_append_reversal_refuses_a_target_in_another_tenant(
    session: Session, session_factory: sessionmaker[Session], engine: Engine, tenant_id
) -> None:
    """A reversal must not reach an entry belonging to another institution.

    The composite foreign key refuses this at the database; the tenant-scoped
    read in ``append_reversal`` refuses it first, so the caller gets a named
    error rather than an ``IntegrityError``.
    """
    other_tenant = _make_other_tenant(engine, "reversal")
    try:
        with session_factory() as other_session:
            other_subject = _make_account(other_session, other_tenant)
            other_attendance = _make_attendance(
                other_session, other_tenant, subject_id=other_subject
            )
            foreign_entry = PointLedgerRepository().append_entry(
                other_session,
                tenant_id=other_tenant,
                source_attendance_id=other_attendance,
                amount=100,
                reason="verified attendance",
                occurred_at=WHEN,
            )
            other_session.commit()
            foreign_entry_id = foreign_entry.id

        with pytest.raises(UnknownLedgerEntryError):
            PointLedgerRepository().append_reversal(
                session,
                tenant_id=tenant_id,
                entry_id=foreign_entry_id,
                reason="reaching across a tenant boundary",
                occurred_at=WHEN,
            )
    finally:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM point_ledger_entry WHERE tenant_id = :tid"), {"tid": other_tenant}
            )
            conn.execute(
                text("DELETE FROM attendance_record WHERE tenant_id = :tid"), {"tid": other_tenant}
            )
            conn.execute(text("DELETE FROM org_unit WHERE tenant_id = :tid"), {"tid": other_tenant})
        _drop_other_tenant(engine, other_tenant)


def test_a_reversal_may_itself_be_reversed(session: Session, tenant_id) -> None:
    """ADR-0013 is **silent** on chained reversals, so none is prohibited here.

    Neither ADR-0013 nor ``docs/architecture/engagement-model.md`` says whether
    a compensating entry may itself be compensated for. No prohibition was
    invented: the chain is permitted, each link names its own distinct target,
    and the fold reconciles it — reinstating the original credit.
    """
    subject_id = _make_account(session, tenant_id)
    attendance_id = _make_attendance(session, tenant_id, subject_id=subject_id)
    ledger = PointLedgerRepository()

    original = ledger.append_entry(
        session,
        tenant_id=tenant_id,
        source_attendance_id=attendance_id,
        amount=100,
        reason="verified attendance",
        occurred_at=WHEN,
    )
    reversal = ledger.append_reversal(
        session,
        tenant_id=tenant_id,
        entry_id=original.id,
        reason="attendance recorded in error",
        occurred_at=WHEN + timedelta(hours=1),
    )
    reinstatement = ledger.append_reversal(
        session,
        tenant_id=tenant_id,
        entry_id=reversal.id,
        reason="the error report was itself mistaken",
        occurred_at=WHEN + timedelta(hours=2),
    )

    assert reinstatement.reverses_entry_id == reversal.id
    assert reinstatement.amount == 100
    # 100 - 100 + 100, with all three rows still present and each naming its own
    # target: the audit trail is a chain, not an overwrite.
    assert ledger.balance_for_subject(session, tenant_id=tenant_id, subject_id=subject_id) == 100
    assert len(ledger.entries_for_subject(session, tenant_id=tenant_id, subject_id=subject_id)) == 3


def test_balance_of_a_student_with_no_attendance_is_zero(session: Session, tenant_id) -> None:
    """Zero, and known — not unknown. Nothing is seeded, so this is the norm."""
    subject_id = _make_account(session, tenant_id)
    balance = PointLedgerRepository().balance_for_subject(
        session, tenant_id=tenant_id, subject_id=subject_id
    )
    assert balance == 0


def test_balance_counts_only_the_named_students_entries(session: Session, tenant_id) -> None:
    """The join through ``attendance_record`` is what scopes an entry to a student."""
    ledger = PointLedgerRepository()
    student = _make_account(session, tenant_id)
    other_student = _make_account(session, tenant_id)

    for subject_id, amount in ((student, 100), (other_student, 600)):
        attendance_id = _make_attendance(session, tenant_id, subject_id=subject_id)
        ledger.append_entry(
            session,
            tenant_id=tenant_id,
            source_attendance_id=attendance_id,
            amount=amount,
            reason="verified attendance",
            occurred_at=WHEN,
        )

    assert ledger.balance_for_subject(session, tenant_id=tenant_id, subject_id=student) == 100
