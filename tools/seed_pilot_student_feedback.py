#!/usr/bin/env python3
"""Rate speakers as the demo student, through the student's own route.

The last empty table on an already-generated pilot tenant, and the one that
cannot be filled by writing rows. ``student_speaker_feedback`` is the surface
the whole of MM-A01 is about: ``routers/student_speaker_feedback.py`` takes
``student_id`` from the verified principal and from nowhere else, so there is no
request field a caller could put somebody else's id in. A seeder that inserted
rows through a repository would exercise none of that — not the attendance
check, not the roster check, not the seven-day edit window — and would leave the
one structural guarantee the surface exists for undemonstrated.

So every rating here is a ``POST`` the student's own bearer token made, exactly
as ``generate_pilot_dataset``'s Phase C does for its synthetic cohort. The
difference is whose token, and it is the point of this file: Phase C mints eight
``SMARTMATCH_DEV_PRINCIPALS`` fixtures that no browser can sign in as, and the
compose ``dataset`` one-shot therefore runs with ``--feedback-students 0`` and
skips the phase entirely. This tool signs in as the **login** student —
``student@`` — with ``POST /v1/auth/login``, so the rows land on the account a
reviewer opens the portal with.

## The password

Read from the environment and from nowhere else. ``SMARTMATCH_PILOT_STUDENT_EMAIL``
and ``SMARTMATCH_PILOT_STUDENT_PASSWORD`` are the same two variables
``tools/seed_pilot_logins.py`` created the account from, so there is one place a
pilot credential is written down and this tool is not a second one. Neither has
a default; a missing one is a refusal naming the variable, never an invented
password and never a literal in this file.

## What it must arrange first

``StudentSpeakerFeedbackRepository.eligibility`` asks three questions, and a
``403`` or ``409`` is each one's answer:

* **Attendance.** There must be an ``attendance_record`` for this student at
  this event. The student's *history* — what ``seed-pilot-engagement`` credits
  — is the unit's oldest events, whose feedback windows closed months ago, so
  this tool records attendance at the events that are still open. Through
  ``AttendanceRepository`` with ``SYNTHETIC_ATTENDANCE_METHOD``, the same
  writer and the same method every other synthetic attendance in this tree uses.
* **The roster.** The speaker must hold a ``speaker_profile`` on this unit.
  Rather than pick one, this tool asks which speakers the pipeline already has
  *confirmed* at that event, and rates those: a rating of somebody who never
  spoke there is a connected-looking row that means nothing. It falls back to
  the unit roster only if no journey reached ``confirmed`` for the event, and
  says so in the report.
* **The window.** Seven days from the event's anchor, which for a date-only
  event is midnight UTC at the end of that day — not the event's own zone. The
  anchor is computed by :func:`~smartmatch_domain.student_speaker_feedback.feedback_anchor`
  and the state by ``resolve_edit_window``, imported rather than reimplemented,
  because "the date plus seven" is right most of the time and wrong exactly when
  it matters.

Events whose window is ``UNKNOWN`` — ADR-0010 unresolved, no anchor to have
closed — are deliberately not used: OQ-CBA-052 is open on what a rating of an
undated event means, and a seeder writing rows into an open question would be
answering it in code.

## Ratings

The scale is the domain's (:class:`~smartmatch_domain.student_speaker_feedback.Rating`),
and the values are spread rather than uniform so the portal shows a spread. No
comment is ever sent: a sentence attributed to a student nobody asked is a
quotation nobody said, and this tool has no business writing one.

## The cohort leg (``--cohort``)

The login leg fills one student's history, and one student can never make a
per-speaker aggregate publish: ``aggregate_speaker_feedback`` withholds both the
mean and the count below three **distinct** submitted responses. On a tenant
where the same two roster speakers are the only ones rateable, that is why the
Speakers page shows a single published number beside a column of "not enough
responses yet" — the privacy rule working exactly as designed on a dataset too
thin to show it working.

``--cohort`` runs a second leg that fixes the thinness rather than the rule.
It mints the eight ``synthetic-pilot-feedback-student-NN`` accounts
``generate_pilot_dataset``'s Phase C writes — the same deterministic
``student_subject_id`` derivation, so the two tools land on the same accounts
when both run — gives each a ``student`` membership on this unit, records their
attendance at every open-window event that has pipeline-confirmed speakers, and
posts one rating per ``pilot_dataset_plan.build_speaker_feedback`` plan entry,
each POST authenticated with that student's own dev bearer token
(``pilot-feedback-NN``). Because each confirmed speaker appears at one event,
the publish threshold needs several *students*, and this cohort is the designed
source of them.

Two conditions it cannot arrange itself, and refuses past rather than around:

* **The tokens.** ``pilot-feedback-NN`` must be in the API process's
  ``SMARTMATCH_DEV_PRINCIPALS`` *before it boots* — the map is read once at
  startup. ``pilot_dataset_plan.feedback_dev_principals()`` builds the fragment
  and ``scripts/reset_pilot_dataset.sh`` merges it there; a compose stack needs
  the same entries on the api service's environment and a recreated container.
  The leg probes ``GET /v1/me`` with the first token once that account exists
  and refuses on a ``401`` rather than posting fifty requests into a wall.
* **Confirmed speakers.** Unlike the login leg there is no roster fallback: an
  open event with no journey at ``confirmed`` is skipped, because the cohort
  exists to spread ratings across speakers who *spoke*, and eight students
  rating roster members nobody confirmed would manufacture exactly the
  connected-looking nothing the fallback already risks.

The plan is the plan module's own: ``COHORT_RESPONSE_SHAPE`` gives each
(event, speaker) pair a posted-response count — most at or above the publish
threshold and a couple deliberately below it — and ``build_speaker_feedback``
draws which students stay silent (about a quarter, per
``FEEDBACK_WITHHELD_SHARE``) and what the rest rate, seeded so a re-run posts
the same values and the route answers ``200``.

## Rerunning it

Idempotent. Attendance is ``ON CONFLICT DO NOTHING`` on
``(tenant, subject, event)``; the rating's natural key is
``(tenant, student, event, speaker)``, so a second submission is an edit of the
caller's own rating and the route answers ``200`` rather than ``201``. Both are
success and the report distinguishes them. The cohort accounts are
``ensure_account`` upserts and their memberships insert-or-verify, so the whole
leg is safe to run twice.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

import sqlalchemy as sa
from generate_pilot_dataset import FEEDBACK_PACE_SECONDS, student_subject_id
from pilot_dataset_plan import (
    FEEDBACK_STUDENT_COUNT,
    build_speaker_feedback,
    feedback_plan_summary,
    feedback_student_external_subject,
    feedback_student_token,
)
from seed_demo_pipeline import resolve_tenant_id, resolve_unit_id
from seed_pilot import (
    SEED_PILOT_ADVISORY_LOCK_KEY,
    SeedConfigurationError,
    _existing_or_insert_membership,
    require_development_fixture_settings,
)
from seed_pilot_engagement import DEFAULT_SUBJECT_SET, SUBJECT_SETS, SeedEngagementError
from smartmatch_api.config import Settings
from smartmatch_domain.student_speaker_feedback import (
    MIN_RESPONSES_FOR_AGGREGATE,
    EditWindowState,
    feedback_anchor,
    resolve_edit_window,
)
from smartmatch_domain.synthetic_pilot import SYNTHETIC_ATTENDANCE_METHOD
from smartmatch_persistence import schema
from smartmatch_persistence.attendance import AttendanceRepository
from smartmatch_persistence.engine import create_session_factory
from smartmatch_persistence.professionals import ProfessionalIdentityRepository
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

__all__ = [
    "COHORT_MAX_EVENTS",
    "COHORT_MAX_SPEAKERS_PER_EVENT",
    "COHORT_RESPONSE_SHAPE",
    "EMAIL_VARIABLE",
    "PASSWORD_VARIABLE",
    "RATING_CYCLE",
    "FeedbackReport",
    "OpenEvent",
    "SeedFeedbackError",
    "cohort_events",
    "login",
    "main",
    "open_window_events",
    "seed_feedback_cohort",
    "seed_student_feedback",
]

#: The two variables the student login was created from, and the only source of
#: its password. Named rather than defaulted, for the reason
#: ``seed_pilot_logins`` gives about the same pair: a default password in a file
#: is a credential in a file.
EMAIL_VARIABLE: Final[str] = "SMARTMATCH_PILOT_STUDENT_EMAIL"
PASSWORD_VARIABLE: Final[str] = "SMARTMATCH_PILOT_STUDENT_PASSWORD"

#: The ratings this tool cycles through, in order.
#:
#: Spread rather than uniform, and not centred: a portal showing five identical
#: fours demonstrates a form, not an opinion. The values are within the domain's
#: scale and the domain validates them; this tuple chooses no bound of its own.
RATING_CYCLE: Final[tuple[int, ...]] = (5, 4, 5, 3, 4)

#: How many open-window events to rate at, at most. Small on purpose: the window
#: is seven days wide and a generated calendar has two or three events inside
#: it, so a larger number would silently mean "all of them" and read as a target
#: this tool had missed.
MAX_EVENTS: Final[int] = 3

#: How many speakers to rate at each event, at most.
MAX_SPEAKERS_PER_EVENT: Final[int] = 2

#: How many open-window events the cohort leg rates across, at most, and how
#: many confirmed speakers it rates at each. Wider than the login leg's bounds
#: because the cohort's purpose is breadth: the Speakers page needs several
#: published aggregates to demonstrate anything, and a generated calendar has
#: two or three confirmed journeys per open event.
COHORT_MAX_EVENTS: Final[int] = 6
COHORT_MAX_SPEAKERS_PER_EVENT: Final[int] = 3

#: How many ratings each (event, speaker) pair receives, in pair order —
#: newest event first — cycled when there are more pairs than entries.
#:
#: Counts, not scores: which of the eight cohort students stay silent (about a
#: quarter, per ``FEEDBACK_WITHHELD_SHARE``) and what the rest rate is
#: ``build_speaker_feedback``'s seeded draw. The shape is what the two surfaces
#: the demo walks both need: entries at or above the domain's three-response
#: publish threshold produce visible per-speaker means at several different
#: values, and the trailing entries below it leave those speakers reading "not
#: enough responses yet", which is the state the page exists to distinguish
#: from a zero. The widest entry needs all eight students —
#: ``round(6 / 0.75)`` opportunities — so no entry may exceed 6 without
#: raising ``FEEDBACK_STUDENT_COUNT`` too.
COHORT_RESPONSE_SHAPE: Final[tuple[int, ...]] = (6, 5, 4, 3, 3, 3, 3, 3, 3, 3, 2, 1)


class SeedFeedbackError(RuntimeError):
    """A precondition this tool refuses to invent its way past.

    A missing credential, an API that answered something other than success, a
    tenant with no open feedback window. None of them is something a seeder of
    *ratings* may work around: a rating written around the route's checks is the
    defect the route exists to prevent.
    """


@dataclass(frozen=True, slots=True)
class OpenEvent:
    """One event whose seven-day feedback window is still open."""

    event_id: uuid.UUID
    title: str
    speaker_ids: tuple[uuid.UUID, ...]
    speakers_confirmed: bool


@dataclass(slots=True)
class FeedbackReport:
    """What this run did, for the report :func:`main` prints.

    The ``cohort_*`` fields belong to the ``--cohort`` leg; ``cohort_ran``
    rather than a nonzero count gates their display, because a leg that ran
    and posted nothing still has something to say.
    """

    events_open: int = 0
    attendances_recorded: int = 0
    ratings_created: int = 0
    ratings_amended: int = 0
    cohort_ran: bool = False
    cohort_events: int = 0
    cohort_events_skipped: int = 0
    cohort_students: int = 0
    cohort_attendances: int = 0
    cohort_ratings_created: int = 0
    cohort_ratings_amended: int = 0
    cohort_ratings_withheld: int = 0
    cohort_speakers_rated: int = 0
    speakers_publishing: int = 0
    speakers_below_threshold: int = 0
    notes: list[str] = field(default_factory=list)

    def lines(self) -> tuple[str, ...]:
        """The counts, one per line, in the order they happened."""
        lines = [
            f"events with an open feedback window   {self.events_open}",
            f"attendance_record written             {self.attendances_recorded}",
            f"student_speaker_feedback created      {self.ratings_created}",
            f"student_speaker_feedback amended      {self.ratings_amended} (re-run)",
        ]
        if self.cohort_ran:
            lines += [
                f"cohort events rated                 {self.cohort_events}",
                f"cohort events skipped (no confirmed speaker) {self.cohort_events_skipped}",
                f"cohort students ensured             {self.cohort_students}",
                f"cohort attendance_record written    {self.cohort_attendances}",
                f"cohort ratings created              {self.cohort_ratings_created}",
                f"cohort ratings amended              {self.cohort_ratings_amended} (re-run)",
                f"cohort ratings withheld by plan     {self.cohort_ratings_withheld}",
                f"speakers now publishing (>=3 responses)   {self.speakers_publishing}",
                f"speakers rated but below the line   {self.speakers_below_threshold}",
            ]
        return tuple(lines)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def _request(
    *,
    method: str,
    url: str,
    body: Mapping[str, Any] | None = None,
    bearer_token: str | None = None,
    timeout: float = 30.0,
) -> tuple[int, Any]:
    """Issue one request, returning its status and decoded body.

    A ``4xx``/``5xx`` is returned rather than raised, for the reason
    ``generate_pilot_dataset._request`` gives: a ``200`` on a resubmitted rating
    is the ordinary re-run path, and a helper that raised on every non-2xx would
    make each caller catch and re-inspect an exception to tell those apart.
    """
    headers = {"Content-Type": "application/json"}
    if bearer_token is not None:
        headers["Authorization"] = f"Bearer {bearer_token}"
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url=url, data=payload, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return int(response.status), (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return int(exc.code), json.loads(raw)
        except json.JSONDecodeError:
            return int(exc.code), {"raw": raw[:400]}
    except urllib.error.URLError as exc:
        raise SeedFeedbackError(f"could not reach {url}: {exc.reason}") from exc


def login(*, api_base: str, environ: Mapping[str, str] | None = None) -> str:
    """Sign in as the pilot student and return the opaque session token.

    The credential comes from :data:`EMAIL_VARIABLE` and
    :data:`PASSWORD_VARIABLE` and from nowhere else. There is no default and no
    literal: the account was created from those two variables by
    ``make seed-pilot-logins``, so reading them here keeps one place where a
    pilot password is written down.

    The token is opaque and encodes nothing — ``LoginResponse`` deliberately
    carries no identity — so this function returns it and asks ``/v1/me``
    nothing. Who the token is, is the server's answer to give.

    Raises:
        SeedFeedbackError: a variable is unset, or the API refused the sign-in.
    """
    source = os.environ if environ is None else environ
    email = source.get(EMAIL_VARIABLE, "").strip()
    password = source.get(PASSWORD_VARIABLE, "")
    if not email or not password:
        missing = [
            name
            for name, value in ((EMAIL_VARIABLE, email), (PASSWORD_VARIABLE, password))
            if not value
        ]
        raise SeedFeedbackError(
            f"{' and '.join(missing)} is not set. This tool signs in as the pilot "
            "student and reads its credential from the same two variables "
            "`make seed-pilot-logins` created the account from; it invents no password "
            "and carries no default. Export them (they are in .env.example) and re-run."
        )

    status, payload = _request(
        method="POST",
        url=f"{api_base}/v1/auth/login",
        body={"email": email, "password": password},
    )
    if status != 200 or not isinstance(payload, dict) or not payload.get("access_token"):
        raise SeedFeedbackError(
            f"POST {api_base}/v1/auth/login answered {status} for {email}: {payload}. "
            "A 401 means the stored credential does not match "
            f"{PASSWORD_VARIABLE}; run `make seed-pilot-logins` against this database "
            "with the same variables set."
        )
    return str(payload["access_token"])


# ---------------------------------------------------------------------------
# What is rateable, and by whom
# ---------------------------------------------------------------------------


def _window_state(
    *,
    time_precision: str,
    starts_at: datetime | None,
    ends_at: datetime | None,
    on_date: Any,
    now: datetime,
) -> EditWindowState:
    """Where one event sits in the seven-day window, by the domain's own rule.

    ``feedback_anchor`` and ``resolve_edit_window`` are imported and called
    rather than reimplemented, for ``generate_pilot_dataset.feedback_window_state``'s
    reason: for a date-only event the anchor is midnight at the *end* of that
    day in **UTC**, the event's own time zone deliberately ignored, and a tool
    that guessed would be right most of the time and would silently produce a
    run the API refuses with ``409``.
    """
    anchor = feedback_anchor(
        time_precision=time_precision,
        starts_at=starts_at,
        ends_at=ends_at,
        on_date=on_date if time_precision == "date_only" else None,
    )
    return resolve_edit_window(anchor=anchor, now=now).state


def _confirmed_speakers(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    event_id: uuid.UUID,
    limit: int = MAX_SPEAKERS_PER_EVENT,
) -> tuple[uuid.UUID, ...]:
    """Professionals a pipeline journey confirmed at this event, roster-checked.

    Asked of ``pipeline_record`` rather than chosen from the roster, because a
    rating is a statement about somebody who spoke. The ``speaker_profile`` join
    is not belt-and-braces: ``pipeline_record.subject_id`` is a professional and
    the route's roster check is on ``speaker_profile``, so a confirmed journey
    for somebody with no profile on this unit would be a ``403`` several calls
    later rather than an empty list now.

    Ordered by ``confirmed_at`` with a ``subject_id`` tiebreak: several journeys
    can share one confirmation instant, and which speakers the ``limit`` keeps
    must not drift between runs — the same pairs must be planned each time or a
    re-run would post different ratings under different students instead of
    amending the ones it already wrote.
    """
    rows = session.execute(
        sa.select(schema.pipeline_record.c.subject_id)
        .join(
            schema.speaker_profile,
            sa.and_(
                schema.speaker_profile.c.tenant_id == schema.pipeline_record.c.tenant_id,
                schema.speaker_profile.c.professional_id == schema.pipeline_record.c.subject_id,
                schema.speaker_profile.c.owning_unit_id == unit_id,
            ),
        )
        .where(
            schema.pipeline_record.c.tenant_id == tenant_id,
            schema.pipeline_record.c.owning_unit_id == unit_id,
            schema.pipeline_record.c.opportunity_event_id == event_id,
            schema.pipeline_record.c.confirmed_at.is_not(None),
        )
        .order_by(
            schema.pipeline_record.c.confirmed_at.asc(),
            schema.pipeline_record.c.subject_id.asc(),
        )
        .limit(limit)
    ).all()
    return tuple(uuid.UUID(str(row.subject_id)) for row in rows)


def _roster_speakers(
    session: Session, *, tenant_id: uuid.UUID, unit_id: uuid.UUID
) -> tuple[uuid.UUID, ...]:
    """The unit's §13 roster, oldest first. The fallback, never the first choice."""
    rows = session.execute(
        sa.select(schema.speaker_profile.c.professional_id)
        .where(
            schema.speaker_profile.c.tenant_id == tenant_id,
            schema.speaker_profile.c.owning_unit_id == unit_id,
        )
        .order_by(schema.speaker_profile.c.created_at.asc())
        .limit(MAX_SPEAKERS_PER_EVENT)
    ).all()
    return tuple(uuid.UUID(str(row.professional_id)) for row in rows)


