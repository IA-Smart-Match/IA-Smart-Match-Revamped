"""HTTP-level proof that a coordinator's accept provisions the pipeline (Card 6).

Every other test that exercises `smartmatch_api.pipeline_provisioning` calls it
directly, in-process (Card 5). This file is the first to prove it is actually
*reachable* — from a deployed, authenticated path, exactly the way a real
coordinator triggers it: `POST /v1/review-items/{review_item_id}/decision`,
through a real `TestClient`, a real `FixtureTokenVerifier`, and a real
`coordinator` membership, after `charge_quota(...)` and `assert_allowed(...)`
have both already run (plan §1.6). Nothing here calls
`provision_on_accept` or `PipelineRepository` to drive a decision — only to
pre-seed a fixture (the rollback test) or to compute the same deterministic
ids `smartmatch_api.pipeline_provisioning` derives, so an assertion can name
the row it expects to find rather than merely counting rows.

`routers/review.py::decide_review_item` is the only call site this plan wires
(Decision 1). This file's whole point is proving that call site is real: an
accept truly writes a `user_account`, a `professional_unit_relationship`, and
a `pipeline_record` row that a caller with the coordinator role, and only that
role, can trigger through the actual route — and that everything §1.6 pins
(the role set, the rate limit, the `assert_allowed` call's shape) still
behaves exactly as it did before this card, because this card touches an
authorized route and a regression there is worse than one anywhere else in
this plan.

Requires a live database, and is skipped when none is reachable
(`engine` fixture, `tests/integration/conftest.py`).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

pytest.importorskip("sqlalchemy")

import httpx
from conftest import JOB_OWNING_UNIT_PATH, ensure_owning_unit, unique_subject
from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_api.routers.review import _REVIEW_ROLES, REVIEW_DECISION_RATE_LIMIT
from smartmatch_domain.synthetic_pilot import (
    synthetic_opportunity_event_id,
    synthetic_professional_email,
    synthetic_professional_external_subject,
    synthetic_professional_subject_id,
)
from smartmatch_persistence.engine import create_session_factory
from smartmatch_persistence.pipeline import (
    MATCH_PROVENANCE_SYNTHETIC_COORDINATOR,
    ConflictingOwningUnitError,
    PipelineRepository,
)
from smartmatch_persistence.rate_limit import RateLimit
from smartmatch_persistence.review import ReviewRepository
from smartmatch_providers import FixtureTokenVerifier
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker
from test_import_review_constraints import _make_job
from test_pipeline_record_constraints import _make_unit

pytestmark = pytest.mark.integration

#: Mirrors `test_pipeline_record_writers.py`'s own dataset shape for the
#: compose smoke path's `professionals` row — no email column, no
#: `board_role` (P9 Gate A). See plan §2 Decision 6.
_PROFESSIONAL_ROW: Mapping[str, Any] = {"name": "Ada Lovelace", "metro_region": "Portland"}

#: An in-list category (`smartmatch_domain.metrics.OPPORTUNITY_IN_LIST_CATEGORIES`).
_IN_LIST_EVENT_ROW: Mapping[str, Any] = {"category": "hackathon"}


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    """A session factory bound to the live test engine.

    Mirrors `test_pipeline_record_writers.py`'s own `db_session_factory`.
    `ReviewRepository.create_batch_with_items` takes an ORM `Session`; the
    fixture is named `session_factory` here (not `db_session_factory`) only
    because this file has no other session-shaped fixture to collide with.
    """
    return create_session_factory(engine.url.render_as_string(hide_password=False))


@pytest.fixture(autouse=True)
def _clean_provisioned_rows(engine: Engine, tenant_id: uuid.UUID) -> Iterator[None]:
    """Delete this file's `pipeline_record` / `professional_unit_relationship` rows.

    Both carry `ON DELETE RESTRICT` foreign keys back to `org_unit` and (for
    `pipeline_record`) `user_account`. Neither table is in `conftest.py`'s
    `_TENANT_SCOPED_TABLES`, so a row left behind here would make the
    `tenant_id` fixture's own teardown fail — the same arrangement, for the
    same reason, as `test_pipeline_record_writers.py`'s
    `_clean_pipeline_and_attendance_tables`. `import_batch` and `review_item`
    need no cleanup of their own: both cascade from `job`, which `tenant_id`'s
    teardown already deletes (`test_import_review_constraints.py::_make_job`'s
    own docstring).
    """
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM pipeline_record WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(
            text("DELETE FROM professional_unit_relationship WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )


@pytest.fixture
def other_tenant_id(engine: Engine) -> Iterator[uuid.UUID]:
    """A second, fully independent tenant — for the cross-tenant negative test.

    Mirrors `test_engagement_schema_constraints.py::other_tenant_id`, extended
    with the extra tables this file's helpers write for it: `job` (via
    `_make_job`) and `org_unit` (via `ensure_owning_unit`), both of which
    `import_batch`/`review_item` and `pipeline_record`/
    `professional_unit_relationship` respectively would cascade or restrict
    against if left behind.
    """
    tid = uuid.uuid4()
    slug = f"test-other-{tid.hex[:12]}"
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :name)"),
            {"id": tid, "slug": slug, "name": slug},
        )
    yield tid
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM pipeline_record WHERE tenant_id = :tid"), {"tid": tid})
        conn.execute(
            text("DELETE FROM professional_unit_relationship WHERE tenant_id = :tid"), {"tid": tid}
        )
        conn.execute(text("DELETE FROM job WHERE tenant_id = :tid"), {"tid": tid})
        conn.execute(text("DELETE FROM user_account WHERE tenant_id = :tid"), {"tid": tid})
        conn.execute(text("DELETE FROM org_unit WHERE tenant_id = :tid"), {"tid": tid})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tid})


def _make_client(engine: Engine) -> TestClient:
    """A `TestClient` wired to the live test database and a fixture verifier.

    Copies `test_pipeline_record_writers.py::_make_client`'s shape exactly, per
    this card's brief.
    """
    client = TestClient(app)
    client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    client.app.state.token_verifier = FixtureTokenVerifier()
    return client


def _register_principal(
    engine: Engine,
    client: TestClient,
    tenant_id: uuid.UUID,
    *,
    unit_path: str | None,
    role: str | None,
    subject_prefix: str,
) -> tuple[str, uuid.UUID]:
    """Register a `user_account`, optionally a `membership`, and a bearer token.

    `unit_path` / `role` both `None` registers an authenticated caller with no
    membership anywhere — the "no role at all" negative case §5's assertion
    list asks for, distinct from a membership at the wrong role.
    """
    user_id = uuid.uuid4()
    subject = unique_subject(f"{subject_prefix}-{user_id.hex[:8]}")
    token = f"tok-{subject_prefix}-{uuid.uuid4().hex}"
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO user_account (id, tenant_id, external_subject, email) "
                "VALUES (:id, :tid, :sub, :email)"
            ),
            {
                "id": user_id,
                "tid": tenant_id,
                "sub": subject,
                "email": f"{user_id.hex[:8]}@example.edu",
            },
        )
        if unit_path is not None and role is not None:
            conn.execute(
                text(
                    "INSERT INTO membership (id, tenant_id, user_id, granted_path, role) "
                    "VALUES (:id, :tid, :uid, CAST(:path AS ltree), :role)"
                ),
                {
                    "id": uuid.uuid4(),
                    "tid": tenant_id,
                    "uid": user_id,
                    "path": unit_path,
                    "role": role,
                },
            )
    client.app.state.token_verifier.register(token, subject)
    return token, user_id


def _register_coordinator(
    engine: Engine, client: TestClient, tenant_id: uuid.UUID, unit_path: str
) -> tuple[str, uuid.UUID]:
    """A coordinator, registered at `unit_path`. Copies the brief's shape."""
    return _register_principal(
        engine,
        client,
        tenant_id,
        unit_path=unit_path,
        role="coordinator",
        subject_prefix="review-decision-coordinator",
    )


