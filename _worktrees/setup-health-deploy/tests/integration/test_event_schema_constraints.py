"""What migration ``0017``'s event tables refuse, against a real PostgreSQL instance.

Card S3's test line is "constraints reject publishable-unresolved rows
(integration, CI-proof)", and ADR-0010 is explicit that this belongs in the
database rather than in a validator: rule 2 is "a state-machine constraint, not
a validation warning ... Validation is advisory and is applied by whoever
remembers to call it."

So every test here attempts the forbidden write and requires the database to
refuse it. None of them calls ``smartmatch_persistence.events`` — that module
guards the same rules in application code, and a test that went through it
would prove the guard rather than the constraint. The upsert and quarantine
behaviour it *does* own is in ``test_event_identity_upsert.py``.

Requires a live database, and is skipped when none is reachable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest

pytest.importorskip("sqlalchemy")

from conftest import ensure_owning_unit, unique_subject
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration

#: A fixed local date, not `date.today()`: it lands in the identity key, and a
#: generated one would make these inserts non-reproducible across midnight.
ON_DATE = date(2026, 9, 14)
STARTS_AT = datetime(2026, 9, 14, 19, 30, tzinfo=UTC)
ZONE = "America/Los_Angeles"


@pytest.fixture(autouse=True)
def _clean_event_tables(engine: Engine, tenant_id):
    """Delete this file's rows before ``tenant_id`` tears down its own.

    `event.host_org_unit_id` is `ON DELETE RESTRICT`, so a row left behind here
    would make `conftest.py`'s teardown fail on the `org_unit` delete. Ordered
    child-before-parent; `event_tag` and `discovery_review_item` would cascade
    anyway and are deleted explicitly so a failure names the table it happened
    in.
    """
    yield
    with engine.begin() as conn:
        for table in ("attendance_record", "event_tag", "discovery_review_item", "event"):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})


# ---------------------------------------------------------------------------
# Row builders. Each takes the values actually under test as keywords and
# defaults everything else to a row the constraints accept, so a test body
# contains only the value in question.
# ---------------------------------------------------------------------------


def _insert_event(
    conn,
    tenant_id: uuid.UUID,
    *,
    title: str = "Synthetic Capstone Showcase",
    normalized_title: str | None = None,
    starts_at: datetime | None = None,
    on_date: date | None = ON_DATE,
    time_zone: str | None = ZONE,
    time_precision: str = "date_only",
    resolved_date: date | None = ON_DATE,
    publication_status: str = "unpublished",
    review_status: str = "pending",
    quarantined_tag_count: int = 0,
    origin: str = "coordinator_entry",
    source_url: str | None = None,
    fetched_at: datetime | None = None,
    extractor_version: str | None = None,
) -> uuid.UUID:
    event_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO event (id, tenant_id, host_org_unit_id, title, normalized_title, "
            "starts_at, on_date, time_zone, time_precision, resolved_date, "
            "publication_status, review_status, quarantined_tag_count, origin, "
            "source_url, fetched_at, extractor_version) "
            "VALUES (:id, :tid, :unit, :title, :normalized, :starts_at, :on_date, :zone, "
            ":precision, :resolved, :publication, :review, :quarantined, :origin, "
            ":source_url, :fetched_at, :extractor)"
        ),
        {
            "id": event_id,
            "tid": tenant_id,
            "unit": ensure_owning_unit(conn, tenant_id),
            "title": title,
            "normalized": normalized_title if normalized_title is not None else title.casefold(),
            "starts_at": starts_at,
            "on_date": on_date,
            "zone": time_zone,
            "precision": time_precision,
            "resolved": resolved_date,
            "publication": publication_status,
            "review": review_status,
            "quarantined": quarantined_tag_count,
            "origin": origin,
            "source_url": source_url,
            "fetched_at": fetched_at,
            "extractor": extractor_version,
        },
    )
    return event_id


def _insert_tag(
    conn,
    tenant_id: uuid.UUID,
    event_id: uuid.UUID,
    *,
    resolution: str,
    term: str | None = None,
    raw_value: str | None = None,
    vocabulary_version: str = "g3-2026-08-29",
) -> uuid.UUID:
    tag_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO event_tag (id, tenant_id, event_id, resolution, term, raw_value, "
            "vocabulary_version) "
            "VALUES (:id, :tid, :event, :resolution, :term, :raw, :version)"
        ),
        {
            "id": tag_id,
            "tid": tenant_id,
            "event": event_id,
            "resolution": resolution,
            "term": term,
            "raw": raw_value,
            "version": vocabulary_version,
        },
    )
    return tag_id


def _insert_review_item(
    conn,
    tenant_id: uuid.UUID,
    event_id: uuid.UUID,
    *,
    kind: str = "unmapped_tag",
    raw_value: str | None = "Networking Mixer",
    vocabulary_version: str | None = "g3-2026-08-29",
    status: str = "pending",
    decided_at: datetime | None = None,
    decided_by: uuid.UUID | None = None,
) -> uuid.UUID:
    item_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO discovery_review_item (id, tenant_id, owning_unit_id, event_id, kind, "
            "raw_value, vocabulary_version, status, decided_at, decided_by) "
            "VALUES (:id, :tid, :unit, :event, :kind, :raw, :version, :status, :at, :by)"
        ),
        {
            "id": item_id,
            "tid": tenant_id,
            "unit": ensure_owning_unit(conn, tenant_id),
            "event": event_id,
            "kind": kind,
            "raw": raw_value,
            "version": vocabulary_version,
            "status": status,
            "at": decided_at,
            "by": decided_by,
        },
    )
    return item_id


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
            "sub": unique_subject(f"event-{user_id.hex[:8]}"),
            "email": f"{user_id.hex[:8]}@example.edu",
        },
    )
    return user_id


# ---------------------------------------------------------------------------
# ck_event_publishable — ADR-0010 rule 2 and ADR-0012's quarantine rule.
# The constraint card S3 names by itself.
# ---------------------------------------------------------------------------


def test_an_unresolved_event_cannot_be_published(engine: Engine, tenant_id) -> None:
    """ADR-0010 rule 2, enforced by the database rather than by a validator."""
    with pytest.raises(IntegrityError, match="ck_event_publishable"), engine.begin() as conn:
        _insert_event(
            conn,
            tenant_id,
            starts_at=None,
            on_date=None,
            time_zone=None,
            time_precision="unresolved",
            resolved_date=None,
            publication_status="published",
        )


def test_an_event_with_quarantined_tags_cannot_be_published(engine: Engine, tenant_id) -> None:
    """ADR-0012: an unmapped value is "never rendered and never matched on"."""
    with pytest.raises(IntegrityError, match="ck_event_publishable"), engine.begin() as conn:
        _insert_event(conn, tenant_id, publication_status="published", quarantined_tag_count=1)


def test_a_resolved_event_with_no_quarantined_tags_publishes(engine: Engine, tenant_id) -> None:
    """The permitted write, so the constraint is not merely refusing everything."""
    with engine.begin() as conn:
        event_id = _insert_event(conn, tenant_id, publication_status="published")

        status = conn.execute(
            text("SELECT publication_status FROM event WHERE id = :id"), {"id": event_id}
        ).scalar_one()
    assert status == "published"


def test_an_unresolved_event_may_exist_while_unpublished(engine: Engine, tenant_id) -> None:
    """Unresolved is a storable state, not an unstorable one.

    ADR-0012: leaving such an event unkeyed "keeps them distinct, unmatchable
    (ADR-0010), and visible to review — which is the honest state." A schema
    that refused the row outright would lose the event instead of queueing it.
    """
    with engine.begin() as conn:
        event_id = _insert_event(
            conn,
            tenant_id,
            starts_at=None,
            on_date=None,
            time_zone=None,
            time_precision="unresolved",
            resolved_date=None,
        )

        status = conn.execute(
            text("SELECT publication_status FROM event WHERE id = :id"), {"id": event_id}
        ).scalar_one()
    assert status == "unpublished"


def test_publishing_an_event_that_later_quarantines_a_tag_is_refused(
    engine: Engine, tenant_id
) -> None:
    """The constraint holds against an UPDATE, not only against an INSERT.

    A row can become unpublishable after it was published — a re-extraction
    finds a tag the vocabulary does not carry. The CHECK is re-evaluated on
    every write to the row, so raising the counter on a published event is
    refused rather than quietly leaving a published event with quarantined tags.
    """
    with engine.begin() as conn:
        event_id = _insert_event(conn, tenant_id, publication_status="published")

    with pytest.raises(IntegrityError, match="ck_event_publishable"), engine.begin() as conn:
        conn.execute(
            text("UPDATE event SET quarantined_tag_count = 1 WHERE id = :id"), {"id": event_id}
        )


# ---------------------------------------------------------------------------
# ck_event_temporal_shape — ADR-0010's three precisions, each with one shape.
# ---------------------------------------------------------------------------


def test_an_unresolved_event_cannot_carry_a_fabricated_instant(engine: Engine, tenant_id) -> None:
    """The Fix #4 defect, made unstorable.

    An `unresolved` row carrying a `starts_at` is a fabricated instant wearing
    an honest label — the legacy pipeline's "30 days from now", relabelled.
    """
    with pytest.raises(IntegrityError, match="ck_event_temporal_shape"), engine.begin() as conn:
        _insert_event(
            conn,
            tenant_id,
            starts_at=STARTS_AT,
            on_date=None,
            time_zone=None,
            time_precision="unresolved",
            resolved_date=None,
        )


def test_a_date_only_event_cannot_carry_an_instant(engine: Engine, tenant_id) -> None:
    """Fix #6: collapsing a date-only event to midnight is how a list shows 3 AM."""
    with pytest.raises(IntegrityError, match="ck_event_temporal_shape"), engine.begin() as conn:
        _insert_event(conn, tenant_id, starts_at=STARTS_AT, time_precision="date_only")


