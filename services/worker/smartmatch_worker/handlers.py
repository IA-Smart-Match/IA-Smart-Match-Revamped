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

## Business writes belong to the executor's outcome transaction

A handler receives the executor-owned :attr:`CommandContext.session` for every
durable business write. It may stage work there, but it must never commit or
roll it back: the executor conditionally moves the job out of ``running`` in
that same transaction, and only an applied terminal transition makes the
handler's work durable. If cancellation or J9's stalled-job sweep wins first,
the executor rolls the session back before recording ``job.outcome_discarded``.
That keeps the review queue from containing work attributed to a job whose
success was refused by the state machine.

:attr:`CommandContext.emit` deliberately remains different. Progress commits
immediately in its own transaction so an SSE client can see it while the work
is running, and so a rollback of business work does not erase the evidence that
the handler was active. The split is therefore by meaning, not convenience:
business work is atomic with the terminal outcome; progress is independently
durable and renews the job lease (J9).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar, Final

from smartmatch_domain.factor_registry import (
    SUPERSEDED_G1_MODEL,
    RegistryNotApprovedError,
    RegistryNotReadyError,
    assert_registry_approved,
    assert_scoring_ready,
    normalize_weights,
    resolve_scoring_model,
)
from smartmatch_domain.factors.proximity import (
    CBA_PROXIMITY_FORMULA_VERSION,
    UnknownScoringModeError,
)
from smartmatch_domain.factors.travel_burden import TRAVEL_BURDEN_FORMULA_VERSION
from smartmatch_domain.ingest import QualityFinding, Severity, validate_columns
from smartmatch_domain.ingest import normalize_header as _normalize_header
from smartmatch_domain.jobs import JobState
from smartmatch_domain.match_run import (
    MATCH_RUN_COMMAND_TYPE,
    MatchRunPins,
    inputs_fingerprint,
    weights_fingerprint,
)
from smartmatch_domain.optimizer import PortfolioCandidate, PortfolioRequest, solve_portfolio
from smartmatch_domain.public_url import StaticUrlShapeRefusal, validate_static_url_shape
from smartmatch_persistence.jobs import JobRecord
from smartmatch_persistence.match_runs import MatchRunRepository
from smartmatch_persistence.review import ReviewRepository
from sqlalchemy.orm import Session

from smartmatch_worker.column_contract import (
    ColumnContractError,
    DatasetColumnContract,
    get_column_contract,
)

