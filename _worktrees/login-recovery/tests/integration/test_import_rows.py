"""``POST /v1/units/{unit_id}/imports`` with inline ``rows``: T4.

Stakeholder Fix #2 was that a live import never imported anything —
``handle_import_create`` refused every ``dry_run=false`` request with
``import_content_unavailable``, because reading ``source_reference`` needs an
object-storage adapter this worker does not have, and (until migration
``0008``) there was no ``review_item`` table for the results to go in either
way.

``rows`` removes object storage from the critical path: the caller submits
already-parsed rows in the request body, and a live import over them can
actually run ``smartmatch_domain.ingest.validate_columns`` and write
quarantine-and-review rows (v1.1 §1.5). ``source_reference`` stays exactly as
refused as before — that is asserted here too, as a regression guard, and
covered from the other direction by
``test_worker_execution.py::test_a_live_import_is_refused_rather_than_reported_as_done``.

The acceptance bar, from the plan this closes: a ``POST`` with inline rows
creates ``review_item`` rows and the job reaches ``succeeded``, not
``failed_policy``. That is
:func:`test_a_live_inline_row_import_creates_review_items_and_succeeds`, below;
everything else in this file is the surrounding behaviour the plan also names —
dry run writes nothing, an unusable dataset fails closed with its findings
surfaced, the bounds are enforced, ``rows``/``source_reference`` are mutually
exclusive, a re-drive does not double-insert, and a review item cannot cross a
tenant boundary.
"""

from __future__ import annotations

import uuid

import pytest
from conftest import unique_subject
from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_domain.jobs import JobState
from smartmatch_persistence.engine import create_session_factory
from smartmatch_persistence.jobs import JobRepository
from smartmatch_persistence.review import ReviewRepository
from smartmatch_providers import FixtureTokenVerifier
from smartmatch_providers.tasks import FixtureTaskQueue
from smartmatch_worker.dispatcher import OutboxDispatcher
from smartmatch_worker.execution import TaskExecutor
from smartmatch_worker.handlers import (
    CommandContext,
    CommandRegistry,
    HandlerResult,
    default_registry,
    handle_import_create,
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration

UNIT_PATH = "iawest.imports.rows"

# ---------------------------------------------------------------------------
# Fixtures — the same local shape test_command_path.py uses; each integration
# test file in this suite builds its own rather than sharing one, so a change
# to one file's wiring cannot silently affect another's.
# ---------------------------------------------------------------------------


@pytest.fixture
def unit_id(engine, tenant_id) -> uuid.UUID:
    """An org unit owned by the test tenant."""
    uid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                "VALUES (:id, :tid, CAST(:path AS ltree), 'department', 'Rows')"
            ),
            {"id": uid, "tid": tenant_id, "path": UNIT_PATH},
        )
    return uid


def _make_user(engine, tenant_id, *, subject: str) -> uuid.UUID:
    user_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO user_account (id, tenant_id, external_subject, email, suspended) "
                "VALUES (:id, :tid, :sub, :email, false)"
            ),
            {"id": user_id, "tid": tenant_id, "sub": subject, "email": f"{subject}@example.edu"},
        )
    return user_id


def _grant(engine, tenant_id, user_id, *, path: str = "iawest", role: str = "coordinator"):
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO membership (id, tenant_id, user_id, granted_path, role) "
                "VALUES (:id, :tid, :uid, CAST(:path AS ltree), :role)"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "uid": user_id, "path": path, "role": role},
        )


@pytest.fixture
def client(engine) -> TestClient:
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
    user_id = _make_user(engine, tenant_id, subject=unique_subject("sub-rows-coordinator"))
    _grant(engine, tenant_id, user_id)
    client.verifier.register("tok-rows-coordinator", unique_subject("sub-rows-coordinator"))
    return "tok-rows-coordinator"


def _post_import(client, unit_id, token, *, key: str, body: dict) -> object:
    return client.post(
        f"/v1/units/{unit_id}/imports",
        json=body,
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
    )


def _rows_body(rows: list[dict], *, dry_run: bool, dataset: str = "professionals") -> dict:
    return {"dataset": dataset, "dry_run": dry_run, "rows": rows}