def _iter_open_events(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    now: datetime,
    speakers_per_event: int,
) -> Iterator[tuple[uuid.UUID, str, tuple[uuid.UUID, ...]]]:
    """Yield ``(event_id, title, confirmed speaker ids)`` per open-window event.

    Only events whose window is genuinely ``OPEN``. ``CLOSED`` events answer
    ``409`` and most of a generated calendar is closed, which is the calendar
    being honest rather than a defect. ``UNKNOWN`` — an ADR-0010 unresolved
    event with no anchor — is writable and deliberately unused: OQ-CBA-052 is
    open on what a rating of an undated event means.

    Newest first by ``on_date`` (with an id tiebreak), which is the order the
    rating plan indexes, so a re-run pairs the same speakers with the same
    plan entries and amends rather than rewrites.
    """
    rows = session.execute(
        sa.select(
            schema.event.c.id,
            schema.event.c.title,
            schema.event.c.time_precision,
            schema.event.c.starts_at,
            schema.event.c.ends_at,
            schema.event.c.on_date,
        )
        .where(
            schema.event.c.tenant_id == tenant_id,
            schema.event.c.host_org_unit_id == unit_id,
            schema.event.c.time_precision != "unresolved",
        )
        .order_by(schema.event.c.on_date.desc().nulls_last(), schema.event.c.id.asc())
    ).all()

    for row in rows:
        state = _window_state(
            time_precision=str(row.time_precision),
            starts_at=row.starts_at,
            ends_at=row.ends_at,
            on_date=row.on_date,
            now=now,
        )
        if state is not EditWindowState.OPEN:
            continue
        event_id = uuid.UUID(str(row.id))
        confirmed = _confirmed_speakers(
            session,
            tenant_id=tenant_id,
            unit_id=unit_id,
            event_id=event_id,
            limit=speakers_per_event,
        )
        yield event_id, str(row.title), confirmed


