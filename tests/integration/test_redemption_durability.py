"""Migration ``0019``: the durable redemption, the representable debit, the guard.

The behavioural half of what `tests/integration/test_check_constraints.py`
declares. That file pins what each CHECK constraint *says*, read out of
``pg_get_constraintdef``; this one attempts the write each constraint exists to
refuse, **and** the write it must still permit — the second half being what
catches an inverted expression, which keeps its name and would otherwise stay
green.

It is a separate file for the reason ``test_engagement_schema_constraints.py``
and ``test_match_run_snapshot.py`` are: landing a table should not require
editing a file other tracks are touching concurrently.

Three things here are not CHECK constraints, and so are not in that registry at
all:

* ``uq_point_ledger_entry_attendance_credit``, the partial unique index that
  makes earning idempotent for every writer rather than only for callers of one
  repository method;
* ``uq_redemption_open_per_item``, the partial unique index behind card L4's
  "concurrent duplicate requests resolve to one redemption";
* the composite ``RESTRICT`` foreign keys, which are what keep a debit's
  redemption and a ticket's reward item from disappearing underneath them.

The ``BEFORE UPDATE`` trigger that makes ``point_ledger_entry`` append-only
(card **L2**) is exercised in ``test_engagement_schema_constraints.py``
instead, where that table's other append-only claims already live and where the
test asserting the guard's *absence* had to be replaced.

And one thing is none of the above:
``test_the_migration_round_trips_from_an_empty_database`` runs ``0019`` up and
back down as a subprocess against a scratch database, the way an operator
would, because a downgrade that has never been run is a downgrade nobody knows
the state of.

Requires a live database, and is skipped when none is reachable (``engine``
fixture, ``tests/integration/conftest.py``).

Teardown, and why it is this shape. Every foreign key ``0009`` and ``0019``
declare is ``RESTRICT``, so a row this file leaves behind makes ``conftest``'s
own ``tenant_id`` teardown fail on the ``user_account`` it still references.
``_clean_redemption_tables`` depends on ``tenant_id``, which makes pytest tear
it down *first*, and deletes child before parent — ``point_ledger_entry``,
then ``redemption``, then ``attendance_record`` and ``reward_item``. That is
the ordering ``test_engagement_schema_constraints.py`` establishes, extended by
the one table this migration adds. ``redemption`` is deliberately **not** added
to ``conftest``'s ``_TENANT_SCOPED_TABLES``: ``attendance_record`` is already
absent from that tuple for the stated reason that the modules which write it
delete it in their own fixtures, and adding ``redemption`` there alone would
fail in any case, since a redemption debit references it under ``RESTRICT`` and
``point_ledger_entry`` is not in the tuple either.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest

pytest.importorskip("sqlalchemy")

from conftest import ensure_event, ensure_owning_unit, unique_subject
from migration_harness import alembic, applied_revision, connected, scratch_database
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration

#: The revision immediately before this one. Named once so the round-trip test
#: downgrades to a revision that exists rather than to a literal repeated at
#: three call sites.
REVISION_BEFORE = "0018_match_run_snapshot"

#: This migration's own revision id, for the same reason.
REVISION = "0019_redemption_durability"


@pytest.fixture(autouse=True)
def _clean_redemption_tables(engine: Engine, tenant_id: uuid.UUID) -> Iterator[None]:
    """Delete this file's rows before ``tenant_id`` tears its own down."""
    yield
    with engine.begin() as conn:
        for table in ("point_ledger_entry", "redemption", "attendance_record", "reward_item"):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})


# ---------------------------------------------------------------------------
# Row builders. Synthetic fixtures written by this test, not seeded data: D6
# gates a shipped catalog, and the point costs below are D7's *tentative*
# recorded bands rather than invented numbers.
# ---------------------------------------------------------------------------

#: The cheapest of D7's recorded bands. Used wherever a test needs a cost and
#: does not care which one, so no figure in this file is one nobody wrote down.
D7_CHEAPEST_BAND = 300


def _make_user(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    """A ``user_account`` row: a student, a budget owner, or a coordinator."""
    user_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :tenant_id, :sub, :email)"
        ),
        {
            "id": user_id,
            "tenant_id": tenant_id,
            "sub": unique_subject(f"redemption-{user_id.hex[:8]}"),
            "email": f"{user_id.hex[:8]}@example.edu",
        },
    )
    return user_id