def test_an_exact_event_must_carry_an_instant(engine: Engine, tenant_id) -> None:
    with pytest.raises(IntegrityError, match="ck_event_temporal_shape"), engine.begin() as conn:
        _insert_event(conn, tenant_id, starts_at=None, on_date=None, time_precision="exact")


def test_an_exact_event_must_name_its_zone(engine: Engine, tenant_id) -> None:
    """ADR-0010 rule 1: an instant without the event's own zone is not a time."""
    with pytest.raises(IntegrityError, match="ck_event_temporal_shape"), engine.begin() as conn:
        _insert_event(
            conn,
            tenant_id,
            starts_at=STARTS_AT,
            on_date=None,
            time_zone=None,
            time_precision="exact",
        )


def test_an_exact_event_stores_the_instant_and_the_zone(engine: Engine, tenant_id) -> None:
    with engine.begin() as conn:
        event_id = _insert_event(
            conn,
            tenant_id,
            starts_at=STARTS_AT,
            on_date=None,
            time_precision="exact",
        )

        row = conn.execute(
            text("SELECT starts_at, on_date, time_zone FROM event WHERE id = :id"),
            {"id": event_id},
        ).one()
    assert row.starts_at == STARTS_AT
    assert row.on_date is None
    assert row.time_zone == ZONE


