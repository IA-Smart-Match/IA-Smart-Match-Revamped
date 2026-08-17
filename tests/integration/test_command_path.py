"""End-to-end tests for the command submission path.

Exercises the whole request path against a real database: bearer token →
principal lookup → authorization → rate limit → idempotency → job + outbox, all
in one transaction, then the job status and SSE endpoints.

These are the tests that would catch the legacy's characteristic failures —
caller-selected identity, per-instance counters, work started in the request
path — because each is asserted directly rather than assumed absent.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import text

pytestmark = pytest.mark.integration

UNIT_PATH = "iawest.cpp.engineering.ie"


@pytest.fixture
def unit_id(engine, tenant_id) -> uuid.UUID:
    """An org unit owned by the test tenant."""
    uid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                "VALUES (:id, :tid, CAST(:path AS ltree), 'department', 'IE')"
            ),
            {"id": uid, "tid": tenant_id, "path": UNIT_PATH},
        )
    return uid


def _make_user(engine, tenant_id, *, subject: str, suspended: bool = False) -> uuid.UUID:
    user_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO user_account "
                "(id, tenant_id, external_subject, email, suspended) "
                "VALUES (:id, :tid, :sub, :email, :susp)"
            ),
            {
                "id": user_id,
                "tid": tenant_id,
                "sub": subject,
                "email": f"{subject}@example.edu",
                "susp": suspended,
            },
        )
    return user_id


def _grant(engine, tenant_id, user_id, *, path: str = "iawest", role: str = "coordinator"):
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO membership (id, tenant_id, user_id, granted_path, role) "
                "VALUES (:id, :tid, :uid, CAST(:path AS ltree), :role)"
            ),
            {
                "id": uuid.uuid4(),
                "tid": tenant_id,
                "uid": user_id,
                "path": path,
                "role": role,
            },
        )


@pytest.fixture
def client(engine, monkeypatch) -> TestClient:
    """A client wired to the test database and a fixture token verifier."""
    verifier = FixtureTokenVerifier()

    test_client = TestClient(app)
    # render_as_string(hide_password=False), not str(): SQLAlchemy masks the
    # password as "***" in the default repr, which produces a URL that looks
    # right and cannot authenticate.
    test_client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    test_client.app.state.token_verifier = verifier
    test_client.verifier = verifier  # type: ignore[attr-defined]
    return test_client


@pytest.fixture
def coordinator(engine, tenant_id, client) -> str:
    """A coordinator with a valid token. Returns the bearer token."""
    user_id = _make_user(engine, tenant_id, subject="sub-coordinator")
    _grant(engine, tenant_id, user_id)
    client.verifier.register("tok-coordinator", "sub-coordinator")
    return "tok-coordinator"


def _import_body() -> dict[str, object]:
    return {
        "source_reference": "gs://bucket/import-1.csv",
        "dataset": "professionals",
        "dry_run": True,
    }


def _post_import(client, unit_id, token, *, key: str, body=None):
    return client.post(
        f"/v1/units/{unit_id}/imports",
        json=body or _import_body(),
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
    )


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_command_requires_a_token(client, unit_id):
    response = client.post(f"/v1/units/{unit_id}/imports", json=_import_body())
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_invalid_token_is_rejected(client, unit_id):
    response = _post_import(client, unit_id, "not-a-real-token", key="k1")
    assert response.status_code == 401


def test_valid_token_with_no_local_account_is_rejected(client, unit_id):
    """A person may authenticate with the IdP and still have no account here."""
    client.verifier.register("tok-stranger", "sub-stranger")
    response = _post_import(client, unit_id, "tok-stranger", key="k1")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_authentication_failures_are_indistinguishable(client, unit_id):
    """Absent, invalid, and unknown-account must look identical to a caller.

    Distinguishing them tells an attacker which subjects exist.
    """
    client.verifier.register("tok-stranger", "sub-stranger")

    bodies = [
        client.post(f"/v1/units/{unit_id}/imports", json=_import_body()).json(),
        _post_import(client, unit_id, "garbage", key="k1").json(),
        _post_import(client, unit_id, "tok-stranger", key="k2").json(),
    ]
    assert len({b["error"]["code"] for b in bodies}) == 1
    assert len({b["error"]["message"] for b in bodies}) == 1


def test_suspended_account_is_denied(client, engine, tenant_id, unit_id):
    """Suspension fails local authorization, independent of IdP revocation."""
    user_id = _make_user(engine, tenant_id, subject="sub-suspended", suspended=True)
    _grant(engine, tenant_id, user_id)
    client.verifier.register("tok-suspended", "sub-suspended")

    response = _post_import(client, unit_id, "tok-suspended", key="k1")

    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "principal_suspended"


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def test_membership_without_the_required_role_is_denied(client, engine, tenant_id, unit_id):
    """Importing is restricted to admin and coordinator."""
    user_id = _make_user(engine, tenant_id, subject="sub-student")
    _grant(engine, tenant_id, user_id, role="student")
    client.verifier.register("tok-student", "sub-student")

    assert _post_import(client, unit_id, "tok-student", key="k1").status_code == 403


def test_membership_on_a_sibling_subtree_is_denied(client, engine, tenant_id, unit_id):
    """A grant on one department does not reach another."""
    user_id = _make_user(engine, tenant_id, subject="sub-other-dept")
    _grant(engine, tenant_id, user_id, path="iawest.cpp.engineering.cs")
    client.verifier.register("tok-other", "sub-other-dept")

    assert _post_import(client, unit_id, "tok-other", key="k1").status_code == 403


def test_unknown_unit_is_404_not_403(client, coordinator):
    """A missing unit and another tenant's unit must look the same."""
    response = _post_import(client, uuid.uuid4(), coordinator, key="k1")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unit_not_found"


