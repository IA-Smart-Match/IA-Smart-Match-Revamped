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

import logging
import threading
import time
import uuid

import pytest
from conftest import unique_subject
from fastapi.testclient import TestClient
from smartmatch_api.main import app
from smartmatch_domain.jobs import JobState
from smartmatch_persistence.engine import create_session_factory
from smartmatch_persistence.jobs import JobRepository
from smartmatch_persistence.outbox import OutboxRepository, OutboxStatus, derive_task_name
from smartmatch_persistence.redrive import RedriveRepository
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
    return _register(
        client, engine, tenant_id, subject=unique_subject("sub-coordinator"), role="coordinator"
    )


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
    assert subject == unique_subject("sub-coordinator")


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
    viewer = _register(
        client, engine, tenant_id, subject=unique_subject("sub-viewer"), role="viewer"
    )
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
    guest = _register(client, engine, tenant_id, subject=unique_subject("sub-guest"), role="viewer")
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)

    with engine.begin() as conn:
        user_id = conn.execute(
            text("SELECT id FROM user_account WHERE external_subject = :sub"),
            {"sub": unique_subject("sub-guest")},
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
    token = _register(
        client, engine, tenant_id, subject=unique_subject("sub-denied"), role="coordinator"
    )
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)

    with engine.begin() as conn:
        user_id = conn.execute(
            text("SELECT id FROM user_account WHERE external_subject = :sub"),
            {"sub": unique_subject("sub-denied")},
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
        client,
        engine,
        tenant_id,
        subject=unique_subject("sub-suspended"),
        role="admin",
        suspended=True,
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
        token = _register(
            client, engine, tenant_id, subject=unique_subject("sub-outsider"), role="admin"
        )

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
    client, coordinator, session_factory, jobs, outbox, tenant_id, dispatcher, engine
):
    """A replayed key with a different body is a client bug, not a retry.

    Answering with the earlier decision would silently discard the new one — and
    the reason is the audited part, so quietly keeping the wrong one is exactly
    the failure the audit trail exists to prevent.

    The quota assertion guards S-008 on this specific path. ``_reserve`` used to
    commit the transaction itself before letting the conflict propagate, purely
    so the rate-limit increment stuck; that commit is gone and the savepoint in
    the handler carries the property instead. Nothing else in the suite would
    notice if it stopped being carried, and an unbounded stream of conflicting
    requests costing nothing is precisely the traffic a limiter exists to bound.
    """
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)

    assert _post_redrive(client, job_id, coordinator, key="reused", reason="A.").status_code == 202
    before = _quota_consumed(engine, tenant_id)
    response = _post_redrive(client, job_id, coordinator, key="reused", reason="B.")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_key_reused"
    assert len(_outbox_rows(session_factory, job_id)) == 2
    assert _quota_consumed(engine, tenant_id) > before, (
        "a key-reuse conflict is a rejection, and a rejection still costs quota"
    )


def test_two_coordinators_racing_produce_one_run(
    client, engine, coordinator, session_factory, jobs, outbox, tenant_id, dispatcher, queue
):
    """Different keys, same intent. The compare-and-set transition arbitrates.

    Idempotency keys cannot help here — two people clicking a button generate two
    different keys — so the guard has to be the job's own state. The loser sees
    the job already re-driven and is refused rather than queuing a second run.
    """
    other = _register(
        client, engine, tenant_id, subject=unique_subject("sub-coordinator-2"), role="coordinator"
    )
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
    viewer = _register(
        client, engine, tenant_id, subject=unique_subject("sub-viewer-2"), role="viewer"
    )
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


def _quota_consumed(engine, tenant_id) -> int:
    """Total rate-limit units this tenant has spent.

    Both re-drive routes share the ``job.redrive`` bucket, so this is the whole
    picture for either of them.
    """
    with engine.begin() as conn:
        return (
            conn.execute(
                text(
                    "SELECT coalesce(sum(count), 0) FROM rate_limit_counter WHERE tenant_id = :tid"
                ),
                {"tid": tenant_id},
            ).scalar_one()
            or 0
        )


