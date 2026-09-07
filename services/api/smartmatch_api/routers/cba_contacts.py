"""Speaker contacts: add one by hand, read the roster, edit one, correct its classification.

Customer §13 gives a Speaker Connector a roster to keep. ``routers/imports.py``
grows that roster from a spreadsheet through the quarantine/review path, and
``routers/speaker_requests.py`` is the *other* side of the match — a host asking
for a speaker. This module is the manual half: a Connector met somebody, and this
is where they say so.

## Five operations

* ``POST  /v1/units/{unit_id}/speaker-contacts`` — add a contact.
* ``GET   /v1/units/{unit_id}/speaker-contacts`` — the unit's roster.
* ``GET   /v1/units/{unit_id}/speaker-contacts/{professional_id}`` — one contact.
* ``PATCH /v1/units/{unit_id}/speaker-contacts/{professional_id}`` — edit one.
* ``POST  /v1/units/{unit_id}/speaker-contacts/{professional_id}/classification``
  — correct the §§7-8 classification.

## One authorizer for all five, and why that is not what the file next door does

``routers/speaker_requests.py`` deliberately has **two** authorizers for its two
operations, and says so at length: customer §12 admits the Event Host to filing a
request, §13 admits only the Speaker Connector to reading the queue, and one
helper taking the role set as an argument would make a single call site the place
both could be widened from. That is the right shape there, because the two
operations gate on two different customer sections and their role sets genuinely
differ.

These five do not. Every one of them is §13's Speaker Connector acting on the
roster their own unit owns, and their authorization rectangles in
``tests/authz/test_policy_matrix.py`` are identical cell for cell. So this module
follows ``routers/outreach_contacts.py``'s arrangement instead — one
:func:`_authorize_speaker_contacts`, one role set — for the reason that module
gives about its own five: it makes "may this caller work with this unit's
contacts" **one question with one answer**, so a widening applies to all of it or
to none of it and cannot reach one route by accident. Five identical helpers
would be five answers to a question asked once, and the day §13 does split, the
split should have to be argued in a diff rather than already sitting there
unused.

The role set is ``{admin, coordinator}`` and not
``_SPEAKER_REQUEST_CREATE_ROLES``' ``{admin, coordinator, volunteer}``. That one
name is the whole difference between the two cards: an Event Host asks for a
speaker, and deciding who is on the list of people who may be asked is not part
of asking.

## The contact email is recognized, discarded, and reported

§13's create form collects an email address. OQ-CBA-011's **ratified** posture is
that an address entered this way does not become sendable, and this module
implements that literally:

* The field is accepted in the request body, so a client that sends one gets a
  ``201`` rather than a validation error about a field the form legitimately has.
* It is **never persisted**. Not in ``speaker_profile``, not in a note, and above
  all not in ``contact_channel`` — no row is written to that table on any path
  here, and ``smartmatch_persistence.cba_contacts`` does not import its schema
  object at all, so there is no line to accidentally uncomment.
* The ``user_account.email`` a create does write is derived, on the RFC 2606
  ``.invalid`` TLD, and is not the address the caller sent.
* The response names it in ``withheld_fields``.

That last point is the one worth defending. Silently dropping the field would be
indistinguishable from saving it, and a Connector who types an address and sees
no complaint will believe the contact can be emailed — which is precisely the
belief OQ-CBA-011 exists to prevent. Naming it is how the refusal reaches the
person who needs to know about it. **OQ-CBA-015** records the remaining question:
whether a form should collect a field the system always throws away.

Consent is not created, activated, or implied anywhere in this module. A contact
record is not a contact channel, and a Connector label is not a permission.

## A duplicate name is a hint, never a refusal

**OQ-CBA-017, decided 2026-09-05.** This surface used to answer
``409 speaker_contact_name_already_used`` when a create named somebody the unit
already held. It does not any more, and the reason is that the ``409`` was
enforcing an identity scheme rather than a rule anybody wanted: a contact's
``professional_id`` was ``uuid5(namespace, "tenant:unit:folded_name")``, so two
genuinely different people sharing a name derived one id and there was no second
row for the second person to live in.

Two professionals in one department can share a name. The identity is now
opaque, so both of them are storable, and a same-name create returns ``201``
like any other.

What the refusal was *also* doing — crude duplicate prevention — does not
disappear with it. The create reports ``same_name_contacts``: the other contacts
in this unit carrying this name, named and attributed, so a Connector can see
that "Dana Reyes at Reyes Analytics" is already here and stop. That is the one
thing the ``409`` did well, kept, and downgraded from a block to a statement. It
is never a refusal and never a merge — the record is written before the response
is rendered, and the hint describes the roster rather than gating it.

The case this closes is the one the ``409`` could not see. An edit that corrected
a name did not move the derived key, so after ``"Dana Ryes"`` became
``"Dana Reyes"`` a create of ``"Dana Reyes"`` derived a *different* id and the
guard passed it in silence — one person, two records. The hint compares
**names**, which is the thing a rename changes.

## The edit hints too, and says something else

**OQ-CBA-049, decided 2026-09-06.** The create warns that you *may be about to
duplicate somebody*. Renaming a contact into a name the unit already holds is
the same hazard arriving from the other direction, and until this decision the
edit said nothing about it at all — a Connector could turn one of two people
into the other's namesake and read a clean ``200``.

The edit now reports ``name_now_shared_with``, and the **different field name is
the point** rather than a naming preference. The two messages are not the same
message: a create's hint is *you may be about to duplicate*, and an edit's is
*you may have just collided*. One is about a record that did not exist a moment
ago; the other is about a record that has been on this roster for months and
has just changed its label. A client that received both under one key would
have to reconstruct which it was holding from the HTTP method, and a reader of
either would be entitled to assume the wrong one. So ``same_name_contacts`` is
the create's and stays the create's, ``name_now_shared_with`` is the edit's, and
each is empty everywhere the other might speak.

It fires only when the edit **changes** the name into one somebody else holds.
An edit that leaves the name alone reports nothing, and neither does one that
re-states the same name in different case or spacing — the comparison is the
create's fold and the collision set has not moved. Otherwise every save of §13's
form would re-announce a collision the Connector already knows about, and a
warning that fires on every save is one nobody reads.

Exact folded equality and nothing cleverer, which is **OQ-CBA-050** decided the
same day: no similarity scoring, no edit distance, no cutoff to tune. That
decision is revisitable when somebody has a roster large enough to measure a
false-positive rate on, and not before.

Not here, deliberately: no uniqueness constraint on
``(tenant_id, owning_unit_id, full_name)``, in any form, ever — OQ-CBA-021,
argued in migration ``0030``. The edit hint is a hint on exactly the create's
terms: the ``UPDATE`` has already committed by the time anybody reads it, and
there is no status code, no ``409``, and no refusal anywhere on this surface.
No merge either — no ``duplicate_of``, no "these are the same person" — because
recording that two rows are one person is a product decision nobody has taken.
What ships is the statement that two rows share a name. And no request-level
idempotency: a double-clicked form now adds the same person twice rather than
resolving to one derived id, which is the cost of the decision and is recorded
as **OQ-CBA-047** rather than papered over.

## What this module does not do

No scoring. ADR-0016 is **Proposed and not accepted**, and nothing here computes,
stores, or returns a figure describing how well anybody fits anything. No
outreach, no cold contact, no scraping, no external lookup: every field is typed
by a person about somebody their institution already knows.

Quota is charged first — ADR-0015's ordering, ahead of the load, the
authorization and the validation, as every other route in this package does it.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Annotated, Final

from fastapi import APIRouter, Path, status
from pydantic import BaseModel, Field
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_domain.cba_contacts import (
    WITHHELD_CONTACT_EMAIL_FIELD,
    ClassificationCorrection,
    SpeakerContactDraft,
    folded_contact_name,
)
from smartmatch_domain.cba_role_categories import UnknownCbaRoleCategory
from smartmatch_domain.naics_sectors import UnknownNaicsSector
from smartmatch_persistence.cba_contacts import (
    SpeakerContactRepository,
    SpeakerContactRow,
)
from smartmatch_persistence.rate_limit import RateLimit
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal, DbSession, charge_quota
from smartmatch_api.errors import ApiError
from smartmatch_api.units import load_unit_or_404
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/units", tags=["speaker-contacts"])

_contacts: Final[SpeakerContactRepository] = SpeakerContactRepository()

#: Who may manage a unit's speaker contacts. Customer §13 gives the roster to the
#: **Speaker Connector**, which is the stored ``admin``/``coordinator`` persona,
#: and names nobody else. ``volunteer`` — the Event Host, per customer §4 — is
#: deliberately absent: §12 lets a host file a Speaker Request, and deciding who
#: is on the list of people who may be asked is a different authority. Under
#: deny-by-default the absence of a permit is a denial rather than an invitation
#: to guess.
#:
#: A literal ``frozenset`` rather than an import of another module's role set,
#: for the reason ``tests/authz/test_route_roles.py`` gives about its own ledger:
#: several role sets agreeing today is not a reason a widening of one should
#: silently widen the others.
_SPEAKER_CONTACT_ROLES: Final[frozenset[str]] = frozenset({"admin", "coordinator"})

#: The write is the consequential one and carries the tighter limit, the same
#: relationship ``speaker_requests.py`` and ``pipeline.py`` both draw between
#: their two. Thirty contacts a minute is already faster than a Connector can
#: have met people; the read is a roster somebody refreshes.
SPEAKER_CONTACT_WRITE_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="speaker_contact.write", max_requests=30, window=timedelta(minutes=1)
)
SPEAKER_CONTACT_READ_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="speaker_contact.read", max_requests=120, window=timedelta(minutes=1)
)

#: The most contacts one response returns. G3 §2.2a's 200-record cap, reused
#: rather than a second number invented here — ``routers/events.py::MAX_ROWS``,
#: ``routers/match_runs.py::MAX_CANDIDATES`` and
#: ``routers/speaker_requests.py::MAX_ROWS`` are the same number for the same
#: reason. Paging is deliberately not shipped: a cursor nobody has asked for is a
#: contract to maintain, and ``truncated`` is what keeps a full page from reading
#: as a complete one.
MAX_ROWS: Final[int] = 200

#: The most same-name contacts a create's duplicate hint names.
#:
#: Deliberately far below :data:`MAX_ROWS`, because this is not a listing. The
#: hint answers "is this person already here?", and a Connector who wants the
#: full picture has the roster one call away. Ten is generous for a question
#: whose honest answer is almost always zero or one: a unit holding eleven
#: people under one folded name has a problem that a longer list would not help
#: with.
#:
#: Not a limit on what may be *stored* — nothing here refuses anything. Two
#: professionals sharing a name are two contacts (OQ-CBA-017), and a hundred of
#: them would be a hundred contacts.
MAX_SAME_NAME_HINTS: Final[int] = 10


# ---------------------------------------------------------------------------
# Request and response models
# ---------------------------------------------------------------------------


class SpeakerContactCreate(BaseModel):
    """One speaker contact, as a Speaker Connector fills it in (customer §13).

    Note what is **not** here: no tenant, no owning unit, no professional id, no
    actor. The first two come from the verified principal and the path; the third
    is generated by the server, so a caller cannot choose an identity — least of
    all somebody else's (MM-A01); the fourth is never a body field.

    ``contact_email`` **is** here, and is the one field this model accepts in
    order to refuse. See the module docstring.
    """

    full_name: str = Field(
        min_length=1,
        max_length=200,
        description=(
            "The contact's name. The one field without which the record is not a "
            "contact — and an ordinary label rather than an identifier: the "
            "stored identity is generated, so correcting a name later moves "
            "nothing. Two submissions of the same name are two people, and the "
            "second one's response says who already carries it."
        ),
    )
    company: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description=(
            "Where they work, or null. Null is a real answer — a retired "
            "professional or an independent consultant has none — and an empty "
            "string is refused rather than stored as one (ADR-0011)."
        ),
    )
    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Their job title, or null.",
    )
    topic_text: str | None = Field(
        default=None,
        min_length=1,
        max_length=4000,
        description=(
            "§18's topic/interests/expertise text. Compared semantically by §9; "
            "nothing here parses it."
        ),
    )
    prior_talk: str | None = Field(
        default=None,
        min_length=1,
        max_length=4000,
        description="§18's optional prior talk information.",
    )
    location_city: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="§10: city or ZIP is sufficient. Neither is derived from the other.",
    )
    location_postal_code: str | None = Field(
        default=None,
        min_length=1,
        max_length=20,
        description="The other half of §10's 'or'.",
    )
    primary_industry_code: str | None = Field(
        default=None,
        description=(
            "Customer §7's single primary sector code, or null. Null is a real "
            "state: §19 records a contact first and classifies them after."
        ),
    )
    primary_role_code: str | None = Field(
        default=None,
        description="Customer §8's single primary role category code, or null.",
    )
    contact_email: str | None = Field(
        default=None,
        max_length=320,
        description=(
            "Accepted and then discarded. This address is never stored, never "
            "becomes a contact channel, and never makes this person writable-to "
            "(OQ-CBA-011, ratified). The response reports it in `withheld_fields` "
            "so the refusal is visible rather than silent — see OQ-CBA-015."
        ),
    )


class SpeakerContactUpdate(SpeakerContactCreate):
    """Edit one contact. The body states the record in full, absences included.

    Inherits every field from the create, including ``contact_email``, which is
    withheld here on the same terms — a field a client may send on the create and
    not on the edit is a field they will assume the edit preserved.

    A ``PATCH`` that states the whole record rather than a delta is deliberate:
    §13's edit form posts every box, and a Connector who empties the company box
    means the company is gone. A merge-shaped edit would make removing a value
    the one change they could never make.
    """


class ClassificationCorrectionRequest(BaseModel):
    """Correct one or both of a contact's §§7-8 classification axes.

    An omitted axis is left alone, never cleared. Nothing in §13 or §§7-8
    describes un-classifying a speaker, and giving null two meanings — "not part
    of this correction" and "delete the stored value" — would make the commoner
    case the dangerous one.

    Note what is not here: no field saying who is correcting, and none saying
    what the value was before. OQ-CBA-008's interim ruling is current value only,
    and a request field for provenance would be this route inventing the audit
    vocabulary that ruling declines to invent.
    """

    primary_industry_code: str | None = Field(
        default=None,
        description="§7's sector code, or null to leave the stored industry untouched.",
    )
    primary_role_code: str | None = Field(
        default=None,
        description="§8's role category code, or null to leave the stored role untouched.",
    )


class SpeakerContactClassificationSource(BaseModel):
    """How each axis's current value was set (OQ-CBA-008).

    Two fields and not six: the timestamps and the actor id are on the row, and
    a §13 roster screen does not need them to answer the question this surface
    exists to answer — *has anybody looked at this?* Exposing
    ``classified_by_user_id`` would put one Connector's account id in front of
    another with no screen asking for it, and OQ-CBA-008 recorded provenance for
    accountability rather than for display.

    ``null`` on an axis means unclassified, which is a real state: §19 imports a
    contact first and classifies it afterwards.
    """

    industry: str | None = Field(
        default=None,
        description="'inferred', 'human', or null when the industry is unclassified.",
    )
    role: str | None = Field(
        default=None,
        description="'inferred', 'human', or null when the role is unclassified.",
    )


class SameNameContact(BaseModel):
    """One contact this unit already holds under a name a write just used.

    Carried by both hints — the create's ``same_name_contacts`` and the edit's
    ``name_now_shared_with`` — because "who else is called this" has one honest
    answer and rendering it two ways would invite the two to drift. What differs
    between the routes is the *claim being made*, and that lives in the field
    name rather than in the shape underneath it.

    Enough to recognize a person and nothing more. The identifying fields are
    here because a bare "somebody has this name" is not something a Connector
    can act on, and "Dana Reyes, Principal Analyst at Reyes Analytics" is — that
    was the removed ``409``'s one virtue and it is the part kept.

    What is **not** here is everything else on the row: no classification, no
    provenance, no match eligibility, no email of any kind. This is a prompt to
    look, not a second way to read a contact — the roster and the by-id read are
    that, and both are one call away with their own authorization already
    applied.
    """

    professional_id: uuid.UUID
    full_name: str = Field(
        description=(
            "As stored, not as folded. The match is case- and space-insensitive, "
            "so this may differ from what the caller typed — and seeing how the "
            "existing record spells the name is part of recognizing it."
        )
    )
    company: str | None
    title: str | None
    created_at: str = Field(
        description=(
            "When this contact was added. The one field that helps a Connector "
            "tell 'I added this five seconds ago by double-clicking' from 'this "
            "person has been on the roster since March'."
        )
    )


class SpeakerContactResponse(BaseModel):
    """One stored contact, as §13's screens render it.

    Carries **no email of any kind** — neither the address the create discarded
    nor the ``.invalid`` placeholder ``user_account`` holds. A response field
    holding an address is the first thing a later card would try to send to, and
    there is nothing here to send to.
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
    classification_source: SpeakerContactClassificationSource
    match_eligible: bool = Field(
        description=(
            "Whether customer §19's review step has been satisfied on both axes, "
            "and therefore whether this contact may enter matching. False for an "
            "unclassified contact and for one carrying a classifier's proposal "
            "nobody has reviewed."
        )
    )
    match_ineligibility_reason: str | None = Field(
        default=None,
        description=(
            "Why this contact may not enter matching yet, or null when it may. A "
            "stable token rather than a sentence, and a reason rather than a bare "
            "false, so a screen can tell 'the classifier proposed Finance and "
            "nobody has checked' from 'we have no idea where this person works' — "
            "two states that call for different actions and would otherwise be one "
            "greyed-out row."
        ),
    )
    created_at: str
    updated_at: str
    withheld_fields: list[str] = Field(
        default_factory=list,
        description=(
            "Fields this request supplied that were deliberately not stored. "
            "Empty on reads. Present so a discard is something the caller is told "
            "about rather than something they infer from an absence."
        ),
    )
    same_name_contacts: list[SameNameContact] = Field(
        default_factory=list,
        description=(
            "Other contacts in this unit that already carry the name this create "
            "used, matched case- and space-insensitively. **A hint, never a "
            "refusal** — the contact in this response was created, and these are "
            "additional people the caller may not have meant to duplicate. Empty "
            "on every read and on every edit, and empty on a create when nobody "
            "else has the name, which is the ordinary case."
        ),
    )
    same_name_truncated: bool = Field(
        default=False,
        description=(
            "True when more same-name contacts exist than this response lists. "
            "Answered by reading one row past the cap, so a capped hint never "
            "reads as the complete set — the same guarantee the roster's "
            "`truncated` gives. False on reads and edits."
        ),
    )
    name_now_shared_with: list[SameNameContact] = Field(
        default_factory=list,
        description=(
            "Other contacts in this unit that carry the name this **edit** just "
            "moved the contact to, matched case- and space-insensitively. **A "
            "hint, never a refusal** — the edit in this response is committed, "
            "and this says who it collided with. Deliberately not "
            "`same_name_contacts`: that field means *you may be about to "
            "duplicate somebody* and this one means *you may have just collided "
            "with somebody*, and a client holding one under the other's name "
            "would be reading the wrong sentence. Empty on every create and "
            "every read; empty on an edit that left the name alone, that only "
            "re-cased or re-spaced it, or that moved it to a name nobody else "
            "holds — which is the ordinary case."
        ),
    )
    name_now_shared_with_truncated: bool = Field(
        default=False,
        description=(
            "True when more contacts share the new name than this response "
            "lists. Answered by reading one row past the cap, exactly as "
            "`same_name_truncated` is. False on creates and reads."
        ),
    )