def test_no_endpoint_accepts_a_tenant_from_the_body(client, unit_id, coordinator):
    """Tenant comes from the token. Sending one must not change anything."""
    body = {**_import_body(), "tenant_id": str(uuid.uuid4())}
    response = _post_import(client, unit_id, coordinator, key="k1", body=body)

    # The extra field is ignored, not honoured — the command still succeeds
    # under the caller's own tenant.
    assert response.status_code == 202


# ---------------------------------------------------------------------------
# Command acceptance
# ---------------------------------------------------------------------------


def test_successful_submission_returns_202_and_a_job(client, unit_id, coordinator):
    """202, not 200: nothing has been imported when this returns."""
    response = _post_import(client, unit_id, coordinator, key="k1")

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["replayed"] is False
    assert body["events_url"] == f"/v1/jobs/{body['job_id']}/events"


def test_submission_creates_job_and_outbox_row_together(client, engine, unit_id, coordinator):
    """v1.1 §1.6: the intent to dispatch commits with the job."""
    job_id = _post_import(client, unit_id, coordinator, key="k1").json()["job_id"]

    with engine.connect() as conn:
        job = conn.execute(
            text("SELECT status, command_type FROM job WHERE id = :id"), {"id": job_id}
        ).one()
        outbox = conn.execute(
            text("SELECT status FROM outbox_record WHERE job_id = :id"), {"id": job_id}
        ).one()

    assert job.status == "queued"
    assert job.command_type == "import.create"
    assert outbox.status == "pending"


