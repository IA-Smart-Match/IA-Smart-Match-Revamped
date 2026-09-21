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

PLACEHOLDER (OQ-CE-03) — and why this route refuses today
=========================================================
The simulated-results rule ships **no coefficients**: the register says "Chau
proposes; Ann confirms" and nothing has been confirmed, so
``simulation.EXERCISE_SIMULATION_COEFFICIENTS`` is ``None`` and
``require_coefficients`` refuses. ``POST …/results`` therefore answers one plain
sentence naming the open question. **That is this route working**, not this
route unfinished: a number invented here would be an unreviewed coefficient on a
classroom projector under Ann's name. The tests exercise the full path by
injecting a clearly-labelled test-only coefficient set; no value is written into
any source file.

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

from collections.abc import Mapping, Sequence

from fastapi import APIRouter, Body, Depends, Path, status
from smartmatch_domain.exercise.asking import AskingChoice
from smartmatch_domain.exercise.matching import exercise_ranked_list
from smartmatch_domain.exercise.simulation import (
    CoefficientsNotConfirmedError,
    InviteLimitExceededError,
    SimulationCoefficients,
    require_coefficients,
    run_email_everyone,
    seats_empty,
    simulate_results,
)

from smartmatch_api.exercise_dependencies import (
    AlreadyRunError,
    CurrentWorkspace,
    DatasetRepository,
    ExerciseEventRow,
    ExerciseResultsWriteRefused,
    ExerciseSession,
    ExerciseWorkspace,
    ResultPanel,
    ResultsRepository,
    SettingsRepository,
    StoredResultRun,
    TeamProfileRow,
    TeamResultsState,
    TeamViewRepository,
    require_exercise_request_header,
)
from smartmatch_api.exercise_errors import ExerciseError
from smartmatch_api.routers.exercise_matching import event_or_refusal
from smartmatch_api.routers.exercise_matching_models import (
    event_evidence,
    rankable_set,
)
from smartmatch_api.routers.exercise_matching_weights import validated
from smartmatch_api.routers.exercise_results_models import (
    FIRST_ROUND,
    AskingChoiceRequest,
    AskingStateView,
    RefreshView,
    ResultsView,
    RunResultsRequest,
    asking_state_view,
    round_of,
    simulation_event,
    simulation_profiles,
    stored_results_view,
)
from smartmatch_api.routers.exercise_results_refresh import refresh_one_team
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


def _round_or_refusal(events: Sequence[ExerciseEventRow], event_key: str) -> int:
    """Which round this event is, or one plain sentence.

    Read off the data file's own rows by ``round_of`` — the exercise events in
    sequence order — rather than matched against a name, because the two names
    are Ann's and OQ-CE-01 is open.

    A past event has no round, and ``exercise_result_run.round`` admits 1 and 2,
    so a run for one has nothing to store. Refusing it here makes that a sentence
    a class participant can read rather than a constraint violation.
    """
    number = round_of(events, event_key)
    if number is None:
        raise ExerciseError(
            status_code=status.HTTP_409_CONFLICT,
            code="exercise_event_is_not_a_round",
            message="Results are only run for the two rounds of the exercise.",
        )
    return number


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


def _coefficients_or_refusal() -> SimulationCoefficients:
    """The results rule's coefficients, or **OQ-CE-03's own sentence**.

    The register's answer is "Chau proposes; Ann confirms", and nothing has been
    confirmed — so the domain ships none and refuses. The sentence a team reads
    is the domain's, passed through unchanged rather than rewritten here: the
    open question's identifier belongs in it, and two wordings of "this is not
    decided yet" would be one more than the question has.
    """
    try:
        return require_coefficients()
    except CoefficientsNotConfirmedError as error:
        raise ExerciseError(
            status_code=status.HTTP_409_CONFLICT,
            code="exercise_results_rule_not_confirmed",
            message=str(error),
        ) from None


