"""Design spec §13's refresh: who is asked, who answers, who stops answering.

One module for the policy, because there are **two** routes that run it — a
team's own ``POST …/refresh`` and the instructor's ``POST /refresh-all`` — and a
policy written twice is a policy that will be two policies. Both routers call
:func:`refresh_one_team`; neither reimplements a share.

What is decided here and what is not
====================================
Here: *which* profiles a share falls on, assembled from the domain's own
constants and the domain's own deterministic selector. Not here: what the shares
are (``smartmatch_domain.exercise.asking``, OQ-CE-04 closed), how a card is
copied (``results_repository.apply_refresh``, which is also the only code that
touches the withheld column on this path), and what HTTP any of it is (the two
routers).

ADR-0025 D6
===========
Nothing in this module reads a profile's hidden true interests. It passes
**profile numbers** to the repository and gets **counts** back; there is no
parameter and no return field here with a place to put an interest term.

OQ-CE-04 — the shares and the half-round in ``select_share``
============================================================
Closed 2026-09-25 (Ann Wang, email reply to the team's question list): 30 /
55 / 80 percent, plus 15 percent non-responding under "required". Ann gave no
view on halves, so Danny settled the half-rounding per the owner-doc
recommendation: **round half up**. ``asking.select_share`` rounds
``share * n`` half up in decimal arithmetic, so a group of ten at a share of
exactly ``0.05`` picks one, and a group of fifteen at thirty percent picks five.

The rounding lives in the domain's selector, not here: this module reads the
shares and calls the selector, and restates neither.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from smartmatch_domain.exercise.asking import (
    CARD_COMPLETION_SHARE,
    REQUIRED_NON_RESPONDING_SHARE,
    AskingChoice,
    select_share,
)

from smartmatch_api.exercise_dependencies import (
    ExerciseSession,
    RefreshCounts,
    ResultsRepository,
    TeamProfileRow,
)

__all__ = [
    "CARD_COMPLETION_SALT",
    "NON_RESPONDING_SALT",
    "RefreshPlan",
    "invited_without_a_card",
    "refresh_one_team",
    "refresh_plan",
]

#: What is being drawn, as the salt design spec §13's two draws are separated
#: by. Two salts over one seed draw independently, so the profiles that complete
#: a card and the profiles that stop answering are not the same people picked
#: twice — which they would be under one salt, making "required" a choice whose
#: cost fell exactly on the profiles it had just helped.
CARD_COMPLETION_SALT = "card_completion"
NON_RESPONDING_SALT = "non_responding"


@dataclass(frozen=True, slots=True)
class RefreshPlan:
    """Which profiles design spec §13's three effects fall on, for one team.

    Profile numbers only. Assembled from the team's own seed, so two teams that
    invited the same people and chose the same way still refresh differently —
    which is the point of a per-team seed.

    Attributes:
        topic_gainers: The round-one attended set, which gains the round-one
            event's topics under ``added_event_topics``.
        card_completers: The share of invited profiles with no card that complete
            one.
        non_responding: Under ``required`` only, the further share that stops
            opening messages and never signs up in round two. Empty for the other
            two ways of asking, which is the whole of what makes ``required``'s
            cost visible in the exercise.
    """

    topic_gainers: tuple[int, ...]
    card_completers: tuple[int, ...]
    non_responding: tuple[int, ...]


def invited_without_a_card(
    profiles: Sequence[TeamProfileRow], invited_profile_nos: Sequence[int]
) -> tuple[int, ...]:
    """The invited profiles this team has no card for, in profile-number order.

    "Has a card" follows ``exercise_matching_models._profile_evidence`` exactly:
    a card exists when **either** the overlay or the base row recorded interests,
    and ``card_career_goal`` alone does not conjure one. Reading it the same way
    in both places is what keeps the marker a team sees on its list and the group
    this refresh asks from the same set of people — two readings of "has a card"
    would show a team a completed card and then offer to complete it.

    ``NULL`` and ``{}`` stay distinct, which is design spec §7's three-state rule:
    an empty card is a card that was filled in with nothing, and asking its owner
    again is asking somebody who already answered.
    """
    wanted = set(invited_profile_nos)
    return tuple(
        profile.profile_no
        for profile in profiles
        if profile.profile_no in wanted
        and profile.overlay_card_interests is None
        and profile.stated_interests is None
    )


def refresh_plan(
    *,
    choice: AskingChoice,
    seed: int,
    attended_profile_nos: Sequence[int],
    no_card_profile_nos: Sequence[int],
) -> RefreshPlan:
    """Design spec §13's three groups, for one team, the same way every time.

    The shares are ``asking.CARD_COMPLETION_SHARE`` and
    ``asking.REQUIRED_NON_RESPONDING_SHARE`` — read, never restated. The
    selection is ``asking.select_share``, which draws from a digest over the
    team's seed rather than from :mod:`random`, so a refresh run twice picks the
    same profiles in any process (design spec §11's behaviour (4), applied to
    §13).

    See this module's docstring for the half-rounding inside ``select_share``
    (OQ-CE-04: round half up).
    """
    card_completers = select_share(
        no_card_profile_nos,
        CARD_COMPLETION_SHARE[choice],
        seed=seed,
        salt=CARD_COMPLETION_SALT,
    )
    non_responding = (
        select_share(
            no_card_profile_nos,
            REQUIRED_NON_RESPONDING_SHARE,
            seed=seed,
            salt=NON_RESPONDING_SALT,
        )
        if choice is AskingChoice.REQUIRED
        else ()
    )
    return RefreshPlan(
        topic_gainers=tuple(sorted(set(attended_profile_nos))),
        card_completers=card_completers,
        non_responding=non_responding,
    )


def refresh_one_team(
    session: ExerciseSession,
    results: ResultsRepository,
    *,
    dataset_id: uuid.UUID,
    workspace_id: uuid.UUID,
    seed: int,
    choice: AskingChoice,
    profiles: Sequence[TeamProfileRow],
    invited_profile_nos: Sequence[int],
    attended_profile_nos: Sequence[int],
    added_topics: Sequence[str],
    now: datetime,
) -> tuple[RefreshPlan, RefreshCounts] | None:
    """Plan and apply one team's refresh, or ``None`` when it may not refresh.

    ``None`` means the repository declined to claim the refresh — the team has
    not chosen, or it has already refreshed — which is a fact about the row and
    not an HTTP status. Both routers turn it into their own sentence.

    The plan is built **before** the claim is attempted and returned beside the
    counts, so a caller can report what was asked for and what landed without
    either of them being recomputed.

    Nothing here commits: the caller's transaction is what makes the claim and
    the overlay writes atomic, and ``get_exercise_session`` rolls back a request
    that forgot.
    """
    plan = refresh_plan(
        choice=choice,
        seed=seed,
        attended_profile_nos=attended_profile_nos,
        no_card_profile_nos=invited_without_a_card(profiles, invited_profile_nos),
    )
    counts = results.apply_refresh(
        session,
        dataset_id=dataset_id,
        workspace_id=workspace_id,
        added_topics=added_topics,
        topic_gainers=plan.topic_gainers,
        card_profile_nos=plan.card_completers,
        non_responding_profile_nos=plan.non_responding,
        now=now,
    )
    if counts is None:
        return None
    return plan, counts