def open_window_events(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    now: datetime,
    limit: int = MAX_EVENTS,
    report: FeedbackReport | None = None,
) -> tuple[OpenEvent, ...]:
    """The unit's events a rating can still be written against, newest first.

    See :func:`_iter_open_events` for the window rule. Speakers are the
    pipeline-confirmed ones where a journey reached ``confirmed``, and the
    unit's roster otherwise — the fallback that keeps the demo student's own
    history writable on a calendar with no confirmed journeys.
    """
    chosen: list[OpenEvent] = []
    for event_id, title, confirmed in _iter_open_events(
        session,
        tenant_id=tenant_id,
        unit_id=unit_id,
        now=now,
        speakers_per_event=MAX_SPEAKERS_PER_EVENT,
    ):
        speakers = confirmed or _roster_speakers(session, tenant_id=tenant_id, unit_id=unit_id)
        if not speakers:
            continue
        chosen.append(
            OpenEvent(
                event_id=event_id,
                title=title,
                speaker_ids=speakers,
                speakers_confirmed=bool(confirmed),
            )
        )
        if len(chosen) == limit:
            break

    if report is not None and chosen and not all(e.speakers_confirmed for e in chosen):
        report.notes.append(
            "at least one rated event had no pipeline journey at 'confirmed', so this "
            "tool rated speakers from the unit's roster instead. The rating is real and "
            "the route accepted it; it is not evidence that that speaker spoke there."
        )
    return tuple(chosen)