class SpeakerContactListResponse(BaseModel):
    """A page of a unit's contacts."""

    contacts: list[SpeakerContactResponse]
    truncated: bool = Field(
        description=(
            "True when more contacts exist than this response carries. Answered by "
            "reading one row past the cap, so a full page never reads as a "
            "complete roster."
        )
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _authorize_speaker_contacts(
    session: Session,
    principal: CurrentPrincipal,
    unit_id: uuid.UUID,
) -> uuid.UUID:
    """Load the unit and authorize a Speaker Connector against *that row's* path.

    Shared by all five operations, in the spirit of ``_authorize_outreach`` and
    ``_authorize_match_run``: they ask the identical question against the
    identical resource, so a widening applies to all of them or to none. The
    module docstring explains why this is one function where
    ``routers/speaker_requests.py`` deliberately has two.

    The unit is loaded first and authorization runs against that row's own path,
    never against a path taken from the request. ``load_unit_or_404`` scopes the
    lookup by the caller's own tenant, so a unit in another tenant is a 404
    rather than a 403 that would confirm the id names something real.

    No ``require_membership`` — :data:`_SPEAKER_CONTACT_ROLES` is non-empty, so
    ``evaluate`` already refuses a bare ``resource_grant`` on the required-roles
    check (S-007). No ``tenant_wide_roles`` — the metrics decision's §4 is the
    only artifact that makes anything tenant-wide, and it says so of aggregate
    reads rather than of a department's own roster.

    Returns:
        The authorized unit id, which is what every read and write is scoped by.
    """
    unit = load_unit_or_404(session, tenant_id=principal.tenant_id, unit_id=unit_id)
    assert_allowed(
        principal.principal,
        Resource(
            resource_type="org_unit",
            resource_id=str(unit_id),
            tenant_id=str(principal.tenant_id),
            owning_unit_path=OrgPath.parse(unit.path),
        ),
        at=utc_now(),
        required_roles=_SPEAKER_CONTACT_ROLES,
    )
    return unit_id


def _view(
    row: SpeakerContactRow,
    *,
    withheld: list[str] | None = None,
    same_name: tuple[SpeakerContactRow, ...] | None = None,
    name_now_shared_with: tuple[SpeakerContactRow, ...] | None = None,
) -> SpeakerContactResponse:
    """Render one stored contact.

    ``withheld`` is passed only by the write paths, and only for fields the
    request actually supplied — a read reports nothing withheld, because a read
    supplied nothing to withhold.

    ``same_name`` is passed only by the **create**, and
    ``name_now_shared_with`` only by the **edit**, for the same shape of reason:
    each hint answers a question its own route asks and a read asks neither, so
    an empty list on a read is the absence of a question rather than a claim
    that nobody shares the name. Passing them here rather than reading them
    inside means a read cannot accidentally acquire an extra query, and it is
    also what keeps the two mutually exclusive by construction — a route that
    passes one passes ``None`` for the other, so no response can make both
    claims at once (OQ-CBA-049).

    Truncation is decided here for both, rather than by the repository, which
    returns at most what it was asked for and says nothing about the rest —
    ``list_for_unit``'s arrangement. Each caller asks for
    ``MAX_SAME_NAME_HINTS + 1``; this renders the first
    :data:`MAX_SAME_NAME_HINTS` and reports whether there were more.
    """
    matches = same_name or ()
    collisions = name_now_shared_with or ()
    return SpeakerContactResponse(
        professional_id=row.professional_id,
        owning_unit_id=row.owning_unit_id,
        full_name=row.full_name,
        company=row.company,
        title=row.title,
        topic_text=row.topic_text,
        prior_talk=row.prior_talk,
        location_city=row.location_city,
        location_postal_code=row.location_postal_code,
        primary_industry_code=row.primary_industry_code,
        industry_taxonomy_version=row.industry_taxonomy_version,
        primary_role_code=row.primary_role_code,
        role_taxonomy_version=row.role_taxonomy_version,
        classification_source=SpeakerContactClassificationSource(
            industry=row.industry_classification_source,
            role=row.role_classification_source,
        ),
        # Read off the row rather than recomputed here, so the roster screen and
        # the eligibility filter a matching pool is built from cannot disagree
        # about whether one contact is ready.
        match_eligible=row.match_eligible,
        match_ineligibility_reason=row.match_ineligibility_reason,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
        withheld_fields=withheld or [],
        same_name_contacts=[
            SameNameContact(
                professional_id=match.professional_id,
                full_name=match.full_name,
                company=match.company,
                title=match.title,
                created_at=match.created_at.isoformat(),
            )
            for match in matches[:MAX_SAME_NAME_HINTS]
        ],
        same_name_truncated=len(matches) > MAX_SAME_NAME_HINTS,
        name_now_shared_with=[
            SameNameContact(
                professional_id=match.professional_id,
                full_name=match.full_name,
                company=match.company,
                title=match.title,
                created_at=match.created_at.isoformat(),
            )
            for match in collisions[:MAX_SAME_NAME_HINTS]
        ],
        name_now_shared_with_truncated=len(collisions) > MAX_SAME_NAME_HINTS,
    )


def _withheld_fields(body: SpeakerContactCreate) -> list[str]:
    """Which supplied fields were deliberately not stored.

    Only ``contact_email``, and only when the caller actually sent one. Reporting
    it unconditionally would tell every caller about a refusal that did not
    happen to them, which is how a field trains people to ignore it.
    """
    return [WITHHELD_CONTACT_EMAIL_FIELD] if body.contact_email is not None else []


def _draft_or_400(body: SpeakerContactCreate) -> SpeakerContactDraft:
    """Build a validated draft, turning the domain's three refusals into ``400``s.

    The taxonomy lookups raise rather than quarantine because §13's Connector
    picks from a rendered list: a code off the list is a client defect, not a
    spreadsheet cell awaiting review. Quarantine is the import path's problem
    (OQ-CBA-010) and this is not that path.

    Raises:
        ApiError: 400, naming which field was refused and why.
    """
    try:
        return SpeakerContactDraft.create(
            full_name=body.full_name,
            company=body.company,
            title=body.title,
            topic_text=body.topic_text,
            prior_talk=body.prior_talk,
            location_city=body.location_city,
            location_postal_code=body.location_postal_code,
            primary_industry_code=body.primary_industry_code,
            primary_role_code=body.primary_role_code,
        )
    except UnknownNaicsSector as exc:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="speaker_contact_industry_code_unknown",
            message=str(exc),
        ) from exc
    except UnknownCbaRoleCategory as exc:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="speaker_contact_role_code_unknown",
            message=str(exc),
        ) from exc
    except ValueError as exc:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="speaker_contact_invalid",
            message=str(exc),
        ) from exc


