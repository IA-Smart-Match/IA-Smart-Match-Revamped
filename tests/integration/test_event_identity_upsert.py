"""Deterministic identity, upsert, and the quarantine path (cards S4 and S5).

The plan's own acceptance lines for these two cards:

* S4 — "two synthetic sources with one deterministic key yield one event
  (integration); provenance fields never appear in title assertions."
* S5 — "unmapped tag round-trips to the queue and never surfaces in a read
  model (integration)."

Both are tested here through ``smartmatch_persistence.events``, because both
are statements about the *writer*: which statement it issues, and what it
leaves behind. What the database refuses regardless of the writer is
``test_event_schema_constraints.py``.

Every event below is synthetic. ``example.invalid`` is reserved by RFC 2606 and
nothing in this file, or in the module under test, opens a socket — G3 §9's
"pointing the adapter at live hosts remains prohibited" is not merely honored
here, there is no code path that could.

Requires a live database, and is skipped when none is reachable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest

pytest.importorskip("sqlalchemy")

from conftest import ensure_owning_unit
from smartmatch_domain.event_vocabulary import G3_VOCABULARY
from smartmatch_domain.events import (
    DateOnlyTime,
    EventProvenance,
    ExactTime,
    QuarantinedTag,
    UnresolvedTime,
)
from smartmatch_persistence.events import (
    ORIGIN_COORDINATOR_ENTRY,
    ORIGIN_EXTRACTION,
    EventNotPublishableError,
    EventRepository,
    ProvenanceRequiredError,
    quarantined_values,
)
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration

ON_DATE = date(2026, 9, 14)
ZONE = "America/Los_Angeles"

#: Two *different* sources describing the same event, which is the situation
#: ADR-0012's key exists for: "A department's events appear on the university
#: calendar, the department page, and an aggregator. The source domain differs
#: across all three; the host does not."
CALENDAR_SOURCE = EventProvenance(
    source_url="https://calendar.example.invalid/events/1",
    fetched_at=datetime(2026, 9, 1, 8, 0, tzinfo=UTC),
    extractor_version="synthetic-json-1",
)
DEPARTMENT_SOURCE = EventProvenance(
    source_url="https://department.example.invalid/news/fall-showcase",
    fetched_at=datetime(2026, 9, 2, 8, 0, tzinfo=UTC),
    extractor_version="synthetic-html-1",
)


@pytest.fixture
def repo() -> EventRepository:
    return EventRepository()


@pytest.fixture
def db_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@pytest.fixture
def unit_id(engine: Engine, tenant_id: uuid.UUID) -> uuid.UUID:
    with engine.begin() as conn:
        return ensure_owning_unit(conn, tenant_id)


@pytest.fixture(autouse=True)
def _clean_event_tables(engine: Engine, tenant_id):
    """Same arrangement, and the same reason, as ``test_event_schema_constraints``."""
    yield
    with engine.begin() as conn:
        for table in ("event_tag", "discovery_review_item", "event"):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})


# ---------------------------------------------------------------------------
# Card S4 — two sources, one key, one event.
# ---------------------------------------------------------------------------


def test_two_sources_describing_one_event_yield_one_row(
    tenant_id, unit_id, repo: EventRepository, db_session_factory, engine: Engine
) -> None:
    """The card's headline acceptance. Different URLs, different extractors,
    different fetch times, different title casing and punctuation — one event."""
    when = DateOnlyTime(on_date=ON_DATE, time_zone=ZONE)

    with db_session_factory() as session:
        first = repo.upsert(
            session,
            tenant_id=tenant_id,
            host_org_unit_id=unit_id,
            title="Fall Capstone Showcase",
            event_time=when,
            origin=ORIGIN_EXTRACTION,
            provenance=CALENDAR_SOURCE,
        )
        session.commit()

    with db_session_factory() as session:
        second = repo.upsert(
            session,
            tenant_id=tenant_id,
            host_org_unit_id=unit_id,
            # Same event, as a different page writes it: `normalize_title`
            # case-folds and replaces punctuation with a boundary.
            title="fall  capstone-showcase",
            event_time=when,
            origin=ORIGIN_EXTRACTION,
            provenance=DEPARTMENT_SOURCE,
        )
        session.commit()

    assert second == first

    with engine.begin() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM event WHERE tenant_id = :tid"), {"tid": tenant_id}
        ).scalar_one()
    assert count == 1


def test_the_second_source_updates_the_row_rather_than_inserting(
    tenant_id, unit_id, repo: EventRepository, db_session_factory, engine: Engine
) -> None:
    """ADR-0012: "the second updates the first rather than inserting"."""
    when = DateOnlyTime(on_date=ON_DATE, time_zone=ZONE)

    with db_session_factory() as session:
        event_id = repo.upsert(
            session,
            tenant_id=tenant_id,
            host_org_unit_id=unit_id,
            title="Fall Capstone Showcase",
            event_time=when,
            origin=ORIGIN_EXTRACTION,
            provenance=CALENDAR_SOURCE,
        )
        session.commit()
        repo.upsert(
            session,
            tenant_id=tenant_id,
            host_org_unit_id=unit_id,
            title="Fall Capstone Showcase",
            event_time=when,
            origin=ORIGIN_EXTRACTION,
            provenance=DEPARTMENT_SOURCE,
            description="Seniors present their capstone projects.",
        )
        session.commit()

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT source_url, extractor_version, description FROM event WHERE id = :id"),
            {"id": event_id},
        ).one()

    assert row.source_url == DEPARTMENT_SOURCE.source_url
    assert row.extractor_version == "synthetic-html-1"
    assert row.description == "Seniors present their capstone projects."


def test_provenance_never_appears_in_the_title(
    tenant_id, unit_id, repo: EventRepository, db_session_factory, engine: Engine
) -> None:
    """The card's second acceptance line, as an assertion about stored data.

    ADR-0012's Fix #4 defect was "Event titles included the name of the page
    they were scraped from". `upsert` takes title and provenance as separate
    parameters and there is no code path in this module or the domain that
    combines them — this checks the outcome rather than the absence.
    """
    with db_session_factory() as session:
        event_id = repo.upsert(
            session,
            tenant_id=tenant_id,
            host_org_unit_id=unit_id,
            title="Fall Capstone Showcase",
            event_time=DateOnlyTime(on_date=ON_DATE, time_zone=ZONE),
            origin=ORIGIN_EXTRACTION,
            provenance=CALENDAR_SOURCE,
        )
        session.commit()

    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT title, normalized_title, description, source_url, extractor_version "
                "FROM event WHERE id = :id"
            ),
            {"id": event_id},
        ).one()

    assert row.title == "Fall Capstone Showcase"
    assert row.normalized_title == "fall capstone showcase"
    assert row.description is None
    for display in (row.title, row.normalized_title):
        assert "calendar.example.invalid" not in display
        assert "synthetic-json-1" not in display
    assert row.source_url == CALENDAR_SOURCE.source_url


def test_the_same_title_on_a_different_date_is_a_different_event(
    tenant_id, unit_id, repo: EventRepository, db_session_factory
) -> None:
    """The date is part of the key, so a recurring series is not one row."""
    with db_session_factory() as session:
        first = repo.upsert(
            session,
            tenant_id=tenant_id,
            host_org_unit_id=unit_id,
            title="Weekly Workshop",
            event_time=DateOnlyTime(on_date=ON_DATE, time_zone=ZONE),
            origin=ORIGIN_COORDINATOR_ENTRY,
        )
        second = repo.upsert(
            session,
            tenant_id=tenant_id,
            host_org_unit_id=unit_id,
            title="Weekly Workshop",
            event_time=DateOnlyTime(on_date=date(2026, 9, 21), time_zone=ZONE),
            origin=ORIGIN_COORDINATOR_ENTRY,
        )
        session.commit()

    assert first != second


def test_the_key_uses_the_events_own_zone_not_the_utc_date(
    tenant_id, unit_id, repo: EventRepository, db_session_factory, engine: Engine
) -> None:
    """`resolved_date`'s reason for existing, proven end to end.

    An event at 2026-09-15T06:30Z in America/Los_Angeles happens on the 14th.
    Reading the UTC date would key it to the 15th, and the same event described
    by a second source from the other side of local midnight would then resolve
    to a *second* identity key — the duplicate class ADR-0012 closes, arriving
    through the one door the key itself left open.
    """
    with db_session_factory() as session:
        event_id = repo.upsert(
            session,
            tenant_id=tenant_id,
            host_org_unit_id=unit_id,
            title="Late Evening Panel",
            event_time=ExactTime(
                starts_at=datetime(2026, 9, 15, 6, 30, tzinfo=UTC), time_zone=ZONE
            ),
            origin=ORIGIN_COORDINATOR_ENTRY,
        )
        session.commit()

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT resolved_date, time_precision FROM event WHERE id = :id"),
            {"id": event_id},
        ).one()

    assert row.resolved_date == date(2026, 9, 14)
    assert row.time_precision == "exact"


def test_a_correction_from_exact_to_date_only_clears_the_instant(
    tenant_id, unit_id, repo: EventRepository, db_session_factory, engine: Engine
) -> None:
    """`_temporal_columns` names every column on every branch, and this is why.

    An UPDATE that omitted `starts_at` would leave the first extraction's
    instant on a row that has since become `date_only` — a fabricated instant
    surviving its own correction. `ck_event_temporal_shape` would also refuse
    it, so this is the writer and the constraint agreeing.
    """
    with db_session_factory() as session:
        event_id = repo.upsert(
            session,
            tenant_id=tenant_id,
            host_org_unit_id=unit_id,
            title="Ambiguous Start",
            event_time=ExactTime(
                starts_at=datetime(2026, 9, 14, 19, 30, tzinfo=UTC), time_zone=ZONE
            ),
            origin=ORIGIN_COORDINATOR_ENTRY,
        )
        session.commit()
        repo.upsert(
            session,
            tenant_id=tenant_id,
            host_org_unit_id=unit_id,
            title="Ambiguous Start",
            event_time=DateOnlyTime(on_date=ON_DATE, time_zone=ZONE),
            origin=ORIGIN_COORDINATOR_ENTRY,
        )
        session.commit()

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT starts_at, on_date, time_precision FROM event WHERE id = :id"),
            {"id": event_id},
        ).one()

    assert row.starts_at is None
    assert row.on_date == ON_DATE
    assert row.time_precision == "date_only"


def test_two_unresolved_events_insert_separately_and_stay_unkeyed(
    tenant_id, unit_id, repo: EventRepository, db_session_factory, engine: Engine
) -> None:
    """ADR-0012: an unresolved event "has no identity key and cannot be resolved
    against anything", so identical unresolved extractions do not deduplicate."""
    with db_session_factory() as session:
        first = repo.upsert(
            session,
            tenant_id=tenant_id,
            host_org_unit_id=unit_id,
            title="Date To Be Announced",
            event_time=UnresolvedTime(),
            origin=ORIGIN_EXTRACTION,
            provenance=CALENDAR_SOURCE,
        )
        second = repo.upsert(
            session,
            tenant_id=tenant_id,
            host_org_unit_id=unit_id,
            title="Date To Be Announced",
            event_time=UnresolvedTime(),
            origin=ORIGIN_EXTRACTION,
            provenance=DEPARTMENT_SOURCE,
        )
        session.commit()

    assert first != second

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT resolved_date, time_precision, publication_status FROM event "
                "WHERE tenant_id = :tid ORDER BY created_at"
            ),
            {"tid": tenant_id},
        ).all()

    assert len(rows) == 2
    for row in rows:
        assert row.resolved_date is None
        assert row.time_precision == "unresolved"
        assert row.publication_status == "unpublished"


