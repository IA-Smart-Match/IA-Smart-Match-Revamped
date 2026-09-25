"""What the results routes return, and the arithmetic that has no HTTP in it.

Split from ``exercise_results.py`` the way ``exercise_matching_models`` is split
from ``exercise_matching``: this module holds the response contract, the step
that turns stored rows into the domain's simulation inputs, and the derivation
of a run's *round*. Nothing here imports FastAPI and nothing here decides a
status code.

ADR-0025 D6 — the withheld columns
==================================
:func:`simulation_profiles` is the one function in the API package that reads a
profile's hidden true interests and hidden true career goal, and it reads them
**into** :class:`~smartmatch_domain.exercise.simulation.SimulationProfile` — the
input of design spec §11's rule, which is what the columns exist for. The goal
goes in as the topic it points at (``vocabulary.goal_topic_for_matching``, the
same table the ranker reads). From there the values go nowhere: the rule
returns profile numbers, the panels below carry profile numbers, and no model in
this module has a field with a place to put an interest term or a goal.

The two ways such a value escapes without anybody writing a line that names it
are both shut. A response model cannot carry it, because none of them has the
field — ``tests/unit/test_exercise_results_router.py`` walks every model here,
every handler docstring (FastAPI publishes those as operation descriptions) and
the whole exercise-scope OpenAPI document. And a ``repr`` cannot print it,
because both types that hold it declare the field ``repr=False``:
``dataset_repository.SimulationProfileRow`` already did, and
``simulation.SimulationProfile`` now does for the same reason.

ADR-0025 D8 — no numeric score
==============================
Every number on every model below is a count of people or of chairs:
``invited_count``, ``seats_empty``, ``event_seats``, ``existing_signups``,
``cards_completed``. ``round`` is 1 or 2. There is no probability, no share and
no percentage anywhere on a response — the shares design spec §12 names are
applied on the server and reported as *how many profiles*, never as *what
fraction*.

PLACEHOLDER (OQ-CE-03)
======================
The simulated-results rule ships no coefficients: the register says "Chau
proposes; Ann confirms" and nothing has been confirmed.
``simulation.require_coefficients`` refuses until that changes, and
:func:`~smartmatch_api.routers.exercise_results.run_results` turns that refusal
into one plain sentence. That is the correct behaviour of this route today, not
a gap in it — a number invented here would be an unreviewed coefficient on a
projector under Ann's name.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, model_validator
from smartmatch_domain.exercise.asking import AskingChoice
from smartmatch_domain.exercise.simulation import (
    EVENT_SEATS,
    EXISTING_SIGNUPS,
    SimulationEvent,
    SimulationProfile,
)
from smartmatch_domain.exercise.vocabulary import goal_topic_for_matching

from smartmatch_api.exercise_dependencies import (
    ExerciseEventRow,
    ResultPanel,
    SimulationProfileRow,
    StoredResultRun,
)

__all__ = [
    "EXERCISE_ROUNDS",
    "FIRST_ROUND",
    "MAX_ASKING_CHOICE_CHARACTERS",
    "AskingChoiceRequest",
    "AskingStateView",
    "PreviousRoundView",
    "RefreshAllView",
    "RefreshView",
    "ResultPanelView",
    "ResultsView",
    "RunResultsRequest",
    "asking_state_view",
    "panel_view",
    "previous_round_view",
    "round_of",
    "row_is_round",
    "simulation_event",
    "simulation_profiles",
    "stored_results_view",
]

#: How many rounds the case has. Two — Northline and Harbor — which design spec
#: §2 states and ``ck_exercise_result_run_round`` enforces as ``round IN (1, 2)``.
#: A case fact, not a placeholder: no open question governs it.
EXERCISE_ROUNDS: Final[int] = 2

#: The round design spec §13's refresh reads and adds the topics of. One, by
#: definition: the refresh happens *between* the two rounds. Named here rather
#: than in each router so the two routes that run a refresh cannot disagree about
#: which round they are reading.
FIRST_ROUND: Final[int] = 1

#: The longest an asking choice may be before it is refused unread.
#:
#: Generous against the longest of the three names the domain declares, and
#: short enough that the value cannot be a payload. It exists because these
#: routes take no login: a refusal that echoed a caller's string would reflect
#: the caller's own text onto a classroom projector, and a refusal that ran
#: through pydantic's per-field validation would put the value in an error
#: ``loc``. See :meth:`AskingChoiceRequest._refuse_oversized_choice`.
MAX_ASKING_CHOICE_CHARACTERS: Final[int] = 64


# ---------------------------------------------------------------------------
# The stored row -> domain value step
# ---------------------------------------------------------------------------


def round_of(events: Sequence[ExerciseEventRow], event_key: str) -> int | None:
    """Which round an event is, or ``None`` when it is not one of the rounds.

    **Derived from the data file, never written down.** Design spec §2: the file
    carries ten past events and then the two the teams run, and
    ``is_exercise_event`` is what tells them apart. So round one is the first
    exercise event by ``sequence`` and round two is the second — read off the
    rows rather than matched against a name, because the two events' names are
    Ann's data and may change from one file to the next.

    ``None`` for a past event, and for a third exercise event in a file that
    somehow carried one: ``exercise_result_run.round`` admits 1 and 2 and a run
    that cannot say which round it is has nothing to store. The route turns that
    into one plain sentence rather than a constraint violation.
    """
    in_file_order = sorted(events, key=lambda row: row.sequence)
    rounds = [event for event in in_file_order if row_is_round(event)]
    for position, event in enumerate(rounds[:EXERCISE_ROUNDS], start=1):
        if event.event_key == event_key:
            return position
    return None


def row_is_round(event: ExerciseEventRow) -> bool:
    """Whether one stored event is one the teams run."""
    return event.is_exercise_event


def simulation_event(event: ExerciseEventRow) -> SimulationEvent:
    """One stored event as design spec §11's rule reads it."""
    return SimulationEvent(
        event_key=event.event_key,
        topic_tags=frozenset(event.topic_tags),
        target_majors=frozenset(event.target_majors),
    )


