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

## The routes this module owns

* `POST /v1/review-items/{review_item_id}/decision` — decide one item, on
  `router`. Named by item, with its unit derived; see above.
* `GET /v1/units/{unit_id}/review-items` — list a unit's items, on
  `unit_router`. Named by unit, because a queue has no item to derive one
  from; see below.

## Why the list is named by unit, when the decision is not

The decision route's whole argument above is that a caller must not be able to
*assert* which unit their request is scoped against. The list route takes a
`unit_id` in its path and so appears to do exactly that. It does not, and the
difference is worth stating precisely rather than leaving as an apparent
contradiction.

A review item names a unit whether or not the request does, so on the decision
route a `unit_id` in the path would be a **second, redundant** value alongside
the row's own ancestry — and MM-A01 is what happens when an authorizer trusts
the redundant one over the row. A queue has no such row to derive from: "which
unit's queue" *is* the request, the way `/v1/units/{unit_id}/imports` and
`/v1/units/{unit_id}/metrics` are. There is no second value for a bug to
prefer, so there is no mismatch to go unchecked.

What makes that safe is not the path shape but the authorization:
`_authorize_review_item_list` loads *that* unit with `load_unit_or_404` and
authorizes against the loaded row's own path, so naming a unit is a request to
be refused, never a claim to be believed. A coordinator naming a sibling
department's `unit_id` is denied by the policy on containment, and a unit in
another tenant is a 404 rather than a 403 that would confirm the id names
something real.

## The list and the count must not be able to disagree

`GET /v1/units/{unit_id}/metrics` has published `pending_review_items` for this
unit since before either review route existed. That count is the *reason* this
list exists: the coordinator dashboard showed a number with no route behind it,
so the screen contradicted itself — a badge saying seven items pending, and
nowhere to see the seven.

Closing that by writing a *second* query would have reproduced the defect in a
subtler form, because `review_item` carries no owning unit column: the unit is
derived by joining `import_batch.owning_unit_id`, and two derivations that
drifted apart would put a row in one unit's queue and another unit's badge.
So `ReviewRepository.list_for_unit` reuses the join shape
`routers/metrics.py::_pending_review_item_rows_v1` already makes — same joins,
same tenant scoping, same `ORDER BY created_at, id` — and
`tests/contract/test_review_item_list.py` asserts the equality directly, on one
fixture, through both routes. ADR-0011 rule 4 is the rule being followed: a
number with an owning query is read from that query. This route does not carry
a count of its own, for the reason `ReviewDecisionResponse`'s docstring already
gives about its own response.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated, Any, Final, Literal, cast

import sqlalchemy as sa
from fastapi import APIRouter, Path, Query, status
from pydantic import BaseModel, Field
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_persistence import schema
from smartmatch_persistence.rate_limit import RateLimit
from smartmatch_persistence.review import ReviewItemRow, ReviewRepository
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal, DbSession, charge_quota
from smartmatch_api.errors import ApiError
from smartmatch_api.pipeline_provisioning import provision_on_accept
from smartmatch_api.units import load_unit_or_404
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/review-items", tags=["review"])

#: The unit-scoped half of this module. A second ``APIRouter`` rather than a
#: second module, because both routes are the same resource seen from two
#: sides — one names an item and derives its unit, the other names a unit and
#: lists its items — and splitting them would put the two halves of one
#: authorization story in two files. The prefixes genuinely differ
#: (``/v1/review-items`` against ``/v1/units``) and a FastAPI prefix cannot be
#: escaped per-route, so one router cannot serve both. The same shape
#: ``outreach.py``, ``cba_invitations.py`` and ``student_speaker_feedback.py``
#: already use for their own second routers; ``main.py`` mounts this one
#: beside ``router``.
unit_router = APIRouter(prefix="/v1/units", tags=["review"])

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

