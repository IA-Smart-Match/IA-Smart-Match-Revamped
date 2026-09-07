"""An unmeasured speaker is absent from a physical pool, not last in it.

OQ-CBA-024 removed the route's 503, so ``cba-physical-1`` now scores. The
refusal existed for a reason, and this file pins that the reason is still
honoured by a different mechanism rather than quietly dropped along with the
error code.

The mechanism is :func:`~smartmatch_api.routers.match_runs._partition_pool`,
and the distinction it enforces is the whole of ADR-0011. A speaker whose ZIP
the California table does not name has an **unknown** distance. Under the
physical model an unknown factor makes the composite unknown, so that speaker
has no utility — and there are exactly two things a system can do with them:

* enter them at ``0.0``, where they sort below every measured candidate and a
  coordinator reads the ranking as "we looked at this person and they were a
  poor fit"; or
* leave them out of the pool and **say so**, which reads as "nobody has
  recorded where this person is", and points at an action that fixes it.

The second is what the code does. These tests fail if it ever becomes the
first — including the subtle version of the first, where the candidate is
technically excluded but nothing reports the exclusion, and a shortlist of
three silently comes back drawn from a roster of five.
"""

from __future__ import annotations

import pytest
from smartmatch_api.routers.match_runs import _partition_pool
from smartmatch_api.zip_proximity import resolve_distance_from_campus
from smartmatch_domain.cba_role_categories import resolve_role_category
from smartmatch_domain.explanation import ScoreState, explain_candidates
from smartmatch_domain.factors.cba_semantic_topic import (
    CBA_SEMANTIC_TOPIC_FACTOR_KEY,
    SpeakerTopicEvidence,
)
from smartmatch_domain.factors.industry_match import IndustryMatchInputs
from smartmatch_domain.factors.proximity import (
    CBA_PHYSICAL_SCORING_MODE,
    CBA_PROXIMITY_FACTOR_KEY,
    FAR_BAND_SCORE,
    SpeakerLocation,
)
from smartmatch_domain.factors.role_match import RoleMatchInputs
from smartmatch_domain.naics_sectors import resolve_sector
from smartmatch_domain.scoring import CbaCandidateEvidence, rank_cba_candidates
from smartmatch_providers.topic_semantics import FixtureSemanticTopicProvider

REQUEST_DESCRIPTION = "A panel on financial planning for small businesses."
TOPIC_TEXT = "corporate treasury and financial planning"
SECTOR = "52"
ROLE = "finance"

#: In the table. Pomona, a few miles from the campus.
RESOLVABLE_ZIP = "91768"

#: Well formed, five digits, and not a Californian ZCTA. The distance is
#: unknown — not "far", which is what a fallback would have made it.
UNRESOLVABLE_ZIP = "10001"


def _candidate(
    subject_id: str, postal_code: str | None, *, city: str | None = "Pomona"
) -> CbaCandidateEvidence:
    """One speaker who differs from the others only in where they live.

    Everything else is deliberately identical and strong: same sector, same
    role, same topic text, same recorded comparison. If the unmeasured speaker
    is excluded, it can only be because of the distance — not because they were
    weak on some other axis that muddies the reading.
    """
    distance = resolve_distance_from_campus(postal_code)
    return CbaCandidateEvidence(
        subject_id=subject_id,
        industry=IndustryMatchInputs(
            speaker_sector=resolve_sector(SECTOR),
            requested_sectors=(resolve_sector(SECTOR),),
        ),
        role=RoleMatchInputs(
            speaker_role=resolve_role_category(ROLE),
            requested_roles=(resolve_role_category(ROLE),),
        ),
        topic_evidence=SpeakerTopicEvidence.from_profile(topic_text=TOPIC_TEXT, prior_talk=None),
        location=SpeakerLocation(city=city, postal_code=postal_code),
        distance_miles=None if distance is None else distance.miles,
        distance_provenance=None if distance is None else distance.provenance,
    )


def _provider() -> FixtureSemanticTopicProvider:
    provider = FixtureSemanticTopicProvider()
    provider.record(
        REQUEST_DESCRIPTION,
        TOPIC_TEXT,
        score=0.8,
        rationale="Their recorded treasury work addresses the request's financial planning focus.",
    )
    return provider


def _partitioned(*candidates: CbaCandidateEvidence):
    ranked = rank_cba_candidates(
        candidates,
        request_description=REQUEST_DESCRIPTION,
        topic_provider=_provider(),
        scoring_mode=CBA_PHYSICAL_SCORING_MODE,
    )
    return _partition_pool(explain_candidates(ranked))


@pytest.fixture
def pool():
    return _partitioned(
        _candidate("MEASURED", RESOLVABLE_ZIP),
        _candidate("UNRESOLVED-ZIP", UNRESOLVABLE_ZIP),
        # Neither a city nor a ZIP: the *other* absence, and the one ADR-0016
        # Proposal 4 words differently.
        _candidate("NO-PLACE-ON-FILE", None, city=None),
    )


