"""The unit-scoped engagement read surface (R2).

One route:

* ``GET /v1/units/{unit_id}/engagement/attendance-summary`` — how much
  attendance evidence one unit holds, counted from ``attendance_record`` rows.
  See :func:`read_attendance_summary`.

This module used to declare no handlers at all, and
``tests/unit/test_matching_fail_closed.py`` asserted that emptiness. That
assertion is now an exact allowlist of the one path below, flipped in the
commit that lands the capability — the rule
``docs/plans/2026-08-28-plan-portfolio-index.md`` states for that file, and the
shape cards P-EVENTS-API, P-MATCH-API and P-REWARDS-API each used before this
one. An allowlist rather than a licence: a second engagement path fails there
whether or not anyone regenerated the contract.

## A count of evidence, and nothing about a person

The response carries a total, a breakdown by the three mechanisms
``ck_attendance_record_method`` allows, two distinct counts, and the first and
last instants a row was recorded. It carries no ``subject_id``, no name, no
email, and no per-student row — and not because a filter drops them:
:class:`~smartmatch_persistence.engagement.EngagementRepository` counts subjects
and events with ``count(distinct ...)`` inside the database and never selects
either column, so there is no projection a student identifier could arrive
through.

That is what lets this route exist while **D8** — the disclosure-consent policy,
and what "FERPA-aware" asserts — is still open
(``docs/architecture/engagement-model.md`` §8, ADR-0014). A roster of who
attended is a disclosure about people and waits for D8. A count of how much
evidence a unit holds is a fact about the unit's own record-keeping, which is
what a coordinator needs to answer "is check-in actually being used here".
``docs/plans/open-questions/engagement-deferred.md`` records both deferrals and
what would have to land to lift them.

## Coordinator-and-above, and scoped to the unit in the path

``{admin, coordinator}``, matching ``routers/events.py``'s reads rather than
``routers/rewards.py``'s student surface: a summary is about a cohort, so the
person it is written for is the one who runs the cohort, and a student reading
it would learn about other people's attendance without learning anything about
their own that ``GET /v1/units/{unit_id}/rewards`` does not already tell them.

No ``tenant_wide_roles``. The ratified metrics decision's §4 makes *aggregate*
reads tenant-wide for an admin, and this is an aggregate — but that decision
names the metrics surface, not this one, and reading a committed decision as
covering a route it does not mention is how a scope quietly widens. Ordinary
subtree containment applies, so an admin or coordinator in a sibling department
is refused, which is the cross-unit denial this card is measured on.

## Nothing is computed in a browser, and nothing is computed twice

The total is :func:`~smartmatch_domain.attendance.summarize_attendance`'s fold
over the same breakdown this response carries, so a client that adds the
breakdown up gets the total it was sent. That is Fix #9's rule — "a balance is a
fold over recorded rows, computed server-side, never in a browser" (ADR-0013) —
applied to the coordinator's number as well as the student's.

## What this module deliberately does not ship

**No writer.** There is no ``POST`` here and no check-in endpoint. B08
(``docs/plans/frontend-broken-buttons.md``) puts the QR check-in *flow* behind
S11 and D8; :mod:`smartmatch_domain.checkin` lands the token rule it will need,
unwired, and no route in this repository imports it
(``tests/unit/test_checkin_wiring.py``).

**No points.** ``point_ledger_entry`` is not read here. A summary of evidence is
not a statement about anybody's balance, and the balance already has one honest
home in ``routers/rewards.py`` — including its ``unknown`` state, which a second
computation of the same thing would be free to disagree with.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Final

from fastapi import APIRouter, Path
from pydantic import BaseModel, Field
from smartmatch_authz import OrgPath, Resource, assert_allowed
from smartmatch_domain.attendance import summarize_attendance
from smartmatch_persistence.engagement import EngagementRepository
from sqlalchemy.orm import Session

from smartmatch_api.dependencies import CurrentPrincipal, DbSession
from smartmatch_api.units import load_unit_or_404
from smartmatch_api.utils import utc_now

router = APIRouter(prefix="/v1/units", tags=["engagement"])

#: The repository, built once. Stateless — every method takes its session — so
#: one module-level instance is the same object every request would construct.
#: ``routers/rewards.py`` and ``routers/review.py`` hold theirs the same way.
_engagement = EngagementRepository()

#: Roles permitted to read a unit's attendance summary. ``{admin, coordinator}``
#: — the same set ``routers/events.py``'s reads use, and for the same reason:
#: this is unit record-keeping a coordinator is accountable for, not a student's
#: own standing.
#:
#: A literal ``frozenset`` rather than an import of another router's set, for
#: the reason ``tests/authz/test_route_roles.py`` gives: two role sets agreeing
#: today is not a reason a widening of one should silently widen the other.
_ENGAGEMENT_READ_ROLES: Final[frozenset[str]] = frozenset({"admin", "coordinator"})


class AttendanceSummaryResponse(BaseModel):
    """One unit's attendance evidence, counted. Never a roster."""

    unit_id: uuid.UUID = Field(
        description=(
            "The unit this summary counts, which is also the unit the request "
            "was authorized against. Rows are selected on "
            "`attendance_record.owning_unit_id`, so the two cannot differ."
        )
    )
    total: int = Field(
        description=(
            "Attendance rows recorded for this unit. The sum of `by_method`, "
            "folded server-side from the same counts this response carries — "
            "never a stored counter and never arithmetic left to a client."
        )
    )
    by_method: dict[str, int] = Field(
        description=(
            "Row count for every mechanism `ck_attendance_record_method` allows: "
            "`qr_scan`, `coordinator_entry`, `import`. All three keys are always "
            "present; a mechanism with no rows is a measured 0, not an absent key."
        )
    )
    distinct_subjects: int = Field(
        description=(
            "How many different accounts those rows belong to. A count only — "
            "this API returns no list of them while D8 is open."
        )
    )
    distinct_events: int = Field(
        description="How many different events those rows attest to.",
    )
    first_recorded_at: datetime | None = Field(
        default=None,
        description=(
            "When the earliest of those rows was recorded, or null when there "
            "are none. Timezone-aware (ADR-0010)."
        ),
    )
    last_recorded_at: datetime | None = Field(
        default=None,
        description="When the latest was recorded, or null when there are none.",
    )


