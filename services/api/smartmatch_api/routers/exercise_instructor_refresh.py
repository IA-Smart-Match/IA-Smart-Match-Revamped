"""Design spec §14's "refresh all", as a router of its own.

One route, and a separate module for it rather than a ninth section of
``routers/exercise_instructor.py``: that file is already past this repository's
800-line ceiling, and adding the handler that *replaces its stub* to it would
have grown the file the review of PR #188 asked to stop growing. No count is
written down here (review round 1, F6) — a number in a docstring is a fact that
goes stale the next time somebody edits the other file, and the ceiling is the
thing that matters.

The split is along a seam the instructor page already has. Everything in
``exercise_instructor.py`` is about the **data file and the teams in it** —
upload, invite limit, unlock, list, open, reset, re-point. This is about the
**teams' own work**, and it is the one instructor route whose statements are the
results track's rather than the instructor track's. It reaches them through the
same repository the team's own refresh does, so "what a refresh changes" has one
answer (``exercise_results_refresh.refresh_one_team``).

The gate is the same gate
=========================
:data:`router` takes
:func:`~smartmatch_api.exercise_dependencies.require_instructor_session` as a
**router-level** dependency, exactly as ``exercise_instructor.router`` does, and
requires ``X-Exercise-Request`` on its one state-changing route. A gate written
as a handler parameter is a gate that comes off when somebody edits a signature,
and an open instructor route looks exactly like a working one.

The prefix is written out as a literal on the ``APIRouter(...)`` below rather
than imported from a constant, for ``exercise_instructor``'s reason: the route
ledger in ``tests/authz/test_policy_matrix.py`` reads prefixes out of the AST and
only sees ``prefix="…"``.

What this replaces
==================
``POST /v1/exercise/instructor/refresh-all`` shipped in PR #184 as a route that
**always refused**, because the share a refresh applies is decided by an asking
choice that no route stored yet. The choice is stored now
(``POST /v1/exercise/workspaces/current/asking-choice``), so the stub is deleted
rather than deprecated and this is the route at that path.

The report (Ann, 2026-10-02)
============================
*"…says, after running, which teams were refreshed and which were skipped and
why."* So the route visits **every** team that exists, not only the ones it can
refresh, and answers one line per team: refreshed, with the same counts that
team reads about itself; or skipped, with a reason code. The codes are the
three states a team can be in instead — it has not chosen, it has not run round
one, it was already refreshed. The instructor's screen writes the words.

A team that never entered a number has no workspace and is not listed: the
Teams panel treats it as absent too, and a line about a team nobody is on would
report something nobody was asked.

ADR-0025 D6 and D8
==================
Nothing here reads the withheld column. The refresh's card copy happens inside
``results_repository.apply_refresh``, behind
``dataset_repository.load_simulation_profiles``; this module passes profile
numbers and reports team numbers and counts. No score, no percentage, no
confidence appears on the response — the instructor's screen is on the same
projector as the teams'. The data file is named by its label, never its id.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from fastapi import APIRouter, Depends, status
from smartmatch_domain.exercise.asking import AskingChoice

from smartmatch_api.exercise_dependencies import (
    DatasetRepository,
    ExerciseEventRow,
    ExerciseResultsWriteRefused,
    ExerciseSession,
    ResultsRepository,
    TeamViewRepository,
    WorkspaceRefreshStatus,
    require_exercise_request_header,
    require_instructor_session,
)
from smartmatch_api.exercise_errors import ExerciseError
from smartmatch_api.routers.exercise_results_models import (
    FIRST_ROUND,
    RefreshAllTeamView,
    RefreshAllView,
    refresh_counts_view,
    row_is_round,
)
from smartmatch_api.routers.exercise_results_refresh import refresh_one_team, refresh_report
from smartmatch_api.utils import utc_now

#: Why a team was skipped, as the response names it. Codes, not sentences: the
#: instructor's screen owns the words, as a team's screen does for its own.
NO_ASKING_CHOICE = "no_asking_choice"
NO_ROUND_ONE_RUN = "no_round_one_run"
ALREADY_REFRESHED = "already_refreshed"

#: Every route here is gated by the instructor session, on the router. A bare
#: module-level assignment, for ``exercise_public.router``'s reason: the route
#: ledger reads ``name = APIRouter(...)`` out of the AST.
router = APIRouter(
    prefix="/v1/exercise/instructor",
    tags=["class-exercise"],
    dependencies=[Depends(require_instructor_session)],
)


@router.post(
    "/refresh-all",
    response_model=RefreshAllView,
    dependencies=[Depends(require_exercise_request_header)],
    summary="Refresh every team that has chosen how to ask",
)
def refresh_all_workspaces(
    session: ExerciseSession,
    datasets: DatasetRepository,
    team_view: TeamViewRepository,
    results: ResultsRepository,
) -> RefreshAllView:
    """Apply each team's own way of asking to that team's own view, once each.

    Design spec §14: *"refresh all"* runs design spec §13's refresh for every
    team that has chosen and not yet refreshed. Every other team is left exactly
    as it was and **named in the report with the reason**: it has not chosen
    (there is no share to apply), it has already had its one refresh, or it has
    chosen but has not run the first round's results — the refresh adds the
    first round's topics to the people who attended it, and there is nothing to
    add for a team that has not run it. None of these is an error, so the button
    does not fail for the teams that are ready.

    ``teams`` carries one entry per team, in the order the instructor's list
    shows them. ``skipped`` keeps the meaning it has always had — teams that had
    chosen and still could not be refreshed — and is not the length of the
    skipped entries.

    Each team is refreshed in its own right, from its own seed, so this produces
    exactly what six teams pressing their own button would have produced.

    **All or nothing.** Every team is refreshed inside one transaction, so a
    refusal for any one of them rolls back every team in the same request and
    nothing is left half applied. Pressing the button again after a refusal
    therefore starts from where it started, not from part way through.

    Raises:
        ExerciseError: 401 without a live instructor session, 403 without the
            ``X-Exercise-Request`` header, 409 when a write is refused.
    """
    now = utc_now()
    events_by_dataset: dict[uuid.UUID, tuple[ExerciseEventRow, ...]] = {}
    teams: list[RefreshAllTeamView] = []
    awaiting = 0
    for team in results.workspaces_refresh_status(session):
        if team.asking_choice is None:
            teams.append(_skipped(team, NO_ASKING_CHOICE))
            continue
        if team.refreshed_at is not None:
            teams.append(_skipped(team, ALREADY_REFRESHED, refreshed_at=team.refreshed_at))
            continue
        awaiting += 1
        events = events_by_dataset.setdefault(
            team.dataset_id,
            datasets.list_events(session, dataset_id=team.dataset_id),
        )
        choice = AskingChoice(team.asking_choice)
        teams.append(
            _refresh_team(session, results, team_view, team, events, choice=choice, now=now)
        )
    session.commit()
    refreshed = [team.team_number for team in teams if team.outcome == "refreshed"]
    return RefreshAllView(
        refreshed_team_numbers=refreshed,
        refreshed=len(refreshed),
        skipped=awaiting - len(refreshed),
        teams=teams,
    )


def _skipped(
    team: WorkspaceRefreshStatus, reason_code: str, *, refreshed_at: datetime | None = None
) -> RefreshAllTeamView:
    """One team's line when this request did not refresh it."""
    return RefreshAllTeamView.model_validate(
        {
            "team_number": team.team_number,
            "dataset_label": team.dataset_label,
            "outcome": "skipped",
            "reason_code": reason_code,
            "refreshed_at": refreshed_at,
        }
    )