def simulation_profiles(
    rows: Sequence[SimulationProfileRow],
    *,
    non_responding_profile_nos: frozenset[int],
) -> tuple[SimulationProfile, ...]:
    """Stored profiles as design spec §11's rule reads them, in file order.

    The rule reads a profile's **hidden true interests** and the topic its
    **hidden true career goal** points at, which is what those columns are for
    and what makes "a list built on what the app knows can miss people" true
    rather than asserted. This function is where those rows become
    rule inputs; see this module's docstring for why that is the whole of their
    journey.

    ``major`` is ``""`` for a row the file records none for. The rule compares
    normalised terms against the event's target majors, so an empty string
    matches nothing and earns no same-major lift — which is the right answer for
    a profile whose major is not on file, and is *not* a penalty: it collects
    every other lift exactly as it would otherwise (ADR-0011).

    ``past_event_count`` is how many past events the row records, which is what
    the rule's "frequent attender" threshold counts. The overlay's added topics
    are not counted: design spec §13 adds *topics*, not attendances, and a team's
    refresh must not make a profile a frequent attender of an event that has not
    happened yet.

    Args:
        rows: The data file's profiles, including the withheld columns.
        non_responding_profile_nos: Profiles this team's refresh marked as asked
            and not answering (design spec §13, under ``required`` only). Passed
            in rather than read here because it is a fact about *one team's*
            overlay and these rows are the file's.
    """
    return tuple(
        SimulationProfile(
            profile_no=row.profile_no,
            major=row.major or "",
            true_interests=frozenset(row.hidden_true_interests),
            career_goal=goal_topic_for_matching(row.hidden_true_career_goal),
            past_event_count=len(row.past_event_keys),
            non_responding=row.profile_no in non_responding_profile_nos,
        )
        for row in rows
    )


# ---------------------------------------------------------------------------
# The request contract
# ---------------------------------------------------------------------------


_FINAL_SETTING_DESCRIPTION = (
    "Your team's final setting: the name of one of your saved settings for this "
    "event. The invited list is built from it. Required."
)


def _publish_the_final_setting_as_required(schema: dict[str, Any]) -> None:
    """Publish ``setting_name`` as the required, non-blank string it is.

    The field is **optional to pydantic on purpose**. A body without it has to
    reach the handler, so that the refusal is one plain sentence in the
    exercise's own shape *and* comes after the event's own refusals (locked,
    already run) — see ``exercise_results_run.final_setting_or_refusal``. A
    pydantic-required field would be refused by FastAPI's validation envelope
    before the handler ran, ahead of every other sentence.

    The published contract is still the rule: a run without a final setting
    never succeeds, so a client is told it must send one.
    """
    schema["properties"]["setting_name"] = {
        "type": "string",
        "minLength": 1,
        "title": "Setting Name",
        "description": _FINAL_SETTING_DESCRIPTION,
    }
    schema["required"] = ["setting_name"]