# Spelled per the ratified contract (``docs/pilot-data/columns.yaml``), which
# the worker now enforces (P9 card W1): the professionals name column is
# ``name``, not ``full_name``. The mixed casing is the point — the first row is
# spelled the way a coordinator's spreadsheet export would spell it, and
# ``validate_columns`` normalizes both to the same required columns.
_SAMPLE_ROWS = [
    {"Name": "A. Rivera", "Metro Region": "Inland Empire"},
    {"name": "B. Osei", "metro_region": "Coastal"},
]


def _run_job_to_terminal(session_factory, tenant_id, job_id) -> JobState:
    """Dispatch and execute one job with the real worker path, and return its state."""
    OutboxDispatcher(session_factory, FixtureTaskQueue()).run_once()
    outcome = TaskExecutor(session_factory, default_registry()).execute(
        tenant_id=tenant_id, job_id=job_id
    )
    return outcome.state


def _terminal_event(session_factory, tenant_id, job_id) -> dict:
    jobs = JobRepository()
    with session_factory() as session:
        events = [
            event.payload
            for event in jobs.events_since(session, tenant_id=tenant_id, job_id=job_id)
        ]
    return events[-1]


# ---------------------------------------------------------------------------
# The acceptance bar
# ---------------------------------------------------------------------------


def test_a_live_inline_row_import_creates_review_items_and_succeeds(
    client, engine, session_factory, unit_id, coordinator, tenant_id
):
    """The blocker, closed: HTTP in, review items out, job succeeded.

    Every earlier release reached ``failed_policy`` with reason
    ``import_content_unavailable`` for a live import, regardless of what was
    submitted. This asserts the opposite outcome end to end — accepted through
    the real API, dispatched by the real dispatcher, executed by the real
    executor and the registry that ships — and that the review items actually
    exist in the database with the tenant, batch, index, and normalized content
    a coordinator's review view would need.
    """
    job_id = uuid.UUID(
        _post_import(
            client,
            unit_id,
            coordinator,
            key="live-rows",
            body=_rows_body(_SAMPLE_ROWS, dry_run=False),
        ).json()["job_id"]
    )

    state = _run_job_to_terminal(session_factory, tenant_id, job_id)

    assert state is JobState.SUCCEEDED, f"job reached {state}, not succeeded"

    completed = _terminal_event(session_factory, tenant_id, job_id)
    assert completed["type"] == "job.completed"
    assert completed["state"] == JobState.SUCCEEDED.value
    summary = completed["summary"]
    assert summary["mode"] == "live"
    assert summary["content_validated"] is True
    assert summary["rows_examined"] == 2
    assert summary["review_items_created"] == 2
    batch_id = uuid.UUID(summary["import_batch_id"])

    with engine.connect() as conn:
        batch_row = conn.execute(
            text(
                "SELECT tenant_id, owning_unit_id, job_id, dataset, row_count, dry_run "
                "FROM import_batch WHERE id = :id"
            ),
            {"id": batch_id},
        ).one()
        items = conn.execute(
            text(
                "SELECT row_index, row_data, status FROM review_item "
                "WHERE import_batch_id = :id ORDER BY row_index"
            ),
            {"id": batch_id},
        ).all()

    assert batch_row.tenant_id == tenant_id
    assert batch_row.owning_unit_id == unit_id
    assert batch_row.job_id == job_id
    assert batch_row.dataset == "professionals"
    assert batch_row.row_count == 2
    assert batch_row.dry_run is False

    assert [item.row_index for item in items] == [0, 1]
    assert all(item.status == "pending" for item in items)
    # Normalized: "Name" / "Metro Region" collapse to the same keys the
    # already-lowercase second row used — validate_columns compares them this
    # way, and row_data is documented (schema.py) to store that normalized
    # shape, not the raw submission.
    assert items[0].row_data == {"name": "A. Rivera", "metro_region": "Inland Empire"}
    assert items[1].row_data == {"name": "B. Osei", "metro_region": "Coastal"}


