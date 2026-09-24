"""Owner ruling R-A (2026-09-24): the load block's schema has no load numbers.

The committed OpenAPI document is what a client is generated against. The
hours, the declared capacity and the utilization a band was computed from stay
in the stored run payload; no wire schema may offer a field for them.
"""

from __future__ import annotations

import json
from pathlib import Path

OPENAPI = Path(__file__).resolve().parents[2] / "contracts" / "openapi" / "smartmatch.json"
LOAD_NUMBER_FIELDS = frozenset(
    {"completed_hours", "confirmed_hours", "capacity_hours", "utilization"}
)


def _schemas() -> dict[str, dict]:
    return json.loads(OPENAPI.read_text(encoding="utf-8"))["components"]["schemas"]


def test_the_load_block_schema_is_band_and_reason_not_numbers() -> None:
    properties = set(_schemas()["LoadBlockView"]["properties"])
    assert properties == {"band", "reason", "measurable", "as_of", "eli_formula_version"}


def test_no_schema_on_the_wire_names_a_load_number() -> None:
    offenders = {
        name
        for name, schema in _schemas().items()
        if LOAD_NUMBER_FIELDS & set(schema.get("properties", {}))
    }
    assert offenders == set()
