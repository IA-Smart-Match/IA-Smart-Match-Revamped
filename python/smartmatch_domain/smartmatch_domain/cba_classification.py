"""Customer §19's classification proposals, their provenance, and the review gate.

Customer §19 draws the flow this module types:

    Contact record imported or manually created
            -> Company + current position/title analyzed
            -> Initial Industry classification assigned
            -> Initial Role classification assigned
            -> Speaker Connector reviews/corrects classifications
            -> Speaker becomes available for matching

and states the reason for the fifth step in one line: "Human correction is
required because classification may involve judgment calls."

Three things follow from that line, and this module exists to make all three
impossible to violate by accident rather than merely documented.

A proposal is not a classification
------------------------------------
Steps three and four *assign* something, and step five lets a human overrule it.
Between them the stored value is a **proposal**: a machine's reading of a
company name and a job title, not a statement about the person. Presenting it as
established — rendering it beside a human-chosen one with nothing to tell them
apart, or letting it into matching — would delete step five while leaving the
diagram intact.

So :data:`CLASSIFICATION_SOURCE_INFERRED` and :data:`CLASSIFICATION_SOURCE_HUMAN`
are the two values ``speaker_profile``'s provenance columns hold (migration
``0028``), and :func:`is_match_eligible` is step six's precondition expressed as
a function rather than as a habit.

An undetermined axis is reviewable, never a guess
---------------------------------------------------
:class:`UndeterminedClassification` is a first-class outcome, not a failure
mode. A classifier that cannot resolve ``"Reyes Analytics"`` into one of §7's
twenty sectors returns one, and the profile keeps a NULL code — which reads on a
Connector's screen as "nobody has classified this", which is true.

The alternative, and the reason this type is shaped the way it is: a classifier
under pressure to fill the column would emit its best-scoring sector with a low
confidence number attached, and every consumer that forgot to check the number
would treat a coin-flip as a classification. :class:`UndeterminedClassification`
has **no ``code`` attribute**, so there is nothing to forget to check — the same
technique :class:`smartmatch_domain.naics_sectors.QuarantinedSector` uses, for
the same reason its docstring gives. There is deliberately no confidence score
anywhere in this module: a number nobody has calibrated is not evidence, and
storing one would invite a threshold nobody has approved.

A correction wins, and says who made it
-----------------------------------------
:func:`human_classification` and :func:`inferred_classification` are the only
two ways to build a :class:`ClassificationAssignment`, and they differ in
exactly what ``0028``'s constraint differs in: the human one requires an actor
and the inferred one has no parameter through which to accept one. A Connector's
correction is therefore a ``human`` assignment that replaces whatever was there,
inferred or otherwise, and it carries their id because the constructor will not
build one without it.

What is not here
------------------
No previous value, no revision record, and no way to ask what a classification
used to be. That is OQ-CBA-008's decided answer — *add provenance, no history* —
and not an omission this module is waiting for somebody to fill in. The question
provenance answers is "can I trust this?"; the previous value is not evidence
about the current one. Migration ``0028``'s docstring argues it at length.

No consent state either, and nothing that reads or writes a contact channel. A
classifier reads a company and a job title; an email address is neither, and
possessing one is not permission to use it — ``smartmatch_domain.consent`` admits
four approved sources and an import is none of them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, Protocol, TypeAlias

from smartmatch_domain.cba_role_categories import (
    CBA_ROLE_TAXONOMY_VERSION,
    role_category_for_code,
)
from smartmatch_domain.naics_sectors import NAICS_TAXONOMY_VERSION, sector_for_code

__all__ = [
    "CLASSIFICATION_SOURCES",
    "CLASSIFICATION_SOURCE_HUMAN",
    "CLASSIFICATION_SOURCE_INFERRED",
    "UNDETERMINED_NO_EVIDENCE",
    "UNDETERMINED_REASONS",
    "UNDETERMINED_UNRECOGNIZED",
    "ClassificationAssignment",
    "ClassificationOutcome",
    "ClassificationSource",
    "ContactClassificationProposal",
    "ContactClassifier",
    "ProposedClassification",
    "UndeterminedClassification",
    "human_classification",
    "inferred_classification",
    "is_match_eligible",
    "match_ineligibility_reason",
]


#: The stored source, narrowed so the type checker enforces what the ``CHECK``
#: enforces. Declared before the two constants rather than after them so they can
#: be annotated with it: typed as a bare ``str`` they would not satisfy this
#: alias at a call site, and every caller would need a cast to say what the
#: values already are.
ClassificationSource: TypeAlias = Literal["inferred", "human"]

#: A classifier proposed this value from the contact's own company and title
#: text. §19's steps three and four, and nothing more: it is a reading awaiting
#: step five, and :func:`is_match_eligible` refuses it.
CLASSIFICATION_SOURCE_INFERRED: Final[ClassificationSource] = "inferred"

#: A person chose this value — §13's create form, or §19's correction. The only
#: source that satisfies "Human correction is required".
CLASSIFICATION_SOURCE_HUMAN: Final[ClassificationSource] = "human"

#: The closed vocabulary ``speaker_profile``'s two provenance columns hold.
#: Migration ``0028`` transcribes these two literals into its ``CHECK`` rather
#: than importing them, for the reason ``0023`` and ``0024`` both state; the
#: binding back to this tuple is behavioural, in
#: ``tests/integration/test_cba_import_classification.py``.
#:
#: Two values, and deliberately not three. A ``"corrected"`` source would try to
#: encode history in an enum — it says something about what the value *was*,
#: which is exactly what OQ-CBA-008 declined to store. A corrected value is
#: ``human``, indistinguishable from one typed at create time, because both are
#: a person's judgment and that is the only property step five turns on.
CLASSIFICATION_SOURCES: Final[tuple[ClassificationSource, ...]] = (
    CLASSIFICATION_SOURCE_INFERRED,
    CLASSIFICATION_SOURCE_HUMAN,
)


#: The classifier had nothing to read: the contact states no company (for the
#: industry axis) or no job title (for the role axis). Distinguished from
#: :data:`UNDETERMINED_UNRECOGNIZED` because they call for different human acts
#: — one asks a Connector to *find out where this person works*, the other to
#: *decide which sector this employer belongs to*.
UNDETERMINED_NO_EVIDENCE: Final[str] = "no_evidence"

#: The classifier read the text and the closed taxonomy does not name it. The
#: text itself is not copied into a quarantine column: it is already stored, in
#: ``speaker_profile.company`` or ``.title``, where the reviewer reads it
#: (OQ-CBA-010).
UNDETERMINED_UNRECOGNIZED: Final[str] = "unrecognized"

#: Why an axis was left unclassified. Closed, for the reason every vocabulary in
#: this package is closed: a free-text reason is a log line, and a reviewer's
#: screen cannot branch on a log line.
UNDETERMINED_REASONS: Final[tuple[str, ...]] = (
    UNDETERMINED_NO_EVIDENCE,
    UNDETERMINED_UNRECOGNIZED,
)


@dataclass(frozen=True, slots=True)
class ProposedClassification:
    """One axis a classifier resolved into its closed taxonomy.

    A **proposal**, and the name is load-bearing. Nothing on this type asserts
    that the value is correct, and :attr:`source` is fixed at
    :data:`CLASSIFICATION_SOURCE_INFERRED` rather than accepted as an argument,
    so a caller cannot construct one that claims a human agreed with it.

    Attributes:
        code: The taxonomy code. What gets stored.
        taxonomy_version: Which released taxonomy resolved it, stamped so a
            stored code stays interpretable after a revision.
        evidence: The company or title text the proposal was drawn from,
            unnormalized. Carried so a reviewer sees what the classifier
            actually read, which is the difference between "this is wrong" and
            "this is wrong *because the sheet said Reyes Analytics*".
        classifier: The adapter's name, for the reason
            ``TopicSimilarity`` carries ``provider``: a synthetic result must be
            identifiable as one in a log. Not stored on ``speaker_profile`` —
            ``0028`` stores whether a value was inferred, not by which adapter,
            because a column that could also hold ``"csv-import-v3"`` would be a
            provenance log wearing an enum's name.
        source: Fixed at :data:`CLASSIFICATION_SOURCE_INFERRED`. An attribute
            rather than a parameter; see above.
    """

    code: str
    taxonomy_version: str
    evidence: str
    classifier: str
    source: ClassificationSource = CLASSIFICATION_SOURCE_INFERRED

    def __post_init__(self) -> None:
        if not self.evidence.strip():
            raise ValueError(
                "evidence must be the non-blank text the proposal was drawn from; "
                "a proposal with nothing behind it is an UndeterminedClassification"
            )
        if not self.classifier.strip():
            raise ValueError("classifier must be a non-blank adapter name")
        if self.source != CLASSIFICATION_SOURCE_INFERRED:
            raise ValueError(
                f"a proposal's source is always {CLASSIFICATION_SOURCE_INFERRED!r}; "
                "a human-assigned value is built by human_classification, which "
                "requires the actor this type has nowhere to put"
            )


@dataclass(frozen=True, slots=True)
class UndeterminedClassification:
    """One axis the classifier declined to propose a value for.

    **Has no ``code`` attribute**, deliberately, so a caller cannot reach a
    value from an undetermined outcome even by ignoring the type — the technique
    :class:`smartmatch_domain.naics_sectors.QuarantinedSector` uses and states
    its reason for. The only way to classify this axis is for a person to do it.

    Not an error and not a failure: §19 imports a contact and classifies it
    after, so an unclassified axis is a state the schema stores (``0024``'s
    nullable columns) and a Connector's roster renders.

    Attributes:
        reason: One of :data:`UNDETERMINED_REASONS`.
        evidence: The text that was read and not recognized, or ``None`` when
            there was none to read.
        taxonomy_version: The version the text was checked against and did not
            match, so a later revision that *does* name it can be identified as
            the thing that changed.
        classifier: The adapter that declined.
    """

    reason: str
    evidence: str | None
    taxonomy_version: str
    classifier: str

    def __post_init__(self) -> None:
        if self.reason not in UNDETERMINED_REASONS:
            raise ValueError(
                f"reason must be one of {UNDETERMINED_REASONS!r}, got {self.reason!r}; "
                "a free-text reason is a log line and a reviewer's screen cannot "
                "branch on one"
            )
        if self.reason == UNDETERMINED_NO_EVIDENCE and self.evidence is not None:
            raise ValueError(
                "an outcome reporting no evidence must carry none; text that was "
                "read and rejected is UNDETERMINED_UNRECOGNIZED"
            )
        if self.reason == UNDETERMINED_UNRECOGNIZED and not (self.evidence or "").strip():
            raise ValueError(
                "an outcome reporting unrecognized text must carry that text; "
                "without it a reviewer cannot see what the classifier read"
            )


#: What a classifier returns for one axis. A union rather than an optional code,
#: so the undetermined case has to be handled rather than defaulted past.
ClassificationOutcome: TypeAlias = ProposedClassification | UndeterminedClassification


@dataclass(frozen=True, slots=True)
class ContactClassificationProposal:
    """Both of §19's axes for one contact, as a classifier read them.

    Both axes always present — as an outcome, which may be undetermined. A
    classifier that returned only what it could resolve would make "the role was
    not classified" and "the role axis was never considered" the same absence.

    Attributes:
        industry: §7's axis, read from the contact's company.
        role: §8's axis, read from the contact's job title.
    """

    industry: ClassificationOutcome
    role: ClassificationOutcome

    @property
    def proposes_anything(self) -> bool:
        """Whether either axis resolved.

        ``False`` means the contact is stored exactly as it was entered, with
        both classifications left for a person — a normal outcome, not an import
        failure.
        """
        return isinstance(self.industry, ProposedClassification) or isinstance(
            self.role, ProposedClassification
        )


class ContactClassifier(Protocol):
    """What §19's steps three and four require of any adapter behind them.

    Structural, and narrow on purpose. It takes the two fields §19 names —
    "Company + current position/title analyzed" — and nothing else. It is not
    given the contact's name, its id, its unit, or its email: a classifier that
    could see an email address would be one somebody could later be tempted to
    have look one up, and §20 puts finding people on the internet out of scope
    outright.

    Attributes:
        name: The adapter's name, stamped onto every outcome it produces.
        is_model: Whether this adapter consults a live model. ``False`` for
            every adapter that exists today, and it must stay ``False`` for any
            deterministic one that is ever added — the discipline
            ``FixtureSemanticTopicProvider`` states about ``is_semantic_model``,
            for the same reason: a misleading name becomes a permanent lie in
            the data.
    """

    name: str
    is_model: bool

    def propose(self, *, company: str | None, title: str | None) -> ContactClassificationProposal:
        """Read the two fields and propose what they resolve to.

        Must not raise for unrecognized or absent text: that is an
        :class:`UndeterminedClassification`, which is an answer.
        """
        ...


@dataclass(frozen=True, slots=True)
class ClassificationAssignment:
    """One axis's value as it will be stored, with the provenance that explains it.

    Built through :func:`inferred_classification` or :func:`human_classification`
    and not by calling the constructor, because the two differ in exactly what
    migration ``0028``'s ``CHECK`` differs in — the human form requires an actor
    and the inferred form has nowhere to put one — and a constructor taking both
    as optional arguments would let a caller write the combination the database
    rejects, discovering it as an ``IntegrityError`` instead of a ``TypeError``.

    Attributes:
        code: The taxonomy code being stored.
        taxonomy_version: Which released taxonomy it was resolved against.
        source: One of :data:`CLASSIFICATION_SOURCES`.
        actor_id: The person whose judgment this is, or ``None`` when the source
            is inferred — because a classifier has none.
        assigned_at: When the value was set.
    """

    code: str
    taxonomy_version: str
    source: ClassificationSource
    actor_id: uuid.UUID | None
    assigned_at: datetime


def inferred_classification(
    proposal: ProposedClassification, *, at: datetime
) -> ClassificationAssignment:
    """A proposal, ready to store as ``inferred``.

    Takes no actor and offers no parameter for one. That is the card's
    non-negotiable made unwritable rather than merely documented: there is no
    argument through which a caller could attach a person to a machine's
    reading, so no code path can produce a row asserting a review that did not
    happen.

    Args:
        proposal: The resolved axis. Typed as :class:`ProposedClassification`,
            so an :class:`UndeterminedClassification` cannot be passed — an axis
            with no proposal is stored as NULL, not as an assignment.
        at: When the classifier ran.
    """
    return ClassificationAssignment(
        code=proposal.code,
        taxonomy_version=proposal.taxonomy_version,
        source=CLASSIFICATION_SOURCE_INFERRED,
        actor_id=None,
        assigned_at=at,
    )


def human_classification(
    code: str, *, axis: str, actor_id: uuid.UUID, at: datetime
) -> ClassificationAssignment:
    """A person's chosen value, ready to store as ``human``.

    ``actor_id`` is required rather than optional: "a human decided this" is
    worth storing only if somebody can be asked which human, and an optional
    actor would make the unattributed form the one a hurried caller reaches for.
    Migration ``0028`` permits a NULL actor beside ``human`` only to describe
    rows written before the column existed; nothing built here may produce one.

    The code is re-checked against its taxonomy even though every caller has
    already validated it. The check is cheap and the failure it prevents is not:
    a code outside the vocabulary would otherwise be stored under a provenance
    claiming somebody vouched for it.

    Args:
        code: The taxonomy code the person chose.
        axis: ``"industry"`` or ``"role"`` — which closed vocabulary ``code`` is
            held to, and which taxonomy version is stamped.
        actor_id: The ``user_account`` id of the person who chose it.
        at: When they chose it.

    Raises:
        ValueError: ``axis`` is neither ``"industry"`` nor ``"role"``.
        smartmatch_domain.naics_sectors.UnknownNaicsSector: an industry code
            outside customer §7's twenty.
        smartmatch_domain.cba_role_categories.UnknownCbaRoleCategory: a role
            code outside customer §8's ten.
    """
    if axis == "industry":
        sector_for_code(code)  # raises UnknownNaicsSector
        version = NAICS_TAXONOMY_VERSION
    elif axis == "role":
        role_category_for_code(code)  # raises UnknownCbaRoleCategory
        version = CBA_ROLE_TAXONOMY_VERSION
    else:
        raise ValueError(
            f"axis must be 'industry' or 'role', got {axis!r}; customer §§7-8 "
            "name two axes and no third is approved"
        )

    return ClassificationAssignment(
        code=code,
        taxonomy_version=version,
        source=CLASSIFICATION_SOURCE_HUMAN,
        actor_id=actor_id,
        assigned_at=at,
    )


def match_ineligibility_reason(
    *,
    primary_industry_code: str | None,
    industry_classification_source: str | None,
    primary_role_code: str | None,
    role_classification_source: str | None,
) -> str | None:
    """Why this contact may not enter matching yet, or ``None`` if it may.

    §19's last two steps are ordered — "Speaker Connector reviews/corrects
    classifications" *then* "Speaker becomes available for matching" — and this
    is that ordering, evaluated. A contact is eligible when **both** axes hold a
    code and **both** were set by a person.

    Returning a reason rather than a bare ``False`` is what lets the surface
    above say which of four situations a Connector is looking at. A boolean would
    collapse "we have no idea where they work" and "the classifier proposed
    Finance and nobody has checked" into one greyed-out row, and those call for
    different actions.

    The unreviewed cases are reported before the missing ones because they are
    the ones a Connector can resolve in a single click, and because an inferred
    value on screen is the state most likely to be mistaken for done.

    ADR-0011 is not in tension with this. An unknown is not a zero *in scoring*;
    this function is not scoring, and it does not give an unreviewed contact a
    low score — it keeps them out of the pool entirely, which is §19's own
    instruction rather than a scoring judgment.

    Args:
        primary_industry_code: ``speaker_profile.primary_industry_code``.
        industry_classification_source: its provenance, or ``None``.
        primary_role_code: ``speaker_profile.primary_role_code``.
        role_classification_source: its provenance, or ``None``.

    Returns:
        A stable machine-readable reason token, or ``None`` when the contact is
        eligible.
    """
    for axis, code, source in (
        ("industry", primary_industry_code, industry_classification_source),
        ("role", primary_role_code, role_classification_source),
    ):
        if code is None:
            continue
        if source == CLASSIFICATION_SOURCE_INFERRED:
            return f"{axis}_classification_awaiting_review"
        if source != CLASSIFICATION_SOURCE_HUMAN:
            # A code with no source, or a source outside the vocabulary. Post-0028
            # the database cannot hold such a row, so reaching this means the
            # caller did not select the provenance columns — and the eligibility
            # question must be answered against what was actually read, not
            # against what the schema would have guaranteed had it been read.
            #
            # Tested by name rather than folded into the branch above: this is a
            # caller defect and "somebody must review this speaker" would send an
            # operator to the wrong screen for it. Matching a positive value
            # (`== human`) rather than excluding a negative one (`!= inferred`)
            # is what makes this arm exist at all — the exclusion form returns
            # *eligible* here, which is the one way an unreviewed speaker could
            # enter matching without anybody writing a line of code saying so.
            return f"{axis}_classification_provenance_unknown"

    if primary_industry_code is None:
        return "industry_classification_missing"
    if primary_role_code is None:
        return "role_classification_missing"
    return None


def is_match_eligible(
    *,
    primary_industry_code: str | None,
    industry_classification_source: str | None,
    primary_role_code: str | None,
    role_classification_source: str | None,
) -> bool:
    """Whether §19's review step has been satisfied for both axes.

    The boolean form of :func:`match_ineligibility_reason`, defined in terms of
    it rather than beside it so the two can never disagree about a case.

    **Fails closed.** Every argument being ``None`` — a caller that read the row
    before ``0028`` ran, or forgot to select the provenance columns — returns
    ``False``, which keeps an unreviewed speaker out of matching. The opposite
    default would make a missing column look like an approval.
    """
    return (
        match_ineligibility_reason(
            primary_industry_code=primary_industry_code,
            industry_classification_source=industry_classification_source,
            primary_role_code=primary_role_code,
            role_classification_source=role_classification_source,
        )
        is None
    )
