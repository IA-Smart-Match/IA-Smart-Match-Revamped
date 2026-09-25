"""Golden cases for the exercise's matching (ADR-0025 D3/D4/D5/D8).

Four claims that are cheap to hold and expensive to discover broken:

1. Every factor, known and unknown, composes to a pinned value.
2. Every tie-break branch puts a pinned name in a pinned place.
3. The fixed order is the *same* order in a fresh process under any
   ``PYTHONHASHSEED``. Design spec §11 writes a sibling draw as
   ``random.Random(seed ^ hash(event_key))``, and ``hash()`` of a string is
   salted per process; the subprocess case below is the test that catches the
   same mistake here.
4. Registering a second rulebook leaves the CBA registry's own numbers exactly
   where they were.

The class-year mapping is **test-only**, so these cases stay about the ranker;
production passes ``vocabulary.EXERCISE_CLASS_YEAR_RANK``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap

import pytest
from smartmatch_domain.exercise.determinism import exercise_permutation
from smartmatch_domain.exercise.matching import (
    ExerciseProfile,
    exercise_ranked_list,
    score_exercise_pair,
)
from smartmatch_domain.exercise.registry import EXERCISE_REGISTRY
from smartmatch_domain.factor_registry import (
    CBA_PHYSICAL_MODEL,
    CBA_REGISTRY,
    CBA_VIRTUAL_MODEL,
    REGISTRY_VERSION,
    display_weights,
    normalize_weights,
)
from smartmatch_domain.student_factors import ProfileCard, ProfileEvidence
from smartmatch_domain.student_factors.evidence import EventEvidence

GOLDEN_CHECKSUM = "sha256:0f1e2d3c4b5a69788796a5b4c3d2e1f0"

GOLDEN_EVENT = EventEvidence(
    event_key="northline",
    topic_tags=("analytics", "careers"),
    target_majors=("Marketing",),
)

# Test-only. NOT a proposal for OQ-CE-01.
GOLDEN_YEAR_RANK = {"Senior": 4, "Junior": 3, "Sophomore": 2, "First year": 1}


# ---------------------------------------------------------------------------
# G-CE-01 … G-CE-06: every factor, known and unknown
# ---------------------------------------------------------------------------

#: ``(case id, profile, composite, unknown keys)``. Every value is the exercise
#: default weighting — 0.25 each (OQ-CE-02, closed 2026-09-25) — so a change to the
#: defaults is visible here rather than silent.
FACTOR_CASES = [
    (
        "G-CE-01 major only",
        ProfileEvidence("p01", "Marketing"),
        0.25,
        ("stated_interest_overlap", "career_goal_fit", "past_event_topic_overlap"),
    ),
    (
        "G-CE-02 major misses, nothing else on file",
        ProfileEvidence("p02", "History"),
        0.0,
        ("stated_interest_overlap", "career_goal_fit", "past_event_topic_overlap"),
    ),
    (
        "G-CE-03 every factor known and perfect",
        ProfileEvidence(
            "p03",
            "Marketing",
            card=ProfileCard(("analytics", "careers"), career_goal="analytics"),
            attended_event_topics=(("analytics", "careers"),),
        ),
        1.0,
        (),
    ),
    (
        "G-CE-04 empty card is measured, past events unknown",
        ProfileEvidence("p04", "Marketing", card=ProfileCard()),
        0.25,
        ("past_event_topic_overlap",),
    ),
    (
        "G-CE-05 past events only",
        ProfileEvidence("p05", "Marketing", attended_event_topics=(("analytics", "careers"),)),
        0.5,
        ("stated_interest_overlap", "career_goal_fit"),
    ),
    (
        "G-CE-06 card with a partial interest overlap",
        # interests {analytics, sports} vs topics {analytics, careers}: 1/3.
        ProfileEvidence(
            "p06",
            "Marketing",
            card=ProfileCard(("analytics", "sports"), career_goal="law"),
        ),
        0.25 + 0.25 * 0.3333,
        ("past_event_topic_overlap",),
    ),
]


@pytest.mark.golden
@pytest.mark.parametrize(
    ("case_id", "profile", "expected", "unknown"),
    FACTOR_CASES,
    ids=[case[0] for case in FACTOR_CASES],
)
def test_factor_golden_case(
    case_id: str,
    profile: ProfileEvidence,
    expected: float,
    unknown: tuple[str, ...],
) -> None:
    score = score_exercise_pair(profile, GOLDEN_EVENT)
    assert score.value == pytest.approx(expected, abs=1e-6), case_id
    assert score.unknown_factor_keys == unknown, case_id
    assert score.registry_version == "exercise-0.1.0"


# ---------------------------------------------------------------------------
# G-CE-07 … G-CE-10: every tie-break branch
# ---------------------------------------------------------------------------


def _rank(profiles: list[ExerciseProfile], *, limit: int = 30) -> list[str]:
    listing = exercise_ranked_list(
        GOLDEN_EVENT,
        profiles,
        invite_limit=limit,
        year_rank=GOLDEN_YEAR_RANK,
        dataset_checksum=GOLDEN_CHECKSUM,
    )
    return [entry.profile_id for entry in listing.entries]


@pytest.mark.golden
def test_g_ce_07_value_orders_before_every_other_key() -> None:
    profiles = [
        ExerciseProfile(
            11,
            "First year",
            ProfileEvidence(
                "best",
                "Marketing",
                card=ProfileCard(("analytics", "careers"), career_goal="analytics"),
                attended_event_topics=(("analytics", "careers"),),
            ),
        ),
        ExerciseProfile(12, "Senior", ProfileEvidence("worse", "Marketing")),
    ]
    assert _rank(profiles) == ["best", "worse"]


@pytest.mark.golden
def test_g_ce_08_information_breaks_an_equal_value() -> None:
    profiles = [
        ExerciseProfile(21, "Senior", ProfileEvidence("thin", "Marketing")),
        ExerciseProfile(
            22,
            "Senior",
            ProfileEvidence("thick", "Marketing", attended_event_topics=(("sports",),)),
        ),
    ]
    assert _rank(profiles) == ["thick", "thin"]


@pytest.mark.golden
def test_g_ce_09_year_breaks_an_equal_value_and_information() -> None:
    profiles = [
        ExerciseProfile(31, "First year", ProfileEvidence("youngest", "Marketing")),
        ExerciseProfile(32, "Sophomore", ProfileEvidence("middle", "Marketing")),
        ExerciseProfile(33, "Senior", ProfileEvidence("senior", "Marketing")),
    ]
    assert _rank(profiles) == ["senior", "middle", "youngest"]


#: The fixed order for these five profile numbers under
#: :data:`GOLDEN_CHECKSUM`. Derived once from the digest and pinned; a change
#: to the derivation changes this list and is meant to.
GOLDEN_FIXED_ORDER_IDS = ["p42", "p43", "p45", "p41", "p44"]


@pytest.mark.golden
def test_g_ce_10_the_fixed_order_breaks_an_equal_everything() -> None:
    profiles = [
        ExerciseProfile(number, "Senior", ProfileEvidence(f"p{number}", "Marketing"))
        for number in range(41, 46)
    ]
    assert _rank(profiles) == GOLDEN_FIXED_ORDER_IDS
    assert _rank(list(reversed(profiles))) == GOLDEN_FIXED_ORDER_IDS


@pytest.mark.golden
def test_g_ce_11_the_cap_is_the_invite_limit() -> None:
    profiles = [
        ExerciseProfile(number, "Senior", ProfileEvidence(f"p{number}", "Marketing"))
        for number in range(41, 46)
    ]
    assert _rank(profiles, limit=2) == GOLDEN_FIXED_ORDER_IDS[:2]


@pytest.mark.golden
def test_g_ce_12_the_reason_lines_are_anns_words() -> None:
    profiles = [
        ExerciseProfile(51, "Senior", ProfileEvidence("senior", "Marketing")),
        ExerciseProfile(52, "Sophomore", ProfileEvidence("younger", "Marketing")),
        ExerciseProfile(
            53,
            "Senior",
            ProfileEvidence(
                "carded",
                "Marketing",
                card=ProfileCard(("analytics", "careers"), career_goal="analytics"),
                attended_event_topics=(("analytics", "careers"),),
            ),
        ),
    ]
    listing = exercise_ranked_list(
        GOLDEN_EVENT,
        profiles,
        invite_limit=30,
        year_rank=GOLDEN_YEAR_RANK,
        dataset_checksum=GOLDEN_CHECKSUM,
    )
    reasons = {entry.profile_id: entry.reason for entry in listing.entries}
    assert reasons["senior"] == "Tied on major; ordered by year."
    assert reasons["younger"] == "Tied on major; ordered by year."
    assert reasons["carded"] == (
        "What counted: same major, said they are interested in this topic, career "
        "goal fits this event, and went to similar events before."
    )


# ---------------------------------------------------------------------------
# G-CE-13: determinism across PYTHONHASHSEED, in a fresh process
# ---------------------------------------------------------------------------

_SUBPROCESS_SOURCE = textwrap.dedent(
    """
    import json
    import sys

    from smartmatch_domain.exercise.determinism import exercise_permutation

    checksum = sys.argv[1]
    numbers = json.loads(sys.argv[2])
    permutation = exercise_permutation(checksum, numbers)
    print(json.dumps({str(key): value for key, value in permutation.items()}))
    """
)


def _permutation_in_subprocess(hash_seed: str, numbers: list[int]) -> dict[str, int]:
    environment = {
        **os.environ,
        "PYTHONHASHSEED": hash_seed,
        "PYTHONPATH": os.pathsep.join(path for path in sys.path if path),
    }
    completed = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_SOURCE, GOLDEN_CHECKSUM, json.dumps(numbers)],
        capture_output=True,
        text=True,
        check=True,
        env=environment,
    )
    parsed: dict[str, int] = json.loads(completed.stdout)
    return parsed


@pytest.mark.golden
@pytest.mark.parametrize("hash_seed", ["0", "1", "12345", "random"])
def test_g_ce_13_the_fixed_order_survives_a_fresh_process(hash_seed: str) -> None:
    numbers = list(range(41, 46))
    expected = {
        str(key): value for key, value in exercise_permutation(GOLDEN_CHECKSUM, numbers).items()
    }
    assert _permutation_in_subprocess(hash_seed, numbers) == expected


@pytest.mark.golden
def test_g_ce_14_a_different_checksum_gives_a_different_order() -> None:
    numbers = list(range(41, 46))
    assert exercise_permutation(GOLDEN_CHECKSUM, numbers) != exercise_permutation(
        "sha256:ffffffffffffffffffffffffffffffff", numbers
    )


# ---------------------------------------------------------------------------
# G-CE-15: registry isolation — the CBA numbers do not move
# ---------------------------------------------------------------------------


@pytest.mark.golden
def test_g_ce_15_the_cba_registry_is_unchanged_with_a_second_registry_present() -> None:
    """ADR-0016's approved weights, asserted while ``exercise-0.1.0`` is bound."""
    assert EXERCISE_REGISTRY.version != CBA_REGISTRY.version
    physical = dict(normalize_weights(model=CBA_PHYSICAL_MODEL))
    assert physical == {
        "industry_match": pytest.approx(0.30),
        "role_match": pytest.approx(0.25),
        "cba_semantic_topic": pytest.approx(0.15),
        "proximity": pytest.approx(0.30),
    }
    assert dict(display_weights(CBA_VIRTUAL_MODEL)) == {
        "industry_match": 0.428571,
        "role_match": 0.357143,
        "cba_semantic_topic": 0.214286,
    }
    assert REGISTRY_VERSION == "2.0.0-approved-oq-cba-004"