def test_a_precision_outside_adr_0010s_three_values_is_refused(engine: Engine, tenant_id) -> None:
    """`ck_event_temporal_shape` is what actually fires, and that is expected.

    Both constraints enumerate the same three precisions, so no row can violate
    `ck_event_time_precision` while satisfying the shape rule — every value
    outside the enum also fails to match any of the shape's three arms, and
    PostgreSQL reports whichever it evaluates first. `ck_event_time_precision`
    is therefore defence in depth rather than an independently reachable
    guard, and this test names that rather than asserting a constraint name it
    cannot reliably provoke — the same honesty `0011`'s own docstring applies
    to `ck_pipeline_record_stage_prefix`'s unreachable first clause.

    What is asserted is the property that matters: the value does not store.
    """
    with (
        pytest.raises(IntegrityError, match=r"ck_event_temporal_shape|ck_event_time_precision"),
        engine.begin() as conn,
    ):
        _insert_event(conn, tenant_id, time_precision="approximate")


# ---------------------------------------------------------------------------
# ck_event_identity_iff_resolved — an event has a key exactly when its date did.
# ---------------------------------------------------------------------------


def test_an_unresolved_event_cannot_carry_an_identity_date(engine: Engine, tenant_id) -> None:
    """ADR-0012: "an `unresolved` event has no identity key"."""
    with (
        pytest.raises(IntegrityError, match="ck_event_identity_iff_resolved"),
        engine.begin() as conn,
    ):
        _insert_event(
            conn,
            tenant_id,
            starts_at=None,
            on_date=None,
            time_zone=None,
            time_precision="unresolved",
            resolved_date=ON_DATE,
        )


