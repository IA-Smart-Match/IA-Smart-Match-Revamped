"""Contact-classification adapters for customer §19, and the reason none is live.

Customer §19's second step reads "Company + current position/title analyzed",
and its third and fourth assign an Industry and a Role from what that reading
found. This module is the seam that reading goes through. Today exactly one
adapter exists behind it, and it is a fixture.

## Why there is no live adapter

Choosing a model is not an implementation detail that can be settled at a
keyboard. It commits the project to a vendor, a set of terms, a per-run cost,
and — because the input is a named person's employer and job title — a decision
about sending CBA contact data to a third party. None of those has an owner's
answer, which is **OQ-CBA-038**. So :func:`build_contact_classifier` refuses a
live client under *every* edition rather than only the classroom one, on the
pattern ``registry.build_paid_extraction_provider`` established and
``topic_semantics.build_semantic_topic_provider`` repeated: the refusal is a
property of what has been approved, not of where the code happens to be
running, and expressing it as a deployment property would leave a production
boot silently able to construct something nobody ratified.

``ALLOW_LIVE_PROVIDERS=false`` is the standing environment default and is
necessary but not sufficient here — flipping it reaches an adapter that still
does not exist.

Customer §20 is the other half of the reason, and it is a scope boundary rather
than a procurement one: "finding new speakers on the internet", "scraping
LinkedIn" and "scraping other external sources" are out of scope for this phase
outright. A classifier that looked a company up would be doing the thing §20
forbids, whoever approved the model.

## What the fixture actually does, stated precisely

:class:`FixtureContactClassifier` resolves text two ways, in this order, and
does nothing else:

1. **A recording.** A caller registers ``"Northwind Mutual" -> "52"``, and the
   classifier replays it. This is ``FixtureSemanticTopicProvider``'s playback
   arrangement and it is here for the same reason: a test or a seeded pilot
   dataset that wants a particular classification *states* that classification,
   so there is no algorithm to drift.
2. **The taxonomy's own reading.** Text that *is* one of §7's sector names or
   codes, or one of §8's role names or codes, resolves to it via
   ``resolve_sector`` / ``resolve_role_category``. This is recognition rather
   than inference: a spreadsheet whose column already holds ``"Finance and
   Insurance"`` is being read, not classified, and the taxonomy modules already
   quarantine everything they do not name.

Everything else is
:class:`~smartmatch_domain.cba_classification.UndeterminedClassification`.

**There is no third step, and the absence is the design.** The obvious way to
make a classifier look useful is token overlap — ``"Northwind Mutual Bank"``
contains ``"bank"``, so propose Finance and Insurance. That is not done here.
Token overlap is a *lexical* heuristic, and a lexical heuristic that fills in
``primary_industry_code`` is indistinguishable in the database from a
classification somebody decided. The card's rule is that ambiguous is reviewable
and never a guess; the way to keep that rule is to have no code that could
produce a guess, not to have code that produces guesses carefully.

For the same reason there is **no confidence score** anywhere in this module,
and none on the domain types it returns. A number nobody has calibrated is not
evidence, and a threshold over it would be an approval nobody granted.

## Everything it proposes is still a proposal

An outcome from this module is
:class:`~smartmatch_domain.cba_classification.ProposedClassification`, whose
``source`` is fixed at ``inferred``. §19 requires a Speaker Connector to review
it before the speaker becomes available for matching, and nothing here shortens
that: a recorded mapping is a deployment's stated expectation about its own
data, not a person exercising the judgment §19 says is required.
"""

from __future__ import annotations

from typing import Final

from smartmatch_domain.cba_classification import (
    UNDETERMINED_NO_EVIDENCE,
    UNDETERMINED_UNRECOGNIZED,
    ClassificationOutcome,
    ContactClassificationProposal,
    ProposedClassification,
    UndeterminedClassification,
)
from smartmatch_domain.cba_role_categories import (
    CBA_ROLE_TAXONOMY_VERSION,
    ClassifiedRoleCategory,
    resolve_role_category,
    role_category_for_code,
)
from smartmatch_domain.naics_sectors import (
    NAICS_TAXONOMY_VERSION,
    ClassifiedSector,
    resolve_sector,
    sector_for_code,
)

from smartmatch_providers.base import Edition, ProviderConfigurationError

__all__ = [
    "FIXTURE_CLASSIFIER_NAME",
    "FixtureContactClassifier",
    "build_contact_classifier",
]

#: Prefixed ``fixture-`` for the reason ``FixtureEmailProvider``'s message ids
#: are: a synthetic result must never be mistakable for a real one in a log, in
#: the database, or on a screen.
FIXTURE_CLASSIFIER_NAME: Final[str] = "fixture-cba-contact-classifier"


