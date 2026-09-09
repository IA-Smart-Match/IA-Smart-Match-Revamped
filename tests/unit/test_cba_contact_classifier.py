"""The §19 contact classifier: what it proposes, what it refuses, and what it is.

Customer §19 assigns an initial Industry and Role classification from a
contact's company and title, and then requires a Speaker Connector to review
them. These tests hold the classifier to the half of that flow it owns, and the
assertions are mostly about what it *declines* to do — because the failure this
card exists to prevent is a plausible-looking value nobody chose.

No database and no network. The classifier is pure, and one test below removes
the ability to open a socket to prove the second half of that.
"""

from __future__ import annotations

import datetime as dt
import inspect
import uuid

import pytest
from smartmatch_domain.cba_classification import (
    CLASSIFICATION_SOURCE_HUMAN,
    CLASSIFICATION_SOURCE_INFERRED,
    UNDETERMINED_NO_EVIDENCE,
    UNDETERMINED_UNRECOGNIZED,
    ContactClassifier,
    ProposedClassification,
    UndeterminedClassification,
    human_classification,
    inferred_classification,
    is_match_eligible,
    match_ineligibility_reason,
)
from smartmatch_domain.cba_role_categories import CBA_ROLE_TAXONOMY_VERSION
from smartmatch_domain.naics_sectors import NAICS_TAXONOMY_VERSION, UnknownNaicsSector
from smartmatch_providers.base import Edition, ProviderConfigurationError
from smartmatch_providers.cba_classification import (
    FIXTURE_CLASSIFIER_NAME,
    FixtureContactClassifier,
    build_contact_classifier,
)

#: No ``pytestmark``. ``--strict-markers`` is on and the project registers only
#: ``golden``, ``integration`` and ``e2e``; an unmarked test under ``tests/unit``
#: is the default suite, which is what this is.

#: A fixed instant. Every assertion about provenance needs one and none of them
#: cares which, so it is stated once rather than read from the clock — a test
#: that reads ``now()`` asserts a slightly different thing on every run.
AT = dt.datetime(2026, 9, 6, 14, 3, tzinfo=dt.UTC)

#: A Connector. An opaque id: nothing under test resolves it, and giving it a
#: name would suggest something does.
ACTOR = uuid.UUID("00000000-0000-4000-8000-00000000c0a1")


def _classifier() -> FixtureContactClassifier:
    """The fixture as its builder returns it, so no test constructs one directly."""
    return build_contact_classifier(Edition.CLASSROOM)


# ---------------------------------------------------------------------------
# It satisfies the protocol, and says what it is
# ---------------------------------------------------------------------------


def test_the_fixture_satisfies_the_contact_classifier_protocol():
    """Structural conformance, asserted rather than assumed.

    ``ContactClassifier`` is what the persistence and API layers depend on. A
    fixture that drifted from it would fail at the call site with an
    ``AttributeError`` in whichever test happened to exercise that branch, which
    is a worse place to learn it than here.
    """
    classifier: ContactClassifier = _classifier()

    assert classifier.name == FIXTURE_CLASSIFIER_NAME
    assert callable(classifier.propose)


def test_the_fixture_does_not_call_itself_a_model():
    """A deterministic lookup that claimed to be a model would be a permanent lie.

    The discipline ``FixtureSemanticTopicProvider.is_semantic_model`` states:
    long after anybody remembers this classifier was a dictionary and a taxonomy
    lookup, the name is what a reader of the data will believe.
    """
    assert _classifier().is_model is False


def test_the_fixture_name_is_visibly_synthetic():
    """Prefixed ``fixture-``, so a synthetic proposal is identifiable in a log."""
    assert FIXTURE_CLASSIFIER_NAME.startswith("fixture-")


