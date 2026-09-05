"""What an Event Host may ask for, and what a Speaker Request refuses to be.

Customer §12 lists the Event Host's capabilities as one sentence each — "create
a new event / Speaker Request", "select one or more industries", "select one or
more roles", "enter event topic/description", "specify event location",
"specify physical vs. virtual", "submit". This module is that list stated as a
value that cannot be built wrong, so the rules live where a test can reach them
without a database and without an HTTP client.

Nothing here writes, reads, fetches, or resolves anything external. A
:class:`SpeakerRequestDraft` is a description of one request; turning it into
rows is ``smartmatch_persistence.speaker_requests``' job, and deciding who may
submit one is ``smartmatch_authz``'s.

Four refusals, each traceable to something already ratified
=============================================================

**A Speaker Request must have a resolved date.** ADR-0010 rule 2: "an event at
``unresolved`` cannot reach a matchable or publishable state", and ADR-0012 adds
that it "has no identity key and cannot be resolved against anything". A request
whose whole purpose is to feed matching cannot be filed in the one state that is
unmatchable by construction — and, because the identity key is what makes a
resubmission update rather than duplicate, an unresolved request would also be a
request with no idempotency. Both facts are the same fact, so the refusal is one
check (:class:`UnschedulableSpeakerRequestError`) rather than two.

**A Speaker Request must name at least one industry and at least one role.**
Customer §7 and §8 say a request "may target multiple" and "do not restrict an
event request to one" — a ceiling, removed. §12 says the Event Host selects
"one or more" of each, which is the floor, and it is a floor with teeth: the
matching specification in §5 gives Industry 30% and Role 25% of the default
score, so a request naming neither is a request 55% of the matcher cannot
evaluate. Refusing it is the ADR-0011 posture applied at intake — an unknown is
never silently scored as a zero — rather than storing a request that can only
produce a shortlist nobody should trust.

**Every code comes from the released taxonomy.** ``naics_sectors`` and
``cba_role_categories`` are the only copies of §7's twenty sectors and §8's ten
role categories, and migration ``0024``'s CHECK constraints hold the database to
the same lists. This module resolves each submitted code through those modules,
so an unreleased code is refused with the taxonomy's own error before any
statement is built. There is deliberately **no quarantine arm**: a host picks
from a rendered list rather than resolving a spreadsheet cell, so an unknown
code here is a malformed request and not a value awaiting a reviewer
(migration ``0024``'s OQ-CBA-010 records where a quarantined *import* value
would live instead).

**A virtual request carries no location, and a physical one carries a place.**
The first half is ``ck_event_virtual_has_no_location`` and customer §11's
"ignore Proximity entirely" — a location stored on a virtual event is a value
the scoring rule is required to ignore, which is the shape of a field that gets
read by accident two cards later. The second half is this module's own
fail-closed reading of §10 ("distance ... in miles from the CPP campus. City or
ZIP code is sufficient for this phase") against §5's 30% Proximity weight: a
physical request with no place is a request the largest single factor cannot
score, and the deferral policy for this phase is that an unresolved field fails
closed rather than becoming a silent default. It is recorded as **OQ-CBA-011**
rather than treated as settled, because the customer stated a capability
("specify event location") and not an obligation.

What this module deliberately does not decide
===============================================

* **Whether the request is published or matchable.** Publication is
  ``ck_event_publishable`` and ``EventRepository.publish``; a freshly filed
  request is ``unpublished``/``pending`` like every other event row.
* **Topic scoring.** §9's semantic comparison reads ``description``; nothing
  here parses it, and a blank one is refused as absent rather than stored as
  text that says nothing (ADR-0011: absent is a value, blank is a writer that
  forgot).
* **How multi-select is stored.** That is migration ``0024``'s child table, and
  :func:`classifications_of` only says which rows a draft implies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from smartmatch_domain.cba_role_categories import (
    CBA_ROLE_TAXONOMY_VERSION,
    role_category_for_code,
)
from smartmatch_domain.events import EventTime, is_resolved
from smartmatch_domain.naics_sectors import NAICS_TAXONOMY_VERSION, sector_for_code

__all__ = [
    "CLASSIFICATION_KINDS",
    "KIND_INDUSTRY",
    "KIND_ROLE",
    "ClassificationRequiredError",
    "DuplicateClassificationError",
    "LocationRequiredError",
    "SpeakerRequestClassification",
    "SpeakerRequestDraft",
    "SpeakerRequestError",
    "UnschedulableSpeakerRequestError",
    "VirtualRequestLocationError",
    "classifications_of",
]

#: ``speaker_request_classification.kind`` — customer §7's axis.
KIND_INDUSTRY: Final[str] = "industry"

#: ``speaker_request_classification.kind`` — customer §8's axis.
KIND_ROLE: Final[str] = "role"

#: Both axes, mirroring ``ck_speaker_request_classification_kind`` exactly. No
#: third axis is approved, and the constraint would refuse one anyway.
CLASSIFICATION_KINDS: Final[frozenset[str]] = frozenset({KIND_INDUSTRY, KIND_ROLE})


class SpeakerRequestError(ValueError):
    """A Speaker Request that cannot be filed as described.

    One base so an API layer can answer every one of these with a 400 without
    enumerating the subclasses, and four subclasses so a message can name which
    rule refused — the courtesy ``smartmatch_persistence.events`` extends by
    naming the constraint in its own ``ProvenanceRequiredError``.
    """


class UnschedulableSpeakerRequestError(SpeakerRequestError):
    """The request's date could not be resolved (ADR-0010 rule 2, ADR-0012)."""


