"""The twenty NAICS sector groups customer §7 supplied, as a released taxonomy.

`docs/product/cba-smart-match-customer-requirements.md` §7 says "Use the 20
NAICS sector groups supplied by the customer" and then prints them. This module
is that table expressed as code and nothing else. **Every code and every name
below is copied verbatim from §7**, including the hyphenated ranges (`31-33`,
`44-45`, `48-49`), the serial commas, and `Other Services (except Public
Administration)`'s parenthetical. Tidying any of them would be renaming a
sector, which is a customer decision and not an executor's.

A module and not a data file, for `event_vocabulary`'s reason: this package's
import-linter contract forbids `os` and `pathlib`, so a taxonomy loaded from
disk could not live in this layer at all. The consequence is the intended one —
every version of the table is a reviewed code diff.

This is the sole source
=======================

Nothing else may hold a second copy. Not the frontend, which reads these
values from the API rather than shipping its own enum; not a migration, which
stores the *code* string and leaves the meaning here; not the matcher, which
compares codes it was given. A duplicated list is a place for a twenty-first
sector to appear in one copy and not the other, and §7 is a closed list.

Two arms for a value the table does not name
============================================

* :func:`sector_for_code` **refuses** — it raises :class:`UnknownNaicsSector`.
  Its caller is holding a code that a Speaker Connector already approved and a
  database column already stores; a code outside the table is a bug in the
  caller, and returning a nearest match would hide it.

* :func:`resolve_sector` **quarantines** — it returns a
  :class:`QuarantinedSector` carrying the raw text unchanged. Its caller is
  holding a spreadsheet cell or an inferred guess, and ADR-0012's reasoning
  transfers directly: "Dropping loses the signal that the vocabulary is wrong.
  The unmapped values are the input to the next vocabulary revision, and
  discarding them is how a closed vocabulary ossifies into a wrong one."

Neither arm guesses. Customer §7 allows a speaker's sector to be *inferred*
from company name or title, and §7 also requires a Speaker Connector to be able
to correct it — but the inference rules are learned from real pilot data and
are a later versioned decision. Until one is made, `Tech` does not silently
become `Information` and `Banking` does not silently become `Finance and
Insurance`; both quarantine, visibly, for a human to decide.

Not the event tag vocabulary
============================

ADR-0012's closed tag vocabulary (:mod:`smartmatch_domain.event_vocabulary`)
describes *events* — what kind of event it is and what function a speaker
performs at it. This describes the *industry a speaker works in*. They are
separate versioned vocabularies with separate version tokens and structurally
unrelated resolution types, so neither can be stored in the other's column by
accident. `tests/unit/test_event_vocabulary.py` holds the tests that prove it.

Sources
=======

* ``docs/product/cba-smart-match-customer-requirements.md`` §7
* ``docs/product/cba-taxonomies.md`` (this table, in prose)
* ``docs/plans/2026-09-05-cba-pivot-waves.md`` (CBA-TAXONOMY)
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, TypeAlias

__all__ = [
    "NAICS_SECTORS",
    "NAICS_TAXONOMY_VERSION",
    "SECTOR_CODES",
    "SECTOR_NAMES",
    "ClassifiedSector",
    "NaicsSector",
    "QuarantinedSector",
    "SectorResolution",
    "UnknownNaicsSector",
    "classified_sectors",
    "quarantined_sectors",
    "resolve_sector",
    "sector_for_code",
]

#: The released version token stamped onto every :class:`ClassifiedSector` and
#: :class:`QuarantinedSector` this module produces. Dated by the customer
#: requirements document this table was transcribed from rather than numbered,
#: so a stored classification names the source it was evaluated against and
#: not merely its ordinal. Changing the table means a new token, never an
#: edit under the old one.
NAICS_TAXONOMY_VERSION: Final[str] = "cba-naics-2026-09-04"


class UnknownNaicsSector(LookupError):
    """A sector code customer §7's table does not name.

    A :class:`LookupError` so a caller may catch it without importing this
    module, and a distinct class so a caller that wants to distinguish "this
    code is not a sector" from any other lookup failure can.
    """


@dataclass(frozen=True, slots=True)
class NaicsSector:
    """One row of customer §7's table.

    Attributes:
        code: The sector code exactly as §7 prints it — `"11"`, or a
            hyphenated range such as `"31-33"`. This is the value that gets
            stored; it is a string and not an integer precisely because three
            of the twenty are ranges.
        name: The sector name exactly as §7 prints it, punctuation included.
            This is the display string, and it is not derived from the code.
    """

    code: str
    name: str


@dataclass(frozen=True, slots=True)
class ClassifiedSector:
    """A raw value that resolved into the taxonomy. Matchable and renderable.

    Attributes:
        sector: The canonical row.
        taxonomy_version: The :data:`NAICS_TAXONOMY_VERSION` this was resolved
            against, carried so a stored classification stays interpretable
            after the taxonomy is revised.
    """

    sector: NaicsSector
    taxonomy_version: str


@dataclass(frozen=True, slots=True)
class QuarantinedSector:
    """A raw value the taxonomy did not recognize, awaiting human review.

    Deliberately has no ``sector`` and no ``code`` attribute — there is
    nothing on this type that reads as a classified value, so a caller cannot
    reach one from a quarantined value by accident. The only way to obtain a
    :class:`ClassifiedSector` for this raw text is to resolve it again against
    a later taxonomy version that names it, which is a deliberate, reviewed
    change.

    Attributes:
        raw_value: The text exactly as received, unnormalized — a reviewer
            deciding what this row should be classified as needs to see what
            the sheet actually said, casing, spacing and all.
        taxonomy_version: The version this was checked against and did not
            match.
    """

    raw_value: str
    taxonomy_version: str


#: The outcome of resolving one raw value against this taxonomy.
SectorResolution: TypeAlias = ClassifiedSector | QuarantinedSector


#: Customer §7's table, in its order. Frozen rows in an immutable tuple: a
#: released taxonomy is replaced by a new version, never edited in place.
NAICS_SECTORS: Final[tuple[NaicsSector, ...]] = (
    NaicsSector("11", "Agriculture, Forestry, Fishing and Hunting"),
    NaicsSector("21", "Mining, Quarrying, and Oil and Gas Extraction"),
    NaicsSector("22", "Utilities"),
    NaicsSector("23", "Construction"),
    NaicsSector("31-33", "Manufacturing"),
    NaicsSector("42", "Wholesale Trade"),
    NaicsSector("44-45", "Retail Trade"),
    NaicsSector("48-49", "Transportation and Warehousing"),
    NaicsSector("51", "Information"),
    NaicsSector("52", "Finance and Insurance"),
    NaicsSector("53", "Real Estate and Rental and Leasing"),
    NaicsSector("54", "Professional, Scientific, and Technical Services"),
    NaicsSector("55", "Management of Companies and Enterprises"),
    NaicsSector(
        "56",
        "Administrative and Support and Waste Management and Remediation Services",
    ),
    NaicsSector("61", "Educational Services"),
    NaicsSector("62", "Health Care and Social Assistance"),
    NaicsSector("71", "Arts, Entertainment, and Recreation"),
    NaicsSector("72", "Accommodation and Food Services"),
    NaicsSector("81", "Other Services (except Public Administration)"),
    NaicsSector("92", "Public Administration"),
)

#: Every sector code, in table order. Derived from :data:`NAICS_SECTORS` rather
#: than written a second time, so the two can never disagree.
SECTOR_CODES: Final[tuple[str, ...]] = tuple(s.code for s in NAICS_SECTORS)

#: Every sector name, in table order. Derived, for the same reason.
SECTOR_NAMES: Final[tuple[str, ...]] = tuple(s.name for s in NAICS_SECTORS)

_BY_CODE: Final[Mapping[str, NaicsSector]] = MappingProxyType({s.code: s for s in NAICS_SECTORS})


def _fold(text: str) -> str:
    """Case-fold, then collapse every run of non-alphanumeric characters to one space.

    The same technique :func:`smartmatch_domain.events.normalize_tag_value`
    uses, and written out again rather than imported for the reason this whole
    module exists: the event tag vocabulary and this taxonomy are separate
    decisions that happen to share an algorithm today, and importing one into
    the other would make a future divergence in either look like a change to
    both. It also keeps the career/industry taxonomies free of any import from
    the event vocabulary, so no reader can mistake one for a layer over the
    other.

    Replacing punctuation with a boundary rather than deleting it is what makes
    `"31-33"` fold to `"31 33"` and not `"3133"`, so a code and a name can
    share one lookup index without a hyphen silently merging two numbers.

    Deliberately does not: fold accents, stem, or resolve synonyms. This is an
    exact, reproducible comparison, not a similarity measure — ADR-0012
    rejects fuzzy identity outright and the same discipline applies here.
    """
    folded = text.casefold()
    boundary = "".join(ch if ch.isalnum() else " " for ch in folded)
    return " ".join(boundary.split())


#: Folded code *and* folded name both point at their row, so a spreadsheet
#: column holding either form resolves. Nothing else is indexed: an alias
#: (`Tech`, `Banking`) would be an inference rule, and this card defers those.
_RESOLUTION_INDEX: Final[Mapping[str, NaicsSector]] = MappingProxyType(
    {
        **{_fold(s.code): s for s in NAICS_SECTORS},
        **{_fold(s.name): s for s in NAICS_SECTORS},
    }
)


def sector_for_code(code: str) -> NaicsSector:
    """The sector a stored code names.

    Matched exactly against §7's printed code — `" 11"`, `"3133"` and `"31"`
    are not stored codes and are refused rather than rounded to `"11"` or
    `"31-33"`. Use :func:`resolve_sector` for text that came from a human or a
    spreadsheet, which is where tolerance belongs.

    Raises:
        UnknownNaicsSector: if ``code`` is not one of :data:`SECTOR_CODES`.
    """
    try:
        return _BY_CODE[code]
    except KeyError:
        raise UnknownNaicsSector(
            f"{code!r} is not one of the twenty NAICS sector codes customer §7 "
            f"supplies ({NAICS_TAXONOMY_VERSION}); a stored code outside the "
            "table is a caller error, and values arriving from import or "
            "inference belong in resolve_sector, which quarantines them for "
            "review instead"
        ) from None


def resolve_sector(raw_value: str) -> SectorResolution:
    """Map a raw value into the taxonomy, or quarantine it for review.

    Accepts either §7's code or §7's sector name, in any casing and with any
    surrounding or repeated whitespace. Accepts nothing else — the taxonomy is
    closed, and there is no parameter here that could add a row to it.

    Args:
        raw_value: The text as received. Must not be blank: an empty cell is
            nothing for a reviewer to decide about, so it is refused rather
            than filed into a queue that a human then has to empty.

    Raises:
        ValueError: if ``raw_value`` is empty or only whitespace.
    """
    if not raw_value.strip():
        raise ValueError(
            "raw_value must not be blank; an empty industry value is missing "
            "data, not a value awaiting classification"
        )
    sector = _RESOLUTION_INDEX.get(_fold(raw_value))
    if sector is None:
        return QuarantinedSector(raw_value=raw_value, taxonomy_version=NAICS_TAXONOMY_VERSION)
    return ClassifiedSector(sector=sector, taxonomy_version=NAICS_TAXONOMY_VERSION)


def classified_sectors(
    resolutions: Iterable[SectorResolution],
) -> tuple[ClassifiedSector, ...]:
    """The subset of ``resolutions`` that may be rendered or matched on.

    Enforced by type rather than by remembering to call this filter —
    :class:`QuarantinedSector` has no ``sector`` attribute for a caller to
    reach even by skipping it.
    """
    return tuple(r for r in resolutions if isinstance(r, ClassifiedSector))


def quarantined_sectors(
    resolutions: Iterable[SectorResolution],
) -> tuple[QuarantinedSector, ...]:
    """The subset of ``resolutions`` awaiting a Speaker Connector's decision."""
    return tuple(r for r in resolutions if isinstance(r, QuarantinedSector))
