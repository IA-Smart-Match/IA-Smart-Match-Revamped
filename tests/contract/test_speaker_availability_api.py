"""HTTP contract for a Connector's view of a roster contact's availability (B26 T3).

``GET``/``PATCH /v1/units/{unit_id}/speaker-contacts/{professional_id}/availability``.

``tests/authz/test_policy_matrix.py`` owns the authorization rectangle;
``tests/integration/test_speaker_availability_repository.py`` owns what reaches
the tables. This file owns what only HTTP shows: status codes, error codes and
their ``details``, "not stated" versus "stated, nothing blocked", full-replace
semantics, the stale check, the UTC "today", and that the quota is charged
before anything else.

Requires a live PostgreSQL migrated to ``0038``; skipped when none is reachable.
The clock the router reads is pinned, so no test flakes across UTC midnight.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_persistence.engine import create_session_factory
from smartmatch_persistence.rate_limit import RateLimit
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import Engine, create_engine, text
from sqlalchemy import event as sa_event

pytestmark = pytest.mark.integration

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)

ROUTER_MODULE = "smartmatch_api.routers.speaker_availability"

UNIT_PATH = "iawest.availability"
SIBLING_UNIT_PATH = "iawest.availabilitysibling"
OTHER_TENANT_UNIT_PATH = "elsewhere.availability"

#: The pinned request clock. Its UTC date is ``TODAY``.
NOW = datetime(2026, 10, 6, 15, 0, tzinfo=UTC)
TODAY = NOW.date()


def _body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "expected_version": None,
        "invitations_paused_until": None,
        "declared_capacity_hours_per_90_days": None,
        "unavailable": [],
    }
    body.update(overrides)
    return body


def _window(starts_on: date, ends_on: date) -> dict[str, str]:
    return {"starts_on": starts_on.isoformat(), "ends_on": ends_on.isoformat()}


class _Context:
    """One tenant, a Connector, a volunteer and a student, two units, and a second tenant."""

    def __init__(
        self,
        client: TestClient,
        engine: Engine,
        tenant_id: uuid.UUID,
        unit_id: uuid.UUID,
        sibling_unit_id: uuid.UUID,
        other_tenant_unit_id: uuid.UUID,
        tokens: dict[str, str],
    ) -> None:
        self.client = client
        self.engine = engine
        self.tenant_id = tenant_id
        self.unit_id = unit_id
        self.sibling_unit_id = sibling_unit_id
        self.other_tenant_unit_id = other_tenant_unit_id
        self.tokens = tokens

    def headers(self, role: str = "coordinator") -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens[role]}"}

    def add_roster_contact(self, *, unit_id: uuid.UUID | None = None) -> str:
        response = self.client.post(
            f"/v1/units/{unit_id or self.unit_id}/speaker-contacts",
            json={
                "full_name": "Rae Okafor",
                "topic_text": "Supply-chain analytics for new graduates.",
                "location_city": "Pomona",
            },
            headers=self.headers(),
        )
        assert response.status_code == 201, response.text
        professional_id: str = response.json()["professional_id"]
        return professional_id

    def url(self, professional_id: str, unit_id: uuid.UUID | None = None) -> str:
        return (
            f"/v1/units/{unit_id or self.unit_id}/speaker-contacts/{professional_id}/availability"
        )

    def get(self, professional_id: str, *, unit_id: uuid.UUID | None = None, role="coordinator"):
        return self.client.get(self.url(professional_id, unit_id), headers=self.headers(role))

    def patch(
        self,
        professional_id: str,
        body: dict[str, Any],
        *,
        unit_id: uuid.UUID | None = None,
        role: str = "coordinator",
    ):
        return self.client.patch(
            self.url(professional_id, unit_id), json=body, headers=self.headers(role)
        )

    def patch_raw(self, professional_id: str, raw: str):
        return self.client.patch(
            self.url(professional_id),
            content=raw,
            headers={**self.headers(), "Content-Type": "application/json"},
        )

    def create(self, professional_id: str, **overrides: Any) -> dict[str, Any]:
        """First write (expected_version null); returns the response body."""
        response = self.patch(professional_id, _body(**overrides))
        assert response.status_code == 200, response.text
        result: dict[str, Any] = response.json()
        return result

    def rows(self, professional_id: str) -> int:
        with self.engine.connect() as conn:
            return int(
                conn.execute(
                    text("SELECT count(*) FROM speaker_availability WHERE professional_id = :p"),
                    {"p": professional_id},
                ).scalar_one()
            )


@pytest.fixture(scope="module")
def engine() -> Engine:
    """A live engine migrated to ``0038``, or skip."""
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT full_name FROM speaker_profile LIMIT 1"))
            conn.execute(text("SELECT 1 FROM speaker_availability LIMIT 1"))
            conn.execute(text("SELECT 1 FROM speaker_availability_window LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no PostgreSQL migrated to 0038 at {DATABASE_URL}: {exc}")
    return eng


def _insert_unit(conn: Any, unit_id: uuid.UUID, tenant_id: uuid.UUID, path: str) -> None:
    conn.execute(
        text(
            "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
            "VALUES (:id, :tid, CAST(:path AS ltree), 'department', :path)"
        ),
        {"id": unit_id, "tid": tenant_id, "path": path},
    )


@pytest.fixture
def ctx(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[_Context]:
    monkeypatch.setattr(f"{ROUTER_MODULE}.utc_now", lambda: NOW)

    tenant_id = uuid.uuid4()
    other_tenant_id = uuid.uuid4()
    unit_id = uuid.uuid4()
    sibling_unit_id = uuid.uuid4()
    other_tenant_unit_id = uuid.uuid4()
    verifier = FixtureTokenVerifier()
    tokens: dict[str, str] = {}

    with engine.begin() as conn:
        for tid in (tenant_id, other_tenant_id):
            conn.execute(
                text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
                {"id": tid, "slug": f"test-availability-{tid.hex[:12]}"},
            )
        _insert_unit(conn, unit_id, tenant_id, UNIT_PATH)
        _insert_unit(conn, sibling_unit_id, tenant_id, SIBLING_UNIT_PATH)
        _insert_unit(conn, other_tenant_unit_id, other_tenant_id, OTHER_TENANT_UNIT_PATH)
        for role in ("coordinator", "volunteer", "student"):
            user_id = uuid.uuid4()
            # Built at runtime: a credential literal in a source file is a
            # credential in a commit patch.
            subject = f"sub-availability-{role}-{uuid.uuid4().hex}"
            tokens[role] = f"tok-availability-{role}-{uuid.uuid4().hex}"
            verifier.register(tokens[role], subject)
            conn.execute(
                text(
                    "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                    "VALUES (:id, :tid, :subject, :email)"
                ),
                {"id": user_id, "tid": tenant_id, "subject": subject, "email": f"{subject}@x.edu"},
            )
            conn.execute(
                text(
                    "INSERT INTO membership (id, tenant_id, user_id, granted_path, role) "
                    "VALUES (:id, :tid, :uid, CAST('iawest' AS ltree), :role)"
                ),
                {"id": uuid.uuid4(), "tid": tenant_id, "uid": user_id, "role": role},
            )

    client = TestClient(app)
    client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    client.app.state.token_verifier = verifier

    yield _Context(
        client, engine, tenant_id, unit_id, sibling_unit_id, other_tenant_unit_id, tokens
    )

    with engine.begin() as conn:
        # Child-first: the availability rows restrict against `user_account`
        # (created_by / updated_by) and cascade from `speaker_profile`.
        for table in (
            # B26 T8d: bookings and their events, before the people and units.
            "pipeline_record",
            "attendance_record",
            "event",
            "speaker_availability_window",
            "speaker_availability",
            "speaker_profile",
            "professional_unit_relationship",
            "membership",
            "resource_grant",
            "user_account",
            "org_unit",
            "rate_limit_counter",
        ):
            for tid in (tenant_id, other_tenant_id):
                conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tid})
        for tid in (tenant_id, other_tenant_id):
            conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tid})


def _error(response: Any) -> dict[str, Any]:
    error: dict[str, Any] = response.json()["error"]
    return error


# ---------------------------------------------------------------------------
# 1-4. Read, first write, provenance, full replace
# ---------------------------------------------------------------------------


def test_get_unstated_is_stated_false_with_null_version(ctx: _Context) -> None:
    pid = ctx.add_roster_contact()
    response = ctx.get(pid)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "professional_id": pid,
        "stated": False,
        "version": None,
        "invitations_paused_until": None,
        "declared_capacity_hours_per_90_days": None,
        "unavailable": [],
        "updated_source": None,
        "updated_at": None,
        # B26 T8d: the current load band, on every response.
        "load": {
            "band": "unknown",
            "reason": "capacity_not_stated",
            "as_of": TODAY.isoformat(),
            "used_in_matching": False,
            "engagements_without_end_time": [],
            "engagements_without_end_time_truncated": False,
        },
    }


def test_first_patch_with_null_expected_version_creates_version_1(ctx: _Context) -> None:
    pid = ctx.add_roster_contact()
    created = ctx.create(pid, declared_capacity_hours_per_90_days=12)
    assert created["stated"] is True
    assert created["version"] == 1
    assert ctx.get(pid).json() == created


def test_patch_sets_connector_source_on_row_and_new_windows(ctx: _Context) -> None:
    pid = ctx.add_roster_contact()
    window = _window(TODAY + timedelta(days=10), TODAY + timedelta(days=12))
    created = ctx.create(pid, unavailable=[window])
    assert created["updated_source"] == "connector"
    assert created["unavailable"] == [{**window, "source": "connector"}]


def test_patch_is_full_replace(ctx: _Context) -> None:
    pid = ctx.add_roster_contact()
    keep = _window(TODAY + timedelta(days=10), TODAY + timedelta(days=12))
    drop = _window(TODAY + timedelta(days=20), TODAY + timedelta(days=21))
    ctx.create(pid, unavailable=[keep, drop])
    # Mark the kept window as the speaker's own, so "keeps its source" is visible.
    with ctx.engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE speaker_availability_window SET created_source = 'speaker' "
                "WHERE professional_id = :p AND starts_on = :s"
            ),
            {"p": pid, "s": keep["starts_on"]},
        )
    added = _window(TODAY + timedelta(days=30), TODAY + timedelta(days=31))
    response = ctx.patch(pid, _body(expected_version=1, unavailable=[added, keep]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"] == 2
    assert body["unavailable"] == [
        {**keep, "source": "speaker"},
        {**added, "source": "connector"},
    ]


def test_empty_windows_stays_stated_true(ctx: _Context) -> None:
    pid = ctx.add_roster_contact()
    ctx.create(pid, unavailable=[_window(TODAY, TODAY)])
    response = ctx.patch(pid, _body(expected_version=1, unavailable=[]))
    assert response.status_code == 200, response.text
    assert response.json()["stated"] is True
    assert response.json()["unavailable"] == []


def test_null_pause_and_capacity_clear(ctx: _Context) -> None:
    pid = ctx.add_roster_contact()
    ctx.create(
        pid,
        invitations_paused_until=(TODAY + timedelta(days=5)).isoformat(),
        declared_capacity_hours_per_90_days=8,
    )
    response = ctx.patch(pid, _body(expected_version=1))
    assert response.status_code == 200, response.text
    assert response.json()["invitations_paused_until"] is None
    assert response.json()["declared_capacity_hours_per_90_days"] is None


# ---------------------------------------------------------------------------
# 5. Stale
# ---------------------------------------------------------------------------


def _assert_stale(response: Any) -> None:
    assert response.status_code == 409, response.text
    error = _error(response)
    assert error["code"] == "speaker_availability_stale"
    assert "details" not in error


def test_stale_version_is_409_and_writes_nothing(ctx: _Context) -> None:
    pid = ctx.add_roster_contact()
    before = ctx.create(pid, declared_capacity_hours_per_90_days=5)
    _assert_stale(ctx.patch(pid, _body(expected_version=7, declared_capacity_hours_per_90_days=9)))
    assert ctx.get(pid).json() == before


def test_null_expected_version_on_existing_row_is_409(ctx: _Context) -> None:
    pid = ctx.add_roster_contact()
    ctx.create(pid)
    _assert_stale(ctx.patch(pid, _body(expected_version=None)))


def test_version_on_missing_row_is_409(ctx: _Context) -> None:
    pid = ctx.add_roster_contact()
    _assert_stale(ctx.patch(pid, _body(expected_version=1)))
    assert ctx.rows(pid) == 0


def test_stale_wins_over_domain_invalid_body(ctx: _Context) -> None:
    pid = ctx.add_roster_contact()
    ctx.create(pid)
    _assert_stale(ctx.patch(pid, _body(expected_version=3, declared_capacity_hours_per_90_days=0)))


def test_domain_invalid_writes_nothing(ctx: _Context) -> None:
    """Plan-gate addition 1: a 422 leaves version 1 and its data untouched."""
    pid = ctx.add_roster_contact()
    before = ctx.create(pid, declared_capacity_hours_per_90_days=5)
    response = ctx.patch(pid, _body(expected_version=1, declared_capacity_hours_per_90_days=0))
    assert response.status_code == 422, response.text
    after = ctx.get(pid).json()
    assert after == before
    assert after["version"] == 1


# ---------------------------------------------------------------------------
# 6. Capacity
# ---------------------------------------------------------------------------


def _assert_invalid(response: Any, code: str, details: dict[str, Any]) -> None:
    assert response.status_code == 422, response.text
    error = _error(response)
    assert error["code"] == f"speaker_availability_{code}"
    assert error["details"] == details


_CAPACITY_DETAILS = {"field": "declared_capacity_hours_per_90_days"}


@pytest.mark.parametrize("value", ["0", "-1", "720.1", "24.05", "NaN", "Infinity"])
def test_capacity_invalid(ctx: _Context, value: str) -> None:
    """Sent as raw JSON so ``NaN`` and ``Infinity`` (plan-gate addition 4) reach the server."""
    pid = ctx.add_roster_contact()
    raw = json.dumps(_body()).replace(
        '"declared_capacity_hours_per_90_days": null',
        f'"declared_capacity_hours_per_90_days": {value}',
    )
    _assert_invalid(ctx.patch_raw(pid, raw), "capacity_invalid", _CAPACITY_DETAILS)
    assert ctx.rows(pid) == 0


@pytest.mark.parametrize("value", [0.1, 720])
def test_capacity_bounds_accepted(ctx: _Context, value: float) -> None:
    pid = ctx.add_roster_contact()
    created = ctx.create(pid, declared_capacity_hours_per_90_days=value)
    assert created["declared_capacity_hours_per_90_days"] == value


def test_capacity_is_a_json_number_in_response(ctx: _Context) -> None:
    pid = ctx.add_roster_contact()
    ctx.create(pid, declared_capacity_hours_per_90_days=24.5)
    raw = ctx.get(pid).text
    assert '"declared_capacity_hours_per_90_days":24.5' in raw.replace(" ", "")


# ---------------------------------------------------------------------------
# 7. Pause and the UTC "today"
# ---------------------------------------------------------------------------

_PAUSE_DETAILS = {"field": "invitations_paused_until"}


def test_pause_yesterday_422(ctx: _Context) -> None:
    pid = ctx.add_roster_contact()
    yesterday = (TODAY - timedelta(days=1)).isoformat()
    response = ctx.patch(pid, _body(invitations_paused_until=yesterday))
    _assert_invalid(response, "pause_invalid", _PAUSE_DETAILS)


def test_pause_today_ok(ctx: _Context) -> None:
    pid = ctx.add_roster_contact()
    created = ctx.create(pid, invitations_paused_until=TODAY.isoformat())
    assert created["invitations_paused_until"] == TODAY.isoformat()


def test_pause_at_12_months_ok_and_day_after_422(ctx: _Context) -> None:
    pid = ctx.add_roster_contact()
    limit = date(TODAY.year + 1, TODAY.month, TODAY.day)
    too_far = (limit + timedelta(days=1)).isoformat()
    _assert_invalid(
        ctx.patch(pid, _body(invitations_paused_until=too_far)), "pause_invalid", _PAUSE_DETAILS
    )
    assert ctx.create(pid, invitations_paused_until=limit.isoformat())["version"] == 1


def test_today_is_the_utc_date(ctx: _Context, monkeypatch: pytest.MonkeyPatch) -> None:
    """03:00Z on 6 Oct is still 5 Oct in Pacific; the server's today is the 6th (C1)."""
    monkeypatch.setattr(f"{ROUTER_MODULE}.utc_now", lambda: datetime(2026, 10, 6, 3, tzinfo=UTC))
    pid = ctx.add_roster_contact()
    _assert_invalid(
        ctx.patch(pid, _body(invitations_paused_until="2026-10-05")),
        "pause_invalid",
        _PAUSE_DETAILS,
    )
    assert ctx.create(pid, invitations_paused_until="2026-10-06")["version"] == 1


