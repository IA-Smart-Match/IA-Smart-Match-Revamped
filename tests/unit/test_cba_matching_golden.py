"""Golden-case runner for the **approved CBA four-factor set** (ADR-0016).

A separate module from ``tests/unit/test_matching_approved_golden.py``, which
runs the G1 two-factor cases against the superseded composition. The two sets
assert different rulebooks and must not be merged: a single runner would have to
branch on registry version in every assertion, and the first thing such a branch
loses is the fact that the two are not comparable.

``tests/golden/matching/cba/`` holds twelve fixtures, one per row of ADR-0016's
own "Golden cases implied by these proposals" table, plus B26's: G-CBA-14…19
assert registry 3.0.0 (proposed, never current) under named owner decisions
(Q1/D2, Q7 = A, unknown load) and run with its approval gate evaluated by
``tests/unit/registry_evaluation.py``. Each names the proposals it
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

import copy
import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from smartmatch_domain.availability_verdict import verdicts_for_pool
from smartmatch_domain.cba_role_categories import resolve_role_category
from smartmatch_domain.cba_topic_explanation import explain_cba_topic
from smartmatch_domain.eli import Engagement, LoadBand
from smartmatch_domain.eligibility import apply_availability_filter
from smartmatch_domain.explanation import (
    COMPOSITE_NEUTRAL_CAPTION,
    ScoreState,
    explain_candidate,
    explanation_from_payload,
    explanation_to_payload,
)
from smartmatch_domain.factor_registry import (
    CBA_3_PHYSICAL_MODEL,
    CBA_3_VIRTUAL_MODEL,
    CBA_PHYSICAL_MODEL,
    CBA_REGISTRY,
    CBA_REGISTRY_3,
    CBA_VIRTUAL_MODEL,
    REGISTRY_3_VERSION,
    REGISTRY_VERSION,
    SCORING_MODE_VERSION,
    SUPERSEDED_G1_MODEL,
    SUPERSEDED_REGISTRY_VERSION,
    display_weights,
    factor_keys,
    normalize_weights,
    registry_for_version,
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
from smartmatch_domain.load_bands import (
    AssessedLoad,
    LoadReviewStatus,
    assess_pool_loads,
    stage_a_load_excluded,
)
from smartmatch_domain.match_run import (
    inputs_fingerprint,
    registry_fingerprint,
    weights_fingerprint,
)
from smartmatch_domain.naics_sectors import resolve_sector
from smartmatch_domain.scoring import (
    CBA_LOAD_STAGE_B_FORMULA_VERSION,
    CBA_STAGE_B_FORMULA_VERSION,
    CbaCandidateEvidence,
    rank_cba_candidates,
    score_cba_candidate,
)
from smartmatch_domain.speaker_availability import (
    AvailabilityStatement,
    UnavailableWindow,
    availability_state_for_event,
)
from smartmatch_providers.topic_semantics import FixtureSemanticTopicProvider

from tests.unit.registry_evaluation import evaluate_registry_3

CBA_DIR = Path(__file__).resolve().parents[1] / "golden" / "matching" / "cba"
SCHEMA_PATH = CBA_DIR / "cba_case.schema.json"

#: Mirrors the schema's own ``id`` pattern — a hand-rolled check rather than a
#: jsonschema dependency, matching what the G1 runner does.
_CASE_ID_PATTERN = re.compile(r"^G-CBA-[0-9]{2}$")

#: Every case id ADR-0016's golden-case table requires a fixture for, plus the
#: owner-ruled cases after it (G-CBA-13, B26 T4; G-CBA-14…19, B26 T8c: registry
#: 3.0.0 under owner decisions Q1/D2, Q7 = A and unknown load). Listed here
#: rather than derived from the directory, so *deleting* a fixture fails this
#: suite instead of quietly shrinking it.
REQUIRED_CASE_IDS = frozenset(f"G-CBA-{n:02d}" for n in range(1, 20))


def _case_paths() -> list[Path]:
    return sorted(CBA_DIR.glob("G-CBA-*.json"))


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _cases() -> list[dict[str, Any]]:
    return [_load(path) for path in _case_paths()]


def _scored_cases() -> list[dict[str, Any]]:
    """The 2.x cases the CBA composition can actually run (not the 1.x one, not 3.x)."""
    return [
        case
        for case in _cases()
        if case["scoring_mode"] is not None and case["registry_version"] != REGISTRY_3_VERSION
    ]


def _load_cases() -> list[dict[str, Any]]:
    """The registry 3.0.0 cases (B26 T8c), run with the load band table."""
    return [case for case in _cases() if case["registry_version"] == REGISTRY_3_VERSION]


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
    proposals = case.get("adr_proposals")
    decisions = case.get("owner_decisions")
    assert proposals or decisions, f"{case['id']} names no ADR-0016 proposal or owner ruling"
    if proposals:
        assert all(1 <= n <= 10 for n in proposals)
    if decisions:
        assert all(isinstance(d, str) and d.strip() for d in decisions)


@pytest.mark.parametrize("case", _cases(), ids=_ids(_cases()))
def test_every_case_pins_the_registry_it_was_approved_under(case):
    """A case that did not say which rulebook it asserts could assert either."""
    if case["scoring_mode"] is None:
        assert case["registry_version"] == SUPERSEDED_REGISTRY_VERSION
    else:
        assert case["registry_version"] in {REGISTRY_VERSION, REGISTRY_3_VERSION}
    if case["registry_version"] == REGISTRY_3_VERSION:
        # 3.0.0 is proposed: a case may assert it only under a named owner decision.
        assert case.get("owner_decisions"), f"{case['id']} pins 3.0.0 with no owner decision"


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


# ---------------------------------------------------------------------------
# G-CBA-13 (B26 T4): Stage A availability moves neither hash nor order
# ---------------------------------------------------------------------------


def _statement(entry: dict[str, Any]) -> AvailabilityStatement | None:
    stated = entry["availability"]
    if stated is None:
        return None
    paused = stated["invitations_paused_until"]
    return AvailabilityStatement(
        invitations_paused_until=None if paused is None else date.fromisoformat(paused),
        declared_capacity_hours_per_90_days=None,
        unavailable=tuple(
            UnavailableWindow(date.fromisoformat(w["starts_on"]), date.fromisoformat(w["ends_on"]))
            for w in stated["unavailable"]
        ),
    )


def _fingerprints(ranked) -> tuple[str, str]:
    weights = ranked[0].applied_weights
    return (
        weights_fingerprint(weights),
        inputs_fingerprint(
            event_need_id="G-CBA-13",
            candidate_subject_ids=[score.subject_id for score in ranked],
            candidate_utilities=[score.value for score in ranked],
            portfolio_size=2,
            random_seed=0,
            weights=weights,
        ),
    )


def test_g_cba_13_availability_leaves_hash_and_pool_alone():
    """Four Speakers, one per verdict: the verdicts annotate and change nothing else.

    The unavailable Speaker scores highest, so a verdict that reordered, dropped
    or re-weighted anybody would move the ranking or one of the two digests.
    """
    case = _case("G-CBA-13")
    assert case["registry_version"] == REGISTRY_VERSION
    span = (
        date.fromisoformat(case["event_span"]["first"]),
        date.fromisoformat(case["event_span"]["last"]),
    )
    as_of = date.fromisoformat(case["as_of"])

    before = _rank(case)
    ranking = [score.subject_id for score in before]
    utilities = [score.value for score in before]
    digests = _fingerprints(before)

    statements = {
        entry["subject_id"]: statement
        for entry in case["candidates"]
        if (statement := _statement(entry)) is not None
    }
    verdicts = verdicts_for_pool(tuple(ranking), statements, span, as_of)

    after = _rank(case)
    assert [score.subject_id for score in after] == ranking == case["expected"]["ranking"]
    assert [score.value for score in after] == utilities
    assert _fingerprints(after) == digests
    assert weights_fingerprint(after[0].applied_weights) == digests[0]

    # One decision per subject, in ranked order: the gate never reorders.
    evidence = {
        subject: availability_state_for_event(statements.get(subject), span, as_of).to_evidence(
            subject
        )
        for subject in ranking
    }
    decisions = apply_availability_filter(tuple(ranking), evidence)
    assert [d.subject_id for d in decisions] == ranking
    assert [v.subject_id for v in verdicts] == ranking
    assert [v.verdict for v in verdicts] == [d.outcome for d in decisions]

    # Each subject's verdict is the hand-written one.
    for verdict in verdicts:
        wanted = case["expected"]["candidates"][verdict.subject_id]["availability"]
        assert verdict.verdict.value == wanted["verdict"]
        assert verdict.state.value == wanted["state"]
        assert verdict.reason.value == wanted["reason"]
        paused = verdict.paused_until
        assert (None if paused is None else paused.isoformat()) == wanted["paused_until"]
        assert verdict.as_of == as_of


# ---------------------------------------------------------------------------
# B26 T8c: registry 3.0.0 (proposed) — the load cases G-CBA-14…19
# ---------------------------------------------------------------------------
#
# 3.0.0 is never current. Each case below names it explicitly and evaluates its
# approval gate through tests/unit/registry_evaluation.py, which lets exactly
# CBA_REGISTRY_3 through the scoring and explanation gates for one test.

_US_PER_HOUR = 3_600_000_000


def _exact_hours(hours: str | None) -> timedelta | None:
    """Decimal hours to an exact timedelta; a fixture that would round fails."""
    if hours is None:
        return None
    us = Decimal(hours) * _US_PER_HOUR
    assert us == us.to_integral_value(), f"fixture hours {hours} are not whole microseconds"
    return timedelta(microseconds=int(us))


def _case_loads(case: dict[str, Any]) -> Mapping[str, AssessedLoad]:
    as_of = date.fromisoformat(case["as_of"])
    capacities: dict[str, Decimal | None] = {}
    engagements: dict[str, tuple[Engagement, ...]] = {}
    for entry in case["candidates"]:
        load = entry["load"]
        subject = entry["subject_id"]
        capacity = load["capacity_hours"]
        capacities[subject] = None if capacity is None else Decimal(capacity)
        engagements[subject] = tuple(
            Engagement(
                ref=e["ref"],
                event_date=None
                if e["offset_days"] is None
                else as_of + timedelta(days=e["offset_days"]),
                duration=_exact_hours(e["hours"]),
                confirmed=e["confirmed"],
                attended=e["attended"],
                cancelled=e["cancelled"],
            )
            for e in load["engagements"]
        )
    return assess_pool_loads(
        [entry["subject_id"] for entry in case["candidates"]],  # type: ignore[misc]
        capacities=capacities,  # type: ignore[arg-type]
        engagements=engagements,  # type: ignore[arg-type]
        as_of=as_of,
        bands=CBA_REGISTRY_3.load_bands,  # type: ignore[arg-type]
    )


def _stage_a(case: dict[str, Any]):
    """Split the pool at Stage A: Full is removed as load_full, before any scoring."""
    loads = _case_loads(case)
    kept: list[CbaCandidateEvidence] = []
    excluded: list[dict[str, str]] = []
    for evidence in _pool(case):
        load = loads[evidence.subject_id]
        if stage_a_load_excluded(load):
            excluded.append({"subject_id": evidence.subject_id, "reason": "load_full"})
        else:
            kept.append(dataclasses.replace(evidence, load=load))
    return loads, kept, excluded


def _rank_3(case: dict[str, Any], kept, *, scoring_mode: str | None = None):
    return rank_cba_candidates(
        kept,
        request_description=case["request"]["description"],
        topic_provider=_provider(case),
        scoring_mode=scoring_mode or case["scoring_mode"],
        registry=registry_for_version(case["registry_version"]),
    )


@pytest.fixture
def registry_3(monkeypatch):
    evaluate_registry_3(monkeypatch)


def _assert_load(case_id: str, subject: str, load: AssessedLoad, wanted: dict[str, Any]) -> None:
    assessment = load.assessment
    if "load_band" in wanted:
        assert assessment.band.value == wanted["load_band"], (case_id, subject)
    if "load_reason" in wanted:
        assert assessment.reason.value == wanted["load_reason"], (case_id, subject)
    if "load_measurable" in wanted:
        assert assessment.measurable is wanted["load_measurable"], (case_id, subject)
    if "utilization" in wanted:
        expected = wanted["utilization"]
        if expected is None:
            assert assessment.utilization is None, (case_id, subject)
        else:
            assert assessment.utilization == Decimal(expected), (case_id, subject)
    if "unknown_hours_refs" in wanted:
        assert list(assessment.unknown_hours_refs) == wanted["unknown_hours_refs"]


@pytest.mark.parametrize("case", _load_cases(), ids=_ids(_load_cases()))
def test_the_load_case_scores_exactly_as_approved(case, registry_3):
    """Every 3.0.0 case: Stage A removal, bands, multipliers, scores, round trip."""
    expected = case["expected"]
    loads, kept, excluded = _stage_a(case)
    ranked = _rank_3(case, kept)
    by_subject = {score.subject_id: score for score in ranked}

    assert excluded == expected.get("excluded", [])
    if "ranking" in expected:
        assert [score.subject_id for score in ranked] == expected["ranking"]

    for score in ranked:
        assert score.registry_version == REGISTRY_3_VERSION
        assert score.scoring_mode == case["scoring_mode"]
        assert score.formula_version == CBA_LOAD_STAGE_B_FORMULA_VERSION
        assert score.load is loads[score.subject_id]
        explanation = explain_candidate(score)
        payload = explanation_to_payload(explanation)
        assert "load" in payload
        assert explanation_from_payload(payload) == explanation

    excluded_ids = {entry["subject_id"] for entry in excluded}
    for subject, wanted in expected.get("candidates", {}).items():
        _assert_load(case["id"], subject, loads[subject], wanted)
        if subject in excluded_ids:
            assert "heuristic_score" not in wanted, "an excluded subject is never scored"
            assert subject not in by_subject
            continue
        score = by_subject[subject]
        explanation = explain_candidate(score)
        if "heuristic_score" in wanted:
            assert score.value == wanted["heuristic_score"]
            assert explanation.heuristic_score == wanted["heuristic_score"]
        if "composite_state" in wanted:
            assert explanation.state.value == wanted["composite_state"]
        if "load_multiplier" in wanted:
            assert explanation.load is not None
            assert explanation.load.multiplier == Decimal(wanted["load_multiplier"])
            payload_load = explanation_to_payload(explanation)["load"]
            assert payload_load["multiplier"] == wanted["load_multiplier"]


@pytest.mark.parametrize("case", _load_cases(), ids=_ids(_load_cases()))
def test_no_load_case_renders_a_percentage_or_an_unknown_as_zero(case, registry_3):
    _, kept, _ = _stage_a(case)
    for score in _rank_3(case, kept):
        explanation = explain_candidate(score)
        assert explanation.score_label == "heuristic score"
        assert explanation.load is not None
        assert explanation.load.band is not LoadBand.FULL
        if explanation.load.band is LoadBand.UNKNOWN:
            # Unknown is neutral (multiplier 1), never a zero load.
            assert explanation.load.multiplier == 1
        if explanation.heuristic_score is not None:
            assert 0.0 <= explanation.heuristic_score <= 1.0


def test_g_cba_14_band_boundaries(registry_3):
    case = _case("G-CBA-14")
    loads, kept, excluded = _stage_a(case)
    bands = {subject: load.assessment.band.value for subject, load in loads.items()}
    assert bands == {
        "SYNTH-CBA-14-A-U4999": "light",
        "SYNTH-CBA-14-B-U5000": "moderate",
        "SYNTH-CBA-14-C-U7999": "moderate",
        "SYNTH-CBA-14-D-U8000": "heavy",
        "SYNTH-CBA-14-E-U10000": "heavy",
        "SYNTH-CBA-14-F-U10001": "full",
    }
    assert excluded == [{"subject_id": "SYNTH-CBA-14-F-U10001", "reason": "load_full"}]
    values = {score.subject_id: score.value for score in _rank_3(case, kept)}
    assert values == {
        "SYNTH-CBA-14-A-U4999": 0.97,
        "SYNTH-CBA-14-B-U5000": 0.873,
        "SYNTH-CBA-14-C-U7999": 0.873,
        "SYNTH-CBA-14-D-U8000": 0.679,
        "SYNTH-CBA-14-E-U10000": 0.679,
    }


def test_g_cba_15_full_is_removed_before_the_solve(registry_3):
    case = _case("G-CBA-15")
    loads, kept, excluded = _stage_a(case)
    assert [entry["subject_id"] for entry in excluded] == [
        "SYNTH-CBA-15-FULL",
        "SYNTH-CBA-15-FULL-LOWER-BOUND",
    ]
    # Full can never reach Stage B, even if a caller forgets Stage A.
    full = next(e for e in _pool(case) if e.subject_id == "SYNTH-CBA-15-FULL")
    with pytest.raises(ValueError, match="Stage A"):
        _rank_3(case, [dataclasses.replace(full, load=loads[full.subject_id])])

    # The kept pool fingerprints exactly like a pool that never named the Full two.
    ranked = _rank_3(case, kept)
    never_named = dict(
        case, candidates=[c for c in case["candidates"] if "LIGHT" in c["subject_id"]]
    )
    _, kept_alone, excluded_alone = _stage_a(never_named)
    assert excluded_alone == []
    ranked_alone = _rank_3(never_named, kept_alone)

    def fingerprint(scores):
        return inputs_fingerprint(
            event_need_id="G-CBA-15",
            candidate_subject_ids=[s.subject_id for s in scores],
            candidate_utilities=[s.value for s in scores],
            portfolio_size=2,
            random_seed=0,
            weights=scores[0].applied_weights,
        )

    assert fingerprint(ranked) == fingerprint(ranked_alone)


def test_g_cba_16_a_cancelled_booking_drops_out(registry_3):
    case = _case("G-CBA-16")
    loads, kept, _ = _stage_a(case)
    assert loads["SYNTH-CBA-16-CANCELLED"].assessment.confirmed_hours == Decimal(4)
    assert loads["SYNTH-CBA-16-KEPT"].assessment.confirmed_hours == Decimal(10)
    ranked = _rank_3(case, kept)
    assert [(s.subject_id, s.value) for s in ranked] == [
        ("SYNTH-CBA-16-CANCELLED", 0.97),
        ("SYNTH-CBA-16-KEPT", 0.679),
    ]


def test_g_cba_17_unknown_load_scores_neutral_and_is_labelled(registry_3):
    case = _case("G-CBA-17")
    _, kept, _ = _stage_a(case)
    two_point_oh = {
        score.subject_id: score.value
        for score in rank_cba_candidates(
            _pool(case),
            request_description=case["request"]["description"],
            topic_provider=_provider(case),
            scoring_mode=case["scoring_mode"],
        )
    }
    for score in _rank_3(case, kept):
        # Float equality, not approx: multiplier 1.0 leaves the 2.0.0 number alone.
        assert score.value == two_point_oh[score.subject_id]
        payload = explanation_to_payload(explain_candidate(score))
        assert payload["load"]["band"] == "unknown"
        assert payload["load"]["multiplier"] == "1"
        assert payload["load"]["measurable"] is False


_PRE_T8C_PAYLOAD_KEYS = frozenset(
    {
        "subject_id",
        "heuristic_score",
        "state",
        "score_label",
        "registry_version",
        "formula_version",
        "scoring_mode",
        "scoring_mode_version",
        "unknown_factor_keys",
        "policy_neutral_factor_keys",
        "factors",
    }
)


def test_g_cba_18_a_two_point_oh_run_stays_readable_and_keeps_its_hash(registry_3):
    case = _case("G-CBA-18")
    assert case["registry_version"] == REGISTRY_VERSION
    pinned = case["expected"]["registry_hash"]

    # 1. The hash function for 1.1.1 and 2.0.0 is unchanged, byte for byte.
    for key, model in (
        ("cba-physical-1", CBA_PHYSICAL_MODEL),
        ("cba-virtual-1", CBA_VIRTUAL_MODEL),
        ("g1", SUPERSEDED_G1_MODEL),
    ):
        weights = normalize_weights(model=model)
        assert registry_fingerprint(weights, load_bands=None) == pinned[key]
        assert weights_fingerprint(weights) == pinned[key]

    # 2. A 2.0.0 payload carries no load key and reads back with none.
    explanation = explain_candidate(_rank(case)[0])
    payload = explanation_to_payload(explanation)
    assert "load" not in payload
    assert set(payload) == _PRE_T8C_PAYLOAD_KEYS
    restored = explanation_from_payload(payload)
    assert restored.load is None
    assert restored == explanation

    # 3. A load key on it, even null, is refused rather than ignored.
    with pytest.raises(ValueError, match="load"):
        explanation_from_payload({**payload, "load": None})

    # 4. A 3.0.0 payload with its load deleted is refused rather than defaulted.
    three = _case("G-CBA-14")
    _, kept, _ = _stage_a(three)
    stored = explanation_to_payload(explain_candidate(_rank_3(three, kept)[0]))
    del stored["load"]
    with pytest.raises(ValueError, match="load"):
        explanation_from_payload(stored)

    # 5. Every pin resolves to the rulebook that produced it.
    assert registry_for_version(SUPERSEDED_REGISTRY_VERSION) is CBA_REGISTRY
    assert registry_for_version(REGISTRY_VERSION) is CBA_REGISTRY
    assert registry_for_version(REGISTRY_3_VERSION) is CBA_REGISTRY_3


#: Hand-written, not rendered by the code under test (T8c plan §10, G-CBA-19).
_G_CBA_19_LITERAL = (
    b'{"load_bands":{"eli_formula_version":"2.0.0","full_above":"1","heavy_from":"0.8",'
    b'"moderate_from":"0.5","multipliers":{"heavy":"0.7","light":"1","moderate":"0.9",'
    b'"unknown":"1"}},"weights":{"cba_semantic_topic":"0.15","industry_match":"0.3",'
    b'"proximity":"0.3","role_match":"0.25"}}'
)


def test_g_cba_19_same_weights_different_registry_hash(registry_3):
    case = _case("G-CBA-19")
    bands = CBA_REGISTRY_3.load_bands
    assert bands is not None

    # 1. Same weights, value for value.
    w3 = normalize_weights(model=CBA_3_PHYSICAL_MODEL, registry=CBA_REGISTRY_3)
    w2 = normalize_weights(model=CBA_PHYSICAL_MODEL)
    assert dict(w3) == dict(w2)
    v3 = normalize_weights(model=CBA_3_VIRTUAL_MODEL, registry=CBA_REGISTRY_3)
    v2 = normalize_weights(model=CBA_VIRTUAL_MODEL)
    assert dict(v3) == dict(v2)

    # 2. Different hash.
    h2 = registry_fingerprint(w2, load_bands=None)
    h3 = registry_fingerprint(w3, load_bands=bands)
    assert h2 == "sha256:f870192c2b1d9977aaf4be3368f51f67accbbbba9955e4346a4445b0be4be4e5"
    assert h3 != h2

    # 3. Pinned, and equal to a hand-written byte string.
    assert h3 == case["expected"]["registry_hash"]["cba-physical-1"]
    assert h3 == "sha256:73d5b67c898424c58984db49fa9542163e31438c23bed9742ecaebc50d9075f2"
    assert h3 == "sha256:" + hashlib.sha256(_G_CBA_19_LITERAL).hexdigest()

    # 4. Virtual 3.x differs from virtual 2.x and from physical 3.x.
    hv3 = registry_fingerprint(v3, load_bands=bands)
    assert hv3 != registry_fingerprint(v2, load_bands=None)
    assert hv3 != h3

    # 5. A multiplier moves it; review status does not; 0.5 and 0.50 hash alike.
    table = bands.table
    heavier = dataclasses.replace(
        bands,
        table=dataclasses.replace(
            table,
            multipliers={**table.multipliers, LoadBand.HEAVY: Decimal("0.71")},
        ),
    )
    assert registry_fingerprint(w3, load_bands=heavier) != h3
    reviewed = dataclasses.replace(
        bands,
        ownership=dataclasses.replace(bands.ownership, review_status=LoadReviewStatus.REVIEWED),
    )
    assert registry_fingerprint(w3, load_bands=reviewed) == h3
    respelled = dataclasses.replace(
        bands, table=dataclasses.replace(table, moderate_from=Decimal("0.5"))
    )
    assert table.moderate_from == Decimal("0.50")
    assert registry_fingerprint(w3, load_bands=respelled) == h3

    # 6. Same scoring_mode, different registry_version.
    _, kept, _ = _stage_a(case)
    three = _rank_3(case, kept)[0]
    two = _rank(_case("G-CBA-09"))[0]
    assert three.scoring_mode == two.scoring_mode == CBA_PHYSICAL_SCORING_MODE
    assert three.registry_version == REGISTRY_3_VERSION
    assert two.registry_version == REGISTRY_VERSION
    assert three.value == two.value == 0.97


def test_the_load_cases_never_make_3_0_0_current():
    from smartmatch_domain.factor_registry import current_cba_registry

    assert current_cba_registry() is CBA_REGISTRY
    assert copy.copy(REGISTRY_VERSION) == "2.0.0-approved-oq-cba-004"
