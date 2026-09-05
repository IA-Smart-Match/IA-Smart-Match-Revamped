"""HTTP contracts for the Speaker Request intake and the Connector's queue.

``tests/authz/test_policy_matrix.py`` owns the full authorization rectangle for
both operations and needs no database to run it. What this file adds is the part
that only exists over HTTP: that authorization is actually reached before any row
is written, that an Event Host really can file and a Student really cannot, that
the queue is narrower than the intake by exactly the Event Host, that a unit in
another tenant is a 404 rather than a 403, and — the one this card turns on —
that a resubmission answers ``200`` against the same request id rather than
filing a second one.

``tests/integration/test_speaker_request_persistence.py`` owns what the writer
does to the rows. Nothing here re-asserts that; what it asserts is that the
response describes those rows rather than the request body, which is why the
interesting assertions read the *response of a second call* rather than the echo
of the first.

Every request is synthetic and nothing in the path under test opens a socket:
there is no field on the request model that could carry a URL, which is customer
§20's out-of-scope external discovery refused by the shape of the contract.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_domain.cba_role_categories import CBA_ROLE_TAXONOMY_VERSION
from smartmatch_domain.naics_sectors import NAICS_TAXONOMY_VERSION
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import Engine, create_engine, text

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)

UNIT_PATH = "iawest.requests"
#: A second department in the same tenant containing none of :data:`UNIT_PATH`.
#: Neither route passes ``tenant_wide_roles``, so ordinary subtree containment
#: applies and a coordinator here must not reach the requests unit.
SIBLING_UNIT_PATH = "iawest.requestssibling"

TITLE = "Analytics Careers Panel"
ON_DATE = "2026-10-14"
STARTS_AT = "2026-10-14T19:30:00Z"
ZONE = "America/Los_Angeles"

FINANCE = "52"
PROFESSIONAL_SERVICES = "54"


def _body(**overrides) -> dict[str, object]:
    """A physical, date-only request. Overrides replace whole fields."""
    body: dict[str, object] = {
        "title": TITLE,
        "time_zone": ZONE,
        "on_date": ON_DATE,
        "is_virtual": False,
        "location_city": "Pomona",
        "industry_codes": [FINANCE],
        "role_codes": ["finance"],
        "description": "A panel on analytics careers for CBA students.",
    }
    body.update(overrides)
    return body


@pytest.fixture(scope="module")
def engine() -> Engine:
    """A live migrated PostgreSQL engine, or skip this contract."""
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1 FROM speaker_request_classification LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}")
    return eng


@pytest.fixture
def request_context(engine: Engine) -> Iterator[tuple[TestClient, uuid.UUID, str, uuid.UUID]]:
    """One tenant, one unit, one sibling unit, and an Event Host in the unit.

    The default principal is a ``volunteer`` — the stored role
    ``smartmatch_domain.role_presentation`` maps onto the **Event Host** persona
    — because §12's host is the caller this surface exists for. A fixture that
    defaulted to a coordinator would let a route that quietly dropped
    ``volunteer`` from its role set pass every test but one.
    """
    tenant_id = uuid.uuid4()
    unit_id = uuid.uuid4()
    sibling_unit_id = uuid.uuid4()
    user_id = uuid.uuid4()
    subject = f"sub-requests-{uuid.uuid4().hex}"
    token = f"tok-requests-{uuid.uuid4().hex}"

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"test-requests-{tenant_id.hex[:12]}"},
        )
        for new_unit_id, path, name in (
            (unit_id, UNIT_PATH, "Requests"),
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
                "VALUES (:id, :tid, :uid, CAST(:path AS ltree), 'volunteer')"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "uid": user_id, "path": UNIT_PATH},
        )

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
            "speaker_request_classification",
            "event_tag",
            "event",
            "membership",
            "resource_grant",
            "user_account",
            "org_unit",
            "rate_limit_counter",
        ):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tenant_id})


def _post(client: TestClient, path: str, token: str | None, body: dict[str, object]):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return client.post(path, json=body, headers=headers)


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

    The same shape ``tests/contract/test_events_api.py`` and
    ``tests/contract/test_metrics.py`` use, and deliberately so: the interesting
    variation between these tests is the principal, and a second way of building
    one would make three contract files disagree about what "a coordinator" is.
    ``role=None`` builds the bare-``resource_grant`` shape S-007 says a
    role-gated operation must refuse.
    """
    user_id = uuid.uuid4()
    subject = f"sub-requests-{uuid.uuid4().hex}"
    token = f"tok-requests-{uuid.uuid4().hex}"

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
# Filing a request
# ---------------------------------------------------------------------------