# ---------------------------------------------------------------------------
# 8. The expired-pause drop rule
# ---------------------------------------------------------------------------


def _seed_expired_pause(ctx: _Context, pid: str) -> str:
    ctx.create(pid, invitations_paused_until=TODAY.isoformat())
    past = (TODAY - timedelta(days=3)).isoformat()
    with ctx.engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE speaker_availability SET invitations_paused_until = :d "
                "WHERE professional_id = :p"
            ),
            {"d": past, "p": pid},
        )
    return past


def test_expired_pause_resent_unchanged_is_stored_null(ctx: _Context) -> None:
    pid = ctx.add_roster_contact()
    past = _seed_expired_pause(ctx, pid)
    assert ctx.get(pid).json()["invitations_paused_until"] == past
    response = ctx.patch(pid, _body(expected_version=1, invitations_paused_until=past))
    assert response.status_code == 200, response.text
    assert response.json()["invitations_paused_until"] is None
    assert response.json()["version"] == 2


def test_expired_pause_changed_is_422(ctx: _Context) -> None:
    pid = ctx.add_roster_contact()
    past = date.fromisoformat(_seed_expired_pause(ctx, pid))
    other = (past - timedelta(days=1)).isoformat()
    response = ctx.patch(pid, _body(expected_version=1, invitations_paused_until=other))
    _assert_invalid(response, "pause_invalid", _PAUSE_DETAILS)


