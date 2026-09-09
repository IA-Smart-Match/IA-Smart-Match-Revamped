"""ADR-0017's offline embedding model is reachable, but only as a deployment fact.

PR #114 merged ``LocalEmbeddingSemanticTopicProvider`` and gave
``build_semantic_topic_provider`` a ``use_local_embedding`` keyword, off by
default. Nothing in that PR called it with anything but the default, so the
model was merged and unreachable: the only production call site,
``smartmatch_api.routers.match_runs._topic_provider``, never passed
``use_local_embedding=True``.

This file pins the wiring that closes that gap:

* ``Settings.cba_topic_local_embedding_enabled`` is off by default, so an
  unconfigured deployment's provider — and therefore its golden pins — is
  unchanged.
* Setting it (a deployment/environment fact, never a request field) routes
  ``_topic_provider()`` to the offline embedding model.
* With the flag on, a candidate pair the fixture has no recording for now
  gets a *measured* score instead of *unknown* — the concrete defect this
  wiring exists to fix.
* The stored ``basis`` for a measured Topic factor names which engine
  produced it (``fixture-topic-semantics`` vs. ``local-embedding-topic-
  semantics``), so a stored run is distinguishable from another by that text
  alone, with no schema change needed — see the PR description for why this,
  and not ``scoring_mode``, is the honest place for that provenance.
* A live/external model credential still fails closed with the flag on:
  ADR-0017 approves an offline model, not a vendor.
"""

from __future__ import annotations

import pytest
from smartmatch_api.config import Settings, get_settings
from smartmatch_api.routers.match_runs import _topic_provider
from smartmatch_domain.cba_role_categories import resolve_role_category
from smartmatch_domain.explanation import explain_candidates
from smartmatch_domain.factors.cba_semantic_topic import (
    CBA_SEMANTIC_TOPIC_FACTOR_KEY,
    SpeakerTopicEvidence,
)
from smartmatch_domain.factors.industry_match import IndustryMatchInputs
from smartmatch_domain.factors.proximity import CBA_VIRTUAL_SCORING_MODE
from smartmatch_domain.factors.role_match import RoleMatchInputs
from smartmatch_domain.naics_sectors import resolve_sector
from smartmatch_domain.scoring import CbaCandidateEvidence, rank_cba_candidates
from smartmatch_providers import Edition, ProviderConfigurationError
from smartmatch_providers.topic_semantics import (
    FIXTURE_TOPIC_PROVIDER_NAME,
    LOCAL_EMBEDDING_TOPIC_PROVIDER_NAME,
    FixtureSemanticTopicProvider,
    LocalEmbeddingSemanticTopicProvider,
    build_semantic_topic_provider,
)