def _seed_review_items(
    engine: Engine,
    session_factory: sessionmaker[Session],
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    dataset: str,
    rows: Sequence[Mapping[str, Any]],
) -> tuple[uuid.UUID, ...]:
    """Write one import batch (via a fresh `job`) and return its review item ids, in row order.

    `ReviewRepository.create_batch_with_items` needs a real `job` row — this
    reuses `test_import_review_constraints.py::_make_job` rather than
    inventing a new helper, per the brief. Rows are handed to the repository
    exactly as given: normalizing a submitted row is the *import path's* job
    (`smartmatch_worker.handlers`), not the repository's, and this helper
    seeds review items directly, bypassing that path entirely — the row data
    here is already in the lower-cased, underscore-joined shape
    `review_item.row_data` is documented to hold.
    """
    with engine.begin() as conn:
        job_id = _make_job(conn, tenant_id)

    reviews = ReviewRepository()
    with session_factory() as session:
        batch = reviews.create_batch_with_items(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            job_id=job_id,
            dataset=dataset,
            rows=rows,
        )
        session.commit()

    with engine.begin() as conn:
        result = conn.execute(
            text(
                "SELECT id FROM review_item WHERE tenant_id = :tid AND import_batch_id = :bid "
                "ORDER BY row_index"
            ),
            {"tid": tenant_id, "bid": batch.id},
        )
        return tuple(row.id for row in result)


