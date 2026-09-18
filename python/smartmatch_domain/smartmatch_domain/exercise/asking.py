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
profile numbers and a share, it says *which* of them. The refresh itself
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
    "REQUIRED_NON_RESPONDING_SHARE",
    "AskingChoice",
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


def _rank_key(seed: int, salt: str, profile_no: int) -> tuple[bytes, int]:
    """A stable sort key for one profile, from a digest rather than a shuffle.

    Same reasoning as the simulation module: Python's ``hash()`` is salted per
    process, so a shuffle keyed on it would pick different profiles in a
    different process. The profile number is the second element so two profiles
    with the same digest still have one fixed order.
    """
    digest = hashlib.sha256(f"{seed}:{salt}:{profile_no}".encode()).digest()
    return digest, profile_no


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
