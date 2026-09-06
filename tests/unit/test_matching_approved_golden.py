"""Golden-case runner for gate G1 **approved** cases — expected outputs included.

Unlike ``tests/unit/test_matching_golden_case_schema.py``, which runs against
the structure-only ``tests/golden/matching/symptoms/`` drafts where
``expected`` is forbidden, this module runs against
``tests/golden/matching/approved/``, whose schema *requires* ``expected`` and
whose seven fixtures carry the ratified 2026-09-03 ``zero_classification``
table (M6j). See ``docs/plans/workshops/g1-workshop-output-worksheet.md``
agenda item 3.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from smartmatch_domain.factor_registry import (
    REGISTRY_VERSION,
    SUPERSEDED_REGISTRY_VERSION,
    factor_keys,
)
from smartmatch_domain.factors.topic_relevance import TopicRelevanceInputs
from smartmatch_domain.factors.travel_burden import GeoPoint, TravelInputs
from smartmatch_domain.match_depth import EngagementHistoryEvidence, derive_match_depth
from smartmatch_domain.scoring import CandidateEvidence, rank_candidates, score_candidate

#: Mirrors approved_case.schema.json's own `id` pattern — a hand-rolled check
#: rather than a jsonschema dependency, matching test_matching_golden_case_schema.py.
_CASE_ID_PATTERN = re.compile(r"G1-GC-[0-9]{3}")

GOLDEN_DIR = Path(__file__).resolve().parents[1] / "golden" / "matching"
APPROVED_DIR = GOLDEN_DIR / "approved"
SYMPTOMS_DIR = GOLDEN_DIR / "symptoms"
SCHEMA_PATH = APPROVED_DIR / "approved_case.schema.json"
GOLDEN_CASE_SCHEMA_PATH = GOLDEN_DIR / "golden_case.schema.json"

#: Every ratified case id this approved directory must carry a fixture for.
RATIFIED_CASE_IDS = frozenset(
    {"G1-GC-002", "G1-GC-003", "G1-GC-004", "G1-GC-005", "G1-GC-006", "G1-GC-007", "G1-GC-008"}
)

#: The ratified ADR-0011 classification table (2026-09-03), copied verbatim
#: from the plan's global constraints — never re-derived.
RATIFIED_ZERO_CLASSIFICATIONS = {
    "G1-GC-002": "measured_zero",
    "G1-GC-003": "measured_zero",
    "G1-GC-005": "unknown",
    "G1-GC-006": "measured_zero",
    "G1-GC-007": "unknown",
    "G1-GC-008": "measured_zero",
}


def _case_paths() -> list[Path]:
    return sorted(APPROVED_DIR.glob("G1-GC-*.json"))


def _load_case(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _case_path(case_id: str) -> Path:
    return next(path for path in _case_paths() if path.stem.startswith(case_id))


def _candidate_from_inputs(
    subject_id: str, professional: dict[str, Any], event_need: dict[str, Any]
) -> CandidateEvidence:
    """Build a :class:`CandidateEvidence` from one fixture's professional/event_need."""
    expertise = professional.get("expertise_topics")
    origin = professional.get("coordinates")
    destination = event_need.get("coordinates")
    return CandidateEvidence(
        subject_id=subject_id,
        topic=TopicRelevanceInputs(
            expertise_topics=tuple(expertise) if expertise is not None else None,
            required_topics=tuple(event_need.get("required_topics", ())),
            preferred_topics=tuple(event_need.get("preferred_topics", ())),
        ),
        travel=TravelInputs(
            origin=(
                GeoPoint(origin["latitude"], origin["longitude"]) if origin is not None else None
            ),
            destination=(
                GeoPoint(destination["latitude"], destination["longitude"])
                if destination is not None
                else None
            ),
        ),
    )


@pytest.mark.golden
def test_approved_schema_file_exists():
    assert SCHEMA_PATH.is_file()


@pytest.mark.golden
def test_approved_schema_permits_expected_outputs():
    """The structural proof that the approved directory is a different contract."""
    schema = _load_case(SCHEMA_PATH)
    assert "expected" in schema["required"]
    assert "not" not in schema["properties"]["expected"]


@pytest.mark.golden
def test_every_ratified_case_id_has_a_fixture():
    ids = {_load_case(path)["id"] for path in _case_paths()}
    assert ids == RATIFIED_CASE_IDS


