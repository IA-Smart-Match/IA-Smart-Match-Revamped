"""Behavioural coverage for the ADR-0013 engagement schema (migration ``0009``).

Same pattern ``test_import_review_constraints.py`` set for ``review_item``:
`tests/integration/test_check_constraints.py` is the shared home for CHECK
constraint *declarations* (`CHECK_CONSTRAINT_DEFINITIONS`,
`BEHAVIOURAL_COVERAGE`), and its own meta-test requires every live CHECK
constraint to be declared there — but the forbidden-write and permitted-write
tests themselves live in a separate, newly-added file, so that landing three
new tables does not require editing a file other tracks are touching
concurrently. This file is that separate file for
``ck_attendance_record_method``, ``ck_point_ledger_entry_amount_nonzero``,
``ck_reward_item_points_cost_positive``, and
``ck_reward_item_fulfilment_cost_non_negative``.

It also covers the two constraints ADR-0013 is chiefly about, which are not
CHECK constraints and so are not in that registry at all:
``reward_item.budget_owner_id NOT NULL`` and ``reward_item.funded NOT NULL``
— D6's "named human budget owner" and "funded balance", each unenforceable by
convention alone (Fix #15) and each proved here to be unenforceable to *skip*
now: an explicit ``NULL`` for either is refused by PostgreSQL, not by an
application check that a caller could bypass or forget. And it covers
``uq_attendance_record_subject_event``, which protects the one thing
ADR-0013 says points may depend on ("attendance ... and nothing else") from a
duplicate recording of the same evidence.

Requires a live database, and is skipped when none is reachable (``engine``
fixture, ``tests/integration/conftest.py``).

No shared teardown to lean on. ``review_item``'s rows are cleaned up for free
because ``import_batch`` cascades from ``job``, and ``job`` is one of the
tables ``conftest.py``'s ``tenant_id`` fixture deletes on teardown. Every
foreign key this migration adds is deliberately ``RESTRICT``, not ``CASCADE``
(see ``0009_engagement_schema.py``'s docstring for why), so a row left behind
here would make that fixture's own teardown fail trying to delete the
``user_account``/``org_unit`` row it still references. ``_clean_engagement_tables``
below is this file's own teardown, run before ``tenant_id``'s by fixture
dependency order, so nothing crosses that boundary.
"""

from __future__ import annotations

import uuid

import pytest

pytest.importorskip("sqlalchemy")