def test_an_extraction_without_provenance_is_refused_before_any_statement(
    tenant_id, unit_id, repo: EventRepository, db_session_factory
) -> None:
    with db_session_factory() as session, pytest.raises(ProvenanceRequiredError):
        repo.upsert(
            session,
            tenant_id=tenant_id,
            host_org_unit_id=unit_id,
            title="Unsourced",
            event_time=DateOnlyTime(on_date=ON_DATE, time_zone=ZONE),
            origin=ORIGIN_EXTRACTION,
        )


def test_a_coordinator_entry_carrying_provenance_is_refused(
    tenant_id, unit_id, repo: EventRepository, db_session_factory
) -> None:
    with db_session_factory() as session, pytest.raises(ProvenanceRequiredError):
        repo.upsert(
            session,
            tenant_id=tenant_id,
            host_org_unit_id=unit_id,
            title="Typed In",
            event_time=DateOnlyTime(on_date=ON_DATE, time_zone=ZONE),
            origin=ORIGIN_COORDINATOR_ENTRY,
            provenance=CALENDAR_SOURCE,
        )


def test_a_manual_entry_uses_the_same_key_as_an_extraction(
    tenant_id, unit_id, repo: EventRepository, db_session_factory, engine: Engine
) -> None:
    """ADR-0012's closing line: "A coordinator typing an event is not exempt, or
    the duplicate class reopens through a second door."."""
    when = DateOnlyTime(on_date=ON_DATE, time_zone=ZONE)

    with db_session_factory() as session:
        typed = repo.upsert(
            session,
            tenant_id=tenant_id,
            host_org_unit_id=unit_id,
            title="Fall Capstone Showcase",
            event_time=when,
            origin=ORIGIN_COORDINATOR_ENTRY,
        )
        session.commit()
        extracted = repo.upsert(
            session,
            tenant_id=tenant_id,
            host_org_unit_id=unit_id,
            title="Fall Capstone Showcase",
            event_time=when,
            origin=ORIGIN_EXTRACTION,
            provenance=CALENDAR_SOURCE,
        )
        session.commit()

    assert extracted == typed

    with engine.begin() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM event WHERE tenant_id = :tid"), {"tid": tenant_id}
        ).scalar_one()
    assert count == 1


