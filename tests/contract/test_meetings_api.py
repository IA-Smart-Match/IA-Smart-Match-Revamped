"""HTTP contract for the internal CBA meeting record (migration ``0034``).

Every row asserted here is a real ``cba_meeting`` row written through the route
into a throwaway tenant this module creates and deletes. Nothing is mocked: a
route that returned a clean ``201`` and stored nothing is a live failure mode in
this codebase — ``get_session`` rolls back unconditionally — so the write tests
read the listing back rather than trusting the status code.

``tests/authz/test_policy_matrix.py`` owns the full authorization rectangle for
both operations and needs no database. What this file adds is the part that only
exists over HTTP:

* **the refusal.** A meeting whose time carries no UTC offset is a ``422`` naming
  the missing fact, and **no row is written**. That is ADR-0010 rule 2 and
  migration finding F-003 — the legacy turned an unparsed date into "thirty days
  from now" and fabricated a slot nobody chose — and the assertion that the table
  is still empty afterwards is the half that distinguishes a refusal from a
  fabrication.
* a unit in another tenant is a ``404`` rather than a ``403`` that would confirm
  the id names something real;
* a sibling department's coordinator is refused;
* a student is refused, on both routes;
* the recorder is the verified principal and cannot be chosen by the body.

What this file also asserts by omission: **no response carries a participant of
any kind**, because no model has a field one could travel in. What a meeting with
the CBA team is contractually — who may book, whether an external participant is
a ``user_account``, whether a booking ever leaves the system — is **OQ-CBA-066**,
open.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import Engine, create_engine, text

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)

UNIT_PATH = "iawest.meetings"
#: A second department in the same tenant containing none of :data:`UNIT_PATH`.
#: Neither route passes ``tenant_wide_roles``, so ordinary subtree containment
#: applies and a coordinator here must not reach the meetings unit.
SIBLING_UNIT_PATH = "iawest.meetingsibling"

#: The zone every meeting below is agreed in. A real IANA name, because the
#: column stores the zone the people in the room used.
ZONE = "America/Los_Angeles"

#: An instant with an explicit offset — the only shape the route accepts.
SCHEDULED_AT = "2026-09-15T17:00:00+00:00"

#: The same wall-clock reading with **no** offset. Not an instant: resolving it
#: would mean picking a zone on the unit's behalf, which is the defect this
#: surface exists to refuse.
SCHEDULED_AT_WITHOUT_OFFSET = "2026-09-15T17:00:00"


def _meetings_path(unit_id: uuid.UUID) -> str:
    return f"/v1/units/{unit_id}/meetings"


@pytest.fixture(scope="module")
def engine() -> Engine:
    """A live migrated PostgreSQL engine, or skip this contract."""
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1 FROM cba_meeting LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}")
    return eng


def _register_principal(
    engine: Engine,
    tenant_id: uuid.UUID,
    verifier: FixtureTokenVerifier,
    *,
    role: str | None,
    membership_path: str = UNIT_PATH,
) -> tuple[str, uuid.UUID]:
    """Create one more principal in ``tenant_id``; return its bearer token and id.

    Same shape as ``tests/contract/test_engagement_api.py``'s helper of the same
    name, deliberately: the interesting variation between these files is the
    route, and a second way of building "a coordinator" would let two contract
    files disagree about what one is.

    The user id is returned as well as the token because one assertion below is
    about *which* account the server recorded as the author.
    """
    user_id = uuid.uuid4()
    subject = f"sub-meetings-{uuid.uuid4().hex}"
    token = f"tok-meetings-{uuid.uuid4().hex}"

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

    verifier.register(token, subject)
    return token, user_id


def _provision_tenant(engine: Engine) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """One tenant with two departments in it."""
    tenant_id = uuid.uuid4()
    unit_id = uuid.uuid4()
    sibling_unit_id = uuid.uuid4()

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"test-meetings-{tenant_id.hex[:12]}"},
        )
        for new_unit_id, path, name in (
            (unit_id, UNIT_PATH, "Meetings"),
            (sibling_unit_id, SIBLING_UNIT_PATH, "Sibling"),
        ):
            conn.execute(
                text(
                    "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                    "VALUES (:id, :tid, CAST(:path AS ltree), 'department', :name)"
                ),
                {"id": new_unit_id, "tid": tenant_id, "path": path, "name": name},
            )
    return tenant_id, unit_id, sibling_unit_id


def _drop_tenant(engine: Engine, tenant_id: uuid.UUID) -> None:
    with engine.begin() as conn:
        for table in (
            "cba_meeting",
            "membership",
            "resource_grant",
            "user_account",
            "org_unit",
            "rate_limit_counter",
        ):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tenant_id})


@pytest.fixture
def meetings_context(engine: Engine) -> Iterator[dict[str, object]]:
    """One tenant, two departments, one coordinator, and an empty meeting table."""
    tenant_id, unit_id, sibling_unit_id = _provision_tenant(engine)

    verifier = FixtureTokenVerifier()
    client = TestClient(app)
    client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    client.app.state.token_verifier = verifier

    token, user_id = _register_principal(engine, tenant_id, verifier, role="coordinator")

    yield {
        "client": client,
        "engine": engine,
        "verifier": verifier,
        "tenant_id": tenant_id,
        "unit_id": unit_id,
        "sibling_unit_id": sibling_unit_id,
        "token": token,
        "user_id": user_id,
    }

    _drop_tenant(engine, tenant_id)


def _post(client: TestClient, path: str, token: str | None, body: dict[str, object]):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(path, headers=headers, json=body)


def _get(client: TestClient, path: str, token: str | None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.get(path, headers=headers)


def _record(context: dict[str, object], token: str | None = None, **overrides: object):
    body: dict[str, object] = {
        "title": "CBA team sync",
        "scheduled_at": SCHEDULED_AT,
        "time_zone": ZONE,
        "location_or_link": "Bldg 9-241",
    }
    body.update(overrides)
    return _post(
        context["client"],  # type: ignore[arg-type]
        _meetings_path(context["unit_id"]),  # type: ignore[arg-type]
        context["token"] if token is None else token,  # type: ignore[arg-type]
        body,
    )


def _list(context: dict[str, object], token: str | None = None):
    return _get(
        context["client"],  # type: ignore[arg-type]
        _meetings_path(context["unit_id"]),  # type: ignore[arg-type]
        context["token"] if token is None else token,  # type: ignore[arg-type]
    )


def _stored_count(engine: Engine, tenant_id: uuid.UUID) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                text("SELECT count(*) FROM cba_meeting WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            ).scalar_one()
        )


# ---------------------------------------------------------------------------
# The refusal this surface exists to make
# ---------------------------------------------------------------------------


def test_a_meeting_with_an_offsetless_time_is_refused_and_nothing_is_stored(
    meetings_context,
) -> None:
    """The invariant, over HTTP. ADR-0010 rule 2, finding F-003.

    Both halves matter. The ``422`` is what the caller sees; the empty table is
    what says the server refused rather than resolved. A route that assigned a
    zone and stored the row would answer ``201`` and pass no assertion here — but
    a route that stored the row *and* complained would pass a status-code-only
    test while leaving exactly the fabricated slot this rule exists to prevent.
    """
    response = _record(meetings_context, scheduled_at=SCHEDULED_AT_WITHOUT_OFFSET)

    assert response.status_code == 422
    assert _stored_count(meetings_context["engine"], meetings_context["tenant_id"]) == 0


def test_a_meeting_with_no_time_at_all_is_refused(meetings_context) -> None:
    """An absent ``scheduled_at`` is a ``422`` from the request model.

    The outermost of the three layers that refuse this. The repository and the
    column refuse it too, and none of the three is load-bearing alone.
    """
    body = {"title": "CBA team sync", "time_zone": ZONE}
    response = _post(
        meetings_context["client"],
        _meetings_path(meetings_context["unit_id"]),
        meetings_context["token"],
        body,
    )

    assert response.status_code == 422
    assert _stored_count(meetings_context["engine"], meetings_context["tenant_id"]) == 0


def test_a_meeting_with_no_zone_is_refused(meetings_context) -> None:
    """The zone is required, because it is the half the instant cannot recover.

    A surface that wants to say "5pm" has to know 5pm where, and a route that
    accepted a missing zone would leave every rendering to guess one — the same
    fabrication as an unresolved time, one column over.
    """
    body = {"title": "CBA team sync", "scheduled_at": SCHEDULED_AT}
    response = _post(
        meetings_context["client"],
        _meetings_path(meetings_context["unit_id"]),
        meetings_context["token"],
        body,
    )

    assert response.status_code == 422
    assert _stored_count(meetings_context["engine"], meetings_context["tenant_id"]) == 0


# ---------------------------------------------------------------------------
# The happy path, read back out of the table
# ---------------------------------------------------------------------------


def test_a_coordinator_records_a_meeting_and_it_is_in_the_listing(meetings_context) -> None:
    """201, the row is stored, and the listing returns it."""
    created = _record(meetings_context)
    assert created.status_code == 201

    body = created.json()
    assert body["title"] == "CBA team sync"
    assert body["time_zone"] == ZONE
    assert body["location_or_link"] == "Bldg 9-241"
    assert body["status"] == "scheduled"
    assert body["unit_id"] == str(meetings_context["unit_id"])

    assert _stored_count(meetings_context["engine"], meetings_context["tenant_id"]) == 1

    listed = _list(meetings_context)
    assert listed.status_code == 200
    listing = listed.json()
    assert listing["total"] == 1
    assert [row["id"] for row in listing["meetings"]] == [body["id"]]


def test_the_stored_time_is_the_instant_that_was_sent(meetings_context) -> None:
    """No shifting, no re-zoning. What went in is what comes back.

    The response renders ``scheduled_at`` as an ISO-8601 string, so this compares
    instants rather than spellings — ``+00:00`` and ``Z`` are the same moment and
    the assertion should not depend on which one the serializer chose.
    """
    created = _record(meetings_context)
    assert created.status_code == 201

    returned = datetime.fromisoformat(created.json()["scheduled_at"])
    assert returned == datetime.fromisoformat(SCHEDULED_AT)


def test_a_meeting_with_no_location_reports_null_rather_than_a_blank(meetings_context) -> None:
    """A whitespace-only location means "nobody has said", not a stored blank.

    ``ck_cba_meeting_location_shape`` refuses ``''`` outright, so without the
    normalization this would be a ``500`` from an ``IntegrityError`` rather than
    the answer the caller actually meant.
    """
    created = _record(meetings_context, location_or_link="   ")

    assert created.status_code == 201
    assert created.json()["location_or_link"] is None


def test_the_recorder_is_the_verified_principal_and_the_body_cannot_choose_it(
    meetings_context,
) -> None:
    """MM-A01: caller-selected identity has no field to enter through.

    The extra keys are ignored by the request model rather than honoured, and the
    stored author is the token's own account. A route that accepted either field
    would let a coordinator file a meeting under somebody else's name.
    """
    created = _record(
        meetings_context,
        created_by_user_id=str(uuid.uuid4()),
        status="cancelled",
    )
    assert created.status_code == 201

    # The body could not choose the status either: every meeting starts
    # `scheduled`, because one recorded as already cancelled is a meeting that
    # was never arranged.
    assert created.json()["status"] == "scheduled"

    with meetings_context["engine"].connect() as conn:
        author = conn.execute(
            text("SELECT created_by_user_id FROM cba_meeting WHERE id = :id"),
            {"id": created.json()["id"]},
        ).scalar_one()
    assert author == meetings_context["user_id"]


def test_no_response_carries_a_participant_of_any_kind(meetings_context) -> None:
    """OQ-CBA-066 is open, and the API says nothing it has not decided.

    Asserted as an exact key set rather than as a handful of ``not in`` checks:
    a field added by a later edit fails here whatever it is called, which is the
    property a list of forbidden names would not have.
    """
    created = _record(meetings_context)
    assert created.status_code == 201

    assert set(created.json()) == {
        "id",
        "unit_id",
        "title",
        "scheduled_at",
        "time_zone",
        "location_or_link",
        "status",
        "recorded_at",
        "updated_at",
    }


def test_the_listing_reports_a_measured_total_beside_a_bounded_page(meetings_context) -> None:
    """``total`` is counted in the database, so a truncated page is visible as one."""
    for index in range(3):
        assert _record(meetings_context, title=f"Meeting {index}").status_code == 201

    listed = _get(
        meetings_context["client"],
        f"{_meetings_path(meetings_context['unit_id'])}?limit=2",
        meetings_context["token"],
    )

    assert listed.status_code == 200
    body = listed.json()
    assert len(body["meetings"]) == 2
    assert body["total"] == 3
    assert body["limit"] == 2


def test_an_empty_unit_reports_a_measured_zero(meetings_context) -> None:
    """The query ran and found none — a different claim from "we did not look"."""
    listed = _list(meetings_context)

    assert listed.status_code == 200
    assert listed.json() == {
        "unit_id": str(meetings_context["unit_id"]),
        "meetings": [],
        "total": 0,
        "limit": 100,
    }


# ---------------------------------------------------------------------------
# Refusals that only exist over HTTP
# ---------------------------------------------------------------------------


def test_a_student_may_not_record_a_meeting(meetings_context) -> None:
    """A unit's internal schedule is operational detail; §15 gives a Student no part in it."""
    token, _ = _register_principal(
        meetings_context["engine"],
        meetings_context["tenant_id"],
        meetings_context["verifier"],
        role="student",
    )

    assert _record(meetings_context, token=token).status_code == 403
    assert _stored_count(meetings_context["engine"], meetings_context["tenant_id"]) == 0