def _decide(
    client: TestClient, token: str, review_item_id: uuid.UUID, decision: str
) -> httpx.Response:
    return client.post(
        f"/v1/review-items/{review_item_id}/decision",
        json={"decision": decision},
        headers={"Authorization": f"Bearer {token}"},
    )


def _get(client: TestClient, path: str, token: str) -> httpx.Response:
    return client.get(path, headers={"Authorization": f"Bearer {token}"})


def _pipeline_record_count(engine: Engine, tenant_id: uuid.UUID) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                text("SELECT count(*) FROM pipeline_record WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            ).scalar_one()
        )


@dataclass(frozen=True, slots=True)
class _Context:
    client: TestClient
    engine: Engine
    tenant_id: uuid.UUID
    unit_id: uuid.UUID
    session_factory: sessionmaker[Session]
    coordinator_token: str
    coordinator_id: uuid.UUID


@pytest.fixture
def ctx(engine: Engine, tenant_id: uuid.UUID, session_factory: sessionmaker[Session]) -> _Context:
    with engine.begin() as conn:
        unit_id = ensure_owning_unit(conn, tenant_id)
    client = _make_client(engine)
    token, actor_id = _register_coordinator(engine, client, tenant_id, JOB_OWNING_UNIT_PATH)
    return _Context(
        client=client,
        engine=engine,
        tenant_id=tenant_id,
        unit_id=unit_id,
        session_factory=session_factory,
        coordinator_token=token,
        coordinator_id=actor_id,
    )


# ---------------------------------------------------------------------------
# 1 & 3 — accepting a professionals item provisions identity; rejecting provisions nothing
# ---------------------------------------------------------------------------


def test_accepting_a_professionals_item_provisions_a_synthetic_identity(ctx: _Context) -> None:
    (review_item_id,) = _seed_review_items(
        ctx.engine,
        ctx.session_factory,
        tenant_id=ctx.tenant_id,
        unit_id=ctx.unit_id,
        dataset="professionals",
        rows=[_PROFESSIONAL_ROW],
    )

    response = _decide(ctx.client, ctx.coordinator_token, review_item_id, "accepted")
    assert response.status_code == 200

    subject_id = synthetic_professional_subject_id(
        tenant_id=ctx.tenant_id, unit_id=ctx.unit_id, name=_PROFESSIONAL_ROW["name"]
    )
    with ctx.engine.connect() as conn:
        account = conn.execute(
            text(
                "SELECT external_subject, email FROM user_account "
                "WHERE tenant_id = :tid AND id = :sid"
            ),
            {"tid": ctx.tenant_id, "sid": subject_id},
        ).one_or_none()
        relationship = conn.execute(
            text(
                "SELECT board_role FROM professional_unit_relationship "
                "WHERE tenant_id = :tid AND professional_id = :sid AND unit_id = :uid"
            ),
            {"tid": ctx.tenant_id, "sid": subject_id, "uid": ctx.unit_id},
        ).one_or_none()

    assert account is not None
    assert account.external_subject == synthetic_professional_external_subject(subject_id)
    assert account.email == synthetic_professional_email(subject_id)
    assert relationship is not None
    assert relationship.board_role == "synthetic_pilot_participant"