class RunResultsRequest(BaseModel):
    """The body of a run: the team's final setting (Ann to Chau, Discord, 2026-09-24).

    The owner's flow is: set weights, save up to three settings and compare two,
    **choose one final setting**, then run once after the instructor unlocks the
    event. There is no run on the course's starting values; a team that wants
    them saves them under a name like any other setting.
    """

    model_config = ConfigDict(
        extra="forbid", json_schema_extra=_publish_the_final_setting_as_required
    )

    setting_name: str | None = Field(default=None, description=_FINAL_SETTING_DESCRIPTION)


class AskingChoiceRequest(BaseModel):
    """The body of design spec §12's choice: one of three names, and nothing else."""

    model_config = ConfigDict(extra="forbid")

    choice: str = Field(
        description=(
            "One of `better_recommendations`, `small_reward` or `required`. "
            f"At most {MAX_ASKING_CHOICE_CHARACTERS} characters."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _refuse_oversized_choice(cls, data: object) -> object:
        """Bound the value **before** pydantic can quote it back.

        Review round 2's F2 on PR #188, applied to the one string this track
        accepts from a client. ``smartmatch_api.errors._describe_validation_error``
        builds its ``field`` from the error's ``loc`` and its message from the
        validator that failed, so a value refused *inside* pydantic can reach the
        response; ``mode="before"`` sees the raw mapping and can refuse the shape
        while there is still nothing to put in a ``loc``.

        The refusal names no value and quotes no length the caller chose — a
        refusal about a payload being too large is the last place to echo the
        payload.
        """
        if not isinstance(data, dict):
            return data
        choice = data.get("choice")
        if isinstance(choice, str) and len(choice) > MAX_ASKING_CHOICE_CHARACTERS:
            raise ValueError("choice: too long to be one of the three ways of asking")
        return data


# ---------------------------------------------------------------------------
# The response contract
# ---------------------------------------------------------------------------


class ResultPanelView(BaseModel):
    """One panel of design spec §10: who was invited, who signed up, who came.

    Profile numbers and counts. No name, no major, no interest and no number
    that ranks a person (ADR-0025 D6 and D8) — a screen that wants the names
    reads them from the ranked list, which is the route that already has them.

    The counts sit beside the lists rather than being left to the reader,
    because the three numbers are what the comparison is *about*: a team reads
    "eleven of thirty signed up" off this panel and "sixty of three hundred" off
    the other.
    """

    model_config = ConfigDict(extra="forbid")

    invited_profile_nos: list[int] = Field(description="The profiles the run was given.")
    signed_up_profile_nos: list[int] = Field(description="Those of them that signed up.")
    attended_profile_nos: list[int] = Field(description="Those of the sign-ups that attended.")
    invited_count: int = Field(description="How many were invited.")
    signed_up_count: int = Field(description="How many signed up.")
    attended_count: int = Field(description="How many attended.")


class PreviousRoundView(BaseModel):
    """Design spec §10's third panel: what this team's earlier round did."""

    model_config = ConfigDict(extra="forbid")

    event_key: str = Field(description="The event that round was for.")
    round: int = Field(description="Which round it was. 1 or 2.")
    setting_name: str | None = Field(
        default=None, description="The saved setting that run's list came from, or null."
    )
    team: ResultPanelView = Field(description="That round's invited, signed up and attended.")
    seats_empty: int = Field(description="The seats still empty after that round.")
    created_at: datetime = Field(description="When that round was run.")


class ResultsView(BaseModel):
    """One team's results for one event: design spec §10's three panels.

    The three are always present as fields. ``round_one`` is ``null`` in round
    one, because there is no earlier round to compare with — a screen that has a
    panel for it can say so rather than discovering a missing key.
    """

    model_config = ConfigDict(extra="forbid")

    event_key: str = Field(description="The event these results are for.")
    event_name: str = Field(description="That event's label, as the data file spells it.")
    round: int = Field(description="Which round this is. 1 or 2.")
    setting_name: str | None = Field(
        default=None,
        description="The saved setting the invited list came from, or null when it did not.",
    )
    team: ResultPanelView = Field(description="Your team's own list through the results rule.")
    email_everyone: ResultPanelView = Field(
        description=(
            "Everybody in the data file through the same rule with the same "
            "seed, so the two panels are comparable rather than two different "
            "simulations."
        ),
    )
    seats_empty: int = Field(
        description=(
            "Seats still empty after this round: the room's seats, less the "
            "sign-ups the event already had, less the people who attended."
        ),
    )
    event_seats: int = Field(description="Seats in the room, from the case.")
    existing_signups: int = Field(
        description="Sign-ups the event already had before anybody was invited, from the case."
    )
    round_one: PreviousRoundView | None = Field(
        default=None, description="Your team's stored round-one result, in round two."
    )
    created_at: datetime = Field(description="When this run was stored.")


class AskingStateView(BaseModel):
    """Design spec §12: how this team chose to ask, and whether it has refreshed."""

    model_config = ConfigDict(extra="forbid")

    choice: str | None = Field(
        default=None, description="What your team chose, or null before it has chosen."
    )
    choices: list[str] = Field(description="The three ways of asking, as the course names them.")
    refreshed: bool = Field(description="Whether your team has already used its one refresh.")


class RefreshView(BaseModel):
    """Design spec §13: what one refresh changed, in three counts."""

    model_config = ConfigDict(extra="forbid")

    choice: str = Field(description="The way of asking this refresh applied.")
    cards_completed: int = Field(description="How many invited profiles completed a card.")
    non_responding: int = Field(
        description=(
            "How many stopped opening messages and will not sign up in round "
            "two. Only the `required` way of asking produces any."
        ),
    )
    topics_added: int = Field(
        description="How many profiles gained the first round's topics from having attended it."
    )


class RefreshAllView(BaseModel):
    """Design spec §14's "refresh all", as what it did to the classroom."""

    model_config = ConfigDict(extra="forbid")

    refreshed_team_numbers: list[int] = Field(
        description="The teams that were refreshed, in the order they were visited."
    )
    refreshed: int = Field(description="How many teams were refreshed.")
    skipped: int = Field(
        description=(
            "How many teams had chosen but could not be refreshed yet, because "
            "they have not run the first round's results."
        ),
    )


# ---------------------------------------------------------------------------
# Building the views
# ---------------------------------------------------------------------------


def panel_view(panel: ResultPanel) -> ResultPanelView:
    """One stored or freshly run panel as a response.

    The counts are derived here rather than stored, which is the opposite of
    ``seats_empty``'s treatment and deliberately so: a count of a list that is on
    the same response cannot disagree with it, whereas ``seats_empty`` depends on
    two case constants that a later change must not silently restate.
    """
    return ResultPanelView(
        invited_profile_nos=list(panel.invited_profile_nos),
        signed_up_profile_nos=list(panel.signed_up_profile_nos),
        attended_profile_nos=list(panel.attended_profile_nos),
        invited_count=len(panel.invited_profile_nos),
        signed_up_count=len(panel.signed_up_profile_nos),
        attended_count=len(panel.attended_profile_nos),
    )


def previous_round_view(run: StoredResultRun) -> PreviousRoundView:
    """A stored earlier run as design spec §10's third panel."""
    return PreviousRoundView(
        event_key=run.event_key,
        round=run.round,
        setting_name=run.setting_name,
        team=panel_view(run.team),
        seats_empty=run.seats_empty,
        created_at=run.created_at,
    )


def stored_results_view(
    run: StoredResultRun,
    *,
    event: ExerciseEventRow,
    round_one: StoredResultRun | None,
) -> ResultsView:
    """One stored run as the full three-panel response.

    Built from the **stored** row on both the write and the read path, so a team
    that reloads the screen sees the run it was shown rather than the run the
    rule would produce now. That is what makes the one-run rule mean something:
    the numbers are a record, not a recomputation.
    """
    return ResultsView(
        event_key=run.event_key,
        event_name=event.name,
        round=run.round,
        setting_name=run.setting_name,
        team=panel_view(run.team),
        email_everyone=panel_view(run.email_everyone),
        seats_empty=run.seats_empty,
        event_seats=EVENT_SEATS,
        existing_signups=EXISTING_SIGNUPS,
        round_one=previous_round_view(round_one) if round_one is not None else None,
        created_at=run.created_at,
    )


def asking_state_view(choice: str | None, *, refreshed: bool) -> AskingStateView:
    """This team's asking choice, with the three names read off the domain.

    ``choices`` comes from :class:`~smartmatch_domain.exercise.asking.AskingChoice`
    rather than from a list written here, so the three names on the response, the
    three the refresh applies a share for, and the three
    ``ck_exercise_team_workspace_asking_choice`` admits cannot drift apart.
    """
    return AskingStateView(
        choice=choice,
        choices=[member.value for member in AskingChoice],
        refreshed=refreshed,
    )
