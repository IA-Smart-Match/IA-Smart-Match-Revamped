"""The fixture-to-database seam, against a real PostgreSQL.

``tests/unit/test_fixture_ingest.py`` proves the reader produces the right
values in memory and persists nothing. ``tests/integration/
test_event_identity_upsert.py`` proves the repository writes the right rows
when handed values directly. Neither can see the thing this file is about:
that ``smartmatch_worker.event_ingest`` carries the first into the second
without losing, inventing, or flattening anything on the way.

Every assertion below is about a property an ADR or a signed artifact fixed,
not about the fixture tree's contents for their own sake:

* an unresolved date stays unresolved and stays unkeyed (ADR-0010 rule 2,
  ADR-0012);
* an unmapped tag lands in ``discovery_review_item`` rather than being dropped
  (ADR-0012, G3 §5), and raises ``event.quarantined_tag_count`` so
  ``ck_event_publishable`` refuses that event;
* provenance is written to its own columns and names the document actually
  read, never the URL the document advertises (ADR-0012);
* nothing publishes itself (G3 §5's first-seen approval rule);
* the counts the seam reports are the counts the database holds (ADR-0011 —
  a summary that disagreed with the rows would be the accountable-number
  defect arriving through a return value).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")

from conftest import ensure_owning_unit
from smartmatch_worker.event_ingest import (
    EXTRACTOR_VERSION,
    FIXTURE_URL_SCHEME,
    IngestSummary,
    ingest_fixture_directory_into_events,
)
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "pilot_events"

#: The zone the synthetic sources declare. Passed through to the Stage 0
#: parsers unchanged; an unknown name is a refusal there, never a substitution.
SOURCE_ZONE = "America/Los_Angeles"

#: A fixed instant, not ``datetime.now``. It is written to ``event.fetched_at``
#: and compared below, and a generated one would make the comparison a
#: tautology while also making two runs of this file disagree about a column
#: whose whole purpose is saying when a reading happened.
FETCHED_AT = datetime(2026, 9, 3, 17, 0, tzinfo=UTC)

#: What the tree contains, restated here so a fixture edit fails a test rather
#: than silently changing what this file proves. See
#: ``tests/fixtures/pilot_events/README.md``.
DATED_TITLE = "Spring Analytics Hackathon"
UNDATED_TITLE = "Capstone Showcase - date to be announced"
QUARANTINING_TITLE = "Autumn Data Ethics Seminar"
UNMAPPED_VALUE = "Underwater Basket Weaving"


@pytest.fixture
def host_unit_id(engine: Engine, tenant_id: uuid.UUID) -> uuid.UUID:
    """The org unit these synthetic events are hosted by.

    ``ensure_owning_unit`` rather than a fourth way of making a unit: the
    helper already exists for exactly this reason, and a per-file variant is
    how two tests come to disagree about what a unit looks like.
    """
    with engine.begin() as conn:
        return ensure_owning_unit(conn, tenant_id)


@pytest.fixture
def ingested(
    session_factory: sessionmaker[Session],
    tenant_id: uuid.UUID,
    host_unit_id: uuid.UUID,
) -> Iterator[tuple[IngestSummary, Session]]:
    """Run the ingest once and hand back its summary and an open session.

    The session is committed here because the assertions read the rows back
    through it; the ingest itself commits nothing, which is the property
    :meth:`TestTheSeamOwnsNoTransaction.test_the_ingest_does_not_commit_on_its_own`
    states directly.
    """
    session = session_factory()
    try:
        summary = ingest_fixture_directory_into_events(
            session,
            tenant_id=tenant_id,
            host_org_unit_id=host_unit_id,
            directory=FIXTURES,
            root=FIXTURES,
            source_time_zone=SOURCE_ZONE,
            fetched_at=FETCHED_AT,
        )
        session.commit()
        yield summary, session
    finally:
        session.rollback()
        session.close()


def _event_row(session: Session, tenant_id: uuid.UUID, title: str):
    return session.execute(
        text(
            "SELECT id, title, description, starts_at, on_date, time_zone, "
            "time_precision, resolved_date, publication_status, review_status, "
            "quarantined_tag_count, origin, source_url, fetched_at, extractor_version "
            "FROM event WHERE tenant_id = :tid AND title = :title"
        ),
        {"tid": tenant_id, "title": title},
    ).one()


class TestWhatLanded:
    """Three events from two documents, each keeping its own shape."""

    def test_the_summary_counts_documents_read_and_refused_separately(
        self, ingested: tuple[IngestSummary, Session]
    ):
        """The README is skipped, not refused, and nothing here is malformed.

        ``documents_refused`` is asserted as ``0`` rather than left unmentioned:
        a field nobody checks is a field that can start counting silently.
        """
        summary, _ = ingested

        assert summary.documents_read == 2
        assert summary.documents_refused == 0

    def test_every_candidate_became_a_row_including_the_unkeyed_one(
        self, ingested: tuple[IngestSummary, Session], tenant_id: uuid.UUID
    ):
        """An event with no resolvable date is written, not dropped."""
        summary, session = ingested
        stored = session.execute(
            text("SELECT count(*) FROM event WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        ).scalar_one()

        assert summary.events_written == 3
        assert stored == 3

    def test_the_summary_agrees_with_the_rows(
        self, ingested: tuple[IngestSummary, Session], tenant_id: uuid.UUID
    ):
        """ADR-0011: a reported number is read from the thing it counts.

        Each count is re-derived from SQL rather than trusted, because a
        summary that drifted from the database would be exactly the
        accountable-number defect, arriving through a return value instead of
        through a dashboard.
        """
        summary, session = ingested

        unkeyed = session.execute(
            text(
                "SELECT count(*) FROM event WHERE tenant_id = :tid "
                "AND time_precision = 'unresolved'"
            ),
            {"tid": tenant_id},
        ).scalar_one()
        quarantined = session.execute(
            text(
                "SELECT count(*) FROM event_tag WHERE tenant_id = :tid "
                "AND resolution = 'quarantined'"
            ),
            {"tid": tenant_id},
        ).scalar_one()

        assert summary.events_unkeyed == unkeyed == 1
        assert summary.quarantined_tags == quarantined == 1


class TestTemporalPrecisionSurvives:
    """ADR-0010: three precisions, three shapes, no collapsing."""

    def test_an_exact_source_keeps_its_instant_and_its_zone(
        self, ingested: tuple[IngestSummary, Session], tenant_id: uuid.UUID
    ):
        _, session = ingested
        row = _event_row(session, tenant_id, DATED_TITLE)

        assert row.time_precision == "exact"
        assert row.starts_at is not None
        assert row.on_date is None
        assert row.time_zone == SOURCE_ZONE

    def test_a_date_only_source_gets_no_fabricated_instant(
        self, ingested: tuple[IngestSummary, Session], tenant_id: uuid.UUID
    ):
        """The 3 AM / 7 AM defect, closed at the column level.

        ``starts_at IS NULL`` is the whole point: a ``date_only`` source
        collapsed to midnight and re-rendered in another zone is what ADR-0010
        was written about.
        """
        _, session = ingested
        row = _event_row(session, tenant_id, QUARANTINING_TITLE)

        assert row.time_precision == "date_only"
        assert row.starts_at is None
        assert row.on_date is not None

    def test_an_unresolved_source_has_no_date_and_no_identity_key(
        self, ingested: tuple[IngestSummary, Session], tenant_id: uuid.UUID
    ):
        """ADR-0012: an unresolved event has no identity key at all.

        ``resolved_date IS NULL`` is both halves of that at once — it is the
        key's date component, and ``ck_event_identity_iff_resolved`` ties it to
        the precision — so this asserts the absence rather than a sentinel
        standing in for it.
        """
        _, session = ingested
        row = _event_row(session, tenant_id, UNDATED_TITLE)

        assert row.time_precision == "unresolved"
        assert row.starts_at is None
        assert row.on_date is None
        assert row.time_zone is None
        assert row.resolved_date is None


class TestQuarantineReachesTheQueue:
    """ADR-0012 and G3 §5: an unmapped value is escalated, never discarded."""

    def test_the_unmapped_value_is_stored_verbatim_as_a_tag(
        self, ingested: tuple[IngestSummary, Session], tenant_id: uuid.UUID
    ):
        """Unnormalized, so a reviewer sees what was actually on the page."""
        _, session = ingested
        rows = session.execute(
            text(
                "SELECT raw_value, term, vocabulary_version FROM event_tag "
                "WHERE tenant_id = :tid AND resolution = 'quarantined'"
            ),
            {"tid": tenant_id},
        ).all()

        assert [row.raw_value for row in rows] == [UNMAPPED_VALUE]
        # No term to match on, which is ADR-0012's rule enforced by the row's
        # own shape rather than by a query remembering to filter.
        assert rows[0].term is None
        assert rows[0].vocabulary_version

    def test_it_also_lands_one_review_item_for_a_human(
        self, ingested: tuple[IngestSummary, Session], tenant_id: uuid.UUID
    ):
        """``discovery_review_item``, not ``review_item`` — G3 §5's whole point.

        ``review_item`` cascades from ``import_batch``, so a discovery finding
        parked on it would be deleted along with an unrelated import.
        """
        _, session = ingested
        rows = session.execute(
            text(
                "SELECT kind, raw_value, status, decided_at, decided_by "
                "FROM discovery_review_item WHERE tenant_id = :tid"
            ),
            {"tid": tenant_id},
        ).all()

        assert len(rows) == 1
        assert rows[0].kind == "unmapped_tag"
        assert rows[0].raw_value == UNMAPPED_VALUE
        assert rows[0].status == "pending"
        assert rows[0].decided_at is None
        assert rows[0].decided_by is None

    def test_the_mapped_values_on_the_same_event_still_map(
        self, ingested: tuple[IngestSummary, Session], tenant_id: uuid.UUID
    ):
        """One bad tag does not poison the event's good ones.

        Resolution partitions; it does not reject a whole extraction because
        part of it was unrecognized.
        """
        _, session = ingested
        event = _event_row(session, tenant_id, QUARANTINING_TITLE)
        terms = session.execute(
            text(
                "SELECT term FROM event_tag WHERE tenant_id = :tid AND event_id = :eid "
                "AND resolution = 'mapped' ORDER BY term"
            ),
            {"tid": tenant_id, "eid": event.id},
        ).scalars()

        assert list(terms) == ["career panel"]

    def test_the_counter_that_blocks_publication_is_raised(
        self, ingested: tuple[IngestSummary, Session], tenant_id: uuid.UUID
    ):
        """``ck_event_publishable`` reads this column, so it has to be right."""
        _, session = ingested

        assert _event_row(session, tenant_id, QUARANTINING_TITLE).quarantined_tag_count == 1
        assert _event_row(session, tenant_id, DATED_TITLE).quarantined_tag_count == 0


class TestProvenanceIsStructuredAndHonest:
    """ADR-0012: separate columns, and a claim this repository can defend."""

    def test_provenance_names_the_document_read_not_the_url_it_advertises(
        self, ingested: tuple[IngestSummary, Session], tenant_id: uuid.UUID
    ):
        """The fixture advertises an ``example.edu`` URL nothing ever fetched.

        Recording that string would be a fabricated fetch. What is recorded is
        the in-repo document, relative to the ingest root, under a scheme that
        cannot be mistaken for something retrieved.
        """
        _, session = ingested
        row = _event_row(session, tenant_id, DATED_TITLE)

        assert row.origin == "extraction"
        assert row.source_url == f"{FIXTURE_URL_SCHEME}engineering_calendar.ics"
        assert not row.source_url.startswith(("http://", "https://"))
        assert row.fetched_at == FETCHED_AT
        assert row.extractor_version == EXTRACTOR_VERSION

    def test_provenance_is_never_folded_into_the_title_or_description(
        self, ingested: tuple[IngestSummary, Session], tenant_id: uuid.UUID
    ):
        """The defect ADR-0012 names: a title carrying the name of its page.

        Asserted against every stored row rather than the one this file
        happens to be about, because the rule is about the write path, not
        about one document.
        """
        _, session = ingested
        rows = session.execute(
            text("SELECT title, description FROM event WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        ).all()

        for row in rows:
            assert FIXTURE_URL_SCHEME not in row.title
            assert "example.edu" not in row.title
            assert EXTRACTOR_VERSION not in row.title
            if row.description is not None:
                assert FIXTURE_URL_SCHEME not in row.description
                assert EXTRACTOR_VERSION not in row.description


class TestNothingPublishesItself:
    """G3 §5: every first-seen event requires human approval."""

    def test_every_row_lands_unpublished_and_pending(
        self, ingested: tuple[IngestSummary, Session], tenant_id: uuid.UUID
    ):
        _, session = ingested
        rows = session.execute(
            text("SELECT publication_status, review_status FROM event WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        ).all()

        assert len(rows) == 3
        assert {row.publication_status for row in rows} == {"unpublished"}
        assert {row.review_status for row in rows} == {"pending"}


class TestIdentityHoldsAcrossRuns:
    """ADR-0012: the same document read twice is the same event, not two."""

    def test_a_second_ingest_updates_the_keyed_events_rather_than_duplicating(
        self,
        ingested: tuple[IngestSummary, Session],
        session_factory: sessionmaker[Session],
        tenant_id: uuid.UUID,
        host_unit_id: uuid.UUID,
    ):
        """The keyed rows converge; the unkeyed one cannot, and does not pretend to.

        Both halves are asserted because both are ADR-0012 decisions rather
        than accidents. A resolved event has a key, so the second read lands on
        ``ON CONFLICT ON CONSTRAINT uq_event_identity`` and updates. An
        unresolved event has no key — "two events with unknown dates are not
        evidence of being the same event" — so it inserts again, which is the
        honest answer and not a de-duplication bug to file.
        """
        _, _first_session = ingested
        second = session_factory()
        try:
            summary = ingest_fixture_directory_into_events(
                second,
                tenant_id=tenant_id,
                host_org_unit_id=host_unit_id,
                directory=FIXTURES,
                root=FIXTURES,
                source_time_zone=SOURCE_ZONE,
                fetched_at=FETCHED_AT,
            )
            second.commit()

            assert summary.events_written == 3
            keyed = second.execute(
                text(
                    "SELECT count(*) FROM event WHERE tenant_id = :tid "
                    "AND resolved_date IS NOT NULL"
                ),
                {"tid": tenant_id},
            ).scalar_one()
            unkeyed = second.execute(
                text("SELECT count(*) FROM event WHERE tenant_id = :tid AND resolved_date IS NULL"),
                {"tid": tenant_id},
            ).scalar_one()

            assert keyed == 2
            assert unkeyed == 2
        finally:
            second.rollback()
            second.close()

    def test_re_resolving_the_same_tags_queues_no_second_review_item(
        self,
        ingested: tuple[IngestSummary, Session],
        session_factory: sessionmaker[Session],
        tenant_id: uuid.UUID,
        host_unit_id: uuid.UUID,
    ):
        """A reviewer must not see the same value twice for the same event.

        ``uq_discovery_review_item_event_value`` is what makes that true, and
        the ``ON CONFLICT DO NOTHING`` against it is what keeps a re-read from
        re-queueing a value somebody may already have decided.
        """
        _, _first_session = ingested
        second = session_factory()
        try:
            ingest_fixture_directory_into_events(
                second,
                tenant_id=tenant_id,
                host_org_unit_id=host_unit_id,
                directory=FIXTURES,
                root=FIXTURES,
                source_time_zone=SOURCE_ZONE,
                fetched_at=FETCHED_AT,
            )
            second.commit()
            queued = second.execute(
                text(
                    "SELECT count(*) FROM discovery_review_item WHERE tenant_id = :tid "
                    "AND raw_value = :value"
                ),
                {"tid": tenant_id, "value": UNMAPPED_VALUE},
            ).scalar_one()

            assert queued == 1
        finally:
            second.rollback()
            second.close()


class TestTheSeamOwnsNoTransaction:
    """Boundaries belong to the caller, as in every repository in the package."""

    def test_the_ingest_does_not_commit_on_its_own(
        self,
        session_factory: sessionmaker[Session],
        tenant_id: uuid.UUID,
        host_unit_id: uuid.UUID,
    ):
        """Rolled back afterwards, nothing survives.

        This is what lets a caller compose an ingest with other work and
        discard the whole thing on failure — the same guarantee
        ``handlers.py`` documents for the executor-owned session.
        """
        session = session_factory()
        try:
            ingest_fixture_directory_into_events(
                session,
                tenant_id=tenant_id,
                host_org_unit_id=host_unit_id,
                directory=FIXTURES,
                root=FIXTURES,
                source_time_zone=SOURCE_ZONE,
                fetched_at=FETCHED_AT,
            )
            session.rollback()
            survivors = session.execute(
                text("SELECT count(*) FROM event WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            ).scalar_one()

            assert survivors == 0
        finally:
            session.rollback()
            session.close()
