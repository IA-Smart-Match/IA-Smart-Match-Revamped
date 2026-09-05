"""Pure rules for customer §13's manually managed speaker contacts.

Customer §13 gives a Speaker Connector a surface for adding a professional
contact by hand, listing the ones their unit owns, editing one, and correcting
a classification the pipeline assigned. This module holds the half of that
surface that is a computation rather than a write: what a valid draft is, what
a valid correction is, and how a hand-typed name becomes the deterministic
identity ``speaker_profile.professional_id`` needs.

It stores nothing, reaches nothing, and opens no connection — every function
here is pure over its arguments, which the import-linter layering contract
checks at import time (``smartmatch_domain`` may not import ``sqlalchemy``,
``os``, ``pathlib``, or any storage or framework package).

Why this does not reuse ``synthetic_pilot``'s namespace
---------------------------------------------------------
:mod:`smartmatch_domain.synthetic_pilot` already derives ``user_account``
identities by ``uuid5`` from ``(tenant, unit, name)``, and reaching for it here
would have been one import. It is the wrong import, and the reason is not
tidiness.

That module's identities *assert synthetic-ness*. Its prefix is
``synthetic-professional:``, its email domain is ``synthetic.invalid``, and its
own docstring says the accounts it creates "are synthetic … never issued a
credential, never registered with a token verifier, and are not sign-in
identities". Every one of those is a true statement about a row the pilot
appliance fabricated from a spreadsheet, and a false statement about a person a
Speaker Connector met and typed in on purpose. A real contact recorded under a
``synthetic-`` prefix would be filtered out of exactly the reports that exist to
find fabricated data, which is the worst place for a mislabel to sit: the label
is load-bearing precisely because tooling trusts it.

So this module keeps the *shape* — deterministic ``uuid5``, folded name, tenant
and unit in the hash input, an ``.invalid`` email — and states its own facts.
:data:`SPEAKER_CONTACT_NAMESPACE` is a distinct namespace, so the same name in
the same unit derives a *different* id here than it would there: a CBA contact
and a synthetic pilot professional are not the same person, and two identity
schemes that collided would silently merge them.

Why the email is still ``.invalid``
--------------------------------------
``user_account.email`` is ``NOT NULL``, so creating a contact forces an address
into that column, and OQ-CBA-011's ratified posture is that a manually entered
address must not become sendable. Those two facts are only compatible if the
address written is one nothing can deliver to, which is what the RFC 2606
reserved ``.invalid`` TLD is for.

The address a Connector actually typed is *not* stored anywhere — not in this
column, not in ``contact_channel``, not in a note field. It is recognized by the
create surface, discarded, and reported back as withheld
(:data:`WITHHELD_CONTACT_EMAIL_FIELD`). That is deliberately visible rather than
silent: a Connector who types an address and gets no acknowledgement will assume
it was saved, and the next thing they assume is that the contact can be emailed.
See **OQ-CBA-015**, which asks whether §13's form should collect the field at
all given that the system's answer is always to throw it away.

What a correction is, and what it is not
-------------------------------------------
:class:`ClassificationCorrection` carries a current value and nothing else. No
``corrected_by``, no previous value, no ``industry_source`` vocabulary
distinguishing inferred from human-assigned. That is OQ-CBA-008's interim
ruling, and migration ``0024``'s docstring gives the reason: nobody has stated
an audit requirement for classification provenance, and inventing one by adding
a column is what ``0012``'s refusal to invent a ``board_role`` vocabulary is the
local precedent against. If the answer turns out to be that history is required,
the shape is ``contact_channel_transition``'s and it is a later revision — not a
field quietly added to this dataclass.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Final

from smartmatch_domain.cba_role_categories import (
    CBA_ROLE_TAXONOMY_VERSION,
    role_category_for_code,
)
from smartmatch_domain.naics_sectors import NAICS_TAXONOMY_VERSION, sector_for_code

__all__ = [
    "CONTACT_BOARD_ROLE",
    "SPEAKER_CONTACT_NAMESPACE",
    "WITHHELD_CONTACT_EMAIL_FIELD",
    "ClassificationCorrection",
    "SpeakerContactDraft",
    "speaker_contact_email",
    "speaker_contact_external_subject",
    "speaker_contact_subject_id",
]

#: ``uuid5`` namespace for manually created speaker contacts. A fixed,
#: arbitrary UUID, and deliberately **not**
#: :data:`smartmatch_domain.synthetic_pilot.SYNTHETIC_PROFESSIONAL_NAMESPACE` —
#: see the module docstring. Distinctness is the whole content of this
#: constant: it is what stops a hand-entered contact and a pilot-fabricated
#: professional with the same name in the same unit from deriving one id and
#: silently becoming one person.
SPEAKER_CONTACT_NAMESPACE: Final[uuid.UUID] = uuid.UUID("b74d3f01-52a8-4c6e-9d13-8e5fa0c27b64")

#: ``professional_unit_relationship.board_role`` for every relationship a §13
#: manual create writes.
#:
#: That column is ``NOT NULL`` free text and migration ``0012`` refused to give
#: it a vocabulary, so a create is *forced* to write something — this constant
#: is that something, and it is a placeholder rather than a classification.
#: Spelled to describe the provenance of the row (a Connector added this
#: contact by hand) rather than to describe the person, because describing the
#: person is what a vocabulary would do and no committed artifact supplies one.
#: **OQ-CBA-016** is where that gap is recorded; nothing here should be read as
#: answering it.
CONTACT_BOARD_ROLE: Final[str] = "cba_speaker_contact"

#: The create body field that is recognized, never persisted, and reported back
#: in the response's ``withheld_fields``. Named here rather than spelled in the
#: router so the API, the tests, and the front end cannot disagree about which
#: field the withhold posture applies to.
WITHHELD_CONTACT_EMAIL_FIELD: Final[str] = "contact_email"


def speaker_contact_subject_id(
    *, tenant_id: uuid.UUID, unit_id: uuid.UUID, full_name: str
) -> uuid.UUID:
    """Derive a stable ``user_account.id`` for a manually created contact.

    ``uuid5(SPEAKER_CONTACT_NAMESPACE, f"{tenant_id}:{unit_id}:{folded_name}")``,
    with ``folded_name`` being ``full_name.strip().casefold()``.

    Deterministic, so a Connector who submits the same contact twice — a
    double-clicked form, a retried request — derives the same id rather than
    minting a second identity for one person. Folding means ``"Dana Reyes"``,
    ``"  dana reyes  "`` and ``"DANA REYES"`` all land on the same id, because a
    re-typed name is the ordinary way the same person gets entered again.

    Both ``tenant_id`` and ``unit_id`` are in the hash input. ``unit_id``
    because two departments' contacts must not collide on one ``user_account``
    row merely because they share a name. ``tenant_id`` because
    ``uq_user_account_external_subject`` is **globally** unique rather than
    per-tenant — ``0007`` dropped the tenant-scoped constraint that used to
    stand beside it — so without the tenant in the hash, two institutions'
    identically named contacts would derive the same external subject and the
    second one's create would fail on a constraint that names neither of them.

    That determinism is exactly why a second, genuinely different person with
    the same name in the same unit cannot simply be inserted: they derive the
    id of the first. Silently merging them and silently duplicating them are
    both worse than refusing, so the create surface answers ``409`` and asks
    which the caller meant. **OQ-CBA-017.**

    Raises:
        ValueError: ``full_name.strip()`` is empty. An identity derived from an
            empty name would be the same identity for every unnamed row.
    """
    folded_name = full_name.strip().casefold()
    if not folded_name:
        raise ValueError(
            "full_name must not be blank — a contact identity derived from an "
            "empty name would collide across every unnamed row"
        )
    return uuid.uuid5(SPEAKER_CONTACT_NAMESPACE, f"{tenant_id}:{unit_id}:{folded_name}")


def speaker_contact_external_subject(subject_id: uuid.UUID) -> str:
    """Derive ``user_account.external_subject`` from an already-derived subject id.

    Prefixed ``"contact-professional:"``, which says two true things and no
    false ones: this identity belongs to a professional contact, and no
    identity provider has ever seen it. It is deliberately **not**
    ``synthetic-professional:`` — a person a Connector met is not fabricated
    data, and the tooling that filters on that prefix would be wrong about this
    row.

    Derived *from* ``subject_id`` rather than computed independently, so the two
    can never disagree. ``ProfessionalIdentityRepository.ensure_account``
    depends on exactly that: its ``ON CONFLICT`` targets ``user_account_pkey``,
    which is correct only while every caller keeps this derivation discipline.
    """
    return f"contact-professional:{subject_id}"


def speaker_contact_email(subject_id: uuid.UUID) -> str:
    """Derive the placeholder ``user_account.email`` from an already-derived subject id.

    On the RFC 2606 reserved ``.invalid`` TLD, so it is undeliverable by
    construction rather than by a rule somebody has to remember. ``email`` is
    ``NOT NULL``, so a create must write *something*; OQ-CBA-011's ratified
    posture is that a manually entered address must not become sendable; and an
    address nothing can deliver to is the only value that satisfies both.

    The Connector's actual input never reaches this function. It is discarded at
    the create surface and reported in ``withheld_fields`` — see
    :data:`WITHHELD_CONTACT_EMAIL_FIELD`.
    """
    return f"contact-{subject_id}@contact.invalid"


def _require_present(value: str, *, field: str) -> str:
    """Return ``value`` stripped, refusing a blank.

    ADR-0011, applied one layer earlier than the ``CHECK`` that also enforces
    it: absent is a value, blank is a writer that forgot. Catching it here means
    a Connector gets a message naming the field rather than an
    ``IntegrityError`` naming ``ck_speaker_profile_text_present``.
    """
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field} must not be blank")
    return stripped


def _optional_present(value: str | None, *, field: str) -> str | None:
    """Return ``value`` stripped, or ``None``; refuse a blank string.

    ``None`` and ``""`` are not the same input and must not become the same
    row. ``None`` means nobody told us, which is a real §13 answer for a
    company or a job title. ``""`` means a form posted an empty box, which is a
    writer that forgot — and normalizing it to ``None`` here would be this
    module deciding that those two are the same thing, which is the decision
    ADR-0011 says not to make silently.
    """
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        raise ValueError(
            f"{field} must be absent or non-blank; an empty string is a writer "
            "that forgot, not a stated absence (ADR-0011)"
        )
    return stripped


@dataclass(frozen=True, slots=True)
class SpeakerContactDraft:
    """A validated §13 create or edit body, normalized and ready to write.

    Frozen, so a caller cannot adjust a draft between validating it and writing
    it. Built through :meth:`create` rather than by calling the constructor
    directly, because the normalization is the point: the constructor would
    happily accept the untrimmed, blank-bearing values ``create`` exists to
    refuse.

    Every text attribute is already stripped, and every optional one is either
    ``None`` or non-blank — the same guarantee ``ck_speaker_profile_text_present``
    makes about the stored row, established here so the failure names the field
    instead of the constraint.

    The classification codes are optional and default to absent. §19 imports a
    contact and classifies it afterwards, so an unclassified contact is a real
    state; and a Connector adding somebody they just met may not yet know which
    sector they belong to. A code present here has already been checked against
    the closed taxonomy, so a draft can never carry a value the database would
    refuse.

    Attributes:
        full_name: Required. The one field without which the record is not a
            contact.
        company: Optional. A retired professional or an independent consultant
            genuinely has none.
        title: Optional, for the same reason.
        topic_text: §18's "Topic/interests/expertise text".
        prior_talk: §18's "optional prior talk information".
        location_city: §10 — city or ZIP is sufficient, and neither is derived
            from the other.
        location_postal_code: The other half of §10's "or".
        primary_industry_code: Customer §7's single primary sector, or ``None``.
        primary_role_code: Customer §8's single primary role category, or
            ``None``.
    """

    full_name: str
    company: str | None
    title: str | None
    topic_text: str | None
    prior_talk: str | None
    location_city: str | None
    location_postal_code: str | None
    primary_industry_code: str | None
    primary_role_code: str | None

    @classmethod
    def create(
        cls,
        *,
        full_name: str,
        company: str | None = None,
        title: str | None = None,
        topic_text: str | None = None,
        prior_talk: str | None = None,
        location_city: str | None = None,
        location_postal_code: str | None = None,
        primary_industry_code: str | None = None,
        primary_role_code: str | None = None,
    ) -> SpeakerContactDraft:
        """Validate and normalize a §13 body.

        Raises:
            ValueError: ``full_name`` is blank, or any optional text field is
                present but blank.
            smartmatch_domain.naics_sectors.UnknownNaicsSector: an industry code
                outside customer §7's twenty. Raised rather than quarantined:
                §13's Connector picks from a rendered list, so a code off the
                list is a client defect, not a spreadsheet cell awaiting review
                (OQ-CBA-010 covers the quarantine question for the import path,
                which is a different surface).
            smartmatch_domain.cba_role_categories.UnknownCbaRoleCategory: a role
                code outside customer §8's ten, for the same reason.
        """
        if primary_industry_code is not None:
            # Raises UnknownNaicsSector. Called for its refusal, not its value:
            # what gets stored is §7's printed code, which is what came in.
            sector_for_code(primary_industry_code)
        if primary_role_code is not None:
            role_category_for_code(primary_role_code)

        return cls(
            full_name=_require_present(full_name, field="full_name"),
            company=_optional_present(company, field="company"),
            title=_optional_present(title, field="title"),
            topic_text=_optional_present(topic_text, field="topic_text"),
            prior_talk=_optional_present(prior_talk, field="prior_talk"),
            location_city=_optional_present(location_city, field="location_city"),
            location_postal_code=_optional_present(
                location_postal_code, field="location_postal_code"
            ),
            primary_industry_code=primary_industry_code,
            primary_role_code=primary_role_code,
        )

    @property
    def industry_taxonomy_version(self) -> str | None:
        """The version token that travels with :attr:`primary_industry_code`.

        ``ck_speaker_profile_industry_versioned`` requires the code and its
        version to be present or absent together, so this is computed from the
        code rather than accepted as an argument: a caller cannot supply one
        without the other, and cannot supply a version that disagrees with the
        taxonomy the code was checked against.
        """
        return None if self.primary_industry_code is None else NAICS_TAXONOMY_VERSION

    @property
    def role_taxonomy_version(self) -> str | None:
        """The version token that travels with :attr:`primary_role_code`."""
        return None if self.primary_role_code is None else CBA_ROLE_TAXONOMY_VERSION


@dataclass(frozen=True, slots=True)
class ClassificationCorrection:
    """A Speaker Connector's correction to one or both classification axes.

    Customer §§7-8 both require a Connector to be able to correct an assigned
    classification, and §19's flow is exactly that: the pipeline infers, then a
    human fixes it. This is the value that expresses one such fix.

    **Current value only.** There is no ``corrected_by``, no previous value, and
    no field saying whether the value being replaced was inferred or
    human-assigned. That is OQ-CBA-008's interim ruling rather than an
    omission — see the module docstring. A reader who wants to know who
    corrected what will not find it here, and should not add it here without
    the audit requirement that would justify the column.

    An omitted axis means **leave it alone**, not **clear it**. Nothing in §13
    or §§7-8 describes un-classifying a speaker, and giving ``None`` two
    meanings — "not part of this correction" and "delete the stored value" —
    would make the commoner case the dangerous one. A surface that needs
    clearing should say so explicitly and argue for it.

    Attributes:
        primary_industry_code: §7's sector code, or ``None`` to leave the
            stored industry untouched.
        industry_taxonomy_version: Present exactly when
            :attr:`primary_industry_code` is, satisfying
            ``ck_speaker_profile_industry_versioned``.
        primary_role_code: §8's role category code, or ``None`` to leave the
            stored role untouched.
        role_taxonomy_version: Present exactly when :attr:`primary_role_code`
            is.
    """

    primary_industry_code: str | None
    industry_taxonomy_version: str | None
    primary_role_code: str | None
    role_taxonomy_version: str | None

    @classmethod
    def create(
        cls,
        *,
        primary_industry_code: str | None = None,
        primary_role_code: str | None = None,
    ) -> ClassificationCorrection:
        """Validate a correction and stamp each supplied code with its taxonomy version.

        The version is derived rather than accepted, for
        ``ck_speaker_profile_industry_versioned``'s reason: a code and its
        version travel together in both directions, and a caller who could
        supply them separately could supply a pair that disagrees.

        Raises:
            ValueError: neither axis is named. A correction that changes nothing
                is not a correction, and accepting it would make an empty body
                indistinguishable from a successful edit in every log and every
                response.
            smartmatch_domain.naics_sectors.UnknownNaicsSector: the industry code
                is outside customer §7's twenty.
            smartmatch_domain.cba_role_categories.UnknownCbaRoleCategory: the
                role code is outside customer §8's ten.
        """
        if primary_industry_code is None and primary_role_code is None:
            raise ValueError(
                "a correction must name at least one of primary_industry_code "
                "or primary_role_code; an empty correction changes nothing and "
                "would be indistinguishable from a successful edit"
            )

        industry_version: str | None = None
        if primary_industry_code is not None:
            sector_for_code(primary_industry_code)  # raises UnknownNaicsSector
            industry_version = NAICS_TAXONOMY_VERSION

        role_version: str | None = None
        if primary_role_code is not None:
            role_category_for_code(primary_role_code)  # raises UnknownCbaRoleCategory
            role_version = CBA_ROLE_TAXONOMY_VERSION

        return cls(
            primary_industry_code=primary_industry_code,
            industry_taxonomy_version=industry_version,
            primary_role_code=primary_role_code,
            role_taxonomy_version=role_version,
        )
