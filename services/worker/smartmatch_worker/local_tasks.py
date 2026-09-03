"""A local, PostgreSQL-backed loopback task queue (docker compose only).

**This is a developer appliance that emulates the Cloud Tasks half of this
platform's queue for `docker compose up`, and it is never that queue's
implementation.** Nothing here claims Cloud Tasks' durability, its retry
schedule, or its production suitability, and Cloud Scheduler's
OIDC-authenticated trigger and Cloud Tasks' own OIDC identity remain open
F5/S-001 deployment work — see ``smartmatch_worker.config``'s "local
development path" section for the settings that gate this module, and
``smartmatch_worker.identity.LocalBearerTaskVerifier`` for what accepts the
credential the delivery pump presents.

## Why this is two classes and not one

:class:`LocalPostgresHttpTaskQueue` satisfies
:class:`smartmatch_providers.tasks.TaskQueue` — the interface
``dispatcher.OutboxDispatcher`` calls synchronously, inside the request that
is running a scheduled pass. :class:`LocalTaskDeliveryPump` is a background
thread that discovers already-dispatched work and ``POST``s it to
``/tasks/execute``. They are not the same object because they must not run at
the same time for the same row:

``run_once`` claims a row, calls :meth:`LocalPostgresHttpTaskQueue.enqueue`,
and *only then* commits the row as ``outbox_record.status='dispatched'`` in a
second transaction. If ``enqueue`` itself delivered the task synchronously —
POSTing to ``/tasks/execute`` before that second commit — the delivery would
race the very commit that makes the job claimable: ``execute_task`` re-reads
the job from PostgreSQL and answers ``503`` whenever it still reads
``queued``, which is the correct behavior for Cloud Tasks racing the same
commit, but a synchronous local delivery would lose every one of those races
and retry against a job that will *never* have been dispatched by the time it
asks, because nothing schedules a second attempt. Real Cloud Tasks survives
this because the queue and the retry schedule are Google's, running outside
this process, on their own timer. This appliance has no such thing, so it
earns the same property by ordering instead: the pump only ever looks at rows
PostgreSQL has already committed as ``dispatched``, which happens strictly
after ``enqueue`` returns. Delivery begins only once the race is already
over.

So ``enqueue`` does the one thing it safely can at that moment — prove the
task it is being asked to create corresponds to a row the dispatcher has
actually, durably claimed — and leaves *sending* it to the pump, which reads
nothing but committed state.

## What this queue refuses, on purpose

* **Anything not backed by an already-leased, durable outbox row.** A caller
  that invented a task name would get ``TaskQueueError``, not a task.
* **A payload carrying anything but ``{tenant_id, job_id}``.** The dispatcher
  never sends anything else (see ``dispatcher._dispatch_row``), and this
  queue does not trust a caller to keep it that way — it checks.
* **Delivering to anywhere but the one loopback address and exact path
  ``smartmatch_worker.config.validate_local_task_target_url`` already
  validated at boot.** Neither the queue nor the pump accepts a URL, a path,
  a header, or a credential from a request, a payload, or a tenant; the
  target and the bearer token are both fixed at construction, from settings
  an operator configured, not from anything this process is later asked to
  do.
* **Treating a redirect as delivery.** The pump speaks :mod:`http.client`
  directly rather than a client that follows redirects by default, so a
  ``3xx`` from the target is simply an unexpected status this module
  classifies as a contract error — see :class:`LocalTaskDeliveryPump` — never
  something it chases.
* **Marking a job complete because a request happened.** Every disposition
  below short of a ``2xx`` leaves the durable state exactly as it was: still
  ``dispatched``, still visible, still retried by a later poll for the
  dispositions worth retrying. Manufacturing success here would be the exact
  defect ``main``'s module docstring already refuses for
  ``FixtureTaskQueue`` — reporting a task as handled when nothing durable
  says so — reintroduced one layer further out.
"""

from __future__ import annotations

import http.client
import json
import logging
import threading
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Final
from urllib.parse import urlsplit

import sqlalchemy as sa
from smartmatch_domain.jobs import JobState
from smartmatch_persistence import schema
from smartmatch_persistence.outbox import OutboxStatus
from smartmatch_providers.tasks import (
    TaskAlreadyExists,
    TaskHandle,
    TaskQueueError,
    TaskRequest,
)
from sqlalchemy.orm import Session, sessionmaker

