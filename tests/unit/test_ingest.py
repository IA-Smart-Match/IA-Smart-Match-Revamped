"""Tests for import validation (migration manifest MM-004)."""

from __future__ import annotations

from smartmatch_domain.ingest import (
    Severity,
    normalize_header,
    validate_columns,
)

REQUIRED = ("full_name", "metro_region")


def test_valid_dataset_has_no_findings():
    quality = validate_columns(
        "professionals",
        [{"full_name": "A. Rivera", "metro_region": "Inland Empire"}],
        required=REQUIRED,
    )
    assert quality.is_usable
    assert quality.findings == ()
    assert quality.row_count == 1


def test_empty_dataset_is_an_error_not_a_silent_pass():
    quality = validate_columns("professionals", [], required=REQUIRED)

    assert not quality.is_usable
    assert quality.errors[0].code == "empty_dataset"


def test_missing_required_column_fails_closed():
    """The legacy loader returned a partial frame and let scoring proceed."""
    quality = validate_columns(
        "professionals", [{"full_name": "A. Rivera"}], required=REQUIRED
    )

    assert not quality.is_usable
    finding = quality.errors[0]
    assert finding.code == "missing_required_columns"
    assert finding.columns == ("metro_region",)


def test_all_missing_columns_are_reported_at_once():
    """A coordinator fixing an import should see the whole list, not the first."""
    quality = validate_columns("professionals", [{"unrelated": 1}], required=REQUIRED)
    finding = quality.errors[0]
    assert set(finding.columns) == set(REQUIRED)


def test_header_normalization_tolerates_case_and_punctuation():
    """``Metro-Region`` and ``metro_region`` are the same column."""
    quality = validate_columns(
        "professionals",
        [{"Full Name": "A. Rivera", "  Metro-Region ": "Inland Empire"}],
        required=REQUIRED,
    )
    assert quality.is_usable


def test_unexpected_columns_warn_but_do_not_block():
    quality = validate_columns(
        "professionals",
        [{"full_name": "A", "metro_region": "IE", "internal_note": "x"}],
        required=REQUIRED,
    )
    assert quality.is_usable
    assert quality.warnings[0].code == "unexpected_columns"
    assert quality.warnings[0].columns == ("internal_note",)


def test_optional_columns_are_not_flagged_as_unexpected():
    quality = validate_columns(
        "professionals",
        [{"full_name": "A", "metro_region": "IE", "pronouns": "they/them"}],
        required=REQUIRED,
        optional=("pronouns",),
    )
    assert quality.warnings == ()


def test_required_column_blank_in_every_row_is_an_error():
    """Present-but-empty is as unusable as absent; the legacy called it healthy."""
    quality = validate_columns(
        "professionals",
        [
            {"full_name": "A. Rivera", "metro_region": ""},
            {"full_name": "B. Chen", "metro_region": "   "},
        ],
        required=REQUIRED,
    )
    assert not quality.is_usable
    assert quality.errors[0].code == "required_column_entirely_blank"


def test_partially_blank_required_column_is_acceptable():
    """Some rows missing a value is a data problem for review, not a hard stop."""
    quality = validate_columns(
        "professionals",
        [
            {"full_name": "A. Rivera", "metro_region": "Inland Empire"},
            {"full_name": "B. Chen", "metro_region": ""},
        ],
        required=REQUIRED,
    )
    assert quality.is_usable


def test_csv_null_sentinels_count_as_blank():
    """``nan``/``none``/``null`` are what a CSV export of a null field produces."""
    quality = validate_columns(
        "professionals",
        [{"full_name": "A", "metro_region": "nan"}, {"full_name": "B", "metro_region": "NULL"}],
        required=REQUIRED,
    )
    assert not quality.is_usable
    assert quality.errors[0].code == "required_column_entirely_blank"


def test_findings_accumulate_across_categories():
    quality = validate_columns(
        "professionals", [{"stray": "x"}], required=REQUIRED
    )
    codes = {f.code for f in quality.findings}
    assert "missing_required_columns" in codes
    assert "unexpected_columns" in codes


def test_severity_partitioning():
    quality = validate_columns(
        "professionals", [{"stray": "x"}], required=REQUIRED
    )
    assert all(f.severity is Severity.ERROR for f in quality.errors)
    assert all(f.severity is Severity.WARNING for f in quality.warnings)


def test_normalize_header_examples():
    assert normalize_header("  Metro-Region ") == "metro_region"
    assert normalize_header("Full Name") == "full_name"
    assert normalize_header("IA Event Date") == "ia_event_date"