def test_gate_b_contact_values_are_persisted_after_gate_close(
    client, engine, session_factory, unit_id, coordinator, tenant_id
):
    """P9 Gate B closed 2026-09-02 — human/import contact fields may reach review_item."""
    rows = [
        {
            "Event / Program": "Career Day",
            "Category": "Outreach",
            "Host / Unit": "Riverside High",
            "Public URL": "https://example.edu/career-day",
            "Point(s) of Contact (published)": "R. Vance",
            "Contact Email / Phone (published)": "nobody@example.edu",
        }
    ]
    job_id = uuid.UUID(
        _post_import(
            client,
            unit_id,
            coordinator,
            key="gate-b-collect",
            body=_rows_body(rows, dry_run=False, dataset="events"),
        ).json()["job_id"]
    )

    state = _run_job_to_terminal(session_factory, tenant_id, job_id)
    assert state is JobState.SUCCEEDED, f"job reached {state}, not succeeded"

    completed = _terminal_event(session_factory, tenant_id, job_id)
    summary = completed["summary"]
    assert summary["usable"] is True

    withheld = [
        finding
        for finding in summary["findings"]
        if finding["code"] == "columns_withheld_pending_gate"
    ]
    assert withheld == []

    with engine.connect() as conn:
        items = conn.execute(
            text("SELECT row_data FROM review_item WHERE import_batch_id = :id ORDER BY row_index"),
            {"id": uuid.UUID(summary["import_batch_id"])},
        ).all()

    (item,) = items
    assert item.row_data == {
        "event_program": "Career Day",
        "category": "Outreach",
        "host_unit": "Riverside High",
        "public_url": "https://example.edu/career-day",
        "point_s_of_contact_published": "R. Vance",
        "contact_email_phone_published": "nobody@example.edu",
    }


def test_an_invalid_public_url_shape_is_a_finding_not_a_crash_or_a_drop(
    client, engine, session_factory, unit_id, coordinator, tenant_id
):
    """P9 pilot columns V2: URL-shape wiring, exercised end to end.

    ``smartmatch_domain.public_url.validate_static_url_shape`` is genuinely
    called on this import path (``handlers._url_shape_findings``, wired from
    ``columns.yaml``'s ``url_shaped_columns``). A shape-invalid ``Public URL``
    (here: plain ``http://``, not ``https://``) does not crash the job and
    does not silently drop the value — it is a WARNING finding the job's
    summary surfaces, the import still succeeds, and the value is written to
    ``review_item.row_data`` exactly as submitted, for a coordinator's review.
    """
    rows = [
        {
            "Event / Program": "Career Day",
            "Category": "Outreach",
            "Public URL": "http://example.edu/career-day",
        }
    ]
    job_id = uuid.UUID(
        _post_import(
            client,
            unit_id,
            coordinator,
            key="url-shape-invalid",
            body=_rows_body(rows, dry_run=False, dataset="events"),
        ).json()["job_id"]
    )

    state = _run_job_to_terminal(session_factory, tenant_id, job_id)
    assert state is JobState.SUCCEEDED, f"job reached {state}, not succeeded"

    completed = _terminal_event(session_factory, tenant_id, job_id)
    summary = completed["summary"]
    assert summary["usable"] is True

    (finding,) = [f for f in summary["findings"] if f["code"] == "url_shape_invalid"]
    assert finding["severity"] == "warning"
    assert finding["columns"] == ["Public URL"]
    assert "scheme_not_https" in finding["message"]

    with engine.connect() as conn:
        (row_data,) = conn.execute(
            text("SELECT row_data FROM review_item WHERE import_batch_id = :id"),
            {"id": uuid.UUID(summary["import_batch_id"])},
        ).one()
    assert row_data["public_url"] == "http://example.edu/career-day"


def test_an_import_missing_a_ratified_required_column_fails_closed(
    client, session_factory, unit_id, coordinator, tenant_id
):
    """The contract is enforced, not decorative (P9 card W1).

    Before W1 this import succeeded: ``validate_columns`` ran with
    ``required=()``, so a professionals export with no ``name`` column at all
    produced review items nobody could review. It now fails closed with the
    ratified requirement named.
    """
    job_id = uuid.UUID(
        _post_import(
            client,
            unit_id,
            coordinator,
            key="missing-required",
            body=_rows_body([{"metro_region": "Coastal"}], dry_run=False),
        ).json()["job_id"]
    )

    state = _run_job_to_terminal(session_factory, tenant_id, job_id)
    assert state is JobState.FAILED_POLICY

    completed = _terminal_event(session_factory, tenant_id, job_id)
    assert completed["reason"] == "dataset_not_usable"
    assert "missing_required_columns" in completed["detail"]
    assert "name" in completed["detail"]


