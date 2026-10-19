"""Harbor's before-and-after rows, computed on read (Ann Wang, Oct 2026 feedback).

The team's chosen setting is run twice on the same event with the same seed:
once on profiles with this team's overlay cleared, once on the updated profiles
(that second row is the stored run itself). A "major first" row is added for
contrast. Nothing is stored and the team's one results run is not touched.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace

from smartmatch_domain.exercise.registry import EXERCISE_DEFAULT_WEIGHTS
from smartmatch_domain.exercise.simulation import SimulationCoefficients
from smartmatch_domain.student_factors import SAME_MAJOR_FACTOR_KEY

from smartmatch_api.exercise_dependencies import (
    DatasetRepository,
    ExerciseEventRow,
    ExerciseSession,
    ExerciseWorkspace,
    ResultPanel,
    StoredResultRun,
    TeamProfileRow,
)
from smartmatch_api.routers.exercise_results_models import BeforeAfterRowView, BeforeAfterView
from smartmatch_api.routers.exercise_results_run import _invited_entries, run_the_rule

#: Round two is the only round with an "asking" between rounds.
COMPARED_ROUND = 2
_MAJOR_FIRST: Mapping[str, float] = {
    key: (EXERCISE_DEFAULT_WEIGHTS[key] if key == SAME_MAJOR_FACTOR_KEY else 0.0)
    for key in EXERCISE_DEFAULT_WEIGHTS
}
#: Rows per stored run. A stored run never changes (one per team and event; a
#: reset deletes it and the next one has a new ``created_at``), so the two
#: simulations behind its rows are worked out once, not on every page read.
# ponytail: per-process dict wiped at 512 entries (a class is 6 teams x 1 round-two run);
# with uvicorn --workers each process keeps its own copy. Shared cache if that ever matters.
_MEMO: dict[tuple[object, ...], BeforeAfterView | None] = {}
_MEMO_CEILING = 512


def _row(label: str, team: ResultPanel, everyone: ResultPanel) -> BeforeAfterRowView:
    """Same arithmetic as the screen's lift line: sign-ups the mass email missed."""
    mass = set(everyone.signed_up_profile_nos)
    added = {n for n in team.signed_up_profile_nos if n not in mass}
    came = added & set(team.attended_profile_nos)
    return BeforeAfterRowView(
        label=label,
        mass_email_signups=len(mass),
        with_list_signups=len(mass) + len(added),
        list_added=len(added),
        list_added_came=len(came),
    )


def before_after_or_none(
    session: ExerciseSession,
    *,
    datasets: DatasetRepository,
    profiles: Callable[[], Sequence[TeamProfileRow]],
    events: Sequence[ExerciseEventRow],
    event: ExerciseEventRow,
    workspace: ExerciseWorkspace,
    run: StoredResultRun,
    seed: int,
    coefficients: SimulationCoefficients,
) -> BeforeAfterView | None:
    """The three rows for a stored round-two run; ``None`` otherwise.

    ``None`` also for a run stored before weights were kept (revision 0046):
    the setting cannot be rebuilt, so nothing is guessed.

    ``profiles`` is called only when the rows are not kept yet, so a reload
    of the results page does not read three hundred profiles for nothing.
    """
    if run.round != COMPARED_ROUND or run.setting_weights is None:
        return None
    key = (workspace.id, run.event_key, run.created_at, seed, coefficients)
    if key not in _MEMO:
        if len(_MEMO) >= _MEMO_CEILING:
            _MEMO.clear()
        _MEMO[key] = _before_after(
            session,
            datasets=datasets,
            profiles=profiles(),
            events=events,
            event=event,
            workspace=workspace,
            run=run,
            weights=run.setting_weights,
            seed=seed,
            coefficients=coefficients,
        )
    return _MEMO[key]


def _before_after(
    session: ExerciseSession,
    *,
    datasets: DatasetRepository,
    profiles: Sequence[TeamProfileRow],
    events: Sequence[ExerciseEventRow],
    event: ExerciseEventRow,
    workspace: ExerciseWorkspace,
    run: StoredResultRun,
    weights: Mapping[str, float],
    seed: int,
    coefficients: SimulationCoefficients,
) -> BeforeAfterView:
    """The three rows, simulated. Called once per stored run (``_MEMO``)."""
    cleared = tuple(
        replace(
            p,
            overlay_card_interests=None,
            overlay_card_career_goal=None,
            overlay_added_event_topics=(),
            non_responding=False,
        )
        for p in profiles
    )

    def simulate(
        rows: Sequence[TeamProfileRow], weights: Mapping[str, float]
    ) -> tuple[ResultPanel, ResultPanel]:
        invited = _invited_entries(
            session,
            datasets=datasets,
            profiles=rows,
            events=events,
            event=event,
            workspace=workspace,
            weights=weights,
        )
        return run_the_rule(
            session,
            datasets=datasets,
            profiles=rows,
            event=event,
            workspace=workspace,
            # Cut at the run's own length: the limit may have changed since (#419 moved 30 to 60).
            invited=[entry.profile_no for entry in invited][: len(run.team.invited_profile_nos)],
            seed=seed,
            coefficients=coefficients,
        )

    name = run.setting_name or "your setting"
    before = simulate(cleared, weights)
    major = simulate(profiles, _MAJOR_FIRST)
    return BeforeAfterView(
        rows=[
            _row(f"Your setting '{name}', before asking", *before),
            _row(f"Your setting '{name}', after asking", run.team, run.email_everyone),
            _row("Major first, after asking", *major),
        ]
    )
