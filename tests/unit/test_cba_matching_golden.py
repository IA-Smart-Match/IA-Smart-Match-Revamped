"""Golden-case runner for the **approved CBA four-factor set** (ADR-0016).

A separate module from ``tests/unit/test_matching_approved_golden.py``, which
runs the G1 two-factor cases against the superseded composition. The two sets
assert different rulebooks and must not be merged: a single runner would have to
branch on registry version in every assertion, and the first thing such a branch
loses is the fact that the two are not comparable.

``tests/golden/matching/cba/`` holds twelve fixtures, one per row of ADR-0016's
own "Golden cases implied by these proposals" table. Each names the proposals it
asserts, so a case can never be added for a behaviour nobody approved — the
failure mode §26 of the customer requirements calls out in terms: "Do not
silently invent permanent behavior for these items."

**Every expected number in the fixtures is a hand-computed literal**, not a
value recorded from a previous run. A golden set that records current behaviour
proves only that the code still does what it did; these fixtures state what the
owner approved, and the arithmetic connecting the two is the thing under test.

Two cases cannot be expressed as a single-mode fixture and have dedicated tests
below instead: **G-CBA-09** compares one pool scored in both modes, and
**G-CBA-12** is about *reading* a stored 1.x run rather than producing one.

The topic provider is the deterministic fixture throughout
(``ALLOW_LIVE_PROVIDERS=false``); no network is reachable from this suite and
none is attempted.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from smartmatch_domain.cba_role_categories import resolve_role_category
from smartmatch_domain.cba_topic_explanation import explain_cba_topic
from smartmatch_domain.explanation import (
    COMPOSITE_NEUTRAL_CAPTION,
    ScoreState,
    explain_candidate,
    explanation_from_payload,
    explanation_to_payload,
)
from smartmatch_domain.factor_registry import (
    REGISTRY_VERSION,
    SCORING_MODE_VERSION,
    SUPERSEDED_REGISTRY_VERSION,
    display_weights,
    factor_keys,
    resolve_scoring_model,
)
from smartmatch_domain.factors.cba_semantic_topic import (
    SpeakerTopicEvidence,
    score_cba_semantic_topic,
)
from smartmatch_domain.factors.industry_match import IndustryMatchInputs
from smartmatch_domain.factors.proximity import (
    CBA_PHYSICAL_SCORING_MODE,
    CBA_VIRTUAL_SCORING_MODE,
    ProximityInputs,
    SpeakerLocation,
    score_proximity,
)
from smartmatch_domain.factors.role_match import RoleMatchInputs
from smartmatch_domain.match_run import weights_fingerprint
from smartmatch_domain.naics_sectors import resolve_sector
from smartmatch_domain.scoring import (
    CBA_STAGE_B_FORMULA_VERSION,
    CbaCandidateEvidence,
    rank_cba_candidates,
    score_cba_candidate,
)
from smartmatch_providers.topic_semantics import FixtureSemanticTopicProvider

CBA_DIR = Path(__file__).resolve().parents[1] / "golden" / "matching" / "cba"
SCHEMA_PATH = CBA_DIR / "cba_case.schema.json"

#: Mirrors the schema's own ``id`` pattern — a hand-rolled check rather than a
#: jsonschema dependency, matching what the G1 runner does.
_CASE_ID_PATTERN = re.compile(r"^G-CBA-[0-9]{2}$")

#: Every case id ADR-0016's golden-case table requires a fixture for. Listed
#: here rather than derived from the directory, so *deleting* a fixture fails
#: this suite instead of quietly shrinking it.
REQUIRED_CASE_IDS = frozenset(f"G-CBA-{n:02d}" for n in range(1, 13))


def _case_paths() -> list[Path]:
    return sorted(CBA_DIR.glob("G-CBA-*.json"))


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _cases() -> list[dict[str, Any]]:
    return [_load(path) for path in _case_paths()]


def _scored_cases() -> list[dict[str, Any]]:
    """The cases the CBA composition can actually run (i.e. not the 1.x one)."""
    return [case for case in _cases() if case["scoring_mode"] is not None]


def _case(case_id: str) -> dict[str, Any]:
    return next(case for case in _cases() if case["id"] == case_id)


def _ids(cases: list[dict[str, Any]]) -> list[str]:
    return [case["id"] for case in cases]


# ---------------------------------------------------------------------------
# Building the run from a fixture
# ---------------------------------------------------------------------------


def _evidence(entry: dict[str, Any]) -> CbaCandidateEvidence:
    """Turn one fixture candidate into domain evidence, inventing nothing.

    Every ``None`` in a fixture stays a ``None``: a missing sector stays
    missing, a missing coordinate stays missing, and an absent profile stays
    absent. That is exactly the boundary a well-meaning default would cross, so
    this mapping has no defaults beyond the schema's own.
    """
    sector = entry.get("sector")
    role = entry.get("role")
    profile_present = entry.get("profile_present", False)

    topic_evidence = (
        SpeakerTopicEvidence.from_profile(
            topic_text=entry.get("topic_text"), prior_talk=entry.get("prior_talk")
        )
        if profile_present
        else SpeakerTopicEvidence.no_profile_record()
    )

    city = entry.get("city")
    postal_code = entry.get("postal_code")
    location = (
        None
        if city is None and postal_code is None
        else SpeakerLocation(city=city, postal_code=postal_code)
    )

    return CbaCandidateEvidence(
        subject_id=entry["subject_id"],
        industry=IndustryMatchInputs(
            speaker_sector=None if sector is None else resolve_sector(sector),
            requested_sectors=(),
        ),
        role=RoleMatchInputs(
            speaker_role=None if role is None else resolve_role_category(role),
            requested_roles=(),
        ),
        topic_evidence=topic_evidence,
        location=location,
        distance_miles=entry.get("distance_miles"),
    )


def _pool(case: dict[str, Any]) -> list[CbaCandidateEvidence]:
    """Build the pool, with the request's own targets on every candidate."""
    request = case["request"]
    requested_sectors = tuple(resolve_sector(code) for code in request.get("sectors", ()))
    requested_roles = tuple(resolve_role_category(code) for code in request.get("roles", ()))

    pool: list[CbaCandidateEvidence] = []
    for entry in case["candidates"]:
        base = _evidence(entry)
        pool.append(
            CbaCandidateEvidence(
                subject_id=base.subject_id,
                industry=IndustryMatchInputs(
                    speaker_sector=base.industry.speaker_sector,
                    requested_sectors=requested_sectors,
                ),
                role=RoleMatchInputs(
                    speaker_role=base.role.speaker_role, requested_roles=requested_roles
                ),
                topic_evidence=base.topic_evidence,
                location=base.location,
                distance_miles=base.distance_miles,
            )
        )
    return pool


