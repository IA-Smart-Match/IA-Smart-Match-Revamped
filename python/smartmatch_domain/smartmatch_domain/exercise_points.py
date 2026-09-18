"""Per-profile points for the class exercise (ADR-0025 scope).

The requirements table's "Points" row is *Not required*; its **nice to have**
is "a points counter per profile that rises with attendance and card
completion", and its **not now** is "reward catalog, redeeming points, faculty
extra credit". This module is exactly that nice-to-have and nothing beyond it:
one pure function that folds a made-up profile's exercise events into a points
value.

## This is not the CBA rewards ledger, and shares nothing with it

ADR-0013 governs the CBA platform's points: real students, a server-side
ledger over ``attendance_record`` rows, tenancy, and a disclosure policy.
None of that applies here and none of it is reached from here. This module
imports nothing from ``smartmatch_persistence`` — ``rewards.py`` least of all
— nothing from ``smartmatch_authz``, and nothing that reads a database. A
class exercise point and a CBA reward point are two different things that
happen to share an English word, and joining them would put a fictional row
one call from a real ledger, which ADR-0025 D2 refuses.

## No persistence, deliberately

There is no persistence in this module and none behind it. The ``exercise_``
tables of ADR-0025 D2 do not exist yet; when they do, a caller reads a
profile's overlay rows and hands the counts to :func:`profile_points`. The
seam is the argument, so this module is finished before the schema starts.

## Unknown is not "no"

ADR-0011 rule 1: a profile whose card completion has never been recorded is
``CardCompletion.UNKNOWN``. It earns nothing — there is no completed card to
reward — but it is *reported* as unknown, never rewritten to "did not
complete". A team that has not yet run its refresh has 300 profiles in that
state, and the screen should say so rather than assert 300 refusals.

## No other number leaves here

ADR-0025 D8: the exercise shows rank, the team's weights, one reason per name,
and — by this module — points. There is no percentage, no rate, no match
score, and no confidence on :class:`ProfilePoints`, and a field for one must
not be added.

## The values are placeholders

``POINTS_PER_ATTENDANCE`` and ``POINTS_PER_COMPLETED_CARD`` are **PLACEHOLDER**
values. No requirement, ADR, or design section fixes them; the requirements row
only says the counter *rises* with each. The simplest defaults that satisfy
"rises" are used, deliberately equal so neither behaviour is implicitly
declared the more valuable one. Confirming them is register row OQ-CE-10 in
``docs/plans/open-questions/class-exercise-open-questions.md`` (ADR-0025's
amendment discipline: "changing a coefficient ... is a register row, not an
amendment"), not a change to this module's shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

__all__ = [
    "POINTS_PER_ATTENDANCE",
    "POINTS_PER_COMPLETED_CARD",
    "CardCompletion",
    "ProfilePoints",
    "ProfilePointsInput",
    "profile_points",
]


#: PLACEHOLDER (OQ-CE-10): points earned for each past event a
#: profile attended. One point per event is the simplest value that satisfies
#: "rises with attendance" and keeps the counter readable from a projector.
POINTS_PER_ATTENDANCE: int = 1

#: PLACEHOLDER (OQ-CE-10): points earned once, when a profile has
#: completed its five-questions card. Equal to :data:`POINTS_PER_ATTENDANCE`
#: so this module does not quietly decide that one behaviour is worth more
#: than the other; that ranking is Ann's to make.
POINTS_PER_COMPLETED_CARD: int = 1


class CardCompletion(Enum):
    """Whether a profile has completed its card, with "not asked yet" kept apart.

    ``UNKNOWN`` is the state before a team's refresh has run, or before the
    data file said anything. It is not ``NOT_COMPLETED``: nobody has declined.
    """

    UNKNOWN = "unknown"
    NOT_COMPLETED = "not_completed"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class ProfilePointsInput:
    """One profile's exercise events, as a caller already read them.

    Attributes:
        attended_count: How many events this profile attended. Zero is a
            counted zero; a count that was never read is not representable
            here, because a caller with no counts has no points to show.
        card_completion: Card state, ``UNKNOWN`` until something records it.
    """

    attended_count: int
    card_completion: CardCompletion = CardCompletion.UNKNOWN


@dataclass(frozen=True, slots=True)
class ProfilePoints:
    """What one profile has earned, with its two parts kept visible.

    Attributes:
        attendance_points: The attendance part of the total.
        card_points: The card-completion part of the total.
        total: The sum of the two, computed here so no surface re-derives it.
        card_completion: The state the points were computed from, carried back
            verbatim so a screen can say "not asked yet" instead of "no".
    """

    attendance_points: int
    card_points: int
    total: int
    card_completion: CardCompletion

    @property
    def card_completion_known(self) -> bool:
        """``False`` while nothing has recorded this profile's card state."""
        return self.card_completion is not CardCompletion.UNKNOWN


def profile_points(events: ProfilePointsInput) -> ProfilePoints:
    """Fold one profile's exercise events into its points counter.

    Args:
        events: The profile's attendance count and card state.

    Returns:
        A new :class:`ProfilePoints`. Nothing is mutated; the argument is
        frozen and is not stored.

    Raises:
        TypeError: If ``attended_count`` is not an ``int`` (a ``bool`` is
            refused too).
        ValueError: If ``attended_count`` is negative. A negative head count
            is not a low score, it is a bad read, and failing here keeps a
            nonsense number off the projector.
    """
    # `bool` is an `int` in Python, and a dataclass does not enforce its
    # annotations, so a bad parse (2.7, True, "3") would otherwise reach the
    # projector as a points total.
    if isinstance(events.attended_count, bool) or not isinstance(events.attended_count, int):
        raise TypeError(f"attended_count must be a whole number; got {events.attended_count!r}.")
    if events.attended_count < 0:
        raise ValueError(
            "attended_count must not be negative; "
            f"got {events.attended_count}. A count that was not read is not a "
            "negative count."
        )

    attendance_points = events.attended_count * POINTS_PER_ATTENDANCE
    card_points = (
        POINTS_PER_COMPLETED_CARD if events.card_completion is CardCompletion.COMPLETED else 0
    )
    return ProfilePoints(
        attendance_points=attendance_points,
        card_points=card_points,
        total=attendance_points + card_points,
        card_completion=events.card_completion,
    )
