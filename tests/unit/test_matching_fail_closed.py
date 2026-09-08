"""Executable fail-closed contracts for gated product surfaces.

G1 (matching/scoring), G3 (crawler/discovery), and D6 (shippable rewards)
remain intentionally closed until named human decisions land. These tests pin
the absence of HTTP capability and domain guards without substituting for
workshop approval.
"""

from __future__ import annotations

import json
from pathlib import Path

from smartmatch_api.routers import engagement, events
from smartmatch_domain.factor_registry import (
    REGISTRY_STATUS,
    assert_registry_approved,
)

OPENAPI_PATH = Path(__file__).resolve().parents[2] / "contracts" / "openapi" / "smartmatch.json"

# G1 — forbidden path segments until D1/G1 program owner approves the registry.
_G1_FORBIDDEN_SEGMENTS = frozenset(
    {
        "match",
        "matches",
        "matching",
        "score",
        "scores",
        "scoring",
        "rank",
        "ranks",
        "ranking",
    }
)

# G3 — forbidden path segments until G3 control decision + R3 threat-model sign-off.
_G3_FORBIDDEN_SEGMENTS = frozenset(
    {
        "crawl",
        "crawler",
        "crawlers",
        "discovery",
    }
)

# D6 — forbidden path segments until D6/D7 budget owners ratify catalog + S6/S7 exist.
_D6_FORBIDDEN_SEGMENTS = frozenset(
    {
        "reward",
        "rewards",
        "redemption",
        "redemptions",
        "balance",
        "balances",
        "catalog",
    }
)


def _path_segments(path: str) -> list[str]:
    """Return literal path segments, ignoring ``{param}`` placeholders."""
    return [
        segment for segment in path.strip("/").split("/") if segment and not segment.startswith("{")
    ]


def _forbidden_gate_for_path(path: str) -> str | None:
    """Return the gate id blocking ``path``, or None when the path is allowed."""
    segments = [segment.lower() for segment in _path_segments(path)]

    for segment in segments:
        if segment in _G1_FORBIDDEN_SEGMENTS:
            return "G1"
        if segment in _G3_FORBIDDEN_SEGMENTS:
            return "G3"
        if segment in _D6_FORBIDDEN_SEGMENTS:
            return "D6"

    return None


def test_registry_status_is_approved():
    """G1 gate closed 2026-09-03 — Danny Tran ratified factor registry."""
    assert REGISTRY_STATUS == "approved"


def test_assert_registry_approved_succeeds():
    """G1 guard passes after program-owner approval."""
    assert_registry_approved()


def test_manual_events_do_not_reopen_crawler_routes_and_engagement_stays_closed():
    """Manual event entry is authorized without opening crawler or rewards gates."""
    event_paths = {route.path for route in (*events.router.routes, *events.public_router.routes)}
    assert event_paths
    assert all(
        not (set(_path_segments(path)) & _G3_FORBIDDEN_SEGMENTS) for path in event_paths
    ), "G3: manual event entry must not expose crawl or discovery routes"
    assert engagement.router.routes == [], (
        "D6: engagement handlers must not ship before D6/D7 + S6/S7"
    )


def test_openapi_exposes_no_gated_product_surface_routes():
    """No HTTP surface for match/score/rank, crawl/discovery, or rewards until gates close."""
    document = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    paths = document.get("paths", {})
    for path in paths:
        gate = _forbidden_gate_for_path(path)
        assert gate is None, (
            f"forbidden route {path!r} in OpenAPI — gate {gate} not closed "
            f"(check path segments, not descriptions)"
        )