def test_no_provider_call_happens_in_the_request_path(client, unit_id, coordinator):
    """The request records intent only.

    Asserted by state rather than by mocking: the job is still ``queued`` and no
    task exists, so nothing downstream can have run.
    """
    response = _post_import(client, unit_id, coordinator, key="k1")
    assert response.status_code == 202

    status_body = client.get(
        f"/v1/jobs/{response.json()['job_id']}",
        headers={"Authorization": f"Bearer {coordinator}"},
    ).json()
    assert status_body["status"] == "queued"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_idempotency_key_is_required(client, unit_id, coordinator):
    response = client.post(
        f"/v1/units/{unit_id}/imports",
        json=_import_body(),
        headers={"Authorization": f"Bearer {coordinator}"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "idempotency_key_required"


def test_replayed_key_with_the_same_body_returns_the_original_job(
    client, engine, unit_id, coordinator
):
    """A retry must not create a second job."""
    first = _post_import(client, unit_id, coordinator, key="same-key")
    second = _post_import(client, unit_id, coordinator, key="same-key")

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["job_id"] == first.json()["job_id"]
    assert second.json()["replayed"] is True

    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM job WHERE command_type = 'import.create'")
        ).scalar_one()
    assert count == 1


def test_replayed_key_with_a_different_body_is_a_conflict(client, unit_id, coordinator):
    """Answering with the earlier result would discard what was actually asked."""
    _post_import(client, unit_id, coordinator, key="same-key")
    second = _post_import(
        client,
        unit_id,
        coordinator,
        key="same-key",
        body={**_import_body(), "dataset": "something-else"},
    )

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "idempotency_key_reused"


def test_different_keys_create_different_jobs(client, unit_id, coordinator):
    first = _post_import(client, unit_id, coordinator, key="k1")
    second = _post_import(client, unit_id, coordinator, key="k2")
    assert first.json()["job_id"] != second.json()["job_id"]


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def test_rate_limit_is_enforced_and_returns_retry_after(client, unit_id, coordinator):
    """v1.1 §3.4: 429 with Retry-After and a stable error code.

    The import limit is 10/min; the eleventh distinct submission is refused.
    """
    for index in range(10):
        assert _post_import(client, unit_id, coordinator, key=f"k{index}").status_code == 202

    refused = _post_import(client, unit_id, coordinator, key="k-over")

    assert refused.status_code == 429
    assert refused.json()["error"]["code"] == "rate_limited"
    assert int(refused.headers["Retry-After"]) >= 1
    assert refused.headers["X-RateLimit-Limit"] == "10"


def test_rate_limit_counter_is_in_the_database_not_the_process(
    client, engine, unit_id, coordinator, tenant_id
):
    """The counter must be shared across instances, not per-process.

    An in-process counter would let each Cloud Run instance permit the full
    quota independently — a 10/min limit becoming 10/min *per instance*.
    """
    _post_import(client, unit_id, coordinator, key="k1")

    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT count, operation FROM rate_limit_counter "
                "WHERE tenant_id = :tid AND operation = 'import.create'"
            ),
            {"tid": tenant_id},
        ).one()

    assert row.count == 1


# ---------------------------------------------------------------------------
# Job status and SSE
# ---------------------------------------------------------------------------


def test_job_status_is_tenant_scoped(client, engine, unit_id, coordinator, tenant_id):
    """Another tenant's job is a 404, not a 403."""
    job_id = _post_import(client, unit_id, coordinator, key="k1").json()["job_id"]

    other_tenant = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :s, :s)"),
            {"id": other_tenant, "s": f"other-{other_tenant.hex[:8]}"},
        )
        other_user = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                "VALUES (:id, :tid, 'sub-outsider', 'o@example.edu')"
            ),
            {"id": other_user, "tid": other_tenant},
        )
    client.verifier.register("tok-outsider", "sub-outsider")

    try:
        response = client.get(
            f"/v1/jobs/{job_id}", headers={"Authorization": "Bearer tok-outsider"}
        )
        assert response.status_code == 404
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM user_account WHERE tenant_id = :t"), {"t": other_tenant})
            conn.execute(text("DELETE FROM tenant WHERE id = :t"), {"t": other_tenant})


