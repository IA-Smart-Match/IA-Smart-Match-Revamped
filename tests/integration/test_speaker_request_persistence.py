"""Filing a Speaker Request, against a real PostgreSQL instance (CBA-EVENT-REQUEST).

Everything here goes through ``smartmatch_persistence.speaker_requests``, because
everything here is a statement about the *writer*: which statement it issues, what
it leaves behind, and what a second filing of the same request does to the first.
What the database refuses regardless of the writer is
``tests/integration/test_cba_classification_schema.py``'s subject and is not
restated.

Two properties carry most of the file:

* **Idempotency is the identity key.** ADR-0012 says two writes producing the same
  key are the same event and the second updates the first, and that manual entry
  is not exempt. So filing the same request twice must leave one ``event`` row,
  report ``created`` once, and keep the id stable — which is what lets an API
  answer ``201`` and then ``200``.
* **Targets are replaced, not accumulated.** A resubmission states the whole
  request, so an industry the new draft does not name must be gone. A test that
  only checked the added row would pass against an implementation that never
  removes one, and a host un-selecting Finance would keep matching on Finance
  forever.

Every event below is synthetic and nothing opens a socket: a Speaker Request is
typed by a person, and the writer has no parameter that could carry a URL.

Requires a live database, and is skipped when none is reachable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest

pytest.importorskip("sqlalchemy")

from conftest import ensure_owning_unit
from smartmatch_domain.cba_role_categories import CBA_ROLE_TAXONOMY_VERSION
from smartmatch_domain.events import DateOnlyTime, ExactTime, UnresolvedTime
from smartmatch_domain.naics_sectors import NAICS_TAXONOMY_VERSION
from smartmatch_domain.speaker_requests import (
    KIND_INDUSTRY,
    KIND_ROLE,
    ClassificationRequiredError,
    DuplicateClassificationError,
    LocationRequiredError,
    SpeakerRequestDraft,
    UnschedulableSpeakerRequestError,
    VirtualRequestLocationError,
)
from smartmatch_persistence.speaker_requests import SpeakerRequestRepository
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.integration

#: Fixed literals, not `date.today()`: the identity key folds the date in, so a
#: generated one would make a re-file non-reproducible across midnight — the
#: once-a-day flake `conftest.SYNTHETIC_EVENT_DATE` exists to avoid.
ON_DATE = date(2026, 10, 14)
STARTS_AT = datetime(2026, 10, 14, 19, 30, tzinfo=UTC)
ZONE = "America/Los_Angeles"

TITLE = "Analytics Careers Panel"

#: 52 = Finance and Insurance, 54 = Professional, Scientific, and Technical
#: Services. Written as codes rather than looked up, so a taxonomy edit that
#: dropped one fails here rather than passing against whatever it returned.
FINANCE = "52"
PROFESSIONAL_SERVICES = "54"


@pytest.fixture(autouse=True)
def _clean_event_tables(engine: Engine, tenant_id):
    """Delete this file's rows before ``tenant_id`` tears down its own.

    ``event.host_org_unit_id`` is ``ON DELETE RESTRICT``, so a row left behind
    here would make ``conftest.py``'s teardown fail on the ``org_unit`` delete.
    ``speaker_request_classification`` would cascade with its event and is
    deleted explicitly so a failure names the table it happened in.
    """
    yield
    with engine.begin() as conn:
        for table in ("speaker_request_classification", "event_tag", "event"):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})


@pytest.fixture
def session(session_factory: sessionmaker[Session]):
    """One session per test, rolled back rather than left open."""
    db = session_factory()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


@pytest.fixture
def unit_id(session: Session, tenant_id: uuid.UUID) -> uuid.UUID:
    """The unit these requests are filed under."""
    unit = ensure_owning_unit(session, tenant_id)
    session.commit()
    return unit


def _draft(**overrides) -> SpeakerRequestDraft:
    """A physical request one industry and one role wide, plus overrides."""
    fields: dict[str, object] = {
        "title": TITLE,
        "event_time": DateOnlyTime(on_date=ON_DATE, time_zone=ZONE),
        "is_virtual": False,
        "industry_codes": (FINANCE,),
        "role_codes": ("finance",),
        "description": "A panel on analytics careers for CBA students.",
        "location_city": "Pomona",
        "location_postal_code": None,
    }
    fields.update(overrides)
    return SpeakerRequestDraft(**fields)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# The draft refuses before the database is reached
#
# These are domain rules and could be unit tests. They are here because what is
# worth asserting is that the *writer* never gets the chance to store one of
# them — a rule enforced only in a router would be a rule a second caller could
# walk around.
# ---------------------------------------------------------------------------


def test_an_undated_request_cannot_be_drafted_at_all() -> None:
    """ADR-0010 rule 2 and ADR-0012, at intake rather than at publication."""
    with pytest.raises(UnschedulableSpeakerRequestError):
        _draft(event_time=UnresolvedTime())


def test_a_request_with_no_industry_is_refused() -> None:
    """Customer §12's floor. Industry is 30% of the default score."""
    with pytest.raises(ClassificationRequiredError):
        _draft(industry_codes=())