class ClassificationRequiredError(SpeakerRequestError):
    """The request named no industry, or no role (customer §12)."""


class DuplicateClassificationError(SpeakerRequestError):
    """The same industry or role was selected twice.

    Refused rather than folded away. ``uq_speaker_request_classification``
    would deduplicate the write, so accepting a repeat would be a request whose
    stored form is not what the caller sent — and the caller would never learn
    that the two selections it made were one. A multi-select is a set; a bag
    arriving at this boundary is a malformed body, not a smaller set.
    """


class VirtualRequestLocationError(SpeakerRequestError):
    """A virtual request carried a location (``ck_event_virtual_has_no_location``)."""


class LocationRequiredError(SpeakerRequestError):
    """A physical request named neither a city nor a postal code (OQ-CBA-011)."""


@dataclass(frozen=True, slots=True)
class SpeakerRequestClassification:
    """One stored target of a Speaker Request.

    Attributes:
        kind: :data:`KIND_INDUSTRY` or :data:`KIND_ROLE`.
        code: The released taxonomy code, already resolved.
        taxonomy_version: Which released taxonomy resolved it. Stored beside the
            code for the reason migration ``0024`` gives: "a code stays
            interpretable after a revision only if the row says which table
            evaluated it".
    """

    kind: str
    code: str
    taxonomy_version: str


def _require_present(value: str | None, field: str) -> None:
    """Reject a blank or whitespace-only string. ``None`` is allowed here.

    ADR-0011's distinction, at the boundary that can still name the field:
    absent is a value and blank is a writer that forgot, and the CHECK
    constraints ``ck_event_location_present`` and
    ``ck_speaker_profile_text_present`` refuse the second for the same reason.
    """
    if value is not None and not value.strip():
        raise SpeakerRequestError(f"{field} must be absent or a non-blank string")


def _require_unique(codes: tuple[str, ...], kind: str) -> None:
    """Refuse a repeated selection. See :class:`DuplicateClassificationError`."""
    seen: set[str] = set()
    for code in codes:
        if code in seen:
            raise DuplicateClassificationError(
                f"{kind} target {code!r} was selected more than once. A multi-select is "
                "a set, and uq_speaker_request_classification would store it once — so "
                "accepting the repeat would store something other than what was sent."
            )
        seen.add(code)


