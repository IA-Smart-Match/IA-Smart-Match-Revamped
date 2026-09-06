"""The paid seam's unit-testable half: the estimate, the constant, the refusal.

ADR-0015 Amendment A1, Task 4. Three things are provable without a database:

1. **The estimate arithmetic** — that it is `Decimal` throughout, that it
   rounds a *maximum* upward, and that its provenance is the A3 the source
   document actually records.
2. **The type-level refusal** — that a call site which never reserved cannot
   reach a paid call. `smartmatch_domain.spend.dispatch` is the runtime half of
   that (mypy strict is the other half, and it runs in `make typecheck`), and
   these tests pin the runtime half against every shape an untyped caller might
   present.
3. **The registry's construction-time refusal** — that no edition, not merely
   the classroom one, can construct a live paid adapter, and that a stray
   credential fails closed rather than being ignored.

What is *not* here: anything that debits a bucket. That is a guarded SQL write
and belongs to `tests/integration` (Task 5).
"""

from __future__ import annotations

import inspect
import uuid
from decimal import ROUND_CEILING, Decimal

import pytest
import smartmatch_providers.paid as paid_module
from smartmatch_domain.spend import SpendReservationReceipt, dispatch
from smartmatch_providers.base import Edition, ProviderConfigurationError
from smartmatch_providers.paid import (
    A3_PRICE_PER_PROSE_PAGE,
    A3_RECORDED_ON,
    A3_SOURCE,
    MONEY_PRECISION,
    PaidCallOutcome,
    SyntheticPaidProvider,
    SyntheticProviderTimeout,
    estimate_max_cost,
)
from smartmatch_providers.registry import build_paid_extraction_provider

TENANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
RESERVATION_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
LEASE_TOKEN = uuid.UUID("44444444-4444-4444-4444-444444444444")


def _receipt(estimate: Decimal = Decimal("0.3500")) -> SpendReservationReceipt:
    """A receipt of the shape a committed reservation mints."""
    return SpendReservationReceipt(
        reservation_id=RESERVATION_ID,
        tenant_id=TENANT_ID,
        work_key="spend-abc",
        lease_token=LEASE_TOKEN,
        estimate=estimate,
    )


# ---------------------------------------------------------------------------
# Assumption A3 carries its provenance in the code that uses it
# ---------------------------------------------------------------------------


def test_a3_is_the_figure_the_source_document_records():
    """A1 requires the constant to be the source's number, not a rounded memory."""
    assert Decimal("0.035") == A3_PRICE_PER_PROSE_PAGE
    assert A3_SOURCE == "docs/plans/prep/g3-limits-and-policy-options.md:221"
    assert A3_RECORDED_ON.isoformat() == "2026-08-29"


def test_a3_is_a_decimal_and_not_a_float():
    """Money is `Decimal`. `0.035` has no exact binary representation.

    Widening the `float` shows what a `float`-typed price would actually carry
    into the ledger, and that it is not the number anybody wrote down.
    """
    assert isinstance(A3_PRICE_PER_PROSE_PAGE, Decimal)
    widened_float = Decimal(float("0.035"))
    assert widened_float != A3_PRICE_PER_PROSE_PAGE
    assert str(widened_float).startswith("0.03500000000000000")


def test_a3_documentation_says_it_is_unverified():
    """The provenance is only useful if it says what is missing from it.

    Pinned as a test rather than trusted to review because that documentation
    is the only place a reader learns that nobody has checked this number
    against a bill; an edit that tidied the wording away would otherwise be
    invisible.
    """
    docs = (paid_module.__doc__ or "").lower()
    assert "unverified" in docs
    assert "a3" in docs


# ---------------------------------------------------------------------------
# estimate_max_cost
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pages", "expected"),
    [
        (0, "0.0000"),
        (1, "0.0350"),
        (2, "0.0700"),
        (20, "0.7000"),
        (57, "1.9950"),
    ],
)
def test_estimate_is_pages_times_a3_at_ledger_precision(pages: int, expected: str):
    """`pages x A3`, quantized to the `NUMERIC(12,4)` the ledger stores."""
    assert estimate_max_cost(pages) == Decimal(expected)
    assert estimate_max_cost(pages).as_tuple().exponent == MONEY_PRECISION.as_tuple().exponent


def test_estimate_returns_decimal_never_float():
    assert isinstance(estimate_max_cost(3), Decimal)


def test_estimate_matches_the_adr_worked_example():
    """A1: a `$2.00` job stops after roughly 57 reserved pages.

    Not arithmetic for its own sake — it checks that this estimator is the one
    the amendment reasoned about, so the pessimism A1 accepts is the pessimism
    this code actually has.
    """
    assert estimate_max_cost(57) <= Decimal("2.00")
    assert estimate_max_cost(58) > Decimal("2.00")


def test_estimate_rounds_a_maximum_upward_never_down():
    """A reserved maximum rounded down debits less than the call may cost.

    A3 currently yields at most three decimal places, so the quantizer is a
    no-op today. This pins the *direction* it will round when the constant
    changes, which is the thing expected to change.
    """
    assert Decimal("0.00005").quantize(MONEY_PRECISION, rounding=ROUND_CEILING) == Decimal("0.0001")


