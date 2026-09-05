"""HTTP contract for the unit-scoped attendance summary.

The rows counted here are real ``attendance_record`` rows written through
:class:`~smartmatch_persistence.attendance.AttendanceRepository` — the same
writer the synthetic seed path uses — against real ``event`` rows, so what is
asserted is the whole path from evidence to response rather than a shape a
fixture invented. Every row is synthetic and belongs to a throwaway tenant this
module creates and deletes.

``tests/authz/test_policy_matrix.py`` owns the full authorization rectangle for
this operation and needs no database to run it. What this file adds is the part
that only exists over HTTP: that authorization is reached before any attendance
row is read, that a unit in another tenant is a 404 rather than a 403, that a
sibling department's coordinator is refused, and — the claim D8 rests on — that
no response body carries a student identifier.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_persistence.attendance import AttendanceRepository
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import sessionmaker

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)

UNIT_PATH = "iawest.engagement"
#: A second department in the same tenant containing none of :data:`UNIT_PATH`.
#: The route passes no ``tenant_wide_roles``, so ordinary subtree containment
#: applies and a coordinator here must not reach the engagement unit.
SIBLING_UNIT_PATH = "iawest.sibling"

ON_DATE = date(2026, 9, 1)
FETCHED_AT = datetime(2026, 9, 3, 17, 0, tzinfo=UTC)

#: Three students, two events, and six attendance rows across three mechanisms.
#: Small enough to state the expected summary as a literal below rather than as
#: arithmetic this test would then be checking against itself.
_ATTENDANCE_PLAN = (
    (0, 0, "qr_scan"),
    (1, 0, "qr_scan"),
    (2, 0, "qr_scan"),
    (0, 1, "qr_scan"),
    (1, 1, "coordinator_entry"),
    (2, 1, "import"),
)

SUMMARY_PATH_SUFFIX = "engagement/attendance-summary"


def _summary_path(unit_id: uuid.UUID) -> str:
    return f"/v1/units/{unit_id}/{SUMMARY_PATH_SUFFIX}"


@pytest.fixture(scope="module")
def engine() -> Engine:
    """A live migrated PostgreSQL engine, or skip this contract."""
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1 FROM attendance_record LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}")
    return eng


def _insert_event(conn, *, tenant_id: uuid.UUID, unit_id: uuid.UUID, title: str) -> uuid.UUID:
    """One coordinator-entered, date-only event. No crawler, no source URL.

    ``origin='coordinator_entry'`` with a null ``source_url`` is what
    ``ck_event_provenance_evidence`` requires of an event nobody extracted, and
    it is the honest origin here: the product note for this surface is that
    coordinators add events manually.
    """
    event_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO event (id, tenant_id, host_org_unit_id, title, normalized_title, "
            "on_date, time_zone, time_precision, resolved_date, origin) "
            "VALUES (:id, :tid, :uid, :title, :normalized, :on_date, 'America/Los_Angeles', "
            "'date_only', :on_date, 'coordinator_entry')"
        ),
        {
            "id": event_id,
            "tid": tenant_id,
            "uid": unit_id,
            "title": title,
            "normalized": title.lower(),
            "on_date": ON_DATE,
        },
    )
    return event_id


def _register_principal(
    engine: Engine,
    tenant_id: uuid.UUID,
    verifier: FixtureTokenVerifier,
    *,
    role: str | None,
    membership_path: str = UNIT_PATH,
    resource_grant_unit_id: uuid.UUID | None = None,
) -> str:
    """Create one more principal in ``tenant_id`` and return a bearer token.

    Same shape as ``tests/contract/test_events_api.py``'s helper of the same
    name, deliberately: the interesting variation between these files is the
    route, and a second way of building "a coordinator" would let two contract
    files disagree about what one is. ``role=None`` builds the bare
    ``resource_grant`` shape S-007 says a role-gated operation must refuse.
    """
    user_id = uuid.uuid4()
    subject = f"sub-engagement-{uuid.uuid4().hex}"
    token = f"tok-engagement-{uuid.uuid4().hex}"

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

    verifier.register(token, subject)
    return token


@pytest.fixture
def engagement_context(engine: Engine) -> Iterator[dict[str, object]]:
    """One tenant, two departments, six attendance rows, one coordinator."""
    tenant_id = uuid.uuid4()
    unit_id = uuid.uuid4()
    sibling_unit_id = uuid.uuid4()
    student_ids = [uuid.uuid4() for _ in range(3)]

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"test-engagement-{tenant_id.hex[:12]}"},
        )
        for new_unit_id, path, name in (
            (unit_id, UNIT_PATH, "Engagement"),
            (sibling_unit_id, SIBLING_UNIT_PATH, "Sibling"),
        ):
            conn.execute(
                text(
                    "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                    "VALUES (:id, :tid, CAST(:path AS ltree), 'department', :name)"
                ),
                {"id": new_unit_id, "tid": tenant_id, "path": path, "name": name},
            )
        for index, student_id in enumerate(student_ids):
            subject = f"sub-student-{student_id.hex}"
            conn.execute(
                text(
                    "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                    "VALUES (:id, :tid, :subject, :email)"
                ),
                {
                    "id": student_id,
                    "tid": tenant_id,
                    "subject": subject,
                    "email": f"student{index}-{student_id.hex[:8]}@example.edu",
                },
            )
        event_ids = [
            _insert_event(conn, tenant_id=tenant_id, unit_id=unit_id, title=title)
            for title in ("Autumn Kickoff", "Analytics Night")
        ]
        # One event under the sibling department, so a later assertion can show
        # that unit scoping is what separates the two counts.
        sibling_event_id = _insert_event(
            conn, tenant_id=tenant_id, unit_id=sibling_unit_id, title="Sibling Social"
        )

    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    session = session_factory()
    attendance = AttendanceRepository()
    try:
        for student_index, event_index, method in _ATTENDANCE_PLAN:
            attendance.record_attendance(
                session,
                tenant_id=tenant_id,
                owning_unit_id=unit_id,
                subject_id=student_ids[student_index],
                event_id=event_ids[event_index],
                method=method,
            )
        # One row under the sibling department. If the summary ever counted it,
        # the unit scoping in the query would have stopped working.
        attendance.record_attendance(
            session,
            tenant_id=tenant_id,
            owning_unit_id=sibling_unit_id,
            subject_id=student_ids[0],
            event_id=sibling_event_id,
            method="coordinator_entry",
        )
        session.commit()
    finally:
        session.rollback()
        session.close()

    verifier = FixtureTokenVerifier()
    client = TestClient(app)
    client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    client.app.state.token_verifier = verifier

    token = _register_principal(engine, tenant_id, verifier, role="coordinator")

    yield {
        "client": client,
        "engine": engine,
        "verifier": verifier,
        "tenant_id": tenant_id,
        "unit_id": unit_id,
        "sibling_unit_id": sibling_unit_id,
        "student_ids": student_ids,
        "token": token,
    }

    with engine.begin() as conn:
        for table in (
            "attendance_record",
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
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.get(path, headers=headers)


def _read_summary(context: dict[str, object], token: str | None = None):
    return _get(
        context["client"],  # type: ignore[arg-type]
        _summary_path(context["unit_id"]),  # type: ignore[arg-type]
        context["token"] if token is None else token,  # type: ignore[arg-type]
    )


def test_the_summary_counts_the_units_own_attendance_rows(engagement_context) -> None:
    """Six rows, three mechanisms, three students, two events — and the total is the sum."""
    response = _read_summary(engagement_context)

    assert response.status_code == 200
    body = response.json()

    assert body["unit_id"] == str(engagement_context["unit_id"])
    assert body["by_method"] == {"qr_scan": 4, "coordinator_entry": 1, "import": 1}
    assert body["total"] == 6 == sum(body["by_method"].values())
    assert body["distinct_subjects"] == 3
    assert body["distinct_events"] == 2


def test_every_method_in_the_vocabulary_is_reported(engagement_context) -> None:
    """All three keys, always. A mechanism with no rows is a measured 0 (ADR-0011)."""
    body = _read_summary(engagement_context).json()

    assert set(body["by_method"]) == {"qr_scan", "coordinator_entry", "import"}


def test_the_sibling_departments_row_is_not_counted(engagement_context) -> None:
    """The unit scoping is a `WHERE` clause on `owning_unit_id`, not a filter afterwards.

    A seventh attendance row exists in this tenant, under the sibling
    department. The summary above totals six, and the sibling's own summary
    totals one — the same fact stated from both sides, so a query that lost its
    unit predicate would fail here rather than merely inflate a number nobody
    checked.
    """
    admin_token = _register_principal(
        engagement_context["engine"],
        engagement_context["tenant_id"],
        engagement_context["verifier"],
        role="admin",
        membership_path="iawest",
    )

    response = _get(
        engagement_context["client"],
        _summary_path(engagement_context["sibling_unit_id"]),
        admin_token,
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_the_response_names_no_student(engagement_context) -> None:
    """The D8 claim, checked against the raw body rather than against the model.

    None of the three seeded students' ids may appear anywhere in the response
    text, and no field may be named for one. This is what makes the summary
    publishable while the disclosure-consent policy is still open.
    """
    response = _read_summary(engagement_context)
    raw = response.text

    for student_id in engagement_context["student_ids"]:
        assert str(student_id) not in raw

    body = response.json()
    assert not [key for key in body if "subject_id" in key or "email" in key]


def test_a_unit_with_no_attendance_reports_a_measured_zero(engagement_context) -> None:
    """Zero rows, three zeroed methods, two null instants — not an error, not an absence."""
    empty_unit_id = uuid.uuid4()
    with engagement_context["engine"].begin() as conn:
        conn.execute(
            text(
                "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                "VALUES (:id, :tid, CAST(:path AS ltree), 'department', 'Empty')"
            ),
            {
                "id": empty_unit_id,
                "tid": engagement_context["tenant_id"],
                "path": "iawest.empty",
            },
        )
    token = _register_principal(
        engagement_context["engine"],
        engagement_context["tenant_id"],
        engagement_context["verifier"],
        role="coordinator",
        membership_path="iawest.empty",
    )

    response = _get(engagement_context["client"], _summary_path(empty_unit_id), token)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["by_method"] == {"qr_scan": 0, "coordinator_entry": 0, "import": 0}
    assert body["first_recorded_at"] is None
    assert body["last_recorded_at"] is None


def test_the_recorded_instants_bracket_the_rows(engagement_context) -> None:
    """Both bounds are present whenever rows are, and the first is not after the last."""
    body = _read_summary(engagement_context).json()

    assert body["first_recorded_at"] is not None
    assert body["last_recorded_at"] is not None
    assert body["first_recorded_at"] <= body["last_recorded_at"]


def test_an_unauthenticated_caller_is_refused(engagement_context) -> None:
    assert _read_summary(engagement_context, token="").status_code == 401


def test_a_coordinator_in_a_sibling_department_is_refused(engagement_context) -> None:
    """The cross-unit denial, over HTTP. No `tenant_wide_roles` is passed."""
    token = _register_principal(
        engagement_context["engine"],
        engagement_context["tenant_id"],
        engagement_context["verifier"],
        role="coordinator",
        membership_path=SIBLING_UNIT_PATH,
    )

    assert _read_summary(engagement_context, token=token).status_code == 403


def test_an_admin_in_a_sibling_department_is_refused(engagement_context) -> None:
    """The role is right and the department is not — the metrics §4 exception is not taken."""
    token = _register_principal(
        engagement_context["engine"],
        engagement_context["tenant_id"],
        engagement_context["verifier"],
        role="admin",
        membership_path=SIBLING_UNIT_PATH,
    )

    assert _read_summary(engagement_context, token=token).status_code == 403


def test_an_active_membership_with_the_wrong_role_is_refused(engagement_context) -> None:
    """A student at the owning unit is refused: this is a cohort fact, not their own."""
    token = _register_principal(
        engagement_context["engine"],
        engagement_context["tenant_id"],
        engagement_context["verifier"],
        role="student",
    )

    assert _read_summary(engagement_context, token=token).status_code == 403


def test_a_bare_resource_grant_does_not_convey_the_role(engagement_context) -> None:
    """S-007: a grant conveys reach, not authority."""
    token = _register_principal(
        engagement_context["engine"],
        engagement_context["tenant_id"],
        engagement_context["verifier"],
        role=None,
        resource_grant_unit_id=engagement_context["unit_id"],
    )

    assert _read_summary(engagement_context, token=token).status_code == 403


def test_an_unknown_unit_is_a_404_and_not_a_403(engagement_context) -> None:
    """`load_unit_or_404` runs first, and it is scoped by the caller's own tenant."""
    response = _get(
        engagement_context["client"],
        _summary_path(uuid.uuid4()),
        engagement_context["token"],
    )

    assert response.status_code == 404


def test_a_unit_in_another_tenant_is_a_404_and_not_a_403(engagement_context) -> None:
    """A 403 would confirm the id names something real, which is itself a disclosure."""
    other_tenant_id = uuid.uuid4()
    other_unit_id = uuid.uuid4()
    engine: Engine = engagement_context["engine"]
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
            {"id": other_unit_id, "tid": other_tenant_id, "path": "other.engagement"},
        )

    try:
        response = _get(
            engagement_context["client"],
            _summary_path(other_unit_id),
            engagement_context["token"],
        )

        assert response.status_code == 404
    finally:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM org_unit WHERE tenant_id = :tid"), {"tid": other_tenant_id}
            )
            conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": other_tenant_id})


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_the_summary_offers_no_way_to_write_anything(engagement_context, method: str) -> None:
    """B08's check-in command is blocked on S11 and D8; no verb here pretends otherwise."""
    response = getattr(engagement_context["client"], method)(
        _summary_path(engagement_context["unit_id"]),
        headers={"Authorization": f"Bearer {engagement_context['token']}"},
    )

    assert response.status_code == 405, f"{method.upper()} on the summary is routed"