def test_rejecting_a_professionals_item_provisions_nothing(ctx: _Context) -> None:
    (review_item_id,) = _seed_review_items(
        ctx.engine,
        ctx.session_factory,
        tenant_id=ctx.tenant_id,
        unit_id=ctx.unit_id,
        dataset="professionals",
        rows=[{"name": "Grace Hopper", "metro_region": "Portland"}],
    )

    response = _decide(ctx.client, ctx.coordinator_token, review_item_id, "rejected")
    assert response.status_code == 200

    subject_id = synthetic_professional_subject_id(
        tenant_id=ctx.tenant_id, unit_id=ctx.unit_id, name="Grace Hopper"
    )
    with ctx.engine.connect() as conn:
        account_count = conn.execute(
            text("SELECT count(*) FROM user_account WHERE tenant_id = :tid AND id = :sid"),
            {"tid": ctx.tenant_id, "sid": subject_id},
        ).scalar_one()
        relationship_count = conn.execute(
            text(
                "SELECT count(*) FROM professional_unit_relationship "
                "WHERE tenant_id = :tid AND professional_id = :sid"
            ),
            {"tid": ctx.tenant_id, "sid": subject_id},
        ).scalar_one()
        # Only the coordinator's own account should exist for this tenant.
        total_accounts = conn.execute(
            text("SELECT count(*) FROM user_account WHERE tenant_id = :tid"),
            {"tid": ctx.tenant_id},
        ).scalar_one()

    assert account_count == 0
    assert relationship_count == 0
    assert total_accounts == 1
    assert _pipeline_record_count(ctx.engine, ctx.tenant_id) == 0


# ---------------------------------------------------------------------------
# 2 — accepting an in-list events item opens a pipeline_record journey
# ---------------------------------------------------------------------------


def test_accepting_an_inlist_events_item_opens_a_pipeline_record(ctx: _Context) -> None:
    (professional_item_id,) = _seed_review_items(
        ctx.engine,
        ctx.session_factory,
        tenant_id=ctx.tenant_id,
        unit_id=ctx.unit_id,
        dataset="professionals",
        rows=[_PROFESSIONAL_ROW],
    )
    assert (
        _decide(ctx.client, ctx.coordinator_token, professional_item_id, "accepted").status_code
        == 200
    )

    (event_item_id,) = _seed_review_items(
        ctx.engine,
        ctx.session_factory,
        tenant_id=ctx.tenant_id,
        unit_id=ctx.unit_id,
        dataset="events",
        rows=[_IN_LIST_EVENT_ROW],
    )
    response = _decide(ctx.client, ctx.coordinator_token, event_item_id, "accepted")
    assert response.status_code == 200

    subject_id = synthetic_professional_subject_id(
        tenant_id=ctx.tenant_id, unit_id=ctx.unit_id, name=_PROFESSIONAL_ROW["name"]
    )
    opportunity_event_id = synthetic_opportunity_event_id(
        tenant_id=ctx.tenant_id, review_item_id=event_item_id
    )

    with ctx.engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT owning_unit_id, subject_id, opportunity_event_id, matched_provenance "
                "FROM pipeline_record WHERE tenant_id = :tid"
            ),
            {"tid": ctx.tenant_id},
        ).one()

    assert row.owning_unit_id == ctx.unit_id
    assert row.subject_id == subject_id
    assert row.opportunity_event_id == opportunity_event_id
    assert row.matched_provenance == MATCH_PROVENANCE_SYNTHETIC_COORDINATOR
    assert row.matched_provenance == "synthetic / coordinator-accepted"