@pytest.mark.golden
@pytest.mark.parametrize("path", _case_paths(), ids=lambda p: p.stem)
def test_approved_cases_have_required_shape(path: Path):
    case = _load_case(path)
    assert _CASE_ID_PATTERN.fullmatch(case["id"])
    assert case["symptom_class"] in {"tie", "zero_or_unknown", "depth_zero"}
    assert case["description"]
    assert "inputs" in case
    assert "expected" in case
    if case["symptom_class"] in {"zero_or_unknown", "depth_zero"}:
        assert case["zero_classification"] in {"measured_zero", "unknown"}


@pytest.mark.golden
def test_zero_classifications_match_the_ratified_table():
    for case_id, classification in RATIFIED_ZERO_CLASSIFICATIONS.items():
        case = _load_case(_case_path(case_id))
        assert case["zero_classification"] == classification


@pytest.mark.golden
@pytest.mark.parametrize("case_id", ["G1-GC-002", "G1-GC-005", "G1-GC-006"])
def test_stage_b_cases_reproduce_expected_scores(case_id: str):
    case = _load_case(_case_path(case_id))
    inputs = case["inputs"]
    candidate = _candidate_from_inputs(
        inputs["candidate"]["subject_id"], inputs["professional"], inputs["event_need"]
    )
    result = score_candidate(candidate)
    expected = case["expected"]

    if expected["stage_b_score"] is None:
        assert result.value is None
    else:
        assert result.value == pytest.approx(expected["stage_b_score"], abs=1e-6)

    assert result.unknown_factor_keys == tuple(expected["unknown_factor_keys"])

    scores_by_key = {factor_score.factor_key: factor_score for factor_score in result.factor_scores}
    for key, expected_factor in expected["factor_scores"].items():
        actual = scores_by_key[key]
        if expected_factor["value"] is None:
            assert actual.value is None
        else:
            assert actual.value == pytest.approx(expected_factor["value"], abs=1e-6)
        assert actual.zero_classification == expected_factor["zero_classification"]


@pytest.mark.golden
def test_tie_case_reproduces_the_ratified_tie_break():
    case = _load_case(_case_path("G1-GC-004"))
    inputs = case["inputs"]
    event_need = inputs["event_need"]
    candidates = [
        _candidate_from_inputs(entry["subject_id"], entry, event_need)
        for entry in inputs["candidates"]
    ]
    ranked = rank_candidates(candidates)

    assert len(ranked) == 2
    assert ranked[0].value == pytest.approx(ranked[1].value)
    assert ranked[0].value == pytest.approx(case["expected"]["stage_b_score"])
    assert [result.subject_id for result in ranked] == case["expected"]["ranking"]

    expected_factor_scores = case["expected"]["factor_scores"]
    scores_by_key = {
        factor_score.factor_key: factor_score for factor_score in ranked[0].factor_scores
    }
    for key, expected_factor in expected_factor_scores.items():
        actual = scores_by_key[key]
        assert actual.value == pytest.approx(expected_factor["value"])
        assert actual.zero_classification == expected_factor["zero_classification"]


@pytest.mark.golden
@pytest.mark.parametrize("case_id", ["G1-GC-003", "G1-GC-007", "G1-GC-008"])
def test_match_depth_cases_reproduce_expected_depth(case_id: str):
    case = _load_case(_case_path(case_id))
    inputs = case["inputs"]
    engagement_ids = inputs["engagement_ids"]
    evidence = EngagementHistoryEvidence(
        subject_id=inputs["subject_id"],
        unit_id=inputs["unit_id"],
        engagement_ids=tuple(engagement_ids) if engagement_ids is not None else None,
    )
    depth = derive_match_depth(evidence)
    expected = case["expected"]["match_depth"]

    assert depth.count == expected["count"]
    assert depth.zero_classification == expected["zero_classification"]

    # match_depth is a derived display quantity, never a registry factor —
    # assert both the fixture's own ratified expectation and the registry
    # fact it records, so neither can silently go unread.
    assert case["expected"]["match_depth_is_a_registry_factor"] is False
    assert "match_depth" not in factor_keys()


