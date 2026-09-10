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

What this tool does not populate, and why
------------------------------------------
``reward_item`` — the rewards catalog — is seeded separately, by
``tools/seed_pilot_rewards.py``, not by this tool. ``RewardsRepository`` does
have a writer now (``create_item``, authorized 7 September 2026 beside D6 in
``docs/plans/open-questions/cba-phase-deferred.md``), and this tool could call
it with the same arguments a caller supplied — but every catalog value the D6
worksheet says engineering "must not invent" (name, points cost, fulfilment
cost, budget owner, funded) would then have to come from a flag on *this*
tool's invocation too, and this generator's whole contract is that it invents
nothing an operator did not already accept elsewhere in the product's own
routes. So this run still produces real attendance-derived balances and an
**empty catalog** unless the operator has separately run
``make seed-pilot-rewards``, and therefore no redemption in any state unless
they have. That is reported at the end of every run rather than papered over.

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
This tool builds no topic provider at all — the name
``build_semantic_topic_provider`` appears nowhere in it as a call. The **API
process this tool submits its match run to** makes that call, in
``smartmatch_api.routers.match_runs._topic_provider``, which passes
``use_local_embedding=settings.cba_topic_local_embedding_enabled``. Left
unset that is ``False``, so the API gets the fixture semantic-topic
provider, which holds no recordings: a speaker carrying ``topic_text`` scores
``unknown`` on customer §9, ADR-0011 rule 1 makes their composite ``None``,
and they are reported as *unscorable* rather than shortlisted — while a
speaker who filled nothing in gets §9's stated policy neutral and is
shortlistable. The seed puts expertise text on most professionals, so most
named candidates are unscorable and the shortlist is filled from the quiet
minority. This was tracked as OQ-CBA-061; ADR-0017 dissolved it on 7
September 2026 by approving an offline, in-process embedding model
(`docs/plans/open-questions/cba-phase-deferred.md`), removing the cause
rather than answering it as a separate question. That model is reached only
when the API is started with ``SMARTMATCH_CBA_TOPIC_LOCAL_EMBEDDING_ENABLED``
set — nothing this generator passes can reach it, and nothing it passes can
prevent it either. The counts described above are the ones an API running
without that variable produces.

Every one of those counts is printed at the end of a run rather than smoothed
over. Stripping the seed's topic text would make the demo look fuller and is
**not** done here: it was one of two alternatives ADR-0017 rejected — the
other was ratifying a lexical comparator under the semantic provider's name —
and choosing either inside a generator would have been answering an open
question by writing code.

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
    FEEDBACK_SPEAKER_RESPONSE_SHAPE,
    FEEDBACK_STUDENT_COUNT,
    IN_LIST_CATEGORIES,
    EventPlan,
    FeedbackPlan,
    ProfessionalPlan,
    StudentPlan,
    build_events,
    build_professionals,
    build_speaker_feedback,
    build_students,
    feedback_plan_summary,
    feedback_student_external_subject,
    feedback_student_token,
    plan_summary,
    records_contact_channel,
)
from seed_demo_pipeline import (
    _SelectedJourney,
    advance_journey,
    resolve_tenant_id,
    resolve_unit_id,
)
from seed_pilot import (
    SeedConfigurationError,
    _existing_or_insert_membership,
    require_development_fixture_settings,
)
from smartmatch_api.config import Settings
from smartmatch_api.routers.match_runs import MAX_CANDIDATES
from smartmatch_domain.event_vocabulary import G3_VOCABULARY
from smartmatch_domain.events import DateOnlyTime, EventTime, ExactTime, UnresolvedTime
from smartmatch_domain.explanation import MAX_SHORTLIST_SIZE
from smartmatch_domain.pipeline import PipelineStage
from smartmatch_domain.student_speaker_feedback import (
    EditWindowState,
    feedback_anchor,
    resolve_edit_window,
)
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
#: The floor is the fixture semantic-topic provider's refusal (tracked as
#: OQ-CBA-061 until ADR-0017 dissolved it on 7 September 2026), and this is
#: the uncomfortable part. Only the professionals carrying *no* expertise text
#: can be scored at all — everyone else is ``unknown`` on customer §9 and
#: therefore unscorable — and the plan gives only
#: :data:`~pilot_dataset_plan.UNKNOWN_TOPIC_SHARE` of them no expertise text.
#: After the deliberate unreviewed fifth and the deliberate unclassified share
#: are taken out too, a roster of sixty yields exactly three scorable
#: candidates for a three-speaker shortlist: a demo one unlucky seed away from
#: a ``422``. A hundred yields five. The margin is thin because the fixture
#: path makes it thin — ADR-0017's offline embedding model would remove the
#: refusal, but only for a caller that passes ``use_local_embedding=True``,
#: which this generator does not — and widening it by removing topic text
#: from the seed is the workaround this file will not take.
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

#: How many Speaker Requests a run files, and therefore how many match runs it
#: submits and how many invitation batches it composes.
#:
#: It used to be one, and one was not enough to demonstrate the surface built on
#: top of it. The invitations page composes against a **recorded shortlist**, so
#: a single run means a single reachable shortlist: one batch, one set of
#: outcomes, and no way to see two batches in different states beside each
#: other. Three requests give the Connector surface a list rather than a row.
#:
#: Three rather than five, and the ceiling is arithmetic. Each run names the
#: whole reviewed roster as candidates and each is paced below; more runs is
#: more minutes for a demo that gains nothing after the third. Each is also one
#: more chance to meet the ``422`` this generator refuses to paper over — see
#: :func:`submit_match_run`.
SPEAKER_REQUEST_COUNT: Final[int] = 3

#: Seconds between match-run submissions. There is no per-unit match-run rate
#: limit to stay under; this exists so three runs against the same roster do not
#: arrive inside one second and contend on the same rows. A pace, not a retry.
MATCH_RUN_PACE_SECONDS: Final[float] = 1.05