# ---------------------------------------------------------------------------
# Card S5 — vocabulary, quarantine, review queue.
# ---------------------------------------------------------------------------


def _make_event(repo: EventRepository, session, tenant_id, unit_id, title: str) -> uuid.UUID:
    return repo.upsert(
        session,
        tenant_id=tenant_id,
        host_org_unit_id=unit_id,
        title=title,
        event_time=DateOnlyTime(on_date=ON_DATE, time_zone=ZONE),
        origin=ORIGIN_COORDINATOR_ENTRY,
    )


def test_an_unmapped_tag_round_trips_to_the_queue_and_not_to_the_read_model(
    tenant_id, unit_id, repo: EventRepository, db_session_factory, engine: Engine
) -> None:
    """The card's acceptance line, both halves in one test."""
    with db_session_factory() as session:
        event_id = _make_event(repo, session, tenant_id, unit_id, "Tagged Event")
        resolutions = repo.record_tags(
            session,
            tenant_id=tenant_id,
            event_id=event_id,
            owning_unit_id=unit_id,
            # One approved term (§6.2) and one deliberately cut candidate.
            raw_values=["Hackathon", "Networking Mixer"],
            vocabulary=G3_VOCABULARY,
        )
        session.commit()

        terms = repo.matchable_terms(session, tenant_id=tenant_id, event_id=event_id)

    assert quarantined_values(resolutions) == ("Networking Mixer",)
    assert terms == ("hackathon",)

    with engine.begin() as conn:
        queued = conn.execute(
            text(
                "SELECT raw_value, kind, status, vocabulary_version FROM discovery_review_item "
                "WHERE event_id = :id"
            ),
            {"id": event_id},
        ).all()

    assert len(queued) == 1
    assert queued[0].raw_value == "Networking Mixer"
    assert queued[0].kind == "unmapped_tag"
    assert queued[0].status == "pending"
    assert queued[0].vocabulary_version == G3_VOCABULARY.version