def _provider(case: dict[str, Any]) -> FixtureSemanticTopicProvider:
    """Record exactly the comparisons the fixture declares, and nothing else.

    An unrecorded pair raises ``TopicComparisonUnavailable``, which the factor
    turns into an ``unknown``. That is deliberate, and it is what lets a case
    assert "the comparison could not be evaluated" without a mock: the fixture
    simply does not record it.
    """
    provider = FixtureSemanticTopicProvider()
    description = case["request"]["description"]
    for entry in case["candidates"]:
        score = entry.get("topic_score")
        if score is None:
            continue
        evidence = _evidence(entry).topic_evidence.usable_text
        if evidence is None:
            continue
        provider.record(
            description,
            evidence,
            score=score,
            rationale=entry.get("topic_rationale")
            or "Their recorded evidence was compared against the request.",
        )
    return provider


def _rank(case: dict[str, Any], *, scoring_mode: str | None = None):
    return rank_cba_candidates(
        _pool(case),
        request_description=case["request"]["description"],
        topic_provider=_provider(case),
        scoring_mode=scoring_mode or case["scoring_mode"],
    )


def _factor_ui_label(factor_key: str, case: dict[str, Any], subject: str) -> str:
    """The approved words for one factor, from whichever module owns them.

    The labels deliberately do not live in one table: the Topic wording belongs
    beside the factor that produces the neutral, and the band names beside the
    band table. This function is the test's own join, not a fourth copy.
    """
    entry = next(e for e in case["candidates"] if e["subject_id"] == subject)
    built = _evidence(entry)

    if factor_key == "cba_semantic_topic":
        score = score_cba_semantic_topic(
            case["request"]["description"], built.topic_evidence, _provider(case)
        )
        return explain_cba_topic(score).ui_label

    if factor_key == "proximity":
        return score_proximity(
            ProximityInputs(
                location=built.location,
                distance_miles=built.distance_miles,
                scoring_mode=case["scoring_mode"],
            )
        ).ui_label

    raise AssertionError(f"no ui_label rule for {factor_key}")