def _not_found() -> ApiError:
    """The 404 every by-id route raises.

    A contact that exists under a *different* unit is reported identically to one
    that does not exist, exactly as ``outreach_contacts._load_or_404`` does it: a
    403 would confirm that an id the caller may not read names a real person.
    """
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="speaker_contact_not_found",
        message="No such speaker contact in this unit.",
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@router.post(
    "/{unit_id}/speaker-contacts",
    status_code=status.HTTP_201_CREATED,
    response_model=SpeakerContactResponse,
    summary="Add a speaker contact to a unit",
)
def create_speaker_contact(
    principal: CurrentPrincipal,
    session: DbSession,
    body: SpeakerContactCreate,
    unit_id: Annotated[uuid.UUID, Path()],
) -> SpeakerContactResponse:
    """Record one professional this unit knows (customer §13).

    ``201``: this has completed when it returns. Three rows exist — the
    professional's ``user_account``, their link to this unit, and the
    ``speaker_profile`` holding what the Connector typed.

    No ``contact_channel`` row is written and no consent is recorded. If the body
    carried ``contact_email``, it was discarded and is named in
    ``withheld_fields``.

    **A name this unit already holds is not an error.** The identity is opaque
    (OQ-CBA-017), so this create stores a second, distinct person and reports
    the ones already carrying the name in ``same_name_contacts``. There is no
    ``409`` on this route any more, and there is no circumstance in which the
    hint prevents the write — see the module docstring.

    Raises:
        ApiError: 400 when a field is blank or a classification code is outside
            its closed taxonomy. Nothing else; a same-name create is a ``201``.
    """
    charge_quota(session, principal, SPEAKER_CONTACT_WRITE_RATE_LIMIT)

    owning_unit_id = _authorize_speaker_contacts(session, principal, unit_id)
    draft = _draft_or_400(body)

    created = _contacts.create(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=owning_unit_id,
        draft=draft,
        # §19's step five, satisfied at the moment the value is set: a code
        # typed into §13's form is this Connector's judgment, so it is stored
        # as `human` with them named rather than left for a review that has
        # already happened.
        actor_id=principal.user_id,
        # One past the cap, so `same_name_truncated` is answered by the read
        # itself rather than by a second count — the shape the roster listing
        # uses for its own `truncated`.
        same_name_limit=MAX_SAME_NAME_HINTS + 1,
    )

    # `get_session` rolls back unconditionally on the way out — a route that
    # changes state commits explicitly, and committing by default would turn a
    # half-finished request into a persisted one. All three rows land here or
    # none of them do.
    session.commit()

    return _view(
        created.contact,
        withheld=_withheld_fields(body),
        same_name=created.same_name,
    )


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