def test_the_classifier_opens_no_socket(monkeypatch: pytest.MonkeyPatch):
    """No live lookup — asserted by removing the ability to make one.

    A classifier that quietly grew a network call would pass every behavioural
    test in this file and fail this one, which is the only reason it exists.
    Customer §20 puts "finding new speakers on the internet" and "scraping other
    external sources" out of scope outright; this is that boundary, enforced.
    """
    import socket

    def _refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the fixture contact classifier must not touch the network")

    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)

    classifier = _classifier()
    classifier.record_company("Northwind Mutual", sector_code="52")

    proposal = classifier.propose(company="Northwind Mutual", title=None)

    assert isinstance(proposal.industry, ProposedClassification)
    assert proposal.industry.code == "52"


# ---------------------------------------------------------------------------
# What it proposes
# ---------------------------------------------------------------------------


def test_a_recorded_company_yields_an_industry_proposal_stamped_inferred():
    """The proposal carries the taxonomy version and the source, not just a code.

    ``source`` is asserted here rather than left to the persistence layer
    because it is the whole distinction §19's review step turns on, and a
    proposal that arrived without one would be indistinguishable from a
    Connector's own choice by the time it reached a column.
    """
    classifier = _classifier()
    classifier.record_company("Northwind Mutual", sector_code="52")

    industry = classifier.propose(company="Northwind Mutual", title=None).industry

    assert isinstance(industry, ProposedClassification)
    assert industry.code == "52"
    assert industry.source == CLASSIFICATION_SOURCE_INFERRED
    assert industry.taxonomy_version == NAICS_TAXONOMY_VERSION
    assert industry.classifier == FIXTURE_CLASSIFIER_NAME


def test_a_recorded_title_yields_a_role_proposal_stamped_inferred():
    classifier = _classifier()
    classifier.record_title("VP of Financial Planning", role_code="finance")

    role = classifier.propose(company=None, title="VP of Financial Planning").role

    assert isinstance(role, ProposedClassification)
    assert role.code == "finance"
    assert role.source == CLASSIFICATION_SOURCE_INFERRED
    assert role.taxonomy_version == CBA_ROLE_TAXONOMY_VERSION


def test_a_proposal_carries_the_text_it_was_drawn_from_unnormalized():
    """A reviewer needs to see what the sheet actually said.

    "This is wrong" and "this is wrong *because the column said Northwind
    Mutual*" are different pieces of information, and only the second lets a
    Connector fix the import rather than the row.
    """
    classifier = _classifier()
    classifier.record_company("Northwind Mutual", sector_code="52")

    industry = classifier.propose(company="  NORTHWIND   Mutual ", title=None).industry

    assert isinstance(industry, ProposedClassification)
    assert industry.evidence == "  NORTHWIND   Mutual "


def test_lookup_is_case_and_whitespace_insensitive_but_nothing_more():
    """Key normalization, not similarity.

    Folding decides *which recording to replay* and never what a code should be
    — the distinction ``FixtureSemanticTopicProvider._canonical`` draws. A near
    miss is a miss.
    """
    classifier = _classifier()
    classifier.record_company("Northwind Mutual", sector_code="52")

    assert isinstance(
        classifier.propose(company="northwind   MUTUAL", title=None).industry,
        ProposedClassification,
    )
    assert isinstance(
        classifier.propose(company="Northwind Mutual Holdings", title=None).industry,
        UndeterminedClassification,
    )


def test_text_that_is_itself_a_taxonomy_value_resolves_without_a_recording():
    """Recognition, not inference.

    A spreadsheet whose industry column already holds §7's own sector name is
    not being *classified* — it is being read. The taxonomy's own
    ``resolve_sector`` does exactly that and quarantines everything else, so
    admitting it here adds no judgment the taxonomy has not already released.
    """
    classifier = _classifier()

    industry = classifier.propose(company="Finance and Insurance", title=None).industry
    role = classifier.propose(company=None, title="Marketing").role

    assert isinstance(industry, ProposedClassification)
    assert industry.code == "52"
    assert isinstance(role, ProposedClassification)
    assert role.code == "marketing"