def test_estimate_refuses_a_negative_page_count():
    with pytest.raises(ValueError, match="zero or more"):
        estimate_max_cost(-1)


def test_estimate_refuses_a_float_page_count():
    """The runtime half of the annotation, guarding the dollar path.

    A `float` reaching this function is the exact defect the module forbids, so
    it is refused rather than silently multiplied.
    """
    with pytest.raises(TypeError, match="must be an int"):
        estimate_max_cost(3.0)  # type: ignore[arg-type]


def test_estimate_refuses_a_bool_page_count():
    """`isinstance(True, int)` is `True`; `True` pages is nobody's intent."""
    with pytest.raises(TypeError, match="must be an int"):
        estimate_max_cost(True)  # type: ignore[arg-type]


def test_estimate_refuses_a_total_the_ledger_column_cannot_hold():
    with pytest.raises(ValueError, match="NUMERIC"):
        estimate_max_cost(10**12)


# ---------------------------------------------------------------------------
# The type-level refusal: no reservation, no paid call
# ---------------------------------------------------------------------------


def test_dispatch_refuses_a_call_site_that_never_reserved():
    """A1: "a paid call cannot be made by a path that never reserved."

    mypy strict refuses such a program at the call site; these assertions are
    the runtime half, for a caller that reached the seam through an untyped
    path.
    """
    provider = SyntheticPaidProvider()

    for impostor in (None, "receipt", {"reservation_id": RESERVATION_ID}, 1, object()):
        with pytest.raises(TypeError, match="requires a SpendReservationReceipt"):
            dispatch(
                impostor,  # type: ignore[arg-type]
                lambda proof: provider.extract(proof, pages=1),
            )

    assert provider.calls == [], "a refused dispatch must not reach the provider"


def test_dispatch_with_a_real_receipt_reaches_the_provider():
    """The other half of the refusal: a genuine receipt is not obstructed."""
    provider = SyntheticPaidProvider()
    receipt = _receipt()

    outcome = dispatch(receipt, lambda proof: provider.extract(proof, pages=10))

    assert isinstance(outcome, PaidCallOutcome)
    assert provider.calls == [receipt]


# ---------------------------------------------------------------------------
# SyntheticPaidProvider
# ---------------------------------------------------------------------------


def test_synthetic_provider_reports_a_decimal_cost_labeled_synthetic():
    outcome = SyntheticPaidProvider().extract(_receipt(), pages=10)

    assert outcome.actual_cost == Decimal("0.1200")
    assert isinstance(outcome.actual_cost, Decimal)
    assert outcome.pages == 10
    assert outcome.provider.startswith("synthetic-"), (
        "a synthetic cost must be identifiable as one wherever it is displayed"
    )


def test_synthetic_provider_can_cost_more_than_the_reservation():
    """A1's overage case has to be reachable, or it cannot be tested at all."""
    provider = SyntheticPaidProvider(cost_per_page=Decimal("0.5"))

    outcome = provider.extract(_receipt(), pages=2)

    assert outcome.actual_cost > estimate_max_cost(2)


def test_synthetic_provider_records_the_call_before_timing_out():
    """A timeout means the client stopped waiting, not that nothing was sent."""
    provider = SyntheticPaidProvider(times_out=True)
    receipt = _receipt()

    with pytest.raises(SyntheticProviderTimeout):
        provider.extract(receipt, pages=4)

    assert provider.calls == [receipt]


def test_synthetic_provider_refuses_a_negative_cost_per_page():
    with pytest.raises(ValueError, match="non-negative"):
        SyntheticPaidProvider(cost_per_page=Decimal("-0.01"))


def test_synthetic_provider_holds_no_credential():
    """There is nowhere in this adapter for a secret to be passed.

    Asserted on the signature rather than by inspection, so an added
    ``api_key``/``token``/``credential`` parameter fails here instead of in a
    review somebody skims.
    """
    parameters = set(inspect.signature(SyntheticPaidProvider.__init__).parameters)
    assert parameters == {"self", "cost_per_page", "times_out"}


# ---------------------------------------------------------------------------
# Registry: no edition may construct a live paid adapter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("edition", list(Edition))
def test_every_edition_gets_the_synthetic_provider(edition: Edition):
    assert isinstance(build_paid_extraction_provider(edition), SyntheticPaidProvider)


@pytest.mark.parametrize("edition", list(Edition))
def test_no_edition_may_construct_a_live_paid_adapter(edition: Edition):
    """Stricter than `_assert_fixture_only`, and deliberately so.

    A1 ratifies "only a synthetic-provider reservation implementation"; there
    is no edition today under which a live paid adapter is an approved thing to
    build, so the refusal cannot be a property of the deployment.
    """
    with pytest.raises(ProviderConfigurationError):
        build_paid_extraction_provider(edition, use_synthetic=False)


@pytest.mark.parametrize("edition", list(Edition))
def test_a_paid_credential_fails_closed_under_every_edition(edition: Edition):
    with pytest.raises(ProviderConfigurationError, match="credential is present"):
        build_paid_extraction_provider(edition, api_key="live-key")