def test_a_dataset_the_contract_does_not_declare_is_refused(
    client, session_factory, unit_id, coordinator, tenant_id
):
    """An undeclared dataset refuses rather than validating against nothing."""
    job_id = uuid.UUID(
        _post_import(
            client,
            unit_id,
            coordinator,
            key="unknown-dataset",
            body=_rows_body([{"name": "A. Rivera"}], dry_run=False, dataset="rosters"),
        ).json()["job_id"]
    )

    state = _run_job_to_terminal(session_factory, tenant_id, job_id)
    assert state is JobState.FAILED_POLICY
    assert _terminal_event(session_factory, tenant_id, job_id)["reason"] == (
        "dataset_contract_unknown"
    )


def test_cancellation_after_handler_writes_discards_review_work(
    client, engine, session_factory, unit_id, coordinator, tenant_id
):
    """A terminal outcome that loses its race must lose its business writes too.

    ``running -> cancelled`` is allowed while a handler is working. This puts
    that cancellation in the narrow window after the real import handler has
    staged its batch and review items but before the executor attempts
    ``running -> succeeded``. The conditional transition is the authority: if
    it loses, retaining the staged review queue would claim useful work exists
    for a job whose outcome was explicitly discarded.
    """
    job_id = uuid.UUID(
        _post_import(
            client,
            unit_id,
            coordinator,
            key="cancel-after-review-write",
            body=_rows_body(_SAMPLE_ROWS, dry_run=False),
        ).json()["job_id"]
    )
    OutboxDispatcher(session_factory, FixtureTaskQueue()).run_once()
    jobs = JobRepository()

    def import_then_cancel(context: CommandContext) -> HandlerResult:
        result = handle_import_create(context)
        with session_factory() as cancellation:
            assert jobs.transition(
                cancellation,
                tenant_id=tenant_id,
                job_id=job_id,
                to_state=JobState.CANCELLED,
                expected_from=JobState.RUNNING,
            )
            cancellation.commit()
        return result

    outcome = TaskExecutor(
        session_factory,
        CommandRegistry(handlers={"import.create": import_then_cancel}),
    ).execute(tenant_id=tenant_id, job_id=job_id)

    assert outcome.state is JobState.CANCELLED
    with engine.connect() as conn:
        batches = conn.execute(
            text("SELECT count(*) FROM import_batch WHERE job_id = :job_id"),
            {"job_id": job_id},
        ).scalar_one()
        items = conn.execute(
            text(
                "SELECT count(*) FROM review_item ri "
                "JOIN import_batch ib ON ib.id = ri.import_batch_id "
                "WHERE ib.job_id = :job_id"
            ),
            {"job_id": job_id},
        ).scalar_one()

    assert batches == 0
    assert items == 0
    assert _terminal_event(session_factory, tenant_id, job_id)["type"] == ("job.outcome_discarded")


def test_a_dry_run_inline_row_import_creates_no_review_items(
    client, engine, session_factory, unit_id, coordinator, tenant_id
):
    """Dry run's contract: validate and report, never write.

    Unlike the ``source_reference`` path, this dry run genuinely validates the
    submitted data — the rows are already in hand, no adapter is missing — but
    still must not create review items, which is the whole point of it being
    the safe default.
    """
    job_id = uuid.UUID(
        _post_import(
            client,
            unit_id,
            coordinator,
            key="dry-run-rows",
            body=_rows_body(_SAMPLE_ROWS, dry_run=True),
        ).json()["job_id"]
    )

    state = _run_job_to_terminal(session_factory, tenant_id, job_id)
    assert state is JobState.SUCCEEDED

    completed = _terminal_event(session_factory, tenant_id, job_id)
    summary = completed["summary"]
    assert summary["mode"] == "dry_run"
    assert summary["content_validated"] is True
    assert summary["rows_examined"] == 2
    assert summary["review_items_created"] == 0
    assert summary["usable"] is True

    with engine.connect() as conn:
        batches = conn.execute(text("SELECT count(*) FROM import_batch")).scalar_one()
        items = conn.execute(text("SELECT count(*) FROM review_item")).scalar_one()
    assert batches == 0
    assert items == 0