# ---------------------------------------------------------------------------
# The set itself
# ---------------------------------------------------------------------------


def test_every_adr_golden_case_has_a_fixture():
    """ADR-0016's table is the contract; a missing case is a missing assertion."""
    present = {case["id"] for case in _cases()}
    missing = REQUIRED_CASE_IDS - present
    assert not missing, f"ADR-0016 requires golden cases {sorted(missing)} and none exists"
    assert not present - REQUIRED_CASE_IDS, (
        "a CBA golden case exists that ADR-0016's table does not list; a case with no "
        "approved decision behind it freezes a behaviour nobody sanctioned"
    )


def test_the_schema_file_is_the_cba_contract_not_the_g1_one():
    """Separate schemas, because the two directories are separate contracts."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["$id"].endswith("cba-approved-golden-case-v1.json")
    assert schema["properties"]["id"]["pattern"] == "^G-CBA-[0-9]{2}$"
    # The third state, which no G1 schema has a word for.
    states = schema["properties"]["expected"]["properties"]["candidates"]["additionalProperties"][
        "properties"
    ]["composite_state"]["enum"]
    assert set(states) == {"measured", "policy_neutral", "unknown"}


@pytest.mark.parametrize("case", _cases(), ids=_ids(_cases()))
def test_every_case_declares_the_decision_it_asserts(case):
    """A golden case with no approved proposal behind it is not a golden case."""
    assert _CASE_ID_PATTERN.match(case["id"])
    assert case["title"].strip()
    assert case["asserts"].strip()
    assert case["adr_proposals"], f"{case['id']} names no ADR-0016 proposal"
    assert all(1 <= n <= 10 for n in case["adr_proposals"])


@pytest.mark.parametrize("case", _cases(), ids=_ids(_cases()))
def test_every_case_pins_the_registry_it_was_approved_under(case):
    """A case that did not say which rulebook it asserts could assert either."""
    if case["scoring_mode"] is None:
        assert case["registry_version"] == SUPERSEDED_REGISTRY_VERSION
    else:
        assert case["registry_version"] == REGISTRY_VERSION


@pytest.mark.parametrize("case", _scored_cases(), ids=_ids(_scored_cases()))
def test_the_case_scores_exactly_as_approved(case):
    """The whole golden set, run against the CBA composition.

    Asserts only what the fixture declares, so a case stays about the one thing
    it exists for — but everything it declares is checked, including the
    factor-level states and the approved UI wording.
    """
    expected = case["expected"]
    ranked = _rank(case)
    explanations = {score.subject_id: explain_candidate(score) for score in ranked}
    by_subject = {score.subject_id: score for score in ranked}

    if "ranking" in expected:
        assert [score.subject_id for score in ranked] == expected["ranking"]

    for score in ranked:
        # Pins first: a right number under the wrong rulebook is still wrong.
        assert score.registry_version == case["registry_version"]
        assert score.scoring_mode == case["scoring_mode"]
        assert score.scoring_mode_version == SCORING_MODE_VERSION
        assert score.formula_version == CBA_STAGE_B_FORMULA_VERSION

        if "applied_weights" in expected:
            rendered = {key: round(value, 6) for key, value in dict(score.applied_weights).items()}
            assert rendered == expected["applied_weights"]

        if "scored_factor_keys" in expected:
            keys = [factor.factor_key for factor in score.factor_scores]
            assert keys == expected["scored_factor_keys"]
            # In registry order, so a surface renders the same columns every time.
            assert keys == [key for key in factor_keys() if key in set(keys)]

    for subject, wanted in expected.get("candidates", {}).items():
        score = by_subject[subject]
        explanation = explanations[subject]

        if "composite_state" in wanted:
            assert explanation.state.value == wanted["composite_state"]
        if "heuristic_score" in wanted:
            assert score.value == wanted["heuristic_score"]
            assert explanation.heuristic_score == wanted["heuristic_score"]
        if "is_shortlistable" in wanted:
            assert explanation.is_shortlistable is wanted["is_shortlistable"]
        if "unknown_factor_keys" in wanted:
            assert list(score.unknown_factor_keys) == wanted["unknown_factor_keys"]
        if "policy_neutral_factor_keys" in wanted:
            assert list(score.policy_neutral_factor_keys) == wanted["policy_neutral_factor_keys"]
        if "ui_caption" in wanted:
            assert explanation.caption == wanted["ui_caption"]

        factors = {factor.factor_key: factor for factor in explanation.factors}
        for key, wanted_factor in wanted.get("factors", {}).items():
            factor = factors[key]
            if "state" in wanted_factor:
                assert factor.state.value == wanted_factor["state"]
            if "value" in wanted_factor:
                assert factor.value == wanted_factor["value"]
            if "zero_classification" in wanted_factor:
                assert factor.zero_classification == wanted_factor["zero_classification"]
            if "policy_id" in wanted_factor:
                assert factor.policy_id == wanted_factor["policy_id"]
            if "policy_version" in wanted_factor:
                assert factor.policy_version == wanted_factor["policy_version"]
            if "ui_label" in wanted_factor:
                assert _factor_ui_label(key, case, subject) == wanted_factor["ui_label"]


@pytest.mark.parametrize("case", _scored_cases(), ids=_ids(_scored_cases()))
def test_no_case_ever_renders_a_percentage_or_an_unknown_as_zero(case):
    """The two rules every case must obey, whatever else it asserts.

    ADR-0011's rule 1 and the §6 presentation rule are not case-specific, so
    they are checked on every case rather than only on the ones that happen to
    be about them. This is the guard that would catch an unknown becoming a
    zero in a case whose author was thinking about something else entirely.
    """
    for score in _rank(case):
        explanation = explain_candidate(score)
        assert explanation.score_label == "heuristic score"
        for factor in explanation.factors:
            if factor.state is ScoreState.UNKNOWN:
                assert factor.value is None, (
                    f"{case['id']}/{factor.factor_key}: an unknown carries a value"
                )
                assert factor.zero_classification == "unknown"
            else:
                assert factor.value is not None
                assert 0.0 <= factor.value <= 1.0
        if explanation.state is ScoreState.UNKNOWN:
            assert explanation.heuristic_score is None
        else:
            assert 0.0 <= (explanation.heuristic_score or 0.0) <= 1.0


# ---------------------------------------------------------------------------
# The cases a single-mode fixture cannot state
# ---------------------------------------------------------------------------


def test_g_cba_09_same_registry_different_hash_different_mode():
    """One pool, both modes: same rulebook, different model.

    The clearest statement of ADR-0016 Proposal 9. If ``registry_hash`` did not
    move between the modes, two runs that scored different factor sets would be
    indistinguishable in storage; if ``registry_version`` did move, the virtual
    mode would look like a different rulebook and every cross-mode comparison
    would be refused for the wrong reason.
    """
    case = _case("G-CBA-09")
    physical = _rank(case, scoring_mode=CBA_PHYSICAL_SCORING_MODE)[0]
    virtual = _rank(case, scoring_mode=CBA_VIRTUAL_SCORING_MODE)[0]

    assert physical.registry_version == virtual.registry_version == REGISTRY_VERSION
    assert physical.scoring_mode != virtual.scoring_mode
    assert physical.scoring_mode == CBA_PHYSICAL_SCORING_MODE
    assert virtual.scoring_mode == CBA_VIRTUAL_SCORING_MODE

    physical_hash = weights_fingerprint(physical.applied_weights)
    virtual_hash = weights_fingerprint(virtual.applied_weights)
    assert physical_hash != virtual_hash
    assert physical_hash.startswith("sha256:")

    # And the virtual run genuinely has no proximity factor — absent from the
    # model, not present-and-unknown.
    assert "proximity" in {f.factor_key for f in physical.factor_scores}
    assert "proximity" not in {f.factor_key for f in virtual.factor_scores}
    assert dict(display_weights(resolve_scoring_model(CBA_VIRTUAL_SCORING_MODE))) == {
        "industry_match": 0.428571,
        "role_match": 0.357143,
        "cba_semantic_topic": 0.214286,
    }


def test_g_cba_10_policy_provenance_survives_the_payload_round_trip():
    """A neutral that lost its policy on the way to storage is an unlabelled 0.5."""
    case = _case("G-CBA-10")
    explanation = explain_candidate(_rank(case)[0])

    payload = explanation_to_payload(explanation)
    assert payload["policy_neutral_factor_keys"] == ["cba_semantic_topic"]
    assert payload["scoring_mode"] == CBA_PHYSICAL_SCORING_MODE
    assert payload["scoring_mode_version"] == SCORING_MODE_VERSION

    restored = explanation_from_payload(payload)
    assert restored == explanation
    assert restored.state is ScoreState.POLICY_NEUTRAL
    assert restored.caption == COMPOSITE_NEUTRAL_CAPTION

    topic = next(f for f in restored.factors if f.factor_key == "cba_semantic_topic")
    assert topic.state is ScoreState.POLICY_NEUTRAL
    assert topic.value == 0.5
    assert topic.policy_id == "cba-neutral-topic"
    assert topic.policy_version == "1.0.0"


def test_g_cba_10_a_neutral_with_no_policy_is_refused_not_repaired():
    """The reader will not invent the provenance it cannot find."""
    case = _case("G-CBA-10")
    payload = explanation_to_payload(explain_candidate(_rank(case)[0]))
    for entry in payload["factors"]:
        if entry["state"] == "policy_neutral":
            entry["policy_id"] = None
            entry["policy_version"] = None

    with pytest.raises(ValueError, match="policy_neutral"):
        explanation_from_payload(payload)


def test_g_cba_12_a_stored_run_with_no_mode_reads_as_pre_adr_0016():
    """Not ``cba-physical-1``. A run that named no mode predates the vocabulary.

    Reading it as physical would claim a proximity factor was scored under a
    rulebook that had no modes at all — which is how an old record silently
    acquires a property nobody gave it.
    """
    case = _case("G-CBA-12")
    assert case["scoring_mode"] is None
    assert case["registry_version"] == SUPERSEDED_REGISTRY_VERSION

    # A payload as an older release would have written it: no mode keys and no
    # policy-neutral list, because neither existed.
    stored = explanation_to_payload(explain_candidate(_rank(_case("G-CBA-09"))[0]))
    stored["registry_version"] = SUPERSEDED_REGISTRY_VERSION
    del stored["scoring_mode"]
    del stored["scoring_mode_version"]
    del stored["policy_neutral_factor_keys"]

    restored = explanation_from_payload(stored)
    assert restored.scoring_mode is None
    assert restored.scoring_mode_version is None
    assert restored.policy_neutral_factor_keys == ()
    assert restored.registry_version == SUPERSEDED_REGISTRY_VERSION

    # And it is not comparable with a 2.x run: the pins differ, which is the
    # only thing standing between the two and a silent shared average.
    current = explain_candidate(_rank(_case("G-CBA-09"))[0])
    assert current.registry_version == REGISTRY_VERSION
    assert restored.registry_version != current.registry_version


def test_the_superseded_model_is_not_reachable_through_the_cba_scorer():
    """``score_cba_candidate`` cannot produce a 1.x run, by construction."""
    case = _case("G-CBA-09")
    score = score_cba_candidate(
        _pool(case)[0],
        request_description=case["request"]["description"],
        topic_provider=_provider(case),
        scoring_mode=CBA_PHYSICAL_SCORING_MODE,
    )
    assert score.registry_version == REGISTRY_VERSION
    assert score.registry_version != SUPERSEDED_REGISTRY_VERSION
