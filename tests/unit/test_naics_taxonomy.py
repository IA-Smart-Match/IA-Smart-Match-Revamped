"""The twenty NAICS sector groups customer §7 supplied, as a released taxonomy.

`smartmatch_domain.naics_sectors` is a transcription of a customer decision, so
most of these tests are transcription checks: the risk they cover is a code or
a sector name that drifted from
`docs/product/cba-smart-match-customer-requirements.md` §7's table, not an
algorithm that stopped working.

The rest fix the two-armed contract for a value the table does not name.
`sector_for_code` **refuses** — it raises rather than returning a nearest
match — because a caller holding a stored code is holding something a
Speaker Connector already approved, and a code that is not in the table is a
bug in the caller, not data awaiting review. `resolve_sector` **quarantines**,
for ADR-0012's reason applied to a different vocabulary: an unmapped value
imported from a spreadsheet is the input to the next taxonomy revision, and
dropping it is how a closed taxonomy ossifies into a wrong one.
"""

from __future__ import annotations

import pytest
from smartmatch_domain.naics_sectors import (
    NAICS_SECTORS,
    NAICS_TAXONOMY_VERSION,
    SECTOR_CODES,
    SECTOR_NAMES,
    ClassifiedSector,
    NaicsSector,
    QuarantinedSector,
    UnknownNaicsSector,
    classified_sectors,
    quarantined_sectors,
    resolve_sector,
    sector_for_code,
)

#: Copied from `docs/product/cba-smart-match-customer-requirements.md` §7's
#: table, in its order. Written out a second time rather than derived from the
#: module under test: a test that recomputed the rows from the code could not
#: notice the code disagreeing with the customer's table, which is the main
#: failure this file exists to catch.
CUSTOMER_SECTORS = (
    ("11", "Agriculture, Forestry, Fishing and Hunting"),
    ("21", "Mining, Quarrying, and Oil and Gas Extraction"),
    ("22", "Utilities"),
    ("23", "Construction"),
    ("31-33", "Manufacturing"),
    ("42", "Wholesale Trade"),
    ("44-45", "Retail Trade"),
    ("48-49", "Transportation and Warehousing"),
    ("51", "Information"),
    ("52", "Finance and Insurance"),
    ("53", "Real Estate and Rental and Leasing"),
    ("54", "Professional, Scientific, and Technical Services"),
    ("55", "Management of Companies and Enterprises"),
    (
        "56",
        "Administrative and Support and Waste Management and Remediation Services",
    ),
    ("61", "Educational Services"),
    ("62", "Health Care and Social Assistance"),
    ("71", "Arts, Entertainment, and Recreation"),
    ("72", "Accommodation and Food Services"),
    ("81", "Other Services (except Public Administration)"),
    ("92", "Public Administration"),
)


def test_the_taxonomy_holds_exactly_twenty_sectors():
    """Customer §7 supplies twenty sector groups, and this taxonomy is those."""
    assert len(NAICS_SECTORS) == 20


def test_every_row_matches_the_customer_table_in_order():
    assert tuple((s.code, s.name) for s in NAICS_SECTORS) == CUSTOMER_SECTORS


def test_the_code_and_name_tuples_agree_with_the_rows():
    assert tuple(code for code, _ in CUSTOMER_SECTORS) == SECTOR_CODES
    assert tuple(name for _, name in CUSTOMER_SECTORS) == SECTOR_NAMES


def test_the_ranged_codes_keep_the_customers_hyphenated_form():
    """`31-33`, not `31`, `33`, or `3133` — a stored code is the customer's string."""
    assert {"31-33", "44-45", "48-49"} <= set(SECTOR_CODES)


def test_codes_are_unique():
    assert len(set(SECTOR_CODES)) == len(SECTOR_CODES)


def test_names_are_unique():
    assert len(set(SECTOR_NAMES)) == len(SECTOR_NAMES)


def test_the_version_is_a_non_blank_token():
    assert NAICS_TAXONOMY_VERSION.strip() == NAICS_TAXONOMY_VERSION
    assert NAICS_TAXONOMY_VERSION


def test_a_sector_row_is_frozen():
    """Immutability is the point: a released taxonomy is not edited in place."""
    with pytest.raises((AttributeError, TypeError)):
        NAICS_SECTORS[0].name = "Something Else"  # type: ignore[misc]


def test_the_sector_tuple_cannot_be_grown_in_place():
    assert isinstance(NAICS_SECTORS, tuple)


