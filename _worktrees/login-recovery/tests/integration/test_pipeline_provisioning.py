"""``provision_on_accept``, against a real PostgreSQL instance (Card 5).

`services/api/smartmatch_api/pipeline_provisioning.py` is the application
service the whole `pilot/pipeline-synthetic-caller` branch exists to build:
`PipelineRepository.record_matched` has had no production caller since it was
written, and this module is where a coordinator's review-accept becomes a
real ``pipeline_record`` row. This file calls :func:`provision_on_accept`
directly against a live session — no HTTP, no route, no authorizer; that
end-to-end proof through the real ``POST /v1/review-items/{id}/decision``
route is Card 8's, once Card 6 has wired this module into the router.

Every call below opens its own session and commits immediately — mirroring
``test_professional_identity_writers.py``'s own pattern — rather than sharing
one uncommitted session across a test. Several assertions read the written
rows back through a *separate* raw connection (``engine.begin()``), and under
READ COMMITTED (this project's isolation level) a separate connection cannot
see another session's uncommitted writes; committing after each provisioning
call is what makes those reads correct rather than flaky.

Requires a live database, and is skipped when none is reachable.
"""

from __future__ import annotations

import ast
import inspect
import logging
import uuid
from datetime import UTC, datetime
from types import ModuleType

import pytest

pytest.importorskip("sqlalchemy")

from smartmatch_api import pipeline_provisioning as provisioning_module
from smartmatch_api.pipeline_provisioning import (
    EVENT_CATEGORY_KEY,
    EVENTS_DATASET,
    PROFESSIONAL_NAME_KEY,
    PROFESSIONALS_DATASET,
    ProvisionOutcome,
    provision_on_accept,
)
from smartmatch_domain.synthetic_pilot import (
    MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT,
    SYNTHETIC_BOARD_ROLE,
    SYNTHETIC_MATCH_PROVENANCE,
    synthetic_opportunity_event_id,
    synthetic_professional_subject_id,
)
from smartmatch_persistence.pipeline import (
    MATCH_PROVENANCE_SYNTHETIC_COORDINATOR,
    ConflictingOwningUnitError,
    PipelineRepository,
)
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration

#: Score-shaped identifier fragments — see
#: ``test_professional_identity_writers.py::_fabricated_score_identifiers``,
#: which this helper mirrors exactly, for why these are checked against
#: identifiers only, never against prose.
_FABRICATED_SCORE_TOKENS = ("score", "confidence", "match_score", "rank", "weight")


def _fabricated_score_identifiers(module: ModuleType) -> list[str]:
    """Score-shaped names used as assignment targets, parameters, or function names.

    Walks the module's AST rather than grepping its raw source text, so a
    docstring explaining at length what this module refuses to compute
    cannot fail this check for containing the word.
    """
    tree = ast.parse(inspect.getsource(module))
    offenders: list[str] = []
    for node in ast.walk(tree):
        name: str | None
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            name = node.id
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
            name = node.attr
        elif isinstance(node, ast.arg | ast.keyword):
            name = node.arg
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            name = node.name
        else:
            name = None
        if name is not None and any(token in name.lower() for token in _FABRICATED_SCORE_TOKENS):
            offenders.append(name)
    return offenders