#: Seconds between invitation-batch compositions.
#: ``INVITATION_BATCH_RATE_LIMIT`` allows twenty a minute; three batches cannot
#: approach that, and the pace is here for the reason
#: :data:`DECISION_PACE_SECONDS` gives — a tool that runs flat out against a
#: limiter is a tool that hides how close it is running to one.
INVITATION_BATCH_PACE_SECONDS: Final[float] = 3.05

#: Seconds between student feedback submissions. ``STUDENT_FEEDBACK_RATE_LIMIT``
#: allows thirty writes a minute and the whole of Phase C is a dozen or so
#: requests spread over a cohort, so this is well clear of it. It is here for
#: :data:`DECISION_PACE_SECONDS`'s reason and for one more: these requests each
#: authenticate as a *different* principal, and pacing them keeps the API's
#: quota accounting legible in a log rather than a burst.
FEEDBACK_PACE_SECONDS: Final[float] = 0.35

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
class MatchRunOutcome:
    """One Speaker Request, the run submitted against it, and the batch composed from it.

    One record per variant rather than one set of scalars on the report, because
    the whole point of filing more than one request is that the three differ:
    different §7/§8 targets produce different shortlists, and a batch composed
    from a thin shortlist and a batch composed from a full one are the two
    states a Connector needs to be able to tell apart.

    ``dispatched`` is a field and is always ``False``. It is recorded rather than
    omitted because "composed, not sent" is a real and reportable state of a
    batch, and a report with no such field would leave a reader to assume the
    messages went out. Nothing here dispatches: the outreach transport ships
    behind gate G4 (consent-origin policy, supervised recipient policy, and
    deliverability review approved), and ``smartmatch_providers.registry``
    refuses to construct an adapter until it opens.

    Attributes:
        variant: This request's ordinal, ``0``-based, and the offset into the
            roster's ranked §7/§8 codes its targets are drawn from.
        category: The in-list engagement category this request is named for.
            Presentation only — ``POST /v1/units/{id}/speaker-requests`` has no
            category field, and the counting rule reads a category off an
            *event* row, not off a request. It is here so three requests read as
            three different programmes rather than three copies.
        skip_reasons: Why each un-invited recipient produced no invitation,
            counted by reason. A skip is an outcome, not an error: see
            :func:`compose_invitation_batch`.
    """

    variant: int
    category: str
    speaker_request_id: str | None = None
    job: str | None = None
    job_status: str | None = None
    run_id: str | None = None
    scoring_mode: str | None = None
    candidates: int | None = None
    scored: int | None = None
    unscorable: int | None = None
    excluded: int | None = None
    excluded_reasons: dict[str, int] = field(default_factory=dict)
    portfolio_status: str | None = None
    shortlist: tuple[uuid.UUID, ...] = ()
    batch_id: str | None = None
    invited: int | None = None
    skipped: int | None = None
    skip_reasons: dict[str, int] = field(default_factory=dict)
    dispatched: bool = False
    notes: list[str] = field(default_factory=list)

    def lines(self) -> tuple[str, ...]:
        """This variant's block of the report, one fact per line."""
        return (
            f"request {self.variant + 1} ({self.category})",
            f"  speaker request           {self.speaker_request_id or 'not filed'}",
            f"  match-run job             {self.job or 'not submitted'}",
            f"    job status              {self.job_status}",
            f"    match run               {self.run_id}",
            f"    scoring mode            {self.scoring_mode}",
            f"    candidates named        {self.candidates}",
            f"    scored candidates       {self.scored}",
            f"    unscorable candidates   {self.unscorable} (reported, never zeroed)",
            f"    excluded candidates     {self.excluded} (never evaluated)",
            f"      by reason             {self.excluded_reasons or '{}'}",
            f"    portfolio status        {self.portfolio_status}",
            f"    shortlist               {len(self.shortlist)} speakers",
            f"  invitation batch          {self.batch_id or 'not composed'}",
            f"    invitations composed    {self.invited}",
            f"    recipients skipped      {self.skipped}",
            f"      by reason             {self.skip_reasons or '{}'}",
            f"    dispatched              {self.dispatched} (G4-gated; composed, not sent)",
        )


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
    contact_channels_recorded: int = 0
    contact_channels_activated: int = 0
    contact_channels_already_recorded: int = 0
    contacts_left_unreachable: int = 0
    match_runs: list[MatchRunOutcome] = field(default_factory=list)
    feedback_students: int = 0
    feedback_events: int = 0
    feedback_speakers: int = 0
    feedback_attendances: int = 0
    feedback_ratings_posted: int = 0
    feedback_ratings_amended: int = 0
    feedback_withheld: int = 0
    feedback_speakers_published: int = 0
    feedback_speakers_suppressed: int = 0
    feedback_unit_residual: int = 0
    feedback_unit_publishes: bool = False
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
            f"contact channels recorded   {self.contact_channels_recorded} (consented)",
            f"  activated                 {self.contact_channels_activated} (separate act)",
            f"  already recorded          {self.contact_channels_already_recorded} (re-run)",
            f"  left with NO channel      {self.contacts_left_unreachable} (deliberate)",
            f"speaker requests filed      {sum(1 for r in self.match_runs if r.speaker_request_id)}"
            f" of {len(self.match_runs)}",
            *(line for outcome in self.match_runs for line in outcome.lines()),
            f"feedback students           {self.feedback_students} (each holds its own token)",
            f"  events rated at           {self.feedback_events} (edit window still open)",
            f"  speakers rated            {self.feedback_speakers}",
            f"  attendance records        {self.feedback_attendances}",
            f"  ratings posted            {self.feedback_ratings_posted}",
            f"  ratings amended           {self.feedback_ratings_amended} (re-run)",
            f"  deliberately withheld     {self.feedback_withheld} (attended, said nothing)",
            f"  per-speaker published     {self.feedback_speakers_published}",
            f"  per-speaker SUPPRESSED    {self.feedback_speakers_suppressed} (below threshold)",
            f"  unit residual             {self.feedback_unit_residual}",
            f"  unit aggregate publishes  {self.feedback_unit_publishes}",
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
            ).attendance_id
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


