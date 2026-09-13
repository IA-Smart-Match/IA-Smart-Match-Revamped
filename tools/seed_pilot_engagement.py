#!/usr/bin/env python3
"""Seed the engagement surfaces **under the accounts the demo logins resolve to**.

An operator tool, like :mod:`seed_pilot`, :mod:`seed_pilot_principals` and
:mod:`seed_pilot_rewards`, whose settings gate and advisory lock it reuses. It
fills the three tables no phase of ``tools/generate_pilot_dataset.py`` writes at
all — ``event_registration``, ``cba_meeting`` and ``redemption`` — and it credits
the student surfaces to the one student account a person can actually sign in as.

## The defect this exists for, stated plainly

The pilot appliance had 187 ``point_ledger_entry`` rows and a blank student
rewards screen. Both facts were true at once, and neither is a bug in a route.

Three surfaces are scoped by ``principal.user_id`` and not by unit:

* the rewards balance — ``_fold_balance_for(subject_id=principal.user_id)``;
* the student agenda — ``attendance_record`` and ``event_registration`` for
  *this* student;
* the Event Host's own filed requests — ``filed_by_user_id ==
  principal.user_id`` (OQ-CBA-014).

The generator writes the first two under ``synthetic-student:*`` accounts it
mints itself, and files every Speaker Request with the **coordinator** token. So
the rows exist, the tenant-wide counts look healthy, and the four people who sign
in see nothing. A row count cannot see that;
``verify_pilot_dataset.DEMO_PORTAL_SURFACES`` and this tool are the two halves of
the answer, and ``tests/unit/test_demo_portal_surfaces.py`` holds them together.

Every subject this tool writes under is therefore one of the four accounts a
*person* can reach, resolved from ``user_account`` by ``external_subject`` at
run time. By default that is the ``pilot-login-*`` family — the accounts
``tools/seed_pilot_logins.py`` creates for the four ``@``-addressed credentials
a reviewer types into ``POST /v1/auth/login``. ``--subjects fixture`` selects
the ``compose-pilot-*`` accounts the local ``SMARTMATCH_DEV_PRINCIPALS`` bearer
tokens resolve to, for a stack driven by tokens and no browser.

That default was the other way round, and it reproduced the very defect above
one level up: the rows landed on accounts nobody signs in as, so ``student@``
and ``volunteer@`` saw blank pages over a database this tool reported as
seeded. A default is not a documentation problem; it is where the trap lives.

It **creates no account**: if neither ``make seed-pilot-logins`` nor
``make seed-pilot-principals`` has run for the chosen family, this tool refuses
rather than minting a fifth identity that nothing can authenticate as.

## What it does not do

It does not invent catalog content. Every ``reward_item`` value is still
owner-supplied through :mod:`seed_pilot_rewards`, whose
:func:`~seed_pilot_rewards.seed_reward_item` this tool calls rather than
reimplements — so the worksheet stays the one place a price is written down and
this tool cannot become a second one. ``--items-from-worksheet`` names the rows
of ``docs/pilot-data/rewards-catalog-worksheet.md`` that an owner has already
filled in; it is not a default catalog, and the flag is required.

It writes no ``speaker_request_classification`` row by hand. The one Event Host
request it files goes through :class:`SpeakerRequestDraft`, so §7/§8's
"at least one industry and one role" and §10's location rule are enforced by the
domain exactly as they are for a request a person types. The plan's warning
against ``INSERT``-ing classifications directly is the reason: a half-valid row
minted around the validator is the class of defect being removed, not a shortcut
to removing it.

It grants nothing, and opens no route. Seeding is an operator's act (see
:mod:`seed_pilot_rewards`'s docstring making the same point), and no role set
anywhere moved to make any of these rows readable.

## Rerunning it

Idempotent throughout, by the same rule the rest of this family applies:
attendance is ``ON CONFLICT DO NOTHING`` on ``(tenant, subject, event)``, a
credit is refused twice by ``uq_point_ledger_entry_attendance_credit``,
registration is idempotent on its natural key, a redemption is matched on
``(subject, item)`` before it is opened — the partial
``uq_redemption_open_per_item`` index cannot do that alone, because it neither
sees a terminal row nor runs before the balance check — a reward item with
identical values is a verified repeat, and a meeting is matched on
``(unit, title)`` before it is written. A second run reports and changes
nothing.
"""

from __future__ import annotations

import argparse
import decimal
import sys
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Final
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from seed_demo_pipeline import resolve_tenant_id, resolve_unit_id
from seed_pilot import (
    SEED_PILOT_ADVISORY_LOCK_KEY,
    SeedConfigurationError,
    SeedConflictError,
    require_development_fixture_settings,
)
from seed_pilot_logins import ROLE_CREDENTIALS
from seed_pilot_principals import COMPOSE_DEV_PRINCIPALS
from seed_pilot_rewards import seed_reward_item
from smartmatch_api.config import Settings
from smartmatch_domain.events import DateOnlyTime
from smartmatch_domain.rewards import Redemption, RedemptionState
from smartmatch_domain.speaker_requests import SpeakerRequestDraft
from smartmatch_domain.synthetic_pilot import SYNTHETIC_ATTENDANCE_METHOD
from smartmatch_persistence import schema
from smartmatch_persistence.attendance import AttendanceRepository
from smartmatch_persistence.engine import create_session_factory
from smartmatch_persistence.event_registration import EventRegistrationRepository
from smartmatch_persistence.meetings import MeetingRepository
from smartmatch_persistence.rewards import AlreadyCreditedError, RewardsRepository
from smartmatch_persistence.speaker_requests import SpeakerRequestRepository
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

