"""HTTP contract for ``GET /v1/units/{unit_id}/speaker-pipeline``.

This writes real ``pipeline_record`` and ``review_item`` rows and asserts that
the funnel, the conversions and the insights come back consistent with them —
the storage queries, not a fake adapter. The load-bearing assertion is that
this route's counts equal the ones ``GET /v1/units/{unit_id}/metrics`` returns
for the same unit in the same state: two routes, one owning query each, and no
room for a second definition.

``tests/contract/test_pipeline_stages.py`` is its counterpart on the write
side (the S12 coordinator stage writers). Nothing there reads this route, and
nothing here writes through one — the rows are seeded directly so that a
failure names the read, not the writer.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

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
UNIT_PATH = "iawest.pipeline"
#: A second department in the same tenant containing none of the first. Rows
#: written here must never be counted for :data:`UNIT_PATH`.
OTHER_UNIT_PATH = "iawest.pipelineother"

#: How many records reach each stage in the seeded population. Chosen so the
#: three conversions are distinct from each other and from 100%, and so the
#: matched-to-contacted rate sits below ``WEAK_OUTREACH_RATE_PCT``.
MATCHED = 10
CONTACTED = 4
CONFIRMED = 2
ATTENDED = 1

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)

#: Tables this fixture clears for its own throwaway tenant, ordered so a child
#: is removed before the row it references. Every statement is scoped by
#: ``tenant_id`` to a tenant created seconds earlier in the same test, and the
#: list mirrors ``tests/contract/test_metrics.py``.
TEARDOWN_TABLES = (
    "pipeline_record",
    "point_ledger_entry",
    "attendance_record",
    "event",
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
)


def drop_tenant(engine: Engine, tenant_id: uuid.UUID, tables: tuple[str, ...]) -> None:
    """Remove one throwaway tenant's rows, mirroring ``test_metrics.py``."""
    with engine.begin() as conn:
        for table in tables:
            conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": tenant_id})
        conn.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tenant_id})


def seed_pipeline_records(
    conn,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    subject_id: uuid.UUID,
    matched: int,
    contacted: int,
    confirmed: int,
    attended: int,
) -> None:
    """Write ``matched`` records, the first ``contacted`` of which advance, etc.

    The nesting is deliberate and is what ``ck_pipeline_record_stage_prefix``
    requires anyway: the rows that reached Attended are a subset of those that
    reached Confirmed, and so on outward. That is the property that makes a
    conversion rate a cohort rate rather than a quotient of two numbers.
    """
    for index in range(matched):
        attendance_id: uuid.UUID | None = None
        contacted_at = BASE_TIME + timedelta(days=1) if index < contacted else None
        confirmed_at = BASE_TIME + timedelta(days=2) if index < confirmed else None
        attended_at = BASE_TIME + timedelta(days=3) if index < attended else None

        if attended_at is not None:
            # ``ck_pipeline_record_attendance_evidence`` makes the attendance
            # row a biconditional with ``attended_at``: the claim never travels
            # without its evidence, so the evidence is written first — and the
            # attendance row in turn cites a real ``event``, which is what its
            # own ``(tenant_id, event_id)`` foreign key requires.
            #
            # The event is deliberately the least-committed shape the schema
            # admits: ``time_precision = 'unresolved'`` (so ``starts_at``,
            # ``on_date`` and ``time_zone`` are all null under
            # ``ck_event_temporal_shape``) and ``origin = 'coordinator_entry'``
            # (so no ``source_url``/``fetched_at``/``extractor_version``
            # provenance triple is owed under ``ck_event_provenance_evidence``).
            # Nothing in this file asserts anything about the event; it exists
            # only so the attendance evidence has something to point at.
            event_id = uuid.uuid4()
            conn.execute(
                text(
                    "INSERT INTO event "
                    "(id, tenant_id, host_org_unit_id, title, normalized_title, "
                    "time_precision, origin) "
                    "VALUES (:id, :tid, :unit, :title, :title, 'unresolved', "
                    "'coordinator_entry')"
                ),
                {
                    "id": event_id,
                    "tid": tenant_id,
                    "unit": unit_id,
                    "title": f"pipeline-fixture-{index}",
                },
            )

            attendance_id = uuid.uuid4()
            conn.execute(
                text(
                    "INSERT INTO attendance_record "
                    "(id, tenant_id, owning_unit_id, subject_id, event_id, method) "
                    "VALUES (:id, :tid, :unit, :subject, :event, 'coordinator_entry')"
                ),
                {
                    "id": attendance_id,
                    "tid": tenant_id,
                    "unit": unit_id,
                    "subject": subject_id,
                    "event": event_id,
                },
            )

        conn.execute(
            text(
                "INSERT INTO pipeline_record "
                "(id, tenant_id, owning_unit_id, subject_id, opportunity_event_id, "
                "matched_at, contacted_at, confirmed_at, attended_at, "
                "attended_attendance_id, matched_provenance) "
                "VALUES (:id, :tid, :unit, :subject, :event, :matched_at, :contacted_at, "
                ":confirmed_at, :attended_at, :attendance, 'synthetic / coordinator-accepted')"
            ),
            {
                "id": uuid.uuid4(),
                "tid": tenant_id,
                "unit": unit_id,
                "subject": subject_id,
                "event": uuid.uuid4(),
                "matched_at": BASE_TIME,
                "contacted_at": contacted_at,
                "confirmed_at": confirmed_at,
                "attended_at": attended_at,
                "attendance": attendance_id,
            },
        )