# ---------------------------------------------------------------------------
# 4 — a second decision on the same item is 409 and does not double-provision
# ---------------------------------------------------------------------------


def test_a_second_decision_on_the_same_item_is_409_and_does_not_double_provision(
    ctx: _Context,
) -> None:
    (professional_item_id,) = _seed_review_items(
        ctx.engine,
        ctx.session_factory,
        tenant_id=ctx.tenant_id,
        unit_id=ctx.unit_id,
        dataset="professionals",
        rows=[_PROFESSIONAL_ROW],
    )
    assert (
        _decide(ctx.client, ctx.coordinator_token, professional_item_id, "accepted").status_code
        == 200
    )

    (event_item_id,) = _seed_review_items(
        ctx.engine,
        ctx.session_factory,
        tenant_id=ctx.tenant_id,
        unit_id=ctx.unit_id,
        dataset="events",
        rows=[_IN_LIST_EVENT_ROW],
    )
    first = _decide(ctx.client, ctx.coordinator_token, event_item_id, "accepted")
    assert first.status_code == 200
    assert _pipeline_record_count(ctx.engine, ctx.tenant_id) == 1

    second = _decide(ctx.client, ctx.coordinator_token, event_item_id, "accepted")
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "review_item_already_decided"
    assert _pipeline_record_count(ctx.engine, ctx.tenant_id) == 1


# ---------------------------------------------------------------------------
# 5 — authorization is unchanged: wrong role, no membership, unauthenticated
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("unit_path", "role", "subject_prefix"),
    [
        pytest.param(JOB_OWNING_UNIT_PATH, "student", "review-decision-student", id="wrong-role"),
        pytest.param(None, None, "review-decision-no-membership", id="no-membership"),
    ],
)
def test_a_non_coordinator_principal_is_denied_and_provisions_nothing(
    ctx: _Context, unit_path: str | None, role: str | None, subject_prefix: str
) -> None:
    """A `student` membership at the right path, and no membership at all,
    are both refused — neither is the `_REVIEW_ROLES` this route requires.
    """
    (event_item_id,) = _seed_review_items(
        ctx.engine,
        ctx.session_factory,
        tenant_id=ctx.tenant_id,
        unit_id=ctx.unit_id,
        dataset="events",
        rows=[_IN_LIST_EVENT_ROW],
    )
    token, _ = _register_principal(
        ctx.engine,
        ctx.client,
        ctx.tenant_id,
        unit_path=unit_path,
        role=role,
        subject_prefix=subject_prefix,
    )

    response = _decide(ctx.client, token, event_item_id, "accepted")

    assert response.status_code == 403
    assert _pipeline_record_count(ctx.engine, ctx.tenant_id) == 0


def test_unauthenticated_is_denied_and_provisions_nothing(ctx: _Context) -> None:
    (event_item_id,) = _seed_review_items(
        ctx.engine,
        ctx.session_factory,
        tenant_id=ctx.tenant_id,
        unit_id=ctx.unit_id,
        dataset="events",
        rows=[_IN_LIST_EVENT_ROW],
    )

    response = ctx.client.post(
        f"/v1/review-items/{event_item_id}/decision", json={"decision": "accepted"}
    )

    assert response.status_code == 401
    assert _pipeline_record_count(ctx.engine, ctx.tenant_id) == 0


# ---------------------------------------------------------------------------
# 6 — cross-tenant: a valid id from another tenant is 404, not 403
# ---------------------------------------------------------------------------


def test_a_review_item_from_another_tenant_is_404_not_403(
    ctx: _Context, other_tenant_id: uuid.UUID
) -> None:
    with ctx.engine.begin() as conn:
        other_unit_id = ensure_owning_unit(conn, other_tenant_id)

    (other_tenant_item_id,) = _seed_review_items(
        ctx.engine,
        ctx.session_factory,
        tenant_id=other_tenant_id,
        unit_id=other_unit_id,
        dataset="events",
        rows=[_IN_LIST_EVENT_ROW],
    )

    response = _decide(ctx.client, ctx.coordinator_token, other_tenant_item_id, "accepted")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "review_item_not_found"
    assert _pipeline_record_count(ctx.engine, other_tenant_id) == 0