#: Reading the queue, charged separately from deciding in it. A read starts
#: nothing and writes nothing, so it is looser than
#: :data:`REVIEW_DECISION_RATE_LIMIT` for the same reason that one is looser
#: than ``imports.py::IMPORT_RATE_LIMIT`` — and it is the identical shape and
#: number ``speaker_requests.py::SPEAKER_REQUEST_READ_RATE_LIMIT`` uses for the
#: identical act: a coordinator working a queue in a browser, refreshing it
#: after each decision. Its own ``operation`` string rather than a share of the
#: decision's, so a caller exhausting one is not refused the other: a
#: coordinator who has spent their minute's decisions must still be able to see
#: what is left, and being unable to *look* is not a limit anyone intended.
REVIEW_LIST_RATE_LIMIT: Final[RateLimit] = RateLimit(
    operation="review.list",
    max_requests=120,
    window=timedelta(minutes=1),
)

#: The most review items one response returns. G3 §2.2a's 200-record cap,
#: reused rather than a second number invented here — the same value and the
#: same reason ``speaker_requests.py::MAX_ROWS``, ``events.py::MAX_ROWS`` and
#: ``match_runs.py::MAX_CANDIDATES`` all carry. Paging is deliberately not
#: shipped: a cursor nobody has asked for is a contract to maintain, and
#: :attr:`ReviewItemListResponse.truncated` is what keeps a full page from
#: reading as a complete one.
MAX_ROWS: Final[int] = 200

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


#: Every status a review item may be listed at, and nothing else.
#:
#: Wider than :data:`ReviewDecisionValue` by exactly one member, because the
#: two answer different questions: that type is what a decision may *write*,
#: and ``pending`` is not a decision. This one is what a queue may be *filtered
#: to*, and a coordinator wanting to see what they already accepted is asking a
#: reasonable question about rows that exist.
#:
#: A ``Literal`` rather than ``str``, for the reason
#: :data:`ReviewDecisionValue`'s own comment gives: an out-of-vocabulary value
#: is refused by Pydantic in the standard ``invalid_request`` 422 envelope
#: before the handler body runs, so there is one enforcement site rather than a
#: second hand-written one to keep in step with ``ck_review_item_status``. It
#: also means there is no "everything" arm to reach by accident — no empty
#: string, no ``all``, no ``None`` that a repository predicate could widen into
#: the whole table. A caller must always name exactly one status, and the
#: default is the one the dashboard counts.
ReviewItemStatusFilter = Literal["pending", "accepted", "rejected"]


class ReviewItemView(BaseModel):
    """One review item as the queue discloses it.

    Deliberately **not** carrying ``decided_by``, which the row does have. That
    column holds a ``user_account`` id, and nothing in this API discloses one
    today — ``ReviewDecisionResponse`` above answers a decision with ``id``,
    ``status`` and ``decided_at`` and stops there. Under deny-by-default the
    absence of an existing disclosure is the answer, not an invitation: a list
    is the widest possible place to become the first surface that publishes who
    acted, since it returns many rows at once to anyone holding the unit's
    role rather than one row to the caller who just acted. Publishing it would
    be a product decision with its own justification to write down, and this
    route is not the place that decision would be made. See
    ``ReviewItemRow``'s docstring, which omits it one layer down for the same
    reason, so it is never selected at all rather than selected and dropped.

    ``row_data`` is the submitted record itself, verbatim as the import wrote
    it. That is the point of a review queue — a coordinator cannot decide a row
    they cannot read — and it is also why ``_REVIEW_ROLES`` gates this route
    exactly as ``metrics.drill_down`` is gated: this is the same disclosure the
    drill-down makes, so it answers to the same roles.
    """

    id: uuid.UUID
    import_batch_id: uuid.UUID = Field(
        description="The import that submitted this row; rows from one import share it."
    )
    row_index: int = Field(description="This row's position within its import batch, from zero.")
    status: ReviewItemStatusFilter
    row_data: dict[str, Any] = Field(
        description="The submitted record, exactly as the import wrote it."
    )
    created_at: datetime
    decided_at: datetime | None = Field(
        default=None,
        description=(
            "When this item was decided, or null when it is still pending. "
            "Null means undecided and never 'unknown' — the column is null for "
            "exactly the pending rows (ck_review_item_decision_evidence)."
        ),
    )