def test_a_recording_beats_the_taxonomy_reading_of_the_same_text():
    """Explicit beats derived, and the precedence is stated rather than incidental.

    A deployment that records ``"Information"`` as something other than §7's
    sector 51 has said something specific about its own data; the taxonomy
    reading is the fallback, so the recording must win. The reverse order would
    make a recording silently ineffective for exactly the values most likely to
    collide.
    """
    classifier = _classifier()
    classifier.record_company("Information", sector_code="54")

    industry = classifier.propose(company="Information", title=None).industry

    assert isinstance(industry, ProposedClassification)
    assert industry.code == "54"


def test_both_axes_are_always_reported():
    """A classifier that returned only what it resolved would hide a question.

    "The role was not classified" and "the role axis was never considered" must
    not be the same absence, because only the first is something a Connector can
    act on.
    """
    classifier = _classifier()
    classifier.record_company("Northwind Mutual", sector_code="52")

    proposal = classifier.propose(company="Northwind Mutual", title=None)

    assert isinstance(proposal.industry, ProposedClassification)
    assert isinstance(proposal.role, UndeterminedClassification)


# ---------------------------------------------------------------------------
# What it refuses
# ---------------------------------------------------------------------------


def test_unrecognized_company_text_is_undetermined_rather_than_a_guess():
    """The central non-negotiable: no confident value to avoid an empty field.

    ``UndeterminedClassification`` has no ``code`` attribute, so this is
    enforced by the type rather than by the caller remembering to check a
    confidence score — of which there is none anywhere in this module, because a
    number nobody has calibrated is not evidence.
    """
    classifier = _classifier()

    industry = classifier.propose(company="Reyes Analytics", title=None).industry

    assert isinstance(industry, UndeterminedClassification)
    assert industry.reason == UNDETERMINED_UNRECOGNIZED
    assert industry.evidence == "Reyes Analytics"
    assert not hasattr(industry, "code")


def test_absent_text_is_undetermined_for_a_different_reason_than_unrecognized_text():
    """Two reasons, because they call for two different human acts.

    "We do not know where this person works" asks a Connector to find out; "we
    do not know which sector Reyes Analytics is" asks them to decide. One reason
    token would send both to the same screen.
    """
    classifier = _classifier()

    proposal = classifier.propose(company=None, title=None)

    assert isinstance(proposal.industry, UndeterminedClassification)
    assert proposal.industry.reason == UNDETERMINED_NO_EVIDENCE
    assert proposal.industry.evidence is None
    assert isinstance(proposal.role, UndeterminedClassification)
    assert proposal.role.reason == UNDETERMINED_NO_EVIDENCE


def test_blank_text_is_treated_as_absent_rather_than_as_something_to_review():
    """An empty cell is missing data, not a value awaiting classification.

    ``resolve_sector`` refuses a blank for this reason, and filing one into a
    review queue would give a Connector a row with nothing on it to decide about.
    """
    classifier = _classifier()

    industry = classifier.propose(company="   ", title="\t\n").industry

    assert isinstance(industry, UndeterminedClassification)
    assert industry.reason == UNDETERMINED_NO_EVIDENCE


def test_the_classifier_never_raises_for_text_it_cannot_read():
    """An unclassifiable contact is an outcome, not an import failure.

    §19 imports a contact and classifies it after, so a row the classifier
    cannot read must still be storable. Raising here would let one strange
    company name fail a whole import.
    """
    classifier = _classifier()

    proposal = classifier.propose(company="!!!", title="~~~")

    assert isinstance(proposal.industry, UndeterminedClassification)
    assert isinstance(proposal.role, UndeterminedClassification)
    assert proposal.proposes_anything is False


def test_a_recording_outside_the_closed_taxonomy_is_refused_at_record_time():
    """The failure names the recording, not a later proposal.

    A fixture that accepted ``"banking"`` as a sector code would emit it happily
    and fail at the database ``CHECK`` hours later, in whichever import happened
    to touch that company.
    """
    classifier = _classifier()

    with pytest.raises(UnknownNaicsSector):
        classifier.record_company("Northwind Mutual", sector_code="banking")