@router.get(
    "/{unit_id}/speaker-contacts",
    response_model=SpeakerContactListResponse,
    summary="List a unit's speaker contacts",
)
def list_speaker_contacts(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
) -> SpeakerContactListResponse:
    """This unit's roster, by name.

    Reads at most :data:`MAX_ROWS` + 1 rows so ``truncated`` is answered by the
    read itself rather than by a second count — the shape
    ``routers/speaker_requests.py`` uses for the same reason.
    """
    charge_quota(session, principal, SPEAKER_CONTACT_READ_RATE_LIMIT)

    owning_unit_id = _authorize_speaker_contacts(session, principal, unit_id)

    rows = _contacts.list_for_unit(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=owning_unit_id,
        limit=MAX_ROWS + 1,
    )
    return SpeakerContactListResponse(
        contacts=[_view(row) for row in rows[:MAX_ROWS]],
        truncated=len(rows) > MAX_ROWS,
    )


@router.get(
    "/{unit_id}/speaker-contacts/{professional_id}",
    response_model=SpeakerContactResponse,
    summary="Read one speaker contact",
)
def read_speaker_contact(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    professional_id: Annotated[uuid.UUID, Path()],
) -> SpeakerContactResponse:
    """One contact from this unit's roster.

    Raises:
        ApiError: 404 when the contact is not in this unit.
    """
    charge_quota(session, principal, SPEAKER_CONTACT_READ_RATE_LIMIT)

    owning_unit_id = _authorize_speaker_contacts(session, principal, unit_id)

    row = _contacts.get(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=owning_unit_id,
        professional_id=professional_id,
    )
    if row is None:
        raise _not_found()
    return _view(row)


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------