def test_a_resolved_event_must_carry_an_identity_date(engine: Engine, tenant_id) -> None:
    with (
        pytest.raises(IntegrityError, match="ck_event_identity_iff_resolved"),
        engine.begin() as conn,
    ):
        _insert_event(conn, tenant_id, resolved_date=None)


def test_two_unresolved_events_with_the_same_host_and_title_both_insert(
    engine: Engine, tenant_id
) -> None:
    """The unkeyed rule, proven rather than asserted.

    ADR-0012: "Two events with unknown dates are not evidence of being the same
    event, and a key that ignores the date would merge them." `uq_event_identity`
    carries `resolved_date`, which is NULL here, and PostgreSQL treats NULLs as
    distinct — so both rows exist, unmatched and unmatchable, with no branch in
    any writer needed to arrange it.
    """
    with engine.begin() as conn:
        first = _insert_event(
            conn,
            tenant_id,
            title="Same Title",
            starts_at=None,
            on_date=None,
            time_zone=None,
            time_precision="unresolved",
            resolved_date=None,
        )
        second = _insert_event(
            conn,
            tenant_id,
            title="Same Title",
            starts_at=None,
            on_date=None,
            time_zone=None,
            time_precision="unresolved",
            resolved_date=None,
        )

        count = conn.execute(
            text("SELECT count(*) FROM event WHERE tenant_id = :tid AND title = 'Same Title'"),
            {"tid": tenant_id},
        ).scalar_one()

    assert first != second
    assert count == 2


def test_two_resolved_events_with_the_same_key_collide(engine: Engine, tenant_id) -> None:
    """The other half: a resolved duplicate is refused, which is what makes the
    writer's ON CONFLICT an update rather than a second row."""
    with engine.begin() as conn:
        _insert_event(conn, tenant_id, title="Same Title")

    with pytest.raises(IntegrityError, match="uq_event_identity"), engine.begin() as conn:
        _insert_event(conn, tenant_id, title="Same Title")


# ---------------------------------------------------------------------------
# ck_event_provenance_evidence and ck_event_origin — ADR-0012's structured
# provenance, never smuggled into a display string.
# ---------------------------------------------------------------------------


def test_an_extracted_event_must_name_its_source(engine: Engine, tenant_id) -> None:
    with (
        pytest.raises(IntegrityError, match="ck_event_provenance_evidence"),
        engine.begin() as conn,
    ):
        _insert_event(conn, tenant_id, origin="extraction")


def test_a_coordinator_entered_event_must_not_claim_a_source(engine: Engine, tenant_id) -> None:
    """A human typing an event has no source URL; recording one would attribute
    their entry to a page nobody fetched."""
    with (
        pytest.raises(IntegrityError, match="ck_event_provenance_evidence"),
        engine.begin() as conn,
    ):
        _insert_event(
            conn,
            tenant_id,
            origin="coordinator_entry",
            source_url="https://example.invalid/events",
            fetched_at=STARTS_AT,
            extractor_version="fixture-1",
        )


def test_an_extraction_cannot_name_a_url_without_a_fetch_time(engine: Engine, tenant_id) -> None:
    with (
        pytest.raises(IntegrityError, match="ck_event_provenance_evidence"),
        engine.begin() as conn,
    ):
        _insert_event(
            conn,
            tenant_id,
            origin="extraction",
            source_url="https://example.invalid/events",
            fetched_at=None,
            extractor_version="fixture-1",
        )