def cohort_events(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    now: datetime,
    limit: int = COHORT_MAX_EVENTS,
) -> tuple[tuple[OpenEvent, ...], int]:
    """The open-window events with pipeline-confirmed speakers, newest first.

    Deliberately *not* :func:`open_window_events`'s roster fallback: the cohort
    exists to put several students' ratings behind speakers who actually spoke,
    and a roster pick nobody confirmed would manufacture the connected-looking
    nothing the fallback already risks.

    Returns the chosen events plus how many open events were skipped for
    holding no confirmed speaker — reported, because "open but unrated" is a
    fact about the calendar a reader of the report should not have to infer.
    """
    chosen: list[OpenEvent] = []
    skipped = 0
    for event_id, title, confirmed in _iter_open_events(
        session,
        tenant_id=tenant_id,
        unit_id=unit_id,
        now=now,
        speakers_per_event=COHORT_MAX_SPEAKERS_PER_EVENT,
    ):
        if not confirmed:
            skipped += 1
        elif len(chosen) < limit:
            chosen.append(
                OpenEvent(
                    event_id=event_id,
                    title=title,
                    speaker_ids=confirmed,
                    speakers_confirmed=True,
                )
            )
    return tuple(chosen), skipped


def _subject_id(session: Session, *, tenant_id: uuid.UUID, subject: str) -> uuid.UUID:
    """Resolve the student's ``user_account.id``, or refuse.

    Refused rather than created, for ``seed_pilot_engagement._subject_id``'s
    reason: an account minted here would carry no membership and no credential,
    so nothing could sign in as it and every row written under it would be
    invisible.
    """
    row = session.execute(
        sa.select(schema.user_account.c.id).where(
            schema.user_account.c.tenant_id == tenant_id,
            schema.user_account.c.external_subject == subject,
        )
    ).one_or_none()
    if row is None:
        raise SeedFeedbackError(
            f"no user_account with external_subject {subject!r} in this tenant; run "
            "`make seed-pilot-logins` first. This tool will not create the account."
        )
    return uuid.UUID(str(row.id))