def test_the_classifier_is_not_given_an_email_address_to_look_at():
    """``propose`` takes company and title, and §19 names exactly those two.

    A classifier that could see an email address is one somebody could later be
    tempted to have look one up. Asserted against the signature rather than
    trusted to the docstring.
    """
    parameters = inspect.signature(FixtureContactClassifier.propose).parameters

    assert set(parameters) == {"self", "company", "title"}


# ---------------------------------------------------------------------------
# Provenance: a proposal cannot be dressed as a judgment
# ---------------------------------------------------------------------------


def test_an_inferred_assignment_has_no_actor_and_no_way_to_be_given_one():
    """The card's non-negotiable, made unwritable rather than merely documented.

    ``inferred_classification`` offers no parameter through which a person could
    be attached to a machine's reading, so no code path can produce a row
    asserting a review that did not happen. Migration ``0028``'s middle arm
    refuses the same row at the database, so this is belt and braces on purpose.
    """
    classifier = _classifier()
    classifier.record_company("Northwind Mutual", sector_code="52")
    industry = classifier.propose(company="Northwind Mutual", title=None).industry
    assert isinstance(industry, ProposedClassification)

    assignment = inferred_classification(industry, at=AT)

    assert assignment.source == CLASSIFICATION_SOURCE_INFERRED
    assert assignment.actor_id is None
    assert assignment.assigned_at == AT
    assert "actor_id" not in inspect.signature(inferred_classification).parameters


def test_a_human_assignment_will_not_be_built_without_an_actor():
    """A human decided this, and somebody must be able to be asked which human.

    Required rather than optional, so the unattributed form is not the one a
    hurried caller reaches for.
    """
    assignment = human_classification("52", axis="industry", actor_id=ACTOR, at=AT)

    assert assignment.source == CLASSIFICATION_SOURCE_HUMAN
    assert assignment.actor_id == ACTOR
    assert assignment.taxonomy_version == NAICS_TAXONOMY_VERSION

    with pytest.raises(TypeError):
        human_classification("52", axis="industry", at=AT)  # type: ignore[call-arg]


def test_a_human_assignment_rechecks_the_code_against_its_taxonomy():
    """A bad code under a provenance claiming somebody vouched for it is the worst row.

    Every caller has already validated; the check is cheap and the failure it
    prevents is not.
    """
    with pytest.raises(UnknownNaicsSector):
        human_classification("banking", axis="industry", actor_id=ACTOR, at=AT)


