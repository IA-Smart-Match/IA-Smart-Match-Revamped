"""The results screen's routes (design spec §9–§13, ADR-0025 D6/D7/D8).

A team runs its invited list through the simulated-results rule once, reads the
three comparison panels, chooses how to ask the people who did not complete a
card, and refreshes its own view once. That is the whole of this module.

Every route is addressed by the workspace cookie
================================================
There is **no team number, dataset id or workspace id in any path, query or
body here**, exactly as in ``exercise_matching``. A team acts on its own
workspace and its own data file, both resolved from the ``exercise_workspace``
cookie by ``exercise_dependencies.get_current_workspace``. A client that could
name a workspace could name another team's, and in a product whose whole
identity is "somebody typed 4 on a classroom laptop" that is not a permission
check anybody could write.

The paths therefore differ from design spec §9's
``/v1/exercise/workspaces/{token}/…`` in the way the matching track's do: they
are ``/v1/exercise/workspaces/current/…``, because a token in a URL is a token in
a browser history, a referrer header and a projector.

The three rules this module exists to enforce
=============================================
1. **The lock** (§9). A run is refused unless ``exercise_result_unlock`` has a
   row for this data file and this event. The instructor writes that row.
2. **The one-run rule** (§9). ``uq_exercise_result_run_workspace_event`` — a
   constraint, not a count in code — and a second run is refused with the
   sentence the spec writes out.
3. **One refresh, after the choice** (§12, §13). The choice is a once-only
   ``UPDATE … WHERE asking_choice IS NULL``; the refresh is a once-only
   ``UPDATE … WHERE refreshed_at IS NULL``, claimed before any overlay row is
   written. Both live in the repository, where a concurrent second press meets a
   predicate rather than a read-then-write.

What this route runs on
=======================
The simulated-results rule's coefficients are the domain's, not this route's:
``simulation.EXERCISE_SIMULATION_COEFFICIENTS`` holds the team's translation of
Ann's answer of 2026-09-25, which Chau approved (wave-2 decision D7, closing
OQ-CE-03). If that value is ever ``None``, ``require_coefficients`` refuses and
``POST …/results`` answers one plain sentence. The tests exercise the full path by
injecting a clearly-labelled test-only coefficient set, so no pinned outcome
here moves when the shipped numbers do; no value is written into this file.

ADR-0025 D6, and why the docstrings are part of it
==================================================
FastAPI publishes a handler's docstring as its operation description, so a
docstring is a response field with extra steps. No docstring here, no ``Field``
description, no error sentence and no log line names the withheld column or any
value of it. ``tests/unit/test_exercise_results_router.py`` walks the models, the
handlers' docstrings and the whole exercise-scope OpenAPI document to say so.

The rule itself does read that column — it is the one thing the column is for
(§11) — through ``exercise_results_models.simulation_profiles``. What comes back
from the rule is profile numbers.

ADR-0025 D8
===========
Every number on every response here is a count of people or of chairs. The
shares design spec §12 names are applied on the server and reported as *how many
profiles*, never as *what fraction*.

Rate limiting (OQ-CE-06, owner Danny)
=====================================
Not built, for the reason the workspace and matching routers state: the
repository's limiter needs a principal or ``smartmatch_persistence``, and an
exercise router may import neither. What bounds these routes meanwhile is that
each of the three writes is permitted **once** per team — by a UNIQUE constraint
and by two once-only ``UPDATE`` predicates — so the work a caller can cause is
bounded by the six teams the product has.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Path, status
from smartmatch_domain.exercise.asking import AskingChoice

from smartmatch_api.exercise_dependencies import (
    CurrentWorkspace,
    DatasetRepository,
    ExerciseSession,
    ExerciseWorkspace,
    ResultsRepository,
    SettingsRepository,
    StoredResultRun,
    TeamResultsState,
    TeamViewRepository,
    require_exercise_request_header,
)
from smartmatch_api.exercise_errors import ExerciseError
from smartmatch_api.routers.exercise_matching_models import event_or_refusal
from smartmatch_api.routers.exercise_results_models import (
    FIRST_ROUND,
    AskingChoiceRequest,
    AskingStateView,
    RefreshView,
    ResultsView,
    RunResultsRequest,
    asking_state_view,
    stored_results_view,
)
from smartmatch_api.routers.exercise_results_refresh import refresh_one_team
from smartmatch_api.routers.exercise_results_run import (
    coefficients_or_refusal,
    final_setting_or_refusal,
    invited_list,
    run_the_rule,
    runnable_or_refusal,
    store,
)
from smartmatch_api.utils import utc_now

#: A bare assignment, not an annotated one, for ``exercise_public.router``'s
#: reason: the route ledger in ``tests/authz/test_policy_matrix.py`` reads router
#: prefixes out of the AST and matches ``name = APIRouter(...)``.
router = APIRouter(prefix="/v1/exercise/workspaces/current", tags=["class-exercise"])

#: Applied to every state-changing route in this module. Passed as a
#: ``dependencies`` entry rather than as a handler parameter so it cannot be
#: dropped by editing a signature.
_STATE_CHANGING = [Depends(require_exercise_request_header)]

# ---------------------------------------------------------------------------
# Resolving what a request is about
# ---------------------------------------------------------------------------


def _team_state_or_refusal(
    session: ExerciseSession, results: ResultsRepository, workspace: ExerciseWorkspace
) -> TeamResultsState:
    """This team's seed, choice and refresh state, or one plain sentence.

    The refusal is unreachable for a request whose cookie resolved a workspace —
    the row was read to resolve it — and is written anyway, because the
    alternative is an ``assert`` in a classroom.
    """
    team_state = results.team_state(session, workspace_id=workspace.id)
    if team_state is None:  # pragma: no cover - the cookie resolved this workspace
        raise ExerciseError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="exercise_workspace_required",
            message="Enter your team number to open your team's workspace.",
        )
    return team_state


def _round_one_or_none(
    session: ExerciseSession,
    results: ResultsRepository,
    *,
    workspace: ExerciseWorkspace,
    round_number: int,
) -> StoredResultRun | None:
    """This team's stored round-one run, when this is round two.

    Design spec §10's third panel. ``None`` in round one, where there is nothing
    earlier to compare with, and ``None`` in round two for a team that never ran
    round one — which the response reports as an absent panel rather than as a
    refusal, because a team is allowed to run the rounds out of order and the
    comparison is the part that is missing, not the results.
    """
    if round_number == FIRST_ROUND:
        return None
    return results.get_run_for_round(session, workspace_id=workspace.id, round_number=FIRST_ROUND)


# ---------------------------------------------------------------------------
# Results (design spec §9, §10, §11)
# ---------------------------------------------------------------------------


@router.post(
    "/events/{event_key}/results",
    response_model=ResultsView,
    dependencies=_STATE_CHANGING,
    status_code=status.HTTP_201_CREATED,
    summary="Run results for one event, once",
    # The body carries the required final setting, so the operation says the
    # body is required too — the component schema alone would let a generated
    # client send none. The handler still answers a missing body with the
    # exercise's own sentence (``Body(default_factory=...)`` below).
    openapi_extra={"requestBody": {"required": True}},
)
def run_results(
    session: ExerciseSession,
    workspace: CurrentWorkspace,
    datasets: DatasetRepository,
    team_view: TeamViewRepository,
    settings: SettingsRepository,
    results: ResultsRepository,
    event_key: str = Path(description="An event key from this team's data file."),
    payload: RunResultsRequest = Body(default_factory=RunResultsRequest),
) -> ResultsView:
    """Run your team's invited list through the results rule and keep the answer.

    Allowed **once** per team per event: the second attempt is refused with one
    sentence. Two presses arriving together cannot both succeed, because the
    write takes an advisory key and the table carries a UNIQUE constraint behind
    it — a read alone would not be enough. Allowed at all only after the
    instructor has unlocked this event.

    The invited list is the ranked list this team's screen shows, built from the
    team's **final setting**: ``setting_name`` is required and names one of the
    team's saved settings for this event (Ann to Chau, Discord, 2026-09-24).
    There is no run on the course's starting values.

    The answer carries three panels: your team's list, everybody in the data
    file through the same rule with the same seed, and — in round two — your
    team's stored round-one result.

    The rule the answer comes from is written in plain words in
    ``smartmatch_domain/exercise/simulation.py`` and is the statement the course
    owner receives. Its numbers are the ones Chau approved.

    The refusals come in this order, so the most useful sentence wins:

    1. The event — unknown (404), not a round, locked, already run (409). These
       say whether this event can be run at all, whatever the body says; telling
       a team that has already run to choose a setting would invite a second try.
    2. The final setting — left out or blank (422). The team's own step, so it
       is answered before anything the team cannot fix.
    3. The rule — no coefficient set (409). Only reachable if the approved set
       is removed; it would then refuse every run, so it comes before the
       team's own saved-setting lookup.
    4. The saved setting itself — not one this team saved (404).

    Raises:
        ExerciseError: 401 without a workspace cookie, 403 without the
            ``X-Exercise-Request`` header, 404 for an event or a saved setting
            this team does not have, 409 when the event is locked, is not one of
            the two rounds, has already been run, has no confirmed rule, or the
            write is refused, 422 without a final setting.
    """
    events, event, round_number = runnable_or_refusal(
        session, results, datasets=datasets, workspace=workspace, event_key=event_key
    )
    final_setting = final_setting_or_refusal(payload.setting_name)
    coefficients = coefficients_or_refusal()
    team_state = _team_state_or_refusal(session, results, workspace)
    profiles, invited, setting_name = invited_list(
        session,
        datasets=datasets,
        team_view=team_view,
        settings=settings,
        workspace=workspace,
        events=events,
        event=event,
        requested_setting=final_setting,
    )
    team, everyone = run_the_rule(
        session,
        datasets=datasets,
        profiles=profiles,
        event=event,
        workspace=workspace,
        invited=invited,
        seed=team_state.seed,
        coefficients=coefficients,
    )
    stored = store(
        session,
        results,
        workspace=workspace,
        event=event,
        round_number=round_number,
        setting_name=setting_name,
        team=team,
        everyone=everyone,
    )
    session.commit()
    return stored_results_view(
        stored,
        event=event,
        round_one=_round_one_or_none(
            session, results, workspace=workspace, round_number=round_number
        ),
    )


@router.get(
    "/events/{event_key}/results",
    response_model=ResultsView,
    summary="Your team's stored results for one event",
)
def read_results(
    session: ExerciseSession,
    workspace: CurrentWorkspace,
    datasets: DatasetRepository,
    results: ResultsRepository,
    event_key: str = Path(description="An event key from this team's data file."),
) -> ResultsView:
    """The run your team kept for this event, with the same three panels.

    Read from the stored row rather than recomputed, so a reload shows what the
    team was shown. That is what the one-run rule is for: the numbers are a
    record, not a recomputation.

    Raises:
        ExerciseError: 401 without a workspace cookie, 404 for an event that is
            not in this team's data file or for an event this team has not run.
    """
    events = datasets.list_events(session, dataset_id=workspace.dataset_id)
    event = event_or_refusal(events, event_key)
    stored = results.get_run(session, workspace_id=workspace.id, event_key=event.event_key)
    if stored is None:
        raise ExerciseError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="exercise_results_not_run",
            message="Your team has not run results for this event yet.",
        )
    return stored_results_view(
        stored,
        event=event,
        round_one=_round_one_or_none(
            session, results, workspace=workspace, round_number=stored.round
        ),
    )


# ---------------------------------------------------------------------------
# Asking for more (design spec §12) and the refresh (design spec §13)
# ---------------------------------------------------------------------------


@router.get(
    "/asking-choice",
    response_model=AskingStateView,
    summary="How your team chose to ask, and whether it has refreshed",
)
def read_asking_choice(
    session: ExerciseSession,
    workspace: CurrentWorkspace,
    results: ResultsRepository,
) -> AskingStateView:
    """What your team chose, the three choices it may make, and its refresh state.

    ``choices`` is on the response so a screen renders the three names it is
    offered rather than writing them into a component, which is the same reason
    the settings route returns ``max_settings``.

    Raises:
        ExerciseError: 401 when the cookie is absent or names no workspace.
    """
    team_state = _team_state_or_refusal(session, results, workspace)
    return asking_state_view(
        team_state.asking_choice, refreshed=team_state.refreshed_at is not None
    )


@router.post(
    "/asking-choice",
    response_model=AskingStateView,
    dependencies=_STATE_CHANGING,
    summary="Choose how your team asks for more",
)
def choose_asking(
    payload: AskingChoiceRequest,
    session: ExerciseSession,
    workspace: CurrentWorkspace,
    results: ResultsRepository,
) -> AskingStateView:
    """Store your team's one choice of how to ask, which unlocks the refresh.

    Design spec §12: one of three ways of asking, each of which brings in a
    different number of completed cards, and one of which costs your team people
    who stop answering altogether. The choice is stored once — a second choice is
    refused rather than quietly replacing the first, because the share it decides
    is what the refresh then applies.

    Raises:
        ExerciseError: 401 without a workspace cookie, 403 without the
            ``X-Exercise-Request`` header, 409 when this team has already chosen,
            422 for a choice that is not one of the three.
    """
    choice = _choice_or_refusal(payload.choice)
    if not results.choose_asking(session, workspace_id=workspace.id, choice=choice.value):
        raise ExerciseError(
            status_code=status.HTTP_409_CONFLICT,
            code="exercise_asking_already_chosen",
            message="Your team has already chosen how to ask.",
        )
    session.commit()
    team_state = _team_state_or_refusal(session, results, workspace)
    return asking_state_view(
        team_state.asking_choice, refreshed=team_state.refreshed_at is not None
    )


def _choice_or_refusal(raw: str) -> AskingChoice:
    """One of the three ways of asking, or one plain sentence.

    Matched against ``AskingChoice`` rather than against a list written here, so
    the names this route accepts, the names the refresh applies a share for, and
    the names ``ck_exercise_team_workspace_asking_choice`` admits are one set.

    The refusal quotes nothing the caller sent: these routes take no login, and a
    sentence on a projector is not the place to echo a stranger's string.
    """
    try:
        return AskingChoice(raw.strip())
    except ValueError:
        raise ExerciseError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="exercise_asking_choice_unknown",
            message="Pick one of the three ways of asking.",
        ) from None


@router.post(
    "/refresh",
    response_model=RefreshView,
    dependencies=_STATE_CHANGING,
    summary="Ask the people you invited, once",
)
def refresh_profiles(
    session: ExerciseSession,
    workspace: CurrentWorkspace,
    datasets: DatasetRepository,
    team_view: TeamViewRepository,
    results: ResultsRepository,
) -> RefreshView:
    """Apply your team's way of asking to your team's own view, once.

    Design spec §13, for this team and no other: everyone on your first round's
    attended list gains that event's topics; a share of the people you invited
    who had no card complete one; and under the third way of asking a further
    share stops answering and will not sign up in round two. How large each share
    is comes from the course's own numbers, which are not confirmed yet
    (OQ-CE-04).

    Allowed once, and only after the choice. Both are the database's own
    predicates rather than checks in code, so a second press cannot land while
    the first is still committing.

    Raises:
        ExerciseError: 401 without a workspace cookie, 403 without the
            ``X-Exercise-Request`` header, 409 when this team has not chosen, has
            already refreshed, or has not run the first round yet.
    """
    team_state = _team_state_or_refusal(session, results, workspace)
    if team_state.asking_choice is None:
        raise ExerciseError(
            status_code=status.HTTP_409_CONFLICT,
            code="exercise_asking_not_chosen",
            message="Choose how your team asks before refreshing.",
        )
    if team_state.refreshed_at is not None:
        raise _already_refreshed()
    first_round = results.get_run_for_round(
        session, workspace_id=workspace.id, round_number=FIRST_ROUND
    )
    if first_round is None:
        raise ExerciseError(
            status_code=status.HTTP_409_CONFLICT,
            code="exercise_no_first_round_results",
            message="Run the first round's results before refreshing.",
        )
    events = datasets.list_events(session, dataset_id=workspace.dataset_id)
    event = event_or_refusal(events, first_round.event_key)
    profiles = team_view.list_team_profiles(
        session, dataset_id=workspace.dataset_id, workspace_id=workspace.id
    )
    choice = AskingChoice(team_state.asking_choice)
    applied = refresh_one_team(
        session,
        results,
        dataset_id=workspace.dataset_id,
        workspace_id=workspace.id,
        seed=team_state.seed,
        choice=choice,
        profiles=profiles,
        invited_profile_nos=first_round.team.invited_profile_nos,
        attended_profile_nos=first_round.team.attended_profile_nos,
        added_topics=event.topic_tags,
        now=utc_now(),
    )
    if applied is None:
        raise _already_refreshed()
    _, counts = applied
    session.commit()
    return RefreshView(
        choice=choice.value,
        cards_completed=counts.cards_completed,
        non_responding=counts.non_responding,
        topics_added=counts.topics_added,
    )


def _already_refreshed() -> ExerciseError:
    """One sentence for a second refresh, raised from the check and from the race."""
    return ExerciseError(
        status_code=status.HTTP_409_CONFLICT,
        code="exercise_already_refreshed",
        message="Your team has already asked the people it invited.",
    )
