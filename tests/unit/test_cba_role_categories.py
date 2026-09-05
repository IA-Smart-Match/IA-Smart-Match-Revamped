"""The ten CBA-aligned career role categories customer §8 supplied.

Same shape as `test_naics_taxonomy.py` and for the same reasons: the customer's
list is transcribed here a second time so a drift in
`smartmatch_domain.cba_role_categories` fails loudly, and the two-armed
contract for an unnamed value — refuse on lookup, quarantine on resolution — is
pinned as behaviour rather than left as prose.

The one thing worth naming separately is what these are *not*. A CBA role
category is a career discipline a speaker works in ("Finance"), not the
function a speaker performs at an event ("panelist"). ADR-0012's tag
vocabulary owns the second, this module owns the first, and
`test_event_vocabulary.py` holds the tests that prove the two never merge.
"""

from __future__ import annotations

import pytest
from smartmatch_domain.cba_role_categories import (
    CBA_ROLE_CATEGORIES,
    CBA_ROLE_TAXONOMY_VERSION,
    ROLE_CATEGORY_CODES,
    ROLE_CATEGORY_NAMES,
    CbaRoleCategory,
    ClassifiedRoleCategory,
    QuarantinedRoleCategory,
    UnknownCbaRoleCategory,
    classified_role_categories,
    quarantined_role_categories,
    resolve_role_category,
    role_category_for_code,
)

#: Customer §8's numbered list, verbatim and in its order, paired with the
#: stable storage code this taxonomy assigns each row. The *names* are the
#: customer's; the *codes* are this module's contribution, and they are fixed
#: here so a later revision cannot renumber stored rows unnoticed.
CUSTOMER_ROLE_CATEGORIES = (
    ("accounting", "Accounting"),
    ("finance", "Finance"),
    ("marketing", "Marketing"),
    ("management_strategy", "Management & Strategy"),
    ("human_resources", "Human Resources"),
    ("operations_supply_chain", "Operations & Supply Chain"),
    ("information_systems_analytics", "Information Systems & Analytics"),
    ("international_business", "International Business"),
    ("entrepreneurship_founder", "Entrepreneurship / Founder"),
    ("sales_business_development", "Sales & Business Development"),
)


def test_the_taxonomy_holds_exactly_ten_role_categories():
    """Customer §8: "Use these ten CBA-aligned role categories"."""
    assert len(CBA_ROLE_CATEGORIES) == 10


def test_every_row_matches_the_customer_list_in_order():
    assert tuple((c.code, c.name) for c in CBA_ROLE_CATEGORIES) == CUSTOMER_ROLE_CATEGORIES


def test_the_code_and_name_tuples_agree_with_the_rows():
    assert tuple(code for code, _ in CUSTOMER_ROLE_CATEGORIES) == ROLE_CATEGORY_CODES
    assert tuple(name for _, name in CUSTOMER_ROLE_CATEGORIES) == ROLE_CATEGORY_NAMES


def test_the_display_names_keep_the_customers_punctuation():
    """`Management & Strategy`, not `Management and Strategy`; `Entrepreneurship
    / Founder`, not `Entrepreneurship or Founder`. The display string is the
    customer's, and tidying it is renaming a category."""
    assert "Management & Strategy" in ROLE_CATEGORY_NAMES
    assert "Entrepreneurship / Founder" in ROLE_CATEGORY_NAMES
    assert "Information Systems & Analytics" in ROLE_CATEGORY_NAMES


def test_codes_are_unique_and_storage_safe():
    assert len(set(ROLE_CATEGORY_CODES)) == len(ROLE_CATEGORY_CODES)
    for code in ROLE_CATEGORY_CODES:
        assert code == code.lower()
        assert code.replace("_", "").isalnum()


def test_names_are_unique():
    assert len(set(ROLE_CATEGORY_NAMES)) == len(ROLE_CATEGORY_NAMES)


def test_the_version_is_a_non_blank_token_distinct_from_the_sector_taxonomy():
    from smartmatch_domain.naics_sectors import NAICS_TAXONOMY_VERSION

    assert CBA_ROLE_TAXONOMY_VERSION
    assert CBA_ROLE_TAXONOMY_VERSION != NAICS_TAXONOMY_VERSION


def test_a_role_category_row_is_frozen():
    with pytest.raises((AttributeError, TypeError)):
        CBA_ROLE_CATEGORIES[0].name = "Bookkeeping"  # type: ignore[misc]


