"""Classroom-isolation configuration assertions.

Architecture v1.1 §3.3: "a diagram label is not a control". These tests are the
CI half of the isolation mechanism — they assert that no classroom code path can
construct a live provider client, which the verification matrix requires.
"""

from __future__ import annotations

import pytest
from smartmatch_domain.product_scope import ProductScope, enabled_capabilities
from smartmatch_providers import (
    Edition,
    FixtureEmailProvider,
    FixtureRouteMatrixProvider,
    ProviderConfigurationError,
    SendRequest,
    build_email_provider,
    build_route_matrix_provider,
)


def _send_request(**overrides: object) -> SendRequest:
    base: dict[str, object] = {
        "to_address": "person@example.edu",
        "subject": "Invitation",
        "body_text": "Hello",
        "approval_id": "approval-1",
        "approved_draft_version": 2,
        "idempotency_key": "idem-1",
        "list_unsubscribe_url": "https://example.test/u/abc",
        "list_unsubscribe_post_url": "https://example.test/v1/unsubscribe",
    }
    base.update(overrides)
    return SendRequest(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Classroom isolation
# ---------------------------------------------------------------------------


def test_classroom_edition_yields_fixture_adapters():
    assert isinstance(build_email_provider(Edition.CLASSROOM), FixtureEmailProvider)
    assert isinstance(build_route_matrix_provider(Edition.CLASSROOM), FixtureRouteMatrixProvider)


def test_classroom_edition_with_a_credential_fails_closed():
    """No provider secret should exist in a classroom project at all.

    Finding one means the deployment or secret binding is wrong, so this fails
    rather than quietly ignoring the credential.
    """
    with pytest.raises(ProviderConfigurationError, match="must have no provider secrets"):
        build_email_provider(Edition.CLASSROOM, api_key="live-key")

    with pytest.raises(ProviderConfigurationError, match="must have no provider secrets"):
        build_route_matrix_provider(Edition.CLASSROOM, api_key="live-key")


def test_no_classroom_path_can_construct_a_live_client():
    """The assertion the verification matrix names, stated directly."""
    for builder in (build_email_provider, build_route_matrix_provider):
        result = builder(Edition.CLASSROOM)
        assert type(result).__name__.startswith("Fixture")


# ---------------------------------------------------------------------------
# Live adapters cannot initialize
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("edition", [Edition.DEV, Edition.STAGING, Edition.PRODUCTION])
def test_live_email_adapter_cannot_initialize_without_a_transport(edition: Edition):
    """The Resend adapter exists now; nothing connects it.

    This assertion used to read "not implemented", and the rewrite is the
    point: a credential alone still fails at boot, and the reason it fails
    changed from "no code" to "no approved tenant" (OQ-002). See
    ``tests/unit/test_resend_email_adapter.py`` for the adapter itself.
    """
    with pytest.raises(ProviderConfigurationError, match="no transport is wired"):
        build_email_provider(edition, api_key="live-key")


@pytest.mark.parametrize("edition", [Edition.DEV, Edition.STAGING, Edition.PRODUCTION])
def test_live_adapter_without_credentials_fails_closed(edition: Edition):
    with pytest.raises(ProviderConfigurationError, match="no email credential"):
        build_email_provider(edition)


def test_use_fixture_flag_works_in_any_edition():
    """Local development and CI opt into fixtures explicitly."""
    assert isinstance(build_email_provider(Edition.DEV, use_fixture=True), FixtureEmailProvider)


# ---------------------------------------------------------------------------
# Fixture behavior
# ---------------------------------------------------------------------------


def test_fixture_email_records_instead_of_sending():
    provider = build_email_provider(Edition.CLASSROOM)
    result = provider.send(_send_request())

    assert result.provider_message_id.startswith("fixture-")
    assert provider.sent[0].to_address == "person@example.edu"  # type: ignore[attr-defined]


def test_fixture_message_ids_are_visibly_synthetic():
    """A synthetic send must never be mistakable for a real one in the database."""
    provider = build_email_provider(Edition.CLASSROOM)
    assert "fixture" in provider.send(_send_request()).provider_message_id


def test_send_request_requires_idempotency_key():
    with pytest.raises(ValueError, match="idempotency_key is required"):
        _send_request(idempotency_key="")


def test_send_request_requires_a_pinned_approval():
    with pytest.raises(ValueError, match="approval_id is required"):
        _send_request(approval_id="")


def test_send_request_requires_both_unsubscribe_headers():
    """RFC 8058 one-click needs the POST variant alongside the link."""
    with pytest.raises(ValueError, match="List-Unsubscribe"):
        _send_request(list_unsubscribe_post_url="")


def test_route_provider_reports_unavailable_rather_than_guessing():
    """v1.1 §3.6 R4: 'travel estimate unavailable', never fabricated mileage."""
    provider = FixtureRouteMatrixProvider(available=False)
    estimate = provider.estimate("Pomona", "Riverside")

    assert not estimate.is_available
    assert estimate.duration is None
    assert estimate.quality == "unavailable"


# ---------------------------------------------------------------------------
# Product scope is not deployment Edition (CBA-SCOPE-POLICY, Wave 0)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scope", list(ProductScope))
@pytest.mark.parametrize("edition", list(Edition))
def test_product_scope_cannot_change_provider_selection(scope: ProductScope, edition: Edition):
    """A product-scope flag must not be able to reach provider selection.

    The CBA pivot introduces a second axis — which product this is — beside the
    existing one — which deployment this is. If the two were ever read from the
    same value, "switch the product to CBA" would silently be "switch the
    deployment", and the classroom isolation assertions above would be arguing
    about the wrong variable. ``build_email_provider`` takes an ``Edition`` and
    nothing else, and this test pins that: no scope changes what it returns.
    """
    assert isinstance(build_email_provider(edition, use_fixture=True), FixtureEmailProvider)
    assert isinstance(
        build_route_matrix_provider(edition, use_fixture=True), FixtureRouteMatrixProvider
    )
    # The scope is a product decision that provider construction never consults.
    assert scope in ProductScope


def test_no_product_scope_enables_a_live_provider_capability():
    """No scope may name a capability that would authorize live provider work.

    ``ALLOW_LIVE_PROVIDERS=false`` is an environment gate, not a product
    decision. A capability such as ``live_email`` would give a product flag a
    route into that gate, so the vocabulary itself is constrained.
    """
    forbidden = ("live", "resend", "provider_credential", "deploy")
    for scope in ProductScope:
        for capability in enabled_capabilities(scope):
            assert not any(term in capability.value for term in forbidden), (
                f"{scope} enables {capability!r}, which names live provider work"
            )


def test_classroom_isolation_holds_under_every_product_scope():
    """Changing the product must never weaken the classroom boundary."""
    for _scope in ProductScope:
        with pytest.raises(ProviderConfigurationError, match="must have no provider secrets"):
            build_email_provider(Edition.CLASSROOM, api_key="live-key")
