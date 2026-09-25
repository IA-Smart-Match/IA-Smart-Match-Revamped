"""How one run of the results rule is built, and every gate in front of it.

Split out of ``exercise_results.py`` in review round 1 (F3): extracting the
gates from ``run_results`` — which was past the fifty-line limit for a function
— put that module past the 800-line ceiling for a file, so the seam it already
had is cut. ``exercise_results.py`` is **routes**; this is the work one of them
does: check the lock and the one-run rule, resolve the weighting, build the
invited list, run design spec §11's rule, store what it produced.

Same shape as the matching track, which is three modules for the same reason:
``exercise_matching.py`` is routes, ``exercise_matching_models.py`` is the
contract and the arithmetic, ``exercise_matching_weights.py`` is what a
weighting may be.

It **does** decide status codes, unlike ``exercise_results_models``: every
function here can refuse, and a refusal is one plain sentence with an
``exercise_``-prefixed code through
:class:`~smartmatch_api.exercise_errors.ExerciseError`. What it does not do is
declare a route.

ADR-0025 D6
===========
:func:`run_the_rule` is the one function in this track that calls
``load_simulation_profiles``, and it calls it to hand rows to design spec §11's
rule — the one thing the withheld column is for. What the rule returns is
profile numbers. Nothing here logs, nothing here puts a value in an exception
message, and no function here returns a value with a place to put an interest
term.

PLACEHOLDER (OQ-CE-03)
======================
:func:`coefficients_or_refusal` reads the domain's coefficient set — the team's
translation of Ann's words, still marked as a placeholder — and turns the
domain's refusal, should the set ever be ``None``, into one plain sentence
naming the open row. This module invents none.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from fastapi import status
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
    TeamViewRepository,
)
from smartmatch_api.exercise_errors import ExerciseError
from smartmatch_api.routers.exercise_matching_models import (
    event_evidence,
    event_or_refusal,
    rankable_set,
)
from smartmatch_api.routers.exercise_matching_weights import validated
from smartmatch_api.routers.exercise_results_models import (
    round_of,
    simulation_event,
    simulation_profiles,
)

__all__ = [
    "FINAL_SETTING_SENTENCE",
    "already_run",
    "coefficients_or_refusal",
    "final_setting_or_refusal",
    "invited_list",
    "round_or_refusal",
    "run_the_rule",
    "runnable_or_refusal",
    "store",
    "weights_or_refusal",
]


def round_or_refusal(events: Sequence[ExerciseEventRow], event_key: str) -> int:
    """Which round this event is, or one plain sentence.

    Read off the data file's own rows by ``round_of`` — the exercise events in
    sequence order — rather than matched against a name, because the two names
    are Ann's data and may change from one file to the next.

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


def coefficients_or_refusal() -> SimulationCoefficients:
    """The results rule's coefficients, or **OQ-CE-03's own sentence**.

    The register's answer is "Chau proposes; Ann confirms". The domain ships the
    team's proposal, and refuses only if it is ever removed. The sentence a team reads
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


#: The owner's rule in a team's words (Ann to Chau, Discord, 2026-09-24).
FINAL_SETTING_SENTENCE = (
    "Choose one of your saved settings as your final setting before running results."
)


def final_setting_or_refusal(setting_name: str | None) -> str:
    """The team's final setting, trimmed, or one plain sentence.

    Step three of the owner's flow (Ann to Chau, Discord, 2026-09-24): the team
    chooses **one final setting** and the run is built from it. There is no run
    on the course's starting values any more; a team that wants them saves them
    under a name like any other setting.

    422 with an ``exercise_``-prefixed code, the status the neighbouring body
    refusals use (``exercise_setting_name_unusable``,
    ``exercise_asking_choice_unknown``): the request is well-formed and the
    event may be runnable, but the body does not say what to run. Whether the
    name is one this team saved is :func:`weights_or_refusal`'s 404, unchanged.

    Called from the handler rather than from a pydantic validator so that it
    comes **after** the event's own refusals — see ``run_results`` for the order.
    """
    name = (setting_name or "").strip()
    if not name:
        raise ExerciseError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="exercise_final_setting_required",
            message=FINAL_SETTING_SENTENCE,
        )
    return name


def weights_or_refusal(
    session: ExerciseSession,
    settings: SettingsRepository,
    *,
    workspace: ExerciseWorkspace,
    event_key: str,
    setting_name: str,
) -> tuple[Mapping[str, float], str]:
    """The weighting a run's list is built from, and the name to store for it.

    ``setting_name`` is the team's final setting, already through
    :func:`final_setting_or_refusal`; it is trimmed again here so the lookup and
    the stored name cannot disagree if a caller skips that step.

    Re-validated on the way out rather than trusted because it was validated on
    the way in, for ``exercise_matching._saved_weights_or_refusal``'s reason: the
    rulebook is a value object and a later version could name different factors,
    at which point a stored weighting is input again.
    """
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
    weights: Mapping[str, float],
) -> tuple[int, ...]:
    """The ranked list's profile numbers, in order — the team's invited set.

    **Composed, never re-derived.** The order, the cut at the invite limit and
    the tie-break are ``exercise_ranked_list``'s, reached through the same
    ``rankable_set`` / ``event_evidence`` helpers the matching routes use, so the
    names a team invited are the names its screen showed it. Re-deriving them
    here would be a second ranker, and the failure mode of two rankers is a team
    told it invited somebody it did not.

    The year rank is ``rankable_set``'s — ``EXERCISE_CLASS_YEAR_RANK``, seniors
    first; this module does not touch it.
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


