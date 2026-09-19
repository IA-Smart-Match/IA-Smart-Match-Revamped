"""What the four student factors are permitted to see.

ADR-0025 D3 / design spec §4.2. These are the ``(ProfileEvidence,
EventEvidence)`` pair the four pure factor functions take, and they are shared:
the exercise registry composes them today, and ADR-0024's student registry is
expected to compose the same functions over the same shapes when that track
ships. Nothing here is exercise-specific, and nothing here knows about a
registry, a ranker, or a screen.

**PLACEHOLDER (OQ-CE-01).** The column names and value vocabularies of Ann's
data file are open. Every field below is therefore free text compared as an
exact normalized string (:mod:`smartmatch_domain.student_factors.terms`); no
enum, no CHECK, no fixed list, and no G3 mapping is declared. When OQ-CE-01
closes, what changes is the mapping from Ann's columns onto these fields, not
these shapes.

**The three-state rule (ADR-0011, and the pattern**
:mod:`smartmatch_domain.match_depth` **sets).** An empty card is not the same
fact as no card, and the types say so rather than leaving it to a convention:

``card is None``
    No profile card exists. The two card-fed factors are **unknown**.
``card is ProfileCard()``
    A card exists and the person recorded nothing in it. That is a *measured*
    emptiness: the card-fed factors score, and they score ``0.0``.

``attended_event_topics`` carries the same distinction — ``None`` for "no
attendance record on file" against ``()`` for "the record exists and is empty"
— and both read as unknown for ``past_event_topic_overlap``, because that
factor's question ("did the topics of the events they went to overlap this
one?") has no input to measure when there is no event to read topics from.
The distinction is preserved on the evidence rather than collapsed, so the
marker in :mod:`smartmatch_domain.exercise.markers` and any later consumer can
still tell the two apart.

**No withheld field appears here.** ``hidden_true_interests`` (ADR-0025 D6,
:data:`smartmatch_domain.exercise.EXERCISE_WITHHELD_FIELDS`) is read by the
simulated-results rule and by nothing else. It is not a field of any type in
this package, and ``tests/unit/test_student_factors.py`` walks these
dataclasses to assert it.
"""

from __future__ import annotations

from dataclasses import dataclass

from smartmatch_domain.student_factors.terms import normalized_term, normalized_terms

__all__ = [
    "EventEvidence",
    "ProfileCard",
    "ProfileEvidence",
]


@dataclass(frozen=True, slots=True)
class ProfileCard:
    """A completed profile card, as the factors read it.

    A card that exists is a card, however little is written on it. Both fields
    may be empty, and an empty field is a recorded emptiness rather than an
    absence: the person answered, and the answer had nothing in common with
    this event.

    Attributes:
        stated_interests: The interests written on the card, as given. Compared
            as exact normalized strings.
        career_goal: The career goal written on the card, or ``None`` when that
            one field of an existing card is blank.
    """

    stated_interests: tuple[str, ...] = ()
    career_goal: str | None = None

    def __post_init__(self) -> None:
        if self.career_goal is not None and not self.career_goal.strip():
            raise ValueError(
                "career_goal: blank — use None for a card whose career goal is not "
                "filled in, not a blank string"
            )
        object.__setattr__(self, "stated_interests", tuple(self.stated_interests))

    @property
    def normalized_interests(self) -> frozenset[str]:
        """The card's interests as they are compared."""
        return normalized_terms(self.stated_interests)

    @property
    def normalized_career_goal(self) -> str | None:
        """The card's career goal as it is compared, or ``None``."""
        if self.career_goal is None:
            return None
        return normalized_term(self.career_goal)


@dataclass(frozen=True, slots=True)
class ProfileEvidence:
    """Everything the four student factors may see about one profile.

    Attributes:
        profile_id: Stable identifier for the profile. Non-blank. This is what
            reaches ``StageBScore.subject_id`` (ADR-0025 D4).
        major: The profile's major. Always on file, which is why ``same_major``
            is never unknown.
        card: The profile card, or ``None`` when no card exists.
        attended_event_topics: One entry per past event attended, each holding
            that event's topics; or ``None`` when no attendance record exists
            for this profile at all.
    """

    profile_id: str
    major: str
    card: ProfileCard | None = None
    attended_event_topics: tuple[tuple[str, ...], ...] | None = None

    def __post_init__(self) -> None:
        if not self.profile_id.strip():
            raise ValueError("profile_id: must not be empty or blank")
        if not self.major.strip():
            raise ValueError(
                "major: must not be empty or blank — every profile has a major on file "
                "(class-exercise requirements, 'Data')"
            )
        if self.attended_event_topics is not None:
            object.__setattr__(
                self,
                "attended_event_topics",
                tuple(tuple(topics) for topics in self.attended_event_topics),
            )

    @property
    def has_attendance_record(self) -> bool:
        """Whether an attendance record exists at all, empty or not."""
        return self.attended_event_topics is not None

    @property
    def attended_event_count(self) -> int | None:
        """How many past events were attended, or ``None`` with no record."""
        if self.attended_event_topics is None:
            return None
        return len(self.attended_event_topics)

    @property
    def normalized_attended_topics(self) -> frozenset[str] | None:
        """The union of the attended events' topics, or ``None`` with no record."""
        if self.attended_event_topics is None:
            return None
        flattened: list[str] = []
        for topics in self.attended_event_topics:
            flattened.extend(topics)
        return normalized_terms(flattened)


@dataclass(frozen=True, slots=True)
class EventEvidence:
    """Everything the four student factors may see about one event.

    Attributes:
        event_key: The event's key. Non-blank.
        topic_tags: The event's topics, as given.
        target_majors: The majors the event is aimed at, as given.
    """

    event_key: str
    topic_tags: tuple[str, ...] = ()
    target_majors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.event_key.strip():
            raise ValueError("event_key: must not be empty or blank")
        object.__setattr__(self, "topic_tags", tuple(self.topic_tags))
        object.__setattr__(self, "target_majors", tuple(self.target_majors))

    @property
    def normalized_topics(self) -> frozenset[str]:
        """The event's topics as they are compared."""
        return normalized_terms(self.topic_tags)

    @property
    def normalized_majors(self) -> frozenset[str]:
        """The event's target majors as they are compared."""
        return normalized_terms(self.target_majors)