@pytest.mark.golden
@pytest.mark.parametrize("path", _case_paths(), ids=lambda p: p.stem)
def test_no_approved_fixture_asserts_a_legacy_score(path: Path):
    """MM-002: no fixture may characterize the legacy engine, anywhere in it.

    Scans the whole case — not just ``expected`` — so a description, a
    stakeholder reference, or any future field is covered too. A prior
    version of this guard scanned only ``json.dumps(case["expected"])``,
    which let a description carrying "43%" and "legacy" pass silently.

    The forbidden legacy tie value is checked as "43%" / "43 percent" /
    "0.43", its natural textual representations, rather than the bare digit
    pair "43": every approved fixture's synthetic coordinates include Los
    Angeles' longitude (``-118.2437``), which contains "43" as a harmless
    numeric coincidence once the scan covers ``inputs`` too. A
    bare-substring check would flag that coordinate on every fixture without
    ever catching a real legacy-value reference more precisely than these
    checks already do.

    "legacy" itself stays checked too, even though every current fixture
    says "predecessor" instead — the point is to catch the *value*
    (43%/0.43), whatever word introduces it, so a future description reading
    "the predecessor engine's 43 percent tie value" cannot slip past this
    guard the way it would if only "legacy" were checked.
    """
    case = _load_case(path)
    case_text = json.dumps(case).lower()
    assert "legacy" not in case_text
    assert "43%" not in case_text
    assert "43 percent" not in case_text
    assert "43-percent" not in case_text
    assert "0.43" not in case_text


@pytest.mark.golden
def test_symptom_fixtures_are_untouched():
    """Executable proof that this card left the draft symptoms directory alone."""
    symptom_paths = sorted(SYMPTOMS_DIR.glob("G1-GC-*.json"))
    assert symptom_paths, "expected symptom fixtures to still exist"
    for path in symptom_paths:
        payload = _load_case(path)
        assert "expected" not in payload, f"{path.name} unexpectedly carries expected outputs"

    golden_case_schema = _load_case(GOLDEN_CASE_SCHEMA_PATH)
    assert "not" in golden_case_schema["properties"]["expected"]


# ---------------------------------------------------------------------------
# Supersession (ADR-0016 Proposal 9, OQ-CBA-025)
#
# The registry moved to 2.0.0-approved-oq-cba-004 and these seven cases did not
# move with it. That is the point of a major bump: the G1 cases assert the G1
# rulebook, they must keep reproducing under it, and they must never be read as
# though they asserted the CBA one.
# ---------------------------------------------------------------------------


@pytest.mark.golden
@pytest.mark.parametrize("case_id", ["G1-GC-002", "G1-GC-005", "G1-GC-006"])
def test_a_g1_case_still_reproduces_at_its_own_pin_after_the_2x_bump(case_id: str):
    """The reproducibility half of OQ-CBA-025's *coexist* decision.

    ``topic_relevance`` and ``travel_burden`` are retired — they carry no active
    weight in the current model — but they are still declared and still
    implemented, precisely so this keeps working. If retirement had meant
    deletion, every run a coordinator has already seen would have become
    unreproducible on the day the CBA factors landed.
    """
    case = _load_case(_case_path(case_id))
    inputs = case["inputs"]
    result = score_candidate(
        _candidate_from_inputs(
            inputs["candidate"]["subject_id"], inputs["professional"], inputs["event_need"]
        )
    )

    assert result.registry_version == SUPERSEDED_REGISTRY_VERSION
    assert result.registry_version != REGISTRY_VERSION
    # The G1 factor set, unchanged and undiluted by the four CBA factors.
    assert {score.factor_key for score in result.factor_scores} == {
        "topic_relevance",
        "travel_burden",
    }
    assert set(result.applied_weights) == {"topic_relevance", "travel_burden"}
    assert sum(result.applied_weights.values()) == pytest.approx(1.0)
    # No mode, because the vocabulary postdates this rulebook entirely.
    assert result.scoring_mode is None
    assert result.scoring_mode_version is None


@pytest.mark.golden
def test_the_g1_cases_never_claim_the_cba_registry():
    """A 1.x case that drifted onto the 2.x pin would be silently comparable.

    Two scores under two rulebooks must never be averaged, ranked, or charted
    together, and the version string is the only thing keeping them apart. This
    asserts the separation from the fixture side as well as the code side.
    """
    for path in _case_paths():
        case_text = json.dumps(_load_case(path))
        assert REGISTRY_VERSION not in case_text, (
            f"{path.name} names the CBA registry version; the G1 approved set asserts "
            "the superseded rulebook and must not borrow the 2.x pin"
        )


@pytest.mark.golden
def test_the_cba_golden_set_is_a_separate_directory():
    """The two sets are separate contracts and stay in separate directories.

    Not a filesystem nicety: a CBA case dropped into ``approved/`` would be run
    by *this* module's parametrization against the superseded composition, which
    would either error confusingly or — worse — pass while asserting the wrong
    rulebook.
    """
    cba_dir = GOLDEN_DIR / "cba"
    assert cba_dir.is_dir(), "the CBA golden set must live in its own directory"
    assert not list(APPROVED_DIR.glob("G-CBA-*.json"))
    assert not list(cba_dir.glob("G1-GC-*.json"))