# ---------------------------------------------------------------------------
# 9. Windows
# ---------------------------------------------------------------------------


def _distinct_windows(count: int) -> list[dict[str, str]]:
    return [_window(TODAY + timedelta(days=i), TODAY + timedelta(days=i)) for i in range(count)]


def test_21_windows_too_many_20_ok(ctx: _Context) -> None:
    pid = ctx.add_roster_contact()
    _assert_invalid(
        ctx.patch(pid, _body(unavailable=_distinct_windows(21))),
        "too_many_windows",
        {"field": "unavailable", "limit": 20},
    )
    assert len(ctx.create(pid, unavailable=_distinct_windows(20))["unavailable"]) == 20


_OK = _window(TODAY + timedelta(days=40), TODAY + timedelta(days=41))


@pytest.mark.parametrize(
    ("windows", "index"),
    [
        pytest.param(
            [_OK, _window(TODAY + timedelta(days=5), TODAY + timedelta(days=1))], 1, id="order"
        ),
        pytest.param([_window(date(2026, 1, 1), date(2027, 1, 3)), _OK], 0, id="span-367"),
        pytest.param([_OK, _window(date(2028, 4, 1), date(2028, 4, 7))], 1, id="horizon"),
        pytest.param([_OK, _OK], 1, id="duplicate"),
    ],
)
def test_window_invalid_reports_request_index(
    ctx: _Context, windows: list[dict[str, str]], index: int
) -> None:
    pid = ctx.add_roster_contact()
    _assert_invalid(
        ctx.patch(pid, _body(unavailable=windows)),
        "window_invalid",
        {"field": "unavailable", "index": index},
    )
    assert ctx.rows(pid) == 0