def test_a_request_with_no_role_is_refused() -> None:
    """The same floor on §8's axis. Role is 25%."""
    with pytest.raises(ClassificationRequiredError):
        _draft(role_codes=())


def test_a_repeated_target_is_refused_rather_than_folded_away() -> None:
    """A bag is not a smaller set — see ``DuplicateClassificationError``."""
    with pytest.raises(DuplicateClassificationError):
        _draft(industry_codes=(FINANCE, FINANCE))


def test_a_virtual_request_may_not_carry_a_location() -> None:
    """Customer §11 ignores Proximity entirely; a stored place would be read anyway."""
    with pytest.raises(VirtualRequestLocationError):
        _draft(is_virtual=True, location_city="Pomona")


def test_a_physical_request_must_name_a_place() -> None:
    """OQ-CBA-013, fail-closed: Proximity is 30% and cannot score a placeless event."""
    with pytest.raises(LocationRequiredError):
        _draft(location_city=None, location_postal_code=None)


def test_an_unreleased_industry_code_is_refused_by_the_taxonomy() -> None:
    """The vocabulary is closed, and this module is not a second authority on it."""
    with pytest.raises(LookupError):
        _draft(industry_codes=("99",))


def test_an_unreleased_role_code_is_refused_by_the_taxonomy() -> None:
    with pytest.raises(LookupError):
        _draft(role_codes=("underwater_basket_weaving",))


# ---------------------------------------------------------------------------
# The write
# ---------------------------------------------------------------------------


def test_filing_a_request_stores_the_event_and_both_axes(
    session: Session, tenant_id: uuid.UUID, unit_id: uuid.UUID
) -> None:
    """One filing, one event row, and one classification row per target."""
    repository = SpeakerRequestRepository()
    result = repository.file(
        session,
        tenant_id=tenant_id,
        host_org_unit_id=unit_id,
        draft=_draft(industry_codes=(FINANCE, PROFESSIONAL_SERVICES), role_codes=("finance",)),
    )
    session.commit()

    assert result.created is True

    row = session.execute(
        text(
            "SELECT title, origin, source_url, fetched_at, extractor_version, "
            "       time_precision, on_date, starts_at, time_zone, is_virtual, "
            "       location_city, location_postal_code, publication_status, review_status "
            "FROM event WHERE tenant_id = :tid AND id = :eid"
        ),
        {"tid": tenant_id, "eid": result.event_id},
    ).one()

    assert row.title == TITLE
    # Manual origin, and provenance that does not exist rather than provenance
    # left blank: `ck_event_provenance_evidence` requires all three to be NULL
    # on a `coordinator_entry` row, and a fabricated source URL would attribute
    # a person's typing to a page nobody fetched.
    assert row.origin == "coordinator_entry"
    assert row.source_url is None
    assert row.fetched_at is None
    assert row.extractor_version is None
    # ADR-0010: the precision the host actually stated, and no invented instant.
    assert row.time_precision == "date_only"
    assert row.on_date == ON_DATE
    assert row.starts_at is None
    assert row.time_zone == ZONE
    assert row.is_virtual is False
    assert row.location_city == "Pomona"
    assert row.location_postal_code is None
    # Filing records what a host asked for; it does not publish an event.
    assert row.publication_status == "unpublished"
    assert row.review_status == "pending"

    stored = session.execute(
        text(
            "SELECT kind, code, taxonomy_version FROM speaker_request_classification "
            "WHERE tenant_id = :tid AND event_id = :eid ORDER BY kind, code"
        ),
        {"tid": tenant_id, "eid": result.event_id},
    ).all()
    assert [(r.kind, r.code) for r in stored] == [
        (KIND_INDUSTRY, FINANCE),
        (KIND_INDUSTRY, PROFESSIONAL_SERVICES),
        (KIND_ROLE, "finance"),
    ]
    # Each stored code says which released table evaluated it.
    versions = {r.kind: r.taxonomy_version for r in stored}
    assert versions[KIND_INDUSTRY] == NAICS_TAXONOMY_VERSION
    assert versions[KIND_ROLE] == CBA_ROLE_TAXONOMY_VERSION


