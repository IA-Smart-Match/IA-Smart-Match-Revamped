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
rather than papered over.

The match run, and why it is four steps rather than one
-------------------------------------------------------
It used to be one call carrying its own evidence. OQ-CBA-031 removed that: a
request body that could state a speaker's expertise is a request body that can
decide its own shortlist, so ``POST /v1/units/{unit_id}/match-runs`` now takes a
``speaker_request_id`` and a list of ``candidate_subject_ids`` and nothing else,
and ``smartmatch_api.match_run_evidence`` reads every scored fact off this
tenant's own rows. Producing a match run therefore means producing those rows,
through the product's own routes, in customer §19's own order:

1. **A professionals import, accepted.** ``pipeline_provisioning`` turns each
   accepted row into a ``speaker_profile`` — the table the evidence assembler
   reads — plus an *unreviewed* classification proposal for whatever §7/§8 code
   the export stated.
2. **The §19 review step**, through
   ``POST /v1/units/{unit_id}/speaker-contacts/{professional_id}/classification``.
   §19 orders review before availability, and a proposal is a proposal: an
   unreviewed contact is *absent* from every pool, reported with the reason
   ``industry_classification_awaiting_review``. A deliberate fraction of the
   roster is left unreviewed so that state is visible in generated data rather
   than only in a test.
3. **A Speaker Request, filed** through
   ``POST /v1/units/{unit_id}/speaker-requests``. It is a real ``event`` row with
   real ``speaker_request_classification`` targets, and it is what supplies §9's
   description text and §11's virtual/physical switch. Virtual, because the
   generated roster carries no postal codes and a physical run would answer with
   a pool nobody has located.
4. **The run itself**, submitted with ids the API handed back rather than ids
   this tool derived from a name.

What the shortlist actually looks like, stated in advance
----------------------------------------------------------
Most of the named pool drops out, and not because of anything in this file.
OQ-CBA-061: the fixture semantic-topic provider holds no recordings, so a
speaker carrying ``topic_text`` scores ``unknown`` on customer §9, ADR-0011
rule 1 makes their composite ``None``, and they are reported as *unscorable*
rather than shortlisted — while a speaker who filled nothing in gets §9's stated
policy neutral and is shortlistable. The seed puts expertise text on most
professionals, so most named candidates are unscorable and the shortlist is
filled from the quiet minority.