def seed_student_feedback(
    session: Session,
    *,
    api_base: str,
    bearer_token: str,
    tenant_slug: str,
    unit_path: str,
    student_subject: str,
    now: datetime | None = None,
) -> FeedbackReport:
    """Record the attendance the route requires, then post the ratings.

    Two writers on purpose. Attendance is a repository write because no
    caller-facing writer for it exists; the rating is an HTTP call because one
    does, and because it is the call whose refusals are the surface's whole
    point. The attendance is committed before the first ``POST``: the route
    reads it in a different session, and a rating posted against an uncommitted
    attendance is a ``403`` this tool caused itself.
    """
    report = FeedbackReport()
    moment = datetime.now(tz=UTC) if now is None else now

    tenant_id = resolve_tenant_id(session, slug=tenant_slug)
    if tenant_id is None:
        raise SeedFeedbackError(f"no tenant with slug {tenant_slug!r}; run `make seed-pilot`")
    unit_id = resolve_unit_id(session, tenant_id=tenant_id, path=unit_path)
    if unit_id is None:
        raise SeedFeedbackError(
            f"no org_unit at path {unit_path!r} in tenant {tenant_slug!r}; run `make seed-pilot`"
        )
    student_id = _subject_id(session, tenant_id=tenant_id, subject=student_subject)

    events = open_window_events(
        session, tenant_id=tenant_id, unit_id=unit_id, now=moment, report=report
    )
    if not events:
        raise SeedFeedbackError(
            "no event in this unit has an open feedback window, so no rating can be "
            "written through the student route. The window is seven days wide and the "
            "generated calendar is built from a fixed CALENDAR_ANCHOR in "
            "tools/pilot_dataset_plan.py; once that literal is more than a week past, "
            "every generated event is closed. Move the anchor and regenerate — do not "
            "widen the window, which is a ratified decision."
        )
    report.events_open = len(events)

    attendance = AttendanceRepository()
    for event in events:
        if attendance.record_attendance(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=student_id,
            event_id=event.event_id,
            method=SYNTHETIC_ATTENDANCE_METHOD,
        ).created:
            # The counter counts this run's writes, not its checks — on a
            # re-run the row already exists and the report must not claim it.
            report.attendances_recorded += 1
    session.commit()

    index = 0
    for event in events:
        for speaker_id in event.speaker_ids:
            rating = RATING_CYCLE[index % len(RATING_CYCLE)]
            index += 1
            status, payload = _request(
                method="POST",
                url=(
                    f"{api_base}/v1/units/{unit_id}/student/events/{event.event_id}"
                    f"/speakers/{speaker_id}/feedback"
                ),
                bearer_token=bearer_token,
                # No comment. A rating is a number a student chose; a sentence
                # attributed to a synthetic student is a quotation nobody said.
                body={"rating": rating},
            )
            if status == 201:
                report.ratings_created += 1
            elif status == 200:
                report.ratings_amended += 1
            else:
                raise SeedFeedbackError(
                    f"POST .../student/events/{event.event_id}/speakers/{speaker_id}"
                    f"/feedback answered {status}: {payload}. A 401 means the session "
                    "token was refused; a 403 means this account holds no `student` "
                    "membership on this unit, or the attendance this tool just wrote was "
                    "not committed; a 409 means the seven-day edit window closed between "
                    "the read above and this call."
                )
    return report


