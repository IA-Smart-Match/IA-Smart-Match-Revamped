"""HTTP contracts for the coordinator event catalog and the tag-quarantine queue.

The rows these two routes read are not hand-written here. They are produced by
running the real ingest — ``smartmatch_worker.event_ingest`` over
``tests/fixtures/pilot_events/`` — so what is asserted is the whole path a
synthetic pilot actually exercises: committed document, Stage 0 parser,
contact-free candidate, ADR-0012 identity and vocabulary resolution,
``event``/``event_tag``/``discovery_review_item``, and finally the JSON a
coordinator sees. A fixture that inserted the rows directly would let the
listing agree with a shape the ingest never produces.

``tests/authz/test_policy_matrix.py`` owns the full authorization rectangle for
both operations and needs no database to run it. What this file adds is the
part that only exists over HTTP: that authorization is actually reached before
any row is read, that a unit in another tenant is a 404 rather than a 403, and
that the two exclusions the routes promise are visible in the response body.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_domain.event_vocabulary import VOCABULARY_VERSION
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import FixtureTokenVerifier
from smartmatch_worker.event_ingest import (
    EXTRACTOR_VERSION,
    FIXTURE_URL_SCHEME,
    ingest_fixture_directory_into_events,
)
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import sessionmaker

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "pilot_events"

UNIT_PATH = "iawest.events"
#: A second department in the same tenant containing none of :data:`UNIT_PATH`.
#: A coordinator here must not reach the events unit — neither of these routes
#: passes ``tenant_wide_roles``, so ordinary subtree containment applies.
SIBLING_UNIT_PATH = "iawest.sibling"

SOURCE_ZONE = "America/Los_Angeles"
FETCHED_AT = datetime(2026, 9, 3, 17, 0, tzinfo=UTC)

DATED_TITLE = "Spring Analytics Hackathon"
QUARANTINING_TITLE = "Autumn Data Ethics Seminar"
UNMAPPED_VALUE = "Underwater Basket Weaving"


@pytest.fixture(scope="module")
def engine() -> Engine:
    """A live migrated PostgreSQL engine, or skip this contract."""
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1 FROM event LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}")
    return eng


@pytest.fixture
def event_context(engine: Engine) -> Iterator[tuple[TestClient, uuid.UUID, str, uuid.UUID]]:
    """One tenant, one authorized coordinator, and a real ingest into it."""
    tenant_id = uuid.uuid4()
    unit_id = uuid.uuid4()
    sibling_unit_id = uuid.uuid4()
    user_id = uuid.uuid4()
    subject = f"sub-events-{uuid.uuid4().hex}"
    token = f"tok-events-{uuid.uuid4().hex}"

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"test-events-{tenant_id.hex[:12]}"},
        )
        for new_unit_id, path, name in (
            (unit_id, UNIT_PATH, "Events"),
            (sibling_unit_id, SIBLING_UNIT_PATH, "Sibling"),
        ):
            conn.execute(
                text(
                    "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                    "VALUES (:id, :tid, CAST(:path AS ltree), 'department', :name)"
                ),
                {"id": new_unit_id, "tid": tenant_id, "path": path, "name": name},
            )
        conn.execute(
            text(
                "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                "VALUES (:id, :tid, :subject, :email)"
            ),
            {
                "id": user_id,
                "tid": tenant_id,
                "subject": subject,
                "email": f"{subject}@example.edu",
            },
        )
        conn.execute(
            text(
                "INSERT INTO membership (id, tenant_id, user_id, granted_path, role) "
                "VALUES (:id, :tid, :uid, CAST(:path AS ltree), 'coordinator')"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "uid": user_id, "path": UNIT_PATH},
        )

    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    session = session_factory()
    try:
        ingest_fixture_directory_into_events(
            session,
            tenant_id=tenant_id,
            host_org_unit_id=unit_id,
            directory=FIXTURES,
            root=FIXTURES,
            source_time_zone=SOURCE_ZONE,
            fetched_at=FETCHED_AT,
        )
        session.commit()
    finally:
        session.rollback()
        session.close()

    verifier = FixtureTokenVerifier()
    verifier.register(token, subject)
    client = TestClient(app)
    client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    client.app.state.token_verifier = verifier

    yield client, unit_id, token, tenant_id

    with engine.begin() as conn:
        for table in (
            "event_tag",
            "discovery_review_item",
            "event",
            "membership",
            "resource_grant",
            "user_account",
            "org_unit",
            "rate_limit_counter",
        ):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tenant_id})


def _get(client: TestClient, path: str, token: str | None):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return client.get(path, headers=headers)


def _register_principal(
    engine: Engine,
    client: TestClient,
    tenant_id: uuid.UUID,
    *,
    role: str | None,
    membership_path: str = UNIT_PATH,
    resource_grant_unit_id: uuid.UUID | None = None,
) -> str:
    """Create one more principal in ``tenant_id`` and return a bearer token.

    Same shape as ``tests/contract/test_metrics.py``'s helper of the same name,
    and deliberately so: the interesting variation between these tests is the
    principal, and a second way of building one would make two contract files
    disagree about what "a coordinator" is. ``role=None`` builds the
    bare-``resource_grant`` shape S-007 says must be refused by a role-gated
    operation.
    """
    user_id = uuid.uuid4()
    subject = f"sub-events-{uuid.uuid4().hex}"
    token = f"tok-events-{uuid.uuid4().hex}"

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                "VALUES (:id, :tid, :subject, :email)"
            ),
            {
                "id": user_id,
                "tid": tenant_id,
                "subject": subject,
                "email": f"{subject}@example.edu",
            },
        )
        if role is not None:
            conn.execute(
                text(
                    "INSERT INTO membership (id, tenant_id, user_id, granted_path, role) "
                    "VALUES (:id, :tid, :uid, CAST(:path AS ltree), :role)"
                ),
                {
                    "id": uuid.uuid4(),
                    "tid": tenant_id,
                    "uid": user_id,
                    "path": membership_path,
                    "role": role,
                },
            )
        if resource_grant_unit_id is not None:
            conn.execute(
                text(
                    "INSERT INTO resource_grant "
                    "(id, tenant_id, user_id, resource_type, resource_id, effect) "
                    "VALUES (:id, :tid, :uid, 'org_unit', :rid, 'allow')"
                ),
                {
                    "id": uuid.uuid4(),
                    "tid": tenant_id,
                    "uid": user_id,
                    "rid": resource_grant_unit_id,
                },
            )

    client.app.state.token_verifier.register(token, subject)
    return token


# ---------------------------------------------------------------------------
# The event catalog
# ---------------------------------------------------------------------------


def test_only_the_presentable_event_is_listed(event_context) -> None:
    """Three events were ingested; exactly one reaches a coordinator's list.

    The other two are the two exclusions the route exists to make: one has no
    resolvable date (ADR-0010 rule 2) and one carries a quarantined tag
    (ADR-0012). Both are real rows in ``event`` — this asserts they were
    *withheld*, not that they were never written, which is the distinction the
    integration test on the ingest already pins from the other side.
    """
    client, unit_id, token, _ = event_context

    response = _get(client, f"/v1/units/{unit_id}/events", token)

    assert response.status_code == 200
    body = response.json()
    assert [event["title"] for event in body["events"]] == [DATED_TITLE]


def test_the_withheld_events_are_counted_rather_than_silently_dropped(event_context) -> None:
    """ADR-0011: an omission is not rendered as an absence.

    Without these two numbers a coordinator could not tell "this unit has one
    event" from "this unit has one event and two the pipeline could not
    finish", and the difference is the whole reason the review queue exists.
    """
    client, unit_id, token, _ = event_context

    body = _get(client, f"/v1/units/{unit_id}/events", token).json()

    assert body["withheld_unresolved_date"] == 1
    assert body["withheld_quarantined_tags"] == 1
    assert body["truncated"] is False


def test_an_event_withheld_for_both_reasons_is_counted_once(engine: Engine, event_context) -> None:
    """Two reasons to withhold one event is still one event withheld.

    The undated event is already excluded by ADR-0010 rule 2. Quarantining a
    tag on it as well gives it both reasons at once — a shape the fixture tree
    does not produce naturally, and the one where a naive pair of counts
    reports two withheld events where there is one. The two numbers partition
    the withheld rows rather than tallying reasons, so with one event listed
    they still account for exactly the three events that exist.
    """
    client, unit_id, token, tenant_id = event_context
    with engine.begin() as conn:
        undated_id = conn.execute(
            text("SELECT id FROM event WHERE tenant_id = :tid AND time_precision = 'unresolved'"),
            {"tid": tenant_id},
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO event_tag "
                "(id, tenant_id, event_id, resolution, term, raw_value, vocabulary_version) "
                "VALUES (:id, :tid, :eid, 'quarantined', NULL, :raw, :version)"
            ),
            {
                "id": uuid.uuid4(),
                "tid": tenant_id,
                "eid": undated_id,
                "raw": "Quidditch Club",
                "version": VOCABULARY_VERSION,
            },
        )
        conn.execute(
            text("UPDATE event SET quarantined_tag_count = 1 WHERE id = :eid"),
            {"eid": undated_id},
        )

    body = _get(client, f"/v1/units/{unit_id}/events", token).json()

    assert body["withheld_unresolved_date"] == 1
    assert body["withheld_quarantined_tags"] == 1
    assert (
        len(body["events"]) + body["withheld_unresolved_date"] + body["withheld_quarantined_tags"]
        == 3
    )


def test_the_listed_event_reports_its_precision_and_its_own_zone(event_context) -> None:
    """ADR-0010: the instant, the zone, and the precision, as three facts."""
    client, unit_id, token, _ = event_context

    listed = _get(client, f"/v1/units/{unit_id}/events", token).json()["events"][0]

    assert listed["time"]["precision"] == "exact"
    assert listed["time"]["time_zone"] == SOURCE_ZONE
    assert listed["time"]["starts_at"] is not None
    # No fabricated calendar date beside a real instant: `on_date` belongs to
    # `date_only` and is null here, which `ck_event_temporal_shape` enforces
    # at the column level too.
    assert listed["time"]["on_date"] is None


def test_the_listed_event_carries_only_mapped_vocabulary_terms(event_context) -> None:
    """ADR-0012: quarantined values are never rendered and never matched on."""
    client, unit_id, token, _ = event_context

    listed = _get(client, f"/v1/units/{unit_id}/events", token).json()["events"][0]

    assert sorted(listed["tags"]) == ["hackathon", "keynote"]
    assert UNMAPPED_VALUE not in listed["tags"]


def test_provenance_is_a_structured_field_and_not_part_of_the_title(event_context) -> None:
    """ADR-0012's second defect: a title carrying the name of its source page.

    The response has a place for provenance, and it is not the title. The
    recorded URL names the in-repo document the ingest actually read rather
    than the ``example.edu`` address the fixture advertises, so nothing in this
    body claims a fetch that did not happen.
    """
    client, unit_id, token, _ = event_context

    listed = _get(client, f"/v1/units/{unit_id}/events", token).json()["events"][0]

    assert listed["title"] == DATED_TITLE
    assert listed["provenance"]["origin"] == "extraction"
    assert listed["provenance"]["source_url"] == f"{FIXTURE_URL_SCHEME}engineering_calendar.ics"
    assert listed["provenance"]["extractor_version"] == EXTRACTOR_VERSION
    assert listed["provenance"]["fetched_at"] is not None
    for field in ("source_url", "extractor_version"):
        assert listed["provenance"][field] not in listed["title"]


def test_nothing_listed_claims_to_be_published(event_context) -> None:
    """G3 §5: a first-seen event is awaiting a human, and says so."""
    client, unit_id, token, _ = event_context

    listed = _get(client, f"/v1/units/{unit_id}/events", token).json()["events"][0]

    assert listed["publication_status"] == "unpublished"
    assert listed["review_status"] == "pending"


# ---------------------------------------------------------------------------
# The tag-quarantine queue
# ---------------------------------------------------------------------------


def test_the_quarantine_queue_shows_the_unmapped_value_and_its_event(event_context) -> None:
    """The raw text, unnormalized, tied to the event it came from.

    A reviewer deciding whether ``Underwater Basket Weaving`` belongs in the
    vocabulary needs to see what was on the page and which event it described;
    a folded value or a bare list of strings would answer neither question.
    """
    client, unit_id, token, _ = event_context

    response = _get(client, f"/v1/units/{unit_id}/tag-quarantine", token)

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["raw_value"] == UNMAPPED_VALUE
    assert item["event_title"] == QUARANTINING_TITLE
    assert body["truncated"] is False


def test_each_item_names_the_vocabulary_version_it_was_judged_against(event_context) -> None:
    """A stale judgement and a current one must not look the same.

    G3 §6.3 makes growing the vocabulary a versioned code change, so an item
    queued under an older version may simply resolve now. The response says
    which version judged it and whether that is still the released one, rather
    than leaving a reviewer to assume.
    """
    client, unit_id, token, _ = event_context

    body = _get(client, f"/v1/units/{unit_id}/tag-quarantine", token).json()

    assert body["current_vocabulary_version"] == VOCABULARY_VERSION
    assert body["items"][0]["vocabulary_version"] == VOCABULARY_VERSION
    assert body["items"][0]["judged_against_current_vocabulary"] is True


def test_the_quarantine_queue_offers_no_way_to_decide_an_item(event_context) -> None:
    """Read-only by construction, not by convention.

    Accepting a term is a new ``TagVocabulary`` with a new version signed by
    G3 §6.3's named owner — something no HTTP handler in this codebase can do.
    A decision endpoint would therefore be a control that looks like it works,
    so there is none, and this asserts the absence rather than trusting it.
    """
    client, unit_id, token, _ = event_context
    path = f"/v1/units/{unit_id}/tag-quarantine"

    for method in ("post", "patch", "put", "delete"):
        response = getattr(client, method)(path, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 405, f"{method.upper()} {path} is routed"


# ---------------------------------------------------------------------------
# Authorization, over HTTP
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("suffix", ["events", "tag-quarantine"])
def test_an_unauthenticated_caller_is_refused(event_context, suffix: str) -> None:
    client, unit_id, _, _ = event_context

    response = _get(client, f"/v1/units/{unit_id}/{suffix}", None)

    assert response.status_code == 401


@pytest.mark.parametrize("suffix", ["events", "tag-quarantine"])
def test_an_active_membership_with_the_wrong_role_is_refused(
    engine: Engine, event_context, suffix: str
) -> None:
    """Deny-by-default: at the right unit, still refused for the wrong role."""
    client, unit_id, _, tenant_id = event_context
    token = _register_principal(engine, client, tenant_id, role="student")

    response = _get(client, f"/v1/units/{unit_id}/{suffix}", token)

    assert response.status_code == 403


@pytest.mark.parametrize("suffix", ["events", "tag-quarantine"])
def test_a_coordinator_in_a_sibling_department_is_refused(
    engine: Engine, event_context, suffix: str
) -> None:
    """The role is right and the department is not.

    Neither route passes ``tenant_wide_roles``, so unit scoping is a path
    question here exactly as it is for ``import.create`` and ``review.decide``.
    """
    client, unit_id, _, tenant_id = event_context
    token = _register_principal(
        engine, client, tenant_id, role="coordinator", membership_path=SIBLING_UNIT_PATH
    )

    response = _get(client, f"/v1/units/{unit_id}/{suffix}", token)

    assert response.status_code == 403


@pytest.mark.parametrize("suffix", ["events", "tag-quarantine"])
def test_a_bare_resource_grant_does_not_convey_the_role(
    engine: Engine, event_context, suffix: str
) -> None:
    """S-007: a grant conveys reach, not authority."""
    client, unit_id, _, tenant_id = event_context
    token = _register_principal(
        engine, client, tenant_id, role=None, resource_grant_unit_id=unit_id
    )

    response = _get(client, f"/v1/units/{unit_id}/{suffix}", token)

    assert response.status_code == 403


@pytest.mark.parametrize("suffix", ["events", "tag-quarantine"])
def test_an_unknown_unit_is_a_404_and_not_a_403(event_context, suffix: str) -> None:
    """A 403 would confirm to an unauthorized caller that the id names a row.

    ``load_unit_or_404`` scopes its lookup by the caller's own tenant, so a
    unit id that exists in some other tenant is indistinguishable from one that
    exists nowhere — which is the point.
    """
    client, _, token, _ = event_context

    response = _get(client, f"/v1/units/{uuid.uuid4()}/{suffix}", token)

    assert response.status_code == 404


@pytest.mark.parametrize("suffix", ["events", "tag-quarantine"])
def test_a_coordinator_sees_nothing_from_another_tenants_unit(
    engine: Engine, event_context, suffix: str
) -> None:
    """Tenant isolation is structural and precedes every grant question.

    The second tenant's unit really exists; the first tenant's coordinator
    still gets a 404, because the lookup never leaves their own tenant.
    """
    client, _, token, _ = event_context
    other_tenant_id = uuid.uuid4()
    other_unit_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": other_tenant_id, "slug": f"test-other-{other_tenant_id.hex[:12]}"},
        )
        conn.execute(
            text(
                "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                "VALUES (:id, :tid, CAST(:path AS ltree), 'department', 'Other')"
            ),
            {"id": other_unit_id, "tid": other_tenant_id, "path": UNIT_PATH},
        )

    try:
        response = _get(client, f"/v1/units/{other_unit_id}/{suffix}", token)

        assert response.status_code == 404
    finally:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM org_unit WHERE tenant_id = :tid"), {"tid": other_tenant_id}
            )
            conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": other_tenant_id})


def test_the_events_of_one_unit_do_not_appear_under_another(engine: Engine, event_context) -> None:
    """The listing is scoped by ``host_org_unit_id``, not merely by tenant.

    The sibling unit is in the same tenant and the caller is an admin over
    both, so nothing but the unit filter itself keeps this list empty.
    """
    client, _, _, tenant_id = event_context
    with engine.connect() as conn:
        sibling_unit_id = conn.execute(
            text("SELECT id FROM org_unit WHERE tenant_id = :tid AND path = CAST(:path AS ltree)"),
            {"tid": tenant_id, "path": SIBLING_UNIT_PATH},
        ).scalar_one()
    token = _register_principal(engine, client, tenant_id, role="admin", membership_path="iawest")

    body = _get(client, f"/v1/units/{sibling_unit_id}/events", token).json()

    assert body["events"] == []
    assert body["withheld_unresolved_date"] == 0
    assert body["withheld_quarantined_tags"] == 0