Every one of those counts is printed at the end of a run rather than smoothed
over. Stripping the seed's topic text would make the demo look fuller and is
**not** done here: it is one of three candidate answers the CBA product owner
holds for OQ-CBA-061, and choosing one of them inside a generator would be
answering an open question by writing code.

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
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from datetime import time as clock_time
from typing import Any, Final
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from pilot_dataset_plan import (
    CALENDAR_ANCHOR,
    DEFAULT_SEED,
    IN_LIST_CATEGORIES,
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
from smartmatch_api.routers.match_runs import MAX_CANDIDATES
from smartmatch_domain.event_vocabulary import G3_VOCABULARY
from smartmatch_domain.events import DateOnlyTime, EventTime, ExactTime, UnresolvedTime
from smartmatch_domain.explanation import MAX_SHORTLIST_SIZE
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
#: opposite of the real distribution this tool exists to produce. Two rows adds
#: a hundred journeys at Matched, which reads as a believable recently-matched
#: cohort next to the walked funnel below it.
FANOUT_IMPORT_ROWS: Final[int] = 2

#: How many professionals go into the deliberately-undecided review queue.
PENDING_IMPORT_ROWS: Final[int] = 30

#: How many professionals are imported **and accepted** so they become §13
#: speaker contacts, and therefore the pool a match run can name.
#:
#: A hundred, and the number is squeezed from both ends.
#:
#: The ceiling is a rate limit: ``SPEAKER_CONTACT_WRITE_RATE_LIMIT`` allows
#: thirty writes a minute and every reviewed contact costs one, so the whole
#: 250-professional roster would spend seven minutes doing nothing but §19
#: corrections. It is also bounded by ``routers/match_runs.MAX_CANDIDATES``
#: (200), which a run may not exceed.
#:
#: The floor is OQ-CBA-061, and this is the uncomfortable part. Only the
#: professionals carrying *no* expertise text can be scored at all — everyone
#: else is ``unknown`` on customer §9 and therefore unscorable — and the plan
#: gives only :data:`~pilot_dataset_plan.UNKNOWN_TOPIC_SHARE` of them no
#: expertise text. After the deliberate unreviewed fifth and the deliberate
#: unclassified share are taken out too, a roster of sixty yields exactly three
#: scorable candidates for a three-speaker shortlist: a demo one unlucky seed
#: away from a ``422``. A hundred yields five. The margin is thin because the
#: open question makes it thin, and widening it by removing topic text from the
#: seed is the workaround this file will not take.
MATCH_ROSTER_ROWS: Final[int] = 100

#: Seconds between §19 classification corrections, for the reason
#: :data:`DECISION_PACE_SECONDS` exists: ``SPEAKER_CONTACT_WRITE_RATE_LIMIT`` is
#: thirty a minute, and a tool that hammers a limiter and recovers from the
#: ``429`` is a tool that hides how close it is running to it.
CLASSIFICATION_PACE_SECONDS: Final[float] = 2.05

#: How many §7 sectors and §8 role categories the generated Speaker Request
#: targets. Two of each rather than one: with a single target every scorable
#: candidate lands on the same two-valued comparison and the shortlist is
#: decided by tie-breaking, and with a dozen the targets stop discriminating at
#: all. Two produces candidates that match both axes, one axis and neither,
#: which is the spread that makes a ranking readable.
SPEAKER_REQUEST_TARGETS: Final[int] = 2

#: The generated Speaker Request's date. Derived from the plan's own calendar
#: anchor rather than from ``date.today()``, for the reason
#: :data:`~pilot_dataset_plan.CALENDAR_ANCHOR` is a literal: a request whose date
#: moved between runs would resolve to a different ADR-0012 identity key and the
#: filing would stop being idempotent across a midnight boundary. Ninety days
#: after the anchor, so it reads as an event still being planned.
SPEAKER_REQUEST_LEAD_DAYS: Final[int] = 90


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
    professionals_without_classification: int = 0
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
    speaker_contacts_on_roster: int = 0
    speaker_contacts_reviewed: int = 0
    speaker_contacts_left_unreviewed: int = 0
    speaker_contacts_unclassifiable: int = 0
    speaker_request_id: str | None = None
    match_run_job: str | None = None
    match_run_id: str | None = None
    match_run_job_status: str | None = None
    match_run_scoring_mode: str | None = None
    match_run_candidates: int | None = None
    match_run_scored: int | None = None
    match_run_unscorable: int | None = None
    match_run_excluded: int | None = None
    match_run_excluded_reasons: dict[str, int] = field(default_factory=dict)
    match_run_portfolio_status: str | None = None
    match_run_shortlist: int | None = None
    notes: list[str] = field(default_factory=list)

    def lines(self) -> tuple[str, ...]:
        """The report, one fact per line."""
        return (
            f"seed                        {self.seed}",
            f"professionals               {self.professionals}",
            f"  no topic evidence         {self.professionals_without_topics} (deliberate)",
            f"  no location evidence      {self.professionals_without_location} (deliberate)",
            f"  no §7/§8 classification   {self.professionals_without_classification} (deliberate)",
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
            f"speaker contacts on roster {self.speaker_contacts_on_roster} (whole unit)",
            f"  classifications reviewed  {self.speaker_contacts_reviewed} (§19, now matchable)",
            f"  left unreviewed           {self.speaker_contacts_left_unreviewed} (deliberate)",
            f"  nothing to review         {self.speaker_contacts_unclassifiable} (unclassified)",
            f"speaker request filed       {self.speaker_request_id or 'not filed'}",
            f"match-run job               {self.match_run_job or 'not submitted'}",
            f"  job status                {self.match_run_job_status}",
            f"  match run                 {self.match_run_id}",
            f"  scoring mode              {self.match_run_scoring_mode}",
            f"  candidates named          {self.match_run_candidates}",
            f"  scored candidates         {self.match_run_scored}",
            f"  unscorable candidates     {self.match_run_unscorable} (reported, never zeroed)",
            f"  excluded candidates       {self.match_run_excluded} (never evaluated)",
            f"    by reason               {self.match_run_excluded_reasons or '{}'}",
            f"  portfolio status          {self.match_run_portfolio_status}",
            f"  shortlist                 {self.match_run_shortlist} speakers",
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


def _request_text(*, url: str, bearer_token: str, timeout: float = 60.0) -> tuple[int, str]:
    """One authenticated ``GET`` whose body is not JSON.

    Separate from :func:`_request` rather than a flag on it, because there is
    exactly one such body in this tool — the job event stream, which is
    ``text/event-stream`` — and folding a "decode or don't" switch into the
    general helper would make every other caller's return type a union.
    """
    request = urllib.request.Request(
        url=url, method="GET", headers={"Authorization": f"Bearer {bearer_token}"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace")
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
    required and ``company`` / ``title`` / ``expertise_tags`` / ``initials`` /
    ``primary_industry_code`` / ``primary_role_code`` optional. A professional
    with no expertise record contributes no ``expertise_tags`` key at all rather
    than an empty string: an absent column is an absent record, and a blank one
    is a record that says nothing, which are not the same claim. The same rule
    governs the two classification cells.

    Those two cells matter more than their size suggests. They are what
    ``pipeline_provisioning._stated_code`` reads on an accept, and without them
    every accepted contact arrives unclassified — the fixture classifier reads
    company and title text and this plan's organizations and titles are not
    taxonomy names — so §19 would hold the whole roster out of every pool and a
    match run would have nobody to score. The values are only *stated*, never
    reviewed: the accept records them as an ``inferred`` proposal, and a person
    has to confirm one before the speaker becomes matchable.
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
        if person.industry_code is not None:
            row["primary_industry_code"] = person.industry_code
        if person.role_code is not None:
            row["primary_role_code"] = person.role_code
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
# The match run — assembled from rows, because OQ-CBA-031 says a body may not
# ---------------------------------------------------------------------------


def match_roster(planned: Sequence[ProfessionalPlan]) -> tuple[ProfessionalPlan, ...]:
    """The slice imported, accepted, and named as the match run's candidate pool.

    Taken *after* the rows Phase A.2 leaves pending, so no professional is both
    an undecided review item and an accepted speaker contact. Overlapping the
    two would make the pending queue's size depend on how fast the accept ran,
    and would decide the same row twice on a re-run.

    A plain slice rather than a selection: which professionals carry topic text,
    a classification or neither is what makes the run's report interesting, and
    a generator that picked its own candidates on those grounds would be
    choosing the shortlist it wanted to demonstrate.
    """
    start = min(PENDING_IMPORT_ROWS, len(planned))
    return tuple(planned[start : start + MATCH_ROSTER_ROWS])


def reviews_classification(index: int) -> bool:
    """Whether roster member ``index`` gets its §19 classification review.

    Arithmetic rather than random, so the same roster reviews the same people on
    every run — the property ``decision_for`` exists for, applied to the other
    decision this tool makes on somebody's behalf.

    Four in five, and the fifth is not an oversight. Customer §19 orders review
    before availability, so an unreviewed contact is *absent* from every pool
    with the reason ``industry_classification_awaiting_review``. A generator that
    reviewed the whole roster would leave that state unreachable from generated
    data, and a Connector looking at the demo would never see the difference
    between "nobody has checked this record" and "we checked and they scored
    badly" — two situations that call for different actions.
    """
    return index % 5 != 4


def _frequent_codes(values: Sequence[str | None], *, wanted: int) -> list[str]:
    """The ``wanted`` most common non-null codes, ties broken by the code itself.

    Deterministic on purpose: ``collections.Counter.most_common`` breaks ties by
    insertion order, which for this caller is roster order, which changes with
    ``--professionals``. Sorting on the count *and* the code makes the Speaker
    Request's targets a function of the seed alone.
    """
    counts: dict[str, int] = {}
    for value in values:
        if value is not None:
            counts[value] = counts.get(value, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [code for code, _ in ranked[:wanted]]


def speaker_request_body(
    roster: Sequence[ProfessionalPlan],
    *,
    seed: int,
) -> dict[str, Any]:
    """Build the ``POST /v1/units/{unit_id}/speaker-requests`` body (customer §12).

    **Virtual**, and that is a statement about the generated data rather than a
    convenience. Customer §11 removes Proximity from the virtual model; the
    physical model measures miles from the CPP campus against a speaker's stored
    postal code, and this plan puts no postal code on anybody. A physical request
    would therefore produce a pool nobody has located — every candidate's
    distance an honest unknown — which is correct behaviour and a useless demo.
    The switch is the Speaker Request's to make, and this makes it deliberately.

    The industry and role targets are the roster's own most common codes. A
    request targeting a sector nobody on the roster holds would score every
    candidate the same defensible zero, and a shortlist drawn from that is
    tie-breaking rather than matching.

    ``description`` is §9's text — the thing a speaker's topic evidence is
    compared *against*. It names the request's own targets rather than reciting
    the tag vocabulary, because a description assembled out of the same twelve
    terms the speakers' expertise cells are drawn from would make the comparison
    a lexical overlap wearing a semantic factor's clothes.
    """
    industries = _frequent_codes(
        [person.industry_code for person in roster], wanted=SPEAKER_REQUEST_TARGETS
    )
    roles = _frequent_codes([person.role_code for person in roster], wanted=SPEAKER_REQUEST_TARGETS)
    if not industries or not roles:
        raise GeneratorError(
            "the planned roster states no §7 sector or no §8 role category at all, so no "
            "Speaker Request could name a target; check UNCLASSIFIED_INDUSTRY_SHARE and "
            "UNCLASSIFIED_ROLE_SHARE in tools/pilot_dataset_plan.py"
        )
    return {
        "title": f"Synthetic pilot speaker panel {seed}",
        "time_zone": PILOT_TIME_ZONE,
        "on_date": (CALENDAR_ANCHOR + timedelta(days=SPEAKER_REQUEST_LEAD_DAYS)).isoformat(),
        "is_virtual": True,
        "industry_codes": industries,
        "role_codes": roles,
        "description": (
            "A virtual panel for students weighing a first role: how professionals in "
            "these sectors and functions evaluate offers, build a first year, and decide "
            "what to specialise in."
        ),
    }


def match_run_body(
    *,
    speaker_request_id: uuid.UUID,
    candidate_subject_ids: Sequence[uuid.UUID],
    seed: int,
) -> dict[str, Any]:
    """Build one ``POST /v1/units/{unit_id}/match-runs`` submission.

    Four fields, and the interesting thing about this function is everything it
    does **not** build. There is no topic here, no location, no expertise, no
    event description and no physical/virtual switch, because OQ-CBA-031 took
    them all out of the request: every one is read from this tenant's own rows by
    ``smartmatch_api.match_run_evidence``. A body that could state a speaker's
    expertise is a body that can decide its own shortlist, and this tool
    submitting one would make the generated run a record of what the generator
    asserted rather than of what the appliance holds.

    ``candidate_subject_ids`` are ``speaker_profile.professional_id`` values the
    API handed back from its own roster listing — see :func:`resolve_candidates`
    — never ids derived here from a name. Naming somebody does not assert
    anything about them.

    ``portfolio_size`` is the G1 presentation rule's upper bound, taken from
    ``smartmatch_domain.explanation`` rather than typed in, so a shortlist that
    can be filled is filled.

    Raises:
        GeneratorError: the pool is over the route's own cap. Refused here
            rather than left to the ``400``, because the request model does not
            enforce the cap — ``maxItems`` sits in ``json_schema_extra``, which
            documents the limit for a schema reader and validates nothing — so a
            body that passed ``model_validate`` would still be rejected at the
            route, and a tool that only found out over HTTP would have written
            the whole dataset first.
    """
    if len(candidate_subject_ids) > MAX_CANDIDATES:
        raise GeneratorError(
            f"a match run may name at most {MAX_CANDIDATES} candidates; this pool holds "
            f"{len(candidate_subject_ids)}. Lower MATCH_ROSTER_ROWS."
        )
    return {
        "speaker_request_id": str(speaker_request_id),
        "portfolio_size": MAX_SHORTLIST_SIZE,
        "random_seed": seed % 1000,
        "candidate_subject_ids": [str(subject_id) for subject_id in candidate_subject_ids],
    }


def file_speaker_request(
    *,
    api_base: str,
    bearer_token: str,
    unit_id: uuid.UUID,
    body: Mapping[str, Any],
    report: RunReport,
) -> uuid.UUID:
    """File the Speaker Request a match run cannot exist without, and return its id.

    Both success codes are accepted and they mean different things. ``201`` filed
    a new request; ``200`` means ADR-0012's identity key — same host unit, same
    folded title, same date — resolved this onto a request already filed and
    updated it, which is the ordinary second-run path and is exactly why
    :data:`SPEAKER_REQUEST_LEAD_DAYS` is measured from a fixed calendar anchor.
    """
    status, payload = _request(
        method="POST",
        url=f"{api_base}/v1/units/{unit_id}/speaker-requests",
        bearer_token=bearer_token,
        body=body,
    )
    if status not in (200, 201) or not isinstance(payload, dict):
        raise GeneratorError(
            f"POST /v1/units/{unit_id}/speaker-requests answered {status}: {payload}"
        )
    request_id = uuid.UUID(str(payload["request_id"]))
    report.speaker_request_id = str(request_id)
    print(
        f"generate-pilot-dataset: speaker request {request_id} "
        f"({'filed' if status == 201 else 'already filed, updated'})"
    )
    return request_id


def list_speaker_contacts(
    *,
    api_base: str,
    bearer_token: str,
    unit_id: uuid.UUID,
) -> dict[str, dict[str, Any]]:
    """This unit's §13 roster, keyed by ``full_name``.

    Read back rather than derived. The import path does key a professional's
    identity off the folded name today — that is OQ-CBA-048's residual, not a
    contract — and a tool that recomputed the id would be asserting a derivation
    the API's own contract says a caller must not make. Asking the roster which
    id it holds costs one request and stays correct the day OQ-CBA-048 closes.

    A truncated listing is raised rather than silently used: a roster read that
    quietly returned its first two hundred rows would produce a candidate pool
    missing people nobody could account for.
    """
    status, payload = _request(
        method="GET",
        url=f"{api_base}/v1/units/{unit_id}/speaker-contacts",
        bearer_token=bearer_token,
    )
    if status != 200 or not isinstance(payload, dict):
        raise GeneratorError(
            f"GET /v1/units/{unit_id}/speaker-contacts answered {status}: {payload}"
        )
    if payload.get("truncated"):
        raise GeneratorError(
            "the speaker-contact roster is truncated, so the candidate pool this tool "
            "assembles would silently omit contacts; lower MATCH_ROSTER_ROWS or page the "
            "listing when the API grows a cursor"
        )
    return {str(contact["full_name"]): contact for contact in payload["contacts"]}


def review_classifications(
    *,
    api_base: str,
    bearer_token: str,
    unit_id: uuid.UUID,
    roster: Sequence[ProfessionalPlan],
    contacts: Mapping[str, Mapping[str, Any]],
    report: RunReport,
) -> None:
    """Perform customer §19's review step on four of every five roster members.

    The import recorded whatever code the export stated as an **inferred**
    proposal, and ``match_ineligibility_reason`` holds a proposal out of every
    pool until a person confirms it. This is that person, acting through the
    route built for it — not an ``UPDATE``, and not a widening of what counts as
    reviewed.

    Three outcomes, all counted:

    * reviewed — both axes confirmed, so the contact becomes match-eligible;
    * left unreviewed — deliberate, so the run reports somebody as
      ``industry_classification_awaiting_review`` rather than ranking them last;
    * nothing to review — the export stated no code on an axis, so there is no
      proposal to confirm and no value this tool is entitled to invent. The
      contact stays ineligible with ``industry_classification_missing``, which
      is the honest reason and a different one.
    """
    for index, person in enumerate(roster):
        contact = contacts.get(person.name)
        if contact is None:
            raise GeneratorError(
                f"the accepted roster member {person.name!r} is not in this unit's "
                "speaker-contact listing; the professionals accept did not provision a "
                "speaker_profile for them"
            )
        if not reviews_classification(index):
            report.speaker_contacts_left_unreviewed += 1
            continue
        if person.industry_code is None and person.role_code is None:
            # `ClassificationCorrection.create` refuses a correction naming
            # neither axis, and rightly: there is nothing here to confirm.
            report.speaker_contacts_unclassifiable += 1
            continue

        body: dict[str, str] = {}
        if person.industry_code is not None:
            body["primary_industry_code"] = person.industry_code
        if person.role_code is not None:
            body["primary_role_code"] = person.role_code

        professional_id = contact["professional_id"]
        status, payload = _request(
            method="POST",
            url=(
                f"{api_base}/v1/units/{unit_id}/speaker-contacts/{professional_id}/classification"
            ),
            bearer_token=bearer_token,
            body=body,
        )
        if status != 200:
            raise GeneratorError(
                f"POST /v1/units/{unit_id}/speaker-contacts/{professional_id}/classification "
                f"answered {status}: {payload}"
            )
        report.speaker_contacts_reviewed += 1
        time.sleep(CLASSIFICATION_PACE_SECONDS)


def resolve_candidates(
    roster: Sequence[ProfessionalPlan],
    contacts: Mapping[str, Mapping[str, Any]],
) -> tuple[uuid.UUID, ...]:
    """The ``professional_id`` of every roster member, as the API reported it.

    Every one of them, including the ones §19 will exclude. Naming only the
    eligible would hand the demo a pool that had already been filtered by this
    tool and a run that could not report an exclusion — and the exclusion
    reporting is the part of this surface that distinguishes "nobody has reviewed
    this record" from "we looked and they scored badly".
    """
    return tuple(uuid.UUID(str(contacts[person.name]["professional_id"])) for person in roster)


def wait_for_job(
    *,
    api_base: str,
    bearer_token: str,
    job_id: uuid.UUID,
    attempts: int,
    delay: float,
) -> str:
    """Poll one job to a terminal state and return that state.

    Returned rather than asserted, because the caller reports it: a job that
    ``failed`` is a fact about this appliance the run should print, not an
    exception that hides which of the run's phases had already succeeded.
    """
    last = "unknown"
    for attempt in range(1, attempts + 1):
        status, payload = _request(
            method="GET",
            url=f"{api_base}/v1/jobs/{job_id}",
            bearer_token=bearer_token,
        )
        if status != 200 or not isinstance(payload, dict):
            raise GeneratorError(f"GET /v1/jobs/{job_id} answered {status}: {payload}")
        last = str(payload["status"])
        if last in {"succeeded", "failed", "abandoned"}:
            print(f"generate-pilot-dataset: match-run job {last} on attempt {attempt}")
            return last
        time.sleep(delay)
    raise GeneratorError(
        f"match-run job {job_id} never left status {last!r}; check `docker compose logs worker`"
    )


def _completed_match_run_id(
    *,
    api_base: str,
    bearer_token: str,
    job_id: uuid.UUID,
) -> uuid.UUID | None:
    """The ``match_run_id`` from the job's own terminal event, or ``None``.

    Read from the job's event stream because that is where the completion
    summary lives and there is no route that lists a unit's match runs. Nothing
    is inferred from the ``202``: the acknowledgement carries a job id and says
    nothing about which run the job went on to write.
    """
    status, stream = _request_text(
        url=f"{api_base}/v1/jobs/{job_id}/events",
        bearer_token=bearer_token,
    )
    if status != 200:
        raise GeneratorError(f"GET /v1/jobs/{job_id}/events answered {status}: {stream[:400]}")
    for line in stream.splitlines():
        if not line.startswith("data: "):
            continue
        try:
            event = json.loads(line.removeprefix("data: "))
        except json.JSONDecodeError:  # pragma: no cover - a malformed frame is not fatal here
            continue
        body = event.get("payload", {})
        if body.get("type") == "job.completed":
            run_id = body.get("summary", {}).get("match_run_id")
            if run_id is not None:
                return uuid.UUID(str(run_id))
    return None


def submit_match_run(
    *,
    api_base: str,
    bearer_token: str,
    unit_id: uuid.UUID,
    body: Mapping[str, Any],
    request_id: str,
    attempts: int,
    delay: float,
    report: RunReport,
) -> None:
    """Submit the run, follow it to a terminal state, and report the shortlist.

    A ``202`` on its own proves the body was well formed and nothing else. What a
    stakeholder opens is the *persisted run*, so this follows the job to a
    terminal state and reads the run back — and reports the shortlist it found,
    including when that shortlist is thin. A green submission over an empty
    shortlist is not a working demo, and reporting it as one is the failure mode
    this whole phase exists to avoid.

    ``503 registry_not_ready`` is reported rather than raised. It means the
    factor registry on this appliance is not approved or not fully implemented,
    which is a deployment fact about the stack rather than a defect in the
    dataset the run had already generated.
    """
    status, payload = _request(
        method="POST",
        url=f"{api_base}/v1/units/{unit_id}/match-runs",
        bearer_token=bearer_token,
        body=body,
        request_id=request_id,
    )
    if status == 503 and isinstance(payload, dict) and "registry_not_ready" in str(payload):
        report.notes.append(
            "match run NOT submitted: the API answered 503 registry_not_ready, so this "
            "appliance's factor registry is not approved or not fully implemented. Every "
            "other phase above completed; the Connector surface has a filed Speaker "
            "Request and a reviewed roster and no run to open."
        )
        return
    if status == 422:
        # The route's ordinary answer when fewer candidates can be scored than
        # the requested shortlist needs. Reported rather than raised, and
        # reported as what it is: the appliance refusing to present a shortlist
        # it could not fill, which is ADR-0011 behaving correctly over a pool
        # OQ-CBA-061 emptied. Papering over it with a smaller portfolio_size
        # here would be this tool choosing a presentation rule.
        report.notes.append(
            "match run REFUSED with 422: fewer candidates could be scored than the "
            f"{MAX_SHORTLIST_SIZE}-speaker shortlist needs. The Connector surface has a "
            "filed Speaker Request and a reviewed roster and NO run to open. See the "
            f"OQ-CBA-061 note below — the API's answer was: {payload}"
        )
        return
    if status != 202 or not isinstance(payload, dict):
        raise GeneratorError(f"POST /v1/units/{unit_id}/match-runs answered {status}: {payload}")

    job_id = uuid.UUID(str(payload["job_id"]))
    report.match_run_job = str(job_id)
    report.match_run_scoring_mode = payload.get("scoring_mode")
    report.match_run_candidates = len(body["candidate_subject_ids"])
    report.match_run_scored = payload.get("scored_candidates")
    report.match_run_unscorable = payload.get("unscorable_candidates")

    excluded = payload.get("excluded_candidates") or []
    report.match_run_excluded = len(excluded)
    reasons: dict[str, int] = {}
    for entry in excluded:
        reason = str(entry.get("reason"))
        reasons[reason] = reasons.get(reason, 0) + 1
    report.match_run_excluded_reasons = reasons

    report.match_run_job_status = wait_for_job(
        api_base=api_base,
        bearer_token=bearer_token,
        job_id=job_id,
        attempts=attempts,
        delay=delay,
    )
    if report.match_run_job_status != "succeeded":
        report.notes.append(
            f"the match-run job finished {report.match_run_job_status!r} rather than "
            "'succeeded', so there is no persisted run for a stakeholder to open. The "
            "submission was accepted; the work was not completed."
        )
        return

    run_id = _completed_match_run_id(api_base=api_base, bearer_token=bearer_token, job_id=job_id)
    if run_id is None:
        report.notes.append(
            "the match-run job succeeded but its completion event named no match_run_id, "
            "so this tool cannot say what the shortlist holds"
        )
        return
    report.match_run_id = str(run_id)

    status, run = _request(
        method="GET",
        url=f"{api_base}/v1/units/{unit_id}/match-runs/{run_id}",
        bearer_token=bearer_token,
    )
    if status != 200 or not isinstance(run, dict):
        raise GeneratorError(
            f"GET /v1/units/{unit_id}/match-runs/{run_id} answered {status}: {run}"
        )
    report.match_run_portfolio_status = run.get("portfolio_status")
    report.match_run_shortlist = len(run.get("shortlist") or [])
    if not run.get("shortlist_available", True):
        report.notes.append(
            "the persisted run's shortlist could not be reconstructed: "
            f"{run.get('shortlist_unavailable_reason')}"
        )


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
    report.professionals_without_classification = summary.professionals_without_classification

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
    # Every fan-out row is forced to an in-list category. The ordinary plan
    # gives about one row in seven an out-of-list category on purpose, and an
    # out-of-list accept provisions nothing — so leaving this to chance would
    # make "did the fan-out get demonstrated at all" a coin toss on the seed.
    fanout = tuple(
        replace(event, category=IN_LIST_CATEGORIES[0])
        for event in build_events(FANOUT_IMPORT_ROWS, seed=args.seed + 1)
    )
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

    # -- Phase A.4: the roster a match run can actually name ----------------
    #
    # Imported and *accepted*, because an accept is what runs
    # `pipeline_provisioning` and therefore what writes the `speaker_profile`
    # rows `match_run_evidence` reads. Everything Phase B wrote is a
    # `user_account` and a unit link; neither is a speaker record, and a match
    # run naming one answers `speaker_profile_not_found`.
    roster = match_roster(professionals)
    if not roster:
        raise GeneratorError(
            f"--professionals {args.professionals} leaves no roster to match on after the "
            f"{PENDING_IMPORT_ROWS} rows Phase A.2 keeps pending"
        )
    roster_job = submit_import(
        api_base=api_base,
        bearer_token=args.bearer_token,
        unit_id=unit_id,
        dataset="professionals",
        rows=professionals_rows(roster),
        request_id=f"pilot-dataset-roster-{args.seed}",
    )
    roster_items = wait_for_review_items(
        session,
        tenant_id=tenant_id,
        job_id=roster_job,
        wanted=len(roster),
        attempts=args.dispatch_attempts,
        delay=2.0,
    )
    report.review_items_submitted += len(roster_items)
    for item_id in roster_items:
        _decide_one(
            api_base=api_base,
            bearer_token=args.bearer_token,
            item_id=item_id,
            decision="accepted",
            report=report,
        )
    contacts = list_speaker_contacts(
        api_base=api_base, bearer_token=args.bearer_token, unit_id=unit_id
    )
    report.speaker_contacts_on_roster = len(contacts)

    # -- Phase A.5: customer §19's review step ------------------------------
    review_classifications(
        api_base=api_base,
        bearer_token=args.bearer_token,
        unit_id=unit_id,
        roster=roster,
        contacts=contacts,
        report=report,
    )

    # -- Phase A.6: the Speaker Request, then the run against it ------------
    speaker_request_id = file_speaker_request(
        api_base=api_base,
        bearer_token=args.bearer_token,
        unit_id=unit_id,
        body=speaker_request_body(roster, seed=args.seed),
        report=report,
    )
    submit_match_run(
        api_base=api_base,
        bearer_token=args.bearer_token,
        unit_id=unit_id,
        body=match_run_body(
            speaker_request_id=speaker_request_id,
            candidate_subject_ids=resolve_candidates(roster, contacts),
            seed=args.seed,
        ),
        request_id=f"pilot-dataset-match-run-{args.seed}",
        attempts=args.dispatch_attempts,
        delay=2.0,
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
        "OQ-CBA-061: the fixture semantic-topic provider holds no recordings, so every "
        "candidate carrying expertise text scores unknown on customer §9, their composite "
        "is None (ADR-0011 rule 1), and they are reported UNSCORABLE rather than "
        "shortlisted. The shortlist above is therefore drawn from the minority of "
        "candidates who filed no expertise text at all. That is the open question's cost "
        "to this demo, not a defect in the generated data — and it is NOT worked around "
        "here by stripping topic text from the seed."
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