def test_provenance_is_stored_beside_the_title_and_never_inside_it(
    engine: Engine, tenant_id
) -> None:
    """ADR-0012's "titles carrying their source" defect, checked as data.

    The permitted extraction write, plus the assertion that closes Fix #4's
    third part: the source lives in its own column, and the title the row
    stores is the title alone.
    """
    with engine.begin() as conn:
        event_id = _insert_event(
            conn,
            tenant_id,
            title="Fall Capstone Showcase",
            origin="extraction",
            source_url="https://example.invalid/calendar/1",
            fetched_at=STARTS_AT,
            extractor_version="synthetic-fixture-1",
        )

        row = conn.execute(
            text("SELECT title, source_url, extractor_version FROM event WHERE id = :id"),
            {"id": event_id},
        ).one()

    assert row.title == "Fall Capstone Showcase"
    assert row.source_url == "https://example.invalid/calendar/1"
    assert row.source_url not in row.title
    assert row.extractor_version not in row.title


def test_origin_admits_only_the_two_recorded_values(engine: Engine, tenant_id) -> None:
    with pytest.raises(IntegrityError, match="ck_event_origin"), engine.begin() as conn:
        _insert_event(conn, tenant_id, origin="imported")


# ---------------------------------------------------------------------------
# The remaining event CHECKs.
# ---------------------------------------------------------------------------


def test_publication_status_admits_only_two_values(engine: Engine, tenant_id) -> None:
    with (
        pytest.raises(IntegrityError, match="ck_event_publication_status"),
        engine.begin() as conn,
    ):
        _insert_event(conn, tenant_id, publication_status="draft")


def test_review_status_admits_only_the_review_vocabulary(engine: Engine, tenant_id) -> None:
    with pytest.raises(IntegrityError, match="ck_event_review_status"), engine.begin() as conn:
        _insert_event(conn, tenant_id, review_status="escalated")


def test_the_quarantined_tag_counter_cannot_go_negative(engine: Engine, tenant_id) -> None:
    with (
        pytest.raises(IntegrityError, match="ck_event_quarantined_tag_count_non_negative"),
        engine.begin() as conn,
    ):
        _insert_event(conn, tenant_id, quarantined_tag_count=-1)


def test_an_event_cannot_name_a_unit_in_another_tenant(engine: Engine, tenant_id) -> None:
    """The composite foreign key, which is what makes v1.1 §2.2's isolation real."""
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO event (id, tenant_id, host_org_unit_id, title, normalized_title, "
                "on_date, time_zone, time_precision, resolved_date, origin) "
                "VALUES (:id, :tid, :unit, 'Elsewhere', 'elsewhere', :on_date, "
                "'America/Los_Angeles', 'date_only', :on_date, 'coordinator_entry')"
            ),
            {
                "id": uuid.uuid4(),
                "tid": tenant_id,
                # A unit id belonging to no tenant at all, which is the same
                # failure as one belonging to another.
                "unit": uuid.uuid4(),
                "on_date": ON_DATE,
            },
        )


# ---------------------------------------------------------------------------
# event_tag — the database half of "a QuarantinedTag has no term".
# ---------------------------------------------------------------------------


def test_a_quarantined_tag_cannot_carry_a_matchable_term(engine: Engine, tenant_id) -> None:
    """`QuarantinedTag` has no `term` attribute; this is the same rule in SQL."""
    with (
        pytest.raises(IntegrityError, match="ck_event_tag_resolution_shape"),
        engine.begin() as conn,
    ):
        event_id = _insert_event(conn, tenant_id)
        _insert_tag(
            conn,
            tenant_id,
            event_id,
            resolution="quarantined",
            term="hackathon",
            raw_value="Datathon",
        )


def test_a_mapped_tag_must_carry_a_term(engine: Engine, tenant_id) -> None:
    with (
        pytest.raises(IntegrityError, match="ck_event_tag_resolution_shape"),
        engine.begin() as conn,
    ):
        event_id = _insert_event(conn, tenant_id)
        _insert_tag(conn, tenant_id, event_id, resolution="mapped", term=None, raw_value="x")


def test_tag_resolution_admits_only_the_two_domain_arms(engine: Engine, tenant_id) -> None:
    with (
        pytest.raises(IntegrityError, match="ck_event_tag_resolution"),
        engine.begin() as conn,
    ):
        event_id = _insert_event(conn, tenant_id)
        _insert_tag(conn, tenant_id, event_id, resolution="pending", term="hackathon")


