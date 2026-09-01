"""The paid-extraction seam: a price assumption, an estimate, and a synthetic adapter.

ADR-0015 Amendment A1. A1 ratifies **a synthetic-provider reservation
implementation and its verification as the next slice**, and explicitly does
*not* ratify the price assumption A3, production credentials, or production
spend ceilings — those three "remain external dependencies". This module is
therefore the whole paid surface the repository is allowed to have: a named,
dated, unverified price constant; the arithmetic that turns it into a reserved
maximum; and a fixture-backed adapter that cannot reach a network and never
reads a credential.

## Why the price lives here and not in a settings module

A1 requires that the price constant be **"named as an assumption in the code
that uses it — carrying its identifier (A3), its source, and the date it was
recorded — not left as a bare float in a settings module where the next reader
takes it for a measured figure."** :data:`A3_PRICE_PER_PROSE_PAGE` carries that
provenance in its own docstring, immediately above the only function that
multiplies by it. A settings key named ``price_per_page`` would satisfy every
mechanical review and lose the one fact that matters: nobody has ever checked
this number against a bill.

## Why the receipt is a required parameter and not a keyword with a default

A1: *"a paid call cannot be made by a path that never reserved, and a type
checker says so at the call site"*. :meth:`SyntheticPaidProvider.extract` takes
a :class:`~smartmatch_domain.spend.SpendReservationReceipt` as its first
positional parameter, with no default, not ``| None``, and not ``Any`` — a
value only a committed reservation ever mints. Under strict mypy a call site
that never reserved cannot construct the argument and the program does not
type-check. The runtime half of the same refusal lives in
:func:`smartmatch_domain.spend.dispatch`, which every caller here routes
through; this module never invokes a provider on a caller's behalf.

## Why the interfaces are declared here rather than in ``base.py``

``smartmatch_providers.base`` is the Foundation scaffold's ratified interface
surface. Nothing in this module is ratified for live use, and keeping the
protocol, the adapter, the price, and the estimate in one file means the whole
unratified surface can be read — or deleted, if A3 does not survive
verification — in one place, rather than leaving an orphan protocol in the
module a reader takes for settled architecture.

## Money is ``Decimal``

Every figure here is a :class:`~decimal.Decimal`, quantized to the four decimal
places ``NUMERIC(12,4)`` stores (migration ``0010``). There is no ``float`` on
any dollar path in this module, deliberately: binary floating point cannot
represent ``0.035``, and a ledger whose arithmetic drifts is a ledger that
cannot be reconciled against an invoice.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_CEILING, Decimal
from typing import Final, Protocol, runtime_checkable

from smartmatch_domain.spend import SpendReservationReceipt

__all__ = [
    "A3_PRICE_PER_PROSE_PAGE",
    "A3_RECORDED_ON",
    "A3_SOURCE",
    "MONEY_PRECISION",
    "SYNTHETIC_ACTUAL_PER_PROSE_PAGE",
    "PaidCallOutcome",
    "PaidExtractionProvider",
    "SyntheticPaidProvider",
    "SyntheticProviderTimeout",
    "estimate_max_cost",
]

#: The scale ``spend_ceiling_bucket`` and ``spend_reservation`` store money at
#: (``NUMERIC(12,4)``, migration ``0010``). Every figure this module returns is
#: quantized to it, so what a caller reserves is exactly what the column holds
#: — an unquantized value would be rounded by the database instead, and a
#: reserved maximum silently rounded *down* is a ceiling debited for less than
#: the call may cost.
MONEY_PRECISION: Final[Decimal] = Decimal("0.0001")

#: The largest value ``NUMERIC(12,4)`` can hold. A page count large enough to
#: exceed it is refused here, where the caller can be told which input was
#: unreasonable, rather than at the ``INSERT`` as an opaque numeric overflow.
_MAX_STORABLE_AMOUNT: Final[Decimal] = Decimal("99999999.9999")

A3_PRICE_PER_PROSE_PAGE: Final[Decimal] = Decimal("0.035")
"""Assumption **A3** — LLM extraction price, **$0.035 per prose page**.

