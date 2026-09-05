"""Which product this is, and which named capabilities it includes.

This is the single CBA product-scope capability policy. API composition
(``services/api/smartmatch_api/main.py``) and frontend navigation
(``apps/web/legacy-frontend/src/lib/productScope.ts``) both read *these* named
decisions; neither invents its own.

Product scope is not deployment ``Edition``
===========================================

:class:`~smartmatch_providers.Edition` answers a deployment question — which
environment is this, and may it hold a provider credential — and drives the
classroom isolation assertions in ``services/api/smartmatch_api/config.py``.
:class:`ProductScope` answers a product question — which product is this, and
which capabilities does the customer's current phase include.

They are deliberately two values. A classroom deployment can run either
product, and the CBA product can run in any edition. Folding them into one flag
would mean a deployment knob silently changing a product decision, and a
product decision silently changing what may hold a credential.

Nothing here can enable live providers, live data, or a cloud deploy. Those are
environment gates (``ALLOW_LIVE_PROVIDERS``, ``ALLOW_LIVE_DATA``,
``ALLOW_CLOUD_DEPLOY``) and edition rules, and the capability vocabulary below
deliberately names none of them — a capability called ``live_email`` would be a
second door into a gate that already has an owner.

Fail-closed, and never silent
=============================

Every capability carries an explicit ``True``/``False`` for every scope. A
policy that treats "absent" as "disabled" is fail-closed but silent: a
capability could end up gated because someone forgot it rather than because
someone decided. :data:`_POLICY` is validated as it is built, so an
unclassified capability fails the import rather than defaulting quietly, and an
unknown capability or scope name raises :class:`CapabilityScopeError` rather
than reading as "correctly disabled".

A UI gate is not authorization
==============================

Hiding a link removes a claim, not an access path. Every route the API keeps
mounted still enforces its own tenant-scoped, deny-by-default authorization
(``smartmatch_authz``). This policy decides what the product *offers*; it never
decides what a caller is *allowed* to do, and no capability may ever be derived
from a role label.

Sources
=======

* ``docs/product/cba-smart-match-customer-requirements.md`` §§1, 4, 20, 22
* ``docs/plans/open-questions/cba-phase-deferred.md`` (CBA-gated capabilities)
* ``docs/product/cba-capability-policy.md`` (this policy, in prose)
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Final

__all__ = [
    "DEFAULT_PRODUCT_SCOPE",
    "Capability",
    "CapabilityScopeError",
    "ProductScope",
    "capability_decisions",
    "enabled_capabilities",
    "is_capability_enabled",
]


class CapabilityScopeError(RuntimeError):
    """Raised for an unrecognised scope or capability name.

    Deliberately not "return ``False``". An unknown name is a typo or a stale
    reference, and answering it with "disabled" would let the mistake read as a
    correctly closed gate for as long as nobody looked.
    """


class ProductScope(StrEnum):
    """Which product the running system is.

    ``CBA`` is the Cal Poly Pomona College of Business Administration
    career-readiness speaker/event matching product — the current phase.
    ``IA_WEST_LEGACY`` is the earlier IA West / Insights Association chapter
    product. It is kept as a named scope, rather than deleted, because the
    capabilities CBA gates are *out of the current product's scope*, not
    defective: the code, data, and history stay in the repository, and this
    enum is what says which product they belong to.
    """

    CBA = "cba"
    IA_WEST_LEGACY = "ia_west_legacy"


#: The scope an unconfigured process runs. The narrower product, so a missing
#: environment variable cannot widen what the system offers.
DEFAULT_PRODUCT_SCOPE: Final[ProductScope] = ProductScope.CBA


class Capability(StrEnum):
    """A named product capability, decided per scope.

    Names describe what the product offers a user, not which module implements
    it: a capability that named a file would have to be renamed whenever the
    file moved, and would tempt a reader into treating the gate as a code
    inventory rather than a product decision.
    """

    #: One standard, backend-derived login. Customer §3: no portal chooser, no
    #: role selection at login, roles read server-side.
    AUTHENTICATED_LOGIN = "authenticated_login"

    #: Reading the event catalog already in the system. Customer §22.
    EVENT_READS = "event_reads"

    #: Immutable, versioned match runs over records already in the system.
    #: Customer §1: matching occurs only between records already entered.
    MATCH_RUNS = "match_runs"

    #: The red/yellow/green discovery feed and the funnel/pipeline metrics that
    #: back it. Customer §17 explicitly keeps this and forbids redesigning it
    #: merely because the target customer changed.
    DISCOVERY_METRICS = "discovery_metrics"

    #: Sending an approved draft to a contact whose consent is on record, with
    #: consent re-checked at delivery. Distinct from
    #: :attr:`COLD_UNKNOWN_CONTACT_OUTREACH` in trust model, not just wording.
    CONSENTED_OUTREACH = "consented_outreach"

    #: Server-backed rewards/points: catalog, balance, and ledger-backed
    #: redemption. Customer §4 says "Rewards / points — Keep". Refinements and
    #: CBA wording are P2; the capability itself is not gated.
    REWARDS_LEDGER = "rewards_ledger"

    #: An operator importing records the institution already holds, through the
    #: quarantine/review path. This is how the CBA lists grow — manually,
    #: inside the system (customer §20) — and is the opposite of acquisition.
    OPERATOR_RECORD_IMPORT = "operator_record_import"

    #: Finding new speakers on the internet, scraping LinkedIn or other
    #: external sources, automatic external event discovery, paid extraction.
    #: Customer §20: explicitly out of scope for this phase.
    EXTERNAL_SPEAKER_ACQUISITION = "external_speaker_acquisition"

    #: Contacting a person who has not consented and is not already a known
    #: institutional contact. Customer §20: out of scope for this phase.
    COLD_UNKNOWN_CONTACT_OUTREACH = "cold_unknown_contact_outreach"

    #: Chapter membership and membership dues as a *product* concept. Customer
    #: §4 and §20 remove both. This never refers to the backend ``membership``
    #: authorization record, which stays exactly as it is.
    CHAPTER_MEMBERSHIP_DUES = "chapter_membership_dues"

    #: Presenting ``member_inquiry`` as a CBA funnel outcome. The stored stage
    #: and its history are preserved; CBA has no approved equivalent outcome,
    #: so the narrative and its tile are not offered and no CBA writer may
    #: produce one.
    MEMBER_INQUIRY_NARRATIVE = "member_inquiry_narrative"


def _classified(decisions: dict[Capability, bool]) -> Mapping[Capability, bool]:
    """Freeze one scope's column, refusing it if any capability is missing."""
    missing = sorted(c.value for c in Capability if c not in decisions)
    if missing:
        raise CapabilityScopeError(
            "every capability must be classified explicitly; unclassified: " + ", ".join(missing)
        )
    return MappingProxyType(dict(decisions))