class ReviewItemListResponse(BaseModel):
    """One unit's review items at one status.

    Carries no count — not of these items and not of the unit's pending total.
    ``GET /v1/units/{unit_id}/metrics`` owns ``pending_review_items``, and
    ADR-0011 rule 4 is that a number with an owning query is read from that
    query rather than recomputed by a second handler that would have to stay in
    step with it by hand. :attr:`ReviewDecisionResponse` refuses the same
    temptation for the same reason, and the contract test asserts the two
    surfaces agree rather than letting this one restate the number.

    :attr:`truncated` is the one thing this response says about what it is not
    showing, and it is a fact rather than an estimate: the handler reads
    ``MAX_ROWS + 1`` rows and reports whether the extra one came back. It is
    never a guess and never a silent zero — ADR-0011 rule 1, unknown must not
    degrade to 0 — because "there are more" is measured by the same query that
    produced the page, not by a second count whose filters could drift from it.
    """

    unit_id: uuid.UUID
    status: ReviewItemStatusFilter = Field(
        description="The status these items were filtered to; echoes the request."
    )
    items: list[ReviewItemView]
    truncated: bool = Field(
        description="True when more items exist at this status than the response cap returns."
    )


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


def _authorize_review_item_list(
    session: Session,
    principal: CurrentPrincipal,
    unit_id: uuid.UUID,
) -> uuid.UUID:
    """Load the unit and authorize a coordinator's read of its review queue.

    **Its own function, and never a parameter on the decision path.** The two
    review routes gate on the same constant, :data:`_REVIEW_ROLES`, and it
    would be entirely possible to give ``decide_review_item``'s inline
    ``assert_allowed`` an extra argument and call it from here too. That is the
    refactor ``speaker_requests.py``'s two read authorizers exist to refuse,
    and their docstrings say why in one sentence: a helper that takes the role
    set — or the unit — as an argument makes a single call site the place from
    which every operation sharing it can be widened at once. Two functions
    naming one constant is a coupling the policy matrix *checks*
    (``test_the_authorizer_reads_the_role_constant_the_matrix_names``, against
    the live object); one function serving two operations is a coupling nothing
    checks, and the day the two roles should stop agreeing there would be no
    seam to separate them at.

    They also do genuinely different work. ``decide_review_item`` authorizes
    against a unit it *derives* from the review item's own import batch
    (:func:`_load_review_item_context_or_404`) and never accepts one from the
    request; this function is handed a ``unit_id`` from the path and loads
    *that* unit. Sharing a body would require one of the two to pass the other's
    input, which is how the derived unit stops being derived.

    ``load_unit_or_404`` scopes the lookup by the caller's own tenant, so a unit
    in another tenant is a 404 rather than a 403 that would confirm the id names
    something real — the same conclusion
    :func:`_load_review_item_context_or_404` reaches about a review item id.
    Authorization then runs against **that loaded row's path**, never against a
    path taken from the request, so naming a unit is a request to be refused
    rather than a claim to be believed.

    No ``require_membership``: :data:`_REVIEW_ROLES` is non-empty, so
    ``evaluate`` already refuses a bare ``resource_grant`` on the required-roles
    check (S-007). No ``tenant_wide_roles``: the metrics-authorization
    decision's §4 makes an ``admin`` unrestricted within the tenant for
    *aggregates*, and this route publishes ``row_data`` — the same disclosure
    ``metrics.drill_down`` withholds from an admin outside the subtree. Widening
    it here would silently overturn that, so nothing is passed.

    Returns:
        The authorized unit id — the only value that selects which rows the
        caller is about to read.
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
        required_roles=_REVIEW_ROLES,
    )
    return unit_id


@unit_router.get(
    "/{unit_id}/review-items",
    response_model=ReviewItemListResponse,
    summary="List a unit's review items",
)
def list_unit_review_items(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
    status_filter: Annotated[
        ReviewItemStatusFilter,
        Query(
            alias="status",
            description="Which status to list. Defaults to the queue a coordinator works.",
        ),
    ] = "pending",
) -> ReviewItemListResponse:
    """Return the review items this unit owns at one status, oldest first.

    The queue behind the badge. ``GET /v1/units/{unit_id}/metrics`` has counted
    ``pending_review_items`` for this unit since before this route existed, and
    until it did there was nothing to click through to — the dashboard showed a
    number it could not explain. The list and the count derive a row's owning
    unit through the *same* join (``review_item`` → ``import_batch`` →
    ``owning_unit_id``, in ``ReviewRepository.list_for_unit``), because
    ``review_item`` has no owning unit column and two derivations that drifted
    would put a row in one unit's queue and another unit's badge. See the module
    docstring; the contract test asserts the two agree on one fixture.

    **Nothing in the request selects whose rows come back beyond the authorized
    unit.** The path names a unit, which
    :func:`_authorize_review_item_list` loads and authorizes against before any
    review item is read; ``status`` chooses a column value and cannot widen
    across units; and there is no caller-supplied identity, no ``user_id``, no
    ``batch_id`` and no free-text predicate anywhere on this path. A caller who
    may read this unit reads all of this unit's items at that status, and a
    caller who may not reads none of them.

    Reads at most :data:`MAX_ROWS` + 1 rows so ``truncated`` is answered by the
    same query that produced the page rather than by a second count whose
    filters could drift from this one's — the shape
    ``speaker_requests.py::list_speaker_requests`` uses, followed here
    deliberately rather than reinvented. A full page therefore never reads as a
    complete one, and "there are more" is measured rather than assumed: ADR-0011
    rule 1, an unknown must not degrade to a 0 (or, here, to a quiet ``false``).

    Quota is charged before the unit is loaded and before authorization runs
    (ADR-0015), so a caller producing 404s against unit ids they invented spends
    exactly what a caller reading their own queue spends — the same ordering
    ``decide_review_item`` and ``create_import`` both apply, for the same
    reason: those are the refusals cheapest to produce in bulk.

    Raises:
        ApiError: 403 when the caller holds no ``_REVIEW_ROLES`` membership
            covering this unit; 404 when the unit is not this tenant's; 429 when
            the minute's quota is spent. A 422 comes from Pydantic when
            ``status`` is not one of the three the column admits.
    """
    charge_quota(session, principal, REVIEW_LIST_RATE_LIMIT)

    authorized_unit_id = _authorize_review_item_list(session, principal, unit_id)

    rows = _review_items.list_for_unit(
        session,
        tenant_id=principal.tenant_id,
        # The unit the authorizer just returned, not the raw path parameter.
        # They are equal today by construction, and using the returned value
        # says which of the two is load-bearing: the id that survived
        # authorization is the one the query may be scoped by.
        owning_unit_id=authorized_unit_id,
        status=status_filter,
        limit=MAX_ROWS + 1,
    )

    return ReviewItemListResponse(
        unit_id=authorized_unit_id,
        status=status_filter,
        items=[_item_view(row) for row in rows[:MAX_ROWS]],
        truncated=len(rows) > MAX_ROWS,
    )


def _item_view(row: ReviewItemRow) -> ReviewItemView:
    """Render one row for the wire, selecting fields rather than spreading them.

    Written out field by field instead of ``ReviewItemView(**vars(row))`` so
    that a column added to :class:`~smartmatch_persistence.review.ReviewItemRow`
    later cannot reach the wire by accident. ``decided_by`` is the exact reason
    that matters here: the omission is a decision, and a spread would let the
    next person undo it without noticing they had.
    """
    return ReviewItemView(
        id=row.id,
        import_batch_id=row.import_batch_id,
        row_index=row.row_index,
        status=cast(ReviewItemStatusFilter, row.status),
        row_data=dict(row.row_data),
        created_at=row.created_at,
        decided_at=row.decided_at,
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