# ---------------------------------------------------------------------------
# 10. Scope: unknown, sibling-unit and other-tenant ids
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["GET", "PATCH"])
def test_unknown_professional_404(ctx: _Context, method: str) -> None:
    pid = str(uuid.uuid4())
    response = ctx.get(pid) if method == "GET" else ctx.patch(pid, _body())
    assert response.status_code == 404, response.text
    assert _error(response)["code"] == "speaker_contact_not_found"


@pytest.mark.parametrize("method", ["GET", "PATCH"])
def test_sibling_unit_profile_404_and_nothing_written(ctx: _Context, method: str) -> None:
    pid = ctx.add_roster_contact(unit_id=ctx.sibling_unit_id)
    response = ctx.get(pid) if method == "GET" else ctx.patch(pid, _body())
    assert response.status_code == 404, response.text
    assert _error(response)["code"] == "speaker_contact_not_found"
    assert ctx.rows(pid) == 0


@pytest.mark.parametrize("method", ["GET", "PATCH"])
def test_other_tenant_unit_404_unit_not_found(ctx: _Context, method: str) -> None:
    pid = ctx.add_roster_contact()
    unit_id = ctx.other_tenant_unit_id
    response = (
        ctx.get(pid, unit_id=unit_id)
        if method == "GET"
        else ctx.patch(pid, _body(), unit_id=unit_id)
    )
    assert response.status_code == 404, response.text
    assert _error(response)["code"] == "unit_not_found"
    assert ctx.rows(pid) == 0


