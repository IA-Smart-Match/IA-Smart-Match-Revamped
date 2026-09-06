"""Pure derivation rules for the synthetic pilot's stand-in identities.

This module holds the *derivation* half of the synthetic-pilot authorization
(`docs/decisions/synthetic-pilot-development-authorization-2026-09-03.md`
§4 item 6): given a tenant, a unit, and the row a coordinator just accepted,
it computes the deterministic identifiers a caller needs to write real
``pipeline_record`` and ``user_account`` rows. It stores nothing, reaches
nothing, and opens no connection — every function here is a pure computation
over its arguments, checked at import time by the layering contract
(`smartmatch_domain` may not import `sqlalchemy`, `os`, `pathlib`, or any
storage or framework package).

**This module computes no fitness figure of any kind, and never will.** No
matching engine exists in this repository: G1 (plan P5, M1–M10 matching) has
not closed, and the real engine is landing separately on
``pilot/match-engine-m2-m7`` (PR #12). The provenance of every match these
identifiers participate in is :data:`SYNTHETIC_MATCH_PROVENANCE` — a claim
about *who accepted a row*, persisted verbatim in
``pipeline_record.matched_provenance``, and never a claim about computed
fit. A caller that wants a number describing how well a professional and an
opportunity fit will not find one here; this module cannot produce one,
because producing one would be exactly the fabricated-evidence defect
ADR-0011 exists to prevent.

**Why `SYNTHETIC_MATCH_PROVENANCE` is a literal here, not an import.** The
obvious way to keep one spelling of ``"synthetic / coordinator-accepted"``
would be to import it from ``smartmatch_persistence.pipeline``, where the
database-facing constant of the same value lives. The import-linter layering
contract forbids exactly that: ``smartmatch_domain`` may not import
``smartmatch_persistence`` (storage sits outside the domain layer, never the
reverse — see the root ``pyproject.toml``'s import-linter contracts). So the
two literals are independent, hand-typed, and pinned equal by a test
(``tests/unit/test_synthetic_pilot_identity.py``) rather than by a shared
import. That test is the control that keeps this deliberate duplication
safe: if the two ever drift, every synthetic write raises ``IntegrityError``
at runtime, and the test — not a production incident — is where that surfaces.
"""

from __future__ import annotations

import uuid
from typing import Final

__all__ = [
    "MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT",
    "SYNTHETIC_ATTENDANCE_METHOD",
    "SYNTHETIC_BOARD_ROLE",
    "SYNTHETIC_MATCH_PROVENANCE",
    "SYNTHETIC_OPPORTUNITY_NAMESPACE",
    "SYNTHETIC_PROFESSIONAL_NAMESPACE",
    "synthetic_opportunity_event_id",
    "synthetic_professional_email",
    "synthetic_professional_external_subject",
    "synthetic_professional_subject_id",
]

#: A coordinator accepted a synthetic, in-list opportunity row in the pilot
#: appliance — no matching engine ran. Must equal
#: ``smartmatch_persistence.pipeline.MATCH_PROVENANCE_SYNTHETIC_COORDINATOR``
#: exactly; see the module docstring for why that equality is pinned by a
#: test rather than an import.
SYNTHETIC_MATCH_PROVENANCE: Final[str] = "synthetic / coordinator-accepted"

#: ``professional_unit_relationship.board_role`` for every relationship this
#: pilot's identity writer creates.
SYNTHETIC_BOARD_ROLE: Final[str] = "synthetic_pilot_participant"

#: ``attendance_record.method`` for every row the synthetic attendance writer
#: creates. One member of ``smartmatch_persistence.attendance.ATTENDANCE_METHODS``
#: — deliberately not ``"qr_scan"``, which names a real scanning device this
#: pilot never touches.
SYNTHETIC_ATTENDANCE_METHOD: Final[str] = "coordinator_entry"

#: The cap on journeys a single events-row accept may open, one per
#: professional already linked to the accepting unit.
MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT: Final[int] = 50

#: ``uuid5`` namespace for synthetic professional subject ids. A fixed,
#: arbitrary UUID distinct from :data:`SYNTHETIC_OPPORTUNITY_NAMESPACE`, so a
#: professional and an opportunity built from otherwise-identical input
#: strings can never collide on the same derived id.
SYNTHETIC_PROFESSIONAL_NAMESPACE: Final[uuid.UUID] = uuid.UUID(
    "6f2a1c34-9d5b-4e18-8a70-2b6c4d9e1f03"
)