__all__ = [
    "DEFAULT_SUBJECT_SET",
    "FIXTURE_SUBJECT_SET",
    "LOGIN_SUBJECT_SET",
    "MEETINGS",
    "REDEMPTION_PLAN",
    "WORKSHEET_ITEMS",
    "EngagementReport",
    "MeetingPlan",
    "RedemptionStep",
    "SeedEngagementError",
    "WorksheetItem",
    "main",
    "seed_engagement",
    "subjects_for",
]

#: The pilot's zone, matching ``generate_pilot_dataset.PILOT_TIME_ZONE``. Stated
#: rather than imported because importing the generator would drag its whole
#: HTTP-driven module into an operator tool that makes no request.
PILOT_TIME_ZONE: Final[str] = "America/Los_Angeles"

# ---------------------------------------------------------------------------
# Whose accounts these rows are written under
# ---------------------------------------------------------------------------
#
# Two families of pilot account exist and only one of them can be signed in as
# from a browser. ``pilot-login-*`` are the accounts ``seed_pilot_logins``
# creates for the four ``@``-addressed credentials a reviewer types into the
# login form; ``compose-pilot-*`` are the accounts the local
# ``SMARTMATCH_DEV_PRINCIPALS`` bearer tokens resolve to.
#
# This tool defaulted to the *fixtures*, and that default was the defect. It
# fills the surfaces a person reads — an agenda, a balance, a redemption
# history, a filed request — and a person reads them after signing in. Writing
# them under a bearer-token fixture left ``student@`` and ``volunteer@`` looking
# at blank pages over a database this tool's own report called full.
#
# Neither list is restated here: they are the seeds that write the accounts, and
# a third copy would be the first to drift.

#: ``membership.role`` -> ``external_subject`` for the browser logins.
LOGIN_SUBJECT_SET: Final[Mapping[str, str]] = {
    entry.role: entry.subject for entry in ROLE_CREDENTIALS
}

#: ``membership.role`` -> ``external_subject`` for the compose bearer fixtures.
FIXTURE_SUBJECT_SET: Final[Mapping[str, str]] = {
    principal.role: principal.subject for principal in COMPOSE_DEV_PRINCIPALS
}

#: The selectable families, by the value ``--subjects`` takes.
SUBJECT_SETS: Final[Mapping[str, Mapping[str, str]]] = {
    "login": LOGIN_SUBJECT_SET,
    "fixture": FIXTURE_SUBJECT_SET,
}

#: The default, and the correction this module carries.
DEFAULT_SUBJECT_SET: Final[str] = "login"

#: The roles this tool writes under. Named so a family missing one is refused
#: at argument-parsing time rather than as a ``SeedEngagementError`` three
#: writes into a run.
REQUIRED_ROLES: Final[tuple[str, ...]] = ("student", "coordinator", "volunteer", "admin")


def subjects_for(
    name: str = DEFAULT_SUBJECT_SET, *, overrides: Mapping[str, str | None] | None = None
) -> Mapping[str, str]:
    """The ``role -> external_subject`` map for ``name``, with per-role overrides.

    An override of ``None`` means "not given" and leaves the family's own
    answer in place, so a caller can name one subject without restating the
    other three.

    Raises:
        SeedEngagementError: ``name`` is not a declared family, or the family
            has no account for a role this tool writes under. Both are refused
            rather than defaulted: silently falling back to the fixture accounts
            is the exact failure ``--subjects`` exists to end.
    """
    try:
        family = dict(SUBJECT_SETS[name])
    except KeyError:
        raise SeedEngagementError(
            f"unknown subject family {name!r}; choose one of {sorted(SUBJECT_SETS)}"
        ) from None
    for role, subject in (overrides or {}).items():
        if subject is not None:
            family[role] = subject
    missing = [role for role in REQUIRED_ROLES if not family.get(role)]
    if missing:
        raise SeedEngagementError(
            f"subject family {name!r} names no account for {missing}; pass the "
            "matching --*-subject flag or seed that login first"
        )
    return family


class SeedEngagementError(RuntimeError):
    """A precondition this tool refuses to invent its way past.

    Every instance names something that must already exist — a tenant, a unit, a
    seeded principal, a resolved event. None of them is something a seed of
    *engagement* rows is entitled to create: an account minted here would
    authenticate as nobody, and an event minted here would be a programme no
    coordinator entered.
    """


