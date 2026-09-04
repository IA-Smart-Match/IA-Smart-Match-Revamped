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
    RedemptionState,
    events_still_needed,
    is_listable,
    request_redemption,
    satisfies_calibration,
)
from smartmatch_domain.synthetic_pilot import SYNTHETIC_ATTENDANCE_METHOD
from smartmatch_persistence.rewards import (
    ATTENDANCE_EARN_REASON,
    REVERSAL_REASON_PREFIX,
    AlreadyCreditedError,
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