def test_an_empty_dataset_fails_closed_with_findings_surfaced(
    client, engine, session_factory, unit_id, coordinator, tenant_id
):
    """An unusable dataset (here: zero rows) fails closed, and says why.

    ``rows=[]`` is a legal, explicit submission distinct from omitting rows
    (see ``tests/unit/test_import_rows_validation.py``), and
    ``validate_columns`` reports zero rows as an ``empty_dataset`` ERROR
    finding — unusable. Nothing is written, and the findings are on the event
    stream for a coordinator to act on.
    """
    job_id = uuid.UUID(
        _post_import(
            client,
            unit_id,
            coordinator,
            key="unusable-rows",
            body=_rows_body([], dry_run=False),
        ).json()["job_id"]
    )

    state = _run_job_to_terminal(session_factory, tenant_id, job_id)
    assert state is JobState.FAILED_POLICY

    completed = _terminal_event(session_factory, tenant_id, job_id)
    assert completed["type"] == "job.failed"
    assert completed["reason"] == "dataset_not_usable"
    assert "empty_dataset" in completed["detail"]

    jobs = JobRepository()
    with session_factory() as session:
        events = [
            event.payload
            for event in jobs.events_since(session, tenant_id=tenant_id, job_id=job_id)
        ]
    progress = next(e for e in events if e["type"] == "progress" and "findings" in e)
    assert progress["usable"] is False
    codes = [f["code"] for f in progress["findings"]]
    assert "empty_dataset" in codes

    with engine.connect() as conn:
        batches = conn.execute(text("SELECT count(*) FROM import_batch")).scalar_one()
    assert batches == 0


def test_source_reference_live_import_is_still_refused(
    client, session_factory, unit_id, coordinator, tenant_id
):
    """The other content shape is unchanged: still refused, still terminal.

    A regression guard for the half of this route that was explicitly told not
    to change. The mirror image of this file's rows-succeed test.
    """
    job_id = uuid.UUID(
        _post_import(
            client,
            unit_id,
            coordinator,
            key="source-ref-live",
            body={
                "dataset": "professionals",
                "dry_run": False,
                "source_reference": "gs://bucket/roster.csv",
            },
        ).json()["job_id"]
    )

    state = _run_job_to_terminal(session_factory, tenant_id, job_id)
    assert state is JobState.FAILED_POLICY

    completed = _terminal_event(session_factory, tenant_id, job_id)
    assert completed["reason"] == "import_content_unavailable"


# ---------------------------------------------------------------------------
# Request shape: mutual exclusivity and bounds
# ---------------------------------------------------------------------------