@dataclass(frozen=True, slots=True)
class WorksheetItem:
    """One row an owner has written into the rewards-catalog worksheet.

    Not a default catalog and not a proposal. These are the values already
    recorded in ``docs/pilot-data/rewards-catalog-worksheet.md``, transcribed so
    ``make seed-pilot-engagement`` can seed the catalog the worksheet describes
    in one call rather than five hand-typed ones. Changing a price means editing
    the worksheet row and this tuple together — which is the same discipline
    :func:`seed_pilot_rewards.seed_reward_item` enforces at the database, where a
    changed value on an existing name is a :class:`SeedConflictError` and never a
    silent update.

    Attributes:
        name: The item's display name, and half its idempotency key.
        points_cost: Whole events' worth of attendance, at
            ``POINTS_PER_VERIFIED_ATTENDANCE`` per event.
        fulfilment_cost: USD, recorded and never spent by any route.
        funded: D6's listability flag. One item is deliberately ``False``.
    """

    name: str
    points_cost: int
    fulfilment_cost: decimal.Decimal
    funded: bool


#: The worksheet's catalog table, transcribed. See that file for the reasoning
#: behind each cost; the short version is that the whole earn policy is 100
#: points per verified attendance and nothing else, so every cost here is a whole
#: number of attended events — 3, 6, 10, 15 and 25.
#:
#: The 300 row is the calibration floor: D7's property is
#: ``min(points_cost over listed items) <= N * points_per_event`` with ``N = 3``,
#: and this is the row that clears it. The 2500 row is unfunded on purpose, so
#: the seeded catalog also demonstrates that ``listable_items`` filters on
#: ``funded`` rather than merely claiming it does.
WORKSHEET_ITEMS: Final[tuple[WorksheetItem, ...]] = (
    WorksheetItem("Bronco Bookstore $10 Gift Card", 300, decimal.Decimal("10.00"), True),
    WorksheetItem("CBA Career Closet Voucher", 600, decimal.Decimal("35.00"), True),
    WorksheetItem("Professional Headshot Session", 1000, decimal.Decimal("60.00"), True),
    WorksheetItem("Lunch with a Visiting Executive Speaker", 1500, decimal.Decimal("45.00"), True),
    WorksheetItem("CBA Leadership Summit VIP Pass", 2500, decimal.Decimal("150.00"), False),
)


@dataclass(frozen=True, slots=True)
class RedemptionStep:
    """One redemption to open, and how far to carry it.

    Three rows in three different states, which is the point: a redemptions
    screen showing only ``requested`` rows demonstrates a queue, not a state
    machine. ``fulfilled`` is the only state that moves the balance, and it is
    reachable only through ``approved`` — the database's
    ``ck_redemption_approval_evidence`` refuses any other route, including a
    hand-written ``UPDATE``.

    Attributes:
        item_name: Which catalog row, by the name in :data:`WORKSHEET_ITEMS`.
        final_state: Where this redemption stops.
    """

    item_name: str
    final_state: RedemptionState


#: The student's redemption history, in the order it must be written.
#:
#: **The order is load-bearing and is not a style choice.**
#: :meth:`RewardsRepository.open_redemption` folds the balance and refuses a
#: request the balance does not cover, and a fulfilment debits it. So every
#: redemption is *opened* first, while the full attendance-derived balance is
#: still there, and only then are the approvals and the one fulfilment applied.
#: Opening after the debit would refuse the 1000-point row against a balance that
#: had just dropped to 900 — a correct refusal, and a pointlessly empty screen.
REDEMPTION_PLAN: Final[tuple[RedemptionStep, ...]] = (
    RedemptionStep("Bronco Bookstore $10 Gift Card", RedemptionState.FULFILLED),
    RedemptionStep("CBA Career Closet Voucher", RedemptionState.APPROVED),
    RedemptionStep("Professional Headshot Session", RedemptionState.REQUESTED),
)


@dataclass(frozen=True, slots=True)
class MeetingPlan:
    """One meeting with the CBA team, as a coordinator would have recorded it.

    ``days_ahead`` and ``hour`` are resolved into a real instant in
    :data:`PILOT_TIME_ZONE` before the write. ``cba_meeting.scheduled_at`` is
    ``NOT NULL`` with **no server default** — ADR-0010 rule 2, finding F-003, the
    legacy "thirty days from now" fabricated out of an unparsed date — so a
    meeting with no time is refused rather than defaulted, and this tool supplies
    a real one rather than relying on anything to fill it in.
    """

    title: str
    days_ahead: int
    hour: int
    location_or_link: str | None


#: Four meetings: two rooms, one link, one with nowhere named yet.
#:
#: The fourth carries ``location_or_link=None`` deliberately. NULL there means
#: *nobody has said yet*, and it is a state the column exists to hold — the
#: schema refuses ``''`` precisely so a blank string cannot become a second way
#: of saying it. A seeded set where every meeting has a room would leave that
#: distinction undemonstrated.
MEETINGS: Final[tuple[MeetingPlan, ...]] = (
    MeetingPlan("CBA speaker pipeline review — fall quarter", 4, 10, "Building 163, Room 1005"),
    MeetingPlan("Industry advisory board check-in", 11, 14, "Zoom — link in the calendar invite"),
    MeetingPlan("Alumni speaker outreach planning", 18, 9, "Building 94, Room 2012"),
    MeetingPlan("Spring career week programming sync", 32, 13, None),
)

#: How many attended events to credit the demo student with. Twelve events at
#: 100 points is 1,200, which covers the 300, 600 and 1000 rows at request time
#: and leaves 900 after the one fulfilment — enough to make the catalog's cheaper
#: half affordable and its top row visibly not.
STUDENT_ATTENDANCES: Final[int] = 12

