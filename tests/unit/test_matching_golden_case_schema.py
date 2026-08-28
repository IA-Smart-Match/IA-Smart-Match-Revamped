"""Golden-case input schema for gate G1 — structure only, no expected scores."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

GOLDEN_DIR = Path(__file__).resolve().parents[1] / "golden" / "matching"
SCHEMA_PATH = GOLDEN_DIR / "golden_case.schema.json"
SYMPTOM_DIR = GOLDEN_DIR / "symptoms"

REQUIRED_SYMPTOM_IDS = frozenset({"G1-GC-001", "G1-GC-002", "G1-GC-003"})


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _symptom_files() -> list[Path]:
    return sorted(SYMPTOM_DIR.glob("G1-GC-*.json"))


@pytest.mark.golden
def test_golden_case_schema_file_exists():
    assert SCHEMA_PATH.is_file()


@pytest.mark.golden
@pytest.mark.parametrize("path", _symptom_files(), ids=lambda p: p.stem)
def test_symptom_fixtures_have_required_shape(path: Path):
    """Input-only golden cases for the three stakeholder symptoms."""
    payload = _load_json(path)
    assert payload["id"].startswith("G1-GC-")
    assert payload["symptom_class"] in {"tie", "zero_or_unknown", "depth_zero"}
    assert payload["description"]
    assert "inputs" in payload
    assert "expected" not in payload, "expected scores forbidden until G1 closes"


@pytest.mark.golden
def test_all_three_stakeholder_symptoms_have_input_fixtures():
    ids = { _load_json(p)["id"] for p in _symptom_files() }
    assert REQUIRED_SYMPTOM_IDS <= ids


@pytest.mark.golden
def test_schema_declares_no_expected_scores_property():
    schema = _load_json(SCHEMA_PATH)
    expected_prop = schema["properties"]["expected"]
    assert "not" in expected_prop, "schema must forbid expected scores at prep time"
