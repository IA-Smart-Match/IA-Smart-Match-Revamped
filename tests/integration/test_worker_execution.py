"""Worker execution and task-identity integration tests.

The dispatcher creates Cloud Tasks entries; these tests are what proves anything
consumes them. Two properties dominate, and both are asserted against a live
PostgreSQL instance rather than a double, because both are enforced by the
database:

* **A duplicate delivery does not execute twice.** Cloud Tasks guarantees
  at-least-once delivery, so the second delivery is not an anomaly — it is the
  normal case the design must survive. The conditional ``dispatched -> running``
  claim is the whole guard, and a test that stubbed the repository would assert
  nothing about it.
* **No failure leaves a job in ``running``.** A job stuck in ``running`` with no
  worker behind it is invisible work: the SSE stream shows progress that will
  never arrive, and no operations view lists it as needing attention.

The identity tests mint real JWTs and feed them through the real verifier. What
they cannot do is verify a real RSA signature: the hash-pinned dependency lock
carries no asymmetric primitive (see ``smartmatch_worker.identity``), so the
signature step — and only that step — runs against the stand-in below. Every
check around it is production code: the algorithm ban, the header/key algorithm
agreement, the key lookup, and every claim check.
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
import smartmatch_worker.handlers as handler_module
import smartmatch_worker.main as worker_main
from conftest import ensure_owning_unit
from fastapi.testclient import TestClient
from smartmatch_domain.jobs import JobState
from smartmatch_persistence.engine import create_session_factory
from smartmatch_persistence.jobs import JobRepository
from smartmatch_persistence.outbox import OutboxRepository
from smartmatch_providers.tasks import FixtureTaskQueue
from smartmatch_worker.config import WorkerSettings
from smartmatch_worker.dispatcher import OutboxDispatcher
from smartmatch_worker.handlers import (
    BudgetFailure,
    CommandContext,
    CommandRegistry,
    HandlerResult,
    PolicyFailure,
    ProviderFailure,
    default_registry,
)
from smartmatch_worker.identity import (
    JsonWebKey,
    OidcTaskVerifier,
    StaticJwksSource,
    TaskIdentityError,
    UnconfiguredTaskVerifier,
)
from smartmatch_worker.main import create_app
from sqlalchemy import text

pytestmark = pytest.mark.integration

AUDIENCE = "https://worker.smartmatch.invalid/tasks/execute"
ISSUER = "https://accounts.google.com"
DISPATCHER_ACCOUNT = "tasks-dispatcher@smartmatch-test.iam.gserviceaccount.com"
KID = "test-signing-key"
SIGNING_MATERIAL = "only-the-legitimate-signer-holds-this"


# ---------------------------------------------------------------------------
# The signature stand-in, and exactly what it does and does not prove
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StandInSignatureVerifier:
    """A key-bound signature primitive that needs no third-party library.

    It computes HMAC-SHA256 over the JWT signing input with the key's material.
    That is *not* RS256, and this class must never be wired into a deployment —
    it lives in the test suite for that reason.

    What it nonetheless proves, because the surrounding verifier is production
    code: a token signed with the wrong key is rejected, a token whose payload
    was edited after signing is rejected, and the signature is checked before any
    claim is trusted. What it cannot prove is that RSA PKCS#1 v1.5 verification
    is implemented correctly — nothing in this repository can, because no
    asymmetric primitive is available to it.

    Attributes:
        algorithms: Declared as ``RS256`` deliberately. The token header must
            agree with the key's declared algorithm and with this set, and using
            the real algorithm name keeps the test tokens shaped like the ones
            Cloud Tasks actually mints.
    """

    algorithms: frozenset[str] = frozenset({"RS256"})

    def verify(self, *, signing_input: bytes, signature: bytes, key: JsonWebKey) -> None:
        """Raise unless ``signature`` is this key's MAC over ``signing_input``."""
        expected = hmac.new(
            key.material["k"].encode("utf-8"), signing_input, hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected, signature):
            raise TaskIdentityError("signature does not verify")


@dataclass(frozen=True, slots=True)
class SymmetricStandInVerifier:
    """A stand-in that *declares* symmetric support, to test the ban structurally.

    The algorithm ban must not depend on the configured verifier happening to
    support only asymmetric algorithms. This one advertises ``HS256`` so the test
    can prove the rejection comes from the verifier's own rule.
    """

    algorithms: frozenset[str] = frozenset({"HS256", "RS256"})

    def verify(self, *, signing_input: bytes, signature: bytes, key: JsonWebKey) -> None:
        """Accept anything. If this is ever reached, the ban failed."""
        return None