def test_an_event_host_files_a_request_and_gets_the_stored_row_back(request_context) -> None:
    """Customer §12, end to end, and the response describes the row not the body.

    ``publication_status`` is the tell: nothing in the request mentions it, so a
    handler echoing its input could not produce it.
    """
    client, unit_id, token, _ = request_context

    response = _post(client, f"/v1/units/{unit_id}/speaker-requests", token, _body())

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == TITLE
    assert body["unit_id"] == str(unit_id)
    assert body["time"]["precision"] == "date_only"
    assert body["time"]["on_date"] == ON_DATE
    assert body["time"]["starts_at"] is None
    assert body["time"]["ends_at"] is None
    assert body["time"]["time_zone"] == ZONE
    assert body["is_virtual"] is False
    assert body["location_city"] == "Pomona"
    assert body["location_postal_code"] is None
    # Filing records what a host asked for; it does not publish an event.
    assert body["publication_status"] == "unpublished"
    assert body["review_status"] == "pending"


def test_the_response_carries_both_axes_with_their_taxonomy_versions(request_context) -> None:
    """Multi-select on both axes (customer §§7-8, 12), with the released names.

    ``display_name`` comes from the taxonomy module rather than from the body —
    the request sent codes and nothing else — so a code stored against a
    vocabulary this build does not have could not be rendered at all.
    """
    client, unit_id, token, _ = request_context

    body = _post(
        client,
        f"/v1/units/{unit_id}/speaker-requests",
        token,
        _body(
            industry_codes=[PROFESSIONAL_SERVICES, FINANCE],
            role_codes=["finance", "marketing"],
        ),
    ).json()

    assert [item["code"] for item in body["industries"]] == [FINANCE, PROFESSIONAL_SERVICES]
    assert [item["display_name"] for item in body["industries"]] == [
        "Finance and Insurance",
        "Professional, Scientific, and Technical Services",
    ]
    assert {item["taxonomy_version"] for item in body["industries"]} == {NAICS_TAXONOMY_VERSION}

    assert [item["code"] for item in body["roles"]] == ["finance", "marketing"]
    assert [item["display_name"] for item in body["roles"]] == ["Finance", "Marketing"]
    assert {item["taxonomy_version"] for item in body["roles"]} == {CBA_ROLE_TAXONOMY_VERSION}


def test_a_virtual_request_is_filed_without_a_location(request_context) -> None:
    """Customer §§11-12. The response says virtual and says no place, not a blank one."""
    client, unit_id, token, _ = request_context

    body = _post(
        client,
        f"/v1/units/{unit_id}/speaker-requests",
        token,
        _body(is_virtual=True, location_city=None),
    ).json()

    assert body["is_virtual"] is True
    assert body["location_city"] is None
    assert body["location_postal_code"] is None


def test_an_exact_time_request_keeps_its_instant_and_names_its_zone(request_context) -> None:
    """ADR-0010: the instant the host stated, in the zone the event happens in."""
    client, unit_id, token, _ = request_context

    body = _post(
        client,
        f"/v1/units/{unit_id}/speaker-requests",
        token,
        _body(on_date=None, starts_at=STARTS_AT),
    ).json()

    assert body["time"]["precision"] == "exact"
    assert body["time"]["starts_at"] is not None
    assert body["time"]["on_date"] is None
    assert body["time"]["time_zone"] == ZONE


# ---------------------------------------------------------------------------
# Idempotency over HTTP: the status code is how a caller learns which happened
# ---------------------------------------------------------------------------


def test_refiling_the_same_request_answers_200_with_the_same_id(request_context) -> None:
    """ADR-0012's identity key, as a status code.

    The card's idempotency requirement seen from the outside: two identical
    submissions are one request, and the second says so rather than reporting a
    creation that did not happen.
    """
    client, unit_id, token, _ = request_context

    first = _post(client, f"/v1/units/{unit_id}/speaker-requests", token, _body())
    second = _post(client, f"/v1/units/{unit_id}/speaker-requests", token, _body())

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["request_id"] == first.json()["request_id"]


def test_a_resubmission_replaces_the_targets_it_no_longer_names(request_context) -> None:
    """A host removing an industry sees it gone, not merely un-added."""
    client, unit_id, token, _ = request_context

    _post(
        client,
        f"/v1/units/{unit_id}/speaker-requests",
        token,
        _body(industry_codes=[FINANCE, PROFESSIONAL_SERVICES]),
    )
    body = _post(
        client,
        f"/v1/units/{unit_id}/speaker-requests",
        token,
        _body(industry_codes=[PROFESSIONAL_SERVICES]),
    ).json()

    assert [item["code"] for item in body["industries"]] == [PROFESSIONAL_SERVICES]