# ---------------------------------------------------------------------------
# The cohort leg
# ---------------------------------------------------------------------------


def _probe_cohort_token(*, api_base: str) -> None:
    """Refuse early when the API cannot resolve the cohort's dev tokens.

    Called only after rank 1's account and membership are committed — the map
    resolves a token to a subject and the principal lookup then needs the
    account row, so a probe before that commit could not tell "token unmapped"
    from "account unwritten" apart.

    ``GET /v1/me`` rather than the feedback route itself: the question here is
    whether the bearer token resolves at all, and the answer should not depend
    on any unit, event or attendance row.
    """
    status, payload = _request(
        method="GET", url=f"{api_base}/v1/me", bearer_token=feedback_student_token(1)
    )
    if status == 200:
        return
    raise SeedFeedbackError(
        f"GET /v1/me answered {status} for the feedback cohort's first bearer "
        f"token ({feedback_student_token(1)!r}): {payload}. The cohort "
        "authenticates with dev principals the API's SMARTMATCH_DEV_PRINCIPALS "
        "must carry *before it boots* — the map is read once at startup. "
        "pilot_dataset_plan.feedback_dev_principals() builds the fragment and "
        "scripts/reset_pilot_dataset.sh merges it into that map; on a compose "
        "stack, add the same eight entries to the api service's environment and "
        "recreate the container. Rank 1's account and membership were committed "
        "so the token had something to resolve to; they are inert until it does."
    )


def _speakers_publishing(
    session: Session, *, tenant_id: uuid.UUID, unit_id: uuid.UUID
) -> tuple[int, int]:
    """How many of this unit's speakers publish their aggregate, and how many don't.

    Asked of the database rather than the plan, because the report should state
    what the Speakers page can now show — which includes rows written by earlier
    legs and earlier runs — not what this run intended.
    """
    rows = session.execute(
        sa.select(
            schema.student_speaker_feedback.c.speaker_professional_id,
            sa.func.count().label("responses"),
        )
        .where(
            schema.student_speaker_feedback.c.tenant_id == tenant_id,
            schema.student_speaker_feedback.c.owning_unit_id == unit_id,
            schema.student_speaker_feedback.c.status == "submitted",
        )
        .group_by(schema.student_speaker_feedback.c.speaker_professional_id)
    ).all()
    published = sum(1 for row in rows if int(row.responses) >= MIN_RESPONSES_FOR_AGGREGATE)
    return published, len(rows) - published