# ---------------------------------------------------------------------------
# Token minting
# ---------------------------------------------------------------------------


def _segment(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _json_segment(value: dict[str, Any]) -> str:
    return _segment(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def mint_token(
    *,
    material: str = SIGNING_MATERIAL,
    header: dict[str, Any] | None = None,
    claims: dict[str, Any] | None = None,
    sign: bool = True,
) -> str:
    """Mint a JWT the way Cloud Tasks would, with overridable parts.

    Args:
        material: Signing material. A different value models an attacker's key.
        header: Merged over the default header.
        claims: Merged over the default claims. A ``None`` value removes a claim,
            which is how the "missing ``exp``" cases are expressed.
        sign: When false the signature segment is empty — the shape an
            ``alg: none`` token takes.
    """
    now = int(datetime.now(UTC).timestamp())
    full_header: dict[str, Any] = {"alg": "RS256", "kid": KID, "typ": "JWT"}
    full_header.update(header or {})

    full_claims: dict[str, Any] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "114857392847362718293",
        "email": DISPATCHER_ACCOUNT,
        "email_verified": True,
        "iat": now,
        "exp": now + 600,
    }
    full_claims.update(claims or {})
    full_claims = {k: v for k, v in full_claims.items() if v is not None}

    signing_input = f"{_json_segment(full_header)}.{_json_segment(full_claims)}"
    if not sign:
        return f"{signing_input}."

    signature = hmac.new(
        material.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{signing_input}.{_segment(signature)}"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def jwks() -> StaticJwksSource:
    return StaticJwksSource(
        keys={KID: JsonWebKey(kid=KID, alg="RS256", material={"k": SIGNING_MATERIAL})}
    )


@pytest.fixture
def verifier(jwks: StaticJwksSource) -> OidcTaskVerifier:
    return OidcTaskVerifier(
        expected_audience=AUDIENCE,
        allowed_service_accounts=frozenset({DISPATCHER_ACCOUNT}),
        jwks=jwks,
        signature_verifier=StandInSignatureVerifier(),
        accepted_issuers=frozenset({ISSUER}),
    )


@pytest.fixture
def jobs() -> JobRepository:
    return JobRepository()


@pytest.fixture
def outbox() -> OutboxRepository:
    return OutboxRepository()


@dataclass
class RecordingRegistry:
    """A registry whose handlers count their own invocations."""

    calls: list[str] = field(default_factory=list)

    def build(self) -> CommandRegistry:
        def noop(context: CommandContext) -> HandlerResult:
            self.calls.append(context.job.command_type)
            context.emit({"type": "progress", "detail": "doing nothing, on purpose"})
            return HandlerResult(state=JobState.SUCCEEDED, summary={"performed": "nothing"})

        def boom(context: CommandContext) -> HandlerResult:
            self.calls.append(context.job.command_type)
            raise RuntimeError("the handler exploded")

        def policy(context: CommandContext) -> HandlerResult:
            raise PolicyFailure("consent was withdrawn while the task waited")

        def budget(context: CommandContext) -> HandlerResult:
            raise BudgetFailure("the tenant's provider ceiling was reached")

        def provider(context: CommandContext) -> HandlerResult:
            raise ProviderFailure("the provider returned 503")

        return CommandRegistry(
            handlers={
                "test.noop": noop,
                "test.boom": boom,
                "test.policy": policy,
                "test.budget": budget,
                "test.provider": provider,
            }
        )


@pytest.fixture
def recorder() -> RecordingRegistry:
    return RecordingRegistry()


@pytest.fixture
def client(session_factory, verifier, recorder) -> TestClient:
    """A worker whose identity verifier and registry are both injected."""
    return TestClient(
        create_app(
            session_factory=session_factory,
            task_verifier=verifier,
            registry=recorder.build(),
        )
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def accept_command(
    session_factory, jobs, outbox, tenant_id, command_type, payload=None
) -> uuid.UUID:
    """Accept a command the way the API does: job, payload, and outbox together.

    ``payload=None`` writes a job with a NULL payload, which is what every job
    accepted before migration ``0005`` looks like. It is not the same as an
    empty payload and the handlers do not treat it as one — see
    ``test_an_import_with_no_persisted_payload_fails_rather_than_inventing_one``.
    """
    with session_factory() as session:
        job = jobs.create(
            session,
            tenant_id=tenant_id,
            command_type=command_type,
            owning_unit_id=ensure_owning_unit(session, tenant_id),
            payload=payload,
        )
        outbox.enqueue(session, tenant_id=tenant_id, job_id=job.id, command_type=command_type)
        session.commit()
    return job.id


def import_payload(**overrides):
    """The payload ``POST /v1/units/{unit_id}/imports`` persists, plus overrides."""
    payload = {
        "unit_id": str(uuid.uuid4()),
        "source_reference": "gs://bucket/roster.csv",
        "dataset": "professionals",
        "dry_run": True,
    }
    payload.update(overrides)
    return payload


def dispatch_everything(session_factory) -> FixtureTaskQueue:
    """Run one dispatcher pass and hand back the queue it filled."""
    queue = FixtureTaskQueue()
    OutboxDispatcher(session_factory, queue).run_once()
    return queue


def job_state(session_factory, jobs, tenant_id, job_id) -> JobState:
    with session_factory() as session:
        record = jobs.get(session, tenant_id=tenant_id, job_id=job_id)
        assert record is not None
        return record.status


def job_events(session_factory, jobs, tenant_id, job_id) -> list[dict[str, Any]]:
    with session_factory() as session:
        return [
            event.payload
            for event in jobs.events_since(session, tenant_id=tenant_id, job_id=job_id)
        ]


def deliver(client, tenant_id, job_id, token: str | None = None):
    return client.post(
        "/tasks/execute",
        json={"tenant_id": str(tenant_id), "job_id": str(job_id)},
        headers=auth(token if token is not None else mint_token()),
    )


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------


def test_a_dispatched_command_executes_and_reaches_a_terminal_state(
    session_factory, jobs, outbox, tenant_id, client, recorder
):
    """The loop the dispatcher was written for, closed.

    Submitted, dispatched, delivered, executed, terminal — with the events a
    client following the SSE stream would actually see.
    """
    job_id = accept_command(session_factory, jobs, outbox, tenant_id, "test.noop")
    queue = dispatch_everything(session_factory)

    assert len(queue.enqueued) == 1
    payload = queue.enqueued[0].payload
    assert payload == {"tenant_id": str(tenant_id), "job_id": str(job_id)}

    response = client.post("/tasks/execute", json=payload, headers=auth(mint_token()))

    assert response.status_code == 200
    assert response.json()["state"] == JobState.SUCCEEDED.value
    assert recorder.calls == ["test.noop"]
    assert job_state(session_factory, jobs, tenant_id, job_id) is JobState.SUCCEEDED

    events = job_events(session_factory, jobs, tenant_id, job_id)
    types = [event["type"] for event in events]
    assert types == ["job.started", "progress", "job.completed"]
    assert events[-1]["state"] == JobState.SUCCEEDED.value


def test_a_duplicate_delivery_is_acknowledged_without_executing_twice(
    session_factory, jobs, outbox, tenant_id, client, recorder
):
    """At-least-once delivery is the normal case, not an anomaly.

    The second delivery must return 200. An error status would make Cloud Tasks
    retry a task whose work is already done or already running, which is the
    failure mode the conditional claim exists to prevent — so the status code is
    as load-bearing here as the claim itself.
    """
    job_id = accept_command(session_factory, jobs, outbox, tenant_id, "test.noop")
    dispatch_everything(session_factory)

    first = deliver(client, tenant_id, job_id)
    second = deliver(client, tenant_id, job_id)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    assert recorder.calls == ["test.noop"], "the handler ran exactly once"

    events = job_events(session_factory, jobs, tenant_id, job_id)
    assert [event["type"] for event in events] == ["job.started", "progress", "job.completed"]
    assert job_state(session_factory, jobs, tenant_id, job_id) is JobState.SUCCEEDED


def test_an_unknown_command_type_fails_the_job_explicitly(
    session_factory, jobs, outbox, tenant_id, client
):
    """Silently succeeding on a command nobody implemented is the worst outcome.

    ``failed_provider`` rather than ``failed_policy`` because it is the only
    failure state with a path back to ``queued``: an unknown command type is
    usually version skew during a rolling deploy, and that is recoverable by a
    human once the right worker is running.
    """
    job_id = accept_command(session_factory, jobs, outbox, tenant_id, "match-run.create")
    dispatch_everything(session_factory)

    response = deliver(client, tenant_id, job_id)

    assert response.status_code == 200
    assert job_state(session_factory, jobs, tenant_id, job_id) is JobState.FAILED_PROVIDER

    failure = job_events(session_factory, jobs, tenant_id, job_id)[-1]
    assert failure["type"] == "job.failed"
    assert failure["reason"] == "unknown_command_type"
    assert "match-run.create" in failure["detail"]


def test_a_raising_handler_never_leaves_the_job_running(
    session_factory, jobs, outbox, tenant_id, client
):
    """A job in ``running`` behind a dead worker is invisible work."""
    job_id = accept_command(session_factory, jobs, outbox, tenant_id, "test.boom")
    dispatch_everything(session_factory)

    response = deliver(client, tenant_id, job_id)

    assert response.status_code == 200
    state = job_state(session_factory, jobs, tenant_id, job_id)
    assert state is not JobState.RUNNING
    assert state is JobState.FAILED_PROVIDER

    failure = job_events(session_factory, jobs, tenant_id, job_id)[-1]
    assert failure["type"] == "job.failed"
    assert failure["reason"] == "unhandled_error"
    assert "RuntimeError" in failure["detail"]


@pytest.mark.parametrize(
    ("command_type", "expected"),
    [
        ("test.policy", JobState.FAILED_POLICY),
        ("test.budget", JobState.FAILED_BUDGET),
        ("test.provider", JobState.FAILED_PROVIDER),
    ],
)
def test_declared_failures_map_to_the_state_that_names_them(
    session_factory, jobs, outbox, tenant_id, client, command_type, expected
):
    """The state machine distinguishes three failure states for a reason.

    A budget stop and a consent withdrawal are not provider outages, and an
    operations view that cannot tell them apart cannot act on either.
    """
    job_id = accept_command(session_factory, jobs, outbox, tenant_id, command_type)
    dispatch_everything(session_factory)

    assert deliver(client, tenant_id, job_id).status_code == 200
    assert job_state(session_factory, jobs, tenant_id, job_id) is expected


@pytest.fixture
def shipped_worker(session_factory, verifier) -> TestClient:
    """A worker running the registry that actually ships, not the test double."""
    return TestClient(
        create_app(
            session_factory=session_factory,
            task_verifier=verifier,
            registry=default_registry(),
        )
    )


def test_the_import_command_executes_the_payload_it_was_submitted_with(
    session_factory, jobs, outbox, tenant_id, shipped_worker
):
    """``import.create`` executes, and the parameters it executes are the submitted ones.

    This is J10 closed at the worker end. Before ``job.payload`` existed the
    handler had a tenant, a job id and a command type, and failed every import
    as ``command_not_executable``; the parameters had been hashed into an
    idempotency fingerprint and dropped.

    The assertions are about *success with the right values*, not about the
    absence of an exception. A handler that ignored the payload and returned
    ``succeeded`` with an empty summary would satisfy "reached a terminal state"
    and fail here, which is the point: the dataset, the unit and the source
    reference in the terminal event are the ones that were persisted, so they
    demonstrably travelled from the submission to the worker.
    """
    payload = import_payload(dataset="professionals", source_reference="gs://bucket/roster.csv")
    job_id = accept_command(
        session_factory, jobs, outbox, tenant_id, "import.create", payload=payload
    )
    dispatch_everything(session_factory)

    response = deliver(shipped_worker, tenant_id, job_id)

    assert response.status_code == 200
    assert response.json()["state"] == JobState.SUCCEEDED.value
    assert job_state(session_factory, jobs, tenant_id, job_id) is JobState.SUCCEEDED

    events = job_events(session_factory, jobs, tenant_id, job_id)
    assert [event["type"] for event in events] == ["job.started", "progress", "job.completed"]

    completed = events[-1]
    assert completed["state"] == JobState.SUCCEEDED.value
    assert completed["summary"]["dataset"] == payload["dataset"]
    assert completed["summary"]["source_reference"] == payload["source_reference"]
    assert completed["summary"]["unit_id"] == payload["unit_id"]

    # The success is scoped, and says so where a client reading the stream sees
    # it. A dry run that had validated the caller's data would report rows; this
    # one reports that it read none, which is the difference between a narrow
    # true claim and a broad false one.
    assert completed["summary"]["content_validated"] is False
    assert completed["summary"]["rows_examined"] == 0


def test_injected_session_factory_owns_live_import_writes(
    engine,
    session_factory,
    jobs,
    outbox,
    tenant_id,
    verifier,
    monkeypatch,
):
    """``create_app(session_factory=X)`` makes X authoritative for handlers too.

    Reading process-global settings from the handler would bypass the
    application's injection seam and could send business rows to a different
    database. The sentinel is deliberately installed at that forbidden
    construction boundary; the observable result still comes from the injected
    database, where both the job and its review rows must live.
    """
    factory_builds = 0

    def reject_global_factory(_database_url: str):
        nonlocal factory_builds
        factory_builds += 1
        raise AssertionError("a handler must not build a process-global session factory")

    monkeypatch.setattr(
        handler_module,
        "create_session_factory",
        reject_global_factory,
        raising=False,
    )
    owning_unit_id = ensure_owning_unit(engine, tenant_id)
    payload = import_payload(
        unit_id=str(owning_unit_id),
        source_reference=None,
        rows=[{"full_name": "A. Rivera"}],
        dry_run=False,
    )
    job_id = accept_command(
        session_factory,
        jobs,
        outbox,
        tenant_id,
        "import.create",
        payload=payload,
    )
    dispatch_everything(session_factory)
    client = TestClient(
        create_app(
            session_factory=session_factory,
            task_verifier=verifier,
            registry=default_registry(),
        )
    )

    response = deliver(client, tenant_id, job_id)

    assert response.status_code == 200
    assert response.json()["state"] == JobState.SUCCEEDED.value
    assert factory_builds == 0
    with engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM import_batch WHERE job_id = :job_id"),
                {"job_id": job_id},
            ).scalar_one()
            == 1
        )
        assert (
            conn.execute(
                text(
                    "SELECT count(*) FROM review_item ri "
                    "JOIN import_batch ib ON ib.id = ri.import_batch_id "
                    "WHERE ib.job_id = :job_id"
                ),
                {"job_id": job_id},
            ).scalar_one()
            == 1
        )


def test_worker_lifespan_creates_and_disposes_one_engine(
    engine,
    session_factory,
    jobs,
    outbox,
    tenant_id,
    verifier,
    monkeypatch,
):
    """One worker process owns one pool, including handler business writes.

    The lifespan is the resource owner. A handler-created pool is not merely an
    avoidable duplicate: it is invisible to lifespan teardown and doubles the
    instance's configured connection ceiling. Running a real live import while
    the lifespan is active proves both the count and disposal at the boundary
    where the leak used to occur.
    """
    created_engines = []
    disposed_engines = []

    def tracked_factory(database_url: str):
        factory = create_session_factory(database_url)
        created_engine = factory.kw["bind"]
        original_dispose = created_engine.dispose

        def tracked_dispose() -> None:
            disposed_engines.append(created_engine)
            original_dispose()

        monkeypatch.setattr(created_engine, "dispose", tracked_dispose)
        created_engines.append(created_engine)
        return factory

    monkeypatch.setattr(worker_main, "create_session_factory", tracked_factory)
    monkeypatch.setattr(
        handler_module,
        "create_session_factory",
        tracked_factory,
        raising=False,
    )
    owning_unit_id = ensure_owning_unit(engine, tenant_id)
    job_id = accept_command(
        session_factory,
        jobs,
        outbox,
        tenant_id,
        "import.create",
        payload=import_payload(
            unit_id=str(owning_unit_id),
            source_reference=None,
            rows=[{"full_name": "A. Rivera"}],
            dry_run=False,
        ),
    )
    dispatch_everything(session_factory)
    settings = WorkerSettings(
        database_url=engine.url.render_as_string(hide_password=False),
    )
    app = create_app(settings=settings, task_verifier=verifier, registry=default_registry())

    with TestClient(app) as client:
        response = deliver(client, tenant_id, job_id)
        assert response.status_code == 200
        assert response.json()["state"] == JobState.SUCCEEDED.value

    assert len(created_engines) == 1
    assert disposed_engines == created_engines


def test_an_import_with_no_persisted_payload_fails_rather_than_inventing_one(
    session_factory, jobs, outbox, tenant_id, shipped_worker
):
    """A NULL payload is a job accepted before ``0005``, and it is unrecoverable.

    Reading it as "an import with no parameters" and completing would report an
    import that never happened. Terminal, because nothing can recover the
    parameters — the idempotency fingerprint that was kept is a one-way hash —
    so a re-drivable state would send an operator to press a button that cannot
    work.
    """
    job_id = accept_command(session_factory, jobs, outbox, tenant_id, "import.create")
    dispatch_everything(session_factory)

    assert deliver(shipped_worker, tenant_id, job_id).status_code == 200
    assert job_state(session_factory, jobs, tenant_id, job_id) is JobState.FAILED_POLICY

    failure = job_events(session_factory, jobs, tenant_id, job_id)[-1]
    assert failure["type"] == "job.failed"
    assert failure["reason"] == "command_payload_missing"


@pytest.mark.parametrize(
    ("overrides", "expected_problem"),
    [
        ({"dataset": ""}, "dataset"),
        ({"source_reference": "   "}, "source_reference"),
        ({"unit_id": "not-a-uuid"}, "unit_id"),
        ({"dry_run": "false"}, "dry_run"),
    ],
    ids=["blank-dataset", "blank-source", "unit-id-not-a-uuid", "dry-run-not-a-boolean"],
)
def test_an_unreadable_import_payload_fails_honestly(
    session_factory, jobs, outbox, tenant_id, shipped_worker, overrides, expected_problem
):
    """An invalid payload is a terminal failure that names what was wrong with it.

    Two things are asserted rather than one. That the job is *not* succeeded —
    a persisted payload makes it possible to execute an import and therefore
    possible to claim one that could not be read — and that the failure names
    the field, so the person who submitted it can fix it rather than resubmit
    the same thing.

    ``dry_run: "false"`` is in the list because it is the coercion trap:
    ``bool("false")`` is ``True``, so a handler that coerced would run this as a
    dry run and report success for a request nobody validated.
    """
    job_id = accept_command(
        session_factory,
        jobs,
        outbox,
        tenant_id,
        "import.create",
        payload=import_payload(**overrides),
    )
    dispatch_everything(session_factory)

    assert deliver(shipped_worker, tenant_id, job_id).status_code == 200

    state = job_state(session_factory, jobs, tenant_id, job_id)
    assert state is not JobState.SUCCEEDED
    assert state is JobState.FAILED_POLICY

    failure = job_events(session_factory, jobs, tenant_id, job_id)[-1]
    assert failure["type"] == "job.failed"
    assert failure["reason"] == "invalid_command_payload"
    assert expected_problem in failure["detail"]


def test_a_live_import_is_refused_rather_than_reported_as_done(
    session_factory, jobs, outbox, tenant_id, shipped_worker
):
    """``dry_run=false`` is the door this item does not open, and it fails loudly.

    A live import has to read the content named by ``source_reference`` and
    write review items into the quarantine-and-review path (v1.1 §1.5). Neither
    exists: the worker has no object-storage adapter, and there is no
    ``review_item`` table. The refusal is terminal for the same reason as an
    unreadable payload, and it is a refusal rather than a silent downgrade to a
    dry run — answering a live import with a validated command would be
    reporting work that was never done.
    """
    job_id = accept_command(
        session_factory,
        jobs,
        outbox,
        tenant_id,
        "import.create",
        payload=import_payload(dry_run=False),
    )
    dispatch_everything(session_factory)

    assert deliver(shipped_worker, tenant_id, job_id).status_code == 200
    assert job_state(session_factory, jobs, tenant_id, job_id) is JobState.FAILED_POLICY

    failure = job_events(session_factory, jobs, tenant_id, job_id)[-1]
    assert failure["reason"] == "import_content_unavailable"


def test_the_worker_reads_state_from_postgresql_not_from_the_payload(
    session_factory, jobs, outbox, tenant_id, client, recorder
):
    """A task can sit in the queue while the world changes underneath it.

    Here the job is cancelled after dispatch. The claim finds no ``dispatched``
    row, so nothing executes — which is only possible because the authoritative
    state is re-read rather than inferred from the delivery.
    """
    job_id = accept_command(session_factory, jobs, outbox, tenant_id, "test.noop")
    dispatch_everything(session_factory)

    with session_factory() as session:
        assert jobs.transition(
            session,
            tenant_id=tenant_id,
            job_id=job_id,
            to_state=JobState.CANCELLED,
            expected_from=JobState.DISPATCHED,
        )
        session.commit()

    response = deliver(client, tenant_id, job_id)

    assert response.status_code == 200
    assert recorder.calls == []
    assert job_state(session_factory, jobs, tenant_id, job_id) is JobState.CANCELLED


# ---------------------------------------------------------------------------
# Task identity
# ---------------------------------------------------------------------------


def executed_nothing(session_factory, jobs, tenant_id, job_id) -> bool:
    return job_state(session_factory, jobs, tenant_id, job_id) is JobState.DISPATCHED


@pytest.fixture
def dispatched_job(session_factory, jobs, outbox, tenant_id) -> uuid.UUID:
    job_id = accept_command(session_factory, jobs, outbox, tenant_id, "test.noop")
    dispatch_everything(session_factory)
    return job_id


def test_a_missing_credential_is_rejected(client, tenant_id, dispatched_job):
    response = client.post(
        "/tasks/execute",
        json={"tenant_id": str(tenant_id), "job_id": str(dispatched_job)},
    )
    assert response.status_code == 401


def test_a_token_signed_by_the_wrong_key_is_rejected(
    session_factory, jobs, tenant_id, dispatched_job, client, recorder
):
    """The forged-token case. Everything else about the token is correct."""
    response = deliver(client, tenant_id, dispatched_job, mint_token(material="a-forgers-key"))

    assert response.status_code == 403
    assert recorder.calls == []
    assert executed_nothing(session_factory, jobs, tenant_id, dispatched_job)


def test_a_validly_signed_token_for_another_audience_is_rejected(
    session_factory, jobs, tenant_id, dispatched_job, client
):
    """A token minted for a different Cloud Run service must not work here.

    Without this check any service sharing the dispatcher's identity becomes a
    way in, and audience is the only thing distinguishing them.
    """
    response = deliver(
        client,
        tenant_id,
        dispatched_job,
        mint_token(claims={"aud": "https://some-other-service.invalid/"}),
    )

    assert response.status_code == 403
    assert executed_nothing(session_factory, jobs, tenant_id, dispatched_job)


def test_alg_none_is_rejected(session_factory, jobs, tenant_id, dispatched_job, client):
    """The classic JWT bypass: an unsigned token asserting whatever it likes."""
    response = deliver(
        client,
        tenant_id,
        dispatched_job,
        mint_token(header={"alg": "none"}, sign=False),
    )

    assert response.status_code == 403
    assert executed_nothing(session_factory, jobs, tenant_id, dispatched_job)


def test_a_symmetric_algorithm_is_rejected_even_when_the_backend_supports_it(
    session_factory, jobs, tenant_id, dispatched_job, jwks, recorder
):
    """Algorithm confusion, tested structurally rather than by configuration.

    The injected backend advertises ``HS256`` and would accept anything. The ban
    must come from the verifier's own rule, or it is only as strong as whichever
    backend happens to be wired in.
    """
    permissive = OidcTaskVerifier(
        expected_audience=AUDIENCE,
        allowed_service_accounts=frozenset({DISPATCHER_ACCOUNT}),
        jwks=StaticJwksSource(
            keys={KID: JsonWebKey(kid=KID, alg="HS256", material={"k": SIGNING_MATERIAL})}
        ),
        signature_verifier=SymmetricStandInVerifier(),
        accepted_issuers=frozenset({ISSUER}),
    )
    client = TestClient(
        create_app(
            session_factory=session_factory,
            task_verifier=permissive,
            registry=recorder.build(),
        )
    )

    response = deliver(client, tenant_id, dispatched_job, mint_token(header={"alg": "HS256"}))

    assert response.status_code == 403
    assert recorder.calls == []
    assert executed_nothing(session_factory, jobs, tenant_id, dispatched_job)


def test_a_header_algorithm_that_disagrees_with_the_key_is_rejected(
    session_factory, jobs, tenant_id, dispatched_job, client
):
    """The token does not get to choose which algorithm verifies it."""
    response = deliver(client, tenant_id, dispatched_job, mint_token(header={"alg": "ES256"}))

    assert response.status_code == 403
    assert executed_nothing(session_factory, jobs, tenant_id, dispatched_job)


def test_an_unknown_key_id_is_rejected(session_factory, jobs, tenant_id, dispatched_job, client):
    """Key rotation is the JWKS source's problem; an unknown kid is a rejection."""
    response = deliver(
        client, tenant_id, dispatched_job, mint_token(header={"kid": "not-a-known-key"})
    )

    assert response.status_code == 403
    assert executed_nothing(session_factory, jobs, tenant_id, dispatched_job)


@pytest.mark.parametrize(
    ("description", "claims"),
    [
        ("expired", {"exp": int((datetime.now(UTC) - timedelta(hours=1)).timestamp())}),
        ("no exp at all", {"exp": None}),
        (
            "issued in the future",
            {"iat": int((datetime.now(UTC) + timedelta(hours=1)).timestamp())},
        ),
        ("wrong issuer", {"iss": "https://accounts.evil.invalid"}),
        ("no email", {"email": None}),
        ("email unverified", {"email_verified": False}),
        ("service account not on the allowlist", {"email": "someone-else@example.invalid"}),
        ("no subject", {"sub": None}),
    ],
)
def test_tokens_failing_any_single_claim_check_are_rejected(
    session_factory, jobs, tenant_id, dispatched_job, client, description, claims
):
    """Each claim check on its own, with everything else valid.

    Parameterized so a check that silently stops running fails one case rather
    than disappearing into a composite assertion.
    """
    response = deliver(client, tenant_id, dispatched_job, mint_token(claims=claims))

    assert response.status_code == 403, description
    assert executed_nothing(session_factory, jobs, tenant_id, dispatched_job)


def test_a_tampered_payload_is_rejected(session_factory, jobs, tenant_id, dispatched_job, client):
    """Re-encoding the claims after signing must invalidate the signature."""
    token = mint_token()
    header, _payload, signature = token.split(".")
    forged_claims = _json_segment({"iss": ISSUER, "aud": AUDIENCE, "email": DISPATCHER_ACCOUNT})

    response = deliver(client, tenant_id, dispatched_job, f"{header}.{forged_claims}.{signature}")

    assert response.status_code == 403
    assert executed_nothing(session_factory, jobs, tenant_id, dispatched_job)


@pytest.mark.parametrize(
    ("description", "verifier_kwargs"),
    [
        ("no expected audience", {"expected_audience": None}),
        ("empty service-account allowlist", {"allowed_service_accounts": frozenset()}),
        ("no signature backend", {"signature_verifier": None}),
    ],
)
def test_an_unconfigured_verifier_rejects_a_token_that_is_otherwise_valid(
    session_factory, jobs, tenant_id, dispatched_job, jwks, recorder, description, verifier_kwargs
):
    """Missing configuration must not become missing verification.

    This is the property the 501 stub had and the one easiest to lose: a
    deployment that forgot to set an audience, or was rolled out without the
    signature backend, must refuse everything rather than skip the check. The
    token here is fully valid, so only the configuration gap can reject it.
    """
    kwargs: dict[str, Any] = {
        "expected_audience": AUDIENCE,
        "allowed_service_accounts": frozenset({DISPATCHER_ACCOUNT}),
        "jwks": jwks,
        "signature_verifier": StandInSignatureVerifier(),
        "accepted_issuers": frozenset({ISSUER}),
    }
    kwargs.update(verifier_kwargs)

    client = TestClient(
        create_app(
            session_factory=session_factory,
            task_verifier=OidcTaskVerifier(**kwargs),
            registry=recorder.build(),
        )
    )
    response = deliver(client, tenant_id, dispatched_job)

    assert response.status_code == 501, description
    assert recorder.calls == []
    assert executed_nothing(session_factory, jobs, tenant_id, dispatched_job)


def test_the_default_worker_is_unconfigured_and_refuses_everything(
    session_factory, jobs, tenant_id, dispatched_job, recorder
):
    """The shipped default, with no environment configuration, is a closed door."""
    client = TestClient(
        create_app(
            session_factory=session_factory,
            task_verifier=UnconfiguredTaskVerifier(reason="nothing is configured"),
            registry=recorder.build(),
        )
    )

    response = deliver(client, tenant_id, dispatched_job)

    assert response.status_code == 501
    assert recorder.calls == []
    assert executed_nothing(session_factory, jobs, tenant_id, dispatched_job)


def test_a_verified_caller_still_cannot_execute_another_tenants_job(
    session_factory, jobs, outbox, tenant_id, client, recorder
):
    """Identity authenticates the *dispatcher*, never the tenant.

    The tenant comes from the delivery, so a mismatched pair must find nothing
    rather than execute anything — the composite ``(tenant_id, id)`` lookup is
    what makes that structural.
    """
    job_id = accept_command(session_factory, jobs, outbox, tenant_id, "test.noop")
    dispatch_everything(session_factory)

    response = deliver(client, uuid.uuid4(), job_id)

    assert response.status_code == 200
    assert response.json()["status"] == "unknown"
    assert recorder.calls == []
    assert job_state(session_factory, jobs, tenant_id, job_id) is JobState.DISPATCHED


def test_a_delivery_that_arrives_before_dispatch_is_recorded_is_retried(
    session_factory, jobs, outbox, tenant_id, client, recorder
):
    """A delivery racing the dispatcher must not be acknowledged away.

    The dispatcher enqueues the task and records ``queued -> dispatched`` in a
    *separate* transaction afterwards, so there is a real window in which the
    task is live in the queue and the job still reads ``queued``. Cloud Tasks
    can deliver inside that window.

    ``claim`` requires ``dispatched``, so the claim fails — and treating every
    claim failure as a duplicate acknowledges the delivery with 200. Cloud Tasks
    then deletes the task and the job is stranded: nothing re-delivers it, and
    ``queued`` has no route to ``redrive_pending``, so the re-drive command
    cannot rescue it either. The work is simply lost.

    The distinction is the job's state. ``running`` or terminal means another
    delivery genuinely got there first, and retrying would be pointless.
    ``queued`` means this delivery arrived too early, which is exactly what the
    queue's own retry exists for.
    """
    job_id = accept_command(session_factory, jobs, outbox, tenant_id, "test.noop")
    assert job_state(session_factory, jobs, tenant_id, job_id) is JobState.QUEUED

    response = client.post(
        "/tasks/execute",
        json={"tenant_id": str(tenant_id), "job_id": str(job_id)},
        headers=auth(mint_token()),
    )

    assert response.status_code == 503, (
        "a delivery that beat the dispatcher's commit must be retried by the "
        f"queue, not acknowledged (got {response.status_code})"
    )
    assert recorder.calls == [], "the handler must not have run"
    assert job_state(session_factory, jobs, tenant_id, job_id) is JobState.QUEUED
