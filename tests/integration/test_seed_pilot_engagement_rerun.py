"""``seed_pilot_engagement`` must be re-runnable — the Makefile's promise, pinned.

``make top-up-pilot-dataset`` tells the operator: "Run it twice and the second
run changes nothing." The dataset-verification run that prompted this file
proved that false on the redemption leg: a second run called
``open_redemption`` for every planned item, and ``open_redemption`` folds the
balance and lets ``request_redemption`` refuse an unaffordable cost *before*
its ``ON CONFLICT`` dedupe can return the in-flight row — so on an
already-seeded tenant the run crashed on the 1000-point step against the
post-fulfilment balance (900 < 1000) instead of recognising its own earlier
work. A step whose row had already closed terminal would have been worse:
``uq_redemption_open_per_item`` is partial and never blocks it, so a second
open mints a duplicate and a second debit.

These tests run the tool's real entry point — ``seed_engagement``, twice —
against a real tenant with enough events for the plan, and assert what the
Makefile asserts: the second run writes nothing. A variant pins the
terminal-state guard on its own: a redemption a person closed differently is
never reopened, never doubled.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from conftest import JOB_OWNING_UNIT_PATH, ensure_event, unique_subject
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[2]

# `tools/` on the path rather than the repository root — these modules are run
# by compose as bare siblings, the same shape the unit suite already imports
# them under.
sys.path.insert(0, str(REPO_ROOT / "tools"))

from seed_pilot_engagement import (  # noqa: E402
    REDEMPTION_PLAN,
    STUDENT_ATTENDANCES,
    STUDENT_CANCELLATIONS,
    STUDENT_REGISTRATIONS,
    EngagementReport,
    _seed_catalog,
    seed_engagement,
)
from smartmatch_persistence import schema  # noqa: E402

pytestmark = pytest.mark.integration

#: The ltree path `seed_engagement` resolves — conftest's shared unit, whose
#: `ensure_owning_unit`/`ensure_event` helpers already write under it.
UNIT_PATH = JOB_OWNING_UNIT_PATH


def _make_user(session: Session, tenant_id: uuid.UUID, subject: str) -> uuid.UUID:
    """A bare ``user_account`` the tool's ``_subject_id`` can resolve."""
    user_id = uuid.uuid4()
    session.execute(
        sa.insert(schema.user_account).values(
            id=user_id,
            tenant_id=tenant_id,
            external_subject=subject,
            email=f"{subject}@example.com",
        )
    )
    return user_id


def _tenant_slug(session: Session, tenant_id: uuid.UUID) -> str:
    """The slug the ``tenant_id`` fixture gave this run's tenant."""
    slug: str = session.execute(
        sa.select(schema.tenant.c.slug).where(schema.tenant.c.id == tenant_id)
    ).scalar_one()
    return slug


def _subject_id(session: Session, tenant_id: uuid.UUID, subject: str) -> uuid.UUID:
    """Resolve an ``external_subject`` to its ``user_account.id``."""
    user_id: uuid.UUID = session.execute(
        sa.select(schema.user_account.c.id).where(
            schema.user_account.c.tenant_id == tenant_id,
            schema.user_account.c.external_subject == subject,
        )
    ).scalar_one()
    return uuid.UUID(str(user_id))


@pytest.fixture
def seeded_tenant(engine: Engine, session_factory: sessionmaker[Session], tenant_id: uuid.UUID):
    """A tenant holding the minimum the engagement plan needs to run at all.

    ``STUDENT_ATTENDANCES + STUDENT_REGISTRATIONS + STUDENT_CANCELLATIONS``
    published, date-resolved events: one per attendance (the natural key
    forbids two on one event) and enough left over for the registration leg,
    whose candidates are drawn from the *published* non-attended pool. No
    speaker profiles: the host-request leg then takes its honest "nothing to
    file" note, which is also what keeps this test out of the §7/§8 vocabulary
    tables.
    """
    with session_factory() as session:
        ids = {
            "slug": _tenant_slug(session, tenant_id),
            "student": unique_subject("rerun-student"),
            "coordinator": unique_subject("rerun-coordinator"),
            "host": unique_subject("rerun-host"),
            "admin": unique_subject("rerun-admin"),
        }
        for key in ("student", "coordinator", "host", "admin"):
            _make_user(session, tenant_id, ids[key])
        event_ids = [
            ensure_event(session, tenant_id, slug=f"rerun-{index}")
            for index in range(STUDENT_ATTENDANCES + STUDENT_REGISTRATIONS + STUDENT_CANCELLATIONS)
        ]
        # Registrations are taken from the published pool; publishing the lot
        # keeps the leg's selection independent of which rows attendance took.
        session.execute(
            sa.update(schema.event)
            .where(
                schema.event.c.tenant_id == tenant_id,
                schema.event.c.id.in_(event_ids),
            )
            .values(publication_status="published")
        )
        session.commit()
    yield ids
    with engine.begin() as conn:
        # Deliberately absent from conftest's _TENANT_SCOPED_TABLES, for the
        # reasons test_redemption_durability gives: every writer of these
        # tables deletes what it wrote. Order honours the FK directions.
        for table in (
            "point_ledger_entry",
            "redemption",
            "event_registration",
            "cba_meeting",
            "attendance_record",
            "reward_item",
        ):
            conn.execute(
                text(f"DELETE FROM {table} WHERE tenant_id = :tenant_id"),
                {"tenant_id": tenant_id},
            )