def _authorize_engagement_read(
    session: Session,
    principal: CurrentPrincipal,
    unit_id: uuid.UUID,
) -> None:
    """Load the unit and authorize a coordinator's engagement read against it.

    The unit is loaded first and authorization runs against *that row's* path,
    never a path taken from the request. ``load_unit_or_404`` scopes the lookup
    by the caller's own tenant, so a unit in another tenant is a 404 rather than
    a 403 that would confirm the id names something real.

    No ``require_membership`` and no ``tenant_wide_roles``.
    :data:`_ENGAGEMENT_READ_ROLES` is non-empty, so ``evaluate`` refuses a bare
    ``resource_grant`` on the required-roles check before membership is reached
    (S-007), and no committed artifact makes an attendance summary tenant-wide —
    see this module's docstring on why the metrics decision's §4 is not read as
    covering it.
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
        required_roles=_ENGAGEMENT_READ_ROLES,
    )


@router.get(
    "/{unit_id}/engagement/attendance-summary",
    response_model=AttendanceSummaryResponse,
    summary="Count one unit's recorded attendance evidence",
)
def read_attendance_summary(
    principal: CurrentPrincipal,
    session: DbSession,
    unit_id: Annotated[uuid.UUID, Path()],
) -> AttendanceSummaryResponse:
    """Return how much attendance evidence this unit holds, by mechanism.

    Authorization runs before any attendance row is read
    (:func:`_authorize_engagement_read`), and the unit it authorizes against is
    the unit the counts are scoped to.

    A unit with nothing recorded answers ``total: 0``, all three methods at
    ``0``, and two null instants — a measured zero, because the query ran and
    found none, which is a different claim from "we did not look" (ADR-0011).
    The route cannot be reached for a unit that does not exist: that is a 404
    from ``load_unit_or_404``, decided before any counting.

    Quota is not charged. ADR-0015 governs command routes, where a refusal still
    cost something to attempt; this route reads rows the caller is already
    authorized for, exactly as the two event reads and the rewards catalog do.
    """
    _authorize_engagement_read(session, principal, unit_id)

    counts = _engagement.attendance_counts_for_unit(
        session, tenant_id=principal.tenant_id, owning_unit_id=unit_id
    )
    summary = summarize_attendance(
        method_counts=counts.method_counts,
        distinct_subjects=counts.distinct_subjects,
        distinct_events=counts.distinct_events,
        first_recorded_at=counts.first_recorded_at,
        last_recorded_at=counts.last_recorded_at,
    )

    return AttendanceSummaryResponse(
        unit_id=unit_id,
        total=summary.total,
        # `dict(...)` because the fold hands back a read-only mapping over the
        # whole of ATTENDANCE_METHODS; the copy is the response's own, and the
        # domain's stays immutable.
        by_method=dict(summary.by_method),
        distinct_subjects=summary.distinct_subjects,
        distinct_events=summary.distinct_events,
        first_recorded_at=summary.first_recorded_at,
        last_recorded_at=summary.last_recorded_at,
    )
