"""Command handlers and the registry that routes to them.

Architecture v1.1 §1.6: the API records intent, the dispatcher moves it, and the
worker performs it. This module is the "performs it" half — the only place in
the platform where a durable command's actual work is allowed to happen.

## The registry is a mapping, and the mapping is exhaustive by construction

A command type either has a handler or it does not, and the difference is
visible in one dictionary rather than scattered across ``if`` branches. What
matters more than the shape is what happens on a miss: an unregistered command
**fails the job explicitly**. The alternative — logging a warning and returning
success — is the single worst outcome available here, because the job would
report ``succeeded`` while nothing whatsoever had been done, and every consumer
downstream (the SSE stream, the operations view, the person who submitted it)
would believe it.

## Failure is declared, not inferred

A handler says how it failed by raising one of three exceptions, and each maps
to the state in the domain state machine that names it:

* :class:`PolicyFailure` becomes ``failed_policy`` — a gate refused. Terminal.
* :class:`BudgetFailure` becomes ``failed_budget`` — a ceiling was reached, or a
  kill switch is on. Terminal.
* :class:`ProviderFailure` becomes ``failed_provider`` — a dependency failed and
  might not next time. Re-drivable.

The distinction is not cosmetic. ``failed_provider`` and ``timed_out`` are the
only failure states with a transition back to ``queued`` (v1.1 §1.7), so
choosing one of them says "a human or a retry can fix this" and choosing
``failed_policy`` or ``failed_budget`` says "it cannot, and re-driving it would
only fail again". Mislabeling a budget stop as a provider failure produces a
job that is retried until it exhausts its attempts against a ceiling that was
never going to move.

## Handlers do not get a session

A handler receives its job and an :attr:`CommandContext.emit` callable, and
nothing else. Emitting commits immediately, so a client watching the SSE stream
sees progress while the work is still running rather than only at the end.
Business writes will need a session when there is business data to write; until
then, handing one out would be handing out the ability to write anything at all
from code whose transaction boundaries nobody has thought about yet.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar, Final

from smartmatch_domain.jobs import JobState
from smartmatch_persistence.jobs import JobRecord

__all__ = [
    "BudgetFailure",
    "CommandContext",
    "CommandHandler",
    "CommandRegistry",
    "HandlerFailure",
    "HandlerResult",
    "PolicyFailure",
    "ProviderFailure",
    "default_registry",
]


class HandlerFailure(Exception):
    """A handler could not complete its work, and says which kind of failure it was.

    Subclasses exist so the executor can map a failure to a job state without
    inspecting messages. Raising this base class directly is deliberately not
    supported by that mapping: an executor confronted with an unclassified
    failure treats it like any other unexpected exception, which is the safe
    reading.

    Attributes:
        reason: A stable machine-readable label, recorded on the job's failure
            event. Separate from the message so a consumer can branch on the
            kind of failure without parsing prose, and so rewording a message
            never breaks one. Defaults to the subclass's
            :attr:`default_reason`; a handler may override it when it has
            something more specific to say.
    """

    #: The label used when the raiser does not supply one.
    default_reason: ClassVar[str] = "handler_failure"

    def __init__(self, message: str, *, reason: str | None = None) -> None:
        super().__init__(message)
        self.reason: str = reason or type(self).default_reason


class ProviderFailure(HandlerFailure):
    """A dependency the handler needed failed, and might not next time.

    Maps to ``failed_provider``, which is re-drivable. Use it for outages,
    timeouts against a provider, and anything else where the same command might
    succeed later.
    """

    default_reason: ClassVar[str] = "provider_failure"


class PolicyFailure(HandlerFailure):
    """A gate refused the work at execution time.

    Maps to ``failed_policy``, which is terminal. This is the state that makes
    the send-time gate rechecks meaningful (v1.1 §1.8): consent withdrawn while
    the task sat in the queue is not a provider outage and must never be retried
    into succeeding.
    """

    default_reason: ClassVar[str] = "policy_failure"


class BudgetFailure(HandlerFailure):
    """A spend ceiling or kill switch stopped the work.

    Maps to ``failed_budget``, which is terminal. Retrying against a ceiling
    burns attempts and changes nothing; the ceiling has to move first, and that
    is a decision, not a retry.
    """

    default_reason: ClassVar[str] = "budget_failure"


@dataclass(frozen=True, slots=True)
class CommandContext:
    """Everything a handler is given.

    Attributes:
        job: The job as read from PostgreSQL at execution time — not the task
            payload. A task can sit in the queue for minutes while consent,
            budget, or approval change, so the delivery is treated as a
            *notification that work exists*, never as a description of it.
        emit: Records one job event immediately, in its own transaction, and
            returns its sequence number. Progress a client can see while the
            work is still running.
    """

    job: JobRecord
    emit: Callable[[dict[str, Any]], int]


@dataclass(frozen=True, slots=True)
class HandlerResult:
    """How a handler finished, when it finished at all.

    Attributes:
        state: ``succeeded`` or ``partial``. Nothing else is accepted — a
            handler reports failure by raising, so that a handler which forgets
            to check something cannot quietly *return* a failure state and have
            it read as a considered decision.
        summary: Recorded on the terminal job event. Small and factual: what was
            done, and how much of it.

    ``partial`` is here because v1.1 §3.6 N2 requires it. Work that half
    succeeded is labeled as such with its results retained, and is never
    reported as success — the legacy's inability to represent this is exactly
    the defect the state exists to correct.
    """

    state: JobState
    summary: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject any completion state that is not a success-shaped one.

        Raises:
            ValueError: if ``state`` is not ``succeeded`` or ``partial``.
        """
        if self.state not in _COMPLETION_STATES:
            raise ValueError(
                f"a handler may only complete as {sorted(s.value for s in _COMPLETION_STATES)}; "
                f"got {self.state.value!r}. Report failure by raising a HandlerFailure."
            )


