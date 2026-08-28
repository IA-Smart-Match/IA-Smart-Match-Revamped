"""Tests for import validation (migration manifest MM-004)."""

from __future__ import annotations

import pytest
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
    quality = validate_columns("professionals", [{"full_name": "A. Rivera"}], required=REQUIRED)

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


def test_declared_null_sentinels_count_as_blank():
    """An adapter that knows its export writes ``nan`` for nulls says so."""
    quality = validate_columns(
        "professionals",
        [{"full_name": "A", "metro_region": "nan"}, {"full_name": "B", "metro_region": "NULL"}],
        required=REQUIRED,
        blank_sentinels=("nan", "null"),
    )
    assert not quality.is_usable
    assert quality.errors[0].code == "required_column_entirely_blank"


def test_null_and_none_are_values_unless_the_caller_declares_otherwise():
    """``Null`` and ``None`` are real surnames.

    The domain is handed already-parsed rows and cannot tell a source's null
    marker from a coordinator's data, so it does not guess: it rejects the
    import only for what is blank on its own face.
    """
    quality = validate_columns(
        "professionals",
        [{"full_name": "Null", "metro_region": "None"}],
        required=REQUIRED,
    )
    assert quality.is_usable
    assert quality.findings == ()


def test_findings_accumulate_across_categories():
    quality = validate_columns("professionals", [{"stray": "x"}], required=REQUIRED)
    codes = {f.code for f in quality.findings}
    assert "missing_required_columns" in codes
    assert "unexpected_columns" in codes


def test_severity_partitioning():
    quality = validate_columns("professionals", [{"stray": "x"}], required=REQUIRED)
    assert all(f.severity is Severity.ERROR for f in quality.errors)
    assert all(f.severity is Severity.WARNING for f in quality.warnings)


def test_normalize_header_examples():
    assert normalize_header("  Metro-Region ") == "metro_region"
    assert normalize_header("Full Name") == "full_name"
    assert normalize_header("IA Event Date") == "ia_event_date"


# ---------------------------------------------------------------------------
# Ragged rows (F-15)
# ---------------------------------------------------------------------------


def test_verdict_does_not_depend_on_row_order():
    """The same rows in either order must produce the same verdict.

    The column set was read from ``rows[0]`` alone, so a ragged import was
    rejected or accepted according to which row the exporter happened to emit
    first — a fail-closed control failing open on row order.
    """
    complete = {"full_name": "A. Rivera", "metro_region": "Inland Empire"}
    ragged = {"full_name": "B. Chen"}

    complete_first = validate_columns("professionals", [complete, ragged], required=REQUIRED)
    ragged_first = validate_columns("professionals", [ragged, complete], required=REQUIRED)

    assert complete_first.is_usable == ragged_first.is_usable
    assert {f.code for f in complete_first.findings} == {f.code for f in ragged_first.findings}


def test_required_column_absent_from_some_rows_fails_closed():
    """Present in row 0 is not present in the dataset."""
    quality = validate_columns(
        "professionals",
        [
            {"full_name": "A. Rivera", "metro_region": "Inland Empire"},
            {"full_name": "B. Chen"},
        ],
        required=REQUIRED,
    )
    assert not quality.is_usable
    finding = quality.errors[0]
    assert finding.code == "ragged_rows"
    assert finding.columns == ("metro_region",)
    assert "1 row(s)" in finding.message


def test_ragged_optional_column_warns_but_does_not_block():
    """Raggedness outside the required set is a quality signal, not a stop."""
    quality = validate_columns(
        "professionals",
        [
            {"full_name": "A. Rivera", "metro_region": "IE", "pronouns": "they/them"},
            {"full_name": "B. Chen", "metro_region": "IE"},
        ],
        required=REQUIRED,
        optional=("pronouns",),
    )
    assert quality.is_usable
    assert quality.warnings[0].code == "ragged_rows"
    assert quality.warnings[0].columns == ("pronouns",)


# ---------------------------------------------------------------------------
# Header reporting (F-17)
# ---------------------------------------------------------------------------


def test_findings_quote_the_coordinators_own_header():
    """A finding must name a string the coordinator can find in their file."""
    quality = validate_columns(
        "professionals",
        [{"full_name": "A", "metro_region": "IE", "Internal Note!": "x"}],
        required=REQUIRED,
    )
    finding = quality.warnings[0]
    assert finding.columns == ("Internal Note!",)
    assert "Internal Note!" in finding.message


def test_headers_colliding_on_a_required_column_fail_closed():
    """Two spellings of one required column: the second value is dropped."""
    quality = validate_columns(
        "professionals",
        [{"Full Name": "A. Rivera", "full_name": "B. Chen", "metro_region": "IE"}],
        required=REQUIRED,
    )
    assert not quality.is_usable
    finding = quality.errors[0]
    assert finding.code == "colliding_headers"
    assert finding.columns == ("Full Name", "full_name")


def test_headers_colliding_outside_the_required_set_warn():
    quality = validate_columns(
        "professionals",
        [{"full_name": "A", "metro_region": "IE", "Pronouns": "they", "pronouns": "she"}],
        required=REQUIRED,
        optional=("pronouns",),
    )
    assert quality.is_usable
    assert quality.warnings[0].code == "colliding_headers"


def test_duplicate_declared_columns_are_a_caller_error():
    """A column declared twice would collapse silently and validate one spelling."""
    with pytest.raises(ValueError, match="after normalization"):
        validate_columns(
            "professionals",
            [{"full_name": "A", "metro_region": "IE"}],
            required=("full_name", "Full Name", "metro_region"),
        )