def _frequent_codes(values: Sequence[str | None], *, wanted: int, offset: int = 0) -> list[str]:
    """The ``wanted`` most common non-null codes, ties broken by the code itself.

    Deterministic on purpose: ``collections.Counter.most_common`` breaks ties by
    insertion order, which for this caller is roster order, which changes with
    ``--professionals``. Sorting on the count *and* the code makes the Speaker
    Request's targets a function of the seed alone.

    ``offset`` slides the window down the ranking, and it is what makes
    :data:`SPEAKER_REQUEST_COUNT` requests differ from one another rather than
    being three copies of the same filing. It wraps: a roster holding fewer
    distinct codes than ``offset + wanted`` reaches around to the head rather
    than returning a short list, because a Speaker Request naming *fewer*
    targets than its siblings would score its candidates on a narrower
    comparison and the three runs would stop being comparable. Wrapping is
    stated here rather than left to a caller to notice.
    """
    counts: dict[str, int] = {}
    for value in values:
        if value is not None:
            counts[value] = counts.get(value, 0) + 1
    ranked = [code for code, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]
    if not ranked:
        return []
    return [ranked[(offset + step) % len(ranked)] for step in range(min(wanted, len(ranked)))]


def speaker_request_body(
    roster: Sequence[ProfessionalPlan],
    *,
    seed: int,
    variant: int = 0,
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

    ``variant`` selects one of :data:`SPEAKER_REQUEST_COUNT` sibling requests.
    It does three things and each is deliberate: it slides the §7/§8 target
    window down the roster's ranking (see :func:`_frequent_codes`), so the three
    runs score their candidates against genuinely different targets rather than
    producing one shortlist three times; it picks an in-list engagement category
    to name the request after; and it distinguishes the ADR-0012 identity key —
    same host unit, same folded title, same date — so filing three requests on
    one date does not resolve all three onto the first.

    The category is **presentation only**. There is no category field on
    ``POST /v1/units/{id}/speaker-requests``, and the ratified counting rule
    reads a category off an ``event`` row rather than off a request; naming one
    here would be inventing a field if it claimed to be anything more.

    Raises:
        ValueError: ``variant`` is negative.
    """
    if variant < 0:
        raise ValueError("variant must not be negative")
    category = IN_LIST_CATEGORIES[variant % len(IN_LIST_CATEGORIES)]
    industries = _frequent_codes(
        [person.industry_code for person in roster],
        wanted=SPEAKER_REQUEST_TARGETS,
        offset=variant * SPEAKER_REQUEST_TARGETS,
    )
    roles = _frequent_codes(
        [person.role_code for person in roster],
        wanted=SPEAKER_REQUEST_TARGETS,
        offset=variant * SPEAKER_REQUEST_TARGETS,
    )
    if not industries or not roles:
        raise GeneratorError(
            "the planned roster states no §7 sector or no §8 role category at all, so no "
            "Speaker Request could name a target; check UNCLASSIFIED_INDUSTRY_SHARE and "
            "UNCLASSIFIED_ROLE_SHARE in tools/pilot_dataset_plan.py"
        )
    return {
        "title": f"Synthetic pilot {category.lower()} panel {seed}-{variant + 1}",
        "time_zone": PILOT_TIME_ZONE,
        "on_date": (
            CALENDAR_ANCHOR + timedelta(days=SPEAKER_REQUEST_LEAD_DAYS + variant)
        ).isoformat(),
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
    outcome: MatchRunOutcome,
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
    outcome.speaker_request_id = str(request_id)
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
    outcome: MatchRunOutcome,
) -> None:
    """Submit the run, follow it to a terminal state, and record the shortlist.

    A ``202`` on its own proves the body was well formed and nothing else. What a
    stakeholder opens is the *persisted run*, so this follows the job to a
    terminal state and reads the run back — and records the shortlist it found,
    including when that shortlist is thin. A green submission over an empty
    shortlist is not a working demo, and reporting it as one is the failure mode
    this whole phase exists to avoid.

    The shortlist is **kept**, not merely counted, because the invitation batch
    this variant composes next is composed from it. That is the whole reason
    more than one request is filed: the invitations surface composes against a
    recorded shortlist, so one run is one reachable batch.

    ``503 registry_not_ready`` and ``422`` are recorded rather than raised. Both
    are the appliance answering honestly — the factor registry here is not
    approved, or fewer candidates could be scored than the shortlist needs — and
    both leave this variant with a filed request and no run, which is a state the
    report names rather than a failure that aborts the other two variants.
    """
    status, payload = _request(
        method="POST",
        url=f"{api_base}/v1/units/{unit_id}/match-runs",
        bearer_token=bearer_token,
        body=body,
        request_id=request_id,
    )
    if status == 503 and isinstance(payload, dict) and "registry_not_ready" in str(payload):
        outcome.notes.append(
            "match run NOT submitted: the API answered 503 registry_not_ready, so this "
            "appliance's factor registry is not approved or not fully implemented. This "
            "variant has a filed Speaker Request and no run to open."
        )
        return
    if status == 422:
        # The route's ordinary answer when fewer candidates can be scored than
        # the requested shortlist needs. Reported rather than raised, and
        # reported as what it is: the appliance refusing to present a shortlist
        # it could not fill, which is ADR-0011 behaving correctly over a pool
        # the fixture semantic-topic provider's refusal emptied (tracked as
        # OQ-CBA-061 until ADR-0017 dissolved it — see the note below).
        # Papering over it with a smaller portfolio_size here would be this
        # tool choosing a presentation rule.
        outcome.notes.append(
            "match run REFUSED with 422: fewer candidates could be scored than the "
            f"{MAX_SHORTLIST_SIZE}-speaker shortlist needs. This variant has a filed "
            "Speaker Request and NO run to open. See the OQ-CBA-061 note the run prints "
            f"— the API's answer was: {payload}"
        )
        return
    if status != 202 or not isinstance(payload, dict):
        raise GeneratorError(f"POST /v1/units/{unit_id}/match-runs answered {status}: {payload}")

    job_id = uuid.UUID(str(payload["job_id"]))
    outcome.job = str(job_id)
    outcome.scoring_mode = payload.get("scoring_mode")
    outcome.candidates = len(body["candidate_subject_ids"])
    outcome.scored = payload.get("scored_candidates")
    outcome.unscorable = payload.get("unscorable_candidates")

    excluded = payload.get("excluded_candidates") or []
    outcome.excluded = len(excluded)
    reasons: dict[str, int] = {}
    for entry in excluded:
        reason = str(entry.get("reason"))
        reasons[reason] = reasons.get(reason, 0) + 1
    outcome.excluded_reasons = reasons

    outcome.job_status = wait_for_job(
        api_base=api_base,
        bearer_token=bearer_token,
        job_id=job_id,
        attempts=attempts,
        delay=delay,
    )
    if outcome.job_status != "succeeded":
        outcome.notes.append(
            f"the match-run job finished {outcome.job_status!r} rather than 'succeeded', so "
            "there is no persisted run for a stakeholder to open. The submission was "
            "accepted; the work was not completed."
        )
        return

    run_id = _completed_match_run_id(api_base=api_base, bearer_token=bearer_token, job_id=job_id)
    if run_id is None:
        outcome.notes.append(
            "the match-run job succeeded but its completion event named no match_run_id, "
            "so this tool cannot say what the shortlist holds"
        )
        return
    outcome.run_id = str(run_id)

    status, run = _request(
        method="GET",
        url=f"{api_base}/v1/units/{unit_id}/match-runs/{run_id}",
        bearer_token=bearer_token,
    )
    if status != 200 or not isinstance(run, dict):
        raise GeneratorError(
            f"GET /v1/units/{unit_id}/match-runs/{run_id} answered {status}: {run}"
        )
    outcome.portfolio_status = run.get("portfolio_status")
    shortlist = run.get("shortlist") or []
    outcome.shortlist = tuple(uuid.UUID(str(entry["subject_id"])) for entry in shortlist)
    if not run.get("shortlist_available", True):
        outcome.notes.append(
            "the persisted run's shortlist could not be reconstructed: "
            f"{run.get('shortlist_unavailable_reason')}"
        )


# ---------------------------------------------------------------------------
# Phase D — contact channels, through the three acts the consent surface wants
# ---------------------------------------------------------------------------


def record_contact_channels(
    *,
    api_base: str,
    bearer_token: str,
    unit_id: uuid.UUID,
    roster: Sequence[ProfessionalPlan],
    contacts: Mapping[str, Mapping[str, Any]],
    report: RunReport,
) -> None:
    """Give half the roster an address an invitation may address. Two acts each.

    ``routers/cba_contact_channels.py`` is explicit that this is not one step,
    and this function does not shortcut it:

    1. **The create** — ``POST .../speaker-contacts/{professional_id}/channels``
       — records the address at ``consented``, naming an approved source and the
       evidence for it. A create may assert at most ``discovered`` (this unit
       holds the address and says nothing more) or ``consented`` (a named,
       dated, approved permission already exists). It may **never** create an
       ``active_candidate``.
    2. **The transition** — ``POST .../channels/{id}/transitions`` — moves
       ``consented -> active_candidate``, the single legal edge into the one
       state a send may address, carrying an actor.

    That second request is not ceremony and is not skippable. A row born
    sendable makes "who activated this person" a question with no answer, which
    is the exact defect the module's docstring says it exists to prevent. The
    only way to reach ``active_candidate`` is a recorded move, so this makes one.

    **What the evidence string says, and why it says it.** The consent evidence
    names this dataset and its reserved domain in words. It does not invent a
    form submission id, a date somebody signed something, or a coordinator's
    note about a conversation that did not happen — those would be fabricating
    precisely the evidence gate G4 exists to require, and an auditor following
    the trail would find a citation to nothing. What is true here is that a
    synthetic-pilot fixture recorded a synthetic address, and that is what the
    trail says. ``institutional_relationship`` is the approved source it is
    recorded under: these are a unit's own roster contacts on that unit's own
    campus fixture, which is the one of the four approved sources that describes
    a relationship rather than an act somebody took.

    **Half the roster, and the other half is deliberate.**
    :func:`~pilot_dataset_plan.records_contact_channel` decides which, so a
    remainder is left holding no channel at all and ``no_contact_channel``
    stays a visible skip on every composed batch. A roster where everybody is
    reachable would assert a consent coverage no real programme has.

    Nothing here sends. The synthetic-pilot authorization covers recording a
    channel and a consent; it does not cover dispatch, and dispatch stays behind
    gate G4.
    """
    for index, person in enumerate(roster):
        if not records_contact_channel(index):
            report.contacts_left_unreachable += 1
            continue
        contact = contacts.get(person.name)
        if contact is None:
            continue
        professional_id = uuid.UUID(str(contact["professional_id"]))
        base = f"{api_base}/v1/units/{unit_id}/speaker-contacts/{professional_id}/channels"

        status, payload = _request(
            method="POST",
            url=base,
            bearer_token=bearer_token,
            body={
                # Derived, never typed: the same `.invalid` address this run
                # already put on the account (RFC 2606, cannot resolve, cannot
                # be written to by accident).
                "address": synthetic_professional_email(professional_id),
                "contact_state": "consented",
                "consent_source": "institutional_relationship",
                "consent_evidence": (
                    "Synthetic pilot dataset: this address is generated on the reserved "
                    ".invalid domain by tools/generate_pilot_dataset.py and is not "
                    "deliverable. No real permission is asserted and no form submission "
                    "is cited."
                ),
                "reason": "Synthetic pilot fixture: recorded so an invitation batch has a "
                "reachable recipient to compose against.",
            },
        )
        if status == 409:
            # Already recorded on an earlier run, or suppressed. Either way this
            # tool does not record a second consent over it — that is the "we
            # got a new form" reasoning suppression exists to overrule.
            report.contact_channels_already_recorded += 1
            time.sleep(CLASSIFICATION_PACE_SECONDS)
            continue
        if status != 201 or not isinstance(payload, dict):
            raise GeneratorError(f"POST {base} answered {status}: {payload}")
        channel_id = payload["channel"]["contact_channel_id"]
        report.contact_channels_recorded += 1
        time.sleep(CLASSIFICATION_PACE_SECONDS)

        status, payload = _request(
            method="POST",
            url=f"{base}/{channel_id}/transitions",
            bearer_token=bearer_token,
            body={
                "to_state": "active_candidate",
                "reason": "Synthetic pilot fixture: activated as a separate recorded act, "
                "because a channel may never be created in this state.",
            },
        )
        if status != 201:
            raise GeneratorError(
                f"POST {base}/{channel_id}/transitions answered {status}: {payload}. The "
                "channel was recorded at 'consented' and NOT activated, so it cannot be "
                "addressed — which is the correct outcome for a failed activation, but "
                "leaves this run half done."
            )
        report.contact_channels_activated += 1
        time.sleep(CLASSIFICATION_PACE_SECONDS)


# ---------------------------------------------------------------------------
# Invitations — composed against a recorded shortlist, and never sent
# ---------------------------------------------------------------------------


def compose_invitation_batch(
    *,
    api_base: str,
    bearer_token: str,
    unit_id: uuid.UUID,
    seed: int,
    outcome: MatchRunOutcome,
) -> None:
    """Compose one invitation per shortlisted speaker, through the real route.

    ``POST /v1/units/{unit_id}/speaker-invitations/batches``, with the
    ``Idempotency-Key`` header the route requires. That header is required
    rather than defaulted for a reason worth restating at the place it is
    supplied: on this surface a retry without one is a *second batch*, and a
    second batch is a second message to everybody in the first. The key is
    derived from the seed and the variant, so a re-run replays the first
    submission's decisions instead of composing again.

    **Nothing is dispatched.** ``201`` means the batch and every outcome in it
    are rows a Connector can read back; it does not mean a message left the
    building, and this tool does not ask for one to. Outreach ships behind gate
    G4 — consent-origin policy, supervised recipient policy and deliverability
    review, all approved — and ``smartmatch_providers.registry`` refuses to
    construct a transport until it opens. "Composed, not sent" is therefore the
    true state of every batch this generator produces, and
    :attr:`MatchRunOutcome.dispatched` records it as a fact rather than leaving
    a reader to assume otherwise.

    **Every recipient may be skipped on a freshly generated appliance, and that
    is not a defect.** A batch invites somebody only if they hold a contact
    channel that is ``active_candidate``, carries an approved consent source and
    is unsuppressed. Nothing in the import path writes a ``contact_channel``
    row — ``smartmatch_api.pipeline_provisioning`` says so itself — and this
    generator will not write one either: a consent origin is precisely the kind
    of evidence ADR-0011 and gate G4 forbid a generator from manufacturing. So
    the honest outcome is a real batch holding real skips, each carrying the
    reason that names the condition which failed, and the report prints them by
    reason. Seeding a consent to make the number look better would be inventing
    the one piece of evidence this entire surface exists to respect.

    No batch is composed when the run produced no shortlist. A batch needs at
    least one recipient (``professional_ids`` is ``min_length=1``), and picking
    one by hand would make the batch a record of this tool's choice rather than
    of the run's.
    """
    if not outcome.shortlist:
        outcome.notes.append(
            "no invitation batch composed: this variant has no recorded shortlist to "
            "compose against, and a hand-picked recipient list would make the batch a "
            "record of this tool's choice rather than of the run's."
        )
        return

    status, payload = _request(
        method="POST",
        url=f"{api_base}/v1/units/{unit_id}/speaker-invitations/batches",
        bearer_token=bearer_token,
        body={
            "professional_ids": [str(subject_id) for subject_id in outcome.shortlist],
            "match_run_id": outcome.run_id,
            "event_name": f"Synthetic pilot {outcome.category.lower()} panel",
            # Stored and rendered verbatim, never parsed — the field's own
            # contract. A date formatted for a person to read, not an instant.
            "event_date": (
                CALENDAR_ANCHOR + timedelta(days=SPEAKER_REQUEST_LEAD_DAYS + outcome.variant)
            ).strftime("%d %B %Y"),
            # A display name, not an identity: who *submitted* the batch is the
            # authenticated caller and is recorded separately, so this cannot
            # attribute the batch to somebody else.
            "coordinator_name": "Synthetic Pilot Speaker Connector",
        },
        request_id=f"pilot-dataset-invitations-{seed}-{outcome.variant + 1}",
    )
    if status != 201 or not isinstance(payload, dict):
        raise GeneratorError(
            f"POST /v1/units/{unit_id}/speaker-invitations/batches answered {status}: {payload}"
        )

    outcome.batch_id = str(payload["batch_id"])
    outcome.invited = payload.get("invited_count")
    outcome.skipped = payload.get("skipped_count")

    skip_reasons: dict[str, int] = {}
    for entry in payload.get("invitations") or []:
        reason = entry.get("skip_reason")
        if reason is not None:
            skip_reasons[str(reason)] = skip_reasons.get(str(reason), 0) + 1
    outcome.skip_reasons = skip_reasons

    if payload.get("replayed"):
        outcome.notes.append(
            "the invitation batch was REPLAYED: this idempotency key had already composed "
            "a batch, so nothing was recomposed and the outcomes above are the first "
            "submission's. That is the key doing its job, not a failure."
        )
    print(
        f"generate-pilot-dataset: invitation batch {outcome.batch_id} "
        f"({outcome.invited} composed, {outcome.skipped} skipped, not dispatched)"
    )
    time.sleep(INVITATION_BATCH_PACE_SECONDS)


# ---------------------------------------------------------------------------
# Phase C — student speaker feedback, through the student's own route
# ---------------------------------------------------------------------------
#
# Phase A goes through the API because a caller-facing writer exists. Phase B
# goes through repositories because for those tables none does. Phase C is a
# third case and belongs with Phase A: there is a real student route, and the
# reason to use it is stronger here than anywhere else in this file.
#
# `routers/student_speaker_feedback.py` takes `student_id` from the verified
# principal and from nowhere else — there is no request field a caller could put
# somebody else's id in, which is the structural guarantee against MM-A01's
# caller-selected identity. A generator that wrote `student_speaker_feedback`
# rows through a repository would be exercising none of that: not the
# attendance check, not the roster check, not the seven-day edit window, and not
# the one thing the surface is built to make impossible. So every rating below
# is a POST somebody's own bearer token made.
#
# That costs real principals — an account, a `student` membership, a token in
# SMARTMATCH_DEV_PRINCIPALS — and the cost is the point.


def feedback_window_state(event: EventPlan, *, now: datetime) -> EditWindowState:
    """Where ``event`` sits in the seven-day window, by the domain's own rule.

    ``feedback_anchor`` and ``resolve_edit_window`` are imported and called
    rather than reimplemented, because the anchor is not the obvious thing: for
    an exact event it is the stated end or else the start, and for a date-only
    event it is **midnight at the end of that day, in UTC** — the event's own
    time zone deliberately ignored. A tool that guessed "the event's date plus
    seven" would be right most of the time and would silently produce a run
    whose ratings the API refuses with ``409``.
    """
    anchor = feedback_anchor(
        time_precision=(
            "unresolved"
            if event.on_date is None
            else ("exact" if event.exact_hour is not None else "date_only")
        ),
        starts_at=(
            None
            if event.on_date is None or event.exact_hour is None
            else datetime.combine(
                event.on_date, clock_time(hour=event.exact_hour), tzinfo=ZoneInfo(PILOT_TIME_ZONE)
            )
        ),
        ends_at=None,
        on_date=event.on_date if event.exact_hour is None else None,
    )
    return resolve_edit_window(anchor=anchor, now=now).state


def feedback_events(
    events: Sequence[tuple[EventPlan, uuid.UUID]],
    *,
    now: datetime,
    wanted: int,
) -> tuple[tuple[EventPlan, uuid.UUID], ...]:
    """The events a rating can still be written against, most recent first.

    Only events whose window is genuinely ``OPEN``. Two states are deliberately
    excluded and each for its own reason:

    * ``CLOSED`` — the API answers ``409 student_feedback_window_closed``, and
      most of the generated calendar is closed because the plan spreads six
      months *back* from a fixed anchor. That is the calendar being honest, not
      a defect, and this phase works with whatever is still open.
    * ``UNKNOWN`` — an ADR-0010 unresolved event, whose window ``permits_change``
      because there is no anchor to have closed. Writable, and not used here: a
      rating of a speaker at an event with no date is exactly the case OQ-CBA-052
      is open on, and a generator picking a side of an open question by writing
      rows into it would be answering it in code.

    Returns fewer than ``wanted`` without complaint — the caller decides whether
    that is enough. Returns them newest-first so a demo's ratings cluster on the
    events a viewer is most likely to open.

    Raises:
        GeneratorError: nothing is open at all. Raised rather than skipped
            because it means one specific thing worth saying out loud: the
            plan's fixed ``CALENDAR_ANCHOR`` has aged more than seven days into
            the past, so no generated event can be rated any more and this phase
            can never produce a row until that literal moves.
    """
    open_events = [
        (event, event_id)
        for event, event_id in events
        if event.resolved and feedback_window_state(event, now=now) is EditWindowState.OPEN
    ]
    if not open_events:
        raise GeneratorError(
            "no generated event still has an open feedback window, so no rating could be "
            "written through the student route. The plan's CALENDAR_ANCHOR "
            f"({CALENDAR_ANCHOR.isoformat()}) is a fixed literal and the window is seven "
            "days wide, so once the anchor is more than a week past, every generated "
            "event is closed. Move CALENDAR_ANCHOR in tools/pilot_dataset_plan.py — do "
            "not widen the window, which is a ratified decision."
        )
    open_events.sort(key=lambda pair: pair[0].on_date or CALENDAR_ANCHOR, reverse=True)
    return tuple(open_events[:wanted])


def feedback_speakers(
    roster: Sequence[ProfessionalPlan],
    contacts: Mapping[str, Mapping[str, Any]],
    *,
    wanted: int,
) -> tuple[tuple[str, uuid.UUID], ...]:
    """The speakers this phase rates, as ``(name, professional_id)`` pairs.

    Taken from the §13 roster listing this run already read back — the same
    mapping :func:`resolve_candidates` uses — so **no speaker id is derived
    here and no student-scoped roster read is added**. That matters beyond
    tidiness: OQ-CBA-064 concerns what a student may be told about a unit's
    roster, and a seeder that asked the student surface "who spoke?" would be
    exercising a read the open question has not settled. The seeder already
    holds the ids it caused to exist, so it uses those.

    A plain prefix of the roster rather than a selection. Which speakers get
    which counts is :data:`~pilot_dataset_plan.FEEDBACK_SPEAKER_RESPONSE_SHAPE`'s
    decision, and choosing *who* on any other grounds — the best scored, the
    most reviewed — would make the published aggregate a statement about this
    tool's taste.
    """
    chosen: list[tuple[str, uuid.UUID]] = []
    for person in roster:
        contact = contacts.get(person.name)
        if contact is None:
            continue
        chosen.append((person.name, uuid.UUID(str(contact["professional_id"]))))
        if len(chosen) == wanted:
            break
    return tuple(chosen)


def write_feedback_students(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    unit_path: str,
    events: Sequence[tuple[EventPlan, uuid.UUID]],
    count: int,
    report: RunReport,
) -> dict[int, uuid.UUID]:
    """Create the feedback cohort and record their attendance. Returns rank -> account id.

    Three writes per student, and each one is required by a different check the
    route makes:

    1. **The account**, through ``ProfessionalIdentityRepository.ensure_account``
       — the compromise ``write_students`` already states and for the same
       reason: no student-identity writer exists in the application, and this is
       the only ``user_account`` writer that accepts a caller-supplied id, which
       is what determinism needs. Its ``external_subject`` is the *stable*
       string :func:`~pilot_dataset_plan.feedback_student_external_subject`
       derives from a rank alone, rather than the tenant-and-unit-derived one
       the ordinary students carry, because the rebuild script has to put that
       subject into ``SMARTMATCH_DEV_PRINCIPALS`` before any tenant uuid exists.
    2. **A ``student`` membership on this unit**, through ``seed_pilot``'s own
       insert-or-verify helper rather than an ``UPDATE`` of this tool's own.
       That helper refuses to change a membership that already exists with
       different values, which is the behaviour wanted here: a re-run must not
       quietly reassign a server-assigned role. Without a membership the route
       answers ``403 forbidden`` — the role is what authorizes, and a token
       proves only who you are.
    3. **Attendance at each rated event.** ``eligibility`` requires an
       ``attendance_record`` for this student at this event and applies no status
       filter; without one the route answers ``403
       student_feedback_not_eligible``. The method is
       ``SYNTHETIC_ATTENDANCE_METHOD``, the same value every other synthetic
       attendance in this file carries — no attendance method is invented here.

    No ``link_to_unit`` call is made, exactly as in :func:`write_students`: a
    student is not a professional, and a row in
    ``professional_unit_relationship`` would put them in a fan-out pool.
    """
    accounts = ProfessionalIdentityRepository()
    attendance = AttendanceRepository()
    subject_ids: dict[int, uuid.UUID] = {}

    for rank in range(1, count + 1):
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
        for _, event_id in events:
            attendance.record_attendance(
                session,
                tenant_id=tenant_id,
                owning_unit_id=unit_id,
                subject_id=subject_id,
                event_id=event_id,
                method=SYNTHETIC_ATTENDANCE_METHOD,
            )
            report.feedback_attendances += 1
        subject_ids[rank] = subject_id
        report.feedback_students += 1
        session.commit()

    return subject_ids


def post_speaker_feedback(
    *,
    api_base: str,
    unit_id: uuid.UUID,
    planned: Sequence[FeedbackPlan],
    speakers: Sequence[tuple[str, uuid.UUID]],
    events: Sequence[tuple[EventPlan, uuid.UUID]],
    report: RunReport,
) -> None:
    """Post each planned rating as the student who holds it.

    One ``POST`` per planned rating, each authenticated with **that student's
    own** bearer token. ``201`` created it, ``200`` amended or repeated one —
    both are success, and the second is the ordinary re-run path, since the
    natural key ``(tenant, student, event, speaker)`` makes a second submission
    an edit of the caller's own rating rather than a second vote.

    A planned entry whose ``rating`` is ``None`` produces **no request at all**.
    Not a request carrying a zero, not a withdrawal, not a row in any state:
    nothing. That is the whole of what a deliberately withheld rating means, and
    it is why the loop's silence is explicit here rather than filtered out by
    the caller — a reader of this function should see the branch that does
    nothing.

    Each speaker is rated at one event, chosen by rotating through the events
    with open windows. The natural key includes the event, so two speakers
    sharing an event is fine and a speaker appearing at two would be two
    separate ratings from the same student — which the plan does not ask for.
    """
    for entry in planned:
        if entry.rating is None:
            # Deliberate silence. ADR-0011 rule 1: no evidence, no row, and
            # certainly not a zero. This branch exists to be seen.
            report.feedback_withheld += 1
            continue

        _, speaker_id = speakers[entry.speaker_rank % len(speakers)]
        _, event_id = events[entry.speaker_rank % len(events)]
        token = feedback_student_token(entry.student_rank)
        status, payload = _request(
            method="POST",
            url=(
                f"{api_base}/v1/units/{unit_id}/student/events/{event_id}"
                f"/speakers/{speaker_id}/feedback"
            ),
            bearer_token=token,
            # No comment. A rating is a number a student chose; a sentence
            # attributed to a synthetic student is a quotation nobody said, and
            # this generator has no business writing one.
            body={"rating": entry.rating},
        )
        if status == 201:
            report.feedback_ratings_posted += 1
        elif status == 200:
            report.feedback_ratings_amended += 1
        else:
            raise GeneratorError(
                f"POST .../student/events/{event_id}/speakers/{speaker_id}/feedback answered "
                f"{status} for feedback student {entry.student_rank}: {payload}. A 401 means "
                "this token is not in the API process's SMARTMATCH_DEV_PRINCIPALS (it is read "
                "once at startup); a 403 means the student holds no membership on this unit or "
                "no attendance record at this event; a 409 means the seven-day edit window "
                "closed."
            )
        time.sleep(FEEDBACK_PACE_SECONDS)

    report.feedback_speakers = len(speakers)
    report.feedback_events = len(events)


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
        "--feedback-students",
        type=int,
        default=FEEDBACK_STUDENT_COUNT,
        help=(
            "How many of the feedback cohort to create. Each needs a matching entry in the "
            "API process's SMARTMATCH_DEV_PRINCIPALS, so lowering this is safe and raising "
            "it above the cohort the plan derives tokens for is refused."
        ),
    )
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

    # -- Phase D: contact channels, before anything composes an invitation --
    #
    # Deliberately BEFORE the batches below. A batch resolves each recipient's
    # channel at the moment it composes, so a channel recorded afterwards would
    # change nothing about the outcomes already stored, and every batch would
    # hold nothing but skips. Half the roster is left unreachable on purpose, so
    # the batches carry a mix rather than being uniformly one or the other.
    record_contact_channels(
        api_base=api_base,
        bearer_token=args.bearer_token,
        unit_id=unit_id,
        roster=roster,
        contacts=contacts,
        report=report,
    )

    # -- Phase A.6: several Speaker Requests, a run each, a batch each ------
    #
    # Several rather than one, because the invitations surface composes against
    # a *recorded shortlist*: one run is one reachable shortlist, one batch, and
    # no way to see two batches beside each other. Each variant targets a
    # different slice of the roster's ranked §7/§8 codes, so the three runs
    # score against genuinely different targets rather than repeating one.
    #
    # The candidate pool is the same reviewed roster every time and is resolved
    # once. Naming the same people against different targets is the comparison
    # worth demonstrating; re-resolving it per variant would only risk the three
    # runs disagreeing about who was even considered.
    candidate_subject_ids = resolve_candidates(roster, contacts)
    for variant in range(SPEAKER_REQUEST_COUNT):
        body = speaker_request_body(roster, seed=args.seed, variant=variant)
        outcome = MatchRunOutcome(
            variant=variant,
            category=IN_LIST_CATEGORIES[variant % len(IN_LIST_CATEGORIES)],
        )
        report.match_runs.append(outcome)

        speaker_request_id = file_speaker_request(
            api_base=api_base,
            bearer_token=args.bearer_token,
            unit_id=unit_id,
            body=body,
            outcome=outcome,
        )
        submit_match_run(
            api_base=api_base,
            bearer_token=args.bearer_token,
            unit_id=unit_id,
            body=match_run_body(
                speaker_request_id=speaker_request_id,
                candidate_subject_ids=candidate_subject_ids,
                seed=args.seed + variant,
            ),
            request_id=f"pilot-dataset-match-run-{args.seed}-{variant + 1}",
            attempts=args.dispatch_attempts,
            delay=2.0,
            outcome=outcome,
        )
        compose_invitation_batch(
            api_base=api_base,
            bearer_token=args.bearer_token,
            unit_id=unit_id,
            seed=args.seed,
            outcome=outcome,
        )
        time.sleep(MATCH_RUN_PACE_SECONDS)

    report.notes.append(
        "contact channels: half the roster holds an activated channel and half holds NONE, "
        "so every batch above carries a mix of composed invitations and honest "
        "`no_contact_channel` skips. Each activated channel took the two acts the consent "
        "surface requires — a create at `consented` naming an approved source and its "
        "evidence, then a separate recorded transition to `active_candidate`, which a "
        "create may never assert. The evidence string names this dataset and its reserved "
        ".invalid domain rather than citing a form submission that does not exist."
    )
    report.notes.append(
        "NO invitation batch was dispatched, and none was meant to be. Composing writes "
        "the batch and its outcomes as rows a Connector can read back; sending is a "
        "separate operation behind gate G4 (consent-origin policy, supervised recipient "
        "policy, deliverability review), and smartmatch_providers.registry refuses to "
        "construct a transport until that gate opens. Every batch above is therefore "
        "genuinely 'composed, not sent' — a true state of this surface, not a step this "
        "run skipped."
    )

    # -- Phase C: student speaker feedback, through the student's own route --
    #
    # After the roster exists, because a rating names a speaker who has to be on
    # it, and after the events exist, because a rating names an event the
    # student has to have attended.
    feedback_plan = build_speaker_feedback(seed=args.seed)
    feedback_summary = feedback_plan_summary(feedback_plan)
    report.feedback_withheld = 0  # counted per entry below, not copied from the plan
    report.feedback_speakers_published = feedback_summary.speakers_published
    report.feedback_speakers_suppressed = feedback_summary.speakers_suppressed
    report.feedback_unit_residual = feedback_summary.unit_residual
    report.feedback_unit_publishes = feedback_summary.unit_publishes

    rated_events = feedback_events(
        written_events,
        now=datetime.now(UTC),
        wanted=len(FEEDBACK_SPEAKER_RESPONSE_SHAPE),
    )
    rated_speakers = feedback_speakers(
        roster, contacts, wanted=len(FEEDBACK_SPEAKER_RESPONSE_SHAPE)
    )
    if not rated_speakers:
        raise GeneratorError(
            "no roster member could be rated: the §13 listing named none of the accepted "
            "professionals, so the accept did not provision speaker_profile rows"
        )
    feedback_students = write_feedback_students(
        session,
        tenant_id=tenant_id,
        unit_id=unit_id,
        unit_path=args.unit_path,
        events=rated_events,
        count=args.feedback_students,
        report=report,
    )
    print(
        f"generate-pilot-dataset: feedback cohort of {len(feedback_students)} rating "
        f"{len(rated_speakers)} speakers across {len(rated_events)} open-window events"
    )
    post_speaker_feedback(
        api_base=api_base,
        unit_id=unit_id,
        planned=feedback_plan,
        speakers=rated_speakers,
        events=rated_events,
        report=report,
    )

    report.notes.append(
        "student feedback: the per-speaker aggregate publishes for "
        f"{feedback_summary.speakers_published} speakers and is SUPPRESSED for "
        f"{feedback_summary.speakers_suppressed}, because fewer than "
        "MIN_RESPONSES_FOR_AGGREGATE students rated them. A suppressed aggregate carries "
        "no count and no mean — not a zero, which is a thing no student can say. The unit "
        f"aggregate publishes ({feedback_summary.unit_publishes}) with a residual of "
        f"{feedback_summary.unit_residual}: the pooled count minus every published "
        "per-speaker count, which is the only quantity a reader can form by subtracting "
        "what this API publishes from what it publishes, and it is 0 or >= 3 by design. "
        f"{feedback_summary.withheld} of {feedback_summary.opportunities} students who "
        "attended and could have rated a speaker deliberately did not — those speakers' "
        "counts are lower than the number of people who saw them, on purpose."
    )

    report.notes.append(
        "rewards catalog left EMPTY by this tool: `reward_item` rows are seeded "
        "separately, by `make seed-pilot-rewards` (tools/seed_pilot_rewards.py), whose "
        "every value — name, points cost, fulfilment cost, budget owner, funded — is a "
        "required argument the operator supplies from the worksheet "
        "(docs/pilot-data/rewards-catalog-worksheet.md), never invented by this "
        "generator. Run it separately if a redemption should be openable. The balances "
        "above are real and attendance-derived; the catalog is not missing by accident."
    )
    report.notes.append(
        "OQ-CBA-061 (dissolved 7 September 2026 by ADR-0017): this generator calls the "
        "fixture semantic-topic provider, which holds no recordings, so every candidate "
        "carrying expertise text scores unknown on customer §9, their composite is None "
        "(ADR-0011 rule 1), and they are reported UNSCORABLE rather than shortlisted. The "
        "shortlist above is therefore drawn from the minority of candidates who filed no "
        "expertise text at all. That was the open question's cost to this demo, not a "
        "defect in the generated data. ADR-0017 approved an offline embedding model that "
        "removes the refusal, but only via use_local_embedding=True, which this generator "
        "does not pass — so the cost above is unchanged, and it is NOT worked around here "
        "by stripping topic text from the seed."
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