def _refresh_team(
    session: ExerciseSession,
    results: ResultsRepository,
    team_view: TeamViewRepository,
    team: WorkspaceRefreshStatus,
    events: Sequence[ExerciseEventRow],
    *,
    choice: AskingChoice,
    now: datetime,
) -> RefreshAllTeamView:
    """Refresh one team that has chosen and not refreshed, and say what happened.

    The first round's run is what supplies both the attended set that gains
    topics and the invited set the card share is drawn from, so a team without
    one is skipped rather than refreshed with two empty sets — a refresh that
    changed nothing would still have consumed the team's one refresh.

    The round-one event is resolved from the stored run's own ``event_key``
    against this data file's events, so the topics added are the topics of the
    event that was actually run.

    The counts are read back from the team's view after the claim
    (``refresh_report``), which is what that team's own asking state will say:
    the instructor's line and the team's screen are one derivation.
    """
    first_round = results.get_run_for_round(
        session, workspace_id=team.workspace_id, round_number=FIRST_ROUND
    )
    if first_round is None:
        return _skipped(team, NO_ROUND_ONE_RUN)
    event = next(
        (row for row in events if row.event_key == first_round.event_key and row_is_round(row)),
        None,
    )
    if event is None:  # pragma: no cover - the run's foreign key names this event
        return _skipped(team, NO_ROUND_ONE_RUN)
    profiles = team_view.list_team_profiles(
        session, dataset_id=team.dataset_id, workspace_id=team.workspace_id
    )
    try:
        applied = refresh_one_team(
            session,
            results,
            dataset_id=team.dataset_id,
            workspace_id=team.workspace_id,
            seed=team.seed,
            choice=choice,
            profiles=profiles,
            invited_profile_nos=first_round.team.invited_profile_nos,
            attended_profile_nos=first_round.team.attended_profile_nos,
            added_topics=event.topic_tags,
            now=now,
        )
    except ExerciseResultsWriteRefused as error:
        raise ExerciseError(
            status_code=status.HTTP_409_CONFLICT,
            code="exercise_refresh_write_refused",
            message=str(error),
        ) from None
    if applied is None:
        return _claim_lost(session, results, team)
    report = refresh_report(
        team_view.list_team_profiles(
            session, dataset_id=team.dataset_id, workspace_id=team.workspace_id
        ),
        first_round.team.invited_profile_nos,
    )
    return RefreshAllTeamView(
        team_number=team.team_number,
        dataset_label=team.dataset_label,
        outcome="refreshed",
        refreshed_at=now,
        refresh_counts=refresh_counts_view(report),
        first_round_event_name=event.name,
    )


def _claim_lost(
    session: ExerciseSession, results: ResultsRepository, team: WorkspaceRefreshStatus
) -> RefreshAllTeamView:
    """Name a team whose row changed between the listing and the claim.

    The repository declines the claim when the team has refreshed itself in the
    same moment, or has been cleared and has no choice any more. Neither is "has
    not run round one", so the row is read again and named for what it says now.
    """
    current = results.team_state(session, workspace_id=team.workspace_id)
    if current is not None and current.refreshed_at is not None:
        return _skipped(team, ALREADY_REFRESHED, refreshed_at=current.refreshed_at)
    return _skipped(team, NO_ASKING_CHOICE)
