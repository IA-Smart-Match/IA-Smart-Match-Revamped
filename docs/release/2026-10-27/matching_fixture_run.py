"""Run the real exercise matching and simulation on the shipped 300-profile fixture.

Revision under test: 4fc80d0 (working tree). Every ranking, cut, tie-break and
chance draw below is the production domain code; this script only assembles
inputs the way the API routes do (see the notes in MATCHING_VERIFICATION.md).

Round two's asking step is modelled with the domain's own pieces:
``asking.select_share`` picks the card completers, and a completer's overlay card
is the hidden true interests plus ``copied_card_career_goal`` (the shipped
HIDDEN_GOAL reading). Round-one attendees gain the round-one event's topics, as
design spec section 13 describes. The refresh's DB write is not run; the overlay
is rebuilt in memory.

Usage (from the repository root, with the venv from ``make setup``):
    .venv/bin/python docs/release/2026-10-27/matching_fixture_run.py
Writes docs/release/2026-10-27/MATCHING_TEST_RESULTS.csv next to this file.
"""

from __future__ import annotations

import csv
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

from smartmatch_domain.exercise.asking import (
    CARD_COMPLETION_SHARE,
    AskingChoice,
    copied_card_career_goal,
    select_share,
)
from smartmatch_domain.exercise.determinism import exercise_permutation
from smartmatch_domain.exercise.ingest import parse_exercise_file
from smartmatch_domain.exercise.markers import derive_marker, information_rank
from smartmatch_domain.exercise.matching import (
    ExerciseProfile,
    exercise_ranked_list,
    rank_profiles_for_event,
)
from smartmatch_domain.exercise.registry import EXERCISE_DEFAULT_WEIGHTS
from smartmatch_domain.exercise.simulation import (
    EXERCISE_SIMULATION_COEFFICIENTS,
    SimulationEvent,
    SimulationProfile,
    run_email_everyone,
    simulate_results,
)
from smartmatch_domain.exercise.vocabulary import (
    EXERCISE_CLASS_YEAR_RANK,
    goal_topic_for_matching,
)
from smartmatch_domain.student_factors import (
    CAREER_GOAL_FIT_FACTOR_KEY,
    PAST_EVENT_TOPIC_OVERLAP_FACTOR_KEY,
    SAME_MAJOR_FACTOR_KEY,
    STATED_INTEREST_OVERLAP_FACTOR_KEY,
    EventEvidence,
    ProfileCard,
    ProfileEvidence,
)

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "exercise" / "SmartMatch_Student_Body_300_10022026.xlsx"
OUT_CSV = HERE / "MATCHING_TEST_RESULTS.csv"

#: The fixed team seed for every test row. Any fixed integer works; this one is
#: the date of the run, so the CSV can be matched to it by eye.
SEED = 20261027
#: The invite limit at 4fc80d0 (migration 0047 moves the default to 60; 0049 on
#: origin/main fixes it at 60). Seats stay at 60 in the simulation.
LIST_SIZE = 60
#: The refresh salt for card completers (services/api/.../exercise_results_refresh.py:76).
CARD_COMPLETION_SALT = "card_completion"
#: The team's major-first setting, as exercise_results_compare._MAJOR_FIRST builds it.
MAJOR_FIRST = {
    key: (EXERCISE_DEFAULT_WEIGHTS[key] if key == SAME_MAJOR_FACTOR_KEY else 0.0)
    for key in EXERCISE_DEFAULT_WEIGHTS
}
BALANCED = None  # None means the 3/3/2/2 defaults, as the domain defines them.
ASKING = AskingChoice.SMALL_REWARD


@dataclass(frozen=True, slots=True)
class Run:
    """One simulated round: what the team's list and the mass email produced."""

    listed: tuple[int, ...]
    signed_up: tuple[int, ...]
    attended: tuple[int, ...]
    mass_signed_up: tuple[int, ...]
    mass_attended: tuple[int, ...]


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _topics_by_key(events) -> dict[str, tuple[str, ...]]:
    return {event.event_key: tuple(event.topic_tags) for event in events}


