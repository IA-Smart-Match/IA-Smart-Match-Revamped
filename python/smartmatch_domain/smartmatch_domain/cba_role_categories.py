"""The ten CBA-aligned career role categories customer §8 supplied.

`docs/product/cba-smart-match-customer-requirements.md` §8 prints a numbered
list of ten and says "Use these ten CBA-aligned role categories". **Every
:attr:`CbaRoleCategory.name` below is copied verbatim from that list**, down to
the ampersand in `Management & Strategy` and the spaced slash in
`Entrepreneurship / Founder`. Rewriting `&` as `and` would be renaming a
category, which is a customer decision.

A career discipline, not an event function
==========================================

This is the single most important thing about this module, and the reason it
is a separate file rather than a second vocabulary inside
:mod:`smartmatch_domain.event_vocabulary`. ADR-0012's closed tag vocabulary
holds terms like `panelist`, `judge`, `keynote` and `mentor`: the *function a
person performs at an event*. A CBA role category is the *career discipline a
speaker works in*: `Finance`, `Human Resources`. The two use the word "role"
for unrelated things.

`docs/plans/2026-09-05-cba-pivot-waves.md` states the rule directly —
"ADR-0012's event type/speaker-function tag vocabulary is not the CBA
career-role taxonomy. They remain separate versioned vocabularies." Separation
is held structurally, not by discipline: distinct version tokens, and
resolution types that are not substitutable for each other, so a career
classification cannot reach `matchable_tags` and an event tag cannot be stored
in a career-role column. `tests/unit/test_event_vocabulary.py` proves it.

The names are the customer's; the codes are this module's
=========================================================

§8 supplies display names only. Storage needs a stable key that survives a
display rename, so this taxonomy assigns each row a lowercase, underscored
``code``. Those codes are a decision made here and fixed by
`tests/unit/test_cba_role_categories.py`, so a later revision cannot renumber
stored rows unnoticed. A code is never derived from a name at runtime — the
two are written side by side and the pairing is the released artifact.

This is the sole source
=======================

No frontend enum, no migration literal, no matcher constant holds a second
copy. §8 is a closed list of ten and a duplicated list is where an eleventh
appears in one copy only.

Two arms for a value the list does not name
===========================================

:func:`role_category_for_code` **refuses** (raises
:class:`UnknownCbaRoleCategory`) because its caller holds a stored, approved
code and an unknown one is a caller bug. :func:`resolve_role_category`
**quarantines**, keeping the reviewer's original text, because its caller holds
a spreadsheet cell or an inferred guess and ADR-0012's reasoning transfers:
discarding an unmapped value is how a closed vocabulary ossifies into a wrong
one.

Customer §8 does allow a role to be inferred from a speaker's title, and
requires a Speaker Connector to be able to correct it. The inference rules
themselves are learned from real pilot data and are a later versioned
decision — so `HR` does not silently become `Human Resources` here, and
`Sales` does not silently become `Sales & Business Development`. Both
quarantine, visibly, for a human.

Sources
=======

* ``docs/product/cba-smart-match-customer-requirements.md`` §8
* ``docs/product/cba-taxonomies.md`` (this list, in prose)
* ``docs/plans/2026-09-05-cba-pivot-waves.md`` (CBA-TAXONOMY)
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, TypeAlias

__all__ = [
    "CBA_ROLE_CATEGORIES",
    "CBA_ROLE_TAXONOMY_VERSION",
    "ROLE_CATEGORY_CODES",
    "ROLE_CATEGORY_NAMES",
    "CbaRoleCategory",
    "ClassifiedRoleCategory",
    "QuarantinedRoleCategory",
    "RoleCategoryResolution",
    "UnknownCbaRoleCategory",
    "classified_role_categories",
    "quarantined_role_categories",
    "resolve_role_category",
    "role_category_for_code",
]

#: The released version token stamped onto every classification this module
#: produces. Dated by the customer requirements document §8 was transcribed
#: from, and deliberately distinct from both
#: :data:`smartmatch_domain.naics_sectors.NAICS_TAXONOMY_VERSION` and
#: :data:`smartmatch_domain.event_vocabulary.VOCABULARY_VERSION`, so a stored
#: value names which of the three vocabularies evaluated it.
CBA_ROLE_TAXONOMY_VERSION: Final[str] = "cba-roles-2026-09-04"


class UnknownCbaRoleCategory(LookupError):
    """A role-category code customer §8's list does not name."""