#: The policy. Read it as a table: one row per capability, one column per
#: scope, no blanks.
_POLICY: Final[Mapping[ProductScope, Mapping[Capability, bool]]] = MappingProxyType(
    {
        ProductScope.CBA: _classified(
            {
                Capability.AUTHENTICATED_LOGIN: True,
                Capability.EVENT_READS: True,
                Capability.MATCH_RUNS: True,
                Capability.DISCOVERY_METRICS: True,
                Capability.CONSENTED_OUTREACH: True,
                Capability.REWARDS_LEDGER: True,
                Capability.OPERATOR_RECORD_IMPORT: True,
                Capability.EXTERNAL_SPEAKER_ACQUISITION: False,
                Capability.COLD_UNKNOWN_CONTACT_OUTREACH: False,
                Capability.CHAPTER_MEMBERSHIP_DUES: False,
                Capability.MEMBER_INQUIRY_NARRATIVE: False,
            }
        ),
        ProductScope.IA_WEST_LEGACY: _classified(
            {
                Capability.AUTHENTICATED_LOGIN: True,
                Capability.EVENT_READS: True,
                Capability.MATCH_RUNS: True,
                Capability.DISCOVERY_METRICS: True,
                Capability.CONSENTED_OUTREACH: True,
                Capability.REWARDS_LEDGER: True,
                Capability.OPERATOR_RECORD_IMPORT: True,
                Capability.EXTERNAL_SPEAKER_ACQUISITION: True,
                Capability.COLD_UNKNOWN_CONTACT_OUTREACH: True,
                Capability.CHAPTER_MEMBERSHIP_DUES: True,
                Capability.MEMBER_INQUIRY_NARRATIVE: True,
            }
        ),
    }
)

if set(_POLICY) != set(ProductScope):  # pragma: no cover - import-time assertion
    raise CapabilityScopeError("every product scope must appear in the capability policy")


def _coerce_scope(scope: ProductScope | str) -> ProductScope:
    try:
        return ProductScope(scope)
    except ValueError as exc:
        raise CapabilityScopeError(f"unknown product scope: {scope!r}") from exc


def _coerce_capability(capability: Capability | str) -> Capability:
    try:
        return Capability(capability)
    except ValueError as exc:
        raise CapabilityScopeError(f"unknown capability: {capability!r}") from exc


def capability_decisions(scope: ProductScope | str) -> Mapping[Capability, bool]:
    """Every capability's decision under ``scope``, as a read-only mapping.

    Returns the whole table rather than only the enabled half: a caller
    rendering "what this product does and does not do" needs both, and a caller
    checking completeness needs to see that nothing was omitted.

    Raises:
        CapabilityScopeError: if ``scope`` is not a known product scope.
    """
    return _POLICY[_coerce_scope(scope)]


def enabled_capabilities(scope: ProductScope | str) -> frozenset[Capability]:
    """The capabilities ``scope`` offers.

    Raises:
        CapabilityScopeError: if ``scope`` is not a known product scope.
    """
    return frozenset(
        capability for capability, enabled in capability_decisions(scope).items() if enabled
    )


def is_capability_enabled(scope: ProductScope | str, capability: Capability | str) -> bool:
    """Whether ``scope`` offers ``capability``.

    Raises:
        CapabilityScopeError: if either name is unknown. An unknown name is
            never answered with ``False`` — see :class:`CapabilityScopeError`.
    """
    return capability_decisions(scope)[_coerce_capability(capability)]
