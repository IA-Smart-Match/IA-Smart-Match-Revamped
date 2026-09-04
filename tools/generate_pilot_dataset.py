#!/usr/bin/env python3
"""Dev-only operator tool: generate a synthetic pilot dataset deep enough to measure.

The pilot appliance demonstrates its *mechanics* correctly and its *statistics*
not at all. ``tools/seed_pilot.py`` creates one principal;
``tools/seed_pilot_review.py`` gives that principal two rows to review;
``tools/seed_demo_pipeline.py`` walks whatever journeys somebody else already
opened. The result is a stack where every screen is correct and almost every
number is ``unknown`` — which is exactly what ADR-0011 requires of a value with
no evidence, and which reads to a stakeholder as broken software.

This tool fixes that the only admissible way: **by generating more evidence,
never by relaxing the rule.** Nothing here writes a zero where a value is
unknown, nothing here adds a "show 0 instead of unknown" mode, and a deliberate
fraction of what it writes carries no evidence at all so that the unknown
states stay visible and provable. See ``tools/pilot_dataset_plan.py`` for the
exact fractions.

How this relates to the three seeds that already exist
------------------------------------------------------
It extends them; it does not replace or parallel them.

* ``seed_pilot.py`` — **prerequisite.** It creates the tenant, the unit, and
  the coordinator identity. This tool resolves them and refuses to run if they
  are absent, and it imports that module's
  :func:`~seed_pilot.require_development_fixture_settings` verbatim rather than
  restating the dev/fixture guard, so the two tools can never disagree about
  what "dev" means.
* ``seed_pilot_review.py`` — **the pattern this tool's Phase A follows.** That
  tool established that a demo review queue must be produced *by the product*:
  submit an ordinary import through the running API with the ordinary bearer
  token, then poll until the ordinary worker/scheduler path has turned it into
  review items. Phase A does exactly that, at dataset scale, and then decides
  those items through the ordinary ``POST /v1/review-items/{id}/decision``
  route.
* ``seed_demo_pipeline.py`` — **reused, not duplicated.** Its
  ``resolve_tenant_id``, ``resolve_unit_id`` and, most importantly,
  ``advance_journey`` are imported and called here. Every funnel stage this
  tool writes goes through that function, which means it goes through
  ``PipelineRepository.advance_stage`` and
  ``AttendanceRepository.record_attendance`` with the same ten-minute stage
  spacing and the same ``SYNTHETIC_ATTENDANCE_METHOD`` as before. This tool's
  contribution is that it *opens* the journeys that tool could only walk, and
  opens them against **real** ``event`` rows.

Two phases, and why the split is where it is
--------------------------------------------
**Phase A goes through the HTTP API**, because for imports and review decisions
a real caller-facing writer exists and using anything else would prove less.
Three imports and a few dozen decisions produce genuine ``import_batch`` /
``review_item`` rows, genuine accepted opportunities, and — on the small third
import — a genuine fan-out through ``smartmatch_api.pipeline_provisioning``
opening journeys the product's own way.

**Phase B goes through the repositories**, because for events, attendance,
points and the funnel there is *no* HTTP writer to go through and the
repositories say so themselves: ``smartmatch_persistence.events``,
``.attendance``, ``.pipeline`` and ``.rewards`` each document that no
production caller wires them yet. ``seed_demo_pipeline.py`` already set the
precedent that an operator tool is the legitimate caller in that situation.
Nothing in this file issues an ``INSERT`` of its own — every write is a
repository method call, so every CHECK constraint, foreign key and
CHECK-registry entry applies exactly as it does in production.

What this tool cannot populate, and why
---------------------------------------
``reward_item`` — the rewards catalog — has **no writer anywhere in the
application**. ``RewardsRepository`` reads it (``listable_items``,
``_load_item``) and never writes it; the only inserts against that table in
this repository are raw SQL inside tests. Reaching around that with an
``INSERT`` here is precisely what this tool must not do, so the generated
dataset has real attendance-derived balances and an **empty catalog**, and
therefore no redemption in any state. That is reported at the end of every run
rather than papered over. The same is true of professional topic and location
evidence: no table holds it, so it is derived from the seed and submitted in
the match-run request body, which is where the API contract actually expects it
to come from.

Determinism
-----------
Every decision this tool makes is a pure function of ``--seed`` (default
:data:`~pilot_dataset_plan.DEFAULT_SEED`) — names, regions, topics, dates,
which rows are accepted, which journeys reach which stage, who attended what.
Two runs against two freshly migrated databases produce the same *content*.
Row **identifiers** are a narrower claim, stated honestly: where a repository
lets a caller supply an id, this tool supplies a derived one and the id is
stable (``user_account.id`` via ``synthetic_professional_subject_id``,
``pipeline_record`` keyed on subject and opportunity); where a repository mints
its own — ``event.id``, ``review_item.id`` and ``point_ledger_entry.id`` are
all ``uuid4`` inside the repository — the id differs between databases, and
this tool cannot change that without editing application code, which is out of
scope here.

Re-runnable, not merely idempotent
----------------------------------
Running twice does not double anything and does not fail on a unique
constraint. Every writer this tool calls is already idempotent by construction
— ``ensure_account`` and ``link_to_unit`` are ``ON CONFLICT DO NOTHING``,
``EventRepository.upsert`` resolves ADR-0012's identity key, ``record_matched``
and ``record_attendance`` return the existing row, ``advance_stage`` no-ops on
a stage already reached, and ``credit_attendance`` raises
:class:`~smartmatch_persistence.rewards.AlreadyCreditedError`, which this tool
treats as "already done". Phase A's decisions are once-only by the API's own
rule: a second decision on a decided item answers ``409``, which this tool
counts as already-decided rather than as a failure.

Dev-only
--------
:func:`require_development_fixture_settings` — imported from ``seed_pilot`` —
refuses to run unless ``SMARTMATCH_EDITION=dev`` and
``SMARTMATCH_USE_FIXTURE_PROVIDERS=true``. This tool cannot be pointed at any
other edition.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from datetime import time as clock_time
from typing import Any, Final
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from pilot_dataset_plan import (
    DEFAULT_SEED,
    EVENT_LOCATION,
    EventPlan,
    ProfessionalPlan,
    StudentPlan,
    build_events,
    build_professionals,
    build_students,
    plan_summary,
)
from seed_demo_pipeline import (
    _SelectedJourney,
    advance_journey,
    resolve_tenant_id,
    resolve_unit_id,
)
from seed_pilot import SeedConfigurationError, require_development_fixture_settings
from smartmatch_api.config import Settings
from smartmatch_domain.event_vocabulary import G3_VOCABULARY
from smartmatch_domain.events import DateOnlyTime, EventTime, ExactTime, UnresolvedTime
from smartmatch_domain.pipeline import PipelineStage
from smartmatch_domain.synthetic_pilot import (
    SYNTHETIC_ATTENDANCE_METHOD,
    SYNTHETIC_BOARD_ROLE,
    SYNTHETIC_MATCH_PROVENANCE,
    synthetic_professional_email,
    synthetic_professional_external_subject,
    synthetic_professional_subject_id,
)
from smartmatch_persistence import schema
from smartmatch_persistence.attendance import AttendanceRepository
from smartmatch_persistence.engine import create_session_factory
from smartmatch_persistence.events import ORIGIN_COORDINATOR_ENTRY, EventRepository
from smartmatch_persistence.pipeline import PipelineRepository
from smartmatch_persistence.professionals import ProfessionalIdentityRepository
from smartmatch_persistence.rewards import AlreadyCreditedError, RewardsRepository
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

#: The zone every generated event happens in. One zone, named on the row —
#: ADR-0010 rule 3 renders an event in its own zone, never the viewer's.
PILOT_TIME_ZONE: Final[str] = "America/Los_Angeles"

#: ``uuid5`` namespace for synthetic *student* subject ids. Distinct from the
#: two namespaces ``smartmatch_domain.synthetic_pilot`` declares, so a student
#: and a professional built from the same ordinal can never collide.
#:
#: It lives here rather than in the domain because a student identity is this
#: demo tool's own notion — nothing in the application derives one — and adding
#: it to shipped domain code would be an application change this card does not
#: own.
STUDENT_NAMESPACE: Final[uuid.UUID] = uuid.UUID("2d7c4a90-6b31-4f5e-9c08-3ae1d5b70642")

#: How far before an event a journey is recorded as matched. A fixed offset, so
#: every ``matched_at`` derives from the event's own date rather than from
#: ``utc_now()`` — a re-run therefore writes the same timestamps, exactly as
#: ``seed_demo_pipeline`` derives its stage times from ``matched_at``.
MATCH_LEAD_DAYS: Final[int] = 30

#: The funnel shape, as a repeating cycle rather than a random draw. Entry *i*
#: is the furthest stage journey *i* reaches; ``None`` means the journey stops
#: at Matched. Thirty-six entries in the proportions 8 : 9 : 7 : 9 : 3, so 180
#: journeys land as 40 matched-only, 45 through contacted, 35 through
#: confirmed, 45 through attended and 15 through member inquiry. A cycle rather
#: than a seeded shuffle because the funnel's *shape* is the thing being
#: demonstrated and it should not wobble from one seed to the next.
JOURNEY_STAGE_CYCLE: Final[tuple[PipelineStage | None, ...]] = (
    None,
    PipelineStage.CONTACTED,
    PipelineStage.CONFIRMED,
    PipelineStage.ATTENDED,
    None,
    PipelineStage.CONTACTED,
    PipelineStage.CONFIRMED,
    PipelineStage.ATTENDED,
    PipelineStage.MEMBER_INQUIRY,
    None,
    PipelineStage.CONTACTED,
    PipelineStage.CONFIRMED,
    PipelineStage.ATTENDED,
    None,
    PipelineStage.CONTACTED,
    PipelineStage.CONFIRMED,
    PipelineStage.ATTENDED,
    PipelineStage.MEMBER_INQUIRY,
    None,
    PipelineStage.CONTACTED,
    PipelineStage.CONFIRMED,
    PipelineStage.ATTENDED,
    None,
    PipelineStage.CONTACTED,
    PipelineStage.CONFIRMED,
    PipelineStage.ATTENDED,
    PipelineStage.MEMBER_INQUIRY,
    None,
    PipelineStage.CONTACTED,
    PipelineStage.CONFIRMED,
    PipelineStage.ATTENDED,
    None,
    PipelineStage.CONTACTED,
    PipelineStage.CONFIRMED,
    PipelineStage.ATTENDED,
    None,
)

#: Seconds between review decisions. ``REVIEW_DECISION_RATE_LIMIT`` allows 60 a
#: minute; pacing just under that is what keeps a dataset-scale run from
#: refusing itself with ``429`` partway through. Deliberately a fixed pace
#: rather than a retry-on-429 loop: a tool that hammers a limiter and recovers
#: is a tool that hides how close it is running to it.
DECISION_PACE_SECONDS: Final[float] = 1.05

#: How many rows go in the small third import whose acceptances demonstrate
#: ``pipeline_provisioning``'s own fan-out. Small on purpose: each accepted
#: in-list row opens one journey per professional already linked to the unit,
#: capped at ``MAX_SYNTHETIC_JOURNEYS_PER_ACCEPT`` (50), so accepting many of
#: them would bury the funnel under a single enormous Matched bar — the
#: opposite of the real distribution this tool exists to produce.
FANOUT_IMPORT_ROWS: Final[int] = 4

#: How many professionals go into the deliberately-undecided review queue.
PENDING_IMPORT_ROWS: Final[int] = 30


class GeneratorError(RuntimeError):
    """The dataset could not be generated through the paths this tool insists on."""


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class RunReport:
    """Everything one run did, including everything it deliberately did not.

    Printed in full at the end of every run — a silent success is
    indistinguishable from a silent no-op, which the standing §1.10 rule the
    other seed tools follow treats as a defect.
    """

    seed: int
    professionals: int = 0
    professionals_without_topics: int = 0
    professionals_without_location: int = 0
    events: int = 0
    events_unresolved: int = 0
    events_quarantined: int = 0
    events_published: int = 0
    review_items_submitted: int = 0
    review_items_accepted: int = 0
    review_items_rejected: int = 0
    review_items_left_pending: int = 0
    review_items_already_decided: int = 0
    journeys_opened: int = 0
    stages_advanced: int = 0
    students: int = 0
    student_attendances: int = 0
    ledger_credits: int = 0
    students_left_uncredited: int = 0
    match_run_job: str | None = None
    match_run_scored: int | None = None
    match_run_unscorable: int | None = None
    notes: list[str] = field(default_factory=list)

    def lines(self) -> tuple[str, ...]:
        """The report, one fact per line."""
        return (
            f"seed                        {self.seed}",
            f"professionals               {self.professionals}",
            f"  no topic evidence         {self.professionals_without_topics} (deliberate)",
            f"  no location evidence      {self.professionals_without_location} (deliberate)",
            f"events                      {self.events}",
            f"  unresolved date           {self.events_unresolved} (deliberate, ADR-0010)",
            f"  quarantined tags          {self.events_quarantined} (deliberate)",
            f"  published                 {self.events_published}",
            f"review items submitted      {self.review_items_submitted}",
            f"  accepted                  {self.review_items_accepted}",
            f"  rejected                  {self.review_items_rejected}",
            f"  left pending              {self.review_items_left_pending} (deliberate)",
            f"  already decided           {self.review_items_already_decided} (re-run)",
            f"pipeline journeys opened    {self.journeys_opened}",
            f"funnel stages advanced      {self.stages_advanced}",
            f"students                    {self.students}",
            f"student attendance records  {self.student_attendances}",
            f"point ledger credits        {self.ledger_credits}",
            f"  attended but uncredited   {self.students_left_uncredited} (deliberate: unknown)",
            f"match-run job               {self.match_run_job or 'not submitted'}",
            f"  scored candidates         {self.match_run_scored}",
            f"  unscorable candidates     {self.match_run_unscorable} (reported, never zeroed)",
        )


# ---------------------------------------------------------------------------
# HTTP — the ordinary API, with the ordinary bearer token
# ---------------------------------------------------------------------------


def _request(
    *,
    method: str,
    url: str,
    bearer_token: str,
    body: Mapping[str, Any] | None = None,
    request_id: str | None = None,
    timeout: float = 60.0,
) -> tuple[int, Any]:
    """Issue one authenticated request, returning its status and decoded body.

    A ``4xx``/``5xx`` is returned rather than raised: several of this tool's
    calls have an expected non-2xx answer (a ``409`` on an already-decided
    review item is the normal re-run path), and a helper that raised on all of
    them would make every caller catch and re-inspect an exception to tell
    those apart from a real failure.
    """
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json",
    }
    if request_id is not None:
        # A request de-duplication id, not a credential — the same reason
        # ``seed_pilot_review.DEMO_IMPORT_REQUEST_ID`` is named for what it is.
        headers["Idempotency-Key"] = request_id

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
        raise GeneratorError(f"could not reach {url}: {exc.reason}") from exc


def wait_for_api(*, api_base: str, attempts: int, delay: float) -> None:
    """Block until the API answers ``/api/health``, or say plainly that it never did."""
    last = "no attempt made"
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(f"{api_base}/api/health", timeout=5.0) as response:
                if response.status == 200:
                    print(f"generate-pilot-dataset: api healthy on attempt {attempt}")
                    return
                last = f"HTTP {response.status}"
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            last = str(exc)
        print(f"generate-pilot-dataset: waiting for api ({last})")
        time.sleep(delay)
    raise GeneratorError(f"api never became healthy at {api_base}: {last}")


# ---------------------------------------------------------------------------
# Phase A — imports and review decisions, through the real routes
# ---------------------------------------------------------------------------


def professionals_rows(planned: Sequence[ProfessionalPlan]) -> list[dict[str, str]]:
    """The ratified ``professionals`` columns, spelled as a coordinator's export would.

    ``docs/pilot-data/columns.yaml`` declares ``name`` and ``metro_region``
    required and ``company`` / ``title`` / ``expertise_tags`` / ``initials``
    optional. A professional with no expertise record contributes no
    ``expertise_tags`` key at all rather than an empty string: an absent column
    is an absent record, and a blank one is a record that says nothing, which
    are not the same claim.
    """
    rows: list[dict[str, str]] = []
    for person in planned:
        row = {
            "name": person.name,
            "metro_region": person.region,
            "company": person.organization,
            "title": person.title,
            "initials": person.initials,
        }
        if person.topics is not None:
            row["expertise_tags"] = ", ".join(person.topics)
        rows.append(row)
    return rows


def events_rows(planned: Sequence[EventPlan]) -> list[dict[str, str]]:
    """The ratified ``events`` columns, verbatim including punctuation and casing.

    ``"Event / Program"`` and ``"Category"`` are the two required columns;
    ``smartmatch_domain.ingest.normalize_header`` folds them to
    ``event_program`` and ``category`` on the way into ``review_item.row_data``,
    which is the spelling ``pipeline_provisioning`` and the ``opportunities``
    metric both read.
    """
    return [
        {
            "Event / Program": event.title,
            "Category": event.category,
            "Recurrence (typical)": "Annual",
            "Host / Unit": "Synthetic Pilot Unit",
            "Volunteer Roles (fit)": ", ".join(event.tags),
            "Primary Audience": "Students",
        }
        for event in planned
    ]


def submit_import(
    *,
    api_base: str,
    bearer_token: str,
    unit_id: uuid.UUID,
    dataset: str,
    rows: Sequence[Mapping[str, str]],
    request_id: str,
) -> uuid.UUID:
    """Submit one import through ``POST /v1/units/{unit_id}/imports``.

    Returns the accepted command's ``job_id``. A non-202 is a failure this tool
    reports rather than works around: if the import path is broken, a demo
    dataset staged behind it would be a claim about a pipeline that does not
    run.
    """
    status, body = _request(
        method="POST",
        url=f"{api_base}/v1/units/{unit_id}/imports",
        bearer_token=bearer_token,
        body={"dataset": dataset, "dry_run": False, "rows": list(rows)},
        request_id=request_id,
    )
    if status != 202 or not isinstance(body, dict) or "job_id" not in body:
        raise GeneratorError(
            f"POST /v1/units/{unit_id}/imports answered {status} for dataset {dataset!r}: {body}"
        )
    return uuid.UUID(str(body["job_id"]))


def wait_for_review_items(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    job_id: uuid.UUID,
    wanted: int,
    attempts: int,
    delay: float,
) -> tuple[uuid.UUID, ...]:
    """Poll until the worker has turned one import into ``wanted`` review items.

    A poll of the real outcome, exactly as ``seed_pilot_review`` does it and for
    the same reason: an appliance whose scheduler sidecar never started must
    fail here loudly rather than have this tool quietly carry on against a queue
    nothing produced. Returns the item ids ordered by ``row_index``, so which
    row gets which decision is a function of the plan and not of whatever order
    PostgreSQL happened to return.
    """
    observed: tuple[uuid.UUID, ...] = ()
    for attempt in range(1, attempts + 1):
        # Roll back first: this session holds a transaction whose snapshot
        # predates the worker's commit, and polling inside it would loop
        # forever against a view of the database taken before the rows landed.
        session.rollback()
        rows = session.execute(
            sa.select(schema.review_item.c.id)
            .join(
                schema.import_batch,
                sa.and_(
                    schema.import_batch.c.tenant_id == schema.review_item.c.tenant_id,
                    schema.import_batch.c.id == schema.review_item.c.import_batch_id,
                ),
            )
            .where(
                schema.review_item.c.tenant_id == tenant_id,
                schema.import_batch.c.job_id == job_id,
            )
            .order_by(schema.review_item.c.row_index)
        ).all()
        observed = tuple(uuid.UUID(str(row.id)) for row in rows)
        print(f"generate-pilot-dataset: attempt {attempt}: review items for job = {len(observed)}")
        if len(observed) >= wanted:
            return observed
        time.sleep(delay)
    raise GeneratorError(
        f"the queued import never reached review: expected {wanted} review items for job "
        f"{job_id}, still {len(observed)}. This is a dispatch failure, not a slow start — "
        "check `docker compose ps -a scheduler` and `docker compose logs scheduler`."
    )


def decision_for(index: int) -> str | None:
    """Which decision row ``index`` of the events import receives.

    ``None`` means "left pending", which is not indecision — a review queue with
    nothing in it is as unrealistic as a funnel with nothing in it, and
    ``pending_review_items`` is itself one of the register's metrics. The
    arithmetic is deliberate rather than random so the same row always gets the
    same decision.
    """
    if index % 13 == 0:
        return "rejected"
    if index % 7 == 3:
        return None
    return "accepted"


def decide_items(
    *,
    api_base: str,
    bearer_token: str,
    item_ids: Sequence[uuid.UUID],
    report: RunReport,
) -> None:
    """Decide each item through the ordinary review-decision route.

    Paced at :data:`DECISION_PACE_SECONDS` so a dataset-scale run stays inside
    ``REVIEW_DECISION_RATE_LIMIT``. A ``409`` means this item was decided on an
    earlier run, which is the ordinary re-run path and is counted, not raised.
    """
    for index, item_id in enumerate(item_ids):
        decision = decision_for(index)
        if decision is None:
            report.review_items_left_pending += 1
            continue
        _decide_one(
            api_base=api_base,
            bearer_token=bearer_token,
            item_id=item_id,
            decision=decision,
            report=report,
        )


def _decide_one(
    *,
    api_base: str,
    bearer_token: str,
    item_id: uuid.UUID,
    decision: str,
    report: RunReport,
) -> None:
    """Record one decision, counting the already-decided answer rather than raising."""
    status, body = _request(
        method="POST",
        url=f"{api_base}/v1/review-items/{item_id}/decision",
        bearer_token=bearer_token,
        body={"decision": decision},
    )
    if status == 200:
        if decision == "accepted":
            report.review_items_accepted += 1
        else:
            report.review_items_rejected += 1
    elif status == 409:
        report.review_items_already_decided += 1
    else:
        raise GeneratorError(f"POST /v1/review-items/{item_id}/decision answered {status}: {body}")
    time.sleep(DECISION_PACE_SECONDS)


# ---------------------------------------------------------------------------
# Phase B — the writers with no HTTP door
# ---------------------------------------------------------------------------


def write_professionals(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    planned: Sequence[ProfessionalPlan],
    report: RunReport,
) -> tuple[uuid.UUID, ...]:
    """Create each professional's account and link it to the unit.

    Through ``ProfessionalIdentityRepository`` — the same Choice A writer
    ``pipeline_provisioning`` calls on a review accept — and with the same
    derivations, so a professional this tool creates and the same professional
    arriving later through an accepted import are one account, not two.
    """
    repository = ProfessionalIdentityRepository()
    subject_ids: list[uuid.UUID] = []
    for person in planned:
        subject_id = synthetic_professional_subject_id(
            tenant_id=tenant_id, unit_id=unit_id, name=person.name
        )
        repository.ensure_account(
            session,
            tenant_id=tenant_id,
            subject_id=subject_id,
            external_subject=synthetic_professional_external_subject(subject_id),
            email=synthetic_professional_email(subject_id),
        )
        repository.link_to_unit(
            session,
            tenant_id=tenant_id,
            professional_id=subject_id,
            unit_id=unit_id,
            board_role=SYNTHETIC_BOARD_ROLE,
        )
        subject_ids.append(subject_id)
    session.commit()
    report.professionals = len(subject_ids)
    return tuple(subject_ids)


def _event_time(event: EventPlan) -> EventTime:
    """The ADR-0010 temporal value for one planned event.

    Three cases, three types. There is no branch here that turns a missing date
    into a midnight instant, because ``UnresolvedTime`` has no field one could
    be written to.
    """
    if event.on_date is None:
        return UnresolvedTime()
    if event.exact_hour is None:
        return DateOnlyTime(on_date=event.on_date, time_zone=PILOT_TIME_ZONE)
    return ExactTime(
        starts_at=datetime.combine(
            event.on_date,
            clock_time(hour=event.exact_hour),
            tzinfo=ZoneInfo(PILOT_TIME_ZONE),
        ),
        time_zone=PILOT_TIME_ZONE,
    )


def write_events(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    planned: Sequence[EventPlan],
    report: RunReport,
) -> tuple[tuple[EventPlan, uuid.UUID], ...]:
    """Write the calendar, its tags, and publish the events that may publish.

    ``origin`` is ``coordinator_entry`` for every row and no provenance is
    attached: nothing fetched these events, and naming a source URL for a row a
    generator typed in is exactly the fabricated-evidence defect
    ``ck_event_provenance_evidence`` exists to refuse.

    Returns each plan paired with the ``event.id`` the repository resolved it
    to, so callers can cite a **real** event rather than a derived identifier.
    """
    repository = EventRepository()
    written: list[tuple[EventPlan, uuid.UUID]] = []
    for event in planned:
        event_id = repository.upsert(
            session,
            tenant_id=tenant_id,
            host_org_unit_id=unit_id,
            title=event.title,
            event_time=_event_time(event),
            origin=ORIGIN_COORDINATOR_ENTRY,
            description=f"Synthetic pilot {event.category.lower()} session.",
        )
        repository.record_tags(
            session,
            tenant_id=tenant_id,
            event_id=event_id,
            owning_unit_id=unit_id,
            raw_values=(*event.tags, *event.off_vocabulary_tags),
            vocabulary=G3_VOCABULARY,
        )
        if event.publishable:
            repository.publish(session, tenant_id=tenant_id, event_id=event_id)
            report.events_published += 1
        written.append((event, event_id))
    session.commit()

    report.events = len(written)
    report.events_unresolved = sum(1 for event, _ in written if not event.resolved)
    report.events_quarantined = sum(1 for event, _ in written if event.off_vocabulary_tags)
    return tuple(written)


def write_journeys(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    subject_ids: Sequence[uuid.UUID],
    events: Sequence[tuple[EventPlan, uuid.UUID]],
    count: int,
    report: RunReport,
) -> None:
    """Open ``count`` journeys against real events and walk each to its stage.

    Pairing is arithmetic, not random: journey *j* pairs professional
    ``j * 7 mod len(subject_ids)`` with resolved event ``j mod len(events)``.
    The stride of 7 is coprime with any plausible roster size, so the pair
    ``(professional, event)`` does not repeat within a run — which matters,
    because ``pipeline_record``'s natural key is exactly that pair and a repeat
    would silently be the same journey.

    Every stage is written by ``seed_demo_pipeline.advance_journey``, so this
    tool has no funnel-walking logic of its own to keep in step with that one.
    ``matched_at`` derives from the event's own date, never from ``utc_now()``.
    """
    resolved = [(event, event_id) for event, event_id in events if event.resolved]
    if not resolved or not subject_ids:
        report.notes.append(
            "no journeys opened: the plan produced no resolved events or no professionals"
        )
        return

    pipeline_repo = PipelineRepository()
    attendance_repo = AttendanceRepository()

    for index in range(count):
        subject_id = subject_ids[(index * 7) % len(subject_ids)]
        event, event_id = resolved[index % len(resolved)]
        if event.on_date is None:  # unreachable: filtered by `resolved` above
            raise GeneratorError(f"resolved event {event.title!r} has no date")
        matched_at = datetime.combine(event.on_date, clock_time(hour=9), tzinfo=UTC) - timedelta(
            days=MATCH_LEAD_DAYS
        )

        record = pipeline_repo.record_matched(
            session,
            tenant_id=tenant_id,
            owning_unit_id=unit_id,
            subject_id=subject_id,
            opportunity_event_id=event_id,
            matched_at=matched_at,
            matched_provenance=SYNTHETIC_MATCH_PROVENANCE,
        )
        report.journeys_opened += 1

        through = JOURNEY_STAGE_CYCLE[index % len(JOURNEY_STAGE_CYCLE)]
        if through is not None:
            report.stages_advanced += advance_journey(
                session,
                pipeline_repo=pipeline_repo,
                attendance_repo=attendance_repo,
                tenant_id=tenant_id,
                owning_unit_id=unit_id,
                journey=_SelectedJourney(
                    id=record.id,
                    subject_id=subject_id,
                    opportunity_event_id=event_id,
                    matched_at=matched_at,
                ),
                through=through,
            )
        session.commit()


def student_subject_id(*, tenant_id: uuid.UUID, unit_id: uuid.UUID, suffix: str) -> uuid.UUID:
    """Derive a stable ``user_account.id`` for a synthetic student.

    The same shape ``synthetic_professional_subject_id`` uses, under this tool's
    own namespace: deterministic, so a re-run resolves to the same student
    rather than minting a second one, and folded over tenant and unit so two
    units' students cannot collide on the globally-unique ``external_subject``
    derived from this id.
    """
    return uuid.uuid5(STUDENT_NAMESPACE, f"{tenant_id}:{unit_id}:{suffix}")


def write_students(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    planned: Sequence[StudentPlan],
    events: Sequence[tuple[EventPlan, uuid.UUID]],
    report: RunReport,
) -> None:
    """Create students, record their attendance, and credit most of it.

    **The account writer here is
    ``ProfessionalIdentityRepository.ensure_account``, and that is a compromise
    this tool states rather than hides.** No student-identity writer exists in
    the application; that repository is the only ``user_account`` writer that
    accepts a caller-supplied id, which is what determinism requires. It is
    used for its ``user_account`` insert only — no ``link_to_unit`` call is made
    for a student, so no student appears in
    ``professional_unit_relationship`` and none is ever fanned out a journey by
    ``pipeline_provisioning``.

    Points are credited at ``POINTS_PER_VERIFIED_ATTENDANCE`` (D7's 100 per
    verified event), the repository's own default — this tool never passes a
    figure of its own. A deliberate few attending students are left uncredited
    so the rewards surface still has its *unknown* balance to show.
    """
    accounts = ProfessionalIdentityRepository()
    attendance = AttendanceRepository()
    rewards = RewardsRepository()
    resolved = [event_id for event, event_id in events if event.resolved]
    if not resolved:
        report.notes.append("no student attendance written: the plan produced no resolved events")
        return

    for student in planned:
        subject_id = student_subject_id(
            tenant_id=tenant_id, unit_id=unit_id, suffix=student.external_suffix
        )
        accounts.ensure_account(
            session,
            tenant_id=tenant_id,
            subject_id=subject_id,
            external_subject=f"synthetic-student:{subject_id}",
            email=f"student-{subject_id}@synthetic.invalid",
        )

        for step in range(student.attendances):
            event_id = resolved[(student.index * 3 + step) % len(resolved)]
            attendance_id = attendance.record_attendance(
                session,
                tenant_id=tenant_id,
                owning_unit_id=unit_id,
                subject_id=subject_id,
                event_id=event_id,
                method=SYNTHETIC_ATTENDANCE_METHOD,
            )
            report.student_attendances += 1
            if not student.credited:
                continue
            try:
                rewards.credit_attendance(session, tenant_id=tenant_id, attendance_id=attendance_id)
                report.ledger_credits += 1
            except AlreadyCreditedError:
                # The ordinary re-run path: migration 0019's partial unique
                # index already holds this attendance's one credit.
                pass

        if student.attendances and not student.credited:
            report.students_left_uncredited += 1
        report.students += 1
        session.commit()


# ---------------------------------------------------------------------------
# The match run — evidence in the request body, because no table holds it
# ---------------------------------------------------------------------------


def match_run_body(
    planned: Sequence[ProfessionalPlan],
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    limit: int,
    seed: int,
) -> dict[str, Any]:
    """Build one ``POST /match-runs`` submission from the plan.

    The candidate pool carries **evidence, never a score** — the request model
    refuses a caller-supplied score, and rightly: a caller scoring its own pool
    would be a caller choosing its own shortlist.

    ``expertise_topics`` is ``null`` for a professional with no expertise record
    and a list for one with a record. That distinction is the whole point of
    including them: a ``null`` makes ``topic_relevance`` unknown, and the route
    excludes that candidate from the pool and *reports* it rather than entering
    it at zero, where it would sit below every measured candidate as though it
    had been measured and found wanting.

    ``required_topics`` and ``preferred_topics`` name terms that are common in
    the plan, so a genuine shortlist forms rather than every candidate scoring
    unknown.
    """
    return {
        "event_need_id": f"synthetic-pilot-need-{seed}",
        "required_topics": ["workshop"],
        "preferred_topics": ["career panel", "mentor"],
        "event_location": {"latitude": EVENT_LOCATION[0], "longitude": EVENT_LOCATION[1]},
        "portfolio_size": 3,
        "random_seed": seed % 1000,
        "candidates": [
            {
                "subject_id": str(
                    synthetic_professional_subject_id(
                        tenant_id=tenant_id, unit_id=unit_id, name=person.name
                    )
                ),
                "expertise_topics": None if person.topics is None else list(person.topics),
                "location": (
                    None
                    if person.location is None
                    else {"latitude": person.location[0], "longitude": person.location[1]}
                ),
            }
            for person in planned[:limit]
        ],
    }


def submit_match_run(
    *,
    api_base: str,
    bearer_token: str,
    unit_id: uuid.UUID,
    body: Mapping[str, Any],
    request_id: str,
    report: RunReport,
) -> None:
    """Submit the match run and record what the API said about the pool."""
    status, payload = _request(
        method="POST",
        url=f"{api_base}/v1/units/{unit_id}/match-runs",
        bearer_token=bearer_token,
        body=body,
        request_id=request_id,
    )
    if status != 202 or not isinstance(payload, dict):
        raise GeneratorError(f"POST /v1/units/{unit_id}/match-runs answered {status}: {payload}")
    report.match_run_job = str(payload.get("job_id"))
    report.match_run_scored = payload.get("scored_candidates")
    report.match_run_unscorable = payload.get("unscorable_candidates")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", required=True, help="Base URL of the running API")
    parser.add_argument(
        "--bearer-token",
        required=True,
        help="Dev-only bearer token the API maps to the seeded coordinator subject",
    )
    parser.add_argument("--tenant-slug", default="pilot", help="Synthetic tenant slug")
    parser.add_argument("--unit-path", default="pilot", help="ltree path owning the dataset")
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="The seed every generated value derives from. Record it with the demo.",
    )
    parser.add_argument("--professionals", type=int, default=250, help="Professionals to create")
    parser.add_argument("--events", type=int, default=60, help="Events to write to the calendar")
    parser.add_argument("--students", type=int, default=120, help="Students to create")
    parser.add_argument("--journeys", type=int, default=180, help="Pipeline journeys to open")
    parser.add_argument(
        "--ready-attempts", type=int, default=60, help="API readiness poll attempts (2s apart)"
    )
    parser.add_argument(
        "--dispatch-attempts",
        type=int,
        default=90,
        help="Review-item poll attempts after an import (2s apart)",
    )
    return parser.parse_args(argv)


def _run(args: argparse.Namespace, session: Session) -> RunReport:
    """Generate the dataset. Raises :class:`GeneratorError` on any refused path."""
    api_base = args.api_base.rstrip("/")
    report = RunReport(seed=args.seed)

    tenant_id = resolve_tenant_id(session, slug=args.tenant_slug)
    if tenant_id is None:
        raise GeneratorError(
            f"no tenant with slug {args.tenant_slug!r}; run tools/seed_pilot.py "
            "(the compose `seed` service) first"
        )
    unit_id = resolve_unit_id(session, tenant_id=tenant_id, path=args.unit_path)
    if unit_id is None:
        raise GeneratorError(
            f"no org_unit at path {args.unit_path!r} in tenant {args.tenant_slug!r}; "
            "run tools/seed_pilot.py first"
        )

    professionals = build_professionals(args.professionals, seed=args.seed)
    events = build_events(args.events, seed=args.seed)
    students = build_students(args.students, seed=args.seed)
    summary = plan_summary(professionals, events, students)
    report.professionals_without_topics = summary.professionals_without_topics
    report.professionals_without_location = summary.professionals_without_location

    wait_for_api(api_base=api_base, attempts=args.ready_attempts, delay=2.0)

    # -- Phase A.1: the events import and its decisions --------------------
    #
    # Deliberately BEFORE the professionals exist. Accepting an in-list events
    # row fans out one journey per professional already linked to this unit,
    # capped at 50; running these decisions against an empty roster keeps the
    # funnel's shape under this tool's control and leaves the fan-out to be
    # demonstrated once, deliberately, by the small third import below.
    events_job = submit_import(
        api_base=api_base,
        bearer_token=args.bearer_token,
        unit_id=unit_id,
        dataset="events",
        rows=events_rows(events),
        request_id=f"pilot-dataset-events-{args.seed}",
    )
    events_items = wait_for_review_items(
        session,
        tenant_id=tenant_id,
        job_id=events_job,
        wanted=len(events),
        attempts=args.dispatch_attempts,
        delay=2.0,
    )
    report.review_items_submitted += len(events_items)
    decide_items(
        api_base=api_base,
        bearer_token=args.bearer_token,
        item_ids=events_items,
        report=report,
    )

    # -- Phase A.2: a professionals import left entirely pending ------------
    #
    # A coordinator's queue is never empty in a live program, and
    # `pending_review_items` is one of the register's own metrics. These rows
    # are submitted through the real path and deliberately not decided.
    pending_slice = professionals[: min(PENDING_IMPORT_ROWS, len(professionals))]
    if pending_slice:
        pending_job = submit_import(
            api_base=api_base,
            bearer_token=args.bearer_token,
            unit_id=unit_id,
            dataset="professionals",
            rows=professionals_rows(pending_slice),
            request_id=f"pilot-dataset-professionals-{args.seed}",
        )
        pending_items = wait_for_review_items(
            session,
            tenant_id=tenant_id,
            job_id=pending_job,
            wanted=len(pending_slice),
            attempts=args.dispatch_attempts,
            delay=2.0,
        )
        report.review_items_submitted += len(pending_items)
        report.review_items_left_pending += len(pending_items)

    # -- Phase B: the writers with no HTTP door ----------------------------
    subject_ids = write_professionals(
        session, tenant_id=tenant_id, unit_id=unit_id, planned=professionals, report=report
    )
    written_events = write_events(
        session, tenant_id=tenant_id, unit_id=unit_id, planned=events, report=report
    )
    write_journeys(
        session,
        tenant_id=tenant_id,
        unit_id=unit_id,
        subject_ids=subject_ids,
        events=written_events,
        count=args.journeys,
        report=report,
    )
    write_students(
        session,
        tenant_id=tenant_id,
        unit_id=unit_id,
        planned=students,
        events=written_events,
        report=report,
    )

    # -- Phase A.3: the product's own fan-out, demonstrated once ------------
    #
    # A small third import, accepted now that the roster exists, so the demo
    # shows `pipeline_provisioning` opening journeys the way the product does —
    # and shows it at a scale that adds a believable "recently matched" cohort
    # rather than burying the funnel.
    fanout = build_events(FANOUT_IMPORT_ROWS, seed=args.seed + 1)
    fanout_job = submit_import(
        api_base=api_base,
        bearer_token=args.bearer_token,
        unit_id=unit_id,
        dataset="events",
        rows=events_rows(fanout),
        request_id=f"pilot-dataset-fanout-{args.seed}",
    )
    fanout_items = wait_for_review_items(
        session,
        tenant_id=tenant_id,
        job_id=fanout_job,
        wanted=len(fanout),
        attempts=args.dispatch_attempts,
        delay=2.0,
    )
    report.review_items_submitted += len(fanout_items)
    for item_id in fanout_items:
        _decide_one(
            api_base=api_base,
            bearer_token=args.bearer_token,
            item_id=item_id,
            decision="accepted",
            report=report,
        )

    # -- The match run -----------------------------------------------------
    submit_match_run(
        api_base=api_base,
        bearer_token=args.bearer_token,
        unit_id=unit_id,
        body=match_run_body(
            professionals, tenant_id=tenant_id, unit_id=unit_id, limit=200, seed=args.seed
        ),
        request_id=f"pilot-dataset-match-run-{args.seed}",
        report=report,
    )

    report.notes.append(
        "rewards catalog left EMPTY: `reward_item` has no application writer — "
        "`RewardsRepository` only reads it — so this tool cannot create catalog items "
        "without an INSERT of its own, and therefore cannot open a redemption in any "
        "state. The balances above are real and attendance-derived; the catalog is not "
        "missing by accident."
    )
    report.notes.append(
        "professional topic and location evidence is NOT stored: no table holds it. It is "
        "derived from --seed and submitted in the match-run request body, which is where "
        "the API contract expects it to come from."
    )
    return report


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        settings = require_development_fixture_settings(Settings())
    except SeedConfigurationError as exc:
        print(f"generate-pilot-dataset: configuration error: {exc}", file=sys.stderr)
        return 2

    session_factory = create_session_factory(settings.database_url)
    with session_factory() as session:
        try:
            report = _run(args, session)
        except GeneratorError as exc:
            print(f"generate-pilot-dataset: {exc}", file=sys.stderr)
            return 1
        except SQLAlchemyError as exc:
            print(
                "generate-pilot-dataset: database operation failed; the database must be "
                f"migrated and seeded first: {exc}",
                file=sys.stderr,
            )
            return 1

    print("generate-pilot-dataset: done.")
    for line in report.lines():
        print(f"  {line}")
    for note in report.notes:
        print(f"  NOTE: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
