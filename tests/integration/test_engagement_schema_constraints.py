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