@router.patch(
    "/{unit_id}/speaker-contacts/{professional_id}",
    response_model=SpeakerContactResponse,
    summary="Edit one speaker contact",
)
def update_speaker_contact(
    principal: CurrentPrincipal,
    session: DbSession,
    body: SpeakerContactUpdate,
    unit_id: Annotated[uuid.UUID, Path()],
    professional_id: Annotated[uuid.UUID, Path()],
) -> SpeakerContactResponse:
    """Replace what this unit records about one contact.

    The body states the record in full, so an omitted optional field clears the
    stored value rather than preserving it — §13's form posts every box, and a
    Connector who empties one means it is empty.

    Changing ``full_name`` changes the displayed name and **not** the identity.
    ``professional_id`` is generated rather than derived (OQ-CBA-017), so there
    is no longer any sense in which a rename *could* move it — which is the
    point of the decision, since under the previous scheme the id stayed put
    while quietly ceasing to correspond to the name beside it.

    **A rename into an existing name is reported, and the field is not the
    create's.** This route answers ``name_now_shared_with`` where the create
    answers ``same_name_contacts``, and the two names are deliberately different
    because the two sentences are: a create says *you may be about to duplicate
    somebody*, an edit says *you may have just collided with somebody*. The
    module docstring argues that at length; what matters at this call site is
    that a client can never be holding one while reading the other's meaning.

    Neither field is a refusal. The ``UPDATE`` has already happened when the
    hint is composed, the response is a ``200`` whatever it contains, and there
    is no uniqueness constraint on ``(tenant_id, owning_unit_id, full_name)``
    anywhere under this route (OQ-CBA-021) — a Connector who has looked and
    decided these are two different people simply proceeds.

    The hint is quiet unless the edit **moved** the name. The stored contact is
    read before the write for exactly that reason, and the two names are
    compared through ``folded_contact_name`` — the create's fold, so a save that
    only re-cases or re-spaces the name is not a rename and the collision set it
    belongs to has not changed. A hint on every save of §13's form, which posts
    the whole record every time, would be noise a Connector learns to skip.

    The lookup excludes this contact (``exclude_professional_id``). A row is not
    a duplicate of itself, and after the write it carries the very name being
    searched for — the create gets that guarantee free by reading before it
    inserts, and this route has to ask for it.

    Raises:
        ApiError: 400 when a field is blank or a classification code is unknown;
            404 when the contact is not in this unit. A rename that collides is
            none of those — it is a ``200`` carrying a hint.
    """
    charge_quota(session, principal, SPEAKER_CONTACT_WRITE_RATE_LIMIT)

    owning_unit_id = _authorize_speaker_contacts(session, principal, unit_id)
    draft = _draft_or_400(body)

    # Read before the write, and only for the name: the hint has to know whether
    # this edit *changed* it, and the UPDATE's RETURNING can only say what the
    # name is now. A miss here is the same 404 the write would have produced, so
    # the extra read costs a query rather than a behaviour.
    stored = _contacts.get(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=owning_unit_id,
        professional_id=professional_id,
    )
    if stored is None:
        raise _not_found()

    row = _contacts.update(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=owning_unit_id,
        professional_id=professional_id,
        draft=draft,
        actor_id=principal.user_id,
    )
    if row is None:
        raise _not_found()

    shared: tuple[SpeakerContactRow, ...] = ()
    if folded_contact_name(row.full_name) != folded_contact_name(stored.full_name):
        shared = _contacts.list_same_name(
            session,
            tenant_id=principal.tenant_id,
            owning_unit_id=owning_unit_id,
            full_name=row.full_name,
            # One past the cap, so `name_now_shared_with_truncated` is answered
            # by the read itself rather than by a second count — the create's
            # arrangement, and the roster listing's before it.
            limit=MAX_SAME_NAME_HINTS + 1,
            exclude_professional_id=professional_id,
        )

    # Explicit, for the reason the create states. Placed after the 404 guard so
    # a miss commits nothing.
    session.commit()

    return _view(row, withheld=_withheld_fields(body), name_now_shared_with=shared)