# ---------------------------------------------------------------------------
# 11. Roles, body shape, bearer, quota
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["volunteer", "student"])
def test_volunteer_and_student_get_403(ctx: _Context, role: str) -> None:
    pid = ctx.add_roster_contact()
    assert ctx.get(pid, role=role).status_code == 403
    response = ctx.patch(pid, _body(), role=role)
    assert response.status_code == 403
    assert _error(response)["code"] == "forbidden"
    assert ctx.rows(pid) == 0


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"expected_version": None}, id="missing-keys"),
        pytest.param(_body(professional_id=str(uuid.uuid4())), id="extra-key"),
        pytest.param(_body(expected_version=True), id="bool-version"),
        pytest.param(_body(declared_capacity_hours_per_90_days="24"), id="string-capacity"),
        pytest.param(_body(invitations_paused_until="not-a-date"), id="bad-date"),
    ],
)
def test_invalid_body_is_invalid_request(ctx: _Context, body: dict[str, Any]) -> None:
    pid = ctx.add_roster_contact()
    response = ctx.patch(pid, body)
    assert response.status_code == 422, response.text
    assert _error(response)["code"] == "invalid_request"
    assert ctx.rows(pid) == 0


def test_no_bearer_is_401(ctx: _Context) -> None:
    """Plan-gate addition 5."""
    pid = str(uuid.uuid4())
    for response in (
        ctx.client.get(ctx.url(pid)),
        ctx.client.patch(ctx.url(pid), json=_body()),
    ):
        assert response.status_code == 401, response.text
        assert _error(response)["code"] == "unauthenticated"


def test_quota_is_charged_before_the_404(ctx: _Context, monkeypatch: pytest.MonkeyPatch) -> None:
    """Plan-gate addition 3 (ADR-0015): a refused 404 still spends the quota.

    The router's write limit is swapped for a one-request limit on its own
    bucket, so the roster create (charged to ``speaker_contact.write``) does
    not spend it.
    """
    pid = ctx.add_roster_contact()
    monkeypatch.setattr(
        f"{ROUTER_MODULE}.SPEAKER_CONTACT_WRITE_RATE_LIMIT",
        RateLimit(
            operation="speaker_contact.availability_probe",
            max_requests=1,
            window=timedelta(minutes=1),
        ),
    )
    missing = ctx.patch(str(uuid.uuid4()), _body())
    assert missing.status_code == 404, missing.text
    refused = ctx.patch(pid, _body())
    assert refused.status_code == 429, refused.text
    assert _error(refused)["code"] == "rate_limited"
    assert ctx.rows(pid) == 0


# ---------------------------------------------------------------------------
# B26 T8d: the current load band on the Connector's availability read
# ---------------------------------------------------------------------------
#
# Computed at request time with T8c's load read and T8b's compute_eli, against
# the Q7 table while 2.0.0 is current (used_in_matching false). A band word's
# inputs only: no number inside `load`. Another unit's engagement counts but
# reaches the Connector with no title, date or record id.

_ZONE = "America/Los_Angeles"
_BOOKED_AT = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
#: Digit-free titles, so "no number" assertions test the load, not the title.
_TITLE = "Corporate treasury guest lecture"


def _event_time(day: date, *, hours: float | None, precision: str) -> Any:
    from smartmatch_domain.events import DateOnlyTime, ExactTime, UnresolvedTime

    if precision == "date_only":
        return DateOnlyTime(on_date=day, time_zone=_ZONE)
    if precision == "unresolved":
        return UnresolvedTime()
    starts = datetime(day.year, day.month, day.day, 12, 0, tzinfo=ZoneInfo(_ZONE))
    ends = None if hours is None else starts + timedelta(hours=hours)
    return ExactTime(starts_at=starts, time_zone=_ZONE, ends_at=ends)


def _book(
    ctx: _Context,
    pid: str,
    *,
    offset_days: int,
    hours: float | None = None,
    precision: str = "exact",
    host: uuid.UUID | None = None,
    extracted: bool = False,
    attended: bool = False,
    title: str | None = None,
) -> uuid.UUID:
    """One confirmed booking of ``pid`` at an event ``offset_days`` from TODAY.

    ``hours=None`` on an exact event states no end: its hours are unknown.
    """
    from smartmatch_persistence.events import (
        ORIGIN_COORDINATOR_ENTRY,
        ORIGIN_EXTRACTION,
        EventProvenance,
        EventRepository,
    )

    host_unit = host or ctx.unit_id
    factory = create_session_factory(ctx.engine.url.render_as_string(hide_password=False))
    with factory() as session:
        event_id = EventRepository().upsert(
            session,
            tenant_id=ctx.tenant_id,
            host_org_unit_id=host_unit,
            title=title or f"{_TITLE} {uuid.uuid4().hex}",
            event_time=_event_time(
                TODAY + timedelta(days=offset_days), hours=hours, precision=precision
            ),
            origin=ORIGIN_EXTRACTION if extracted else ORIGIN_COORDINATOR_ENTRY,
            provenance=(
                EventProvenance(
                    source_url=f"https://calendar.example.invalid/{uuid.uuid4().hex}",
                    fetched_at=_BOOKED_AT,
                    extractor_version="synthetic-json-1",
                )
                if extracted
                else None
            ),
        )
        session.commit()
    record_id = uuid.uuid4()
    attendance_id = uuid.uuid4() if attended else None
    with ctx.engine.begin() as conn:
        if attendance_id is not None:
            conn.execute(
                text(
                    "INSERT INTO attendance_record (id, tenant_id, owning_unit_id, subject_id, "
                    "event_id, method) VALUES (:id, :t, :u, :s, :e, 'qr_scan')"
                ),
                {"id": attendance_id, "t": ctx.tenant_id, "u": host_unit, "s": pid, "e": event_id},
            )
        conn.execute(
            text(
                "INSERT INTO pipeline_record (id, tenant_id, owning_unit_id, subject_id, "
                "opportunity_event_id, matched_provenance, matched_at, contacted_at, "
                "confirmed_at, attended_at, attended_attendance_id) VALUES (:id, :t, :u, :s, "
                ":e, 'synthetic / coordinator-accepted', :m, :c, :k, :a, :aid)"
            ),
            {
                "id": record_id,
                "t": ctx.tenant_id,
                "u": host_unit,
                "s": pid,
                "e": event_id,
                "m": _BOOKED_AT,
                "c": _BOOKED_AT + timedelta(hours=1),
                "k": _BOOKED_AT + timedelta(hours=2),
                "a": _BOOKED_AT + timedelta(hours=3) if attended else None,
                "aid": attendance_id,
            },
        )
    return record_id


