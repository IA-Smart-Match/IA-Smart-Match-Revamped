"""What the local task queue refuses before it ever touches PostgreSQL.

:class:`~smartmatch_worker.local_tasks.LocalPostgresHttpTaskQueue` is the
compose appliance's stand-in for Cloud Tasks. It is the piece that holds a
credential and decides where a ``POST`` carrying it goes, so the interesting
assertions about it are refusals, and the most important of them happen
*before* any database work: an argument that never reaches a session cannot be
made safe by anything the session does afterwards.

This file covers exactly that layer — the checks reachable with no database:

* the target path, which is fixed and not something a caller may choose;
* the payload, which is identifiers only and nothing else;
* the status classifier, which decides whether a delivery is done, worth
  asking again, or a contract problem to stop on.

The database-dependent half of ``enqueue`` — that a task's name is backed by
a real outbox row, in ``leased`` status, whose tenant and job match the
payload — needs real rows and belongs in an integration test. Splitting them
this way is deliberate: these rules are worth asserting on every run of
``make test``, including on a machine with no PostgreSQL, because they are
the ones that decide whether a credentialed request can be aimed somewhere it
should not go.

The session factory handed to the queue below is a callable that fails if it
is ever called. That is the assertion, not a convenience: it proves these
refusals happen ahead of the database rather than merely alongside it.
"""

from __future__ import annotations

import inspect
import threading
import uuid
from typing import Any, NoReturn

import pytest
from smartmatch_providers.tasks import TaskQueue, TaskQueueError, TaskRequest
from smartmatch_worker.local_tasks import (
    LocalPostgresHttpTaskQueue,
    LocalTaskDeliveryPump,
    _classify_status,
    _parse_identifier_payload,
)


def _exploding_session_factory() -> NoReturn:
    """Stand in for the session factory, and fail if anything opens a session.

    Every test in this file asserts a refusal that must be decided from the
    request alone. Reaching PostgreSQL would still *usually* produce a
    refusal — there is no matching outbox row in a unit test — so a permissive
    mock would let a check that runs in the wrong order pass anyway, for the
    wrong reason. Exploding is what tells the two apart.
    """
    raise AssertionError(
        "the local task queue opened a database session for a request it should "
        "have refused from its arguments alone"
    )


def _queue() -> LocalPostgresHttpTaskQueue:
    return LocalPostgresHttpTaskQueue(_exploding_session_factory)  # type: ignore[arg-type]


def _identifier_payload() -> dict[str, Any]:
    """A well-formed payload, for tests where the payload is not the subject."""
    return {"tenant_id": str(uuid.uuid4()), "job_id": str(uuid.uuid4())}


# ---------------------------------------------------------------------------
# The queue satisfies the protocol it claims to
# ---------------------------------------------------------------------------


def test_the_local_queue_is_a_task_queue() -> None:
    """It is composed where a ``TaskQueue`` is expected, so it must be one.

    ``main``'s lifespan assigns this into ``app.state.task_queue``, the same
    slot a real Cloud Tasks client would occupy, and ``ScheduledPass`` calls
    it through that protocol. A structural check here fails at the moment the
    shapes diverge rather than at composition time in a running worker.
    """
    assert isinstance(_queue(), TaskQueue)


# ---------------------------------------------------------------------------
# The target path is fixed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "target_path",
    [
        "/operations/dispatch",
        "/tasks/execute/../operations/dispatch",
        "/tasks/execute/",
        "/health",
        "",
        "http://example.invalid/tasks/execute",
    ],
)
def test_only_the_task_execution_path_may_be_targeted(target_path: str) -> None:
    """A caller does not get to choose where a credentialed delivery lands.

    ``/operations/dispatch`` is the case with teeth: the delivery pump holds
    the *task* credential, and the whole reason the two tokens are kept
    distinct is that a task credential must not drive dispatch. A queue that
    honored a caller-supplied path would hand that separation back, one layer
    below where anyone is looking for it.

    The traversal and trailing-slash entries are here because "starts with
    ``/tasks/execute``" is the tempting wrong implementation, and it accepts
    both.
    """
    with pytest.raises(TaskQueueError, match="only ever delivers to"):
        _queue().enqueue(
            TaskRequest(
                name="task-name",
                payload=_identifier_payload(),
                target_path=target_path,
            )
        )


# ---------------------------------------------------------------------------
# The payload carries identifiers, and nothing else
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"tenant_id": str(uuid.uuid4())},
        {"job_id": str(uuid.uuid4())},
        {
            "tenant_id": str(uuid.uuid4()),
            "job_id": str(uuid.uuid4()),
            "rows": [{"name": "Ada Lovelace"}],
        },
        {
            "tenant_id": str(uuid.uuid4()),
            "job_id": str(uuid.uuid4()),
            "target_url": "http://example.invalid/",
        },
    ],
)
def test_a_payload_that_is_not_exactly_the_two_identifiers_is_refused(
    payload: dict[str, Any],
) -> None:
    """Exactly two keys — extra ones are refused, not ignored.

    The two entries carrying a third key are the point of this test. Silently
    dropping an unexpected key would let a caller believe it had been
    honored; the ``rows`` case is imported row content, which must never
    travel in a task payload when the worker's contract is to re-read
    authoritative state from PostgreSQL, and the ``target_url`` case is an
    attempt to redirect the delivery through the payload after the
    ``target_path`` door was closed above.
    """
    with pytest.raises(TaskQueueError, match="must be exactly"):
        _parse_identifier_payload(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"tenant_id": "not-a-uuid", "job_id": str(uuid.uuid4())},
        {"tenant_id": str(uuid.uuid4()), "job_id": "not-a-uuid"},
        {"tenant_id": None, "job_id": None},
        {"tenant_id": 7, "job_id": 9},
    ],
)
def test_both_identifiers_must_parse_as_uuids(payload: dict[str, Any]) -> None:
    """Well-named but unparseable values are refused as firmly as missing ones."""
    with pytest.raises(TaskQueueError, match="must be UUIDs"):
        _parse_identifier_payload(payload)