@pytest.mark.parametrize(("code", "name"), CUSTOMER_SECTORS)
def test_every_code_looks_up_its_sector(code: str, name: str):
    sector = sector_for_code(code)
    assert isinstance(sector, NaicsSector)
    assert sector.name == name


def test_lookup_refuses_an_unknown_code():
    """The refuse arm: a stored code outside the table is a caller bug."""
    with pytest.raises(UnknownNaicsSector):
        sector_for_code("99")


def test_lookup_refuses_a_code_that_differs_only_in_shape():
    """No rounding to the nearest row: `3133` and `31` are not `31-33`."""
    for near_miss in ("3133", "31", "33", " 11", "11 "):
        with pytest.raises(UnknownNaicsSector):
            sector_for_code(near_miss)


def test_the_refusal_is_a_lookup_error():
    """So a caller may catch `LookupError` without importing the taxonomy."""
    assert issubclass(UnknownNaicsSector, LookupError)


@pytest.mark.parametrize(("code", "name"), CUSTOMER_SECTORS)
def test_each_code_resolves(code: str, name: str):
    resolution = resolve_sector(code)
    assert isinstance(resolution, ClassifiedSector)
    assert resolution.sector.code == code
    assert resolution.sector.name == name


@pytest.mark.parametrize(("code", "name"), CUSTOMER_SECTORS)
def test_each_name_resolves_from_the_casing_a_spreadsheet_would_carry(code: str, name: str):
    resolution = resolve_sector(name.upper())
    assert isinstance(resolution, ClassifiedSector)
    assert resolution.sector.code == code


def test_resolution_tolerates_surrounding_and_repeated_whitespace():
    resolution = resolve_sector("  Retail   Trade ")
    assert isinstance(resolution, ClassifiedSector)
    assert resolution.sector.code == "44-45"


def test_both_arms_carry_the_taxonomy_version():
    """So a stored classification stays interpretable after a revision."""
    classified = resolve_sector("22")
    quarantined = resolve_sector("Cryptocurrency")

    assert classified.taxonomy_version == NAICS_TAXONOMY_VERSION
    assert quarantined.taxonomy_version == NAICS_TAXONOMY_VERSION


@pytest.mark.parametrize(
    "unmapped",
    [
        "Technology",
        "Tech",
        "Banking",
        "Nonprofit",
        "Consulting",
        "Aerospace",
        "Government",
    ],
)
def test_a_value_the_table_does_not_name_is_quarantined_not_guessed(unmapped: str):
    """The deferral this card is under: aliases learned from real data are a
    later versioned decision, so `Tech` does not silently become `Information`
    and `Banking` does not silently become `Finance and Insurance`."""
    resolution = resolve_sector(unmapped)
    assert isinstance(resolution, QuarantinedSector)
    assert resolution.raw_value == unmapped


def test_a_quarantined_value_keeps_the_reviewers_original_text():
    """Unnormalized: a reviewer needs what the sheet said, casing and all."""
    resolution = resolve_sector("  FinTech  ")
    assert isinstance(resolution, QuarantinedSector)
    assert resolution.raw_value == "  FinTech  "


def test_a_quarantined_sector_exposes_no_sector_to_reach_for():
    resolution = resolve_sector("FinTech")
    assert not hasattr(resolution, "sector")
    assert not hasattr(resolution, "code")


def test_a_blank_value_is_refused_rather_than_quarantined():
    """An empty cell is nothing for a reviewer to decide about."""
    for blank in ("", "   ", "\t"):
        with pytest.raises(ValueError):
            resolve_sector(blank)


def test_the_partition_helpers_split_a_batch():
    resolutions = [
        resolve_sector("52"),
        resolve_sector("Crypto"),
        resolve_sector("Utilities"),
    ]

    assert [r.sector.code for r in classified_sectors(resolutions)] == ["52", "22"]
    assert [r.raw_value for r in quarantined_sectors(resolutions)] == ["Crypto"]


def test_a_speaker_carries_one_primary_sector_but_a_request_may_carry_many():
    """Customer §7 gives the speaker side and the event side different
    cardinalities. Neither is enforced here — that is `CBA-DATA-SCHEMA`'s
    column constraint — but nothing in this module blocks either, and this test
    is where a reader sees that a sector value is a plain immutable row usable
    on both sides."""
    speaker_primary = sector_for_code("54")
    request_targets = (sector_for_code("51"), sector_for_code("52"))

    assert speaker_primary not in request_targets
    assert len(set(request_targets)) == 2