def _numbers_in(value: Any) -> list[Any]:
    """Every int or float (bools excluded) anywhere in a JSON value."""
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [value]
    if isinstance(value, dict):
        return [n for child in value.values() for n in _numbers_in(child)]
    if isinstance(value, list):
        return [n for child in value for n in _numbers_in(child)]
    return []


@contextmanager
def _statements() -> Iterator[list[str]]:
    """Every SQL statement any engine executes inside the block."""
    captured: list[str] = []

    def _capture(_conn: Any, _cursor: Any, statement: str, *_args: Any) -> None:
        captured.append(statement)

    sa_event.listen(Engine, "before_cursor_execute", _capture)
    try:
        yield captured
    finally:
        sa_event.remove(Engine, "before_cursor_execute", _capture)


def _load(response: Any) -> dict[str, Any]:
    assert response.status_code == 200, response.text
    load: dict[str, Any] = response.json()["load"]
    return load


# A1
def test_get_carries_load_on_every_response(ctx: _Context) -> None:
    pid = ctx.add_roster_contact()
    unstated = _load(ctx.get(pid))
    created = ctx.create(pid, declared_capacity_hours_per_90_days=10)
    stated = _load(ctx.get(pid))

    assert (unstated["band"], unstated["reason"]) == ("unknown", "capacity_not_stated")
    assert created["load"] == stated
    assert (stated["band"], stated["reason"]) == ("light", "measured")
    assert set(stated) == {
        "band",
        "reason",
        "as_of",
        "used_in_matching",
        "engagements_without_end_time",
        "engagements_without_end_time_truncated",
    }


# A2
def test_capacity_and_exact_engagements_give_the_band_word(ctx: _Context) -> None:
    """Attended 6 h ten days ago against 10.0 h: utilization 0.6, Moderate."""
    pid = ctx.add_roster_contact()
    ctx.create(pid, declared_capacity_hours_per_90_days=10)
    _book(ctx, pid, offset_days=-10, hours=6, attended=True)

    load = _load(ctx.get(pid))

    assert (load["band"], load["reason"]) == ("moderate", "measured")
    assert load["engagements_without_end_time"] == []
    assert load["as_of"] == TODAY.isoformat()


# A3
def test_a_date_only_engagement_is_hours_unknown_and_listed(ctx: _Context) -> None:
    pid = ctx.add_roster_contact()
    ctx.create(pid, declared_capacity_hours_per_90_days=10)
    record = _book(ctx, pid, offset_days=3, precision="date_only", title=_TITLE)

    load = _load(ctx.get(pid))

    assert (load["band"], load["reason"]) == ("unknown", "hours_unknown")
    assert load["engagements_without_end_time"] == [
        {
            "engagement_id": str(record),
            "shown": "event",
            "event_title": _TITLE,
            "local_date": (TODAY + timedelta(days=3)).isoformat(),
            "time_precision": "date_only",
            "editable_here": True,
        }
    ]
    assert load["engagements_without_end_time_truncated"] is False


# A4
def test_an_exact_event_without_end_is_listed_with_precision_exact(ctx: _Context) -> None:
    pid = ctx.add_roster_contact()
    ctx.create(pid, declared_capacity_hours_per_90_days=10)
    record = _book(ctx, pid, offset_days=2, hours=None, title=_TITLE)

    (item,) = _load(ctx.get(pid))["engagements_without_end_time"]

    assert item["engagement_id"] == str(record)
    assert (item["shown"], item["time_precision"]) == ("event", "exact")
    assert item["local_date"] == (TODAY + timedelta(days=2)).isoformat()


# A5
def test_another_units_engagement_counts_but_shows_no_title_and_no_record_id(
    ctx: _Context,
) -> None:
    pid = ctx.add_roster_contact()
    ctx.create(pid, declared_capacity_hours_per_90_days=10)
    away_title = "Audit committee panel"
    away = _book(
        ctx, pid, offset_days=4, precision="date_only", host=ctx.sibling_unit_id, title=away_title
    )
    _book(ctx, pid, offset_days=5, hours=12, host=ctx.sibling_unit_id)

    response = ctx.get(pid)
    load = _load(response)

    # Counted: 12 known hours already exceed 10.0, with one more unknown.
    assert (load["band"], load["reason"]) == ("full", "full_by_known_hours")
    assert load["engagements_without_end_time"] == [
        {
            "engagement_id": None,
            "shown": "other_unit",
            "event_title": None,
            "local_date": None,
            "time_precision": None,
            "editable_here": False,
        }
    ]
    assert str(away) not in response.text
    assert away_title not in response.text


# A6
def test_own_coordinator_entry_event_is_editable_and_extracted_is_not(ctx: _Context) -> None:
    pid = ctx.add_roster_contact()
    ctx.create(pid, declared_capacity_hours_per_90_days=10)
    entered = _book(ctx, pid, offset_days=2, precision="date_only")
    extracted = _book(ctx, pid, offset_days=3, precision="date_only", extracted=True)

    items = _load(ctx.get(pid))["engagements_without_end_time"]

    assert [(i["engagement_id"], i["editable_here"]) for i in items] == [
        (str(entered), True),
        (str(extracted), False),
    ]


