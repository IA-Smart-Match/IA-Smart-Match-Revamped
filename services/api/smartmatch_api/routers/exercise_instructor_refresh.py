"""Design spec §14's "refresh all", as a router of its own.

One route, and a separate module for it rather than a ninth section of
``routers/exercise_instructor.py``: that file is 898 lines, already past this
repository's 800-line ceiling, and adding the handler that *replaces its stub*
to it would have grown the file the review of PR #188 asked to stop growing.

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

ADR-0025 D6 and D8
==================
Nothing here reads the withheld column. The refresh's card copy happens inside
``results_repository.apply_refresh``, behind
``dataset_repository.load_simulation_profiles``; this module passes profile
numbers and reports team numbers and counts. No score, no percentage, no
confidence appears on the response — the instructor's screen is on the same
projector as the teams'.
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
    RefreshCandidate,
    ResultsRepository,
    TeamViewRepository,
    require_exercise_request_header,
    require_instructor_session,
)
from smartmatch_api.exercise_errors import ExerciseError
from smartmatch_api.routers.exercise_results_models import (
    FIRST_ROUND,
    RefreshAllView,
    row_is_round,
)
from smartmatch_api.routers.exercise_results_refresh import refresh_one_team
from smartmatch_api.utils import utc_now

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
    team that has chosen and not yet refreshed. Teams that have not chosen are
    not visited — there is no share to apply — and teams that have already
    refreshed have had their one refresh; neither is an error and neither is
    counted.

    A team that has chosen but has not run the first round's results is
    **skipped and counted**, not refused: the refresh adds the first round's
    topics to the people who attended it, and there is nothing to add for a team
    that has not run it. Reporting it as a number lets the instructor see that
    two teams are behind without the button failing for the four that are not.

    Each team is refreshed in its own right, from its own seed, so this produces
    exactly what six teams pressing their own button would have produced.

    Raises:
        ExerciseError: 401 without a live instructor session, 403 without the
            ``X-Exercise-Request`` header, 409 when a write is refused.
    """
    now = utc_now()
    events_by_dataset: dict[uuid.UUID, tuple[ExerciseEventRow, ...]] = {}
    refreshed: list[int] = []
    skipped = 0
    for candidate in results.workspaces_awaiting_refresh(session):
        events = events_by_dataset.setdefault(
            candidate.dataset_id,
            datasets.list_events(session, dataset_id=candidate.dataset_id),
        )
        if _refresh_candidate(session, results, team_view, candidate, events, now=now):
            refreshed.append(candidate.team_number)
        else:
            skipped += 1
    session.commit()
    return RefreshAllView(
        refreshed_team_numbers=refreshed,
        refreshed=len(refreshed),
        skipped=skipped,
    )


def _refresh_candidate(
    session: ExerciseSession,
    results: ResultsRepository,
    team_view: TeamViewRepository,
    candidate: RefreshCandidate,
    events: Sequence[ExerciseEventRow],
    *,
    now: datetime,
) -> bool:
    """Refresh one team. ``False`` when there is nothing to refresh from yet.

    The first round's run is what supplies both the attended set that gains
    topics and the invited set the card share is drawn from, so a team without
    one is skipped rather than refreshed with two empty sets — a refresh that
    changed nothing would still have consumed the team's one refresh.

    The round-one event is resolved from the stored run's own ``event_key``
    against this data file's events, so the topics added are the topics of the
    event that was actually run.
    """
    first_round = results.get_run_for_round(
        session, workspace_id=candidate.workspace_id, round_number=FIRST_ROUND
    )
    if first_round is None:
        return False
    event = next(
        (row for row in events if row.event_key == first_round.event_key and row_is_round(row)),
        None,
    )
    if event is None:  # pragma: no cover - the run's foreign key names this event
        return False
    profiles = team_view.list_team_profiles(
        session, dataset_id=candidate.dataset_id, workspace_id=candidate.workspace_id
    )
    try:
        applied = refresh_one_team(
            session,
            results,
            dataset_id=candidate.dataset_id,
            workspace_id=candidate.workspace_id,
            seed=candidate.seed,
            choice=AskingChoice(candidate.asking_choice),
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
    return applied is not None
