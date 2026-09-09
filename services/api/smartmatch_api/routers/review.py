"""The review decision resource: closing the loop `imports.py` opened.

Architecture v1.1 §1.5: a validated import produces review items, not verified
records — `routers/imports.py` and `smartmatch_worker.handlers` are the write
half of that sentence, and until this router existed nothing in the API was the
*read* half of it. `review_item.status` (migration `0008`) has carried
`pending`/`accepted`/`rejected` since the table was created, and every row an
import writes starts `pending` (the column's own `server_default`); no route
ever moved one to `accepted` or `rejected`. The consequence was a metric with
no ceiling: `pending_review_items` (`smartmatch_domain.metrics`) could only
ever climb, because nothing fed it a decrement. This router is that decrement.

## The unit is derived, never named

`POST /v1/review-items/{review_item_id}/decision` carries no unit in its path,
and that omission is deliberate rather than an oversight this route will grow
into later. A caller names the review item; the unit that decision is
authorized against is read off `import_batch.owning_unit_id` for that item's
batch, exactly as `job_authz.py` derives a job's owning unit off the job row
rather than accepting one from the request. The alternative —
`POST /v1/units/{unit_id}/review-items/{review_item_id}/decision`, matching
`imports.py`'s own `/v1/units/{unit_id}/imports` shape — would let a caller
*assert* which unit their decision is scoped against, and an authorizer that
trusted the assertion over the row's own ancestry would be the exact
caller-supplied-identity pattern archived as MM-A01: a coordinator in one
department naming a sibling department's `unit_id` on a review item they do
hold real authority over, hoping the mismatch is never checked against the
row. `_load_review_item_context_or_404` below reads the unit the row actually
belongs to; there is no second value in the request for a bug to trust
instead.

## Why this is not a command resource

`imports.py`'s module docstring explains why `/imports` accepts a command
shape — the work is queued, dispatched, and performed by a worker, because
`smartmatch_worker.handlers` is where every provider call and every durable
write of consequence happens (v1.1 §1.6). A review decision has no such
external effect to queue: it is one conditional `UPDATE` against a row already
in this database, gated by nothing outside the request itself. Routing it
through `submit_command` would buy idempotent replay this route does not need
— `ReviewRepository.decide`'s own `WHERE status = 'pending'` already makes a
retried decision refuse cleanly as a 409 rather than double-apply — at the
cost of a `202` response for work that, unlike an import, really did finish
before the response was written. So this is an ordinary synchronous mutation,
`200` on success, the same shape `routers/redrive.py::abandon_job` takes for
the same reason: nothing is left to follow.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal, cast

import sqlalchemy as sa
from fastapi import APIRouter, Path, status
from pydantic import BaseModel, Field
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_persistence import schema
from smartmatch_persistence.rate_limit import RateLimit
from smartmatch_persistence.review import ReviewRepository
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal, DbSession, charge_quota
from smartmatch_api.errors import ApiError
from smartmatch_api.pipeline_provisioning import provision_on_accept
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/review-items", tags=["review"])

logger = logging.getLogger(__name__)

_review_items = ReviewRepository()

#: v1.1 §3.4's pilot defaults are hypotheses to tune with recorded evidence. A
#: decision is one conditional `UPDATE` against a single row already in this
#: database — no durable job, no queued provider call, nothing an import's
#: `MAX_INLINE_ROWS` bounds — so it is deliberately looser than
#: `imports.py::IMPORT_RATE_LIMIT` (10/minute). It is still a write, still
#: charged before authorization (ADR-0015), and still bounded: 60/minute is one
#: decision per second sustained, which is far above the pace a human
#: triaging a review queue actually clicks at, while still refusing a script
#: that hammers the route with ids it invents.
REVIEW_DECISION_RATE_LIMIT = RateLimit(
    operation="review.decide",
    max_requests=60,
    window=timedelta(minutes=1),
)

#: Roles permitted to decide a review item. Matches `imports.py::_IMPORT_ROLES`
#: exactly, and that agreement is not incidental: accepting or rejecting a
#: submitted record is the other half of the same consequential act importing
#: it was, so the set of people trusted to do one is the set trusted to do the
#: other. A literal frozenset rather than an import of `_IMPORT_ROLES`, for the
#: same reason `tests/authz/test_route_roles.py`'s own ledger insists on
#: literals: the two roles agreeing today does not mean a widening of one
#: should silently widen the other.
_REVIEW_ROLES = frozenset({"admin", "coordinator"})

#: The only two values `ReviewRepository.decide` will ever write, and the only
#: two `ck_review_item_status` (migration `0008`) admits beyond `pending`.
#: Expressed as `Literal` rather than `str` with a manual membership check: an
#: out-of-vocabulary value is refused by Pydantic before this handler's body
#: even runs, in the same standard `invalid_request` 422 envelope every other
#: malformed request in this API answers with
#: (`smartmatch_api.errors.request_validation_handler`) — one enforcement site
#: rather than a second one this router would otherwise have to write and keep
#: in step with the CHECK constraint by hand.
ReviewDecisionValue = Literal["accepted", "rejected"]


class ReviewDecisionRequest(BaseModel):
    """A coordinator's decision on one pending review item."""

    decision: ReviewDecisionValue = Field(
        description="Whether the row is accepted into the dataset or rejected."
    )