# ---------------------------------------------------------------------------
# 7 — a rejected in-list events item never becomes an opportunity
# ---------------------------------------------------------------------------


def test_a_rejected_events_item_never_becomes_an_opportunity(ctx: _Context) -> None:
    (event_item_id,) = _seed_review_items(
        ctx.engine,
        ctx.session_factory,
        tenant_id=ctx.tenant_id,
        unit_id=ctx.unit_id,
        dataset="events",
        rows=[_IN_LIST_EVENT_ROW],
    )
    assert _decide(ctx.client, ctx.coordinator_token, event_item_id, "rejected").status_code == 200

    metrics = _get(ctx.client, f"/v1/units/{ctx.unit_id}/metrics", ctx.coordinator_token)
    assert metrics.status_code == 200
    by_name = {item["name"]: item for item in metrics.json()["metrics"]}
    assert by_name["opportunities"]["value"] == 0


# ---------------------------------------------------------------------------
# 8 — the decision response shape is unchanged: no provenance, no journey count, no score
# ---------------------------------------------------------------------------


def test_the_decision_response_shape_is_unchanged(ctx: _Context) -> None:
    (professional_item_id,) = _seed_review_items(
        ctx.engine,
        ctx.session_factory,
        tenant_id=ctx.tenant_id,
        unit_id=ctx.unit_id,
        dataset="professionals",
        rows=[_PROFESSIONAL_ROW],
    )

    response = _decide(ctx.client, ctx.coordinator_token, professional_item_id, "accepted")

    assert response.status_code == 200
    assert set(response.json().keys()) == {"id", "status", "decided_at"}


# ---------------------------------------------------------------------------
# Silent zero (plan §1.10): the route's own logging, not merely the service's
# ---------------------------------------------------------------------------


def test_accepting_an_inlist_events_item_with_no_linked_professionals_is_logged_by_the_route(
    ctx: _Context, caplog: pytest.LogCaptureFixture
) -> None:
    """No professional is accepted into `ctx.unit_id` first — the accept below
    opens zero journeys, and that must be visible from `routers/review.py`'s
    own logger, not only from `smartmatch_api.pipeline_provisioning`'s.
    """
    (event_item_id,) = _seed_review_items(
        ctx.engine,
        ctx.session_factory,
        tenant_id=ctx.tenant_id,
        unit_id=ctx.unit_id,
        dataset="events",
        rows=[_IN_LIST_EVENT_ROW],
    )

    with caplog.at_level(logging.WARNING, logger="smartmatch_api.routers.review"):
        response = _decide(ctx.client, ctx.coordinator_token, event_item_id, "accepted")

    assert response.status_code == 200
    assert _pipeline_record_count(ctx.engine, ctx.tenant_id) == 0

    route_warnings = [
        record
        for record in caplog.records
        if record.name == "smartmatch_api.routers.review" and record.levelno == logging.WARNING
    ]
    assert len(route_warnings) == 1
    assert str(event_item_id) in route_warnings[0].getMessage()
    assert "zero pipeline journeys" in route_warnings[0].getMessage()

    # The decision itself is still recorded — a zero-journey outcome is not an
    # error (plan §1.10; `pipeline_provisioning.py`'s own module docstring).
    with ctx.engine.connect() as conn:
        status_value = conn.execute(
            text("SELECT status FROM review_item WHERE tenant_id = :tid AND id = :id"),
            {"tid": ctx.tenant_id, "id": event_item_id},
        ).scalar_one()
    assert status_value == "accepted"


# ---------------------------------------------------------------------------
# A provisioning failure rolls back the decision with it
# ---------------------------------------------------------------------------