def _canonical(text: str) -> str:
    """Fold a string to its lookup form.

    Case- and whitespace-insensitive so that a recorded mapping is found
    regardless of how the same company name was typed. This is a *key*
    normalization, not a similarity computation — it decides which recording to
    replay and never what a code should be. ``FixtureSemanticTopicProvider``
    draws the same line in the same words.

    A near miss is a miss: ``"Northwind Mutual Holdings"`` does not find
    ``"Northwind Mutual"``, because prefix matching would be the token-overlap
    heuristic the module docstring refuses, arriving through the door marked
    "normalization".
    """
    return " ".join(text.split()).casefold()


def _evidence(value: str | None) -> str | None:
    """The text to classify, or ``None`` when there is nothing to read.

    A blank cell counts as nothing: ``resolve_sector`` refuses a blank because
    "an empty industry value is missing data, not a value awaiting
    classification", and filing one for review would hand a Connector a row with
    nothing on it to decide about.
    """
    if value is None or not value.strip():
        return None
    return value


class FixtureContactClassifier:
    """Resolves company and title text deterministically. Infers nothing.

    Not a weaker version of a model and not a demo-data source. It replays what
    it was told and recognizes what the released taxonomies already name, and
    reports everything else as undetermined.

    Example:
        >>> classifier = FixtureContactClassifier()
        >>> classifier.record_company("Northwind Mutual", sector_code="52")
        >>> proposal = classifier.propose(company="Northwind Mutual", title=None)
        >>> proposal.industry.code
        '52'
        >>> proposal.role.reason
        'no_evidence'
    """

    name = FIXTURE_CLASSIFIER_NAME

    #: A dictionary and two taxonomy lookups are not a model, and this says so.
    #: It must stay ``False`` for any deterministic adapter ever added here —
    #: see the module docstring.
    is_model = False

    def __init__(self) -> None:
        self._companies: dict[str, str] = {}
        self._titles: dict[str, str] = {}
        #: Every ``(company, title)`` pair this classifier was asked about, in
        #: order. Lets a test assert that a branch which must not classify — a
        #: Connector's own correction, say — did not consult one.
        self.calls: list[tuple[str | None, str | None]] = []

    def record_company(self, company: str, *, sector_code: str) -> None:
        """Register the §7 sector to propose for one company.

        The code is validated here rather than at :meth:`propose`, so a bad
        recording fails in the code that wrote it, naming the value. A fixture
        that accepted ``"banking"`` would emit it happily and fail at
        ``ck_speaker_profile_industry_code`` hours later, inside whichever
        import happened to touch that company.

        Raises:
            ValueError: ``company`` is blank — there is no text to key on.
            smartmatch_domain.naics_sectors.UnknownNaicsSector: ``sector_code``
                is outside customer §7's twenty.
        """
        if not company.strip():
            raise ValueError("company must be non-blank; a blank key matches nothing")
        sector_for_code(sector_code)  # raises UnknownNaicsSector
        self._companies[_canonical(company)] = sector_code

    def record_title(self, title: str, *, role_code: str) -> None:
        """Register the §8 role category to propose for one job title.

        Raises:
            ValueError: ``title`` is blank.
            smartmatch_domain.cba_role_categories.UnknownCbaRoleCategory:
                ``role_code`` is outside customer §8's ten.
        """
        if not title.strip():
            raise ValueError("title must be non-blank; a blank key matches nothing")
        role_category_for_code(role_code)  # raises UnknownCbaRoleCategory
        self._titles[_canonical(title)] = role_code

    def propose(self, *, company: str | None, title: str | None) -> ContactClassificationProposal:
        """Read the two fields §19 names and propose what they resolve to.

        Never raises for text it cannot read. §19 imports a contact and
        classifies it after, so an unreadable company name must leave a storable
        row rather than failing the import that carried it; the outcome is an
        :class:`~smartmatch_domain.cba_classification.UndeterminedClassification`,
        which is an answer.

        Both axes are always returned, so "the role was not classified" and "the
        role axis was never considered" cannot become the same absence.
        """
        self.calls.append((company, title))
        return ContactClassificationProposal(
            industry=self._industry(_evidence(company)),
            role=self._role(_evidence(title)),
        )

    def _industry(self, company: str | None) -> ClassificationOutcome:
        """§7's axis, from the company text.

        Recording first, taxonomy reading second. The precedence is deliberate:
        a deployment that recorded ``"Information"`` as something other than
        sector 51 has said something specific about its own data, and the
        taxonomy reading is the fallback. The reverse order would make a
        recording silently ineffective for exactly the values most likely to
        collide with a sector name.
        """
        if company is None:
            return UndeterminedClassification(
                reason=UNDETERMINED_NO_EVIDENCE,
                evidence=None,
                taxonomy_version=NAICS_TAXONOMY_VERSION,
                classifier=self.name,
            )

        recorded = self._companies.get(_canonical(company))
        if recorded is not None:
            return ProposedClassification(
                code=recorded,
                taxonomy_version=NAICS_TAXONOMY_VERSION,
                evidence=company,
                classifier=self.name,
            )

        resolution = resolve_sector(company)
        if isinstance(resolution, ClassifiedSector):
            return ProposedClassification(
                code=resolution.sector.code,
                taxonomy_version=resolution.taxonomy_version,
                evidence=company,
                classifier=self.name,
            )

        # The taxonomy quarantined it, and this module has nowhere better to put
        # it than the reviewer's screen — where the raw text already sits, in
        # `speaker_profile.company`. See OQ-CBA-010.
        return UndeterminedClassification(
            reason=UNDETERMINED_UNRECOGNIZED,
            evidence=resolution.raw_value,
            taxonomy_version=resolution.taxonomy_version,
            classifier=self.name,
        )

    def _role(self, title: str | None) -> ClassificationOutcome:
        """§8's axis, from the job title. :meth:`_industry`'s shape exactly."""
        if title is None:
            return UndeterminedClassification(
                reason=UNDETERMINED_NO_EVIDENCE,
                evidence=None,
                taxonomy_version=CBA_ROLE_TAXONOMY_VERSION,
                classifier=self.name,
            )

        recorded = self._titles.get(_canonical(title))
        if recorded is not None:
            return ProposedClassification(
                code=recorded,
                taxonomy_version=CBA_ROLE_TAXONOMY_VERSION,
                evidence=title,
                classifier=self.name,
            )

        resolution = resolve_role_category(title)
        if isinstance(resolution, ClassifiedRoleCategory):
            return ProposedClassification(
                code=resolution.category.code,
                taxonomy_version=resolution.taxonomy_version,
                evidence=title,
                classifier=self.name,
            )

        return UndeterminedClassification(
            reason=UNDETERMINED_UNRECOGNIZED,
            evidence=resolution.raw_value,
            taxonomy_version=resolution.taxonomy_version,
            classifier=self.name,
        )