@pytest.fixture(scope="module")
def engine() -> Engine:
    """Return a live migrated PostgreSQL engine, or skip this contract."""
    try:
        eng = create_engine(DATABASE_URL, future=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1 FROM pipeline_record LIMIT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"no migrated PostgreSQL available at {DATABASE_URL}: {exc}")
    return eng


@pytest.fixture
def pipeline_context(engine: Engine) -> Iterator[tuple[TestClient, uuid.UUID, str]]:
    """One authorized unit seeded with a nested funnel and a review queue."""
    tenant_id = uuid.uuid4()
    unit_id = uuid.uuid4()
    other_unit_id = uuid.uuid4()
    user_id = uuid.uuid4()
    job_id = uuid.uuid4()
    batch_id = uuid.uuid4()
    subject = f"sub-pipe-{uuid.uuid4().hex}"
    token = f"tok-pipe-{uuid.uuid4().hex}"

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"test-pipe-{tenant_id.hex[:12]}"},
        )
        for oid, path in ((unit_id, UNIT_PATH), (other_unit_id, OTHER_UNIT_PATH)):
            conn.execute(
                text(
                    "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                    "VALUES (:id, :tid, CAST(:path AS ltree), 'department', 'Pipeline')"
                ),
                {"id": oid, "tid": tenant_id, "path": path},
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
                "VALUES (:id, :tid, :uid, CAST(:path AS ltree), 'coordinator')"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "uid": user_id, "path": UNIT_PATH},
        )
        conn.execute(
            text(
                "INSERT INTO job "
                "(id, tenant_id, command_type, status, actor_id, owning_unit_id, payload) "
                "VALUES (:id, :tid, 'import.create', 'succeeded', :actor, :unit, '{}'::jsonb)"
            ),
            {"id": job_id, "tid": tenant_id, "actor": user_id, "unit": unit_id},
        )
        conn.execute(
            text(
                "INSERT INTO import_batch "
                "(id, tenant_id, owning_unit_id, job_id, dataset, row_count, dry_run) "
                "VALUES (:id, :tid, :unit, :job, 'events', 3, false)"
            ),
            {"id": batch_id, "tid": tenant_id, "unit": unit_id, "job": job_id},
        )
        # Two pending rows and one accepted, in-list row: a review queue whose
        # pending share clears ``REVIEW_BACKLOG_SHARE_PCT``.
        for row_index, review_status, category in (
            (0, "pending", "hackathon"),
            (1, "pending", "hackathon"),
            (2, "accepted", "hackathon"),
        ):
            decided = review_status != "pending"
            conn.execute(
                text(
                    "INSERT INTO review_item "
                    "(id, tenant_id, import_batch_id, row_index, row_data, status, "
                    "decided_at, decided_by) "
                    "VALUES (:id, :tid, :batch, :idx, CAST(:data AS jsonb), :status, "
                    ":decided_at, :decided_by)"
                ),
                {
                    "id": uuid.uuid4(),
                    "tid": tenant_id,
                    "batch": batch_id,
                    "idx": row_index,
                    "data": '{"category": "' + category + '"}',
                    "status": review_status,
                    "decided_at": datetime.now(UTC) if decided else None,
                    "decided_by": user_id if decided else None,
                },
            )

        seed_pipeline_records(
            conn,
            tenant_id=tenant_id,
            unit_id=unit_id,
            subject_id=user_id,
            matched=MATCHED,
            contacted=CONTACTED,
            confirmed=CONFIRMED,
            attended=ATTENDED,
        )
        # A sibling unit's records, which must not be counted for ``unit_id``.
        seed_pipeline_records(
            conn,
            tenant_id=tenant_id,
            unit_id=other_unit_id,
            subject_id=user_id,
            matched=7,
            contacted=7,
            confirmed=7,
            attended=0,
        )

    verifier = FixtureTokenVerifier()
    verifier.register(token, subject)
    client = TestClient(app)
    client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    client.app.state.token_verifier = verifier

    yield client, unit_id, token

    drop_tenant(engine, tenant_id, TEARDOWN_TABLES)


def get_as(client: TestClient, path: str, token: str):
    return client.get(path, headers={"Authorization": f"Bearer {token}"})


def payload_of(context) -> dict:
    client, unit_id, token = context
    response = get_as(client, f"/v1/units/{unit_id}/speaker-pipeline", token)
    assert response.status_code == 200, response.text
    return response.json()