def test_a_provisioning_failure_rolls_back_the_decision(ctx: _Context) -> None:
    """A genuine `ConflictingOwningUnitError`, not a mock, aborts the whole request.

    Set up a *different* unit in the same tenant that already holds a
    `pipeline_record` for exactly the `(subject_id, opportunity_event_id)`
    pair this accept is about to derive. `record_matched`'s own idempotency
    key excludes `owning_unit_id` (migration `0011`'s docstring), so writing
    that pair under a second, different unit is refused —
    `ConflictingOwningUnitError` — deliberately left to propagate
    (`pipeline_provisioning.py`'s own docstring). Because it propagates before
    this handler's own `session.commit()`, the whole request rolls back with
    it: the `review_item` this test accepts must still read back `pending`
    afterward, and `pipeline_record` must still hold only the one row this
    test pre-seeded — not a second one for `ctx.unit_id`.
    """
    (professional_item_id,) = _seed_review_items(
        ctx.engine,
        ctx.session_factory,
        tenant_id=ctx.tenant_id,
        unit_id=ctx.unit_id,
        dataset="professionals",
        rows=[_PROFESSIONAL_ROW],
    )
    assert (
        _decide(ctx.client, ctx.coordinator_token, professional_item_id, "accepted").status_code
        == 200
    )

    (event_item_id,) = _seed_review_items(
        ctx.engine,
        ctx.session_factory,
        tenant_id=ctx.tenant_id,
        unit_id=ctx.unit_id,
        dataset="events",
        rows=[_IN_LIST_EVENT_ROW],
    )

    subject_id = synthetic_professional_subject_id(
        tenant_id=ctx.tenant_id, unit_id=ctx.unit_id, name=_PROFESSIONAL_ROW["name"]
    )
    opportunity_event_id = synthetic_opportunity_event_id(
        tenant_id=ctx.tenant_id, review_item_id=event_item_id
    )

    with ctx.engine.begin() as conn:
        conflicting_unit_id = _make_unit(conn, ctx.tenant_id, "iawest.reviewaccept.conflict")

    pipeline = PipelineRepository()
    with ctx.session_factory() as session:
        pipeline.record_matched(
            session,
            tenant_id=ctx.tenant_id,
            owning_unit_id=conflicting_unit_id,
            subject_id=subject_id,
            opportunity_event_id=opportunity_event_id,
            matched_at=datetime.now(UTC),
            matched_provenance=MATCH_PROVENANCE_SYNTHETIC_COORDINATOR,
        )
        session.commit()
    assert _pipeline_record_count(ctx.engine, ctx.tenant_id) == 1

    with pytest.raises(ConflictingOwningUnitError):
        _decide(ctx.client, ctx.coordinator_token, event_item_id, "accepted")

    # The decision must not have been committed: the item is still pending,
    # and the only pipeline_record row is the one this test pre-seeded under
    # the conflicting unit — nothing was written for ctx.unit_id.
    with ctx.engine.connect() as conn:
        status_value = conn.execute(
            text("SELECT status, decided_at FROM review_item WHERE tenant_id = :tid AND id = :id"),
            {"tid": ctx.tenant_id, "id": event_item_id},
        ).one()
    assert status_value.status == "pending"
    assert status_value.decided_at is None
    assert _pipeline_record_count(ctx.engine, ctx.tenant_id) == 1
    with ctx.engine.connect() as conn:
        rows_for_ctx_unit = conn.execute(
            text(
                "SELECT count(*) FROM pipeline_record "
                "WHERE tenant_id = :tid AND owning_unit_id = :uid"
            ),
            {"tid": ctx.tenant_id, "uid": ctx.unit_id},
        ).scalar_one()
    assert rows_for_ctx_unit == 0


# ---------------------------------------------------------------------------
# The role set and rate limit this plan must not touch
# ---------------------------------------------------------------------------


def test_review_roles_and_rate_limit_are_unchanged() -> None:
    """A cheap, no-database guard against exactly the drift plan §1.6 forbids."""
    assert frozenset({"admin", "coordinator"}) == _REVIEW_ROLES
    assert (
        RateLimit(operation="review.decide", max_requests=60, window=timedelta(minutes=1))
        == REVIEW_DECISION_RATE_LIMIT
    )