def build_contact_classifier(
    edition: Edition,
    *,
    api_key: str | None = None,
    use_fixture: bool = True,
    allow_live_providers: bool = False,
) -> FixtureContactClassifier:
    """Construct the §19 contact classifier. Only the fixture exists.

    Mirrors ``topic_semantics.build_semantic_topic_provider`` exactly, including
    the part that matters: the refusal applies to **every** edition, not only the
    fixture-only ones, because no edition has an approved model to reach.

    ``use_fixture`` defaults to ``True`` so the safe outcome is what a caller
    gets by writing nothing, and the only way to ask for anything else is to say
    so explicitly and be refused for it.

    Args:
        edition: The running edition. Recorded in the refusal messages so an
            operator can see which deployment asked, and otherwise not consulted
            — every edition gets the same answer.
        api_key: Present only so a misconfigured deployment fails loudly. No
            model credential should exist in any environment of this repository;
            finding one is a deployment defect worth failing on.
        use_fixture: Force the fixture. Passing ``False`` is the only way to
            request a live model, and it is always refused.
        allow_live_providers: Mirrors the ``ALLOW_LIVE_PROVIDERS`` environment
            gate. Accepted so a caller can pass the real value rather than
            assume it, and deliberately **not** sufficient: the gate being open
            does not conjure an adapter or answer OQ-CBA-038.

    Returns:
        A :class:`FixtureContactClassifier`, which makes no network call and
        reads no credential.

    Raises:
        ProviderConfigurationError: if a model credential is present under any
            edition, or if a live adapter is requested at all.
    """
    if api_key:
        raise ProviderConfigurationError(
            f"a classification-model credential is present under edition "
            f"{edition.value!r}. No environment in this repository should hold one: "
            "the model, the vendor terms, and whether a named person's employer and "
            "job title may be sent to a third party at all are unanswered "
            "(OQ-CBA-038). Failing closed; check the environment configuration and "
            "secret bindings, and rotate anything actually bound."
        )

    if not use_fixture:
        raise ProviderConfigurationError(
            f"no live contact classifier may be constructed under edition "
            f"{edition.value!r} — or any other. Which model, on whose credentials, "
            "under which terms, and with what per-run cost is OQ-CBA-038, and it is "
            "open. ALLOW_LIVE_PROVIDERS is a necessary gate, not a sufficient one: "
            f"it was passed as {allow_live_providers!r} here and there is still no "
            "adapter behind it. Customer §19's classification ships against a model "
            "when the question is answered, not when the flag is flipped — and "
            "customer §20 puts looking a company up on the internet out of scope "
            "regardless of which model is approved."
        )

    return FixtureContactClassifier()