@pytest.fixture(autouse=True)
def _clean_provisioning_tables(engine: Engine, tenant_id: uuid.UUID):
    """Delete this file's rows for the test tenant, in dependency order.

    ``pipeline_record`` first (cites ``user_account`` via ``ON DELETE
    RESTRICT``), then ``professional_unit_relationship``, then
    ``user_account`` itself — the same order and the same reason
    ``test_professional_identity_writers.py`` uses.
    """
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM pipeline_record WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(
            text("DELETE FROM professional_unit_relationship WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )
        conn.execute(text("DELETE FROM user_account WHERE tenant_id = :tid"), {"tid": tenant_id})


def _accept_professional(
    session_factory: sessionmaker[Session],
    *,
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    name: object,
    review_item_id: uuid.UUID | None = None,
    accepted_at: datetime | None = None,
    row_data: dict[str, object] | None = None,
) -> ProvisionOutcome:
    """Accept one ``professionals`` row in its own session, and commit.

    Committing immediately is what lets later raw-SQL reads through a
    different connection see the write — see the module docstring.
    """
    data = row_data if row_data is not None else {PROFESSIONAL_NAME_KEY: name}
    with session_factory() as session:
        outcome = provision_on_accept(
            session,
            tenant_id=tenant_id,
            owning_unit_id=owning_unit_id,
            review_item_id=review_item_id or uuid.uuid4(),
            dataset=PROFESSIONALS_DATASET,
            row_data=data,
            accepted_at=accepted_at or datetime.now(UTC),
        )
        session.commit()
    return outcome


def _accept_event(
    session_factory: sessionmaker[Session],
    *,
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    review_item_id: uuid.UUID,
    category: object,
    accepted_at: datetime | None = None,
) -> ProvisionOutcome:
    """Accept one ``events`` row in its own session, and commit.

    See :func:`_accept_professional` for why each call commits immediately.
    """
    with session_factory() as session:
        outcome = provision_on_accept(
            session,
            tenant_id=tenant_id,
            owning_unit_id=owning_unit_id,
            review_item_id=review_item_id,
            dataset=EVENTS_DATASET,
            row_data={EVENT_CATEGORY_KEY: category},
            accepted_at=accepted_at or datetime.now(UTC),
        )
        session.commit()
    return outcome


def _make_second_org_unit(conn, tenant_id: uuid.UUID, path: str) -> uuid.UUID:
    """A second ``org_unit`` row in ``tenant_id``, for the unit-conflict test.

    A local copy of the identical helper
    ``test_pipeline_record_constraints.py::_make_unit`` and
    ``test_professional_identity_writers.py::_make_unit`` both define,
    rather than an import of either — those files are owned by Cards 1 and
    3, closed to this card's fence, and importing a private helper from a
    file this card cannot modify would make this file's tests break the
    moment that helper is renamed or removed for reasons unrelated to this
    module.
    """
    unit_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
            "VALUES (:id, :tid, CAST(:path AS ltree), 'department', 'Other Unit')"
        ),
        {"id": unit_id, "tid": tenant_id, "path": path},
    )
    return unit_id


# ---------------------------------------------------------------------------
# 1-2 — professionals accept: identity, and idempotency
# ---------------------------------------------------------------------------


def test_accepting_a_professionals_row_writes_identity_and_opens_no_journey(
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    engine: Engine,
    session_factory: sessionmaker[Session],
) -> None:
    name = f"Ada Lovelace {uuid.uuid4().hex[:8]}"
    expected_subject_id = synthetic_professional_subject_id(
        tenant_id=tenant_id, unit_id=owning_unit_id, name=name
    )

    outcome = _accept_professional(
        session_factory, tenant_id=tenant_id, owning_unit_id=owning_unit_id, name=name
    )

    assert outcome.professional_subject_id == expected_subject_id
    assert outcome.journeys_opened == ()
    assert outcome.opportunity_event_id is None

    with engine.begin() as conn:
        account_count = conn.execute(
            text("SELECT COUNT(*) FROM user_account WHERE id = :id"),
            {"id": expected_subject_id},
        ).scalar_one()
        relationship = conn.execute(
            text(
                "SELECT board_role FROM professional_unit_relationship "
                "WHERE tenant_id = :tid AND professional_id = :pid AND unit_id = :uid"
            ),
            {"tid": tenant_id, "pid": expected_subject_id, "uid": owning_unit_id},
        ).one()

    assert account_count == 1
    assert relationship.board_role == SYNTHETIC_BOARD_ROLE


def test_accepting_the_same_professionals_row_twice_is_idempotent(
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    engine: Engine,
    session_factory: sessionmaker[Session],
) -> None:
    name = f"Grace Hopper {uuid.uuid4().hex[:8]}"

    first = _accept_professional(
        session_factory, tenant_id=tenant_id, owning_unit_id=owning_unit_id, name=name
    )
    second = _accept_professional(
        session_factory, tenant_id=tenant_id, owning_unit_id=owning_unit_id, name=name
    )

    assert first.professional_subject_id == second.professional_subject_id

    with engine.begin() as conn:
        account_count = conn.execute(
            text("SELECT COUNT(*) FROM user_account WHERE id = :id"),
            {"id": first.professional_subject_id},
        ).scalar_one()
        relationship_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM professional_unit_relationship "
                "WHERE tenant_id = :tid AND professional_id = :pid"
            ),
            {"tid": tenant_id, "pid": first.professional_subject_id},
        ).scalar_one()

    assert account_count == 1
    assert relationship_count == 1