def test_a_virtual_request_stores_no_location(
    session: Session, tenant_id: uuid.UUID, unit_id: uuid.UUID
) -> None:
    """Customer §11, held by the schema as well as by the draft."""
    repository = SpeakerRequestRepository()
    result = repository.file(
        session,
        tenant_id=tenant_id,
        host_org_unit_id=unit_id,
        draft=_draft(is_virtual=True, location_city=None, location_postal_code=None),
    )
    session.commit()

    row = session.execute(
        text(
            "SELECT is_virtual, location_city, location_postal_code "
            "FROM event WHERE tenant_id = :tid AND id = :eid"
        ),
        {"tid": tenant_id, "eid": result.event_id},
    ).one()
    assert row.is_virtual is True
    assert row.location_city is None
    assert row.location_postal_code is None


def test_an_exact_time_request_keeps_its_instant_and_its_end(
    session: Session, tenant_id: uuid.UUID, unit_id: uuid.UUID
) -> None:
    """ADR-0010's other precision, including an end the host actually stated."""
    ends_at = datetime(2026, 10, 14, 21, 0, tzinfo=UTC)
    repository = SpeakerRequestRepository()
    result = repository.file(
        session,
        tenant_id=tenant_id,
        host_org_unit_id=unit_id,
        draft=_draft(event_time=ExactTime(starts_at=STARTS_AT, time_zone=ZONE, ends_at=ends_at)),
    )
    session.commit()

    row = session.execute(
        text(
            "SELECT time_precision, starts_at, ends_at, on_date, time_zone "
            "FROM event WHERE tenant_id = :tid AND id = :eid"
        ),
        {"tid": tenant_id, "eid": result.event_id},
    ).one()
    assert row.time_precision == "exact"
    assert row.starts_at == STARTS_AT
    assert row.ends_at == ends_at
    assert row.on_date is None
    assert row.time_zone == ZONE


# ---------------------------------------------------------------------------
# Idempotency, which is ADR-0012's identity key rather than a header
# ---------------------------------------------------------------------------


def test_refiling_the_same_request_updates_it_rather_than_duplicating(
    session: Session, tenant_id: uuid.UUID, unit_id: uuid.UUID
) -> None:
    """The card's idempotency requirement, stated as ADR-0012 states it.

    Same host unit, same folded title, same resolved date — so the second filing
    is the same request. One row, the same id, and ``created`` true exactly once,
    which is what lets the route answer ``201`` and then ``200``.
    """
    repository = SpeakerRequestRepository()
    first = repository.file(session, tenant_id=tenant_id, host_org_unit_id=unit_id, draft=_draft())
    session.commit()
    second = repository.file(session, tenant_id=tenant_id, host_org_unit_id=unit_id, draft=_draft())
    session.commit()

    assert first.created is True
    assert second.created is False
    assert second.event_id == first.event_id

    count = session.execute(
        text("SELECT count(*) FROM event WHERE tenant_id = :tid"), {"tid": tenant_id}
    ).scalar_one()
    assert count == 1


