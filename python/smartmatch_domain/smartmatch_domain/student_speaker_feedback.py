"""What a student may say about a speaker, until when, and what a Connector sees.

Customer §§15-16, implementing OQ-CBA-003 as decided on 6 September 2026 by
Danny Tran, program owner of record. §26 item 3 had recorded the scale, the
fields and the aggregation rules as unspecified; this module is the whole of
what was specified, and deliberately nothing more.

**This is not** ``smartmatch_domain.feedback``. That module is a coordinator's
accept/decline on a *match proposal*, aggregated into shadow-mode weight
deltas — a signal that adjusts ranking. Nothing here feeds matching. A student
saying a speaker was good is a record of what happened at an event, not
evidence about who should be invited to the next one, and wiring the two
together would be a scoring change made through a feedback form. Whether it
ever should be is **OQ-CBA-053**, and it is open.

The four parts, and where each one lives
==========================================
**1. Anonymity is a display rule.** Not visible in this module at all, which is
the point worth stating: the row stores ``student_id``, and no type here has a
field to carry one into an aggregate. :class:`SpeakerFeedbackAggregate` is
three numbers and nothing else. The rule that a Connector-facing route never
returns the column is enforced in the router and proved in the contract suite.

**2. One dimension.** :class:`Rating` is a required ``1..5`` integer plus an
optional comment. There are no sub-criteria, and adding some is a product
decision rather than a refactor.

**3. A seven-day post-event cutoff.** :data:`FEEDBACK_EDIT_WINDOW_DAYS`, applied
by :func:`resolve_edit_window` to an anchor that :func:`feedback_anchor` derives
from ADR-0010's temporal triple. The interesting case is the one ADR-0010
insists exists: an event whose date is ``unresolved`` has no anchor, so the
window's close is :attr:`EditWindowState.UNKNOWN` rather than a date somebody
made up.

**4. Mean and count, suppressed below three responses.**
:func:`aggregate_speaker_feedback`, following ADR-0011 rule 1 — an aggregate
over a possibly-empty set returns optionals, and absence never renders as zero.
It is stricter than that rule requires: below the threshold the *count* is
withheld as well, because "two students rated this speaker" is a re-identifying
statement in a class of thirty, and a suppression that still publishes n has
suppressed only the harmless half.

No clock, no I/O
=================
Every function that needs the time takes ``now`` as an argument. A deadline
whose evaluation cannot be pinned to a chosen instant cannot be tested, and
this one has a boundary that matters.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import Final

__all__ = [
    "FEEDBACK_EDIT_WINDOW_DAYS",
    "MAX_COMMENT_LENGTH",
    "MAX_RATING",
    "MIN_RATING",
    "MIN_RESPONSES_FOR_AGGREGATE",
    "NOT_ENOUGH_RESPONSES",
    "EditWindow",
    "EditWindowState",
    "FeedbackStatus",
    "Rating",
    "SpeakerFeedbackAggregate",
    "aggregate_speaker_feedback",
    "feedback_anchor",
    "resolve_edit_window",
]

#: The one approved scale, as two named bounds rather than four literals spread
#: across a request model, a CHECK, a form and a test.
MIN_RATING: Final[int] = 1
MAX_RATING: Final[int] = 5

#: Longest comment a student may leave. Mirrored by
#: ``ck_student_speaker_feedback_comment_shape`` in migration 0031, because a
#: request model is not the last line of defence for a text column.
MAX_COMMENT_LENGTH: Final[int] = 2000

#: How long after an event a student may still change or withdraw what they
#: said. The decision says "~7 days"; this is that number, named, so the cutoff
#: is one edit rather than a literal repeated at every call site.
FEEDBACK_EDIT_WINDOW_DAYS: Final[int] = 7

#: Fewest responses an aggregate may be computed from. Below it nothing is
#: published — see :func:`aggregate_speaker_feedback`.
MIN_RESPONSES_FOR_AGGREGATE: Final[int] = 3

#: What a suppressed aggregate says instead of a number. A sentence rather than
#: a dash or a zero, because the reader has to be able to tell "we are not
#: telling you" from "the answer is nothing".
NOT_ENOUGH_RESPONSES: Final[str] = "not enough responses yet"


class FeedbackStatus(StrEnum):
    """The two states a rating can be in.

    There is no ``never_rated``: that is the absence of a row, and spelling it
    as a value would make it storable — a row asserting something nobody did.
    A withdrawal is a transition on the same row rather than a ``DELETE``, which
    is the shape OQ-CBA-018 settled for ``event_registration``.
    """

    SUBMITTED = "submitted"
    WITHDRAWN = "withdrawn"


@dataclass(frozen=True, slots=True)
class Rating:
    """One student's opinion of one speaker: a required score and optional words.

    Attributes:
        value: The overall rating, ``MIN_RATING..MAX_RATING`` inclusive.
        comment: Free text, or ``None`` when the student wrote nothing. Blank
            and whitespace-only input normalizes to ``None`` rather than being
            stored as ``''`` — an empty string would be a third state that no
            surface distinguishes from absence and no reader would render
            differently.

    Raises:
        ValueError: If ``value`` is off the scale, or ``comment`` is longer than
            :data:`MAX_COMMENT_LENGTH`.
    """

    value: int
    comment: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.value, int) or isinstance(self.value, bool):
            raise ValueError("a rating must be a whole number between 1 and 5")
        if not MIN_RATING <= self.value <= MAX_RATING:
            raise ValueError(
                f"a rating must be between 1 and 5; got {self.value}. "
                "There is no zero on this scale: an unrated speaker has no row."
            )
        normalized = self.comment.strip() if self.comment is not None else None
        if normalized == "":
            normalized = None
        if normalized is not None and len(normalized) > MAX_COMMENT_LENGTH:
            raise ValueError(f"a comment may be at most {MAX_COMMENT_LENGTH} characters")
        object.__setattr__(self, "comment", normalized)


class EditWindowState(StrEnum):
    """Whether a rating may still be changed, and whether that is even knowable.

    ``UNKNOWN`` is a real third state and not a synonym for either neighbour. It
    means the event carries no resolved date (ADR-0010), so no deadline can be
    measured — which is different from a deadline that has not arrived, and
    different again from one that has.
    """

    OPEN = "open"
    CLOSED = "closed"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class EditWindow:
    """When a student's own rating stops being theirs to change.

    Attributes:
        state: Open, closed, or unknowable.
        closes_at: The instant the window shuts, or ``None`` when :attr:`state`
            is :attr:`EditWindowState.UNKNOWN`. Never a fabricated date — a
            surface with no cutoff to show must say so.
    """

    state: EditWindowState
    closes_at: datetime | None

    @property
    def permits_change(self) -> bool:
        """Whether an edit or a withdrawal may proceed.

        ``UNKNOWN`` permits it. The asymmetry is deliberate and is the one
        judgement call in this module: locking on an unknown cutoff would assert
        that a deadline nobody can name has already passed, and would take away a
        student's ability to retract their own words on the strength of a date
        the system admits it does not have. Leaving it open asserts nothing — the
        surface still shows no closing date, because there is none.

        Whether that is the right way round for an event whose date is never
        resolved is **OQ-CBA-052**, and it is open.
        """
        return self.state is not EditWindowState.CLOSED


def feedback_anchor(
    *,
    time_precision: str,
    starts_at: datetime | None,
    ends_at: datetime | None,
    on_date: date | None,
) -> datetime | None:
    """The moment the seven days are counted from, or ``None`` when there is none.

    Takes ADR-0010's temporal triple as it is stored on ``event`` rather than an
    already-resolved instant, so the ``unresolved`` case is handled here — once —
    instead of at every call site that would otherwise have to remember it.

    Args:
        time_precision: ``'exact'``, ``'date_only'`` or ``'unresolved'``.
        starts_at: Present at ``'exact'``.
        ends_at: Present at ``'exact'`` only when the source stated an end.
        on_date: Present at ``'date_only'``.

    Returns:
        The anchor instant, or ``None`` for an unresolved event.

        For ``'exact'`` that is the end when one was stated and the start
        otherwise: ``ends_at IS NULL`` means the source gave no end (migration
        0022), not that the event had none, so the start is the latest moment
        actually known. For ``'date_only'`` it is midnight at the end of that
        day, in UTC. Resolving a bare date to its own end rather than its
        beginning costs at most one of the seven days and errs toward leaving
        the window open, which is the direction that does not silently take a
        student's retraction away. The timezone approximation is deliberate and
        bounded: ``event.time_zone`` may be set at ``date_only``, but applying it
        would move the deadline by at most a day inside a seven-day window, and
        reading a nullable timezone into a deadline is a second way to get it
        wrong for no accuracy that matters here.
    """
    if time_precision == "exact":
        return ends_at or starts_at
    if time_precision == "date_only" and on_date is not None:
        return datetime.combine(on_date + timedelta(days=1), time.min, tzinfo=UTC)
    return None


def resolve_edit_window(*, anchor: datetime | None, now: datetime) -> EditWindow:
    """Decide whether a rating anchored at ``anchor`` may still be changed at ``now``.

    The boundary is lower-inclusive and upper-exclusive — the closing instant
    itself is closed — matching ADR-0016's convention for proximity bands, so the
    two do not disagree about what "at the boundary" means.

    Args:
        anchor: From :func:`feedback_anchor`; ``None`` when the event's date is
            unresolved.
        now: The instant the decision is being made at. Passed in rather than
            read from a clock, so a deadline can be tested at its boundary.

    Returns:
        An :class:`EditWindow`. With no anchor the state is
        :attr:`EditWindowState.UNKNOWN` and ``closes_at`` is ``None``; a date is
        never invented to fill it.
    """
    if anchor is None:
        return EditWindow(state=EditWindowState.UNKNOWN, closes_at=None)
    closes_at = anchor + timedelta(days=FEEDBACK_EDIT_WINDOW_DAYS)
    state = EditWindowState.OPEN if now < closes_at else EditWindowState.CLOSED
    return EditWindow(state=state, closes_at=closes_at)


@dataclass(frozen=True, slots=True)
class SpeakerFeedbackAggregate:
    """What a Connector is told about one speaker's ratings.

    Three fields, and none of them can name a student — part 1 of the decision is
    a property of this type, not a habit of its callers.

    Attributes:
        response_count: How many ratings the mean was computed from, or ``None``
            when suppressed. Withheld rather than published because a small n is
            re-identifying: in a class of thirty, "two students rated this
            speaker" narrows the field considerably.
        mean_rating: The average, rounded to two decimals, or ``None`` when
            suppressed. ``None`` and never ``0.0`` — ADR-0011 rule 1, and the
            exact defect Fix #8 reported.
        suppressed: Whether the numbers were withheld.

    Raises:
        ValueError: If the fields disagree — a suppressed aggregate carrying
            numbers, or an unsuppressed one carrying none. That combination is
            the leak this rule exists to prevent, so it is made unrepresentable
            rather than merely unproduced.
    """

    response_count: int | None
    mean_rating: float | None
    suppressed: bool

    def __post_init__(self) -> None:
        carries_numbers = self.response_count is not None or self.mean_rating is not None
        if self.suppressed and carries_numbers:
            raise ValueError(
                "a suppressed aggregate must carry no numbers at all: "
                "publishing the count behind a withheld mean re-identifies the raters"
            )
        if not self.suppressed and (self.response_count is None or self.mean_rating is None):
            raise ValueError("an aggregate that is not suppressed must carry both numbers")

    @property
    def display_text(self) -> str:
        """What to render. :data:`NOT_ENOUGH_RESPONSES` when suppressed.

        A sentence rather than a dash or a zero, so the reader can tell "we are
        not telling you" from "the answer is nothing".
        """
        if self.suppressed:
            return NOT_ENOUGH_RESPONSES
        return f"{self.mean_rating} from {self.response_count} responses"


def aggregate_speaker_feedback(ratings: Sequence[int]) -> SpeakerFeedbackAggregate:
    """Mean and count over the ratings given, suppressed below the threshold.

    Args:
        ratings: The scores that count — already filtered by the caller to
            submitted, non-withdrawn rows. This function filters nothing: a
            withdrawn rating that reaches here is a caller's bug, and a
            defensive filter here would let that bug survive undetected.

    Returns:
        A :class:`SpeakerFeedbackAggregate`. Below
        :data:`MIN_RESPONSES_FOR_AGGREGATE` responses — including none at all —
        it carries no mean and no count, and reads as
        :data:`NOT_ENOUGH_RESPONSES`.

        An empty input is suppressed for the same reason two responses are, not
        a different one: zero is not the average of nothing, and a speaker nobody
        rated must not appear beside a speaker rated 0.0, which is a thing no
        student can even say.
    """
    if len(ratings) < MIN_RESPONSES_FOR_AGGREGATE:
        return SpeakerFeedbackAggregate(response_count=None, mean_rating=None, suppressed=True)
    return SpeakerFeedbackAggregate(
        response_count=len(ratings),
        mean_rating=round(sum(ratings) / len(ratings), 2),
        suppressed=False,
    )