def test_stage_counts_are_cumulative_and_unit_scoped(pipeline_context) -> None:
    """Each stage counts its own rows and the sibling unit's never leak in."""
    body = payload_of(pipeline_context)
    counts = {stage["metric_name"]: stage["value"] for stage in body["stages"]}
    assert counts == {
        "pipeline_matched": MATCHED,
        "pipeline_contacted": CONTACTED,
        "pipeline_confirmed": CONFIRMED,
        "pipeline_attended": ATTENDED,
    }


def test_this_route_and_the_metrics_collection_agree(pipeline_context) -> None:
    """The same owning query serves both, so the numbers cannot differ."""
    client, unit_id, token = pipeline_context
    pipeline = payload_of(pipeline_context)
    collection = get_as(client, f"/v1/units/{unit_id}/metrics?surface=cba", token).json()

    as_pipeline = {m["name"]: m["value"] for m in pipeline["metrics"]}
    as_collection = {m["name"]: m["value"] for m in collection["metrics"]}
    assert as_pipeline == as_collection


def test_conversions_are_only_the_three_lifecycle_transitions(pipeline_context) -> None:
    body = payload_of(pipeline_context)
    assert [(c["from_metric"], c["to_metric"]) for c in body["conversions"]] == [
        ("pipeline_matched", "pipeline_contacted"),
        ("pipeline_contacted", "pipeline_confirmed"),
        ("pipeline_confirmed", "pipeline_attended"),
    ]
    rates = {c["to_metric"]: c["rate_pct"] for c in body["conversions"]}
    assert rates["pipeline_contacted"] == pytest.approx(CONTACTED / MATCHED * 100)
    assert rates["pipeline_confirmed"] == pytest.approx(CONFIRMED / CONTACTED * 100)
    assert rates["pipeline_attended"] == pytest.approx(ATTENDED / CONFIRMED * 100)
    assert all(c["rate_pct"] <= 100 for c in body["conversions"])


def test_review_metrics_travel_as_companions_not_stages(pipeline_context) -> None:
    body = payload_of(pipeline_context)
    companions = {c["metric_name"]: c["value"] for c in body["companions"]}
    assert companions == {"opportunities": 1, "pending_review_items": 2}
    stage_names = {stage["metric_name"] for stage in body["stages"]}
    assert stage_names.isdisjoint(companions)


def test_insights_reflect_the_seeded_population(pipeline_context) -> None:
    body = payload_of(pipeline_context)
    codes = {insight["code"] for insight in body["insights"]}
    # 40% of matched were contacted, and two of three review rows are pending.
    assert {"weak_outreach", "review_backlog"} <= codes
    assert len(body["insights"]) <= 3


def test_the_range_is_named_as_unfiltered(pipeline_context) -> None:
    body = payload_of(pipeline_context)
    assert body["range"]["kind"] == "all_time"
    assert body["range"]["label"]
    assert body["range"]["note"]


def test_an_empty_unit_reports_measured_zeros_and_no_rates(engine: Engine) -> None:
    """Zero everywhere is a measured zero; its conversions are em dashes."""
    tenant_id = uuid.uuid4()
    unit_id = uuid.uuid4()
    user_id = uuid.uuid4()
    subject = f"sub-empty-{uuid.uuid4().hex}"
    token = f"tok-empty-{uuid.uuid4().hex}"
    path = "iawest.pipelineempty"

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": tenant_id, "slug": f"test-empty-{tenant_id.hex[:12]}"},
        )
        conn.execute(
            text(
                "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                "VALUES (:id, :tid, CAST(:path AS ltree), 'department', 'Empty')"
            ),
            {"id": unit_id, "tid": tenant_id, "path": path},
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
                "VALUES (:id, :tid, :uid, CAST(:path AS ltree), 'coordinator')"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "uid": user_id, "path": path},
        )

    verifier = FixtureTokenVerifier()
    verifier.register(token, subject)
    client = TestClient(app)
    client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    client.app.state.token_verifier = verifier

    try:
        body = get_as(client, f"/v1/units/{unit_id}/speaker-pipeline", token).json()
        assert all(stage["value"] == 0 for stage in body["stages"])
        for conversion in body["conversions"]:
            assert conversion["rate_pct"] is None
            assert conversion["display"] == "—"
            assert conversion["unavailable_reason"]
        assert [i["code"] for i in body["insights"]] == ["insufficient_activity"]
    finally:
        drop_tenant(engine, tenant_id, ("membership", "user_account", "org_unit"))


def test_an_unauthenticated_caller_is_refused(pipeline_context) -> None:
    client, unit_id, _token = pipeline_context
    assert client.get(f"/v1/units/{unit_id}/speaker-pipeline").status_code == 401


def test_a_foreign_unit_is_refused(pipeline_context) -> None:
    """A coordinator's membership does not reach a unit it does not contain."""
    client, _unit_id, token = pipeline_context
    response = get_as(client, f"/v1/units/{uuid.uuid4()}/speaker-pipeline", token)
    assert response.status_code in (403, 404)
