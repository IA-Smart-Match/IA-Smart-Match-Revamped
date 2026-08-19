"""Re-drive: the authorized, audited command that restarts parked work.

Cloud Tasks has no native dead-letter queue (architecture v1.1 §1.6), so work
that fails terminally parks in ``redrive_record`` and is restarted by an
explicit command rather than by a retry loop. These tests exercise that command
against a real database, a real dispatcher, and the fixture task queue.

## The one that matters

:func:`test_a_redriven_job_actually_runs_again` is the load-bearing test, and it
is deliberately not satisfied by a ``202`` or by a row appearing in a table.
ADR-0007 records why: ``derive_task_name`` is a pure function of
``(job_id, command_type)``, so a job re-driven under its original identifiers
derives *the same task name its own failed attempt already used*. That fails
twice over —

1. ``uq_outbox_task_name`` is global, so PostgreSQL refuses the second outbox
   row before Cloud Tasks is ever consulted; and
2. even past the database, the queue rejects a duplicate name, and the
   dispatcher treats ``TaskAlreadyExists`` as *success* — so the row would be
   marked ``dispatched``, the job would advance, and the work would never run.

The second failure is the dangerous one, because it is silent: an audit trail
saying the job was re-driven, and nothing executed. So the test asserts the
whole chain — a fresh dispatchable outbox row, a dispatcher pass that reports
``dispatched`` rather than ``already_existed``, and a second, distinct task in
the queue.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_domain.jobs import JobState
from smartmatch_persistence.engine import create_session_factory
from smartmatch_persistence.jobs import JobRepository
from smartmatch_persistence.outbox import OutboxRepository, OutboxStatus, derive_task_name
from smartmatch_providers import FixtureTokenVerifier
from smartmatch_providers.tasks import FixtureTaskQueue
from smartmatch_worker.dispatcher import OutboxDispatcher
from sqlalchemy import text

pytestmark = pytest.mark.integration

UNIT_PATH = "iawest.cpp.engineering.ie"
COMMAND = "import.create"


# ---------------------------------------------------------------------------
# Fixtures — the same wiring test_command_path uses, plus a dispatcher
# ---------------------------------------------------------------------------


@pytest.fixture
def jobs() -> JobRepository:
    return JobRepository()


@pytest.fixture
def outbox() -> OutboxRepository:
    return OutboxRepository()


@pytest.fixture
def queue() -> FixtureTaskQueue:
    return FixtureTaskQueue()


@pytest.fixture
def dispatcher(session_factory, queue) -> OutboxDispatcher:
    return OutboxDispatcher(session_factory, queue)


@pytest.fixture
def client(engine) -> TestClient:
    """A client wired to the test database and a fixture token verifier."""
    verifier = FixtureTokenVerifier()

    test_client = TestClient(app)
    test_client.app.state.session_factory = create_session_factory(
        engine.url.render_as_string(hide_password=False)
    )
    test_client.app.state.token_verifier = verifier
    test_client.verifier = verifier  # type: ignore[attr-defined]
    return test_client


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


def _grant(engine, tenant_id, user_id, *, path: str = "iawest", role: str = "coordinator") -> None:
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


def _register(
    client, engine, tenant_id, *, subject: str, role: str, suspended: bool = False
) -> str:
    """Create an account with one membership and return its bearer token."""
    user_id = _make_user(engine, tenant_id, subject=subject, suspended=suspended)
    _grant(engine, tenant_id, user_id, role=role)
    token = f"tok-{subject}"
    client.verifier.register(token, subject)
    return token


@pytest.fixture
def coordinator(client, engine, tenant_id) -> str:
    return _register(client, engine, tenant_id, subject="sub-coordinator", role="coordinator")


# ---------------------------------------------------------------------------
# Helpers that put a job into the state re-drive exists for
# ---------------------------------------------------------------------------


def _accept_command(session_factory, jobs, outbox, tenant_id, *, actor_id=None) -> uuid.UUID:
    """Accept a command the way the API does: job and outbox in one transaction."""
    with session_factory() as session:
        job = jobs.create(session, tenant_id=tenant_id, command_type=COMMAND, actor_id=actor_id)
        outbox.enqueue(session, tenant_id=tenant_id, job_id=job.id, command_type=COMMAND)
        session.commit()
    return job.id


def _fail_terminally(
    session_factory, jobs, tenant_id, job_id, *, to_state=JobState.FAILED_PROVIDER
) -> None:
    """Walk the job through a real attempt that ends in terminal failure."""
    with session_factory() as session:
        jobs.transition(
            session,
            tenant_id=tenant_id,
            job_id=job_id,
            to_state=JobState.RUNNING,
            expected_from=JobState.DISPATCHED,
        )
        jobs.transition(
            session,
            tenant_id=tenant_id,
            job_id=job_id,
            to_state=to_state,
            expected_from=JobState.RUNNING,
        )
        session.commit()


def _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher, **kwargs) -> uuid.UUID:
    """A job that was accepted, dispatched, ran, and failed terminally."""
    job_id = _accept_command(session_factory, jobs, outbox, tenant_id, **kwargs)
    dispatcher.run_once()
    _fail_terminally(session_factory, jobs, tenant_id, job_id)
    return job_id


def _post_redrive(client, job_id, token, *, key: str, reason: str = "Provider outage resolved."):
    return client.post(
        f"/v1/jobs/{job_id}/redrive",
        json={"reason": reason},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
    )


def _post_abandon(client, job_id, token, *, key: str, reason: str = "Source data withdrawn."):
    return client.post(
        f"/v1/jobs/{job_id}/abandon",
        json={"reason": reason},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
    )


def _outbox_rows(session_factory, job_id) -> list:
    with session_factory() as session:
        return session.execute(
            text(
                "SELECT task_name, status, dispatch_attempts FROM outbox_record "
                "WHERE job_id = :job_id ORDER BY created_at, task_name"
            ),
            {"job_id": job_id},
        ).all()


def _redrive_rows(session_factory, job_id) -> list:
    with session_factory() as session:
        return session.execute(
            text(
                "SELECT id, attempt_history, parked_at, redriven_at, redriven_by, "
                "redrive_reason FROM redrive_record WHERE job_id = :job_id "
                "ORDER BY parked_at, id"
            ),
            {"job_id": job_id},
        ).all()


def _job_status(session_factory, jobs, tenant_id, job_id) -> JobState:
    with session_factory() as session:
        return jobs.get(session, tenant_id=tenant_id, job_id=job_id).status


# ---------------------------------------------------------------------------
# The load-bearing test
# ---------------------------------------------------------------------------


def test_a_redriven_job_actually_runs_again(
    client, coordinator, session_factory, jobs, outbox, tenant_id, dispatcher, queue
):
    """A re-driven job must reach the queue a second time, as new work.

    Every weaker assertion passes on a broken implementation. ``202`` passes
    when nothing was written; "a redrive_record exists" passes when the outbox
    row was never created; "an outbox row exists" passes when the dispatcher
    silently discards it as a duplicate of the job's own failed attempt. So the
    chain is asserted end to end.
    """
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)
    assert len(queue.enqueued) == 1
    original_task = queue.enqueued[0].name

    response = _post_redrive(client, job_id, coordinator, key="redrive-1")

    assert response.status_code == 202, response.text
    assert response.json()["job_id"] == str(job_id)
    assert response.json()["replayed"] is False

    # The job is queued again, and a *second* outbox row exists, pending, with a
    # task name distinct from the one the failed attempt used. A shared name is
    # the ADR-0007 collision: PostgreSQL would have refused this row.
    assert _job_status(session_factory, jobs, tenant_id, job_id) is JobState.QUEUED

    rows = _outbox_rows(session_factory, job_id)
    assert len(rows) == 2, "the re-drive must produce a new dispatchable outbox row"
    names = {row.task_name for row in rows}
    assert len(names) == 2, "the re-drive's task name must differ from the failed attempt's"
    assert original_task in names

    pending = [row for row in rows if row.status == OutboxStatus.PENDING.value]
    assert len(pending) == 1
    assert pending[0].dispatch_attempts == 0

    # And the dispatcher genuinely enqueues it. `already_existed` here would be
    # the silent failure: the row marked dispatched, the job advanced, the work
    # never run.
    outcome = dispatcher.run_once()

    assert outcome.dispatched == 1, "the re-driven work must be enqueued, not deduplicated away"
    assert outcome.already_existed == 0
    assert len(queue.enqueued) == 2, "the queue must hold the original task and the re-drive"
    assert queue.enqueued[1].name != original_task
    assert queue.enqueued[1].payload == {"tenant_id": str(tenant_id), "job_id": str(job_id)}

    assert _job_status(session_factory, jobs, tenant_id, job_id) is JobState.DISPATCHED


def test_task_names_differ_across_generations_but_are_stable_within_one():
    """Determinism *within* an attempt is what makes crash recovery safe.

    ADR-0007's whole argument rests on a retried dispatch deriving the name the
    first attempt used. Varying the name per re-drive generation must not cost
    that: the same generation always derives the same name, and only a
    deliberate new generation differs.
    """
    job_id = uuid.uuid4()

    assert derive_task_name(job_id, COMMAND) == derive_task_name(job_id, COMMAND)
    assert derive_task_name(job_id, COMMAND, redrive_generation=0) == derive_task_name(
        job_id, COMMAND
    ), "generation 0 is the original attempt; its name must be unchanged"

    first = derive_task_name(job_id, COMMAND, redrive_generation=1)
    assert first == derive_task_name(job_id, COMMAND, redrive_generation=1)
    assert first != derive_task_name(job_id, COMMAND)
    assert first != derive_task_name(job_id, COMMAND, redrive_generation=2)

    # The name still leaks nothing, which is why it is a hash at all.
    assert str(job_id) not in first
    assert "import" not in first

    with pytest.raises(ValueError):
        derive_task_name(job_id, COMMAND, redrive_generation=-1)


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


def test_a_job_in_a_non_redrivable_state_is_rejected(
    client, coordinator, session_factory, jobs, outbox, tenant_id, dispatcher, queue
):
    """Only the states the domain routes into ``redrive_pending`` may re-drive.

    A succeeded job is the dangerous case: re-driving it would re-run work that
    already had its effects.
    """
    job_id = _accept_command(session_factory, jobs, outbox, tenant_id)
    dispatcher.run_once()
    _fail_terminally(session_factory, jobs, tenant_id, job_id, to_state=JobState.SUCCEEDED)

    response = _post_redrive(client, job_id, coordinator, key="redrive-succeeded")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state_transition"
    assert _job_status(session_factory, jobs, tenant_id, job_id) is JobState.SUCCEEDED
    assert len(_outbox_rows(session_factory, job_id)) == 1
    assert len(queue.enqueued) == 1


def test_a_timed_out_job_may_be_redriven(
    client, coordinator, session_factory, jobs, outbox, tenant_id, dispatcher
):
    """``timed_out -> redrive_pending`` is declared, so it must work."""
    job_id = _accept_command(session_factory, jobs, outbox, tenant_id)
    dispatcher.run_once()
    _fail_terminally(session_factory, jobs, tenant_id, job_id, to_state=JobState.TIMED_OUT)

    assert _post_redrive(client, job_id, coordinator, key="redrive-timeout").status_code == 202
    assert _job_status(session_factory, jobs, tenant_id, job_id) is JobState.QUEUED


def test_redrive_requires_a_recorded_reason(
    client, coordinator, session_factory, jobs, outbox, tenant_id, dispatcher
):
    """An unexplained re-drive is not auditable, so it is not accepted."""
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)

    missing = client.post(
        f"/v1/jobs/{job_id}/redrive",
        json={},
        headers={"Authorization": f"Bearer {coordinator}", "Idempotency-Key": "no-reason"},
    )
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "invalid_request"

    blank = _post_redrive(client, job_id, coordinator, key="blank-reason", reason="   ")
    assert blank.status_code == 400
    assert blank.json()["error"]["code"] == "redrive_reason_required"

    assert _job_status(session_factory, jobs, tenant_id, job_id) is JobState.FAILED_PROVIDER


def test_redrive_requires_an_idempotency_key(
    client, coordinator, session_factory, jobs, outbox, tenant_id, dispatcher
):
    """A command that re-runs consequential work must be safely retryable."""
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)

    response = client.post(
        f"/v1/jobs/{job_id}/redrive",
        json={"reason": "Provider outage resolved."},
        headers={"Authorization": f"Bearer {coordinator}"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "idempotency_key_required"


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def test_the_redrive_record_names_the_actor_and_the_reason(
    client, coordinator, engine, session_factory, jobs, outbox, tenant_id, dispatcher
):
    """Who re-drove it, when, and why — all three, or it is not an audit trail."""
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)

    _post_redrive(client, job_id, coordinator, key="audited", reason="Vendor confirmed fix.")

    rows = _redrive_rows(session_factory, job_id)
    assert len(rows) == 1
    record = rows[0]

    assert record.redriven_at is not None
    assert record.redriven_by is not None
    assert record.redrive_reason == "Vendor confirmed fix."
    assert record.parked_at <= record.redriven_at

    with engine.connect() as conn:
        subject = conn.execute(
            text("SELECT external_subject FROM user_account WHERE id = :uid"),
            {"uid": record.redriven_by},
        ).scalar_one()
    assert subject == "sub-coordinator"


def test_attempt_history_survives_a_second_redrive(
    client, coordinator, session_factory, jobs, outbox, tenant_id, dispatcher, queue
):
    """History accumulates. The point of parking is seeing *how often* and *why*.

    A second failure must not overwrite the first re-drive's record: an operator
    deciding whether to re-drive a third time needs to know this job has already
    burned two attempts, and on what.
    """
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)

    assert (
        _post_redrive(client, job_id, coordinator, key="cycle-1", reason="First try.").status_code
        == 202
    )
    dispatcher.run_once()
    _fail_terminally(session_factory, jobs, tenant_id, job_id)

    first_after_one = _redrive_rows(session_factory, job_id)
    assert len(first_after_one) == 1

    assert (
        _post_redrive(client, job_id, coordinator, key="cycle-2", reason="Second try.").status_code
        == 202
    )
    dispatcher.run_once()

    rows = _redrive_rows(session_factory, job_id)
    assert len(rows) == 2, "each parking is its own audit record"

    # The first record is untouched: same id, same reason, same history.
    assert rows[0].id == first_after_one[0].id
    assert rows[0].redrive_reason == "First try."
    assert rows[0].attempt_history == first_after_one[0].attempt_history
    assert rows[1].redrive_reason == "Second try."

    # The second park saw the failed generation-1 attempt, so its history is
    # strictly richer than the first's.
    assert len(rows[1].attempt_history) > len(rows[0].attempt_history)
    events = [entry["event"] for entry in rows[1].attempt_history]
    assert events.count("attempt") == 2, "both attempts are recorded, not just the latest"
    assert "redriven" in events, "the earlier re-drive is part of the history"

    # Three distinct tasks: original, first re-drive, second re-drive.
    assert len({task.name for task in queue.enqueued}) == 3
    assert len(_outbox_rows(session_factory, job_id)) == 3


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def test_an_unauthorized_principal_is_denied(
    client, engine, session_factory, jobs, outbox, tenant_id, dispatcher
):
    """Tenant membership is not authority to re-run failed work."""
    viewer = _register(client, engine, tenant_id, subject="sub-viewer", role="viewer")
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)

    response = _post_redrive(client, job_id, viewer, key="viewer-redrive")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert response.json()["error"]["details"]["reason"] == "no_grant"
    assert _job_status(session_factory, jobs, tenant_id, job_id) is JobState.FAILED_PROVIDER
    assert len(_outbox_rows(session_factory, job_id)) == 1


def test_a_resource_grant_alone_does_not_authorize_a_redrive(
    client, engine, session_factory, jobs, outbox, tenant_id, dispatcher
):
    """A grant conveys access to a resource, not authority over it.

    Mirrors ``smartmatch_authz.policy``: a bare ``resource_grant`` cannot satisfy
    a role-gated operation, and the distinct reason code keeps the open
    policy-matrix gap visible rather than silent.
    """
    guest = _register(client, engine, tenant_id, subject="sub-guest", role="viewer")
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)

    with engine.begin() as conn:
        user_id = conn.execute(
            text("SELECT id FROM user_account WHERE external_subject = 'sub-guest'")
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO resource_grant "
                "(id, tenant_id, user_id, resource_type, resource_id, effect) "
                "VALUES (:id, :tid, :uid, 'job', :rid, 'allow')"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "uid": user_id, "rid": job_id},
        )

    response = _post_redrive(client, job_id, guest, key="grant-only")

    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "resource_grant_lacks_required_role"


def test_an_explicit_deny_beats_the_role(
    client, engine, session_factory, jobs, outbox, tenant_id, dispatcher
):
    """A resource-level deny is how an administrator carves out an exception."""
    token = _register(client, engine, tenant_id, subject="sub-denied", role="coordinator")
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)

    with engine.begin() as conn:
        user_id = conn.execute(
            text("SELECT id FROM user_account WHERE external_subject = 'sub-denied'")
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO resource_grant "
                "(id, tenant_id, user_id, resource_type, resource_id, effect) "
                "VALUES (:id, :tid, :uid, 'job', :rid, 'deny')"
            ),
            {"id": uuid.uuid4(), "tid": tenant_id, "uid": user_id, "rid": job_id},
        )

    response = _post_redrive(client, job_id, token, key="denied")

    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "explicit_resource_deny"


def test_a_suspended_principal_is_denied(
    client, engine, session_factory, jobs, outbox, tenant_id, dispatcher
):
    """Suspension is enforced locally and first, not by waiting for the IdP."""
    suspended = _register(
        client, engine, tenant_id, subject="sub-suspended", role="admin", suspended=True
    )
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)

    response = _post_redrive(client, job_id, suspended, key="suspended-redrive")

    assert response.status_code == 403
    assert response.json()["error"]["details"]["reason"] == "principal_suspended"
    assert _job_status(session_factory, jobs, tenant_id, job_id) is JobState.FAILED_PROVIDER


def test_another_tenants_job_is_not_found(
    client, engine, session_factory, jobs, outbox, tenant_id, dispatcher
):
    """A job in another tenant is indistinguishable from one that does not exist."""
    other_tenant = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO tenant (id, slug, display_name) VALUES (:id, :s, :s)"),
            {"id": other_tenant, "s": f"other-{other_tenant.hex[:10]}"},
        )
    try:
        job_id = _a_failed_job(session_factory, jobs, outbox, other_tenant, dispatcher)
        token = _register(client, engine, tenant_id, subject="sub-outsider", role="admin")

        response = _post_redrive(client, job_id, token, key="cross-tenant")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "job_not_found"
        assert _job_status(session_factory, jobs, other_tenant, job_id) is JobState.FAILED_PROVIDER
    finally:
        with engine.begin() as conn:
            for table in ("job_event", "outbox_record", "redrive_record", "job"):
                conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :t"), {"t": other_tenant})
            conn.execute(text("DELETE FROM tenant WHERE id = :t"), {"t": other_tenant})


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_a_duplicate_redrive_does_not_double_run(
    client, coordinator, session_factory, jobs, outbox, tenant_id, dispatcher, queue
):
    """A retried re-drive is a replay, not a second run."""
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)

    first = _post_redrive(client, job_id, coordinator, key="same-key")
    second = _post_redrive(client, job_id, coordinator, key="same-key")

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["replayed"] is False
    assert second.json()["replayed"] is True
    assert second.json()["job_id"] == str(job_id)

    assert len(_outbox_rows(session_factory, job_id)) == 2, "exactly one new dispatch"
    assert len(_redrive_rows(session_factory, job_id)) == 1

    dispatcher.run_once()
    assert len(queue.enqueued) == 2


def test_a_key_reused_for_a_different_reason_is_a_conflict(
    client, coordinator, session_factory, jobs, outbox, tenant_id, dispatcher
):
    """A replayed key with a different body is a client bug, not a retry.

    Answering with the earlier decision would silently discard the new one — and
    the reason is the audited part, so quietly keeping the wrong one is exactly
    the failure the audit trail exists to prevent.
    """
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)

    assert _post_redrive(client, job_id, coordinator, key="reused", reason="A.").status_code == 202
    response = _post_redrive(client, job_id, coordinator, key="reused", reason="B.")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_key_reused"
    assert len(_outbox_rows(session_factory, job_id)) == 2


def test_two_coordinators_racing_produce_one_run(
    client, engine, coordinator, session_factory, jobs, outbox, tenant_id, dispatcher, queue
):
    """Different keys, same intent. The compare-and-set transition arbitrates.

    Idempotency keys cannot help here — two people clicking a button generate two
    different keys — so the guard has to be the job's own state. The loser sees
    the job already re-driven and is refused rather than queuing a second run.
    """
    other = _register(client, engine, tenant_id, subject="sub-coordinator-2", role="coordinator")
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)

    first = _post_redrive(client, job_id, coordinator, key="click-a")
    second = _post_redrive(client, job_id, other, key="click-b")

    assert first.status_code == 202
    assert second.status_code == 409, second.text

    assert len(_outbox_rows(session_factory, job_id)) == 2
    dispatcher.run_once()
    assert len(queue.enqueued) == 2, "the work must be queued once, not twice"


# ---------------------------------------------------------------------------
# Abandon
# ---------------------------------------------------------------------------


def test_abandon_stops_showing_a_hopeless_job(
    client, coordinator, session_factory, jobs, outbox, tenant_id, dispatcher, queue
):
    """``redrive_pending -> abandoned`` exists so an operator can close the loop."""
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)

    response = _post_abandon(client, job_id, coordinator, key="abandon-1")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == JobState.ABANDONED.value
    assert _job_status(session_factory, jobs, tenant_id, job_id) is JobState.ABANDONED

    # Nothing new was queued, and the decision is on the record.
    assert len(_outbox_rows(session_factory, job_id)) == 1
    assert len(queue.enqueued) == 1

    rows = _redrive_rows(session_factory, job_id)
    assert len(rows) == 1
    events = [entry["event"] for entry in rows[0].attempt_history]
    assert "abandoned" in events
    abandoned = next(e for e in rows[0].attempt_history if e["event"] == "abandoned")
    assert abandoned["reason"] == "Source data withdrawn."
    assert abandoned["actor_id"] is not None
    # Abandoning is not re-driving; the re-drive columns stay empty.
    assert rows[0].redriven_at is None


def test_an_abandoned_job_cannot_be_redriven(
    client, coordinator, session_factory, jobs, outbox, tenant_id, dispatcher
):
    """``abandoned`` is terminal. That is the whole point of saying it."""
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)
    assert _post_abandon(client, job_id, coordinator, key="abandon-2").status_code == 200

    response = _post_redrive(client, job_id, coordinator, key="redrive-abandoned")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state_transition"
    assert len(_outbox_rows(session_factory, job_id)) == 1


def test_abandon_requires_authorization(
    client, engine, session_factory, jobs, outbox, tenant_id, dispatcher
):
    """Closing work permanently is at least as privileged as re-running it."""
    viewer = _register(client, engine, tenant_id, subject="sub-viewer-2", role="viewer")
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)

    response = _post_abandon(client, job_id, viewer, key="viewer-abandon")

    assert response.status_code == 403
    assert _job_status(session_factory, jobs, tenant_id, job_id) is JobState.FAILED_PROVIDER


def test_attempt_history_does_not_duplicate_across_three_cycles(
    client, coordinator, session_factory, jobs, outbox, tenant_id, dispatcher, queue
):
    """Three cycles, because two do not reach the defect.

    Each audit record is seeded with the decisions carried from the one before
    it, so the latest record already holds the whole narrative. Seeding from
    *every* record instead re-adds each earlier decision once per record that
    already carried it. With two parkings the totals still look plausible; by
    the third the first parking appears twice and the column has grown
    super-linearly, which is exactly the shape that makes an audit trail stop
    being evidence.
    """
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)

    sizes: list[int] = []
    for cycle in range(3):
        response = _post_redrive(client, job_id, coordinator, key=f"cycle-{cycle}")
        assert response.status_code == 202, response.text
        dispatcher.run_once()
        _fail_terminally(session_factory, jobs, tenant_id, job_id)

        # The newest record is the one an operator reads: it is seeded with
        # everything carried forward, so it must be the whole narrative told
        # once. Earlier records legitimately repeat their own predecessors —
        # that is what carrying forward means — so they are not the subject.
        latest = _redrive_rows(session_factory, job_id)[-1]
        entries = list(latest.attempt_history)
        sizes.append(len(entries))

        decisions = [
            (entry.get("event"), entry.get("at"), entry.get("reason"))
            for entry in entries
            if entry.get("event") != "attempt"
        ]
        assert len(decisions) == len(set(decisions)), (
            f"cycle {cycle}: the newest audit record repeats a decision — {decisions}"
        )

    growth = [sizes[i + 1] - sizes[i] for i in range(len(sizes) - 1)]
    assert growth[0] == growth[-1], (
        f"the audit record must grow by a fixed amount per cycle, saw sizes {sizes}"
    )


def test_a_replayed_redrive_reports_the_generation_it_replays(
    client, coordinator, session_factory, jobs, outbox, tenant_id, dispatcher
):
    """A replay answers identically — including the generation.

    Omitting it fell back to the field default of ``0``, which the schema
    documents as the original submission. So a replayed re-drive described
    itself as the one thing it demonstrably was not, and a client reconciling
    generations against the event stream would read it as a different dispatch.
    """
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)

    first = _post_redrive(client, job_id, coordinator, key="same-key")
    assert first.status_code == 202, first.text
    assert first.json()["replayed"] is False
    generation = first.json()["generation"]
    assert generation >= 1

    replay = _post_redrive(client, job_id, coordinator, key="same-key")

    assert replay.status_code == 202, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["generation"] == generation, (
        "a replay must report the generation it replays, not the default 0"
    )


def test_a_rejected_redrive_still_consumes_quota(
    client, coordinator, session_factory, jobs, outbox, tenant_id, engine
):
    """Rejection is not free.

    The rate-limit increment is still uncommitted when the conflict propagates,
    and the request-scoped session rolls it back — so a caller hammering a job
    that cannot be re-driven paid nothing at all. This is the hole closed for
    idempotency conflicts as security finding S-008; a command rejected still
    consumed the capacity used to reject it.
    """
    # A job that never failed cannot be re-driven.
    job_id = _accept_command(session_factory, jobs, outbox, tenant_id)

    def _consumed() -> int:
        with engine.begin() as conn:
            return (
                conn.execute(
                    text(
                        "SELECT coalesce(sum(count), 0) FROM rate_limit_counter "
                        "WHERE tenant_id = :tid"
                    ),
                    {"tid": tenant_id},
                ).scalar_one()
                or 0
            )

    before = _consumed()
    response = _post_redrive(client, job_id, coordinator, key="rejected-1")
    assert response.status_code == 409, response.text

    assert _consumed() > before, "a rejected re-drive must still cost quota"