# ---------------------------------------------------------------------------
# Classification correction
# ---------------------------------------------------------------------------


@router.post(
    "/{unit_id}/speaker-contacts/{professional_id}/classification",
    response_model=SpeakerContactResponse,
    summary="Correct a speaker contact's classification",
)
def correct_speaker_contact_classification(
    principal: CurrentPrincipal,
    session: DbSession,
    body: ClassificationCorrectionRequest,
    unit_id: Annotated[uuid.UUID, Path()],
    professional_id: Annotated[uuid.UUID, Path()],
) -> SpeakerContactResponse:
    """Replace one or both classification axes (customer §§7-8, §19).

    Its own route rather than a corner of the edit, because it is its own act: a
    Connector correcting an inferred classification is doing something they can
    describe, and folding it into the general edit would make "I fixed the
    industry" and "I retyped the whole record" the same event in every log.

    A ``POST`` rather than a ``PATCH`` on a sub-resource, for the reason
    ``outreach_contacts``' transitions are a POST: this is an act performed on the
    contact, not a field being set on it.

    The write is a current-value ``UPDATE`` that bumps ``updated_at``, and it
    records **who** corrected each axis and when — OQ-CBA-008, decided on
    6 September 2026 as *provenance, no history*. What the value was before is
    still not recorded anywhere, and deliberately: see migration ``0028``.

    A corrected axis becomes ``human``, which is what §19's step five gates
    matching on, so this route is how an inferred contact becomes matchable. An
    axis this body does not name is left exactly as it was, provenance included.

    Raises:
        ApiError: 400 when the correction names neither axis, or names a code
            outside its closed taxonomy; 404 when the contact is not in this
            unit.
    """
    charge_quota(session, principal, SPEAKER_CONTACT_WRITE_RATE_LIMIT)

    owning_unit_id = _authorize_speaker_contacts(session, principal, unit_id)

    try:
        correction = ClassificationCorrection.create(
            primary_industry_code=body.primary_industry_code,
            primary_role_code=body.primary_role_code,
        )
    except UnknownNaicsSector as exc:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="speaker_contact_industry_code_unknown",
            message=str(exc),
        ) from exc
    except UnknownCbaRoleCategory as exc:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="speaker_contact_role_code_unknown",
            message=str(exc),
        ) from exc
    except ValueError as exc:
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="speaker_contact_correction_empty",
            message=str(exc),
        ) from exc

    row = _contacts.correct_classification(
        session,
        tenant_id=principal.tenant_id,
        owning_unit_id=owning_unit_id,
        professional_id=professional_id,
        correction=correction,
        # A correction wins over a proposal and takes its author's name with it.
        actor_id=principal.user_id,
    )
    if row is None:
        raise _not_found()

    # Explicit, for the reason the create states. Placed after the 404 guard so
    # a correction aimed at a contact this unit does not hold commits nothing.
    session.commit()

    return _view(row)
