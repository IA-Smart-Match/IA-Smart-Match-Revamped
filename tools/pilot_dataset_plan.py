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
coordinates, and :data:`UNRESOLVED_EVENT_SHARE` of events have no resolvable
date (ADR-0010 ``unresolved``). :func:`plan_summary` reports those fractions so
a run can say out loud how much of what it wrote is deliberately unmeasured.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final

__all__ = [
    "CALENDAR_ANCHOR",
    "DEFAULT_SEED",
    "EVENT_LOCATION",
    "IN_LIST_CATEGORIES",
    "OUT_OF_LIST_CATEGORIES",
    "EventPlan",
    "PlanSummary",
    "ProfessionalPlan",
    "StudentPlan",
    "build_events",
    "build_professionals",
    "build_students",
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
    all**, which is a different claim from an empty tuple and is carried
    through to the match-run contract's own ``expertise_topics`` as ``null``
    rather than ``[]``. ``location`` is ``None`` on the same terms.
    """

    index: int
    name: str
    organization: str
    title: str
    region: str
    topics: tuple[str, ...] | None
    location: tuple[float, float] | None

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

        planned.append(
            ProfessionalPlan(
                index=index,
                name=names[index],
                organization=_ORGANIZATIONS[org_rng.randrange(len(_ORGANIZATIONS))],
                title=_TITLES[org_rng.randrange(len(_TITLES))],
                region=region,
                topics=topics,
                location=location,
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
        events=len(events),
        events_unresolved=sum(1 for e in events if not e.resolved),
        events_quarantined=sum(1 for e in events if e.off_vocabulary_tags),
        events_publishable=sum(1 for e in events if e.publishable),
        events_out_of_list_category=sum(1 for e in events if e.category in OUT_OF_LIST_CATEGORIES),
        students=len(students),
        students_without_attendance=sum(1 for s in students if s.attendances == 0),
        students_uncredited=sum(1 for s in students if s.attendances and not s.credited),
    )
