"""Unit-scoped, read-only coordinator surfaces over the ``event`` model.

Migration ``0017`` created ``event``, ``event_tag`` and
``discovery_review_item``; ``smartmatch_persistence.events`` is the only module
that writes them, and ``smartmatch_worker.event_ingest`` is the only caller of
that writer. This module is the other half: the two reads a coordinator needs
to see what that write path produced, and nothing else.

## Two routes, both ``GET``, both unit-scoped

* ``GET /v1/units/{unit_id}/events`` — the unit's event catalog, restricted to
  events that are *actually presentable*: a resolved date (ADR-0010 rule 2)
  and no quarantined tags (ADR-0012). See :func:`list_events`.
* ``GET /v1/units/{unit_id}/tag-quarantine`` — the tag values that did **not**
  map into the closed vocabulary and are waiting for a human. See
  :func:`list_quarantined_tags`.

Nothing here writes. G3's standing constraints (§9) put every network action
worker-side and leave API handlers "commands and review decisions only"; these
two routes make no network call, run no extraction, and hold no session open
past the request. There is no fetch, no crawl trigger, and no route that
accepts a URL — ``ALLOW_LIVE_PROVIDERS`` stays false and nothing in this module
would consult it if it were true.

## Why the quarantine route does not accept a decision

G3 §6.3 makes vocabulary growth a *reviewed code diff* signed by a named owner
("Terms must arrive already normalized; an executor editing an approved term
would be inventing one, which P6 forbids"), and
``smartmatch_domain.event_vocabulary`` implements that by making
:data:`~smartmatch_domain.event_vocabulary.G3_VOCABULARY` a frozen module
constant. So an ``accept`` button on this queue could not do the thing its
label promised: accepting a term is a new ``TagVocabulary`` with a new
version, not a row update. Shipping one anyway would be a control that looks
like it works — the exact shape this repository treats as worse than an
absence. The queue is therefore readable and not decidable here, and the
response says which vocabulary version each item was judged against so a
reviewer can tell a stale judgement from a current one.

## What "unknown is not zero" costs this response (ADR-0011)

:class:`EventListResponse` does not report only the events it lists. An event
withheld for an unresolved date and an event withheld for a quarantined tag
are two different facts about a unit's catalog, and a list that silently
dropped both would make "this unit has three events" indistinguishable from
"this unit has three presentable events and four the pipeline could not
finish".

``routers/metrics.py`` states the rule those counts have to satisfy: no
separate ``COUNT`` whose filters can drift from the row query. It satisfies it
by returning the rows once and taking ``len(rows)``, which is only available to
a query that reads everything it counts — and a catalog route cannot do that,
because "read every event this unit has ever had, then return two hundred of
them" is unbounded work on the request path.

So the same guarantee is obtained a different way: :data:`_UNRESOLVED_EVENT`
and :data:`_QUARANTINED_EVENT` are built once, and the counting query and the
listing query are both built *from those objects*. They are not two clauses
that happen to agree; they are one clause used twice, so there is nothing for a
later edit to change in one place and not the other. The listing then reads at
most :data:`MAX_ROWS` + 1 rows, and the counts come back as two integers.

## The 200-row ceiling

Both routes cap what they return at :data:`MAX_ROWS`, which is G3 §2.2a's
200-record cap reused rather than a second number invented here, and both say
whether the cap actually truncated anything. A page that silently returned the
first 200 of 900 rows would be a fabricated total; ``truncated`` is how the
caller learns the difference. Paging is deliberately not shipped: a cursor
nobody has asked for is a contract to maintain, and the synthetic pilot's
fixtures do not approach the ceiling.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Final

import sqlalchemy as sa
from fastapi import APIRouter, Path
from pydantic import BaseModel, Field
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_domain.event_vocabulary import VOCABULARY_VERSION
from smartmatch_persistence import schema
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal, DbSession
from smartmatch_api.units import load_unit_or_404
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/units", tags=["events"])

#: Roles permitted to read a unit's event catalog and its tag-quarantine queue.
#:
#: ``admin`` and ``coordinator``, matching ``imports.py::_IMPORT_ROLES``,
#: ``review.py::_REVIEW_ROLES`` and ``metrics.py::_DRILL_DOWN_ROLES``. No
#: committed artifact names a third role for either surface, and under
#: deny-by-default the absence of a permit is a denial rather than an
#: invitation to guess: G3 §5 makes event approval a coordinator-and-above
#: act, and the quarantine queue carries raw source text a reviewer is trusted
#: with, not a value the vocabulary has cleared for display.
#:
#: A literal ``frozenset`` rather than an import of one of the sets above, for
#: the reason ``tests/authz/test_route_roles.py`` gives about its own ledger:
#: four role sets agreeing today is not a reason a widening of one should
#: silently widen the others.
_EVENT_ROLES: Final[frozenset[str]] = frozenset({"admin", "coordinator"})

#: The most rows either route returns in one response. G3 §2.2a's 200-record
#: cap, reused rather than re-decided — "no card invented a vocabulary term,
#: allowlist entry, or limit value" (the S3-S5 plan's "Done means").
MAX_ROWS: Final[int] = 200

#: ``event.time_precision`` for an event whose date could not be resolved.
#: ADR-0010 rule 2 keeps such an event out of any matchable or publishable
#: state, and :func:`list_events` keeps it out of the catalog for the same
#: reason: it is a real row with an honest absence in it, not a listing.
_UNRESOLVED: Final[str] = "unresolved"

#: The two reasons an event is withheld from the catalog, as SQL expressions
#: built once and used by both the counting query and the listing query — see
#: the module docstring on ADR-0011. Module-level rather than rebuilt per call
#: so there is exactly one definition of each: a predicate written out twice is
#: a predicate that can be corrected once.
#:
#: ADR-0010 rule 2 — no resolvable date, therefore no identity key and no
#: publishable state.
_UNRESOLVED_EVENT = schema.event.c.time_precision == _UNRESOLVED
#: ADR-0012 — at least one tag value is still waiting for a human.
#: ``> 0`` rather than truthiness: ``quarantined_tag_count`` is ``NOT NULL``
#: with ``ck_event_quarantined_tag_count_non_negative``, so this is the whole
#: of "carries quarantined tags" and needs no NULL arm.
_QUARANTINED_EVENT = schema.event.c.quarantined_tag_count > 0


class EventTimeView(BaseModel):
    """An event's time at whichever precision is actually known (ADR-0010).

    Three fields plus a discriminator, never a single nullable timestamp. A
    ``date_only`` event has no instant, and reporting one — midnight in some
    zone — is the fabrication ADR-0010 exists to stop; a client reading
    ``precision`` knows which of ``starts_at`` and ``on_date`` is real without
    inferring it from a null.
    """

    precision: str = Field(description="exact, date_only, or unresolved.")
    starts_at: datetime | None = Field(
        default=None, description="The instant, present only at exact precision."
    )
    ends_at: datetime | None = Field(
        default=None,
        description=(
            "The instant the event finishes, present only when the source actually "
            "stated one. Null is not a duration of zero and not a default of an hour: "
            "it is the absence that makes an .ics download refusable rather than "
            "guessable, and it is what a client checks before offering the link."
        ),
    )
    on_date: date | None = Field(
        default=None, description="The calendar date, present only at date_only precision."
    )
    time_zone: str | None = Field(
        default=None,
        description="The IANA zone the event happens in — never the viewer's or the server's.",
    )


class EventProvenanceView(BaseModel):
    """Where the event came from, as its own object (ADR-0012).

    A separate field on a separate model, never folded into ``title`` or
    ``description``. ``smartmatch_domain.events`` has no function that combines
    a title with an :class:`~smartmatch_domain.events.EventProvenance`, and
    neither does this module, so "provenance is never part of the title" holds
    by there being no code path that could join them rather than by a
    convention a serializer has to remember.

    Every field but ``origin`` is null on a ``coordinator_entry`` event, which
    ``ck_event_provenance_evidence`` requires: a human typing an event fetched
    nothing, and inventing a source URL to fill the column would be the
    fabricated-field defect arriving through a response model.
    """

    origin: str = Field(description="coordinator_entry or extraction.")
    source_url: str | None = None
    fetched_at: datetime | None = None
    extractor_version: str | None = None


class EventSummary(BaseModel):
    """One presentable event.

    ``tags`` carries mapped vocabulary terms only. A quarantined value has no
    ``term`` to carry (``event_tag.term`` is NULL on those rows, and
    :class:`~smartmatch_domain.events.QuarantinedTag` has no ``term``
    attribute at all), so ADR-0012's "never rendered and never matched on" is
    upheld by the shape of the data rather than by this model remembering a
    filter — and, belt to that, by the ``resolution = 'mapped'`` predicate in
    :func:`_mapped_terms`.
    """

    id: uuid.UUID
    title: str
    description: str | None = None
    time: EventTimeView
    tags: list[str] = Field(description="Mapped vocabulary terms. Never a quarantined value.")
    publication_status: str
    review_status: str
    provenance: EventProvenanceView


class EventListResponse(BaseModel):
    """A unit's presentable events, and an honest account of what is missing.

    ``withheld_unresolved_date`` and ``withheld_quarantined_tags`` are not
    decoration. They are what keeps the empty list meaningful: zero events with
    zero withheld means the unit has no events, and zero events with seven
    withheld means the unit has seven the pipeline could not finish. ADR-0011's
    rule is that an unknown is never rendered as a zero; the corollary this
    response applies is that an *omission* is never rendered as an absence.
    """

    unit_id: uuid.UUID
    events: list[EventSummary]
    withheld_unresolved_date: int = Field(
        description="Events excluded because no date could be resolved (ADR-0010 rule 2)."
    )
    withheld_quarantined_tags: int = Field(
        description="Events excluded because a tag value awaits human review (ADR-0012)."
    )
    truncated: bool = Field(
        description="True when more presentable events exist than the response cap returns."
    )


class QuarantinedTagItem(BaseModel):
    """One unmapped tag value waiting for a human (ADR-0012, G3 §5).

    ``raw_value`` is the source text exactly as received, unnormalized: a
    reviewer deciding whether a term belongs in the vocabulary needs to see
    what was actually on the page, casing and all. It is reported here and
    nowhere else — it is not a tag, and no matching or rendering path can
    reach it.
    """

    id: uuid.UUID
    event_id: uuid.UUID
    event_title: str
    raw_value: str
    vocabulary_version: str = Field(
        description="The vocabulary version this value was judged against and did not match."
    )
    judged_against_current_vocabulary: bool = Field(
        description=(
            "False when the item was judged against an older vocabulary than the one "
            "released now, so a reviewer can tell a stale judgement from a current one."
        )
    )
    created_at: datetime


class QuarantinedTagListResponse(BaseModel):
    """The unit's pending tag-quarantine queue.

    Pending only. A decided item is a decision already made, and mixing it back
    into the queue would make "seven values need review" and "seven values were
    ever quarantined" the same number. This route records no decision — see the
    module docstring for why an ``accept`` here could not do what it said.
    """

    unit_id: uuid.UUID
    current_vocabulary_version: str = Field(
        description="The released vocabulary version terms are resolved against today."
    )
    items: list[QuarantinedTagItem]
    truncated: bool = Field(
        description="True when more pending items exist than the response cap returns."
    )


def _authorize_event_read(
    session: Session,
    principal: CurrentPrincipal,
    unit_id: uuid.UUID,
) -> None:
    """Load the unit and authorize a coordinator read against it.

    Shared by both routes because both authorize the identical question — may
    this caller see this unit's discovery output — against the identical
    resource. One function rather than two near-identical ones, in the same
    spirit as ``smartmatch_api.job_authz`` sharing one authorizer across four
    job operations: a widening applies to both surfaces or to neither, and
    cannot be applied to one by accident.

    The unit is loaded first and authorization runs against *that row's* path,
    never against a path taken from the request. ``load_unit_or_404`` scopes
    the lookup by the caller's own tenant, so a unit in another tenant is a
    404 rather than a 403 that would confirm the id names something real.

    No ``require_membership`` and no ``tenant_wide_roles``. ``_EVENT_ROLES`` is
    non-empty, so ``evaluate`` already refuses a bare ``resource_grant`` on the
    required-roles check (S-007), and no committed artifact makes either of
    these reads tenant-wide the way the metrics decision's §4 makes aggregate
    reads tenant-wide — under deny-by-default, ordinary subtree containment is
    the only reading available.
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
        required_roles=_EVENT_ROLES,
    )


