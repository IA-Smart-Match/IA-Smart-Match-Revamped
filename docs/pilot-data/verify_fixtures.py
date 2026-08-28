"""Verify docs/pilot-data fixtures against the ratified column contract.

This script is a demonstration and a check, not application code: it loads
each fixture in ``docs/pilot-data/fixtures/``, runs
``smartmatch_domain.ingest.validate_columns`` against the column contract
ratified in ``docs/pilot-data/columns.yaml``, and asserts that the finding
codes match what ``docs/pilot-data/README.md`` claims for that fixture. It
does not import or modify anything in ``smartmatch_worker`` or
``smartmatch_api`` -- the ratified contract in ``columns.yaml`` is not wired
into either.

Run from the repository root with the repo venv:

    PYTHONPATH="python/smartmatch_domain" .venv/bin/python \\
        docs/pilot-data/verify_fixtures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from smartmatch_domain.ingest import DatasetQuality, validate_columns

PILOT_DATA_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = PILOT_DATA_DIR / "fixtures"
COLUMNS_PATH = PILOT_DATA_DIR / "columns.yaml"


def load_contract() -> dict[str, dict[str, Any]]:
    """Load the ratified per-dataset column contract."""
    with COLUMNS_PATH.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    return dict(raw["datasets"])


def load_rows(fixture_name: str) -> list[dict[str, Any]]:
    """Load one fixture's rows."""
    path = FIXTURES_DIR / fixture_name
    with path.open(encoding="utf-8") as handle:
        rows: list[dict[str, Any]] = json.load(handle)
    return rows


def run_validation(
    dataset: str,
    fixture_name: str,
    *,
    contract: dict[str, dict[str, Any]],
    blank_sentinels: tuple[str, ...] | None = None,
) -> DatasetQuality:
    """Validate one fixture's rows against ``dataset``'s ratified contract.

    ``blank_sentinels``, when given, replaces the contract's sentinel
    declarations *entirely* -- both the dataset-wide fallback and the
    per-column map -- with one global set applied to every column. That is
    deliberately the pre-ratification shape of the parameter, so this script
    can show the same rows validating differently under a global declaration,
    under a per-column one, and under none at all.
    """
    declared = contract[dataset]
    rows = load_rows(fixture_name)
    if blank_sentinels is not None:
        return validate_columns(
            dataset,
            rows,
            required=declared["required"],
            optional=declared["optional"],
            blank_sentinels=blank_sentinels,
        )
    return validate_columns(
        dataset,
        rows,
        required=declared["required"],
        optional=declared["optional"],
        blank_sentinels=declared["blank_sentinels"],
        blank_sentinels_by_column=declared["blank_sentinels_by_column"],
    )


def assert_codes(quality: DatasetQuality, expected: set[str], *, label: str) -> None:
    """Assert that exactly the expected finding codes were produced."""
    actual = {finding.code for finding in quality.findings}
    if actual != expected:
        raise AssertionError(
            f"{label}: expected finding codes {sorted(expected)}, got {sorted(actual)}"
        )
    print(f"  OK  {label}: codes={sorted(actual) or '(none)'} row_count={quality.row_count}")


def assert_per_column_sentinels_protect_the_name_column(
    contract: dict[str, dict[str, Any]],
) -> None:
    """Prove a sentinel can be a placeholder in one column and a value in another.

    ``professionals_null_surname_and_null_region.json`` holds three people
    surnamed "Null" whose metro_region is one of the export's null markers --
    the collision the pre-ratification contract could only flag in prose. Under
    one global set of sentinels, declaring "NULL" to clean up metro_region also
    blanks every one of those surnames, and validate_columns reports *both*
    columns as entirely blank. Under the ratified per-column declaration, the
    marker is honoured in metro_region and withheld from name, so exactly one
    column is reported and the surnames survive.
    """
    fixture = "professionals_null_surname_and_null_region.json"

    per_column = run_validation("professionals", fixture, contract=contract)
    blank_columns = {column for f in per_column.findings for column in f.columns}
    assert {f.code for f in per_column.findings} == {"required_column_entirely_blank"}, (
        f"{fixture}: expected only required_column_entirely_blank under the ratified "
        f"per-column contract; got {per_column.findings}"
    )
    assert blank_columns == {"metro_region"}, (
        f"{fixture}: the ratified contract declares 'NULL'/'nan'/'N/A' for metro_region "
        f"and withholds them from name, so only metro_region may be reported blank; "
        f"got {sorted(blank_columns)}"
    )
    print(
        f"  OK  {fixture} (ratified per-column sentinels): "
        "codes=['required_column_entirely_blank'] blank_columns=['metro_region'] "
        "-- the surname 'Null' survived"
    )

    # The same rows with those three tokens declared globally instead, which is
    # what the parameter could express before ratification.
    global_sentinels = run_validation(
        "professionals", fixture, contract=contract, blank_sentinels=("NULL", "nan", "N/A")
    )
    global_blank_columns = {column for f in global_sentinels.findings for column in f.columns}
    assert global_blank_columns == {"name", "metro_region"}, (
        f"{fixture}: one global sentinel set must blank BOTH columns -- that is the defect "
        f"per-column sentinels exist to fix; got {sorted(global_blank_columns)}"
    )
    print(
        f"  OK  {fixture} (one global sentinel set, pre-ratification shape): "
        "blank_columns=['metro_region', 'name'] -- the surname was clobbered, "
        "which is why the contract no longer declares sentinels this way"
    )


