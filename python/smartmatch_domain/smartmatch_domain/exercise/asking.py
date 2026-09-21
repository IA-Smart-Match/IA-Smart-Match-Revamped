"""The three "asking for more" choices and what each one produces (§12).

Before the refresh, a team picks one of three ways to ask the profiles it
invited to complete a card. Ann's build table fixes what each one produces:

    promise better recommendations (about 30 percent of invited profiles
    without a card complete one); small reward (about 55 percent); required
    (about 80 percent, but about 15 percent of those without a card stop
    opening messages and never sign up in round two).

Those four numbers are **PLACEHOLDER (OQ-CE-04)** — the register's row says
"30 percent / 55 percent / 80 percent with 15 percent non-responding, as named
constants", and Ann confirms them before the November practice run. Unlike the
simulation's coefficients (OQ-CE-03, which has no proposed value at all), these
*are* stated values in Ann's own table, so they live here as named constants
rather than as ``None``.

The three choice names are not placeholders. They are fixed by design spec §12
and again by the database: the ``ck_exercise_team_workspace_asking_choice``
check constraint in ``db/migrations/versions/0037_exercise_tables.py`` admits
exactly ``better_recommendations``, ``small_reward``, and ``required``.

## What is here and what is not

:func:`select_share` is the pure, deterministic part of the refresh: given some
profile numbers and a share, it says *which* of them.
:func:`copied_card_career_goal` is the other pure part: given the base row's
career goal, it says what the copied card carries — **PLACEHOLDER (OQ-CE-13)**,
switchable in one line. The refresh itself
(design spec §13 — writing overlay rows, copying a card from the hidden true
interests, recomputing markers) is not here and cannot be: it needs the overlay
repository, and this package imports no persistence.

Nothing in this module reads a profile's hidden true interests, and nothing it
returns carries one: it takes profile numbers and returns profile numbers.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Final

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


#: PLACEHOLDER (OQ-CE-04): the share of *invited profiles without a card* that
#: complete one, per choice. Ann's build table's own numbers; she confirms them
#: before the November practice run. A read-only mapping so a caller cannot
#: quietly re-tune the exercise at runtime.
CARD_COMPLETION_SHARE: Final[Mapping[AskingChoice, float]] = MappingProxyType(
    {
        AskingChoice.BETTER_RECOMMENDATIONS: 0.30,
        AskingChoice.SMALL_REWARD: 0.55,
        AskingChoice.REQUIRED: 0.80,
    }
)

#: PLACEHOLDER (OQ-CE-04): under :attr:`AskingChoice.REQUIRED` only, the share
#: of invited profiles without a card that stop opening messages and never sign
#: up in round two. This is the cost the "required" choice carries, and the
#: point of the exercise's third option.
REQUIRED_NON_RESPONDING_SHARE: Final[float] = 0.15


class CopiedCardCareerGoal(StrEnum):
    """What career goal a card copied by design spec §13's refresh carries.

    The refresh copies *interests* out of the withheld column onto a team's
    overlay row. What the same card says about a career goal is a separate
    question, because the base row's ``career_goal`` is **not** withheld and is
    already visible to every team — so the copied card can either restate it or
    say nothing and let the base row stand.

    Both readings produce the same ranked list today (see
    :func:`copied_card_career_goal`), which is exactly why the rule has to be
    written down rather than inferred: it is invisible until something else
    changes, and then it is load-bearing.

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


#: PLACEHOLDER (OQ-CE-13): which reading design spec §13's copied card takes.
#:
#: The owner ruled on 2026-09-21 that *"copied cards carry the base
#: ``career_goal``; ``NULL`` only when the base has none"*, and the register row
#: **OQ-CE-13 is OPEN** pending Ann — so this is a placeholder in the same sense
#: the shares above are: a stated answer, held in one named place. Changing Ann's
#: answer is changing this one line; every caller takes it as a default.
COPIED_CARD_CAREER_GOAL: Final[CopiedCardCareerGoal] = CopiedCardCareerGoal.BASE_GOAL


def copied_card_career_goal(
    base_career_goal: str | None,
    policy: CopiedCardCareerGoal = COPIED_CARD_CAREER_GOAL,
) -> str | None:
    """The career goal a copied card carries, under ``policy``.

    Pure: it takes the base row's career goal and returns a value, and it is the
    **one** place either reading is written. A caller that wants the shipped
    reading passes no ``policy`` at all.

    Under :attr:`CopiedCardCareerGoal.BASE_GOAL` the answer is the base row's own
    goal — which is ``None`` when the base row has none, so "the base has no
    goal" and "the card says nothing" stay the same fact rather than becoming
    two. Under :attr:`CopiedCardCareerGoal.NONE` the answer is always ``None``.

    Why both give the same ranked list today: a reader resolves a team's view as
    overlay-over-base (``exercise_matching_models._profile_evidence``), so a
    copied card with no goal of its own already reads the base row's. Writing the
    goal makes that resolution explicit at the row rather than implicit in the
    reader; it does not move a profile.

    Args:
        base_career_goal: The base row's ``career_goal``, or ``None``.
        policy: Which reading to apply. Defaults to
            :data:`COPIED_CARD_CAREER_GOAL`.

    Returns:
        The value to store in ``exercise_profile_overlay.card_career_goal``, or
        ``None`` for "this card says nothing about a career goal".
    """
    if policy is CopiedCardCareerGoal.BASE_GOAL:
        return base_career_goal
    return None


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


def select_share(
    profile_nos: Iterable[int],
    share: float,
    *,
    seed: int,
    salt: str,
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
            ``round(share * n)`` — Python's banker's rounding, so a group of
            ten at a share of exactly ``0.05`` picks none rather than one.
        seed: The team's seed, so one team's refresh is another team's
            business.
        salt: What is being picked, e.g. ``"card_completion"``. Two calls with
            one seed and one salt agree; with different salts they do not.

    Returns:
        The picked profile numbers, sorted ascending and free of duplicates.

    Raises:
        ValueError: If ``share`` is outside ``[0, 1]``.
    """
    if not 0.0 <= share <= 1.0:
        raise ValueError(f"share must be between 0 and 1 inclusive; got {share}.")
    distinct = sorted(set(profile_nos))
    count = round(share * len(distinct))
    ordered = sorted(distinct, key=lambda profile_no: _rank_key(seed, salt, profile_no))
    return tuple(sorted(ordered[:count]))