REQUEST_DESCRIPTION = "An event on supply chain analytics for retail operators."
#: Real topic text a fixture has no recording for — one of the 56 pilot
#: dropouts ADR-0017's Findings section describes, in miniature.
UNRECORDED_TOPIC_TEXT = "logistics optimization and inventory forecasting"
SECTOR = "52"
ROLE = "finance"


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """``get_settings`` is process-cached; each test must see its own env."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# The setting itself
# ---------------------------------------------------------------------------


def test_the_local_embedding_setting_defaults_off():
    settings = Settings()
    assert settings.cba_topic_local_embedding_enabled is False


def test_the_setting_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SMARTMATCH_CBA_TOPIC_LOCAL_EMBEDDING_ENABLED", "true")
    settings = Settings()
    assert settings.cba_topic_local_embedding_enabled is True


# ---------------------------------------------------------------------------
# _topic_provider: off by default, reachable when the deployment opts in
# ---------------------------------------------------------------------------


def test_topic_provider_is_the_fixture_when_unconfigured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SMARTMATCH_CBA_TOPIC_LOCAL_EMBEDDING_ENABLED", raising=False)
    provider = _topic_provider()
    assert isinstance(provider, FixtureSemanticTopicProvider)
    assert provider.name == FIXTURE_TOPIC_PROVIDER_NAME


def test_topic_provider_reaches_the_offline_embedding_model_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("SMARTMATCH_CBA_TOPIC_LOCAL_EMBEDDING_ENABLED", "true")
    provider = _topic_provider()
    assert isinstance(provider, LocalEmbeddingSemanticTopicProvider)
    assert provider.name == LOCAL_EMBEDDING_TOPIC_PROVIDER_NAME


# ---------------------------------------------------------------------------
# The measured consequence: an unrecorded pair stops being "unknown"
# ---------------------------------------------------------------------------


def _candidate(topic_text: str) -> CbaCandidateEvidence:
    return CbaCandidateEvidence(
        subject_id="SPEAKER-1",
        industry=IndustryMatchInputs(
            speaker_sector=resolve_sector(SECTOR),
            requested_sectors=(resolve_sector(SECTOR),),
        ),
        role=RoleMatchInputs(
            speaker_role=resolve_role_category(ROLE),
            requested_roles=(resolve_role_category(ROLE),),
        ),
        topic_evidence=SpeakerTopicEvidence.from_profile(topic_text=topic_text, prior_talk=None),
        location=None,
        distance_miles=None,
        distance_provenance=None,
    )


def _topic_factor(provider):
    ranked = rank_cba_candidates(
        [_candidate(UNRECORDED_TOPIC_TEXT)],
        request_description=REQUEST_DESCRIPTION,
        topic_provider=provider,
        scoring_mode=CBA_VIRTUAL_SCORING_MODE,
    )
    [explanation] = explain_candidates(ranked)
    [factor] = [f for f in explanation.factors if f.factor_key == CBA_SEMANTIC_TOPIC_FACTOR_KEY]
    return factor


def test_flag_off_an_unrecorded_pair_stays_unknown_byte_identical_to_today():
    factor = _topic_factor(FixtureSemanticTopicProvider())
    assert factor.state.value == "unknown"
    assert factor.value is None


def test_flag_on_the_same_unrecorded_pair_is_now_measured():
    factor = _topic_factor(LocalEmbeddingSemanticTopicProvider())
    assert factor.state.value == "measured"
    assert factor.value is not None


def test_recorded_provenance_differs_between_the_two_engines():
    """The whole of the provenance requirement: reading the stored ``basis``
    alone tells you which engine produced a measured Topic factor. No
    ``scoring_mode`` bump, no new column — the factor has always recorded its
    provider's name in ``basis``; this just confirms the two names actually
    diverge in what gets stored."""
    fixture_basis = _topic_factor(FixtureSemanticTopicProvider())
    # The fixture has no recording for this pair, so it is unknown and its
    # basis says why — it never claims a provider produced a number.
    assert FIXTURE_TOPIC_PROVIDER_NAME not in fixture_basis.basis

    local_basis = _topic_factor(LocalEmbeddingSemanticTopicProvider())
    assert LOCAL_EMBEDDING_TOPIC_PROVIDER_NAME in local_basis.basis
    assert FIXTURE_TOPIC_PROVIDER_NAME not in local_basis.basis


# ---------------------------------------------------------------------------
# Safety properties that must survive the flag being on
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "edition", [Edition.DEV, Edition.STAGING, Edition.CLASSROOM, Edition.PRODUCTION]
)
def test_a_live_model_credential_still_fails_closed_with_the_flag_on(edition: Edition):
    """The exact keyword combination ``_topic_provider`` would pass once this
    deployment's flag is on, plus a credential nothing in this repository
    should ever hold. ADR-0017 approves an offline model, not a vendor."""
    with pytest.raises(ProviderConfigurationError):
        build_semantic_topic_provider(
            edition,
            use_local_embedding=True,
            api_key="live-key",
        )


def test_a_live_external_vendor_is_still_refused_when_local_embedding_is_off():
    with pytest.raises(ProviderConfigurationError):
        build_semantic_topic_provider(Edition.PRODUCTION, use_fixture=False)