def _mapped_terms(
    session: Session, *, tenant_id: uuid.UUID, event_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[str]]:
    """The mapped vocabulary terms of each listed event, in one query.

    Issued only for the ids actually being returned, so a truncated listing
    does not read tags it will not render. ``resolution = 'mapped'`` is the
    filter ADR-0012 requires, and it is redundant with the schema rather than
    load-bearing on its own: ``ck_event_tag_resolution_shape`` keeps ``term``
    NULL on a quarantined row, so a query that forgot this predicate would
    still surface no quarantined value as a term.
    """
    if not event_ids:
        return {}
    rows = session.execute(
        sa.select(schema.event_tag.c.event_id, schema.event_tag.c.term)
        .where(
            schema.event_tag.c.tenant_id == tenant_id,
            schema.event_tag.c.event_id.in_(event_ids),
            schema.event_tag.c.resolution == "mapped",
        )
        .order_by(schema.event_tag.c.event_id, schema.event_tag.c.term)
    ).all()
    terms: dict[uuid.UUID, list[str]] = {}
    for row in rows:
        if row.term is not None:
            terms.setdefault(row.event_id, []).append(str(row.term))
    return terms


@router.get(
    "/{unit_id}/events",
    response_model=EventListResponse,
    summary="List a unit's presentable events",
)
def list_events(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
) -> EventListResponse:
    """Return the unit's events that are actually presentable, and count the rest.

    Two exclusions, both pinned by an Accepted ADR rather than chosen here:

    * **No resolved date.** ADR-0010 rule 2 — "an event at ``unresolved``
      cannot reach a matchable or publishable state". It also has no identity
      key (ADR-0012), which is the same fact about it stated twice. Listing one
      would put a dateless row in a catalog whose whole purpose is telling a
      coordinator when something happens, which is the legacy defect
      ``date: "See link for details"`` recorded as finding H21.
    * **A quarantined tag.** ADR-0012 — a value the closed vocabulary did not
      recognize is "stored with the event, visible to a human review queue, and
      never rendered and never matched on". An event carrying one is not
      finished being extracted; ``ck_event_publishable`` refuses to publish it
      for the same reason, and this route refuses to list it.

    Neither exclusion is silent. Both are counted from the same rows this
    listing is partitioned out of and reported on the response — see
    :class:`EventListResponse`.

    Only ``admin`` and ``coordinator`` may read this
    (:func:`_authorize_event_read`), and authorization runs before any row is
    read.
    """
    _authorize_event_read(session, principal, unit_id)

    owned_by_this_unit = (
        schema.event.c.tenant_id == principal.tenant_id,
        schema.event.c.host_org_unit_id == unit_id,
    )

    # The two withheld counts, from the same expressions the listing below
    # excludes on. `FILTER (WHERE ...)` rather than two queries: one scan, and
    # the predicates are the module-level objects, not restatements of them.
    withheld = session.execute(
        sa.select(
            sa.func.count().filter(_UNRESOLVED_EVENT).label("unresolved"),
            # An unresolved event could also carry a quarantined tag, and would
            # then be counted twice — one withholding reported as two. The
            # `~_UNRESOLVED_EVENT` arm makes the two counts a partition of the
            # withheld rows rather than two overlapping tallies, so they can be
            # read side by side and, with the listing, add up to the total.
            sa.func.count()
            .filter(sa.and_(~_UNRESOLVED_EVENT, _QUARANTINED_EVENT))
            .label("quarantined"),
        ).where(*owned_by_this_unit)
    ).one()

    listed = session.execute(
        sa.select(
            schema.event.c.id,
            schema.event.c.title,
            schema.event.c.description,
            schema.event.c.starts_at,
            schema.event.c.ends_at,
            schema.event.c.on_date,
            schema.event.c.time_zone,
            schema.event.c.time_precision,
            schema.event.c.publication_status,
            schema.event.c.review_status,
            schema.event.c.origin,
            schema.event.c.source_url,
            schema.event.c.fetched_at,
            schema.event.c.extractor_version,
        )
        .where(*owned_by_this_unit, ~_UNRESOLVED_EVENT, ~_QUARANTINED_EVENT)
        # Deterministic across calls: `id` breaks ties so two events on one day
        # never swap places between two identical requests — which also makes
        # the truncation below cut at a stable point rather than an arbitrary
        # one.
        .order_by(schema.event.c.resolved_date, schema.event.c.id)
        # One more than the cap, so "there are exactly MAX_ROWS" and "there are
        # more than MAX_ROWS" are distinguishable without a third query.
        .limit(MAX_ROWS + 1)
    ).all()

    truncated = len(listed) > MAX_ROWS
    listed = listed[:MAX_ROWS]
    terms = _mapped_terms(
        session, tenant_id=principal.tenant_id, event_ids=[row.id for row in listed]
    )

    return EventListResponse(
        unit_id=unit_id,
        events=[
            EventSummary(
                id=row.id,
                title=row.title,
                description=row.description,
                time=EventTimeView(
                    precision=row.time_precision,
                    starts_at=row.starts_at,
                    ends_at=row.ends_at,
                    on_date=row.on_date,
                    time_zone=row.time_zone,
                ),
                tags=terms.get(row.id, []),
                publication_status=row.publication_status,
                review_status=row.review_status,
                provenance=EventProvenanceView(
                    origin=row.origin,
                    source_url=row.source_url,
                    fetched_at=row.fetched_at,
                    extractor_version=row.extractor_version,
                ),
            )
            for row in listed
        ],
        withheld_unresolved_date=withheld.unresolved,
        withheld_quarantined_tags=withheld.quarantined,
        truncated=truncated,
    )