# ---------------------------------------------------------------------------
# 3 — a nameless professionals row writes nothing and warns
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_name", ["", "   ", None, 12345])
def test_professionals_row_with_no_usable_name_writes_nothing_and_warns(
    bad_name: object,
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    engine: Engine,
    session_factory: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    row_data: dict[str, object] = {} if bad_name is None else {PROFESSIONAL_NAME_KEY: bad_name}

    with caplog.at_level(logging.WARNING, logger="smartmatch_api.pipeline_provisioning"):
        outcome = _accept_professional(
            session_factory,
            tenant_id=tenant_id,
            owning_unit_id=owning_unit_id,
            name=bad_name,
            row_data=row_data,
        )

    assert outcome == ProvisionOutcome()
    assert any(record.levelno == logging.WARNING for record in caplog.records)

    with engine.begin() as conn:
        account_count = conn.execute(
            text("SELECT COUNT(*) FROM user_account WHERE tenant_id = :tid"), {"tid": tenant_id}
        ).scalar_one()
    assert account_count == 0


# ---------------------------------------------------------------------------
# 4 — an in-list events accept opens one journey per linked professional
# ---------------------------------------------------------------------------


def test_in_list_events_accept_opens_one_journey_per_linked_professional(
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    engine: Engine,
    session_factory: sessionmaker[Session],
) -> None:
    subject_ids = [
        _accept_professional(
            session_factory,
            tenant_id=tenant_id,
            owning_unit_id=owning_unit_id,
            name=f"Professional {label} {uuid.uuid4().hex[:8]}",
        ).professional_subject_id
        for label in ("one", "two")
    ]

    review_item_id = uuid.uuid4()
    accepted_at = datetime.now(UTC)
    outcome = _accept_event(
        session_factory,
        tenant_id=tenant_id,
        owning_unit_id=owning_unit_id,
        review_item_id=review_item_id,
        category="hackathon",
        accepted_at=accepted_at,
    )

    expected_opportunity_event_id = synthetic_opportunity_event_id(
        tenant_id=tenant_id, review_item_id=review_item_id
    )
    assert outcome.opportunity_event_id == expected_opportunity_event_id
    assert len(outcome.journeys_opened) == 2

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT id, subject_id, owning_unit_id, opportunity_event_id, matched_at, "
                "matched_provenance FROM pipeline_record WHERE tenant_id = :tid"
            ),
            {"tid": tenant_id},
        ).all()

    assert len(rows) == 2
    assert {row.id for row in rows} == set(outcome.journeys_opened)
    assert {row.subject_id for row in rows} == set(subject_ids)
    for row in rows:
        assert row.owning_unit_id == owning_unit_id
        assert row.opportunity_event_id == expected_opportunity_event_id
        assert row.matched_at == accepted_at
        assert row.matched_provenance == "synthetic / coordinator-accepted"
        assert row.matched_provenance == MATCH_PROVENANCE_SYNTHETIC_COORDINATOR


# ---------------------------------------------------------------------------
# 5-6 — out-of-list and absent categories open zero journeys, not an error
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "category", ["some unmapped label", None, "", "   "], ids=["unmapped", "none", "empty", "blank"]
)
def test_non_in_list_events_accept_opens_zero_journeys(
    category: object,
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    engine: Engine,
    session_factory: sessionmaker[Session],
) -> None:
    _accept_professional(
        session_factory,
        tenant_id=tenant_id,
        owning_unit_id=owning_unit_id,
        name=f"Linked Professional {uuid.uuid4().hex[:8]}",
    )

    with engine.begin() as conn:
        count_before = conn.execute(
            text("SELECT COUNT(*) FROM pipeline_record WHERE tenant_id = :tid"), {"tid": tenant_id}
        ).scalar_one()

    outcome = _accept_event(
        session_factory,
        tenant_id=tenant_id,
        owning_unit_id=owning_unit_id,
        review_item_id=uuid.uuid4(),
        category=category,
    )

    assert outcome == ProvisionOutcome()

    with engine.begin() as conn:
        count_after = conn.execute(
            text("SELECT COUNT(*) FROM pipeline_record WHERE tenant_id = :tid"), {"tid": tenant_id}
        ).scalar_one()
    assert count_after == count_before


