"""The student rewards catalog and the redemption command surface (S8, S9).

Card **U1** of ``docs/plans/2026-08-28-d6-rewards-s8-s9-plan.md`` asks for four
things at once: a server catalog, a server balance, a redemption that goes
through the durable state machine, and the deletion of the browser-side
formulas that used to stand in for all three. This module is the HTTP half.

* ``GET  /v1/units/{unit_id}/rewards`` — the listable catalog, the caller's own
  folded balance, and per-item progress. See :func:`read_reward_catalog`.
* ``POST /v1/units/{unit_id}/redemptions`` — open a redemption for one item.
  See :func:`request_redemption_route`.
* ``GET  /v1/units/{unit_id}/redemptions`` — the caller's own tickets. See
  :func:`read_own_redemptions`.
* ``POST /v1/units/{unit_id}/redemptions/{redemption_id}/decision`` — the
  coordinator hop through the state machine. See :func:`decide_redemption`.

## Nothing here is computed in a browser

ADR-0013's objection to the legacy rewards surface is quoted in
:mod:`smartmatch_domain.rewards`: a balance with no history behind it "cannot
answer 'why is my balance this'". The legacy frontend answered it with
``attendance_streak * 100 + events_attended * 25``
(``apps/web/legacy-frontend/src/lib/studentPoints.ts``, deleted in the commit
that lands this module) over a hard-coded seven-item catalog
(``studentRewardsCatalog.ts``, likewise). Both are gone, and the replacement is
not "the same arithmetic moved server-side": the balance below is
:func:`~smartmatch_domain.rewards.fold_balance` over ``point_ledger_entry``
rows, which is a sum of recorded facts rather than a formula over two summary
counters.

The catalog is likewise not a constant in this file. Every item comes from
:meth:`~smartmatch_persistence.rewards.RewardsRepository.listable_items`, whose
``WHERE funded IS TRUE`` and inner join to ``user_account`` on the composite
``(tenant_id, budget_owner_id)`` are D6's two halves stated in SQL. An unfunded
or unowned row is therefore never *selected*, so no filter in this module and
no filter in a client is what keeps it out of a student's view — which is the
difference between a rule and a rendering choice. There is deliberately no
query parameter that could widen the selection, and no ``include_unlisted``.

## Identity is the token's, and never the request's

``subject_id`` on every redemption below is ``principal.user_id`` — the account
:func:`~smartmatch_api.dependencies.get_current_principal` resolved from the
verified bearer token, the same value ``GET /v1/me`` reports. No request body,
query parameter, or header names a student. That is MM-A01 (stakeholder Fix
#7): the legacy portal let the caller pick who they were, and a redemption
route that accepted a ``subject_id`` would be that defect with points attached
to it. :class:`RedemptionRequest` carries exactly one field, ``item_id``, for
that reason.

## Zero is a measurement, not a default (ADR-0011)

:func:`~smartmatch_domain.rewards.fold_balance` folds an empty ledger to ``0``
and its docstring defends that: zero *known* entries is a known balance of
zero. What that reasoning does not cover is the case this router can see and
the fold cannot — a student with **attendance records** and **no ledger entry
deriving from them**. There the evidence exists and the credit has not been
applied, so ``0`` would be a number about a student's engagement that their own
attendance record contradicts. :func:`_fold_balance_for` therefore reports
:data:`BALANCE_UNKNOWN` in exactly that case, carrying the reason, and
:class:`RewardBalanceResponse` puts ``state`` beside ``points`` so no client has
to reconstruct "unknown" from a ``null`` that is one ``?? 0`` away from becoming
a fabricated zero — the same shape ``routers/match_runs.py`` uses for a
candidate it could not score.

An unknown balance is not merely a display concern.
:func:`request_redemption_route` refuses outright rather than passing the fold
to :func:`~smartmatch_domain.rewards.request_redemption`, whose refusal would
name a balance of ``0`` this router has just said it does not know.

## Progress only toward what a student could actually reach

``docs/architecture/engagement-model.md`` §4 asks that progress be shown only
toward reachable items, and
:func:`~smartmatch_domain.rewards.events_still_needed` enforces it by *raising*
for an unlistable item rather than returning a number a progress bar would
render. This module keeps that refusal representable end to end:
:attr:`RewardCatalogItemResponse.progress_state` is ``"unknown"`` and both
distance fields are ``null`` whenever the distance has no honest value, and the
frontend renders no bar for such an item. It is never approximated, and it is
never ``0`` — ``0`` here means "affordable now", which is a different and
checkable claim.

## The debit is taken at fulfilment, and this module does not move it

Migration ``0019`` deliberately did not add a fourth "refund" ledger kind, so
there is no entry that could return points to a student whose approved
redemption is later denied or expires — which is exactly why the debit is taken
when the reward is handed over and not when it is asked for. See
:meth:`~smartmatch_persistence.rewards.RewardsRepository.transition_redemption`.
Nothing in this module debits anything itself; the whole ledger consequence of
a fulfilment is that repository call.

## What this module deliberately does not ship

**No coordinator queue.** There is no route listing *other* people's
redemptions. ``GET /v1/units/{unit_id}/redemptions`` is a self-read, scoped to
``principal.user_id`` in the query rather than filtered afterwards, so a
coordinator calling it would see their own tickets and nobody else's. A queue is
a surface over other students' engagement records and needs the read-role
decision ``docs/decisions/d6-rewards-budget-decision-record.md`` §5 still lists
as open; :func:`decide_redemption` therefore acts on an id a coordinator was
given out of band.

**No catalog writer, no seeding, and no money.** ``reward_item`` rows are
written by the synthetic seed path, not by this API —
:class:`~smartmatch_persistence.rewards.RewardsRepository` has no item writer by
construction. ``fulfilment_cost`` is never read, returned, or summed here. D8
disclosure, procurement and real money are all out of scope, exactly as they
were before this module existed.

**No unit ownership claim.** ``reward_item`` and ``redemption`` are
tenant-scoped: neither table has an owning unit, so the catalog one student sees
is the catalog every student in the tenant sees. The ``{unit_id}`` in the path
is the *authorization* scope — the strictest scope this API can express, and the
one every other resource here is authorized against — not a claim that the
returned items belong to that unit. Saying so plainly is better than inventing a
per-unit catalog the schema cannot store.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Annotated, Final, Literal

import sqlalchemy as sa
from fastapi import APIRouter, Path, status
from pydantic import BaseModel, ConfigDict, Field
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_domain.rewards import (
    EARN_POLICY_RATIFIED,
    POINTS_PER_VERIFIED_ATTENDANCE,
    Redemption,
    RedemptionState,
    RewardItem,
    UnlistableRewardError,
    events_still_needed,
    fold_balance,
    is_listable,
)
from smartmatch_persistence import schema
from smartmatch_persistence.rate_limit import RateLimit
from smartmatch_persistence.rewards import (
    InsufficientBalanceError,
    RewardsRepository,
    UnknownRedemptionError,
    UnknownRewardItemError,
)
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal, DbSession, charge_quota
from smartmatch_api.errors import ApiError
from smartmatch_api.units import load_unit_or_404
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/units", tags=["rewards"])

#: The repository, built once. Stateless — every method takes its session — so
#: one module-level instance is the same object every request would construct.
#: ``routers/review.py`` holds its repository the same way.
_rewards = RewardsRepository()

#: Roles permitted to read the catalog, read their own tickets, and ask for a
#: redemption. The direction this card implements is "students see a server
#: catalog and request redemption", so ``student`` is the role, and under
#: deny-by-default the absence of a permit for anybody else is a denial rather
#: than an invitation to guess:
#: ``docs/decisions/d6-rewards-budget-decision-record.md`` §5 still lists
#: "Read/redemption roles" among the fields no artifact resolves, so a wider set
#: would be this module inventing one.
#:
#: A coordinator is therefore *not* admitted to these three operations. That is
#: not an oversight and not a hardship: a coordinator reads nothing here they
#: need — the catalog they administer is seeded, not browsed, and the only
#: tickets these routes return are the caller's own. What a coordinator needs is
#: :data:`_REDEMPTION_DECISION_ROLES` below.
#:
#: A literal ``frozenset`` rather than an import of another router's set, for
#: the reason ``tests/authz/test_route_roles.py`` gives: two role sets agreeing
#: today is not a reason a widening of one should silently widen the other.
_REWARDS_STUDENT_ROLES: Final[frozenset[str]] = frozenset({"student"})

#: Roles permitted to move a redemption through its state machine. ``admin``
#: and ``coordinator``, matching ``review.py::_REVIEW_ROLES`` — and for the
#: reason that file gives for matching ``imports.py``: approving, denying or
#: fulfilling a reward is the same kind of consequential act on a student's
#: record that deciding a review item is, and
#: ``d6-rewards-budget-decision-record.md`` §2 puts operational administration of
#: the rewards program with the IA West Coordinator by name.
_REDEMPTION_DECISION_ROLES: Final[frozenset[str]] = frozenset({"admin", "coordinator"})

#: v1.1 §3.4 pilot default. A redemption request writes one row inside the
#: request — no durable job, no queued provider call — so it is bounded like
#: ``review.py``'s decision rather than like an import, but tighter: a request is
#: idempotent per item (``uq_redemption_open_per_item``), so a student has no
#: legitimate reason to issue many per minute.
REDEMPTION_REQUEST_RATE_LIMIT = RateLimit(
    operation="redemption.request",
    max_requests=10,
    window=timedelta(minutes=1),
)

#: Same shape and the same number as ``review.py::REVIEW_DECISION_RATE_LIMIT``,
#: because it bounds the same thing: a human working through a queue of pending
#: items, one click at a time.
REDEMPTION_DECISION_RATE_LIMIT = RateLimit(
    operation="redemption.decide",
    max_requests=60,
    window=timedelta(minutes=1),
)

#: Whether a points figure in a response is a number at all. Two values and no
#: third: there is no "stale", no "partial", and no "estimated" — a figure this
#: API is not certain of is simply not reported.
BalanceState = Literal["measured", "unknown"]

#: The balance is a fold this request actually performed. Typed as the
#: ``Literal`` rather than as ``str`` so a typo in a constructor call below is a
#: type error rather than an invalid response discovered at runtime.
BALANCE_MEASURED: Final[BalanceState] = "measured"

#: The balance is *not* reported. See the module docstring: attendance is on file
#: and no ledger entry derives from it, so the fold's ``0`` would describe a
#: student whose own attendance record contradicts it.
BALANCE_UNKNOWN: Final[BalanceState] = "unknown"

#: The transitions a person may command over HTTP. ``expired`` is absent
#: deliberately and is not an omission a later card should quietly fill:
#: :meth:`~smartmatch_persistence.rewards.RewardsRepository.transition_redemption`
#: refuses an expiry that names an actor — "an expiry has no author: it is
#: something time does" — so an HTTP command, which always has one, could not
#: produce one honestly. Ageing a redemption out is a sweeper's job, and this API
#: has no route that pretends otherwise.
RedemptionDecisionValue = Literal["approved", "fulfilled", "denied"]


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class RewardBalanceResponse(BaseModel):
    """The caller's own point balance, and whether it is a number at all.

    ``state`` is carried beside ``points`` rather than left to be inferred from
    a ``null``, which is ADR-0011's whole point: a consumer that has to
    reconstruct "unknown" from an absent number is one ``?? 0`` away from
    rendering a fabricated zero, which is exactly what the deleted
    ``studentPoints.ts`` call site did (``profile ? getStudentTotalPoints(profile) : 0``).
    """

    state: BalanceState = Field(
        description=(
            "'measured' when this response carries a fold over the ledger; "
            "'unknown' when the ledger has nothing to fold and the student's "
            "attendance record says it should. Read this before `points`."
        )
    )
    points: int | None = Field(
        default=None,
        description=(
            "The folded balance, or null when `state` is 'unknown'. Never a "
            "stored counter: recomputed from `point_ledger_entry` on every "
            "request (ADR-0013)."
        ),
    )
    ledger_entry_count: int = Field(
        description=(
            "How many ledger entries this fold summed. The evidence that makes a "
            "zero a measured zero rather than a default one."
        )
    )
    unknown_reason: str | None = Field(
        default=None,
        description="Why the balance is unknown, when it is. Null otherwise.",
    )


class RewardCatalogItemResponse(BaseModel):
    """One listable reward, with the caller's distance to it.

    Every item in a catalog response is listable by construction — the query
    that produced it selects on ``funded IS TRUE`` and joins the budget owner —
    so this model has no ``funded`` or ``budget_owner_id`` field to render. An
    item's presence *is* the statement that it is owned and funded; a boolean
    beside it would invite a client to render the unlistable case, which the
    server never sends.
    """

    item_id: uuid.UUID = Field(description="This reward item's id, as a redemption names it")
    name: str = Field(description="The item's current name")
    points_cost: int = Field(description="What it costs now; a redemption snapshots this")
    affordable: bool = Field(
        description=(
            "Whether the caller's measured balance already covers `points_cost`. "
            "False whenever the balance is unknown — an unknown balance affords "
            "nothing, rather than affording what a zero would not."
        )
    )
    progress_state: BalanceState = Field(
        description=(
            "'measured' when the two distance fields below carry numbers; "
            "'unknown' when this student's distance to this item has no honest "
            "value. A client renders no progress bar for 'unknown'."
        )
    )
    points_still_needed: int | None = Field(
        default=None,
        description="Points between the measured balance and `points_cost`; 0 when affordable.",
    )
    events_still_needed: int | None = Field(
        default=None,
        description=(
            "Verified attendances still needed at the *tentative* D7 earn rate "
            "reported by `points_per_verified_attendance`; 0 when affordable."
        ),
    )


class RewardCatalogResponse(BaseModel):
    """The catalog a student may be shown, and their own standing against it."""

    unit_id: uuid.UUID = Field(
        description=(
            "The unit this request was authorized against. Not the items' owner: "
            "`reward_item` is tenant-scoped and has no owning unit."
        )
    )
    balance: RewardBalanceResponse = Field(description="The caller's own balance")
    points_per_verified_attendance: int = Field(
        description=(
            "The earn rate the `events_still_needed` arithmetic used. Reported "
            "rather than assumed by the client, because it is D7's and D7 is "
            "tentative — see `earn_policy_ratified`."
        )
    )
    earn_policy_ratified: bool = Field(
        description=(
            "Whether the earn policy behind `points_per_verified_attendance` is "
            "organizationally ratified. False today: D7 is recorded tentative "
            "(docs/decisions/pilot-decisions.md §D7)."
        )
    )
    items: list[RewardCatalogItemResponse] = Field(
        description=(
            "Every listable item in this tenant, cheapest first. An unfunded or "
            "unowned item is absent because the query never selected it, not "
            "because a filter dropped it."
        )
    )


class RedemptionResponse(BaseModel):
    """One redemption ticket, as its owner and its coordinator both see it.

    The item name and cost are the redemption's own **snapshots**, not a join
    back to ``reward_item``: D7 says an existing redemption keeps its point-cost
    snapshot and that a deactivated reward stays visible on existing tickets, so
    a join would answer with today's price and might answer with nothing at all.
    """

    redemption_id: uuid.UUID = Field(description="This ticket's id")
    item_id: uuid.UUID = Field(description="The reward item redeemed against")
    item_name: str = Field(description="The item's name as the student was shown it")
    points_cost: int = Field(description="The cost snapshotted when the request was made")
    state: Literal["requested", "approved", "fulfilled", "denied", "expired"] = Field(
        description=(
            "Where this ticket sits in `requested -> approved -> "
            "fulfilled | denied | expired`. `fulfilled` is reachable only from "
            "`approved`."
        )
    )


class RedemptionListResponse(BaseModel):
    """The caller's own redemptions. Never anybody else's."""

    unit_id: uuid.UUID = Field(description="The unit this request was authorized against")
    redemptions: list[RedemptionResponse] = Field(
        description="The caller's own tickets, newest request first"
    )


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class RedemptionRequest(BaseModel):
    """A student asking for one reward.

    One field, and that is the design. There is no ``subject_id`` here and there
    will not be one: identity comes from the verified token (module docstring,
    MM-A01). There is no ``points_cost`` either — a caller naming their own price
    is the same defect wearing a different hat, and the snapshot is taken
    server-side from the row.

    ``extra="forbid"`` so a body that *tries* to name a subject is refused
    rather than silently ignored. Ignoring it would be safe — nothing reads it —
    but a caller who sent ``subject_id`` and received a ``201`` has been told
    their request was honoured as sent, and the next person to read this route's
    traffic would reasonably conclude the field does something. A 422 says
    plainly that there is no such field.
    """

    model_config = ConfigDict(extra="forbid")

    item_id: uuid.UUID = Field(description="The reward item to redeem against")


class RedemptionDecisionRequest(BaseModel):
    """A coordinator's move on one redemption.

    ``Literal`` rather than ``str``: an out-of-vocabulary value is refused by
    Pydantic in the standard ``invalid_request`` envelope before this handler
    runs, which is one enforcement site rather than a second one this router
    would have to keep in step with ``ck_redemption_state`` by hand — the same
    reasoning ``review.py::ReviewDecisionValue`` records.
    """

    decision: RedemptionDecisionValue = Field(
        description=(
            "The state to move to. `expired` is not offered: an expiry has no "
            "author, and every HTTP command has one."
        )
    )


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def _authorize_student_rewards(
    session: Session,
    principal: CurrentPrincipal,
    unit_id: uuid.UUID,
) -> None:
    """Load the unit and authorize a student's own rewards surface against it.

    Shared by the catalog read, the self-read of tickets, and the redemption
    request, because all three ask the identical question — may this caller act
    on this unit's rewards as a student — against the identical ``org_unit``
    resource. One function rather than three, in the same spirit as
    ``routers/events.py::_authorize_event_read`` and
    ``routers/match_runs.py::_authorize_match_run``: a widening applies to all of
    them or to none, and cannot reach one by accident.

    The unit is loaded first and authorization runs against *that row's* path,
    never a path taken from the request. ``load_unit_or_404`` scopes the lookup
    by the caller's own tenant, so a unit in another tenant is a 404 rather than
    a 403 that would confirm the id names something real.

    No ``require_membership`` and no ``tenant_wide_roles``.
    :data:`_REWARDS_STUDENT_ROLES` is non-empty, so ``evaluate`` refuses a bare
    ``resource_grant`` on the required-roles check before membership is reached
    (S-007), and no committed artifact makes a rewards read tenant-wide the way
    the metrics decision's §4 makes aggregate reads tenant-wide.
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
        required_roles=_REWARDS_STUDENT_ROLES,
    )


