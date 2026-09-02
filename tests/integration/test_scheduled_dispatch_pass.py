"""The scheduled dispatcher pass and the endpoint that drives it (J8).

``run_once`` and ``lag`` existed long before J8; what J8 added is the thing that
calls them on a timer, the J9 sweep beside them, and the heartbeat an operator's
"the schedule stopped firing" alert is built from. The handoff
(``docs/plans/pr1-blockers-handoff.md`` §2.2) found none of it tested: the
dispatcher module's lease assertions are all about ``outbox_record``, and no
test touched ``ScheduledPass``, the sweep's place in it, or either
``/operations/dispatch`` route.

Three properties carry the item, and each is here because getting it wrong is
silent:

* **Order.** Sweep, then dispatch, then measure. The sweep is first for the
  reason J8's own backlog row gives about the reclaim, turned on J9: a database
  refusing claims is the same database whose workers are dying mid-job, so a
  sweep placed after the dispatch would never run in exactly the incident that
  needs it (``docs/plans/transaction-boundary-defects.md`` §3.3).
* **What may abort a pass.** Only a failed claim. The sweep and the lag read are
  janitorial and observational; neither may cost a healthy row its dispatch, and
  a guarded failure is reported in the outcome rather than turned into a zero.
* **What the heartbeat means.** ``last_completed`` and the log line move only on
  a pass that finished. A heartbeat that ticked on failure would report a
  dispatcher which dispatches nothing as healthy — the exact condition the alert
  exists to catch.

The endpoint tests run against a **real** :class:`OidcTaskVerifier` carrying the
scheduler's own audience and allowlist, using the signature stand-in
``test_worker_execution`` documents. Removing the verifier would prove nothing
about the control that keeps Cloud Tasks credentials from driving dispatch.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from conftest import ensure_owning_unit
from fastapi.testclient import TestClient
from smartmatch_domain.jobs import JobState
from smartmatch_persistence.jobs import JobRepository
from smartmatch_persistence.outbox import MAX_DISPATCH_ATTEMPTS, OutboxRepository
from smartmatch_providers.tasks import FixtureTaskQueue
from smartmatch_worker.dispatcher import (
    DispatcherLag,
    DispatchOutcome,
    OutboxDispatcher,
    ScheduledPass,
)
from smartmatch_worker.execution import StalledJobSweeper
from smartmatch_worker.identity import JsonWebKey, OidcTaskVerifier, StaticJwksSource
from smartmatch_worker.main import create_app
from sqlalchemy import text
from test_worker_execution import StandInSignatureVerifier

pytestmark = pytest.mark.integration

COMMAND = "test.scheduled"

ISSUER = "https://accounts.google.com"
KID = "test-signing-key"
SIGNING_MATERIAL = "only-the-legitimate-signer-holds-this"

#: The scheduler's own audience and account. Deliberately **not** the queue's:
#: the two callers are kept apart all the way down, and a test that reused the
#: queue's credentials here would assert the opposite of the property.
SCHEDULER_AUDIENCE = "https://worker.smartmatch.invalid/operations/dispatch"
SCHEDULER_ACCOUNT = "scheduler@smartmatch-test.iam.gserviceaccount.com"
TASK_AUDIENCE = "https://worker.smartmatch.invalid/tasks/execute"
TASK_ACCOUNT = "tasks-dispatcher@smartmatch-test.iam.gserviceaccount.com"


# ---------------------------------------------------------------------------
# Identity: a real verifier, a real token, one stand-in primitive
# ---------------------------------------------------------------------------


def _segment(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _json_segment(value: dict[str, Any]) -> str:
    return _segment(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def mint_token(*, audience: str = SCHEDULER_AUDIENCE, email: str = SCHEDULER_ACCOUNT) -> str:
    """Mint the token Cloud Scheduler would present, or a near miss."""
    now = int(datetime.now(UTC).timestamp())
    header = {"alg": "RS256", "kid": KID, "typ": "JWT"}
    claims = {
        "iss": ISSUER,
        "aud": audience,
        "sub": "114857392847362718293",
        "email": email,
        "email_verified": True,
        "iat": now,
        "exp": now + 600,
    }
    signing_input = f"{_json_segment(header)}.{_json_segment(claims)}"
    signature = hmac.new(
        SIGNING_MATERIAL.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{signing_input}.{_segment(signature)}"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def scheduler_verifier() -> OidcTaskVerifier:
    return OidcTaskVerifier(
        expected_audience=SCHEDULER_AUDIENCE,
        allowed_service_accounts=frozenset({SCHEDULER_ACCOUNT}),
        jwks=StaticJwksSource(
            keys={KID: JsonWebKey(kid=KID, alg="RS256", material={"k": SIGNING_MATERIAL})}
        ),
        signature_verifier=StandInSignatureVerifier(),
        accepted_issuers=frozenset({ISSUER}),
    )


# ---------------------------------------------------------------------------
# Fixtures and helpers
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
def client(session_factory, scheduler_verifier, queue) -> TestClient:
    """A worker whose scheduler identity, sessions, and task queue are injected."""
    return TestClient(
        create_app(
            session_factory=session_factory,
            scheduler_verifier=scheduler_verifier,
            task_queue=queue,
        )
    )


def accept_command(session_factory, jobs, outbox, tenant_id) -> uuid.UUID:
    """Accept a command the way the API does: job and outbox in one transaction."""
    with session_factory() as session:
        job = jobs.create(
            session,
            tenant_id=tenant_id,
            command_type=COMMAND,
            owning_unit_id=ensure_owning_unit(session, tenant_id),
        )
        outbox.enqueue(session, tenant_id=tenant_id, job_id=job.id, command_type=COMMAND)
        session.commit()
    return job.id


def stalled_job(session_factory, jobs, tenant_id) -> uuid.UUID:
    """A job left ``running`` with a deadline an hour in the past.

    What a killed worker leaves behind, written directly rather than by killing
    something: the claim committed, the terminal transition never did.
    """
    with session_factory() as session:
        job = jobs.create(
            session,
            tenant_id=tenant_id,
            command_type=COMMAND,
            owning_unit_id=ensure_owning_unit(session, tenant_id),
        )
        jobs.transition(
            session,
            tenant_id=tenant_id,
            job_id=job.id,
            to_state=JobState.DISPATCHED,
            expected_from=JobState.QUEUED,
        )
        jobs.claim(session, tenant_id=tenant_id, job_id=job.id, lease=timedelta(minutes=10))
        session.execute(
            text("UPDATE job SET lease_expires_at = :past WHERE id = :job_id"),
            {"past": datetime.now(UTC) - timedelta(hours=1), "job_id": job.id},
        )
        session.commit()
    return job.id


def strand_outbox_row(session_factory, outbox, tenant_id) -> None:
    """Spend a row's whole attempt budget while ``leased``, recording nothing.

    The condition ``reclaim_stranded`` exists for, reached the way it is reached
    in production — a dispatcher that never comes back — and the only source of
    a non-zero ``reclaimed`` a test can produce honestly.
    """
    for _ in range(MAX_DISPATCH_ATTEMPTS):
        expire_outbox_leases(session_factory, tenant_id)
        with session_factory() as session:
            outbox.claim_batch(session, limit=10)
            session.commit()
    expire_outbox_leases(session_factory, tenant_id)


def expire_outbox_leases(session_factory, tenant_id: uuid.UUID) -> None:
    with session_factory() as session:
        session.execute(
            text("UPDATE outbox_record SET lease_expires_at = :past WHERE tenant_id = :tid"),
            {"past": datetime.now(UTC) - timedelta(hours=1), "tid": tenant_id},
        )
        session.commit()


def job_status(session_factory, jobs, tenant_id, job_id) -> JobState:
    with session_factory() as session:
        record = jobs.get(session, tenant_id=tenant_id, job_id=job_id)
        assert record is not None
        return record.status


@dataclass
class Recorder:
    """Notes the order collaborators were called in, and delegates unchanged.

    A proxy rather than a double: the pass runs against the real dispatcher and
    the real sweeper, on real rows, and this only writes down when each was
    reached. A stubbed pair would let the order assertion pass over code that
    never touched the database.
    """

    calls: list[str] = field(default_factory=list)


@dataclass
class RecordingSweeper:
    inner: StalledJobSweeper
    recorder: Recorder
    fail_with: Exception | None = None

    def sweep(self) -> int:
        self.recorder.calls.append("sweep")
        if self.fail_with is not None:
            raise self.fail_with
        return self.inner.sweep()


@dataclass
class RecordingDispatcher:
    inner: OutboxDispatcher
    recorder: Recorder
    fail_claim_with: Exception | None = None

    def run_once(self, *, batch_size: int = 20) -> DispatchOutcome:
        self.recorder.calls.append("dispatch")
        if self.fail_claim_with is not None:
            raise self.fail_claim_with
        return self.inner.run_once(batch_size=batch_size)

    def lag(self) -> DispatcherLag:
        self.recorder.calls.append("lag")
        return self.inner.lag()


def build_pass(
    session_factory,
    queue,
    *,
    recorder: Recorder,
    sweep_failure: Exception | None = None,
    claim_failure: Exception | None = None,
) -> ScheduledPass:
    return ScheduledPass(
        RecordingDispatcher(
            OutboxDispatcher(session_factory, queue), recorder, fail_claim_with=claim_failure
        ),
        RecordingSweeper(StalledJobSweeper(session_factory), recorder, fail_with=sweep_failure),
    )


# ---------------------------------------------------------------------------
# The pass itself
# ---------------------------------------------------------------------------


def test_a_pass_sweeps_then_dispatches_then_measures_lag(
    session_factory, jobs, outbox, tenant_id, queue
):
    """The order is the design, so it is asserted as an order and not inferred.

    Both halves do real work in this pass — one stalled job to rescue, one
    pending row to dispatch — so the recorded sequence is a statement about a
    pass that accomplished something, not about three calls into empty tables.
    """
    stalled = stalled_job(session_factory, jobs, tenant_id)
    pending = accept_command(session_factory, jobs, outbox, tenant_id)
    recorder = Recorder()

    outcome = build_pass(session_factory, queue, recorder=recorder).run()

    assert recorder.calls == ["sweep", "dispatch", "lag"], (
        "the sweep goes first: a database refusing claims is the same database "
        "whose workers are dying mid-job, and a sweep after the dispatch would "
        "never run in that incident"
    )
    assert outcome.timed_out == 1
    assert outcome.sweep_failed is False
    assert outcome.dispatch.dispatched == 1
    assert len(queue.enqueued) == 1
    assert outcome.lag is not None, "a lag of zero pending rows is not the same as no reading"

    assert job_status(session_factory, jobs, tenant_id, stalled) is JobState.TIMED_OUT
    assert job_status(session_factory, jobs, tenant_id, pending) is JobState.DISPATCHED
    assert outcome.finished_at >= outcome.ran_at
    assert outcome.duration >= timedelta(0)


def test_a_failing_sweep_does_not_cost_a_healthy_row_its_dispatch(
    session_factory, jobs, outbox, tenant_id, queue
):
    """Janitorial work must never abort the work of the day.

    And the zero it leaves behind is reported as unmeasured rather than as
    nothing-to-do: ``sweep_failed`` is beside the count precisely because a
    ``timed_out`` of zero would otherwise read as a healthy fleet.
    """
    stalled = stalled_job(session_factory, jobs, tenant_id)
    pending = accept_command(session_factory, jobs, outbox, tenant_id)
    recorder = Recorder()

    outcome = build_pass(
        session_factory,
        queue,
        recorder=recorder,
        sweep_failure=RuntimeError("the sweep deadlocked"),
    ).run()

    assert outcome.sweep_failed is True
    assert outcome.timed_out == 0, "a failed sweep rescued nothing, and says so"
    assert outcome.dispatch.dispatched == 1, "the dispatch must survive a failed sweep"
    assert len(queue.enqueued) == 1
    assert recorder.calls == ["sweep", "dispatch", "lag"]

    assert job_status(session_factory, jobs, tenant_id, stalled) is JobState.RUNNING, (
        "the stalled job stays running until a later pass sweeps it"
    )
    assert job_status(session_factory, jobs, tenant_id, pending) is JobState.DISPATCHED


def test_a_failing_claim_aborts_the_pass_and_keeps_the_sweep_that_committed(
    session_factory, jobs, tenant_id, queue
):
    """The one failure that aborts a pass, and what must survive it.

    The claim propagates — ``run_once``'s rule, inherited unchanged. But the
    sweep committed before it, and those jobs are rescued whatever happened
    next; losing that count here would erase the signal exactly when a database
    is under enough strain to fail a claim, which is when it is most
    informative. The pass carries it out on the exception as a note.
    """
    stalled = stalled_job(session_factory, jobs, tenant_id)
    recorder = Recorder()
    scheduled = build_pass(
        session_factory,
        queue,
        recorder=recorder,
        claim_failure=RuntimeError("the claim could not be committed"),
    )

    with pytest.raises(RuntimeError, match="the claim could not be committed") as raised:
        scheduled.run()

    assert recorder.calls == ["sweep", "dispatch"], "the lag read is never reached"
    assert job_status(session_factory, jobs, tenant_id, stalled) is JobState.TIMED_OUT, (
        "the sweep committed on its own, and a failed dispatch does not undo it"
    )
    assert any("timed out and committed" in note for note in raised.value.__notes__), (
        "the rescued count must travel out with the exception, not vanish with it"
    )
    assert scheduled.last_completed is None, (
        "a heartbeat that ticked on failure would report a dispatcher which "
        "dispatches nothing as healthy"
    )


def test_rescued_is_the_reclaimed_rows_plus_the_timed_out_jobs(
    session_factory, jobs, outbox, tenant_id, queue
):
    """One number for work that had to be rescued, split two ways for diagnosis.

    ``§3.3`` asked the pass for a single surface an operator can alert on, and
    the two halves for the operator who then has to decide which table to open.
    Both are produced here by real recoveries — a stranded outbox row whose
    attempts were spent while ``leased``, and a job whose worker never came back
    — because a sum asserted over two zeros would hold against arithmetic that
    counted neither.
    """
    stalled = stalled_job(session_factory, jobs, tenant_id)
    accept_command(session_factory, jobs, outbox, tenant_id)
    strand_outbox_row(session_factory, outbox, tenant_id)
    recorder = Recorder()

    outcome = build_pass(session_factory, queue, recorder=recorder).run()

    assert outcome.dispatch.reclaimed == 1, "a stranded row is a real signal and must be countable"
    assert outcome.timed_out == 1
    assert outcome.rescued == outcome.dispatch.reclaimed + outcome.timed_out
    assert outcome.rescued == 2
    assert job_status(session_factory, jobs, tenant_id, stalled) is JobState.TIMED_OUT


def test_the_heartbeat_moves_only_on_a_pass_that_finished(
    session_factory, jobs, outbox, tenant_id, queue
):
    """``last_completed`` is the signal, and it is written at the end for a reason."""
    accept_command(session_factory, jobs, outbox, tenant_id)
    recorder = Recorder()
    scheduled = build_pass(session_factory, queue, recorder=recorder)

    assert scheduled.last_completed is None, "nothing has run yet"

    outcome = scheduled.run()

    assert scheduled.last_completed is outcome
    assert scheduled.last_completed.dispatch.dispatched == 1


# ---------------------------------------------------------------------------
# The endpoint Cloud Scheduler calls
# ---------------------------------------------------------------------------


def test_the_dispatch_endpoint_runs_a_pass_for_a_verified_scheduler(
    client, session_factory, jobs, outbox, tenant_id, queue
):
    """``POST /operations/dispatch`` is what makes any of this run on a timer.

    Asserted through the route rather than by calling ``ScheduledPass`` again:
    the endpoint is the only thing Cloud Scheduler can reach, and a pass nothing
    calls is J8 unclosed however well the class behaves.
    """
    stalled = stalled_job(session_factory, jobs, tenant_id)
    pending = accept_command(session_factory, jobs, outbox, tenant_id)

    response = client.post("/operations/dispatch", headers=auth(mint_token()))

    assert response.status_code == 200
    body = response.json()
    assert body["dispatched"] == 1
    assert body["timed_out"] == 1
    assert body["rescued"] == 1, "the reclaim was zero, so rescued is the sweep alone"
    assert body["sweep_failed"] is False
    assert body["pending"] == 0, "the row it just dispatched is no longer claimable"
    assert len(queue.enqueued) == 1

    assert job_status(session_factory, jobs, tenant_id, stalled) is JobState.TIMED_OUT
    assert job_status(session_factory, jobs, tenant_id, pending) is JobState.DISPATCHED


def test_the_dispatch_endpoint_refuses_a_caller_holding_only_queue_credentials(
    client, session_factory, jobs, outbox, tenant_id, queue
):
    """The two callers are kept apart, and this is where that is decided.

    A token that is validly signed, unexpired, and minted by a real Google
    account is still not a scheduler credential. If ``/operations/dispatch``
    fell back to the task audience or the task allowlist, a deployment that
    configured only the queue would accept queue-minted tokens on the endpoint
    that drives dispatch — which is the whole reason the verifier is separate.
    """
    accept_command(session_factory, jobs, outbox, tenant_id)

    anonymous = client.post("/operations/dispatch")
    assert anonymous.status_code == 401

    queue_credential = client.post(
        "/operations/dispatch",
        headers=auth(mint_token(audience=TASK_AUDIENCE, email=TASK_ACCOUNT)),
    )
    assert queue_credential.status_code == 403

    wrong_account = client.post(
        "/operations/dispatch",
        headers=auth(mint_token(email="someone-else@smartmatch-test.iam.gserviceaccount.com")),
    )
    assert wrong_account.status_code == 403

    assert queue.enqueued == [], "no refused call may have dispatched anything"


def test_the_heartbeat_endpoint_reports_this_instance_last_completed_pass(
    client, session_factory, jobs, outbox, tenant_id
):
    """``GET /operations/dispatch`` answers "did this instance run a pass, and when".

    Before any pass it must say ``configured`` with a ``null`` reading — a
    deployment that has never dispatched, which is a different fact from a
    deployment that cannot. After one, it must carry that pass's numbers, which
    is what makes it a heartbeat rather than a liveness probe.
    """
    before = client.get("/operations/dispatch")
    assert before.status_code == 200
    assert before.json() == {"configured": True, "last_completed": None}

    accept_command(session_factory, jobs, outbox, tenant_id)
    ran = client.post("/operations/dispatch", headers=auth(mint_token())).json()

    after = client.get("/operations/dispatch").json()
    assert after["configured"] is True
    assert after["last_completed"] is not None
    assert after["last_completed"]["ran_at"] == ran["ran_at"]
    assert after["last_completed"]["finished_at"] == ran["finished_at"]
    assert after["last_completed"]["dispatched"] == 1


def test_a_deployment_with_no_task_queue_reports_unconfigured_and_refuses_to_claim(
    session_factory, scheduler_verifier, jobs, outbox, tenant_id
):
    """No queue means no pass, and the refusal is the correct behaviour.

    A pass that claimed rows it could not enqueue would burn an attempt off
    every one of them for a reason that will not change until someone redeploys,
    so the endpoint answers ``501`` and the heartbeat says ``configured: false``
    rather than reporting a dispatcher that has simply never run.
    """
    client = TestClient(
        create_app(session_factory=session_factory, scheduler_verifier=scheduler_verifier)
    )
    job_id = accept_command(session_factory, jobs, outbox, tenant_id)

    refused = client.post("/operations/dispatch", headers=auth(mint_token()))
    assert refused.status_code == 501

    assert client.get("/operations/dispatch").json() == {
        "configured": False,
        "last_completed": None,
    }
    assert job_status(session_factory, jobs, tenant_id, job_id) is JobState.QUEUED, (
        "a refused pass must not have spent the row's attempts"
    )
