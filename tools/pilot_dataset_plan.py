#!/usr/bin/env python3
"""Deterministic *plan* for the synthetic pilot dataset — pure, no database.

This module answers one question and stores nothing: **given a seed, which
synthetic rows should exist?** Every function here is a pure computation over
its arguments, so the shape of the demo dataset can be tested — its scale, its
distributions, and above all the fraction of it that is deliberately missing —
without a PostgreSQL instance anywhere in sight.
``tools/generate_pilot_dataset.py`` is the writer that takes this plan and puts
it through the product's own repositories and routes.

Why a separate module
---------------------
The generator's interesting property is not that it can execute SQL; it is
that the *numbers* it produces are believable and reproducible. Keeping the
derivation pure is what lets ``tests/unit/test_pilot_dataset_plan.py`` assert
"the same seed twice is the same plan", "about a tenth of the professionals
carry no topic evidence at all", and "some events are ADR-0010 ``unresolved``"
in milliseconds and with no fixture file committed to the repository. That last
point is not incidental: a committed dataset of a few hundred rows is a
realistic place for a secret scanner to fire on a random-looking identifier,
and there is no identifier here to fire on — the data is derived at run time
from an integer.

Obviously synthetic, deliberately
---------------------------------
Every name below is a historical figure's given name paired with an invented
surname (``"Ada Thornquist"``), so no row can be mistaken for a real person's
record. Emails and external subjects are derived by
``smartmatch_domain.synthetic_pilot`` onto the reserved ``.invalid`` TLD (RFC
2606) and are never deliverable. Organizations are invented. Metro regions and
their coordinates are ordinary place names, which are not personal data and
match the spelling the existing fixtures under ``docs/pilot-data/fixtures/``
already use.

Unknowns are part of the plan, not a gap in it
----------------------------------------------
ADR-0011 requires that a value with no evidence renders as ``unknown`` and
never as ``0``. A dataset in which every record is complete would hide that
behaviour completely — the demo would look full and would prove nothing. So a
fixed fraction of this plan carries no evidence *on purpose*:
:data:`UNKNOWN_TOPIC_SHARE` of professionals have no expertise record at all
(``topics=None``, which is not ``()``), :data:`UNKNOWN_LOCATION_SHARE` have no
coordinates, :data:`UNCLASSIFIED_INDUSTRY_SHARE` and
:data:`UNCLASSIFIED_ROLE_SHARE` have no §7/§8 classification on one axis or the
other, and :data:`UNRESOLVED_EVENT_SHARE` of events have no resolvable date
(ADR-0010 ``unresolved``). :func:`plan_summary` reports those fractions so a run
can say out loud how much of what it wrote is deliberately unmeasured.

Where the classification codes come from
----------------------------------------
:attr:`ProfessionalPlan.industry_code` and :attr:`ProfessionalPlan.role_code`
are drawn from the **released** taxonomies —
``smartmatch_domain.naics_sectors.SECTOR_CODES`` (customer §7) and
``smartmatch_domain.cba_role_categories.ROLE_CATEGORY_CODES`` (§8) — imported
rather than restated. A second copy of those lists here would drift, and a code
this module invented would be dropped by
``smartmatch_api.pipeline_provisioning._stated_code`` on the way in: the
professional would arrive unclassified, §19 would hold them out of every pool,
and the plan would have no way to know it had happened.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final

from smartmatch_domain.cba_role_categories import ROLE_CATEGORY_CODES
from smartmatch_domain.naics_sectors import SECTOR_CODES

__all__ = [
    "CALENDAR_ANCHOR",
    "DEFAULT_SEED",
    "EVENT_LOCATION",
    "FEEDBACK_RATING_DISTRIBUTION",
    "FEEDBACK_SPEAKER_RESPONSE_SHAPE",
    "FEEDBACK_STUDENT_COUNT",
    "FEEDBACK_WITHHELD_SHARE",
    "IN_LIST_CATEGORIES",
    "OUT_OF_LIST_CATEGORIES",
    "EventPlan",
    "FeedbackPlan",
    "FeedbackSummary",
    "PlanSummary",
    "ProfessionalPlan",
    "StudentPlan",
    "build_events",
    "build_professionals",
    "build_speaker_feedback",
    "build_students",
    "feedback_dev_principals",
    "feedback_plan_summary",
    "feedback_student_external_subject",
    "feedback_student_token",
    "plan_summary",
]

#: The seed a run uses unless one is passed. Recorded here rather than left to
#: a caller's habit, because "which seed produced the demo we were looking at"
#: is the first question anyone asks about a number on a screen.
DEFAULT_SEED: Final[int] = 20260904

#: The day the generated six months of calendar ends on. A fixed literal, never
#: ``date.today()``: a dataset whose contents depend on when it was generated
#: cannot be compared between two runs, and the identity key
#: ``smartmatch_persistence.events.EventRepository.upsert`` computes folds the
#: resolved date in, so a drifting anchor would make the writer non-idempotent
#: across a midnight boundary.
CALENDAR_ANCHOR: Final[date] = date(2026, 9, 28)

#: How far back the calendar reaches from :data:`CALENDAR_ANCHOR`. Six months,
#: so the metrics screens show a spread rather than one week's worth of bars.
CALENDAR_SPAN_DAYS: Final[int] = 183

#: Share of professionals with no expertise record at all. Their topics are
#: ``None`` — which the match-run contract distinguishes from ``[]`` — so
#: ``topic_relevance`` reports unknown for them and they are excluded from a
#: shortlist rather than entered at zero.
UNKNOWN_TOPIC_SHARE: Final[float] = 0.12

#: Share of professionals with no coordinates on file, so ``travel_burden`` is
#: unknown for them for the opposite reason.
UNKNOWN_LOCATION_SHARE: Final[float] = 0.10

#: Share of professionals whose export states no customer §7 sector, and share
#: whose export states no §8 role category. Two shares rather than one, drawn
#: independently, because the two axes really do arrive separately: §18 says the
#: source data "is scattered across multiple people and systems", and a contact
#: whose sector is known and whose role is not is the ordinary case rather than
#: a corner one.
#:
#: These are the states customer §19 opens with — a contact is recorded first
#: and classified afterwards — and they are the reason a generated run reports
#: ``industry_classification_missing`` / ``role_classification_missing`` against
#: some of its named candidates. Set either to zero and that reporting becomes
#: unreachable from generated data, which is the demo losing an honest state
#: rather than gaining a fuller shortlist.
UNCLASSIFIED_INDUSTRY_SHARE: Final[float] = 0.15
UNCLASSIFIED_ROLE_SHARE: Final[float] = 0.08

#: How many ratings each planned speaker actually receives, one entry per
#: speaker, and the arithmetic here is load-bearing rather than decorative.
#:
#: ``smartmatch_domain.student_speaker_feedback`` publishes a per-speaker
#: aggregate only at ``MIN_RESPONSES_FOR_AGGREGATE`` (three) or above, and
#: publishes the *unit* aggregate only when the pool clears the same threshold
#: **and** its residual does::
#:
#:     residual = n_unit - sum of n_s over speakers whose own aggregate published
#:     publish iff n_unit >= 3 and (residual == 0 or residual >= 3)
#:
#: The residual rule closes a subtraction: with one speaker published at ``n=3``
#: and the unit at ``n=5``, the two ratings of somebody else are recoverable as a
#: mean over two students, which is exactly the statement suppression exists to
#: withhold.
#:
#: ``(5, 4, 2, 1)`` satisfies both while demonstrating both outcomes at once.
#: Speakers one and two publish (5 and 4 are each above the threshold); speakers
#: three and four are **suppressed** (2 and 1 are below it); the pool is 12 and
#: the published sum is 9, so the residual is exactly 3 and the unit aggregate
#: publishes. A demo built on this shows a published unit number beside a
#: genuinely withheld per-speaker one, which is the pair a reader has to be able
#: to tell apart.
#:
#: Change any entry and check the arithmetic again. ``(5, 4, 2)`` would leave a
#: residual of 2 and silently suppress the unit aggregate — the demo would then
#: show nothing at all and look broken rather than careful.
FEEDBACK_SPEAKER_RESPONSE_SHAPE: Final[tuple[int, ...]] = (5, 4, 2, 1)

#: Share of the students who *could* rate a given speaker and deliberately do
#: not. They attended the event, the speaker is on the roster, the window is
#: open — and no rating exists, so that speaker's count is lower than the number
#: of people who saw them.
#:
#: This is the same discipline as :data:`UNKNOWN_TOPIC_SHARE` and its
#: neighbours, applied to the one surface where the absence is most easily
#: mistaken for a zero. A dataset in which everybody who could rate did would
#: make the suppressed states above unreachable by construction, and would
#: quietly assert a response rate no real programme has. It is emphatically not
#: a number to render: a speaker nobody rated has an *unknown* mean, never
#: ``0.0``, and :class:`SpeakerFeedbackAggregate` makes that combination
#: unrepresentable rather than merely unproduced.
#:
#: The realized share can differ from this constant by a rounding step per
#: speaker — opportunities are a whole number of people — so
#: :func:`feedback_plan_summary` reports what a run actually withheld rather
#: than restating this figure.
FEEDBACK_WITHHELD_SHARE: Final[float] = 0.25

#: How the posted ratings are distributed over the 1-5 scale, as
#: ``(rating, relative weight)``. Skewed high and long-tailed low, which is the
#: shape voluntary feedback actually takes: people who disliked a session mostly
#: do not fill the form in, and the ones who do are few and emphatic.
#:
#: Not uniform, for the reason the attendance shape is not uniform: a flat draw
#: over five values makes every speaker's mean land near 3.0, and a demo in
#: which every published mean is the same number demonstrates nothing about the
#: aggregate it is showing. The weights are relative and are scaled to whatever
#: number of ratings :data:`FEEDBACK_SPEAKER_RESPONSE_SHAPE` calls for.
FEEDBACK_RATING_DISTRIBUTION: Final[tuple[tuple[int, int], ...]] = (
    (5, 5),
    (4, 8),
    (3, 4),
    (2, 2),
    (1, 1),
)

#: Share of events whose date cannot be resolved (ADR-0010 ``unresolved``).
#: These have no identity key, never publish, and are withheld from the
#: calendar listing with a count rather than shown at a made-up time.
UNRESOLVED_EVENT_SHARE: Final[float] = 0.08

#: Share of events carrying a tag value outside the ratified G3 vocabulary.
#: Each one lands a ``discovery_review_item`` row, so ``/tag-quarantine`` has
#: something real in it and the event is withheld from the calendar.
QUARANTINED_TAG_SHARE: Final[float] = 0.15

#: Share of events filed under a category the ratified counting rule treats as
#: out-of-list. Present on purpose: an accepted out-of-list row must NOT count
#: toward ``opportunities``, and a dataset with none of them would never prove
#: that the filter does anything.
OUT_OF_LIST_CATEGORY_SHARE: Final[float] = 0.15

#: How many students hold a bearer token and rate a speaker through the real
#: student route. A small named cohort rather than the whole student body, and
#: the size is forced by arithmetic rather than chosen for looks.
#:
#: Customer feedback publishes an aggregate only above
#: ``smartmatch_domain.student_speaker_feedback.MIN_RESPONSES_FOR_AGGREGATE``
#: (three), and the unit-level aggregate additionally requires its *residual* —
#: the pooled count minus every per-speaker count that published — to be zero or
#: itself at least three. :data:`FEEDBACK_SPEAKER_RESPONSE_SHAPE` below is chosen
#: to satisfy both while still leaving a speaker suppressed, and its widest
#: speaker needs this many distinct students to have attended and spoken.
#:
#: Each of these students is a real principal: an account, a ``student``
#: membership on the pilot unit, and a dev bearer token the API's
#: ``SMARTMATCH_DEV_PRINCIPALS`` map resolves. Nothing here writes a rating on
#: somebody's behalf — every rating is a ``POST`` the student's own token made,
#: because ``routers/student_speaker_feedback.py`` takes ``student_id`` from the
#: verified principal and there is no request field that could carry another.
FEEDBACK_STUDENT_COUNT: Final[int] = 8

#: The ``external_subject`` prefix for that cohort.
#:
#: Deliberately **not** derived from the tenant and unit uuids the way
#: ``generate_pilot_dataset.student_subject_id`` derives the ordinary students'
#: identities. Those uuids do not exist until ``make seed-pilot`` has run,
#: whereas ``SMARTMATCH_DEV_PRINCIPALS`` has to be in the API process's
#: environment *before* it boots — the API reads it once at startup. A subject
#: that a rebuild script can compute from nothing but a rank is what lets the
#: script write that map before starting anything.
_FEEDBACK_SUBJECT_PREFIX: Final[str] = "synthetic-pilot-feedback-student-"

#: The bearer-token prefix for the same cohort. Short, plain and readable, for
#: the reason ``docker-compose.yml``'s header note gives about its own tokens:
#: nothing in a fixture identity map may carry the *shape* of a real credential.
#: These have no password, no expiry and no revocation because there is no
#: account-authentication system here to have them, and the settings validator
#: refuses the whole map outside ``edition=dev`` with fixture providers.
_FEEDBACK_TOKEN_PREFIX: Final[str] = "pilot-feedback-"


def feedback_student_external_subject(rank: int) -> str:
    """The stable ``user_account.external_subject`` for feedback student ``rank``.

    Args:
        rank: A one-based ordinal within the cohort.

    Raises:
        ValueError: ``rank`` is outside ``1..FEEDBACK_STUDENT_COUNT``. Refused
            rather than clamped: a caller asking for a rank the cohort does not
            hold would otherwise get a subject the seeder never created, and the
            API's answer to a token mapped to an unseeded subject is a bare
            ``401`` that says nothing about why.
    """
    _require_rank(rank)
    return f"{_FEEDBACK_SUBJECT_PREFIX}{rank:02d}"


def feedback_student_token(rank: int) -> str:
    """The dev bearer token that resolves to :func:`feedback_student_external_subject`.

    Raises:
        ValueError: ``rank`` is outside ``1..FEEDBACK_STUDENT_COUNT``.
    """
    _require_rank(rank)
    return f"{_FEEDBACK_TOKEN_PREFIX}{rank:02d}"


def feedback_dev_principals(count: int = FEEDBACK_STUDENT_COUNT) -> dict[str, str]:
    """The whole cohort as a ``SMARTMATCH_DEV_PRINCIPALS`` fragment.

    Returned as a plain ``dict`` rather than a JSON string so the one place that
    serialises it is the one place that writes an environment variable. The
    rebuild script merges this with the coordinator's own token before starting
    the API; merging rather than replacing is what keeps the coordinator token
    the operator already had working.

    Raises:
        ValueError: ``count`` is outside ``0..FEEDBACK_STUDENT_COUNT``.
    """
    if not 0 <= count <= FEEDBACK_STUDENT_COUNT:
        raise ValueError(
            f"count must be between 0 and FEEDBACK_STUDENT_COUNT ({FEEDBACK_STUDENT_COUNT})"
        )
    return {
        feedback_student_token(rank): feedback_student_external_subject(rank)
        for rank in range(1, count + 1)
    }


def _require_rank(rank: int) -> None:
    """Refuse a rank the feedback cohort does not hold."""
    if not 1 <= rank <= FEEDBACK_STUDENT_COUNT:
        raise ValueError(
            f"feedback student rank {rank} is outside 1..{FEEDBACK_STUDENT_COUNT}; "
            "raise FEEDBACK_STUDENT_COUNT if the cohort really needs to be bigger"
        )


#: Given names, all of historical figures, so a reader recognises immediately
#: that these rows are illustrative. The existing review seed
#: (``tools/seed_pilot_review.py``) already uses Grace Hopper and Katherine
#: Johnson in the same spirit.
_GIVEN_NAMES: Final[tuple[str, ...]] = (
    "Ada",
    "Grace",
    "Katherine",
    "Alan",
    "Rosalind",
    "Srinivasa",
    "Emmy",
    "Hedy",
    "Barbara",
    "Dorothy",
    "Charles",
    "Blaise",
    "Sofia",
    "Edsger",
    "Marie",
    "Nikola",
    "Lise",
    "Percy",
    "Annie",
    "Jane",
    "Claude",
    "Norbert",
    "Vera",
    "Gertrude",
    "Shirley",
    "Kalpana",
    "Hypatia",
    "Euclid",
    "Archimedes",
    "Maryam",
)

#: Surnames, all invented, so no generated row is a real person's name. Chosen
#: to read as plainly fictional next to the given names above.
_SURNAMES: Final[tuple[str, ...]] = (
    "Thornquist",
    "Marlowbridge",
    "Fernbrook",
    "Halloway",
    "Kestrelwood",
    "Ambervale",
    "Quillfeather",
    "Ridgemantle",
    "Stonebarrow",
    "Wintergrove",
    "Lockridge",
    "Pemberly",
    "Harrowgate",
    "Saltmeadow",
    "Ellingwood",
    "Draycott",
    "Norbury",
    "Vandermoor",
    "Cliffwater",
    "Ashenford",
    "Brightwell",
    "Coldstream",
    "Duskhollow",
    "Everline",
    "Fairmount",
)

#: Invented organizations. ``Example`` and ``Invalid`` appear in each so the
#: fiction is visible in the value itself.
_ORGANIZATIONS: Final[tuple[str, ...]] = (
    "Thornquist Example Labs",
    "Marlowbridge Invalid Works",
    "Fernbrook Example Analytics",
    "Halloway Example Robotics",
    "Kestrelwood Invalid Systems",
    "Ambervale Example Health",
    "Quillfeather Example Media",
    "Ridgemantle Invalid Energy",
    "Stonebarrow Example Foundry",
    "Wintergrove Example Studio",
)

#: Job titles. Ordinary, uninteresting, and not identifying.
_TITLES: Final[tuple[str, ...]] = (
    "Staff Engineer",
    "Director of Analytics",
    "Principal Researcher",
    "Program Manager",
    "Lead Designer",
    "Head of Operations",
    "Senior Data Scientist",
    "Community Programs Lead",
)

#: Metro regions and a representative coordinate for each. The regions are the
#: ones the existing ``professionals_clean.json`` fixture already names;
#: coordinates are coarse area centroids, which is what ``travel_burden`` needs
#: and is not personal data. The spread matters: a pool whose members all sit at
#: one point scores identically on the 0.30-weighted travel factor, and the
#: shortlist would then be decided entirely by topic.
_REGIONS: Final[tuple[tuple[str, float, float], ...]] = (
    ("Los Angeles - Central", 34.05, -118.24),
    ("Los Angeles - East", 34.03, -118.15),
    ("San Gabriel Valley", 34.09, -118.03),
    ("San Fernando Valley", 34.20, -118.53),
    ("Long Beach", 33.77, -118.19),
    ("Orange County", 33.72, -117.83),
    ("Inland Empire", 34.06, -117.44),
    ("South Bay", 33.86, -118.38),
    ("Ventura County", 34.28, -119.29),
    ("High Desert", 34.53, -117.29),
)

#: The event's own coordinate — the pilot unit's campus, the one fixed point
#: every travel distance is measured from.
EVENT_LOCATION: Final[tuple[float, float]] = (34.06, -117.82)

#: Topics drawn from the ratified G3 tag vocabulary
#: (``smartmatch_domain.event_vocabulary.TERM_CONCEPTS``). Using the approved
#: terms rather than inventing a second vocabulary is what lets an event's
#: declared required topics and a professional's expertise actually overlap —
#: two independent word lists would score every candidate unknown or zero and
#: the shortlist would be noise.
_TOPICS: Final[tuple[str, ...]] = (
    "hackathon",
    "case competition",
    "guest lecture",
    "career panel",
    "workshop",
    "conference",
    "capstone showcase",
    "keynote",
    "panelist",
    "judge",
    "mentor",
    "guest lecturer",
)

#: Raw tag values deliberately outside the vocabulary above, so they quarantine.
_OFF_VOCABULARY_TAGS: Final[tuple[str, ...]] = (
    "fireside chat",
    "unconference",
    "demo day",
    "office hours",
)

#: Event title stems. Combined with an ordinal so every generated title is
#: distinct, which keeps ADR-0012's identity key distinct per event.
_EVENT_STEMS: Final[tuple[str, ...]] = (
    "Bronco Systems Workshop",
    "Example Valley Career Panel",
    "Invalid Coast Hackathon",
    "Thornquist Guest Lecture",
    "Fernbrook Capstone Showcase",
    "Marlowbridge Case Competition",
    "Kestrelwood Mentoring Circle",
    "Ambervale Industry Conference",
)

#: Categories the ratified counting rule treats as in-list — the five
#: programmatic engagement types
#: ``smartmatch_domain.metrics.OPPORTUNITY_IN_LIST_CATEGORIES`` names, spelled
#: here the way a coordinator's export would spell them (comparison is
#: case-insensitive, so the title casing is presentation only).
#:
#: **This list is load-bearing and is easy to get wrong.** The existing
#: ``docs/pilot-data/fixtures/events_clean.json`` uses ``"Technology"``,
#: ``"Innovation"``, ``"Networking"`` and friends — every one of which the
#: ratified rule classifies as *out-of-list*. A dataset built from vocabulary
#: like that produces a measured ``opportunities`` count of **zero** and opens
#: no pipeline journey on accept, which looks exactly like a broken metric. The
#: terms below are the ones the closed P8 decision actually names.
IN_LIST_CATEGORIES: Final[tuple[str, ...]] = (
    "Hackathon",
    "Datathon",
    "Competition",
    "Guest Lecturer Event",
    "School Event",
)

#: Categories it does not. See :data:`OUT_OF_LIST_CATEGORY_SHARE`. An
#: out-of-list category is *pending coordinator review*, never an error — which
#: is why these read as plausible programme labels rather than as junk.
OUT_OF_LIST_CATEGORIES: Final[tuple[str, ...]] = (
    "Social Mixer",
    "Fundraising Gala",
)


@dataclass(frozen=True, slots=True)
class ProfessionalPlan:
    """One planned professional, with the evidence it does and does not carry.

    ``topics`` is ``None`` when this professional has **no expertise record at
    all**, which is a different claim from an empty tuple: it becomes an absent
    ``expertise_tags`` cell in the import, and therefore a NULL
    ``speaker_profile.topic_text`` rather than an empty one. ``location`` is
    ``None`` on the same terms.

    ``industry_code`` and ``role_code`` are customer §7's and §8's codes as this
    professional's export states them, and ``None`` means the export states
    nothing on that axis. They are **not** a classification: an import states a
    value, a Speaker Connector reviews it, and only a reviewed value makes
    somebody match-eligible (§19). Nothing in this module decides that; see
    ``tools/generate_pilot_dataset.py::reviews_classification``.
    """

    index: int
    name: str
    organization: str
    title: str
    region: str
    topics: tuple[str, ...] | None
    location: tuple[float, float] | None
    industry_code: str | None
    role_code: str | None

    @property
    def initials(self) -> str:
        """The two-letter initials the professionals column contract allows."""
        return "".join(part[0] for part in self.name.split()[:2]).upper()


@dataclass(frozen=True, slots=True)
class EventPlan:
    """One planned event.

    ``on_date`` is ``None`` for an ADR-0010 ``unresolved`` event: there is no
    field on this type that could hold a fabricated date for one, which is the
    same discipline ``smartmatch_domain.events.UnresolvedTime`` applies.
    """

    index: int
    title: str
    category: str
    on_date: date | None
    exact_hour: int | None
    tags: tuple[str, ...]
    off_vocabulary_tags: tuple[str, ...]

    @property
    def resolved(self) -> bool:
        """Whether this event has a date at all."""
        return self.on_date is not None

    @property
    def publishable(self) -> bool:
        """Whether ``EventRepository.publish`` will accept it.

        Both of ``ck_event_publishable``'s conditions, restated here so the plan
        can be asserted against without a database: a resolved date, and no
        quarantined tag awaiting review.
        """
        return self.resolved and not self.off_vocabulary_tags


@dataclass(frozen=True, slots=True)
class StudentPlan:
    """One planned student and how many events they attended.

    ``attendances`` clusters rather than spreads — see :func:`build_students`.
    ``credited`` is ``False`` for a deliberate few, which is exactly the narrow
    case ``routers/rewards.py::_fold_balance_for`` reports as an *unknown*
    balance: attendance on file, no ledger entry derived from it yet.
    """

    index: int
    external_suffix: str
    attendances: int
    credited: bool


@dataclass(frozen=True, slots=True)
class PlanSummary:
    """Counts a run reports, including what it deliberately leaves unmeasured."""

    professionals: int
    professionals_without_topics: int
    professionals_without_location: int
    professionals_without_classification: int
    events: int
    events_unresolved: int
    events_quarantined: int
    events_publishable: int
    events_out_of_list_category: int
    students: int
    students_without_attendance: int
    students_uncredited: int


def _rng(seed: int, stream: str) -> random.Random:
    """A generator for one named stream of the plan.

    One ``Random`` per stream rather than one shared across the whole plan:
    adding a professional would otherwise shift every event and every student
    that came after it, so a plan built with ``--events 60`` and one built with
    ``--events 61`` would disagree about data that has nothing to do with
    events. Streams keep each part of the plan reproducible on its own.
    """
    return random.Random(f"{seed}:{stream}")


def build_professionals(count: int, *, seed: int = DEFAULT_SEED) -> tuple[ProfessionalPlan, ...]:
    """Plan ``count`` professionals with a genuine spread of topics and places.

    Names are drawn without replacement from the cross product of
    :data:`_GIVEN_NAMES` and :data:`_SURNAMES`, so no two planned professionals
    share a name — which matters, because
    ``synthetic_professional_subject_id`` derives identity from the folded name
    and two identical names would silently be one account.

    Topic evidence is deliberately uneven. Most professionals carry two to four
    topics; :data:`UNKNOWN_TOPIC_SHARE` carry none at all. The topics themselves
    are weighted toward the front of :data:`_TOPICS` rather than drawn
    uniformly, so that an event declaring a common topic finds many candidates
    and one declaring a rare topic finds few — which is what makes a shortlist's
    scores actually differ from one another.

    Classification evidence is uneven on the same principle and on its own
    random stream, so adding it did not move a single topic, region or name in
    any previously generated plan. :data:`UNCLASSIFIED_INDUSTRY_SHARE` state no
    sector and :data:`UNCLASSIFIED_ROLE_SHARE` state no role category; the rest
    are drawn from the released §7/§8 taxonomies, weighted toward the head of
    each so a Speaker Request's targets actually find people.

    Raises:
        ValueError: ``count`` is negative, or exceeds the number of distinct
            names this module can produce.
    """
    if count < 0:
        raise ValueError("count must not be negative")
    available = len(_GIVEN_NAMES) * len(_SURNAMES)
    if count > available:
        raise ValueError(
            f"cannot plan {count} distinct professionals; this module's name pools "
            f"yield {available} distinct names"
        )

    names = [f"{given} {surname}" for given in _GIVEN_NAMES for surname in _SURNAMES]
    _rng(seed, "professional-names").shuffle(names)

    topic_rng = _rng(seed, "professional-topics")
    place_rng = _rng(seed, "professional-places")
    org_rng = _rng(seed, "professional-orgs")
    code_rng = _rng(seed, "professional-classification")

    planned: list[ProfessionalPlan] = []
    for index in range(count):
        region, latitude, longitude = _REGIONS[place_rng.randrange(len(_REGIONS))]

        topics: tuple[str, ...] | None
        if topic_rng.random() < UNKNOWN_TOPIC_SHARE:
            topics = None
        else:
            # Weighted toward the head of the list: a triangular draw over the
            # index makes the common topics common and the rare ones rare,
            # which a uniform sample would flatten into noise.
            wanted = topic_rng.choice((2, 2, 3, 3, 4))
            chosen: list[str] = []
            while len(chosen) < wanted:
                position = int(topic_rng.triangular(0, len(_TOPICS) - 1, 0))
                term = _TOPICS[position]
                if term not in chosen:
                    chosen.append(term)
            topics = tuple(chosen)

        location = None if place_rng.random() < UNKNOWN_LOCATION_SHARE else (latitude, longitude)

        # Weighted the same way the topics are, and for the same reason: a
        # uniform draw over twenty sectors would give a Speaker Request's target
        # a handful of matches in a roster of sixty and flatten the §7 factor
        # into noise. A triangular draw makes a few sectors common, which is
        # also what a real alumni roster looks like.
        industry_code = (
            None
            if code_rng.random() < UNCLASSIFIED_INDUSTRY_SHARE
            else SECTOR_CODES[int(code_rng.triangular(0, len(SECTOR_CODES) - 1, 0))]
        )
        role_code = (
            None
            if code_rng.random() < UNCLASSIFIED_ROLE_SHARE
            else ROLE_CATEGORY_CODES[int(code_rng.triangular(0, len(ROLE_CATEGORY_CODES) - 1, 0))]
        )

        planned.append(
            ProfessionalPlan(
                index=index,
                name=names[index],
                organization=_ORGANIZATIONS[org_rng.randrange(len(_ORGANIZATIONS))],
                title=_TITLES[org_rng.randrange(len(_TITLES))],
                region=region,
                topics=topics,
                location=location,
                industry_code=industry_code,
                role_code=role_code,
            )
        )
    return tuple(planned)


def build_events(count: int, *, seed: int = DEFAULT_SEED) -> tuple[EventPlan, ...]:
    """Plan ``count`` events spread across the six months before the anchor.

    Dates are spread across :data:`CALENDAR_SPAN_DAYS` rather than clustered,
    because a calendar is the one surface where an even spread is the honest
    shape. Precision is not even: most events carry an exact time, about a fifth
    are date-only, and :data:`UNRESOLVED_EVENT_SHARE` carry no resolvable date
    at all — the ADR-0010 case the calendar must withhold rather than render at
    a fabricated midnight.

    Raises:
        ValueError: ``count`` is negative.
    """
    if count < 0:
        raise ValueError("count must not be negative")

    shape_rng = _rng(seed, "event-shape")
    tag_rng = _rng(seed, "event-tags")

    planned: list[EventPlan] = []
    for index in range(count):
        unresolved = shape_rng.random() < UNRESOLVED_EVENT_SHARE
        if unresolved:
            on_date: date | None = None
            exact_hour: int | None = None
        else:
            offset = 0 if count <= 1 else round(index * (CALENDAR_SPAN_DAYS / (count - 1)))
            on_date = CALENDAR_ANCHOR - timedelta(days=CALENDAR_SPAN_DAYS - offset)
            # About a fifth of the resolved events are date-only: "Thursday, on
            # campus" is real information that is not an instant.
            exact_hour = None if shape_rng.random() < 0.20 else shape_rng.choice((9, 12, 15, 18))

        tag_count = tag_rng.choice((1, 2, 2, 3))
        tags = tuple(sorted(tag_rng.sample(_TOPICS, tag_count)))
        off_vocabulary = (
            (tag_rng.choice(_OFF_VOCABULARY_TAGS),)
            if tag_rng.random() < QUARANTINED_TAG_SHARE
            else ()
        )

        pool = (
            OUT_OF_LIST_CATEGORIES
            if tag_rng.random() < OUT_OF_LIST_CATEGORY_SHARE
            else IN_LIST_CATEGORIES
        )

        planned.append(
            EventPlan(
                index=index,
                title=f"{_EVENT_STEMS[index % len(_EVENT_STEMS)]} {index + 1:03d}",
                category=pool[tag_rng.randrange(len(pool))],
                on_date=on_date,
                exact_hour=exact_hour,
                tags=tags,
                off_vocabulary_tags=off_vocabulary,
            )
        )
    return tuple(planned)


#: How many events a student attended, and the relative share of students with
#: that count. A long tail rather than a uniform draw: real attendance clusters
#: near zero and thins out, and a flat distribution would make every reward
#: balance look alike. The weights are relative — :func:`build_students` scales
#: them to whatever ``count`` it is asked for.
_ATTENDANCE_SHAPE: Final[tuple[tuple[int, int], ...]] = (
    (0, 22),  # never attended: a measured zero balance, not an unknown one
    (1, 34),
    (2, 24),
    (3, 12),
    (5, 5),
    (8, 3),
)


def build_students(count: int, *, seed: int = DEFAULT_SEED) -> tuple[StudentPlan, ...]:
    """Plan ``count`` students whose attendance clusters the way real attendance does.

    A deliberate few students with attendance are left **uncredited**: no
    ``point_ledger_entry`` derives from their attendance record, which is
    precisely the narrow case ``routers/rewards.py::_fold_balance_for`` answers
    with an *unknown* balance rather than a zero. Without them the rewards
    screen would never show its unknown state, and the one behaviour ADR-0011
    exists to guarantee would be invisible in the demo.

    Raises:
        ValueError: ``count`` is negative.
    """
    if count < 0:
        raise ValueError("count must not be negative")

    total_weight = sum(weight for _, weight in _ATTENDANCE_SHAPE)
    attendances: list[int] = []
    for events, weight in _ATTENDANCE_SHAPE:
        attendances.extend([events] * round(count * weight / total_weight))
    # Rounding can leave the list a row or two short or long; the tail is the
    # single-event bucket, which is the one a rounding error least distorts.
    while len(attendances) < count:
        attendances.append(1)
    attendances = attendances[:count]
    _rng(seed, "student-attendance").shuffle(attendances)

    credit_rng = _rng(seed, "student-credit")
    return tuple(
        StudentPlan(
            index=index,
            external_suffix=f"{index + 1:04d}",
            attendances=attendances[index],
            # About one attending student in twelve is left uncredited.
            credited=attendances[index] == 0 or credit_rng.random() >= 0.08,
        )
        for index in range(count)
    )


@dataclass(frozen=True, slots=True)
class FeedbackPlan:
    """One student's opportunity to rate one speaker, taken or deliberately not.

    A *plan of opportunities*, not of rows. ``rating is None`` means this
    student attended, could have rated this speaker, and did not — so **no row
    is written at all**. That is the whole point of the type: a withheld rating
    is the absence of a ``student_speaker_feedback`` row, never a row carrying a
    zero, and there is no field here a zero could be put in.

    The ranks are positions, not identities. ``speaker_rank`` indexes
    :data:`FEEDBACK_SPEAKER_RESPONSE_SHAPE` and ``student_rank`` is a one-based
    ordinal into the feedback cohort; the writer maps each onto a real
    ``speaker_profile.professional_id`` and a real principal it created. Keeping
    them as positions is what lets this module stay pure — it invents no speaker
    id, which is also what keeps OQ-CBA-064 untouched.

    Attributes:
        speaker_rank: Which planned speaker this opinion is about.
        student_rank: Which member of the feedback cohort holds it.
        rating: ``MIN_RATING..MAX_RATING``, or ``None`` for a deliberate
            non-response.
    """

    speaker_rank: int
    student_rank: int
    rating: int | None


@dataclass(frozen=True, slots=True)
class FeedbackSummary:
    """What a feedback plan will and will not let the aggregates say.

    Computed rather than asserted, so a change to
    :data:`FEEDBACK_SPEAKER_RESPONSE_SHAPE` shows up here — and in the test that
    reads it — instead of quietly turning the unit aggregate off.

    Attributes:
        opportunities: Every (student, speaker) pair the plan reached.
        posted: How many of them produced a rating.
        withheld: How many deliberately did not. ``opportunities - posted``.
        withheld_share: The realized share, which rounding can move a step away
            from :data:`FEEDBACK_WITHHELD_SHARE`.
        speakers_published: Speakers whose own aggregate will publish.
        speakers_suppressed: Speakers whose own aggregate will be withheld.
        unit_residual: The pool minus every published per-speaker count — the
            one quantity a reader can form by subtracting what this API
            publishes from what it publishes.
        unit_publishes: Whether the unit aggregate clears both conditions.
    """

    opportunities: int
    posted: int
    withheld: int
    withheld_share: float
    speakers_published: int
    speakers_suppressed: int
    unit_residual: int
    unit_publishes: bool


def _feedback_opportunities(posted: int) -> int:
    """How many students could have rated a speaker who received ``posted`` ratings.

    ``posted`` grossed up by :data:`FEEDBACK_WITHHELD_SHARE`, rounded to a whole
    number of people. Rounded rather than ceilinged: a ceiling would push every
    speaker's withheld count up by one and make the realized share consistently
    higher than the constant it is derived from, which would be this module
    claiming a response rate it did not plan.

    Raises:
        ValueError: ``posted`` is negative.
    """
    if posted < 0:
        raise ValueError("posted must not be negative")
    return round(posted / (1.0 - FEEDBACK_WITHHELD_SHARE))


def build_speaker_feedback(
    *,
    shape: Sequence[int] = FEEDBACK_SPEAKER_RESPONSE_SHAPE,
    seed: int = DEFAULT_SEED,
) -> tuple[FeedbackPlan, ...]:
    """Plan who rates whom, with what, and who deliberately says nothing.

    One entry per (speaker, student) opportunity. For speaker ``i``, the plan
    reaches ``_feedback_opportunities(shape[i])`` students — cohort ranks ``1``
    upward — and gives ``shape[i]`` of them a rating drawn from
    :data:`FEEDBACK_RATING_DISTRIBUTION`. The rest carry ``rating=None`` and
    produce no row.

    Which students stay silent is drawn from a seeded stream rather than taken
    off the end of the list, because the tail of the list is also the tail of
    the cohort: withholding by position would make the same two students the
    ones who never say anything about anybody, which is a pattern rather than a
    response rate.

    Ranks start at ``1`` and count up per speaker, so the widest speaker uses
    ranks ``1..n`` and a narrower one uses a prefix of the same people. That
    overlap is deliberate — a student who rated one speaker and not another is
    the ordinary case, and a cohort partitioned per speaker would need far more
    principals to say the same thing.

    Raises:
        ValueError: ``shape`` is empty, holds a negative count, or calls for
            more students than :data:`FEEDBACK_STUDENT_COUNT` provides. The last
            one is refused rather than clamped: silently narrowing a speaker's
            pool would change the residual arithmetic
            :data:`FEEDBACK_SPEAKER_RESPONSE_SHAPE` was chosen for, and the unit
            aggregate would stop publishing for a reason nothing reported.
    """
    if not shape:
        raise ValueError("shape must name at least one speaker")
    if any(posted < 0 for posted in shape):
        raise ValueError("every entry in shape must be non-negative")

    widest = max(_feedback_opportunities(posted) for posted in shape)
    if widest > FEEDBACK_STUDENT_COUNT:
        raise ValueError(
            f"this shape needs {widest} distinct students and the cohort holds "
            f"{FEEDBACK_STUDENT_COUNT}; raise FEEDBACK_STUDENT_COUNT rather than "
            "narrowing the shape, which would change the residual arithmetic"
        )

    silence_rng = _rng(seed, "feedback-silence")
    rating_rng = _rng(seed, "feedback-ratings")
    scale = [rating for rating, weight in FEEDBACK_RATING_DISTRIBUTION for _ in range(weight)]

    planned: list[FeedbackPlan] = []
    for speaker_rank, posted in enumerate(shape):
        opportunities = _feedback_opportunities(posted)
        ranks = list(range(1, opportunities + 1))
        speaking = set(silence_rng.sample(ranks, min(posted, opportunities)))
        for student_rank in ranks:
            planned.append(
                FeedbackPlan(
                    speaker_rank=speaker_rank,
                    student_rank=student_rank,
                    rating=rating_rng.choice(scale) if student_rank in speaking else None,
                )
            )
    return tuple(planned)


def feedback_plan_summary(planned: Sequence[FeedbackPlan]) -> FeedbackSummary:
    """Work out what the aggregates will be able to say about this plan.

    The residual condition is restated here rather than imported, and that is a
    deliberate duplication with a stated cost: this module may not import from
    ``smartmatch_domain.student_speaker_feedback`` without making a pure plan
    depend on the shipped aggregate. The duplication is safe only because
    ``tests/unit/test_pilot_dataset_plan.py`` asserts this function's verdict
    against that module's own ``aggregate_unit_feedback``, so the two cannot
    drift without a test failing.
    """
    posted_by_speaker: dict[int, int] = {}
    opportunities = 0
    for entry in planned:
        opportunities += 1
        if entry.rating is not None:
            posted_by_speaker[entry.speaker_rank] = posted_by_speaker.get(entry.speaker_rank, 0) + 1

    posted = sum(posted_by_speaker.values())
    published = [count for count in posted_by_speaker.values() if count >= _MIN_RESPONSES]
    suppressed = sum(1 for count in posted_by_speaker.values() if count < _MIN_RESPONSES)
    residual = posted - sum(published)
    return FeedbackSummary(
        opportunities=opportunities,
        posted=posted,
        withheld=opportunities - posted,
        withheld_share=0.0 if opportunities == 0 else (opportunities - posted) / opportunities,
        speakers_published=len(published),
        speakers_suppressed=suppressed,
        unit_residual=residual,
        unit_publishes=posted >= _MIN_RESPONSES and (residual == 0 or residual >= _MIN_RESPONSES),
    )


#: The publication threshold, restated for :func:`feedback_plan_summary`. See
#: that function on why the shipped constant is not imported here, and on the
#: test that keeps the two equal.
_MIN_RESPONSES: Final[int] = 3


def plan_summary(
    professionals: Sequence[ProfessionalPlan],
    events: Sequence[EventPlan],
    students: Sequence[StudentPlan],
) -> PlanSummary:
    """Count the plan, including everything it deliberately leaves unmeasured."""
    return PlanSummary(
        professionals=len(professionals),
        professionals_without_topics=sum(1 for p in professionals if p.topics is None),
        professionals_without_location=sum(1 for p in professionals if p.location is None),
        professionals_without_classification=sum(
            1 for p in professionals if p.industry_code is None or p.role_code is None
        ),
        events=len(events),
        events_unresolved=sum(1 for e in events if not e.resolved),
        events_quarantined=sum(1 for e in events if e.off_vocabulary_tags),
        events_publishable=sum(1 for e in events if e.publishable),
        events_out_of_list_category=sum(1 for e in events if e.category in OUT_OF_LIST_CATEGORIES),
        students=len(students),
        students_without_attendance=sum(1 for s in students if s.attendances == 0),
        students_uncredited=sum(1 for s in students if s.attendances and not s.credited),
    )
