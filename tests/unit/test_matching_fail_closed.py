"""Executable fail-closed contracts for gated product surfaces.

G1 (matching/scoring), G3 (crawler/event catalog), and D6 (shippable rewards)
remain intentionally closed until named human decisions land. These tests pin
the absence of HTTP capability and domain guards without substituting for
workshop approval.

## The G3 event-catalog flip (card P-EVENTS-API)

Two read-only routes now exist where this file previously asserted none:
``GET /v1/units/{unit_id}/events`` and
``GET /v1/units/{unit_id}/tag-quarantine``. That is a deliberate flip, made in
the commit that lands the capability, which is the rule
``docs/plans/2026-08-28-plan-portfolio-index.md`` states for this file — "each
deliberate flip happens in the commit that lands the gated capability", naming
P6·S6b among the four that would do it — and the shape card S6b prescribes:
"routes, policy-matrix rows, OpenAPI regeneration, and the deliberate flip of
the fail-closed scan, all in one commit."

What the flip does **not** open is the part G3 actually gates. The forbidden
segment families below are untouched: no ``crawl``, ``crawler``, ``crawlers``
or ``discovery`` path may exist, ``POST /api/crawler/start`` remains a named
non-goal, and ``tests/unit/test_fixture_ingest_wiring.py`` still holds the API
away from the ingest reader entirely. The two routes admitted here read rows a
worker already wrote from committed fixtures; they trigger nothing, accept no
URL, and make no network call. :data:`G3_AUTHORIZED_EVENT_PATHS` is an exact,
literal allowlist of two paths rather than a loosened pattern, and
:func:`test_the_authorized_event_routes_are_read_only` holds them to being
reads — so this gate cannot widen into a command surface without failing here.
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


# G3 — the exact unit-scoped event paths card P-EVENTS-API authorizes, and no
# others. A literal set rather than a prefix or a pattern: a pattern would
# admit whatever a future route happened to hang under `/v1/units/*/events`,
# including a POST that triggered extraction, and the point of a fail-closed
# scan is that widening it is a visible edit to a named list. Both are reads,
# which `test_the_authorized_event_routes_are_read_only` checks rather than
# assumes.
G3_AUTHORIZED_EVENT_PATHS = frozenset(
    {
        "/v1/units/{unit_id}/events",
        "/v1/units/{unit_id}/tag-quarantine",
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

    # The two reads card P-EVENTS-API landed. Checked before the rule below
    # and by exact path, so every *other* unit-scoped event path stays refused
    # — including one that differed from these by a single segment.
    if path in G3_AUTHORIZED_EVENT_PATHS:
        return None

    # G3 unit-scoped event catalog — distinct from durable-command job lifecycle events.
    if "units" in segments:
        unit_index = segments.index("units")
        if unit_index + 1 < len(segments) and segments[unit_index + 1] == "events":
            return "G3"

    return None


def test_registry_status_is_approved():
    """G1 gate closed 2026-09-03 — Danny Tran ratified factor registry."""
    assert REGISTRY_STATUS == "approved"


def test_assert_registry_approved_succeeds():
    """G1 guard passes after program-owner approval."""
    assert_registry_approved()


def test_engagement_router_declares_no_handlers():
    """D6 is untouched by the G3 flip and still ships no handler at all."""
    assert engagement.router.routes == [], (
        "D6: engagement handlers must not ship before D6/D7 + S6/S7"
    )


def test_the_events_router_declares_exactly_the_authorized_routes():
    """The G3 flip is bounded by a list, not by the router's own contents.

    Before card P-EVENTS-API this asserted ``events.router.routes == []``. The
    honest successor is not "the events router may now declare things" — that
    would be a gate replaced by nothing — but an exact equality against
    :data:`G3_AUTHORIZED_EVENT_PATHS`. A third route added to this router fails
    here whether or not anyone regenerated the contract, which is the property
    the original assertion actually provided.
    """
    declared = {str(route.path) for route in events.router.routes}  # type: ignore[attr-defined]

    assert declared == G3_AUTHORIZED_EVENT_PATHS, (
        "G3: the events router declares routes outside the P-EVENTS-API "
        f"allowlist: {sorted(declared - G3_AUTHORIZED_EVENT_PATHS)}"
    )


def test_the_authorized_event_routes_are_read_only():
    """A read was authorized. A trigger was not.

    G3 §9 leaves API handlers "commands and review decisions only" and puts
    every network action worker-side, and card S6b makes an HTTP *command*
    surface conditional on a signed artifact calling for one — which none does.
    A ``POST`` under either of these paths would be that surface arriving
    without the artifact, so the methods are pinned rather than the paths
    alone.
    """
    offenders = sorted(
        f"{method} {route.path}"  # type: ignore[attr-defined]
        for route in events.router.routes
        for method in getattr(route, "methods", set())
        if method not in {"GET", "HEAD"}
    )

    assert offenders == [], f"G3: the events router is read-only; found {offenders}"


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