# ---------------------------------------------------------------------------
# 7 — accepting the same events row twice opens the same journeys
# ---------------------------------------------------------------------------


def test_accepting_the_same_events_row_twice_opens_the_same_journeys(
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    engine: Engine,
    session_factory: sessionmaker[Session],
) -> None:
    _accept_professional(
        session_factory,
        tenant_id=tenant_id,
        owning_unit_id=owning_unit_id,
        name=f"Repeat Professional {uuid.uuid4().hex[:8]}",
    )
    review_item_id = uuid.uuid4()

    first = _accept_event(
        session_factory,
        tenant_id=tenant_id,
        owning_unit_id=owning_unit_id,
        review_item_id=review_item_id,
        category="hackathon",
    )
    second = _accept_event(
        session_factory,
        tenant_id=tenant_id,
        owning_unit_id=owning_unit_id,
        review_item_id=review_item_id,
        category="hackathon",
    )

    assert first.journeys_opened == second.journeys_opened
    assert len(first.journeys_opened) == 1

    with engine.begin() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM pipeline_record WHERE tenant_id = :tid"), {"tid": tenant_id}
        ).scalar_one()
    assert count == 1


# ---------------------------------------------------------------------------
# 8 — fan-out is capped, and truncation is announced rather than silent
# ---------------------------------------------------------------------------


def _accept_n_professionals(
    session_factory: sessionmaker[Session],
    *,
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    count: int,
    label: str,
) -> list[uuid.UUID]:
    """Accept ``count`` distinct ``professionals`` rows; return their subject ids in order."""
    subject_ids: list[uuid.UUID] = []
    for i in range(count):
        name = f"{label} {i:03d} {uuid.uuid4().hex[:8]}"
        outcome = _accept_professional(
            session_factory, tenant_id=tenant_id, owning_unit_id=owning_unit_id, name=name
        )
        assert outcome.professional_subject_id is not None
        subject_ids.append(outcome.professional_subject_id)
    return subject_ids


