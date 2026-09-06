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
``UPDATE`` that bumps ``updated_at``. It records **how the current value was
set** — the source, the acting Connector, the moment — and nothing about what
the value was before: no history table, no revision rows, no ``industry_source``
free-text vocabulary.

That is OQ-CBA-008, decided on 6 September 2026 by the program owner of record
as *add provenance, no history*, and migration ``0028`` is where the reasoning
is written out at length. The short form: the question provenance answers is
"can I trust this?", not "what changed?". A code the pipeline proposed and a
code a Connector chose after reading the person's own account of their work are
the same four characters in the same column, and customer §19's review gate
between them is invisible without a source column. The **previous** value, by
contrast, is not evidence about the current one — a revision table would invite
exactly the audit surface nobody asked for, which is what ``0024``'s docstring
declined to build and this decision confirms.

Every write on every path in this module supplies an actor, and each of the
three takes one as a required argument rather than an optional one. A code set
through §13's form or §19's correction is a person's judgment, so it is stored
as ``human`` with them named; only the import path's proposals are ``inferred``,
and ``ck_speaker_profile_{axis}_provenance`` refuses an actor beside those
outright.

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
from typing import Any

import sqlalchemy as sa
from smartmatch_domain.cba_classification import (
    CLASSIFICATION_SOURCE_HUMAN,
    ContactClassificationProposal,
    ProposedClassification,
    inferred_classification,
    match_ineligibility_reason,
)
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
        industry_classification_source: ``'inferred'`` or ``'human'``, present
            exactly when the code is. §19's review gate, read back rather than
            assumed — a caller deciding match eligibility must answer *has
            anybody looked at this* from the row, and cannot if the row does not
            carry it.
        industry_classified_by_user_id: Whose judgment the industry value is.
            ``None`` beside ``'inferred'`` always, and beside ``'human'`` only
            for rows written before migration ``0028``.
        industry_classified_at: When the industry value was set.
        primary_role_code: §8's single primary role category, or ``None``.
        role_taxonomy_version: Present exactly when the code is.
        role_classification_source: The role axis's half of the same three.
        role_classified_by_user_id: Whose judgment the role value is.
        role_classified_at: When the role value was set.
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
    industry_classification_source: str | None
    industry_classified_by_user_id: uuid.UUID | None
    industry_classified_at: datetime | None
    primary_role_code: str | None
    role_taxonomy_version: str | None
    role_classification_source: str | None
    role_classified_by_user_id: uuid.UUID | None
    role_classified_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @property
    def match_ineligibility_reason(self) -> str | None:
        """Why this contact may not enter matching yet, or ``None`` if it may.

        A property rather than a stored column, because it is a reading of the
        four columns above and not a fact of its own: a stored flag would be a
        second answer that could disagree with them, and the disagreement would
        be invisible until somebody matched on it.

        Delegates to the domain so the roster screen, the eligibility filter and
        any later caller cannot each decide it differently — and so the
        fail-closed behaviour is inherited rather than re-argued: every argument
        ``None`` returns a reason, not eligibility.
        """
        return match_ineligibility_reason(
            primary_industry_code=self.primary_industry_code,
            industry_classification_source=self.industry_classification_source,
            primary_role_code=self.primary_role_code,
            role_classification_source=self.role_classification_source,
        )

    @property
    def match_eligible(self) -> bool:
        """Whether §19's review step has been satisfied for both axes."""
        return self.match_ineligibility_reason is None


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
    schema.speaker_profile.c.industry_classification_source,
    schema.speaker_profile.c.industry_classified_by_user_id,
    schema.speaker_profile.c.industry_classified_at,
    schema.speaker_profile.c.primary_role_code,
    schema.speaker_profile.c.role_taxonomy_version,
    schema.speaker_profile.c.role_classification_source,
    schema.speaker_profile.c.role_classified_by_user_id,
    schema.speaker_profile.c.role_classified_at,
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
        actor_id: uuid.UUID,
    ) -> SpeakerContactRow:
        """Add one contact to ``owning_unit_id``, across all three tables.

        The identity is derived, not generated: the same name submitted twice by
        the same unit resolves to the same ``professional_id``, so a
        double-clicked form does not mint a second person. The second submission
        is therefore a conflict rather than an insert.

        ``actor_id`` is the Speaker Connector performing the create, and it is
        required rather than optional. A classification typed into §13's form is
        a person's judgment, and it is stored as one — ``human``, with them
        named. An optional actor would make the unattributed write the one a
        hurried caller reaches for, and migration ``0028`` permits a NULL actor
        beside ``human`` only to describe rows written before the column
        existed.

        Args:
            actor_id: The ``user_account`` id of the acting Connector, in
                ``tenant_id``. Recorded only on the axes this draft classifies;
                an unclassified draft records no actor, because there is no
                judgment to attribute.

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
                **_draft_values(draft, actor_id=actor_id),
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

    def create_from_import(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        professional_id: uuid.UUID,
        draft: SpeakerContactDraft,
        proposal: ContactClassificationProposal,
        at: datetime,
    ) -> SpeakerContactRow:
        """Record a §19 imported contact with the classifier's proposal, unreviewed.

        Customer §19's steps two through four: an accepted import row becomes a
        speaker record, and the classifier's reading of its company and title
        text is stored beside it as ``inferred`` — a proposal awaiting step
        five, which is the Connector's review. Nothing here is ``human`` and
        nothing here names an actor, because nobody has looked at the
        classification yet: the person who accepted the import row reviewed
        *the row*, and treating that as a review of the classification would be
        the bypass §19's ordering exists to prevent.

        **Takes the professional id rather than deriving one.** The account and
        the unit link already exist by the time this runs — the accept path
        provisions them from ``synthetic_professional_subject_id`` — and
        deriving a second id here from the folded name would produce a
        ``speaker_profile`` whose foreign key points at a different person than
        the one the import provisioned. This method therefore writes exactly one
        table, and its caller owns the other two.

        **An existing profile is left exactly as it is.** A re-import of
        somebody already on the roster returns the stored row untouched rather
        than overwriting it, and that is the hazard this guard exists for: the
        stored classification may have been reviewed and corrected by a
        Connector, and replacing it with a fresh machine proposal would silently
        undo a human judgment and put the contact back behind the review gate.
        Skipping is also what makes replaying an accept harmless.

        Args:
            professional_id: The already-provisioned identity this profile
                belongs to.
            draft: The stated fields. Must carry **no** classification codes —
                the proposal supplies those, and a draft that also carried them
                would give one row two sources of the same value.
            proposal: What the classifier read. Either axis may be
                undetermined, which stores as NULL rather than as a guess.
            at: When the classifier ran.

        Raises:
            ValueError: ``draft`` carries a classification code. Refused rather
                than silently preferring one of the two, because whichever this
                method chose would be wrong half the time and invisible in
                both.
        """
        if draft.primary_industry_code is not None or draft.primary_role_code is not None:
            raise ValueError(
                "a draft passed to create_from_import must carry no classification "
                "codes; the proposal supplies them, and a draft carrying its own "
                "would make the stored value depend on which of the two this "
                "method happened to prefer"
            )

        existing = self.get(
            session,
            tenant_id=tenant_id,
            owning_unit_id=owning_unit_id,
            professional_id=professional_id,
        )
        if existing is not None:
            return existing

        session.execute(
            sa.insert(schema.speaker_profile).values(
                tenant_id=tenant_id,
                professional_id=professional_id,
                owning_unit_id=owning_unit_id,
                **_stated_values(draft),
                **_inferred_values(proposal, at=at),
            )
        )

        created = self.get(
            session,
            tenant_id=tenant_id,
            owning_unit_id=owning_unit_id,
            professional_id=professional_id,
        )
        if created is None:  # pragma: no cover - the insert above is in this transaction
            raise RuntimeError(
                "the imported contact just inserted could not be read back in the "
                "same transaction; this is a defect in this module, not a caller error"
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

    def list_match_eligible(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID,
        owning_unit_id: uuid.UUID,
        limit: int,
    ) -> tuple[SpeakerContactRow, ...]:
        """This unit's contacts that have cleared §19's review gate.

        Customer §19's last two steps are ordered — "Speaker Connector
        reviews/corrects classifications" *then* "Speaker becomes available for
        matching" — and this is that ordering expressed as a query. A contact
        whose classification is still a proposal, or is missing on either axis,
        is not returned. It is not returned with a penalty, a low score, or a
        flag for the caller to remember to check: it is absent, because "a
        contact whose classification still needs review must not silently enter
        matching" is a property a caller should not be able to forget.

        **The predicate is a positive match on ``human``, not an exclusion of
        ``inferred``.** The exclusion form admits a row whose source is NULL,
        which is exactly the unreviewed speaker this gate exists to keep out —
        the same fail-open hole ``match_ineligibility_reason`` documents having
        had. Post-``0028`` the database cannot hold a code with no source, so
        the two forms agree today; they stop agreeing the moment anything reads
        this table through a projection that drops the provenance columns, and
        the positive form is the one that stays correct then.

        This is a filter, not a scorer. It says who may enter matching and
        nothing about how they rank once there — ADR-0011's unknown-is-not-zero
        is untouched, because no unknown is being turned into a number here.

        Raises:
            ValueError: ``limit`` is less than 1, for
                :meth:`list_for_unit`'s reason.
        """
        if limit < 1:
            raise ValueError("limit must be at least 1")

        rows = session.execute(
            sa.select(*_PROFILE_COLUMNS)
            .where(
                schema.speaker_profile.c.tenant_id == tenant_id,
                schema.speaker_profile.c.owning_unit_id == owning_unit_id,
                schema.speaker_profile.c.primary_industry_code.is_not(None),
                schema.speaker_profile.c.primary_role_code.is_not(None),
                schema.speaker_profile.c.industry_classification_source
                == CLASSIFICATION_SOURCE_HUMAN,
                schema.speaker_profile.c.role_classification_source == CLASSIFICATION_SOURCE_HUMAN,
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
        actor_id: uuid.UUID,
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

        **An edit re-states the provenance, and this is where a Connector
        correction beats a proposal.** The draft carries the whole record, so a
        code it names becomes ``human`` attributed to ``actor_id`` whether the
        stored value was inferred, human, or absent — an edit over a classifier's
        proposal is a person adopting or replacing it, which is exactly what
        §19's step five is. A code the draft omits clears the axis and its
        provenance together; see :func:`_human_provenance` on why leaving the
        three columns alone is not an option the ``CHECK`` allows.
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
                **_draft_values(draft, actor_id=actor_id),
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
        actor_id: uuid.UUID,
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

        **Current value only, and now attributed.** OQ-CBA-008 was decided on
        6 September 2026 as *provenance, no history*: this write records that a
        person set the value, which person, and when. It still records nothing
        about what the value was before, and there is still no revision table —
        the previous code is not evidence about the current one.

        This is the write the card's "a Connector correction wins" is made of. A
        corrected axis becomes ``human`` with ``actor_id`` named, and an inferred
        proposal it replaces leaves no trace, because the row now states a
        person's judgment and a proposal's provenance beside it would be a claim
        about a value that is gone. An axis the correction does not name keeps
        whatever provenance it had, inferred included — correcting the industry
        must not silently mark an unreviewed role as reviewed.

        Args:
            actor_id: The ``user_account`` id of the correcting Connector, in
                ``tenant_id``. Required: "a human decided this" is worth storing
                only if somebody can be asked which human.
        """
        values: dict[str, Any] = {}
        if correction.primary_industry_code is not None:
            values["primary_industry_code"] = correction.primary_industry_code
            values["industry_taxonomy_version"] = correction.industry_taxonomy_version
            values.update(
                _human_provenance(
                    "industry",
                    code=correction.primary_industry_code,
                    actor_id=actor_id,
                )
            )
        if correction.primary_role_code is not None:
            values["primary_role_code"] = correction.primary_role_code
            values["role_taxonomy_version"] = correction.role_taxonomy_version
            values.update(
                _human_provenance("role", code=correction.primary_role_code, actor_id=actor_id)
            )

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


