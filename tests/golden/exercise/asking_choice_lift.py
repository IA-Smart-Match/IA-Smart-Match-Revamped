"""Seeded driver: what each asking choice does to round-two attendance (#336).

Pure domain, no database. For every :class:`AskingChoice` and every seed it
walks one team through the class flow on Ann's 300 profiles, reusing the real
pieces and re-implementing none of them:

1. Northline (E11) list at the default weights -> ``simulate_results``;
2. the refresh plan (``refresh_plan``) applied to the team's rows the way
   ``apply_refresh`` writes the overlay;
3. Harbor (E12) list at the default weights on the refreshed rows ->
   ``simulate_results`` with the plan's non-responders flagged.

The list rule, weights and seed are the same for every choice, so the only
thing that differs between choices is the refresh. Round one is therefore
identical across choices (same list, same seed); the lift is round two minus
round one. Nothing here changes a coefficient.

Run ``python -m tests.golden.exercise.asking_choice_lift [N]`` from the repo root.
"""

from __future__ import annotations

import statistics
import sys
from dataclasses import dataclass, replace

from smartmatch_api.exercise_dependencies import ExerciseEventRow, TeamProfileRow
from smartmatch_api.routers.exercise_matching_models import event_evidence, rankable_set
from smartmatch_api.routers.exercise_results_models import simulation_event, simulation_profiles
from smartmatch_api.routers.exercise_results_refresh import invited_without_a_card, refresh_plan
from smartmatch_domain.exercise.asking import AskingChoice, copied_card_career_goal
from smartmatch_domain.exercise.matching import exercise_ranked_list
from smartmatch_domain.exercise.simulation import require_coefficients, simulate_results
from smartmatch_persistence.exercise.dataset_repository import SimulationProfileRow

from tests.unit.exercise_workbooks import ann_full_parsed

ROUND_ONE, ROUND_TWO = "E11", "E12"
INVITE_LIMIT = 30
BASE_SEED = 20261009


@dataclass(frozen=True, slots=True)
class Lift:
    """One choice over all seeds: attended counts per seed, round one and two."""

    choice: AskingChoice
    round_one: tuple[int, ...]
    round_two: tuple[int, ...]

    @property
    def lifts(self) -> tuple[int, ...]:
        return tuple(b - a for a, b in zip(self.round_one, self.round_two, strict=True))


def _events() -> tuple[ExerciseEventRow, ...]:
    return tuple(
        ExerciseEventRow(
            event_key=e.event_key,
            name=e.name,
            topic_tags=e.topic_tags,
            target_majors=e.target_majors,
            is_exercise_event=e.is_exercise_event,
            sequence=e.sequence,
        )
        for e in ann_full_parsed().events
    )


def _base_rows() -> tuple[TeamProfileRow, ...]:
    return tuple(
        TeamProfileRow(
            profile_no=p.profile_no,
            display_name=p.display_name,
            major=p.major,
            class_year=p.class_year,
            past_event_keys=p.past_event_keys,
            stated_interests=p.stated_interests,
            career_goal=p.career_goal,
            overlay_added_event_topics=(),
            overlay_card_interests=None,
            overlay_card_career_goal=None,
            non_responding=False,
            tiebreak_order=p.tiebreak_order,
        )
        for p in ann_full_parsed().profiles
    )


def _invited(
    rows: tuple[TeamProfileRow, ...], events: tuple[ExerciseEventRow, ...], event_key: str
) -> tuple[int, ...]:
    rankable = rankable_set(rows, events)
    event = next(e for e in events if e.event_key == event_key)
    listing = exercise_ranked_list(
        event_evidence(event),
        rankable.profiles,
        weights=None,  # the shipped defaults, 3/3/2/2
        invite_limit=INVITE_LIMIT,
        year_rank=rankable.year_rank,
        dataset_checksum=ann_full_parsed().checksum,
    )
    return tuple(int(entry.profile_id) for entry in listing.entries)


def _refreshed(
    rows: tuple[TeamProfileRow, ...],
    *,
    choice: AskingChoice,
    seed: int,
    invited: tuple[int, ...],
    attended: tuple[int, ...],
    northline_topics: tuple[str, ...],
) -> tuple[tuple[TeamProfileRow, ...], frozenset[int]]:
    """The team's rows after the refresh, as ``apply_refresh`` leaves the overlay."""
    plan = refresh_plan(
        choice=choice,
        seed=seed,
        attended_profile_nos=attended,
        no_card_profile_nos=invited_without_a_card(rows, invited),
    )
    hidden = {p.profile_no: p for p in ann_full_parsed().profiles}
    gainers, completers = set(plan.topic_gainers), set(plan.card_completers)
    silent = frozenset(plan.non_responding)
    out = []
    for row in rows:
        n = row.profile_no
        if n in completers:
            true = hidden[n]
            row = replace(
                row,
                overlay_card_interests=tuple(true.hidden_true_interests),
                overlay_card_career_goal=copied_card_career_goal(
                    row.career_goal, hidden_true_career_goal=true.hidden_true_career_goal
                ),
            )
        if n in gainers:
            row = replace(row, overlay_added_event_topics=northline_topics)
        out.append(replace(row, non_responding=n in silent))
    return tuple(out), silent


