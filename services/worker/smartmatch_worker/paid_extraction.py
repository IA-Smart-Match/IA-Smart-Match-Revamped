"""The one handler path that reserves money before spending it (ADR-0015 A1).

Architecture v1.1 §1.6 makes the worker the only place a durable command's work
actually happens, and ADR-0015 Amendment A1 adds the rule this module exists to
obey: **reserve the maximum estimated cost atomically before the paid call,
then reconcile the reservation to the actual cost after it.** Every other
handler in ``handlers.py`` spends nothing, so this is the first one whose
ordering matters in dollars rather than in tidiness.

## The order is the whole design

reserve (commit) -> dispatch -> settle (commit). A1 rejects the shape a
reviewer would build by default — read the ledger, decide, then call — because
*"a balance read under the ceiling authorizes a call whose cost lands after the
decision, so the ceiling is exceeded by one full call on every job that reaches
it"*. Here the debit is durable before the provider is addressed, which is why
:meth:`~smartmatch_persistence.spend.SpendReservationService.reserve` commits
in its own transaction and why this handler holds a **session of its own**,
taken from the injected factory, rather than using ``context.session``. A
handler may not commit the executor's transaction
(:class:`~smartmatch_worker.handlers.CommandContext`), and a reservation that
could be rolled back after the money moved is not a reservation.

## Every exit settles the reservation

Three ways out of the paid call, and each has a settle A1 names:

* it **returns** — ``reconcile`` records the real cost, overage included and
  never truncated;
* it **times out** — ``expire_on_timeout`` records the *reserved maximum* with
  ``actual_is_estimated=True``. A1: *"an in-worker timeout reconciles to the
  reserved maximum, held as spent, and explicitly flagged as estimated rather
  than actual"*. Not zero, which fails open; not the estimate presented as an
  actual, which fabricates a value;
* it **raises anything else** — the same conservative treatment, for the same
  reason: this side of the wire cannot tell a provider that never received the
  request from one that received it, billed, and then failed to answer.

Nothing here releases. ``release_before_dispatch`` exists one layer down for
the worker that refuses *before* addressing the provider; once
:func:`~smartmatch_domain.spend.dispatch` has been entered, releasing would
credit a ceiling for a call that may well have been paid for, which A1 forbids
without exception.

## Why a redelivery of a timed-out unit fails as ``failed_budget``

A timeout leaves the reservation ``expired_spent``, and A1's redelivery rule
refuses that state with
:attr:`~smartmatch_domain.spend.RefusalReason.EXPIRED_NO_RETRY` — no reuse and
no silent fresh debit. So the re-drive this handler's ``ProviderFailure``
invites will reach the reservation before it reaches the provider, be refused,
and end the job as ``failed_budget``. That is not a defect to route around; A1
names it as a cost: *"a crash after reserving ends that unit of work under the
current budget... an operator seeing failed_budget on a job that never
completed a call is seeing this rule, not a wrong ceiling."*

## Why nothing here is in ``default_registry`` by default

:func:`~smartmatch_worker.handlers.default_registry` is left exactly as it was,
and :func:`with_paid_extraction` composes a *new* registry that also routes
this command — so a worker acquires the ability to spend money only when a
deployment deliberately builds a provider, chooses ceilings, and asks. That
follows the registry's own rule — *"a command type appears here only once
something can genuinely execute it or genuinely refuse it; a handler added
ahead of its gate is a handler someone will trigger"* — and A1's ratification,
which authorizes the synthetic implementation and its verification while
leaving the A3 price, the credentials, and the ceilings as unmet external
dependencies. Composing also keeps this module importing ``handlers`` in one
direction only; having ``handlers`` reach back for the command type would make
a cycle out of a dependency that is genuinely one-way.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Final

from smartmatch_domain.jobs import JobState
from smartmatch_domain.spend import (
    AlreadyReconciledOutcome,
    ReconciledOutcome,
    Refused,
    SpendReservationReceipt,
    dispatch,
)
from smartmatch_persistence.spend import (
    ReservationRequest,
    SpendCeilings,
    SpendReservationService,
)
from smartmatch_providers.paid import (
    PaidCallOutcome,
    PaidExtractionProvider,
    SyntheticProviderTimeout,
    estimate_max_cost,
)
from sqlalchemy.orm import Session, sessionmaker

from smartmatch_worker.handlers import (
    BudgetFailure,
    CommandContext,
    CommandHandler,
    CommandRegistry,
    HandlerResult,
    PolicyFailure,
    ProviderFailure,
)

__all__ = [
    "DEFAULT_RESERVATION_LEASE",
    "PAID_EXTRACTION_COMMAND_TYPE",
    "PaidExtractionCommand",
    "build_paid_extraction_handler",
    "with_paid_extraction",
]

#: The command type this handler answers to. Named for what it spends money on
#: rather than for the provider, so swapping the adapter does not orphan every
#: persisted job row that named the old one.
PAID_EXTRACTION_COMMAND_TYPE: Final[str] = "extraction.paid_pages"

#: How long a reservation is held before the sweep reclaims it as
#: ``expired_spent``. Shorter than ``DEFAULT_JOB_LEASE`` on purpose: A1 records
#: that *"reservations strand capacity until they are reclaimed"* and that the
#: stranding *"is worst exactly when the system is unhealthy"*, so the window in
#: which a dead worker's debit sits against a tenant's ceiling should be bounded
#: by how long one paid call can plausibly take, not by how long a job may run.
#: A handler making several paid calls takes several reservations, each with its
#: own lease, rather than one long one.
DEFAULT_RESERVATION_LEASE: Final[timedelta] = timedelta(minutes=5)


@dataclass(frozen=True, slots=True)
class PaidExtractionCommand:
    """The parameters of one paid extraction, as persisted and read back.

    A separate type rather than a raw mapping, for the reason
    :class:`~smartmatch_worker.handlers.ImportCommand` gives: the payload is
    read from the database, and a row can predate this code, be written by an
    older release, or be edited by hand in an incident. Here the stakes are
    higher than a bad import — ``pages`` is multiplied by a price — so it is
    re-validated rather than trusted.

    Attributes:
        unit_of_work: What this reservation is *for*, at whatever granularity
            one paid call covers — see
            :func:`~smartmatch_domain.spend.derive_work_key`. It is the
            deterministic identity a redelivery is recognised by, so it must
            come from the durable payload and never be generated here: a
            handler minting a fresh identifier per delivery would make every
            redelivery a second debit.
        pages: How many prose pages the call will cover. The only input to the
            estimate.
    """

    unit_of_work: str
    pages: int


def _read_paid_extraction_command(payload: Mapping[str, Any]) -> PaidExtractionCommand:
    """Read a :class:`PaidExtractionCommand` out of a persisted payload.

    Collects every problem before raising, the same way
    ``handlers._read_import_command`` does, so a caller fixing a rejected
    command sees the whole list at once.

    ``pages`` is read, never coerced. ``int("12")`` and ``int(3.9)`` both
    succeed, and both mean somebody's unvalidated value just became a dollar
    figure. A bool is refused explicitly because ``isinstance(True, int)`` is
    ``True`` in Python, and ``True`` pages would reserve one page's worth of
    money for a payload nobody understood.

    Raises:
        PolicyFailure: with the reason ``invalid_command_payload``. Terminal on
            purpose, exactly as the import path argues: the payload is durable,
            so a re-drive re-reads identical bytes and fails identically, and
            ``failed_provider`` would invite an operator to press a button that
            cannot work.
    """
    problems: list[str] = []

    raw_unit = payload.get("unit_of_work")
    unit_of_work = raw_unit.strip() if isinstance(raw_unit, str) else ""
    if not unit_of_work:
        problems.append("unit_of_work is missing, is not a string, or is blank")

    raw_pages = payload.get("pages")
    pages = 0
    if isinstance(raw_pages, bool) or not isinstance(raw_pages, int):
        problems.append(f"pages must be an integer, got {type(raw_pages).__name__}")
    elif raw_pages < 1:
        problems.append(f"pages must be at least 1, got {raw_pages}")
    else:
        pages = raw_pages

    if problems:
        raise PolicyFailure(
            "the persisted paid-extraction payload cannot be read: " + "; ".join(problems),
            reason="invalid_command_payload",
        )
    return PaidExtractionCommand(unit_of_work=unit_of_work, pages=pages)


def _utcnow() -> datetime:
    """Return the current instant in UTC.

    Injected into the handler rather than called inside it so a test can pin
    the reservation instant, the lease expiry, and the settle instant to one
    known clock — the discipline ``ReservationRequest.now`` and
    ``RateLimiter.check`` already impose one layer down.
    """
    return datetime.now(UTC)


def build_paid_extraction_handler(
    *,
    session_factory: sessionmaker[Session],
    provider: PaidExtractionProvider,
    ceilings: SpendCeilings,
    lease: timedelta = DEFAULT_RESERVATION_LEASE,
    clock: Callable[[], datetime] = _utcnow,
) -> CommandHandler:
    """Build the handler that reserves, dispatches, and settles one paid call.

    A factory rather than a bare function, for the reason
    :func:`~smartmatch_worker.handlers.default_registry` is one: the
    collaborators are passed in and captured, so nothing is read from a
    module-level global and a test constructs a different handler instead of
    patching one. It also keeps the spend session out of
    :class:`~smartmatch_worker.handlers.CommandContext` — the reservation needs
    a transaction it may commit, and the executor's is not one a handler may
    commit.

    Args:
        session_factory: Produces the session the reservation and its settle
            own. One session serves the whole handler call; ``reserve``,
            ``reconcile``, and ``expire_on_timeout`` each commit it
            independently, which is what makes the debit durable across the
            provider round trip.
        provider: The adapter to call. Only
            :class:`~smartmatch_providers.paid.SyntheticPaidProvider` exists,
            and ``registry.build_paid_extraction_provider`` is the only
            approved way to obtain one.
        ceilings: The three ceilings this call is checked against.
            **Provisional while A3 is unverified** — A1: *"until A3 is
            confirmed against the actual provider, every ceiling computed from
            it is provisional"* — so they are injected by whoever is
            accountable for the numbers rather than defaulted here.
        lease: How long the reservation is held before the sweep reclaims it.
        clock: Returns "now". Injected for deterministic tests.

    Returns:
        A :data:`~smartmatch_worker.handlers.CommandHandler` for
        :data:`PAID_EXTRACTION_COMMAND_TYPE`.
    """

    def handle_paid_extraction(context: CommandContext) -> HandlerResult:
        """Execute one ``extraction.paid_pages`` under A1's reservation rule.

        Raises:
            PolicyFailure: ``command_payload_missing`` when the job carries no
                payload, ``invalid_command_payload`` when it carries one that
                cannot be read.
            BudgetFailure: whenever the reservation is refused — a ceiling
                reached, an expired or otherwise non-replayable terminal unit,
                or a lost race on the work key. A reconciled redelivery is the
                exception: it succeeds from the recorded actual without a new
                dispatch. Refusals are terminal, per A1: *"a reservation failure is a
                BudgetFailure, and therefore ends the job as failed_budget"*,
                and unlike a counting-quota refusal it does not self-heal at a
                window boundary. See :func:`_reserve_or_fail`.
            ProviderFailure: when the paid call times out or fails after the
                reservation has been settled conservatively.
        """
        payload = context.job.payload
        if payload is None:
            raise PolicyFailure(
                "extraction.paid_pages cannot be executed: this job has no persisted "
                "payload, so there is nothing to estimate a cost from. Reporting "
                "success would claim an extraction that did not happen; submit the "
                "command again against the current release.",
                reason="command_payload_missing",
            )
        command = _read_paid_extraction_command(payload)
        estimate = estimate_max_cost(command.pages)

        with session_factory() as session:
            service = SpendReservationService(session)
            reservation = _reserve_or_fail(
                service,
                context=context,
                command=command,
                estimate=estimate,
                provider_name=provider.name,
                ceilings=ceilings,
                lease=lease,
                now=clock(),
            )
            if isinstance(reservation, AlreadyReconciledOutcome):
                if reservation.actual_cost is None:
                    raise RuntimeError(
                        "reconciled spend reservation has no actual_cost; refusing to "
                        "invent a durable paid-call result"
                    )
                summary: dict[str, Any] = {
                    "unit_of_work": command.unit_of_work,
                    "pages": command.pages,
                    "actual_cost": str(reservation.actual_cost),
                    "actual_is_estimated": False,
                    "already_reconciled": True,
                }
                context.emit({"type": "progress", **summary})
                return HandlerResult(state=JobState.SUCCEEDED, summary=summary)
            return _dispatch_and_settle(
                service,
                context=context,
                command=command,
                receipt=reservation,
                provider=provider,
                clock=clock,
            )

    return handle_paid_extraction


def with_paid_extraction(registry: CommandRegistry, handler: CommandHandler) -> CommandRegistry:
    """Return a **new** registry that also routes the paid-extraction command.

    Composed rather than registered, and returned rather than mutated. The two
    choices answer the two things
    :class:`~smartmatch_worker.handlers.CommandRegistry` says about itself: it
    is immutable and passed in, because "a registry assembled by import side
    effects has contents that depend on import order, and a worker whose
    capabilities depend on import order is a worker whose capabilities nobody
    can state"; and a command type belongs in it "only once something can
    genuinely execute it or genuinely refuse it".

    So this function is the deliberate act. A deployment that has built a
    provider, chosen ceilings it is accountable for, and accepted that A3 is
    still unverified calls it; every other worker keeps
    :func:`~smartmatch_worker.handlers.default_registry`'s output unchanged and
    has no command that can spend money. Refusing a
    ``extraction.paid_pages`` delivery is then the registry's existing
    behavior — an unregistered command fails the job explicitly — rather than a
    second refusal written here.

    Args:
        registry: The base registry, normally
            :func:`~smartmatch_worker.handlers.default_registry`'s. Left
            untouched.
        handler: What :func:`build_paid_extraction_handler` returned.

    Returns:
        A new :class:`~smartmatch_worker.handlers.CommandRegistry` carrying
        everything ``registry`` carried plus
        :data:`PAID_EXTRACTION_COMMAND_TYPE`.

    Raises:
        ValueError: if ``registry`` already routes
            :data:`PAID_EXTRACTION_COMMAND_TYPE`. Silently replacing it would
            mean a worker running a handler nobody at the call site chose,
            against ceilings nobody at the call site passed.
    """
    if PAID_EXTRACTION_COMMAND_TYPE in registry.handlers:
        raise ValueError(
            f"{PAID_EXTRACTION_COMMAND_TYPE!r} is already registered; refusing to "
            "replace a spending handler with another one, because the ceilings and "
            "the provider the existing one captured are not visible from here"
        )
    return CommandRegistry(handlers={**registry.handlers, PAID_EXTRACTION_COMMAND_TYPE: handler})


def _reserve_or_fail(
    service: SpendReservationService,
    *,
    context: CommandContext,
    command: PaidExtractionCommand,
    estimate: Decimal,
    provider_name: str,
    ceilings: SpendCeilings,
    lease: timedelta,
    now: datetime,
) -> SpendReservationReceipt | AlreadyReconciledOutcome:
    """Take the reservation, or end the job as ``failed_budget``.

    The refusal is emitted as a job event *before* it is raised, so that the
    estimate, the page count, and the refusal reason reach the progress stream
    a person may already be watching, not only the terminal failure event. A
    ceiling that stops work silently is a ceiling operators learn about from a
    support ticket.

    Raises:
        BudgetFailure: on any refusal, carrying the domain's stable
            :class:`~smartmatch_domain.spend.RefusalReason` as its ``reason``
            so a consumer branches on the vocabulary both layers already share
            rather than on prose.
    """
    outcome = service.reserve(
        ReservationRequest(
            tenant_id=context.job.tenant_id,
            job_id=context.job.id,
            provider=provider_name,
            unit_of_work=command.unit_of_work,
            estimate=estimate,
            now=now,
            lease=lease,
        ),
        ceilings,
    )
    if isinstance(outcome, Refused):
        context.emit(
            {
                "type": "progress",
                "detail": (
                    f"spend reservation refused for {command.pages} page(s): {outcome.detail}"
                ),
                "reservation_refused": outcome.reason.value,
                "estimate": str(estimate),
            }
        )
        raise BudgetFailure(
            f"no paid call was made: reserving the estimated maximum {estimate} for "
            f"{command.pages} page(s) was refused — {outcome.detail}. A spend ceiling "
            "does not clear at a window boundary the way a rate limit does, so this "
            "job is terminal until a ceiling moves.",
            reason=outcome.reason.value,
        )

    if isinstance(outcome, AlreadyReconciledOutcome):
        return outcome

    context.emit(
        {
            "type": "progress",
            "detail": (
                f"reserved an estimated maximum of {estimate} for {command.pages} "
                f"page(s) before dispatching to {provider_name}"
            ),
            "reservation_id": str(outcome.reservation_id),
            "estimate": str(estimate),
            "estimated": True,
        }
    )
    return outcome


def _dispatch_and_settle(
    service: SpendReservationService,
    *,
    context: CommandContext,
    command: PaidExtractionCommand,
    receipt: SpendReservationReceipt,
    provider: PaidExtractionProvider,
    clock: Callable[[], datetime],
) -> HandlerResult:
    """Make the paid call through the receipt seam, then settle it.

    The call goes through :func:`~smartmatch_domain.spend.dispatch` rather than
    straight to the adapter, so the receipt is checked at runtime as well as by
    the type checker: A1 wants *"a paid call cannot be made by a path that
    never reserved"* to hold even for a caller that reached here through an
    untyped path.

    The broad ``except Exception`` is deliberate and is not a swallowed error —
    it re-raises. What it refuses to do is let an unanticipated exception carry
    the reservation out of this function unsettled, leaving a debit no live
    worker will ever reconcile and a tenant's ceiling stranded until the sweep
    reaches it. The settle is conservative for the reason A1 gives about
    timeouts, which applies identically to any failure after dispatch began.

    Raises:
        ProviderFailure: when the call times out or fails. Re-drivable in the
            executor's mapping, and see the module docstring for why the
            re-drive of a *settled* unit then ends as ``failed_budget`` — that
            is A1's rule showing through, not a mislabeled failure.
    """
    try:
        outcome: PaidCallOutcome = dispatch(
            receipt, lambda proof: provider.extract(proof, pages=command.pages)
        )
    except SyntheticProviderTimeout as exc:
        _settle_without_an_actual(service, context=context, receipt=receipt, now=clock())
        raise ProviderFailure(
            f"the paid call timed out after {command.pages} page(s): {exc}. The "
            f"reserved maximum {receipt.estimate} is held as spent and flagged "
            "estimated rather than actual — the provider may have completed and "
            "billed before this worker stopped waiting.",
            reason="paid_call_timed_out",
        ) from exc
    except Exception as exc:
        _settle_without_an_actual(service, context=context, receipt=receipt, now=clock())
        raise ProviderFailure(
            f"the paid call failed after {command.pages} page(s): {exc}. The reserved "
            f"maximum {receipt.estimate} is held as spent and flagged estimated — a "
            "failure this side of the wire cannot prove the provider was not billed.",
            reason="paid_call_failed",
        ) from exc

    return _reconcile_actual(
        service, context=context, command=command, receipt=receipt, outcome=outcome, now=clock()
    )


def _settle_without_an_actual(
    service: SpendReservationService,
    *,
    context: CommandContext,
    receipt: SpendReservationReceipt,
    now: datetime,
) -> None:
    """Hold the reserved maximum as spent, flagged estimated (A1's timeout rule).

    A refusal here means the sweep or another settle reached the row first, and
    that row is already ``expired_spent`` at the same figure by the same rule —
    so there is nothing to correct and nothing to raise about. It is recorded
    on the event stream rather than passed over in silence, because "somebody
    else settled this" is exactly the kind of fact an operator reconstructing
    an incident needs and cannot recover afterwards.
    """
    settled = service.expire_on_timeout(receipt, now=now)
    if isinstance(settled, Refused):
        context.emit(
            {
                "type": "progress",
                "detail": (
                    "the reservation was already settled by another path before this "
                    f"timeout could record it: {settled.detail}"
                ),
                "reservation_id": str(receipt.reservation_id),
                "timeout_settle_refused": settled.reason.value,
            }
        )
        return
    context.emit(
        {
            "type": "progress",
            "detail": (
                f"no actual cost is available; holding the reserved maximum "
                f"{settled.spent_amount} as spend, flagged estimated"
            ),
            "reservation_id": str(receipt.reservation_id),
            "spent": str(settled.spent_amount),
            "estimated": settled.is_estimated,
        }
    )


def _reconcile_actual(
    service: SpendReservationService,
    *,
    context: CommandContext,
    command: PaidExtractionCommand,
    receipt: SpendReservationReceipt,
    outcome: PaidCallOutcome,
    now: datetime,
) -> HandlerResult:
    """Record the call's real cost, and report what the ledger now holds.

    Three shapes come back, and each means something different to a person
    reading the result:

    * :class:`~smartmatch_domain.spend.ReconciledOutcome` — this call settled
      it. ``succeeded``, with the overage reported when there was one; A1
      requires an overage to *"be visible rather than absorbed"*, so it appears
      in the summary rather than only in a review row.
    * :class:`~smartmatch_domain.spend.AlreadyReconciledOutcome` — a redelivery
      of an already-settled unit. Still ``succeeded``, and A1's own idiom for
      it: *"a no-op returning the recorded outcome"*.
    * :class:`~smartmatch_domain.spend.Refused` — the sweep or a concurrent
      settle won the race, so the ledger holds the *reserved maximum* flagged
      estimated instead of this call's actual. The extraction genuinely
      happened, so this is not a failure; the accounting is genuinely less
      precise than it should be, so it is not a plain success either. That is
      what ``partial`` is for (v1.1 §3.6 N2), and reporting it as ``succeeded``
      would hide a wrong figure behind a green result.
    """
    settled = service.reconcile(receipt, actual_cost=outcome.actual_cost, now=now)
    summary: dict[str, Any] = {
        "unit_of_work": command.unit_of_work,
        "pages": command.pages,
        "provider": outcome.provider,
        "reservation_id": str(receipt.reservation_id),
        "estimate": str(receipt.estimate),
        "actual_cost": str(outcome.actual_cost),
        "actual_is_estimated": False,
    }

    if isinstance(settled, Refused):
        summary["actual_is_estimated"] = True
        summary["ledger_records"] = str(receipt.estimate)
        summary["reconcile_refused"] = settled.reason.value
        summary["detail"] = (
            f"the extraction completed and cost {outcome.actual_cost}, but another "
            f"path settled the reservation first ({settled.detail}), so the ledger "
            "holds the reserved maximum flagged estimated rather than this actual"
        )
        context.emit({"type": "progress", **summary})
        return HandlerResult(state=JobState.PARTIAL, summary=summary)

    overage = settled.overage if isinstance(settled, ReconciledOutcome) else None
    summary["already_reconciled"] = isinstance(settled, AlreadyReconciledOutcome)
    summary["overage"] = str(overage) if overage is not None else None
    summary["detail"] = (
        f"{command.pages} page(s) extracted by {outcome.provider}; reserved "
        f"{receipt.estimate}, actual {outcome.actual_cost}"
        + (
            f", which exceeded the reserved maximum by {overage} and is recorded in "
            "full and flagged for review"
            if overage is not None
            else ""
        )
    )
    context.emit({"type": "progress", **summary})
    return HandlerResult(state=JobState.SUCCEEDED, summary=summary)
