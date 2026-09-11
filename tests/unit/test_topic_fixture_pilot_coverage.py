"""What was tracked as OQ-CBA-061, made executable: the pilot's Topic factor.

The register entry (dissolved 7 September 2026 by ADR-0017) once stated this
defect in prose, as an open question. This file states it as assertions,
against the *real* pilot inputs rather than invented ones — pinned against the
fixture path, which is what this generator still exercises. ADR-0017 approved
an offline embedding model that reaches a measured score instead of
``unknown``, but only for a caller that passes ``use_local_embedding=True``;
this generator does not, so the fixture assertions below remain true of the tree
as it stands.

**Corrected 9 September 2026, and the correction is the point.**

Until that date this paragraph also claimed the assertions "would fail loudly
and say which of them is now wrong the day that changes". They would not have.
Every fixture assertion here holds because ``FixtureSemanticTopicProvider``
holds no recordings and therefore raises for *any* input — so none of them can
tell a right pair from a wrong one, and turning
``SMARTMATCH_CBA_TOPIC_LOCAL_EMBEDDING_ENABLED`` on changes nothing about them
either, because they construct their provider directly rather than reading the
setting. A guard that cannot fail is not a guard, and this one had in fact been
guarding the wrong pair: the text it restated was the seeded *calendar event*'s
description, not the *Speaker Request*'s, which is the string §9 compares
against. See :data:`PILOT_REQUEST_DESCRIPTION` for the mechanism and
:func:`test_the_generator_still_spells_the_pair_section_9_compares` for the
replacement.

Two tests near the foot of this file now exercise the real pair through
ADR-0017's provider, so the file holds assertions that a drifted pair set can
actually fail.

Nothing here changes behaviour. Every assertion below is a statement about the
tree as it stands today:

* :func:`smartmatch_providers.topic_semantics.build_semantic_topic_provider` —
  the call ``smartmatch_api.routers.match_runs._topic_provider`` makes on every
  match run — returns a :class:`FixtureSemanticTopicProvider` with **no
  recordings at all**. Nothing in ``services/``, ``python/`` or ``tools/`` calls
  ``.record()``; the only ``record`` calls outside tests are the module
  docstring's doctest and an unrelated ``_match_runs.record`` in the worker.
* The synthetic pilot dataset genuinely does put topic text on file, so this is
  not moot: ``tools/generate_pilot_dataset.py`` writes ``expertise_tags`` into
  the ``professionals`` import, and
  ``smartmatch_api.pipeline_provisioning._PROFESSIONAL_PROFILE_KEYS`` maps that
  column onto ``speaker_profile.topic_text``.
* The two together produce the perverse ordering: the seeded speaker **with**
  topic evidence is ``unknown`` and unscorable, and the seeded speaker
  **without** any is ``policy_neutral`` and shortlistable.

Why this file records the gap instead of closing it
---------------------------------------------------
Recording fixture comparisons for the pilot's pairs was considered and is not
done, for reasons stated here rather than left in a commit message:

1. The comparison the pilot asks for has no semantic content to record a
   judgement about. Both sides are drawn from one twelve-term vocabulary — the
   speaker's evidence is a comma-joined list of
   ``tools.pilot_dataset_plan._TOPICS`` terms, and the request's description —
   see :data:`PILOT_REQUEST_DESCRIPTION` — is deliberately written *not* to
   recite that vocabulary, precisely so the comparison cannot be satisfied by
   term overlap. Either way, any value a human recorded for such a pair would
   be a judgement about term overlap. That is the lexical comparison
   ``topic_semantics``'s module docstring refuses by name.
2. There is no small set of pairs. At the generator's defaults the seed alone
   yields 165 distinct topic strings, and both ``--seed`` and
   ``--professionals`` change the set. A corpus that covers one invocation
   silently reverts to this defect on the next.
3. Coverage for the synthetic dataset would fix the demo and nothing else. A
   real CBA import carries real topic text, which no recorded corpus reaches, so
   the defect would survive exactly where it matters while looking answered.
4. *Superseded on 7 September 2026, and left standing so the record reads
   honestly.* As written before that date this said: "The register already
   decided the disposition: OQ-CBA-061 says 'Nothing is worked around, and
   this is recorded rather than patched', and assigns the answer to the CBA
   product owner with the matching lead, alongside OQ-CBA-026." Both
   questions are now closed — ADR-0017 approved an offline, in-process
   embedding model, dissolving OQ-CBA-061 as a consequence of closing
   OQ-CBA-026 rather than by a separate policy change
   (`docs/plans/open-questions/cba-phase-deferred.md`). That closes the
   question this reason pointed to; it does not add coverage, since the model
   is opt-in via ``use_local_embedding=True`` and this generator's fixture
   path — and reasons 1-3 above — are unchanged by it.
5. *Superseded on 7 September 2026, and left standing so the record reads
   honestly.* As written on 6 September this said: "It would not change a pilot
   demo today in any case. The generator's own match-run submission is still on
   the pre-CBA contract and is rejected before any comparison is reached." That
   was true then and it is false now — TRACK 17 rewrote the generator's final
   phase, and a generated run submits, scores, and reaches the §9 comparison.
   See :func:`test_the_pilot_generators_match_run_body_is_on_the_cba_contract`,
   which is that same assertion inverted.

   **This strengthens reasons 1-4 rather than weakening them.** The demo now
   reaches the comparison and the comparison is unavailable, so the defect this
   file records is no longer hypothetical: on a live appliance, 56 of 100 named
   candidates were evaluated and came back unscorable, every one of them on
   ``cba_semantic_topic: unknown``. A recorded corpus is still not the remedy,
   for reasons 1-4 unchanged; what has changed is that the cost is now visible
   on screen rather than hidden behind a rejected submission.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
from smartmatch_api.pipeline_provisioning import _PROFESSIONAL_PROFILE_KEYS
from smartmatch_api.routers.match_runs import MatchRunRequest
from smartmatch_domain.factors.cba_semantic_topic import (
    NEUTRAL_TOPIC_POLICY_ID,
    SpeakerTopicEvidence,
    TopicEvidenceState,
    score_cba_semantic_topic,
)
from smartmatch_providers.base import Edition
from smartmatch_providers.topic_semantics import (
    FixtureSemanticTopicProvider,
    TopicComparisonUnavailable,
    build_semantic_topic_provider,
)

from tools import pilot_dataset_plan as plan

#: The generator's ``--professionals`` default, so the roster this file reasons
#: about is the one a demo actually runs.
#:
#: There is deliberately no ``--events`` counterpart. One was here until 9
#: September 2026, building the request side of the pairs out of the seeded
#: calendar events; that was the wrong source. §9 compares a *Speaker Request*'s
#: description, and the generator files :data:`SPEAKER_REQUEST_COUNT` of those
#: regardless of how many calendar events the seed carries. See
#: :data:`PILOT_REQUEST_DESCRIPTION`.
PILOT_PROFESSIONALS: int = 250

#: The §9 request side, verbatim.
#: ``generate_pilot_dataset.speaker_request_body`` builds the Speaker Request
#: every pilot match run is filed against, and its ``description`` is the text
#: :func:`score_cba_semantic_topic` compares a speaker's topic evidence against.
#:
#: **Not** ``f"Synthetic pilot {category.lower()} session."``. That literal is
#: the *calendar event* row's description
#: (``generate_pilot_dataset.write_events``), and §9 never reads it: filing a
#: Speaker Request writes its own ``event`` row from the body above — the route's
#: ``description`` field is documented as "customer §12's event topic/description,
#: and the text §9 compares" — and
#: ``match_run_evidence.SpeakerRequestEvidence.description`` is read off *that*
#: row. Until 9 September 2026 this file restated the event literal and its drift
#: guard pinned the event literal too, so every pair reasoned about below was
#: built from text no comparison ever sees.
PILOT_REQUEST_DESCRIPTION: str = (
    "A virtual panel for students weighing a first role: how professionals in "
    "these sectors and functions evaluate offers, build a first year, and decide "
    "what to specialise in."
)

#: How ``professionals_rows`` spells the ``expertise_tags`` cell that
#: ``pipeline_provisioning`` maps onto ``speaker_profile.topic_text`` — the §9
#: speaker side, and the only side of the pair the pilot varies.
PILOT_TOPIC_JOIN: str = ", "


def _pilot_topic_strings() -> list[str]:
    """Every distinct ``speaker_profile.topic_text`` the default seed produces."""
    planned = plan.build_professionals(PILOT_PROFESSIONALS, seed=plan.DEFAULT_SEED)
    return sorted(
        {PILOT_TOPIC_JOIN.join(person.topics) for person in planned if person.topics is not None}
    )


def _pilot_descriptions() -> list[str]:
    """Every distinct Speaker Request description a generated pilot files.

    There is exactly one. ``speaker_request_body`` files
    ``SPEAKER_REQUEST_COUNT`` sibling requests that differ in title, date and
    §7/§8 targets, and every one carries the same hard-coded ``description``: it
    is not templated on the request's category, and the generator's own docstring
    says why — a description assembled out of the same twelve terms the speakers'
    expertise cells are drawn from "would make the comparison a lexical overlap
    wearing a semantic factor's clothes".

    A list of one rather than a bare string, so the callers below read unchanged
    and a seed that ever does vary the description needs no edit here beyond the
    guard.
    """
    return [PILOT_REQUEST_DESCRIPTION]


# ---------------------------------------------------------------------------
# The gap is not moot: the pilot really does put topic text on file
# ---------------------------------------------------------------------------


def test_the_pilot_seed_puts_topic_evidence_on_most_speakers():
    """If the seed carried no topic evidence, the defect once tracked as
    OQ-CBA-061 (dissolved 7 September 2026 by ADR-0017) would not reach a demo.

    It carries plenty: only ``UNKNOWN_TOPIC_SHARE`` of professionals have no
    expertise record, and every one of the rest becomes a ``topic_text`` value
    through the import path — which is precisely the population the Topic
    factor then cannot score.
    """
    planned = plan.build_professionals(PILOT_PROFESSIONALS, seed=plan.DEFAULT_SEED)
    with_topics = [person for person in planned if person.topics is not None]

    assert len(with_topics) > len(planned) // 2, (
        "the synthetic pilot is supposed to give most professionals expertise tags; "
        f"only {len(with_topics)} of {len(planned)} carry any"
    )


def test_the_import_column_the_pilot_writes_lands_in_topic_text():
    """``expertise_tags`` is the column, ``speaker_profile.topic_text`` the field.

    Asserted off the mapping itself rather than described, because this single
    line is the whole reason a generated dataset reaches the §9 Topic factor at
    all.
    """
    assert _PROFESSIONAL_PROFILE_KEYS["expertise_tags"] == "topic_text"


def test_the_pilot_exercises_many_pairs_and_not_a_recordable_few():
    """The reason a recorded corpus is not the remedy, stated as a number.

    **Corrected 9 September 2026.** This asserted ``len(descriptions) >= 5``,
    which held only because the descriptions were being built from the *event*
    literal — seven engagement categories, seven strings. §9 reads the Speaker
    Request's description and there is one of those, so the real pair set is
    N x 1 rather than N x 7. That is the one assertion in this file the
    wrong-literal defect made false rather than merely irrelevant, and it is
    stated here rather than quietly relaxed.

    The claim under test survives the correction intact. The breadth was never
    on the request side: one seed still puts more distinct speaker strings on
    file than anybody would hand-record a judgement for, and each of the sibling
    requests scores against all of them.
    """
    topics = _pilot_topic_strings()
    descriptions = _pilot_descriptions()

    assert len(topics) > 100, (
        "one seed alone yields more distinct speaker topic strings than anybody "
        f"would hand-record a judgement for; got {len(topics)}"
    )
    assert len(descriptions) == 1, (
        "every sibling Speaker Request the generator files carries the same "
        f"description, so §9 has one request-side string; got {len(descriptions)}"
    )
    assert len(topics) * len(descriptions) > 100


# ---------------------------------------------------------------------------
# The nearer defect, since fixed: the generator's own match-run submission
# ---------------------------------------------------------------------------


def _generator_module():
    """Import ``tools/generate_pilot_dataset.py``, which needs ``tools/`` on the path.

    It does a bare ``from pilot_dataset_plan import ...`` rather than
    ``from tools import ...``, so the package import alone is not enough. The
    insertion is undone before returning so nothing else in the session sees a
    widened path.
    """
    tools_dir = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, tools_dir)
    try:
        from tools import generate_pilot_dataset

        return generate_pilot_dataset
    finally:
        if sys.path and sys.path[0] == tools_dir:
            sys.path.pop(0)


def test_the_pilot_generators_match_run_body_is_on_the_cba_contract():
    """``generate_pilot_dataset`` submits a body the CBA route accepts.

    **Inverted on 7 September 2026, not deleted.** As written on 6 September this
    was ``..._is_on_the_pre_cba_contract`` and asserted the opposite: that
    :func:`generate_pilot_dataset.match_run_body` built the pre-CBA shape (a
    string ``event_need_id``, ``required_topics``, and candidates carrying their
    own ``expertise_topics``) and raised two ``missing`` errors against
    :class:`MatchRunRequest`. That was true, and it was a defect — pinned here
    rather than fixed because the generator sat outside that change's fence.
    TRACK 17 rewrote the generator's final phase and closed it, so the assertion
    is turned around rather than dropped: the property under guard is the same
    one watched from the other side, and a regression to the pre-CBA shape must
    still fail somewhere.

    Why it stays in *this* file and not only in
    ``tests/unit/test_pilot_generator_match_run.py``: paragraph 5 of the module
    docstring above used to argue that recording fixture comparisons "would not
    change a pilot demo today in any case", because the submission was rejected
    before any comparison was reached. That argument is now void — the run
    submits, scores, and drops most of its pool on the §9 factor — and this test
    is what fails if the submission ever breaks again and quietly restores the
    old excuse.

    OQ-CBA-031 is why the body carries no evidence: the server assembles every
    scored fact from this tenant's own rows, so there is no field here in which a
    caller could state a speaker's expertise.
    """
    generator = _generator_module()
    request_id = uuid.uuid4()
    candidates = (uuid.uuid4(), uuid.uuid4())

    body = generator.match_run_body(
        speaker_request_id=request_id,
        candidate_subject_ids=candidates,
        seed=plan.DEFAULT_SEED,
    )

    assert "speaker_request_id" in body
    assert "candidate_subject_ids" in body

    validated = MatchRunRequest.model_validate(body)
    assert validated.speaker_request_id == request_id
    assert validated.candidate_subject_ids == list(candidates)

    # The other half of OQ-CBA-031, and the half a field rename alone would have
    # satisfied: no evidence of any kind travels in the body.
    for banned in ("event_need_id", "required_topics", "expertise_topics", "candidates"):
        assert banned not in body


# ---------------------------------------------------------------------------
# The gap itself
# ---------------------------------------------------------------------------


def test_the_provider_a_match_run_builds_holds_no_recordings():
    """``_topic_provider()`` hands the scorer an empty playback fixture.

    This is the defect in one assertion. The provider is not misconfigured and
    not failing — it is correct, and it has been given nothing to replay.
    """
    provider = build_semantic_topic_provider(Edition.DEV)
    description = _pilot_descriptions()[0]
    evidence = _pilot_topic_strings()[0]

    with pytest.raises(TopicComparisonUnavailable):
        provider.compare(description, evidence)


@pytest.mark.parametrize("edition", list(Edition))
def test_no_edition_gets_a_provider_with_pilot_coverage(edition: Edition):
    """Not a classroom-only shortfall: every edition gets the same empty fixture."""
    provider = build_semantic_topic_provider(edition)

    for description in _pilot_descriptions():
        for topic_text in _pilot_topic_strings()[:5]:
            with pytest.raises(TopicComparisonUnavailable):
                provider.compare(description, topic_text)


def test_a_seeded_pilot_speaker_with_topic_text_scores_unknown():
    """The consequence: the best-documented speaker is unscorable.

    ``unknown`` propagates to a ``None`` composite (ADR-0011 rule 1), so this
    candidate leaves the shortlist entirely.
    """
    score = score_cba_semantic_topic(
        _pilot_descriptions()[0],
        SpeakerTopicEvidence.from_profile(topic_text=_pilot_topic_strings()[0]),
        build_semantic_topic_provider(Edition.DEV),
    )

    assert score.state is TopicEvidenceState.UNKNOWN
    assert score.value is None
    assert not score.is_scorable


def test_absence_of_topic_evidence_outranks_presence_in_the_pilot():
    """The defect once tracked as OQ-CBA-061, in one comparison, on the
    pilot's own data. Dissolved 7 September 2026 by ADR-0017 for a caller
    that opts into the offline embedding model; this test calls
    ``build_semantic_topic_provider`` with no ``use_local_embedding``
    keyword, so it still gets the fixture and the ordering below still holds.

    The seeded speaker who filled nothing in is shortlistable at the §9 neutral;
    the seeded speaker who filled the field in is not shortlistable at all.
    """
    provider = build_semantic_topic_provider(Edition.DEV)
    description = _pilot_descriptions()[0]

    documented = score_cba_semantic_topic(
        description,
        SpeakerTopicEvidence.from_profile(topic_text=_pilot_topic_strings()[0]),
        provider,
    )
    silent = score_cba_semantic_topic(
        description,
        SpeakerTopicEvidence.from_profile(topic_text=None, prior_talk=None),
        provider,
    )

    assert not documented.is_scorable
    assert silent.is_scorable
    assert silent.state is TopicEvidenceState.POLICY_NEUTRAL
    assert silent.policy_id == NEUTRAL_TOPIC_POLICY_ID


# ---------------------------------------------------------------------------
# The guard that must not weaken
# ---------------------------------------------------------------------------


def test_an_unrecorded_pair_still_raises_when_other_pairs_are_recorded():
    """A populated fixture must not answer for a pair it was not given.

    The failure mode this guards against is a corpus that gains a default, a
    nearest-match, or a fallback on the way to covering "enough" pairs. Any of
    those would file "we could not check" as a measurement, which is the exact
    substitution ADR-0011 exists to refuse.
    """
    provider = FixtureSemanticTopicProvider()
    provider.record(
        "Synthetic pilot hackathon session.",
        "hackathon, career panel, workshop",
        score=0.7,
        rationale="Fixture recording for the seeded pilot pair.",
    )

    assert provider.compare(
        "Synthetic pilot hackathon session.", "hackathon, career panel, workshop"
    ).score == pytest.approx(0.7)

    with pytest.raises(TopicComparisonUnavailable):
        provider.compare("Synthetic pilot keynote session.", "hackathon, career panel, workshop")

    with pytest.raises(TopicComparisonUnavailable):
        provider.compare("Synthetic pilot hackathon session.", "workshop")


def test_a_recorded_comparison_never_claims_to_be_a_semantic_model():
    """Whatever is ever recorded, the provenance stays true.

    A recorded value labelled ``is_semantic_model`` would put a permanent
    untruth about how a match was produced into stored data.
    """
    provider = FixtureSemanticTopicProvider()
    provider.record(
        "Synthetic pilot workshop session.",
        "workshop, mentor",
        score=0.6,
        rationale="Fixture recording, not a model output.",
    )

    comparison = provider.compare("Synthetic pilot workshop session.", "workshop, mentor")

    assert provider.is_semantic_model is False
    assert comparison.is_semantic_model is False
    assert comparison.model_id is None


# ---------------------------------------------------------------------------
# The same pairs with ADR-0017's model active, rather than the empty fixture
# ---------------------------------------------------------------------------


def test_the_local_embedding_provider_measures_the_pilots_real_pairs():
    """What ``SMARTMATCH_CBA_TOPIC_LOCAL_EMBEDDING_ENABLED=true`` changes here.

    Every assertion above the fold holds because the fixture answers *nothing*:
    it raises for any input, so it raises for a wrong pair exactly as readily as
    for a right one. That is what let the drift guard below pin the wrong
    literal for as long as it did, and it is why this file needs at least one
    assertion a wrong pair could actually fail.

    This is that assertion. It runs the real §9 pair — the Speaker Request's
    description against the ``expertise_tags`` cells — through the provider the
    flag selects, which computes rather than replays. If either side moves to
    text ADR-0017's vendored vocabulary cannot reach, this goes red instead of
    staying vacuously green.

    The flag itself is not read here. ``routers.match_runs._topic_provider``
    reads ``settings.cba_topic_local_embedding_enabled`` and passes it as
    ``use_local_embedding``; this constructs the same provider directly, so the
    pins hold whichever way an appliance is configured.
    """
    provider = build_semantic_topic_provider(Edition.DEV, use_local_embedding=True)
    description = _pilot_descriptions()[0]
    topics = _pilot_topic_strings()

    measured = 0
    unavailable: list[str] = []
    for topic_text in topics:
        try:
            comparison = provider.compare(description, topic_text)
        except TopicComparisonUnavailable:
            unavailable.append(topic_text)
            continue
        measured += 1
        assert 0.0 <= comparison.score <= 1.0
        assert comparison.is_semantic_model is True

    assert measured == len(topics) - len(unavailable)
    assert measured > 100, (
        "the flag is supposed to turn nearly every pilot pair from unknown into a "
        f"measurement; only {measured} of {len(topics)} were reached"
    )
    # Not zero, and named rather than tolerated. Both terms of this one cell sit
    # outside the vendored vocabulary — neither ``hackathon`` nor ``panelist``
    # appears in ``data/glove_vocab.txt`` — so nothing on the speaker's side can
    # be embedded and the pair is a genuine absence: the residue ADR-0017
    # accepts, not a missing recording. Pinned so it stays a *stated* residue; a
    # second entry appearing here is the seed drifting away from the vocabulary.
    assert unavailable == ["hackathon, panelist"], (
        "the set of pilot pairs the vendored vocabulary cannot reach has changed; "
        f"got {unavailable}"
    )


def test_a_seeded_pilot_speaker_with_topic_text_is_scorable_under_the_flag():
    """The perverse ordering above is the fixture's, and the flag ends it.

    Same speaker, same request, same scorer as
    :func:`test_a_seeded_pilot_speaker_with_topic_text_scores_unknown`; only the
    provider differs. Documented evidence becomes a measurement, and the
    candidate stays in the pool instead of leaving it.
    """
    score = score_cba_semantic_topic(
        _pilot_descriptions()[0],
        SpeakerTopicEvidence.from_profile(topic_text=_pilot_topic_strings()[0]),
        build_semantic_topic_provider(Edition.DEV, use_local_embedding=True),
    )

    assert score.state is TopicEvidenceState.MEASURED
    assert score.is_scorable
    assert score.value is not None


# ---------------------------------------------------------------------------
# Drift guard for the pair §9 actually compares
# ---------------------------------------------------------------------------


def test_the_generator_still_spells_the_pair_section_9_compares():
    """Catch the generator changing under the pairs reasoned about above.

    **Rewritten 9 September 2026, because its predecessor guarded the wrong
    pair.** It asserted that ``f"Synthetic pilot {event.category.lower()} session."``
    was still present in the generator's source — a true statement about the
    source and an irrelevant one about §9, since that literal is the calendar
    event row's description while the comparison reads the Speaker Request's.
    The guard therefore could not have detected drift in the one string that
    matters, and nothing downstream noticed, because the fixture answers no pair
    at all.

    It is also no longer a source-text search. The predecessor's docstring said
    ``generate_pilot_dataset`` "cannot be imported from here";
    :func:`_generator_module` imports it, and has done since TRACK 17. Both
    sides are pinned against the generator functions' own output, which a
    rename, a reflow or a moved literal cannot slip past.
    """
    generator = _generator_module()
    roster = plan.build_professionals(PILOT_PROFESSIONALS, seed=plan.DEFAULT_SEED)

    # The request side: every sibling request a generated pilot files, because
    # §9 scores against each of them and they are only *assumed* to agree.
    for variant in range(generator.SPEAKER_REQUEST_COUNT):
        body = generator.speaker_request_body(roster, seed=plan.DEFAULT_SEED, variant=variant)
        assert body["description"] == PILOT_REQUEST_DESCRIPTION, (
            "the Speaker Request description §9 compares against has moved; update "
            "PILOT_REQUEST_DESCRIPTION"
        )

    # The speaker side: the expertise_tags cell that becomes topic_text.
    cells = {
        row["expertise_tags"]
        for row in generator.professionals_rows(roster)
        if "expertise_tags" in row
    }
    assert cells == set(_pilot_topic_strings()), (
        "the expertise_tags cell this file builds its pairs from has moved; update PILOT_TOPIC_JOIN"
    )