#: How many future events to put on the student's agenda, and how many of those
#: to then cancel. The cancellation is not padding: OQ-CBA-018 settled that a
#: cancellation is a status transition and never a ``DELETE``, so a seeded set
#: with no cancelled row leaves the decision's whole point unexercised.
STUDENT_REGISTRATIONS: Final[int] = 4
STUDENT_CANCELLATIONS: Final[int] = 1


@dataclass(slots=True)
class EngagementReport:
    """What this run wrote, for the report :func:`main` prints."""

    reward_items_created: int = 0
    reward_items_verified: int = 0
    attendances: int = 0
    ledger_credits: int = 0
    registrations: int = 0
    cancellations: int = 0
    redemptions_opened: int = 0
    redemptions_advanced: int = 0
    redemptions_existing: int = 0
    meetings_created: int = 0
    meetings_existing: int = 0
    host_requests_filed: int = 0
    notes: list[str] = field(default_factory=list)

    def lines(self) -> tuple[str, ...]:
        """The counts, one per line, in the order they were written."""
        return (
            f"reward_item created={self.reward_items_created} "
            f"verified={self.reward_items_verified}",
            f"attendance_record written={self.attendances}",
            f"point_ledger_entry credits={self.ledger_credits}",
            f"event_registration registered={self.registrations} cancelled={self.cancellations}",
            f"redemption opened={self.redemptions_opened} "
            f"advanced={self.redemptions_advanced} existing={self.redemptions_existing}",
            f"cba_meeting created={self.meetings_created} existing={self.meetings_existing}",
            f"event (host-filed Speaker Request) filed={self.host_requests_filed}",
        )


def _subject_id(session: Session, *, tenant_id: uuid.UUID, subject: str) -> uuid.UUID:
    """Resolve one seeded principal's ``user_account.id``, or refuse.

    Refused rather than created, for :class:`SeedEngagementError`'s reason: an
    account minted here would carry no membership and no role, so it would
    authenticate as nobody and every row written under it would be invisible —
    which is the exact defect this tool exists to remove.
    """
    row = session.execute(
        sa.select(schema.user_account.c.id).where(
            schema.user_account.c.tenant_id == tenant_id,
            schema.user_account.c.external_subject == subject,
        )
    ).one_or_none()
    if row is None:
        raise SeedEngagementError(
            f"no user_account with external_subject {subject!r} in this tenant; run "
            "`make seed-pilot` and `make seed-pilot-principals` first. This tool will "
            "not create the account: one minted here would carry no membership, so "
            "every row written under it would be invisible to the person signing in."
        )
    return uuid.UUID(str(row.id))


def _resolved_event_ids(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    published_only: bool,
    limit: int,
) -> tuple[uuid.UUID, ...]:
    """Events this unit hosts whose date actually resolved, oldest first.

    ``time_precision != 'unresolved'`` is ADR-0010's line and not a convenience:
    an unresolved event has no instant, so attending it or holding a place at it
    are both statements about a date nobody has. ``published_only`` adds the
    predicate ``_published_event_or_404`` applies on the registration route, so
    a seeded registration is one the student could have made from the browse
    screen rather than one only a tool could reach.
    """
    criteria = [
        schema.event.c.tenant_id == tenant_id,
        schema.event.c.host_org_unit_id == unit_id,
        schema.event.c.time_precision != "unresolved",
    ]
    if published_only:
        criteria.append(schema.event.c.publication_status == "published")
    rows = session.execute(
        sa.select(schema.event.c.id)
        .where(*criteria)
        .order_by(schema.event.c.starts_at.asc().nulls_last(), schema.event.c.id.asc())
        .limit(limit)
    ).all()
    return tuple(uuid.UUID(str(row.id)) for row in rows)


def _seed_catalog(
    session: Session,
    *,
    tenant_slug: str,
    budget_owner_subject: str,
    report: EngagementReport,
) -> dict[str, uuid.UUID]:
    """Write the worksheet's catalog rows, and return their ids by name.

    Delegates every row to :func:`seed_pilot_rewards.seed_reward_item` rather
    than inserting one here, so there is one catalog writer and not two — and so
    a price changed in one place and not the other is the
    :class:`SeedConflictError` that function already raises, rather than a silent
    overwrite this tool invented.
    """
    ids: dict[str, uuid.UUID] = {}
    for item in WORKSHEET_ITEMS:
        outcome = seed_reward_item(
            session.connection(),
            tenant_slug=tenant_slug,
            name=item.name,
            points_cost=item.points_cost,
            fulfilment_cost=item.fulfilment_cost,
            budget_owner_subject=budget_owner_subject,
            funded=item.funded,
        )
        ids[item.name] = outcome.item_id
        if outcome.created:
            report.reward_items_created += 1
        else:
            report.reward_items_verified += 1
        if not outcome.satisfies_calibration:
            report.notes.append(
                f"{item.name!r} at {item.points_cost} points does NOT clear D7's tentative "
                "calibration property. That is deliberate — it is the catalog's stretch "
                "row — and D7 is tentative, so this is reported and never refused."
            )
    return ids