@dataclass(frozen=True, slots=True)
class CbaRoleCategory:
    """One entry of customer §8's list.

    Attributes:
        code: The stable storage key this taxonomy assigns. Lowercase and
            underscored so it is safe as a database value, a query parameter
            and a JSON key without escaping. Survives a display rename.
        name: The display string exactly as §8 prints it, punctuation
            included. Never derived from :attr:`code`.
    """

    code: str
    name: str


@dataclass(frozen=True, slots=True)
class ClassifiedRoleCategory:
    """A raw value that resolved into the taxonomy. Matchable and renderable.

    Attributes:
        category: The canonical entry.
        taxonomy_version: The :data:`CBA_ROLE_TAXONOMY_VERSION` this was
            resolved against.
    """

    category: CbaRoleCategory
    taxonomy_version: str


@dataclass(frozen=True, slots=True)
class QuarantinedRoleCategory:
    """A raw value the taxonomy did not recognize, awaiting human review.

    Deliberately has no ``category`` and no ``code`` attribute, so nothing on
    this type reads as a classified value.

    Attributes:
        raw_value: The text exactly as received, unnormalized — a reviewer
            classifying a speaker needs to see the title the sheet actually
            carried.
        taxonomy_version: The version this was checked against and did not
            match.
    """

    raw_value: str
    taxonomy_version: str


#: The outcome of resolving one raw value against this taxonomy.
RoleCategoryResolution: TypeAlias = ClassifiedRoleCategory | QuarantinedRoleCategory


#: Customer §8's list, in its numbered order. Frozen rows in an immutable
#: tuple: a released taxonomy is replaced by a new version, never edited.
CBA_ROLE_CATEGORIES: Final[tuple[CbaRoleCategory, ...]] = (
    CbaRoleCategory("accounting", "Accounting"),
    CbaRoleCategory("finance", "Finance"),
    CbaRoleCategory("marketing", "Marketing"),
    CbaRoleCategory("management_strategy", "Management & Strategy"),
    CbaRoleCategory("human_resources", "Human Resources"),
    CbaRoleCategory("operations_supply_chain", "Operations & Supply Chain"),
    CbaRoleCategory("information_systems_analytics", "Information Systems & Analytics"),
    CbaRoleCategory("international_business", "International Business"),
    CbaRoleCategory("entrepreneurship_founder", "Entrepreneurship / Founder"),
    CbaRoleCategory("sales_business_development", "Sales & Business Development"),
)

#: Every code, in list order. Derived from :data:`CBA_ROLE_CATEGORIES` rather
#: than written a second time, so the two can never disagree.
ROLE_CATEGORY_CODES: Final[tuple[str, ...]] = tuple(c.code for c in CBA_ROLE_CATEGORIES)

#: Every display name, in list order. Derived, for the same reason.
ROLE_CATEGORY_NAMES: Final[tuple[str, ...]] = tuple(c.name for c in CBA_ROLE_CATEGORIES)

_BY_CODE: Final[Mapping[str, CbaRoleCategory]] = MappingProxyType(
    {c.code: c for c in CBA_ROLE_CATEGORIES}
)