def test_a_student_may_not_read_the_listing(meetings_context) -> None:
    """The read is refused on the same terms as the write, and the rectangle agrees."""
    token, _ = _register_principal(
        meetings_context["engine"],
        meetings_context["tenant_id"],
        meetings_context["verifier"],
        role="student",
    )

    assert _list(meetings_context, token=token).status_code == 403


def test_a_sibling_departments_coordinator_is_refused_on_both_routes(meetings_context) -> None:
    """Ordinary subtree containment: neither route passes ``tenant_wide_roles``."""
    token, _ = _register_principal(
        meetings_context["engine"],
        meetings_context["tenant_id"],
        meetings_context["verifier"],
        role="coordinator",
        membership_path=SIBLING_UNIT_PATH,
    )

    assert _record(meetings_context, token=token).status_code == 403
    assert _list(meetings_context, token=token).status_code == 403
    assert _stored_count(meetings_context["engine"], meetings_context["tenant_id"]) == 0


def test_a_unit_in_another_tenant_is_a_404_rather_than_a_403(meetings_context) -> None:
    """A denial distinguished from an absence is an existence oracle.

    ``load_unit_or_404`` scopes the lookup by the caller's own tenant, so this
    coordinator learns nothing about whether the other tenant's unit exists —
    which it does.
    """
    other_tenant_id, other_unit_id, _sibling = _provision_tenant(meetings_context["engine"])
    try:
        path = _meetings_path(other_unit_id)
        created = _post(
            meetings_context["client"],
            path,
            meetings_context["token"],
            {"title": "CBA team sync", "scheduled_at": SCHEDULED_AT, "time_zone": ZONE},
        )
        assert created.status_code == 404
        assert _get(meetings_context["client"], path, meetings_context["token"]).status_code == 404
        assert _stored_count(meetings_context["engine"], other_tenant_id) == 0
    finally:
        _drop_tenant(meetings_context["engine"], other_tenant_id)


def test_an_unauthenticated_caller_reaches_neither_route(meetings_context) -> None:
    """Both routes take a ``CurrentPrincipal``; neither is public.

    ``token=""`` rather than ``token=None``: ``None`` means "use this context's
    coordinator" in the helpers above, which is the convention
    ``tests/contract/test_engagement_api.py`` uses for the same assertion. An
    empty string sends no ``Authorization`` header at all.
    """
    assert _record(meetings_context, token="").status_code == 401
    assert _list(meetings_context, token="").status_code == 401