@dataclass(frozen=True, slots=True)
class SpeakerRequestDraft:
    """One Speaker Request, as an Event Host described it (customer §12).

    Every field is validated on construction, so a draft that exists is a
    request that may be filed. Nothing is normalized silently: a value that
    would have to be repaired to be storable is refused with the rule that
    refused it, because a request quietly altered on the way in is a request
    whose stored form nobody agreed to.

    Attributes:
        title: What the event is called. Its folded form is ADR-0012's identity
            key component, which is why two submissions differing only in
            casing or punctuation are one request rather than two.
        event_time: ADR-0010's temporal value. ``UnresolvedTime`` is refused —
            see the module docstring.
        is_virtual: Customer §12's physical/virtual switch, and §11's input.
        industry_codes: One or more released NAICS sector codes (§7, §12).
        role_codes: One or more released CBA role-category codes (§8, §12).
        description: §12's "event topic/description", and the text §9 compares
            semantically against a speaker's topic information. Optional,
            because a host may file a request before writing one — and never
            blank, which would reach §9 as text that says nothing.
        location_city: §10's city. Required with or instead of
            ``location_postal_code`` on a physical request; refused on a virtual
            one.
        location_postal_code: §10's ZIP. Same rule.
    """

    title: str
    event_time: EventTime
    is_virtual: bool
    industry_codes: tuple[str, ...]
    role_codes: tuple[str, ...]
    description: str | None = None
    location_city: str | None = None
    location_postal_code: str | None = None

    def __post_init__(self) -> None:
        if not self.title or not self.title.strip():
            raise SpeakerRequestError("title must be a non-blank string")
        _require_present(self.description, "description")
        _require_present(self.location_city, "location_city")
        _require_present(self.location_postal_code, "location_postal_code")

        if not is_resolved(self.event_time):
            raise UnschedulableSpeakerRequestError(
                "a Speaker Request must carry a resolved date. ADR-0010 rule 2 keeps an "
                "unresolved event out of every matchable and publishable state, and "
                "ADR-0012 leaves it with no identity key — so an unresolved request "
                "could neither be matched against nor safely resubmitted."
            )

        if not self.industry_codes:
            raise ClassificationRequiredError(
                "a Speaker Request must target at least one industry sector (customer "
                "§§7, 12). Industry carries 30% of the default match score; a request "
                "naming none is one the matcher cannot evaluate."
            )
        if not self.role_codes:
            raise ClassificationRequiredError(
                "a Speaker Request must target at least one role category (customer "
                "§§8, 12). Role carries 25% of the default match score."
            )

        _require_unique(self.industry_codes, KIND_INDUSTRY)
        _require_unique(self.role_codes, KIND_ROLE)

        # Resolved through the released taxonomies, which raise their own
        # `UnknownNaicsSector` / `UnknownCbaRoleCategory`. Those stay
        # `LookupError` rather than becoming `SpeakerRequestError` on purpose:
        # the vocabulary is not this module's to define, and re-wrapping the
        # error would make this module look like a second authority on what a
        # sector is.
        for code in self.industry_codes:
            sector_for_code(code)
        for code in self.role_codes:
            role_category_for_code(code)

        has_place = self.location_city is not None or self.location_postal_code is not None
        if self.is_virtual and has_place:
            raise VirtualRequestLocationError(
                "a virtual Speaker Request must carry no location "
                "(ck_event_virtual_has_no_location). Customer §11 says to ignore "
                "Proximity entirely for a virtual event, and a stored place the scoring "
                "rule is required to ignore is a field that gets read by accident."
            )
        if not self.is_virtual and not has_place:
            raise LocationRequiredError(
                "a physical Speaker Request must name a city or a postal code. Customer "
                "§10 measures Proximity — 30% of the default score — in miles from the "
                "CPP campus and says city or ZIP is sufficient; a physical request with "
                "no place is one the largest single factor cannot score. Recorded as "
                "OQ-CBA-011: the customer stated the capability, not the obligation."
            )


def classifications_of(draft: SpeakerRequestDraft) -> tuple[SpeakerRequestClassification, ...]:
    """The ``speaker_request_classification`` rows this draft implies.

    Sorted by ``(kind, code)`` rather than left in submission order, so two
    submissions of the same set of targets produce the same sequence of writes
    regardless of the order a form happened to collect them in. The stored set
    is a set either way — the unique constraint sees to that — but a
    deterministic order is what makes a re-file a no-op a reader can compare
    rather than a reshuffle they have to interpret.
    """
    rows = [
        SpeakerRequestClassification(
            kind=KIND_INDUSTRY, code=code, taxonomy_version=NAICS_TAXONOMY_VERSION
        )
        for code in draft.industry_codes
    ] + [
        SpeakerRequestClassification(
            kind=KIND_ROLE, code=code, taxonomy_version=CBA_ROLE_TAXONOMY_VERSION
        )
        for code in draft.role_codes
    ]
    return tuple(sorted(rows, key=lambda row: (row.kind, row.code)))
