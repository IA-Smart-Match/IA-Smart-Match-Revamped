"""Server-side evidence assembly for a match run (OQ-CBA-031).

Until this module existed, ``POST /v1/units/{unit_id}/match-runs`` took a
candidate's evidence **from the request body**. Two things were wrong with
that, and only the second is obvious.

The obvious one is arithmetic: body evidence is ``topic_relevance`` and
``travel_burden``, so the route could only call
:func:`~smartmatch_domain.scoring.rank_candidates` — the superseded two-factor
composition — and every run a client could obtain was pinned to
``1.1.1-approved-g1-m6j`` with ``scoring_mode: null``. Registry
``2.0.0-approved-oq-cba-004`` was approved, golden-verified and unreachable
through any client path.

The other one is trust. A caller could assert whatever evidence it liked and
the stored run recorded that assertion as fact: a coordinator could hand a
speaker any expertise and any coordinates, and the immutable snapshot — the
artifact whose entire purpose is to say what was actually scored — would agree
with them. A run assembled here says what the *record* said, and the record is
``speaker_profile``, written through the import and review path customer §19
describes.

## What is read, and from where

Run-level facts come off the filed Speaker Request (customer §12), which is an
``event`` row with ``origin = 'coordinator_entry'`` and its
``speaker_request_classification`` targets:

* ``description`` — §9's text, compared semantically against each speaker's
  topic evidence.
* ``is_virtual`` — §11's switch, and therefore the run's **scoring mode**.
  ADR-0016 requires the mode to be "resolved from the event before scoring and
  never inferred", and this is that resolution: there is no request field a
  caller could set to choose one.
* the requested industry sectors and role categories (§§7, 8, 12).

Per-candidate evidence comes off ``speaker_profile``, keyed by ``subject_id``:

===========================  ==========================================
Evidence                     Source column
===========================  ==========================================
``industry.speaker_sector``  ``primary_industry_code`` +
                             ``industry_taxonomy_version``
``role.speaker_role``        ``primary_role_code`` +
                             ``role_taxonomy_version``
``topic_evidence``           ``topic_text``, ``prior_talk``
``location``                 ``location_city``, ``location_postal_code``
``distance_miles``           ``location_postal_code`` against the
                             OQ-CBA-024 ZCTA centroid table — see below
===========================  ==========================================

## Track 16's eligibility gate is honoured, not re-implemented

:func:`~smartmatch_domain.cba_classification.match_ineligibility_reason` is the
one authority on whether a contact may enter matching: §19 orders review before
availability, and a classification a machine proposed is a proposal until a
person confirms it. An ineligible contact is **absent** from the pool — not
scored, not entered at zero, not ranked last. It is reported by
:class:`ExcludedCandidate` so the absence is visible and actionable, which is
the same discipline ADR-0011 applies to an unknown factor.

Absence rather than a penalty matters here for the reason it always does: a
proposed classification entered into the pool would be scored as though somebody
had checked it, and a low rank would read as "we looked and they are a poor
fit" rather than "nobody has reviewed this record yet".

## No coordinate is ever invented

``distance_miles`` comes from one place: a **table lookup**.
:func:`~smartmatch_api.zip_proximity.resolve_distance_from_campus` reads the
speaker's stored postal code against the static, offline, build-time-generated
California ZCTA centroid table of OQ-CBA-024 and measures a straight line to the
campus origin. Nothing here geocodes, consults a provider, opens a socket, or
falls back to a plausible number.

A ZIP the table does not name — blank, malformed, or outside California —
resolves to ``None`` and is passed on as ``None``. That is an *unknown*
distance, and ``score_proximity`` renders it as one: not the Far band, not
``0.0``, and distinguishable in its basis string from a speaker who has no place
on file at all. The two are different facts and the surface must be able to tell
them apart, because they call for different actions — one needs an address, the
other needs a ZIP a Californian table can reach.

City names are **not** resolved. ``speaker_profile`` has no state column, so
"Pomona" is ambiguous across states, and the disambiguation rule is an unmade
product decision registered as **OQ-CBA-063**. A city table keyed on name alone
would place Pomona, New York in California and produce a distance that looks
exactly as trustworthy as a correct one.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

import sqlalchemy as sa
from smartmatch_domain.cba_classification import match_ineligibility_reason
from smartmatch_domain.cba_role_categories import (
    CBA_ROLE_TAXONOMY_VERSION,
    ClassifiedRoleCategory,
    RoleCategoryResolution,
    UnknownCbaRoleCategory,
    role_category_for_code,
)
from smartmatch_domain.factors.cba_semantic_topic import SpeakerTopicEvidence
from smartmatch_domain.factors.industry_match import IndustryMatchInputs
from smartmatch_domain.factors.proximity import (
    CBA_PHYSICAL_SCORING_MODE,
    CBA_VIRTUAL_SCORING_MODE,
    SpeakerLocation,
)
from smartmatch_domain.factors.role_match import RoleMatchInputs
from smartmatch_domain.naics_sectors import (
    NAICS_TAXONOMY_VERSION,
    ClassifiedSector,
    SectorResolution,
    UnknownNaicsSector,
    sector_for_code,
)
from smartmatch_domain.scoring import CbaCandidateEvidence
from smartmatch_domain.speaker_requests import KIND_INDUSTRY, KIND_ROLE
from smartmatch_persistence import schema
from smartmatch_persistence.events import ORIGIN_COORDINATOR_ENTRY
from sqlalchemy.orm import Session

from smartmatch_api.zip_proximity import resolve_distance_from_campus

__all__ = [
    "EXCLUSION_INDUSTRY_CODE_UNRECOGNISED",
    "EXCLUSION_INDUSTRY_TAXONOMY_SUPERSEDED",
    "EXCLUSION_PROFILE_NOT_FOUND",
    "EXCLUSION_ROLE_CODE_UNRECOGNISED",
    "EXCLUSION_ROLE_TAXONOMY_SUPERSEDED",
    "AssembledPool",
    "ExcludedCandidate",
    "SpeakerRequestEvidence",
    "assemble_cba_pool",
    "load_speaker_request",
]

#: No ``speaker_profile`` row for this subject in this unit. Reported rather
#: than scored as an unknown: the record was never reached, so there is nothing
#: about this person to explain, and the Speaker Connector's action is to import
#: or re-home them rather than to fill a factor in.
EXCLUSION_PROFILE_NOT_FOUND: Final[str] = "speaker_profile_not_found"

#: The stored classification was resolved against a taxonomy this release no
#: longer scores against. ``industry_match`` refuses to compare across versions
#: rather than pretending two vocabularies agree, so the record must be resolved
#: again — a review action, which is why this is an absence and not a low score.
EXCLUSION_INDUSTRY_TAXONOMY_SUPERSEDED: Final[str] = "industry_taxonomy_version_superseded"

#: Same, for ``role_match``.
EXCLUSION_ROLE_TAXONOMY_SUPERSEDED: Final[str] = "role_taxonomy_version_superseded"

#: A stored code the released NAICS table does not name.
#: ``ck_speaker_profile_industry_code`` forbids such a row, so reaching this
#: means the vocabulary moved under a stored value; it is reported rather than
#: guessed at.
EXCLUSION_INDUSTRY_CODE_UNRECOGNISED: Final[str] = "industry_code_unrecognised"

#: Same, for the CBA role vocabulary.
EXCLUSION_ROLE_CODE_UNRECOGNISED: Final[str] = "role_code_unrecognised"


@dataclass(frozen=True, slots=True)
class SpeakerRequestEvidence:
    """The run-level facts one filed Speaker Request supplies.

    Attributes:
        event_id: The request's ``event`` id. Becomes the run's
            ``event_need_id``, so a stored snapshot names the request it was
            produced for rather than a free string a caller chose.
        description: §12's topic/description, or ``""`` when the host filed the
            request before writing one. Empty is passed through rather than
            defaulted: ``score_cba_semantic_topic`` reads a blank description as
            *the request's* absence and returns unknown, which is a different
            fact from the speaker's own absence and must not be collapsed into
            it.
        is_virtual: §12's switch. The only input to :attr:`scoring_mode`.
        requested_sectors: §7's targets, already resolved.
        requested_roles: §8's targets, already resolved.
    """

    event_id: uuid.UUID
    description: str
    is_virtual: bool
    requested_sectors: tuple[SectorResolution, ...]
    requested_roles: tuple[RoleCategoryResolution, ...]

    @property
    def scoring_mode(self) -> str:
        """``cba-virtual-1`` or ``cba-physical-1``, from the event alone.

        A property rather than a stored field so there is no constructor
        parameter through which a mode could be supplied instead of derived.
        ADR-0016 Proposal 5: the mode is resolved from the event before scoring
        and never inferred at the scorer.
        """
        return CBA_VIRTUAL_SCORING_MODE if self.is_virtual else CBA_PHYSICAL_SCORING_MODE


@dataclass(frozen=True, slots=True)
class ExcludedCandidate:
    """One named candidate that did not enter the pool, and why.

    Attributes:
        subject_id: The subject the caller named.
        reason: A stable machine-readable token — one of this module's
            ``EXCLUSION_*`` constants, or one of
            ``match_ineligibility_reason``'s. Stable because a surface has to
            route a Connector to the right screen, and four situations that need
            four different actions must not arrive as one greyed-out row.
    """

    subject_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class AssembledPool:
    """What the named subjects produced: evidence for some, an absence for the rest.

    Attributes:
        evidence: The candidates that may be scored, in the order the caller
            named them. Ordering is the caller's throughout; the ratified
            tie-break is applied later by
            :func:`~smartmatch_domain.scoring.rank_cba_candidates`, and a second
            ordering rule here would be one nothing approved.
        excluded: The candidates that may not, each with its reason, in the same
            order. Never scored, never entered at zero, never ranked last.
    """

    evidence: tuple[CbaCandidateEvidence, ...]
    excluded: tuple[ExcludedCandidate, ...]


def load_speaker_request(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    host_org_unit_id: uuid.UUID,
    event_id: uuid.UUID,
) -> SpeakerRequestEvidence | None:
    """Read one filed Speaker Request, or ``None`` when this unit has no such row.

    Scoped by ``tenant_id`` **and** ``host_org_unit_id`` in the query rather
    than filtered afterwards, the discipline ``load_unit_or_404`` and
    ``JobRepository.get`` state. The unit scope is not decoration: the run is
    filed under the unit the caller was authorized for, so a request hosted by
    another unit is not this caller's to score against, and a 404 rather than a
    403 keeps the answer from confirming that the id names something real.

    ``origin = 'coordinator_entry'`` is required for the reason
    ``SpeakerRequestRepository.get`` gives: an extracted event is not a Speaker
    Request, and a discovery row reaching this path would let a fetched page's
    description drive a scoring run nobody filed.

    Read here rather than through ``SpeakerRequestRepository`` because that read
    model is not unit-scoped and carries a dozen fields this path must not act
    on; what is wanted is four facts under the scope the caller was authorized
    in.

    Returns:
        The request's run-level evidence, or ``None``.
    """
    row = session.execute(
        sa.select(
            schema.event.c.id,
            schema.event.c.description,
            schema.event.c.is_virtual,
        ).where(
            schema.event.c.tenant_id == tenant_id,
            schema.event.c.host_org_unit_id == host_org_unit_id,
            schema.event.c.id == event_id,
            schema.event.c.origin == ORIGIN_COORDINATOR_ENTRY,
        )
    ).one_or_none()
    if row is None:
        return None

    targets = session.execute(
        sa.select(
            schema.speaker_request_classification.c.kind,
            schema.speaker_request_classification.c.code,
            schema.speaker_request_classification.c.taxonomy_version,
        )
        .where(
            schema.speaker_request_classification.c.tenant_id == tenant_id,
            schema.speaker_request_classification.c.event_id == event_id,
        )
        .order_by(
            schema.speaker_request_classification.c.kind,
            schema.speaker_request_classification.c.code,
        )
    ).all()

    return SpeakerRequestEvidence(
        event_id=row.id,
        # A NULL description is ``""`` here and not ``None``: the scorer's
        # signature takes a string, and its blank branch is exactly the
        # "request has nothing to compare against" case a NULL means.
        description=row.description or "",
        is_virtual=bool(row.is_virtual),
        requested_sectors=_resolved_sectors(targets),
        requested_roles=_resolved_roles(targets),
    )


def _resolved_sectors(targets: Sequence[sa.Row[Any]]) -> tuple[SectorResolution, ...]:
    """The request's industry targets as the factor's own type.

    A stored target whose code or taxonomy version this release cannot honour
    is **dropped** rather than passed on. ``industry_match`` raises a
    ``ValueError`` for either — both are caller bugs from its point of view —
    and a 500 on a stale target would refuse the whole run rather than the one
    target it could not read. Dropping it narrows what the request asks for,
    which is visible in the score's basis, instead of inventing a target the
    host did not name.
    """
    resolved: list[SectorResolution] = []
    for target in targets:
        if target.kind != KIND_INDUSTRY or target.taxonomy_version != NAICS_TAXONOMY_VERSION:
            continue
        try:
            sector = sector_for_code(str(target.code))
        except UnknownNaicsSector:
            continue
        resolved.append(
            ClassifiedSector(sector=sector, taxonomy_version=str(target.taxonomy_version))
        )
    return tuple(resolved)


def _resolved_roles(targets: Sequence[sa.Row[Any]]) -> tuple[RoleCategoryResolution, ...]:
    """The request's role targets as the factor's own type. See :func:`_resolved_sectors`."""
    resolved: list[RoleCategoryResolution] = []
    for target in targets:
        if target.kind != KIND_ROLE or target.taxonomy_version != CBA_ROLE_TAXONOMY_VERSION:
            continue
        try:
            category = role_category_for_code(str(target.code))
        except UnknownCbaRoleCategory:
            continue
        resolved.append(
            ClassifiedRoleCategory(category=category, taxonomy_version=str(target.taxonomy_version))
        )
    return tuple(resolved)


def assemble_cba_pool(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    subject_ids: Sequence[uuid.UUID],
    request: SpeakerRequestEvidence,
) -> AssembledPool:
    """Build every named candidate's evidence from ``speaker_profile``.

    One query for the whole pool, then a per-subject decision in the caller's
    order. Nothing is read from a request body and nothing is defaulted: a
    column that is NULL arrives as ``None`` and the factor modules decide what
    that means, which is the only place that decision is allowed to live.

    Args:
        session: The caller's session. Nothing is written and nothing is
            committed.
        tenant_id: From the authenticated principal, never from a body.
        owning_unit_id: The unit the router already authorized against. Profiles
            owned by another unit are **not found** rather than refused: whether
            a parent unit may match on a child's roster is a policy question
            nobody has answered, and equality is the fail-closed reading of an
            unanswered question.
        subject_ids: The professionals to consider, in the caller's order. May
            contain duplicates; the caller refuses those before calling.
        request: The run-level evidence every candidate is scored against.

    Returns:
        An :class:`AssembledPool`.
    """
    rows = _profiles_by_professional_id(
        session, tenant_id=tenant_id, owning_unit_id=owning_unit_id, subject_ids=subject_ids
    )

    evidence: list[CbaCandidateEvidence] = []
    excluded: list[ExcludedCandidate] = []

    for subject_id in subject_ids:
        subject = str(subject_id)
        row = rows.get(subject_id)
        if row is None:
            excluded.append(ExcludedCandidate(subject, EXCLUSION_PROFILE_NOT_FOUND))
            continue

        # Track 16's gate, called and not re-derived. It is evaluated **before**
        # any evidence is assembled, so an unreviewed record's classification
        # never reaches a factor at all — there is no path by which it could be
        # scored and then filtered, which is the path that leaks a proposal into
        # a ranking.
        ineligible = match_ineligibility_reason(
            primary_industry_code=row.primary_industry_code,
            industry_classification_source=row.industry_classification_source,
            primary_role_code=row.primary_role_code,
            role_classification_source=row.role_classification_source,
        )
        if ineligible is not None:
            excluded.append(ExcludedCandidate(subject, ineligible))
            continue

        candidate = _candidate_evidence(subject, row, request)
        if isinstance(candidate, ExcludedCandidate):
            excluded.append(candidate)
            continue
        evidence.append(candidate)

    return AssembledPool(evidence=tuple(evidence), excluded=tuple(excluded))


def _profiles_by_professional_id(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    owning_unit_id: uuid.UUID,
    subject_ids: Iterable[uuid.UUID],
) -> Mapping[uuid.UUID, sa.Row[Any]]:
    """Every named profile this unit owns, keyed by ``professional_id``.

    The provenance columns are selected alongside the codes deliberately:
    ``match_ineligibility_reason`` answers against what was actually read, and a
    caller that omitted them would get ``*_classification_provenance_unknown``
    rather than a silent pass.
    """
    ids = list(dict.fromkeys(subject_ids))
    if not ids:
        return {}

    rows = session.execute(
        sa.select(
            schema.speaker_profile.c.professional_id,
            schema.speaker_profile.c.primary_industry_code,
            schema.speaker_profile.c.industry_taxonomy_version,
            schema.speaker_profile.c.industry_classification_source,
            schema.speaker_profile.c.primary_role_code,
            schema.speaker_profile.c.role_taxonomy_version,
            schema.speaker_profile.c.role_classification_source,
            schema.speaker_profile.c.topic_text,
            schema.speaker_profile.c.prior_talk,
            schema.speaker_profile.c.location_city,
            schema.speaker_profile.c.location_postal_code,
        ).where(
            schema.speaker_profile.c.tenant_id == tenant_id,
            schema.speaker_profile.c.owning_unit_id == owning_unit_id,
            schema.speaker_profile.c.professional_id.in_(ids),
        )
    ).all()
    return {row.professional_id: row for row in rows}


def _candidate_evidence(
    subject_id: str,
    row: sa.Row[Any],
    request: SpeakerRequestEvidence,
) -> CbaCandidateEvidence | ExcludedCandidate:
    """One eligible profile's evidence, or the reason it cannot be compared.

    Reached only for a row the eligibility gate passed, so both codes are
    present and both were set by a person. What can still go wrong is a
    *vocabulary* mismatch, and both factor modules refuse to compare across
    taxonomy versions rather than pretending two releases agree — so the refusal
    is turned into an absence here, where it can be reported with the record
    that needs re-resolving, instead of surfacing as an unhandled ``ValueError``.
    """
    if row.industry_taxonomy_version != NAICS_TAXONOMY_VERSION:
        return ExcludedCandidate(subject_id, EXCLUSION_INDUSTRY_TAXONOMY_SUPERSEDED)
    if row.role_taxonomy_version != CBA_ROLE_TAXONOMY_VERSION:
        return ExcludedCandidate(subject_id, EXCLUSION_ROLE_TAXONOMY_SUPERSEDED)

    try:
        sector = sector_for_code(str(row.primary_industry_code))
    except UnknownNaicsSector:
        return ExcludedCandidate(subject_id, EXCLUSION_INDUSTRY_CODE_UNRECOGNISED)
    try:
        category = role_category_for_code(str(row.primary_role_code))
    except UnknownCbaRoleCategory:
        return ExcludedCandidate(subject_id, EXCLUSION_ROLE_CODE_UNRECOGNISED)

    # Resolved for every candidate, physical or virtual. It is a dict lookup
    # against a table already in memory, and making it conditional on the mode
    # would put a second copy of "is proximity scored here" in this module —
    # `score_cba_candidate` already asks `proximity_is_scored` and simply does
    # not read the distance under `cba-virtual-1`.
    distance = resolve_distance_from_campus(row.location_postal_code)

    return CbaCandidateEvidence(
        subject_id=subject_id,
        industry=IndustryMatchInputs(
            speaker_sector=ClassifiedSector(
                sector=sector, taxonomy_version=str(row.industry_taxonomy_version)
            ),
            requested_sectors=request.requested_sectors,
        ),
        role=RoleMatchInputs(
            speaker_role=ClassifiedRoleCategory(
                category=category, taxonomy_version=str(row.role_taxonomy_version)
            ),
            requested_roles=request.requested_roles,
        ),
        # `from_profile` and not `no_profile_record`: the row was read. Whether
        # it holds any usable text is the *observed absence* §9 states a policy
        # for, and that distinction is the whole of ADR-0016 Proposal 1 — which
        # is why this constructor is the only honest one at a call site that
        # just fetched the row.
        topic_evidence=SpeakerTopicEvidence.from_profile(
            topic_text=row.topic_text, prior_talk=row.prior_talk
        ),
        location=SpeakerLocation(city=row.location_city, postal_code=row.location_postal_code),
        # A table lookup, or nothing. `resolve_distance_from_campus` returns
        # `None` for a blank, malformed, or non-Californian ZIP, and that `None`
        # is passed through unchanged: an unresolved place is an unknown
        # distance, never a guess and never the Far band. See the module
        # docstring, and `zip_proximity` for what the resolver refuses to do.
        distance_miles=None if distance is None else distance.miles,
        # Set exactly when a distance is. `ProximityInputs` refuses a
        # provenance with no distance, which is the right refusal: a receipt for
        # a measurement nobody made is how an unknown starts to look like a
        # value.
        distance_provenance=None if distance is None else distance.provenance,
    )
