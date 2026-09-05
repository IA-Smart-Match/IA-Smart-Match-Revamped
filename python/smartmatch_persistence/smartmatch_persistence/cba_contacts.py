"""The §13 speaker-contact write and read path (migrations ``0024`` and ``0025``).

Card ``CBA-CONTACT-MANAGEMENT``. Customer §13 lets a Speaker Connector add a
professional contact by hand, list the ones their unit owns, read one, edit one,
and correct a classification the pipeline assigned. This module is the writer
and reader for all five.

Three tables, one transaction
================================

A contact is not one row. Creating one writes:

* ``user_account`` — the professional's persisted identity, which is what
  Choice A of the synthetic pilot authorization made it and what
  ``speaker_profile.professional_id``'s foreign key points at. Written through
  :class:`~smartmatch_persistence.professionals.ProfessionalIdentityRepository`
  rather than directly, so ``user_account_pkey``'s ``ON CONFLICT`` discipline
  and its documented "first call wins" behaviour keep exactly one
  implementation.
* ``professional_unit_relationship`` — the link that makes this contact one of
  *this unit's* professionals, written through the same repository's
  ``link_to_unit``.
* ``speaker_profile`` — the §13 record itself: name, company, title, the §18
  topic fields, §10's location, and the two §§7-8 classification axes.

No commit. Transaction boundaries belong to the caller, like every other
repository in this package, and here that is not merely a style rule: a contact
whose ``speaker_profile`` landed and whose ``user_account`` did not is not a
partial contact, it is a state the foreign key would have refused outright.

Why a repeat create is a conflict rather than an upsert
=========================================================

``speaker_requests.py`` treats a re-filed request as the *same* request and
updates it, because ADR-0012 gives an event a deterministic natural key and says
in as many words that two extractions producing that key are one event.

A contact has no such ruling, and the analogous behaviour would be wrong. The
identity here is derived from ``(tenant, unit, folded name)``
(:func:`smartmatch_domain.cba_contacts.speaker_contact_subject_id`), so two
genuinely different people who share a name in one unit derive one id. Upserting
would silently overwrite the first person's company, title and classification
with the second's — a data-loss bug that looks like a successful save. Inserting
a duplicate is not available either: the derived id is the primary key.

So :meth:`SpeakerContactRepository.create` raises
:class:`SpeakerContactAlreadyExists` carrying the stored contact, and the route
answers ``409`` naming who is already there. Silently merging and silently
duplicating are both worse than making the caller say which they meant. See
**OQ-CBA-017**, which is where the question of what the caller should then be
able to *do* about it is recorded rather than guessed.

A correction updates; it does not accumulate
===============================================

:meth:`SpeakerContactRepository.correct_classification` is a current-value
``UPDATE`` that bumps ``updated_at``. No history table, no ``corrected_by``, no
``industry_source`` vocabulary saying whether the replaced value was inferred or
human-assigned.

That is OQ-CBA-008's interim ruling, and it is a ruling rather than an
oversight. Migration ``0024``'s docstring gives the reasoning: nobody has stated
an audit requirement for classification provenance, and answering an unasked
question by adding a column is what ``0012``'s refusal to invent a
``board_role`` vocabulary is the local precedent against. If the answer turns
out to be that history is required, the shape is
``contact_channel_transition``'s and it is a later revision — not a column
quietly added here.

What this module does not do
===============================

**It never writes ``contact_channel``.** Not once, on any path. OQ-CBA-011's
ratified posture is that an address a Connector types by hand does not become
sendable, and the way this module honours that is structural: it does not import
the contact-channel schema object at all, so there is no line to accidentally
uncomment. The placeholder ``user_account.email`` it does write is on the RFC
2606 ``.invalid`` TLD and is derived, never supplied — see
:func:`smartmatch_domain.cba_contacts.speaker_contact_email`.

No consent is created, activated, or implied. No outreach is queued. No scoring
runs: ADR-0016 is Proposed and not accepted, and nothing here computes a figure
of any kind.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from smartmatch_domain.cba_contacts import (
    CONTACT_BOARD_ROLE,
    ClassificationCorrection,
    SpeakerContactDraft,
    speaker_contact_email,
    speaker_contact_external_subject,
    speaker_contact_subject_id,
)
from sqlalchemy.orm import Session

from smartmatch_persistence import schema
from smartmatch_persistence.professionals import ProfessionalIdentityRepository

__all__ = [
    "SpeakerContactAlreadyExists",
    "SpeakerContactRepository",
    "SpeakerContactRow",
]


@dataclass(frozen=True, slots=True)
class SpeakerContactRow:
    """One §13 contact, as a Speaker Connector reads it.

    Deliberately not a ``speaker_profile`` row with the account stapled on. It
    carries no email of any kind — neither the ``.invalid`` placeholder
    ``user_account`` holds nor the address the create surface discarded —
    because a read model with an email field is the first thing a later card
    would try to send to, and OQ-CBA-011's posture is that there is nothing here
    to send to.

    Attributes:
        professional_id: The contact's identity, derived at create time from
            ``(tenant, unit, folded name)``. Stable across edits, including an
            edit that changes the name — see
            :meth:`SpeakerContactRepository.update`.
        owning_unit_id: The unit whose Connector is accountable for this record.
        full_name: §13's "Name".
        company: §13's "Company", or ``None`` — a stated absence, not a gap.
        title: §13's "Job title", or ``None``.
        topic_text: §18's topic/interests/expertise text.
        prior_talk: §18's optional prior talk information.
        location_city: §10's city, or ``None``.
        location_postal_code: §10's ZIP, or ``None``.
        primary_industry_code: §7's single primary sector, or ``None`` when the
            contact is not yet classified.
        industry_taxonomy_version: Present exactly when the code is.
        primary_role_code: §8's single primary role category, or ``None``.
        role_taxonomy_version: Present exactly when the code is.
        created_at: When the contact was added.
        updated_at: When it was last edited or corrected.
    """

    professional_id: uuid.UUID
    owning_unit_id: uuid.UUID
    full_name: str
    company: str | None
    title: str | None
    topic_text: str | None
    prior_talk: str | None
    location_city: str | None
    location_postal_code: str | None
    primary_industry_code: str | None
    industry_taxonomy_version: str | None
    primary_role_code: str | None
    role_taxonomy_version: str | None
    created_at: datetime
    updated_at: datetime


class SpeakerContactAlreadyExists(Exception):
    """A create derived the identity of a contact this unit already holds.

    Carries the stored contact rather than only its id, so the route can answer
    ``409`` naming who is already there — a Connector can recognize or dispute
    "Dana Reyes at Reyes Analytics", and cannot do either with a bare UUID.

    Raised rather than resolved, for the reason the module docstring gives at
    length: the two silent alternatives are overwriting one person's record with
    another's, and creating a second row under a key that admits only one.

    Attributes:
        existing: The contact already stored under the derived identity.
    """

    def __init__(self, existing: SpeakerContactRow) -> None:
        super().__init__(
            f"a contact named {existing.full_name!r} already exists in this unit "
            f"({existing.professional_id}); two different people with the same "
            "name in one unit cannot be told apart by the derived identity, so "
            "this create is refused rather than merged or duplicated "
            "(OQ-CBA-017)"
        )
        self.existing = existing


#: The ``speaker_profile`` columns every read in this module selects, in the
#: order :class:`SpeakerContactRow` declares them. One tuple rather than a
#: repeated ``select`` list, so a column added to the row type and forgotten in
#: one of the three readers is impossible by construction.
_PROFILE_COLUMNS = (
    schema.speaker_profile.c.professional_id,
    schema.speaker_profile.c.owning_unit_id,
    schema.speaker_profile.c.full_name,
    schema.speaker_profile.c.company,
    schema.speaker_profile.c.title,
    schema.speaker_profile.c.topic_text,
    schema.speaker_profile.c.prior_talk,
    schema.speaker_profile.c.location_city,
    schema.speaker_profile.c.location_postal_code,
    schema.speaker_profile.c.primary_industry_code,
    schema.speaker_profile.c.industry_taxonomy_version,
    schema.speaker_profile.c.primary_role_code,
    schema.speaker_profile.c.role_taxonomy_version,
    schema.speaker_profile.c.created_at,
    schema.speaker_profile.c.updated_at,
)


class SpeakerContactRepository:
    """Writes and reads §13 speaker contacts over three tables.

    Takes a session per call and commits nothing, like every other repository in
    this package.
    """

    def __init__(self, professionals: ProfessionalIdentityRepository | None = None) -> None:
        """Compose the identity writer rather than duplicating it.

        Defaulted so ordinary callers need not know this class writes
        ``user_account`` and ``professional_unit_relationship`` through somebody
        else, and injectable so a test can watch it do so — the arrangement
        ``SpeakerRequestRepository`` uses for ``EventRepository``.
        """
        self._professionals = professionals or ProfessionalIdentityRepository()

    def create(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        draft: SpeakerContactDraft,
    ) -> SpeakerContactRow:
        """Add one contact to ``owning_unit_id``, across all three tables.

        The identity is derived, not generated: the same name submitted twice by
        the same unit resolves to the same ``professional_id``, so a
        double-clicked form does not mint a second person. The second submission
        is therefore a conflict rather than an insert.

        Raises:
            SpeakerContactAlreadyExists: this unit already holds a contact under
                the derived identity. Detected by reading the existing row so
                the exception can name it, rather than by catching an
                ``IntegrityError`` — a caught constraint violation knows the key
                and not the person, and would also have poisoned the session's
                transaction for the route trying to answer with it.
        """
        professional_id = speaker_contact_subject_id(
            tenant_id=tenant_id,
            unit_id=owning_unit_id,
            full_name=draft.full_name,
        )

        existing = self.get(
            session,
            tenant_id=tenant_id,
            owning_unit_id=owning_unit_id,
            professional_id=professional_id,
        )
        if existing is not None:
            raise SpeakerContactAlreadyExists(existing)

        # `external_subject` and `email` are both derived *from* the id, never
        # supplied. `ensure_account`'s ON CONFLICT targets the pkey, which is
        # correct only while every caller keeps exactly that discipline — its
        # own docstring says so at length.
        self._professionals.ensure_account(
            session,
            tenant_id=tenant_id,
            subject_id=professional_id,
            external_subject=speaker_contact_external_subject(professional_id),
            email=speaker_contact_email(professional_id),
        )
        # `board_role` is NOT NULL free text with no vocabulary (0012 refused to
        # invent one), so a create is forced to write something.
        # CONTACT_BOARD_ROLE is that something, and it describes how the row got
        # here rather than what the person does. OQ-CBA-016.
        self._professionals.link_to_unit(
            session,
            tenant_id=tenant_id,
            professional_id=professional_id,
            unit_id=owning_unit_id,
            board_role=CONTACT_BOARD_ROLE,
        )

        session.execute(
            sa.insert(schema.speaker_profile).values(
                tenant_id=tenant_id,
                professional_id=professional_id,
                owning_unit_id=owning_unit_id,
                **_draft_values(draft),
            )
        )

        # Re-read rather than constructed from the draft: `created_at` and
        # `updated_at` are server-defaulted, so what the caller gets back is the
        # row the database holds and not this module's guess at it.
        created = self.get(
            session,
            tenant_id=tenant_id,
            owning_unit_id=owning_unit_id,
            professional_id=professional_id,
        )
        if created is None:  # pragma: no cover - the insert above is in this transaction
            raise RuntimeError(
                "the contact just inserted could not be read back in the same "
                "transaction; this is a defect in this module, not a caller error"
            )
        return created

    def get(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        professional_id: uuid.UUID,
    ) -> SpeakerContactRow | None:
        """One contact, or ``None`` when this unit does not hold it.

        Scoped by ``tenant_id`` **and** ``owning_unit_id``, never by
        ``professional_id`` alone. A contact id belonging to another unit returns
        ``None`` rather than the row, so the route's 404 and its authorization
        agree about what "not yours" means — the composite-scoping discipline
        ADR-0004 states and every other lookup in this codebase applies.
        """
        row = session.execute(
            sa.select(*_PROFILE_COLUMNS).where(
                schema.speaker_profile.c.tenant_id == tenant_id,
                schema.speaker_profile.c.owning_unit_id == owning_unit_id,
                schema.speaker_profile.c.professional_id == professional_id,
            )
        ).one_or_none()
        return None if row is None else SpeakerContactRow(*row)

    def list_for_unit(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        limit: int,
    ) -> tuple[SpeakerContactRow, ...]:
        """This unit's contacts, by name then id, capped at ``limit``.

        Ordered by ``full_name`` so a Connector scanning for somebody finds them
        where a person would look, and by ``professional_id`` after it so two
        contacts sharing a name never swap places between two identical reads —
        which is also what makes a truncation cut at a stable point.

        The caller passes ``limit`` and decides what to do about a full page.
        This method returns at most that many rows and says nothing about
        whether more exist, for ``SpeakerRequestRepository.list_for_unit``'s
        reason: a repository inventing a "truncated" flag would be a second
        opinion beside the route's own cap.

        Raises:
            ValueError: ``limit`` is less than 1. A limit of zero would return
                nothing for every unit, which is not a cap this method exists to
                express.
        """
        if limit < 1:
            raise ValueError("limit must be at least 1")

        rows = session.execute(
            sa.select(*_PROFILE_COLUMNS)
            .where(
                schema.speaker_profile.c.tenant_id == tenant_id,
                schema.speaker_profile.c.owning_unit_id == owning_unit_id,
            )
            .order_by(
                schema.speaker_profile.c.full_name,
                schema.speaker_profile.c.professional_id,
            )
            .limit(limit)
        ).all()
        return tuple(SpeakerContactRow(*row) for row in rows)

    def update(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        professional_id: uuid.UUID,
        draft: SpeakerContactDraft,
    ) -> SpeakerContactRow | None:
        """Replace this contact's stated fields, or ``None`` if the unit lacks it.

        The draft states the record in full, so every field it carries is
        written — including the absences. A ``company`` of ``None`` clears a
        stored company, because §13's edit form posts the whole record and a
        Connector who empties that box means the company is gone. Merging
        instead would make removing a value the one edit a Connector cannot
        perform.

        **The identity does not move when the name does.** ``professional_id``
        was derived from the original name and is now a stored primary key with
        a foreign key pointing at it, so renaming a contact edits the label and
        not the key. The visible consequence is worth stating rather than
        discovering: after ``"Dana Ryes"`` is corrected to ``"Dana Reyes"``, a
        *create* for ``"Dana Reyes"`` derives a different id and succeeds,
        producing a second contact for one person. That is the same
        derivation-discipline caveat ``ensure_account`` documents about
        ``external_subject``, and it is left as a caveat rather than repaired by
        re-deriving the key: re-deriving would rewrite a primary key other rows
        reference, which is a data-bearing migration and not a side effect of an
        edit.
        """
        # RETURNING rather than `rowcount`, the shape `jobs.py`, `outbox.py`,
        # `pilot_auth.py` and `outreach.py` all state a reason for: `rowcount`
        # lives on `CursorResult`, which `Session.execute` is not typed to
        # return, and the returned columns are the updated row itself — so the
        # "did it exist" question and the read-back are one query instead of
        # two, and there is no window between them.
        row = session.execute(
            sa.update(schema.speaker_profile)
            .where(
                schema.speaker_profile.c.tenant_id == tenant_id,
                schema.speaker_profile.c.owning_unit_id == owning_unit_id,
                schema.speaker_profile.c.professional_id == professional_id,
            )
            .values(
                **_draft_values(draft),
                # Bumped explicitly. The server default fills this column on
                # INSERT only; without this line an edited contact would go on
                # claiming it was last touched when it was created.
                updated_at=sa.func.now(),
            )
            .returning(*_PROFILE_COLUMNS)
        ).one_or_none()
        return None if row is None else SpeakerContactRow(*row)

    def correct_classification(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        professional_id: uuid.UUID,
        correction: ClassificationCorrection,
    ) -> SpeakerContactRow | None:
        """Replace one or both classification axes, or ``None`` if the unit lacks it.

        Customer §§7-8 require a Speaker Connector to be able to correct an
        assigned classification, and §19's flow is exactly that: infer, then let
        a human fix it. This is that write.

        An axis the correction does not name is left alone rather than cleared —
        the domain type's own rule, restated here because it is what makes the
        common case (fixing the industry, leaving the role) safe. Each supplied
        code is written together with its taxonomy version, which
        ``ck_speaker_profile_industry_versioned`` and its role counterpart
        require: a code with no version is uninterpretable after the next
        taxonomy revision, and a version with no code is a claim about nothing.

        Current value only. Nothing here records who corrected what, or what the
        value was before — OQ-CBA-008's interim ruling, and the module docstring
        says why that is a ruling rather than a gap.
        """
        values: dict[str, str | None] = {}
        if correction.primary_industry_code is not None:
            values["primary_industry_code"] = correction.primary_industry_code
            values["industry_taxonomy_version"] = correction.industry_taxonomy_version
        if correction.primary_role_code is not None:
            values["primary_role_code"] = correction.primary_role_code
            values["role_taxonomy_version"] = correction.role_taxonomy_version

        # `ClassificationCorrection.create` refuses a correction naming neither
        # axis, so this is unreachable through that constructor. Checked anyway
        # rather than assumed: a hand-built value, or a later constructor that
        # relaxed the rule, would otherwise produce an UPDATE that bumps
        # `updated_at` and changes nothing else — a correction that appears in
        # every timestamp to have happened and did not.
        if not values:
            raise ValueError(
                "a correction must name at least one of primary_industry_code "
                "or primary_role_code; an empty correction would bump "
                "updated_at while changing nothing"
            )

        # RETURNING rather than `rowcount`, for the reason `update` above states.
        row = session.execute(
            sa.update(schema.speaker_profile)
            .where(
                schema.speaker_profile.c.tenant_id == tenant_id,
                schema.speaker_profile.c.owning_unit_id == owning_unit_id,
                schema.speaker_profile.c.professional_id == professional_id,
            )
            .values(**values, updated_at=sa.func.now())
            .returning(*_PROFILE_COLUMNS)
        ).one_or_none()
        return None if row is None else SpeakerContactRow(*row)


def _draft_values(draft: SpeakerContactDraft) -> dict[str, str | None]:
    """The ``speaker_profile`` columns a draft states, for an INSERT or an UPDATE.

    One helper for both, so a field added to the draft cannot reach the create
    path and miss the edit path — the divergence that would let a Connector set
    a value they could never afterwards change.

    The taxonomy versions come from the draft's own properties rather than from
    arguments, so a code and its version cannot disagree.
    """
    return {
        "full_name": draft.full_name,
        "company": draft.company,
        "title": draft.title,
        "topic_text": draft.topic_text,
        "prior_talk": draft.prior_talk,
        "location_city": draft.location_city,
        "location_postal_code": draft.location_postal_code,
        "primary_industry_code": draft.primary_industry_code,
        "industry_taxonomy_version": draft.industry_taxonomy_version,
        "primary_role_code": draft.primary_role_code,
        "role_taxonomy_version": draft.role_taxonomy_version,
    }