@pytest.mark.parametrize(("code", "name"), CUSTOMER_ROLE_CATEGORIES)
def test_every_code_looks_up_its_category(code: str, name: str):
    category = role_category_for_code(code)
    assert isinstance(category, CbaRoleCategory)
    assert category.name == name


def test_lookup_refuses_an_unknown_code():
    with pytest.raises(UnknownCbaRoleCategory):
        role_category_for_code("supply_chain")


def test_lookup_refuses_a_code_that_differs_only_in_shape():
    for near_miss in ("Finance", "finance ", "management-strategy", ""):
        with pytest.raises((UnknownCbaRoleCategory, ValueError)):
            role_category_for_code(near_miss)


def test_the_refusal_is_a_lookup_error():
    assert issubclass(UnknownCbaRoleCategory, LookupError)


@pytest.mark.parametrize(("code", "name"), CUSTOMER_ROLE_CATEGORIES)
def test_each_code_resolves(code: str, name: str):
    resolution = resolve_role_category(code)
    assert isinstance(resolution, ClassifiedRoleCategory)
    assert resolution.category.code == code
    assert resolution.category.name == name


@pytest.mark.parametrize(("code", "name"), CUSTOMER_ROLE_CATEGORIES)
def test_each_name_resolves_from_the_casing_a_spreadsheet_would_carry(code: str, name: str):
    resolution = resolve_role_category(name.upper())
    assert isinstance(resolution, ClassifiedRoleCategory)
    assert resolution.category.code == code


def test_an_ampersand_name_also_resolves_from_its_spelled_out_punctuation_run():
    """`_fold` replaces punctuation with a boundary rather than deleting it, so
    `Management  &  Strategy` and `Management & Strategy` agree — but
    `Management and Strategy` does not, because substituting a word for a
    symbol is an alias, which this card defers."""
    assert isinstance(resolve_role_category("Management  &  Strategy"), ClassifiedRoleCategory)
    assert isinstance(resolve_role_category("Management and Strategy"), QuarantinedRoleCategory)


def test_both_arms_carry_the_taxonomy_version():
    classified = resolve_role_category("finance")
    quarantined = resolve_role_category("Chief of Staff")

    assert classified.taxonomy_version == CBA_ROLE_TAXONOMY_VERSION
    assert quarantined.taxonomy_version == CBA_ROLE_TAXONOMY_VERSION


@pytest.mark.parametrize(
    "unmapped",
    [
        "Sales",
        "Ops",
        "HR",
        "IT",
        "Product Management",
        "Consulting",
        "Data Science",
    ],
)
def test_a_title_the_list_does_not_name_is_quarantined_not_inferred(unmapped: str):
    """Customer §8 allows a role to be *inferred* from a title, but the
    inference rules are learned from real data and are a later versioned
    decision. Until then `HR` does not silently become `Human Resources`."""
    resolution = resolve_role_category(unmapped)
    assert isinstance(resolution, QuarantinedRoleCategory)
    assert resolution.raw_value == unmapped


def test_a_quarantined_value_keeps_the_reviewers_original_text():
    resolution = resolve_role_category("  VP, People Ops ")
    assert isinstance(resolution, QuarantinedRoleCategory)
    assert resolution.raw_value == "  VP, People Ops "


def test_a_quarantined_category_exposes_no_category_to_reach_for():
    resolution = resolve_role_category("Data Science")
    assert not hasattr(resolution, "category")
    assert not hasattr(resolution, "code")


def test_a_blank_value_is_refused_rather_than_quarantined():
    for blank in ("", "   ", "\t"):
        with pytest.raises(ValueError):
            resolve_role_category(blank)


def test_the_partition_helpers_split_a_batch():
    resolutions = [
        resolve_role_category("marketing"),
        resolve_role_category("Growth Hacking"),
        resolve_role_category("Accounting"),
    ]

    assert [r.category.code for r in classified_role_categories(resolutions)] == [
        "marketing",
        "accounting",
    ]
    assert [r.raw_value for r in quarantined_role_categories(resolutions)] == ["Growth Hacking"]


def test_a_speaker_carries_one_primary_category_but_a_request_may_carry_many():
    """Customer §8's two cardinalities, as `test_naics_taxonomy.py` records
    §7's. Enforcement is `CBA-DATA-SCHEMA`'s; nothing here blocks either."""
    speaker_primary = role_category_for_code("finance")
    request_targets = (
        role_category_for_code("marketing"),
        role_category_for_code("sales_business_development"),
    )

    assert speaker_primary not in request_targets
    assert len(set(request_targets)) == 2
