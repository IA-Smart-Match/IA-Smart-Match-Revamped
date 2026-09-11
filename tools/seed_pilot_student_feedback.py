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

## Rerunning it

Idempotent. Attendance is ``ON CONFLICT DO NOTHING`` on
``(tenant, subject, event)``; the rating's natural key is
``(tenant, student, event, speaker)``, so a second submission is an edit of the
caller's own rating and the route answers ``200`` rather than ``201``. Both are
success and the report distinguishes them.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

import sqlalchemy as sa
from seed_demo_pipeline import resolve_tenant_id, resolve_unit_id
from seed_pilot import (
    SEED_PILOT_ADVISORY_LOCK_KEY,
    SeedConfigurationError,
    require_development_fixture_settings,
)
from seed_pilot_engagement import DEFAULT_SUBJECT_SET, SUBJECT_SETS, SeedEngagementError
from smartmatch_api.config import Settings
from smartmatch_domain.student_speaker_feedback import (
    EditWindowState,
    feedback_anchor,
    resolve_edit_window,
)
from smartmatch_domain.synthetic_pilot import SYNTHETIC_ATTENDANCE_METHOD
from smartmatch_persistence import schema
from smartmatch_persistence.attendance import AttendanceRepository
from smartmatch_persistence.engine import create_session_factory
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

__all__ = [
    "EMAIL_VARIABLE",
    "PASSWORD_VARIABLE",
    "RATING_CYCLE",
    "FeedbackReport",
    "OpenEvent",
    "SeedFeedbackError",
    "login",
    "main",
    "open_window_events",
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
    """What this run did, for the report :func:`main` prints."""

    events_open: int = 0
    attendances_recorded: int = 0
    ratings_created: int = 0
    ratings_amended: int = 0
    notes: list[str] = field(default_factory=list)

    def lines(self) -> tuple[str, ...]:
        """The counts, one per line, in the order they happened."""
        return (
            f"events with an open feedback window   {self.events_open}",
            f"attendance_record written             {self.attendances_recorded}",
            f"student_speaker_feedback created      {self.ratings_created}",
            f"student_speaker_feedback amended      {self.ratings_amended} (re-run)",
        )


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
    session: Session, *, tenant_id: uuid.UUID, unit_id: uuid.UUID, event_id: uuid.UUID
) -> tuple[uuid.UUID, ...]:
    """Professionals a pipeline journey confirmed at this event, roster-checked.

    Asked of ``pipeline_record`` rather than chosen from the roster, because a
    rating is a statement about somebody who spoke. The ``speaker_profile`` join
    is not belt-and-braces: ``pipeline_record.subject_id`` is a professional and
    the route's roster check is on ``speaker_profile``, so a confirmed journey
    for somebody with no profile on this unit would be a ``403`` several calls
    later rather than an empty list now.
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
        .order_by(schema.pipeline_record.c.confirmed_at.asc())
        .limit(MAX_SPEAKERS_PER_EVENT)
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

    Only events whose window is genuinely ``OPEN``. ``CLOSED`` events answer
    ``409`` and most of a generated calendar is closed, which is the calendar
    being honest rather than a defect. ``UNKNOWN`` — an ADR-0010 unresolved
    event with no anchor — is writable and deliberately unused: OQ-CBA-052 is
    open on what a rating of an undated event means.
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

    chosen: list[OpenEvent] = []
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
        speakers = _confirmed_speakers(
            session, tenant_id=tenant_id, unit_id=unit_id, event_id=event_id
        )
        confirmed = bool(speakers)
        if not speakers:
            speakers = _roster_speakers(session, tenant_id=tenant_id, unit_id=unit_id)
        if not speakers:
            continue
        chosen.append(
            OpenEvent(
                event_id=event_id,
                title=str(row.title),
                speaker_ids=speakers,
                speakers_confirmed=confirmed,
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
        attendance.record_attendance(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=student_id,
            event_id=event.event_id,
            method=SYNTHETIC_ATTENDANCE_METHOD,
        )
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