__all__ = ["LocalPostgresHttpTaskQueue", "LocalTaskDeliveryPump"]

logger = logging.getLogger(__name__)

#: The only path a delivery may target — matches
#: ``smartmatch_worker.config._LOCAL_TASK_TARGET_PATH``, which already
#: validated the configured URL ends here. Restated rather than imported so
#: this module's own invariant is legible without following an import into
#: ``config`` to know what it says.
_TARGET_PATH: Final[str] = "/tasks/execute"

#: How often the pump looks for newly committed work. An argued code
#: constant, not a setting — see ``config``'s "local development path"
#: section for why a poll interval that exists to exercise a security
#: boundary is not something an environment variable should be able to
#: mistune. One second is fast enough that a developer watching compose logs
#: sees a dispatched job delivered promptly, and slow enough that an idle
#: loop — the ordinary case between imports — costs nothing worth avoiding.
DEFAULT_POLL_INTERVAL: Final[timedelta] = timedelta(seconds=1)

#: How long the pump waits for the worker to answer one delivery before
#: treating the attempt as failed. Generous relative to the poll interval
#: because a slow handler must not be mistaken for a dead target; the pump
#: will simply try again next poll if this expires.
DEFAULT_REQUEST_TIMEOUT_SECONDS: Final[float] = 10.0

#: Statuses at or above this are the one disposition worth retrying — see
#: ``main``'s module docstring for what ``execute_task`` means by ``503`` and
#: ``500``, both of which land here alongside every other ``5xx``.
_RETRYABLE_STATUS_FLOOR: Final[int] = 500

#: The ``5xx`` statuses that are **not** retryable, carved back out of the
#: floor above.
#:
#: ``501`` is a deployment fact, not a transient failure: ``main`` answers it
#: when task-identity verification is not configured in this process, or when
#: no task queue is. Neither changes because a caller asked again, so a pump
#: that treated it as retryable would poll a permanently closed door once per
#: :data:`DEFAULT_POLL_INTERVAL`, forever, logging the same refusal each time
#: — the tight loop against a human-only condition that
#: :func:`_classify_status`'s own contract says it does not do.
#:
#: ``smartmatch_worker.local_scheduler._FATAL_STATUSES`` reaches the same
#: conclusion about the same status on the dispatch side. The two are stated
#: separately rather than shared because they classify different endpoints'
#: answers, but they must not disagree about this one: a worker that cannot
#: verify a credential is equally unreachable whichever door is knocked on.
_NON_RETRYABLE_SERVER_STATUSES: Final[frozenset[int]] = frozenset({501})


def _classify_status(status_code: int) -> str:
    """Sort a delivery's HTTP status into one of three dispositions.

    Returns:
        ``"delivered"`` for ``2xx``: the worker accepted or already handled
            the delivery (``execute_task`` answers ``200`` for a duplicate
            too, by design — see ``main``).
        ``"retry"`` for ``5xx`` other than
            :data:`_NON_RETRYABLE_SERVER_STATUSES`, including ``503``: the
            worker's own documented "ask again" response, and every failure
            mode ``main`` treats as worth a retry.
        ``"refuse"`` for everything else — ``3xx``, ``4xx``, ``501``, and
            anything unrecognised: a configuration or contract problem a
            retry will not resolve. The pump logs these clearly and leaves
            the row exactly as it was; it never retries them tightly and
            never fabricates completion for one.

    ``501`` is the one status whose disposition is not read off its class,
    and it is called out here because "``5xx`` means retry" is otherwise the
    obvious reading of this function. It means "not configured in this
    deployment", which no amount of asking again changes — see
    :data:`_NON_RETRYABLE_SERVER_STATUSES`.
    """
    if 200 <= status_code < 300:
        return "delivered"
    if status_code in _NON_RETRYABLE_SERVER_STATUSES:
        return "refuse"
    if status_code >= _RETRYABLE_STATUS_FLOOR:
        return "retry"
    return "refuse"


