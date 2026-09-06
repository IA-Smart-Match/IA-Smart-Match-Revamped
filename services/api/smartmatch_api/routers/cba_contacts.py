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

## A duplicate name is a 409, not a merge and not a second row

The identity is derived from ``(tenant, unit, folded name)``, so two genuinely
different people who share a name in one unit derive one id. Upserting would
overwrite the first person's record with the second's while looking like a
successful save; a second insert is not available, because the derived id is the
primary key. So the create answers ``409`` and names who is already there, which
is something a Connector can recognize or dispute. **OQ-CBA-017** is where what
they should then be able to *do* about it is recorded rather than guessed.

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
)
from smartmatch_domain.cba_role_categories import UnknownCbaRoleCategory
from smartmatch_domain.naics_sectors import UnknownNaicsSector
from smartmatch_persistence.cba_contacts import (
    SpeakerContactAlreadyExists,
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


# ---------------------------------------------------------------------------
# Request and response models
# ---------------------------------------------------------------------------


class SpeakerContactCreate(BaseModel):
    """One speaker contact, as a Speaker Connector fills it in (customer §13).

    Note what is **not** here: no tenant, no owning unit, no professional id, no
    actor. The first two come from the verified principal and the path; the third
    is derived from the name rather than supplied, so a caller cannot choose
    somebody else's identity (MM-A01); the fourth is never a body field.

    ``contact_email`` **is** here, and is the one field this model accepts in
    order to refuse. See the module docstring.
    """

    full_name: str = Field(
        min_length=1,
        max_length=200,
        description=(
            "The contact's name. The one field without which the record is not a "
            "contact, and the field the stored identity is derived from — so two "
            "submissions of the same name in the same unit are the same person."
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


def _view(row: SpeakerContactRow, *, withheld: list[str] | None = None) -> SpeakerContactResponse:
    """Render one stored contact.

    ``withheld`` is passed only by the write paths, and only for fields the
    request actually supplied — a read reports nothing withheld, because a read
    supplied nothing to withhold.
    """
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
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
        withheld_fields=withheld or [],
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

    Raises:
        ApiError: 400 when a field is blank or a classification code is outside
            its closed taxonomy; 409 when this unit already holds a contact under
            the identity this name derives.
    """
    charge_quota(session, principal, SPEAKER_CONTACT_WRITE_RATE_LIMIT)

    owning_unit_id = _authorize_speaker_contacts(session, principal, unit_id)
    draft = _draft_or_400(body)

    try:
        row = _contacts.create(
            session,
            tenant_id=principal.tenant_id,
            owning_unit_id=owning_unit_id,
            draft=draft,
            # §19's step five, satisfied at the moment the value is set: a code
            # typed into §13's form is this Connector's judgment, so it is stored
            # as `human` with them named rather than left for a review that has
            # already happened.
            actor_id=principal.user_id,
        )
    except SpeakerContactAlreadyExists as exc:
        # 409 rather than 200-with-the-existing-row. The caller asked to add
        # somebody; answering with a different person's record because the names
        # match would be a merge performed silently, and OQ-CBA-017 is exactly
        # the question of whether that is ever what they meant.
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="speaker_contact_name_already_used",
            message=str(exc),
        ) from exc

    # `get_session` rolls back unconditionally on the way out — a route that
    # changes state commits explicitly, and committing by default would turn a
    # half-finished request into a persisted one. All three rows land here or
    # none of them do.
    session.commit()

    return _view(row, withheld=_withheld_fields(body))


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

    Changing ``full_name`` changes the displayed name and **not** the identity:
    ``professional_id`` was derived at create time and is now a stored key other
    rows reference. ``smartmatch_persistence.cba_contacts`` states the
    consequence in full.

    Raises:
        ApiError: 400 when a field is blank or a classification code is unknown;
            404 when the contact is not in this unit.
    """
    charge_quota(session, principal, SPEAKER_CONTACT_WRITE_RATE_LIMIT)

    owning_unit_id = _authorize_speaker_contacts(session, principal, unit_id)
    draft = _draft_or_400(body)

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

    # Explicit, for the reason the create states. Placed after the 404 guard so
    # a miss commits nothing.
    session.commit()

    return _view(row, withheld=_withheld_fields(body))


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
