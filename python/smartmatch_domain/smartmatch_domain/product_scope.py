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
* ``docs/architecture/decisions/ADR-0025-class-exercise-scope-shares-the-matching-mechanism.md``
  D1 (the ``CLASS_EXERCISE`` scope and capability)
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

    ``CLASS_EXERCISE`` is the Spring 2027 classroom exercise (ADR-0025): a
    no-login site over made-up profiles, run by six teams of class
    participants. It is a scope rather than a flag on the CBA product because
    the two share a *mechanism* and no data at all — the exercise stores no real
    student and no real event, has no tenant, no principal, and no consent
    question, and ADR-0025 D1 requires that it never run in the same process as
    real records. A process is one product or the other.
    """

    CBA = "cba"
    IA_WEST_LEGACY = "ia_west_legacy"
    CLASS_EXERCISE = "class_exercise"


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

    #: An Event Host filing a Speaker Request, and a Speaker Connector reading
    #: the queue of them. Customer §12 and §13. Its own capability rather than a
    #: share of :attr:`EVENT_READS` because it is a *write*, and a product that
    #: showed a catalog without accepting requests — or accepted them without
    #: showing the catalog — is a coherent product either way. It is emphatically
    #: not :attr:`EXTERNAL_SPEAKER_ACQUISITION`: the request is typed by a person
    #: about an event their own institution is holding, which is the manual,
    #: inside-the-system growth customer §20 permits.
    SPEAKER_REQUEST_INTAKE = "speaker_request_intake"

    #: A Speaker Connector maintaining their unit's roster of professional
    #: contacts by hand: adding one, listing them, editing one, and correcting
    #: the classification on one. Customer §13, and §§7-8 for the correction.
    #:
    #: Its own capability rather than a share of
    #: :attr:`SPEAKER_REQUEST_INTAKE`, because the two are opposite ends of the
    #: same match and a product could coherently offer either alone. Intake is
    #: an Event Host saying "we need a speaker"; this is a Connector saying
    #: "here is who we know". A product with requests and no roster still
    #: works — the Connector reads requests and answers them from outside the
    #: system — and a product with a roster and no requests is a directory,
    #: which is also a thing. Gating them together would make one decision look
    #: like two, and the authorization rows already say they are two: §12 admits
    #: the Event Host to filing a request, and §13 admits only the Connector to
    #: the roster.
    #:
    #: It is emphatically **not** :attr:`EXTERNAL_SPEAKER_ACQUISITION`. Every
    #: record here is typed in by a person about somebody their institution
    #: already knows, which is exactly the manual, inside-the-system growth
    #: customer §20 permits; the routes make no network call, run no scrape, and
    #: resolve nothing from the internet.
    #:
    #: It is not :attr:`CONSENTED_OUTREACH` either, and the distinction matters
    #: more here than anywhere else on this list: a contact *record* is not a
    #: contact *channel*. Nothing this capability enables writes
    #: ``contact_channel``, creates consent, or makes anybody writable-to — an
    #: address a Connector types on the create form is discarded and reported
    #: back as withheld (OQ-CBA-011). A deployment could enable this and leave
    #: outreach off, and the roster would be exactly as useful and exactly as
    #: unable to send anything.
    SPEAKER_CONTACT_MANAGEMENT = "speaker_contact_management"

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

    #: The Spring 2027 class exercise: its unauthenticated team surface and its
    #: instructor surface, over the ``exercise_`` tables (ADR-0025 D1, D2).
    #:
    #: Granted only in :attr:`ProductScope.CLASS_EXERCISE`, and that scope grants
    #: nothing else. Not a sub-capability of :attr:`MATCH_RUNS`: a match run is
    #: an immutable, versioned, tenant-scoped run over records a principal
    #: entered, and the exercise has none of those four things. Sharing the flag
    #: would mean a CBA deployment could not offer matching without also
    #: offering a no-login surface, which is exactly the process mixing
    #: ADR-0025 D1 forbids.
    #:
    #: The word in code is *exercise*, never "demo" — ADR-0025 D9 and
    #: ``tools/scan_forbidden.py``.
    CLASS_EXERCISE = "class_exercise"

    #: Speaker accounts (B26 T6b-1): a Speaker Connector invites a contact to
    #: set a password, and the contact activates a ``speaker`` login from a
    #: one-time ``/s/{token}`` link. Mounts the invite, revoke, access and
    #: activation routes and the Connector's "Invite to portal" button.
    #:
    #: **Off in every scope** (plan C2 = a). Turning it on is a reviewed edit to
    #: the rows below, never an env var, seed or compose file. **Turn-on rule
    #: (C5, owner-confirmed):** T6b-5 merged **and** parent plan §10 rows 1
    #: (Ann/Pia/Lisa), 2 (named privacy owner) and 4 (pilot hostname) cleared.
    #: It also requires :attr:`AUTHENTICATED_LOGIN`, :attr:`CONSENTED_OUTREACH`
    #: and :attr:`SPEAKER_CONTACT_MANAGEMENT` in the same scope, asserted at
    #: import (:data:`SPEAKER_PORTAL_REQUIRES`).
    SPEAKER_PORTAL = "speaker_portal"


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
                Capability.SPEAKER_REQUEST_INTAKE: True,
                # Customer §13 is a CBA requirement in as many words, and the
                # roster is what §9's matching has to match *against*.
                Capability.SPEAKER_CONTACT_MANAGEMENT: True,
                Capability.MATCH_RUNS: True,
                Capability.DISCOVERY_METRICS: True,
                Capability.CONSENTED_OUTREACH: True,
                Capability.REWARDS_LEDGER: True,
                Capability.OPERATOR_RECORD_IMPORT: True,
                Capability.EXTERNAL_SPEAKER_ACQUISITION: False,
                Capability.COLD_UNKNOWN_CONTACT_OUTREACH: False,
                Capability.CHAPTER_MEMBERSHIP_DUES: False,
                Capability.MEMBER_INQUIRY_NARRATIVE: False,
                # A different product, not a CBA feature deferred. The CBA
                # process holds real students and real events; the exercise
                # surface takes no principal. ADR-0025 D1.
                Capability.CLASS_EXERCISE: False,
                # Staged off until its C5 turn-on rule clears (see the enum).
                Capability.SPEAKER_PORTAL: False,
            }
        ),
        ProductScope.IA_WEST_LEGACY: _classified(
            {
                Capability.AUTHENTICATED_LOGIN: True,
                Capability.EVENT_READS: True,
                Capability.SPEAKER_REQUEST_INTAKE: True,
                # True here for the reason every capability the CBA column
                # enables is true here: this scope is the wider one, and the
                # four it differs on are the four CBA *removes*. Keeping a unit's
                # roster of professional contacts is not among them.
                Capability.SPEAKER_CONTACT_MANAGEMENT: True,
                Capability.MATCH_RUNS: True,
                Capability.DISCOVERY_METRICS: True,
                Capability.CONSENTED_OUTREACH: True,
                Capability.REWARDS_LEDGER: True,
                Capability.OPERATOR_RECORD_IMPORT: True,
                Capability.EXTERNAL_SPEAKER_ACQUISITION: True,
                Capability.COLD_UNKNOWN_CONTACT_OUTREACH: True,
                Capability.CHAPTER_MEMBERSHIP_DUES: True,
                Capability.MEMBER_INQUIRY_NARRATIVE: True,
                # False here even though this is the *wider* scope, and that is
                # not an exception to the rule above it: the four capabilities
                # this column enables and CBA does not are ones CBA *removed*
                # from a shared product. The exercise was never part of this
                # product at all. "Wider" means a superset of the same product's
                # capabilities, not a union of every product in the repository.
                Capability.CLASS_EXERCISE: False,
                Capability.SPEAKER_PORTAL: False,
            }
        ),
        # The class exercise (ADR-0025). One capability on; every capability
        # that implies an authenticated CBA router or a CBA datum explicitly
        # off — not by omission, which this module makes impossible, but as a
        # decision a reader can see.
        #
        # `EVENT_READS` and `MATCH_RUNS` are the two worth pausing on, because
        # the exercise plainly does read events and plainly does rank. It reads
        # `exercise_event` rows and ranks with `rank_profiles_for_event` over
        # `exercise_profile` rows (ADR-0025 D2, D4). Those capabilities name the
        # *CBA* catalog and the *CBA* tenant-scoped, versioned match run, and a
        # `True` here would mount the routers that serve them — which is the
        # process mixing ADR-0025 D1 exists to prevent.
        #
        # `AUTHENTICATED_LOGIN` off is what makes `get_current_principal`
        # unreachable rather than bypassed: ADR-0025 D9 rejected a per-route
        # bypass inside the CBA scope precisely so that this stays a composition
        # fact rather than a handler's good behaviour.
        ProductScope.CLASS_EXERCISE: _classified(
            {
                Capability.AUTHENTICATED_LOGIN: False,
                Capability.EVENT_READS: False,
                Capability.SPEAKER_REQUEST_INTAKE: False,
                Capability.SPEAKER_CONTACT_MANAGEMENT: False,
                Capability.MATCH_RUNS: False,
                Capability.DISCOVERY_METRICS: False,
                Capability.CONSENTED_OUTREACH: False,
                Capability.REWARDS_LEDGER: False,
                Capability.OPERATOR_RECORD_IMPORT: False,
                Capability.EXTERNAL_SPEAKER_ACQUISITION: False,
                Capability.COLD_UNKNOWN_CONTACT_OUTREACH: False,
                Capability.CHAPTER_MEMBERSHIP_DUES: False,
                Capability.MEMBER_INQUIRY_NARRATIVE: False,
                Capability.CLASS_EXERCISE: True,
                Capability.SPEAKER_PORTAL: False,
            }
        ),
    }
)

if set(_POLICY) != set(ProductScope):  # pragma: no cover - import-time assertion
    raise CapabilityScopeError("every product scope must appear in the capability policy")

#: What :attr:`Capability.SPEAKER_PORTAL` cannot run without: a login to
#: activate, outreach to send the invite, and the roster it invites from.
SPEAKER_PORTAL_REQUIRES: Final[frozenset[Capability]] = frozenset(
    {
        Capability.AUTHENTICATED_LOGIN,
        Capability.CONSENTED_OUTREACH,
        Capability.SPEAKER_CONTACT_MANAGEMENT,
    }
)

for _scope, _decisions in _POLICY.items():  # pragma: no cover - import-time assertion
    if _decisions[Capability.SPEAKER_PORTAL] and not all(
        _decisions[required] for required in SPEAKER_PORTAL_REQUIRES
    ):
        raise CapabilityScopeError(
            f"{_scope}: speaker_portal requires "
            + ", ".join(sorted(c.value for c in SPEAKER_PORTAL_REQUIRES))
        )


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