def _event_evidence(event) -> EventEvidence:
    return EventEvidence(
        event_key=event.event_key,
        topic_tags=tuple(event.topic_tags),
        target_majors=tuple(event.target_majors),
    )


def _sim_event(event) -> SimulationEvent:
    return SimulationEvent(
        event_key=event.event_key,
        topic_tags=frozenset(event.topic_tags),
        target_majors=frozenset(event.target_majors),
    )


def _evidence(profile, topics, *, card, extra_topics=()) -> ProfileEvidence:
    attended = [topics.get(key, ()) for key in profile.past_event_keys]
    if extra_topics:
        attended.append(tuple(extra_topics))
    return ProfileEvidence(
        profile_id=str(profile.profile_no),
        major=profile.major,
        card=card,
        attended_event_topics=tuple(attended),
    )


def _base_card(profile) -> ProfileCard | None:
    if profile.stated_interests is None:
        return None
    return ProfileCard(
        stated_interests=tuple(profile.stated_interests),
        career_goal=goal_topic_for_matching(profile.career_goal),
    )


def _overlay_card(profile, *, completed: bool) -> ProfileCard | None:
    """The card after a completed refresh (design spec 13): the hidden truth is copied."""
    if not completed:
        return _base_card(profile)
    goal = copied_card_career_goal(
        profile.career_goal, hidden_true_career_goal=profile.hidden_true_career_goal
    )
    return ProfileCard(
        stated_interests=tuple(profile.hidden_true_interests),
        career_goal=goal_topic_for_matching(goal),
    )


def _exercise_profiles(parsed, *, cards, topic_gainers, topics):
    out = []
    for profile in parsed.profiles:
        out.append(
            ExerciseProfile(
                profile_no=profile.profile_no,
                class_year=profile.class_year,
                evidence=_evidence(
                    profile,
                    topics,
                    card=cards[profile.profile_no],
                    extra_topics=topic_gainers.get(profile.profile_no, ()),
                ),
                tiebreak_order=profile.tiebreak_order,
            )
        )
    return out


def _sim_profiles(parsed, *, silent):
    return tuple(
        SimulationProfile(
            profile_no=profile.profile_no,
            major=profile.major,
            true_interests=frozenset(profile.hidden_true_interests),
            career_goal=goal_topic_for_matching(profile.hidden_true_career_goal),
            past_event_count=len(profile.past_event_keys),
            non_responding=profile.profile_no in silent,
        )
        for profile in parsed.profiles
    )


def _run_round(parsed, event, *, weights, cards, topic_gainers, topics, silent):
    """Rank, cut at LIST_SIZE, then simulate the team's list and the mass email."""
    ranked_profiles = _exercise_profiles(
        parsed, cards=cards, topic_gainers=topic_gainers, topics=topics
    )
    checksum = parsed.checksum
    scored = rank_profiles_for_event(
        _event_evidence(event),
        ranked_profiles,
        weights=weights,
        invite_limit=LIST_SIZE,
        year_rank=EXERCISE_CLASS_YEAR_RANK,
        dataset_checksum=checksum,
    )
    listed = tuple(int(score.subject_id) for score in scored)
    ranked_list = exercise_ranked_list(
        _event_evidence(event),
        ranked_profiles,
        weights=weights,
        invite_limit=LIST_SIZE,
        year_rank=EXERCISE_CLASS_YEAR_RANK,
        dataset_checksum=checksum,
    )
    assert tuple(int(e.profile_id) for e in ranked_list.entries) == listed, (
        "rank_profiles_for_event and exercise_ranked_list disagree on order"
    )

    sim_profiles = _sim_profiles(parsed, silent=silent)
    by_no = {p.profile_no: p for p in sim_profiles}
    invited = tuple(by_no[n] for n in listed)
    sim_event = _sim_event(event)
    team = simulate_results(
        invited,
        sim_event,
        seed=SEED,
        coefficients=EXERCISE_SIMULATION_COEFFICIENTS,
        invite_limit=LIST_SIZE,
    )
    mass = run_email_everyone(
        sim_profiles, sim_event, seed=SEED, coefficients=EXERCISE_SIMULATION_COEFFICIENTS
    )
    run = Run(
        listed=listed,
        signed_up=team.signed_up,
        attended=team.attended,
        mass_signed_up=mass.signed_up,
        mass_attended=mass.attended,
    )
    return run, scored, ranked_profiles


