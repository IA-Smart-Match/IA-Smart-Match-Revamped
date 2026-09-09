"""The twelve approved tag terms (G3 §6.2), as the vocabulary card S5 releases.

`smartmatch_domain.event_vocabulary` is a transcription of a human decision, so
these tests are transcription checks rather than behaviour checks: the risk
they cover is a term that drifted from `docs/decisions/g3-crawler-decision.md`
§6.2, not a resolver that stopped working (`test_events.py` already covers
`resolve_tag`).

One of them is worth naming for what it *deliberately* asserts:
:func:`test_the_deliberately_cut_candidates_quarantine` fixes the eight terms
§6.2 struck as quarantining rather than resolving, because §6.1 calls that
queue "evidence of which terms were actually needed" — a later reader finding
those values in the review queue is looking at the instrument working, and a
test asserting the intended behaviour is what keeps somebody from "fixing" it
by widening the vocabulary without the §6.3 owner.
"""

from __future__ import annotations

import pytest
from smartmatch_domain.event_vocabulary import (
    G3_VOCABULARY,
    TERM_CONCEPTS,
    VOCABULARY_VERSION,
)
from smartmatch_domain.events import (
    MappedTag,
    QuarantinedTag,
    matchable_tags,
    normalize_tag_value,
    resolve_tag,
)

#: Copied from `docs/decisions/g3-crawler-decision.md` §6.2's table, in its
#: order. Written out a second time rather than derived from the module under
#: test: a test that recomputed the list from the code could not notice the
#: code disagreeing with the artifact, which is the only failure this file
#: exists to catch.
APPROVED_TERMS = (
    "hackathon",
    "case competition",
    "guest lecture",
    "career panel",
    "workshop",
    "conference",
    "capstone showcase",
    "keynote",
    "panelist",
    "judge",
    "mentor",
    "guest lecturer",
)

#: §6.2's "Deliberately cut (8)" list, verbatim.
CUT_CANDIDATES = (
    "datathon",
    "symposium",
    "industry night",
    "networking mixer",
    "info session",
    "workshop facilitator",
    "moderator",
    "sponsor contact",
)


def test_the_vocabulary_holds_exactly_the_twelve_approved_terms():
    assert G3_VOCABULARY.terms == frozenset(APPROVED_TERMS)


def test_the_term_cap_is_adr_0012s_ten_to_twelve():
    """ADR-0012 caps the vocabulary at 10-12 terms; G3 §6.2 chose twelve."""
    assert len(G3_VOCABULARY.terms) == 12


def test_every_term_arrives_already_normalized():
    """§6.3: an executor editing an approved term would be inventing one.

    `TagVocabulary.__post_init__` already refuses a term that is not in its own
    normalized form, so this is a second statement of the same rule at the one
    place a reader will look for it — and it names the terms individually, so a
    failure says which one drifted rather than only that construction failed.
    """
    for term in APPROVED_TERMS:
        assert normalize_tag_value(term) == term


def test_the_concept_table_covers_every_term_and_nothing_else():
    assert set(TERM_CONCEPTS) == set(APPROVED_TERMS)
    assert set(TERM_CONCEPTS.values()) == {"type", "role"}


def test_the_concept_table_is_read_only():
    """`TERM_CONCEPTS` is a `MappingProxyType`, not a dict a caller can grow."""
    with pytest.raises(TypeError):
        TERM_CONCEPTS["datathon"] = "type"  # type: ignore[index]


def test_the_version_is_stamped_onto_every_resolution():
    """Both arms carry it, so a stored tag stays interpretable after a revision."""
    mapped = resolve_tag("Hackathon", G3_VOCABULARY)
    quarantined = resolve_tag("Datathon", G3_VOCABULARY)

    assert mapped.vocabulary_version == VOCABULARY_VERSION
    assert quarantined.vocabulary_version == VOCABULARY_VERSION


@pytest.mark.parametrize("term", APPROVED_TERMS)
def test_each_approved_term_resolves(term: str):
    resolution = resolve_tag(term, G3_VOCABULARY)
    assert isinstance(resolution, MappedTag)
    assert resolution.term == term


@pytest.mark.parametrize("term", APPROVED_TERMS)
def test_each_approved_term_resolves_from_the_casing_a_page_would_carry(term: str):
    """`resolve_tag` folds before comparing, so "Career Panel" is the same term."""
    resolution = resolve_tag(term.title(), G3_VOCABULARY)
    assert isinstance(resolution, MappedTag)
    assert resolution.term == term


@pytest.mark.parametrize("candidate", CUT_CANDIDATES)
def test_the_deliberately_cut_candidates_quarantine(candidate: str):
    """§6.2: "Each will quarantine rather than resolve — which is the intended
    measurement." Asserted as the intended behaviour, so nobody closes the
    resulting review-queue volume by widening the vocabulary without §6.3's
    named owner."""
    resolution = resolve_tag(candidate, G3_VOCABULARY)
    assert isinstance(resolution, QuarantinedTag)
    assert resolution.raw_value == candidate


def test_a_quarantined_value_never_reaches_the_matchable_set():
    """ADR-0012: quarantined values are "never rendered and never matched on"."""
    resolutions = [
        resolve_tag("Hackathon", G3_VOCABULARY),
        resolve_tag("Datathon", G3_VOCABULARY),
        resolve_tag("Networking Mixer", G3_VOCABULARY),
    ]

    assert [tag.term for tag in matchable_tags(resolutions)] == ["hackathon"]


