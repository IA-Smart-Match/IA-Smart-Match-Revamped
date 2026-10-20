"""Harbor's before-and-after rows, computed on read (Ann Wang, Oct 2026 feedback).

The team's chosen setting is run twice on the same event with the same seed:
once on profiles with this team's overlay cleared, once on the updated profiles
(that second row is the stored run itself). A "major first" row is added for
contrast. Nothing is stored and the team's one results run is not touched.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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
    profiles: Sequence[TeamProfileRow],
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
    """
    if run.round != COMPARED_ROUND or run.setting_weights is None:
        return None
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
            # Cut at the run's own length: the limit may have moved since, either way.
            invite_limit=len(run.team.invited_profile_nos),
        )
        return run_the_rule(
            session,
            datasets=datasets,
            profiles=rows,
            event=event,
            workspace=workspace,
            invited=[entry.profile_no for entry in invited],
            seed=seed,
            coefficients=coefficients,
        )

    # run_the_rule simulates with the workspace's limit; pin it to the stored run's size.
    workspace = replace(workspace, invite_limit=len(run.team.invited_profile_nos))
    name = run.setting_name or "your setting"
    before = simulate(cleared, run.setting_weights)
    major = simulate(profiles, _MAJOR_FIRST)
    return BeforeAfterView(
        rows=[
            _row(f"Your setting '{name}', before asking", *before),
            _row(f"Your setting '{name}', after asking", run.team, run.email_everyone),
            _row("Major first, after asking", *major),
        ]
    )