#: ``uuid5`` namespace for synthetic opportunity event ids. See
#: :data:`SYNTHETIC_PROFESSIONAL_NAMESPACE`.
SYNTHETIC_OPPORTUNITY_NAMESPACE: Final[uuid.UUID] = uuid.UUID(
    "1c8e7b52-3a40-4f96-b1d7-5e0a92c647db"
)


def synthetic_professional_subject_id(
    *, tenant_id: uuid.UUID, unit_id: uuid.UUID, name: str
) -> uuid.UUID:
    """Derive a stable ``user_account.id`` for a synthetic professional.

    ``uuid5(SYNTHETIC_PROFESSIONAL_NAMESPACE, f"{tenant_id}:{unit_id}:{name.strip().casefold()}")``
    — deterministic, so accepting the same professional twice (a replayed
    import, a re-seeded demo) derives the same id rather than creating a
    second row (Decision 7 in the plan). ``name`` is folded with ``.strip()``
    and ``.casefold()`` before hashing, so ``"Ada Lovelace"``,
    ``"  ada lovelace  "``, and ``"ADA LOVELACE"`` all derive the same
    subject — a coordinator re-typing or re-pasting a name must not silently
    mint a second identity for the same person. ``tenant_id`` and ``unit_id``
    are both folded into the hash input so the same name under a different
    tenant or a different unit within the same tenant derives a different
    id: two different units' professionals must never collide on one
    ``user_account`` row merely because they share a name, and — because
    ``uq_user_account_external_subject`` is **globally** unique, not
    per-tenant (see ``smartmatch_persistence.schema.user_account``'s own
    comment) — folding ``tenant_id`` in is also what keeps two different
    tenants' same-named professionals from deriving the same globally-unique
    external subject and colliding on that constraint.

    Raises:
        ValueError: ``name.strip()`` is empty.
    """
    folded_name = name.strip().casefold()
    if not folded_name:
        raise ValueError(
            "name must not be blank — a synthetic professional identity derived "
            "from an empty name would collide across every unnamed row"
        )
    return uuid.uuid5(SYNTHETIC_PROFESSIONAL_NAMESPACE, f"{tenant_id}:{unit_id}:{folded_name}")


def synthetic_professional_external_subject(subject_id: uuid.UUID) -> str:
    """Derive ``user_account.external_subject`` from an already-derived subject id.

    Prefixed ``"synthetic-professional:"`` so this identity is unmistakably
    synthetic wherever it surfaces — a log line, an admin screen, a support
    ticket — and derived *from* ``subject_id`` rather than independently, so
    the two can never disagree (see
    ``smartmatch_persistence.professionals``'s own docstring for why that
    agreement is what makes ``user_account_pkey`` the correct
    ``ON CONFLICT`` target for this identity's writer).
    """
    return f"synthetic-professional:{subject_id}"


def synthetic_professional_email(subject_id: uuid.UUID) -> str:
    """Derive ``user_account.email`` from an already-derived subject id.

    On the ``.invalid`` reserved TLD (RFC 2606) — never a real, deliverable
    address — so no synthetic account can ever be mistaken for one this
    program could actually email.
    """
    return f"professional-{subject_id}@synthetic.invalid"


def synthetic_opportunity_event_id(*, tenant_id: uuid.UUID, review_item_id: uuid.UUID) -> uuid.UUID:
    """Derive a stable ``pipeline_record.opportunity_event_id`` for a synthetic opportunity.

    ``uuid5(SYNTHETIC_OPPORTUNITY_NAMESPACE, f"{tenant_id}:{review_item_id}")``
    — deterministic per ``(tenant_id, review_item_id)``, so re-running
    provisioning against the same accepted ``events`` row targets the same
    opportunity rather than opening a parallel one. Keyed off the review
    item's own id, not the row's content, because ``review_item`` is the one
    thing this synthetic opportunity has a stable identity of its own to
    hang off — the ``events`` contract (``docs/pilot-data/columns.yaml``)
    declares no id column of its own.
    """
    return uuid.uuid5(SYNTHETIC_OPPORTUNITY_NAMESPACE, f"{tenant_id}:{review_item_id}")