def test_rows_and_source_reference_together_is_rejected(client, unit_id, coordinator):
    response = _post_import(
        client,
        unit_id,
        coordinator,
        key="both",
        body={
            "dataset": "professionals",
            "dry_run": True,
            "rows": [{"full_name": "A"}],
            "source_reference": "gs://bucket/roster.csv",
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "import_source_ambiguous"


def test_neither_rows_nor_source_reference_is_rejected(client, unit_id, coordinator):
    response = _post_import(
        client, unit_id, coordinator, key="neither", body={"dataset": "professionals"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "import_source_ambiguous"


def test_more_than_the_row_count_bound_is_rejected(client, unit_id, coordinator):
    rows = [{"i": i} for i in range(5_001)]
    response = _post_import(
        client, unit_id, coordinator, key="too-many-rows", body=_rows_body(rows, dry_run=True)
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "import_rows_too_many"


def test_more_than_the_byte_bound_is_rejected(client, unit_id, coordinator):
    rows = [{"note": "x" * (2 * 1024 * 1024 + 1)}]
    response = _post_import(
        client, unit_id, coordinator, key="too-many-bytes", body=_rows_body(rows, dry_run=True)
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_body_too_large"


def test_no_job_is_created_for_a_rejected_row_submission(client, engine, unit_id, coordinator):
    """A 400 from the bounds check must not queue anything (ADR-0015's other half).

    Quota is still charged (asserted elsewhere for the route's existing
    refusals); what this pins is that a body-shape refusal, like a 404 or 403,
    creates no job and no outbox row.
    """
    rows = [{"i": i} for i in range(5_001)]
    _post_import(
        client, unit_id, coordinator, key="rejected-no-job", body=_rows_body(rows, dry_run=True)
    )

    with engine.connect() as conn:
        jobs = conn.execute(text("SELECT count(*) FROM job")).scalar_one()
    assert jobs == 0


# ---------------------------------------------------------------------------
# Re-drive idempotence, at the layer that implements it
# ---------------------------------------------------------------------------


def test_create_batch_with_items_is_idempotent_under_replay(
    engine, session_factory, tenant_id, unit_id
):
    """A second execution of the same job must not double-insert.

    Simulates the scenario a re-drive produces: the handler is executed twice
    for the *same job id* with the *same rows* (a re-drive replays the
    identical persisted payload — see ``smartmatch_persistence.redrive``). This
    calls the repository directly, at the layer where idempotence is actually
    implemented (deterministic batch id + ``ON CONFLICT DO NOTHING`` on both
    tables — see ``review.py``'s module docstring), rather than driving the
    full state machine through a failure and a re-drive to reach the same call.
    """
    job_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO job (id, tenant_id, command_type, status, owning_unit_id) "
                "VALUES (:id, :tid, 'import.create', 'queued', :unit_id)"
            ),
            {"id": job_id, "tid": tenant_id, "unit_id": unit_id},
        )

    rows = [{"full_name": "A. Rivera"}, {"full_name": "B. Osei"}]
    reviews = ReviewRepository()

    with session_factory() as session:
        first = reviews.create_batch_with_items(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            job_id=job_id,
            dataset="professionals",
            rows=rows,
        )
        session.commit()

    with session_factory() as session:
        second = reviews.create_batch_with_items(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            job_id=job_id,
            dataset="professionals",
            rows=rows,
        )
        session.commit()

    assert second.id == first.id, "a replay must derive the same batch id"
    assert second.review_item_count == 2, "a replay must not double the review items"

    with engine.connect() as conn:
        batches = conn.execute(
            text("SELECT count(*) FROM import_batch WHERE job_id = :jid"), {"jid": job_id}
        ).scalar_one()
        items = conn.execute(
            text("SELECT count(*) FROM review_item WHERE import_batch_id = :bid"),
            {"bid": first.id},
        ).scalar_one()
    assert batches == 1
    assert items == 2


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


def test_a_review_item_cannot_reference_a_batch_in_another_tenant(engine, tenant_id, unit_id):
    """The composite ``(tenant_id, import_batch_id)`` foreign key, asserted as the write it refuses.

    A single-column ``review_item.import_batch_id -> import_batch.id`` would
    have permitted a review item in one tenant naming a batch in another —
    after which a coordinator's review view for tenant A could be made to read
    tenant B's imported rows by an operator who could name the id. This proves
    the composite key, not merely that a name-only schema comparison agrees
    with the migration.
    """
    other_tenant = uuid.uuid4()
    job_id = uuid.uuid4()
    batch_id = uuid.uuid4()

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :slug, :slug)"),
            {"id": other_tenant, "slug": f"other-{other_tenant.hex[:12]}"},
        )
        other_unit = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO org_unit (id, tenant_id, path, unit_type, display_name) "
                "VALUES (:id, :tid, CAST('elsewhere.rows' AS ltree), 'department', 'Elsewhere')"
            ),
            {"id": other_unit, "tid": other_tenant},
        )
        conn.execute(
            text(
                "INSERT INTO job (id, tenant_id, command_type, status, owning_unit_id) "
                "VALUES (:id, :tid, 'import.create', 'queued', :unit_id)"
            ),
            {"id": job_id, "tid": other_tenant, "unit_id": other_unit},
        )
        conn.execute(
            text(
                "INSERT INTO import_batch "
                "(id, tenant_id, owning_unit_id, job_id, dataset, row_count, dry_run) "
                "VALUES (:id, :tid, :unit_id, :job_id, 'professionals', 0, false)"
            ),
            {"id": batch_id, "tid": other_tenant, "unit_id": other_unit, "job_id": job_id},
        )

    try:
        with pytest.raises(IntegrityError) as raised, engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO review_item "
                    "(id, tenant_id, import_batch_id, row_index, row_data) "
                    "VALUES (:id, :tid, :batch_id, 0, '{}'::jsonb)"
                ),
                # tenant_id names the *caller's* tenant; import_batch_id names a
                # batch that belongs to other_tenant. Neither column alone is
                # wrong — the composite pairing is.
                {"id": uuid.uuid4(), "tid": tenant_id, "batch_id": batch_id},
            )
        assert "foreign key" in str(raised.value).lower(), (
            f"the insert was refused by something other than the composite key: {raised.value}"
        )
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM review_item WHERE tenant_id = :t"), {"t": other_tenant})
            conn.execute(text("DELETE FROM import_batch WHERE tenant_id = :t"), {"t": other_tenant})
            conn.execute(text("DELETE FROM job WHERE tenant_id = :t"), {"t": other_tenant})
            conn.execute(text("DELETE FROM org_unit WHERE tenant_id = :t"), {"t": other_tenant})
            conn.execute(text("DELETE FROM tenant WHERE id = :t"), {"t": other_tenant})
