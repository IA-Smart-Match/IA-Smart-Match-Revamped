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

## Handlers do not get a session — from ``CommandContext``, still

A handler receives its job and an :attr:`CommandContext.emit` callable from
:class:`CommandContext` itself, and nothing else. Emitting commits immediately,
so a client watching the SSE stream sees progress while the work is still
running rather than only at the end. Widening ``CommandContext`` to also carry
a session is a decision about ``smartmatch_worker.execution`` — which owns the
executor's transaction boundaries and constructs every ``CommandContext`` this
module receives — not one this module can make for it.

:func:`handle_import_create` is the first handler with genuine business data to
write, and it does not wait for that decision: for a live import over ``rows``
it opens its own session, independent of the executor's, from the same
``WorkerSettings.database_url`` the executor's own is built from — see
``_review_session_factory`` for the reasoning and the trade-off this makes.
That is a narrower claim than "handlers get a session": every other handler,
and this one on every path but a successful live import over rows, is exactly
as session-less as this section always said.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, ClassVar, Final

from smartmatch_domain.ingest import QualityFinding, validate_columns
from smartmatch_domain.ingest import normalize_header as _normalize_header
from smartmatch_domain.jobs import JobState
from smartmatch_persistence.engine import create_session_factory
from smartmatch_persistence.jobs import JobRecord
from smartmatch_persistence.review import ReviewRepository
from sqlalchemy.orm import Session, sessionmaker

from smartmatch_worker.config import get_settings

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

    ``source_reference`` and ``rows`` are mutually exclusive, and exactly one is
    always set. The router (``smartmatch_api.routers.imports``) enforces that
    before the command is ever persisted, and :func:`_read_import_command`
    re-checks it rather than trusting the row — the same reason every other
    field here is re-validated rather than trusted: a row can predate the check,
    or be edited by hand.
    """

    unit_id: uuid.UUID
    dataset: str
    dry_run: bool
    source_reference: str | None
    rows: tuple[Mapping[str, Any], ...] | None


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
    dataset: str | None = None
    dry_run: bool | None = None
    source_reference: str | None = None
    rows: tuple[Mapping[str, Any], ...] | None = None

    raw_unit = payload.get("unit_id")
    if not isinstance(raw_unit, str) or not raw_unit.strip():
        problems.append("unit_id is missing or is not a string")
    else:
        try:
            unit_id = uuid.UUID(raw_unit)
        except ValueError:
            problems.append(f"unit_id {raw_unit!r} is not a UUID")

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

    raw_source = payload.get("source_reference")
    raw_rows = payload.get("rows")
    has_source = raw_source is not None
    has_rows = raw_rows is not None

    if has_source == has_rows:
        # Covers both "neither" (a row from before rows existed, or one that
        # lost both fields to hand-editing) and "both" — the router refuses to
        # persist either shape, but this handler trusts nothing about how a row
        # came to exist by the time it is executed.
        problems.append(
            "exactly one of source_reference or rows must be present, and this "
            f"payload has {'both' if has_source else 'neither'}"
        )
    elif has_source:
        if isinstance(raw_source, str) and raw_source.strip():
            source_reference = raw_source.strip()
        else:
            problems.append("source_reference is present but is not a non-blank string")
    else:
        if isinstance(raw_rows, list) and all(isinstance(row, Mapping) for row in raw_rows):
            rows = tuple(raw_rows)
        else:
            problems.append("rows is present but is not a list of objects")

    # The checks below are redundant with the problem list — every path that
    # leaves a field unset appended a problem — and are written out anyway so
    # the narrowing is the type checker's conclusion rather than a comment's
    # promise.
    if (
        problems
        or unit_id is None
        or dataset is None
        or dry_run is None
        or (source_reference is None and rows is None)
    ):
        raise PolicyFailure(
            "the persisted import payload cannot be read: "
            + "; ".join(problems or ["no usable fields were found"]),
            reason="invalid_command_payload",
        )

    return ImportCommand(
        unit_id=unit_id,
        dataset=dataset,
        dry_run=dry_run,
        source_reference=source_reference,
        rows=rows,
    )


def handle_import_create(context: CommandContext) -> HandlerResult:
    """Execute ``import.create`` against the payload the submission persisted.

    Until J10 this handler could not run at all: ``submit_command`` hashed the
    request body into an idempotency fingerprint and dropped it, so a delivery
    arrived carrying a tenant, a job id, and a command type, and every import
    failed as ``command_not_executable``. ``job.payload`` (migration ``0005``)
    is what changed; the parameters are now as durable as the intent, and this
    handler reads them off the job row it was given.

    Two shapes, one gate
    ---------------------
    A submission names its content one of two mutually exclusive ways —
    ``source_reference`` or ``rows`` — and this handler treats them
    differently, honestly, because they are not equally capable:

    * **``source_reference``** names content in object storage, and this
      release still cannot read it. Fetching it needs an object-storage client
      in the worker, and the domain package that owns import validation
      (:func:`smartmatch_domain.ingest.validate_columns`) is forbidden every
      module that could reach one — four import-linter contracts, no
      filesystem, no network, not even ``os``. The adapter that would read
      those bytes and hand already-parsed rows to the domain does not exist
      yet. A **dry run** still completes as ``succeeded``, reporting that the
      *command* validated — that it names a unit, a dataset, and a reference —
      which says nothing about the referenced data, and the summary says so.
      A **live import** (``dry_run=false``) is refused with
      ``import_content_unavailable``, exactly as before: there is no adapter to
      read the content with, so refusing is the only honest outcome, and
      ``failed_policy`` rather than ``failed_provider`` because a re-drive
      replays the same payload into the same missing adapter and nothing about
      the job can change that.

    * **``rows``** carries the content already parsed, in the request body
      itself. There is no missing adapter here — the data is already in hand —
      so both a dry run and a live import validate it with
      :func:`~smartmatch_domain.ingest.validate_columns`. A dry run always
      completes as ``succeeded`` and never writes anything, reporting whether
      the data is usable and every finding, which is what makes it a safe
      default rather than a smaller version of the live path. A live import
      that is **not usable** — any ``ERROR`` finding — fails closed as
      ``dataset_not_usable``, with the findings on the event stream, rather
      than writing partial or garbage review items. A live import that **is**
      usable writes one ``import_batch`` row and one ``review_item`` per row
      (v1.1 §1.5, migration ``0008``) through
      :class:`~smartmatch_persistence.review.ReviewRepository`, and completes
      as ``succeeded`` naming the batch and how many items it produced.

    No dataset in this codebase declares which columns it requires. The only
    per-dataset column names anywhere in this repository are a test fixture in
    ``tests/unit/test_ingest.py`` (illustrative, not a contract), and
    ``docs/migration/migration-manifest.yaml``'s own F-28 finding records that
    the specification section that would define one (v1.1 §1.5) has not been
    read into this repository. Asserting a business schema here — "the
    'professionals' dataset requires `full_name` and `metro_region`" — would be
    inventing exactly the kind of contract nobody has written down, so
    ``validate_columns`` is called with no required or optional columns
    declared. It still performs every check that does not depend on knowing the
    schema: an empty dataset is still an error, ragged rows and colliding
    headers are still reported, and once a dataset's real column contract is
    decided it belongs in a small per-``dataset`` declaration this handler
    reads — not fabricated here.

    Raises:
        PolicyFailure: ``command_payload_missing`` when the job carries no
            payload, ``invalid_command_payload`` when it carries one that cannot
            be read, ``import_content_unavailable`` for a live import against a
            ``source_reference``, and ``dataset_not_usable`` for a live import
            over ``rows`` that failed validation.
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

    if command.rows is not None:
        return _execute_inline_rows_import(context, command, command.rows)

    assert command.source_reference is not None  # enforced by _read_import_command
    return _execute_source_reference_import(context, command, command.source_reference)


