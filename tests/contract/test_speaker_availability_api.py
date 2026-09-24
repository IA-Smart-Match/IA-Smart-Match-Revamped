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
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_persistence.engine import create_session_factory
from smartmatch_persistence.rate_limit import RateLimit
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import Engine, create_engine, text

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