def test_a_proposal_cannot_be_constructed_claiming_a_human_source():
    """There is no constructor argument that turns a proposal into a judgment."""
    with pytest.raises(ValueError, match="human_classification"):
        ProposedClassification(
            code="52",
            taxonomy_version=NAICS_TAXONOMY_VERSION,
            evidence="Northwind Mutual",
            classifier=FIXTURE_CLASSIFIER_NAME,
            source=CLASSIFICATION_SOURCE_HUMAN,  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# The match-eligibility gate
# ---------------------------------------------------------------------------


def test_a_fully_reviewed_contact_is_match_eligible():
    """§19's last two steps, in order: reviewed, then available for matching."""
    assert is_match_eligible(
        primary_industry_code="52",
        industry_classification_source=CLASSIFICATION_SOURCE_HUMAN,
        primary_role_code="finance",
        role_classification_source=CLASSIFICATION_SOURCE_HUMAN,
    )


@pytest.mark.parametrize(
    ("industry_source", "role_source", "expected"),
    [
        (
            CLASSIFICATION_SOURCE_INFERRED,
            CLASSIFICATION_SOURCE_HUMAN,
            "industry_classification_awaiting_review",
        ),
        (
            CLASSIFICATION_SOURCE_HUMAN,
            CLASSIFICATION_SOURCE_INFERRED,
            "role_classification_awaiting_review",
        ),
        (
            CLASSIFICATION_SOURCE_INFERRED,
            CLASSIFICATION_SOURCE_INFERRED,
            "industry_classification_awaiting_review",
        ),
    ],
)
def test_an_unreviewed_axis_keeps_the_contact_out_of_matching(
    industry_source: str, role_source: str, expected: str
):
    """A proposal nobody has looked at must not silently enter matching.

    Both codes are present and both are plausible; the only thing wrong with the
    row is that §19's review step has not happened, which is precisely the
    condition a stored-code-only schema could not express.
    """
    reason = match_ineligibility_reason(
        primary_industry_code="52",
        industry_classification_source=industry_source,
        primary_role_code="finance",
        role_classification_source=role_source,
    )

    assert reason == expected
    assert not is_match_eligible(
        primary_industry_code="52",
        industry_classification_source=industry_source,
        primary_role_code="finance",
        role_classification_source=role_source,
    )


def test_a_missing_classification_is_reported_differently_from_an_unreviewed_one():
    """Four situations, not one greyed-out row.

    "We have no idea where they work" and "the classifier proposed Finance and
    nobody has checked" call for different actions, and a bare boolean would
    collapse them.
    """
    assert (
        match_ineligibility_reason(
            primary_industry_code=None,
            industry_classification_source=None,
            primary_role_code="finance",
            role_classification_source=CLASSIFICATION_SOURCE_HUMAN,
        )
        == "industry_classification_missing"
    )
    assert (
        match_ineligibility_reason(
            primary_industry_code="52",
            industry_classification_source=CLASSIFICATION_SOURCE_HUMAN,
            primary_role_code=None,
            role_classification_source=None,
        )
        == "role_classification_missing"
    )


def test_the_gate_fails_closed_on_a_row_with_no_provenance_read():
    """A caller that forgot to select the provenance columns gets ``False``.

    The opposite default would make a missing column look like an approval,
    which is the one way this gate could let an unreviewed speaker through
    without anybody writing a line of code that says so. The gate therefore
    matches a positive value — the source must *be* ``human`` — rather than
    excluding a negative one, since ``!= inferred`` is satisfied by ``None``.

    Reported under its own reason rather than as "awaiting review", because
    post-``0028`` the database cannot hold such a row: reaching it means the
    read was wrong, and sending an operator to a review screen would hide that.
    """
    assert (
        match_ineligibility_reason(
            primary_industry_code="52",
            industry_classification_source=None,
            primary_role_code="finance",
            role_classification_source=None,
        )
        == "industry_classification_provenance_unknown"
    )
    assert not is_match_eligible(
        primary_industry_code="52",
        industry_classification_source=None,
        primary_role_code="finance",
        role_classification_source=None,
    )


# ---------------------------------------------------------------------------
# No live model, under any edition
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("edition", list(Edition))
def test_every_edition_gets_the_fixture_classifier(edition: Edition):
    assert isinstance(build_contact_classifier(edition), FixtureContactClassifier)


@pytest.mark.parametrize("edition", list(Edition))
def test_a_live_classifier_is_refused_under_every_edition(edition: Edition):
    """The refusal is a property of what has been approved, not of where it runs.

    ``build_paid_extraction_provider`` and ``build_semantic_topic_provider``
    both take this shape for the same reason: expressing it as a deployment
    property would leave a production boot silently able to construct something
    nobody ratified.
    """
    with pytest.raises(ProviderConfigurationError, match="OQ-CBA-039"):
        build_contact_classifier(edition, use_fixture=False)


@pytest.mark.parametrize("edition", list(Edition))
def test_a_classifier_credential_fails_closed_under_every_edition(edition: Edition):
    """No environment of this repository should hold one; finding one is a defect."""
    with pytest.raises(ProviderConfigurationError):
        build_contact_classifier(edition, api_key="live-key")


def test_allowing_live_providers_still_does_not_reach_a_live_classifier():
    """``ALLOW_LIVE_PROVIDERS`` is a necessary gate, not a sufficient one.

    Flipping it reaches an adapter that does not exist, because OQ-CBA-039 has
    not been answered. The flag is accepted so a caller can pass the real value
    rather than assume it, and is deliberately not enough.
    """
    with pytest.raises(ProviderConfigurationError, match="OQ-CBA-039"):
        build_contact_classifier(Edition.PRODUCTION, use_fixture=False, allow_live_providers=True)