def _seed_student(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    student_id: uuid.UUID,
    report: EngagementReport,
) -> None:
    """Attendance, points, and an agenda — all under the demo student's account.

    Attendance is credited at the repository's own default rate; no figure of
    this tool's own is passed, for the reason ``generate_pilot_dataset`` gives
    about the same call. The credit is the *only* way points come into being
    (ADR-0013: "points derive from recorded attendance and nothing else"), so
    there is no branch here that grants a balance directly.
    """
    attendance = AttendanceRepository()
    rewards = RewardsRepository()
    registrations = EventRegistrationRepository()

    attended = _resolved_event_ids(
        session,
        tenant_id=tenant_id,
        unit_id=unit_id,
        published_only=False,
        limit=STUDENT_ATTENDANCES,
    )
    if not attended:
        raise SeedEngagementError(
            "this unit hosts no event with a resolved date, so there is nothing for a "
            "student to have attended. Run the dataset generator first."
        )

    for event_id in attended:
        outcome = attendance.record_attendance(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=student_id,
            event_id=event_id,
            method=SYNTHETIC_ATTENDANCE_METHOD,
        )
        if outcome.created:
            # The counter counts this run's writes, not its checks — on a
            # re-run the row already exists and the report must not claim it.
            report.attendances += 1
        attendance_id = outcome.attendance_id
        try:
            rewards.credit_attendance(session, tenant_id=tenant_id, attendance_id=attendance_id)
            report.ledger_credits += 1
        except AlreadyCreditedError:
            # The ordinary re-run path: migration 0019's partial unique index
            # already holds this attendance's one credit.
            pass

    # Registrations go to events the student has *not* attended, so the agenda
    # reads as a forward plan beside a history rather than as the same list
    # twice. Registration is the intent to attend and attendance is the fact of
    # it; migration 0026 keeps them separate precisely so they can disagree.
    wanted_total = STUDENT_REGISTRATIONS + STUDENT_CANCELLATIONS
    candidates = _resolved_event_ids(
        session,
        tenant_id=tenant_id,
        unit_id=unit_id,
        published_only=True,
        limit=STUDENT_ATTENDANCES + wanted_total,
    )
    already = set(attended)
    upcoming = [event_id for event_id in candidates if event_id not in already]
    if not upcoming:
        report.notes.append(
            "no published, resolved event remained that the demo student had not already "
            "attended, so no event_registration row was written. The agenda will show "
            "attendance only."
        )
        return

    wanted = upcoming[:wanted_total]

    # Reconcile, never blindly rewrite: on a re-run the places are already
    # held and the given-up ones already cancelled. Calling ``register`` on a
    # cancelled row would move it back to ``registered`` — a real write — so
    # the desired state per event is compared first, and the repository is
    # asked only when the row is not already there.
    existing_status: dict[uuid.UUID, str] = {
        uuid.UUID(str(row.event_id)): str(row.status)
        for row in session.execute(
            sa.select(
                schema.event_registration.c.event_id,
                schema.event_registration.c.status,
            ).where(
                schema.event_registration.c.tenant_id == tenant_id,
                schema.event_registration.c.subject_id == student_id,
                schema.event_registration.c.event_id.in_(wanted),
            )
        ).all()
    }

    kept = wanted[: len(wanted) - STUDENT_CANCELLATIONS]
    for event_id in kept:
        if existing_status.get(event_id) == "registered":
            continue
        if registrations.register(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=student_id,
            event_id=event_id,
        ).changed:
            report.registrations += 1

    for event_id in wanted[len(wanted) - STUDENT_CANCELLATIONS :]:
        status = existing_status.get(event_id)
        if status == "cancelled":
            continue
        # A cancellation needs a held place to give up: ``cancel`` writes no
        # row where none exists, so the registration is written first — the
        # same two-step shape the first run always takes.
        if (
            status is None
            and registrations.register(
                session,
                tenant_id=tenant_id,
                owning_unit_id=unit_id,
                subject_id=student_id,
                event_id=event_id,
            ).changed
        ):
            report.registrations += 1
        if registrations.cancel(
            session, tenant_id=tenant_id, subject_id=student_id, event_id=event_id
        ).changed:
            report.cancellations += 1
            report.registrations = max(report.registrations - 1, 0)