def test_guest_lecture_and_guest_lecturer_are_both_present_and_distinct():
    """§6.1's accepted consequence of one combined namespace, pinned.

    The pair sits undifferentiated in a single vocabulary, so `matchable_tags`
    returns a list a consumer cannot partition by concept. That is the recorded
    decision, not an oversight, and this test is where a reader finds it stated
    as behaviour rather than as prose.
    """
    assert {"guest lecture", "guest lecturer"} <= G3_VOCABULARY.terms
    assert TERM_CONCEPTS["guest lecture"] == "type"
    assert TERM_CONCEPTS["guest lecturer"] == "role"


# ---------------------------------------------------------------------------
# Separation from the CBA career taxonomies (CBA-TAXONOMY)
# ---------------------------------------------------------------------------
#
# `TERM_CONCEPTS` files five terms under the concept `"role"`, and customer §8
# calls its ten career disciplines "role categories". The two senses of the
# word are unrelated: a `"role"` term here is the *function a person performs
# at an event* (`panelist`, `judge`), while a CBA role category is the *career
# discipline a speaker works in* (`Finance`, `Human Resources`). ADR-0012
# governs the first, `smartmatch_domain.cba_role_categories` the second, and
# `docs/plans/2026-09-05-cba-pivot-waves.md` states the rule these tests
# enforce: "ADR-0012's event type/speaker-function tag vocabulary is not the
# CBA career-role taxonomy. They remain separate versioned vocabularies."
#
# The failure mode this guards is cheap to commit and expensive to undo:
# storing `Finance` as an event tag, or adding `panelist` to the career
# taxonomy, would make one column mean two things and quietly widen a closed
# vocabulary that §6.3's named owner controls.


def test_no_career_role_category_is_an_approved_event_tag_term():
    from smartmatch_domain.cba_role_categories import (
        ROLE_CATEGORY_CODES,
        ROLE_CATEGORY_NAMES,
    )

    folded_names = {normalize_tag_value(name) for name in ROLE_CATEGORY_NAMES}
    folded_codes = {normalize_tag_value(code) for code in ROLE_CATEGORY_CODES}

    assert folded_names.isdisjoint(G3_VOCABULARY.terms)
    assert folded_codes.isdisjoint(G3_VOCABULARY.terms)


def test_no_naics_sector_is_an_approved_event_tag_term():
    from smartmatch_domain.naics_sectors import SECTOR_CODES, SECTOR_NAMES

    folded = {normalize_tag_value(value) for value in SECTOR_NAMES + SECTOR_CODES}

    assert folded.isdisjoint(G3_VOCABULARY.terms)


def test_a_career_role_category_quarantines_when_offered_as_an_event_tag():
    from smartmatch_domain.cba_role_categories import ROLE_CATEGORY_NAMES

    for name in ROLE_CATEGORY_NAMES:
        resolution = resolve_tag(name, G3_VOCABULARY)
        assert isinstance(resolution, QuarantinedTag), name


def test_an_event_tag_term_quarantines_when_offered_as_a_career_role_category():
    from smartmatch_domain.cba_role_categories import (
        QuarantinedRoleCategory,
        resolve_role_category,
    )

    for term in APPROVED_TERMS:
        resolution = resolve_role_category(term)
        assert isinstance(resolution, QuarantinedRoleCategory), term


def test_an_event_tag_term_quarantines_when_offered_as_an_industry_sector():
    from smartmatch_domain.naics_sectors import QuarantinedSector, resolve_sector

    for term in APPROVED_TERMS:
        resolution = resolve_sector(term)
        assert isinstance(resolution, QuarantinedSector), term


def test_the_three_vocabularies_carry_three_distinct_versions():
    """Each stamps its own token, so a stored value names the decision it was
    evaluated against and no consumer can read one version as another."""
    from smartmatch_domain.cba_role_categories import CBA_ROLE_TAXONOMY_VERSION
    from smartmatch_domain.naics_sectors import NAICS_TAXONOMY_VERSION

    versions = {VOCABULARY_VERSION, CBA_ROLE_TAXONOMY_VERSION, NAICS_TAXONOMY_VERSION}
    assert len(versions) == 3


def test_a_classified_career_role_is_not_a_mapped_event_tag():
    """Separation held by type, not by discipline: neither resolution type is
    substitutable for the other, so a career classification cannot reach
    `matchable_tags` and an event tag cannot reach a career-role column."""
    from smartmatch_domain.cba_role_categories import (
        ClassifiedRoleCategory,
        resolve_role_category,
    )

    career = resolve_role_category("finance")
    tag = resolve_tag("panelist", G3_VOCABULARY)

    assert not isinstance(career, MappedTag)
    assert not isinstance(tag, ClassifiedRoleCategory)
    assert matchable_tags([career]) == ()  # type: ignore[list-item]


def test_the_event_role_concept_and_the_career_role_taxonomy_share_only_a_word():
    """`TERM_CONCEPTS`'s `"role"` label means speaker *function at an event*.
    Pinned so a later reader does not repurpose the label as a join key to the
    career taxonomy."""
    from smartmatch_domain.cba_role_categories import ROLE_CATEGORY_NAMES

    event_function_terms = {term for term, concept in TERM_CONCEPTS.items() if concept == "role"}
    career_names = {normalize_tag_value(name) for name in ROLE_CATEGORY_NAMES}

    assert event_function_terms == {
        "keynote",
        "panelist",
        "judge",
        "mentor",
        "guest lecturer",
    }
    assert event_function_terms.isdisjoint(career_names)
