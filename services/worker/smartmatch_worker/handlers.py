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

## A command's parameters come from the job row, never from the delivery

A handler reads what to do from ``context.job.payload`` — the column
``submit_command`` writes in the same INSERT as the job (migration ``0005``,
backlog J10). It is the authoritative copy, re-read from PostgreSQL at execution
time along with the rest of the row, which is what lets a delivery be treated as
a *notification that work exists* rather than as a description of it. The task
delivery still carries identifiers only, and a handler must never be given
parameters that arrived with it: a payload the worker trusts is a payload
anyone who reaches the queue can dictate.

``payload`` is ``None`` on a job written before that column existed. It is not
an empty command and must not be executed as one — see
:func:`handle_import_create`.

## Handlers do not get a session

A handler receives its job and an :attr:`CommandContext.emit` callable, and
nothing else. Emitting commits immediately, so a client watching the SSE stream
sees progress while the work is still running rather than only at the end.
Business writes will need a session when there is business data to write; until
then, handing one out would be handing out the ability to write anything at all
from code whose transaction boundaries nobody has thought about yet.
"""

from __future__ import annotations

import uuid
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
    "ImportCommand",
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
            delivery. A task can sit in the queue for minutes while consent,
            budget, or approval change, so the delivery is treated as a
            *notification that work exists*, never as a description of it. This
            carries ``job.payload``, the command's parameters as the API
            persisted them, which is the only place a handler may read them
            from.
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


@dataclass(frozen=True, slots=True)
class ImportCommand:
    """The parameters of one ``import.create``, as persisted and read back.

    Mirrors the dictionary ``smartmatch_api.routers.imports`` writes to
    ``job.payload``. It is a separate type rather than a raw mapping so that the
    handler works against values whose shape has already been established: the
    payload is read from the database, and a row can predate this code, be
    written by an older release, or be edited by hand in an incident.
    """

    unit_id: uuid.UUID
    source_reference: str
    dataset: str
    dry_run: bool


def _read_import_command(payload: Mapping[str, Any]) -> ImportCommand:
    """Read an :class:`ImportCommand` out of a persisted payload.

    Every problem is collected before raising, rather than reporting the first
    one. A coordinator fixing a rejected import should see the whole list at
    once — the same rule ``smartmatch_domain.ingest.validate_columns`` applies
    to dataset findings, for the same reason.

    Raises:
        PolicyFailure: with the reason ``invalid_command_payload`` when the
            payload cannot be read. **Terminal on purpose.** The payload is
            durable, so a re-drive re-reads the identical bytes and fails
            identically; ``failed_provider`` would invite an operator to press a
            button that cannot work. Fixing it means submitting a new command.
    """
    problems: list[str] = []
    unit_id: uuid.UUID | None = None
    source_reference: str | None = None
    dataset: str | None = None
    dry_run: bool | None = None

    raw_unit = payload.get("unit_id")
    if not isinstance(raw_unit, str) or not raw_unit.strip():
        problems.append("unit_id is missing or is not a string")
    else:
        try:
            unit_id = uuid.UUID(raw_unit)
        except ValueError:
            problems.append(f"unit_id {raw_unit!r} is not a UUID")

    raw_source = payload.get("source_reference")
    if isinstance(raw_source, str) and raw_source.strip():
        source_reference = raw_source.strip()
    else:
        problems.append("source_reference is missing, is not a string, or is blank")

    raw_dataset = payload.get("dataset")
    if isinstance(raw_dataset, str) and raw_dataset.strip():
        dataset = raw_dataset.strip()
    else:
        problems.append("dataset is missing, is not a string, or is blank")

    raw_dry_run = payload.get("dry_run")
    # Read, never coerced. `bool("false")` is `True`, and a payload carrying a
    # string, a number, or nothing at all for `dry_run` is one nobody validated
    # — coercing it would let this handler decide whether a live import runs.
    # Defaulting to the safe mode is refused for the same reason: it would turn
    # a malformed live import into a dry run and report success for a request
    # that was never understood.
    if isinstance(raw_dry_run, bool):
        dry_run = raw_dry_run
    else:
        problems.append(f"dry_run must be a boolean, got {type(raw_dry_run).__name__}")

    # The four `is None` tests are redundant — every path that leaves one unset
    # appended a problem — and are written out anyway so the narrowing below is
    # the type checker's conclusion rather than a comment's promise.
    if (
        problems
        or unit_id is None
        or source_reference is None
        or dataset is None
        or dry_run is None
    ):
        raise PolicyFailure(
            "the persisted import payload cannot be read: "
            + "; ".join(problems or ["no usable fields were found"]),
            reason="invalid_command_payload",
        )

    return ImportCommand(
        unit_id=unit_id,
        source_reference=source_reference,
        dataset=dataset,
        dry_run=dry_run,
    )


def handle_import_create(context: CommandContext) -> HandlerResult:
    """Execute ``import.create`` against the payload the submission persisted.

    Until J10 this handler could not run at all: ``submit_command`` hashed the
    request body into an idempotency fingerprint and dropped it, so a delivery
    arrived carrying a tenant, a job id, and a command type, and every import
    failed as ``command_not_executable``. ``job.payload`` (migration ``0005``)
    is what changed; the parameters are now as durable as the intent, and this
    handler reads them off the job row it was given.

    What it does, exactly
    ---------------------
    It validates the command — that the payload is present, that it names a
    unit, a source reference and a dataset, and that ``dry_run`` is a boolean
    someone actually set — and, for a **dry run**, completes as ``succeeded``
    reporting what it validated.

    **What it does not do, and the terminal event says so in the same words.**
    It does not read the content named by ``source_reference``. That is not an
    oversight to be tidied up later; it is the boundary this service is built
    around. Fetching it means an object-storage client in the worker, and the
    domain package that owns import validation
    (:func:`smartmatch_domain.ingest.validate_columns`) is forbidden every
    module that could reach one — four import-linter contracts, no filesystem,
    no network, not even ``os``. The adapter that reads the bytes and hands
    already-parsed rows to the domain is a component that does not exist yet.
    So a dry run's success here is a statement about the **command**, not about
    the caller's data, and ``summary`` says exactly that rather than leaving a
    coordinator to infer that their file validated.

    A live import — ``dry_run=false`` — is refused for the same reason, and is
    refused rather than quietly downgraded to a dry run: it would have to read
    that content and then write review items into the quarantine-and-review path
    (v1.1 §1.5), and there is no ``review_item`` table for them to go in.
    ``failed_policy`` rather than ``failed_provider`` because nothing about the
    job can change its outcome — a re-drive replays the same payload into the
    same missing adapter — and a re-drivable state would send an operator to
    press a button that cannot work.

    Raises:
        PolicyFailure: ``command_payload_missing`` when the job carries no
            payload, ``invalid_command_payload`` when it carries one that cannot
            be read, and ``import_content_unavailable`` for a live import.
    """
    payload = context.job.payload
    if payload is None:
        # NULL is not an empty command. It means the row was written by a
        # release that did not persist payloads, and the parameters are gone —
        # the fingerprint that was kept is a one-way hash. Nothing recovers
        # them, which is why this is terminal and why it must not be read as
        # "an import with no parameters" and completed.
        context.emit(
            {
                "type": "progress",
                "detail": ("this job carries no command payload, so there is nothing to import"),
            }
        )
        raise PolicyFailure(
            "import.create cannot be executed: this job has no persisted payload. "
            "It was accepted by a release that did not record command parameters, "
            "and they cannot be recovered — the idempotency fingerprint is a hash. "
            "Reporting success would claim an import that did not happen; submit "
            "the import again against the current release.",
            reason="command_payload_missing",
        )

    command = _read_import_command(payload)

    context.emit(
        {
            "type": "progress",
            "detail": (
                f"import command validated for dataset {command.dataset!r} in unit "
                f"{command.unit_id}; the content at {command.source_reference!r} "
                "has not been read"
            ),
            "dry_run": command.dry_run,
        }
    )

    if not command.dry_run:
        raise PolicyFailure(
            "a live import cannot be executed: reading the content named by "
            f"source_reference ({command.source_reference!r}) needs an object-storage "
            "adapter this worker does not have, and the review items a live import "
            "produces have no table to go in. The command itself is valid — "
            "resubmitting it with dry_run=true validates it and reports, which is "
            "everything this release can honestly do.",
            reason="import_content_unavailable",
        )

    return HandlerResult(
        state=JobState.SUCCEEDED,
        summary={
            "mode": "dry_run",
            "unit_id": str(command.unit_id),
            "dataset": command.dataset,
            "source_reference": command.source_reference,
            "validated": "command payload",
            "rows_examined": 0,
            "review_items_created": 0,
            "content_validated": False,
            "detail": (
                "the submitted command was validated and is executable; the content "
                "named by source_reference was not read, so this says nothing about "
                "the dataset itself"
            ),
        },
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
