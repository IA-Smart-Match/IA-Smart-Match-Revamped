"""``RewardsRepository`` against a real PostgreSQL instance.

``tests/unit/test_rewards_domain.py`` proves the rules; this file proves the
repository implements them against rows PostgreSQL holds — that a credit is one
appended row and not two, that a correction leaves the entry it corrects
byte-for-byte intact, that the balance a caller reads is a fold over those rows
rather than anything stored, and that an unfunded or cross-tenant
``reward_item`` never comes back from the listing query however it got into the
table.

The catalog rows here are synthetic fixtures written directly by this test, not
a shipped catalog: D6 gates a shipped catalog and
``smartmatch_persistence.rewards`` deliberately has no ``reward_item`` writer,
so a test that needs one inserts it itself — the same thing
``test_engagement_schema_constraints.py`` does. Nothing here is seeded into a
migration and nothing here is a price anyone has ratified; the point costs are
D7's *tentative* recorded bands, cited so the fixtures are not invented numbers.

Requires a live database, and is skipped when none is reachable (``engine``
fixture, ``tests/integration/conftest.py``).

Teardown, and why it is this shape. Every foreign key migration ``0009``
declares is ``RESTRICT``, so a row this file leaves behind makes ``conftest``'s
own ``tenant_id`` teardown fail on the ``user_account`` or ``org_unit`` it still
references. ``_clean_engagement_tables`` depends on ``tenant_id``, which makes
pytest tear it down *first*, and deletes child before parent
(``point_ledger_entry`` before ``attendance_record``) — exactly the ordering
``test_engagement_schema_constraints.py`` establishes for the same three tables.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest

pytest.importorskip("sqlalchemy")

from conftest import ensure_event, ensure_owning_unit, unique_subject
from smartmatch_domain.rewards import (
    CALIBRATION_N_TENTATIVE,
    D7_TENTATIVE_POINT_BANDS,
    POINTS_PER_VERIFIED_ATTENDANCE,
    InvalidRedemptionTransition,
    LedgerEntryKind,
    RedemptionState,
    UnlistableRewardError,
    events_still_needed,
    is_listable,
    request_redemption,
    satisfies_calibration,
)
from smartmatch_domain.synthetic_pilot import SYNTHETIC_ATTENDANCE_METHOD
from smartmatch_persistence.rewards import (
    ATTENDANCE_EARN_REASON,
    REDEMPTION_DEBIT_REASON_PREFIX,
    REVERSAL_REASON_PREFIX,
    AlreadyCreditedError,
    InsufficientBalanceError,
    NothingToReverseError,
    RewardsRepository,
    UnknownAttendanceError,
)
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clean_engagement_tables(engine: Engine, tenant_id: uuid.UUID) -> Iterator[None]:
    """Delete any committed rows of this file's before ``tenant_id`` tears its own down.

    Belt and braces: :func:`session` rolls back, so ordinarily there is nothing
    here to delete. It stays because a test that commits deliberately later
    would otherwise leave rows that trip the ``RESTRICT`` foreign keys during
    ``conftest``'s teardown, and the failure would surface as an unrelated
    constraint error in whichever test ran next.
    """
    yield
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM point_ledger_entry WHERE tenant_id = :tid"), {"tid": tenant_id}
        )
        # After the ledger and before reward_item: a redemption debit
        # references a redemption under RESTRICT (migration 0019), and a
        # redemption references the reward item it was opened against.
        conn.execute(text("DELETE FROM redemption WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(
            text("DELETE FROM attendance_record WHERE tenant_id = :tid"), {"tid": tenant_id}
        )
        conn.execute(text("DELETE FROM reward_item WHERE tenant_id = :tid"), {"tid": tenant_id})


@pytest.fixture
def other_tenant_id(engine: Engine) -> Iterator[uuid.UUID]:
    """A second isolated tenant, cleaned up in dependency order.

    ``conftest``'s ``tenant_id`` fixture creates exactly one tenant, and the two
    isolation tests here need a second *real* one — a random UUID would prove
    nothing, since a query filtered by a tenant that does not exist returns
    nothing for uninteresting reasons.

    Cleans up the engagement tables and the events they cite itself, before
    deleting the identity rows, for the same ``RESTRICT`` reason
    ``_clean_engagement_tables`` exists.

    Created for every test in this file, not only the two that name it: the
    :func:`session` fixture depends on it so that teardown order is
    deterministic (see that fixture's docstring). One extra ``tenant`` row per
    test is a cheaper price than a suite that can deadlock.
    """
    tid = uuid.uuid4()
    slug = f"test-other-{tid.hex[:12]}"
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :name)"),
            {"id": tid, "slug": slug, "name": slug},
        )
    yield tid
    with engine.begin() as conn:
        for table in (
            "point_ledger_entry",
            # Migration 0019, between the ledger that debits it and the reward
            # item it names, both RESTRICT.
            "redemption",
            "attendance_record",
            "reward_item",
            # After the attendance rows that cite it and before the unit it
            # hosts at, both of which it references under RESTRICT since
            # migration 0017. `conftest` orders its own teardown the same way;
            # this tenant is not one `conftest` knows about, so the ordering is
            # repeated here rather than inherited.
            "event",
            "user_account",
            "org_unit",
        ):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tid})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tid})


@pytest.fixture
def session(
    session_factory: sessionmaker[Session],
    _clean_engagement_tables: None,
    other_tenant_id: uuid.UUID,
) -> Iterator[Session]:
    """One session per test, rolled back at the end.

    The repository never commits — transaction boundaries belong to the caller,
    which here is this fixture. Rolling back rather than committing keeps each
    test's rows out of the next one's queries without a per-test delete.

    It depends on both cleanup fixtures, and that is load-bearing rather than
    incidental. pytest finalizes in reverse setup order, so naming them here
    makes this session the *last* fixture set up and therefore the *first* torn
    down: the rollback releases its row locks before any teardown issues a
    ``DELETE`` against the same rows. Without that ordering the two deadlock —
    an open transaction holding a lock on ``tenant`` while another connection
    tries to delete it — and the suite hangs rather than failing.
    """
    with session_factory() as active:
        yield active
        active.rollback()


@pytest.fixture
def repository() -> RewardsRepository:
    return RewardsRepository()


# ---------------------------------------------------------------------------
# Row builders. Synthetic fixtures, written by this test — not seeded data.
# ---------------------------------------------------------------------------


def _make_user(session: Session, tenant_id: uuid.UUID) -> uuid.UUID:
    """A ``user_account`` row: a student subject, or a named budget owner."""
    user_id = uuid.uuid4()
    session.execute(
        text(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :tenant_id, :sub, :email)"
        ),
        {
            "id": user_id,
            "tenant_id": tenant_id,
            "sub": unique_subject(f"rewards-{user_id.hex[:8]}"),
            "email": f"{user_id.hex[:8]}@example.edu",
        },
    )
    return user_id


def _record_attendance(session: Session, tenant_id: uuid.UUID, subject_id: uuid.UUID) -> uuid.UUID:
    """One verified attendance for ``subject_id`` at a fresh synthetic event.

    ``method`` is :data:`SYNTHETIC_ATTENDANCE_METHOD` — the same
    ``coordinator_entry`` spelling the synthetic pilot's own writer uses. No QR
    scanner and no live check-in is involved anywhere in this file.

    The event is a real ``event`` row from ``conftest``'s :func:`ensure_event`,
    not a bare ``uuid4``. Migration ``0017`` gave ``attendance_record`` a
    composite foreign key to ``event``, so a fabricated id no longer stores; the
    conftest helper is the one place that knows the honest shape of a synthetic
    event, and this file reuses it rather than growing a second copy.

    The slug is derived from ``record_id``, so every call resolves to its *own*
    event. That is what "a fresh synthetic event" has always meant here and it
    is now load-bearing: the tests that credit one subject
    :data:`CALIBRATION_N_TENTATIVE` times need three distinct events, because
    ``uq_attendance_record_subject_event`` is what stops a subject attending the
    same event twice.
    """
    record_id = uuid.uuid4()
    session.execute(
        text(
            "INSERT INTO attendance_record "
            "(id, tenant_id, owning_unit_id, subject_id, event_id, method) "
            "VALUES (:id, :tenant_id, :unit_id, :subject_id, :event_id, :method)"
        ),
        {
            "id": record_id,
            "tenant_id": tenant_id,
            "unit_id": ensure_owning_unit(session, tenant_id),
            "subject_id": subject_id,
            "event_id": ensure_event(session, tenant_id, f"rewards-{record_id.hex[:8]}"),
            "method": SYNTHETIC_ATTENDANCE_METHOD,
        },
    )
    return record_id


def _insert_reward_item(
    session: Session,
    tenant_id: uuid.UUID,
    *,
    name: str,
    points_cost: int,
    budget_owner_id: uuid.UUID,
    funded: bool,
) -> uuid.UUID:
    """A synthetic ``reward_item`` row.

    ``budget_owner_id`` is required by this helper as well as by the column: the
    unowned case cannot be inserted at all (``NOT NULL`` plus a composite
    foreign key), which is what ``test_engagement_schema_constraints.py`` proves
    and is why *this* file's unlistable fixture is the unfunded one.

    ``fulfilment_cost`` is written as zero because
    ``ck_reward_item_fulfilment_cost_non_negative`` requires a value and nothing
    in this change reads, spends, or reserves it. It is not a claim that a real
    reward costs nothing.
    """
    item_id = uuid.uuid4()
    session.execute(
        text(
            "INSERT INTO reward_item "
            "(id, tenant_id, name, points_cost, fulfilment_cost, budget_owner_id, funded) "
            "VALUES (:id, :tenant_id, :name, :cost, 0, :owner, :funded)"
        ),
        {
            "id": item_id,
            "tenant_id": tenant_id,
            "name": name,
            "cost": points_cost,
            "owner": budget_owner_id,
            "funded": funded,
        },
    )
    return item_id


def _raw_entries(session: Session, tenant_id: uuid.UUID) -> list:
    """Every ledger row in the tenant, read with this file's own SQL.

    Deliberately not the repository's reader: a test proving the repository does
    not hide a row must not ask the repository what the rows are.
    """
    return session.execute(
        text(
            "SELECT id, amount, source_attendance_id, reason, actor_id "
            "FROM point_ledger_entry WHERE tenant_id = :tid ORDER BY occurred_at, id"
        ),
        {"tid": tenant_id},
    ).all()


# ---------------------------------------------------------------------------
# Earning
# ---------------------------------------------------------------------------


def test_a_verified_attendance_credits_the_d7_rate(
    session: Session, tenant_id: uuid.UUID, repository: RewardsRepository
):
    subject = _make_user(session, tenant_id)
    attendance = _record_attendance(session, tenant_id, subject)

    entry_id = repository.credit_attendance(session, tenant_id=tenant_id, attendance_id=attendance)

    rows = _raw_entries(session, tenant_id)
    assert len(rows) == 1
    assert rows[0].id == entry_id
    assert rows[0].amount == POINTS_PER_VERIFIED_ATTENDANCE
    assert rows[0].source_attendance_id == attendance
    assert rows[0].reason == ATTENDANCE_EARN_REASON
    # ADR-0013: derivation from attendance has no human author to name.
    assert rows[0].actor_id is None


def test_the_balance_is_a_fold_over_the_rows(
    session: Session, tenant_id: uuid.UUID, repository: RewardsRepository
):
    """Three verified attendances, and the balance the caller reads is 300.

    Which is also D7's calibration statement made concrete: N = 3 events at 100
    points reaches the cheapest recorded band exactly. The number comes out of
    the ledger, not out of a counter — nothing in this test writes a balance
    anywhere, because there is nowhere to write one.
    """
    subject = _make_user(session, tenant_id)
    for _ in range(CALIBRATION_N_TENTATIVE):
        attendance = _record_attendance(session, tenant_id, subject)
        repository.credit_attendance(session, tenant_id=tenant_id, attendance_id=attendance)

    balance = repository.balance_for_subject(session, tenant_id=tenant_id, subject_id=subject)
    assert balance == CALIBRATION_N_TENTATIVE * POINTS_PER_VERIFIED_ATTENDANCE
    assert balance == min(D7_TENTATIVE_POINT_BANDS)


def test_one_students_attendance_does_not_credit_another(
    session: Session, tenant_id: uuid.UUID, repository: RewardsRepository
):
    """The join through ``attendance_record`` is what makes an entry someone's."""
    earner = _make_user(session, tenant_id)
    bystander = _make_user(session, tenant_id)
    repository.credit_attendance(
        session,
        tenant_id=tenant_id,
        attendance_id=_record_attendance(session, tenant_id, earner),
    )

    assert repository.balance_for_subject(session, tenant_id=tenant_id, subject_id=earner) == 100
    assert repository.balance_for_subject(session, tenant_id=tenant_id, subject_id=bystander) == 0


def test_a_second_credit_for_the_same_attendance_is_refused(
    session: Session, tenant_id: uuid.UUID, repository: RewardsRepository
):
    """The double-credit case, which no constraint in the schema refuses today."""
    subject = _make_user(session, tenant_id)
    attendance = _record_attendance(session, tenant_id, subject)
    repository.credit_attendance(session, tenant_id=tenant_id, attendance_id=attendance)

    with pytest.raises(AlreadyCreditedError, match="already credited"):
        repository.credit_attendance(session, tenant_id=tenant_id, attendance_id=attendance)

    assert len(_raw_entries(session, tenant_id)) == 1
    assert repository.balance_for_subject(session, tenant_id=tenant_id, subject_id=subject) == 100


def test_crediting_an_unrecorded_attendance_is_refused(
    session: Session, tenant_id: uuid.UUID, repository: RewardsRepository
):
    """Points derive from recorded attendance and nothing else (ADR-0013)."""
    with pytest.raises(UnknownAttendanceError, match="ADR-0013"):
        repository.credit_attendance(session, tenant_id=tenant_id, attendance_id=uuid.uuid4())
    assert _raw_entries(session, tenant_id) == []


def test_another_tenants_attendance_is_not_creditable_here(
    session: Session,
    tenant_id: uuid.UUID,
    other_tenant_id: uuid.UUID,
    repository: RewardsRepository,
):
    """The lookup is composite, so a real id in the wrong tenant is still unknown."""
    foreign_subject = _make_user(session, other_tenant_id)
    foreign_attendance = _record_attendance(session, other_tenant_id, foreign_subject)

    with pytest.raises(UnknownAttendanceError):
        repository.credit_attendance(session, tenant_id=tenant_id, attendance_id=foreign_attendance)


# ---------------------------------------------------------------------------
# Corrections stay append-only
# ---------------------------------------------------------------------------


def test_a_reversal_appends_and_leaves_the_original_entry_untouched(
    session: Session, tenant_id: uuid.UUID, repository: RewardsRepository
):
    """ADR-0013: a reversal is a compensating entry, never a delete or an update.

    Proved against the rows, not against the balance: the earning row is read
    before and after and must be identical, and the table must have gained a row
    rather than had one changed.

    Rows are matched by id rather than by position. ``occurred_at`` carries a
    server default of ``now()``, which in PostgreSQL is the *transaction's*
    start time, so two entries written in one transaction — as they are here —
    carry the same timestamp and their relative order is whatever the id tie
    break gives. Asserting on position would make this test depend on a UUID
    comparison, which is a coin flip.
    """
    subject = _make_user(session, tenant_id)
    attendance = _record_attendance(session, tenant_id, subject)
    earned_id = repository.credit_attendance(session, tenant_id=tenant_id, attendance_id=attendance)
    before = _raw_entries(session, tenant_id)

    coordinator = _make_user(session, tenant_id)
    reversal_id = repository.record_reversal(
        session,
        tenant_id=tenant_id,
        attendance_id=attendance,
        reason="attendance recorded against the wrong event",
        actor_id=coordinator,
    )

    after = _raw_entries(session, tenant_id)
    assert len(after) == 2
    earned_before = next(row for row in before if row.id == earned_id)
    earned_after = next(row for row in after if row.id == earned_id)
    assert earned_after == earned_before, "the earning entry was modified rather than compensated"
    assert earned_after.amount == POINTS_PER_VERIFIED_ATTENDANCE

    reversal = next(row for row in after if row.id == reversal_id)
    assert reversal.amount == -POINTS_PER_VERIFIED_ATTENDANCE
    assert reversal.source_attendance_id == attendance
    assert reversal.reason.startswith(REVERSAL_REASON_PREFIX)
    assert "wrong event" in reversal.reason
    # D7: a correction names the coordinator who made it.
    assert reversal.actor_id == coordinator

    assert repository.balance_for_subject(session, tenant_id=tenant_id, subject_id=subject) == 0


def test_a_second_reversal_has_nothing_left_to_withdraw(
    session: Session, tenant_id: uuid.UUID, repository: RewardsRepository
):
    """Refused rather than driving the balance below what was ever earned."""
    subject = _make_user(session, tenant_id)
    attendance = _record_attendance(session, tenant_id, subject)
    repository.credit_attendance(session, tenant_id=tenant_id, attendance_id=attendance)
    repository.record_reversal(
        session, tenant_id=tenant_id, attendance_id=attendance, reason="first correction"
    )

    with pytest.raises(NothingToReverseError, match="no outstanding credit"):
        repository.record_reversal(
            session, tenant_id=tenant_id, attendance_id=attendance, reason="again"
        )

    assert len(_raw_entries(session, tenant_id)) == 2
    assert repository.balance_for_subject(session, tenant_id=tenant_id, subject_id=subject) == 0


def test_reversing_an_uncredited_attendance_is_refused(
    session: Session, tenant_id: uuid.UUID, repository: RewardsRepository
):
    subject = _make_user(session, tenant_id)
    attendance = _record_attendance(session, tenant_id, subject)

    with pytest.raises(NothingToReverseError):
        repository.record_reversal(
            session, tenant_id=tenant_id, attendance_id=attendance, reason="nothing here"
        )
    assert _raw_entries(session, tenant_id) == []


@pytest.mark.parametrize("blank", ["", "   ", "\n\t"])
def test_a_reversal_without_a_stated_reason_is_refused(
    session: Session, tenant_id: uuid.UUID, repository: RewardsRepository, blank: str
):
    """D7: a correction is an appended entry *with a reason*, visible to the student."""
    subject = _make_user(session, tenant_id)
    attendance = _record_attendance(session, tenant_id, subject)
    repository.credit_attendance(session, tenant_id=tenant_id, attendance_id=attendance)

    with pytest.raises(ValueError, match="must state its reason"):
        repository.record_reversal(
            session, tenant_id=tenant_id, attendance_id=attendance, reason=blank
        )
    assert len(_raw_entries(session, tenant_id)) == 1


def test_the_entry_reader_returns_both_sides_of_a_correction(
    session: Session, tenant_id: uuid.UUID, repository: RewardsRepository
):
    """A balance that cannot show its history is the counter ADR-0013 rejected.

    Asserted as a set of amounts rather than a sequence: both rows are written
    in one transaction and therefore share an ``occurred_at``, so their relative
    order is an id tie break. What matters is that the reader returns *both*
    sides of the correction and that each explains itself.
    """
    subject = _make_user(session, tenant_id)
    attendance = _record_attendance(session, tenant_id, subject)
    repository.credit_attendance(session, tenant_id=tenant_id, attendance_id=attendance)
    repository.record_reversal(
        session, tenant_id=tenant_id, attendance_id=attendance, reason="miscounted"
    )

    entries = repository.ledger_entries_for_subject(
        session, tenant_id=tenant_id, subject_id=subject
    )
    assert sorted(entry.amount for entry in entries) == [
        -POINTS_PER_VERIFIED_ATTENDANCE,
        POINTS_PER_VERIFIED_ATTENDANCE,
    ]
    assert all(entry.reason for entry in entries), "every entry explains itself"


# ---------------------------------------------------------------------------
# The catalog — Fix #15, in SQL
# ---------------------------------------------------------------------------


def test_only_funded_owned_items_are_listed(
    session: Session, tenant_id: uuid.UUID, repository: RewardsRepository
):
    """An unfunded row exists in the table and never reaches the listing.

    Both rows are inserted with a real, same-tenant budget owner, because an
    unowned one cannot be inserted at all — ``budget_owner_id NOT NULL`` plus
    the composite foreign key, proved in
    ``test_engagement_schema_constraints.py``. So the case this test can create,
    and the one it therefore checks, is the funded flag.
    """
    owner = _make_user(session, tenant_id)
    funded_id = _insert_reward_item(
        session,
        tenant_id,
        name="listable band",
        points_cost=D7_TENTATIVE_POINT_BANDS[0],
        budget_owner_id=owner,
        funded=True,
    )
    unfunded_id = _insert_reward_item(
        session,
        tenant_id,
        name="unfunded bargain",
        points_cost=1,
        budget_owner_id=owner,
        funded=False,
    )

    in_table = (
        session.execute(
            text("SELECT id FROM reward_item WHERE tenant_id = :tid"), {"tid": tenant_id}
        )
        .scalars()
        .all()
    )
    assert set(in_table) == {funded_id, unfunded_id}

    listed = repository.listable_items(session, tenant_id=tenant_id)
    assert [item.item_id for item in listed] == [funded_id]
    assert all(is_listable(item) for item in listed)
    assert all(item.budget_owner_id == owner and item.funded for item in listed)


def test_the_default_for_funded_is_not_a_listing_permission(
    session: Session, tenant_id: uuid.UUID, repository: RewardsRepository
):
    """An insert silent about ``funded`` takes the fail-closed server default.

    Which means the item is not listed. The default governs a statement that
    says nothing about the column; it is not a decision that anyone funded the
    reward.
    """
    owner = _make_user(session, tenant_id)
    session.execute(
        text(
            "INSERT INTO reward_item "
            "(id, tenant_id, name, points_cost, fulfilment_cost, budget_owner_id) "
            "VALUES (:id, :tid, 'silent about funded', 300, 0, :owner)"
        ),
        {"id": uuid.uuid4(), "tid": tenant_id, "owner": owner},
    )
    assert repository.listable_items(session, tenant_id=tenant_id) == ()


def test_another_tenants_funded_item_is_not_listed_here(
    session: Session,
    tenant_id: uuid.UUID,
    other_tenant_id: uuid.UUID,
    repository: RewardsRepository,
):
    """A catalog leaking across institutions would be the worst version of Fix #15."""
    foreign_owner = _make_user(session, other_tenant_id)
    _insert_reward_item(
        session,
        other_tenant_id,
        name="another institution's reward",
        points_cost=300,
        budget_owner_id=foreign_owner,
        funded=True,
    )
    assert repository.listable_items(session, tenant_id=tenant_id) == ()


def test_listing_is_ordered_by_cost(
    session: Session, tenant_id: uuid.UUID, repository: RewardsRepository
):
    owner = _make_user(session, tenant_id)
    for cost in reversed(D7_TENTATIVE_POINT_BANDS):
        _insert_reward_item(
            session,
            tenant_id,
            name=f"band {cost}",
            points_cost=cost,
            budget_owner_id=owner,
            funded=True,
        )
    listed = repository.listable_items(session, tenant_id=tenant_id)
    assert [item.points_cost for item in listed] == list(D7_TENTATIVE_POINT_BANDS)


def test_the_listed_catalog_satisfies_the_tentative_calibration(
    session: Session, tenant_id: uuid.UUID, repository: RewardsRepository
):
    """The cheapest *listed* reward is reachable within D7's tentative N.

    Cited against D7's recorded figures, which are tentative — this asserts the
    property holds for these synthetic rows at those numbers, not that the
    numbers are approved.
    """
    owner = _make_user(session, tenant_id)
    for cost in D7_TENTATIVE_POINT_BANDS:
        _insert_reward_item(
            session,
            tenant_id,
            name=f"band {cost}",
            points_cost=cost,
            budget_owner_id=owner,
            funded=True,
        )
    listed = repository.listable_items(session, tenant_id=tenant_id)
    assert satisfies_calibration(
        listed,
        points_per_event=POINTS_PER_VERIFIED_ATTENDANCE,
        events=CALIBRATION_N_TENTATIVE,
    )


# ---------------------------------------------------------------------------
# The two halves meeting: a folded balance against a listed catalog
# ---------------------------------------------------------------------------


def test_three_attendances_reach_the_cheapest_listed_reward(
    session: Session, tenant_id: uuid.UUID, repository: RewardsRepository
):
    """End to end, with every number coming from the server.

    Attendance rows are recorded, credited, folded into a balance, measured
    against a listed item's cost, and a redemption is opened at that balance —
    without a stored counter anywhere, and without the browser, which is not in
    this picture at all, computing any part of it.
    """
    subject = _make_user(session, tenant_id)
    owner = _make_user(session, tenant_id)
    cheapest_id = _insert_reward_item(
        session,
        tenant_id,
        name="cheapest listed band",
        points_cost=D7_TENTATIVE_POINT_BANDS[0],
        budget_owner_id=owner,
        funded=True,
    )

    listed = repository.listable_items(session, tenant_id=tenant_id)
    cheapest = next(item for item in listed if item.item_id == cheapest_id)

    balance = repository.balance_for_subject(session, tenant_id=tenant_id, subject_id=subject)
    assert balance == 0
    assert events_still_needed(cheapest, balance=balance) == CALIBRATION_N_TENTATIVE

    for _ in range(CALIBRATION_N_TENTATIVE):
        repository.credit_attendance(
            session,
            tenant_id=tenant_id,
            attendance_id=_record_attendance(session, tenant_id, subject),
        )

    balance = repository.balance_for_subject(session, tenant_id=tenant_id, subject_id=subject)
    assert events_still_needed(cheapest, balance=balance) == 0

    redemption = request_redemption(
        redemption_id=uuid.uuid4(), subject_id=subject, item=cheapest, balance=balance
    )
    assert redemption.state is RedemptionState.REQUESTED
    assert redemption.points_cost_snapshot == cheapest.points_cost


def test_an_unfunded_item_is_never_reachable_through_the_listing(
    session: Session, tenant_id: uuid.UUID, repository: RewardsRepository
):
    """Points do not buy a reward nobody has funded.

    The unfunded row is never returned by the listing, so a caller working from
    the listing cannot reach it at all; this asserts the absence directly rather
    than through the domain's own refusal, which the unit suite covers.
    """
    owner = _make_user(session, tenant_id)
    _insert_reward_item(
        session,
        tenant_id,
        name="unfunded bargain",
        points_cost=1,
        budget_owner_id=owner,
        funded=False,
    )
    assert repository.listable_items(session, tenant_id=tenant_id) == ()


# ---------------------------------------------------------------------------
# The redemption, durable at last (migration 0019, plan card L4)
# ---------------------------------------------------------------------------


def _fund_a_listed_item(
    session: Session, tenant_id: uuid.UUID, *, points_cost: int = D7_TENTATIVE_POINT_BANDS[0]
) -> uuid.UUID:
    """A listable reward at one of D7's recorded bands, with a real owner."""
    return _insert_reward_item(
        session,
        tenant_id,
        name="listed band",
        points_cost=points_cost,
        budget_owner_id=_make_user(session, tenant_id),
        funded=True,
    )


def _earn(
    session: Session, tenant_id: uuid.UUID, repository: RewardsRepository, subject: uuid.UUID
) -> None:
    """Credit one verified attendance to ``subject``."""
    repository.credit_attendance(
        session,
        tenant_id=tenant_id,
        attendance_id=_record_attendance(session, tenant_id, subject),
    )


def test_a_requested_redemption_survives_being_read_back(
    session: Session, tenant_id: uuid.UUID, repository: RewardsRepository
):
    """The gap this migration closed, as the thing it enables.

    Before migration ``0019`` the redemption state machine lived entirely in
    memory: there was no ``redemption`` table, so a request existed only for as
    long as the process that made it. This is the same request written down and
    read back by id, with its D7 snapshots intact.
    """
    subject = _make_user(session, tenant_id)
    item = _fund_a_listed_item(session, tenant_id)
    for _ in range(CALIBRATION_N_TENTATIVE):
        _earn(session, tenant_id, repository, subject)

    opened = repository.open_redemption(
        session, tenant_id=tenant_id, subject_id=subject, item_id=item
    )
    assert opened.state is RedemptionState.REQUESTED

    reread = repository.load_redemption(
        session, tenant_id=tenant_id, redemption_id=opened.redemption_id
    )
    assert reread == opened, "the row reads back as the value that was written"
    assert reread.points_cost_snapshot == D7_TENTATIVE_POINT_BANDS[0]
    assert reread.item_name_snapshot == "listed band"


def test_a_redemption_cannot_be_opened_against_an_unaffordable_balance(
    session: Session, tenant_id: uuid.UUID, repository: RewardsRepository
):
    """The balance check is server-side and happens before any row exists.

    Two attendances is 200 points against D7's 300-point cheapest band, so the
    request is refused — and refused before the redemption is written, not
    after, which is what keeps an unaffordable request from ever being a row
    someone could approve.
    """
    subject = _make_user(session, tenant_id)
    item = _fund_a_listed_item(session, tenant_id)
    for _ in range(2):
        _earn(session, tenant_id, repository, subject)

    with pytest.raises(ValueError, match="does not cover"):
        repository.open_redemption(session, tenant_id=tenant_id, subject_id=subject, item_id=item)

    assert (
        repository.redemptions_for_subject(session, tenant_id=tenant_id, subject_id=subject) == ()
    )


def test_an_unfunded_item_cannot_be_redeemed_even_by_id(
    session: Session, tenant_id: uuid.UUID, repository: RewardsRepository
):
    """D6, at the write path rather than only at the listing.

    The listing already excludes an unfunded row, but a caller holding an id
    from somewhere else must be refused too — otherwise "not listed" would be a
    presentation rule rather than a promise about what can be redeemed.
    """
    subject = _make_user(session, tenant_id)
    item = _insert_reward_item(
        session,
        tenant_id,
        name="unfunded bargain",
        points_cost=1,
        budget_owner_id=_make_user(session, tenant_id),
        funded=False,
    )
    _earn(session, tenant_id, repository, subject)

    with pytest.raises(UnlistableRewardError):
        repository.open_redemption(session, tenant_id=tenant_id, subject_id=subject, item_id=item)


def test_a_second_request_for_an_in_flight_reward_resolves_to_the_first(
    session: Session, tenant_id: uuid.UUID, repository: RewardsRepository
):
    """Card L4: "concurrent duplicate requests resolve to one redemption".

    Sequentially here rather than concurrently, because what makes the
    concurrent case safe is ``uq_redemption_open_per_item`` and not the order
    of two calls: the second insert conflicts against the index whichever
    transaction reaches it second, and this method reads the in-flight row back
    instead of opening a twin.
    """
    subject = _make_user(session, tenant_id)
    item = _fund_a_listed_item(session, tenant_id)
    for _ in range(CALIBRATION_N_TENTATIVE):
        _earn(session, tenant_id, repository, subject)

    first = repository.open_redemption(
        session, tenant_id=tenant_id, subject_id=subject, item_id=item
    )
    again = repository.open_redemption(
        session, tenant_id=tenant_id, subject_id=subject, item_id=item
    )

    assert again.redemption_id == first.redemption_id
    assert (
        len(repository.redemptions_for_subject(session, tenant_id=tenant_id, subject_id=subject))
        == 1
    )


def test_fulfilment_debits_the_ledger_and_the_balance_is_the_fold(
    session: Session, tenant_id: uuid.UUID, repository: RewardsRepository
):
    """Card L4's "balance check and ledger debit are atomic", end to end.

    Three verified attendances earn D7's cheapest band exactly; the redemption
    is approved and then fulfilled, and the debit appears as a *fourth* row
    rather than as an edit to any of the three. The balance afterwards is what
    those four rows fold to — nothing decremented a counter, because there is
    no counter.
    """
    subject = _make_user(session, tenant_id)
    coordinator = _make_user(session, tenant_id)
    item = _fund_a_listed_item(session, tenant_id)
    for _ in range(CALIBRATION_N_TENTATIVE):
        _earn(session, tenant_id, repository, subject)

    opened = repository.open_redemption(
        session, tenant_id=tenant_id, subject_id=subject, item_id=item
    )
    repository.transition_redemption(
        session,
        tenant_id=tenant_id,
        redemption_id=opened.redemption_id,
        to_state=RedemptionState.APPROVED,
        actor_id=coordinator,
    )
    fulfilled = repository.transition_redemption(
        session,
        tenant_id=tenant_id,
        redemption_id=opened.redemption_id,
        to_state=RedemptionState.FULFILLED,
        actor_id=coordinator,
    )

    assert fulfilled.state is RedemptionState.FULFILLED
    assert repository.balance_for_subject(session, tenant_id=tenant_id, subject_id=subject) == 0

    entries = repository.ledger_entries_for_subject(
        session, tenant_id=tenant_id, subject_id=subject
    )
    assert len(entries) == CALIBRATION_N_TENTATIVE + 1
    debits = [entry for entry in entries if entry.kind is LedgerEntryKind.REDEMPTION_DEBIT]
    assert len(debits) == 1
    assert debits[0].amount == -D7_TENTATIVE_POINT_BANDS[0]
    assert debits[0].source_attendance_id is None, "a debit derives from no attendance"
    assert debits[0].source_redemption_id == opened.redemption_id
    assert debits[0].reason.startswith(REDEMPTION_DEBIT_REASON_PREFIX)
    assert all(
        entry.amount == POINTS_PER_VERIFIED_ATTENDANCE
        for entry in entries
        if entry.kind is LedgerEntryKind.ATTENDANCE_CREDIT
    ), "the credits are untouched by the debit"


def test_a_debit_is_included_in_the_balance_the_reader_folds(
    session: Session, tenant_id: uuid.UUID, repository: RewardsRepository
):
    """The reader joins through *both* sources, and this is why that matters.

    ``point_ledger_entry`` has no subject column, so an entry belongs to a
    student by way of what it derives from. A debit derives from a redemption,
    so a reader joining only through ``attendance_record`` would drop it — and
    report a balance that is too high, as though it were exact. The redeeming
    student's balance must be the one that fell.
    """
    spender = _make_user(session, tenant_id)
    bystander = _make_user(session, tenant_id)
    coordinator = _make_user(session, tenant_id)
    item = _fund_a_listed_item(session, tenant_id)
    for _ in range(CALIBRATION_N_TENTATIVE + 1):
        _earn(session, tenant_id, repository, spender)
    _earn(session, tenant_id, repository, bystander)

    opened = repository.open_redemption(
        session, tenant_id=tenant_id, subject_id=spender, item_id=item
    )
    for state in (RedemptionState.APPROVED, RedemptionState.FULFILLED):
        repository.transition_redemption(
            session,
            tenant_id=tenant_id,
            redemption_id=opened.redemption_id,
            to_state=state,
            actor_id=coordinator,
        )

    earned = (CALIBRATION_N_TENTATIVE + 1) * POINTS_PER_VERIFIED_ATTENDANCE
    assert (
        repository.balance_for_subject(session, tenant_id=tenant_id, subject_id=spender)
        == earned - D7_TENTATIVE_POINT_BANDS[0]
    )
    assert (
        repository.balance_for_subject(session, tenant_id=tenant_id, subject_id=bystander)
        == POINTS_PER_VERIFIED_ATTENDANCE
    ), "one student's redemption is not another student's debit"


def test_a_request_cannot_skip_the_approval_step(
    session: Session, tenant_id: uuid.UUID, repository: RewardsRepository
):
    """ADR-0013: redemption "is a command with an approval step".

    The refusal is the domain's — this method builds the value from the row and
    asks it — so there is one statement of the state machine rather than two.
    Nothing is written, and no debit is taken.
    """
    subject = _make_user(session, tenant_id)
    coordinator = _make_user(session, tenant_id)
    item = _fund_a_listed_item(session, tenant_id)
    for _ in range(CALIBRATION_N_TENTATIVE):
        _earn(session, tenant_id, repository, subject)

    opened = repository.open_redemption(
        session, tenant_id=tenant_id, subject_id=subject, item_id=item
    )
    with pytest.raises(InvalidRedemptionTransition):
        repository.transition_redemption(
            session,
            tenant_id=tenant_id,
            redemption_id=opened.redemption_id,
            to_state=RedemptionState.FULFILLED,
            actor_id=coordinator,
        )

    still_requested = repository.load_redemption(
        session, tenant_id=tenant_id, redemption_id=opened.redemption_id
    )
    assert still_requested.state is RedemptionState.REQUESTED
    assert (
        repository.balance_for_subject(session, tenant_id=tenant_id, subject_id=subject)
        == CALIBRATION_N_TENTATIVE * POINTS_PER_VERIFIED_ATTENDANCE
    ), "a refused fulfilment takes no debit"


def test_a_denied_redemption_takes_no_debit(
    session: Session, tenant_id: uuid.UUID, repository: RewardsRepository
):
    """The debit is taken at fulfilment, so a denial costs the student nothing.

    That is the whole reason for choosing fulfilment over request as the moment
    of the debit: the alternative needs a refund entry, and a refund is a fourth
    kind of ledger row that ``ck_point_ledger_entry_kind`` does not admit.
    """
    subject = _make_user(session, tenant_id)
    coordinator = _make_user(session, tenant_id)
    item = _fund_a_listed_item(session, tenant_id)
    for _ in range(CALIBRATION_N_TENTATIVE):
        _earn(session, tenant_id, repository, subject)

    opened = repository.open_redemption(
        session, tenant_id=tenant_id, subject_id=subject, item_id=item
    )
    denied = repository.transition_redemption(
        session,
        tenant_id=tenant_id,
        redemption_id=opened.redemption_id,
        to_state=RedemptionState.DENIED,
        actor_id=coordinator,
    )

    assert denied.state is RedemptionState.DENIED
    assert denied.is_terminal
    assert (
        repository.balance_for_subject(session, tenant_id=tenant_id, subject_id=subject)
        == CALIBRATION_N_TENTATIVE * POINTS_PER_VERIFIED_ATTENDANCE
    )


def test_an_expiry_records_no_author_and_an_approval_requires_one(
    session: Session, tenant_id: uuid.UUID, repository: RewardsRepository
):
    """An expiry is something time does; an approval is something a person does.

    Both halves refused at the call, before a statement is issued, rather than
    surfacing as ``ck_redemption_approval_evidence`` naming a constraint the
    caller would have to decode.
    """
    subject = _make_user(session, tenant_id)
    coordinator = _make_user(session, tenant_id)
    item = _fund_a_listed_item(session, tenant_id)
    for _ in range(CALIBRATION_N_TENTATIVE):
        _earn(session, tenant_id, repository, subject)

    opened = repository.open_redemption(
        session, tenant_id=tenant_id, subject_id=subject, item_id=item
    )
    with pytest.raises(ValueError, match="must be named"):
        repository.transition_redemption(
            session,
            tenant_id=tenant_id,
            redemption_id=opened.redemption_id,
            to_state=RedemptionState.APPROVED,
        )
    with pytest.raises(ValueError, match="no author"):
        repository.transition_redemption(
            session,
            tenant_id=tenant_id,
            redemption_id=opened.redemption_id,
            to_state=RedemptionState.EXPIRED,
            actor_id=coordinator,
        )

    expired = repository.transition_redemption(
        session,
        tenant_id=tenant_id,
        redemption_id=opened.redemption_id,
        to_state=RedemptionState.EXPIRED,
    )
    assert expired.state is RedemptionState.EXPIRED


def test_fulfilment_is_refused_when_the_points_behind_it_were_reversed(
    session: Session, tenant_id: uuid.UUID, repository: RewardsRepository
):
    """The balance is re-folded at fulfilment, not trusted from the request.

    A redemption sits ``approved`` for as long as a coordinator takes, and a
    miscounted attendance may be corrected in between. Fulfilling anyway would
    drive the balance below what the student ever earned — so it is refused,
    and the redemption stays ``approved`` for a coordinator to deny or expire.
    """
    subject = _make_user(session, tenant_id)
    coordinator = _make_user(session, tenant_id)
    item = _fund_a_listed_item(session, tenant_id)
    attendances = [_record_attendance(session, tenant_id, subject) for _ in range(3)]
    for attendance in attendances:
        repository.credit_attendance(session, tenant_id=tenant_id, attendance_id=attendance)

    opened = repository.open_redemption(
        session, tenant_id=tenant_id, subject_id=subject, item_id=item
    )
    repository.transition_redemption(
        session,
        tenant_id=tenant_id,
        redemption_id=opened.redemption_id,
        to_state=RedemptionState.APPROVED,
        actor_id=coordinator,
    )
    repository.record_reversal(
        session, tenant_id=tenant_id, attendance_id=attendances[0], reason="miscounted"
    )

    with pytest.raises(InsufficientBalanceError, match="no longer covers"):
        repository.transition_redemption(
            session,
            tenant_id=tenant_id,
            redemption_id=opened.redemption_id,
            to_state=RedemptionState.FULFILLED,
            actor_id=coordinator,
        )

    session.rollback()
    still_approved = repository.load_redemption(
        session, tenant_id=tenant_id, redemption_id=opened.redemption_id
    )
    assert still_approved is None, "the rolled-back transaction wrote nothing at all"


def test_a_redemption_in_another_tenant_is_not_reachable(
    session: Session,
    tenant_id: uuid.UUID,
    other_tenant_id: uuid.UUID,
    repository: RewardsRepository,
):
    """Tenant isolation on the read path, as every other repository here has it."""
    subject = _make_user(session, tenant_id)
    item = _fund_a_listed_item(session, tenant_id)
    for _ in range(CALIBRATION_N_TENTATIVE):
        _earn(session, tenant_id, repository, subject)
    opened = repository.open_redemption(
        session, tenant_id=tenant_id, subject_id=subject, item_id=item
    )

    assert (
        repository.load_redemption(
            session, tenant_id=other_tenant_id, redemption_id=opened.redemption_id
        )
        is None
    )
    assert (
        repository.redemptions_for_subject(session, tenant_id=other_tenant_id, subject_id=subject)
        == ()
    )