**This is an assumption, not a measurement, and it is unverified against any
provider bill.**

:Identifier: A3
:Source: ``docs/plans/prep/g3-limits-and-policy-options.md:221``
:Recorded: 2026-08-29 (that document's own ``Date:`` header; committed
    2026-08-30)
:Status: **unverified**

The source states it in full as: *"A3 — LLM extraction price: $0.035 per prose
page, from ~8,000 input tokens (a trimmed page) at ~$3/M and ~600 output tokens
at ~$15/M ~= $0.024 + $0.009. (Mid-tier frontier model list pricing, from
general knowledge, not verified. Confirm against the actual provider and the
actual chosen model before this number is ratified.)"* It is a token-count
estimate multiplied by remembered list prices — no provider was called, no
invoice was read, and no model was chosen.

ADR-0015 A1 keeps it that way on purpose. Its ratification note records that
approval *"does not ratify, confirm, or make enforceable: the live-provider
price assumption A3... A3 remains unverified against any actual provider"*, and
its *Where the estimate comes from* section makes two demands this constant
exists to satisfy:

* the price must be **named as an assumption in the code that uses it**,
  carrying its identifier, source, and date — "not left as a bare float in a
  settings module where the next reader takes it for a measured figure"; and
* **"until A3 is confirmed against the actual provider, every ceiling computed
  from it is provisional"** — including L21's per-job figure. Confirming A3 is
  a prerequisite of the cost-ceiling work, not a follow-up to it.