@router.get(
    "/{unit_id}/tag-quarantine",
    response_model=QuarantinedTagListResponse,
    summary="List a unit's tag values awaiting human review",
)
def list_quarantined_tags(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
) -> QuarantinedTagListResponse:
    """Return the unit's pending unmapped tag values, with the event each came from.

    This is the human end of ADR-0012's quarantine rule and G3 §5's escalation
    destination: a value the closed vocabulary did not recognize is kept, tied
    to its event, and shown to a person — never dropped, and never quietly
    promoted into a matchable term. G3 §6.1 is explicit that a full queue is
    the instrument working rather than a defect: §6.2 cut eight candidate terms
    on purpose, and "that queue is evidence of which terms were actually
    needed".

    ``kind = 'unmapped_tag'`` narrows the queue to tag quarantine specifically.
    ``discovery_review_item.kind`` also admits ``unresolved_time`` and
    ``first_seen_event`` (``ck_discovery_review_item_kind``), which are
    different review questions with different answers; folding them into one
    list would make a count of "tags needing review" wrong in a way nobody
    could see from the response.

    The route records no decision — see the module docstring. Only ``admin``
    and ``coordinator`` may read it, and authorization runs before any row is
    read.
    """
    _authorize_event_read(session, principal, unit_id)

    rows = session.execute(
        sa.select(
            schema.discovery_review_item.c.id,
            schema.discovery_review_item.c.event_id,
            schema.discovery_review_item.c.raw_value,
            schema.discovery_review_item.c.vocabulary_version,
            schema.discovery_review_item.c.created_at,
            schema.event.c.title.label("event_title"),
        )
        .select_from(schema.discovery_review_item)
        # Composite on `tenant_id` as well as the id, and scoped to the
        # caller's tenant in the query itself: the same discipline
        # `routers/review.py` states for its own joins. A join on the surrogate
        # id alone would return the same rows today only because the composite
        # foreign key already forbids a cross-tenant pairing, and a read a
        # coordinator acts on should not depend on a constraint elsewhere
        # staying intact to remain correct.
        .join(
            schema.event,
            sa.and_(
                schema.event.c.tenant_id == schema.discovery_review_item.c.tenant_id,
                schema.event.c.id == schema.discovery_review_item.c.event_id,
            ),
        )
        .where(
            schema.discovery_review_item.c.tenant_id == principal.tenant_id,
            schema.discovery_review_item.c.owning_unit_id == unit_id,
            schema.discovery_review_item.c.kind == "unmapped_tag",
            schema.discovery_review_item.c.status == "pending",
        )
        .order_by(
            schema.discovery_review_item.c.created_at,
            schema.discovery_review_item.c.id,
        )
        # Oldest first, capped, and one over the cap so ``truncated`` is
        # answered by the same read — the same shape :func:`list_events` uses.
        # A reviewer working a queue wants the values that have waited longest,
        # not whichever page the database found first.
        .limit(MAX_ROWS + 1)
    ).all()

    truncated = len(rows) > MAX_ROWS
    return QuarantinedTagListResponse(
        unit_id=unit_id,
        current_vocabulary_version=VOCABULARY_VERSION,
        items=[
            QuarantinedTagItem(
                id=row.id,
                event_id=row.event_id,
                event_title=row.event_title,
                # `ck_discovery_review_item_tag_evidence` makes both columns
                # NOT NULL for `kind = 'unmapped_tag'`, which the WHERE clause
                # above has already restricted to. `str()` states that for the
                # type checker rather than discovering it.
                raw_value=str(row.raw_value),
                vocabulary_version=str(row.vocabulary_version),
                judged_against_current_vocabulary=row.vocabulary_version == VOCABULARY_VERSION,
                created_at=row.created_at,
            )
            for row in rows[:MAX_ROWS]
        ],
        truncated=truncated,
    )