# ---------------------------------------------------------------------------
# The partition itself
# ---------------------------------------------------------------------------


def test_a_speaker_whose_zip_cannot_be_resolved_is_not_in_the_solvable_pool(pool):
    scorable, _ = pool
    assert [item.subject_id for item in scorable] == ["MEASURED"]


def test_the_unmeasured_speakers_are_reported_rather_than_dropped(pool):
    """Excluded is not the same as forgotten. The count is what a Speaker
    Connector acts on, and a candidate who vanished silently would leave a
    shortlist of three drawn from a roster of five with nothing saying so."""
    _, unscorable = pool
    assert sorted(item.subject_id for item in unscorable) == ["NO-PLACE-ON-FILE", "UNRESOLVED-ZIP"]


def test_every_named_candidate_lands_in_exactly_one_side_of_the_partition(pool):
    scorable, unscorable = pool
    subjects = [item.subject_id for item in scorable] + [item.subject_id for item in unscorable]
    assert sorted(subjects) == ["MEASURED", "NO-PLACE-ON-FILE", "UNRESOLVED-ZIP"]


# ---------------------------------------------------------------------------
# Not 0.0, and not the Far band
# ---------------------------------------------------------------------------


def test_an_unresolved_zip_is_an_unknown_proximity_and_not_a_zero(pool):
    """The coercion ADR-0011 forbids, asserted at the factor rather than at the
    composite: a value of ``0.0`` here would be a measured claim that this
    speaker is maximally distant, which nobody measured."""
    _, unscorable = pool
    unresolved = next(item for item in unscorable if item.subject_id == "UNRESOLVED-ZIP")
    proximity = next(
        factor for factor in unresolved.factors if factor.factor_key == CBA_PROXIMITY_FACTOR_KEY
    )

    assert proximity.state is ScoreState.UNKNOWN
    assert proximity.value is None
    assert proximity.estimate_label is None


def test_an_unresolved_zip_is_not_filed_in_the_far_band(pool):
    """ADR-0016 Proposal 4. Filing an unknown as Far would mean a speaker who
    later supplies a resolvable ZIP sees their score move for no visible
    reason, and until then reads as "measured, and distant"."""
    _, unscorable = pool
    unresolved = next(item for item in unscorable if item.subject_id == "UNRESOLVED-ZIP")
    proximity = next(
        factor for factor in unresolved.factors if factor.factor_key == CBA_PROXIMITY_FACTOR_KEY
    )

    assert proximity.value != FAR_BAND_SCORE
    assert "not resolved to a coordinate" in proximity.basis
    assert "is not the Far band" in proximity.basis


def test_the_unmeasured_composite_is_unknown_rather_than_a_low_number(pool):
    _, unscorable = pool
    for item in unscorable:
        assert item.heuristic_score is None
        assert item.state is ScoreState.UNKNOWN
        assert CBA_PROXIMITY_FACTOR_KEY in item.unknown_factor_keys
        assert not item.is_shortlistable


def test_the_two_unmeasured_speakers_are_distinguishable_from_each_other(pool):
    """A ZIP that resolved to nothing and no ZIP at all are different facts and
    call for different actions — correct the record, or collect one. They must
    not arrive at a surface as one indistinguishable greyed-out row."""
    _, unscorable = pool
    reasons = {
        item.subject_id: next(
            factor.basis for factor in item.factors if factor.factor_key == CBA_PROXIMITY_FACTOR_KEY
        )
        for item in unscorable
    }
    assert reasons["UNRESOLVED-ZIP"] != reasons["NO-PLACE-ON-FILE"]
    assert "no postal code" in reasons["NO-PLACE-ON-FILE"]


# ---------------------------------------------------------------------------
# The measured candidate really was measured
# ---------------------------------------------------------------------------


def test_the_resolvable_zip_produces_a_scored_proximity_with_its_provenance(pool):
    """The other half of the pin: if this stopped working, every test above
    would still pass with an empty pool and nothing scored at all."""
    scorable, _ = pool
    measured = scorable[0]
    proximity = next(
        factor for factor in measured.factors if factor.factor_key == CBA_PROXIMITY_FACTOR_KEY
    )

    assert proximity.state is ScoreState.MEASURED
    assert proximity.value == 1.0
    assert "Distance from zcta-centroid-2023." in proximity.basis
    assert proximity.estimate_label is not None
    assert "ZIP code area" in proximity.estimate_label
    assert measured.heuristic_score is not None
    assert measured.is_shortlistable


def test_the_physical_model_scores_proximity_at_all(pool):
    """A regression net for the mode itself: were the run to fall back to
    ``cba-virtual-1``, proximity would be absent from the factor set and every
    one of these candidates would score, unmeasured distance and all."""
    scorable, _ = pool
    keys = [factor.factor_key for factor in scorable[0].factors]
    assert CBA_PROXIMITY_FACTOR_KEY in keys
    assert CBA_SEMANTIC_TOPIC_FACTOR_KEY in keys
    assert scorable[0].scoring_mode == CBA_PHYSICAL_SCORING_MODE