def test_a_title_differing_only_in_case_and_punctuation_is_the_same_request(
    session: Session, tenant_id: uuid.UUID, unit_id: uuid.UUID
) -> None:
    """ADR-0012's folding rule, which is why a host's typo fix is not a new request."""
    repository = SpeakerRequestRepository()
    first = repository.file(session, tenant_id=tenant_id, host_org_unit_id=unit_id, draft=_draft())
    session.commit()
    second = repository.file(
        session,
        tenant_id=tenant_id,
        host_org_unit_id=unit_id,
        draft=_draft(title="  analytics   careers panel!  "),
    )
    session.commit()

    assert second.event_id == first.event_id
    assert second.created is False


def test_a_different_date_is_a_different_request(
    session: Session, tenant_id: uuid.UUID, unit_id: uuid.UUID
) -> None:
    """The date is in the key, so moving the event files a second request.

    The counterpart to the test above, and the reason that one is not enough on
    its own: an implementation keying on the title alone would pass it and
    silently merge two genuinely different events.
    """
    repository = SpeakerRequestRepository()
    first = repository.file(session, tenant_id=tenant_id, host_org_unit_id=unit_id, draft=_draft())
    session.commit()
    second = repository.file(
        session,
        tenant_id=tenant_id,
        host_org_unit_id=unit_id,
        draft=_draft(event_time=DateOnlyTime(on_date=date(2026, 10, 21), time_zone=ZONE)),
    )
    session.commit()

    assert second.event_id != first.event_id
    assert second.created is True


def test_refiling_replaces_the_targets_rather_than_accumulating_them(
    session: Session, tenant_id: uuid.UUID, unit_id: uuid.UUID
) -> None:
    """A target the new draft does not name is one the host removed.

    Accumulating instead would keep weighting an industry nobody asked for, with
    nothing on screen to explain why a shortlist looked the way it did.
    """
    repository = SpeakerRequestRepository()
    repository.file(
        session,
        tenant_id=tenant_id,
        host_org_unit_id=unit_id,
        draft=_draft(industry_codes=(FINANCE, PROFESSIONAL_SERVICES)),
    )
    session.commit()

    result = repository.file(
        session,
        tenant_id=tenant_id,
        host_org_unit_id=unit_id,
        draft=_draft(industry_codes=(PROFESSIONAL_SERVICES,), role_codes=("marketing",)),
    )
    session.commit()

    stored = session.execute(
        text(
            "SELECT kind, code FROM speaker_request_classification "
            "WHERE tenant_id = :tid AND event_id = :eid ORDER BY kind, code"
        ),
        {"tid": tenant_id, "eid": result.event_id},
    ).all()
    assert [(r.kind, r.code) for r in stored] == [
        (KIND_INDUSTRY, PROFESSIONAL_SERVICES),
        (KIND_ROLE, "marketing"),
    ]


def test_refiling_a_request_that_moved_online_drops_its_stale_location(
    session: Session, tenant_id: uuid.UUID, unit_id: uuid.UUID
) -> None:
    """A place nobody claims any more must not survive the correction.

    ``ck_event_virtual_has_no_location`` would refuse the row outright if the
    update left the city behind, so this also pins that the writer names every
    location column on the update path rather than only on the insert.
    """
    repository = SpeakerRequestRepository()
    first = repository.file(
        session,
        tenant_id=tenant_id,
        host_org_unit_id=unit_id,
        draft=_draft(location_city="Pomona"),
    )
    session.commit()

    second = repository.file(
        session,
        tenant_id=tenant_id,
        host_org_unit_id=unit_id,
        draft=_draft(is_virtual=True, location_city=None, location_postal_code=None),
    )
    session.commit()

    assert second.event_id == first.event_id
    row = session.execute(
        text(
            "SELECT is_virtual, location_city, location_postal_code "
            "FROM event WHERE tenant_id = :tid AND id = :eid"
        ),
        {"tid": tenant_id, "eid": first.event_id},
    ).one()
    assert row.is_virtual is True
    assert row.location_city is None
    assert row.location_postal_code is None