def _execute_source_reference_import(
    context: CommandContext, command: ImportCommand, source_reference: str
) -> HandlerResult:
    """Handle an ``import.create`` naming a ``source_reference``.

    Unchanged behavior: this release has no adapter that can read
    object-storage content, so a dry run validates the command's shape only —
    never the referenced data — and a live import is refused. See
    :func:`handle_import_create`'s docstring for the full argument.
    """
    context.emit(
        {
            "type": "progress",
            "detail": (
                f"import command validated for dataset {command.dataset!r} in unit "
                f"{command.unit_id}; the content at {source_reference!r} "
                "has not been read"
            ),
            "dry_run": command.dry_run,
        }
    )

    if not command.dry_run:
        raise PolicyFailure(
            "a live import cannot be executed: reading the content named by "
            f"source_reference ({source_reference!r}) needs an object-storage "
            "adapter this worker does not have, and this command did not submit "
            "its rows inline. Submit rows directly in the request body instead — "
            "POST /v1/units/{unit_id}/imports accepts a `rows` field mutually "
            "exclusive with source_reference and a live import over it can "
            "succeed — or resubmit this command with dry_run=true, which "
            "validates it and reports.",
            reason="import_content_unavailable",
        )

    return HandlerResult(
        state=JobState.SUCCEEDED,
        summary={
            "mode": "dry_run",
            "unit_id": str(command.unit_id),
            "dataset": command.dataset,
            "source_reference": source_reference,
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


def _execute_inline_rows_import(
    context: CommandContext,
    command: ImportCommand,
    rows: tuple[Mapping[str, Any], ...],
) -> HandlerResult:
    """Handle an ``import.create`` carrying already-parsed ``rows``.

    See :func:`handle_import_create`'s docstring for why ``validate_columns``
    runs with no required or optional columns declared, why a dry run always
    validates the data (not merely the command) and never writes, and why an
    unusable live import fails closed.
    """
    quality = validate_columns(command.dataset, rows, required=(), optional=())
    findings_payload = [_finding_payload(finding) for finding in quality.findings]

    context.emit(
        {
            "type": "progress",
            "detail": (
                f"validated {quality.row_count} inline row(s) for dataset "
                f"{command.dataset!r} in unit {command.unit_id}; usable="
                f"{quality.is_usable}"
            ),
            "dry_run": command.dry_run,
            "usable": quality.is_usable,
            "findings": findings_payload,
        }
    )

    if command.dry_run:
        # Dry run's contract, honored the same way for both content shapes:
        # always validate, always report, never write. Unlike the
        # source_reference path there is no missing adapter here — the rows are
        # already in hand — so this genuinely validates the caller's data, not
        # merely the command's shape, and can say so.
        return HandlerResult(
            state=JobState.SUCCEEDED,
            summary={
                "mode": "dry_run",
                "unit_id": str(command.unit_id),
                "dataset": command.dataset,
                "rows_examined": quality.row_count,
                "review_items_created": 0,
                "content_validated": True,
                "usable": quality.is_usable,
                "findings": findings_payload,
                "detail": (
                    "the submitted rows were validated; dry_run=true means no "
                    "review items were created"
                ),
            },
        )

    if not quality.is_usable:
        raise PolicyFailure(
            "the submitted dataset failed validation and no review items were "
            "created: " + "; ".join(f"{f.code}: {f.message}" for f in quality.errors),
            reason="dataset_not_usable",
        )

    normalized_rows = [_normalize_row(row) for row in rows]
    with _review_session_factory()() as session:
        batch = _reviews.create_batch_with_items(
            session,
            tenant_id=context.job.tenant_id,
            owning_unit_id=context.job.owning_unit_id,
            job_id=context.job.id,
            dataset=command.dataset,
            rows=normalized_rows,
        )
        session.commit()

    return HandlerResult(
        state=JobState.SUCCEEDED,
        summary={
            "mode": "live",
            "unit_id": str(command.unit_id),
            "dataset": command.dataset,
            "import_batch_id": str(batch.id),
            "rows_examined": quality.row_count,
            "review_items_created": batch.review_item_count,
            "content_validated": True,
            "usable": True,
            "findings": findings_payload,
            "detail": (
                f"{batch.review_item_count} review item(s) were created in import "
                f"batch {batch.id} and are pending a coordinator's review (v1.1 §1.5)"
            ),
        },
    )


def _normalize_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one row's keys the way ``validate_columns`` compares them.

    ``validate_columns`` normalizes headers internally to decide which columns
    are present, but hands back only the aggregate
    :class:`~smartmatch_domain.ingest.DatasetQuality` — never the normalized
    rows themselves. This calls the same public
    :func:`~smartmatch_domain.ingest.normalize_header` the domain exports for
    exactly this comparison, and resolves an in-row collision the same way the
    domain's own internal indexing does: first occurrence wins. That collision
    is already reported as a ``colliding_headers`` finding by
    ``validate_columns`` itself, so a caller who acted on this row without
    reading that finding learns nothing new from this repeating the same
    choice — it is consistency with an existing finding, not a second policy.
    """
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        header = _normalize_header(str(key))
        if header in normalized:
            continue
        normalized[header] = value
    return normalized


def _finding_payload(finding: QualityFinding) -> dict[str, Any]:
    """Render one :class:`~smartmatch_domain.ingest.QualityFinding` for an event.

    Job events are plain JSON (``job_event.payload``), and a
    :class:`~smartmatch_domain.ingest.Severity` is an enum, not a JSON value —
    this is the one place that boundary is crossed for import findings.
    """
    return {
        "severity": finding.severity.value,
        "code": finding.code,
        "message": finding.message,
        "columns": list(finding.columns),
    }


#: Module-level, like every other repository instance in this codebase
#: (``commands.py``'s ``_jobs``/``_outbox``, ``redrive.py``'s own ``_jobs``):
#: stateless, so one instance safely serves every call.
_reviews: Final[ReviewRepository] = ReviewRepository()


@lru_cache(maxsize=1)
def _review_session_factory() -> sessionmaker[Session]:
    """A session factory for writing review data, built from this process's own settings.

    ``CommandContext`` deliberately carries no session (see the module
    docstring): ``TaskExecutor`` — this worker's caller, in
    ``smartmatch_worker.execution`` — does not hand this module one, and
    widening ``CommandContext`` to carry the executor's own ``session_factory``
    is a change to that module, outside this track. ``_execute_inline_rows_import``
    is the first handler with genuine business data to write, so it opens its
    own — built from the same :class:`~smartmatch_worker.config.WorkerSettings`
    ``database_url`` that ``smartmatch_worker.main`` builds the executor's
    ``session_factory`` from, which is what makes this safe: the same database,
    a second connection pool to it, not a different one. Cached for the life of
    the process so a busy worker opens the underlying engine once rather than
    per delivery — the same reason ``smartmatch_worker.config.get_settings`` is
    itself cached.
    """
    return create_session_factory(get_settings().database_url)


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
