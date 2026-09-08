"""What was tracked as OQ-CBA-061, made executable: the pilot's Topic factor.

The register entry (dissolved 7 September 2026 by ADR-0017) once stated this
defect in prose, as an open question. This file states it as assertions,
against the *real* pilot inputs rather than invented ones — pinned against the
fixture path, which is what this generator still exercises. ADR-0017 approved
an offline embedding model that reaches a measured score instead of
``unknown``, but only for a caller that passes ``use_local_embedding=True``;
this generator does not, so the assertions below remain true of the tree as it
stands, and would fail loudly and say which of them is now wrong the day that
changes.

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
   ``tools.pilot_dataset_plan._TOPICS`` terms and the request's description is
   ``f"Synthetic pilot {category.lower()} session."`` — so any defensible value
   for a pair is a function of term overlap between them. That is the lexical
   comparison ``topic_semantics``'s module docstring refuses by name.
2. There is no small set of pairs. At the generator's defaults the seed alone
   yields 165 distinct topic strings against 7 category descriptions, and every
   one of ``--seed``, ``--professionals`` and ``--events`` changes the set. A
   corpus that covers one invocation silently reverts to this defect on the
   next.
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

import re
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

#: The generator's ``--professionals`` and ``--events`` defaults, so the plan
#: this file reasons about is the one a demo actually runs.
PILOT_PROFESSIONALS: int = 250
PILOT_EVENTS: int = 60

#: How ``tools/generate_pilot_dataset.py::write_events`` spells a Speaker
#: Request's description, and how ``professionals_rows`` spells the
#: ``expertise_tags`` cell. Restated here rather than imported because that
#: module needs ``tools/`` itself on ``sys.path`` to import (it does a bare
#: ``from pilot_dataset_plan import ...``) and pytest only puts the repository
#: root there. The drift guard at the foot of this file is what keeps the
#: restatement honest.
PILOT_DESCRIPTION_TEMPLATE: str = "Synthetic pilot {category} session."
PILOT_TOPIC_JOIN: str = ", "


def _pilot_topic_strings() -> list[str]:
    """Every distinct ``speaker_profile.topic_text`` the default seed produces."""
    planned = plan.build_professionals(PILOT_PROFESSIONALS, seed=plan.DEFAULT_SEED)
    return sorted(
        {PILOT_TOPIC_JOIN.join(person.topics) for person in planned if person.topics is not None}
    )


def _pilot_descriptions() -> list[str]:
    """Every distinct Speaker Request description the default seed produces."""
    planned = plan.build_events(PILOT_EVENTS, seed=plan.DEFAULT_SEED)
    return sorted(
        {PILOT_DESCRIPTION_TEMPLATE.format(category=event.category.lower()) for event in planned}
    )


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
    """The reason a recorded corpus is not the remedy, stated as a number."""
    topics = _pilot_topic_strings()
    descriptions = _pilot_descriptions()

    assert len(topics) > 100, (
        "one seed alone yields more distinct speaker topic strings than anybody "
        f"would hand-record a judgement for; got {len(topics)}"
    )
    assert len(descriptions) >= 5


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
# Drift guard for the two literals this file restates
# ---------------------------------------------------------------------------


def test_the_generator_still_spells_these_the_way_this_file_assumes():
    """Catch the generator changing under the pairs reasoned about above.

    ``tools/generate_pilot_dataset.py`` cannot be imported from here — it does a
    bare ``from pilot_dataset_plan import ...`` and so needs ``tools/`` on
    ``sys.path``, which pytest does not put there — so the two literals this
    file restates are checked against the source text instead of guessed at.
    """
    generator = Path(__file__).resolve().parents[2] / "tools" / "generate_pilot_dataset.py"
    source = generator.read_text(encoding="utf-8")

    assert 'f"Synthetic pilot {event.category.lower()} session."' in source, (
        "the Speaker Request description this file builds its pairs from has moved; "
        "update PILOT_DESCRIPTION_TEMPLATE"
    )
    assert re.search(r'"\s*,\s*"\.join\(person\.topics\)', source), (
        "the expertise_tags cell this file builds its pairs from has moved; update PILOT_TOPIC_JOIN"
    )