#: The only states a handler may return. Failure is raised, never returned.
_COMPLETION_STATES: Final[frozenset[JobState]] = frozenset({JobState.SUCCEEDED, JobState.PARTIAL})

#: What a handler is: a function from context to result, raising on failure.
CommandHandler = Callable[[CommandContext], HandlerResult]


@dataclass(frozen=True, slots=True)
class CommandRegistry:
    """Maps a command type to the handler that performs it.

    Immutable and passed in, rather than a module-level dictionary handlers
    register themselves into. Module-level mutable registries were archived
    (MM-A02) for a reason that applies here too: a registry assembled by import
    side effects has contents that depend on import order, and a worker whose
    capabilities depend on import order is a worker whose capabilities nobody
    can state.
    """

    handlers: Mapping[str, CommandHandler] = field(default_factory=dict)

    def handler_for(self, command_type: str) -> CommandHandler | None:
        """Return the handler for ``command_type``, or ``None`` when there is none."""
        return self.handlers.get(command_type)

    @property
    def command_types(self) -> frozenset[str]:
        """Every command type this worker can execute."""
        return frozenset(self.handlers)


# ---------------------------------------------------------------------------
# The handlers themselves
# ---------------------------------------------------------------------------


def handle_noop(context: CommandContext) -> HandlerResult:
    """Execute ``test.noop``: prove the path works, and do nothing else.

    This is the command the dispatcher's integration tests submit, and it earns
    its place in the shipped registry by being the only end-to-end check that
    the whole chain — accept, commit, dispatch, deliver, verify, claim, execute,
    transition, record — actually connects. It is not reachable from the API:
    no route submits it, so the only way to create one is to insert a job
    directly, which is what the tests do.

    It does nothing, and says so. A smoke-test command that pretended to do work
    would be a fixture masquerading as behavior, which is the habit v1.1 §5.5
    exists to end.
    """
    context.emit({"type": "progress", "detail": "no-op command; nothing to do"})
    return HandlerResult(
        state=JobState.SUCCEEDED,
        summary={"performed": "nothing", "reason": "test.noop is a path check"},
    )


def handle_import_create(context: CommandContext) -> HandlerResult:
    """Execute ``import.create`` — which it cannot, and says so plainly.

    ``POST /v1/units/{unit_id}/imports`` accepts ``source_reference``,
    ``dataset``, and ``dry_run``, and **none of the three survives the
    submission**. ``submit_command`` uses the body only to compute an
    idempotency fingerprint — a one-way hash — and neither the ``job`` row nor
    the ``outbox_record`` row has a payload column. By the time a delivery
    reaches this handler, the only facts available are the tenant, the job, and
    the command type. There is nothing to import.

    Making that a durable failure is the honest outcome. The alternatives are
    both worse: succeeding would report an import that never happened, and
    importing "something" would be inventing the caller's parameters.

    The state is ``failed_policy`` — terminal — rather than ``failed_provider``,
    which is re-drivable. No retry and no re-drive can recover parameters that
    were never written down, and a state that invites one would send an operator
    to press a button that cannot work.

    Closing this gap needs a durable command payload: a ``job.payload`` column
    (an expand-phase migration) written by ``submit_command`` inside the same
    transaction as the job and the outbox row, so the parameters are as durable
    as the intent. That is a change to the API service and the persistence
    package, both of which are outside this module's remit.

    Raises:
        PolicyFailure: always, until the command payload is persisted.
    """
    context.emit(
        {
            "type": "progress",
            "detail": (
                "import.create was delivered, but the submitted import parameters "
                "were never persisted, so there is nothing to import"
            ),
        }
    )
    raise PolicyFailure(
        "import.create cannot be executed: the command payload (source_reference, "
        "dataset, dry_run) is not durably recorded — job rows carry identifiers "
        "only. Reporting success would claim an import that did not happen. "
        "A durable command payload is required before this command can run.",
        reason="command_not_executable",
    )


# Built by a function rather than exposed as a module-level constant, so that no
# caller can mutate the shipped registry and so a test wanting a different one
# constructs it explicitly instead of patching a global (MM-A02).
def default_registry() -> CommandRegistry:
    """Return the registry the worker runs with.

    Deliberately short. A command type appears here only once something can
    genuinely execute it or genuinely refuse it — a handler added ahead of its
    gate is a handler someone will trigger.
    """
    return CommandRegistry(
        handlers={
            "test.noop": handle_noop,
            "import.create": handle_import_create,
        }
    )