# ---------------------------------------------------------------------------
# Per-column blank sentinels
#
# One sentinel set for the whole dataset could not say that "NULL" is a
# placeholder in metro_region and a surname in the name column, so declaring it
# for the first blanked the second — in every field on that person's row. See
# docs/pilot-data/columns.yaml (ratified 28 Aug 2026, decision 2) and the
# fixture professionals_null_surname_and_null_region.json it cites.
# ---------------------------------------------------------------------------

NAME_REQUIRED = ("name", "metro_region")


def test_per_column_sentinels_apply_only_to_the_column_that_declares_them():
    """The defect this parameter exists to fix, stated as one assertion.

    Every row's ``metro_region`` is a null marker and every row's ``name`` is
    the surname "Null". Declaring the markers for ``metro_region`` alone must
    report that column blank and leave the surname alone.
    """
    rows = [
        {"name": "Null", "metro_region": "NULL"},
        {"name": "Null", "metro_region": "nan"},
    ]
    quality = validate_columns(
        "professionals",
        rows,
        required=NAME_REQUIRED,
        blank_sentinels_by_column={"metro_region": ("NULL", "nan", "N/A")},
    )
    assert not quality.is_usable
    blank = [f for f in quality.findings if f.code == "required_column_entirely_blank"]
    assert [f.columns for f in blank] == [("metro_region",)]


def test_one_global_sentinel_set_still_blanks_every_column():
    """The old shape, kept working and kept honest about what it does.

    The same rows with the same tokens declared globally blank the surname too.
    This is not a bug being preserved — it is what a global declaration means,
    and it is why the pilot contract declares sentinels per column instead.
    """
    rows = [
        {"name": "Null", "metro_region": "NULL"},
        {"name": "Null", "metro_region": "nan"},
    ]
    quality = validate_columns(
        "professionals",
        rows,
        required=NAME_REQUIRED,
        blank_sentinels=("NULL", "nan", "N/A"),
    )
    blanked = {column for f in quality.findings for column in f.columns}
    assert blanked == {"name", "metro_region"}


def test_a_column_may_opt_out_of_the_dataset_wide_sentinels():
    """An empty declaration is a real declaration, not an absent one.

    A caller that must keep a dataset-wide set — an existing contract, say —
    can still exempt one column from it. The per-column set replaces the
    global set for that column rather than adding to it, so ``()`` means none.
    """
    rows = [{"name": "Null", "metro_region": "Inland Empire"}]
    quality = validate_columns(
        "professionals",
        rows,
        required=NAME_REQUIRED,
        blank_sentinels=("NULL",),
        blank_sentinels_by_column={"name": ()},
    )
    assert quality.is_usable
    assert quality.findings == ()


def test_per_column_sentinels_replace_rather_than_extend_the_global_set():
    """Declaring one token for a column does not silently keep the others."""
    rows = [{"name": "A. Rivera", "metro_region": "nan"}]
    quality = validate_columns(
        "professionals",
        rows,
        required=NAME_REQUIRED,
        blank_sentinels=("nan",),
        blank_sentinels_by_column={"metro_region": ("NULL",)},
    )
    assert quality.is_usable


def test_columns_without_a_declaration_fall_back_to_the_global_set():
    quality = validate_columns(
        "professionals",
        [{"name": "A. Rivera", "metro_region": "nan"}],
        required=NAME_REQUIRED,
        blank_sentinels=("nan",),
        blank_sentinels_by_column={"name": ()},
    )
    assert not quality.is_usable
    assert quality.errors[0].code == "required_column_entirely_blank"
    assert quality.errors[0].columns == ("metro_region",)


def test_per_column_sentinel_keys_are_normalized_like_every_other_header():
    quality = validate_columns(
        "professionals",
        [{"name": "A. Rivera", "  Metro-Region ": "NULL"}],
        required=NAME_REQUIRED,
        blank_sentinels_by_column={"Metro Region": ("null",)},
    )
    assert not quality.is_usable
    assert quality.errors[0].code == "required_column_entirely_blank"


def test_sentinels_for_an_undeclared_column_are_a_caller_error():
    """A declaration nothing consults would leave a caller falsely reassured."""
    with pytest.raises(ValueError, match="neither required nor optional"):
        validate_columns(
            "professionals",
            [{"name": "A. Rivera", "metro_region": "IE"}],
            required=NAME_REQUIRED,
            blank_sentinels_by_column={"mtro_region": ("NULL",)},
        )


def test_two_spellings_of_one_column_in_the_sentinel_map_are_a_caller_error():
    """One declaration would overwrite the other; which one wins is not a policy."""
    with pytest.raises(ValueError, match="after normalization"):
        validate_columns(
            "professionals",
            [{"name": "A. Rivera", "metro_region": "IE"}],
            required=NAME_REQUIRED,
            blank_sentinels_by_column={"metro_region": ("NULL",), "Metro Region": ()},
        )


def test_omitting_the_new_parameter_leaves_existing_callers_unchanged():
    """The parameter is additive: the old call shape must behave identically.

    ``smartmatch_worker.handlers`` calls ``validate_columns`` without it.
    """
    rows = [{"full_name": "Null", "metro_region": "NULL"}]
    without = validate_columns("professionals", rows, required=REQUIRED)
    explicit_none = validate_columns(
        "professionals", rows, required=REQUIRED, blank_sentinels_by_column=None
    )
    assert without.findings == explicit_none.findings == ()
