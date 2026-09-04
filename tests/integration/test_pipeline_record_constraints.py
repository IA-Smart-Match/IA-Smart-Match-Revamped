"""The S12 funnel's evidence table, against a real PostgreSQL instance (P8 card O2).

Migration ``0011`` gives the five Pipeline metrics the evidence source they
have never had. This file proves what that table refuses, and — the half that
matters more for a *metric* — that the numbers it can produce are coherent.

ADR-0011's rules are what these tests are ultimately about:

* rule 3, the drill-down equals the aggregate. Here that reduces to a
  uniqueness property: a duplicate journey inflates the count and the row list
  *identically*, so the two still agree while both are wrong. A constraint is
  the only thing that catches it, because no equality check can.
* rule 4, one owning query. The funnel's five numbers come from one predicate
  each over one table, and the query card **O3** will bind
  (``pipeline_funnel_rows_v1``) is written out in
  :func:`funnel_counts` below so the binding has something to be checked
  against rather than invented.

**This card deliberately stops at persistence.** Nothing here registers a
metric or binds an owning query — ``METRIC_REGISTER`` and
``routers/metrics.py`` belong to cards O1 and O3, and until O3 lands every
Pipeline metric still answers ``PIPELINE_UNKNOWN_REASON``, which stays the
truthful answer while nothing reads these rows.

Requires a live database, and is skipped when none is reachable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("sqlalchemy")

from conftest import ensure_event, ensure_owning_unit, unique_subject
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration

#: The five stages, in funnel order. Named once here because every test below
#: is about the relationship between neighbours in this sequence.
STAGES = ("matched_at", "contacted_at", "confirmed_at", "attended_at", "member_inquiry_at")


@pytest.fixture(autouse=True)
def _clean_pipeline_tables(engine: Engine, tenant_id):
    """Delete this file's rows before ``tenant_id`` tears down its own.

    Same arrangement, and the same reason, as
    ``test_engagement_schema_constraints.py``: every foreign key ``0011`` adds
    is ``RESTRICT``, so a row left behind here would make ``conftest.py``'s
    teardown fail trying to delete the ``user_account`` and ``org_unit`` rows
    it still references. Ordered child-before-parent — ``pipeline_record``
    cites ``attendance_record``, so it goes first.
    """
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM pipeline_record WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(
            text("DELETE FROM attendance_record WHERE tenant_id = :tid"), {"tid": tenant_id}
        )


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
            "sub": unique_subject(f"pipeline-{user_id.hex[:8]}"),
            "email": f"{user_id.hex[:8]}@example.edu",
        },
    )
    return user_id


def _make_unit(conn, tenant_id: uuid.UUID, path: str) -> uuid.UUID:
    """A second unit, for the isolation test. ``ensure_owning_unit`` owns the first."""
    unit_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
            "VALUES (:id, :tid, CAST(:path AS ltree), 'department', 'Other Unit')"
        ),
        {"id": unit_id, "tid": tenant_id, "path": path},
    )
    return unit_id


def _insert_attendance(conn, tenant_id: uuid.UUID, subject_id: uuid.UUID) -> uuid.UUID:
    record_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO attendance_record "
            "(id, tenant_id, owning_unit_id, subject_id, event_id, method) "
            "VALUES (:id, :tenant_id, :unit_id, :subject_id, :event_id, 'qr_scan')"
        ),
        {
            "id": record_id,
            "tenant_id": tenant_id,
            "unit_id": ensure_owning_unit(conn, tenant_id),
            "subject_id": subject_id,
            # Migration 0017 constrained this column; ensure_event gives the
            # attendance row a real event to cite.
            "event_id": ensure_event(conn, tenant_id),
        },
    )
    return record_id


def _insert_pipeline_record(
    conn,
    tenant_id: uuid.UUID,
    *,
    reached: str = "matched_at",
    subject_id: uuid.UUID | None = None,
    opportunity_event_id: uuid.UUID | None = None,
    owning_unit_id: uuid.UUID | None = None,
    attended_attendance_id: object = "__auto__",
    times: dict[str, datetime] | None = None,
    matched_provenance: str = "synthetic / coordinator-accepted",
) -> uuid.UUID:
    """Insert one journey that has reached ``reached``, and return its id.

    Writes a timestamp for every stage up to and including ``reached``, an hour
    apart in funnel order, which is the shape the constraints require and the
    shape a real journey has. ``times`` overrides individual stages so a test
    can write an incoherent row on purpose; ``attended_attendance_id`` defaults
    to a real attendance row when the journey reached Attended, and takes an
    explicit value (including ``None``) to exercise the evidence
    biconditional. ``matched_provenance`` defaults to the one value every
    existing call site needs (migration ``0016``), and takes an explicit
    value — including a fabricated one — so a test can exercise
    ``ck_pipeline_record_matched_provenance`` on purpose.
    """
    record_id = uuid.uuid4()
    subject_id = subject_id or _make_user(conn, tenant_id)
    stage_index = STAGES.index(reached)
    base = datetime.now(UTC) - timedelta(days=1)

    values: dict[str, object] = {
        stage: base + timedelta(hours=offset)
        for offset, stage in enumerate(STAGES[: stage_index + 1])
    }
    values.update(times or {})

    evidence = attended_attendance_id
    if evidence == "__auto__":
        evidence = (
            _insert_attendance(conn, tenant_id, subject_id)
            if values.get("attended_at") is not None
            else None
        )

    conn.execute(
        text(
            "INSERT INTO pipeline_record "
            "(id, tenant_id, owning_unit_id, subject_id, opportunity_event_id, "
            "matched_at, matched_provenance, contacted_at, confirmed_at, attended_at, "
            "member_inquiry_at, attended_attendance_id) "
            "VALUES (:id, :tenant_id, :unit_id, :subject_id, :event_id, "
            ":matched_at, :matched_provenance, :contacted_at, :confirmed_at, :attended_at, "
            ":member_inquiry_at, :evidence)"
        ),
        {
            "id": record_id,
            "tenant_id": tenant_id,
            "unit_id": owning_unit_id
            if owning_unit_id is not None
            else ensure_owning_unit(conn, tenant_id),
            "subject_id": subject_id,
            # `pipeline_record.opportunity_event_id` still has no foreign key
            # (see the test at the bottom of this file), so a fabricated id is
            # storable here. It defaults to a real `event` anyway, because
            # `tools/seed_demo_pipeline.py` hands this id to
            # `AttendanceRepository.record_attendance` at the Attended stage,
            # and *that* column has been constrained since migration 0017.
            # A *distinct* event per call, so two journeys for one student stay
            # two journeys rather than colliding on
            # uq_pipeline_record_subject_opportunity.
            "event_id": opportunity_event_id
            or ensure_event(conn, tenant_id, f"journey-{record_id.hex[:8]}"),
            "matched_at": values.get("matched_at"),
            "matched_provenance": matched_provenance,
            "contacted_at": values.get("contacted_at"),
            "confirmed_at": values.get("confirmed_at"),
            "attended_at": values.get("attended_at"),
            "member_inquiry_at": values.get("member_inquiry_at"),
            "evidence": evidence,
        },
    )
    return record_id


def funnel_counts(conn, tenant_id: uuid.UUID, unit_id: uuid.UUID) -> dict[str, int]:
    """The five aggregates, from one query over one unit's rows.

    Written here rather than in the router because card **O3** owns the
    binding: this is the shape ``pipeline_funnel_rows_v1`` reads, expressed
    once so the tests below assert against the same predicate the API will use
    — "reached stage X" is ``<stage>_at IS NOT NULL``, and nothing else. A
    router that computes it differently and a test that computes it here would
    be two owning queries for one number, which is the defect ADR-0011 rule 4
    names.
    """
    row = conn.execute(
        text(
            "SELECT "
            + ", ".join(
                f"count(*) FILTER (WHERE {stage} IS NOT NULL) AS {stage[:-3]}" for stage in STAGES
            )
            + " FROM pipeline_record WHERE tenant_id = :tid AND owning_unit_id = :unit"
        ),
        {"tid": tenant_id, "unit": unit_id},
    ).one()
    return {stage[:-3]: getattr(row, stage[:-3]) for stage in STAGES}


def funnel_rows(conn, tenant_id: uuid.UUID, unit_id: uuid.UUID, stage: str) -> list[uuid.UUID]:
    """The constituent rows behind one of those aggregates — the drill-down."""
    return [
        row.id
        for row in conn.execute(
            text(
                f"SELECT id FROM pipeline_record WHERE tenant_id = :tid "
                f"AND owning_unit_id = :unit AND {stage} IS NOT NULL ORDER BY matched_at, id"
            ),
            {"tid": tenant_id, "unit": unit_id},
        )
    ]


# ---------------------------------------------------------------------------
# The funnel is cumulative, and the numbers it produces are coherent
# ---------------------------------------------------------------------------


def test_a_journey_counts_toward_every_stage_it_has_reached(engine: Engine, tenant_id) -> None:
    """ "Reached X or a later stage" is what the register says, and what the table stores.

    One record that got as far as Confirmed counts toward Matched, Contacted
    and Confirmed, and toward neither of the two beyond it. That is the whole
    semantics of a funnel, and storing a single current-status column would
    have given the opposite answer for the first two.
    """
    with engine.begin() as conn:
        unit = ensure_owning_unit(conn, tenant_id)
        _insert_pipeline_record(conn, tenant_id, reached="confirmed_at")

        assert funnel_counts(conn, tenant_id, unit) == {
            "matched": 1,
            "contacted": 1,
            "confirmed": 1,
            "attended": 0,
            "member_inquiry": 0,
        }


def test_the_funnel_never_widens_as_it_deepens(engine: Engine, tenant_id) -> None:
    """The property a viewer checks by eye, asserted over a mixed population.

    Five journeys stopping at five different stages. Each stage's count must be
    at most the one before it — not because the query sorts them that way, but
    because ``ck_pipeline_record_stage_prefix`` makes any row that would break
    it unstorable. A funnel wider at the bottom than the top is the class of
    number ADR-0011 exists to prevent, and it is the one incoherence a
    drill-down cannot expose: every individual row would be reported
    faithfully.
    """
    with engine.begin() as conn:
        unit = ensure_owning_unit(conn, tenant_id)
        for stage in STAGES:
            _insert_pipeline_record(conn, tenant_id, reached=stage)

        counts = funnel_counts(conn, tenant_id, unit)

    assert list(counts.values()) == [5, 4, 3, 2, 1]
    assert counts["matched"] >= counts["contacted"] >= counts["confirmed"], (
        "a funnel that widens is a number nobody can reconcile"
    )
    assert counts["confirmed"] >= counts["attended"] >= counts["member_inquiry"]


def test_the_drill_down_returns_exactly_the_rows_the_aggregate_counted(
    engine: Engine, tenant_id
) -> None:
    """ADR-0011 rule 3, at the storage layer where it is decided.

    Clicking N must list N rows. Asserted for a non-zero stage and for an empty
    one, because zero is the case a query with a subtly different predicate
    still gets right.
    """
    with engine.begin() as conn:
        unit = ensure_owning_unit(conn, tenant_id)
        _insert_pipeline_record(conn, tenant_id, reached="contacted_at")
        _insert_pipeline_record(conn, tenant_id, reached="attended_at")

        counts = funnel_counts(conn, tenant_id, unit)
        for stage in STAGES:
            rows = funnel_rows(conn, tenant_id, unit, stage)
            assert len(rows) == counts[stage[:-3]], f"{stage}: aggregate and drill-down disagree"
            assert len(set(rows)) == len(rows), f"{stage}: a row was listed twice"

    assert counts["member_inquiry"] == 0, "the empty case must be exercised, not assumed"


def test_one_units_funnel_does_not_count_another_units_records(engine: Engine, tenant_id) -> None:
    """The metric is read per organizational unit, so the rows must be scoped by one.

    ``owning_unit_id`` is written on the row (A5) rather than joined back
    through the opportunity, which is what makes this a filter on one indexed
    table rather than a join whose correctness depends on an event table that
    does not exist yet.
    """
    with engine.begin() as conn:
        mine = ensure_owning_unit(conn, tenant_id)
        theirs = _make_unit(conn, tenant_id, "iawest.other")
        _insert_pipeline_record(conn, tenant_id, reached="attended_at", owning_unit_id=mine)
        _insert_pipeline_record(conn, tenant_id, reached="attended_at", owning_unit_id=theirs)

        assert funnel_counts(conn, tenant_id, mine)["attended"] == 1
        assert funnel_counts(conn, tenant_id, theirs)["attended"] == 1
        assert len(funnel_rows(conn, tenant_id, mine, "attended_at")) == 1


# ---------------------------------------------------------------------------
# uq_pipeline_record_subject_opportunity
# ---------------------------------------------------------------------------


def test_the_same_student_and_opportunity_cannot_be_recorded_twice(
    engine: Engine, tenant_id
) -> None:
    """A duplicate journey is a double count that audits as correct.

    The aggregate and the drill-down would both be inflated, and by the same
    row, so ADR-0011 rule 3 still holds and the number is still wrong. No
    equality check can catch that; a unique constraint is the only instrument
    that can, which is the argument ``uq_attendance_record_subject_event``
    already makes one table over.
    """
    with engine.begin() as conn:
        subject = _make_user(conn, tenant_id)
        opportunity = uuid.uuid4()
        _insert_pipeline_record(
            conn, tenant_id, subject_id=subject, opportunity_event_id=opportunity
        )

    with (
        pytest.raises(IntegrityError, match="uq_pipeline_record_subject_opportunity"),
        engine.begin() as conn,
    ):
        _insert_pipeline_record(
            conn, tenant_id, subject_id=subject, opportunity_event_id=opportunity
        )


def test_the_same_student_may_appear_for_a_different_opportunity(engine: Engine, tenant_id) -> None:
    """The uniqueness is per journey, not per student: two opportunities are two rows."""
    with engine.begin() as conn:
        subject = _make_user(conn, tenant_id)
        unit = ensure_owning_unit(conn, tenant_id)
        _insert_pipeline_record(conn, tenant_id, subject_id=subject)
        _insert_pipeline_record(conn, tenant_id, subject_id=subject)

        assert funnel_counts(conn, tenant_id, unit)["matched"] == 2


# ---------------------------------------------------------------------------
# ck_pipeline_record_stage_prefix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("reached", "missing"),
    [
        ("confirmed_at", "contacted_at"),
        ("attended_at", "confirmed_at"),
        ("member_inquiry_at", "attended_at"),
    ],
)
def test_a_stage_cannot_be_reached_without_the_one_before_it(
    engine: Engine, tenant_id, reached: str, missing: str
) -> None:
    """Every reachable neighbouring pair, refused with its predecessor knocked out.

    Parametrized over the pairs rather than asserted once: the constraint is
    four clauses, and a test of one clause says nothing about the other three.

    **Three cases, not four, and the missing one is stated rather than
    quietly dropped.** The constraint's first clause — Contacted requires
    Matched — cannot be violated while ``matched_at`` is ``NOT NULL``, so no
    write can exercise it. It is kept in the constraint for symmetry and
    against a future migration relaxing that column, and it is named here so a
    reader counting clauses against cases does not conclude one was forgotten.
    """
    with (
        pytest.raises(IntegrityError, match="ck_pipeline_record_stage_prefix"),
        engine.begin() as conn,
    ):
        _insert_pipeline_record(
            conn,
            tenant_id,
            reached=reached,
            times={missing: None},
            attended_attendance_id=None if reached != "attended_at" else "__auto__",
        )


def test_a_journey_may_stop_at_any_stage(engine: Engine, tenant_id) -> None:
    """The permitted writes, which is the half that catches an inverted constraint.

    A prefix rule that refused every partial journey would refuse these five
    too, and a refusal test alone would not notice: it would still be red for
    the wrong reason on the rows it tries.
    """
    with engine.begin() as conn:
        for stage in STAGES:
            _insert_pipeline_record(conn, tenant_id, reached=stage)


# ---------------------------------------------------------------------------
# ck_pipeline_record_stage_order
# ---------------------------------------------------------------------------


def test_a_stage_cannot_be_reached_before_the_one_before_it(engine: Engine, tenant_id) -> None:
    """Presence is not order: the prefix rule alone admits a journey that ran backwards.

    Every timestamp is present and in the right columns; only the clock
    disagrees. Nothing about the *counts* changes, which is why this needs its
    own constraint and its own test — the incoherence surfaces the moment
    anything reports when a stage was reached rather than how many reached it.
    """
    yesterday = datetime.now(UTC) - timedelta(days=1)
    with (
        pytest.raises(IntegrityError, match="ck_pipeline_record_stage_order"),
        engine.begin() as conn,
    ):
        _insert_pipeline_record(
            conn,
            tenant_id,
            reached="confirmed_at",
            times={"confirmed_at": yesterday - timedelta(hours=5)},
        )


def test_two_stages_reached_in_the_same_instant_are_permitted(engine: Engine, tenant_id) -> None:
    """``>=``, not ``>``, and the boundary is deliberate.

    An import that records a completed journey in one statement writes the same
    timestamp to several stages, and there is nothing dishonest about that —
    the evidence really did arrive at once. A strict inequality would refuse
    the ordinary bulk case to gain nothing.
    """
    same = datetime.now(UTC) - timedelta(hours=2)
    with engine.begin() as conn:
        _insert_pipeline_record(
            conn,
            tenant_id,
            reached="confirmed_at",
            times={"matched_at": same, "contacted_at": same, "confirmed_at": same},
        )


# ---------------------------------------------------------------------------
# ck_pipeline_record_attendance_evidence
# ---------------------------------------------------------------------------


def test_an_attended_journey_must_name_the_attendance_it_rests_on(
    engine: Engine, tenant_id
) -> None:
    """ADR-0013's evidence rule, applied to the funnel's claim about the same fact.

    "Attended" here and ``attendance_record`` there are two statements about
    one event. A funnel row asserting the first while citing nothing is the
    fabricated-field defect (H21, Fix #15) at the schema layer, so the schema
    refuses to hold it.
    """
    with (
        pytest.raises(IntegrityError, match="ck_pipeline_record_attendance_evidence"),
        engine.begin() as conn,
    ):
        _insert_pipeline_record(conn, tenant_id, reached="attended_at", attended_attendance_id=None)


def test_evidence_is_never_carried_without_the_claim_it_supports(engine: Engine, tenant_id) -> None:
    """The other direction of the biconditional, which a NOT NULL could not express.

    A row citing an attendance record while claiming not to have attended is
    not a harmless leftover: it is a row whose two halves disagree, and
    whichever half a later reader trusts, one of them is wrong.
    """
    with (
        pytest.raises(IntegrityError, match="ck_pipeline_record_attendance_evidence"),
        engine.begin() as conn,
    ):
        subject = _make_user(conn, tenant_id)
        _insert_pipeline_record(
            conn,
            tenant_id,
            reached="confirmed_at",
            subject_id=subject,
            attended_attendance_id=_insert_attendance(conn, tenant_id, subject),
        )


def test_the_attendance_a_funnel_row_cites_cannot_be_deleted(engine: Engine, tenant_id) -> None:
    """``ON DELETE RESTRICT``: the count must stay explainable.

    A cascade would delete the pipeline record — silently reducing every stage
    count — and a ``SET NULL`` would produce the row the biconditional above
    refuses. Restricting is what keeps the deletion a decision someone has to
    take about the funnel row too.
    """
    with engine.begin() as conn:
        subject = _make_user(conn, tenant_id)
        attendance = _insert_attendance(conn, tenant_id, subject)
        _insert_pipeline_record(
            conn,
            tenant_id,
            reached="attended_at",
            subject_id=subject,
            attended_attendance_id=attendance,
        )

    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text("DELETE FROM attendance_record WHERE id = :id"), {"id": attendance})


# ---------------------------------------------------------------------------
# Tenancy and ownership
# ---------------------------------------------------------------------------


def test_a_record_cannot_name_a_student_from_another_tenant(engine: Engine, tenant_id) -> None:
    """The composite key, tested with a real account rather than an id from nowhere.

    An id belonging to nobody is refused by any foreign key, including a
    single-column one, so it cannot distinguish the two shapes. A real
    ``user_account`` in a second tenant can: the composite key
    ``(tenant_id, subject_id) -> user_account (tenant_id, id)`` refuses it and
    a narrow key would not.
    """
    other_tenant = uuid.uuid4()
    slug = f"test-pipeline-other-{other_tenant.hex[:8]}"
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :name)"),
            {"id": other_tenant, "slug": slug, "name": slug},
        )
        stranger = _make_user(conn, other_tenant)

    try:
        with pytest.raises(IntegrityError), engine.begin() as conn:
            _insert_pipeline_record(conn, tenant_id, subject_id=stranger)
    finally:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM user_account WHERE tenant_id = :tid"), {"tid": other_tenant}
            )
            conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": other_tenant})


def test_the_unit_that_owns_a_funnel_row_cannot_be_deleted_under_it(
    engine: Engine, tenant_id
) -> None:
    """``RESTRICT`` on the owning unit, matching ``job`` and ``import_batch``.

    The unit is the axis the metric is read per, so removing it while records
    still point at it would leave rows no unit's funnel counts and no drill-down
    lists — invisible work, the shape this repository refuses elsewhere.
    """
    with engine.begin() as conn:
        unit = _make_unit(conn, tenant_id, "iawest.doomed")
        _insert_pipeline_record(conn, tenant_id, owning_unit_id=unit)

    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text("DELETE FROM org_unit WHERE id = :id"), {"id": unit})


def test_the_opportunity_is_recorded_even_though_no_event_table_constrains_it(
    engine: Engine, tenant_id
) -> None:
    """The P6 dependency, asserted as the state it actually is rather than assumed.

    ``opportunity_event_id`` is ``NOT NULL`` with no foreign key, exactly as
    ``attendance_record.event_id`` has been since ``0009``: there is no
    ``event`` table for it to reference, and P6 owns the one that will be. This
    test pins both halves — the id is required, and nothing yet checks that it
    refers to anything — so that whichever migration adds ``event`` finds a
    test telling it to add the constraint here too.
    """
    with engine.begin() as conn:
        # Accepted today: an opportunity id referring to nothing.
        _insert_pipeline_record(conn, tenant_id, opportunity_event_id=uuid.uuid4())

        constraints = conn.execute(
            text(
                "SELECT conname FROM pg_constraint WHERE conrelid = 'pipeline_record'::regclass "
                "AND contype = 'f' ORDER BY conname"
            )
        ).scalars()

    assert list(constraints) == [
        "pipeline_record_tenant_id_attended_attendance_id_fkey",
        "pipeline_record_tenant_id_owning_unit_id_fkey",
        "pipeline_record_tenant_id_subject_id_fkey",
    ], (
        "an event table now exists or the keys changed: give opportunity_event_id "
        "its foreign key, alongside attendance_record.event_id (P6)"
    )

    with (
        pytest.raises(IntegrityError, match=r"(?i)null value|not-null|opportunity_event_id"),
        engine.begin() as conn,
    ):
        conn.execute(
            text(
                "INSERT INTO pipeline_record "
                "(id, tenant_id, owning_unit_id, subject_id, opportunity_event_id, "
                "matched_provenance) "
                "VALUES (:id, :tid, :unit, :subject, NULL, :provenance)"
            ),
            {
                "id": uuid.uuid4(),
                "tid": tenant_id,
                "unit": ensure_owning_unit(conn, tenant_id),
                "subject": _make_user(conn, tenant_id),
                "provenance": "synthetic / coordinator-accepted",
            },
        )
