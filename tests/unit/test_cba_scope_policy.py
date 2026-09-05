"""The CBA product-scope capability policy (Wave 0, ``CBA-SCOPE-POLICY``).

Product scope is **not** deployment :class:`~smartmatch_providers.Edition`.
``Edition`` answers "which deployment is this, and may it hold a provider
credential"; product scope answers "which product is this, and which named
capabilities does that product include". A classroom edition can run either
product; the CBA product can run in any edition. Conflating the two would make
a product decision changeable by a deployment knob, and vice versa.

These tests pin four things:

1. The policy lives in exactly one place and classifies every named capability
   for every scope — silence is impossible, so a new capability cannot be added
   without a deliberate, reviewable decision.
2. The CBA defaults are fail-closed: external acquisition, cold unknown-contact
   outreach, chapter membership/dues, and the ``member_inquiry`` narrative are
   off, while login, event reads, match runs, discovery metrics, consented
   outreach, operator record import, and truthful rewards stay on.
3. The API and the frontend read the *same* named decisions. The frontend
   mirror is checked against the Python policy rather than trusted.
4. Nothing here relaxes the live-provider, live-data, or cloud-deploy gates.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from smartmatch_api.config import Settings
from smartmatch_domain.product_scope import (
    DEFAULT_PRODUCT_SCOPE,
    Capability,
    CapabilityScopeError,
    ProductScope,
    capability_decisions,
    enabled_capabilities,
    is_capability_enabled,
)
from smartmatch_providers import Edition

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_POLICY_PATH = (
    REPO_ROOT / "apps" / "web" / "legacy-frontend" / "src" / "lib" / "productScope.ts"
)

#: Customer §22 ("Existing Functionality to Preserve") and §4 ("Rewards /
#: points — Keep"), restated here as a test expectation so that a later edit
#: quietly disabling one of them fails rather than passes.
PRESERVED_UNDER_CBA = frozenset(
    {
        Capability.AUTHENTICATED_LOGIN,
        Capability.EVENT_READS,
        # Customer §12 (an Event Host files a Speaker Request) and §13 (a
        # Speaker Connector reads the queue). Enabled under CBA because it is
        # the CBA workflow's entry point, and under the legacy scope because the
        # volunteer-opportunity surface it renames was already there.
        Capability.SPEAKER_REQUEST_INTAKE,
        # Customer §13 (a Speaker Connector keeps the unit's roster of
        # professional contacts) and §§7-8 (the Connector corrects a
        # classification). Enabled under CBA because §13 is a CBA requirement in
        # as many words, and under the legacy scope because keeping a roster of
        # people the institution already knows is not among the four things CBA
        # removes.
        #
        # Listed here as *preserved* rather than argued separately: the
        # distinction this set draws is on-or-off under CBA, and a roster is the
        # thing §9's matching matches against.
        Capability.SPEAKER_CONTACT_MANAGEMENT,
        Capability.MATCH_RUNS,
        Capability.DISCOVERY_METRICS,
        Capability.CONSENTED_OUTREACH,
        Capability.REWARDS_LEDGER,
        Capability.OPERATOR_RECORD_IMPORT,
    }
)

#: Customer §20 ("Explicit Scope Boundaries") plus the ``member_inquiry``
#: disposition in ``docs/plans/open-questions/cba-phase-deferred.md``.
DISABLED_UNDER_CBA = frozenset(
    {
        Capability.EXTERNAL_SPEAKER_ACQUISITION,
        Capability.COLD_UNKNOWN_CONTACT_OUTREACH,
        Capability.CHAPTER_MEMBERSHIP_DUES,
        Capability.MEMBER_INQUIRY_NARRATIVE,
    }
)


# ---------------------------------------------------------------------------
# The policy itself
# ---------------------------------------------------------------------------


def test_default_product_scope_is_cba() -> None:
    """An unconfigured process runs the narrower product, not the wider one."""
    assert DEFAULT_PRODUCT_SCOPE is ProductScope.CBA


def test_every_capability_is_classified_for_every_scope() -> None:
    """No capability may be left unclassified in any scope.

    A policy that answers "not listed" with ``False`` is fail-closed but silent:
    a capability could end up gated by omission rather than by decision. An
    explicit entry per scope makes every decision visible in a diff.
    """
    for scope in ProductScope:
        assert set(capability_decisions(scope)) == set(Capability), (
            f"{scope} does not classify every capability"
        )


def test_cba_preserves_working_in_scope_behaviour() -> None:
    for capability in sorted(PRESERVED_UNDER_CBA):
        assert is_capability_enabled(ProductScope.CBA, capability), (
            f"{capability} must stay enabled under CBA (customer §22)"
        )


def test_cba_disables_out_of_scope_capabilities() -> None:
    for capability in sorted(DISABLED_UNDER_CBA):
        assert not is_capability_enabled(ProductScope.CBA, capability), (
            f"{capability} must be disabled under CBA (customer §20)"
        )


def test_cba_enabled_set_is_exactly_the_preserved_set() -> None:
    assert enabled_capabilities(ProductScope.CBA) == PRESERVED_UNDER_CBA


def test_the_gate_is_scope_specific_not_a_blanket_disable() -> None:
    """The legacy scope still enables what CBA gates.

    This is what makes the policy a *scope* decision rather than a deletion:
    the capabilities remain in the repository and remain reachable under the
    scope that owns them.
    """
    for capability in sorted(DISABLED_UNDER_CBA):
        assert is_capability_enabled(ProductScope.IA_WEST_LEGACY, capability)


def test_unknown_capability_is_refused_not_silently_disabled() -> None:
    """An unrecognised capability name is a bug, and bugs must be loud.

    Returning ``False`` would let a typo read as "correctly gated" forever.
    """
    with pytest.raises(CapabilityScopeError):
        is_capability_enabled(ProductScope.CBA, "speaker_teleportation")  # type: ignore[arg-type]


def test_unknown_scope_is_refused() -> None:
    with pytest.raises(CapabilityScopeError):
        enabled_capabilities("ia_east")  # type: ignore[arg-type]


def test_policy_names_no_live_provider_data_or_deploy_capability() -> None:
    """Product scope must not become a second way to turn live things on.

    ``ALLOW_LIVE_PROVIDERS``/``ALLOW_LIVE_DATA``/``ALLOW_CLOUD_DEPLOY`` and the
    ``Edition`` isolation rules own those decisions. A capability named
    ``live_...`` or ``..._deploy`` here would let a product-scope flag reach
    them.
    """
    forbidden = re.compile(r"live|deploy|terraform|credential|secret", re.IGNORECASE)
    offenders = [c.value for c in Capability if forbidden.search(c.value)]
    assert offenders == []


# ---------------------------------------------------------------------------
# Scope is not Edition
# ---------------------------------------------------------------------------


def test_product_scope_and_edition_are_independent() -> None:
    """Every edition runs the same capability decisions for a given scope."""
    for edition in Edition:
        settings = Settings(edition=edition, use_fixture_providers=True)
        assert settings.product_scope is ProductScope.CBA
        assert settings.enabled_capabilities() == enabled_capabilities(ProductScope.CBA)


def test_changing_scope_does_not_change_provider_isolation() -> None:
    for scope in ProductScope:
        settings = Settings(edition=Edition.CLASSROOM, product_scope=scope)
        assert settings.use_fixture_providers is True


# ---------------------------------------------------------------------------
# API adapter
# ---------------------------------------------------------------------------


def test_settings_default_scope_is_cba() -> None:
    assert Settings().product_scope is ProductScope.CBA


def test_settings_capability_helper_matches_the_policy() -> None:
    settings = Settings(product_scope=ProductScope.CBA)
    for capability in Capability:
        assert settings.capability_enabled(capability) == is_capability_enabled(
            ProductScope.CBA, capability
        )


def test_settings_refuses_an_unrecognised_scope_value() -> None:
    """A misconfigured scope must fail to boot rather than fall back silently."""
    with pytest.raises(ValueError):
        Settings(product_scope="chapter_mode")  # type: ignore[arg-type]


def test_api_composition_reads_the_same_policy() -> None:
    """API composition classifies each mounted router by capability."""
    from smartmatch_api.main import CAPABILITY_SCOPED_ROUTERS, app

    assert CAPABILITY_SCOPED_ROUTERS, "expected the router set to be capability-classified"
    # Read the served contract rather than ``app.routes``: an included router
    # appears there as one opaque entry, so the paths a caller can actually
    # reach are the ones OpenAPI reports.
    mounted_paths = set(app.openapi()["paths"])
    for router, capability in CAPABILITY_SCOPED_ROUTERS:
        router_paths = {route.path for route in router.routes if hasattr(route, "path")}
        assert router_paths, "expected the classified router to declare at least one route"
        if is_capability_enabled(DEFAULT_PRODUCT_SCOPE, capability):
            assert router_paths <= mounted_paths, f"{capability} routes should be mounted"
        else:
            assert not (router_paths & mounted_paths), f"{capability} routes must not be mounted"


def test_no_cba_disabled_capability_owns_a_router() -> None:
    from smartmatch_api.main import CAPABILITY_SCOPED_ROUTERS

    classified = {capability for _, capability in CAPABILITY_SCOPED_ROUTERS}
    assert classified & DISABLED_UNDER_CBA == set(), (
        "a CBA-disabled capability must not own a router that ships mounted by default"
    )


# ---------------------------------------------------------------------------
# Frontend adapter — same named decisions, checked rather than trusted
# ---------------------------------------------------------------------------


def _frontend_policy() -> dict[str, bool]:
    source = FRONTEND_POLICY_PATH.read_text(encoding="utf-8")
    block = re.search(
        r"export const CBA_CAPABILITY_POLICY = \{(.*?)\} as const;", source, re.DOTALL
    )
    assert block is not None, f"no CBA_CAPABILITY_POLICY object literal in {FRONTEND_POLICY_PATH}"
    return {
        name: value == "true"
        for name, value in re.findall(r"^\s*(\w+): (true|false),\s*$", block.group(1), re.MULTILINE)
    }


def test_frontend_policy_file_exists() -> None:
    assert FRONTEND_POLICY_PATH.is_file(), f"expected {FRONTEND_POLICY_PATH} to exist"


def test_frontend_mirror_matches_the_python_policy_exactly() -> None:
    """One truth, mirrored — never a second frontend-only scope decision."""
    expected = {
        capability.value: is_capability_enabled(ProductScope.CBA, capability)
        for capability in Capability
    }
    assert _frontend_policy() == expected


def test_frontend_mirror_declares_its_source() -> None:
    source = FRONTEND_POLICY_PATH.read_text(encoding="utf-8")
    assert "smartmatch_domain/product_scope.py" in source, (
        "the mirror must name the module it mirrors, or it becomes a second truth"
    )


def test_ui_gate_is_documented_as_not_security() -> None:
    source = FRONTEND_POLICY_PATH.read_text(encoding="utf-8").lower()
    assert "authoriz" in source and "not" in source, (
        "the frontend adapter must say in its own text that hiding a link is not authorization"
    )