def _fold(text: str) -> str:
    """Case-fold, then collapse every run of non-alphanumeric characters to one space.

    Written out here rather than imported from
    :mod:`smartmatch_domain.events` for the reason the module docstring gives:
    the event tag vocabulary and this taxonomy are separate decisions that
    share an algorithm today, and coupling them would make a future divergence
    in either look like a change to both.

    Replacing punctuation with a boundary rather than deleting it is what makes
    `"Management & Strategy"` fold to `"management strategy"` and
    `"information_systems_analytics"` fold to
    `"information systems analytics"`, so a code and a name share one lookup
    index without two words merging into one.

    It also draws the line this card's deferral policy asks for: a punctuation
    difference folds away, but substituting a *word* for a symbol does not.
    `"Management and Strategy"` is an alias, not a spelling, and it
    quarantines.
    """
    folded = text.casefold()
    boundary = "".join(ch if ch.isalnum() else " " for ch in folded)
    return " ".join(boundary.split())


#: Folded code *and* folded name both point at their entry. Nothing else is
#: indexed: `HR`, `Sales`, `Ops` are inference rules, which this card defers.
_RESOLUTION_INDEX: Final[Mapping[str, CbaRoleCategory]] = MappingProxyType(
    {
        **{_fold(c.code): c for c in CBA_ROLE_CATEGORIES},
        **{_fold(c.name): c for c in CBA_ROLE_CATEGORIES},
    }
)


def role_category_for_code(code: str) -> CbaRoleCategory:
    """The role category a stored code names.

    Matched exactly against :data:`ROLE_CATEGORY_CODES` — `"Finance"`,
    `"finance "` and `"management-strategy"` are not stored codes and are
    refused rather than folded to the nearest one. Use
    :func:`resolve_role_category` for text from a human or a spreadsheet.

    Raises:
        UnknownCbaRoleCategory: if ``code`` is not one of
            :data:`ROLE_CATEGORY_CODES`.
    """
    try:
        return _BY_CODE[code]
    except KeyError:
        raise UnknownCbaRoleCategory(
            f"{code!r} is not one of the ten CBA role-category codes customer "
            f"§8 supplies ({CBA_ROLE_TAXONOMY_VERSION}); a stored code outside "
            "the list is a caller error, and values arriving from import or "
            "title inference belong in resolve_role_category, which "
            "quarantines them for review instead"
        ) from None


def resolve_role_category(raw_value: str) -> RoleCategoryResolution:
    """Map a raw value into the taxonomy, or quarantine it for review.

    Accepts a §8 code or a §8 display name, in any casing and with any
    surrounding or repeated whitespace. Accepts nothing else — the taxonomy is
    closed, and there is no parameter here that could add an entry to it.

    Args:
        raw_value: The text as received. Must not be blank: an empty title is
            missing data, not a value awaiting classification.

    Raises:
        ValueError: if ``raw_value`` is empty or only whitespace.
    """
    if not raw_value.strip():
        raise ValueError(
            "raw_value must not be blank; an empty role value is missing "
            "data, not a value awaiting classification"
        )
    category = _RESOLUTION_INDEX.get(_fold(raw_value))
    if category is None:
        return QuarantinedRoleCategory(
            raw_value=raw_value, taxonomy_version=CBA_ROLE_TAXONOMY_VERSION
        )
    return ClassifiedRoleCategory(category=category, taxonomy_version=CBA_ROLE_TAXONOMY_VERSION)


def classified_role_categories(
    resolutions: Iterable[RoleCategoryResolution],
) -> tuple[ClassifiedRoleCategory, ...]:
    """The subset of ``resolutions`` that may be rendered or matched on."""
    return tuple(r for r in resolutions if isinstance(r, ClassifiedRoleCategory))


def quarantined_role_categories(
    resolutions: Iterable[RoleCategoryResolution],
) -> tuple[QuarantinedRoleCategory, ...]:
    """The subset of ``resolutions`` awaiting a Speaker Connector's decision."""
    return tuple(r for r in resolutions if isinstance(r, QuarantinedRoleCategory))