def _idempotency_keys(session_factory, tenant_id, command_type: str) -> list[str]:
    with session_factory() as session:
        return [
            row[0]
            for row in session.execute(
                text(
                    "SELECT idempotency_key FROM idempotency_record "
                    "WHERE tenant_id = :tid AND command_type = :ct ORDER BY idempotency_key"
                ),
                {"tid": tenant_id, "ct": command_type},
            )
        ]


def _a_running_job(session_factory, jobs, outbox, tenant_id, dispatcher) -> uuid.UUID:
    """A job the worker is still executing: accepted, dispatched, running.

    ``running`` has no declared path to ``abandoned``, so this is the state that
    produces the worst sentence the poisoned-key defect can produce — a caller
    told the job is closed permanently while it is in fact still executing.
    """
    job_id = _accept_command(session_factory, jobs, outbox, tenant_id)
    dispatcher.run_once()
    with session_factory() as session:
        jobs.transition(
            session,
            tenant_id=tenant_id,
            job_id=job_id,
            to_state=JobState.RUNNING,
            expected_from=JobState.DISPATCHED,
        )
        session.commit()
    return job_id


def test_a_refused_redrive_does_not_consume_its_idempotency_key(
    client, coordinator, session_factory, jobs, outbox, tenant_id, dispatcher, engine
):
    """A refusal must leave the key free, and must still cost quota.

    A key names *accepted* work. Holding the reservation past a 409 meant the
    retry — the one thing an idempotency key exists to make safe — found the
    reservation and answered ``202 {"replayed": true}`` for a command that was
    refused and never ran. The first request told the truth and every retry
    lied, which inverts the contract and is exactly what a client library does
    automatically.

    Both halves are asserted here on purpose. The reservation must go and the
    quota must stay, and the savepoint boundary is the only thing separating
    them: open it one line too early, around ``enforce_rate_limit``, and the
    quota half regresses silently while this test's first assertions still pass.
    """
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)

    closed = _post_abandon(client, job_id, coordinator, key="close")
    assert closed.status_code == 200, closed.text

    before = _quota_consumed(engine, tenant_id)

    first = _post_redrive(client, job_id, coordinator, key="K")
    assert first.status_code == 409, first.text
    assert first.json()["error"]["code"] == "invalid_state_transition", first.text
    after_first = _quota_consumed(engine, tenant_id)
    assert after_first > before, "a refused re-drive must still cost quota"

    retry = _post_redrive(client, job_id, coordinator, key="K")

    assert retry.status_code == 409, (
        f"a retry of a refused command must be refused again, not replayed: {retry.text}"
    )
    assert retry.json()["error"]["code"] == "invalid_state_transition", retry.text
    assert _quota_consumed(engine, tenant_id) > after_first, (
        "the retry is a fresh attempt and costs quota too"
    )

    assert _job_status(session_factory, jobs, tenant_id, job_id) == JobState.ABANDONED
    assert len(_outbox_rows(session_factory, job_id)) == 1, "no re-drive means no new outbox row"
    assert "K" not in _idempotency_keys(session_factory, tenant_id, "job.redrive"), (
        "a refused command must leave its key free for a later, legitimate attempt"
    )