def _insert_reward_item(
    conn, tenant_id: uuid.UUID, *, points_cost: int = D7_CHEAPEST_BAND
) -> uuid.UUID:
    """A funded, owned ``reward_item`` row — the only kind ``0009`` permits."""
    item_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO reward_item "
            "(id, tenant_id, name, points_cost, fulfilment_cost, budget_owner_id, funded) "
            "VALUES (:id, :tenant_id, :name, :cost, 0, :owner, true)"
        ),
        {
            "id": item_id,
            "tenant_id": tenant_id,
            "name": f"synthetic reward {item_id.hex[:8]}",
            "cost": points_cost,
            "owner": _make_user(conn, tenant_id),
        },
    )
    return item_id


def _insert_attendance(
    conn, tenant_id: uuid.UUID, *, subject_id: uuid.UUID | None = None
) -> uuid.UUID:
    """One verified attendance, at its own synthetic event."""
    record_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO attendance_record "
            "(id, tenant_id, owning_unit_id, subject_id, event_id, method) "
            "VALUES (:id, :tenant_id, :unit_id, :subject_id, :event_id, 'coordinator_entry')"
        ),
        {
            "id": record_id,
            "tenant_id": tenant_id,
            "unit_id": ensure_owning_unit(conn, tenant_id),
            "subject_id": subject_id or _make_user(conn, tenant_id),
            "event_id": ensure_event(conn, tenant_id, slug=record_id.hex[:8]),
        },
    )
    return record_id