__all__ = [
    "BudgetFailure",
    "CommandContext",
    "CommandHandler",
    "CommandRegistry",
    "HandlerFailure",
    "HandlerResult",
    "ImportCommand",
    "MatchRunCommand",
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
        session: The executor-owned transaction for durable business writes.
            A handler may flush or query through it when needed, but must not
            commit or roll it back. The executor commits it only with an
            applied terminal transition, or rolls it back when the job left
            ``running`` before the outcome could be recorded.
    """

    job: JobRecord
    emit: Callable[[dict[str, Any]], int]
    session: Session


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

    Which columns a dataset requires is no longer fabricated here and no longer
    left blank. ``docs/pilot-data/columns.yaml`` was ratified on 28 August 2026
    and, as of P9 card W1, :mod:`smartmatch_worker.column_contract` reads it and
    this handler hands its declarations to ``validate_columns``. The YAML is the
    single source of truth — no column name is spelled out in Python — and a
    contract that cannot be read is a terminal ``column_contract_unavailable``
    refusal rather than a quiet fall back to validating nothing, which would let
    an import appear to pass a contract nobody applied. A dataset the contract
    does not declare is refused as ``dataset_contract_unknown`` for the same
    reason.

    Enforcement is **section-level**, per W1's partial-ratification rule: a
    column still behind an open question would be declared under the
    contract's ``gate_pending`` maps and never enforced as ratified. No column
    is gate-pending today — P9 Gate A's ``board_role`` and Gate B's three
    published contact fields were the only entries, and both gates closed
    2 Sep 2026. ``board_role`` is no longer part of the ``professionals``
    contract at all: it is relationship-scoped, on
    :data:`~smartmatch_persistence.schema.professional_unit_relationship`
    (migration ``0012``), not a flat import column. The mechanism stays in
    place for the next column a gate has not yet answered; when one exists, a
    gate-pending column is recognized and never rejected, and depending on its
    declared posture it is either persisted with a ``columns_pending_gate``
    warning, or — for a column withheld like Gate B's contact fields were
    while that gate was open, where quarantine would itself be collection
    under ADR-0014 — dropped before any write, with a
    ``columns_withheld_pending_gate`` warning naming exactly what was
    withheld.

    A URL-shaped column declared under the contract's ``url_shaped_columns``
    (P9 pilot columns V2; today just ``events``' ``"Public URL"``) is checked
    with :func:`smartmatch_domain.public_url.validate_static_url_shape` for
    every row that carries a value. A candidate that fails the four static
    HTTPS shape rules is neither rejected nor silently dropped: it is reported
    as a ``url_shape_invalid`` warning finding naming the column and the
    failing rule, and the value is still stored exactly as submitted, for a
    coordinator's review — the same quarantine-and-review posture every other
    finding here already has.

    Raises:
        PolicyFailure: ``command_payload_missing`` when the job carries no
            payload, ``invalid_command_payload`` when it carries one that cannot
            be read, ``import_content_unavailable`` for a live import against a
            ``source_reference``, ``column_contract_unavailable`` when the
            ratified contract cannot be read, ``dataset_contract_unknown`` when
            it declares no such dataset, and ``dataset_not_usable`` for a live
            import over ``rows`` that failed validation.
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

    See :func:`handle_import_create`'s docstring for where the required and
    optional columns come from, why a dry run always validates the data (not
    merely the command) and never writes, and why an unusable live import fails
    closed.
    """
    contract = _dataset_contract(command.dataset)
    quality = validate_columns(
        command.dataset,
        rows,
        required=contract.required,
        optional=contract.optional,
        blank_sentinels=contract.blank_sentinels,
        blank_sentinels_by_column=contract.blank_sentinels_by_column,
    )

    # Gate findings and URL-shape findings are appended to the domain's,
    # never merged into ``quality`` itself: ``is_usable`` is the domain's
    # verdict on the ratified column contract, and neither a still-open gate
    # nor a candidate URL's shape can change it in either direction — both are
    # reviewable findings, not usability verdicts.
    gate_findings = _gate_pending_findings(contract, rows)
    url_shape_findings = _url_shape_findings(contract, rows)
    findings_payload = [
        _finding_payload(finding)
        for finding in (*quality.findings, *gate_findings, *url_shape_findings)
    ]

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

    normalized_rows = [_normalize_row(row, withhold=contract.withheld_columns) for row in rows]
    batch = _reviews.create_batch_with_items(
        context.session,
        tenant_id=context.job.tenant_id,
        owning_unit_id=context.job.owning_unit_id,
        job_id=context.job.id,
        dataset=command.dataset,
        rows=normalized_rows,
    )

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


def _dataset_contract(dataset: str) -> DatasetColumnContract:
    """Return the ratified contract for ``dataset``, or refuse.

    Both refusals are :class:`PolicyFailure` — terminal — because a re-drive
    replays the same dataset name against the same file and nothing about the
    job can change either outcome. Neither falls back to an unconstrained
    ``validate_columns`` call: an import that appears to pass a contract nobody
    read is worse than an import that fails.
    """
    try:
        contract = get_column_contract()
    except ColumnContractError as exc:
        raise PolicyFailure(
            f"the ratified column contract could not be read, so no import can be "
            f"validated against it: {exc}",
            reason="column_contract_unavailable",
        ) from exc

    declared = contract.get(dataset)
    if declared is None:
        raise PolicyFailure(
            f"dataset {dataset!r} is not declared in the ratified column contract; "
            f"declared datasets are: {', '.join(sorted(contract))}",
            reason="dataset_contract_unknown",
        )
    return declared


def _gate_pending_findings(
    contract: DatasetColumnContract, rows: Sequence[Mapping[str, Any]]
) -> tuple[QualityFinding, ...]:
    """Report the gate-pending columns this submission actually carries.

    Reported per posture, and only for columns genuinely present — a warning
    about a column nobody sent is noise that trains a coordinator to skim
    findings. Both are WARNING: a gate that has not answered cannot make a
    dataset unusable, and saying otherwise would be enforcing an answer.

    Column names are compared after :func:`~smartmatch_domain.ingest.normalize_header`,
    the same way ``validate_columns`` compares them, so ``"Public URL"`` and
    ``"public_url"`` are the same declared column here too.
    """
    if not contract.gate_pending or not rows:
        return ()

    present = {_normalize_header(str(key)) for row in rows for key in row}
    findings: list[QualityFinding] = []

    for posture, code, phrasing in (
        (
            "accept",
            "columns_pending_gate",
            "accepted and stored, but their meaning is not yet decided",
        ),
        (
            "withhold",
            "columns_withheld_pending_gate",
            "accepted, but their values were not stored",
        ),
    ):
        entries = [
            entry
            for entry in contract.gate_pending
            if entry.posture == posture and _normalize_header(entry.column) in present
        ]
        if not entries:
            continue
        gates = ", ".join(sorted({entry.gate for entry in entries}))
        columns = tuple(entry.column for entry in entries)
        findings.append(
            QualityFinding(
                severity=Severity.WARNING,
                code=code,
                message=(
                    f"{contract.dataset}: {', '.join(columns)} — {phrasing}, because "
                    f"{gates} has not closed"
                ),
                columns=columns,
            )
        )

    return tuple(findings)


def _url_shape_findings(
    contract: DatasetColumnContract, rows: Sequence[Mapping[str, Any]]
) -> tuple[QualityFinding, ...]:
    """Report rows whose declared URL-shaped columns fail the four static HTTPS rules.

    Checked with :func:`smartmatch_domain.public_url.validate_static_url_shape`
    — text shape only; no DNS resolution, no fetch (see that module's
    docstring for what passing does and does not mean). A candidate that fails
    is never rejected and never silently dropped: it is reported here as a
    WARNING, the same non-blocking posture :func:`_gate_pending_findings`
    already uses for the same reason — this is a reviewable signal for the
    coordinator, not a usability verdict. ``quality.is_usable`` (the ratified
    column contract's own verdict) is untouched by this function's result, and
    the value is still written exactly as submitted; only the finding is new.

    Blank or absent values are not failures — there is no candidate to check
    the shape of. A non-string value (a JSON number or boolean a submitter
    put where a URL belongs) is likewise skipped here: that is a shape problem
    :func:`~smartmatch_domain.ingest.validate_columns` has no opinion about
    either, and inventing one would be scope creep past the four rules this
    check exists to run.

    Column names are compared after
    :func:`~smartmatch_domain.ingest.normalize_header`, the same way
    ``validate_columns`` and :func:`_gate_pending_findings` compare them, so
    ``"Public URL"`` and ``"public_url"`` are the same declared column here
    too.
    """
    if not contract.url_shaped_columns or not rows:
        return ()

    findings: list[QualityFinding] = []
    for declared_column in contract.url_shaped_columns:
        target = _normalize_header(declared_column)
        reasons: set[str] = set()
        invalid_count = 0
        for row in rows:
            value: Any = None
            present = False
            for key, raw in row.items():
                if _normalize_header(str(key)) == target:
                    value, present = raw, True
                    break
            if not present or not isinstance(value, str) or not value.strip():
                continue
            result = validate_static_url_shape(value)
            if isinstance(result, StaticUrlShapeRefusal):
                invalid_count += 1
                reasons.add(result.reason.value)

        if invalid_count:
            findings.append(
                QualityFinding(
                    severity=Severity.WARNING,
                    code="url_shape_invalid",
                    message=(
                        f"{contract.dataset}: {declared_column!r} failed static HTTPS "
                        f"shape validation in {invalid_count} row(s) "
                        f"({', '.join(sorted(reasons))}); values were neither rejected "
                        "nor dropped and remain exactly as submitted, for review"
                    ),
                    columns=(declared_column,),
                )
            )

    return tuple(findings)


def _normalize_row(row: Mapping[str, Any], *, withhold: Sequence[str] = ()) -> dict[str, Any]:
    """Normalize one row's keys the way ``validate_columns`` compares them.

    ``withhold`` names columns whose values must not be persisted while their
    gate is open (P9 Gate B's published contact fields). They are dropped here,
    at the last point before the write, rather than filtered earlier: validation
    still sees the submission exactly as it arrived, so the coordinator's
    findings describe what they sent, and only storage is narrowed. The drop is
    reported as ``columns_withheld_pending_gate``, so it is never silent.


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
    withheld = {_normalize_header(column) for column in withhold}
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        header = _normalize_header(str(key))
        if header in withheld or header in normalized:
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


# ---------------------------------------------------------------------------
# match-run.create (plan card M8a)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MatchRunCommand:
    """The parameters of one ``match-run.create``, as persisted and read back.

    Mirrors the dictionary card M8b's router will write to ``job.payload``. A
    separate type rather than a raw mapping, for the reason
    :class:`ImportCommand` gives: the payload is read from the database, and a
    row can predate this code, be written by an older release, or be edited by
    hand in an incident.

    **There is no ``unit_id`` field, and its absence is the point.** The unit a
    run belongs to is ``job.owning_unit_id`` — written by ``submit_command``
    from the unit the router already authorized against, never from the body —
    and reading it back out of the payload instead would be a caller naming the
    subtree their own run is filed under, and therefore naming who may later
    read it. ``ImportCommand`` carries one because its handler passes it to
    ``ReviewRepository`` as a *datum* about the import; this handler needs it as
    an authorization input, and takes it from the job row.

    Attributes:
        event_need_id: The need a portfolio is being selected for.
        portfolio_size: How many candidates to select.
        random_seed: The CP-SAT seed. Part of the reproducibility contract —
            :func:`smartmatch_domain.optimizer.solve_portfolio` is deterministic
            "given identical inputs and seed", so a run that did not record its
            seed could not be reproduced.
        candidates: The already-scored candidate pool. Utilities arrive with the
            command rather than being computed here: an unknown utility is
            rejected by
            :class:`~smartmatch_domain.optimizer.PortfolioCandidate` and never
            coerced to ``0.0`` (ADR-0011), so the decision about how to present
            an unscorable candidate belongs to whoever assembled the pool.
        scoring_mode: The scoring mode the pool's utilities were produced
            under — ``"cba-physical-1"``, ``"cba-virtual-1"``, or ``None``.
            Written by whoever scored the pool, never chosen here and never
            defaulted: this handler does not score, so inventing a mode would
            pin the run to a model nothing actually applied.

            ``None`` means the utilities came from the superseded
            pre-ADR-0016 composition, and the run is pinned to
            ``1.1.1-approved-g1-m6j`` accordingly (ADR-0016 Proposal 7: a
            payload lacking the field is read as a pre-ADR-0016 run, not as
            ``cba-physical-1``). Every payload written before this field
            existed therefore keeps pinning exactly what it pinned before.
    """

    event_need_id: str
    portfolio_size: int
    random_seed: int
    candidates: tuple[PortfolioCandidate, ...]
    scoring_mode: str | None = None


def _read_candidate_pool(raw_candidates: object, problems: list[str]) -> list[PortfolioCandidate]:
    """Read the candidate pool out of a persisted payload, appending to ``problems``.

    Split out of :func:`_read_match_run_command` only because the per-entry
    checks are the bulk of it. Every entry is validated positionally so a
    message names *which* candidate was wrong — a pool of forty with one bad
    utility is not debuggable from "candidates is invalid".

    ``PortfolioCandidate``'s own ``__post_init__`` is what rejects a ``bool``
    utility, a ``NaN``, and anything outside ``[0.0, 1.0]``; its ``ValueError``
    is caught and recorded rather than allowed to propagate, so one bad entry
    does not hide the other nine.
    """
    if not isinstance(raw_candidates, list) or not raw_candidates:
        problems.append("candidates is missing, is not a list, or is empty")
        return []

    pool: list[PortfolioCandidate] = []
    for index, entry in enumerate(raw_candidates):
        if not isinstance(entry, Mapping):
            problems.append(f"candidates[{index}] is not an object")
            continue
        subject = entry.get("subject_id")
        utility = entry.get("utility")
        if not isinstance(subject, str) or not subject.strip():
            problems.append(f"candidates[{index}].subject_id is missing or is not a string")
            continue
        # `bool` before `float`: bool is a subclass of int and duck-types as a
        # float, so `utility: true` would otherwise be read as 1.0 — the same
        # trap PortfolioCandidate names, caught here too because this check
        # decides whether the value even reaches it.
        if isinstance(utility, bool) or not isinstance(utility, int | float):
            problems.append(
                f"candidates[{index}].utility must be a number, got {type(utility).__name__}"
            )
            continue
        try:
            pool.append(PortfolioCandidate(subject_id=subject.strip(), utility=float(utility)))
        except ValueError as exc:
            problems.append(f"candidates[{index}]: {exc}")
    return pool


def _read_match_run_command(payload: Mapping[str, Any]) -> MatchRunCommand:
    """Read a :class:`MatchRunCommand` out of a persisted payload.

    Every problem is collected before raising, exactly as
    :func:`_read_import_command` does and for the same reason.

    Raises:
        PolicyFailure: with the reason ``invalid_command_payload``. Terminal on
            purpose — the payload is durable, so a re-drive re-reads the
            identical bytes and fails identically, and ``failed_provider`` would
            invite an operator to press a button that cannot work.
    """
    problems: list[str] = []
    event_need_id: str | None = None
    portfolio_size: int | None = None
    random_seed: int | None = None

    raw_need = payload.get("event_need_id")
    if isinstance(raw_need, str) and raw_need.strip():
        event_need_id = raw_need.strip()
    else:
        problems.append("event_need_id is missing, is not a string, or is blank")

    raw_size = payload.get("portfolio_size")
    if isinstance(raw_size, bool) or not isinstance(raw_size, int):
        problems.append(f"portfolio_size must be an integer, got {type(raw_size).__name__}")
    elif raw_size < 1:
        problems.append(f"portfolio_size must be >= 1, got {raw_size}")
    else:
        portfolio_size = raw_size

    raw_seed = payload.get("random_seed")
    if isinstance(raw_seed, bool) or not isinstance(raw_seed, int):
        problems.append(f"random_seed must be an integer, got {type(raw_seed).__name__}")
    elif raw_seed < 0:
        # Matches `ck_match_run_random_seed`. Refused here rather than left to
        # the constraint so the failure names the field, not the constraint.
        problems.append(f"random_seed must be >= 0, got {raw_seed}")
    else:
        random_seed = raw_seed

    pool = _read_candidate_pool(payload.get("candidates"), problems)

    # Absent is a fact, not a gap: a payload with no mode was written by a
    # release that had none, and reading it as cba-physical-1 would pin the run
    # to a rulebook it never saw. Present-but-unrecognised is a different thing
    # and is refused, because a typo that fell through to a default would pin a
    # virtual event's run to the physical model.
    scoring_mode: str | None = None
    raw_mode = payload.get("scoring_mode")
    if raw_mode is not None:
        if not isinstance(raw_mode, str) or not raw_mode.strip():
            problems.append(
                f"scoring_mode must be a non-blank string or absent, got {raw_mode!r}"
            )
        else:
            try:
                resolve_scoring_model(raw_mode.strip())
            except UnknownScoringModeError as exc:
                problems.append(str(exc))
            else:
                scoring_mode = raw_mode.strip()

    subject_ids = [candidate.subject_id for candidate in pool]
    if len(set(subject_ids)) != len(subject_ids):
        # PortfolioRequest refuses a duplicate subject_id too. Caught here so
        # the failure is a payload problem the operator can read, rather than a
        # ValueError raised out of the solver call below.
        problems.append("candidates contains a duplicate subject_id")

    if problems or event_need_id is None or portfolio_size is None or random_seed is None:
        raise PolicyFailure(
            "the persisted match-run payload cannot be read: "
            + "; ".join(problems or ["no usable fields were found"]),
            reason="invalid_command_payload",
        )

    return MatchRunCommand(
        event_need_id=event_need_id,
        portfolio_size=portfolio_size,
        random_seed=random_seed,
        candidates=tuple(pool),
        scoring_mode=scoring_mode,
    )


def handle_match_run_create(context: CommandContext) -> HandlerResult:
    """Execute ``match-run.create``: solve, then record an immutable snapshot.

    Plan card M8a. The write is here rather than in a route because a match run
    is durable, possibly slow work whose result a coordinator will act on, and
    v1.1 §1.6 puts every such write on the command path: the API records intent,
    the dispatcher moves it, and this executes it. Card M8b adds the routes that
    submit the command and read the row back; until then the only way to reach
    this handler is a job inserted directly, which is what the integration tests
    do.

    What it stores, and what it does not
    -------------------------------------
    One ``match_run`` row: the inputs hash, the registry version and weights in
    force, the optimizer and route-estimate pins, the solver's verdict, and the
    unit and tenant it is scoped to. **Not** the selected professionals — that
    shortlist is card M10's surface, it has no table, and writing one here would
    be storing an assignment nothing can display and no policy row authorizes.

    The distinction matters for what a re-run means. Two runs with the same
    ``inputs_hash`` and the same pins are two runs of the same problem under the
    same rules, and if they disagreed about the shortlist that would be a defect
    in the solver's determinism rather than a fact about the candidates. The
    snapshot is what makes that statement checkable at all.

    Fail closed at the registry
    ----------------------------
    :func:`~smartmatch_domain.factor_registry.assert_registry_approved` and
    :func:`~smartmatch_domain.factor_registry.assert_scoring_ready` are both
    called before anything is solved or written. That is the standing rule the
    plan states — "every scoring path calls ``assert_registry_approved()``" —
    and the failure is ``failed_policy`` because a re-drive against an
    unapproved or half-implemented registry fails identically. Recording a run
    under a registry that was not ready would produce a snapshot whose pins name
    a state nobody approved, which is worse than no snapshot: it is a
    reproducible-looking record of something unsanctioned.

    Idempotent under re-drive
    --------------------------
    A second execution of the same job re-reads the identical payload, solves it
    to the identical answer (the seed and the pool are both in the payload), and
    finds ``uq_match_run_job`` already taken — so
    :meth:`~smartmatch_persistence.match_runs.MatchRunRepository.record` returns
    the first execution's row rather than writing a second. The summary says
    which happened, because "already recorded" and "recorded now" are both
    successes and a coordinator following the job is entitled to the difference.

    Raises:
        PolicyFailure: ``command_payload_missing`` when the job carries no
            payload, ``invalid_command_payload`` when it carries one that cannot
            be read, and ``registry_not_ready`` when the factor registry is not
            approved or its implemented scoring set is not the approved set.
    """
    payload = context.job.payload
    if payload is None:
        # NULL is not an empty command; see handle_import_create for the full
        # argument. A match run with no parameters is not a smaller match run,
        # it is an unrecoverable one.
        context.emit(
            {
                "type": "progress",
                "detail": "this job carries no command payload, so there is no run to record",
            }
        )
        raise PolicyFailure(
            "match-run.create cannot be executed: this job has no persisted payload. "
            "Its parameters cannot be recovered — the idempotency fingerprint is a "
            "hash — and recording a run against invented inputs would be a "
            "reproducible-looking record of nothing. Submit the run again.",
            reason="command_payload_missing",
        )

    command = _read_match_run_command(payload)

    try:
        assert_registry_approved()
        assert_scoring_ready()
    except (RegistryNotApprovedError, RegistryNotReadyError) as exc:
        raise PolicyFailure(
            f"match-run.create refused before scoring: {exc}",
            reason="registry_not_ready",
        ) from exc

    # The model the *pool* was scored under, resolved from the command rather
    # than assumed. Pinning today's default while the utilities came from an
    # older composition would produce a run whose recorded weights never
    # touched its recorded numbers — a reproducible-looking record of something
    # that did not happen, which is precisely what this snapshot exists to
    # prevent.
    model = resolve_scoring_model(command.scoring_mode)

    # Normalized over that model's factors only — the corrected form of the
    # legacy `_normalize_weights`, whose denominator ranged over nine declared
    # factors while its numerator summed seven, capping every score at 0.90.
    # These are the weights the run is pinned to, so the stored copy is the
    # normalized set that actually applied and not the proposed one.
    weights = normalize_weights(model=model)

    context.emit(
        {
            "type": "progress",
            "detail": "solving the portfolio",
            "candidates": len(command.candidates),
            "portfolio_size": command.portfolio_size,
            "registry_version": model.registry_version,
            "scoring_mode": model.scoring_mode,
        }
    )

    result = solve_portfolio(
        PortfolioRequest(
            event_need_id=command.event_need_id,
            candidates=command.candidates,
            portfolio_size=command.portfolio_size,
            random_seed=command.random_seed,
        )
    )

    pins = MatchRunPins(
        registry_version=model.registry_version,
        # `weights_fingerprint` over the weights *actually applied*, so a
        # virtual run fingerprints three weights and a physical run four. Two
        # runs of the same registry in different modes therefore carry the same
        # registry_version and different registry_hash values — same rulebook,
        # different model (ADR-0016 Proposal 9).
        registry_hash=weights_fingerprint(weights),
        optimizer_model_version=result.model_version,
        solver_name=result.solver_name,
        # From the result, not from this module's own import of ortools: the
        # recorded build is the one that solved.
        solver_version=result.solver_version,
        # Straight-line in both models, and said so rather than implied: the D3
        # route matrix is deferred, and both the superseded `travel_burden` and
        # the CBA band table measure a haversine distance. When D3 lands, these
        # older rows must keep saying what they actually used.
        route_estimate_source="straight_line",
        # Whichever distance formula the pinned model's proximity factor uses.
        # A CBA run that recorded the travel_burden version would name a
        # formula it never ran.
        route_estimate_version=(
            TRAVEL_BURDEN_FORMULA_VERSION
            if model is SUPERSEDED_G1_MODEL
            else CBA_PROXIMITY_FORMULA_VERSION
        ),
        scoring_mode=model.scoring_mode,
        scoring_mode_version=model.scoring_mode_version,
    )

    record = _match_runs.record(
        context.session,
        # Both from the job row, never from the payload. See MatchRunCommand.
        tenant_id=context.job.tenant_id,
        owning_unit_id=context.job.owning_unit_id,
        job_id=context.job.id,
        event_need_id=command.event_need_id,
        inputs_hash=inputs_fingerprint(
            event_need_id=command.event_need_id,
            candidate_subject_ids=[candidate.subject_id for candidate in command.candidates],
            candidate_utilities=[candidate.utility for candidate in command.candidates],
            portfolio_size=command.portfolio_size,
            random_seed=command.random_seed,
            weights=weights,
        ),
        portfolio_size=command.portfolio_size,
        random_seed=command.random_seed,
        weights=weights,
        pins=pins,
        portfolio_status=result.status.value,
    )

    return HandlerResult(
        state=JobState.SUCCEEDED,
        summary={
            "match_run_id": str(record.id),
            "inputs_hash": record.inputs_hash,
            "registry_version": pins.registry_version,
            "registry_hash": pins.registry_hash,
            "optimizer_model_version": pins.optimizer_model_version,
            "solver_name": pins.solver_name,
            "solver_version": pins.solver_version,
            "route_estimate_source": pins.route_estimate_source,
            "route_estimate_version": pins.route_estimate_version,
            # The mode is reported here because `match_run` has no column for
            # it (OQ-CBA-028) and this event is where a follower of the job can
            # read it. `null` is a pre-ADR-0016 run, not the physical model.
            "scoring_mode": pins.scoring_mode,
            "scoring_mode_version": pins.scoring_mode_version,
            "portfolio_status": result.status.value,
            "candidates_considered": len(command.candidates),
            # The count, not the ids: the shortlist is card M10's surface and a
            # job event is not where it lands. A count says the search produced
            # something without publishing a recommendation through a channel no
            # policy row authorizes.
            "selected_count": len(result.selected_subject_ids),
            "already_recorded": record.was_already_recorded,
        },
    )


#: Module-level, like every other repository instance in this codebase
#: (``commands.py``'s ``_jobs``/``_outbox``, ``redrive.py``'s own ``_jobs``):
#: stateless, so one instance safely serves every call.
_reviews: Final[ReviewRepository] = ReviewRepository()

#: Same reasoning as ``_reviews`` above.
_match_runs: Final[MatchRunRepository] = MatchRunRepository()


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
            # Card M8a. It earns its place here before card M8b's routes exist
            # because it can genuinely execute: it solves a portfolio and
            # records the snapshot, and it genuinely refuses — an unapproved or
            # half-implemented registry is a terminal `registry_not_ready`. What
            # nothing can do yet is *submit* one over HTTP, which is M8b's card,
            # so registering it opens no surface.
            MATCH_RUN_COMMAND_TYPE: handle_match_run_create,
        }
    )