def _parse_identifier_payload(payload: Mapping[str, Any]) -> tuple[uuid.UUID, uuid.UUID]:
    """Extract exactly the two identifiers this queue is allowed to carry.

    Raises:
        TaskQueueError: if the payload is not exactly ``{tenant_id, job_id}``,
            or either value is not a UUID. The dispatcher never sends
            anything else (``dispatcher._dispatch_row``); this exists so a
            caller of this queue that is not that dispatcher cannot smuggle
            anything through it, identifiers-only being the one thing a task
            payload is trusted to carry (see ``main``'s ``TaskDelivery``
            docstring for the same rule on the receiving end).
    """
    if set(payload) != {"tenant_id", "job_id"}:
        raise TaskQueueError(
            f"local task queue payload must be exactly {{tenant_id, job_id}}, got {sorted(payload)}"
        )
    try:
        tenant_id = uuid.UUID(str(payload["tenant_id"]))
        job_id = uuid.UUID(str(payload["job_id"]))
    except (ValueError, TypeError, AttributeError) as exc:
        raise TaskQueueError(
            "local task queue payload's tenant_id and job_id must be UUIDs"
        ) from exc
    return tenant_id, job_id


@dataclass
class LocalPostgresHttpTaskQueue:
    """Satisfies :class:`~smartmatch_providers.tasks.TaskQueue` against PostgreSQL.

    Read the module docstring before this one — in particular, why this class
    does not deliver anything itself. :meth:`enqueue` only proves that the
    task the dispatcher is asking for corresponds to an outbox row it has
    genuinely, durably leased; :class:`LocalTaskDeliveryPump` is what actually
    reaches ``/tasks/execute``, and only once PostgreSQL has committed that
    row as ``dispatched``.

    Args:
        session_factory: Opens the read this queue needs to check a row's
            durable state. Never held open across a request — one short
            session per :meth:`enqueue` call, on the same reasoning
            ``OutboxDispatcher`` gives for keeping its own transactions short.
        name: Reported on the :class:`~smartmatch_providers.tasks.TaskHandle`
            this queue returns, and in ``ScheduledPass``'s log lines wherever
            a real deployment's queue name would appear.

    Instance state, never module state — the same discipline
    ``FixtureTaskQueue`` documents and for the same reason (MM-A02): a
    module-level queue shared across requests is the legacy defect this
    platform's target does not reintroduce, whichever queue implementation is
    composed.
    """

    session_factory: sessionmaker[Session]
    name: str = "local-postgres-http"

    def enqueue(self, request: TaskRequest) -> TaskHandle:
        """Validate a task against its durable outbox row. Delivers nothing.

        Raises:
            TaskAlreadyExists: if the row this task name names already reads
                ``dispatched`` — a previous attempt already finished this
                step, and the caller (``OutboxDispatcher``) treats this as
                success, exactly as it would a real Cloud Tasks dedupe.
            TaskQueueError: if ``request.target_path`` is not
                ``/tasks/execute``; if the payload is not exactly
                ``{tenant_id, job_id}``; if no outbox row carries this task
                name at all; if the row's own ``tenant_id``/``job_id`` do not
                match the payload; or if the row is in any status but
                ``leased`` — ``pending`` means the claim that should have
                preceded this call never committed, and ``failed`` means the
                row was already written off. None of those are retryable by
                calling this again with the same arguments.
        """
        if request.target_path != _TARGET_PATH:
            raise TaskQueueError(
                f"local task queue only ever delivers to {_TARGET_PATH!r}, not "
                f"{request.target_path!r}"
            )

        tenant_id, job_id = _parse_identifier_payload(request.payload)

        with self.session_factory() as session:
            row = session.execute(
                sa.select(
                    schema.outbox_record.c.tenant_id,
                    schema.outbox_record.c.job_id,
                    schema.outbox_record.c.status,
                ).where(schema.outbox_record.c.task_name == request.name)
            ).one_or_none()

        if row is None:
            raise TaskQueueError(
                f"no outbox row backs task {request.name!r}; refusing to enqueue a "
                "task this queue could never later prove was dispatched"
            )
        if row.tenant_id != tenant_id or row.job_id != job_id:
            raise TaskQueueError(f"task {request.name!r}'s payload does not match its outbox row")

        row_status = OutboxStatus(row.status)
        if row_status is OutboxStatus.DISPATCHED:
            raise TaskAlreadyExists(request.name)
        if row_status is not OutboxStatus.LEASED:
            raise TaskQueueError(
                f"task {request.name!r}'s outbox row reads {row_status.value!r}, not "
                "'leased'; this queue only accepts a task the dispatcher has just "
                "claimed in this same pass"
            )

        return TaskHandle(name=request.name, queue=self.name)