def _authorize_redemption_decision(
    session: Session,
    principal: CurrentPrincipal,
    unit_id: uuid.UUID,
) -> None:
    """Load the unit and authorize a coordinator's move against it.

    A separate function from :func:`_authorize_student_rewards` rather than the
    same one taking a role-set argument, because the two are genuinely different
    decisions: one admits the student whose points are at stake, the other the
    person who spends the budget on their behalf. Passing the role set in would
    make one call site the place both are widened from.
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
        required_roles=_REDEMPTION_DECISION_ROLES,
    )


# ---------------------------------------------------------------------------
# The balance, and what makes it a number
# ---------------------------------------------------------------------------


def _attendance_count(session: Session, *, tenant_id: uuid.UUID, subject_id: uuid.UUID) -> int:
    """How many attendance records this tenant holds for ``subject_id``.

    Read only to tell an honest zero from an unknown one — see
    :func:`_fold_balance_for`. Nothing else in this module uses it, and it
    returns a count rather than rows so no attendance detail can leak into a
    response through it.
    """
    return int(
        session.execute(
            sa.select(sa.func.count()).where(
                schema.attendance_record.c.tenant_id == tenant_id,
                schema.attendance_record.c.subject_id == subject_id,
            )
        ).scalar_one()
    )


def _fold_balance_for(
    session: Session, *, tenant_id: uuid.UUID, subject_id: uuid.UUID
) -> RewardBalanceResponse:
    """Fold ``subject_id``'s ledger, or report that there is nothing to fold.

    The fold itself is :func:`~smartmatch_domain.rewards.fold_balance` over rows
    this function read — never a ``SUM()`` the database remembers, and never a
    column. That is ADR-0013's requirement and
    :meth:`~smartmatch_persistence.rewards.RewardsRepository.balance_for_subject`
    already satisfies it; the entries are read here rather than through that
    method only because the *count* is part of the answer.

    The unknown case is narrow and stated positively: no ledger entries **and**
    at least one attendance record. Anything else is measured — an empty ledger
    for a student who has attended nothing included, because that student has
    earned nothing, which is a fact and not the absence of one.
    """
    entries = _rewards.ledger_entries_for_subject(
        session, tenant_id=tenant_id, subject_id=subject_id
    )
    if not entries and _attendance_count(session, tenant_id=tenant_id, subject_id=subject_id):
        return RewardBalanceResponse(
            state=BALANCE_UNKNOWN,
            points=None,
            ledger_entry_count=0,
            unknown_reason=(
                "Attendance is on file for this account and no point ledger entry derives "
                "from it yet, so this balance has not been established. It is not zero."
            ),
        )
    return RewardBalanceResponse(
        state=BALANCE_MEASURED,
        points=fold_balance(entries),
        ledger_entry_count=len(entries),
    )


def _catalog_item_view(
    item: RewardItem, balance: RewardBalanceResponse
) -> RewardCatalogItemResponse:
    """Describe one listable item, refusing to invent a distance to it.

    Two things make the distance unknown, and both produce the same shape — no
    numbers, ``progress_state="unknown"``, and therefore no progress bar in any
    client:

    * the balance is unknown, so every distance from it would be too;
    * the item is not listable, which
      :func:`~smartmatch_domain.rewards.events_still_needed` refuses outright.
      The catalog query cannot produce such an item, so this arm is the
      fail-closed answer for the day something else calls this function rather
      than a case :func:`read_reward_catalog` reaches.
    """
    if balance.points is None or not is_listable(item):
        return RewardCatalogItemResponse(
            item_id=item.item_id,
            name=item.name,
            points_cost=item.points_cost,
            affordable=False,
            progress_state=BALANCE_UNKNOWN,
        )
    return RewardCatalogItemResponse(
        item_id=item.item_id,
        name=item.name,
        points_cost=item.points_cost,
        affordable=item.points_cost <= balance.points,
        progress_state=BALANCE_MEASURED,
        points_still_needed=max(0, item.points_cost - balance.points),
        events_still_needed=events_still_needed(
            item,
            balance=balance.points,
            points_per_event=POINTS_PER_VERIFIED_ATTENDANCE,
        ),
    )


def _redemption_view(redemption: Redemption) -> RedemptionResponse:
    """Render one redemption from its own snapshots."""
    return RedemptionResponse(
        redemption_id=redemption.redemption_id,
        item_id=redemption.item_id,
        item_name=redemption.item_name_snapshot,
        points_cost=redemption.points_cost_snapshot,
        state=redemption.state.value,
    )


# ---------------------------------------------------------------------------
# S8 — the catalog
# ---------------------------------------------------------------------------


@router.get(
    "/{unit_id}/rewards",
    response_model=RewardCatalogResponse,
    summary="List the funded rewards catalog and the caller's own balance",
)
def read_reward_catalog(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
) -> RewardCatalogResponse:
    """Return every listable reward, the caller's folded balance, and the distance between.

    Authorization runs before any reward or ledger row is read
    (:func:`_authorize_student_rewards`).

    The listing is the repository's, and its two conditions — a funded balance
    and a named same-tenant budget owner — are D6's. Nothing here filters the
    result further and nothing here could show an unfunded item, because no
    unfunded item is selected.

    Quota is not charged. ADR-0015 governs command routes, where a refusal still
    cost something to attempt; this route reads rows the caller is already
    authorized for, exactly as the two job reads and ``GET /v1/me`` do.
    """
    _authorize_student_rewards(session, principal, unit_id)

    balance = _fold_balance_for(
        session, tenant_id=principal.tenant_id, subject_id=principal.user_id
    )
    items = _rewards.listable_items(session, tenant_id=principal.tenant_id)

    return RewardCatalogResponse(
        unit_id=unit_id,
        balance=balance,
        points_per_verified_attendance=POINTS_PER_VERIFIED_ATTENDANCE,
        earn_policy_ratified=EARN_POLICY_RATIFIED,
        items=[_catalog_item_view(item, balance) for item in items],
    )


# ---------------------------------------------------------------------------
# S9 — redemption
# ---------------------------------------------------------------------------


@router.post(
    "/{unit_id}/redemptions",
    status_code=status.HTTP_201_CREATED,
    response_model=RedemptionResponse,
    summary="Request a redemption against one funded reward",
)
def request_redemption_route(
    principal: CurrentPrincipal,
    session: DbSession,
    body: RedemptionRequest,
    unit_id: Annotated[uuid.UUID, Path()],
) -> RedemptionResponse:
    """Open a ``requested`` redemption for the caller, or return the one already open.

    ``201``, and idempotent: a second request for an item the caller already has
    in flight writes nothing and returns that ticket, which is card L4's
    "concurrent duplicate requests resolve to one redemption" enforced by
    ``uq_redemption_open_per_item`` rather than by this handler noticing.

    The returned ticket is always ``requested``. There is no argument that could
    make it ``approved`` — the approval step is ADR-0013's, and a request route
    that could skip it would be that step deleted rather than passed.

    Quota is charged first (ADR-0015), before the unit is loaded and before
    authorization, so a caller producing 403s against units they hold nothing
    over, or 404s against item ids they invented, spends what a real request
    spends.

    Raises:
        ApiError: 409 when the balance is unknown, when it does not cover the
            item, or when the item is not listable; 404 when no such item exists
            in this tenant.
    """
    charge_quota(session, principal, REDEMPTION_REQUEST_RATE_LIMIT)

    _authorize_student_rewards(session, principal, unit_id)

    balance = _fold_balance_for(
        session, tenant_id=principal.tenant_id, subject_id=principal.user_id
    )
    if balance.points is None:
        # Refused here rather than by `request_redemption`, whose message would
        # name a balance of 0 this response has just declined to claim.
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="balance_unknown",
            message=(
                "This account's point balance has not been established, so it cannot "
                "be spent. It is not zero."
            ),
            details={"unknown_reason": balance.unknown_reason},
        )

    try:
        redemption = _rewards.open_redemption(
            session,
            tenant_id=principal.tenant_id,
            subject_id=principal.user_id,
            item_id=body.item_id,
        )
    except UnknownRewardItemError as exc:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="reward_item_not_found",
            message="No such reward item.",
        ) from exc
    except UnlistableRewardError as exc:
        # Caught before the balance branch below because it is the narrower
        # `ValueError`. D6, not affordability: this item is unowned or unfunded
        # and nobody would honour it at any price.
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="reward_item_not_listable",
            message="That reward is not available for redemption.",
        ) from exc
    except ValueError as exc:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="insufficient_balance",
            message="Your balance does not cover that reward.",
            details={"balance": balance.points},
        ) from exc

    session.commit()
    return _redemption_view(redemption)


@router.get(
    "/{unit_id}/redemptions",
    response_model=RedemptionListResponse,
    summary="List the caller's own redemptions",
)
def read_own_redemptions(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
) -> RedemptionListResponse:
    """Return the caller's own redemption tickets, newest request first.

    Scoped to ``principal.user_id`` **in the query**, not filtered afterwards, so
    there is no shape of this handler in which another student's ticket is loaded
    and then dropped. See the module docstring for why there is no coordinator
    queue here.
    """
    _authorize_student_rewards(session, principal, unit_id)

    redemptions = _rewards.redemptions_for_subject(
        session, tenant_id=principal.tenant_id, subject_id=principal.user_id
    )
    return RedemptionListResponse(
        unit_id=unit_id,
        redemptions=[_redemption_view(redemption) for redemption in redemptions],
    )


@router.post(
    "/{unit_id}/redemptions/{redemption_id}/decision",
    response_model=RedemptionResponse,
    summary="Approve, deny, or fulfil a redemption",
)
def decide_redemption(
    principal: CurrentPrincipal,
    session: DbSession,
    body: RedemptionDecisionRequest,
    unit_id: Annotated[uuid.UUID, Path()],
    redemption_id: Annotated[uuid.UUID, Path()],
) -> RedemptionResponse:
    """Move one redemption through the state machine, taking the debit on fulfilment.

    The legality of the move is decided by
    :meth:`~smartmatch_domain.rewards.Redemption.transition` inside
    :meth:`~smartmatch_persistence.rewards.RewardsRepository.transition_redemption`,
    and this handler restates none of it: ``fulfilled`` is reachable only from
    ``approved`` because the machine says so and because
    ``ck_redemption_approval_evidence`` refuses the row otherwise, not because of
    a check written here.

    Fulfilment is where the ledger debit is taken, inside the same transaction
    and behind the same ``FOR UPDATE`` lock, and the balance is re-folded there
    rather than trusted from the request — an approved ticket may have sat while
    the credits behind it were reversed. Migration ``0019`` added no refund kind,
    which is why the debit is not taken at request time; this route does not
    revisit that decision.

    ``200``, not ``202``: nothing durable starts here. The ``UPDATE`` and the
    ledger insert either land in this request or they do not.

    Raises:
        ApiError: 404 when this tenant has no such redemption; 409 when the move
            is not one the machine allows, or when fulfilment was asked for and
            the balance no longer covers the snapshot cost.
    """
    charge_quota(session, principal, REDEMPTION_DECISION_RATE_LIMIT)

    _authorize_redemption_decision(session, principal, unit_id)

    try:
        moved = _rewards.transition_redemption(
            session,
            tenant_id=principal.tenant_id,
            redemption_id=redemption_id,
            to_state=RedemptionState(body.decision),
            actor_id=principal.user_id,
        )
    except UnknownRedemptionError as exc:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="redemption_not_found",
            message="No such redemption.",
        ) from exc
    except InsufficientBalanceError as exc:
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="insufficient_balance",
            message=(
                "This redemption can no longer be fulfilled: the balance behind it no "
                "longer covers the cost it was requested at."
            ),
        ) from exc
    except ValueError as exc:
        # `InvalidRedemptionTransition` is a `ValueError`, and so is the
        # actor-evidence refusal. Both mean the same thing to a caller: the move
        # asked for is not one this redemption can make.
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="invalid_redemption_transition",
            message=str(exc),
        ) from exc

    session.commit()
    return _redemption_view(moved)