Two consequences for anyone about to change this line. Raising or lowering the
number without a bill in hand replaces one unverified figure with another and
buys nothing. And because :func:`estimate_max_cost` reserves a *maximum*, an A3
that is too high makes ceilings bind before real spend warrants it (A1's own
worked example: a ``$2.00`` job stops after ~57 pages while its real spend is
nearer ``$0.68``), while an A3 that is too low is the direction that overshoots
a ceiling — which is the defect A1 exists to close.
"""

#: The source document and line the assumption above was read from, kept as a
#: value as well as prose so a spend log or an operator view can print its
#: provenance beside the figure instead of asking a reader to trust it.
A3_SOURCE: Final[str] = "docs/plans/prep/g3-limits-and-policy-options.md:221"

#: The date :data:`A3_PRICE_PER_PROSE_PAGE` was recorded in that source. Not
#: the date it was verified — it has not been.
A3_RECORDED_ON: Final[date] = date(2026, 8, 29)

#: What one page costs the synthetic adapter below. ADR-0015 A1's worked
#: example uses *"a typical page actually costs $0.012"* against the ``$0.035``
#: maximum, and this reuses that figure so a synthetic reconciliation exercises
#: the ordinary case A1 describes — an actual materially under its reservation
#: — rather than the degenerate one where estimate and actual coincide and a
#: bug in either could not be seen. It is a **fixture value**, invented for
#: this adapter; it is not evidence about any provider's pricing.
SYNTHETIC_ACTUAL_PER_PROSE_PAGE: Final[Decimal] = Decimal("0.012")


class SyntheticProviderTimeout(TimeoutError):
    """The synthetic adapter's stand-in for a call that stopped being waited on.

    Exists so the timeout branch A1 requires — *"an in-worker timeout
    reconciles to the reserved maximum, held as spent, and explicitly flagged
    as estimated rather than actual"* — is reachable in tests and in the worker
    without a real provider, a real network, or a real clock. A timeout is the
    one outcome with no actual cost available: the provider may well have
    completed and billed before the client gave up, so the caller must not
    reach for zero and must not present the estimate as an actual.
    """


@dataclass(frozen=True, slots=True)
class PaidCallOutcome:
    """What one synthetic paid call reports back.

    Attributes:
        actual_cost: What the call cost, quantized to :data:`MONEY_PRECISION`.
            An **actual**, in A1's sense — the figure a reconciliation records
            in the ``actual_cost`` column with ``actual_is_estimated=False``.
            For this adapter it is synthetic rather than billed, which is what
            ``provider`` says out loud.
        pages: How many prose pages the call covered. Carried so a caller can
            check the cost it is about to reconcile against the work it
            actually got, rather than trusting a bare number.
        provider: The adapter's name. Always prefixed ``synthetic-``, the same
            discipline ``FixtureEmailProvider`` applies to its message ids: a
            synthetic figure must be identifiable as one in a log, in the
            ledger, and in a screenshot, long after this object is gone.
    """

    actual_cost: Decimal
    pages: int
    provider: str


@runtime_checkable
class PaidExtractionProvider(Protocol):
    """The narrow interface a paid extraction adapter may expose.

    One method, and it cannot be called without a receipt. Narrow by the same
    argument ``smartmatch_providers.base`` makes for its own protocols: an
    adapter can do exactly what the interface names and nothing else, which is
    what makes the construction-time refusal in
    :func:`smartmatch_providers.registry.build_paid_extraction_provider`
    meaningful rather than advisory.
    """

    name: str

    def extract(self, receipt: SpendReservationReceipt, *, pages: int) -> PaidCallOutcome:
        """Perform one paid extraction against a committed reservation."""
        ...


def estimate_max_cost(pages: int) -> Decimal:
    """Return the reserved maximum for extracting ``pages`` prose pages.

    ``pages x A3`` — nothing subtler, because a subtler estimator built on an
    unverified price would only disguise where the uncertainty is. A1 requires
    the reservation to be of an **estimated maximum**, so this rounds *upward*
    to :data:`MONEY_PRECISION` (``ROUND_CEILING``): a maximum rounded down
    would debit the ceiling for less than the call may cost, which is the
    overshoot direction A1 exists to close. At ``$0.035`` the product never has
    more than three decimal places, so the rounding is a no-op today and is
    written anyway, because it is the price constant — not this function — that
    is expected to change.

    Reserving the maximum is deliberately pessimistic and A1 names the cost: a
    tenant hits a ceiling *before their actual spend warrants it*, and the gap
    is exactly this estimator's caution. That is accepted because refusing an
    affordable call is recoverable and permitting an unaffordable one is not.

    Args:
        pages: Prose pages the call will cover. Zero is legal and returns
            ``0.0000`` — a unit of work that turns out to have nothing to
            extract still reserves, so the reservation exists to be reconciled
            or released rather than being skipped and leaving a paid call with
            no ledger row.

    Returns:
        The maximum, as a :class:`~decimal.Decimal` quantized to
        ``NUMERIC(12,4)``. Never a ``float``.

    Raises:
        TypeError: if ``pages`` is not an ``int``. The runtime half of the
            annotation, for the same reason
            :func:`smartmatch_domain.spend.dispatch` keeps one: Python does not
            enforce annotations, and a ``float`` slipping in here is precisely
            the ``float``-on-a-dollar-path defect this module forbids.
        ValueError: if ``pages`` is negative — a negative reservation is a
            credit, and A1 has no such transition — or if the product exceeds
            what ``NUMERIC(12,4)`` can store.
    """
    if isinstance(pages, bool) or not isinstance(pages, int):
        raise TypeError(f"pages must be an int, got {type(pages).__name__}")
    if pages < 0:
        raise ValueError(f"pages must be zero or more, got {pages}")

    maximum = (A3_PRICE_PER_PROSE_PAGE * pages).quantize(MONEY_PRECISION, rounding=ROUND_CEILING)
    if maximum > _MAX_STORABLE_AMOUNT:
        raise ValueError(
            f"{pages} pages at {A3_PRICE_PER_PROSE_PAGE} each is {maximum}, which "
            f"exceeds the {_MAX_STORABLE_AMOUNT} a NUMERIC(12,4) ledger column can "
            "hold; a request this large is a defect upstream, not a reservation"
        )
    return maximum


class SyntheticPaidProvider:
    """A fixture-backed stand-in for a paid extraction provider.

    **Makes no network call, reads no credential, and holds no client.** There
    is nowhere in this class for a secret to be passed, which is the point: A1
    authorizes *"only a synthetic-provider reservation implementation"*, and an
    adapter carrying an unused ``api_key`` parameter is one edit away from not
    being synthetic any more.

    Like ``FixtureEmailProvider`` it records what it was asked to do so tests
    can assert on it, and like every fixture in this codebase it is
    deliberately not a demo-data source: its cost is labeled synthetic in the
    outcome it returns, because a synthetic dollar figure presented as a billed
    one is the fabricated-value defect (G3 §7 MP-1) wearing a currency symbol.

    Args:
        cost_per_page: What one page costs this fixture. Defaults to
            :data:`SYNTHETIC_ACTUAL_PER_PROSE_PAGE`; a test wanting to exercise
            A1's overage rule — *"record the overage as actual spend, never
            silently truncate it"* — passes something above
            :data:`A3_PRICE_PER_PROSE_PAGE`.
        times_out: When ``True`` every call raises
            :class:`SyntheticProviderTimeout` instead of returning, so the
            timeout branch can be exercised deterministically. It raises
            *after* recording the call, because a real timeout means the client
            stopped waiting — not that the provider never received the request,
            and A1's whole timeout rule follows from that distinction.

    Raises:
        ValueError: if ``cost_per_page`` is negative. A paid call costs zero or
            more; a credit is not a negative call cost, which is the same rule
            :attr:`~smartmatch_domain.spend.RefusalReason.NEGATIVE_ACTUAL_COST`
            enforces one layer down.
    """

    name = "synthetic-paid-extraction"

    def __init__(
        self,
        *,
        cost_per_page: Decimal = SYNTHETIC_ACTUAL_PER_PROSE_PAGE,
        times_out: bool = False,
    ) -> None:
        if cost_per_page < 0:
            raise ValueError(f"cost_per_page must be non-negative, got {cost_per_page}")
        self._cost_per_page = cost_per_page
        self._times_out = times_out
        #: Every receipt this adapter was called with, in call order. A test
        #: asserting "the paid call happened exactly once for this reservation"
        #: reads this rather than a mock's call count.
        self.calls: list[SpendReservationReceipt] = []

    def extract(self, receipt: SpendReservationReceipt, *, pages: int) -> PaidCallOutcome:
        """Perform one synthetic extraction and report its synthetic cost.

        ``receipt`` is positional, required, and typed as
        :class:`~smartmatch_domain.spend.SpendReservationReceipt` — see the
        module docstring for why it is none of ``None``-able, defaulted, or
        ``Any``. This method does not re-validate it: the runtime check belongs
        to :func:`smartmatch_domain.spend.dispatch`, which is the seam every
        caller reaches this method through, and duplicating it here would put
        the authorization decision in two places that could disagree.

        Args:
            receipt: Proof that the maximum cost of this call is already
                debited against all three ceilings and committed.
            pages: How many prose pages to extract. Must match the count the
                reservation's estimate was computed from; this adapter cannot
                check that, and the caller that computed both can.

        Returns:
            A :class:`PaidCallOutcome` whose ``actual_cost`` is an actual in
            A1's sense — the figure to reconcile with — quantized to
            :data:`MONEY_PRECISION`.

        Raises:
            SyntheticProviderTimeout: when the adapter was constructed with
                ``times_out=True``.
            ValueError: if ``pages`` is negative.
        """
        if pages < 0:
            raise ValueError(f"pages must be zero or more, got {pages}")
        self.calls.append(receipt)
        if self._times_out:
            raise SyntheticProviderTimeout(
                f"synthetic provider stopped being waited on after {pages} page(s) for "
                f"reservation {receipt.reservation_id}; no actual cost is available"
            )
        return PaidCallOutcome(
            actual_cost=(self._cost_per_page * pages).quantize(
                MONEY_PRECISION, rounding=ROUND_CEILING
            ),
            pages=pages,
            provider=self.name,
        )