def _draft_values(draft: SpeakerContactDraft, *, actor_id: uuid.UUID) -> dict[str, Any]:
    """The ``speaker_profile`` columns a draft states, for an INSERT or an UPDATE.

    One helper for both, so a field added to the draft cannot reach the create
    path and miss the edit path — the divergence that would let a Connector set
    a value they could never afterwards change.

    The taxonomy versions come from the draft's own properties rather than from
    arguments, so a code and its version cannot disagree.

    **Provenance travels with the code, on the same principle.** A draft is a
    §13 form a Speaker Connector filled in, so a code it carries is that
    person's judgment and is written as ``human`` with them named — customer
    §19's step five, satisfied at the moment the value is set rather than
    afterwards. The two are emitted by :func:`_human_provenance` from one place
    for ``ck_speaker_profile_industry_provenance``'s reason: the code, its
    version, its source, its actor and its timestamp are five columns that are
    present or absent together, and a caller able to set them separately could
    write the combination the ``CHECK`` refuses.
    """
    return {
        **_stated_values(draft),
        "primary_industry_code": draft.primary_industry_code,
        "industry_taxonomy_version": draft.industry_taxonomy_version,
        **_human_provenance("industry", code=draft.primary_industry_code, actor_id=actor_id),
        "primary_role_code": draft.primary_role_code,
        "role_taxonomy_version": draft.role_taxonomy_version,
        **_human_provenance("role", code=draft.primary_role_code, actor_id=actor_id),
    }