def test_a_refused_abandon_does_not_report_the_job_abandoned(
    client, coordinator, session_factory, jobs, outbox, tenant_id, dispatcher
):
    """The sharpest instance: a running job reported closed while it still runs.

    ``running`` has no declared transition to ``abandoned``, so the first request
    is correctly refused. The retry then found the surviving reservation and
    answered ``200 {"status": "abandoned"}`` — while the worker was still
    executing the job and with no ``redrive_record`` written, so the durable
    audit trail says nothing happened and the only artifact claiming otherwise
    is an HTTP response nobody keeps.
    """
    job_id = _a_running_job(session_factory, jobs, outbox, tenant_id, dispatcher)

    first = _post_abandon(client, job_id, coordinator, key="K2")
    assert first.status_code == 409, first.text

    retry = _post_abandon(client, job_id, coordinator, key="K2")

    assert retry.status_code == 409, (
        f"a refused abandon must not report the job abandoned on retry: {retry.text}"
    )
    assert _job_status(session_factory, jobs, tenant_id, job_id) == JobState.RUNNING
    assert _redrive_rows(session_factory, job_id) == [], "a refused abandon parks nothing"
    assert "K2" not in _idempotency_keys(session_factory, tenant_id, "job.abandon")


def _wait_until_blocked_by(engine, blocker_pid: int, *, timeout: float = 10.0) -> None:
    """Block until some backend is waiting on a lock held by ``blocker_pid``.

    This is the handoff that makes the race test deterministic rather than
    timing-dependent. Sleeping a fixed interval and hoping the other thread got
    far enough is how a race test becomes a flaky test; PostgreSQL reports the
    wait directly through ``pg_blocking_pids``, so the test observes the exact
    interleaving it needs.

    Naming the blocker matters as much as waiting at all. "Is anything blocked?"
    would also answer yes to an unrelated backend, hand control back too early,
    and produce a test that passes for the wrong reason — which is the failure
    mode a race test is most likely to have and least likely to show.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with engine.begin() as conn:
            waiting = conn.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() "
                    "AND :blocker = ANY(pg_blocking_pids(pid))"
                ),
                {"blocker": blocker_pid},
            ).scalar_one()
        if waiting:
            return
        time.sleep(0.01)
    raise AssertionError(
        f"no backend ever blocked on the lock held by pid {blocker_pid}; the race did not set up"
    )


def test_a_redrive_that_loses_the_parking_race_leaves_no_stray_audit_record(
    client, coordinator, session_factory, jobs, outbox, tenant_id, dispatcher, engine
):
    """A lost compare-and-set must undo the record the attempt already wrote.

    This is the one path where deleting the idempotency reservation would not
    have been enough. ``_open_parking`` has a third branch: a job sitting in
    ``redrive_pending`` with no open audit record — the worker owns that
    transition and does not know this table exists — is *backfilled* a record
    before the ``redrive_pending -> queued`` compare-and-set is attempted. If
    that set then loses, the attempt has already written a ``redrive_record``,
    and a fix aimed only at the reservation would commit it: a durable audit row
    for a re-drive that was refused and never happened.

    Reached with two genuinely concurrent transactions and no fault injection.
    A rival re-drive moves the job out of ``redrive_pending`` and holds the row
    lock uncommitted; the request under test reads the still-committed
    ``redrive_pending``, backfills its record, and blocks on the rival's lock.
    Committing the rival releases it, PostgreSQL re-evaluates the ``WHERE``
    against the new committed row, matches nothing, and the conflict is raised
    where the plan says it is raised.
    """
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)

    # The state _open_parking backfills for: parked, with no audit record.
    with session_factory() as session:
        jobs.transition(
            session,
            tenant_id=tenant_id,
            job_id=job_id,
            to_state=JobState.REDRIVE_PENDING,
            expected_from=JobState.FAILED_PROVIDER,
        )
        session.commit()
    assert _redrive_rows(session_factory, job_id) == [], "setup: no record to reuse"

    result: dict[str, object] = {}
    failure: list[Exception] = []

    def _redrive_under_the_rival() -> None:
        # Anything raised here would otherwise die in the worker thread, leaving
        # the main thread to fail on a missing ``result`` key and report a
        # ``KeyError`` in place of the actual cause. Carried across and re-raised
        # below instead: a test this fiddly must not be able to lie about why it
        # failed.
        try:
            result["response"] = _post_redrive(client, job_id, coordinator, key="race")
        except Exception as exc:  # re-raised in the main thread, below
            failure.append(exc)

    contender = threading.Thread(target=_redrive_under_the_rival, daemon=True)

    # A rival coordinator's re-drive, committed only once we are wedged behind it.
    rival = session_factory()
    try:
        rival_pid = rival.execute(text("SELECT pg_backend_pid()")).scalar_one()
        assert jobs.transition(
            rival,
            tenant_id=tenant_id,
            job_id=job_id,
            to_state=JobState.QUEUED,
            expected_from=JobState.REDRIVE_PENDING,
        ), "setup: the rival must win the compare-and-set it is here to win"
        contender.start()
        _wait_until_blocked_by(engine, rival_pid)
        rival.commit()
    finally:
        # Before the join, never after: the contender is blocked on this
        # session's row lock, so joining first would wait on a thread waiting on
        # us. Closing here also covers the setup assertion above failing, which
        # would otherwise leak an open session on the session-scoped engine.
        rival.close()

    contender.join(timeout=15)
    assert not contender.is_alive(), "the blocked request never completed"
    if failure:
        raise AssertionError("the re-drive request raised instead of answering") from failure[0]

    response = result["response"]
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "redrive_conflict", response.text

    assert _redrive_rows(session_factory, job_id) == [], (
        "the backfilled audit record belonged to a re-drive that was refused; "
        "rolling back only the reservation would have left it committed"
    )
    assert "race" not in _idempotency_keys(session_factory, tenant_id, "job.redrive")


# ---------------------------------------------------------------------------
# J14 — a replay reports the generation *its own key* created
# ---------------------------------------------------------------------------


def test_a_replayed_redrive_reports_its_own_generation_not_the_latest(
    client, coordinator, session_factory, jobs, outbox, tenant_id, dispatcher
):
    """The J14 sequence, verbatim from the backlog.

    K1 re-drives and gets generation 1. The job fails again. K2 re-drives and
    gets generation 2. A retry of **K1** must still answer 1 — it is a replay of
    the command that created generation 1, and saying 2 tells the caller their
    re-drive was a dispatch it demonstrably was not.

    Before the fix the replay branch called ``current_generation``, which
    returns the job's *latest* dispatch rather than the one the replayed key
    created, so the retry answered ``{"replayed": true, "generation": 2}``. The
    sequence is ordinary rather than adversarial: two re-drives of one job under
    different keys, and a client library retrying the first.
    """
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)

    first = _post_redrive(client, job_id, coordinator, key="K1", reason="First try.")
    assert first.status_code == 202
    assert first.json()["generation"] == 1
    dispatcher.run_once()
    _fail_terminally(session_factory, jobs, tenant_id, job_id)

    second = _post_redrive(client, job_id, coordinator, key="K2", reason="Second try.")
    assert second.status_code == 202
    assert second.json()["generation"] == 2
    dispatcher.run_once()

    replayed = _post_redrive(client, job_id, coordinator, key="K1", reason="First try.")
    assert replayed.status_code == 202
    body = replayed.json()
    assert body["replayed"] is True, "K1 has been used; this is a replay"
    assert body["generation"] == 1, (
        "a replay of K1 must report the generation K1 created, not the job's "
        f"latest dispatch. Got {body['generation']}."
    )
    assert body["job_id"] == str(job_id), "a replay returns the same job"


def test_a_replayed_redrive_is_answered_identically_every_time(
    client, coordinator, session_factory, jobs, outbox, tenant_id, dispatcher
):
    """Idempotency means the *same* answer, not merely a successful one.

    Two retries of one key, either side of another key's re-drive, must be byte
    for byte the same response. This is the property J14 broke: the answer moved
    depending on what had happened to the job in between.
    """
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)

    _post_redrive(client, job_id, coordinator, key="K1", reason="First try.")
    before = _post_redrive(client, job_id, coordinator, key="K1", reason="First try.")

    dispatcher.run_once()
    _fail_terminally(session_factory, jobs, tenant_id, job_id)
    _post_redrive(client, job_id, coordinator, key="K2", reason="Second try.")
    dispatcher.run_once()

    after = _post_redrive(client, job_id, coordinator, key="K1", reason="First try.")
    # Raw bytes, not parsed JSON. Comparing `.json()` compares decoded objects,
    # so two different serialisations of the same object would pass a test whose
    # docstring promises byte equality. Say what is meant, then assert it.
    assert before.content == after.content, (
        "a replay's answer must not depend on what happened to the job after it"
    )
    assert before.json() == after.json(), "and the decoded bodies agree too"


def test_the_generation_is_recorded_on_the_reservation_that_produced_it(
    client, coordinator, session_factory, jobs, outbox, tenant_id, dispatcher
):
    """The column is written, and written per key rather than per job.

    Reading the rows directly, because the route's answer alone cannot show
    *where* the generation came from — and the whole defect was that it came
    from the wrong place.
    """
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)

    _post_redrive(client, job_id, coordinator, key="K1", reason="First try.")
    dispatcher.run_once()
    _fail_terminally(session_factory, jobs, tenant_id, job_id)
    _post_redrive(client, job_id, coordinator, key="K2", reason="Second try.")

    with session_factory() as session:
        rows = session.execute(
            text(
                "SELECT idempotency_key, result_generation FROM idempotency_record "
                "WHERE tenant_id = :tid AND command_type = 'job.redrive' "
                "ORDER BY idempotency_key"
            ),
            {"tid": tenant_id},
        ).all()

    assert [(row.idempotency_key, row.result_generation) for row in rows] == [
        ("K1", 1),
        ("K2", 2),
    ], "each key records the generation its own command produced"


def test_a_reservation_with_no_recorded_generation_falls_back_and_is_wrong(
    client, coordinator, session_factory, jobs, outbox, tenant_id, dispatcher, caplog
):
    """The legacy-key fallback, and the exact cost of the trade it makes.

    A reservation written before migration ``0004``, or by an instance running
    pre-J14 code, has ``result_generation`` NULL — simulated here by clearing
    it. Refusing would turn those replays into 500s on the privileged route, so
    the replay falls back to ``current_generation`` and warns.

    This is **permanent for those keys**, not a window that closes: nothing
    repairs a legacy row and nothing expires one, so such a key answers this way
    for as long as it exists.

    This asserts the fallback returns the **wrong** answer, not the right one.
    That is the point: a test that set up a single re-drive would assert
    ``generation == 1``, which is what the fallback computes anyway, and would
    pass whether or not the fallback existed. Here two re-drives make the
    fallback observably diverge from the truth — K1 created generation 1, the
    fallback reports 2 — so the test measures the window's cost rather than
    asserting around it.

    If the fallback is ever removed in favour of refusing, this test should
    change to expect the refusal. It is pinning a deliberate compromise, not a
    desirable behaviour.
    """
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)

    assert _post_redrive(client, job_id, coordinator, key="K1", reason="First.").status_code == 202
    dispatcher.run_once()
    _fail_terminally(session_factory, jobs, tenant_id, job_id)
    assert _post_redrive(client, job_id, coordinator, key="K2", reason="Second.").status_code == 202
    dispatcher.run_once()

    with session_factory() as session:
        session.execute(
            text(
                "UPDATE idempotency_record SET result_generation = NULL "
                "WHERE tenant_id = :tid AND idempotency_key = 'K1'"
            ),
            {"tid": tenant_id},
        )
        session.commit()

    with caplog.at_level(logging.WARNING, logger="smartmatch_api.routers.redrive"):
        replayed = _post_redrive(client, job_id, coordinator, key="K1", reason="First.")

    assert replayed.status_code == 202, "the fallback must not turn a replay into a 500"
    body = replayed.json()
    assert body["replayed"] is True
    assert body["generation"] == 2, (
        "with no recorded generation the replay falls back to the job's latest "
        "dispatch — which is J14's wrong answer. This asserts the known cost of "
        "the fallback, not correct behaviour."
    )

    # The warning is the only thing that makes a silently-wrong answer visible,
    # so it is part of the behaviour rather than decoration. Without this the
    # test passed just as happily with the logging removed.
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, "a fallback answer that nobody is told about is the defect again"
    assert any("no recorded generation" in r.getMessage() for r in warnings), (
        "expected a warning naming the missing generation, got: "
        f"{[r.getMessage() for r in warnings]}"
    )


def test_an_abandon_records_no_generation(
    client, coordinator, session_factory, jobs, outbox, tenant_id, dispatcher
):
    """`job.abandon` has no generation, and its reservation must not invent one.

    ``AbandonedResponse`` carries the job id and the status and nothing else, so
    a NULL here is correct and permanent rather than a gap waiting to be filled.
    """
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)

    assert (
        _post_abandon(client, job_id, coordinator, key="A1", reason="Hopeless.").status_code == 200
    )

    with session_factory() as session:
        rows = session.execute(
            text(
                "SELECT result_generation FROM idempotency_record "
                "WHERE tenant_id = :tid AND command_type = 'job.abandon'"
            ),
            {"tid": tenant_id},
        ).all()

    assert [row.result_generation for row in rows] == [None]


# ---------------------------------------------------------------------------
# J15 — a 500 must not refund the quota that produced it
# ---------------------------------------------------------------------------


@pytest.fixture
def failing_client(client) -> TestClient:
    """The same wiring, but rendering an unhandled exception as the caller's 500.

    ``TestClient`` re-raises server exceptions by default, which is right for
    every other test in this module and exactly wrong for these three. J15 is a
    statement about what survives in the database *after* the route 500s, so the
    request has to finish the way it finishes in production — through the error
    middleware, with the dependency teardown running and ``get_session``'s
    unconditional rollback firing — rather than being unwound by the harness
    before any of that happens.

    Depends on ``client`` rather than rebuilding the wiring: the app is a module
    singleton, so this shares that fixture's session factory and its registered
    tokens, and taking it as an argument makes the ordering explicit instead of
    accidental.
    """
    return TestClient(app, raise_server_exceptions=False)


def _explode(*args, **kwargs):
    """Stand in for a repository call failing in a way the handler never named.

    ``RuntimeError`` on purpose: it is outside the three-exception tuple the
    handlers catch, which is the whole condition J15 describes. Any unhandled
    type would do — a driver error, a bug in a repository, an ``AttributeError``
    after a refactor — and the point is that the set of them cannot be
    enumerated in advance, which is why the fix is a broad ``except`` rather
    than a fourth entry in the tuple.
    """
    raise RuntimeError("the command failed in a way nobody anticipated")


def test_an_unhandled_error_in_a_redrive_still_costs_quota(
    failing_client,
    coordinator,
    session_factory,
    jobs,
    outbox,
    tenant_id,
    dispatcher,
    engine,
    monkeypatch,
):
    """A 500 is not a refund.

    Reproduced the way the backlog row reproduced it: make ``_redrive.redrive``
    raise ``RuntimeError``. The savepoint then stayed open, ``session.commit()``
    never ran, and ``get_session``'s unconditional ``finally:
    session.rollback()`` discarded the rate-limit increment along with
    everything the command had written — measured at quota ``0`` before and
    ``0`` after.

    That reopens S-008 through a repeatable 500: a caller who can reliably
    provoke an unhandled error pays no quota for it, on the route rate-limited
    most tightly *because* it is a privileged decision. The 500 itself is a
    defect to be fixed on its own terms; what is asserted here is that it costs
    the caller what it charged them.
    """
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)
    monkeypatch.setattr(RedriveRepository, "redrive", _explode)

    before = _quota_consumed(engine, tenant_id)

    response = _post_redrive(failing_client, job_id, coordinator, key="boom")

    assert response.status_code == 500, (
        f"the error must still reach the caller as a 500, not be swallowed: {response.text}"
    )
    assert _quota_consumed(engine, tenant_id) == before + 1, (
        "an unhandled error must not refund the quota the request already spent"
    )


def test_an_unhandled_error_in_an_abandon_still_costs_quota(
    failing_client,
    coordinator,
    session_factory,
    jobs,
    outbox,
    tenant_id,
    dispatcher,
    engine,
    monkeypatch,
):
    """``abandon_job`` had the identical shape, so it gets the identical test.

    Both routes share the ``job.redrive`` bucket, so this measures the same
    counter — and a fix applied to only one handler would leave the other
    refunding, which is the failure this test exists to catch.
    """
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)
    monkeypatch.setattr(RedriveRepository, "abandon", _explode)

    before = _quota_consumed(engine, tenant_id)

    response = _post_abandon(failing_client, job_id, coordinator, key="boom-abandon")

    assert response.status_code == 500, response.text
    assert _quota_consumed(engine, tenant_id) == before + 1, (
        "an unhandled error in abandon must not refund the quota either"
    )
    assert _job_status(session_factory, jobs, tenant_id, job_id) == JobState.FAILED_PROVIDER


def test_an_unhandled_error_keeps_the_quota_and_none_of_the_commands_writes(
    failing_client,
    coordinator,
    session_factory,
    jobs,
    outbox,
    tenant_id,
    dispatcher,
    engine,
    monkeypatch,
):
    """The other half, and the reason the fix is a savepoint rollback and a commit.

    The two tests above fail before the command writes anything, so on their own
    they would pass against a fix that simply committed on the way out — and
    that fix would persist a half-performed re-drive, which is worse than the
    refund it cured. So here the *real* ``redrive`` runs to completion first —
    parking the job, moving it ``failed_provider -> redrive_pending -> queued``,
    writing the ``redrive_record``, enqueuing a fresh outbox row — and only then
    raises. Everything it wrote is inside the savepoint; the quota is outside
    it. Exactly one of those may survive.

    The reservation is the sharpest of the assertions: ``_reserve`` genuinely
    wrote that row earlier in the same request, so its absence is evidence the
    savepoint rolled back rather than evidence nothing was ever attempted.
    """
    job_id = _a_failed_job(session_factory, jobs, outbox, tenant_id, dispatcher)

    real_redrive = RedriveRepository.redrive

    def _write_everything_then_explode(self, session, **kwargs):
        real_redrive(self, session, **kwargs)
        raise RuntimeError("the command failed after writing every row it writes")

    monkeypatch.setattr(RedriveRepository, "redrive", _write_everything_then_explode)

    before = _quota_consumed(engine, tenant_id)

    response = _post_redrive(failing_client, job_id, coordinator, key="half-written")

    assert response.status_code == 500, response.text
    assert _quota_consumed(engine, tenant_id) == before + 1, "the quota is outside the savepoint"

    assert _job_status(session_factory, jobs, tenant_id, job_id) == JobState.FAILED_PROVIDER, (
        "a discarded command must not leave the job queued for work that will never run"
    )
    assert _redrive_rows(session_factory, job_id) == [], (
        "an audit record for a re-drive that did not happen is worse than none"
    )
    assert len(_outbox_rows(session_factory, job_id)) == 1, (
        "the failed attempt's row and nothing else; a committed outbox row here "
        "would dispatch work no audit trail authorized"
    )
    assert "half-written" not in _idempotency_keys(session_factory, tenant_id, "job.redrive"), (
        "the reservation was written and must go with the command, or the key "
        "would replay a 500 as a success forever"
    )
