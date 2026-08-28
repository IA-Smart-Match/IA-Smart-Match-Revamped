"""Fail-closed guards for matching/scoring until gate G1 closes."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from smartmatch_domain.factor_registry import REGISTRY_STATUS, assert_registry_approved

OPENAPI_PATH = Path(__file__).resolve().parents[2] / "contracts" / "openapi" / "smartmatch.json"

FORBIDDEN_PATH_PATTERNS = (
    re.compile(r"/match", re.I),
    re.compile(r"/score", re.I),
    re.compile(r"/rank", re.I),
    re.compile(r"/crawl", re.I),
)


def test_registry_status_remains_proposed():
    """G1 gate stays open — approval is a deliberate, reviewed commit."""
    assert REGISTRY_STATUS == "proposed"


def test_assert_registry_approved_still_raises():
    """Redundant with test_factor_registry but pins the public contract."""
    with pytest.raises(Exception):
        assert_registry_approved()


def test_openapi_exposes_no_match_scoring_or_crawler_routes():
    """No HTTP surface for scores, ranks, or crawler until respective gates close."""
    document = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    paths = document.get("paths", {})
    for path in paths:
        for pattern in FORBIDDEN_PATH_PATTERNS:
            assert not pattern.search(path), (
                f"forbidden route {path!r} in OpenAPI — gate G1/G3 not closed"
            )