def _checks(scored, ranked_profiles, weights, checksum) -> dict[str, bool]:
    """Order, weights, tie-break and uniqueness checks on one ranked list."""
    values = [score.value for score in scored]
    by_no = {p.profile_no: p for p in ranked_profiles}
    order_ok = all(values[i] >= values[i + 1] for i in range(len(values) - 1))

    # The value is the applied-weight dot product over known factors (matching.py).
    weights_ok = True
    for score in scored:
        recomputed = sum(
            score.applied_weights[f.factor_key] * f.value
            for f in score.factor_scores
            if f.value is not None
        )
        if abs(round(recomputed, 6) - score.value) > 1e-9:
            weights_ok = False

    # Ties on value must be broken by more information, then earlier year, then fixed order.
    # The last key is Ann's tiebreak_order when every profile carries one, else the
    # checksum-seeded permutation (matching._fixed_order). Mirror that choice here.
    if all(p.tiebreak_order is not None for p in ranked_profiles):
        perm = {p.profile_no: p.tiebreak_order for p in ranked_profiles}
    else:
        perm = exercise_permutation(checksum, [p.profile_no for p in ranked_profiles])
    tie_ok = True
    for a, b in zip(scored, scored[1:], strict=False):
        if a.value != b.value:
            continue
        pa, pb = by_no[int(a.subject_id)], by_no[int(b.subject_id)]
        ka = (
            -information_rank(derive_marker(pa.evidence)),
            -EXERCISE_CLASS_YEAR_RANK[pa.class_year],
            perm[pa.profile_no],
        )
        kb = (
            -information_rank(derive_marker(pb.evidence)),
            -EXERCISE_CLASS_YEAR_RANK[pb.class_year],
            perm[pb.profile_no],
        )
        if ka > kb:
            tie_ok = False
    ids = [s.subject_id for s in scored]
    return {
        "order_ok": order_ok,
        "weights_ok": weights_ok,
        "tie_ok": tie_ok,
        "unique_ok": len(set(ids)) == len(ids),
    }


def _row_for(test_id, round_no, event, setting, asking, run, checks, no_card, silent, rerun_equal):
    mass = set(run.mass_signed_up)
    added = [n for n in run.signed_up if n not in mass]
    list_size = len(run.listed)
    unique = len(set(run.listed))
    status_ok = (
        list_size == LIST_SIZE
        and unique == list_size
        and all(checks.values())
        and rerun_equal
    )
    return {
        "test_id": test_id,
        "round": round_no,
        "event": event,
        "setting": setting,
        "asking_choice": asking,
        "seed": SEED,
        "list_size": list_size,
        "unique_students": unique,
        "no_card_in_scope": no_card,
        "non_responding": len(silent),
        "list_signed_up": len(run.signed_up),
        "mass_email_alone_signed_up": len(mass),
        "list_added": len(added),
        "list_attended": len(run.attended),
        "order_ok": checks["order_ok"],
        "weights_ok": checks["weights_ok"],
        "tiebreak_ok": checks["tie_ok"],
        "unique_check_ok": checks["unique_ok"],
        "run1_equals_run2": rerun_equal,
        "status": "PASS" if status_ok else "FAIL",
    }