class ReviewDecisionResponse(BaseModel):
    """What changed, and nothing this response does not own.

    Deliberately **not** carrying `pending_review_items` for the item's unit.
    A caller who wants that count has a route that owns it —
    `GET /v1/units/{unit_id}/metrics` — and ADR-0011 rule 4 is that a number
    with an owning query is read from that query, not recomputed by a second
    handler that would have to stay in step with it by hand. Folding the count
    in here would create exactly that second copy, and the first time the two
    disagreed — a decision recorded here, a metrics query cached or read from
    a replica a beat behind it — there would be no way to tell which one was
    wrong.
    """

    id: uuid.UUID
    status: ReviewDecisionValue
    decided_at: datetime


@dataclass(frozen=True, slots=True)
class _ReviewItemContext:
    """What this router needs about a review item: the unit it authorizes
    against, and the row a synthetic acceptance provisions from."""

    unit_id: uuid.UUID
    unit_path: str
    dataset: str
    row_data: Mapping[str, Any]


def _load_review_item_context_or_404(
    session: Session, *, tenant_id: uuid.UUID, review_item_id: uuid.UUID
) -> _ReviewItemContext:
    """The unit that owns this review item's import batch, or 404 — plus the
    batch's ``dataset`` and the item's own ``row_data``.

    Joins `review_item -> import_batch -> org_unit`, every hop composite on
    `tenant_id` and scoped to the caller's own tenant in the query itself —
    the same discipline `JobRepository.get` states at length for its own
    `job -> org_unit` join: a join on the surrogate id alone would return the
    same rows today only because the composite foreign keys already forbid a
    cross-tenant pairing, and a read that feeds an authorization decision
    should not depend on a constraint elsewhere staying intact to remain safe.

    Both joins are **inner**. `review_item.import_batch_id` and
    `import_batch.owning_unit_id` are both `NOT NULL`, and both are guarded by
    a composite foreign key one migration apart (`0008`), so a `review_item`
    with no matching `import_batch` or a batch with no matching `org_unit`
    cannot exist while those constraints hold. A row that fails to join is
    therefore a `review_item` that does not exist *in this tenant* — the same
    conclusion `units.py::load_unit_or_404` reaches for a unit id naming
    another tenant's row — and both cases collapse into one 404 rather than
    ever becoming a 403 that would confirm to an unauthorized caller that the
    id names something real.

    Returns the unit's id and its path, and — added for Card 6 — the batch's
    `dataset` and this item's own `row_data`, read in this *same* query rather
    than a second one issued after authorization. A second `SELECT` could
    observe a different row than the one just authorized against — another
    request updating or, in a future schema, deleting the row between the two
    reads — and the whole point of authorizing against a specific row is that
    the thing provisioned afterward is *that* row, not whatever a later read
    happens to find. One query makes the two facts — "this caller may decide
    this item" and "this is what provisioning will act on" — atomic with each
    other by construction, not merely by convention.

    `decide_review_item` builds its `Resource` from `unit_id` and `unit_path`
    — `resource_id` from the id, `owning_unit_path` from the path — the
    identical two fields `imports.py::create_import` builds its own `Resource`
    from off `unit: OrgUnitRow`, because this route authorizes against *the
    unit*, not against the review item: `_REVIEW_ROLES` is the same role set
    `_IMPORT_ROLES` is, over the same kind of resource, for the reason the
    module docstring gives — deciding a submitted record is the other half of
    the same consequential act submitting it was. `dataset` and `row_data` are
    used only after authorization succeeds, to provision a synthetic
    acceptance — see `decide_review_item`.
    """
    row = session.execute(
        sa.select(
            schema.import_batch.c.owning_unit_id,
            sa.cast(schema.org_unit.c.path, sa.Text).label("owning_unit_path"),
            schema.import_batch.c.dataset,
            schema.review_item.c.row_data,
        )
        .select_from(schema.review_item)
        .join(
            schema.import_batch,
            sa.and_(
                schema.import_batch.c.tenant_id == schema.review_item.c.tenant_id,
                schema.import_batch.c.id == schema.review_item.c.import_batch_id,
            ),
        )
        .join(
            schema.org_unit,
            sa.and_(
                schema.org_unit.c.tenant_id == schema.import_batch.c.tenant_id,
                schema.org_unit.c.id == schema.import_batch.c.owning_unit_id,
            ),
        )
        .where(
            schema.review_item.c.tenant_id == tenant_id,
            schema.review_item.c.id == review_item_id,
        )
    ).one_or_none()

    if row is None:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="review_item_not_found",
            message="No such review item.",
        )

    return _ReviewItemContext(
        unit_id=row.owning_unit_id,
        unit_path=cast(str, row.owning_unit_path),
        dataset=cast(str, row.dataset),
        row_data=cast("Mapping[str, Any]", row.row_data),
    )