# A7
def test_a_cancelled_booking_is_not_counted(ctx: _Context) -> None:
    from smartmatch_persistence.pipeline import PipelineRepository

    pid = ctx.add_roster_contact()
    ctx.create(pid, declared_capacity_hours_per_90_days=10)
    cancelled = _book(ctx, pid, offset_days=3, hours=12)
    assert _load(ctx.get(pid))["band"] == "full"
    with ctx.engine.connect() as conn:
        actor = conn.execute(
            text(
                "SELECT id FROM user_account WHERE tenant_id = :t "
                "AND external_subject LIKE 'sub-availability-coordinator-%'"
            ),
            {"t": ctx.tenant_id},
        ).scalar_one()
    factory = create_session_factory(ctx.engine.url.render_as_string(hide_password=False))
    with factory() as session:
        outcome = PipelineRepository().cancel_booking(
            session, tenant_id=ctx.tenant_id, record_id=cancelled, actor_user_id=actor, at=NOW
        )
        session.commit()
    assert outcome.transitioned

    load = _load(ctx.get(pid))

    assert (load["band"], load["reason"]) == ("light", "measured")


# A8
def test_patch_response_recomputes_the_band_from_the_new_capacity(ctx: _Context) -> None:
    pid = ctx.add_roster_contact()
    _book(ctx, pid, offset_days=3, hours=6)
    assert _load(ctx.get(pid))["reason"] == "capacity_not_stated"

    tight = ctx.create(pid, declared_capacity_hours_per_90_days=10)
    roomy = ctx.patch(pid, _body(expected_version=1, declared_capacity_hours_per_90_days=100))

    assert (tight["load"]["band"], tight["load"]["reason"]) == ("moderate", "measured")
    assert _load(roomy)["band"] == "light"
    assert _load(ctx.get(pid)) == _load(roomy)