def _stated_values(draft: SpeakerContactDraft) -> dict[str, Any]:
    """The seven non-classification columns a draft states.

    Split out from :func:`_draft_values` so the import path shares them: the
    classification columns are the only ones that path fills differently, and a
    field added to the draft must not reach two of the three writers.
    """
    return {
        "full_name": draft.full_name,
        "company": draft.company,
        "title": draft.title,
        "topic_text": draft.topic_text,
        "prior_talk": draft.prior_talk,
        "location_city": draft.location_city,
        "location_postal_code": draft.location_postal_code,
    }


def _inferred_values(proposal: ContactClassificationProposal, *, at: datetime) -> dict[str, Any]:
    """Both axes of a classifier's proposal, as the ``inferred`` arm stores them.

    An axis the classifier could not resolve produces the *unclassified* arm —
    every column NULL — and not a code of any kind. That is the card's
    "ambiguous or unknown is reviewable, never a guess", and ADR-0011's
    unknown-is-not-zero applied to a taxonomy rather than to a score: the raw
    company or title text is already stored beside these columns, where a
    reviewer reads it, so there is nothing a guess would add except the
    appearance of an answer (OQ-CBA-010).

    ``at`` is passed rather than taken as ``now()`` because a classifier ran at
    a particular moment and both axes were read in the same pass; two
    ``now()`` calls in one statement would agree anyway, but the argument makes
    the shared instant a stated fact rather than a coincidence of the dialect.
    """
    values: dict[str, Any] = {}
    for axis, outcome in (("industry", proposal.industry), ("role", proposal.role)):
        if isinstance(outcome, ProposedClassification):
            # Built through the domain's own constructor rather than assembled
            # here: it is what fixes the source at `inferred` and offers no
            # actor parameter, so this module cannot write a proposal that
            # names somebody even by mistake.
            assignment = inferred_classification(outcome, at=at)
            values.update(
                {
                    f"primary_{axis}_code": assignment.code,
                    f"{axis}_taxonomy_version": assignment.taxonomy_version,
                    f"{axis}_classification_source": assignment.source,
                    f"{axis}_classified_by_user_id": assignment.actor_id,
                    f"{axis}_classified_at": assignment.assigned_at,
                }
            )
        else:
            values.update(
                {
                    f"primary_{axis}_code": None,
                    f"{axis}_taxonomy_version": None,
                    f"{axis}_classification_source": None,
                    f"{axis}_classified_by_user_id": None,
                    f"{axis}_classified_at": None,
                }
            )
    return values