def main() -> int:
    contract = load_contract()

    print("professionals")
    assert_codes(
        run_validation("professionals", "professionals_clean.json", contract=contract),
        set(),
        label="professionals_clean.json",
    )
    assert_codes(
        run_validation("professionals", "professionals_missing_required.json", contract=contract),
        {"missing_required_columns"},
        label="professionals_missing_required.json",
    )
    ragged_quality = run_validation("professionals", "professionals_ragged.json", contract=contract)
    assert {f.code for f in ragged_quality.findings} == {"ragged_rows"}
    assert len(ragged_quality.findings) == 2, (
        "professionals_ragged.json should raise two ragged_rows findings "
        "(one warning for the optional column, one error for the required "
        f"column); got {ragged_quality.findings}"
    )
    severities = sorted(f.severity.value for f in ragged_quality.findings)
    print(
        "  OK  professionals_ragged.json: codes=['ragged_rows', 'ragged_rows'] "
        f"severities={severities}"
    )

    assert_codes(
        run_validation("professionals", "professionals_colliding_headers.json", contract=contract),
        {"colliding_headers"},
        label="professionals_colliding_headers.json",
    )
    assert_codes(
        run_validation(
            "professionals", "professionals_blank_required_column.json", contract=contract
        ),
        {"required_column_entirely_blank"},
        label="professionals_blank_required_column.json",
    )

    # Sentinel contrast: the SAME rows validate differently depending on
    # whether blank_sentinels is declared.
    assert_codes(
        run_validation("professionals", "professionals_null_sentinels.json", contract=contract),
        {"required_column_entirely_blank"},
        label="professionals_null_sentinels.json (sentinels declared, per ratified contract)",
    )
    assert_codes(
        run_validation(
            "professionals",
            "professionals_null_sentinels.json",
            contract=contract,
            blank_sentinels=(),
        ),
        set(),
        label="professionals_null_sentinels.json (blank_sentinels=(), no declaration)",
    )

    # "Null" and "None" are real values and must not be caught by a sentinel
    # declaration. This run declares nothing at all, which was the only way to
    # validate this fixture safely while sentinels were global -- the contract
    # itself would have blanked the surname.
    assert_codes(
        run_validation(
            "professionals",
            "professionals_literal_null_value.json",
            contract=contract,
            blank_sentinels=(),
        ),
        set(),
        label="professionals_literal_null_value.json (blank_sentinels=(), isolated from contract)",
    )
    # The same fixture against the FULL ratified contract, isolating nothing.
    # It passes now because the contract declares "NULL"/"nan"/"N/A" for
    # metro_region and explicitly withholds them from name.
    assert_codes(
        run_validation("professionals", "professionals_literal_null_value.json", contract=contract),
        set(),
        label="professionals_literal_null_value.json (full ratified contract, no isolation)",
    )

    # Per-column sentinels, the point of the mechanism: the same rows, the
    # same three tokens, declared two different ways.
    assert_per_column_sentinels_protect_the_name_column(contract)

    assert_codes(
        run_validation("professionals", "professionals_duplicates.json", contract=contract),
        set(),
        label="professionals_duplicates.json (column-valid; duplicates are an entity-resolution "
        "concern, not a validate_columns finding)",
    )

    print("events")
    assert_codes(
        run_validation("events", "events_clean.json", contract=contract),
        set(),
        label="events_clean.json",
    )
    assert_codes(
        run_validation("events", "events_missing_required.json", contract=contract),
        {"missing_required_columns"},
        label="events_missing_required.json",
    )
    events_ragged_quality = run_validation("events", "events_ragged.json", contract=contract)
    assert {f.code for f in events_ragged_quality.findings} == {"ragged_rows"}
    assert len(events_ragged_quality.findings) == 2, (
        "events_ragged.json should raise two ragged_rows findings (one "
        "warning for the optional column, one error for the required "
        f"column); got {events_ragged_quality.findings}"
    )
    print(
        "  OK  events_ragged.json: codes=['ragged_rows', 'ragged_rows'] "
        f"row_count={events_ragged_quality.row_count}"
    )
    assert_codes(
        run_validation("events", "events_colliding_headers.json", contract=contract),
        {"colliding_headers"},
        label="events_colliding_headers.json",
    )

    print("shared")
    assert_codes(
        run_validation("professionals", "empty_dataset.json", contract=contract),
        {"empty_dataset"},
        label="empty_dataset.json (validated as professionals)",
    )
    assert_codes(
        run_validation("events", "empty_dataset.json", contract=contract),
        {"empty_dataset"},
        label="empty_dataset.json (validated as events)",
    )

    print("\nAll fixtures produced the finding codes documented in README.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