# A9
def test_load_costs_one_query_and_two_with_gaps(
    ctx: _Context, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Against T3's own reads: +1 statement for the engagements, +1 more for labels."""
    from smartmatch_api.routers import speaker_availability as router
    from smartmatch_api.routers.speaker_availability_models import SpeakerLoadView

    pid = ctx.add_roster_contact()
    ctx.create(pid, declared_capacity_hours_per_90_days=10)
    _book(ctx, pid, offset_days=3, hours=2)
    real = router.current_speaker_load
    ctx.get(pid)  # warm the quota bucket, so every counted GET takes the same path

    def _fixed(*_args: Any, **_kwargs: Any) -> SpeakerLoadView:
        return SpeakerLoadView(
            band="light",
            reason="measured",
            as_of=TODAY,
            used_in_matching=False,
            engagements_without_end_time=[],
            engagements_without_end_time_truncated=False,
        )

    monkeypatch.setattr(router, "current_speaker_load", _fixed)
    with _statements() as baseline:
        assert ctx.get(pid).status_code == 200
    monkeypatch.setattr(router, "current_speaker_load", real)
    with _statements() as measured:
        assert _load(ctx.get(pid))["engagements_without_end_time"] == []
    _book(ctx, pid, offset_days=4, precision="date_only")
    with _statements() as with_gaps:
        assert len(_load(ctx.get(pid))["engagements_without_end_time"]) == 1

    assert len(measured) - len(baseline) == 1, measured
    assert len(with_gaps) - len(baseline) == 2, with_gaps


# A10
def test_no_number_inside_load(ctx: _Context) -> None:
    pid = ctx.add_roster_contact()
    ctx.create(pid, declared_capacity_hours_per_90_days=10)
    _book(ctx, pid, offset_days=-10, hours=6, attended=True)
    _book(ctx, pid, offset_days=3, precision="date_only")
    _book(ctx, pid, offset_days=4, precision="date_only", host=ctx.sibling_unit_id)

    load = _load(ctx.get(pid))

    assert len(load["engagements_without_end_time"]) == 2
    assert _numbers_in(load) == []


# A11
def test_band_equals_assess_pool_loads_on_the_same_inputs(ctx: _Context) -> None:
    from decimal import Decimal

    from smartmatch_domain.load_bands import Q7_REGISTERED_LOAD_BANDS, assess_pool_loads
    from smartmatch_persistence.engagement_load import EngagementLoadRepository

    pid = ctx.add_roster_contact()
    ctx.create(pid, declared_capacity_hours_per_90_days=20)
    _book(ctx, pid, offset_days=-10, hours=6, attended=True)
    _book(ctx, pid, offset_days=3, hours=8)
    _book(ctx, pid, offset_days=4, hours=3, host=ctx.sibling_unit_id)

    load = _load(ctx.get(pid))

    subject = uuid.UUID(pid)
    factory = create_session_factory(ctx.engine.url.render_as_string(hide_password=False))
    with factory() as session:
        engagements = EngagementLoadRepository().engagements_for(
            session, tenant_id=ctx.tenant_id, professional_ids=[subject], as_of=TODAY
        )
    expected = assess_pool_loads(
        [subject],
        capacities={subject: Decimal("20")},
        engagements=engagements,
        as_of=TODAY,
        bands=Q7_REGISTERED_LOAD_BANDS,
    )[subject].assessment
    assert (load["band"], load["reason"]) == (expected.band.value, expected.reason.value)
    assert load["band"] == "heavy"


# A12
def test_used_in_matching_is_false_while_2_0_0_is_current_and_true_after_a_patched_flip(
    ctx: _Context, monkeypatch: pytest.MonkeyPatch
) -> None:
    from smartmatch_domain import factor_registry
    from smartmatch_domain.factor_registry import CBA_REGISTRY_3

    pid = ctx.add_roster_contact()
    assert _load(ctx.get(pid))["used_in_matching"] is False

    monkeypatch.setattr(factor_registry, "CURRENT_CBA_REGISTRY", CBA_REGISTRY_3)

    assert _load(ctx.get(pid))["used_in_matching"] is True


# A13
def test_a_load_read_failure_on_patch_rolls_back_so_the_retry_is_not_stale(
    ctx: _Context, monkeypatch: pytest.MonkeyPatch
) -> None:
    from smartmatch_api.routers import speaker_availability as router

    pid = ctx.add_roster_contact()
    ctx.create(pid, declared_capacity_hours_per_90_days=10)
    real = router.current_speaker_load
    calls = {"n": 0}

    def _fails_once(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("load read failed")
        return real(*args, **kwargs)

    monkeypatch.setattr(router, "current_speaker_load", _fails_once)
    lenient = TestClient(ctx.client.app, raise_server_exceptions=False)
    body = _body(expected_version=1, declared_capacity_hours_per_90_days=20)

    failed = lenient.patch(ctx.url(pid), json=body, headers=ctx.headers())
    assert failed.status_code == 500, failed.text
    with ctx.engine.connect() as conn:
        stored = conn.execute(
            text(
                "SELECT version, declared_capacity_hours_per_90_days FROM speaker_availability "
                "WHERE professional_id = :p"
            ),
            {"p": pid},
        ).one()
    assert stored.version == 1
    assert float(stored.declared_capacity_hours_per_90_days) == 10.0

    retried = ctx.patch(pid, body)

    assert retried.status_code == 200, retried.text
    assert retried.json()["version"] == 2


# A14
def test_get_measures_as_of_from_its_own_utc_now(
    ctx: _Context, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The GET reads its own clock: 23:30 UTC on 5 Oct measures as of the 5th (UTC)."""
    pid = ctx.add_roster_contact()
    monkeypatch.setattr(
        f"{ROUTER_MODULE}.utc_now", lambda: datetime(2026, 10, 5, 23, 30, tzinfo=UTC)
    )

    assert _load(ctx.get(pid))["as_of"] == "2026-10-05"


# A15
def test_another_units_booking_without_an_event_row_carries_no_record_id(ctx: _Context) -> None:
    """Review H1: event_missing from another unit's record reaches a Connector without its id."""
    pid = ctx.add_roster_contact()
    ctx.create(pid, declared_capacity_hours_per_90_days=10)
    records = {}
    for unit in (ctx.unit_id, ctx.sibling_unit_id):
        record_id = uuid.uuid4()
        with ctx.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO pipeline_record (id, tenant_id, owning_unit_id, subject_id, "
                    "opportunity_event_id, matched_provenance, matched_at, contacted_at, "
                    "confirmed_at) VALUES (:id, :t, :u, :s, :e, "
                    "'synthetic / coordinator-accepted', :m, :c, :k)"
                ),
                {
                    "id": record_id,
                    "t": ctx.tenant_id,
                    "u": unit,
                    "s": pid,
                    # Names no event row (opportunity_event_id has no FK; T8c OQ3).
                    "e": uuid.uuid4(),
                    "m": _BOOKED_AT,
                    "c": _BOOKED_AT + timedelta(hours=1),
                    "k": _BOOKED_AT + timedelta(hours=2),
                },
            )
        records[unit] = record_id

    response = ctx.get(pid)
    items = _load(response)["engagements_without_end_time"]

    assert sorted((item["shown"], item["engagement_id"] is None) for item in items) == [
        ("event_missing", False),
        ("event_missing", True),
    ]
    assert str(records[ctx.unit_id]) in response.text
    assert str(records[ctx.sibling_unit_id]) not in response.text


#: Owner ruling R-A (2026-09-24): no load number reaches the API wire.
_RA_LOAD_NUMBERS = frozenset(
    {"completed_hours", "confirmed_hours", "capacity_hours", "utilization"}
)


def _keys_in(value: Any) -> set[str]:
    """Every key anywhere in a JSON value."""
    if isinstance(value, dict):
        return set(value) | {k for child in value.values() for k in _keys_in(child)}
    if isinstance(value, list):
        return {k for child in value for k in _keys_in(child)}
    return set()


def _assert_no_load_number(load: dict[str, Any]) -> None:
    keys = _keys_in(load)
    assert _RA_LOAD_NUMBERS.isdisjoint(keys), keys
    assert not [k for k in keys if "hours" in k or "utilization" in k], keys


# A16 (owner ruling R-A)
def test_load_on_get_and_patch_carries_no_hours_capacity_or_utilization(ctx: _Context) -> None:
    """Band and reason only, with numbers behind them; a pin on SpeakerLoadView's shape."""
    pid = ctx.add_roster_contact()
    _book(ctx, pid, offset_days=-10, hours=6, attended=True)
    _book(ctx, pid, offset_days=3, precision="date_only")
    created = ctx.create(pid, declared_capacity_hours_per_90_days=10)
    patched = ctx.patch(pid, _body(expected_version=1, declared_capacity_hours_per_90_days=20))
    read = _load(ctx.get(pid))

    assert (read["band"], read["reason"]) == ("unknown", "hours_unknown")
    for load in (created["load"], _load(patched), read):
        _assert_no_load_number(load)
    # The Speaker's own stated input is not a load number: it stays.
    assert patched.json()["declared_capacity_hours_per_90_days"] == 20