@router.post(
    "/{review_item_id}/decision",
    status_code=status.HTTP_200_OK,
    response_model=ReviewDecisionResponse,
    summary="Accept or reject a pending review item",
)
def decide_review_item(
    principal: CurrentPrincipal,
    session: DbSession,
    body: ReviewDecisionRequest,
    review_item_id: Annotated[uuid.UUID, Path()],
) -> ReviewDecisionResponse:
    """Accept or reject one pending review item.

    `200`, not `202`: unlike `POST /v1/units/{unit_id}/imports` this starts
    nothing durable. `ReviewRepository.decide`'s `UPDATE` either lands inside
    this handler's own request or it does not, and there is no worker on the
    other end of it to follow — see the module docstring for why this route
    is not shaped as a command.

    Authorization runs against the unit `_load_owning_unit_or_404` reads off
    the review item's own batch — after loading it, which is why it happens
    here rather than in a dependency (a dependency cannot authorize a resource
    it has not fetched; `imports.py::create_import` makes the identical point
    about its own unit load).

    Quota is charged before any of that (ADR-0015), so a caller producing 404s
    against review-item ids they invented, or 403s against an item they hold
    no role over, spends exactly what a caller submitting a real decision
    spends — the same ordering `create_import` and `redrive_job` both apply,
    for the same reason: those are the refusals cheapest to produce in bulk.
    \f
    Everything above this form-feed is reproduced **byte for byte** as it
    stood before Card 6 — including its one mention of this loader by its
    pre-Card-6 name, `_load_owning_unit_or_404`, which Card 6 actually renames
    to `_load_review_item_context_or_404` (part (a) of this card; see that
    function's own current docstring for what it does now). That is
    deliberate, not an oversight: FastAPI truncates the OpenAPI-exported
    `description` of a route at the first form-feed in its docstring
    (`fastapi.routing`'s `route.description.split("\\f")[0]`), so this whole
    docstring above this marker *is* that route's exported `description`, and
    `contracts/openapi/smartmatch.json` pins it byte for byte. Card 6's fence
    does not include `contracts/**`, so regenerating that contract is a
    follow-up outside this card, not something committed here — and changing
    even one word above this marker, the stale name included, would make
    `make openapi-check` refuse this change as contract drift before that
    follow-up ever lands. Everything Card 6 actually needs to say — the
    accept/reject provisioning behaviour below, and this note itself — lives
    below the marker instead, where it is still part of this function's real
    docstring (`help()`, an IDE, anyone reading this source sees all of it),
    just not part of the public contract.

    A rejection provisions nothing: only `body.decision == "accepted"` reaches
    `provision_on_accept` below. An acceptance may, in addition to recording
    the decision itself, open one or more synthetic `pipeline_record`
    journeys — see `smartmatch_api.pipeline_provisioning`'s module docstring
    for the full policy — whose `matched_at` is this coordinator's acceptance
    (`now` below) and nothing more: it is not the output of a matching
    computation, no matching engine ran, and no score, confidence, or rank is
    written or computed anywhere on this path. Every such row's
    `matched_provenance` is exactly
    `"synthetic / coordinator-accepted"`
    (`smartmatch_domain.synthetic_pilot.SYNTHETIC_MATCH_PROVENANCE`),
    stored in the database, not only logged. Provisioning runs inside this
    handler's own transaction and is committed by the same `session.commit()`
    that commits the decision — this function never commits on its own, so a
    provisioning failure rolls the decision back with it rather than leaving
    a decision recorded with its journeys missing.
    """
    charge_quota(session, principal, REVIEW_DECISION_RATE_LIMIT)

    context = _load_review_item_context_or_404(
        session, tenant_id=principal.tenant_id, review_item_id=review_item_id
    )

    assert_allowed(
        principal.principal,
        Resource(
            resource_type="org_unit",
            resource_id=str(context.unit_id),
            tenant_id=str(principal.tenant_id),
            owning_unit_path=OrgPath.parse(context.unit_path),
        ),
        at=utc_now(),
        required_roles=_REVIEW_ROLES,
    )

    now = utc_now()
    outcome = _review_items.decide(
        session,
        tenant_id=principal.tenant_id,
        review_item_id=review_item_id,
        decision=body.decision,
        decided_by=principal.user_id,
        decided_at=now,
    )

    if not outcome.exists:
        # Reachable only if the row were deleted between the load above and
        # this call — `review_item` has no delete route, so nothing in this
        # codebase does that today. This is the fail-closed answer for the day
        # something does, not an assumption this handler relies on holding.
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="review_item_not_found",
            message="No such review item.",
        )

    if not outcome.transitioned:
        # `outcome.status` is not `"pending"` here — see
        # `ReviewRepository.decide`'s docstring for why a zero-row `UPDATE`
        # with the row present means exactly this and not a missing row.
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="review_item_already_decided",
            message=(
                f"This review item was already decided ({outcome.status}); "
                "a decision may not be recorded twice."
            ),
        )

    if body.decision == "accepted":
        # Runs inside this handler's own transaction, before the one commit
        # below — a raised `ConflictingOwningUnitError` (or any other error)
        # therefore rolls the decision back with it (plan §2 Decision 7, plan
        # §1.6): `get_session`'s unconditional `finally: session.rollback()`
        # discards everything this request touched, including the `UPDATE`
        # `_review_items.decide` just issued but has not yet committed.
        provision_outcome = provision_on_accept(
            session,
            tenant_id=principal.tenant_id,
            owning_unit_id=context.unit_id,
            review_item_id=review_item_id,
            dataset=context.dataset,
            row_data=context.row_data,
            accepted_at=now,
        )
        # Plan §1.10 — silent zero is a defect, and must be visible in *this*
        # route's own logging, not merely inside the provisioning service.
        # `opportunity_event_id` set with `journeys_opened` empty is exactly,
        # and only, the case Decision 6 says to worry about: an in-list
        # `events` accept that found no professional already linked to its
        # unit. `provision_on_accept` already emits its own WARNING for this;
        # this one is the route's independent record of the same fact, so
        # "opened zero journeys" is visible from the handler that owns the
        # HTTP response, not only from a module several calls away from it.
        opened_nothing = (
            provision_outcome.opportunity_event_id is not None
            and not provision_outcome.journeys_opened
        )
        if opened_nothing:
            logger.warning(
                "review_item %s accept opened zero pipeline journeys "
                "(unit=%s, opportunity_event_id=%s)",
                review_item_id,
                context.unit_id,
                provision_outcome.opportunity_event_id,
            )

    session.commit()

    assert outcome.status is not None  # narrowed by outcome.transitioned above
    assert outcome.decided_at is not None  # narrowed by outcome.transitioned above
    return ReviewDecisionResponse(
        id=review_item_id,
        # `outcome.status` is `str` — read back off the database, or handed
        # straight through from `body.decision` on the fresh-transition path —
        # while the response field is the narrower `ReviewDecisionValue`.
        # `ck_review_item_status` and `ck_review_item_decision_evidence`
        # together guarantee a *transitioned* row's status is one of the two
        # literal values (a row this branch never reaches otherwise), so this
        # cast states a guarantee the schema already enforces rather than
        # discovering one.
        status=cast(ReviewDecisionValue, outcome.status),
        decided_at=outcome.decided_at,
    )