def test_the_quarantined_value_is_stored_exactly_as_received(
    tenant_id, unit_id, repo: EventRepository, db_session_factory, engine: Engine
) -> None:
    """`QuarantinedTag.raw_value` is "the extracted text exactly as received,
    unnormalized", because a reviewer needs to see what was on the page."""
    with db_session_factory() as session:
        event_id = _make_event(repo, session, tenant_id, unit_id, "Odd Casing")
        repo.record_tags(
            session,
            tenant_id=tenant_id,
            event_id=event_id,
            owning_unit_id=unit_id,
            raw_values=["Sponsor  Contact!"],
            vocabulary=G3_VOCABULARY,
        )
        session.commit()

    with engine.begin() as conn:
        stored = conn.execute(
            text("SELECT raw_value, term FROM event_tag WHERE event_id = :id"),
            {"id": event_id},
        ).one()

    assert stored.raw_value == "Sponsor  Contact!"
    assert stored.term is None


def test_re_resolving_the_same_extraction_does_not_duplicate_or_re_queue(
    tenant_id, unit_id, repo: EventRepository, db_session_factory, engine: Engine
) -> None:
    """Re-crawling is the normal case, not the exception (ADR-0012).

    Both `event_tag` inserts and the `discovery_review_item` insert are
    ON CONFLICT DO NOTHING, and the counter is recomputed rather than
    incremented — so a second pass leaves the row set and the number identical.
    """
    values = ["Hackathon", "Datathon", "Symposium"]

    with db_session_factory() as session:
        event_id = _make_event(repo, session, tenant_id, unit_id, "Repeated Extraction")
        repo.record_tags(
            session,
            tenant_id=tenant_id,
            event_id=event_id,
            owning_unit_id=unit_id,
            raw_values=values,
            vocabulary=G3_VOCABULARY,
        )
        session.commit()
        repo.record_tags(
            session,
            tenant_id=tenant_id,
            event_id=event_id,
            owning_unit_id=unit_id,
            raw_values=values,
            vocabulary=G3_VOCABULARY,
        )
        session.commit()

    with engine.begin() as conn:
        tags = conn.execute(
            text("SELECT count(*) FROM event_tag WHERE event_id = :id"), {"id": event_id}
        ).scalar_one()
        queued = conn.execute(
            text("SELECT count(*) FROM discovery_review_item WHERE event_id = :id"),
            {"id": event_id},
        ).scalar_one()
        counter = conn.execute(
            text("SELECT quarantined_tag_count FROM event WHERE id = :id"), {"id": event_id}
        ).scalar_one()

    assert tags == 3
    assert queued == 2
    assert counter == 2


