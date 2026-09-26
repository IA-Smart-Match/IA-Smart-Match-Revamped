"""The three "asking for more" choices and what each one produces (§12).

Before the refresh, a team picks one of three ways to ask the profiles it
invited to complete a card. Ann's build table fixes what each one produces:

    promise better recommendations (about 30 percent of invited profiles
    without a card complete one); small reward (about 55 percent); required
    (about 80 percent, but about 15 percent of those without a card stop
    opening messages and never sign up in round two).

Those four numbers are confirmed: OQ-CE-04 closed 2026-09-25 (Ann Wang,
email reply to the team's question list) — 30 percent / 55 percent / 80
percent, plus 15 percent non-responding under "required". Ann gave no view on
how a half rounds; Danny settled it per the owner-doc recommendation: **round
half up** (see :func:`select_share`).

The three choice names are not placeholders. They are fixed by design spec §12
and again by the database: the ``ck_exercise_team_workspace_asking_choice``
check constraint in ``db/migrations/versions/0037_exercise_tables.py`` admits
exactly ``better_recommendations``, ``small_reward``, and ``required``.

## What is here and what is not

:func:`select_share` is the pure, deterministic part of the refresh: given some
profile numbers and a share, it says *which* of them.
:func:`copied_card_career_goal` is the other pure part: given the base row's
career goal and the hidden true career goal, it says what the copied card
carries — the hidden one, since Ann's Read Me of 2026-09-24 answered OQ-CE-13
("a new card copies these", of both pink columns). The refresh itself
(design spec §13 — writing overlay rows, copying a card from the hidden true
values, recomputing markers) is not here and cannot be: it needs the overlay
repository, and this package imports no persistence.

Nothing in this module reads a profile's hidden true interests.
:func:`copied_card_career_goal` is handed a hidden true career goal by its one
caller and returns it for the overlay write, which is the refresh Ann
describes: a card the profile completes states what it truly wants.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Final, assert_never

__all__ = [
    "CARD_COMPLETION_SHARE",
    "COPIED_CARD_CAREER_GOAL",
    "REQUIRED_NON_RESPONDING_SHARE",
    "AskingChoice",
    "CopiedCardCareerGoal",
    "copied_card_career_goal",
    "select_share",
]


class AskingChoice(StrEnum):
    """The three ways a team may ask its invited profiles for more.

    The values match the database check constraint
    ``ck_exercise_team_workspace_asking_choice`` exactly; a fourth member here
    would be a row the database refuses to store.
    """

    #: "Promise better recommendations."
    BETTER_RECOMMENDATIONS = "better_recommendations"
    #: "A small reward."
    SMALL_REWARD = "small_reward"
    #: "Required."
    REQUIRED = "required"


#: The share of *invited profiles without a card* that complete one, per
#: choice. Ann's build table's own numbers, confirmed (OQ-CE-04 closed
#: 2026-09-25). A read-only mapping so a caller cannot quietly re-tune the
#: exercise at runtime.
CARD_COMPLETION_SHARE: Final[Mapping[AskingChoice, float]] = MappingProxyType(
    {
        AskingChoice.BETTER_RECOMMENDATIONS: 0.30,
        AskingChoice.SMALL_REWARD: 0.55,
        AskingChoice.REQUIRED: 0.80,
    }
)

#: Confirmed (OQ-CE-04): under :attr:`AskingChoice.REQUIRED` only, the share
#: of invited profiles without a card that stop opening messages and never sign
#: up in round two. This is the cost the "required" choice carries, and the
#: point of the exercise's third option.
REQUIRED_NON_RESPONDING_SHARE: Final[float] = 0.15


class CopiedCardCareerGoal(StrEnum):
    """What career goal a card copied by design spec §13's refresh carries.

    The refresh copies *interests* out of the withheld column onto a team's
    overlay row. What the same card says about a career goal was OQ-CE-13, and
    Ann's Read Me answered it on 2026-09-24: the hidden true career goal is
    "used only by the results rule and by the refresh (a new card copies
    these)". :attr:`HIDDEN_GOAL` is that answer; the two earlier readings stay
    as members so a test can still name them.

    A third answer is one member here plus one branch in
    :func:`copied_card_career_goal`. Nothing outside this module decides it, and
    nothing reads it from an environment variable or a request.
    """

    #: The copied card carries the base row's career goal, and ``None`` when the
    #: base row has none. The owner's ruling of 2026-09-21.
    BASE_GOAL = "base_goal"
    #: The copied card carries no career goal at all. What shipped in PR #190:
    #: the overlay column is left ``NULL`` and the base row stands behind it.
    NONE = "none"
    #: The copied card carries the profile's hidden true career goal, and
    #: ``None`` when the file has none. Ann's answer of 2026-09-24.
    HIDDEN_GOAL = "hidden_goal"


#: Which reading design spec §13's copied card takes: Ann's, of 2026-09-24
#: (OQ-CE-13 closed). Every caller takes it as a default.
COPIED_CARD_CAREER_GOAL: Final[CopiedCardCareerGoal] = CopiedCardCareerGoal.HIDDEN_GOAL


def copied_card_career_goal(
    base_career_goal: str | None,
    policy: CopiedCardCareerGoal = COPIED_CARD_CAREER_GOAL,
    *,
    hidden_true_career_goal: str | None = None,
) -> str | None:
    """The career goal a copied card carries, under ``policy``.

    Pure: it takes the base row's goal and the hidden true goal and returns a
    value, and it is the **one** place any reading is written. A caller that
    wants the shipped reading passes no ``policy`` at all.

    * :attr:`CopiedCardCareerGoal.HIDDEN_GOAL` (shipped): the hidden true
      career goal, ``None`` when the file has none.
    * :attr:`CopiedCardCareerGoal.BASE_GOAL`: the base row's own goal.
    * :attr:`CopiedCardCareerGoal.NONE`: always ``None``.

    Args:
        base_career_goal: The base row's ``career_goal``, or ``None``.
        policy: Which reading to apply. Defaults to
            :data:`COPIED_CARD_CAREER_GOAL`.
        hidden_true_career_goal: The profile's withheld true career goal, or
            ``None``. Read only under :attr:`CopiedCardCareerGoal.HIDDEN_GOAL`.

    Returns:
        The value to store in ``exercise_profile_overlay.card_career_goal``, or
        ``None`` for "this card says nothing about a career goal".

    Raises:
        AssertionError: If ``policy`` is not a member of
            :class:`CopiedCardCareerGoal`. A member added without a branch here
            must be refused, not silently read as another reading — raised via
            :func:`typing.assert_never`, so mypy also flags it statically.
    """
    match policy:
        case CopiedCardCareerGoal.HIDDEN_GOAL:
            return hidden_true_career_goal
        case CopiedCardCareerGoal.BASE_GOAL:
            return base_career_goal
        case CopiedCardCareerGoal.NONE:
            return None
        case _:
            assert_never(policy)


def _rank_key(seed: int, salt: str, profile_no: int) -> tuple[bytes, int]:
    """A stable sort key for one profile, from a digest rather than a shuffle.

    Same reasoning as the simulation module: Python's ``hash()`` is salted per
    process, so a shuffle keyed on it would pick different profiles in a
    different process. The profile number is the second element so two profiles
    with the same digest still have one fixed order.

    Each field is length-prefixed rather than joined by ``":"``, so a salt that
    contains the separator cannot produce the digest of a different set of
    fields.
    """
    hasher = hashlib.sha256()
    for field in (seed, salt, profile_no):
        encoded = str(field).encode()
        hasher.update(f"{len(encoded)}:".encode())
        hasher.update(encoded)
    return hasher.digest(), profile_no


def _half_up_count(share: float, size: int) -> int:
    """``share * size`` rounded to a whole count, a half rounding up.

    OQ-CE-04's half-rounding, settled 2026-09-25 by Danny per the owner-doc
    recommendation (round half up). Python's ``round`` is banker's rounding,
    which sends ``4.5`` to ``4``; and ``share * size`` in floats can land a hair
    under the half (``0.29 * 50`` is ``14.499999999999998``). So the product is
    taken in :class:`~decimal.Decimal` from the share's shortest repr — the
    number as written, ``0.29`` rather than its binary neighbour — and rounded
    with :data:`~decimal.ROUND_HALF_UP`.
    """
    exact = Decimal(str(float(share))) * size
    return int(exact.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def select_share(
    profile_nos: Iterable[int],
    share: float,
    *,
    seed: int,
    salt: str,
    of_size: int | None = None,
) -> tuple[int, ...]:
    """Pick a share of the given profiles, the same way every time.

    Which profiles are picked depends only on the seed, the salt, and each
    profile's own number — never on the order they arrive in, and never on who
    else is in the group beyond how many there are. So a team's refresh picks
    the same profiles however the list was built, and two salts over one seed
    pick independently (the card completers and the non-responders are not the
    same draw).

    Args:
        profile_nos: The profiles to pick from. Repeats are folded into one.
        share: How many to pick, as a fraction in ``[0, 1]``. The count is
            ``share * n`` rounded half up (OQ-CE-04), so a group of ten at a
            share of exactly ``0.05`` picks one. See :func:`_half_up_count`.
        seed: The team's seed, so one team's refresh is another team's
            business.
        salt: What is being picked, e.g. ``"card_completion"``. Two calls with
            one seed and one salt agree; with different salts they do not.
        of_size: The group the share is *of*, when it is larger than the pool
            drawn from. "Required" takes 15% of every no-card profile but draws
            them only from those that did not complete a card (owner ruling,
            2026-09-25), so the count and the pool differ. ``None`` means the
            share is of the pool itself.

    Returns:
        The picked profile numbers, sorted ascending and free of duplicates.

    Raises:
        ValueError: If ``share`` is outside ``[0, 1]``, if ``of_size`` is
            smaller than the pool, or if the pool holds fewer profiles than the
            share of ``of_size`` asks for.
    """
    if not 0.0 <= share <= 1.0:
        raise ValueError(f"share must be between 0 and 1 inclusive; got {share}.")
    distinct = sorted(set(profile_nos))
    size = len(distinct) if of_size is None else of_size
    if size < len(distinct):
        raise ValueError(f"of_size must be at least the pool's {len(distinct)}; got {size}.")
    count = _half_up_count(share, size)
    if count > len(distinct):
        raise ValueError(
            f"the share asks for {count} profiles and the pool holds only {len(distinct)}."
        )
    ordered = sorted(distinct, key=lambda profile_no: _rank_key(seed, salt, profile_no))
    return tuple(sorted(ordered[:count]))
