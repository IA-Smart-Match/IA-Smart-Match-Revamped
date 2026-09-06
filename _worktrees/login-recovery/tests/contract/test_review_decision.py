"""HTTP contract for ``POST /v1/review-items/{review_item_id}/decision``.

The load-bearing scenario is the one the slice exists to close: an import
leaves ``pending_review_items`` unable to do anything but climb, because
nothing in the API ever moved a ``review_item`` out of ``pending``. The
end-to-end shape this file proves is exactly that sentence, reversed —

    POST import  ->  pending_review_items = N
    coordinator accepts/rejects rows
    pending_review_items drops

— by writing real ``review_item`` rows directly (the same way
``test_metrics.py`` does, rather than through the import command itself: this
file is about the decision route, not about ingestion, and
``test_import_review_constraints.py`` and
``tests/integration/test_import_rows.py`` already cover how rows get there)
and reading the drop back through the real, already-shipped
``GET /v1/units/{unit_id}/metrics`` route — the same "prove it against the
owning query, not a second copy of the count" discipline
``ReviewDecisionResponse``'s own docstring states for why this route's
response carries no count of its own (ADR-0011 rule 4).

## Why this file carries no ``pytest.mark.integration``

``test_metrics.py``, ``test_me.py`` and ``test_me_suspended.py`` all mark
themselves ``pytest.mark.integration`` because their fixtures need a real,
migrated PostgreSQL — exactly what this file needs too: ``review_item``,
``import_batch``, ``org_unit`` and ``rate_limit_counter`` are real tables with
real constraints (``ck_review_item_status``,
``ck_review_item_decision_evidence``, ``uq_review_item_batch_row``) this test
exercises through the route rather than around it. This file is the
deliberate exception. ``pytest tests/ -m "not integration"`` is this
codebase's fast, no-database pass, and the guarantee this file proves — a
decision actually transitions the row and the pending count actually drops —
is the end-to-end contract this slice exists to demonstrate, not a claim that
should wait for the slow pass to be checked. The ``engine`` fixture below is
the identical skip-if-unreachable mechanism ``test_metrics.py`` uses, so a
developer machine with no PostgreSQL running still gets a clean "not
integration" run; where PostgreSQL is reachable — as it is in this
environment — omitting the marker is what lets this contract run as part of
the fast pass instead of being deferred to the slow one.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import Engine, create_engine, text

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)
UNIT_PATH = "iawest.review-decision"


@pytest.fixture(scope="module")
def engine() -> Engine:
    """Return a live migrated PostgreSQL engine, or skip this contract."""
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1 FROM review_item LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}")
    return eng


@pytest.fixture
def review_context(
    engine: Engine,
) -> Iterator[tuple[TestClient, uuid.UUID, uuid.UUID, str]]:
    """One tenant, one unit, and three ``pending`` review items in one batch.

    Yields ``(client, tenant_id, unit_id, coordinator_token)``. Three rows is
    what ``pending_review_items`` starts at for every test that uses this
    fixture unmodified — enough to prove a single decision moves the count by
    exactly one rather than by "however many rows happened to exist".
    """
    tenant_id = uuid.uuid4()
    unit_id = uuid.uuid4()
    coordinator_id = uuid.uuid4()
    job_id = uuid.uuid4()
    batch_id = uuid.uuid4()
    coordinator_subject = f"sub-review-{uuid.uuid4().hex}"
    coordinator_token = f"tok-review-{uuid.uuid4().hex}"

    review_item_ids = [uuid.uuid4() for _ in range(3)]

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"test-review-{tenant_id.hex[:12]}"},
        )
        conn.execute(
            text(
                "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                "VALUES (:id, :tid, CAST(:path AS ltree), 'department', 'Review')"
            ),
            {"id": unit_id, "tid": tenant_id, "path": UNIT_PATH},
        )
        conn.execute(
            text(
                "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                "VALUES (:id, :tid, :subject, :email)"
            ),
            {
                "id": coordinator_id,
                "tid": tenant_id,
                "subject": coordinator_subject,
                "email": f"{coordinator_subject}@example.edu",
            },
        )
        conn.execute(
            text(
                "INSERT INTO membership (id, tenant_id, user_id, granted_path, role) "
                "VALUES (:id, :tid, :uid, CAST(:path AS ltree), 'coordinator')"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "uid": coordinator_id, "path": UNIT_PATH},
        )
        conn.execute(
            text(
                "INSERT INTO job "
                "(id, tenant_id, command_type, status, actor_id, owning_unit_id, payload) "
                "VALUES (:id, :tid, 'import.create', 'succeeded', :actor, :unit, '{}'::jsonb)"
            ),
            {"id": job_id, "tid": tenant_id, "actor": coordinator_id, "unit": unit_id},
        )
        conn.execute(
            text(
                "INSERT INTO import_batch "
                "(id, tenant_id, owning_unit_id, job_id, dataset, row_count, dry_run) "
                "VALUES (:id, :tid, :unit, :job, 'professionals', 3, false)"
            ),
            {"id": batch_id, "tid": tenant_id, "unit": unit_id, "job": job_id},
        )
        for row_index, item_id in enumerate(review_item_ids):
            conn.execute(
                text(
                    "INSERT INTO review_item "
                    "(id, tenant_id, import_batch_id, row_index, row_data, status) "
                    "VALUES (:id, :tid, :batch, :idx, CAST(:data AS jsonb), 'pending')"
                ),
                {
                    "id": item_id,
                    "tid": tenant_id,
                    "batch": batch_id,
                    "idx": row_index,
                    "data": f'{{"full_name": "Person {row_index}"}}',
                },
            )

    verifier = FixtureTokenVerifier()
    verifier.register(coordinator_token, coordinator_subject)
    client = TestClient(app)
    client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    client.app.state.token_verifier = verifier

    yield client, tenant_id, unit_id, coordinator_token

    with engine.begin() as conn:
        for table in (
            "review_item",
            "import_batch",
            "job_event",
            "outbox_record",
            "redrive_record",
            "job",
            "membership",
            "resource_grant",
            "user_account",
            "org_unit",
            "tenant_budget",
            "concurrency_lease",
            "idempotency_record",
            "rate_limit_counter",
        ):
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tenant_id})


def _decide(client: TestClient, review_item_id: uuid.UUID, decision: str, token: str):
    return client.post(
        f"/v1/review-items/{review_item_id}/decision",
        json={"decision": decision},
        headers={"Authorization": f"Bearer {token}"},
    )


def _pending_count(client: TestClient, unit_id: uuid.UUID, token: str) -> int:
    response = client.get(
        f"/v1/units/{unit_id}/metrics", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200, response.text
    by_name = {item["name"]: item for item in response.json()["metrics"]}
    return int(by_name["pending_review_items"]["value"])


def _one_pending_item_id(client: TestClient, unit_id: uuid.UUID, token: str) -> uuid.UUID:
    """Read one still-``pending`` item's id off the metric's own drill-down.

    Deliberately not tracked by the fixture itself: reading it back through
    ``GET /v1/units/{unit_id}/metrics/pending_review_items/drill-down`` is
    itself part of the guarantee this slice exists to prove — the same rows
    a coordinator would actually see queued for a decision, rather than an id
    this test happened to insert.
    """
    response = client.get(
        f"/v1/units/{unit_id}/metrics/pending_review_items/drill-down",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    rows = response.json()["rows"]
    assert rows, "no pending review item to decide"
    return uuid.UUID(rows[0]["id"])


def _register_principal(
    engine: Engine,
    client: TestClient,
    tenant_id: uuid.UUID,
    *,
    role: str | None,
    resource_grant_unit_id: uuid.UUID | None = None,
    membership_path: str = UNIT_PATH,
) -> str:
    """Create one more user in ``tenant_id`` and return a bearer token for it.

    Mirrors ``test_metrics.py::_register_principal``: ``role=None`` with a
    grant is the bare-``resource_grant``-only shape S-007 says must be
    refused for a role-gated operation (``tests/authz/test_policy_matrix.py``,
    ``review.decide``'s ``resource_grant_only`` cell).
    """
    user_id = uuid.uuid4()
    subject = f"sub-review-{uuid.uuid4().hex}"
    token = f"tok-review-{uuid.uuid4().hex}"

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

    verifier = client.app.state.token_verifier
    verifier.register(token, subject)
    return token


# ---------------------------------------------------------------------------
# The end-to-end shape: import -> pending, decide -> pending drops
# ---------------------------------------------------------------------------


def test_accepting_a_pending_item_drops_the_pending_metric(review_context) -> None:
    client, _tenant_id, unit_id, token = review_context
    item_id = _one_pending_item_id(client, unit_id, token)

    before = _pending_count(client, unit_id, token)
    assert before == 3

    before_call = datetime.now(UTC)
    response = _decide(client, item_id, "accepted", token)
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["id"] == str(item_id)
    assert body["status"] == "accepted"
    decided_at = datetime.fromisoformat(body["decided_at"].replace("Z", "+00:00"))
    assert decided_at >= before_call

    assert _pending_count(client, unit_id, token) == before - 1


def test_rejecting_a_pending_item_drops_the_pending_metric(review_context) -> None:
    client, _tenant_id, unit_id, token = review_context
    item_id = _one_pending_item_id(client, unit_id, token)
    before = _pending_count(client, unit_id, token)

    response = _decide(client, item_id, "rejected", token)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "rejected"

    assert _pending_count(client, unit_id, token) == before - 1


# ---------------------------------------------------------------------------
# A second decision on the same item
# ---------------------------------------------------------------------------


def test_a_second_decision_on_the_same_item_is_409(review_context) -> None:
    client, _tenant_id, unit_id, token = review_context
    item_id = _one_pending_item_id(client, unit_id, token)

    first = _decide(client, item_id, "accepted", token)
    assert first.status_code == 200, first.text

    second = _decide(client, item_id, "rejected", token)
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "review_item_already_decided"

    # The first decision stands; the refused second attempt did not overwrite
    # it — proven against the metric, not just against the response body.
    assert _pending_count(client, unit_id, token) == 3 - 1


# ---------------------------------------------------------------------------
# 404 and 403
# ---------------------------------------------------------------------------


def test_an_unknown_review_item_id_is_404(review_context) -> None:
    client, _tenant_id, _unit_id, token = review_context
    response = _decide(client, uuid.uuid4(), "accepted", token)
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "review_item_not_found"


def test_a_student_role_is_refused(engine: Engine, review_context) -> None:
    """S-007's role-gated shape: an active membership carrying the wrong role."""
    client, tenant_id, unit_id, coordinator_token = review_context
    student_token = _register_principal(engine, client, tenant_id, role="student")
    item_id = _one_pending_item_id(client, unit_id, coordinator_token)

    response = _decide(client, item_id, "accepted", student_token)
    assert response.status_code == 403, response.text
    body = response.json()
    assert body["error"]["code"] == "forbidden"
    assert body["error"]["details"]["reason"] == "no_grant"

    # Refused, not merely answered: the row is still there to decide.
    assert _pending_count(client, unit_id, coordinator_token) == 3


def test_a_bare_resource_grant_with_no_membership_is_refused(
    engine: Engine, review_context
) -> None:
    """S-007: a resource grant conveys reach, not authority — pinned end to end."""
    client, tenant_id, unit_id, coordinator_token = review_context
    grant_only_token = _register_principal(
        engine, client, tenant_id, role=None, resource_grant_unit_id=unit_id
    )
    item_id = _one_pending_item_id(client, unit_id, coordinator_token)

    response = _decide(client, item_id, "accepted", grant_only_token)
    assert response.status_code == 403, response.text
    body = response.json()
    assert body["error"]["code"] == "forbidden"
    assert body["error"]["details"]["reason"] == "resource_grant_lacks_required_role"


# ---------------------------------------------------------------------------
# An invalid decision value
# ---------------------------------------------------------------------------


def test_an_invalid_decision_value_is_422(review_context) -> None:
    client, _tenant_id, unit_id, token = review_context
    item_id = _one_pending_item_id(client, unit_id, token)

    response = client.post(
        f"/v1/review-items/{item_id}/decision",
        json={"decision": "approved"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "invalid_request"

    # Nothing was decided: the pending count is untouched by a request that
    # never reached the handler's own body.
    assert _pending_count(client, unit_id, token) == 3