def test_the_counter_tracks_the_rows_it_counts(
    tenant_id, unit_id, repo: EventRepository, db_session_factory, engine: Engine
) -> None:
    with db_session_factory() as session:
        event_id = _make_event(repo, session, tenant_id, unit_id, "Counted")
        repo.record_tags(
            session,
            tenant_id=tenant_id,
            event_id=event_id,
            owning_unit_id=unit_id,
            raw_values=["Workshop", "Conference"],
            vocabulary=G3_VOCABULARY,
        )
        session.commit()

    with engine.begin() as conn:
        counter = conn.execute(
            text("SELECT quarantined_tag_count FROM event WHERE id = :id"), {"id": event_id}
        ).scalar_one()
    assert counter == 0


def test_a_quarantined_tag_blocks_publication_and_a_clean_event_publishes(
    tenant_id, unit_id, repo: EventRepository, db_session_factory, engine: Engine
) -> None:
    """ "Unpublished means: unresolved dates, or quarantined tags", through the writer."""
    with db_session_factory() as session:
        blocked = _make_event(repo, session, tenant_id, unit_id, "Has An Unmapped Tag")
        clean = _make_event(repo, session, tenant_id, unit_id, "All Terms Mapped")
        repo.record_tags(
            session,
            tenant_id=tenant_id,
            event_id=blocked,
            owning_unit_id=unit_id,
            raw_values=["Info Session"],
            vocabulary=G3_VOCABULARY,
        )
        repo.record_tags(
            session,
            tenant_id=tenant_id,
            event_id=clean,
            owning_unit_id=unit_id,
            raw_values=["Career Panel"],
            vocabulary=G3_VOCABULARY,
        )
        session.commit()

        with pytest.raises(EventNotPublishableError, match="quarantined"):
            repo.publish(session, tenant_id=tenant_id, event_id=blocked)

        repo.publish(session, tenant_id=tenant_id, event_id=clean)
        session.commit()

    with engine.begin() as conn:
        statuses = dict(
            conn.execute(
                text("SELECT id, publication_status FROM event WHERE id IN (:a, :b)"),
                {"a": blocked, "b": clean},
            ).all()
        )

    assert statuses[blocked] == "unpublished"
    assert statuses[clean] == "published"