def _run(
    session_factory: sessionmaker[Session], tenant_id: uuid.UUID, ids: dict
) -> EngagementReport:
    """One full ``seed_engagement`` run against the seeded tenant."""
    with session_factory() as session:
        report = seed_engagement(
            session,
            tenant_slug=ids["slug"],
            unit_path=UNIT_PATH,
            student_subject=ids["student"],
            coordinator_subject=ids["coordinator"],
            host_subject=ids["host"],
            budget_owner_subject=ids["admin"],
        )
        session.commit()
    return report


def _folded_balance(engine: Engine, tenant_id: uuid.UUID, subject: str) -> int:
    """``subject_id`` on a ledger entry's cause, folded — the repository's own rule."""
    with engine.begin() as conn:
        balance = conn.execute(
            text(
                """
                SELECT coalesce(sum(ple.amount), 0)
                FROM point_ledger_entry ple
                LEFT JOIN attendance_record ar ON ar.id = ple.source_attendance_id
                LEFT JOIN redemption rd ON rd.id = ple.source_redemption_id
                JOIN user_account ua ON ua.id = coalesce(ar.subject_id, rd.subject_id)
                WHERE ple.tenant_id = :tenant_id AND ua.external_subject = :subject
                """
            ),
            {"tenant_id": tenant_id, "subject": subject},
        ).scalar_one()
    return int(balance)


def _redemption_states(engine: Engine, tenant_id: uuid.UUID, subject: str) -> list[tuple[str, int]]:
    """Every redemption the student holds, as ``(state, points_cost)``."""
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT r.state, r.points_cost_snapshot
                FROM redemption r
                JOIN user_account ua ON ua.id = r.subject_id
                WHERE r.tenant_id = :tenant_id AND ua.external_subject = :subject
                ORDER BY r.points_cost_snapshot
                """
            ),
            {"tenant_id": tenant_id, "subject": subject},
        ).all()
    return [(str(row[0]), int(row[1])) for row in rows]


def test_a_second_full_run_writes_nothing(
    engine: Engine,
    session_factory: sessionmaker[Session],
    tenant_id: uuid.UUID,
    seeded_tenant,
) -> None:
    """The Makefile claim, end to end — and the redemption leg is the reason."""
    ids = seeded_tenant

    first = _run(session_factory, tenant_id, ids)
    assert first.redemptions_opened == len(REDEMPTION_PLAN)
    assert first.attendances == STUDENT_ATTENDANCES
    assert first.ledger_credits == STUDENT_ATTENDANCES

    # The state the reported bug tripped on: the plan's fulfilled debit landed,
    # so the folded balance no longer covers the 1000-point item it already
    # opened — the crash is in the second open, before the dedupe can answer.
    assert _folded_balance(engine, tenant_id, ids["student"]) == 900

    second = _run(session_factory, tenant_id, ids)

    assert second.reward_items_created == 0
    assert second.attendances == 0
    assert second.ledger_credits == 0
    assert second.registrations == 0
    assert second.cancellations == 0
    assert second.redemptions_opened == 0
    assert second.redemptions_advanced == 0
    assert second.redemptions_existing == len(REDEMPTION_PLAN)
    assert second.meetings_created == 0
    assert second.host_requests_filed == 0

    # Nothing doubled and nothing debited twice: the three planned rows are
    # still the only rows, and the balance is still 1200 - 300.
    assert _redemption_states(engine, tenant_id, ids["student"]) == [
        ("fulfilled", 300),
        ("approved", 600),
        ("requested", 1000),
    ]
    assert _folded_balance(engine, tenant_id, ids["student"]) == 900


def test_a_terminal_redemption_is_never_reopened(
    engine: Engine,
    session_factory: sessionmaker[Session],
    tenant_id: uuid.UUID,
    seeded_tenant,
) -> None:
    """A row a person closed differently is history, not a retry — and cannot double-drain.

    This is the defect the partial unique index cannot stop: ``denied`` is not
    in ``uq_redemption_open_per_item``'s predicate, so a blind re-open would
    mint a second row for the same item — and the seeded data would be lying
    about what happened.
    """
    ids = seeded_tenant
    with session_factory() as session:
        # The catalog first, so the denied row can name a real item: this is
        # "the student asked once, a person denied it, and the seed ran after",
        # which is the only honest shape a pre-existing denial can take.
        report = EngagementReport()
        _seed_catalog(
            session,
            tenant_slug=ids["slug"],
            budget_owner_subject=ids["admin"],
            report=report,
        )
        item_id = session.execute(
            sa.select(schema.reward_item.c.id).where(
                schema.reward_item.c.tenant_id == tenant_id,
                schema.reward_item.c.name == "Bronco Bookstore $10 Gift Card",
            )
        ).scalar_one()
        session.execute(
            sa.insert(schema.redemption).values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                subject_id=_subject_id(session, tenant_id, ids["student"]),
                item_id=item_id,
                item_name_snapshot="Bronco Bookstore $10 Gift Card",
                points_cost_snapshot=300,
                state="denied",
                requested_at=sa.func.now(),
                closed_at=sa.func.now(),
            )
        )
        session.commit()

    report = _run(session_factory, tenant_id, ids)

    # The step is skipped, not reopened: still one row for the item, still
    # denied, and the run says so in a note rather than pretending otherwise.
    states = _redemption_states(engine, tenant_id, ids["student"])
    assert sum(1 for _, cost in states if cost == 300) == 1
    assert ("denied", 300) in states
    assert any("Bronco Bookstore" in note for note in report.notes)