def _weights_or_refusal(
    session: ExerciseSession,
    settings: SettingsRepository,
    *,
    workspace: ExerciseWorkspace,
    event_key: str,
    setting_name: str | None,
) -> tuple[Mapping[str, float] | None, str | None]:
    """The weighting a run's list is built from, and the name to store for it.

    ``None`` weights mean the course's starting values (OQ-CE-02), which
    ``exercise_ranked_list`` resolves through the exercise rulebook — not
    restated here, so there is one answer to what the defaults are.

    Re-validated on the way out rather than trusted because it was validated on
    the way in, for ``exercise_matching._saved_weights_or_refusal``'s reason: the
    rulebook is a value object and a later version could name different factors,
    at which point a stored weighting is input again.
    """
    if setting_name is None:
        return None, None
    name = setting_name.strip()
    stored = settings.get_setting(
        session, workspace_id=workspace.id, event_key=event_key, name=name
    )
    if stored is None:
        raise ExerciseError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="exercise_setting_unknown",
            message="Your team has no saved settings with that name.",
        )
    return validated(dict(stored.weights)), name


def _invited_profile_nos(
    session: ExerciseSession,
    *,
    datasets: DatasetRepository,
    profiles: Sequence[TeamProfileRow],
    events: Sequence[ExerciseEventRow],
    event: ExerciseEventRow,
    workspace: ExerciseWorkspace,
    weights: Mapping[str, float] | None,
) -> tuple[int, ...]:
    """The ranked list's profile numbers, in order — the team's invited set.

    **Composed, never re-derived.** The order, the cut at the invite limit and
    the tie-break are ``exercise_ranked_list``'s, reached through the same
    ``rankable_set`` / ``event_evidence`` helpers the matching routes use, so the
    names a team invited are the names its screen showed it. Re-deriving them
    here would be a second ranker, and the failure mode of two rankers is a team
    told it invited somebody it did not.

    The year rank is ``rankable_set``'s ``PLACEHOLDER_CLASS_YEAR_RANK`` (empty
    while OQ-CE-01 is open); this module does not touch it.
    """
    summary = datasets.get_dataset_summary(session, dataset_id=workspace.dataset_id)
    if summary is None:  # pragma: no cover - the cookie resolved a workspace on it
        raise ExerciseError(
            status_code=status.HTTP_409_CONFLICT,
            code="exercise_no_dataset",
            message="The instructor has not loaded the student body yet.",
        )
    rankable = rankable_set(profiles, events)
    ranked = exercise_ranked_list(
        event_evidence(event),
        rankable.profiles,
        weights=weights,
        invite_limit=summary.invite_limit,
        year_rank=rankable.year_rank,
        dataset_checksum=summary.checksum,
    )
    return tuple(int(entry.profile_id) for entry in ranked.entries)


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
    sentence, and it is the database's UNIQUE constraint rather than a check in
    code that decides, so two presses arriving together cannot both succeed.
    Allowed at all only after the instructor has unlocked this event.

    The invited list is the ranked list this team's screen shows, built from a
    saved weighting when ``setting_name`` names one and from the course's
    starting values otherwise. The answer carries three panels: your team's list,
    everybody in the data file through the same rule with the same seed, and — in
    round two — your team's stored round-one result.

    The rule the answer comes from is written in plain words in
    ``smartmatch_domain/exercise/simulation.py`` and is the statement the course
    owner receives. Its coefficients are **not decided yet** (OQ-CE-03), so this
    route refuses with one sentence naming that question until they are.

    Raises:
        ExerciseError: 401 without a workspace cookie, 403 without the
            ``X-Exercise-Request`` header, 404 for an event or a saved setting
            this team does not have, 409 when the event is locked, is not one of
            the two rounds, has already been run, has no confirmed rule, or the
            write is refused.
    """
    events = datasets.list_events(session, dataset_id=workspace.dataset_id)
    event = event_or_refusal(events, event_key)
    round_number = _round_or_refusal(events, event.event_key)
    if not results.results_unlocked(
        session, dataset_id=workspace.dataset_id, event_key=event.event_key
    ):
        raise ExerciseError(
            status_code=status.HTTP_409_CONFLICT,
            code="exercise_results_locked",
            message="The instructor has not opened results for this event yet.",
        )
    if results.get_run(session, workspace_id=workspace.id, event_key=event.event_key) is not None:
        raise _already_run()
    coefficients = _coefficients_or_refusal()
    team_state = _team_state_or_refusal(session, results, workspace)
    weights, setting_name = _weights_or_refusal(
        session,
        settings,
        workspace=workspace,
        event_key=event.event_key,
        setting_name=payload.setting_name,
    )
    profiles = team_view.list_team_profiles(
        session, dataset_id=workspace.dataset_id, workspace_id=workspace.id
    )
    invited = _invited_profile_nos(
        session,
        datasets=datasets,
        profiles=profiles,
        events=events,
        event=event,
        workspace=workspace,
        weights=weights,
    )
    team, everyone = _run_the_rule(
        session,
        datasets=datasets,
        profiles=profiles,
        event=event,
        workspace=workspace,
        invited=invited,
        seed=team_state.seed,
        coefficients=coefficients,
    )
    stored = _store(
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


def _run_the_rule(
    session: ExerciseSession,
    *,
    datasets: DatasetRepository,
    profiles: Sequence[TeamProfileRow],
    event: ExerciseEventRow,
    workspace: ExerciseWorkspace,
    invited: Sequence[int],
    seed: int,
    coefficients: SimulationCoefficients,
) -> tuple[ResultPanel, ResultPanel]:
    """Design spec §10's first two panels, from one load and one seed.

    **The same seed for both**, which is what makes them a comparison rather than
    two simulations: a profile on both lists has the same outcome in both, so the
    difference a team reads is the difference between *who was asked*, which is
    the lesson.

    Profiles this team's refresh marked as not answering are carried into both
    panels, so design spec §13's cost under ``required`` shows up in round two on
    the team's list and in what "email everyone" would have got.
    """
    rows = datasets.load_simulation_profiles(session, dataset_id=workspace.dataset_id)
    silent = frozenset(profile.profile_no for profile in profiles if profile.non_responding)
    everybody = simulation_profiles(rows, non_responding_profile_nos=silent)
    wanted = set(invited)
    invited_profiles = tuple(profile for profile in everybody if profile.profile_no in wanted)
    simulation = simulation_event(event)
    try:
        team = simulate_results(
            invited_profiles,
            simulation,
            seed=seed,
            coefficients=coefficients,
            invite_limit=workspace.invite_limit,
        )
    except InviteLimitExceededError as error:
        raise ExerciseError(
            status_code=status.HTTP_409_CONFLICT,
            code="exercise_invite_limit_exceeded",
            message=str(error),
        ) from None
    everyone = run_email_everyone(everybody, simulation, seed=seed, coefficients=coefficients)
    return (
        ResultPanel(
            invited_profile_nos=team.invited,
            signed_up_profile_nos=team.signed_up,
            attended_profile_nos=team.attended,
        ),
        ResultPanel(
            invited_profile_nos=everyone.invited,
            signed_up_profile_nos=everyone.signed_up,
            attended_profile_nos=everyone.attended,
        ),
    )


def _store(
    session: ExerciseSession,
    results: ResultsRepository,
    *,
    workspace: ExerciseWorkspace,
    event: ExerciseEventRow,
    round_number: int,
    setting_name: str | None,
    team: ResultPanel,
    everyone: ResultPanel,
) -> StoredResultRun:
    """Write the run, turning the repository's two refusals into two sentences."""
    try:
        return results.record_run(
            session,
            dataset_id=workspace.dataset_id,
            workspace_id=workspace.id,
            event_key=event.event_key,
            round_number=round_number,
            setting_name=setting_name,
            team=team,
            email_everyone=everyone,
            seats_empty=seats_empty(len(team.attended_profile_nos)),
        )
    except AlreadyRunError:
        raise _already_run() from None
    except ExerciseResultsWriteRefused as error:
        raise ExerciseError(
            status_code=status.HTTP_409_CONFLICT,
            code="exercise_results_write_refused",
            message=str(error),
        ) from None


def _already_run() -> ExerciseError:
    """Design spec §9's sentence, written once and raised from two places.

    The spec writes it out, so it is stored on the repository as
    ``ALREADY_RUN_SENTENCE`` and reaches here as the exception's message rather
    than as a second copy of the words.
    """
    return ExerciseError(
        status_code=status.HTTP_409_CONFLICT,
        code="exercise_results_already_run",
        message=str(AlreadyRunError()),
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
    return asking_state_view(team_state.asking_choice, refreshed=team_state.refreshed_at is not None)


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
    return asking_state_view(team_state.asking_choice, refreshed=team_state.refreshed_at is not None)


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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
