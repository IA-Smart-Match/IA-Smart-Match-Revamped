"""Verify docs/pilot-data fixtures against the proposed column contract.

This script is a demonstration and a check, not application code: it loads
each fixture in ``docs/pilot-data/fixtures/``, runs
``smartmatch_domain.ingest.validate_columns`` against the column contract
proposed in ``docs/pilot-data/columns.yaml``, and asserts that the finding
codes match what ``docs/pilot-data/README.md`` claims for that fixture. It
does not import or modify anything in ``smartmatch_worker`` or
``smartmatch_api`` -- the proposed contract in ``columns.yaml`` is not wired
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
    """Load the proposed per-dataset column contract."""
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
    """Validate one fixture's rows against ``dataset``'s proposed contract.

    ``blank_sentinels`` overrides the contract's declared sentinels when
    given, so this script can demonstrate the same rows validating
    differently with and without them declared.
    """
    declared = contract[dataset]
    rows = load_rows(fixture_name)
    sentinels = declared["blank_sentinels"] if blank_sentinels is None else blank_sentinels
    return validate_columns(
        dataset,
        rows,
        required=declared["required"],
        optional=declared["optional"],
        blank_sentinels=sentinels,
    )


def assert_codes(quality: DatasetQuality, expected: set[str], *, label: str) -> None:
    """Assert that exactly the expected finding codes were produced."""
    actual = {finding.code for finding in quality.findings}
    if actual != expected:
        raise AssertionError(
            f"{label}: expected finding codes {sorted(expected)}, got {sorted(actual)}"
        )
    print(f"  OK  {label}: codes={sorted(actual) or '(none)'} row_count={quality.row_count}")


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
        label="professionals_null_sentinels.json (sentinels declared, per proposed contract)",
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
    # declaration. Validated with blank_sentinels=() specifically to keep it
    # isolated from the professionals contract's "NULL" sentinel (see
    # columns.yaml's open_questions for why that collision matters).
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
