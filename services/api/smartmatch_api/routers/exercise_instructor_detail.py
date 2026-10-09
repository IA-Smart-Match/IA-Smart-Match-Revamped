"""Design spec §14's "open any team's work", as a router of its own.

One route — ``GET /v1/exercise/instructor/workspaces/{team_number}`` — and a
separate module for it, for ``exercise_instructor_refresh``'s reason:
``exercise_instructor.py`` sits near this repository's 800-line ceiling, and the
route grew. It used to list the *names* of a team's saved settings and the
*counts* of its runs. Ann's revisions of 2026-10-02 (area 2) ask for the whole
team, because the instructor leads the discussion from this page:

    "For each team, show: its saved settings with the four numbers, its list of
    names, its results for each event, the way of asking it chose, and whether
    it has refreshed."

So it now composes a ranked list per saved setting, which is the matching
track's work, and reads each run's stored snapshot, which is the results
track's. Neither belongs in the file that is about the data file and the teams
in it.

The gate is the same gate
=========================
:data:`router` takes
:func:`~smartmatch_api.exercise_dependencies.require_instructor_session` as a
**router-level** dependency, exactly as ``exercise_instructor.router`` does. The
route is read-only, so it carries no ``X-Exercise-Request`` requirement. The
prefix is a literal on the ``APIRouter(...)`` below, because the route ledger in
``tests/authz/test_policy_matrix.py`` reads prefixes out of the AST.

The team is addressed exactly as before: the data file the teams are on
(``exercise_instructor._teams_dataset``), then the team number. Those two
helpers are imported rather than copied, so "which file does an instructor
action apply to" keeps one answer.

Live for settings, stored for runs
==================================
A **saved setting** is current state, so its list of names is ranked now, from
the team's own view of the profiles — the view a refresh changes. It is
composed through ``rankable_set`` / ``event_evidence`` /
``exercise_ranked_list``, the same three the team's own list route uses, so the
instructor reads the list that team's screen shows. Nothing here ranks.

A **run** is history, so its names come from the snapshot the run stored of its
own list (migration ``0046``): what that team's screen showed at the moment it
ran, whatever has been edited, deleted or refreshed since.

ADR-0025 D6 and D8
==================
Nothing here reads a withheld column: the profiles come through
``TeamViewRepository``, whose read projects the public columns only. The
numbers on the response are the team's own four stated weights — the one number
D8 lets a screen show — a rank, which is a position on a list the team already
sees, and counts. No score, no percentage, no confidence: the instructor's
screen is on the same projector as the teams'.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from fastapi import APIRouter, Depends
from smartmatch_domain.exercise.matching import exercise_ranked_list
from smartmatch_domain.exercise.registry import EXERCISE_FACTOR_LABELS

from smartmatch_api.exercise_dependencies import (
    DatasetRepository,
    ExerciseEventRow,
    ExerciseSession,
    InstructorRepository,
    InstructorResultRun,
    InstructorSavedSetting,
    InvitedProfile,
    TeamViewRepository,
    TeamWorkspaceHandle,
    require_instructor_session,
)
from smartmatch_api.routers.exercise_instructor import (
    _DatasetChoice,
    _require_team,
    _teams_dataset,
)
from smartmatch_api.routers.exercise_instructor_models import (
    TeamDetailView,
    run_view,
    setting_view,
)
from smartmatch_api.routers.exercise_matching_models import event_evidence, rankable_set
from smartmatch_api.routers.exercise_matching_weights import stored_weights
from smartmatch_api.routers.exercise_results_models import round_of
from smartmatch_api.routers.exercise_results_run import invited_snapshot

#: Every route here is gated by the instructor session, on the router. A bare
#: module-level assignment, for ``exercise_public.router``'s reason: the route
#: ledger reads ``name = APIRouter(...)`` out of the AST.
router = APIRouter(
    prefix="/v1/exercise/instructor",
    tags=["class-exercise"],
    dependencies=[Depends(require_instructor_session)],
)


@router.get(
    "/workspaces/{team_number}",
    response_model=TeamDetailView,
    summary="One team's saved settings, lists of names, results and way of asking",
)
def read_team_workspace(
    team_number: int,
    session: ExerciseSession,
    instructor: InstructorRepository,
    datasets: DatasetRepository,
    team_view: TeamViewRepository,
    dataset_id: _DatasetChoice = None,
) -> TeamDetailView:
    """Everything one team has done, for the instructor to lead a discussion from.

    For each saved setting: its four weights as the team stated them, and the
    list of names it builds right now, in order. For each results run: the
    names that run invited, who signed up and who attended, the weights it was
    built with, and whether the setting it came from has been deleted since.
    Beside them, the way of asking the team chose and when it refreshed.

    Read-only. Addressed by *the data file the teams are on*, not by the newest
    upload, so it does not 404 on a team that is plainly still working the
    moment a new file is uploaded.

    A run's names are the ones stored with the run, so they do not change when
    the team edits or deletes the setting. A run stored before names were kept
    answers with its counts and whatever could be rebuilt.

    Raises:
        ExerciseError: 404 when that team has not entered its number, 422 for a
            team number outside 1-6, 409 when no data file can be resolved.
    """
    dataset = _teams_dataset(instructor, session, requested=dataset_id)
    workspace = _require_team(
        instructor, session, dataset_id=dataset.dataset_id, team_number=team_number
    )
    settings = instructor.list_saved_settings(session, workspace_id=workspace.id)
    runs = instructor.list_result_runs(session, workspace_id=workspace.id)
    # The dozen events before the three hundred profiles, for the matching
    # routes' reason: the cheap read first.
    events = datasets.list_events(session, dataset_id=dataset.dataset_id)
    names = {event.event_key: event.name for event in events}
    lists = _lists_by_setting(
        session,
        datasets=datasets,
        team_view=team_view,
        workspace=workspace,
        events=events,
        settings=settings,
    )
    still_saved = {(row.event_key, row.name) for row in settings}
    progress = next(
        (
            row
            for row in instructor.list_workspaces(session, dataset_id=dataset.dataset_id)
            if row.team_number == workspace.team_number
        ),
        None,
    )
    return TeamDetailView(
        team_number=workspace.team_number,
        asking_choice=progress.asking_choice if progress else None,
        refreshed_at=progress.refreshed_at if progress else None,
        factor_labels=dict(EXERCISE_FACTOR_LABELS),
        saved_settings=tuple(
            setting_view(
                row,
                event_name=names.get(row.event_key, row.event_key),
                round_number=round_of(events, row.event_key),
                weights=_stated_weights(row),
                invited=lists.get((row.event_key, row.name), ()),
            )
            for row in settings
        ),
        result_runs=tuple(
            run_view(
                row,
                event_name=names.get(row.event_key, row.event_key),
                setting_deleted=(
                    row.setting_name is not None
                    and (row.event_key, row.setting_name) not in still_saved
                ),
                setting_weights=_run_weights(row),
            )
            for row in runs
        ),
    )


def _stated_weights(row: InstructorSavedSetting) -> Mapping[str, float]:
    """A saved setting's four weights as the team's own screen reports them.

    ``effective_weights`` over the validated stored values: the team's numbers
    written over the 3/3/2/2 defaults, so four numbers are shown even for a
    setting saved with fewer — and never a normalized weight, which would be an
    output (ADR-0025 D8).
    """
    return dict(stored_weights(dict(row.weights)))


def _run_weights(row: InstructorResultRun) -> Mapping[str, float] | None:
    """A run's stored weights as four stated numbers, or ``None`` for none stored.

    A run made since revision 0046 stores all four. A run backfilled by that
    revision holds its saved setting's raw stored values, which may be fewer —
    so it goes through :func:`_stated_weights`' two steps and reads the same.
    """
    if row.setting_weights is None:
        return None
    return dict(stored_weights(dict(row.setting_weights)))


def _lists_by_setting(
    session: ExerciseSession,
    *,
    datasets: DatasetRepository,
    team_view: TeamViewRepository,
    workspace: TeamWorkspaceHandle,
    events: Sequence[ExerciseEventRow],
    settings: Sequence[InstructorSavedSetting],
) -> dict[tuple[str, str], tuple[InvitedProfile, ...]]:
    """The list of names each saved setting builds now, keyed by (event, name).

    **Composed, never re-derived**: ``rankable_set``, ``event_evidence`` and
    ``exercise_ranked_list`` are the team's own list route's three, called with
    the same invite limit, year rank and tie-break seed (the data file's
    checksum), so this is the list that team's screen shows for that setting.

    The profiles are read **once** for the team and ranked once per setting —
    at most three settings for each of two events. A team with nothing saved
    costs no profile read at all.
    """
    if not settings:
        return {}
    summary = datasets.get_dataset_summary(session, dataset_id=workspace.dataset_id)
    if summary is None:  # pragma: no cover - the team's workspace is on this file
        return {}
    profiles = team_view.list_team_profiles(
        session, dataset_id=workspace.dataset_id, workspace_id=workspace.id
    )
    rankable = rankable_set(profiles, events)
    by_key = {event.event_key: event for event in events}
    lists: dict[tuple[str, str], tuple[InvitedProfile, ...]] = {}
    for row in settings:
        event = by_key.get(row.event_key)
        if event is None:  # pragma: no cover - the setting's foreign key names it
            continue
        ranked = exercise_ranked_list(
            event_evidence(event),
            rankable.profiles,
            weights=stored_weights(dict(row.weights)),
            invite_limit=summary.invite_limit,
            year_rank=rankable.year_rank,
            dataset_checksum=summary.checksum,
        )
        lists[(row.event_key, row.name)] = invited_snapshot(ranked, rankable)
    return lists