def _insert_redemption(
    conn,
    tenant_id: uuid.UUID,
    *,
    state: str = "requested",
    subject_id: uuid.UUID | None = None,
    item_id: uuid.UUID | None = None,
    item_name: str = "synthetic reward",
    points_cost: int = D7_CHEAPEST_BAND,
    approved: bool = False,
    approved_author: object = "__auto__",
    closed: bool = False,
    closed_author: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert a ``redemption`` row and return its id.

    The evidence columns are driven by flags rather than by raw timestamps so a
    test says *what shape it is writing* — "approved with no author", "terminal
    with no close time" — instead of assembling one out of four nullable
    values. ``approved_author`` takes a sentinel default so an explicit
    ``None`` can mean "write a time with no author", which is the exact case
    ``ck_redemption_approval_evidence`` is about.
    """
    redemption_id = uuid.uuid4()
    author = _make_user(conn, tenant_id) if approved_author == "__auto__" else approved_author
    conn.execute(
        text(
            "INSERT INTO redemption "
            "(id, tenant_id, subject_id, item_id, item_name_snapshot, points_cost_snapshot, "
            " state, approved_at, approved_by, closed_at, closed_by) "
            "VALUES (:id, :tenant_id, :subject_id, :item_id, :name, :cost, :state, "
            " CASE WHEN :approved THEN now() ELSE NULL END, :author, "
            " CASE WHEN :closed THEN now() ELSE NULL END, :closer)"
        ),
        {
            "id": redemption_id,
            "tenant_id": tenant_id,
            "subject_id": subject_id or _make_user(conn, tenant_id),
            "item_id": item_id or _insert_reward_item(conn, tenant_id),
            "name": item_name,
            "cost": points_cost,
            "state": state,
            "approved": approved,
            "author": author,
            "closed": closed,
            "closer": closed_author,
        },
    )
    return redemption_id


def _insert_ledger_entry(
    conn,
    tenant_id: uuid.UUID,
    *,
    kind: str,
    amount: int,
    source_attendance_id: uuid.UUID | None = None,
    source_redemption_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """One ``point_ledger_entry`` row of the named kind, with the sources given.

    Nothing is derived here — the caller states the kind and both sources
    independently, which is what lets a test write the disagreeing combinations
    ``ck_point_ledger_entry_kind`` exists to refuse.
    """
    entry_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO point_ledger_entry "
            "(id, tenant_id, kind, amount, source_attendance_id, source_redemption_id, reason) "
            "VALUES (:id, :tenant_id, :kind, :amount, :attendance, :redemption, :reason)"
        ),
        {
            "id": entry_id,
            "tenant_id": tenant_id,
            "kind": kind,
            "amount": amount,
            "attendance": source_attendance_id,
            "redemption": source_redemption_id,
            "reason": "synthetic fixture",
        },
    )
    return entry_id


# ---------------------------------------------------------------------------
# ck_redemption_state
# ---------------------------------------------------------------------------


def test_redemption_rejects_a_state_outside_the_vocabulary(engine: Engine, tenant_id) -> None:
    """ADR-0013 names five states; ``cancelled`` is not one of them.

    A sixth state would be a way for a redemption to end that no rule in
    ADR-0013 describes, and — since the two evidence constraints are written
    against the five names — one whose audit trail would go unchecked.
    """
    with (
        pytest.raises(IntegrityError, match="ck_redemption_state"),
        engine.begin() as conn,
    ):
        # Written with no evidence at all, so the two evidence constraints are
        # both satisfied and the vocabulary is the only thing left to refuse
        # it. PostgreSQL evaluates a table's CHECK constraints in name order,
        # so a row that also violated ck_redemption_closure_evidence would
        # report that one instead and this test would pass for the wrong
        # reason.
        _insert_redemption(conn, tenant_id, state="cancelled", approved_author=None)


@pytest.mark.parametrize(
    ("state", "approved", "closed"),
    [
        ("requested", False, False),
        ("approved", True, False),
        ("fulfilled", True, True),
        ("denied", False, True),
        ("expired", False, True),
    ],
)
def test_redemption_accepts_every_state_in_the_vocabulary(
    engine: Engine, tenant_id, state: str, approved: bool, closed: bool
) -> None:
    """All five, each with the evidence its state requires.

    The permitted half, which is what catches an inverted vocabulary: a
    constraint listing the states it *refuses* would still reject ``cancelled``
    above and would fail here on every row.
    """
    with engine.begin() as conn:
        _insert_redemption(
            conn,
            tenant_id,
            state=state,
            approved=approved,
            approved_author="__auto__" if approved else None,
            closed=closed,
        )


# ---------------------------------------------------------------------------
# ck_redemption_approval_evidence — including "fulfilled only from approved"
# ---------------------------------------------------------------------------


def test_an_approval_with_no_author_is_refused(engine: Engine, tenant_id) -> None:
    """An approval nobody signed is not an approval; it is a state change."""
    with (
        pytest.raises(IntegrityError, match="ck_redemption_approval_evidence"),
        engine.begin() as conn,
    ):
        _insert_redemption(conn, tenant_id, state="approved", approved=True, approved_author=None)


def test_an_author_with_no_approval_time_is_refused(engine: Engine, tenant_id) -> None:
    """The other half of the pair: a signature with no date is not a record."""
    with (
        pytest.raises(IntegrityError, match="ck_redemption_approval_evidence"),
        engine.begin() as conn,
    ):
        _insert_redemption(conn, tenant_id, state="requested", approved=False)


def test_a_fulfilled_redemption_with_no_approval_behind_it_is_refused(
    engine: Engine, tenant_id
) -> None:
    """ "Fulfilled is reachable only from approved", as a property of the row.

    The domain state machine already refuses ``requested -> fulfilled``, and
    ADR-0013's reason is that redemption "is a command with an approval step",
    so a request that lands fulfilled is that step deleted rather than passed.
    This is the same rule where a hand-written INSERT can reach it.
    """
    with (
        pytest.raises(IntegrityError, match="ck_redemption_approval_evidence"),
        engine.begin() as conn,
    ):
        _insert_redemption(
            conn,
            tenant_id,
            state="fulfilled",
            approved=False,
            approved_author=None,
            closed=True,
        )


def test_a_requested_redemption_cannot_already_carry_an_approval(engine: Engine, tenant_id) -> None:
    """An approval recorded and then walked back to ``requested`` is refused.

    Without this clause the evidence could outlive the state it evidences, and
    a row would be simultaneously awaiting approval and already approved.
    """
    with (
        pytest.raises(IntegrityError, match="ck_redemption_approval_evidence"),
        engine.begin() as conn,
    ):
        _insert_redemption(conn, tenant_id, state="requested", approved=True)


def test_a_requested_redemption_cannot_be_updated_straight_to_fulfilled(
    engine: Engine, tenant_id
) -> None:
    """The UPDATE case, which is the one that matters.

    ``redemption`` is deliberately mutable — its purpose is to move through
    states — so unlike ``point_ledger_entry`` there is no trigger forbidding an
    ``UPDATE``. What stops a statement skipping the approval step is that a
    CHECK constraint is evaluated on an UPDATE exactly as on an INSERT, and
    this row has no approval to satisfy it with.
    """
    with engine.begin() as conn:
        redemption_id = _insert_redemption(conn, tenant_id, state="requested", approved_author=None)

    with (
        pytest.raises(IntegrityError, match="ck_redemption_approval_evidence"),
        engine.begin() as conn,
    ):
        conn.execute(
            text("UPDATE redemption SET state = 'fulfilled', closed_at = now() WHERE id = :id"),
            {"id": redemption_id},
        )

    with engine.begin() as conn:
        unchanged = conn.execute(
            text("SELECT state FROM redemption WHERE id = :id"), {"id": redemption_id}
        ).scalar_one()
    assert unchanged == "requested"


def test_an_approved_redemption_moves_to_fulfilled(engine: Engine, tenant_id) -> None:
    """The permitted path, which is what catches an inverted constraint.

    A constraint that refused fulfilment *because* an approval was present
    would pass every refusal test above and fail here.
    """
    with engine.begin() as conn:
        redemption_id = _insert_redemption(conn, tenant_id, state="approved", approved=True)
        coordinator = _make_user(conn, tenant_id)

    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE redemption SET state = 'fulfilled', closed_at = now(), "
                "closed_by = :author WHERE id = :id"
            ),
            {"id": redemption_id, "author": coordinator},
        )
        state = conn.execute(
            text("SELECT state FROM redemption WHERE id = :id"), {"id": redemption_id}
        ).scalar_one()
    assert state == "fulfilled"


# ---------------------------------------------------------------------------
# ck_redemption_closure_evidence
# ---------------------------------------------------------------------------


def test_a_terminal_redemption_must_record_when_it_closed(engine: Engine, tenant_id) -> None:
    """A denial with no time is a decision nobody can place in the record."""
    with (
        pytest.raises(IntegrityError, match="ck_redemption_closure_evidence"),
        engine.begin() as conn,
    ):
        _insert_redemption(conn, tenant_id, state="denied", approved_author=None, closed=False)


def test_a_live_redemption_cannot_record_a_close_time(engine: Engine, tenant_id) -> None:
    """The converse: a row still in flight has not closed, whatever it says."""
    with (
        pytest.raises(IntegrityError, match="ck_redemption_closure_evidence"),
        engine.begin() as conn,
    ):
        _insert_redemption(conn, tenant_id, state="requested", approved_author=None, closed=True)


def test_a_closing_author_with_no_close_time_is_refused(engine: Engine, tenant_id) -> None:
    """An author without the act is the same defect ``redrive_record`` refuses."""
    with engine.begin() as setup:
        coordinator = _make_user(setup, tenant_id)

    with (
        pytest.raises(IntegrityError, match="ck_redemption_closure_evidence"),
        engine.begin() as conn,
    ):
        _insert_redemption(
            conn,
            tenant_id,
            state="requested",
            approved_author=None,
            closed=False,
            closed_author=coordinator,
        )


def test_an_expiry_closes_with_no_author(engine: Engine, tenant_id) -> None:
    """``closed_by`` is nullable on a closed row, and this is why.

    ``approved`` and ``denied`` are things a coordinator does; ``expired`` is
    something time does. Requiring an author here would name a human for a row
    no human touched.
    """
    with engine.begin() as conn:
        _insert_redemption(
            conn,
            tenant_id,
            state="expired",
            approved_author=None,
            closed=True,
            closed_author=None,
        )


# ---------------------------------------------------------------------------
# ck_redemption_snapshot_present
# ---------------------------------------------------------------------------


def test_a_redemption_cannot_snapshot_a_free_reward(engine: Engine, tenant_id) -> None:
    """A zero cost would be a reward redeemed for nothing, recorded as a price."""
    with (
        pytest.raises(IntegrityError, match="ck_redemption_snapshot_present"),
        engine.begin() as conn,
    ):
        _insert_redemption(conn, tenant_id, points_cost=0, approved_author=None)


def test_a_redemption_cannot_snapshot_a_nameless_reward(engine: Engine, tenant_id) -> None:
    """D7: a deactivated reward "stays visible on existing tickets".

    A ticket whose name is whitespace is visible and says nothing, which
    satisfies ``NOT NULL`` and defeats the point.
    """
    with (
        pytest.raises(IntegrityError, match="ck_redemption_snapshot_present"),
        engine.begin() as conn,
    ):
        _insert_redemption(conn, tenant_id, item_name="   ", approved_author=None)


def test_a_redemption_accepts_the_calibrated_cheapest_band(engine: Engine, tenant_id) -> None:
    """The permitted write: D7's cheapest recorded band, and a real name."""
    with engine.begin() as conn:
        _insert_redemption(
            conn,
            tenant_id,
            points_cost=D7_CHEAPEST_BAND,
            item_name="Tote bag",
            approved_author=None,
        )


# ---------------------------------------------------------------------------
# ck_point_ledger_entry_kind — the constraint that keeps the new nullability
# from being a hole
# ---------------------------------------------------------------------------


def test_a_ledger_entry_naming_neither_source_is_refused(engine: Engine, tenant_id) -> None:
    """The row the nullability would otherwise admit.

    Before ``0019`` this was impossible because ``source_attendance_id`` was
    ``NOT NULL``. Making it nullable so a redemption debit could exist is
    exactly what would let an entry deriving from *nothing* be written — the
    discretionary grant ADR-0013 refuses — and this constraint is what closes
    that instead.
    """
    with (
        pytest.raises(IntegrityError, match="ck_point_ledger_entry_kind"),
        engine.begin() as conn,
    ):
        _insert_ledger_entry(conn, tenant_id, kind="attendance_credit", amount=100)


def test_a_ledger_entry_naming_both_sources_is_refused(engine: Engine, tenant_id) -> None:
    """An entry that derives from two things derives from neither, checkably."""
    with (
        pytest.raises(IntegrityError, match="ck_point_ledger_entry_kind"),
        engine.begin() as conn,
    ):
        _insert_ledger_entry(
            conn,
            tenant_id,
            kind="redemption_debit",
            amount=-D7_CHEAPEST_BAND,
            source_attendance_id=_insert_attendance(conn, tenant_id),
            source_redemption_id=_insert_redemption(conn, tenant_id, approved_author=None),
        )


def test_a_debit_naming_an_attendance_instead_of_a_redemption_is_refused(
    engine: Engine, tenant_id
) -> None:
    """The workaround this migration exists to make unnecessary, refused.

    Borrowing an unrelated attendance id to satisfy a ``NOT NULL`` was the only
    way to write a debit before ``0019``. It is now not merely unnecessary but
    impossible, which is the difference between a convention and a guarantee.
    """
    with (
        pytest.raises(IntegrityError, match="ck_point_ledger_entry_kind"),
        engine.begin() as conn,
    ):
        _insert_ledger_entry(
            conn,
            tenant_id,
            kind="redemption_debit",
            amount=-D7_CHEAPEST_BAND,
            source_attendance_id=_insert_attendance(conn, tenant_id),
        )


def test_a_credit_deriving_from_a_redemption_is_refused(engine: Engine, tenant_id) -> None:
    """Redeeming must not be a way to earn: no kind pairs a redemption with a credit."""
    with (
        pytest.raises(IntegrityError, match="ck_point_ledger_entry_kind"),
        engine.begin() as conn,
    ):
        _insert_ledger_entry(
            conn,
            tenant_id,
            kind="attendance_credit",
            amount=100,
            source_redemption_id=_insert_redemption(conn, tenant_id, approved_author=None),
        )


@pytest.mark.parametrize(
    ("kind", "amount"),
    [
        ("attendance_credit", -100),
        ("reversal", 100),
        ("redemption_debit", D7_CHEAPEST_BAND),
    ],
)
def test_a_ledger_entry_with_the_wrong_sign_for_its_kind_is_refused(
    engine: Engine, tenant_id, kind: str, amount: int
) -> None:
    """Each kind pins its own sign, so a debit cannot arrive as a credit.

    One case per kind rather than one case overall: a constraint weakened on
    two of the three disjuncts would still refuse whichever single case a
    narrower test happened to try.
    """
    with (
        pytest.raises(IntegrityError, match="ck_point_ledger_entry_kind"),
        engine.begin() as conn,
    ):
        source = (
            {"source_redemption_id": _insert_redemption(conn, tenant_id, approved_author=None)}
            if kind == "redemption_debit"
            else {"source_attendance_id": _insert_attendance(conn, tenant_id)}
        )
        _insert_ledger_entry(conn, tenant_id, kind=kind, amount=amount, **source)


def test_an_unknown_ledger_kind_is_refused(engine: Engine, tenant_id) -> None:
    """The disjunction is the vocabulary: a fourth kind satisfies none of it."""
    with (
        pytest.raises(IntegrityError, match="ck_point_ledger_entry_kind"),
        engine.begin() as conn,
    ):
        _insert_ledger_entry(
            conn,
            tenant_id,
            kind="discretionary_grant",
            amount=100,
            source_attendance_id=_insert_attendance(conn, tenant_id),
        )


def test_all_three_ledger_kinds_are_writable(engine: Engine, tenant_id) -> None:
    """The permitted half, and the proof that the debit is now representable.

    All three in one transaction, against one student: the credit that earned
    the points, the reversal shape, and the debit that spends them. The last of
    those had no row shape at all before this migration —
    ``smartmatch_persistence.rewards.redemption_debit_is_representable`` states
    the same fact against the schema definition.
    """
    with engine.begin() as conn:
        subject = _make_user(conn, tenant_id)
        earned = _insert_attendance(conn, tenant_id, subject_id=subject)
        corrected = _insert_attendance(conn, tenant_id, subject_id=subject)
        redemption_id = _insert_redemption(
            conn, tenant_id, subject_id=subject, approved_author=None
        )

        _insert_ledger_entry(
            conn, tenant_id, kind="attendance_credit", amount=100, source_attendance_id=earned
        )
        _insert_ledger_entry(
            conn, tenant_id, kind="reversal", amount=-100, source_attendance_id=corrected
        )
        _insert_ledger_entry(
            conn,
            tenant_id,
            kind="redemption_debit",
            amount=-D7_CHEAPEST_BAND,
            source_redemption_id=redemption_id,
        )

        kinds = conn.execute(
            text("SELECT kind FROM point_ledger_entry WHERE tenant_id = :tid ORDER BY kind"),
            {"tid": tenant_id},
        ).scalars()
    assert list(kinds) == ["attendance_credit", "redemption_debit", "reversal"]


# ---------------------------------------------------------------------------
# uq_point_ledger_entry_attendance_credit — earning idempotency, as a constraint
# ---------------------------------------------------------------------------


def test_one_attendance_cannot_be_credited_twice(engine: Engine, tenant_id) -> None:
    """The double-credit case, refused by the database rather than by a row lock.

    A second credit for the same attendance is an unearned second credit —
    ADR-0013's "points derive from recorded attendance and nothing else" makes
    the evidence the whole basis, so crediting one piece of evidence twice
    invents points. Before ``0019`` this was closed only for callers who came
    through ``RewardsRepository.credit_attendance``.
    """
    with engine.begin() as conn:
        attendance = _insert_attendance(conn, tenant_id)
        _insert_ledger_entry(
            conn, tenant_id, kind="attendance_credit", amount=100, source_attendance_id=attendance
        )

    with (
        pytest.raises(IntegrityError, match="uq_point_ledger_entry_attendance_credit"),
        engine.begin() as conn,
    ):
        _insert_ledger_entry(
            conn, tenant_id, kind="attendance_credit", amount=100, source_attendance_id=attendance
        )


def test_a_reversal_may_share_a_source_with_the_credit_it_withdraws(
    engine: Engine, tenant_id
) -> None:
    """Why the index is partial, and not a plain unique constraint.

    ADR-0013 anticipates several entries deriving from one attendance as the
    earn policy is revised, and a compensating entry is the first of them. A
    unique constraint over ``(tenant_id, source_attendance_id)`` would forbid
    the correction the ADR requires.
    """
    with engine.begin() as conn:
        attendance = _insert_attendance(conn, tenant_id)
        _insert_ledger_entry(
            conn, tenant_id, kind="attendance_credit", amount=100, source_attendance_id=attendance
        )
        _insert_ledger_entry(
            conn, tenant_id, kind="reversal", amount=-100, source_attendance_id=attendance
        )
        _insert_ledger_entry(
            conn, tenant_id, kind="reversal", amount=-1, source_attendance_id=attendance
        )

        total = conn.execute(
            text("SELECT count(*) FROM point_ledger_entry WHERE source_attendance_id = :src"),
            {"src": attendance},
        ).scalar_one()
    assert total == 3


def test_two_attendances_are_credited_independently(engine: Engine, tenant_id) -> None:
    """The index is scoped to one attendance, not to a student or a tenant."""
    with engine.begin() as conn:
        subject = _make_user(conn, tenant_id)
        for _ in range(2):
            attendance = _insert_attendance(conn, tenant_id, subject_id=subject)
            _insert_ledger_entry(
                conn,
                tenant_id,
                kind="attendance_credit",
                amount=100,
                source_attendance_id=attendance,
            )

        balance = conn.execute(
            text("SELECT COALESCE(SUM(amount), 0) FROM point_ledger_entry WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        ).scalar_one()
    assert balance == 200


# ---------------------------------------------------------------------------
# uq_redemption_open_per_item — one request in flight at a time
# ---------------------------------------------------------------------------


def test_a_student_cannot_hold_two_open_requests_for_one_reward(engine: Engine, tenant_id) -> None:
    """Card L4: "concurrent duplicate requests resolve to one redemption".

    Two tickets for one reward would each carry the student's expectation of
    receiving it, and only one of them could be honoured.
    """
    with engine.begin() as conn:
        subject = _make_user(conn, tenant_id)
        item = _insert_reward_item(conn, tenant_id)
        _insert_redemption(conn, tenant_id, subject_id=subject, item_id=item, approved_author=None)

    with (
        pytest.raises(IntegrityError, match="uq_redemption_open_per_item"),
        engine.begin() as conn,
    ):
        _insert_redemption(conn, tenant_id, subject_id=subject, item_id=item, approved_author=None)


def test_an_approved_request_also_blocks_a_second_one(engine: Engine, tenant_id) -> None:
    """``approved`` is in flight too — the reward has not been handed over yet."""
    with engine.begin() as conn:
        subject = _make_user(conn, tenant_id)
        item = _insert_reward_item(conn, tenant_id)
        _insert_redemption(
            conn, tenant_id, state="approved", approved=True, subject_id=subject, item_id=item
        )

    with (
        pytest.raises(IntegrityError, match="uq_redemption_open_per_item"),
        engine.begin() as conn,
    ):
        _insert_redemption(conn, tenant_id, subject_id=subject, item_id=item, approved_author=None)


@pytest.mark.parametrize("terminal", ["fulfilled", "denied", "expired"])
def test_a_finished_redemption_never_blocks_a_later_one(
    engine: Engine, tenant_id, terminal: str
) -> None:
    """Why the index is partial, on this side too.

    A reward received in October is not a reason to refuse the same reward in
    March, and a denial is not a life sentence. A unique constraint over the
    whole table would say both.
    """
    with engine.begin() as conn:
        subject = _make_user(conn, tenant_id)
        item = _insert_reward_item(conn, tenant_id)
        approved = terminal == "fulfilled"
        _insert_redemption(
            conn,
            tenant_id,
            state=terminal,
            subject_id=subject,
            item_id=item,
            approved=approved,
            approved_author="__auto__" if approved else None,
            closed=True,
        )
        _insert_redemption(conn, tenant_id, subject_id=subject, item_id=item, approved_author=None)

        total = conn.execute(
            text("SELECT count(*) FROM redemption WHERE subject_id = :sub AND item_id = :item"),
            {"sub": subject, "item": item},
        ).scalar_one()
    assert total == 2


# ---------------------------------------------------------------------------
# The RESTRICT references
# ---------------------------------------------------------------------------


def test_the_redemption_a_debit_names_cannot_be_deleted(engine: Engine, tenant_id) -> None:
    """A debit whose redemption vanished would be points spent on nothing.

    The same guarantee ``0009`` gives the credit side: the evidence a ledger
    entry cites must outlive the entry citing it, or the derivation rule stops
    being checkable for exactly the rows it protects.
    """
    with engine.begin() as conn:
        redemption_id = _insert_redemption(conn, tenant_id, approved_author=None)
        _insert_ledger_entry(
            conn,
            tenant_id,
            kind="redemption_debit",
            amount=-D7_CHEAPEST_BAND,
            source_redemption_id=redemption_id,
        )

    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text("DELETE FROM redemption WHERE id = :id"), {"id": redemption_id})


def test_a_reward_item_cannot_be_deleted_while_a_redemption_cites_it(
    engine: Engine, tenant_id
) -> None:
    """D7: a deactivated reward "stays visible on existing tickets".

    Deactivation is not deletion, and the ticket's snapshot is what keeps it
    readable; this is the constraint that stops the row itself disappearing
    underneath the ticket.
    """
    with engine.begin() as conn:
        item = _insert_reward_item(conn, tenant_id)
        _insert_redemption(conn, tenant_id, item_id=item, approved_author=None)

    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text("DELETE FROM reward_item WHERE id = :id"), {"id": item})


def test_a_redemption_cannot_name_a_reward_that_does_not_exist(engine: Engine, tenant_id) -> None:
    """The composite foreign key, doing what a single-column one would not.

    ``(tenant_id, item_id)`` against ``uq_reward_item_tenant_id`` — a bare
    pointer at ``reward_item.id`` would accept an item belonging to another
    institution, which is a cross-tenant read in the one table that decides
    what a student is owed.
    """
    with pytest.raises(IntegrityError), engine.begin() as conn:
        _insert_redemption(conn, tenant_id, item_id=uuid.uuid4(), approved_author=None)


# ---------------------------------------------------------------------------
# The migration itself
# ---------------------------------------------------------------------------


def test_the_migration_round_trips_from_an_empty_database(engine: Engine) -> None:
    """``upgrade`` and ``downgrade`` both run, as a subprocess, from empty.

    A downgrade that has never been executed is a downgrade nobody knows the
    state of — ``0019`` drops a trigger, a function, two indexes, a constraint,
    two columns, a table and a unique constraint, and restores a ``NOT NULL``,
    and any one of those naming something that is not there fails only when
    someone runs it. This runs it.

    The upgrade is repeated afterwards so the revision left applied is the one
    the rest of this suite expects, and so a downgrade that left a stray object
    behind fails here rather than in whichever test ran next.
    """
    with scratch_database(engine) as url:
        alembic(url, REVISION, expect_success=True)
        assert applied_revision(url) == REVISION

        with connected(url) as scratch, scratch.connect() as conn:
            assert conn.execute(
                text("SELECT to_regclass('public.redemption') IS NOT NULL")
            ).scalar_one()

        alembic(url, REVISION_BEFORE, expect_success=True, command="downgrade")
        assert applied_revision(url) == REVISION_BEFORE

        with connected(url) as scratch, scratch.connect() as conn:
            assert conn.execute(
                text("SELECT to_regclass('public.redemption') IS NULL")
            ).scalar_one()
            # The trigger and its function go together: dropping the table
            # first would have taken the trigger and left the function holding
            # a name a later revision could not reuse without noticing.
            leftover = conn.execute(
                text(
                    "SELECT count(*) FROM pg_proc "
                    "WHERE proname = 'point_ledger_entry_reject_mutation'"
                )
            ).scalar_one()
            assert leftover == 0
            restored = conn.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'point_ledger_entry' "
                    "AND column_name = 'source_attendance_id'"
                )
            ).scalar_one()
            assert restored == "NO", "the downgrade restores the NOT NULL 0009 declared"

        alembic(url, REVISION, expect_success=True)
        assert applied_revision(url) == REVISION