# ---------------------------------------------------------------------------
# What the intake refuses
# ---------------------------------------------------------------------------


def test_a_request_with_no_date_is_refused(request_context) -> None:
    """ADR-0010 rule 2 and ADR-0012, refused at intake rather than filed unresolved."""
    client, unit_id, token, _ = request_context

    response = _post(client, f"/v1/units/{unit_id}/speaker-requests", token, _body(on_date=None))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "speaker_request_time_required"


def test_a_request_dated_two_ways_is_refused(request_context) -> None:
    """Two answers to one question; picking one silently would discard the other."""
    client, unit_id, token, _ = request_context

    response = _post(
        client, f"/v1/units/{unit_id}/speaker-requests", token, _body(starts_at=STARTS_AT)
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "speaker_request_time_ambiguous"


def test_an_unreleased_industry_code_is_refused(request_context) -> None:
    """The vocabulary is closed. There is no quarantine arm on this surface."""
    client, unit_id, token, _ = request_context

    response = _post(
        client, f"/v1/units/{unit_id}/speaker-requests", token, _body(industry_codes=["99"])
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "speaker_request_unknown_industry"


def test_an_unreleased_role_code_is_refused(request_context) -> None:
    client, unit_id, token, _ = request_context

    response = _post(
        client, f"/v1/units/{unit_id}/speaker-requests", token, _body(role_codes=["wizardry"])
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "speaker_request_unknown_role"


def test_a_virtual_request_carrying_a_location_is_refused(request_context) -> None:
    """Customer §11: a place the scoring rule must ignore is not stored at all."""
    client, unit_id, token, _ = request_context

    response = _post(
        client,
        f"/v1/units/{unit_id}/speaker-requests",
        token,
        _body(is_virtual=True, location_city="Pomona"),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "speaker_request_invalid"


def test_a_physical_request_with_no_place_is_refused(request_context) -> None:
    """OQ-CBA-011(a), fail-closed rather than stored as an unscoreable request."""
    client, unit_id, token, _ = request_context

    response = _post(
        client, f"/v1/units/{unit_id}/speaker-requests", token, _body(location_city=None)
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "speaker_request_invalid"


def test_a_request_naming_no_industry_is_refused_by_the_schema(request_context) -> None:
    """``min_length=1`` on the array: the floor is in the contract, not only in prose."""
    client, unit_id, token, _ = request_context

    response = _post(
        client, f"/v1/units/{unit_id}/speaker-requests", token, _body(industry_codes=[])
    )

    assert response.status_code == 422


def test_a_naive_start_instant_is_refused_rather_than_assumed_to_be_utc(
    request_context,
) -> None:
    """ADR-0010's own refusal, reaching the caller as a 400 and not a 500.

    A naive datetime is a fact about the submitted body, so answering ``500``
    would report a server fault for a client mistake — and accepting it would be
    the legacy defect of relabelling a local time as UTC.
    """
    client, unit_id, token, _ = request_context

    response = _post(
        client,
        f"/v1/units/{unit_id}/speaker-requests",
        token,
        _body(on_date=None, starts_at="2026-10-14T19:30:00"),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "speaker_request_invalid_time"


def test_an_unknown_time_zone_is_refused(request_context) -> None:
    """ADR-0010 rule 1: the zone is resolved against the real tz database."""
    client, unit_id, token, _ = request_context

    response = _post(
        client, f"/v1/units/{unit_id}/speaker-requests", token, _body(time_zone="Mars/Olympus")
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "speaker_request_invalid_time"


# ---------------------------------------------------------------------------
# Authorization, over HTTP, before any row is written
# ---------------------------------------------------------------------------


def test_a_student_may_not_file_a_request(engine: Engine, request_context) -> None:
    """Customer §15 gives a Student browsing and feedback, not the asking."""
    client, unit_id, _, tenant_id = request_context
    student = _register_principal(engine, client, tenant_id, role="student")

    response = _post(client, f"/v1/units/{unit_id}/speaker-requests", student, _body())

    assert response.status_code == 403


def test_a_coordinator_may_file_a_request(engine: Engine, request_context) -> None:
    """The Speaker Connector persona, which already owns every other write here."""
    client, unit_id, _, tenant_id = request_context
    coordinator = _register_principal(engine, client, tenant_id, role="coordinator")

    response = _post(client, f"/v1/units/{unit_id}/speaker-requests", coordinator, _body())

    assert response.status_code == 201


def test_a_sibling_departments_coordinator_may_not_file_into_this_unit(
    engine: Engine, request_context
) -> None:
    """Ordinary subtree containment. Neither route passes ``tenant_wide_roles``."""
    client, unit_id, _, tenant_id = request_context
    sibling = _register_principal(
        engine, client, tenant_id, role="coordinator", membership_path=SIBLING_UNIT_PATH
    )

    response = _post(client, f"/v1/units/{unit_id}/speaker-requests", sibling, _body())

    assert response.status_code == 403


def test_a_bare_resource_grant_may_not_file_a_request(engine: Engine, request_context) -> None:
    """S-007: a grant conveys reach, not authority."""
    client, unit_id, _, tenant_id = request_context
    granted = _register_principal(
        engine, client, tenant_id, role=None, resource_grant_unit_id=unit_id
    )

    response = _post(client, f"/v1/units/{unit_id}/speaker-requests", granted, _body())

    assert response.status_code == 403


def test_an_unauthenticated_caller_may_not_file_a_request(request_context) -> None:
    client, unit_id, _, _ = request_context

    assert _post(client, f"/v1/units/{unit_id}/speaker-requests", None, _body()).status_code == 401


def test_a_unit_in_another_tenant_is_a_404(request_context) -> None:
    """A unit this tenant does not own must not be confirmed to exist by a 403."""
    client, _, token, _ = request_context

    response = _post(client, f"/v1/units/{uuid.uuid4()}/speaker-requests", token, _body())

    assert response.status_code == 404


def test_authorization_is_reached_before_the_body_is_validated(
    engine: Engine, request_context
) -> None:
    """A caller who may not file learns that, not which of their fields was wrong.

    Ordering asserted rather than assumed: a route that validated first would
    tell an unauthorized caller about the taxonomy, which is a small disclosure
    on this surface and a habit that is not small anywhere.
    """
    client, unit_id, _, tenant_id = request_context
    student = _register_principal(engine, client, tenant_id, role="student")

    response = _post(
        client,
        f"/v1/units/{unit_id}/speaker-requests",
        student,
        _body(industry_codes=["99"], on_date=None),
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# The Connector's queue
# ---------------------------------------------------------------------------


def test_a_coordinator_reads_the_queue(engine: Engine, request_context) -> None:
    """Customer §13: the Speaker Connector sees the requests filed under the unit."""
    client, unit_id, host_token, tenant_id = request_context
    _post(client, f"/v1/units/{unit_id}/speaker-requests", host_token, _body())
    coordinator = _register_principal(engine, client, tenant_id, role="coordinator")

    response = _get(client, f"/v1/units/{unit_id}/speaker-requests", coordinator)

    assert response.status_code == 200
    body = response.json()
    assert [item["title"] for item in body["requests"]] == [TITLE]
    assert body["truncated"] is False


def test_the_event_host_who_filed_may_not_read_the_queue(request_context) -> None:
    """The one cell where the read is narrower than the write (OQ-CBA-011(b)).

    §13 names only the Speaker Connector, and the queue holds every host's
    request text for the unit. The host is not left blind: the filing response
    already handed them their own request, and a resubmission hands it back.
    """
    client, unit_id, host_token, _ = request_context
    filed = _post(client, f"/v1/units/{unit_id}/speaker-requests", host_token, _body())
    assert filed.status_code == 201

    response = _get(client, f"/v1/units/{unit_id}/speaker-requests", host_token)

    assert response.status_code == 403


def test_a_student_may_not_read_the_queue(engine: Engine, request_context) -> None:
    client, unit_id, _, tenant_id = request_context
    student = _register_principal(engine, client, tenant_id, role="student")

    assert _get(client, f"/v1/units/{unit_id}/speaker-requests", student).status_code == 403


def test_the_queue_is_scoped_to_its_unit(engine: Engine, request_context) -> None:
    """A request filed in one department is not a sibling's queue item."""
    client, unit_id, host_token, tenant_id = request_context
    _post(client, f"/v1/units/{unit_id}/speaker-requests", host_token, _body())
    admin = _register_principal(engine, client, tenant_id, role="admin", membership_path="iawest")

    with engine.begin() as conn:
        sibling_unit_id = conn.execute(
            text("SELECT id FROM org_unit WHERE tenant_id = :tid AND path = CAST(:p AS ltree)"),
            {"tid": tenant_id, "p": SIBLING_UNIT_PATH},
        ).scalar_one()

    body = _get(client, f"/v1/units/{sibling_unit_id}/speaker-requests", admin).json()

    assert body["requests"] == []
    assert body["truncated"] is False