def _seed_redemptions(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    student_id: uuid.UUID,
    approver_id: uuid.UUID,
    item_ids: dict[str, uuid.UUID],
    report: EngagementReport,
) -> None:
    """Open every planned redemption first, then advance them — once.

    See :data:`REDEMPTION_PLAN` for why that order is required rather than tidy.
    ``actor_id`` is the coordinator on every hop that needs one: an approval, a
    fulfilment and a denial are all things a person does, and the schema refuses
    an approval with no author. An expiry would take none — time is not a person
    — and this plan contains no expiry for that reason, since a seeded one would
    have to name nobody and would read as a row missing its actor.

    A re-run does **not** go back through
    :meth:`RewardsRepository.open_redemption`. That method folds the balance and
    lets :func:`smartmatch_domain.rewards.request_redemption` refuse a cost the
    balance does not cover *before* the ``ON CONFLICT`` dedupe can return the
    in-flight row — so on an already-seeded tenant the 1000-point step would
    crash against the post-fulfilment balance instead of recognising its own
    earlier work. Nor can a step whose row already closed terminal be left to
    the index: ``uq_redemption_open_per_item`` is partial and never blocks one,
    so a second open would mint a duplicate and a second debit. The student's
    history is therefore read first, and each step is matched against it the
    way every other leg of this tool is: a row already at the planned state is
    a verified repeat, an in-flight one is carried the rest of the way, and a
    terminal one is a person's decision — never reopened, never doubled.
    """
    rewards = RewardsRepository()
    carried: list[tuple[RedemptionStep, Redemption]] = []

    priors_by_item: dict[uuid.UUID, list[Redemption]] = {}
    for prior in rewards.redemptions_for_subject(
        session, tenant_id=tenant_id, subject_id=student_id
    ):
        priors_by_item.setdefault(prior.item_id, []).append(prior)

    for step in REDEMPTION_PLAN:
        item_id = item_ids.get(step.item_name)
        if item_id is None:  # pragma: no cover - the catalog was just written
            raise SeedEngagementError(
                f"redemption plan names {step.item_name!r}, which is not in the seeded catalog"
            )

        priors = priors_by_item.get(item_id, [])
        if any(prior.state is step.final_state for prior in priors):
            # The ordinary re-run: this step's planned row is already on the
            # student's screen, whether it closed there or is still in flight.
            report.redemptions_existing += 1
            continue
        in_flight = next((prior for prior in priors if not prior.is_terminal), None)
        if in_flight is not None:
            # A first run that stopped partway: carry the in-flight row the
            # rest of the way rather than opening a second one — the partial
            # index would have handed this row back anyway.
            carried.append((step, in_flight))
            continue
        if priors:
            # Every prior is terminal and none is the planned state: a person
            # closed this history some other way. Re-requesting after a denial
            # is a student's act, not a seed's — and opening a duplicate of a
            # fulfilled row would debit the balance a second time.
            report.notes.append(
                f"the redemption for {step.item_name!r} already closed as "
                + "/".join(sorted({prior.state.value for prior in priors}))
                + f" and was not reopened toward {step.final_state.value}"
            )
            continue
        try:
            redemption = rewards.open_redemption(
                session, tenant_id=tenant_id, subject_id=student_id, item_id=item_id
            )
        except ValueError as exc:
            raise SeedEngagementError(
                f"cannot open the {step.item_name!r} redemption for the demo student: "
                f"{exc}. The student's folded balance must cover every planned request "
                "at open time — the attendance leg above is what writes those points, "
                "so a tenant too thin for the plan fails here rather than with a bare "
                "traceback."
            ) from exc
        report.redemptions_opened += 1
        carried.append((step, redemption))

    for step, redemption in carried:
        # Only the hops the plan still needs beyond where this row stands:
        # requested -> approved -> fulfilled is its whole shape, because
        # fulfilled is reachable through approval alone. A fresh open enters at
        # `requested`; a carried in-flight row enters wherever it stopped. A
        # plan asking for denial or expiry — a person's act, which this plan
        # never does — gets no transition at all and falls to the refusal
        # below rather than being approved on its way there.
        if redemption.state is RedemptionState.REQUESTED and step.final_state in (
            RedemptionState.APPROVED,
            RedemptionState.FULFILLED,
        ):
            redemption = rewards.transition_redemption(
                session,
                tenant_id=tenant_id,
                redemption_id=redemption.redemption_id,
                to_state=RedemptionState.APPROVED,
                actor_id=approver_id,
            )
            report.redemptions_advanced += 1
        if (
            redemption.state is RedemptionState.APPROVED
            and step.final_state is RedemptionState.FULFILLED
        ):
            redemption = rewards.transition_redemption(
                session,
                tenant_id=tenant_id,
                redemption_id=redemption.redemption_id,
                to_state=step.final_state,
                actor_id=approver_id,
            )
            report.redemptions_advanced += 1
        if redemption.state is not step.final_state:
            # A row ahead of the plan — approved where requested was wanted —
            # cannot be walked back, and walking it back would be a person's
            # decision undone by a seed. Refused with a sentence, not a
            # swallowed difference.
            raise SeedEngagementError(
                f"the existing redemption for {step.item_name!r} is "
                f"{redemption.state.value}, and the planned {step.final_state.value} "
                "cannot be reached from it"
            )


def _seed_meetings(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    created_by: uuid.UUID,
    report: EngagementReport,
) -> None:
    """Record the unit's meetings, skipping any whose title is already there.

    ``MeetingRepository`` has no upsert and should not grow one for a seed's
    convenience — two meetings with the same title on different dates are a
    legitimate thing for a unit to have. So idempotency is this tool's, on
    ``(unit, title)``, checked before the write.
    """
    meetings = MeetingRepository()
    zone = ZoneInfo(PILOT_TIME_ZONE)
    now = datetime.now(tz=UTC)

    for plan in MEETINGS:
        existing = session.execute(
            sa.select(schema.cba_meeting.c.id).where(
                schema.cba_meeting.c.tenant_id == tenant_id,
                schema.cba_meeting.c.owning_unit_id == unit_id,
                schema.cba_meeting.c.title == plan.title,
            )
        ).one_or_none()
        if existing is not None:
            report.meetings_existing += 1
            continue

        scheduled_at = (
            (now + timedelta(days=plan.days_ahead))
            .astimezone(zone)
            .replace(hour=plan.hour, minute=0, second=0, microsecond=0)
        )
        meetings.create(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            title=plan.title,
            scheduled_at=scheduled_at,
            time_zone=PILOT_TIME_ZONE,
            location_or_link=plan.location_or_link,
            created_by_user_id=created_by,
        )
        report.meetings_created += 1