def test_job_events_stream_is_sse(client, engine, unit_id, coordinator, tenant_id):
    """The stream renders SSE frames carrying the sequence as the event id."""
    job_id = _post_import(client, unit_id, coordinator, key="k1").json()["job_id"]

    with engine.begin() as conn:
        for sequence in (1, 2, 3):
            conn.execute(
                text(
                    "INSERT INTO job_event (id, tenant_id, job_id, sequence, payload) "
                    "VALUES (:id, :tid, :jid, :seq, CAST(:p AS jsonb))"
                ),
                {
                    "id": uuid.uuid4(),
                    "tid": tenant_id,
                    "jid": job_id,
                    "seq": sequence,
                    "p": f'{{"step": {sequence}}}',
                },
            )

    response = client.get(
        f"/v1/jobs/{job_id}/events",
        headers={"Authorization": f"Bearer {coordinator}"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "id: 1" in response.text
    assert "id: 3" in response.text
    assert "event: job_event" in response.text


def test_last_event_id_resumes_without_replaying(client, engine, unit_id, coordinator, tenant_id):
    """The reconnect property Redis would otherwise be needed for."""
    job_id = _post_import(client, unit_id, coordinator, key="k1").json()["job_id"]

    with engine.begin() as conn:
        for sequence in (1, 2, 3):
            conn.execute(
                text(
                    "INSERT INTO job_event (id, tenant_id, job_id, sequence, payload) "
                    "VALUES (:id, :tid, :jid, :seq, '{}'::jsonb)"
                ),
                {"id": uuid.uuid4(), "tid": tenant_id, "jid": job_id, "seq": sequence},
            )

    response = client.get(
        f"/v1/jobs/{job_id}/events",
        headers={
            "Authorization": f"Bearer {coordinator}",
            "Last-Event-ID": "2",
        },
    )

    assert "id: 1" not in response.text
    assert "id: 2" not in response.text
    assert "id: 3" in response.text


def test_polling_cursor_matches_the_sse_cursor(client, engine, unit_id, coordinator, tenant_id):
    """Polling and streaming read the same rows, so they cannot disagree."""
    job_id = _post_import(client, unit_id, coordinator, key="k1").json()["job_id"]

    with engine.begin() as conn:
        for sequence in (1, 2):
            conn.execute(
                text(
                    "INSERT INTO job_event (id, tenant_id, job_id, sequence, payload) "
                    "VALUES (:id, :tid, :jid, :seq, '{}'::jsonb)"
                ),
                {"id": uuid.uuid4(), "tid": tenant_id, "jid": job_id, "seq": sequence},
            )

    headers = {"Authorization": f"Bearer {coordinator}"}
    via_header = client.get(
        f"/v1/jobs/{job_id}/events", headers={**headers, "Last-Event-ID": "1"}
    ).text
    via_query = client.get(f"/v1/jobs/{job_id}/events?after=1", headers=headers).text

    assert via_header == via_query


def test_negative_cursor_is_rejected(client, unit_id, coordinator):
    job_id = _post_import(client, unit_id, coordinator, key="k1").json()["job_id"]
    response = client.get(
        f"/v1/jobs/{job_id}/events?after=-5",
        headers={"Authorization": f"Bearer {coordinator}"},
    )
    assert response.status_code == 400


def test_job_status_reports_latest_sequence(client, engine, unit_id, coordinator, tenant_id):
    """So a client knows where to resume without fetching the history."""
    job_id = _post_import(client, unit_id, coordinator, key="k1").json()["job_id"]

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO job_event (id, tenant_id, job_id, sequence, payload) "
                "VALUES (:id, :tid, :jid, 7, '{}'::jsonb)"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "jid": job_id},
        )

    body = client.get(
        f"/v1/jobs/{job_id}", headers={"Authorization": f"Bearer {coordinator}"}
    ).json()

    assert body["latest_sequence"] == 7


# ---------------------------------------------------------------------------
# Archived legacy surface
# ---------------------------------------------------------------------------


def test_mock_login_does_not_exist(client):
    assert client.post("/auth/mock-login", json={"role": "admin"}).status_code == 404


def test_expired_membership_denies_access(client, engine, tenant_id, unit_id):
    """An expired membership grants nothing — checked, not assumed."""
    user_id = _make_user(engine, tenant_id, subject="sub-expired")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO membership "
                "(id, tenant_id, user_id, granted_path, role, valid_until) "
                "VALUES (:id, :tid, :uid, CAST('iawest' AS ltree), 'coordinator', :until)"
            ),
            {
                "id": uuid.uuid4(),
                "tid": tenant_id,
                "uid": user_id,
                "until": datetime.now(UTC) - timedelta(days=1),
            },
        )
    client.verifier.register("tok-expired", "sub-expired")

    assert _post_import(client, unit_id, "tok-expired", key="k1").status_code == 403
