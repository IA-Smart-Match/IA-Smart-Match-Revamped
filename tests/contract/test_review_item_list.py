"""HTTP contract for ``GET /v1/units/{unit_id}/review-items``.

The defect this route closes is a screen that contradicted its own number.
``GET /v1/units/{unit_id}/metrics`` has published ``pending_review_items`` for a
unit since before any review route existed, and the coordinator dashboard
rendered it as a badge — while no route in the API listed the items behind it.
A coordinator was shown "seven pending" and given nowhere to see the seven.

So the load-bearing assertion in this file is not that the route returns rows.
It is :func:`test_the_list_length_equals_the_pending_review_items_metric`: on
one fixture, in one process, the length of this list and the value of that
metric are the same number. ``review_item`` carries **no owning unit column** —
a row's unit is derived by joining ``import_batch.owning_unit_id`` — so a list
and a count that derived ownership differently would put a row in one unit's
queue and another unit's badge, which is the same defect in a subtler form.
``ReviewRepository.list_for_unit`` therefore reuses the join
``routers/metrics.py::_pending_review_item_rows_v1`` already makes, and this
test is what holds the two together as the code changes. ADR-0011 rule 4: a
number with an owning query is read from that query, never recomputed beside it.

The rest of the file is the deny-by-default perimeter, asserted over HTTP rather
than inferred from the policy matrix. ``tests/authz/test_policy_matrix.py``
proves ``_authorize_review_item_list`` decides each principal shape correctly;
what it cannot prove is that the route *calls* it before reading a row, that a
sibling department's coordinator is refused rather than served, and that a unit
in another tenant is a 404 rather than a 403 that would confirm the id names
something real. Those are route facts, so they are asserted through the route.

## Why this file carries no ``pytest.mark.integration``

For the reason ``test_review_decision.py`` states at length for itself, and this
file is the same case: ``review_item``, ``import_batch``, ``org_unit`` and
``rate_limit_counter`` are real tables with real constraints
(``ck_review_item_status``, ``ck_review_item_decision_evidence``,
``uq_review_item_batch_row``) that this test exercises through the route rather
than around it, and the guarantee it proves — that the queue and the badge agree
— is the contract this work exists to demonstrate rather than a claim that
should wait for the slow pass. The ``engine`` fixture is the identical
skip-if-unreachable mechanism, so a developer machine with no PostgreSQL running
still gets a clean ``-m "not integration"`` run.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_api.routers.review import MAX_ROWS
from smartmatch_persistence.engine import create_session_factory
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import Connection, Engine, create_engine, text

DATABASE_URL = os.getenv(
    "SMARTMATCH_DATABASE_URL",
    "postgresql+psycopg://smartmatch:smartmatch@localhost:5432/smartmatch",
)

#: The unit whose queue is read. Its sibling below shares a parent and nothing
#: else — the pair is what makes "unit scoping is a path question, not a role
#: question" assertable rather than merely stated.
UNIT_PATH = "iawest.review_list"
SIBLING_PATH = "iawest.review_list_sibling"

#: Three pending rows, one accepted, one rejected. Three is enough to prove the
#: filter selects rather than happens to match: a filter bug that returned
#: everything would show five, and one that returned nothing would show zero.
PENDING_ROWS = 3


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


def _insert_tenant(conn: Connection, tenant_id: uuid.UUID) -> None:
    conn.execute(
        text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
        {"id": tenant_id, "slug": f"test-rlist-{tenant_id.hex[:12]}"},
    )


def _insert_unit(conn: Connection, tenant_id: uuid.UUID, unit_id: uuid.UUID, path: str) -> None:
    conn.execute(
        text(
            "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
            "VALUES (:id, :tid, CAST(:path AS ltree), 'department', 'Review List')"
        ),
        {"id": unit_id, "tid": tenant_id, "path": path},
    )


def _insert_batch(
    conn: Connection,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    job_id: uuid.UUID,
    batch_id: uuid.UUID,
    actor_id: uuid.UUID,
    row_count: int,
) -> None:
    """A job and the import batch it produced, both owned by ``unit_id``.

    The batch is what makes these review items *this unit's* — the rows
    themselves name no unit at all, which is the whole reason the route and the
    metric must derive ownership the same way.
    """
    conn.execute(
        text(
            "INSERT INTO job "
            "(id, tenant_id, command_type, status, actor_id, owning_unit_id, payload) "
            "VALUES (:id, :tid, 'import.create', 'succeeded', :actor, :unit, '{}'::jsonb)"
        ),
        {"id": job_id, "tid": tenant_id, "actor": actor_id, "unit": unit_id},
    )
    conn.execute(
        text(
            "INSERT INTO import_batch "
            "(id, tenant_id, owning_unit_id, job_id, dataset, row_count, dry_run) "
            "VALUES (:id, :tid, :unit, :job, 'professionals', :n, false)"
        ),
        {"id": batch_id, "tid": tenant_id, "unit": unit_id, "job": job_id, "n": row_count},
    )


def _insert_item(
    conn: Connection,
    *,
    tenant_id: uuid.UUID,
    batch_id: uuid.UUID,
    row_index: int,
    status: str,
    decided_by: uuid.UUID | None = None,
) -> uuid.UUID:
    """One ``review_item``, decided or not.

    ``ck_review_item_decision_evidence`` is biconditional: a non-``pending`` row
    must carry both ``decided_at`` and ``decided_by``, and a ``pending`` row
    must carry neither. Writing the evidence here rather than letting it default
    is what keeps this fixture honest against the real constraint.
    """
    item_id = uuid.uuid4()
    is_decided = status != "pending"
    conn.execute(
        text(
            "INSERT INTO review_item "
            "(id, tenant_id, import_batch_id, row_index, row_data, status, "
            " decided_at, decided_by) "
            "VALUES (:id, :tid, :batch, :idx, CAST(:data AS jsonb), :status, "
            " :decided_at, :decided_by)"
        ),
        {
            "id": item_id,
            "tid": tenant_id,
            "batch": batch_id,
            "idx": row_index,
            "data": f'{{"full_name": "Person {row_index}"}}',
            "status": status,
            "decided_at": datetime(2026, 9, 1, 12, 0, tzinfo=UTC) if is_decided else None,
            "decided_by": decided_by if is_decided else None,
        },
    )
    return item_id


def _cleanup(conn: Connection, tenant_id: uuid.UUID) -> None:
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


@pytest.fixture
def queue(engine: Engine) -> Iterator[dict[str, Any]]:
    """One unit with a mixed-status queue, plus a sibling and a second tenant.

    Yields the client and every id a test in this file needs. The sibling unit
    and the foreign tenant are built here rather than per-test because they are
    part of the *perimeter* being asserted, not incidental setup: a fixture that
    only ever built the happy path would make the two refusal tests describe a
    world that does not exist.
    """
    tenant_id = uuid.uuid4()
    unit_id = uuid.uuid4()
    sibling_unit_id = uuid.uuid4()
    coordinator_id = uuid.uuid4()
    job_id = uuid.uuid4()
    batch_id = uuid.uuid4()

    other_tenant_id = uuid.uuid4()
    other_unit_id = uuid.uuid4()

    coordinator_subject = f"sub-rlist-{uuid.uuid4().hex}"
    coordinator_token = f"tok-rlist-{uuid.uuid4().hex}"

    with engine.begin() as conn:
        _insert_tenant(conn, tenant_id)
        _insert_unit(conn, tenant_id, unit_id, UNIT_PATH)
        _insert_unit(conn, tenant_id, sibling_unit_id, SIBLING_PATH)
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
        _insert_batch(
            conn,
            tenant_id=tenant_id,
            unit_id=unit_id,
            job_id=job_id,
            batch_id=batch_id,
            actor_id=coordinator_id,
            row_count=PENDING_ROWS + 2,
        )
        for row_index in range(PENDING_ROWS):
            _insert_item(
                conn,
                tenant_id=tenant_id,
                batch_id=batch_id,
                row_index=row_index,
                status="pending",
            )
        _insert_item(
            conn,
            tenant_id=tenant_id,
            batch_id=batch_id,
            row_index=PENDING_ROWS,
            status="accepted",
            decided_by=coordinator_id,
        )
        _insert_item(
            conn,
            tenant_id=tenant_id,
            batch_id=batch_id,
            row_index=PENDING_ROWS + 1,
            status="rejected",
            decided_by=coordinator_id,
        )

        # A second tenant with its own unit. Nothing links it to the first; it
        # exists so "another tenant's unit id" is a real id rather than a random
        # UUID that would 404 for the uninteresting reason of not existing.
        _insert_tenant(conn, other_tenant_id)
        _insert_unit(conn, other_tenant_id, other_unit_id, "iaeast.review_list")

    verifier = FixtureTokenVerifier()
    verifier.register(coordinator_token, coordinator_subject)
    client = TestClient(app)
    client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    client.app.state.token_verifier = verifier

    yield {
        "client": client,
        "tenant_id": tenant_id,
        "unit_id": unit_id,
        "sibling_unit_id": sibling_unit_id,
        "batch_id": batch_id,
        "coordinator_id": coordinator_id,
        "token": coordinator_token,
        "other_unit_id": other_unit_id,
    }

    with engine.begin() as conn:
        _cleanup(conn, tenant_id)
        _cleanup(conn, other_tenant_id)


def _list(
    client: TestClient,
    unit_id: uuid.UUID,
    token: str,
    status: str | None = None,
):
    params = {} if status is None else {"status": status}
    return client.get(
        f"/v1/units/{unit_id}/review-items",
        params=params,
        headers={"Authorization": f"Bearer {token}"},
    )


def _pending_metric(client: TestClient, unit_id: uuid.UUID, token: str) -> int:
    """``pending_review_items`` as the owning query publishes it.

    Read through the real metrics route, not recomputed here, for the same
    reason the route under test carries no count of its own: a second
    calculation would agree with the first only until one of them changed.
    """
    response = client.get(
        f"/v1/units/{unit_id}/metrics", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200, response.text
    by_name = {item["name"]: item for item in response.json()["metrics"]}
    return int(by_name["pending_review_items"]["value"])


def _register_principal(
    engine: Engine,
    client: TestClient,
    tenant_id: uuid.UUID,
    *,
    role: str,
    membership_path: str,
) -> str:
    """Create one more user in ``tenant_id`` and return a bearer token for it."""
    user_id = uuid.uuid4()
    subject = f"sub-rlist-{uuid.uuid4().hex}"
    token = f"tok-rlist-{uuid.uuid4().hex}"

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

    client.app.state.token_verifier.register(token, subject)
    return token


# ---------------------------------------------------------------------------
# The guarantee this route exists to provide
# ---------------------------------------------------------------------------


def test_the_list_length_equals_the_pending_review_items_metric(
    queue: dict[str, Any],
) -> None:
    """The queue and the badge are the same number, on the same fixture.

    **This is the test that matters.** The dashboard counted pending review
    items and no route listed them, so the screen contradicted itself; the fix
    is not "a route exists" but "the route and the count cannot disagree".

    Both sides derive a row's owning unit by joining
    ``import_batch.owning_unit_id`` — ``review_item`` has no such column of its
    own — and this asserts the two derivations agree rather than trusting that
    they were written the same way. A future change to either join that did not
    touch the other fails here, which is the point: the equality is the
    contract, not an incidental property of today's fixture.
    """
    client = queue["client"]
    unit_id = queue["unit_id"]
    token = queue["token"]

    response = _list(client, unit_id, token, status="pending")
    assert response.status_code == 200, response.text
    body = response.json()

    assert len(body["items"]) == _pending_metric(client, unit_id, token)
    assert len(body["items"]) == PENDING_ROWS


def test_the_list_and_the_metric_move_together_after_a_decision(
    queue: dict[str, Any],
) -> None:
    """Deciding one item shortens the list and the count by exactly one.

    The equality above could hold on a fixture and still be a coincidence of
    two queries that happen to match once. This drives the pair through a real
    state change — the decision route, the one that already existed — and
    requires them to stay equal on the other side of it.
    """
    client = queue["client"]
    unit_id = queue["unit_id"]
    token = queue["token"]

    before = _list(client, unit_id, token, status="pending").json()["items"]
    assert len(before) == _pending_metric(client, unit_id, token)

    decided = client.post(
        f"/v1/review-items/{before[0]['id']}/decision",
        json={"decision": "accepted"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert decided.status_code == 200, decided.text

    after = _list(client, unit_id, token, status="pending").json()["items"]
    assert len(after) == len(before) - 1
    assert len(after) == _pending_metric(client, unit_id, token)


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


def test_status_selects_rather_than_happening_to_match(queue: dict[str, Any]) -> None:
    """Each status returns its own rows, and never the whole table.

    Five rows exist under this unit at three different statuses. A filter that
    was ignored would answer five to every question; one that matched nothing
    would answer zero. Asserting all three arms together is what distinguishes a
    working predicate from either failure.
    """
    client = queue["client"]
    unit_id = queue["unit_id"]
    token = queue["token"]

    pending = _list(client, unit_id, token, status="pending").json()
    accepted = _list(client, unit_id, token, status="accepted").json()
    rejected = _list(client, unit_id, token, status="rejected").json()

    assert len(pending["items"]) == PENDING_ROWS
    assert len(accepted["items"]) == 1
    assert len(rejected["items"]) == 1

    assert {item["status"] for item in pending["items"]} == {"pending"}
    assert {item["status"] for item in accepted["items"]} == {"accepted"}
    assert {item["status"] for item in rejected["items"]} == {"rejected"}

    assert pending["status"] == "pending"
    assert accepted["status"] == "accepted"


def test_the_default_status_is_the_queue_a_coordinator_works(
    queue: dict[str, Any],
) -> None:
    """Omitting ``status`` lists pending items, not everything.

    Deny-by-default applied to a filter: the absent parameter resolves to the
    narrowest useful answer rather than to "all rows", so a caller who forgets
    it cannot accidentally read decided rows they did not ask for.
    """
    client = queue["client"]
    unit_id = queue["unit_id"]
    token = queue["token"]

    body = _list(client, unit_id, token).json()
    assert body["status"] == "pending"
    assert len(body["items"]) == PENDING_ROWS


def test_an_unknown_status_is_refused_rather_than_widened(
    queue: dict[str, Any],
) -> None:
    """A status outside the column's vocabulary is a 422, never a wildcard.

    The failure mode being excluded is an unrecognised value falling through to
    an unfiltered query. ``ReviewItemStatusFilter`` is a ``Literal``, so Pydantic
    refuses it before the handler body runs and there is no "everything" arm to
    reach at all.
    """
    client = queue["client"]
    response = _list(client, queue["unit_id"], queue["token"], status="all")
    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# Disclosure
# ---------------------------------------------------------------------------


def test_an_item_carries_its_row_and_never_its_decider(queue: dict[str, Any]) -> None:
    """``row_data`` is disclosed; ``decided_by`` is not.

    A coordinator cannot decide a row they cannot read, so ``row_data`` is the
    point of the queue. ``decided_by`` holds a ``user_account`` id and no
    surface in this API discloses one — a list would be the widest possible
    place to become the first, returning many rows at once to anyone holding the
    unit's role. The omission is a decision, so it is pinned here rather than
    left to whoever next edits the response model.
    """
    client = queue["client"]
    unit_id = queue["unit_id"]
    token = queue["token"]

    accepted = _list(client, unit_id, token, status="accepted").json()["items"][0]
    assert "decided_by" not in accepted
    assert accepted["decided_at"] is not None
    assert accepted["row_data"]["full_name"].startswith("Person ")
    assert accepted["import_batch_id"] == str(queue["batch_id"])

    pending = _list(client, unit_id, token, status="pending").json()["items"][0]
    assert "decided_by" not in pending
    # Null means undecided, never "unknown": the column is null for exactly the
    # pending rows (`ck_review_item_decision_evidence`).
    assert pending["decided_at"] is None


# ---------------------------------------------------------------------------
# Truncation
# ---------------------------------------------------------------------------


def test_truncation_is_reported_rather_than_hidden(engine: Engine, queue: dict[str, Any]) -> None:
    """A full page says so; ``truncated`` is measured, not guessed.

    ``MAX_ROWS + 1`` rows are read so the flag is answered by the same query
    that produced the page, rather than by a second count whose filters could
    drift from it. ADR-0011 rule 1 is the rule underneath: an unknown must not
    degrade into a comfortable default — a full page that reported
    ``truncated: false`` would be exactly that, a complete-looking answer to a
    question nobody actually asked the database.
    """
    client = queue["client"]
    unit_id = queue["unit_id"]
    token = queue["token"]

    # A second batch under the same unit, carrying enough rows to overflow the
    # cap on its own. Inserted in one statement rather than a Python loop: two
    # hundred round trips to prove a boundary is a slow way to say very little.
    with engine.begin() as conn:
        overflow_batch_id = uuid.uuid4()
        _insert_batch(
            conn,
            tenant_id=queue["tenant_id"],
            unit_id=unit_id,
            job_id=uuid.uuid4(),
            batch_id=overflow_batch_id,
            actor_id=queue["coordinator_id"],
            row_count=MAX_ROWS + 1,
        )
        conn.execute(
            text(
                "INSERT INTO review_item "
                "(id, tenant_id, import_batch_id, row_index, row_data, status) "
                "SELECT gen_random_uuid(), :tid, :batch, i, "
                "       jsonb_build_object('full_name', 'Bulk ' || i), 'pending' "
                "FROM generate_series(0, :last) AS i"
            ),
            {"tid": queue["tenant_id"], "batch": overflow_batch_id, "last": MAX_ROWS},
        )

    body = _list(client, unit_id, token, status="pending").json()

    assert len(body["items"]) == MAX_ROWS
    assert body["truncated"] is True

    # And the un-truncated case is not merely the absence of the above: a page
    # under the cap must report `false`, or the flag would be uninformative.
    accepted = _list(client, unit_id, token, status="accepted").json()
    assert accepted["truncated"] is False


# ---------------------------------------------------------------------------
# The perimeter
# ---------------------------------------------------------------------------


def test_a_sibling_departments_coordinator_is_refused(
    engine: Engine, queue: dict[str, Any]
) -> None:
    """Unit scoping is a path question, not a role question.

    This principal holds exactly the role the route requires, in the same
    tenant, and is still refused — because their membership covers a different
    department. A 403 rather than an empty list: the caller is being told they
    may not ask, not that there is nothing to see, and the two are different
    facts that must not be rendered the same way.
    """
    client = queue["client"]
    token = _register_principal(
        engine,
        client,
        queue["tenant_id"],
        role="coordinator",
        membership_path=SIBLING_PATH,
    )

    response = _list(client, queue["unit_id"], token, status="pending")
    assert response.status_code == 403, response.text


def test_a_student_at_the_owning_unit_is_refused(engine: Engine, queue: dict[str, Any]) -> None:
    """The membership is active at the right unit; the role is the refusal.

    The queue is every quarantined submission's ``row_data`` — the same
    disclosure ``metrics.drill_down`` role-gates to ``admin``/``coordinator``
    alone. A student standing in exactly the right department still gets none of
    it, which is what makes the refusal about ``_REVIEW_ROLES`` rather than
    about where they stand.
    """
    client = queue["client"]
    token = _register_principal(
        engine,
        client,
        queue["tenant_id"],
        role="student",
        membership_path=UNIT_PATH,
    )

    response = _list(client, queue["unit_id"], token, status="pending")
    assert response.status_code == 403, response.text


def test_another_tenants_unit_is_a_404_rather_than_a_403(queue: dict[str, Any]) -> None:
    """A real unit in another tenant is indistinguishable from no unit at all.

    ``load_unit_or_404`` scopes the lookup by the caller's own tenant, so the
    row is simply not found. The distinction being protected is that a 403 would
    confirm the id names something real — an oracle a caller could walk to
    enumerate another tenant's org tree — while a 404 tells them nothing they
    did not already supply.
    """
    client = queue["client"]
    response = _list(client, queue["other_unit_id"], queue["token"], status="pending")
    assert response.status_code == 404, response.text


def test_an_unauthenticated_caller_reads_nothing(queue: dict[str, Any]) -> None:
    """No token, no queue. The route is authenticated before it is authorized."""
    client = queue["client"]
    response = client.get(f"/v1/units/{queue['unit_id']}/review-items")
    assert response.status_code == 401, response.text