def _attended(invited: tuple[int, ...], event_key: str, seed: int, silent: frozenset[int]) -> int:
    parsed = ann_full_parsed()
    everyone = simulation_profiles(
        [
            SimulationProfileRow(
                profile_no=p.profile_no,
                display_name=p.display_name,
                major=p.major,
                class_year=p.class_year,
                past_event_keys=p.past_event_keys,
                stated_interests=p.stated_interests,
                career_goal=p.career_goal,
                hidden_true_interests=p.hidden_true_interests,
                hidden_true_career_goal=p.hidden_true_career_goal,
            )
            for p in parsed.profiles
        ],
        non_responding_profile_nos=silent,
    )
    wanted = set(invited)
    event = simulation_event(next(e for e in _events() if e.event_key == event_key))
    result = simulate_results(
        tuple(p for p in everyone if p.profile_no in wanted),
        event,
        seed=seed,
        coefficients=require_coefficients(),
        invite_limit=INVITE_LIMIT,
    )
    return len(result.attended)


def measure(seeds: int = 20) -> tuple[Lift, ...]:
    """Round-one and round-two attended per choice, over ``seeds`` team seeds."""
    events = _events()
    rows = _base_rows()
    northline = next(e for e in events if e.event_key == ROUND_ONE).topic_tags
    first = _invited(rows, events, ROUND_ONE)  # same list for every team and choice
    results = []
    for choice in AskingChoice:
        r1, r2 = [], []
        for seed in range(BASE_SEED, BASE_SEED + seeds):
            one = _attended(first, ROUND_ONE, seed, frozenset())
            # Attended profile numbers, to feed the refresh's topic gain.
            attended_nos = _attended_nos(first, seed)
            after, silent = _refreshed(
                rows,
                choice=choice,
                seed=seed,
                invited=first,
                attended=attended_nos,
                northline_topics=tuple(northline),
            )
            second_list = _invited(after, events, ROUND_TWO)
            r1.append(one)
            r2.append(_attended(second_list, ROUND_TWO, seed, silent))
        results.append(Lift(choice, tuple(r1), tuple(r2)))
    return tuple(results)


def _attended_nos(invited: tuple[int, ...], seed: int) -> tuple[int, ...]:
    # ponytail: re-runs the round-one rule once more to read the names; cheap at N~20.
    parsed = ann_full_parsed()
    wanted = set(invited)
    profiles = simulation_profiles(
        [
            SimulationProfileRow(
                profile_no=p.profile_no,
                display_name=p.display_name,
                major=p.major,
                class_year=p.class_year,
                past_event_keys=p.past_event_keys,
                stated_interests=p.stated_interests,
                career_goal=p.career_goal,
                hidden_true_interests=p.hidden_true_interests,
                hidden_true_career_goal=p.hidden_true_career_goal,
            )
            for p in parsed.profiles
            if p.profile_no in wanted
        ],
        non_responding_profile_nos=frozenset(),
    )
    event = simulation_event(next(e for e in _events() if e.event_key == ROUND_ONE))
    return simulate_results(
        profiles, event, seed=seed, coefficients=require_coefficients(), invite_limit=INVITE_LIMIT
    ).attended


def table(lifts: tuple[Lift, ...]) -> str:
    def ms(xs: tuple[int, ...]) -> str:
        return f"{statistics.fmean(xs):5.2f} / {statistics.stdev(xs):4.2f}"

    lines = [
        f"N = {len(lifts[0].round_one)} seeds; attended of 30 invited (mean / sd)",
        f"{'choice':<24}{'round one':>15}{'round two':>15}{'lift':>15}",
    ]
    lines += [
        f"{x.choice.value:<24}{ms(x.round_one):>15}{ms(x.round_two):>15}{ms(x.lifts):>15}"
        for x in lifts
    ]
    base = lifts[0]  # promise; choices are paired on the same seeds
    for x in lifts[1:]:
        d = tuple(a - b for a, b in zip(x.lifts, base.lifts, strict=True))
        se = statistics.stdev(d) / len(d) ** 0.5
        lines.append(
            f"{x.choice.value} minus promise, paired: {statistics.fmean(d):+.2f} (se {se:.2f})"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    print(table(measure(int(sys.argv[1]) if len(sys.argv) > 1 else 20)))