def _ensure_cohort_student(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    unit_path: str,
    rank: int,
    accounts: ProfessionalIdentityRepository,
) -> uuid.UUID:
    """Create (or verify) one cohort account and its student membership.

    The same three writes ``generate_pilot_dataset.write_feedback_students``
    makes, and deliberately the same ``student_subject_id`` derivation, so a
    tenant that later runs Phase C meets these accounts rather than minting
    twins of them: ``ensure_account`` is an upsert on the id, the membership
    insert-or-verify refuses only on a *different* role set, and the external
    subject string is a function of the rank alone for the reason
    ``pilot_dataset_plan._FEEDBACK_SUBJECT_PREFIX`` gives — the rebuild script
    has to know it before any tenant uuid exists.
    """
    external_subject = feedback_student_external_subject(rank)
    subject_id = student_subject_id(
        tenant_id=tenant_id, unit_id=unit_id, suffix=f"feedback-{rank:02d}"
    )
    accounts.ensure_account(
        session,
        tenant_id=tenant_id,
        subject_id=subject_id,
        external_subject=external_subject,
        email=f"{external_subject}@synthetic.invalid",
    )
    _existing_or_insert_membership(
        session.connection(),
        tenant_id=tenant_id,
        account_id=subject_id,
        path=unit_path,
        role="student",
    )
    return subject_id