def test_both_tag_arms_store_and_stay_distinguishable(engine: Engine, tenant_id) -> None:
    """The permitted writes, and the read that proves quarantine is invisible to
    a query looking for terms."""
    with engine.begin() as conn:
        event_id = _insert_event(conn, tenant_id)
        _insert_tag(conn, tenant_id, event_id, resolution="mapped", term="hackathon")
        _insert_tag(conn, tenant_id, event_id, resolution="quarantined", raw_value="Datathon")

        terms = conn.execute(
            text("SELECT term FROM event_tag WHERE event_id = :id AND term IS NOT NULL"),
            {"id": event_id},
        ).scalars()
    assert list(terms) == ["hackathon"]


def test_a_tag_is_deleted_with_the_event_it_describes(engine: Engine, tenant_id) -> None:
    """CASCADE, unlike `event.host_org_unit_id`'s RESTRICT: a tag has no meaning
    without the event it tags."""
    with engine.begin() as conn:
        event_id = _insert_event(conn, tenant_id)
        _insert_tag(conn, tenant_id, event_id, resolution="mapped", term="workshop")

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM event WHERE id = :id"), {"id": event_id})
        remaining = conn.execute(
            text("SELECT count(*) FROM event_tag WHERE event_id = :id"), {"id": event_id}
        ).scalar_one()
    assert remaining == 0


# ---------------------------------------------------------------------------
# discovery_review_item — G3 §5's escalation destination.
# ---------------------------------------------------------------------------


def test_an_unmapped_tag_entry_must_carry_the_value_and_its_vocabulary_version(
    engine: Engine, tenant_id
) -> None:
    with (
        pytest.raises(IntegrityError, match="ck_discovery_review_item_tag_evidence"),
        engine.begin() as conn,
    ):
        event_id = _insert_event(conn, tenant_id)
        _insert_review_item(conn, tenant_id, event_id, kind="unmapped_tag", raw_value=None)


def test_a_non_tag_entry_must_not_carry_a_raw_value(engine: Engine, tenant_id) -> None:
    with (
        pytest.raises(IntegrityError, match="ck_discovery_review_item_tag_evidence"),
        engine.begin() as conn,
    ):
        event_id = _insert_event(conn, tenant_id)
        _insert_review_item(
            conn, tenant_id, event_id, kind="unresolved_time", raw_value="Next Thursday"
        )


def test_a_decision_must_name_who_made_it_and_when(engine: Engine, tenant_id) -> None:
    """`review_item`'s own biconditional (0013), unchanged: a decision that names
    nobody and no time is the fabricated-field defect."""
    with (
        pytest.raises(IntegrityError, match="ck_discovery_review_item_decision_evidence"),
        engine.begin() as conn,
    ):
        event_id = _insert_event(conn, tenant_id)
        _insert_review_item(conn, tenant_id, event_id, status="accepted")


def test_a_pending_entry_must_not_claim_a_decision(engine: Engine, tenant_id) -> None:
    with (
        pytest.raises(IntegrityError, match="ck_discovery_review_item_decision_evidence"),
        engine.begin() as conn,
    ):
        event_id = _insert_event(conn, tenant_id)
        user_id = _make_user(conn, tenant_id)
        _insert_review_item(
            conn,
            tenant_id,
            event_id,
            status="pending",
            decided_at=STARTS_AT,
            decided_by=user_id,
        )


def test_a_decided_entry_stores_its_reviewer(engine: Engine, tenant_id) -> None:
    with engine.begin() as conn:
        event_id = _insert_event(conn, tenant_id)
        user_id = _make_user(conn, tenant_id)
        item_id = _insert_review_item(
            conn,
            tenant_id,
            event_id,
            status="accepted",
            decided_at=STARTS_AT,
            decided_by=user_id,
        )

        row = conn.execute(
            text("SELECT status, decided_by FROM discovery_review_item WHERE id = :id"),
            {"id": item_id},
        ).one()
    assert row.status == "accepted"
    assert row.decided_by == user_id


def test_the_review_kind_vocabulary_is_closed(engine: Engine, tenant_id) -> None:
    with (
        pytest.raises(IntegrityError, match="ck_discovery_review_item_kind"),
        engine.begin() as conn,
    ):
        event_id = _insert_event(conn, tenant_id)
        _insert_review_item(
            conn,
            tenant_id,
            event_id,
            kind="suspicious",
            raw_value=None,
            vocabulary_version=None,
        )