def _host_request_targets(
    session: Session, *, tenant_id: uuid.UUID, unit_id: uuid.UUID
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The roster's own most common §7 sector and §8 role category.

    Taken from the seeded roster rather than hard-coded, for the reason
    ``generate_pilot_dataset.speaker_request_body`` gives about its own targets:
    a request naming a sector nobody holds scores every candidate the same
    defensible zero, and a shortlist drawn from that is tie-breaking wearing
    matching's clothes. The vocabulary is not this tool's to state either way —
    :class:`SpeakerRequestDraft` resolves both codes through the released
    taxonomies and raises if either is not in them.
    """

    def _most_common(column: sa.ColumnElement[str]) -> tuple[str, ...]:
        row = session.execute(
            sa.select(column, sa.func.count().label("n"))
            .where(
                schema.speaker_profile.c.tenant_id == tenant_id,
                schema.speaker_profile.c.owning_unit_id == unit_id,
                column.is_not(None),
            )
            .group_by(column)
            .order_by(sa.desc(sa.text("n")), column.asc())
            .limit(1)
        ).one_or_none()
        return () if row is None else (str(row[0]),)

    industries = _most_common(schema.speaker_profile.c.primary_industry_code)
    roles = _most_common(schema.speaker_profile.c.primary_role_code)
    return industries, roles


def _seed_host_request(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    host_id: uuid.UUID,
    report: EngagementReport,
) -> None:
    """File one Speaker Request **as the Event Host**, through the validator.

    The Event Host portal has exactly one read route and exactly one predicate
    on it: ``filed_by_user_id == principal.user_id``. Every request the generator
    files carries the coordinator's id, so that screen is empty however many
    requests the unit holds — the surface is not thin, it is unreachable by
    construction.

    Filed through :class:`SpeakerRequestDraft` and
    :meth:`SpeakerRequestRepository.file`, never by inserting
    ``speaker_request_classification`` directly: the draft is what enforces §7/§8's
    "at least one industry and one role" and §10's location rule, and a row minted
    around it would be the same class of half-valid data being removed.

    Virtual, for ``speaker_request_body``'s reason: the roster carries no postal
    code, so a physical request would put every candidate's distance in an honest
    unknown and produce a correct, useless refusal.
    """
    industries, roles = _host_request_targets(session, tenant_id=tenant_id, unit_id=unit_id)
    if not industries or not roles:
        report.notes.append(
            "no seeded speaker carries both a §7 sector and an §8 role category, so no "
            "host-filed Speaker Request was written and the Event Host portal stays "
            "empty. Run the dataset generator first."
        )
        return

    draft = SpeakerRequestDraft(
        title="Event Host request — first-year finance and analytics panel",
        event_time=DateOnlyTime(
            on_date=(datetime.now(tz=UTC) + timedelta(days=45)).date(),
            time_zone=PILOT_TIME_ZONE,
        ),
        is_virtual=True,
        industry_codes=industries,
        role_codes=roles,
        description=(
            "A virtual panel for students choosing between a first analyst role and a "
            "graduate programme: how people in these sectors and functions weigh an "
            "offer, what the first year actually looks like, and when to specialise."
        ),
    )
    result = SpeakerRequestRepository().file(
        session,
        tenant_id=tenant_id,
        host_org_unit_id=unit_id,
        draft=draft,
        filed_by_user_id=host_id,
    )
    if result.created:
        report.host_requests_filed += 1
    else:
        report.notes.append(
            "the host-filed Speaker Request already existed under its ADR-0012 identity "
            "key and was not refiled. NOTE: on a resubmission the *first* filer is kept "
            "(OQ-CBA-065), so if this request was originally filed by the coordinator it "
            "still will not appear on the Event Host's screen."
        )


def seed_engagement(
    session: Session,
    *,
    tenant_slug: str,
    unit_path: str,
    student_subject: str,
    coordinator_subject: str,
    host_subject: str,
    budget_owner_subject: str,
) -> EngagementReport:
    """Seed every engagement surface, under the demo accounts that read them.

    Order matters once: the catalog must exist before a redemption can reference
    it, and the student's attendance must be credited before a redemption can be
    afforded. Everything else is independent.

    Raises:
        SeedEngagementError: a tenant, unit, principal or resolved event that
            must already exist does not.
        SeedConflictError: a catalog row exists with different values —
            propagated from :func:`seed_pilot_rewards.seed_reward_item`.
    """
    report = EngagementReport()

    tenant_id = resolve_tenant_id(session, slug=tenant_slug)
    if tenant_id is None:
        raise SeedEngagementError(
            f"no tenant with slug {tenant_slug!r}; run `make seed-pilot` first"
        )
    unit_id = resolve_unit_id(session, tenant_id=tenant_id, path=unit_path)
    if unit_id is None:
        raise SeedEngagementError(
            f"no org_unit at path {unit_path!r} in tenant {tenant_slug!r}; run "
            "`make seed-pilot` first"
        )

    student_id = _subject_id(session, tenant_id=tenant_id, subject=student_subject)
    coordinator_id = _subject_id(session, tenant_id=tenant_id, subject=coordinator_subject)
    host_id = _subject_id(session, tenant_id=tenant_id, subject=host_subject)

    item_ids = _seed_catalog(
        session,
        tenant_slug=tenant_slug,
        budget_owner_subject=budget_owner_subject,
        report=report,
    )
    _seed_student(
        session, tenant_id=tenant_id, unit_id=unit_id, student_id=student_id, report=report
    )
    _seed_redemptions(
        session,
        tenant_id=tenant_id,
        student_id=student_id,
        approver_id=coordinator_id,
        item_ids=item_ids,
        report=report,
    )
    _seed_meetings(
        session, tenant_id=tenant_id, unit_id=unit_id, created_by=coordinator_id, report=report
    )
    _seed_host_request(
        session, tenant_id=tenant_id, unit_id=unit_id, host_id=host_id, report=report
    )

    report.notes.append(
        "the generator's point_ledger_entry rows under synthetic-student:* accounts "
        "are NOT touched by this tool. They are a real, correctly-derived ledger for "
        "students who are not the demo login, and re-pointing them would rewrite whose "
        "attendance produced which credit. The demo student's balance above is its own, "
        "derived from its own attendance."
    )
    return report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-slug", default="pilot", help="Synthetic tenant slug")
    parser.add_argument("--unit-path", default="pilot", help="ltree path owning the dataset")
    parser.add_argument(
        "--subjects",
        choices=sorted(SUBJECT_SETS),
        default=DEFAULT_SUBJECT_SET,
        help=(
            "Which family of account these rows are written under. 'login' (the "
            "default) is the four pilot-login-* accounts a reviewer signs in as at "
            "POST /v1/auth/login; 'fixture' is the compose-pilot-* accounts the local "
            "SMARTMATCH_DEV_PRINCIPALS bearer tokens resolve to, for a stack driven by "
            "tokens and no browser. The four --*-subject flags below override one "
            "member of the chosen family each."
        ),
    )
    parser.add_argument(
        "--student-subject",
        default=None,
        help=(
            "external_subject the student portal's login resolves to "
            "(default: the chosen family's student)"
        ),
    )
    parser.add_argument(
        "--coordinator-subject",
        default=None,
        help=(
            "external_subject that records meetings and decides redemptions "
            "(default: the chosen family's coordinator)"
        ),
    )
    parser.add_argument(
        "--host-subject",
        default=None,
        help=(
            "external_subject the Event Host portal's login resolves to "
            "(default: the chosen family's volunteer)"
        ),
    )
    parser.add_argument(
        "--budget-owner-subject",
        default=None,
        help=(
            "external_subject of the catalog's budget owner, from the worksheet "
            "(default: the chosen family's admin)"
        ),
    )
    parser.add_argument(
        "--items-from-worksheet",
        action="store_true",
        required=True,
        help=(
            "Seed the catalog rows transcribed from "
            "docs/pilot-data/rewards-catalog-worksheet.md. Required, and there is no "
            "other catalog source: this flag is how an operator states that the "
            "worksheet rows are the ones they mean."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Seed, report, and exit non-zero on any refusal.

    Three distinguishable exits, matching the rest of this family: ``2`` for a
    configuration or precondition refusal, ``1`` for a database failure, ``0``
    for a run whose report is printed either way.
    """
    args = parse_args(argv)
    try:
        settings = require_development_fixture_settings(Settings())
    except SeedConfigurationError as exc:
        print(f"seed-pilot-engagement: configuration error: {exc}", file=sys.stderr)
        return 2

    try:
        chosen = subjects_for(
            args.subjects,
            overrides={
                "student": args.student_subject,
                "coordinator": args.coordinator_subject,
                "volunteer": args.host_subject,
                "admin": args.budget_owner_subject,
            },
        )
    except SeedEngagementError as exc:
        print(f"seed-pilot-engagement: {exc}", file=sys.stderr)
        return 2
    print(
        f"seed-pilot-engagement: writing under the {args.subjects!r} accounts: "
        + ", ".join(f"{role}={chosen[role]}" for role in REQUIRED_ROLES)
    )

    session_factory = create_session_factory(settings.database_url)
    with session_factory() as session:
        try:
            session.execute(
                sa.text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": SEED_PILOT_ADVISORY_LOCK_KEY},
            )
            report = seed_engagement(
                session,
                tenant_slug=args.tenant_slug,
                unit_path=args.unit_path,
                student_subject=chosen["student"],
                coordinator_subject=chosen["coordinator"],
                host_subject=chosen["volunteer"],
                budget_owner_subject=chosen["admin"],
            )
            session.commit()
        except (SeedEngagementError, SeedConflictError, SeedConfigurationError) as exc:
            session.rollback()
            print(f"seed-pilot-engagement: {exc}", file=sys.stderr)
            return 2
        except SQLAlchemyError as exc:
            session.rollback()
            print(
                "seed-pilot-engagement: database operation failed; run `make migrate` "
                f"against the target database first: {exc}",
                file=sys.stderr,
            )
            return 1

    print("seed-pilot-engagement: done.")
    for line in report.lines():
        print(f"  {line}")
    for note in report.notes:
        print(f"  NOTE: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