@dataclass
class LocalTaskDeliveryPump:
    """Background thread that delivers already-dispatched work to the worker.

    Read the module docstring first. This class polls PostgreSQL for rows
    both the outbox and the job agree are ``dispatched`` — never for rows
    :meth:`LocalPostgresHttpTaskQueue.enqueue` merely validated — and
    ``POST``s each one's identifiers to a fixed loopback address with a fixed
    bearer token, matching exactly what
    ``smartmatch_worker.identity.LocalBearerTaskVerifier`` expects on the
    receiving end.

    Args:
        session_factory: Opens the read each poll needs. A new, short session
            per poll, never held across the network call that follows.
        target_url: Already validated by
            ``smartmatch_worker.config.validate_local_task_target_url`` before
            this class is ever constructed — see ``main``'s lifespan. Fixed
            for the pump's whole lifetime; nothing here re-reads it from a
            request, a row, or a payload.
        bearer_token: Presented as ``Authorization: Bearer <token>`` on every
            delivery. Never logged and never included in any exception this
            class raises.
        poll_interval: How often to look for newly dispatched work.
            :data:`DEFAULT_POLL_INTERVAL` unless a test needs otherwise.
        request_timeout: Seconds to wait for one delivery's response.

    :meth:`start` and :meth:`stop` are the whole lifecycle. ``main``'s
    lifespan calls :meth:`start` once, at process startup, only when
    ``local_task_queue_enabled`` composed this pump in the first place, and
    calls :meth:`stop` during shutdown so the process does not exit with a
    thread mid-request. The thread is a daemon regardless, so a process that
    is killed rather than asked to stop does not hang on it either.
    """

    session_factory: sessionmaker[Session]
    target_url: str
    bearer_token: str
    poll_interval: timedelta = DEFAULT_POLL_INTERVAL
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT_SECONDS
    _stop: threading.Event = field(default_factory=threading.Event, repr=False, compare=False)
    _thread: threading.Thread | None = field(default=None, repr=False, compare=False)

    def start(self) -> None:
        """Start the background poll loop. Idempotent: a second call is a no-op."""
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="local-task-delivery-pump",
            daemon=True,
        )
        self._thread.start()

    def stop(self, *, timeout: float | None = None) -> None:
        """Ask the loop to stop and wait for it, up to ``timeout`` seconds.

        Safe to call whether or not :meth:`start` ever ran. Does not raise if
        the thread is still finishing a delivery when ``timeout`` elapses —
        the thread is a daemon, so the worst case is one delivery finishing
        after the process has otherwise begun shutting down, not a hang.

        ``timeout`` defaults to a little more than :attr:`request_timeout`
        rather than to a bare constant, and the relationship is the point: a
        join shorter than one in-flight request's own timeout gives up on a
        thread that was about to finish normally. It used to be a flat
        ``5.0`` against a ``10.0`` second request timeout, which meant every
        shutdown landing mid-delivery timed out by construction.

        **The thread handle is kept when the join times out**, and that is
        the other half of the fix. Clearing it unconditionally made
        :meth:`start`'s "a second call is a no-op" guard read ``None`` while
        the old thread was still running, so a stop-then-start would leave
        two pumps polling the same rows — the duplicate delivery this class
        is otherwise careful to avoid, manufactured by its own shutdown path.
        A pump that could not be stopped stays visible instead, so a later
        :meth:`start` correctly declines to add a second one.
        """
        self._stop.set()
        thread = self._thread
        if thread is None:
            return

        thread.join(timeout=self.request_timeout + 1.0 if timeout is None else timeout)
        if thread.is_alive():
            logger.warning(
                "local task delivery pump did not stop within its join timeout; "
                "leaving the thread handle in place so a later start() cannot "
                "run a second pump alongside it"
            )
            return
        self._thread = None

    # -- internals -----------------------------------------------------

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._deliver_ready_rows()
            except Exception:
                # A poll's own failure — reading PostgreSQL raised — must not
                # kill the loop. The next poll tries again, on the same
                # reasoning ``ScheduledPass`` guards its sweep and lag read:
                # janitorial and observational work must not become a process
                # that silently stops looking.
                logger.exception("local task delivery pump: one poll failed; will try again")
            self._stop.wait(self.poll_interval.total_seconds())

    def _deliver_ready_rows(self) -> None:
        query = (
            sa.select(schema.outbox_record.c.tenant_id, schema.outbox_record.c.job_id)
            .select_from(
                schema.outbox_record.join(
                    schema.job,
                    sa.and_(
                        schema.outbox_record.c.tenant_id == schema.job.c.tenant_id,
                        schema.outbox_record.c.job_id == schema.job.c.id,
                    ),
                )
            )
            .where(
                schema.outbox_record.c.status == OutboxStatus.DISPATCHED.value,
                schema.job.c.status == JobState.DISPATCHED.value,
            )
            .order_by(schema.outbox_record.c.created_at)
        )
        with self.session_factory() as session:
            rows = session.execute(query).all()

        for row in rows:
            if self._stop.is_set():
                return
            self._deliver_one(tenant_id=row.tenant_id, job_id=row.job_id)

    def _deliver_one(self, *, tenant_id: uuid.UUID, job_id: uuid.UUID) -> None:
        try:
            status_code = self._post(tenant_id=tenant_id, job_id=job_id)
        except OSError as exc:
            # A connection failure is the same disposition as a 5xx: the
            # target may simply not be up yet, and the row is still
            # dispatched, so the next poll tries again.
            logger.warning(
                "local task delivery: job %s: connection to the worker failed, will retry: %s",
                job_id,
                exc,
            )
            return

        disposition = _classify_status(status_code)
        if disposition == "delivered":
            logger.info(
                "local task delivery: job %s: delivered (worker answered %d)",
                job_id,
                status_code,
            )
        elif disposition == "retry":
            logger.warning(
                "local task delivery: job %s: worker answered %d; will retry",
                job_id,
                status_code,
            )
        else:
            logger.error(
                "local task delivery: job %s: worker answered %d; treating this as "
                "a configuration or contract error rather than fabricating "
                "completion. The job stays visible as dispatched — fix the "
                "configuration and this line will repeat until it is",
                job_id,
                status_code,
            )

    def _post(self, *, tenant_id: uuid.UUID, job_id: uuid.UUID) -> int:
        """``POST`` one delivery. Returns the response status.

        Uses :mod:`http.client` directly rather than a client that follows
        redirects by default: a ``3xx`` here is simply an unexpected status
        this module's classifier reports and moves on from, never a
        ``Location`` this pump chases. The connection is opened, used once,
        and closed — this appliance has no need of keep-alive, and pooling a
        connection would be one more piece of state to reason about for a
        request rate measured in single digits per second.
        """
        parsed = urlsplit(self.target_url)
        # Not defensive: the settings validator has already refused any target
        # whose host is not a loopback literal, so a URL that reaches here has
        # a host. The assertion states that invariant for the type checker
        # rather than inventing a fallback host, which is the one thing this
        # function must never do — a default would silently aim a credentialed
        # POST at an address nobody chose.
        assert parsed.hostname is not None
        body = json.dumps({"tenant_id": str(tenant_id), "job_id": str(job_id)}).encode("utf-8")
        connection = http.client.HTTPConnection(
            parsed.hostname, parsed.port or 80, timeout=self.request_timeout
        )
        try:
            connection.request(
                "POST",
                parsed.path,
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": str(len(body)),
                    "Authorization": f"Bearer {self.bearer_token}",
                },
            )
            response = connection.getresponse()
            # Drained but never inspected: the worker's reply body carries
            # job state a real caller might want, and this pump's only
            # decision is the status code. Reading it fully (rather than
            # leaving it unread) is what lets the connection close cleanly
            # rather than aborting mid-body.
            response.read()
            return response.status
        finally:
            connection.close()