def test_the_review_status_vocabulary_is_closed(engine: Engine, tenant_id) -> None:
    """A fourth status, with a decision attached so only the enum is in question.

    `ck_discovery_review_item_decision_evidence` fires on any non-`pending`
    status that names no reviewer, so a bare `status="deferred"` would prove
    that constraint rather than this one. Supplying the decision isolates the
    vocabulary.
    """
    with (
        pytest.raises(IntegrityError, match="ck_discovery_review_item_status"),
        engine.begin() as conn,
    ):
        event_id = _insert_event(conn, tenant_id)
        user_id = _make_user(conn, tenant_id)
        _insert_review_item(
            conn,
            tenant_id,
            event_id,
            status="deferred",
            decided_at=STARTS_AT,
            decided_by=user_id,
        )


def test_the_discovery_queue_does_not_hang_off_import_batch(engine: Engine, tenant_id) -> None:
    """G3 §5's decision, asserted as structure rather than trusted as prose.

    `review_item` was the alternative and cascades from `import_batch`; a
    discovery finding parked there would be deleted with an unrelated import.
    This asserts the table that exists instead references `event` and
    `org_unit` and nothing from the import path — so a later change that
    re-pointed it would fail here rather than lose review entries in
    production.
    """
    with engine.begin() as conn:
        referenced = conn.execute(
            text(
                "SELECT DISTINCT confrelid::regclass::text AS target FROM pg_constraint "
                "WHERE conrelid = 'discovery_review_item'::regclass AND contype = 'f' "
                "ORDER BY target"
            )
        ).scalars()

    assert list(referenced) == ["event", "org_unit", "user_account"]


# ---------------------------------------------------------------------------
# Card S5f — attendance_record.event_id's foreign key.
# ---------------------------------------------------------------------------


def test_attendance_cannot_cite_an_event_that_does_not_exist(engine: Engine, tenant_id) -> None:
    """The constraint migration 0009 asked "whichever migration adds one" to write."""
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO attendance_record "
                "(id, tenant_id, owning_unit_id, subject_id, event_id, method) "
                "VALUES (:id, :tid, :unit, :subject, :event, 'qr_scan')"
            ),
            {
                "id": uuid.uuid4(),
                "tid": tenant_id,
                "unit": ensure_owning_unit(conn, tenant_id),
                "subject": _make_user(conn, tenant_id),
                "event": uuid.uuid4(),
            },
        )


def test_attendance_stores_when_it_cites_a_real_event(engine: Engine, tenant_id) -> None:
    with engine.begin() as conn:
        event_id = _insert_event(conn, tenant_id)
        record_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO attendance_record "
                "(id, tenant_id, owning_unit_id, subject_id, event_id, method) "
                "VALUES (:id, :tid, :unit, :subject, :event, 'qr_scan')"
            ),
            {
                "id": record_id,
                "tid": tenant_id,
                "unit": ensure_owning_unit(conn, tenant_id),
                "subject": _make_user(conn, tenant_id),
                "event": event_id,
            },
        )

        stored = conn.execute(
            text("SELECT event_id FROM attendance_record WHERE id = :id"), {"id": record_id}
        ).scalar_one()
    assert stored == event_id


def test_an_event_with_recorded_attendance_cannot_be_deleted(engine: Engine, tenant_id) -> None:
    """RESTRICT, not CASCADE: attendance is the only input to points (ADR-0013),
    so deleting the event would leave a ledger entry nothing could explain."""
    with engine.begin() as conn:
        event_id = _insert_event(conn, tenant_id)
        conn.execute(
            text(
                "INSERT INTO attendance_record "
                "(id, tenant_id, owning_unit_id, subject_id, event_id, method) "
                "VALUES (:id, :tid, :unit, :subject, :event, 'qr_scan')"
            ),
            {
                "id": uuid.uuid4(),
                "tid": tenant_id,
                "unit": ensure_owning_unit(conn, tenant_id),
                "subject": _make_user(conn, tenant_id),
                "event": event_id,
            },
        )

    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text("DELETE FROM event WHERE id = :id"), {"id": event_id})
