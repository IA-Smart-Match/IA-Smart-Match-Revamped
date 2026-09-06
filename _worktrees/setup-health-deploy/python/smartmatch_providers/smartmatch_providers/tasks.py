"""Task-queue provider interface and fixture.

Architecture v1.1 §1.6 and §3.1: Cloud Tasks is the only work-distribution
mechanism, delivering to a private worker service authenticated by OIDC service
identity. Pub/Sub is deferred — no event needs multiple independent subscribers.

The interface models the two Cloud Tasks behaviors the dispatcher depends on:

* **Named tasks deduplicate.** Creating a task whose name already exists fails
  rather than enqueuing a second copy. This is what makes a retried dispatch
  safe, so :class:`TaskAlreadyExists` is a distinct, expected outcome — not an
  error to be logged and worried about.
* **Delivery is at-least-once.** The queue may deliver the same task twice. The
  worker's conditional job claim, not the queue, prevents double execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "FixtureTaskQueue",
    "TaskAlreadyExists",
    "TaskHandle",
    "TaskQueue",
    "TaskQueueError",
    "TaskRequest",
]


class TaskQueueError(RuntimeError):
    """A task could not be enqueued for a reason worth retrying."""


class TaskAlreadyExists(Exception):
    """A task with this name already exists in the queue.

    Not an error. It means a previous dispatch attempt succeeded and this one is
    a duplicate — precisely the outcome deterministic task names exist to
    produce. The dispatcher treats it as success.

    Deliberately not a subclass of :class:`TaskQueueError`: a caller catching
    retryable failures must not catch this by accident and retry forever.
    """


@dataclass(frozen=True, slots=True)
class TaskRequest:
    """One task to enqueue.

    Attributes:
        name: Deterministic task name. The dedupe key.
        payload: JSON body delivered to the worker. Carries identifiers only —
            the worker re-reads authoritative state from PostgreSQL rather than
            trusting the payload, because a task can sit in the queue while the
            world changes underneath it.
        target_path: Worker path to POST to.
    """

    name: str
    payload: dict[str, Any]
    target_path: str = "/tasks/execute"


@dataclass(frozen=True, slots=True)
class TaskHandle:
    """Acknowledgement that a task exists in the queue."""

    name: str
    queue: str


@runtime_checkable
class TaskQueue(Protocol):
    """Enqueues durable work."""

    name: str

    def enqueue(self, request: TaskRequest) -> TaskHandle:
        """Create a task.

        Raises:
            TaskAlreadyExists: if a task with this name is already enqueued.
                The caller treats this as success.
            TaskQueueError: on a transient failure worth retrying.
        """
        ...


@dataclass
class FixtureTaskQueue:
    """In-memory task queue for local development, CI, and the classroom.

    Models the dedupe behavior faithfully, because that is the behavior the
    dispatcher's correctness rests on: enqueuing a name twice raises
    :class:`TaskAlreadyExists` exactly as Cloud Tasks would.

    Instance state, never module state. The legacy's module-level queues are
    archived (MM-A02); a fixture owned by a test or a process is fine, a
    module-level one shared across requests is the bug.
    """

    name: str = "fixture-tasks"
    enqueued: list[TaskRequest] = field(default_factory=list)
    #: When set, the next ``enqueue`` raises this instead of succeeding. Lets a
    #: test exercise the dispatcher's failure path without a real outage.
    fail_next_with: Exception | None = None

    def enqueue(self, request: TaskRequest) -> TaskHandle:
        """Record the task, honouring name-based deduplication."""
        if self.fail_next_with is not None:
            failure = self.fail_next_with
            self.fail_next_with = None
            raise failure

        if any(task.name == request.name for task in self.enqueued):
            raise TaskAlreadyExists(request.name)

        self.enqueued.append(request)
        return TaskHandle(name=request.name, queue=self.name)