from conftest import ensure_owning_unit, unique_subject
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clean_engagement_tables(engine: Engine, tenant_id):
    """Delete this file's rows before ``tenant_id`` tears down its own.

    Runs after every test in this module. Depending on ``tenant_id`` makes
    pytest tear this down *first* (fixture teardown is the reverse of setup
    order), which is what lets ``conftest.py``'s own teardown delete
    ``user_account`` and ``org_unit`` afterwards without tripping the
    ``RESTRICT`` foreign keys ``attendance_record`` and ``reward_item`` hold
    against them. Ordered child-before-parent: ``point_ledger_entry`` before
    ``attendance_record``.
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


# ---------------------------------------------------------------------------
# Row builders.
# ---------------------------------------------------------------------------


def _make_user(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    user_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :tenant_id, :sub, :email)"
        ),
        {
            "id": user_id,
            "tenant_id": tenant_id,
            "sub": unique_subject(f"engagement-{user_id.hex[:8]}"),
            "email": f"{user_id.hex[:8]}@example.edu",
        },
    )
    return user_id


def _insert_attendance(
    conn,
    tenant_id: uuid.UUID,
    *,
    subject_id: uuid.UUID | None = None,
    event_id: uuid.UUID | None = None,
    method: str = "qr_scan",
) -> uuid.UUID:
    """Insert an ``attendance_record`` row and return its id.

    Builds its own ``user_account`` (the subject) and reuses the test
    tenant's shared job-owning unit (``ensure_owning_unit``) unless the
    caller wants a specific subject or event — needed by the duplicate-row
    test below, which must reuse both across two inserts.
    """
    record_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO attendance_record "
            "(id, tenant_id, owning_unit_id, subject_id, event_id, method) "
            "VALUES (:id, :tenant_id, :unit_id, :subject_id, :event_id, :method)"
        ),
        {
            "id": record_id,
            "tenant_id": tenant_id,
            "unit_id": ensure_owning_unit(conn, tenant_id),
            "subject_id": subject_id or _make_user(conn, tenant_id),
            "event_id": event_id or uuid.uuid4(),
            "method": method,
        },
    )
    return record_id


def _insert_ledger_entry(
    conn, tenant_id: uuid.UUID, source_attendance_id: uuid.UUID, amount: int
) -> None:
    conn.execute(
        text(
            "INSERT INTO point_ledger_entry "
            "(id, tenant_id, amount, source_attendance_id, reason) "
            "VALUES (:id, :tenant_id, :amount, :source_id, :reason)"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "amount": amount,
            "source_id": source_attendance_id,
            "reason": "verified attendance",
        },
    )


def _insert_reward_item(
    conn,
    tenant_id: uuid.UUID,
    *,
    points_cost: int = 300,
    fulfilment_cost: str = "0",
    budget_owner_id: object = "__auto__",
    funded: object = True,
) -> uuid.UUID:
    """Insert a ``reward_item`` row and return its id.

    ``budget_owner_id`` and ``funded`` default to a legitimate, listable row
    (ADR-0013's happy path); pass an explicit ``None`` for either to exercise
    the ``NOT NULL`` constraint the test is about. The sentinel default
    (rather than ``None``) is what lets ``None`` mean "write an explicit SQL
    NULL" instead of "omit the value".
    """
    item_id = uuid.uuid4()
    owner = _make_user(conn, tenant_id) if budget_owner_id == "__auto__" else budget_owner_id
    conn.execute(
        text(
            "INSERT INTO reward_item "
            "(id, tenant_id, name, points_cost, fulfilment_cost, budget_owner_id, funded) "
            "VALUES (:id, :tenant_id, 'Mentor session', :points_cost, :fulfilment_cost, "
            ":owner, :funded)"
        ),
        {
            "id": item_id,
            "tenant_id": tenant_id,
            "points_cost": points_cost,
            "fulfilment_cost": fulfilment_cost,
            "owner": owner,
            "funded": funded,
        },
    )
    return item_id


# ---------------------------------------------------------------------------
# ck_attendance_record_method — qr_scan | coordinator_entry | import
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["scan", "QR_SCAN", "", "coordinator"])
def test_attendance_record_rejects_a_method_outside_the_vocabulary(
    engine: Engine, tenant_id, method: str
) -> None:
    with pytest.raises(IntegrityError, match="ck_attendance_record_method"), engine.begin() as conn:
        _insert_attendance(conn, tenant_id, method=method)


@pytest.mark.parametrize("method", ["qr_scan", "coordinator_entry", "import"])
def test_attendance_record_accepts_every_vocabulary_value(
    engine: Engine, tenant_id, method: str
) -> None:
    """All three: QR check-in, a coordinator's manual entry, and a bulk import row."""
    with engine.begin() as conn:
        _insert_attendance(conn, tenant_id, method=method)


# ---------------------------------------------------------------------------
# uq_attendance_record_subject_event — attendance is the only input to points
# ---------------------------------------------------------------------------


def test_attendance_record_rejects_a_duplicate_for_the_same_student_and_event(
    engine: Engine, tenant_id
) -> None:
    """A re-scan of the same student at the same event must not double-credit points."""
    with engine.begin() as conn:
        subject_id = _make_user(conn, tenant_id)
        event_id = uuid.uuid4()
        _insert_attendance(conn, tenant_id, subject_id=subject_id, event_id=event_id)

    with (
        pytest.raises(IntegrityError, match="uq_attendance_record_subject_event"),
        engine.begin() as conn,
    ):
        _insert_attendance(conn, tenant_id, subject_id=subject_id, event_id=event_id)


def test_attendance_record_accepts_the_same_student_at_a_different_event(
    engine: Engine, tenant_id
) -> None:
    """The constraint is per-event, not a one-record-per-student rule."""
    with engine.begin() as conn:
        subject_id = _make_user(conn, tenant_id)
        _insert_attendance(conn, tenant_id, subject_id=subject_id, event_id=uuid.uuid4())
        _insert_attendance(conn, tenant_id, subject_id=subject_id, event_id=uuid.uuid4())


# ---------------------------------------------------------------------------
# ck_point_ledger_entry_amount_nonzero, and no balance anywhere in the write path
# ---------------------------------------------------------------------------


def test_point_ledger_entry_rejects_a_zero_amount(engine: Engine, tenant_id) -> None:
    """A zero-amount row changes nothing and records nothing; it is not a ledger entry."""
    with (
        pytest.raises(IntegrityError, match="ck_point_ledger_entry_amount_nonzero"),
        engine.begin() as conn,
    ):
        source_id = _insert_attendance(conn, tenant_id)
        _insert_ledger_entry(conn, tenant_id, source_id, amount=0)


def test_point_ledger_entry_accepts_a_positive_credit_and_a_negative_reversal(
    engine: Engine, tenant_id
) -> None:
    """ADR-0013: "A reversal is a compensating entry, never a delete."

    Both entries name the same ``source_attendance_id`` — the reversal
    corrects the credit without deleting or updating it, which is only
    possible because ``amount`` is signed.
    """
    with engine.begin() as conn:
        source_id = _insert_attendance(conn, tenant_id)
        _insert_ledger_entry(conn, tenant_id, source_id, amount=100)
        _insert_ledger_entry(conn, tenant_id, source_id, amount=-100)


def test_point_ledger_entry_source_must_reference_a_real_attendance_record(
    engine: Engine, tenant_id
) -> None:
    """Points derive from recorded attendance and nothing else (ADR-0013).

    A ledger entry naming an attendance id that does not exist would be a
    discretionary grant wearing the shape of a derived one; the foreign key
    refuses it.
    """
    with pytest.raises(IntegrityError), engine.begin() as conn:
        _insert_ledger_entry(conn, tenant_id, uuid.uuid4(), amount=100)


# ---------------------------------------------------------------------------
# reward_item — the schema constraint ADR-0013 is chiefly about
# ---------------------------------------------------------------------------


def test_reward_item_rejects_a_null_budget_owner(engine: Engine, tenant_id) -> None:
    """D6: no budget holder is named, so the row must be impossible to write, not merely wrong."""
    with (
        pytest.raises(IntegrityError, match=r"(?i)null value|not-null|budget_owner_id"),
        engine.begin() as conn,
    ):
        _insert_reward_item(conn, tenant_id, budget_owner_id=None)


def test_reward_item_rejects_a_null_funded_state(engine: Engine, tenant_id) -> None:
    """The other half of D6's structural pair. Explicit NULL, not merely omitted."""
    with (
        pytest.raises(IntegrityError, match=r"(?i)null value|not-null|funded"),
        engine.begin() as conn,
    ):
        _insert_reward_item(conn, tenant_id, funded=None)


def test_reward_item_accepts_a_named_owner_and_a_funded_balance(engine: Engine, tenant_id) -> None:
    """The legitimate path: a real owner in this tenant, explicitly marked funded."""
    with engine.begin() as conn:
        _insert_reward_item(conn, tenant_id, points_cost=300, fulfilment_cost="0", funded=True)


def test_reward_item_budget_owner_must_be_a_real_account_in_the_same_tenant(
    engine: Engine, tenant_id
) -> None:
    """A composite foreign key: an owner id from nowhere (or another tenant) is refused."""
    with pytest.raises(IntegrityError), engine.begin() as conn:
        _insert_reward_item(conn, tenant_id, budget_owner_id=uuid.uuid4())


# ---------------------------------------------------------------------------
# ck_reward_item_points_cost_positive
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("points_cost", [0, -50])
def test_reward_item_rejects_a_non_positive_points_cost(
    engine: Engine, tenant_id, points_cost: int
) -> None:
    with (
        pytest.raises(IntegrityError, match="ck_reward_item_points_cost_positive"),
        engine.begin() as conn,
    ):
        _insert_reward_item(conn, tenant_id, points_cost=points_cost)


def test_reward_item_accepts_the_calibrated_cheapest_band(engine: Engine, tenant_id) -> None:
    """D7's tentative numbers (``docs/decisions/pilot-decisions.md``): 100 pts/event, N=3.

    300 is the cheapest proposed band, reachable in exactly three events —
    the calibration property the schema does not enforce itself (that is a
    catalog-level test against the live table, per ADR-0013 §"The economy is
    calibrated against a stated, testable property") but must at least be a
    row this schema can hold.
    """
    with engine.begin() as conn:
        _insert_reward_item(conn, tenant_id, points_cost=300)


# ---------------------------------------------------------------------------
# ck_reward_item_fulfilment_cost_non_negative
# ---------------------------------------------------------------------------


def test_reward_item_rejects_a_negative_fulfilment_cost(engine: Engine, tenant_id) -> None:
    with (
        pytest.raises(IntegrityError, match="ck_reward_item_fulfilment_cost_non_negative"),
        engine.begin() as conn,
    ):
        _insert_reward_item(conn, tenant_id, fulfilment_cost="-1")


@pytest.mark.parametrize("fulfilment_cost", ["0", "25.5000"])
def test_reward_item_accepts_a_non_negative_fulfilment_cost(
    engine: Engine, tenant_id, fulfilment_cost: str
) -> None:
    """Zero for a free-to-give item (a certificate PDF); positive for a real cost."""
    with engine.begin() as conn:
        _insert_reward_item(conn, tenant_id, fulfilment_cost=fulfilment_cost)


# ---------------------------------------------------------------------------
# D6 (pilot scope, closed 2026-09-02) — the guarantees behind "a named human
# budget owner", verified rather than extended.
#
# `docs/decisions/pilot-decisions.md` §D6 authorizes verification of the
# already-authorized existing-schema and append-only guarantees, and nothing
# else: no budget envelope, no catalog, no listing, no redemption. The tests
# below tighten what was already covered, each against a case the existing
# assertions leave open — an omitted column rather than an explicit NULL, a
# real account in the wrong tenant rather than an id from nowhere, and the
# writes that could weaken a row *after* it was legitimately written.
# ---------------------------------------------------------------------------


@pytest.fixture
def other_tenant_id(engine: Engine):
    """A second tenant, so "same tenant" can be tested rather than assumed.

    An id belonging to nobody is refused by any foreign key. The composite key
    ADR-0013 chose is about the narrower case only a second tenant can express:
    a *real* account, in good standing, somewhere else.
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
        conn.execute(text("DELETE FROM user_account WHERE tenant_id = :tid"), {"tid": tid})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tid})


def test_reward_item_rejects_an_omitted_budget_owner(engine: Engine, tenant_id) -> None:
    """The absent case, which is not the same statement as an explicit NULL.

    ``test_reward_item_rejects_a_null_budget_owner`` writes ``NULL`` on purpose.
    This writes an INSERT that never mentions the column at all — the shape a
    caller produces by forgetting rather than by deciding — and it must be
    refused for the reason the migration gives: ``budget_owner_id`` carries no
    server default, because there is no safe value to fall back to for who owns
    a budget. ``funded`` has one and this is what distinguishes them.
    """
    with (
        pytest.raises(IntegrityError, match=r"(?i)null value|not-null|budget_owner_id"),
        engine.begin() as conn,
    ):
        conn.execute(
            text(
                "INSERT INTO reward_item (id, tenant_id, name, points_cost, fulfilment_cost) "
                "VALUES (:id, :tenant_id, 'Mentor session', 300, 0)"
            ),
            {"id": uuid.uuid4(), "tenant_id": tenant_id},
        )


def test_reward_item_defaults_to_unfunded_when_funded_is_omitted(engine: Engine, tenant_id) -> None:
    """The default is fail-closed, and a default is not a permission.

    Omitting ``funded`` writes ``false``: an item nothing has agreed to pay for
    is the safe reading of silence, matching ``tenant_budget.kill_switch`` and
    ``user_account.suspended``. The row is still refused if the *owner* is
    missing — the default governs only the column that has one — so this test
    supplies a real owner and asserts the stored value rather than the refusal.
    """
    item_id = uuid.uuid4()
    with engine.begin() as conn:
        owner = _make_user(conn, tenant_id)
        conn.execute(
            text(
                "INSERT INTO reward_item "
                "(id, tenant_id, name, points_cost, fulfilment_cost, budget_owner_id) "
                "VALUES (:id, :tenant_id, 'Mentor session', 300, 0, :owner)"
            ),
            {"id": item_id, "tenant_id": tenant_id, "owner": owner},
        )
        funded = conn.execute(
            text("SELECT funded FROM reward_item WHERE id = :id"), {"id": item_id}
        ).scalar_one()

    assert funded is False, (
        "an item written without saying who is paying for it must not arrive listable"
    )


def test_reward_item_rejects_a_budget_owner_from_another_tenant(
    engine: Engine, tenant_id, other_tenant_id
) -> None:
    """The case the composite foreign key exists for, and the only one that proves it.

    ``test_reward_item_budget_owner_must_be_a_real_account_in_the_same_tenant``
    passes an id belonging to nobody, which a single-column key to
    ``user_account (id)`` would refuse just as firmly. This passes a **real**
    account that exists and is in good standing — in the wrong tenant. A
    single-column key accepts it; the composite key
    ``(tenant_id, budget_owner_id) -> user_account (tenant_id, id)`` does not.
    Without this assertion, narrowing the key back to one column would break
    D6's "named human budget owner" and no test would notice.
    """
    with engine.begin() as conn:
        stranger = _make_user(conn, other_tenant_id)

    with pytest.raises(IntegrityError), engine.begin() as conn:
        _insert_reward_item(conn, tenant_id, budget_owner_id=stranger)


def test_a_reward_cannot_be_stripped_of_its_owner_after_it_is_written(
    engine: Engine, tenant_id
) -> None:
    """``NOT NULL`` governs the UPDATE too, which is where the pressure would come from.

    A row is written correctly, once, under review. The realistic regression is
    later: an "unassign the owner" or "clear the budget while we sort it out"
    write against a row that is already listed. Both must fail at the database,
    for the same reason the insert does — the alternative is an unowned reward
    that was legitimate when it was created.
    """
    with engine.begin() as conn:
        item_id = _insert_reward_item(conn, tenant_id, funded=True)

    for column in ("budget_owner_id", "funded"):
        with (
            pytest.raises(IntegrityError, match=r"(?i)null value|not-null|" + column),
            engine.begin() as conn,
        ):
            conn.execute(
                text(f"UPDATE reward_item SET {column} = NULL WHERE id = :id"), {"id": item_id}
            )


def test_the_budget_owner_cannot_be_deleted_out_from_under_a_reward(
    engine: Engine, tenant_id
) -> None:
    """``ON DELETE RESTRICT``: the named owner cannot vanish and leave the reward listed.

    A cascade here would delete the reward, and a ``SET NULL`` would produce the
    unowned row the schema exists to refuse. Restricting makes removing the
    person a decision someone has to take about the rewards they own, which is
    what "named human budget owner" means once the name belongs to a real
    account rather than to a document.
    """
    with engine.begin() as conn:
        owner = _make_user(conn, tenant_id)
        _insert_reward_item(conn, tenant_id, budget_owner_id=owner)

    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text("DELETE FROM user_account WHERE id = :id"), {"id": owner})


# ---------------------------------------------------------------------------
# point_ledger_entry — append-only, as far as it is guaranteed today
# ---------------------------------------------------------------------------


def test_the_ledger_carries_no_column_an_application_could_legitimately_update(
    engine: Engine,
) -> None:
    """Migration ``0009``'s claim that append-only is "enforced by what is absent".

    The argument is that there is nothing on this table an application could
    honestly ``UPDATE``: no ``status`` to advance, no ``updated_at`` to touch,
    no ``version`` to bump, and — Fix #9 — no ``balance`` anywhere, because a
    balance is a fold over the ledger and never a stored value. That argument
    is only as good as the column list, and a later migration adding one of
    these would silently retract it, so the column set is asserted exactly
    rather than checked for the absences alone.
    """
    with engine.begin() as conn:
        columns = {
            row.column_name
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'point_ledger_entry'"
                )
            )
        }

    assert columns == {
        "id",
        "tenant_id",
        "amount",
        "source_attendance_id",
        "reason",
        "actor_id",
        "occurred_at",
    }, "a column added here is an invitation to the mutation its absence forecloses"


def test_a_correction_is_a_second_entry_and_leaves_the_first_one_standing(
    engine: Engine, tenant_id
) -> None:
    """ADR-0013: "A reversal is a compensating entry, never a delete."

    The positive statement of append-only, asserted as the history it produces:
    after correcting a credit, the ledger holds **two** rows, the original is
    unchanged, and the balance — folded, never stored — is what the pair sums
    to. A destructive correction would give the same balance and a history that
    could not explain it.
    """
    with engine.begin() as conn:
        attendance = _insert_attendance(conn, tenant_id)
        _insert_ledger_entry(conn, tenant_id, attendance, 100)
        _insert_ledger_entry(conn, tenant_id, attendance, -100)

        rows = conn.execute(
            text(
                "SELECT amount FROM point_ledger_entry WHERE tenant_id = :tid "
                "ORDER BY occurred_at, amount"
            ),
            {"tid": tenant_id},
        ).all()
        balance = conn.execute(
            text("SELECT COALESCE(SUM(amount), 0) FROM point_ledger_entry WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        ).scalar_one()

    assert [row.amount for row in rows] == [-100, 100], "both entries survive the correction"
    assert balance == 0, "the balance is the fold, and the fold is over what is still there"


def test_the_attendance_a_ledger_entry_derives_from_cannot_be_deleted(
    engine: Engine, tenant_id
) -> None:
    """``ON DELETE RESTRICT`` on the source, which is what keeps the derivation checkable.

    ADR-0013 allows points to derive from recorded attendance and nothing else.
    If the attendance row could be deleted, that rule would become unverifiable
    for exactly the entries it was written to protect — the ledger would still
    say 100 points and nothing would say why.
    """
    with engine.begin() as conn:
        attendance = _insert_attendance(conn, tenant_id)
        _insert_ledger_entry(conn, tenant_id, attendance, 100)

    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text("DELETE FROM attendance_record WHERE id = :id"), {"id": attendance})


def test_the_ledger_has_no_database_level_append_only_guard_yet(engine: Engine) -> None:
    """The gap, asserted rather than assumed — and deliberately not closed here.

    Append-only on ``point_ledger_entry`` is structural (the test above) and
    conventional (ADR-0013), and it is **not** enforced by the database: no
    trigger and no rule refuses an ``UPDATE`` or a ``DELETE`` on this table
    today. Migration ``0009`` records that as a non-blocking note and
    ``docs/plans/2026-08-28-d6-rewards-s8-s9-plan.md`` card **L2** owns the fix,
    which is gated and not authorized by the D6 pilot-scope record — that record
    says a missing guard is to be *reported*, not added. This test is the
    report, in the only form that cannot go stale unnoticed.

    **When L2 lands, this test fails**, and that is the intended behaviour: it
    is the signal to replace it with the assertions that the guard refuses an
    UPDATE and a DELETE. Card R3 may not ship a route over this table before
    then.
    """
    with engine.begin() as conn:
        guards = conn.execute(
            text(
                "SELECT t.tgname AS name FROM pg_trigger t "
                "JOIN pg_class c ON c.oid = t.tgrelid "
                "WHERE c.relname = 'point_ledger_entry' AND NOT t.tgisinternal "
                "UNION ALL "
                "SELECT rulename AS name FROM pg_rules WHERE tablename = 'point_ledger_entry'"
            )
        ).all()

    assert [row.name for row in guards] == [], (
        "a database-level append-only guard now exists on point_ledger_entry: "
        "replace this test with one asserting that it refuses an UPDATE and a "
        "DELETE (plan P7 card L2)"
    )
