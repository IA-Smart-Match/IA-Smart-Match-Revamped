"""The two halves of the ``pipeline_record.opportunity_event_id`` audit, on real rows.

``verify_pilot_dataset``'s ``pipeline_record_names_an_event`` used to ask one
question of every journey — "names an event" — and failed deterministically on
a complete dataset, because the review-accept fan-out deliberately writes
journeys whose opportunity is ``uuid5(tenant, review_item)``: an id *about* the
accepted events review item, which no ``event`` row ever carries.

The column's audit now splits by referent:

* ``pipeline_record_names_an_event`` — every journey whose opportunity is not a
  review-item-derived id must name a real event. A dangling hand-off journey
  still fails here; the generated Phase-B rows and the
  ``CbaHandoffRepository`` rows are the population it means.
* ``synthetic_fanout_names_a_derived_opportunity`` — every journey that names
  no event must name a derived id. A record naming neither is corruption, not
  fan-out.

These tests put all three shapes in one tenant — a journey on a real event, a
journey on the derived id of an accepted events review item, and one that names
neither — and count what each check says about them.
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest import ensure_event, ensure_owning_unit, unique_subject
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[2]

# `tools/` on the path rather than the repository root — the same shape the
# unit suite already imports these modules under.
sys.path.insert(0, str(REPO_ROOT / "tools"))

from smartmatch_domain.synthetic_pilot import synthetic_opportunity_event_id  # noqa: E402
from verify_pilot_dataset import CROSS_TABLE_CHECKS, PipelineOpportunityCheck  # noqa: E402

pytestmark = pytest.mark.integration


def _make_user(conn, tenant_id: uuid.UUID, stem: str) -> uuid.UUID:
    user_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO user_account (id, tenant_id, external_subject, email) "
            "VALUES (:id, :tenant_id, :sub, :email)"
        ),
        {
            "id": user_id,
            "tenant_id": tenant_id,
            # `unique_subject`'s suffix is per run, not per call — the stem
            # carries the distinctness between the two accounts this makes.
            "sub": unique_subject(f"pipeline-checks-{stem}"),
            "email": f"{user_id.hex[:8]}@example.edu",
        },
    )
    return user_id


def _make_accepted_events_review_item(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    """One accepted ``events`` review item — the shape ``_provision_event`` ran on."""
    unit_id = ensure_owning_unit(conn, tenant_id)
    job_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO job (id, tenant_id, command_type, status, owning_unit_id) "
            "VALUES (:id, :tenant_id, 'import.create', 'succeeded', :unit_id)"
        ),
        {"id": job_id, "tenant_id": tenant_id, "unit_id": unit_id},
    )
    batch_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO import_batch "
            "(id, tenant_id, owning_unit_id, job_id, dataset, row_count, dry_run) "
            "VALUES (:id, :tenant_id, :unit_id, :job_id, 'events', 1, false)"
        ),
        {"id": batch_id, "tenant_id": tenant_id, "unit_id": unit_id, "job_id": job_id},
    )
    item_id = uuid.uuid4()
    decided_by = _make_user(conn, tenant_id, "decider")
    conn.execute(
        text(
            "INSERT INTO review_item "
            "(id, tenant_id, import_batch_id, row_index, row_data, status, "
            "decided_at, decided_by) "
            'VALUES (:id, :tenant_id, :batch_id, 0, \'{"title": "Example"}\', '
            "'accepted', :decided_at, :decided_by)"
        ),
        {
            "id": item_id,
            "tenant_id": tenant_id,
            "batch_id": batch_id,
            "decided_at": datetime.now(UTC),
            "decided_by": decided_by,
        },
    )
    return item_id


def _make_journey(
    conn, tenant_id: uuid.UUID, unit_id: uuid.UUID, subject_id: uuid.UUID, opportunity: uuid.UUID
) -> None:
    conn.execute(
        text(
            "INSERT INTO pipeline_record "
            "(id, tenant_id, owning_unit_id, subject_id, opportunity_event_id, "
            "matched_provenance) "
            "VALUES (:id, :tenant_id, :unit_id, :subject_id, :opportunity, "
            "'synthetic / coordinator-accepted')"
        ),
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "unit_id": unit_id,
            "subject_id": subject_id,
            "opportunity": opportunity,
        },
    )


@pytest.fixture
def journeys(engine: Engine, tenant_id: uuid.UUID):
    """One tenant holding all three opportunity shapes, cleaned up afterwards.

    ``pipeline_record`` is not in conftest's ``_TENANT_SCOPED_TABLES`` —
    the writers that produce it do not run under this suite, so the teardown
    that knows the table is this file's own. ``job``'s cascade carries the
    ``import_batch``/``review_item`` rows away with the tenant.
    """
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
        subject_id = _make_user(conn, tenant_id, "subject")
        review_item_id = _make_accepted_events_review_item(conn, tenant_id)
        real_event = ensure_event(conn, tenant_id, slug="pipeline-checks")
        derived = synthetic_opportunity_event_id(tenant_id=tenant_id, review_item_id=review_item_id)
        bogus = uuid.uuid4()  # names neither an event nor any derived id
        _make_journey(conn, tenant_id, unit_id, subject_id, real_event)
        _make_journey(conn, tenant_id, unit_id, subject_id, derived)
        _make_journey(conn, tenant_id, unit_id, subject_id, bogus)
    yield {"unit_id": unit_id, "real_event": real_event, "derived": derived, "bogus": bogus}
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM pipeline_record WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        )


def _check(name: str) -> PipelineOpportunityCheck:
    check = next(check for check in CROSS_TABLE_CHECKS if check.name == name)
    assert isinstance(check, PipelineOpportunityCheck)
    return check


def test_event_side_counts_the_dangling_journey_and_not_the_fanout(
    engine: Engine,
    session_factory: sessionmaker[Session],
    tenant_id: uuid.UUID,
    journeys,
) -> None:
    """A hand-off journey that dangles is still a violation; the fan-out is not."""
    with session_factory() as session:
        result = _check("pipeline_record_names_an_event").counts(
            session, tenant_id=tenant_id, unit_id=journeys["unit_id"]
        )
    # Population 2: the real-event journey and the bogus one — the derived
    # fan-out is not asked to name an event. Violation 1: the bogus row.
    assert (result.population, result.violations) == (2, 1)
    assert result.failed


def test_fanout_side_counts_only_eventless_journeys_and_flags_the_corrupt_one(
    engine: Engine,
    session_factory: sessionmaker[Session],
    tenant_id: uuid.UUID,
    journeys,
) -> None:
    """Naming no event is legal only for an id an accepted events item derives."""
    with session_factory() as session:
        result = _check("synthetic_fanout_names_a_derived_opportunity").counts(
            session, tenant_id=tenant_id, unit_id=journeys["unit_id"]
        )
    # Population 2: the derived fan-out and the bogus one. Violation 1: the
    # bogus row, which no accepted events review item derives.
    assert (result.population, result.violations) == (2, 1)
    assert result.failed


def test_both_checks_pass_when_every_opportunity_resolves(
    engine: Engine,
    session_factory: sessionmaker[Session],
    tenant_id: uuid.UUID,
    journeys,
) -> None:
    """The dataset the tool verifies: real events and derived ids, nothing else."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM pipeline_record "
                "WHERE tenant_id = :tenant_id AND opportunity_event_id = :bogus"
            ),
            {"tenant_id": tenant_id, "bogus": journeys["bogus"]},
        )
    with session_factory() as session:
        results = {
            check.name: check.counts(session, tenant_id=tenant_id, unit_id=journeys["unit_id"])
            for check in CROSS_TABLE_CHECKS
            if isinstance(check, PipelineOpportunityCheck)
        }
    assert not results["pipeline_record_names_an_event"].failed
    assert results["pipeline_record_names_an_event"].population == 1
    assert not results["synthetic_fanout_names_a_derived_opportunity"].failed
    assert results["synthetic_fanout_names_a_derived_opportunity"].population == 1