def test_a_well_formed_payload_parses_to_its_two_identifiers() -> None:
    """The permitted case, which is what catches a parser that refuses everything."""
    tenant_id = uuid.uuid4()
    job_id = uuid.uuid4()

    parsed = _parse_identifier_payload({"tenant_id": str(tenant_id), "job_id": str(job_id)})

    assert parsed == (tenant_id, job_id)


def test_a_bad_payload_is_refused_before_the_database_is_consulted() -> None:
    """Ordering, asserted through the exploding session factory.

    ``enqueue`` validates the path and the payload and only then opens a
    session. If that order ever inverted, this test fails with the factory's
    own assertion rather than the ``TaskQueueError`` — which is exactly the
    signal wanted, because a request that reaches the database is one whose
    arguments were trusted further than they should have been.
    """
    with pytest.raises(TaskQueueError, match="must be exactly"):
        _queue().enqueue(TaskRequest(name="task-name", payload={"anything": "else"}))


# ---------------------------------------------------------------------------
# How a delivery's status is read
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status_code", [200, 201, 202, 204, 299])
def test_a_2xx_is_delivered(status_code: int) -> None:
    """Including ``200`` for a duplicate delivery, which the worker answers by design."""
    assert _classify_status(status_code) == "delivered"


@pytest.mark.parametrize("status_code", [500, 502, 503, 504])
def test_a_5xx_is_worth_asking_again(status_code: int) -> None:
    """``503`` is the one that matters: the worker's own documented "retry shortly".

    ``execute_task`` answers ``503`` when a delivery races the dispatcher's
    second transaction — the job still reads ``queued`` and the claim could
    not match. That window is one transaction wide and genuinely does close,
    so it is the single case where asking again is the correct behavior
    rather than a way of hiding a failure.
    """
    assert _classify_status(status_code) == "retry"


@pytest.mark.parametrize("status_code", [301, 302, 307, 400, 401, 403, 404, 409, 429, 501])
def test_everything_else_is_refused_rather_than_retried(status_code: int) -> None:
    """A wrong credential or a missing queue does not improve by being asked twice.

    ``401``/``403`` mean the token is wrong and ``501`` means the worker has
    no verifier configured; retrying any of them is a tight loop against a
    condition only a human can change. The ``3xx`` entries matter for a
    second reason: the pump must treat a redirect as an unexpected status to
    stop on, never as a ``Location`` to follow — following one would let the
    response body decide where the next credentialed request goes.
    """
    assert _classify_status(status_code) == "refuse"


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------


def test_a_pump_that_could_not_be_stopped_is_not_replaced_by_a_second_one() -> None:
    """``stop()`` keeps the thread handle when the join times out.

    The bug this pins: ``stop()`` used to clear ``_thread`` unconditionally,
    including when the join expired with the thread still running. ``start()``
    treats ``_thread is None`` as "no pump running" and would then start a
    second one — two pumps polling the same committed rows and delivering each
    of them twice, which is the duplicate delivery this module is otherwise
    careful to avoid, manufactured by its own shutdown path.

    Driven with a real thread that ignores the stop event for longer than the
    join, rather than a mock: what is being asserted is the interaction
    between the join timing out and the handle surviving it, and a mock of
    ``join`` would assert only that this test knows how it was written.
    """
    pump = LocalTaskDeliveryPump(
        _exploding_session_factory,  # type: ignore[arg-type]
        target_url="http://127.0.0.1:8080/tasks/execute",
        bearer_token="compose-task",
    )

    started = threading.Event()
    release = threading.Event()

    def _wedged() -> None:
        started.set()
        release.wait(timeout=30.0)

    pump._thread = threading.Thread(target=_wedged, daemon=True)
    pump._thread.start()
    assert started.wait(timeout=5.0), "the stand-in thread never started"

    try:
        # A join far shorter than the thread's own life, which is exactly the
        # shape the real defect had: a 5s join against a 10s request timeout.
        pump.stop(timeout=0.1)

        assert pump._thread is not None, (
            "stop() discarded the handle of a thread that is still running; "
            "start() would now run a second pump alongside it"
        )

        # And the consequence that actually matters: start() declines.
        pump.start()
        assert pump._thread is not None
        assert not pump._thread.name.startswith("local-task-delivery-pump"), (
            "start() replaced the still-running thread with a second pump"
        )
    finally:
        release.set()


def test_the_default_join_outlasts_one_in_flight_request() -> None:
    """The join timeout is derived from ``request_timeout``, not a bare constant.

    A join shorter than one delivery's own timeout gives up on a thread that
    was about to finish normally — which is what a flat ``5.0`` did against
    the ``10.0`` second default request timeout: every shutdown landing
    mid-delivery timed out by construction.
    """
    pump = LocalTaskDeliveryPump(
        _exploding_session_factory,  # type: ignore[arg-type]
        target_url="http://127.0.0.1:8080/tasks/execute",
        bearer_token="compose-task",
    )

    # No thread was ever started, so this returns immediately; what is being
    # asserted is that the default is a function of request_timeout at all.
    pump.stop()

    signature = inspect.signature(LocalTaskDeliveryPump.stop)
    assert signature.parameters["timeout"].default is None, (
        "a literal default cannot track request_timeout; it must be derived"
    )
