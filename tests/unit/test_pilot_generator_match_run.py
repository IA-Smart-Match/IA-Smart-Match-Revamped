"""What the pilot generator must submit for the Connector demo to run at all.

``tools/generate_pilot_dataset.py`` exists so a stakeholder can open the
appliance and see a Speaker Connector produce a match. Until this file's
assertions passed, it could not: :func:`generate_pilot_dataset.match_run_body`
built the **pre-CBA** shape — a string ``event_need_id``, ``required_topics``,
and candidates carrying their own ``expertise_topics`` — and
``POST /v1/units/{unit_id}/match-runs`` has taken ``speaker_request_id`` and
``candidate_subject_ids`` since OQ-CBA-031 stripped evidence out of the request
body. The generated dataset's central demo path answered ``422`` before any
scoring was reached.

Everything here is asserted against the **real** models the API validates with
— :class:`smartmatch_api.routers.match_runs.MatchRunRequest` and
:class:`smartmatch_api.routers.speaker_requests.SpeakerRequestCreate` — rather
than against a restatement of their fields. A test that pinned a hand-copied
shape would go on passing through exactly the contract change that broke the
generator in the first place.

What this file cannot assert, stated rather than implied
--------------------------------------------------------
A ``202`` and a job reaching a terminal state need a running appliance, a
migrated database and the scheduler sidecar. Those are verified by running the
generator against the compose stack, and the result is reported in the PR. What
is asserted here is the thing that decides between ``202`` and ``422``: whether
the body the generator builds satisfies the model the route validates with.

The shortlist is asserted honestly and pessimistically
------------------------------------------------------
:func:`test_how_many_reviewed_candidates_can_actually_score` counts how many of
the generated candidate pool the §9 Topic factor can score at all. The answer is
small and it is **not** a defect in this change: OQ-CBA-061 says the fixture
topic provider holds no recordings, so a speaker with ``topic_text`` scores
``unknown``, their composite is ``None`` (ADR-0011 rule 1) and they leave the
shortlist — while a speaker who filled nothing in scores the §9 policy neutral
and stays. This file pins that number so the demo's real shape is a measured
fact rather than an impression, and so the day OQ-CBA-061 is answered the number
changes loudly rather than quietly.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from types import ModuleType

import pytest
from smartmatch_api.routers.match_runs import MAX_CANDIDATES, MatchRunRequest
from smartmatch_api.routers.speaker_requests import SpeakerRequestCreate
from smartmatch_domain.cba_role_categories import ROLE_CATEGORY_CODES
from smartmatch_domain.explanation import MAX_SHORTLIST_SIZE, MIN_SHORTLIST_SIZE
from smartmatch_domain.factors.cba_semantic_topic import (
    SpeakerTopicEvidence,
    TopicEvidenceState,
    score_cba_semantic_topic,
)
from smartmatch_domain.naics_sectors import SECTOR_CODES
from smartmatch_providers.base import Edition
from smartmatch_providers.topic_semantics import build_semantic_topic_provider

from tools import pilot_dataset_plan as plan


def _generator() -> ModuleType:
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


def _planned(count: int) -> tuple[plan.ProfessionalPlan, ...]:
    """A planned roster at the default seed, so every count below is reproducible."""
    return plan.build_professionals(count, seed=plan.DEFAULT_SEED)


def _match_roster() -> tuple[plan.ProfessionalPlan, ...]:
    """The slice the generator actually submits, taken the way the generator takes it."""
    generator = _generator()
    return generator.match_roster(_planned(generator.MATCH_ROSTER_ROWS * 4))


# ---------------------------------------------------------------------------
# The match-run body: the shape the CBA route actually validates
# ---------------------------------------------------------------------------


def test_the_match_run_body_validates_against_the_real_request_model() -> None:
    """The defect, inverted: the generated body is one ``MatchRunRequest`` accepts.

    ``model_validate`` here is the same call FastAPI makes before the route body
    runs, so a body that survives it is a body that reaches the route rather
    than one that answers ``422``.
    """
    generator = _generator()
    request_id = uuid.uuid4()
    candidates = tuple(uuid.uuid4() for _ in range(5))

    body = generator.match_run_body(
        speaker_request_id=request_id,
        candidate_subject_ids=candidates,
        seed=plan.DEFAULT_SEED,
    )

    validated = MatchRunRequest.model_validate(body)
    assert validated.speaker_request_id == request_id
    assert validated.candidate_subject_ids == list(candidates)


def test_the_match_run_body_carries_no_evidence_at_all() -> None:
    """OQ-CBA-031, asserted as an absence rather than described in a comment.

    The server assembles every scored fact from this tenant's own rows. A body
    that could state a speaker's expertise is a body that can decide its own
    shortlist, so the generator must not reintroduce one — including by
    accident, through a field name the model happens to ignore.
    """
    generator = _generator()

    body = generator.match_run_body(
        speaker_request_id=uuid.uuid4(),
        candidate_subject_ids=(uuid.uuid4(),),
        seed=plan.DEFAULT_SEED,
    )

    assert set(body) <= set(MatchRunRequest.model_fields), (
        "the generated body carries keys the request model does not declare: "
        f"{sorted(set(body) - set(MatchRunRequest.model_fields))}"
    )
    for banned in (
        "event_need_id",
        "required_topics",
        "preferred_topics",
        "event_location",
        "candidates",
        "expertise_topics",
    ):
        assert banned not in body, (
            f"{banned!r} is pre-CBA request evidence; OQ-CBA-031 removed it and the "
            "server reads the equivalent fact from speaker_profile"
        )


def test_the_portfolio_size_stays_inside_the_ratified_presentation_rule() -> None:
    """G1 says a shortlist holds 2-3 speakers, and the generator must ask for one."""
    generator = _generator()

    body = generator.match_run_body(
        speaker_request_id=uuid.uuid4(),
        candidate_subject_ids=(uuid.uuid4(),),
        seed=plan.DEFAULT_SEED,
    )

    assert MIN_SHORTLIST_SIZE <= body["portfolio_size"] <= MAX_SHORTLIST_SIZE


def test_the_request_model_does_not_itself_enforce_the_candidate_cap() -> None:
    """Why the generator has to carry the check: ``maxItems`` here validates nothing.

    ``MatchRunRequest.candidate_subject_ids`` declares the cap in
    ``json_schema_extra``, which documents it for a schema reader and is not a
    constraint. The route enforces it separately with a ``400``. Pinned so the
    next reader does not delete the generator's own guard as redundant — and so
    that if the model ever *does* gain the constraint, this fails and says the
    guard can go.
    """
    generator = _generator()

    MatchRunRequest.model_validate(
        generator.match_run_body(
            speaker_request_id=uuid.uuid4(),
            candidate_subject_ids=tuple(uuid.uuid4() for _ in range(MAX_CANDIDATES)),
            seed=plan.DEFAULT_SEED,
        )
    )


def test_a_candidate_pool_larger_than_the_cap_is_refused_rather_than_silently_cut() -> None:
    """The generator refuses at the boundary rather than truncating or discovering a 400.

    Truncating would hand the run a pool quietly missing people; discovering it
    over HTTP would mean the whole dataset had already been written before
    anything said so.
    """
    generator = _generator()

    with pytest.raises(generator.GeneratorError):
        generator.match_run_body(
            speaker_request_id=uuid.uuid4(),
            candidate_subject_ids=tuple(uuid.uuid4() for _ in range(MAX_CANDIDATES + 1)),
            seed=plan.DEFAULT_SEED,
        )


def test_the_roster_the_generator_submits_fits_inside_the_candidate_cap() -> None:
    """Stated as an assertion rather than trusted to arithmetic kept in two files."""
    assert len(_match_roster()) <= MAX_CANDIDATES


# ---------------------------------------------------------------------------
# The Speaker Request a match run cannot exist without
# ---------------------------------------------------------------------------


def test_the_speaker_request_body_validates_against_the_real_create_model() -> None:
    """A match run names a *filed* request; the generator has to file one.

    Virtual on purpose: customer §11 removes Proximity from the virtual model,
    and the generated roster carries no postal codes, so a physical request
    would produce a pool nobody could locate rather than a shortlist.
    """
    generator = _generator()

    body = generator.speaker_request_body(_match_roster(), seed=plan.DEFAULT_SEED)
    validated = SpeakerRequestCreate.model_validate(body)

    assert validated.is_virtual is True
    assert validated.location_city is None
    assert validated.location_postal_code is None
    assert validated.description, "a request with no description gives §9 nothing to compare"
    assert set(validated.industry_codes) <= set(SECTOR_CODES)
    assert set(validated.role_codes) <= set(ROLE_CATEGORY_CODES)


def test_the_speaker_request_targets_codes_the_generated_roster_actually_holds() -> None:
    """A request whose targets nobody on the roster holds scores every candidate zero.

    That is a defensible number and a useless demo. The targets are drawn from
    the plan's own most common codes, so the sector and role factors separate
    the pool instead of flattening it.
    """
    generator = _generator()
    roster = _match_roster()

    body = generator.speaker_request_body(roster, seed=plan.DEFAULT_SEED)

    assert set(body["industry_codes"]) & {person.industry_code for person in roster}
    assert set(body["role_codes"]) & {person.role_code for person in roster}


# ---------------------------------------------------------------------------
# The plan's classification evidence, without which nobody enters the pool
# ---------------------------------------------------------------------------


def test_every_planned_classification_code_is_one_the_released_taxonomies_name() -> None:
    """An unreleased code is dropped at import and the speaker never becomes eligible."""
    for person in _planned(120):
        assert person.industry_code is None or person.industry_code in SECTOR_CODES
        assert person.role_code is None or person.role_code in ROLE_CATEGORY_CODES


def test_some_planned_professionals_carry_no_classification_at_all() -> None:
    """The unclassified state is real (customer §19) and must stay visible.

    A plan that classified everybody would hide
    ``industry_classification_missing`` — one of the reasons a run reports a
    candidate as excluded rather than ranking them last.
    """
    roster = _planned(120)
    unclassified = [
        person for person in roster if person.industry_code is None or person.role_code is None
    ]

    assert unclassified, "no planned professional is left unclassified"
    assert len(unclassified) < len(roster) // 2


def test_the_import_row_states_the_classification_columns_the_contract_declares() -> None:
    """``primary_industry_code`` / ``primary_role_code``, spelled the contract's way.

    These are the cells ``pipeline_provisioning._stated_code`` reads on an
    accept; a different spelling would leave every accepted contact
    unclassified and therefore out of every pool.
    """
    generator = _generator()
    person = next(
        candidate
        for candidate in _planned(60)
        if candidate.industry_code is not None and candidate.role_code is not None
    )

    (row,) = generator.professionals_rows([person])

    assert row["primary_industry_code"] == person.industry_code
    assert row["primary_role_code"] == person.role_code


def test_an_unclassified_professional_contributes_no_classification_cell() -> None:
    """An absent column is an absent record; a blank one is a record saying nothing."""
    generator = _generator()
    person = next(candidate for candidate in _planned(200) if candidate.industry_code is None)

    (row,) = generator.professionals_rows([person])

    assert "primary_industry_code" not in row


# ---------------------------------------------------------------------------
# The §19 review step, and who is left unreviewed on purpose
# ---------------------------------------------------------------------------


def test_the_generator_reviews_most_of_the_roster_and_deliberately_leaves_some() -> None:
    """Both §19 states have to be in the dataset for the demo to show either.

    A reviewed contact is match-eligible; an unreviewed one is reported as
    ``industry_classification_awaiting_review`` and is absent from the pool
    rather than ranked last in it. A generator that reviewed everybody would
    make the second state unreachable from generated data.
    """
    generator = _generator()
    decisions = [generator.reviews_classification(index) for index in range(40)]

    assert any(decisions), "nobody is reviewed, so nobody can ever be scored"
    assert not all(decisions), "everybody is reviewed, so the excluded-with-reason state is gone"
    assert sum(decisions) > len(decisions) // 2


def test_the_review_decision_is_a_function_of_the_index_and_nothing_else() -> None:
    """Determinism: the same roster reviews the same people on every run."""
    generator = _generator()

    assert [generator.reviews_classification(index) for index in range(25)] == [
        generator.reviews_classification(index) for index in range(25)
    ]


# ---------------------------------------------------------------------------
# What a stakeholder will actually see: the shortlist, counted
# ---------------------------------------------------------------------------


def _topic_state(topic_text: str | None, description: str) -> TopicEvidenceState:
    """The §9 factor's state for one speaker against the filed request's text."""
    return score_cba_semantic_topic(
        description,
        SpeakerTopicEvidence.from_profile(topic_text=topic_text),
        build_semantic_topic_provider(Edition.DEV),
    ).state


def _scorable_and_unscorable() -> tuple[list[plan.ProfessionalPlan], list[plan.ProfessionalPlan]]:
    """The reviewed roster split by whether the §9 factor can score them at all."""
    generator = _generator()
    roster = _match_roster()
    description = generator.speaker_request_body(roster, seed=plan.DEFAULT_SEED)["description"]

    reviewed = [
        person
        for index, person in enumerate(roster)
        if generator.reviews_classification(index)
        and person.industry_code is not None
        and person.role_code is not None
    ]
    scorable = [
        person
        for person in reviewed
        if _topic_state(None if person.topics is None else ", ".join(person.topics), description)
        is not TopicEvidenceState.UNKNOWN
    ]
    unscorable = [person for person in reviewed if person not in scorable]
    return scorable, unscorable


def test_how_many_reviewed_candidates_can_actually_score() -> None:
    """The honest shortlist count, pinned — OQ-CBA-061, and not this change's to fix.

    Of the generator's reviewed roster, only the professionals carrying **no**
    expertise record score at all: everyone else has ``topic_text``, the fixture
    topic provider holds no recording for it, the §9 factor is ``unknown`` and
    ADR-0011 rule 1 makes their composite ``None``. They are reported as
    unscorable, which is correct, and they are not shortlistable.

    This asserts there are still enough scorable candidates to fill a G1
    shortlist, and pins how thin that margin is.
    """
    scorable, unscorable = _scorable_and_unscorable()

    assert len(scorable) >= MAX_SHORTLIST_SIZE, (
        f"only {len(scorable)} reviewed candidates can be scored at all, which is fewer "
        f"than the {MAX_SHORTLIST_SIZE} a G1 shortlist holds; the generated demo would "
        "open on an under-filled shortlist"
    )
    assert unscorable, (
        "every reviewed candidate is scorable, which would mean OQ-CBA-061 has been "
        "answered or worked around; if it was answered, update this file rather than "
        "deleting the assertion"
    )
    assert len(unscorable) > len(scorable), (
        "the pilot's documented speakers are supposed to outnumber its silent ones; "
        f"got {len(unscorable)} unscorable against {len(scorable)} scorable"
    )


def test_a_candidate_with_expertise_text_is_the_one_that_drops_out() -> None:
    """OQ-CBA-061 restated on this generator's own data, so the cost is legible.

    Not worked around here — stripping the seed's topic text to make the demo
    look fuller is one of three candidate answers the CBA product owner holds,
    and picking one of them inside a generator would be answering an open
    question by writing code.
    """
    generator = _generator()
    roster = _match_roster()
    description = generator.speaker_request_body(roster, seed=plan.DEFAULT_SEED)["description"]

    documented = next(person for person in roster if person.topics is not None)
    silent = next(person for person in roster if person.topics is None)

    assert _topic_state(", ".join(documented.topics or ()), description) is (
        TopicEvidenceState.UNKNOWN
    )
    assert _topic_state(None, description) is TopicEvidenceState.POLICY_NEUTRAL
    assert silent.topics is None
