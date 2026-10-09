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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from smartmatch_domain.exercise.asking import (
    CARD_COMPLETION_SHARE,
    REQUIRED_NON_RESPONDING_SHARE,
    AskingChoice,
    select_share,
)
from smartmatch_domain.exercise.markers import InformationMarker, marker_for

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
    "RefreshReport",
    "invited_without_a_card",
    "marker_counts",
    "refresh_counts_from_view",
    "refresh_one_team",
    "refresh_plan",
    "refresh_report",
]

#: What is being drawn, as the salt design spec §13's two draws are separated
#: by. The card draw comes first; the non-responder draw then ranks only the
#: no-card profiles the card draw did not pick (owner ruling, 2026-09-25), so
#: the two groups never share a profile. Its own salt keeps its order unrelated
#: to the card draw's, so who stops answering is not simply "the next in line".
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


@dataclass(frozen=True, slots=True)
class RefreshReport:
    """What one team's refresh changed, as counts a screen can put in a sentence.

    Counts of people only (ADR-0025 D8): no share and no fraction, so the course's
    completion shares stay on the server. ``cards_completed`` beside
    ``invited_without_card`` is "12 of the 22"; the screen writes the words.

    Attributes:
        counts: The three counts the refresh has always reported.
        invited_without_card: How many of the people the team invited in round
            one had no card in the data file — the group that was asked.
        marker_counts_before: Every row of the data file by "how much we know",
            as the file itself has it.
        marker_counts_after: The same rows as this team sees them now.
    """

    counts: RefreshCounts
    invited_without_card: int
    marker_counts_before: Mapping[str, int]
    marker_counts_after: Mapping[str, int]


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

    **The two groups never overlap** (owner ruling, 2026-09-25). Under
    "required" the non-responders are drawn only from the no-card profiles that
    did *not* complete a card; their count is still the share of *every* no-card
    profile. A profile that filled in a card and also stopped answering was a
    contradiction the M1 class run found four times.
    """
    card_completers = select_share(
        no_card_profile_nos,
        CARD_COMPLETION_SHARE[choice],
        seed=seed,
        salt=CARD_COMPLETION_SALT,
    )
    completed = set(card_completers)
    still_without_a_card = [n for n in set(no_card_profile_nos) if n not in completed]
    non_responding = (
        select_share(
            still_without_a_card,
            REQUIRED_NON_RESPONDING_SHARE,
            seed=seed,
            salt=NON_RESPONDING_SALT,
            of_size=len(set(no_card_profile_nos)),
        )
        if choice is AskingChoice.REQUIRED
        else ()
    )
    return RefreshPlan(
        topic_gainers=tuple(sorted(set(attended_profile_nos))),
        card_completers=card_completers,
        non_responding=non_responding,
    )


def refresh_counts_from_view(profiles: Sequence[TeamProfileRow]) -> RefreshCounts:
    """The three refresh counts, read back from one team's view (M2 B4).

    The refresh is the only writer of these overlay columns, and a reset clears
    them, so the view *is* the stored record of what the refresh changed —
    whether the team pressed the button or the instructor refreshed every team.
    Reading it here means no new column and no second copy to drift:

    * a completed card is an overlay card (``overlay_card_interests`` set);
    * a non-responder is ``non_responding``;
    * a topic gainer is a profile whose overlay added any event topics.
    """
    return RefreshCounts(
        cards_completed=sum(1 for p in profiles if p.overlay_card_interests is not None),
        non_responding=sum(1 for p in profiles if p.non_responding),
        topics_added=sum(1 for p in profiles if p.overlay_added_event_topics),
    )


def marker_counts(profiles: Sequence[TeamProfileRow], *, with_overlay: bool) -> dict[str, int]:
    """How many of **every** row are in each "how much we know" group.

    ``with_overlay=False`` reads the data file's own columns and is the upload
    report's rule exactly (``ingest._markers``): a card when the file recorded
    interests, events when it recorded any past event, otherwise major only.
    ``with_overlay=True`` reads the same rows as this team now sees them — a
    card the team was given is a card, and added topics are one more event on
    file, which is how ``exercise_matching_models._profile_evidence`` reads them.

    Every row is counted, including one the file records no major for. That is
    the difference from the ranked list's own table, whose whole-file side is
    the rankable set: this count answers "all 300", and has to add up to it.

    All three groups are always present, so a screen can print "70 → 82" for
    a group nobody moved into without first checking a key exists.
    """
    counts = dict.fromkeys((str(marker) for marker in InformationMarker), 0)
    for profile in profiles:
        has_card = profile.stated_interests is not None
        attended = len(profile.past_event_keys)
        if with_overlay:
            has_card = has_card or profile.overlay_card_interests is not None
            attended += 1 if profile.overlay_added_event_topics else 0
        counts[str(marker_for(has_card=has_card, attended_event_count=attended))] += 1
    return counts


def refresh_report(
    profiles: Sequence[TeamProfileRow], invited_profile_nos: Sequence[int]
) -> RefreshReport:
    """Everything a screen says about one team's refresh, read from its view.

    Derived, never stored — :func:`refresh_counts_from_view`'s reasoning, taken
    two steps further. Given the team's view and the round-one invited list, the
    answer is the same whether it is asked in the request that refreshed, on a
    reload a week later, or for a team the instructor refreshed.

    ``invited_without_card`` reads the **base** row only. Before the refresh it
    equals ``len(invited_without_a_card(...))``, because a team has no overlay
    cards yet. After it, that function's answer shrinks — the new cards now read
    as cards — while this one stands, so "12 of the 22" keeps saying 22.
    """
    invited = set(invited_profile_nos)
    return RefreshReport(
        counts=refresh_counts_from_view(profiles),
        invited_without_card=sum(
            1 for p in profiles if p.profile_no in invited and p.stated_interests is None
        ),
        marker_counts_before=marker_counts(profiles, with_overlay=False),
        marker_counts_after=marker_counts(profiles, with_overlay=True),
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
        # An event with no topics gives nobody a topic; counting its attenders
        # as gainers made POST report N where the stored view (and GET) said 0.
        topic_gainers=plan.topic_gainers if added_topics else (),
        card_profile_nos=plan.card_completers,
        non_responding_profile_nos=plan.non_responding,
        now=now,
    )
    if counts is None:
        return None
    return plan, counts