# ---------------------------------------------------------------------------
# The read
# ---------------------------------------------------------------------------


def test_the_read_returns_the_request_with_both_axes(
    session: Session, tenant_id: uuid.UUID, unit_id: uuid.UUID
) -> None:
    """The Connector read, from the same rows the write produced."""
    repository = SpeakerRequestRepository()
    result = repository.file(
        session,
        tenant_id=tenant_id,
        host_org_unit_id=unit_id,
        draft=_draft(industry_codes=(FINANCE, PROFESSIONAL_SERVICES), role_codes=("finance",)),
    )
    session.commit()

    rows = repository.list_for_unit(
        session, tenant_id=tenant_id, host_org_unit_id=unit_id, limit=10
    )
    assert len(rows) == 1
    assert rows[0].event_id == result.event_id
    assert rows[0].title == TITLE
    assert [(c.kind, c.code) for c in rows[0].classifications] == [
        (KIND_INDUSTRY, FINANCE),
        (KIND_INDUSTRY, PROFESSIONAL_SERVICES),
        (KIND_ROLE, "finance"),
    ]


def test_the_read_never_returns_an_extracted_event(
    session: Session, tenant_id: uuid.UUID, unit_id: uuid.UUID
) -> None:
    """A crawler's row is not a Speaker Request, and this queue promises hosts' work.

    Written straight to ``event`` rather than through the request writer, because
    the request writer has no parameter that could produce an ``extraction`` row —
    which is the point, and is why the row has to be inserted around it for the
    exclusion to be testable at all.
    """
    repository = SpeakerRequestRepository()
    filed = repository.file(session, tenant_id=tenant_id, host_org_unit_id=unit_id, draft=_draft())
    session.execute(
        text(
            "INSERT INTO event (id, tenant_id, host_org_unit_id, title, normalized_title, "
            "                   on_date, time_zone, time_precision, resolved_date, origin, "
            "                   source_url, fetched_at, extractor_version) "
            "VALUES (:id, :tid, :uid, :title, :norm, :on_date, :zone, 'date_only', :on_date, "
            "        'extraction', :url, now(), 'test-1')"
        ),
        {
            "id": uuid.uuid4(),
            "tid": tenant_id,
            "uid": unit_id,
            "title": "Crawled Career Fair",
            "norm": "crawled career fair",
            "on_date": ON_DATE,
            "zone": ZONE,
            # RFC 2606 reserves `.invalid`, and nothing in this file or in the
            # module under test opens a socket to it.
            "url": "https://example.invalid/events/career-fair",
        },
    )
    session.commit()

    rows = repository.list_for_unit(
        session, tenant_id=tenant_id, host_org_unit_id=unit_id, limit=10
    )
    assert [row.event_id for row in rows] == [filed.event_id]


def test_the_read_is_scoped_to_its_unit(
    session: Session, tenant_id: uuid.UUID, unit_id: uuid.UUID
) -> None:
    """A request filed under one unit is not another unit's queue item."""
    other_unit = uuid.uuid4()
    session.execute(
        text(
            "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
            "VALUES (:id, :tid, CAST('iawest.other' AS ltree), 'department', 'Other')"
        ),
        {"id": other_unit, "tid": tenant_id},
    )
    repository = SpeakerRequestRepository()
    repository.file(session, tenant_id=tenant_id, host_org_unit_id=unit_id, draft=_draft())
    session.commit()

    assert (
        repository.list_for_unit(
            session, tenant_id=tenant_id, host_org_unit_id=other_unit, limit=10
        )
        == ()
    )


def test_get_answers_none_for_another_tenants_request(
    session: Session, tenant_id: uuid.UUID, unit_id: uuid.UUID
) -> None:
    """Tenant isolation in the query, not as a filter applied afterwards."""
    repository = SpeakerRequestRepository()
    result = repository.file(session, tenant_id=tenant_id, host_org_unit_id=unit_id, draft=_draft())
    session.commit()

    assert repository.get(session, tenant_id=tenant_id, event_id=result.event_id) is not None
    assert repository.get(session, tenant_id=uuid.uuid4(), event_id=result.event_id) is None