def _sig(run: Run) -> tuple:
    return (run.listed, run.signed_up, run.attended, run.mass_signed_up, run.mass_attended)


def main() -> int:
    raw = FIXTURE.read_bytes()
    parsed = parse_exercise_file(raw)
    if not hasattr(parsed, "profiles"):
        print(f"fixture refused: {parsed}", file=sys.stderr)
        return 2
    print(f"fixture: {FIXTURE.name} sha256={_sha256_file(FIXTURE)}")
    print(f"profiles={len(parsed.profiles)} events={len(parsed.events)} checksum={parsed.checksum}")

    events = list(parsed.events)
    rounds = sorted((e for e in events if e.is_exercise_event), key=lambda e: e.sequence)
    northline, harbor = rounds[0], rounds[1]
    topics = _topics_by_key(events)
    base_cards = {p.profile_no: _base_card(p) for p in parsed.profiles}
    no_card = [p.profile_no for p in parsed.profiles if p.stated_interests is None]
    no_card_set = set(no_card)
    print(f"round1={northline.name!r} round2={harbor.name!r} no_card={len(no_card)}")

    def round_one(weights):
        return _run_round(
            parsed,
            northline,
            weights=weights,
            cards=base_cards,
            topic_gainers={},
            topics=topics,
            silent=frozenset(),
        )

    def round_two(weights, *, asking: AskingChoice | None):
        if asking is None:
            cards, gainers = base_cards, {}
        else:
            completers = set(
                select_share(
                    no_card,
                    CARD_COMPLETION_SHARE[asking],
                    seed=SEED,
                    salt=CARD_COMPLETION_SALT,
                )
            )
            cards = {
                n: (_overlay_card(p, completed=True) if n in completers else base_cards[n])
                for n, p in ((p.profile_no, p) for p in parsed.profiles)
            }
            r1_run, _, _ = round_one(BALANCED)
            gainers = {n: tuple(northline.topic_tags) for n in r1_run.attended}
        return _run_round(
            parsed,
            harbor,
            weights=weights,
            cards=cards,
            topic_gainers=gainers,
            topics=topics,
            silent=frozenset(),
        )

    cases = [
        ("R1-NL-balanced", 1, northline, "balanced 3/3/2/2", None, BALANCED, None),
        ("R1-NL-major-first", 1, northline, "major first", None, MAJOR_FIRST, None),
        ("R2-HB-balanced-before", 2, harbor, "balanced 3/3/2/2", "none", BALANCED, None),
        ("R2-HB-balanced-after", 2, harbor, "balanced 3/3/2/2", ASKING.value, BALANCED, ASKING),
    ]

    rows = []
    for test_id, round_no, event, setting, asking_label, weights, asking in cases:
        if round_no == 1:
            make = lambda w=weights: round_one(w)  # noqa: E731
        else:
            make = lambda w=weights, a=asking: round_two(w, asking=a)  # noqa: E731
        run_a, scored, ranked_profiles = make()
        run_b, _, _ = make()
        rerun_equal = _sig(run_a) == _sig(run_b)
        checks = _checks(scored, ranked_profiles, weights, parsed.checksum)
        n_no_card = len(no_card_set & set(run_a.listed)) if round_no == 2 else len(no_card_set)
        rows.append(
            _row_for(
                test_id,
                round_no,
                event.name,
                setting,
                asking_label,
                run_a,
                checks,
                n_no_card,
                (),
                rerun_equal,
            )
        )

    fields = list(rows[0].keys())
    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(
            f"{row['test_id']}: list={row['list_size']} unique={row['unique_students']} "
            f"list_signed_up={row['list_signed_up']} mass_email_alone={row['mass_email_alone_signed_up']} "
            f"list_added={row['list_added']} attended={row['list_attended']} rerun_equal={row['run1_equals_run2']} "
            f"status={row['status']}"
        )
    print(f"wrote {OUT_CSV}")
    return 0 if all(r["status"] == "PASS" for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