def seed_feedback_cohort(
    session: Session,
    *,
    api_base: str,
    tenant_slug: str,
    unit_path: str,
    now: datetime | None = None,
    report: FeedbackReport,
) -> None:
    """Seed the eight-student cohort and post their ratings through the route.

    The leg the login leg cannot be: per-speaker aggregates publish at three
    *distinct* submitted responses, and one signed-in student is one response.
    Every rating here is a ``POST`` made by the student's own dev bearer token
    — the same route, the same checks, the same idempotent natural key as the
    login leg. See the module docstring's "The cohort leg" for the two
    preconditions it refuses past rather than around.
    """
    report.cohort_ran = True
    moment = datetime.now(tz=UTC) if now is None else now

    tenant_id = resolve_tenant_id(session, slug=tenant_slug)
    if tenant_id is None:
        raise SeedFeedbackError(f"no tenant with slug {tenant_slug!r}; run `make seed-pilot`")
    unit_id = resolve_unit_id(session, tenant_id=tenant_id, path=unit_path)
    if unit_id is None:
        raise SeedFeedbackError(
            f"no org_unit at path {unit_path!r} in tenant {tenant_slug!r}; run `make seed-pilot`"
        )

    events, skipped = cohort_events(session, tenant_id=tenant_id, unit_id=unit_id, now=moment)
    report.cohort_events = len(events)
    report.cohort_events_skipped = skipped
    if not events:
        report.notes.append(
            "no open-window event has a pipeline-confirmed speaker, so the cohort leg "
            "wrote nothing. Open events without confirmed journeys are skipped by this "
            "leg rather than filled from the roster."
        )
        return

    # The (event, speaker) pairs the plan indexes, newest event first. A pair
    # is one confirmed appearance; two pairs may share a speaker at two events,
    # which is two honest sets of ratings, not one duplicated one.
    pairs: tuple[tuple[uuid.UUID, uuid.UUID], ...] = tuple(
        (event.event_id, speaker_id) for event in events for speaker_id in event.speaker_ids
    )
    shape = tuple(
        COHORT_RESPONSE_SHAPE[index % len(COHORT_RESPONSE_SHAPE)] for index in range(len(pairs))
    )
    planned = build_speaker_feedback(shape=shape)
    summary = feedback_plan_summary(planned)
    report.cohort_speakers_rated = len(pairs)
    report.notes.append(
        f"cohort plan: {summary.posted} ratings across {len(pairs)} confirmed "
        f"(event, speaker) pairs, {summary.withheld} deliberately withheld "
        f"({summary.withheld_share:.0%}); the plan projects "
        f"{summary.speakers_published} publishing and {summary.speakers_suppressed} "
        "staying below the line."
    )

    accounts = ProfessionalIdentityRepository()
    attendance = AttendanceRepository()

    # Rank 1 first and alone: the probe below needs the account committed, and
    # a stack that cannot resolve the token should get the refusal after the
    # smallest possible write, not after the whole cohort's.
    rank_one = _ensure_cohort_student(
        session,
        tenant_id=tenant_id,
        unit_id=unit_id,
        unit_path=unit_path,
        rank=1,
        accounts=accounts,
    )
    session.commit()
    _probe_cohort_token(api_base=api_base)

    subject_ids = {1: rank_one}
    for rank in range(2, FEEDBACK_STUDENT_COUNT + 1):
        subject_ids[rank] = _ensure_cohort_student(
            session,
            tenant_id=tenant_id,
            unit_id=unit_id,
            unit_path=unit_path,
            rank=rank,
            accounts=accounts,
        )
    report.cohort_students = len(subject_ids)

    # Every cohort student attends every rated event, whether or not the plan
    # has them speak there: a withheld rating is a student who attended and did
    # not respond, not a student who was never there.
    for subject_id in subject_ids.values():
        for event in events:
            if attendance.record_attendance(
                session,
                tenant_id=tenant_id,
                owning_unit_id=unit_id,
                subject_id=subject_id,
                event_id=event.event_id,
                method=SYNTHETIC_ATTENDANCE_METHOD,
            ).created:
                report.cohort_attendances += 1
    # Committed before the first POST for the login leg's reason: the route
    # reads attendance in a different session, and a rating posted against an
    # uncommitted row is a 403 this tool caused itself.
    session.commit()

    for entry in planned:
        if entry.rating is None:
            # Deliberate silence — the plan's withheld share. No row, not a
            # zero, and a counted fact about the run rather than an absence.
            report.cohort_ratings_withheld += 1
            continue
        event_id, speaker_id = pairs[entry.speaker_rank]
        status, payload = _request(
            method="POST",
            url=(
                f"{api_base}/v1/units/{unit_id}/student/events/{event_id}"
                f"/speakers/{speaker_id}/feedback"
            ),
            bearer_token=feedback_student_token(entry.student_rank),
            # No comment, for the login leg's reason: a sentence attributed to
            # a synthetic student is a quotation nobody said.
            body={"rating": entry.rating},
        )
        if status == 201:
            report.cohort_ratings_created += 1
        elif status == 200:
            report.cohort_ratings_amended += 1
        else:
            raise SeedFeedbackError(
                f"POST .../student/events/{event_id}/speakers/{speaker_id}/feedback "
                f"answered {status} for cohort student {entry.student_rank}: {payload}. "
                "A 401 means this pilot-feedback-NN token is not in the API process's "
                "SMARTMATCH_DEV_PRINCIPALS (read once at startup — see the probe "
                "refusal above); a 403 means the cohort membership or the attendance "
                "row this leg just committed is missing; a 409 means the seven-day "
                "edit window closed between the read above and this call."
            )
        time.sleep(FEEDBACK_PACE_SECONDS)

    report.speakers_publishing, report.speakers_below_threshold = _speakers_publishing(
        session, tenant_id=tenant_id, unit_id=unit_id
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-base",
        required=True,
        help=(
            "Base URL of the RUNNING API. Required and undefaulted: this tool posts "
            "through the student route rather than writing rows, so there is no "
            "database-only mode to fall back to."
        ),
    )
    parser.add_argument("--tenant-slug", default="pilot", help="Synthetic tenant slug")
    parser.add_argument("--unit-path", default="pilot", help="ltree path owning the dataset")
    parser.add_argument(
        "--subjects",
        choices=sorted(SUBJECT_SETS),
        default=DEFAULT_SUBJECT_SET,
        help=(
            "Which family the rating student belongs to. 'login' (the default) is the "
            "pilot-login-* account student@ signs in as — the only family this tool can "
            "sign in as at all, since the compose fixtures have no password."
        ),
    )
    parser.add_argument(
        "--student-subject",
        default=None,
        help="external_subject of the rating student (default: the family's student)",
    )
    parser.add_argument(
        "--cohort",
        action="store_true",
        help=(
            f"Also run the {FEEDBACK_STUDENT_COUNT}-student feedback cohort: each "
            "synthetic-pilot-feedback-student-NN account rates the confirmed speakers "
            "at open-window events through its own pilot-feedback-NN dev bearer token, "
            "which is what gives the Speakers page several published per-speaker means "
            "rather than one. The API process's SMARTMATCH_DEV_PRINCIPALS must map "
            "those tokens before it boots — pilot_dataset_plan.feedback_dev_principals "
            "builds the fragment; a stack that does not carry them is refused early "
            "by a GET /v1/me probe."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Sign in, seed, report, and exit non-zero on any refusal.

    Three distinguishable exits, matching the rest of this family: ``2`` for a
    configuration or precondition refusal, ``1`` for a database failure, ``0``
    for a run whose report is printed either way.
    """
    args = parse_args(argv)
    try:
        settings = require_development_fixture_settings(Settings())
    except SeedConfigurationError as exc:
        print(f"seed-pilot-student-feedback: configuration error: {exc}", file=sys.stderr)
        return 2

    try:
        family = SUBJECT_SETS[args.subjects]
    except KeyError:  # pragma: no cover - argparse restricts the choices
        print(f"seed-pilot-student-feedback: unknown family {args.subjects!r}", file=sys.stderr)
        return 2
    student_subject = args.student_subject or family.get("student")
    if not student_subject:
        print(
            f"seed-pilot-student-feedback: subject family {args.subjects!r} names no "
            "student account; pass --student-subject",
            file=sys.stderr,
        )
        return 2

    try:
        token = login(api_base=args.api_base)
    except SeedFeedbackError as exc:
        print(f"seed-pilot-student-feedback: {exc}", file=sys.stderr)
        return 2

    session_factory = create_session_factory(settings.database_url)
    with session_factory() as session:
        try:
            session.execute(
                sa.text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": SEED_PILOT_ADVISORY_LOCK_KEY},
            )
            report = seed_student_feedback(
                session,
                api_base=args.api_base,
                bearer_token=token,
                tenant_slug=args.tenant_slug,
                unit_path=args.unit_path,
                student_subject=student_subject,
            )
            if args.cohort:
                seed_feedback_cohort(
                    session,
                    api_base=args.api_base,
                    tenant_slug=args.tenant_slug,
                    unit_path=args.unit_path,
                    report=report,
                )
            session.commit()
        except (SeedFeedbackError, SeedEngagementError, SeedConfigurationError) as exc:
            session.rollback()
            print(f"seed-pilot-student-feedback: {exc}", file=sys.stderr)
            return 2
        except SQLAlchemyError as exc:
            session.rollback()
            print(
                "seed-pilot-student-feedback: database operation failed; run `make migrate` "
                f"against the target database first: {exc}",
                file=sys.stderr,
            )
            return 1

    print(f"seed-pilot-student-feedback: done, as {student_subject}.")
    for line in report.lines():
        print(f"  {line}")
    for note in report.notes:
        print(f"  NOTE: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