def test_an_unresolved_event_cannot_be_published_through_the_writer(
    tenant_id, unit_id, repo: EventRepository, db_session_factory
) -> None:
    """ADR-0010 rule 2 at the application layer; the CHECK holds the same line."""
    with db_session_factory() as session:
        event_id = repo.upsert(
            session,
            tenant_id=tenant_id,
            host_org_unit_id=unit_id,
            title="No Date Anywhere On The Page",
            event_time=UnresolvedTime(),
            origin=ORIGIN_EXTRACTION,
            provenance=CALENDAR_SOURCE,
        )
        session.commit()

        with pytest.raises(EventNotPublishableError, match="no resolved date"):
            repo.publish(session, tenant_id=tenant_id, event_id=event_id)


def test_publishing_an_event_in_another_tenant_is_refused(
    tenant_id, unit_id, repo: EventRepository, db_session_factory
) -> None:
    """The tenant filter is on the read, not only on the write."""
    with db_session_factory() as session:
        event_id = _make_event(repo, session, tenant_id, unit_id, "Someone Elses")
        session.commit()

        with pytest.raises(EventNotPublishableError, match="no event"):
            repo.publish(session, tenant_id=uuid.uuid4(), event_id=event_id)


def test_every_deliberately_cut_candidate_reaches_the_queue(
    tenant_id, unit_id, repo: EventRepository, db_session_factory, engine: Engine
) -> None:
    """G3 §6.1: quarantine volume "is evidence of which terms were actually
    needed". This is that evidence path working end to end, for all eight."""
    cut = [
        "datathon",
        "symposium",
        "industry night",
        "networking mixer",
        "info session",
        "workshop facilitator",
        "moderator",
        "sponsor contact",
    ]

    with db_session_factory() as session:
        event_id = _make_event(repo, session, tenant_id, unit_id, "Everything Cut")
        resolutions = repo.record_tags(
            session,
            tenant_id=tenant_id,
            event_id=event_id,
            owning_unit_id=unit_id,
            raw_values=cut,
            vocabulary=G3_VOCABULARY,
        )
        session.commit()

        terms = repo.matchable_terms(session, tenant_id=tenant_id, event_id=event_id)

    assert all(isinstance(r, QuarantinedTag) for r in resolutions)
    assert terms == ()

    with engine.begin() as conn:
        queued = conn.execute(
            text(
                "SELECT raw_value FROM discovery_review_item WHERE event_id = :id "
                "ORDER BY raw_value"
            ),
            {"id": event_id},
        ).scalars()
    assert sorted(queued) == sorted(cut)