def _human_provenance(axis: str, *, code: str | None, actor_id: uuid.UUID) -> dict[str, Any]:
    """One axis's three provenance columns for a value a person just set.

    A present code produces the ``human`` arm of
    ``ck_speaker_profile_{axis}_provenance``: the source, the acting Connector,
    and the moment. An absent code produces the ``unclassified`` arm — all three
    NULL — rather than leaving them alone, because the ``CHECK`` is written per
    row and not per statement: an edit that clears a code while leaving a stale
    ``classified_at`` behind lands outside every arm and is refused, and an edit
    that cleared the code while leaving a stale *source* behind would, if the
    constraint permitted it, claim a person vouched for a value that is gone.

    ``now()`` rather than a Python ``datetime``, matching ``updated_at``: the
    timestamp on the row should come from the clock the row's other timestamps
    come from, so two columns written by one statement cannot disagree about
    when the statement ran.
    """
    if code is None:
        return {
            f"{axis}_classification_source": None,
            f"{axis}_classified_by_user_id": None,
            f"{axis}_classified_at": None,
        }
    return {
        f"{axis}_classification_source": CLASSIFICATION_SOURCE_HUMAN,
        f"{axis}_classified_by_user_id": actor_id,
        f"{axis}_classified_at": sa.func.now(),
    }