def test_fan_out_is_capped_at_the_configured_maximum(
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    engine: Engine,
    session_factory: sessionmaker[Session],
) -> None:
    total_professionals = 55
    assert total_professionals > MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT

    all_subject_ids = _accept_n_professionals(
        session_factory,
        tenant_id=tenant_id,
        owning_unit_id=owning_unit_id,
        count=total_professionals,
        label="Fanout Professional",
    )
    expected_smallest = set(sorted(all_subject_ids)[:MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT])

    outcome = _accept_event(
        session_factory,
        tenant_id=tenant_id,
        owning_unit_id=owning_unit_id,
        review_item_id=uuid.uuid4(),
        category="hackathon",
    )

    assert len(outcome.journeys_opened) == MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT

    with engine.begin() as conn:
        matched_subject_ids = {
            row.subject_id
            for row in conn.execute(
                text("SELECT subject_id FROM pipeline_record WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            ).all()
        }

    assert len(matched_subject_ids) == MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT
    assert matched_subject_ids == expected_smallest


def test_exactly_at_the_cap_opens_everyone_and_does_not_warn(
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    engine: Engine,
    session_factory: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The boundary the naive ``len(subject_ids) == MAX`` check would misfire on.

    At exactly the cap, nothing was omitted — every linked professional got a
    journey — so no truncation ``WARNING`` may fire. A check that only asked
    "did we hit the limit" could not tell this apart from the over-the-cap
    case; this module asks "did the *(cap + 1)*-th row come back" instead.
    """
    _accept_n_professionals(
        session_factory,
        tenant_id=tenant_id,
        owning_unit_id=owning_unit_id,
        count=MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT,
        label="At-Cap Professional",
    )

    with caplog.at_level(logging.WARNING, logger="smartmatch_api.pipeline_provisioning"):
        outcome = _accept_event(
            session_factory,
            tenant_id=tenant_id,
            owning_unit_id=owning_unit_id,
            review_item_id=uuid.uuid4(),
            category="hackathon",
        )

    assert len(outcome.journeys_opened) == MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT
    assert not any(record.levelno == logging.WARNING for record in caplog.records)

    with engine.begin() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM pipeline_record WHERE tenant_id = :tid"), {"tid": tenant_id}
        ).scalar_one()
    assert count == MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT


def test_one_over_the_cap_warns_and_still_opens_exactly_the_cap(
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    engine: Engine,
    session_factory: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One professional past the cap is enough to make the omission visible."""
    total_professionals = MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT + 1
    all_subject_ids = _accept_n_professionals(
        session_factory,
        tenant_id=tenant_id,
        owning_unit_id=owning_unit_id,
        count=total_professionals,
        label="Over-Cap Professional",
    )
    expected_smallest = set(sorted(all_subject_ids)[:MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT])

    with caplog.at_level(logging.WARNING, logger="smartmatch_api.pipeline_provisioning"):
        outcome = _accept_event(
            session_factory,
            tenant_id=tenant_id,
            owning_unit_id=owning_unit_id,
            review_item_id=uuid.uuid4(),
            category="hackathon",
        )

    assert len(outcome.journeys_opened) == MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT

    cap_warnings = [
        record
        for record in caplog.records
        if record.levelno == logging.WARNING
        and "links more professionals than the synthetic pilot cap" in record.getMessage()
    ]
    assert len(cap_warnings) == 1

    with engine.begin() as conn:
        matched_subject_ids = {
            row.subject_id
            for row in conn.execute(
                text("SELECT subject_id FROM pipeline_record WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            ).all()
        }
    assert matched_subject_ids == expected_smallest


# ---------------------------------------------------------------------------
# 9 — a naive accepted_at is refused
# ---------------------------------------------------------------------------


def test_provision_on_accept_refuses_a_naive_accepted_at(
    tenant_id: uuid.UUID, owning_unit_id: uuid.UUID, session_factory: sessionmaker[Session]
) -> None:
    naive_accepted_at = datetime.now()  # deliberately naive - the value under test
    with (
        session_factory() as session,
        pytest.raises(ValueError, match="accepted_at must be timezone-aware"),
    ):
        provision_on_accept(
            session,
            tenant_id=tenant_id,
            owning_unit_id=owning_unit_id,
            review_item_id=uuid.uuid4(),
            dataset=PROFESSIONALS_DATASET,
            row_data={PROFESSIONAL_NAME_KEY: "Naive Time"},
            accepted_at=naive_accepted_at,
        )


# ---------------------------------------------------------------------------
# 10 — §1.10: the empty-unit WARNING fires, and zero is never silent
# ---------------------------------------------------------------------------


def test_events_accept_with_no_linked_professionals_warns_and_opens_nothing(
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    engine: Engine,
    session_factory: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="smartmatch_api.pipeline_provisioning"):
        outcome = _accept_event(
            session_factory,
            tenant_id=tenant_id,
            owning_unit_id=owning_unit_id,
            review_item_id=uuid.uuid4(),
            category="hackathon",
        )

    assert outcome.journeys_opened == ()

    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "opened NO pipeline journeys" in warnings[0].getMessage()

    with engine.begin() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM pipeline_record WHERE tenant_id = :tid"), {"tid": tenant_id}
        ).scalar_one()
    assert count == 0


# ---------------------------------------------------------------------------
# 11 — provenance is logged exactly once, verbatim
# ---------------------------------------------------------------------------


def test_provenance_is_logged_exactly_once_verbatim(
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    session_factory: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    _accept_professional(
        session_factory,
        tenant_id=tenant_id,
        owning_unit_id=owning_unit_id,
        name=f"Logged Professional {uuid.uuid4().hex[:8]}",
    )

    with caplog.at_level(logging.INFO, logger="smartmatch_api.pipeline_provisioning"):
        _accept_event(
            session_factory,
            tenant_id=tenant_id,
            owning_unit_id=owning_unit_id,
            review_item_id=uuid.uuid4(),
            category="hackathon",
        )

    info_records = [record for record in caplog.records if record.levelno == logging.INFO]
    matching = [r for r in info_records if "synthetic / coordinator-accepted" in r.getMessage()]
    assert len(matching) == 1


# ---------------------------------------------------------------------------
# 12 — negative: no fabricated score, structurally
# ---------------------------------------------------------------------------


def test_module_stores_no_fabricated_score_identifier() -> None:
    offenders = _fabricated_score_identifiers(provisioning_module)
    assert not offenders, (
        f"score-shaped identifier(s) found in pipeline_provisioning.py: {offenders}"
    )


def test_record_matched_signature_has_no_score_parameter() -> None:
    params = set(inspect.signature(PipelineRepository.record_matched).parameters)
    assert params == {
        "self",
        "session",
        "tenant_id",
        "owning_unit_id",
        "subject_id",
        "opportunity_event_id",
        "matched_at",
        "matched_provenance",
    }


# ---------------------------------------------------------------------------
# 13 — negative: no orphan subject_id
# ---------------------------------------------------------------------------


def test_no_orphan_subject_id_is_ever_written(
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    engine: Engine,
    session_factory: sessionmaker[Session],
) -> None:
    _accept_professional(
        session_factory,
        tenant_id=tenant_id,
        owning_unit_id=owning_unit_id,
        name=f"Orphan Check Professional {uuid.uuid4().hex[:8]}",
    )
    outcome = _accept_event(
        session_factory,
        tenant_id=tenant_id,
        owning_unit_id=owning_unit_id,
        review_item_id=uuid.uuid4(),
        category="hackathon",
    )
    assert len(outcome.journeys_opened) == 1

    with engine.begin() as conn:
        orphans = conn.execute(
            text(
                "SELECT pr.subject_id FROM pipeline_record pr "
                "LEFT JOIN user_account ua "
                "ON ua.tenant_id = pr.tenant_id AND ua.id = pr.subject_id "
                "WHERE pr.tenant_id = :tid AND ua.id IS NULL"
            ),
            {"tid": tenant_id},
        ).all()

    assert orphans == []


# ---------------------------------------------------------------------------
# 14 — negative: the CHECKs still bite
# ---------------------------------------------------------------------------


def test_the_checks_still_bite(
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    engine: Engine,
    session_factory: sessionmaker[Session],
) -> None:
    _accept_professional(
        session_factory,
        tenant_id=tenant_id,
        owning_unit_id=owning_unit_id,
        name=f"Check Professional {uuid.uuid4().hex[:8]}",
    )
    outcome = _accept_event(
        session_factory,
        tenant_id=tenant_id,
        owning_unit_id=owning_unit_id,
        review_item_id=uuid.uuid4(),
        category="hackathon",
    )
    assert len(outcome.journeys_opened) == 1
    record_id = outcome.journeys_opened[0]

    with (
        pytest.raises(IntegrityError, match="ck_pipeline_record_stage_order"),
        engine.begin() as conn,
    ):
        conn.execute(
            text(
                "UPDATE pipeline_record SET contacted_at = matched_at - interval '1 hour' "
                "WHERE id = :id"
            ),
            {"id": record_id},
        )

    with (
        pytest.raises(IntegrityError, match="ck_pipeline_record_attendance_evidence"),
        engine.begin() as conn,
    ):
        conn.execute(
            text("UPDATE pipeline_record SET attended_at = now() WHERE id = :id"),
            {"id": record_id},
        )

    with (
        pytest.raises(IntegrityError, match="ck_pipeline_record_matched_provenance"),
        engine.begin() as conn,
    ):
        conn.execute(
            text("UPDATE pipeline_record SET matched_provenance = 'engine' WHERE id = :id"),
            {"id": record_id},
        )


# ---------------------------------------------------------------------------
# 15 — negative: a conflicting owning unit propagates, never absorbed
# ---------------------------------------------------------------------------


def test_conflicting_owning_unit_propagates_rather_than_being_absorbed(
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    engine: Engine,
    session_factory: sessionmaker[Session],
) -> None:
    outcome = _accept_professional(
        session_factory,
        tenant_id=tenant_id,
        owning_unit_id=owning_unit_id,
        name=f"Conflict Professional {uuid.uuid4().hex[:8]}",
    )
    subject_id = outcome.professional_subject_id
    assert subject_id is not None

    event_outcome = _accept_event(
        session_factory,
        tenant_id=tenant_id,
        owning_unit_id=owning_unit_id,
        review_item_id=uuid.uuid4(),
        category="hackathon",
    )
    assert len(event_outcome.journeys_opened) == 1
    opportunity_event_id = event_outcome.opportunity_event_id
    assert opportunity_event_id is not None

    with engine.begin() as conn:
        other_unit_id = _make_second_org_unit(conn, tenant_id, "iawest.provisioning-conflict")

    pipeline_repo = PipelineRepository()
    with (
        session_factory() as session,
        pytest.raises(ConflictingOwningUnitError),
    ):
        pipeline_repo.record_matched(
            session,
            tenant_id=tenant_id,
            owning_unit_id=other_unit_id,
            subject_id=subject_id,
            opportunity_event_id=opportunity_event_id,
            matched_at=datetime.now(UTC),
            matched_provenance=SYNTHETIC_MATCH_PROVENANCE,
        )


# ---------------------------------------------------------------------------
# 16 — an unrecognised dataset is a no-op, not an error
# ---------------------------------------------------------------------------


def test_an_unrecognised_dataset_provisions_nothing_and_logs_nothing(
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    engine: Engine,
    session_factory: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The ``dataset`` branch every one of the 21 tests above never took.

    Every other test in this file passes ``PROFESSIONALS_DATASET`` or
    ``EVENTS_DATASET`` — this one proves the fourth documented branch (an
    unrecognised ``dataset``) actually returns a bare ``ProvisionOutcome()``
    and writes nothing, rather than relying on reading the source and
    trusting it.
    """
    with (
        session_factory() as session,
        caplog.at_level(logging.WARNING, logger="smartmatch_api.pipeline_provisioning"),
    ):
        outcome = provision_on_accept(
            session,
            tenant_id=tenant_id,
            owning_unit_id=owning_unit_id,
            review_item_id=uuid.uuid4(),
            dataset="not-a-real-dataset",
            row_data={PROFESSIONAL_NAME_KEY: "Irrelevant Name"},
            accepted_at=datetime.now(UTC),
        )
        session.commit()

    assert outcome == ProvisionOutcome()
    assert caplog.records == []

    with engine.begin() as conn:
        account_count = conn.execute(
            text("SELECT COUNT(*) FROM user_account WHERE tenant_id = :tid"), {"tid": tenant_id}
        ).scalar_one()
        pipeline_count = conn.execute(
            text("SELECT COUNT(*) FROM pipeline_record WHERE tenant_id = :tid"), {"tid": tenant_id}
        ).scalar_one()
    assert account_count == 0
    assert pipeline_count == 0


# ---------------------------------------------------------------------------
# 17 — name convergence by case/whitespace, proven at composition level
# ---------------------------------------------------------------------------


def test_names_differing_only_by_case_or_whitespace_converge_on_one_account(
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    engine: Engine,
    session_factory: sessionmaker[Session],
) -> None:
    """``synthetic_professional_subject_id``'s ``.strip().casefold()`` folding, through this module.

    Card 2 proves the *derivation* folds case and whitespace; assertion 2 in
    this file only ever re-accepts an identical name, which would pass even
    if this module accidentally bypassed that folding. This test accepts
    three textually different spellings of the same person and proves the
    composition — this module calling the deriver, then
    ``ensure_account``/``link_to_unit`` — still converges on exactly one
    ``user_account`` and one relationship row.
    """
    base_name = f"Case Fold Professional {uuid.uuid4().hex[:8]}"
    spellings = [base_name, base_name.upper(), f"   {base_name.lower()}  "]

    outcomes = [
        _accept_professional(
            session_factory, tenant_id=tenant_id, owning_unit_id=owning_unit_id, name=spelling
        )
        for spelling in spellings
    ]

    subject_ids = {outcome.professional_subject_id for outcome in outcomes}
    assert len(subject_ids) == 1
    (subject_id,) = subject_ids

    with engine.begin() as conn:
        account_count = conn.execute(
            text("SELECT COUNT(*) FROM user_account WHERE id = :id"), {"id": subject_id}
        ).scalar_one()
        relationship_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM professional_unit_relationship "
                "WHERE tenant_id = :tid AND professional_id = :pid"
            ),
            {"tid": tenant_id, "pid": subject_id},
        ).scalar_one()

    assert account_count == 1
    assert relationship_count == 1