def run_the_rule(
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


def store(
    session: ExerciseSession,
    results: ResultsRepository,
    *,
    workspace: ExerciseWorkspace,
    event: ExerciseEventRow,
    round_number: int,
    setting_name: str,
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
        raise already_run() from None
    except ExerciseResultsWriteRefused as error:
        raise ExerciseError(
            status_code=status.HTTP_409_CONFLICT,
            code="exercise_results_write_refused",
            message=str(error),
        ) from None


def already_run() -> ExerciseError:
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


def runnable_or_refusal(
    session: ExerciseSession,
    results: ResultsRepository,
    *,
    datasets: DatasetRepository,
    workspace: ExerciseWorkspace,
    event_key: str,
) -> tuple[Sequence[ExerciseEventRow], ExerciseEventRow, int]:
    """The four gates a run must pass, in the order they cost least to fail.

    Extracted from ``exercise_results.run_results`` (review round 1, F3), which
    had grown past the repository's fifty-line limit for a function.
    Behaviour-preserving: the same four checks, in the same order, raising the
    same sentences.

    The order is load-bearing rather than tidy, for the matching router's
    reason. The events of one data file are a dozen rows and everything after
    this reads three hundred joined to an overlay, so the cheapest thing a
    client can send — an unknown event key — is refused before any of that
    happens. The unlock is one row; the already-run read is one row; the
    coefficients and the ranked list come after.

    The already-run read here is a **courtesy**, not the rule: it turns the
    ordinary second press of a button into a sentence instead of a constraint
    violation. The rule itself is
    ``uq_exercise_result_run_workspace_event``, taken inside
    ``ExerciseResultsRepository.record_run`` under that repository's advisory
    key, and it is what decides if this read is ever dropped or raced past.

    Returns the events beside the resolved event so the caller does not read
    them twice — the ranked list needs the same list for its past-event topic
    lookup.

    Raises:
        ExerciseError: 404 for an event that is not in this team's data file,
            409 when it is not one of the two rounds, is still locked, or has
            already been run.
    """
    events = datasets.list_events(session, dataset_id=workspace.dataset_id)
    event = event_or_refusal(events, event_key)
    round_number = round_or_refusal(events, event.event_key)
    if not results.results_unlocked(
        session, dataset_id=workspace.dataset_id, event_key=event.event_key
    ):
        raise ExerciseError(
            status_code=status.HTTP_409_CONFLICT,
            code="exercise_results_locked",
            message="The instructor has not opened results for this event yet.",
        )
    if results.get_run(session, workspace_id=workspace.id, event_key=event.event_key) is not None:
        raise already_run()
    return events, event, round_number


def invited_list(
    session: ExerciseSession,
    *,
    datasets: DatasetRepository,
    team_view: TeamViewRepository,
    settings: SettingsRepository,
    workspace: ExerciseWorkspace,
    events: Sequence[ExerciseEventRow],
    event: ExerciseEventRow,
    requested_setting: str,
) -> tuple[Sequence[TeamProfileRow], Sequence[int], str]:
    """Who this team invited, and the name of the weighting it was built from.

    The second half of ``run_results``'s preamble, extracted for the same reason
    as :func:`runnable_or_refusal` (review round 1, F3).

    The profiles are returned beside the invited numbers because the run needs
    both: the team's own view is what the rule's non-responding set is read
    from, and reading three hundred rows joined to an overlay twice is the one
    expensive thing on this path. The simulation's own load is a separate read,
    because it carries the withheld column and that read has one caller.
    """
    weights, setting_name = weights_or_refusal(
        session,
        settings,
        workspace=workspace,
        event_key=event.event_key,
        setting_name=requested_setting,
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
    return profiles, invited, setting_name
