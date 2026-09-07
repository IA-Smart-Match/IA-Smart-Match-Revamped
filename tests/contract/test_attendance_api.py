"""HTTP contract for the coordinator's attendance write.

``POST /v1/units/{unit_id}/events/{event_id}/attendance`` is the route OQ-102's
closure authorized: the coordinator is the writer of record for a unit's
attendance evidence, the mechanism is fixed server-side to ``coordinator_entry``,
and the points ADR-0013 derives from that evidence are credited in the same
transaction.

The fixture shape is ``tests/contract/test_engagement_api.py``'s, deliberately —
one tenant, one unit, one sibling department, a coordinator, a student and real
``event`` rows — because the two files describe the two ends of one table and a
second way of building "a coordinator" would let them disagree about what one is.
Every row is synthetic and belongs to a throwaway tenant this module creates and
deletes.

``tests/authz/test_policy_matrix.py`` owns the full authorization rectangle and
needs no database for it. What this file adds is the part that only exists over
HTTP: that a replay is a ``200`` and not a second row, that it does not credit a
second time, that the body cannot choose the mechanism or the instant, that a
speaker subject is accepted as readily as a student one, that an event hosted by
another unit is a ``404``, and that the response carries neither a score nor a
balance.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_domain.rewards import POINTS_PER_VERIFIED_ATTENDANCE
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import Engine, create_engine, text

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)

UNIT_PATH = "iawest.attendance"
#: A second department in the same tenant containing none of :data:`UNIT_PATH`.
#: The route passes no ``tenant_wide_roles``, so ordinary subtree containment
#: applies and a coordinator here must not reach the attendance unit.
SIBLING_UNIT_PATH = "iawest.attsibling"

ON_DATE = date(2026, 9, 1)

#: An instant a caller might try to backdate presence to. Never stored: the
#: route has no field for it and the body forbids extras.
NOT_A_TIMESTAMP = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


def _attendance_path(unit_id: uuid.UUID, event_id: uuid.UUID) -> str:
    return f"/v1/units/{unit_id}/events/{event_id}/attendance"


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
    """One coordinator-entered, date-only event. No crawler, no source URL."""
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


def _insert_user(conn, *, tenant_id: uuid.UUID, label: str) -> uuid.UUID:
    """One ``user_account`` with no membership anywhere."""
    user_id = uuid.uuid4()
    subject = f"sub-{label}-{user_id.hex}"
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
    return user_id


def _register_principal(
    engine: Engine,
    tenant_id: uuid.UUID,
    verifier: FixtureTokenVerifier,
    *,
    role: str | None,
    membership_path: str = UNIT_PATH,
) -> tuple[uuid.UUID, str]:
    """Create one principal in ``tenant_id`` and return its account id and bearer.

    Same shape as ``tests/contract/test_engagement_api.py``'s helper of the same
    name, and it returns the id as well as the token because one of these
    principals is also an attendance *subject*: the student reads back the
    balance the coordinator's write minted for them.
    """
    subject = f"sub-attendance-{uuid.uuid4().hex}"
    token = f"tok-attendance-{uuid.uuid4().hex}"
    user_id = uuid.uuid4()

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
    return user_id, token


@pytest.fixture
def attendance_context(engine: Engine) -> Iterator[dict[str, object]]:
    """One tenant, two departments, two events, a coordinator, a student, a speaker."""
    tenant_id = uuid.uuid4()
    unit_id = uuid.uuid4()
    sibling_unit_id = uuid.uuid4()

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"test-attendance-{tenant_id.hex[:12]}"},
        )
        for new_unit_id, path, name in (
            (unit_id, UNIT_PATH, "Attendance"),
            (sibling_unit_id, SIBLING_UNIT_PATH, "Sibling"),
        ):
            conn.execute(
                text(
                    "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                    "VALUES (:id, :tid, CAST(:path AS ltree), 'department', :name)"
                ),
                {"id": new_unit_id, "tid": tenant_id, "path": path, "name": name},
            )
        event_id = _insert_event(conn, tenant_id=tenant_id, unit_id=unit_id, title="Autumn Kickoff")
        sibling_event_id = _insert_event(
            conn, tenant_id=tenant_id, unit_id=sibling_unit_id, title="Sibling Social"
        )
        # The speaker: a real account in this tenant with no student membership
        # anywhere. The CBA hand-off cites a row whose subject is exactly this,
        # so a route that only accepted students would leave the CBA funnel's
        # Attended stage unreachable through the API.
        speaker_id = _insert_user(conn, tenant_id=tenant_id, label="speaker")

    verifier = FixtureTokenVerifier()
    client = TestClient(app)
    client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    client.app.state.token_verifier = verifier

    _, coordinator_token = _register_principal(engine, tenant_id, verifier, role="coordinator")
    student_id, student_token = _register_principal(engine, tenant_id, verifier, role="student")

    yield {
        "client": client,
        "engine": engine,
        "verifier": verifier,
        "tenant_id": tenant_id,
        "unit_id": unit_id,
        "sibling_unit_id": sibling_unit_id,
        "event_id": event_id,
        "sibling_event_id": sibling_event_id,
        "student_id": student_id,
        "speaker_id": speaker_id,
        "token": coordinator_token,
        "student_token": student_token,
    }

    with engine.begin() as conn:
        for table in (
            "point_ledger_entry",
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


def _record(
    context: dict[str, object],
    *,
    subject_id: uuid.UUID | None = None,
    event_id: uuid.UUID | None = None,
    token: str | None = None,
    body: dict[str, object] | None = None,
):
    """POST one attendance, defaulting every part to the ordinary case."""
    client: TestClient = context["client"]  # type: ignore[assignment]
    payload = (
        body if body is not None else {"subject_id": str(subject_id or context["student_id"])}
    )
    bearer = context["token"] if token is None else token
    headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
    return client.post(
        _attendance_path(
            context["unit_id"],  # type: ignore[arg-type]
            event_id or context["event_id"],  # type: ignore[arg-type]
        ),
        json=payload,
        headers=headers,
    )


def _rows(context: dict[str, object], table: str, **where: object) -> int:
    """Count rows in ``table`` for this tenant, narrowed by ``where``."""
    engine: Engine = context["engine"]  # type: ignore[assignment]
    clauses = " AND ".join(f"{column} = :{column}" for column in where)
    with engine.begin() as conn:
        return int(
            conn.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE tenant_id = :tid AND {clauses}"),
                {"tid": context["tenant_id"], **where},
            ).scalar_one()
        )


def test_a_coordinator_records_a_students_attendance_and_the_row_is_in_the_table(
    attendance_context,
) -> None:
    """A ``201``, and a row PostgreSQL actually holds behind it."""
    response = _record(attendance_context)

    assert response.status_code == 201, response.text
    body = response.json()

    assert body["unit_id"] == str(attendance_context["unit_id"])
    assert body["event_id"] == str(attendance_context["event_id"])
    assert body["subject_id"] == str(attendance_context["student_id"])
    assert uuid.UUID(body["attendance_id"])
    assert body["recorded_at"], "the response reports no instant for a row that has one"

    assert (
        _rows(attendance_context, "attendance_record", id=uuid.UUID(body["attendance_id"])) == 1
    )


def test_the_same_request_twice_is_a_200_and_one_row(attendance_context) -> None:
    """A replay is not a conflict and not a second row.

    ``uq_attendance_record_subject_event`` is the idempotency key and the insert
    is ``ON CONFLICT DO NOTHING`` against it, so the second call has nothing to
    write. It answers ``200`` rather than ``201`` because "they were present" and
    "this request recorded that they were present" are different claims —
    ``routers/speaker_requests.py``'s create draws the same distinction.
    """
    first = _record(attendance_context)
    second = _record(attendance_context)

    assert first.status_code == 201, first.text
    assert second.status_code == 200, second.text
    assert second.json()["attendance_id"] == first.json()["attendance_id"]
    assert (
        _rows(
            attendance_context,
            "attendance_record",
            subject_id=attendance_context["student_id"],
            event_id=attendance_context["event_id"],
        )
        == 1
    )


def test_the_method_is_coordinator_entry_and_the_body_cannot_choose_it(
    attendance_context,
) -> None:
    """The route *is* a coordinator's entry, so the mechanism is not a parameter.

    A caller-chosen ``qr_scan`` would claim a scanner that does not exist and an
    ``import`` would claim a batch that never ran — and the engagement summary
    reports a unit's evidence *by mechanism*, so a false provenance is not a
    cosmetic error. The body forbids extras, so naming the field at all is a
    ``422`` rather than a value silently discarded.
    """
    accepted = _record(attendance_context)
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["method"] == "coordinator_entry"

    refused = _record(
        attendance_context,
        body={"subject_id": str(attendance_context["speaker_id"]), "method": "qr_scan"},
    )
    assert refused.status_code == 422, (
        f"a body naming a method answered {refused.status_code}; a field that is "
        "accepted and ignored is indistinguishable to a client from one that "
        f"worked: {refused.text[:300]}"
    )
    assert (
        _rows(attendance_context, "attendance_record", subject_id=attendance_context["speaker_id"])
        == 0
    ), "the refused request still wrote a row"


def test_the_route_does_not_accept_a_recorded_at(attendance_context) -> None:
    """A coordinator cannot backdate presence.

    ``created_at`` is the server default, and the Attended funnel stage reads
    exactly that column as its own timestamp. A caller-supplied instant would let
    a journey be walked into the past.
    """
    refused = _record(
        attendance_context,
        body={
            "subject_id": str(attendance_context["student_id"]),
            "recorded_at": NOT_A_TIMESTAMP.isoformat(),
        },
    )

    assert refused.status_code == 422, refused.text


def test_attendance_credits_points_once(attendance_context) -> None:
    """One ledger entry after two calls, and the student's own balance is measured.

    ADR-0013: points derive from recorded attendance and nothing else. Crediting
    on record is what keeps the balance out of ``unknown`` — a recorded
    attendance with no entry deriving from it is exactly the state
    ``routers/rewards.py`` refuses to call zero.
    """
    first = _record(attendance_context)
    assert first.status_code == 201, first.text
    assert first.json()["points_credited"] is True
    assert uuid.UUID(first.json()["ledger_entry_id"])

    second = _record(attendance_context)
    assert second.status_code == 200, second.text
    assert second.json()["points_credited"] is False, (
        "the replay reported crediting points it did not credit"
    )
    assert second.json()["ledger_entry_id"] == first.json()["ledger_entry_id"], (
        "a replay must report the entry that already derives from this attendance, "
        "not null — the points exist, and saying nothing about them is not honest"
    )

    assert (
        _rows(
            attendance_context,
            "point_ledger_entry",
            source_attendance_id=uuid.UUID(first.json()["attendance_id"]),
        )
        == 1
    ), "two requests minted two credits from one attendance"

    client: TestClient = attendance_context["client"]  # type: ignore[assignment]
    catalog = client.get(
        f"/v1/units/{attendance_context['unit_id']}/rewards",
        headers={"Authorization": f"Bearer {attendance_context['student_token']}"},
    )
    assert catalog.status_code == 200, catalog.text
    balance = catalog.json()["balance"]
    assert balance["state"] == "measured", (
        f"the student's balance is {balance['state']!r} after a recorded and "
        "credited attendance; the unknown state exists for evidence with no "
        "credit deriving from it, which is no longer this case"
    )
    assert balance["points"] == POINTS_PER_VERIFIED_ATTENDANCE


def test_a_speaker_subject_is_accepted(attendance_context) -> None:
    """The subject of an attendance row is not only a student.

    The CBA hand-off cites a row whose ``subject_id`` is the speaker's own
    account, so a route that accepted only students would leave the CBA funnel's
    Attended stage unreachable through the API.
    """
    response = _record(attendance_context, subject_id=attendance_context["speaker_id"])

    assert response.status_code == 201, response.text
    assert response.json()["subject_id"] == str(attendance_context["speaker_id"])


def test_an_event_hosted_by_another_unit_is_a_404(attendance_context) -> None:
    """The composite foreign key checks the tenant, not the host unit.

    An attendance owned by unit A at an event hosted by unit B is a row nobody's
    drill-down can explain, so the route refuses it in words rather than storing
    it.
    """
    response = _record(attendance_context, event_id=attendance_context["sibling_event_id"])

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "event_not_found"
    assert (
        _rows(
            attendance_context,
            "attendance_record",
            event_id=attendance_context["sibling_event_id"],
        )
        == 0
    )


def test_a_subject_outside_the_tenant_is_a_404(attendance_context) -> None:
    """Refused in words, not as an ``IntegrityError`` a caller reads as a 500."""
    response = _record(attendance_context, subject_id=uuid.uuid4())

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "attendance_subject_not_found"


def test_a_student_may_not_record_attendance(attendance_context) -> None:
    """The cell that matters most: attendance is the only input to points."""
    response = _record(attendance_context, token=attendance_context["student_token"])

    assert response.status_code == 403, response.text
    assert (
        _rows(attendance_context, "attendance_record", subject_id=attendance_context["student_id"])
        == 0
    )


def test_a_sibling_coordinator_may_not_record_attendance(attendance_context) -> None:
    """The cross-unit denial over HTTP. No ``tenant_wide_roles`` is passed."""
    _, token = _register_principal(
        attendance_context["engine"],
        attendance_context["tenant_id"],
        attendance_context["verifier"],
        role="coordinator",
        membership_path=SIBLING_UNIT_PATH,
    )

    response = _record(attendance_context, token=token)

    assert response.status_code == 403, response.text


def test_an_unauthenticated_caller_is_refused(attendance_context) -> None:
    assert _record(attendance_context, token="").status_code == 401


def test_the_response_carries_no_score_and_no_balance(attendance_context) -> None:
    """The balance has one honest home, and this is not it.

    ``GET /v1/units/{unit_id}/rewards`` folds the ledger and knows how to say
    ``unknown``; a second computation of the same number here would be free to
    disagree with it. No score either — nothing on this path ranks anybody.
    """
    response = _record(attendance_context)
    body = response.json()

    assert set(body) == {
        "attendance_id",
        "unit_id",
        "event_id",
        "subject_id",
        "method",
        "recorded_at",
        "points_credited",
        "ledger_entry_id",
    }, f"the response carries {sorted(body)}"

    raw = response.text.lower()
    for forbidden in ("balance", "score", "rank", '"points"'):
        assert forbidden not in raw, f"the attendance response mentions {forbidden!r}: {raw}"