def test_the_downgrade_refuses_to_discard_a_redemption_debit(engine: Engine) -> None:
    """The one case the downgrade will not resolve on its own.

    Restoring ``source_attendance_id NOT NULL`` over a redemption debit is
    impossible without deleting a ledger row — in a table whose whole design
    says corrections are appended and never removed — or inventing an
    attendance for it. So it refuses, names the count, and leaves the decision
    to a human. A downgrade that quietly deleted evidence would be worse than
    one that stops.
    """
    with scratch_database(engine) as url:
        alembic(url, "head", expect_success=True)

        with connected(url) as scratch, scratch.begin() as conn:
            tid = uuid.uuid4()
            conn.execute(
                text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
                {"id": tid, "slug": f"scratch-{tid.hex[:12]}"},
            )
            redemption_id = _insert_redemption(conn, tid, approved_author=None)
            _insert_ledger_entry(
                conn,
                tid,
                kind="redemption_debit",
                amount=-D7_CHEAPEST_BAND,
                source_redemption_id=redemption_id,
            )

        refusal = alembic(url, REVISION_BEFORE, expect_success=False, command="downgrade")
        assert "redemption debit" in refusal.stderr
        assert applied_revision(url) == REVISION, (
            "the refused downgrade did not record itself as applied"
        )
